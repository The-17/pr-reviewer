# Experiment 3: Signed Execution Contracts (SEC)

This experiment documents the use of explicit execution contracts to constrain what an autonomous reviewer may do.

## Research Focus
- Prevent unauthorized merge behavior even if prompt instructions are hijacked.
- Show how capability boundaries can be enforced around the agent runtime.
- Record which actions are allowed vs. denied.

## Evaluation Notes
The main question for this experiment is whether the model can still influence review text, while the merge action remains blocked by contract enforcement.
