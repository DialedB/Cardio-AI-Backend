# Agent Development Rules

Agentic development is allowed in this repository. Agents must follow the same review,
ownership, testing, and documentation standards as human contributors. A human remains
responsible for reviewing every generated change.

## Repository boundaries

This repository is a modular monolith with strict subsystem ownership:

- `backend/` belongs to the backend team. It owns the FastAPI application, persistence,
  jobs, observability, and integration adapters.
- `ai/` belongs to the AI team. Backend work must not add, edit, or infer RAG internals.
- `saferag/` is an independent security wrapper around the shared RAG interface. It must
  not depend on AI implementation details.
- `shared/` contains contracts only. Contract changes affect multiple teams and require
  explicit human instruction and coordinated codeowner review.
- `infra/` belongs to backend and infrastructure codeowners.

Read the nearest `AGENTS.md` before editing. A more specific file in a subdirectory may
add rules for that subtree.

## Agents may

Agents may:

- inspect the repository;
- implement clearly assigned tasks;
- modify backend-owned code when instructed;
- create or edit relevant tests;
- run tests and checks;
- fix failures caused by their changes;
- update relevant documentation;
- update `README.md` after implementation and testing succeed; and
- explain and review code.

## Agents must

Agents must:

- inspect existing code and documentation before changing them;
- keep changes scoped to the assigned task;
- respect ownership boundaries and `CODEOWNERS`;
- preserve public contracts unless explicitly instructed otherwise;
- add or update tests when appropriate;
- review their changes before running tests;
- run the relevant tests and checks;
- fix problems before finalizing documentation;
- update `README.md` only after implementation and tests are correct;
- review the complete diff before handing work back; and
- report every test or check they could not run.

## Agents must not

Agents must not:

- modify the architecture autonomously;
- change shared contracts without explicit human instruction;
- implement or rewrite AI-team RAG internals unless explicitly assigned by the AI
  codeowner;
- alter `ai/` as part of backend work, or alter backend-owned code as part of AI work,
  without coordination;
- modify unrelated files for convenience;
- bypass or weaken tests;
- delete failing tests merely to make CI pass;
- claim placeholder security logic is production ready;
- add external infrastructure or services without approval;
- commit credentials or secrets;
- push directly to `main`;
- approve pull requests;
- merge pull requests; or
- bypass CODEOWNER review.

## Mandatory development loop

Follow this sequence for every implementation task. `README.md` must be updated last,
after implementation has been validated.

```text
Inspect relevant code/documentation
        ↓
Make changes
        ↓
Make/edit tests
        ↓
Review changes
        ↓
Run tests
        ↓
Problems?
   ├─ YES → fix → review again → rerun tests
   └─ NO
        ↓
Update README
        ↓
Review complete diff
        ↓
Hand changes back for human/CODEOWNER PR review
```

## Hand-off expectations

At hand-off, describe what changed, the tests and checks run, their results, intentionally
unfinished areas, and any decision that still needs a human. Do not commit, push, open,
approve, or merge a pull request unless the human explicitly requests that action.
