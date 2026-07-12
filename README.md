# modern-di-aiogram

[![PyPI version](https://img.shields.io/pypi/v/modern-di-aiogram.svg)](https://pypi.org/project/modern-di-aiogram/)
[![Supported Python versions](https://img.shields.io/pypi/pyversions/modern-di-aiogram.svg)](https://pypi.org/project/modern-di-aiogram/)
[![Downloads](https://static.pepy.tech/badge/modern-di-aiogram/month)](https://pepy.tech/projects/modern-di-aiogram)
[![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen.svg)](https://github.com/modern-python/modern-di-aiogram/actions/workflows/ci.yml)
[![CI](https://github.com/modern-python/modern-di-aiogram/actions/workflows/ci.yml/badge.svg)](https://github.com/modern-python/modern-di-aiogram/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/modern-python/modern-di-aiogram.svg)](https://github.com/modern-python/modern-di-aiogram/blob/main/LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/modern-python/modern-di-aiogram)](https://github.com/modern-python/modern-di-aiogram/stargazers)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![ty](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json)](https://github.com/astral-sh/ty)

[Modern-DI](https://github.com/modern-python/modern-di) integration for [aiogram](https://docs.aiogram.dev) 3.x.

Full guide: [aiogram integration docs](https://modern-di.modern-python.org/integrations/aiogram/)

## Installation

```bash
uv add modern-di-aiogram      # or: pip install modern-di-aiogram
```

## Usage

aiogram has no dependency-injection system of its own, so `modern-di-aiogram` pairs an `@inject` decorator with inert `FromDI` markers (or `auto_inject=True` to skip the decorator entirely). `setup_di` opens the root container on dispatcher startup, closes it on shutdown, and installs an outer middleware that builds a per-update `Scope.REQUEST` child container automatically.

```python
import typing

from aiogram import Dispatcher
from aiogram.types import Message
from modern_di import Container, Group, Scope, providers
from modern_di_aiogram import FromDI, inject, setup_di


class Settings:
    def __init__(self) -> None:
        self.greeting = "hello"


class AppGroup(Group):
    settings = providers.Factory(Settings, scope=Scope.APP, cache=True)


dispatcher = Dispatcher()
setup_di(dispatcher, Container(groups=[AppGroup], validate=True))


@dispatcher.message()
@inject
async def greet(
    message: Message,
    settings: typing.Annotated[Settings, FromDI(AppGroup.settings)],
) -> None:
    await message.answer(f"{settings.greeting}, {message.from_user.first_name}")
```

Pass `auto_inject=True` to `setup_di` to wrap every handler already registered on the dispatcher, so individual handlers don't need `@inject` — register handlers before startup for this to take effect. The current `aiogram.types.Update` and the concrete event it carries (`Message`, `CallbackQuery`, …) are resolvable within DI via the pre-built `aiogram_update_provider` / `aiogram_event_provider` context providers. [aiogram-dialog](https://github.com/Tishka17/aiogram_dialog) getters and callbacks are supported via `modern_di_aiogram.dialog` — see the docs.

## API

| Symbol | Description |
|---|---|
| `setup_di(dispatcher, container, *, auto_inject=False)` | Stores the container on the dispatcher, registers the update/event providers, wires `dispatcher.startup`/`dispatcher.shutdown` to open/close it, and installs the per-update middleware. With `auto_inject=True`, also wraps every handler already registered at startup |
| `FromDI(dependency)` | Inert marker (used with `@inject`) that resolves a provider or type from the per-update child container |
| `inject(handler)` | Decorator for an aiogram handler; resolves its `FromDI`-annotated parameters. Not needed when `setup_di(..., auto_inject=True)` is used |
| `fetch_di_container(dispatcher)` | Returns the root `Container` stored on the dispatcher |
| `aiogram_update_provider` | `ContextProvider` for the current `aiogram.types.Update` (`REQUEST` scope) |
| `aiogram_event_provider` | `ContextProvider` for the current `aiogram.types.TelegramObject` (`REQUEST` scope) — the concrete event unwrapped from the `Update` |

## 📦 [PyPI](https://pypi.org/project/modern-di-aiogram)

## 📝 [License](LICENSE)

## Part of `modern-python`

Built on [`modern-di`](https://github.com/modern-python/modern-di), a dependency-injection framework with IoC container and scopes.

Browse the full list of templates and libraries in
[`modern-python`](https://github.com/modern-python) — see the org profile for the categorized index.
