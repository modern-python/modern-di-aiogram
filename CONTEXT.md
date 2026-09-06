# modern-di-aiogram

A [`modern-di`](https://github.com/modern-python/modern-di) integration for aiogram 3.x: it opens
a container with the dispatcher, builds one `Scope.REQUEST` child container per incoming update,
and resolves handler parameters marked with `FromDI` from it.

## Language

A term is listed only when there is a synonym to reject, or a meaning subtle enough that code and
docs must agree on it. General programming vocabulary does not belong here, however heavily this
package uses it.

The domain terms are `modern-di`'s — `Container`, `Provider`, `Group`, `Scope`, `Resolution`,
`Override`. That project's `CONTEXT.md` is the authority for all of them; nothing here redefines
one. The framework terms are aiogram's — dispatcher, router, observer, handler, middleware, and
aiogram-dialog's getter, callback and `DialogManager`; use them as aiogram does. The three below
are this package's own.

**Root container**:
The `Container` handed to `setup_di` and stored on the dispatcher; `fetch_di_container` reads it
back. It tracks the dispatcher's lifecycle — opened on `startup`, closed on `shutdown` — and no
handler ever resolves from it directly.

**Per-update child container**:
The single `Scope.REQUEST` child the middleware builds for one incoming `Update`, seeded with that
`Update` and its concrete event. Every handler, dialog getter and dialog callback that the update
reaches shares this one container, and it is closed when the middleware returns, on the error path
included.
_Avoid_: request container — the unit of work is an update, not an HTTP request, the same reason
`modern-di` rejects "request" for `Connection`.

**Marker**:
What `FromDI(dependency)` returns: an inert annotation value carrying a provider or a bare type. It
resolves nothing on its own — `inject` collects the markers when it decorates and resolves them per
call, so a `FromDI` in a signature that is never decorated (or never swept by `auto_inject`) is
simply an annotation that does nothing.
