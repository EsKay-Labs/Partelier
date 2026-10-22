# Bootstrap report — 20 October 2026

Historical bootstrap record. The user subsequently clarified that the priority
is small parametric CAD helpers, such as hinges. The current
[MVP plan](mvp-plan.md) and [next task](../.ai/next-task.md) supersede the initial
honeycomb-first proposal below. Original implementation and verification results
remain unchanged.

Rename note — 21 October 2026: the user approved **Partelier**. File paths and
launch labels below now use that name so they match the current project; the
historical scope and verification results remain unchanged. Follow the current
README for installation and the next task.

## Delivered structure and current capability

Created a new local Git repository on `main` with a self-contained Python Fusion
add-in bundle, a pure settings module, unit tests, concise planning/development
docs, AGENTS.md and the requested AI workflow files. No dependencies were added.

The command is implemented to select a closed BRep solid, check two honeycomb
dimensions, and display their values without model mutation. It has not been
loaded or exercised inside Fusion. No honeycomb, truss, shell, lattice, geometry
preview, mesh export or structural analysis is implemented. The product MVP
remains future work; this delivery is its foundation.

## Assumptions and reference

The original bootstrap used a provisional product name. Python add-in, native
controls, Windows-first, English UI and honeycomb-first were explicit design
choices at that stage. FDM was a proposed
initial focus, not a confirmed printer requirement. Source-envelope semantics,
shell/skin policy, build direction, machine/material limits and Edit persistence
remain open; see [the plan](mvp-plan.md).

Inspected the supplied `C:/tmp/StructForge-joint-refactor` read-only, including
its existing truss planning and relevant docs. Its HEAD was `9587a0e` and it had
pre-existing local changes. Its reported Git status was unchanged after the
inspection. No files were copied from or changed in that checkout.

## Files created

- Root: `.gitignore`, `AGENTS.md`, `README.md`.
- Add-in: `Partelier/__init__.py`, `Partelier/Partelier.py`,
  `Partelier/Partelier.manifest`, `Partelier/partelier/__init__.py`,
  `Partelier/partelier/addin.py`, `Partelier/partelier/settings.py`.
- Tests: `tests/test_settings.py`.
- Docs: `docs/mvp-plan.md`, `docs/architecture.md`, `docs/development.md`,
  `docs/ai-workflow.md`, `docs/chatgpt-bot-instructions.md`,
  `docs/bootstrap-report.md`.
- Prompt templates: `.ai/templates/feature.md`, `.ai/templates/bug.md`,
  `.ai/templates/refactor.md`, `.ai/templates/review.md`, `.ai/templates/docs.md`,
  `.ai/templates/audit.md`.
- Next scoped prompt: `.ai/next-task.md`.

Total: 23 new source/document/configuration files. There were no pre-existing
project files to modify. Local `.git` metadata and ignored Python caches were
also created. Files remain uncommitted; no remote, GitHub repository, push,
release or Custom GPT configuration was created.

## Run and verification

Link the **Partelier** subfolder in Fusion's Scripts and Add-Ins dialog, Run the
add-in, and open **Partelier: Check honeycomb inputs** in the Design Add-Ins panel.
See [README](../README.md) and [development](development.md) for exact steps.

Observed local results on Python 3.13:

- `py -m unittest discover -s tests -v`: **6 tests passed**.
- `py -m compileall -q Partelier tests`: **passed**.
- Manifest JSON, UUID, platform/startup settings and matching bundle filenames:
  **passed**.
- Template section, local Markdown file-link and direct text whitespace checks:
  **passed**.
- `git diff --check`: **passed**, with no tracked diff yet. The direct whitespace
  check covers the new untracked source/document files.

Native Fusion acceptance is **pending**. No host API, lifecycle, command dialog,
performance or geometry result is claimed validated by the local tests. The
manual acceptance checklist is in [development.md](development.md).

## Official mechanisms and repository conventions

AGENTS.md is the persistent instruction mechanism recognized by Codex, per
[OpenAI's documentation](https://learn.chatgpt.com/docs/agent-configuration/agents-md).
Scoped prompts and task-relevant context follow
[OpenAI's prompting guidance](https://learn.chatgpt.com/docs/prompting).

The `.ai/templates/` directory, six-section prompt format, MVP/architecture docs,
ChatGPT Project Brain role and GitHub review loop are this repository's chosen
conventions. They are not special auto-loaded Codex configuration. The
[OpenAI workflow example](https://developers.openai.com/cookbook/examples/codex/iterating-development-workflows-with-codex)
makes the same distinction between AGENTS.md and supporting workflow documents.

## Next task and practical limits

The next code task is the bounded pure honeycomb centre-line planner. Its
complete copy-ready prompt is [.ai/next-task.md](../.ai/next-task.md). Native smoke
validation of the foundation is a separate immediate check before relying on
the Fusion UI or integrating geometry.

Prioritize small verified honeycomb solids, then planar printable trusses, then
3D strut lattices. Keep-solid regions around screw holes, configurable skins and
print-oriented geometry checks are promising expansion ideas. Defer gyroid,
variable density and automatic optimization until the geometry approach and
performance budget are proven. The plan records these ideas and prerequisites.
