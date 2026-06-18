# Experiment 2 Report: AgentSecrets Core Hardening

## 1. Objective
This report documents the first hardening step: replacing direct plaintext credential usage with AgentSecrets-backed secret handling so that the runtime no longer exposes credentials directly to the agent process.

## 2. Security Hypothesis
If the reviewer no longer holds `GITHUB_TOKEN` and related values in memory, then prompt injections that attempt to exfiltrate credentials should fail or become substantially more difficult to execute.

## 3. Experimental Setup
- Version under test: the AgentSecrets-integrated reviewer
- Secret storage model: secure OS-backed secret handling instead of `.env`-based plaintext loading
- Evaluation target: the same pull request review flow used in Experiment 1
- Comparison baseline: the direct API path from Experiment 1

## 4. Attack Conditions Tested
### 4.1 Credential Exfiltration Attempt
The experiment checks whether attacker instructions can still cause the model to reveal secrets that were previously available in memory.

### 4.2 Review Workflow Continuity
The experiment verifies that the reviewer still performs normal code review tasks while the secret management path changes.

## 5. Findings
The primary result is that this stage reduces the direct exposure surface for credential leakage. The agent is no longer relying on plaintext keys in the same way as the baseline version, which materially changes the threat model.

## 6. What This Demonstrates
- Secret access is no longer equivalent to plaintext environment exposure
- The attacker may still attempt prompt injection, but the system architecture changes the set of actions available to that content
- This stage is primarily about reducing credential theft risk rather than fully eliminating prompt injection risk

## 7. Results Summary
- Credential exfiltration becomes substantially harder under the new runtime model
- The review loop remains operational
- The experiment does not yet fully solve goal hijacking, but it narrows the attack surface in a meaningful way

## 8. Paper-Relevant Takeaway
This version should be presented as the first defensive layer: stronger secret handling, but not yet a complete solution for adversarial instruction control.
