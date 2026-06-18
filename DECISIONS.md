# DECISIONS.md — pr-reviewer Hardening Showcase

> This file is the source of truth for all architectural decisions in this project.
> It is updated as the codebase evolves.

## Technology Stack
- **Language**: Python 3.12+
- **HTTP Client**: `requests`
- **Secrets Management**: Plaintext `.env` (v1) and `agentsecrets` SDK + Local Proxy (v2)
- **APIs**: GitHub REST API v3, Google Gemini API (or compatible LLM interface)
- **Target Platform**: WSL (Ubuntu) / Linux

## Active ADRs
| ADR ID | Title | Status | Chapter |
|--------|-------|--------|---------|
| ADR-001 | Direct API Calls with Plaintext Keys (v1) | Accepted | Ch. 3 |
| ADR-002 | Zero-Knowledge Egress via AgentSecrets SDK (v2) | Accepted | Ch. 3 |

## Entity Registry
| Entity | Attributes | Notes |
|--------|------------|-------|
| `PullRequest` | `number`, `state`, `title`, `diff_url`, `base_repo`, `head_sha` | Extracted from GitHub REST API pulls list. |
| `CodeReview` | `summary`, `decision` (`APPROVE` / `REJECT`), `raw_output` | Output of the LLM diff analysis. |

## Pattern Usage
| Pattern | Applied In | Chapter |
|---------|-----------|---------|
| Direct Configuration | `v1_unsecured` | Ch. 4 |
| Zero-Knowledge Injection | `v2_agentsecrets_core` | Ch. 5 |

## Incident Record (Observed Baseline Failure)
- **Date**: 2026-06-19
- **Scenario**: A pull request containing attacker-influenced content caused the unsecured reviewer to execute an auto-merge.
- **Observed Evidence**:
  ```json
  {"time":"2026-06-19 00:19:40,762", "level":"INFO", "msg":"Successfully merged PR #2"}
  {"time":"2026-06-19 00:19:40,764", "level":"INFO", "msg":"PR #2 approved and auto-merged successfully."}
  ```
- **Reference Branch**: [test/exploit-pr-1](https://github.com/The-17/pr-reviewer/tree/test/exploit-pr-1)
- **Decision Value**: This case is retained as the canonical example of why the later hardening stages are necessary.

## Stage Targets
| Stage | Chapters | Current Status |
|-------|----------|---------------|
| Stage 1 (Unsecured Baseline) | Ch. 1–4 | Complete |
| Stage 2 (Keychain-Vaulted Egress) | Ch. 5 | Complete |
| Stage 3 (Signed Execution Contracts) | Ch. 6 | Planned |
| Stage 4 (Credential Abuse Detection) | Ch. 7 | Planned |

## Naming Conventions
- Experiment root: `experiments/01_baseline_unsecured/`, `experiments/02_agentsecrets_core/`, etc.
- Versioned implementation folders: `v1_unsecured/`, `v2_agentsecrets_core/`, `v3_sec_standalone/`, etc.
- Test artifacts: `tests/` within each experiment folder.
- Entrypoint files: `main.py`
- Environment variables: `GITHUB_TOKEN`, `LLM_API_KEY` (v1 only)
- Paper framing: each experiment folder should be treated as a standalone section of the evaluation narrative.
