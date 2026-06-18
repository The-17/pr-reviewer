# Experiment 1 Report: Baseline Unsecured Reviewer

## 1. Objective
This report documents the first experimental condition in the study: an autonomous pull request reviewer that uses direct API calls and plaintext credentials. The goal is to show how the system behaves when no runtime guardrails are present and how attacker-controlled pull request content can influence review outcomes.

## 2. System Description
- Runtime: direct calls to GitHub and LLM APIs
- Secrets handling: credentials are loaded from environment variables / `.env` files
- Decision logic: the model output is interpreted directly to decide whether to comment or merge
- Threat model: untrusted pull request content is allowed to influence the model prompt context

## 3. Attack Scenario
The experiment is designed to test two major failure modes:

### 3.1 Goal Hijacking
An attacker inserts instructions into pull request content that attempt to override the review instructions and force an approval decision.

### 3.2 Credential Exfiltration
An attacker inserts instructions that attempt to coerce the model into exposing stored secrets in the public review discussion.

## 4. Observed Real Incident
During the unsecured run, the following merge evidence was recorded for the branch [test/exploit-pr-1](https://github.com/The-17/pr-reviewer/tree/test/exploit-pr-1):

```json
{"time":"2026-06-19 00:19:40,762", "level":"INFO", "msg":"Successfully merged PR #2"}
{"time":"2026-06-19 00:19:40,764", "level":"INFO", "msg":"PR #2 approved and auto-merged successfully."}
```

This is the baseline incident that motivates the rest of the study.

## 5. Why the Incident Matters
The key finding is that once the review model is exposed to attacker-controlled text, the agent can treat that text as an instruction source for system-level actions. In this experiment, the model's review output is sufficient to trigger a real repository merge.

## 6. Experimental Notes
- Relevant implementation: [v1_unsecured](v1_unsecured)
- Validation examples: [tests](tests)
- This experiment serves as the control case for all later hardening stages

## 7. Results Summary
- The baseline reviewer is vulnerable to indirect prompt injection
- Merge behavior can be triggered by attacker-controlled pull request content
- Secrets are exposed to the runtime context and are therefore at risk of exfiltration
- This experiment establishes the failure mode that later versions are designed to mitigate
