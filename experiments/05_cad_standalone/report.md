# Experiment 5 Report: CAD Behavioral Hardening

## 1. Objective
This report evaluates whether behavioral monitoring can detect when untrusted pull request content has altered the agent's execution context, especially in cases where the system is trying to exfiltrate data.

## 2. Threat Model
The concern here is not only whether the model can be instructed, but whether the runtime can recognize when the session has become tainted by untrusted inputs.

## 3. Experimental Design
- The reviewer is tested under the same adversarial pull request settings used earlier
- The behavior monitor is evaluated as an additional protection layer
- The goal is to detect suspicious or unsafe data flows that capability checks alone may miss

## 4. Findings
The main result is that this stage adds a behavioral signal to the architecture. Rather than focusing only on what actions are allowed, the system attempts to detect when the context itself has become unsafe.

## 5. Results Summary
- The runtime becomes better at recognizing abnormal data-flow situations
- The experiment complements permission-based enforcement with contextual detection
- This stage is especially relevant for researchers studying taint and quarantine behavior

## 6. Paper-Relevant Takeaway
This is a deeper defense layer: it shifts from static action restrictions toward runtime detection of adversarial influence.
