# Git Cleanup Review

Date: 2026-05-15

## Command

```bash
git status --short
```

Result: clean working tree. No untracked runtime files are currently pending.

## Runtime Garbage Check

The current `.gitignore` already excludes the main runtime and local-only paths:

- `logs/`
- `data/`
- `backups/`
- `venv/`, `.venv/`
- `.env`, `.env.*`
- `__pycache__/`, `*.pyc`
- `.pytest_cache/`
- `*.log`
- `*.backup`
- `*.disabled`
- `config/llm_config.json`
- `config/*.bak`

## Tracked Items To Review Before Public Release

These are already tracked by Git, so adding them to `.gitignore` alone will not remove them from history or from the index:

| Path | Type | Risk | Recommendation |
|---|---|---|---|
| `.claude/settings.json` | local tool settings | machine/local workflow metadata | remove from public release index or replace with a sanitized example |
| `scripts/monitor_2h.sh.bak_before_14h` | backup script | stale monitor config has `TOTAL_CYCLES=56` and can confuse release users | exclude from public release package or move to archival notes |
| `review_cache.py` | source module, not cache garbage | no cleanup needed | keep |

## Minimal Ignore Suggestions

For future local files, add or keep these patterns in a release branch:

```gitignore
.claude/settings.json
.claude/settings.local.json
.claude/*.bak*
*.bak
*.bak_*
*.bak-before-*
*.bak_before_*
logs/
data/
backups/
.pytest_cache/
__pycache__/
*.pyc
.env
.env.*
venv/
.venv/
config/llm_config.json
config/*.bak
```

## Cleanup Decision

No files were deleted in this review. No business code was changed. The working tree was clean before documentation generation.
