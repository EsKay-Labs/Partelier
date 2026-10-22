# AI development workflow

## Roles and source of truth

- **ChatGPT Project Brain:** discuss requirements, inspect the connected GitHub
  repository read-only, and prepare small Codex tasks. Use
  [the bot instructions](chatgpt-bot-instructions.md) to configure it manually.
- **GitHub:** once connected and pushed, the shared source of truth for committed
  code, plans, reviews, and decisions. Local uncommitted or unpushed work is not
  visible there. Identify the branch or commit used when preparing a task.
- **Codex:** inspect the relevant local files, implement the requested change,
  run appropriate checks, and report the result for review.
- **AGENTS.md:** persistent repository guidance recognized by Codex. Keep it
  concise and refer to detailed documents only when relevant to a task.
- **.ai/templates/:** reusable human-selected prompt templates. This directory
  and its filenames are repository conventions, not automatically loaded Codex
  instructions.

The ChatGPT/GitHub/Codex role split is this project's chosen workflow. This
bootstrap does not connect GitHub or configure a Custom GPT.

## Everyday loop

1. Discuss one next outcome with the ChatGPT project bot.
2. Ask it to inspect the connected GitHub repository read-only, starting with
   AGENTS.md and the relevant plan or module. If access is unavailable, it should
   say so and request only the necessary files or excerpts.
3. Choose a template in `.ai/templates/` and produce one small task with **Goal**,
   **Context**, **Relevant files/folders**, **Constraints**, **Done when**, and
   **Checks/tests**. Separate discussion from the final task prompt.
4. Send only the final prompt to Codex in the intended project folder. Mention
   local changes or decisions that have not reached GitHub.
5. Codex reads applicable AGENTS.md guidance, inspects the needed files, makes
   the change, runs relevant checks, and reports evidence and limitations.
   Complex or ambiguous work starts with a short plan and minimal clarification.
6. Review the diff, verify the acceptance criteria, and perform host-application
   checks that could not run in the local environment.
7. Commit the reviewed work and push it to the intended branch; merge a pull
   request if that is the repository's chosen review process. Use the actual
   configured remote rather than inventing a GitHub URL.
8. Repeat using the updated GitHub branch/commit. Keep plans and AGENTS.md aligned
   with material decisions and working commands.

## Selecting a template

| Template | Use it for |
| --- | --- |
| [feature](../.ai/templates/feature.md) | One agreed user-visible outcome |
| [bug](../.ai/templates/bug.md) | A reproducible incorrect behavior |
| [refactor](../.ai/templates/refactor.md) | A bounded structural improvement |
| [review](../.ai/templates/review.md) | Read-only review of a specific change |
| [docs](../.ai/templates/docs.md) | A focused documentation correction |
| [audit](../.ai/templates/audit.md) | A read-only investigation of a defined risk |

## Official mechanisms and local conventions

Codex discovers repository guidance through AGENTS.md; more specific applicable
guidance can refine it. See OpenAI's
[AGENTS.md documentation](https://learn.chatgpt.com/docs/agent-configuration/agents-md).

The six prompt sections, `.ai/templates/`, this document, the MVP plan, and the
Project Brain role are local workflow choices. They are not required Codex
configuration. OpenAI's
[workflow example](https://developers.openai.com/cookbook/examples/codex/iterating-development-workflows-with-codex)
also distinguishes AGENTS.md from optional workflow files. Keep the process as
small as the task needs; no additional agents, services, or planning framework
are required by this bootstrap.
