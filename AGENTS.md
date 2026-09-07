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

Real work **not scheduled** becomes a GitHub issue.

An invariant is a test whose name is the claim, with a docstring opening `INVARIANT:` and a second
paragraph naming **what breaks it** — design rationale, not a report of what this one test catches.
Nothing enforces that docstring shape; it is read at review time.
