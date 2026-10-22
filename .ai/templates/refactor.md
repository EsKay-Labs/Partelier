# Goal
Simplify [specific module or boundary] while preserving its observable behavior.

# Context
Read the applicable AGENTS.md first. Explain the maintenance problem and why this
refactor is needed now. For a complex change, outline the steps before editing.

# Relevant files/folders
- [Module and its callers]
- [Tests or documented behavior defining compatibility]

# Constraints
- Limit changes to [boundary].
- Preserve public interfaces, stored data, and user-visible behavior unless stated.
- Avoid unrelated renames, dependency upgrades, and new abstraction layers.

# Done when
- [Concrete structural improvement]
- Existing supported inputs and outputs are preserved.
- Architecture notes are updated only if a documented boundary changed.

# Checks/tests
- Run relevant existing tests before and after the change when available.
- Check affected callers and any required host-application behavior.
- Report compatibility evidence and checks that remain manual.
