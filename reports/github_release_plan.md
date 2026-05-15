# GitHub Release Plan

Project positioning:

**AI Native Multi-Agent Market Runtime**

Do not present this repository as an automatic money-making system, AI crypto trading system, high-frequency arbitrage system, or quant fund platform.

## Suitable For Public Release

These areas are suitable for a sanitized public repository:

- `agents/` active runtime agents and clearly labeled inactive experiments
- `collectors/` source code without credentials
- `executors/` dry-run guarded execution code
- `risk/` lightweight risk snapshot code
- `scripts/` operational scripts after removing stale backups
- `tests/`
- root entrypoints such as `main.py`, `orchestrator.py`, `_paths.py`, `llm_helper.py`
- documentation:
  - `SYSTEM_ARCHITECTURE.md`
  - `AGENT_PIPELINE.md`
  - `DRY_RUN_VALIDATION.md`
  - `LIMITATIONS.md`
  - selected `reports/*.md` that do not contain secrets

## Not Suitable For Public Release

Do not publish:

- `config/llm_config.json`
- any API keys, proxy keys, account IDs, wallet credentials, cookies, or private endpoints
- `data/` runtime outputs
- `logs/`
- `backups/`
- local virtual environments
- `.env` files
- `.claude/settings.json` or other machine-specific tool settings
- stale backup scripts such as `scripts/monitor_2h.sh.bak_before_14h`
- generated cache folders
- private operational handoff notes if they include credentials or machine paths

## Suggested `.gitignore`

```gitignore
# Secrets and local config
config/llm_config.json
config/*.bak
.env
.env.*

# Runtime output
data/
logs/
backups/

# Local tool settings
.claude/settings.json
.claude/settings.local.json
.claude/*.bak*

# Python
__pycache__/
*.pyc
*.pyo
*.pyd
*.egg-info/
dist/
build/
.pytest_cache/

# Environments
venv/
.venv/

# Backups and local artifacts
*.bak
*.bak_*
*.bak-before-*
*.bak_before_*
*.backup
*.disabled
*.log
.DS_Store
```

## README Structure Recommendation

Recommended README sections:

1. Project Name: AI Native Multi-Agent Market Runtime
2. What This Is
3. What This Is Not
4. Architecture Overview
5. 18-Step Pipeline
6. Dry-Run Safety
7. Risk Layer
8. Learning Bridge
9. Running Locally In Dry-Run
10. Configuration And Secrets
11. Current Limitations
12. Repository Layout
13. Development Status

## Correct Public Description

Use language like:

> A dry-run-first AI native multi-agent runtime for market data collection, signal research, risk review, simulated execution, and learning feedback.

Avoid language like:

- automatic profit engine
- AI crypto trader
- high-frequency arbitrage system
- quant fund platform
- guaranteed alpha

## Release Checklist

- Confirm `git status --short` is clean.
- Remove or sanitize `.claude/settings.json`.
- Remove stale backup scripts from the public release index.
- Verify no `data/`, `logs/`, `.env`, or `config/llm_config.json` files are tracked.
- Keep `LIMITATIONS.md` visible at repo root.
- Keep dry-run setup as the default documented mode.
