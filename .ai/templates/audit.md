# Goal
Audit [bounded area] for [specific reliability, security, or maintenance concern].

# Context
Read the applicable AGENTS.md first. Explain the reason for the audit and the
concrete risk or question to investigate.

# Relevant files/folders
- [Explicit modules, configuration files, or dependency manifests]
- [Relevant architecture or behavior documentation]

# Constraints
- Keep the audit read-only; implementation is a separate task unless requested.
- Stay within [boundary] and follow direct dependencies only when necessary.
- Do not expose credentials, private models, or personal data in findings.
- Do not install scanners or dependencies without a concrete need.

# Done when
- Findings identify evidence, severity, affected locations, and practical remedies.
- Confirmed issues, uncertain risks, and areas not inspected are distinguished.
- Follow-up work is split into small tasks ordered by impact.

# Checks/tests
- Run available checks appropriate to the selected scope.
- Report the commands, observed results, and coverage limits.
- If no issue is found, state the audit scope and remaining uncertainty.
