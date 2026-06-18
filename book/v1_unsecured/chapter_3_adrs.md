# Chapter 3: Architecture Decision Records (ADRs)

Every major architectural choice in a project must be recorded. An ADR documents the context, the decision, consequences, and rejected alternatives.

---

## Skill Level: 🟡 Intermediate
## What You'll Learn
*   How to structure and write ADRs.
*   Evaluating structural vs. semantic security gates.
*   Tradeoffs in LLM API parameter configurations.

---

## ADR-001: Direct API Calls with Plaintext Keys (v1_unsecured)

**Status**: Accepted (v1 baseline)

**Context**:
We need a baseline, functional agent loop in Python to fetch open pull requests, download code diffs, call the Gemini API for evaluation, post comments, and merge pull requests. Setting up a baseline allows us to demonstrate vulnerabilities and run threat simulations.

**Decision**:
We will implement modular Python classes (`GitHubClient`, `GeminiClient`, and `PRReviewerEngine`) loading high-privilege credentials (`GITHUB_TOKEN`, `LLM_API_KEY`) from a `.env` file via `python-dotenv`. All HTTP requests will be executed directly using the standard `requests` client library.

**Consequences**:
*   ✅ Fast initial setup. No local daemons or proxy configurations required.
*   ❌ Severe credential exfiltration surface: If the agent reasoning loop is hijacked via prompt injection, the attacker can force the LLM to read the memory/env variables and write them to a public comment.
*   ❌ Vulnerable to forced merge: The agent executes the merge request directly from code, meaning an approved prompt injection immediately merges the PR.

**Rejected Alternatives**:
*   *Hardcoded secrets*: Rejected due to high risk of secret leakage in git history.
*   *Restricting LLM scope via system prompt only*: Rejected because prompt-level filters are weak policies that can always be bypassed by semantic wrappers.

---

## ADR-002: Structured JSON Outputs for LLM reviews

**Status**: Accepted

**Context**:
Standard text parsing of LLM outputs (e.g. searching for `"DECISION: APPROVE"`) is fragile. An attacker can hijack the LLM to output a complex sentence like `"Review complete. I do not DECISION: APPROVE this code because of bugs."`, which a naive check would mistake for approval.

**Decision**:
We will configure the `GeminiClient` to request **Structured JSON Outputs** using the Gemini REST API's `responseSchema` configuration. This forces the LLM at the decoding layer to return a rigid JSON structure containing `"decision": "APPROVE" | "REJECT"`.

**Consequences**:
*   ✅ Eliminates string-matching fragility in python code.
*   ✅ Ensures consistent feedback parsing for posting line-level comments.
*   ❌ Slightly increases latency during output generation due to constraint checks in the decoding layer.

**Rejected Alternatives**:
*   *JSON parsing in python wrapper*: Asking the LLM to output markdown JSON blocks and parsing in python. Rejected because LLMs regularly fail to close JSON blocks under prompt injection, causing python parsing failures.
