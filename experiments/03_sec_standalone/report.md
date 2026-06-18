# Experiment 3 Report: Signed Execution Contracts (SEC)

## 1. Objective
This report evaluates whether explicit capability bounds can stop an attacker from converting prompt injection into unauthorized system actions such as merging a pull request.

## 2. Threat Model
The core concern is that even if the model is manipulated, the runtime should not allow the model to perform actions beyond the signed contract.

## 3. Experimental Design
- The reviewer is allowed to read and comment on pull requests
- The merge action is explicitly denied by the contract
- The same prompt-injection style attacks from the baseline are reused to probe runtime behavior

## 4. Attack Conditions Tested
### 4.1 Merge Override Attempt
The experiment checks whether the attacker can still force a merge after the capability contract is in place.

### 4.2 Review Comment Manipulation
The experiment observes whether the model can still write review text while the action policy remains constrained.

## 5. Findings
The main result is that this stage adds a policy boundary around the agent. Even if injected instructions attempt to direct the model toward unsafe actions, the runtime contract prevents those actions from being executed.

## 6. Results Summary
- The reviewer can still perform allowed analysis and commentary tasks
- Unauthorized merge actions are blocked by construction
- This stage is a strong step toward isolating prompt injection from operational control

## 7. Paper-Relevant Takeaway
This experiment should be framed as a control-boundary defense: it does not fully solve all prompt-injection problems, but it prevents the most dangerous action from being executed.
