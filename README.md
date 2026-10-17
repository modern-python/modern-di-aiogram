<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)"  srcset="https://raw.githubusercontent.com/modern-python/.github/main/brand/projects/modern-di-aiogram/lockup-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/modern-python/.github/main/brand/projects/modern-di-aiogram/lockup-light.svg">
    <img alt="modern-di-aiogram" src="https://raw.githubusercontent.com/modern-python/.github/main/brand/projects/modern-di-aiogram/lockup.png" width="420">
  </picture>
</p>

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

[modern-di](https://github.com/modern-python/modern-di) integration for [aiogram](https://docs.aiogram.dev) 3.x.

Full guide: [aiogram integration docs](https://modern-di.modern-python.org/integrations/aiogram/)

Usage example: [examples/](https://github.com/modern-python/modern-di-aiogram/tree/main/examples)

## Installation

```bash
uv add modern-di-aiogram      # or: pip install modern-di-aiogram
```

## Usage

aiogram has no dependency-injection system of its own, so `modern-di-aiogram` pairs an `@inject` decorator with inert `FromDI` markers (or `auto_inject=True` to skip the decorator entirely). By default `setup_di` opens the root container on dispatcher startup, closes it on shutdown, and installs an outer middleware that builds a per-update `Scope.REQUEST` child container automatically.

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
container = Container(groups=[AppGroup])
setup_di(dispatcher, container)
container.validate()  # optional fail-fast; must come after setup_di registers its providers


@dispatcher.message()
@inject
async def greet(
    message: Message,
    settings: typing.Annotated[Settings, FromDI(AppGroup.settings)],
) -> None:
    await message.answer(f"{settings.greeting}, {message.from_user.first_name}")
```

Pass `auto_inject=True` to `setup_di` to wrap every handler already registered on the dispatcher, so individual handlers don't need `@inject`. Register handlers before startup for this to take effect. Sync handlers work with both `@inject` and `auto_inject`: aiogram runs them in a worker thread as usual, and their `FromDI` parameters resolve from the same per-update child container. The current `aiogram.types.Update` and the concrete event it carries (`Message`, `CallbackQuery`, and so on) are resolvable within DI via the pre-built `aiogram_update_provider` / `aiogram_event_provider` context providers. [aiogram-dialog](https://github.com/Tishka17/aiogram_dialog) getters and callbacks are supported via `modern_di_aiogram.dialog`; see the docs.

### Shutdown

aiogram can still be handling updates when it emits shutdown. In polling mode with `handle_as_tasks=True` (the default), each update runs in its own task that aiogram does not wait for. The webhook handlers in `aiogram.webhook.aiohttp_server` behave the same way, both inline and with `handle_in_background=True`. Before closing the root container, `setup_di` waits until every update that entered its middleware has finished, so those handlers can still resolve `APP`-scoped dependencies and `APP` finalizers run after them.

Shutdown runs in three steps. First the plugin waits for the updates in flight. Then the shutdown handlers run: the dispatcher's own, including aiogram's FSM storage close and handlers registered after `setup_di`, and then those of every included router. Last, the root container closes and the `APP` finalizers run. On each startup, `setup_di` moves the wait to the front of the dispatcher's shutdown handlers and the close to the end of the shutdown handlers of the last router aiogram runs on shutdown. So every shutdown handler runs after the updates have finished and can still resolve `APP`-scoped dependencies. A shutdown handler added during or after startup, for example by a startup handler, or on a router included at that point, runs after the close until the next startup. If shutdown is emitted without a startup, the wait and the close stay where `setup_di` registered them among the dispatcher's shutdown handlers, so the root container still closes.

The wait has no limit by default. Pass `shutdown_timeout` in seconds to cap it:

```python
setup_di(dispatcher, container, shutdown_timeout=10)
```

When the timeout expires, shutdown goes on, the root container is closed anyway, and a warning on the `modern_di_aiogram` logger says how many updates were still running. Those handlers then fail with `ContainerClosedError` on their next `APP`-scoped resolve.

Some things can close before this wait starts, and the plugin cannot change that. In webhook mode, `SimpleRequestHandler.register` closes the bot session on aiohttp shutdown, and when it is registered before `setup_application`, that happens before the dispatcher's shutdown. A handler that calls the Bot API during the wait may then fail. If shutdown is emitted without a startup, aiogram's FSM storage close and the shutdown handlers registered before `setup_di` also run before the wait.

### Sharing a container

When one container serves several apps, for example a bot and a web API in the same process, exactly one owner should open and close it. Pass `manage_lifespan=False` so the dispatcher leaves the root container alone, and open it yourself around running the apps:

```python
setup_di(dispatcher, container, manage_lifespan=False)

async with container:
    await dispatcher.start_polling(bot)
```

Each update still gets its own `Scope.REQUEST` child container, closed when the update is handled. `APP`-scoped finalizers run once, when the `async with` block exits.

With `manage_lifespan=False` the plugin does not wait for updates in flight either. `start_polling` can return while update tasks are still running, and the `async with` block then closes the container under them. To avoid that, poll with `handle_as_tasks=False`, or register your own outer update middleware that counts updates in flight and wait for the count to reach zero before leaving the block.

## API

| Symbol | Description |
|---|---|
| `setup_di(dispatcher, container, *, auto_inject=False, manage_lifespan=True, shutdown_timeout=None)` | Stores the container on the dispatcher, registers the update/event providers, opens it on `dispatcher.startup`, and installs the per-update middleware. On shutdown it waits for updates in flight before any other shutdown handler runs, for at most `shutdown_timeout` seconds when set, and closes the root after every shutdown handler of the dispatcher and its routers. With `auto_inject=True`, also wraps every handler already registered at startup. With `manage_lifespan=False`, never opens, waits or closes; per-update child containers are still built and closed. Returns the container |
| `FromDI(dependency)` | Inert marker (used with `@inject`) that resolves a provider or type from the per-update child container |
| `inject(handler)` | Decorator for an aiogram handler, sync or async; resolves its `FromDI`-annotated parameters and returns a wrapper of the same kind. Not needed when `setup_di(..., auto_inject=True)` is used. Raises `RuntimeError` naming `setup_di` when an update reaches it without the middleware installed |
| `fetch_di_container(dispatcher)` | Returns the root `Container` stored on the dispatcher |
| `aiogram_update_provider` | `ContextProvider` for the current `aiogram.types.Update` (`REQUEST` scope) |
| `aiogram_event_provider` | `ContextProvider` for the current `aiogram.types.TelegramObject` (`REQUEST` scope): the concrete event unwrapped from the `Update` |

## 📦 [PyPI](https://pypi.org/project/modern-di-aiogram)

## 📝 [License](https://github.com/modern-python/modern-di-aiogram/blob/main/LICENSE)

## Part of `modern-python`

Built on [`modern-di`](https://github.com/modern-python/modern-di), a dependency-injection framework with an IoC container and scopes.

Browse the full list of templates and libraries in
[`modern-python`](https://github.com/modern-python); the org profile has the categorized index.
