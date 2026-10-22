# Goal
Review [specific change, commit range, or files] for actionable defects.

# Context
Read the applicable AGENTS.md first. Describe the intended behavior and review
focus: [correctness, regressions, data handling, or another concrete concern].

# Relevant files/folders
- [Explicit diff or file scope]
- [Nearest callers and tests needed to assess that change]

# Constraints
- Keep the review read-only unless fixes are explicitly requested.
- Prioritize demonstrable defects over style preferences or speculative concerns.
- Do not expand to a full-project audit without a concrete dependency reason.

# Done when
- Findings include severity, file/line, trigger, impact, and a suggested correction.
- Findings are ordered by importance.
- If no actionable defect is found, say so and identify any verification limits.

# Checks/tests
- Inspect the relevant diff and behavior contracts.
- Run targeted, non-destructive checks when useful and available.
- Distinguish verified results from inference; report test gaps.
