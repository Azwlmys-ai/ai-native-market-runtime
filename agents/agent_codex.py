#!/usr/bin/env python3
"""
Agent Codex - deployment code review gate.

Reviews development changes against a Hermes session requirement before release.
It does not modify code, deploy, start containers, or place orders.
"""

import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _paths import get_base_dir
from llm_helper import call_llm_sync


DEFAULT_REVIEW_REQUEST = "data/codex_review_request.json"
DEFAULT_REVIEW_OUTPUT = "data/codex_review_results.json"
DEFAULT_DEPLOY_GATE = "data/deployment_gate.json"
MAX_FILE_CHARS = 30000
MAX_DIFF_CHARS = 50000
REVIEW_DECISIONS = {"APPROVE", "CHANGES_REQUESTED", "BLOCKED"}


class RequestValidationError(ValueError):
    pass


class AgentCodex:
    def __init__(self, base_dir=None, request_file=None, output_file=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.data_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        self.request_file = Path(request_file) if request_file else self.base_dir / DEFAULT_REVIEW_REQUEST
        self.output_file = Path(output_file) if output_file else self.base_dir / DEFAULT_REVIEW_OUTPUT
        self.gate_file = self.base_dir / DEFAULT_DEPLOY_GATE

    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] [Agent Codex] {message}"
        print(line, flush=True)
        with open(self.logs_dir / f"agent_codex_{datetime.now().strftime('%Y%m%d')}.log", "a") as f:
            f.write(line + "\n")

    def load_request(self):
        if self.request_file.exists():
            with open(self.request_file, "r") as f:
                request = json.load(f)
        else:
            request = {}

        if not isinstance(request, dict):
            raise RequestValidationError("review request must be a JSON object")

        files = request.get("files", [])
        tests = request.get("tests", [])
        if not isinstance(files, list) or not all(isinstance(item, str) for item in files):
            raise RequestValidationError("request.files must be a list of strings")
        if not isinstance(tests, list) or not all(isinstance(item, str) for item in tests):
            raise RequestValidationError("request.tests must be a list of strings")

        return {
            "requirements": request.get("requirements", ""),
            "summary": request.get("summary", ""),
            "files": files,
            "tests": tests,
            "release_target": request.get("release_target", "hermes"),
            "notify_to": request.get("notify_to", "hermes"),
        }

    def collect_git_diff(self):
        """Return (kind, content).

        kind ∈ {"ok", "absent", "unavailable", "failed"}:
          - "ok"          → git diff ran cleanly; content is the diff (may be empty for a clean tree)
          - "absent"      → base_dir is not a git repo
          - "unavailable" → subprocess raised; content is a "[git diff unavailable: …]" placeholder
          - "failed"      → git exited non-zero; content is a "[git diff failed: …]" placeholder

        Callers MUST treat only kind=="ok" with non-empty content as real
        review material — placeholder strings are non-empty but carry no
        review value, so they cannot be used to satisfy the
        "空 files + 无 git diff → BLOCKED 且不调用 LLM" fail-closed contract.
        """
        if not (self.base_dir / ".git").exists():
            return ("absent", "")

        try:
            result = subprocess.run(
                ["git", "diff", "--", "."],
                cwd=str(self.base_dir),
                capture_output=True,
                text=True,
                timeout=20,
            )
        except Exception as exc:
            return ("unavailable", f"[git diff unavailable: {exc}]")

        if result.returncode != 0:
            return ("failed", f"[git diff failed: {result.stderr.strip()}]")
        return ("ok", result.stdout[:MAX_DIFF_CHARS])

    def collect_file_context(self, files):
        chunks = []
        for item in files:
            path = (self.base_dir / item).resolve()
            try:
                path.relative_to(self.base_dir.resolve())
            except ValueError:
                chunks.append(f"\n### {item}\n[skipped: outside project root]")
                continue

            if not path.exists() or not path.is_file():
                chunks.append(f"\n### {item}\n[missing]")
                continue

            try:
                text = path.read_text(errors="replace")
            except Exception as exc:
                chunks.append(f"\n### {item}\n[unreadable: {exc}]")
                continue

            truncated = False
            if len(text) > MAX_FILE_CHARS:
                text = text[:MAX_FILE_CHARS]
                truncated = True
            numbered = "\n".join(
                f"{line_no:5} | {line}" for line_no, line in enumerate(text.splitlines(), 1)
            )
            if truncated:
                numbered += "\n[truncated]"
            chunks.append(f"\n### {item}\n```text\n{numbered}\n```")
        return "\n".join(chunks)

    def build_prompt(self, request, diff_text, file_context):
        tests_text = "\n".join(f"- {item}" for item in request["tests"]) or "[未声明测试]"
        return f"""
你是 Agent Codex，一个发布前代码审核员。主 Hermes 模型负责需求和产品判断；
你的职责是独立审核代码是否满足会话要求，是否存在发布/部署风险。

会话要求:
{request['requirements'] or '[未提供明确要求]'}

开发摘要:
{request['summary'] or '[未提供开发摘要]'}

目标发布对象:
{request['release_target']}

开发者声明的测试要求:
{tests_text}

Git diff:
```diff
{diff_text or '[无 git diff；请基于文件上下文审查]'}
```

文件上下文:
{file_context or '[未提供文件列表]'}

请以代码审查方式输出 JSON，字段必须为:
{{
  "decision": "APPROVE | CHANGES_REQUESTED | BLOCKED",
  "summary": "一句话结论",
  "findings": [
    {{
      "severity": "P0 | P1 | P2 | P3",
      "file": "相对路径",
      "line": 0,
      "title": "问题标题",
      "detail": "为什么这是问题，以及建议怎么改"
    }}
  ],
  "required_tests": ["发布前必须跑的测试或检查"],
  "deployment_notes": ["发布/回滚/运行时注意事项"],
  "message_to_hermes": "给 Hermes 主模型看的简短中文审核意见"
}}

判定规则:
- 有 P0/P1 或会真实下单、泄露密钥、破坏状态/数据的风险: BLOCKED
- 有需要修改但不阻断安全的缺陷: CHANGES_REQUESTED
- 没有明显问题且测试要求明确: APPROVE
- 若开发者声明的关键测试缺失、未覆盖或未运行: 至少 CHANGES_REQUESTED
- 若文件上下文出现 [truncated]，不要 APPROVE；要求补充完整上下文后复审
- 不要给空泛建议；问题要能落到文件、行为或测试缺口。
"""

    def blocked_review(self, summary, detail, severity="P1"):
        return {
            "decision": "BLOCKED",
            "summary": summary,
            "findings": [
                {
                    "severity": severity,
                    "file": "",
                    "line": 0,
                    "title": summary,
                    "detail": detail,
                }
            ],
            "required_tests": [],
            "deployment_notes": ["发布 gate 失败关闭；修复后重新运行 Agent Codex。"],
            "message_to_hermes": f"Agent Codex 阻止发布: {summary}",
        }

    def _blocked_template(self, title, detail):
        return {
            "decision": "BLOCKED",
            "summary": "Agent Codex 未能解析结构化输出",
            "findings": [
                {
                    "severity": "P1",
                    "file": "",
                    "line": 0,
                    "title": title,
                    "detail": detail[:2000],
                }
            ],
            "required_tests": [],
            "deployment_notes": ["LLM 输出不合规;修复后重新运行 Agent Codex。"],
            "message_to_hermes": f"Agent Codex 阻止发布: {title}",
        }

    def parse_review(self, response):
        # Non-JSON or unparseable → BLOCKED (fail-closed)
        try:
            start = response.index("{")
            end = response.rindex("}") + 1
            data = json.loads(response[start:end])
        except Exception:
            return self._blocked_template("非 JSON 审核输出", response or "")

        # JSON but not an object → BLOCKED
        if not isinstance(data, dict):
            return self._blocked_template("审核输出不是 JSON object", str(data)[:2000])

        # Invalid / missing decision → BLOCKED (per project policy: fail-closed
        # rather than CHANGES_REQUESTED, because we don't actually know what
        # the model meant).
        decision = data.get("decision")
        if decision not in REVIEW_DECISIONS:
            return self._blocked_template(
                f"非法 decision={decision!r}",
                json.dumps(data, ensure_ascii=False)[:2000],
            )

        # Normalize collection / string fields so downstream code is safe.
        for key in ("findings", "required_tests", "deployment_notes"):
            if not isinstance(data.get(key), list):
                data[key] = []
        if not isinstance(data.get("summary"), str):
            data["summary"] = ""
        if not isinstance(data.get("message_to_hermes"), str):
            data["message_to_hermes"] = data.get("summary") or "Agent Codex 审核完成"
        return data

    def atomic_write_json(self, path, data):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f".{path.name}.tmp.{os.getpid()}.{time.time_ns()}")
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)

    def write_pending_gate(self):
        """Write a BLOCKED placeholder gate before doing any review work.

        Defense-in-depth: if the process crashes mid-review (SIGKILL, OOM,
        unhandled exception before save_result), any stale 'open' gate from a
        previous run is replaced with 'blocked' so deployment is fail-closed.
        """
        pending = {
            "timestamp": datetime.now().isoformat(),
            "status": "blocked",
            "decision": "BLOCKED",
            "summary": "Agent Codex 审核进行中(pending)",
            "findings_count": 0,
            "p0_count": 0,
            "p1_count": 0,
            "review_file": str(self.output_file),
            "release_target": "",
            "tests_declared": [],
            "required_tests": [],
            "pending": True,
        }
        self.atomic_write_json(self.gate_file, pending)

    def save_result(self, request, review):
        payload = {
            "timestamp": datetime.now().isoformat(),
            "agent": "agent_codex",
            "request_file": str(self.request_file),
            "release_target": request["release_target"],
            "tests_declared": request["tests"],
            "decision": review["decision"],
            "review": review,
        }
        self.atomic_write_json(self.output_file, payload)

        findings = review.get("findings", [])
        p0_count = sum(1 for item in findings if item.get("severity") == "P0")
        p1_count = sum(1 for item in findings if item.get("severity") == "P1")

        gate = {
            "timestamp": payload["timestamp"],
            "status": "open" if review["decision"] == "APPROVE" else "blocked",
            "decision": review["decision"],
            "summary": review.get("summary", ""),
            "findings_count": len(findings),
            "p0_count": p0_count,
            "p1_count": p1_count,
            "review_file": str(self.output_file),
            "release_target": request["release_target"],
            "tests_declared": request["tests"],
            "required_tests": review.get("required_tests", []),
        }
        self.atomic_write_json(self.gate_file, gate)
        return payload

    def shared_dir(self):
        candidates = [
            Path(self.base_dir).parent / "shared",
            Path.home() / ".hermes" / "shared",
        ]
        for path in candidates:
            if path.exists():
                return path
        path = Path.home() / ".hermes" / "shared"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def notify_hermes(self, request, payload):
        messages_file = self.shared_dir() / "messages.json"
        review = payload["review"]
        message = {
            "id": f"msg_agent_codex_{int(time.time() * 1000)}_{os.getpid()}",
            "from": "agent_codex",
            "to": request["notify_to"],
            "type": "code_review",
            "content": review["message_to_hermes"],
            "priority": "urgent" if review["decision"] == "BLOCKED" else "high",
            "timestamp": datetime.now().isoformat(),
            "read": False,
            "metadata": {
                "decision": review["decision"],
                "review_file": str(self.output_file),
                "gate_file": str(self.gate_file),
                "tests_declared": request["tests"],
                "required_tests": review.get("required_tests", []),
            },
        }

        messages_file.parent.mkdir(parents=True, exist_ok=True)
        lock_file = messages_file.with_suffix(messages_file.suffix + ".lock")
        with open(lock_file, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if messages_file.exists():
                with open(messages_file, "r") as f:
                    data = json.load(f)
            else:
                data = {"messages": []}

            if not isinstance(data, dict) or not isinstance(data.get("messages"), list):
                raise ValueError(f"invalid Hermes messages file: {messages_file}")

            data["messages"].append(message)
            self.atomic_write_json(messages_file, data)
        return message

    def run(self):
        # Step 0 — pre-emptively replace any stale 'open' gate with BLOCKED.
        # If we crash mid-review, deployment stays fail-closed.
        self.write_pending_gate()

        request = {
            "requirements": "",
            "summary": "",
            "files": [],
            "tests": [],
            "release_target": "hermes",
            "notify_to": "hermes",
        }

        self.log("开始代码审核")
        try:
            request = self.load_request()
            diff_kind, diff_text = self.collect_git_diff()
            file_context = self.collect_file_context(request["files"])

            # Strict fail-closed contract: only count actual review material.
            # File context counts when ANY files were declared (even missing /
            # unreadable / outside-project entries — declaration = intent to
            # review). Diff content counts only when git ran cleanly AND
            # produced non-empty output; an "[git diff unavailable]" or
            # "[git diff failed]" placeholder is non-empty but carries no
            # review value, so it must NOT satisfy the gate.
            has_file_context = bool(file_context.strip())
            has_diff_content = diff_kind == "ok" and bool(diff_text.strip())

            if not has_file_context and not has_diff_content:
                review = self.blocked_review(
                    "空审核请求",
                    (
                        "Agent Codex 没有收到 files 列表，且 git diff 状态="
                        f"{diff_kind}（内容长度={len(diff_text)}）；"
                        "无法进行发布前审核。"
                    ),
                )
            else:
                prompt = self.build_prompt(request, diff_text, file_context)
                response = call_llm_sync("agent_codex", prompt, timeout=120, temperature=0.1)
                review = self.parse_review(response)
        except Exception as exc:
            review = self.blocked_review(
                "Agent Codex 审核失败",
                f"发布 gate fail-closed: {exc}",
                severity="P0",
            )

        payload = self.save_result(request, review)

        # Step N — notify Hermes. If notification itself fails (e.g. corrupt
        # messages.json, full disk, broken lock), force the gate back to
        # BLOCKED and re-raise so the process exits non-zero. This guarantees:
        #  - deployment_gate.json is BLOCKED on disk
        #  - codex_review_results.json reflects the failure reason
        #  - the caller sees a non-zero exit
        try:
            message = self.notify_hermes(request, payload)
        except Exception as exc:
            self.log(f"notify_hermes 失败,强制 gate=BLOCKED 后非零退出: {exc}")
            fail_review = self.blocked_review(
                "Hermes 通知失败",
                (
                    "Agent Codex 已生成审核结论但无法通知 Hermes；"
                    f"deployment_gate 已强制 blocked: {exc}"
                ),
                severity="P0",
            )
            self.save_result(request, fail_review)
            raise

        self.log(f"审核完成: {review['decision']}，已通知 {message['to']}")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return payload


def main():
    parser = argparse.ArgumentParser(description="Run Agent Codex code review gate")
    parser.add_argument("--request", default=None, help="Review request JSON file")
    parser.add_argument("--output", default=None, help="Review output JSON file")
    args = parser.parse_args()

    payload = AgentCodex(request_file=args.request, output_file=args.output).run()
    # Non-APPROVE exits non-zero so CI / launchd / wrappers can tell whether
    # the gate is open without parsing JSON.
    if payload.get("decision") != "APPROVE":
        sys.exit(1)


if __name__ == "__main__":
    main()
