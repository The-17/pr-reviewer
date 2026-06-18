# Chapter 2: Entities, Aggregates & Business Rules

Before writing any database schemas or API integrations, we must design the domain model. Skipping this step leads to complex, hard-to-maintain control flows.

---

## Skill Level: 🟡 Intermediate
## What You'll Learn
*   Designing aggregates and value objects.
*   Enforcing invariants on domain entities.
*   Mapping domain lifecycles.

---

## Part 1: Bounded Contexts & Aggregate Roots

We model our domain inside the pull request review boundary:

```
┌─────────────────────────────────────────────────────────┐
│                      PullRequest                        │
│                   (Aggregate Root)                      │
│                                                         │
│  - number: int                                          │
│  - state: string                                        │
│  - head_sha: string                                     │
│  - base_repo: string                                    │
│                                                         │
│  ┌───────────────────────┐     ┌─────────────────────┐  │
│  │      ChangedFile      │     │      CodeReview     │  │
│  │    (Value Object)     │     │      (Entity)       │  │
│  │                       │     │                     │  │
│  │  - filename: string   │     │  - decision: string │  │
│  │  - patch: string      │     │  - summary: string  │  │
│  └───────────────────────┘     │  - comments: list   │  │
│                                └──────────┬──────────┘  │
│                                           │             │
│                                           ▼             │
│                                ┌─────────────────────┐  │
│                                │     LineComment     │  │
│                                │   (Value Object)    │  │
│                                │                     │  │
│                                │  - file: string     │  │
│                                │  - line: int        │  │
│                                │  - message: string  │  │
│                                └─────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 1. `PullRequest` (Aggregate Root)
Represents the target work item.
*   **Invariants**:
    *   A `PullRequest` must be in `"open"` state to be evaluated.
    *   Merging can only be triggered if a valid `CodeReview` with `decision="APPROVE"` is attached.

### 2. `ChangedFile` (Value Object)
Represents a file changed in the PR.
*   **Invariants**:
    *   The `patch` cannot be empty. If the file is binary or has no patch, it is ignored during review.

### 3. `CodeReview` (Entity)
Represents the evaluation outcome.
*   **Invariants**:
    *   If `comments` contains any comment with `severity="high"` or `category="security"`, the decision MUST be `REJECT` (Fail-Closed).

---

## Part 2: State Transitions

```
 [Open PR] ──► [Filter Noise] ──► [Parse Patches] ──► [LLM Structured Review] ──► [Execute Decision]
                                                                                        │
                                                     ┌──────────────────────────────────┴──────┐
                                                     ▼                                         ▼
                                              [Post Comments]                           [Post Comments]
                                              [Merge Branch]                            [Manual Review]
                                                (APPROVED)                                 (REJECTED)
```

---

## Part 3: Business Logic Rules

1.  **Noise Mitigation**: Do not waste processing time or token count on dependencies. Auto-generated files and lockfiles (`poetry.lock`, `package-lock.json`) are filtered out prior to sending diffs to the LLM.
2.  **Explicit Action Boundary**: The merge request must explicitly verify that the head commit SHA matches the SHA analyzed by the LLM. This prevents race conditions where an attacker pushes a backdoor commit immediately after an approval is generated.
