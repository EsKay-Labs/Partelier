# Goal
Fix [specific incorrect behavior].

# Context
Read the applicable AGENTS.md first.
- Reproduction: [steps, input, environment/version]
- Expected: [observable result]
- Actual: [observable failure and relevant error]

# Relevant files/folders
- [Suspected module and nearest caller]
- [Relevant existing test or failure log, with private data removed]

# Constraints
- Make the smallest fix that addresses the cause.
- Preserve unrelated behavior and public interfaces.
- Expand investigation only when the reproduction or dependencies require it.

# Done when
- The reproduction produces the expected result.
- Related edge cases still work.
- The cause and any remaining limitations are explained.

# Checks/tests
- Reproduce the failure before editing when feasible.
- Add a regression test if it meaningfully protects against recurrence.
- Run the reproduction and relevant checks after the fix; report actual results.
