# Experiment 1: Baseline Unsecured Reviewer

This experiment documents the first stage of the paper: the unsecured autonomous reviewer that relies on direct API calls and plaintext credentials.

## Research Focus
- Show how indirect prompt injections can influence review decisions.
- Record the exact conditions under which a merge action can be triggered.
- Preserve the baseline failure evidence for comparison with later hardening stages.

## Included Artifacts
- Implementation: [v1_unsecured](v1_unsecured)
- Validation tests: [tests](tests)
- Incident evidence: see the main paper overview and the phase-specific notes.
