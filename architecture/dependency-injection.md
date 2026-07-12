# Dependency injection

The capability this package exists for: wiring a `modern-di` `Container` into
an aiogram `Dispatcher` so handler parameters resolve from it, scoped per
update. Everything lives in `modern_di_aiogram/main.py`; the public surface is
`setup_di`, `fetch_di_container`, `FromDI`, `inject`, `aiogram_update_provider`,
and `aiogram_event_provider`.

## Setup

`setup_di(dispatcher, container, *, auto_inject=False)` is the single entry
point. It:

1. Stores the container on the dispatcher under `_ROOT_CONTAINER_KEY`
   (`"modern_di_root_container"`) in the dispatcher's workflow-data, a named
   constant — writer (`setup_di`) and reader (`fetch_di_container`) stay in
   provable agreement instead of relying on a bare string literal.
2. Registers `aiogram_update_provider` and `aiogram_event_provider` — two
   `ContextProvider`s binding `aiogram.types.Update` and
   `aiogram.types.TelegramObject` at `Scope.REQUEST` — on the container, so
   the current update and its inner event are resolvable inside DI.
3. Wires `container.open` to `dispatcher.startup` and `container.close_async`
   to `dispatcher.shutdown`, so the root container's lifecycle tracks the
   dispatcher.
4. Adds `_DiMiddleware(container)` as an outer middleware on
   `dispatcher.update` — the per-update seam described below.
5. If `auto_inject` is `True`, registers a further `dispatcher.startup`
   callback that wraps every un-injected handler in the dispatcher's router
   tree (`_inject_router`, see below).

`fetch_di_container(dispatcher)` reads the same key back and returns the root
container.

## Lifecycle

Only the dispatcher's `startup`/`shutdown` events are wired — a bot process
owns resolution end-to-end, so there is no separate consumer-side lifecycle
to track. Reopening on `startup` is idempotent: a fresh `Container` is already
open on construction, and `Container.open` is a no-op when already open, so a
second `startup` cycle — a restart, a test re-entry — reopens a container that
was closed on a previous `shutdown` instead of raising `ContainerClosedError`.

## Per-update scope

`_DiMiddleware`, registered as an outer middleware on `dispatcher.update`,
runs once per incoming `Update` and wraps every handler that processes it. On
each call it:

1. Builds one `Scope.REQUEST` child container via
   `container.build_child_container(scope=Scope.REQUEST, context={...})`,
   seeded with `{Update: event, TelegramObject: event.event}` — `event` is the
   `Update` itself, and `event.event` is aiogram's resolved inner object for
   that update (`Message`, `CallbackQuery`, etc.).
2. Stashes the child under `_CHILD_CONTAINER_KEY` (`"modern_di_container"`) in
   the per-update `data` dict — the same key name `inject`'s rewritten
   handlers pull their container argument from.
3. Calls the wrapped handler, then closes the child container in a `finally`
   block via `close_async`, so it is closed whether the handler returns
   normally or raises.

Every `FromDI` parameter resolved during that update therefore shares one
child container, and the child is always closed before the middleware
returns, including on the error path.

## Resolution

`FromDI(dependency)` returns an inert marker (`_FromDI`, a frozen dataclass
wrapping a provider or a bare type) — it does nothing on its own. Parameters
opt into injection by annotating them
`typing.Annotated[SomeType, FromDI(dependency)]`.

`inject` rewrites a handler's signature at decoration time:

1. `_parse_inject_params` scans the resolved type hints for `Annotated`
   parameters carrying a `_FromDI` marker.
2. If none are found, the handler is returned unchanged (only marked
   `__modern_di_injected__ = True`, so `auto_inject` skips it later).
3. Otherwise, `inject` builds a `wrapper` whose visible signature drops every
   DI parameter and adds one keyword-only parameter named
   `_CHILD_CONTAINER_KEY`, typed `Container`. At call time the wrapper pops
   that keyword argument, resolves each DI parameter via
   `container.resolve_dependency(marker.dependency)` (which dispatches on
   whether `dependency` is a provider or a bare type), and calls the original
   function with the DI arguments filled in.
4. The wrapper deliberately does **not** use `functools.wraps`: aiogram calls
   `inspect.unwrap` on handler callbacks, which follows `__wrapped__` back to
   the original function and would defeat the rewritten `__signature__` that
   tells aiogram's filter/DI resolution which keyword to supply. Instead,
   `inject` copies just `__name__`, `__qualname__`, `__doc__`, and `__module__`
   by hand, and sets `__signature__` explicitly.

Because `_DiMiddleware` already placed the child container in `data` under
`_CHILD_CONTAINER_KEY`, and aiogram passes `data` entries as keyword arguments
to handlers whose signature names them, the wrapper's added parameter is
filled in automatically by aiogram's own dependency-passing — `inject` never
touches `data` itself.

## auto_inject

When `setup_di(..., auto_inject=True)`, a `dispatcher.startup` callback
(`_inject_router`) walks `dispatcher.chain_tail` — every router reachable from
the dispatcher's router tree — and, for every observer except `update`
(update-level dispatch is handled by `_DiMiddleware`, not per-handler
injection), wraps each handler whose callback is not already marked
`__modern_di_injected__` with `inject`. The rewritten callback and its
recomputed `params` replace the originals on the `HandlerObject` in place.

Because this runs on `startup`, handlers must already be registered on their
routers before startup fires — a handler registered afterward is never
wrapped. Explicitly decorating a handler with `@inject` still works alongside
`auto_inject`: `inject` marks the handler as injected up front, so
`_inject_router` skips it rather than double-wrapping.

`auto_inject` relies on `HandlerObject.params`, added in aiogram 3.2.0, to
recompute the observer's cached parameter set after replacing a handler's
callback — this is why the package requires `aiogram>=3.2,<4`.

## aiogram-dialog

`modern_di_aiogram.dialog` (public surface: `inject`, `FromDI`) adds DI for
[aiogram-dialog](https://github.com/Tishka17/aiogram_dialog) getters and
callbacks. aiogram-dialog runs inside aiogram's own dispatch, so it needs no
container of its own: `setup_di`'s middleware already builds the per-update
`Scope.REQUEST` child and stashes it under `_CHILD_CONTAINER_KEY` in the
per-update `data`, which is also `DialogManager.middleware_data`. The
`FromDI` marker and `_parse_inject_params` are imported unchanged from
`main` — `FromDI` re-exported from `dialog` is the same marker, so it works
in handlers and dialog code interchangeably. The only new code is the
dialog-aware `inject` and its container lookup.

### Call-shape container lookup

aiogram-dialog calls getters and callbacks with different, fixed shapes, and
`_container_from_call(args, kwargs)` dispatches on them instead of on any
declared parameter name:

- **Getter** — aiogram-dialog calls `getter(**manager.middleware_data)`, so
  there are no positional args and the container is a keyword,
  `kwargs[_CHILD_CONTAINER_KEY]`.
- **Callbacks** carry a `DialogManager` positionally instead: `on_start` and
  `on_close` are called as `(data, manager)` (2 args, `_ON_DIALOG_EVENT_ARGS`),
  so the manager is `args[-1]`; `on_click` (`(event, widget, manager, item?)`)
  and `on_process_result` (`(start_data, result, manager)`) are 3–4 args, so
  the manager is always `args[2]`. Either way the container is
  `manager.middleware_data[_CHILD_CONTAINER_KEY]` — the same dict the getter
  received as kwargs.

### functools.wraps is safe here

The handler `inject` in `main` deliberately avoids `functools.wraps` because
aiogram unwraps `__wrapped__` and would defeat the rewritten `__signature__`.
The dialog `inject` has no such hazard: aiogram-dialog never inspects a
getter's or callback's signature — getters are always called with
`**middleware_data` and callbacks always positionally — so there is no
signature to defeat, and `wrapper` uses `functools.wraps(func)` plainly. This
also means the dialog `inject` needs no signature rewrite at all: it just
appends the resolved `FromDI` values as extra keywords via
`func(*args, **kwargs, **resolved)`.

### Requirements and constraints

- **No runtime `aiogram_dialog` dependency.** The lookup is structural
  (duck-typed on `.middleware_data`); `dialog.py` imports nothing from
  `aiogram_dialog`. It is a test dependency only (`aiogram-dialog>=2,<3` in
  the `dev` group).
- **Requires `setup_di`.** Dialog DI has no setup of its own — it depends on
  `setup_di`'s middleware to have already put the child container in
  `middleware_data`. Without it, the lookup raises `KeyError`.
- **A getter decorated with `@inject` must still declare `**kwargs`.**
  aiogram-dialog always calls getters as `getter(**manager.middleware_data)`,
  which carries more entries than just the DI container (dialog manager,
  event, etc.) — a bare getter that doesn't accept `**kwargs` raises
  `TypeError` on that call regardless of `@inject`. This is inherent to
  aiogram-dialog's own calling convention, not something `inject` imposes.
- **No auto-inject for dialogs.** Getters/callbacks live on `Window`/widget
  objects with no router-like registry to walk, so only explicit `@inject`
  is supported.
