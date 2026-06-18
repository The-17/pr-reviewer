# Experiment 2: AgentSecrets Core Hardening

This experiment captures the second stage of the paper's security narrative: moving from plaintext credentials to a key-protected execution path.

## Research Focus
- Prevent credential exfiltration from the runtime environment.
- Evaluate whether the model can still be induced to leak secrets when the agent no longer holds them directly.
- Compare runtime behavior against the baseline experiment.

## Expected Outcome
The agent should retain the same review workflow, but the credentials should no longer be available in process memory for prompt-injected extraction attempts.
