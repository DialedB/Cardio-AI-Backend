# Contributing to CardioSmart

Thank you for contributing. This guide assumes you may be using Git and GitHub for the
first time. Follow every step in order so changes remain easy to review and safe to merge.

## Git concepts in plain language

A **branch** is an independent line of work. It lets you change files without changing the
shared `main` branch. Create a new branch for every change, even a small documentation fix.

A **commit** is a saved checkpoint on your branch. A good commit records one understandable
piece of work with a short message explaining it.

A **pull request**, usually called a **PR**, asks the project team to review the commits on
your branch and merge them into `main`. PRs provide a place for automated tests, discussion,
and CODEOWNER approval.

## Rules that apply to every contribution

- **NEVER work directly on `main`.**
- **NEVER push directly to `main`.**
- **EVERY change requires a PR.**
- PR authors **DO NOT merge their own PRs**.
- The appropriate CODEOWNER reviews and merges the PR.
- Do not modify another team's owned area without coordinating with its CODEOWNER.
- Review and update `README.md` only after the code is correct and relevant tests pass.
- Never commit secrets, passwords, tokens, private keys, or a local `.env` file.

Repository ownership is recorded in [`.github/CODEOWNERS`](.github/CODEOWNERS). In
particular, `ai/` is owned by the AI team, while `backend/` is owned by the backend team.
Changes to `shared/` require coordination because they can affect both teams and SafeRAG.

## Before starting

Install Git, Python 3.12 or newer, and Docker if you plan to run the container setup. Clone
the repository once, then enter its directory:

```bash
git clone <repository-url>
cd Cardio-AI-Backend
```

Configure your name and email if Git has not been configured on your computer:

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

## 1. Get the latest `main`

Start from the repository directory. Check whether you have unfinished work:

```bash
git status
```

If the output shows changes you want to keep, finish or save them before switching branches.
Then update `main`:

```bash
git checkout main
git pull origin main
```

## 2. Create a new branch

Create and switch to a branch with a short, descriptive name:

```bash
git checkout -b feature/example-name
```

Use a prefix that describes the type of work:

- `feature/` for new behavior, such as `feature/document-upload`
- `fix/` for a bug fix, such as `fix/health-timeout`
- `docs/` for documentation only, such as `docs/local-setup`
- `refactor/` for an internal code improvement, such as `refactor/session-factory`
- `test/` for test-only work, such as `test/query-errors`

Confirm that the first line from `git status` names your new branch. Do not continue if it
says you are on `main`.

## 3. Make the change

Inspect the existing code and documentation before editing. Keep the change focused on the
purpose of your branch. Respect these boundaries:

- Backend contributors must not add RAG internals to `backend/` or modify `ai/`.
- AI contributors must coordinate before changing backend-owned code.
- SafeRAG must depend only on shared contracts, not on AI implementation internals.
- Shared contract changes need explicit coordination between affected codeowners.

For local Python development, create an isolated virtual environment and install the project:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
cp .env.example .env
```

On Windows PowerShell, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

## 4. Add or edit tests

Add tests that demonstrate the expected behavior and protect against the problem returning.
Put backend tests under `tests/`, and SafeRAG tests under `saferag/tests/`. AI tests belong to
the AI-owned area once that team establishes its test structure.

Avoid tests that depend on internal details when the public behavior is enough. Never delete
or weaken a failing test just to obtain a passing test run.

## 5. Review your changes

Check which files changed and read the unstaged diff:

```bash
git status
git diff
```

Look for accidental edits, debugging output, secrets, generated files, and changes outside
your assigned area.

## 6. Run relevant tests and checks

For backend and SafeRAG changes, run:

```bash
ruff check .
pytest
```

You can run a focused file while developing, for example:

```bash
pytest tests/backend/test_main.py
pytest saferag/tests/test_wrapper.py
```

To start the local stack with Docker:

```bash
docker compose up --build
```

Visit `http://localhost:8000/api/health`. Stop the foreground stack with `Ctrl+C`, then remove
its containers with:

```bash
docker compose down
```

## 7. Fix problems and rerun checks

If a test or lint check fails, read the first useful error, fix its cause, and review the new
diff. Rerun the failed check and then the complete relevant test set:

```bash
git diff
ruff check .
pytest
```

Repeat this cycle until the change is correct and every relevant check passes. If you cannot
run a test, record which command was skipped and why in the PR.

## 8. Update `README.md` last

Once implementation and tests are correct, review `README.md` as the repository's source of
truth. Update it if setup, behavior, architecture, structure, current status, or limitations
changed. Do not add planned behavior as if it already exists.

Review the README change separately:

```bash
git diff -- README.md
```

## 9. Review the complete diff

Review every changed file before staging:

```bash
git status
git diff
```

If the output is long, inspect one file at a time:

```bash
git diff -- path/to/file
```

## 10. Commit the change

Stage only files that belong in the PR. If every changed file is intentional, you may stage
them together:

```bash
git add .
git status
git diff --staged
git commit -m "feat(backend): add document upload"
```

Read the staged diff before committing. Every commit message must use this format:

```text
type(scope): short description
```

Git records the contributor's configured name and email as the author. The message adds two
more pieces of information: `type` explains what kind of work was done, and `scope` identifies
the owned area that changed.

Use one of these common types:

- `feat` for new behavior
- `fix` for a bug fix
- `docs` for documentation changes
- `refactor` for internal code changes that do not alter behavior
- `test` for test-only changes
- `chore` for maintenance, tooling, or configuration work

Use the most relevant repository area as the scope:

- `backend`
- `ai`
- `saferag`
- `shared`
- `infra`
- `docs`
- `repo` for repository-wide changes

Write the type and scope in lowercase. Keep the description short, start it with a verb, and
do not end it with a period. Examples:

```text
fix(backend): close database sessions after requests
feat(ai): add source ranking
fix(saferag): reject blocked responses
docs(repo): clarify local setup
test(backend): cover health endpoint
chore(infra): update the backend image
```

If a commit changes more than one area, use the area containing the main change. If the areas
cannot be described clearly with one scope, the work may be easier to review as separate
commits or separate PRs.

## 11. Push the branch

Push your branch to GitHub. Replace the example branch name with yours:

```bash
git push -u origin feature/example-name
```

The `-u` option connects your local branch to its remote branch. Later pushes from the same
branch can use `git push`.

## 12. Open a pull request

Open the repository on GitHub. GitHub usually displays a button to create a PR from the branch
you just pushed. Choose `main` as the base and your branch as the compare branch.

Complete every applicable part of the PR template:

- explain what changed and why;
- select all affected areas;
- list the test commands and results;
- confirm that the README reflects the resulting repository; and
- complete the final checklist honestly.

Keep the PR focused. If you notice unrelated work, create a separate branch and PR.

## 13. Respond to review feedback

A reviewer may request changes. Make those edits on the same local branch, review them, rerun
the relevant tests, commit, and push:

```bash
git status
git diff
ruff check .
pytest
git add .
git diff --staged
git commit -m "fix(backend): address review feedback"
git push
```

Replace the example type, scope, and description with values that match the feedback you
addressed.

The existing PR updates automatically. Reply to review comments when a change is ready for
another look or when you need clarification.

## 14. CODEOWNER review and merge

The appropriate CODEOWNER performs the final review and merges the PR. PR authors must not
approve or merge their own PRs. Do not bypass required checks or CODEOWNER review.

After the PR is merged, return your local repository to `main` and update it:

```bash
git checkout main
git pull origin main
```

You may remove the old local branch after confirming its PR was merged:

```bash
git branch -d feature/example-name
```

## Updating your branch when `main` moved

Other PRs may merge while you are working. Update your local `main`, then merge it into your
branch. This approach is explicit and beginner friendly:

```bash
git checkout main
git pull origin main
git checkout feature/example-name
git merge main
```

If Git reports a conflict, do not guess. Open each conflicted file, look for markers beginning
with `<<<<<<<`, `=======`, and `>>>>>>>`, and decide with the relevant codeowner which content
should remain. Remove the markers, then review and test the combined result:

```bash
git add path/to/resolved-file
git status
git commit -m "chore(repo): resolve merge conflicts"
ruff check .
pytest
git push
```

Ask a teammate or codeowner for help if you are uncertain about a conflict. Resolving it
incorrectly can silently remove someone else's work.
