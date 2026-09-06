# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`modern-di-aiogram` is an aiogram 3.x integration for
[`modern-di`](https://github.com/modern-python/modern-di); [`CONTEXT.md`](CONTEXT.md) opens with
what it does and owns the vocabulary — read it before naming a concept in code, a test name, or an
issue title. It is one of that project's integrations, each of which lives in a separate repository
and ships as a separate PyPI package.

## Commands

`just` (task runner) and `uv` (package manager). The [`justfile`](justfile) is the source of truth —
`just --list`, or read it. The one thing it does not say: a `ty` suppression is written
`# ty: ignore`, never `# type: ignore`.

## Architecture

`modern_di_aiogram/main.py` is the handler integration and `dialog.py` the aiogram-dialog one; both
are short enough to read whole. Read them. `dialog.py` reuses `main`'s marker and per-update child
container, so a change to either crosses the two files more often than the split suggests.

### Testing patterns

Tests drive a real `Dispatcher` with a fake-token `Bot` and `feed_update`, and real dialogs with
`aiogram_dialog.test_tools` — nothing about the wiring is stubbed, so a regression shows up as a
handler that never sees its dependency.

## Workflow

**The spec for a change is its PR body**, not a committed file: why, design, non-goals,
verification, reviewed with the diff. There is no change file and no lane to choose. A trivial PR
(typo, dep bump, formatter, CI tweak) ships a conventional-commit title with no body ceremony.

Two things outlive the PR, and there are exactly two places to put them: an alternative **rejected**
with reasoning becomes an ADR in [`docs/adr/`](docs/adr/) (`NNNN-slug.md`, sequential, with a
revisit trigger), and real work **not scheduled** becomes a GitHub issue. There is no third state,
and no separate truth-home directory — a behaviour change is reviewed with the diff, not promoted
to a page.

### Where a fact goes

Four homes, one owner each:

| Home | Holds |
|---|---|
| `modern_di_aiogram/` | anything readable from the module — the default |
| a named test | an **invariant**: must stay true, and a change could silently break it |
| `docs/adr/` | a rejected alternative, with the reasoning that would otherwise be re-litigated |
| `README.md` | anything a user needs |

Before writing a line anywhere:

> Can an agent get this by reading `modern_di_aiogram/`? → **don't write it.**
> Would a wrong change here fail a test? → it belongs **in the test**, not in prose.
> Does a user need it? → **`README.md`**.
> Otherwise it does not get written.

**Prose about mechanism has no home. There is no file to add a paragraph to.** This file included:
it is always loaded, so a line that restates a docstring, a justfile comment, or `pyproject.toml`
costs every turn and rots in two places at once. The aiogram wiring is intricate enough to tempt a
full narration of it; that is the failure mode to watch for here.

An invariant is a test whose name is the claim, with a docstring opening `INVARIANT:` and a second
paragraph naming **what breaks it** — design rationale, not a report of what this one test catches.
Nothing enforces that docstring shape; it is read at review time. A relative link to an ADR *is*
checked — CI runs lychee `--offline` over every `.md`. Both ADRs and `INVARIANT:` docstrings
ratchet: nothing prunes a record once its call is settled. Keeping them lean is a standing habit.
