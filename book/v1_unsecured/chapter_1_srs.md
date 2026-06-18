# Chapter 1: Software Requirements Specification (SRS)

A senior engineer writes an SRS not as a feature list, but as a contract between the business requirements, runtime capabilities, and security boundaries.

---

## Skill Level: 🟡 Intermediate
## What You'll Learn
*   How to write precise functional and non-functional requirements.
*   Token efficiency planning for code review agents.
*   Mapping design boundaries to a Traceability Matrix.

---

## Part 1: Functional Requirements

*   **REQ-001: PR Retrieval**
    *   The agent must retrieve the oldest open pull request from a target repository on GitHub.
*   **REQ-002: Multi-File Diff Parsing**
    *   The agent must retrieve the list of files modified in the pull request, along with their individual patches (diffs).
*   **REQ-003: Lockfile & Noise Filtering**
    *   The agent must filter out lockfiles (`package-lock.json`, `poetry.lock`, `yarn.lock`), binaries, and assets (images, icons, vectors) from the review context to maximize token efficiency.
*   **REQ-004: Structured Code Review**
    *   The agent must request a structured JSON review response from the LLM, specifying file paths, line numbers, category classifications, severity, message feedback, and suggestions.
*   **REQ-005: Line-Level Diff Commenting**
    *   The agent must publish review comments directly to the specific commit diff lines on GitHub.
*   **REQ-006: Review Summary Post**
    *   The agent must post a general summary comment containing the final decision on the pull request thread.
*   **REQ-007: Auto-Merge Action**
    *   If the review decision is `APPROVE`, and no critical or high-severity issues are flagged, the agent must trigger a merge request on GitHub.

---

## Part 2: Non-Functional Requirements (NFR)

*   **NFR-001: Latency Overhead**
    *   The added latency of the AgentSecrets proxy in Phase 2 must not exceed 2.0ms per outbound HTTP request.
*   **NFR-002: Zero-Knowledge Key Storage**
    *   At no point during Phase 2 execution should credential values exist in the agent's environment variables (`os.environ`) or memory space.
*   **NFR-003: Token Efficiency Gate**
    *   The agent must filter noise files to prevent sending unnecessary tokens to the LLM context.
*   **NFR-004: Execution Reliability**
    *   All HTTP requests must carry explicit timeouts, and exceptions must be handled gracefully without crashing the orchestrator loop.

---

## Part 3: Traceability Matrix

Every component implemented in our code must trace back to a specific requirement. This prevents "orphaned" code.

| Req ID | Requirement | Design Element | Verification | Justification |
| :--- | :--- | :--- | :--- | :--- |
| **REQ-001** | PR Retrieval | `GitHubClient.fetch_oldest_open_pr` | `pytest` validation | Fetch the target work item |
| **REQ-002** | File Patches | `GitHubClient.fetch_pr_files` | `pytest` validation | Load changed file diffs |
| **REQ-003** | Lockfile Filter | `PRReviewerEngine._should_skip` | Unit tests | Prevent token waste |
| **REQ-004** | Structured Review | `GeminiClient.review_diffs` | Integration tests | Predictable parsing & decision logic |
| **REQ-005** | Line-Level Comment | `GitHubClient.post_line_comment` | Integration tests | Place comments in diff context |
| **REQ-006** | Review Summary | `GitHubClient.post_general_comment` | Integration tests | Main thread notification |
| **REQ-007** | Auto-Merge | `GitHubClient.merge_pull_request` | Integration tests | Process automation |
