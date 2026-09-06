# No `auto_inject` for dialog getters and callbacks

**Decision:** `setup_di(..., auto_inject=True)` sweeps handlers only. Dialog getters and callbacks
opt in one at a time with `@modern_di_aiogram.dialog.inject`; there is no dialog equivalent of the
startup sweep.

`auto_inject` works on handlers because a dispatcher owns a registry of them: the startup callback
walks `chain_tail`, then each router's observers, and rewrites the callback on every `HandlerObject`
it finds. Dialogs have no comparable registry. Getters and callbacks are attributes of `Window` and
widget objects, reachable only by walking whatever the user passed to `setup_dialogs`, through
widget containers this package does not own and aiogram-dialog does not expose for that purpose. A
sweep would mean traversing another library's object tree by structure — the one thing the dialog
module deliberately avoids, since it is what lets it stay free of a runtime `aiogram_dialog` import.

Nor is the payoff the same. `auto_inject` exists so an existing bot with many registered handlers
does not need a decorator added to each; dialog code is written against `Window` definitions where
the getter and callbacks are already named explicitly at their definition site, so `@inject` sits
directly where a reader is looking. Dishka, the comparable integration, draws the line in the same
place.

**Revisit trigger:** aiogram-dialog exposes a registry of dialogs, windows or widgets that can be
walked as a supported API rather than by structure — at which point a dialog sweep costs about what
`_inject_router` costs, and the runtime-import question can be answered on its own merits.
