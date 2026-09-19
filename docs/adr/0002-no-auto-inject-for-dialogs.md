# No `auto_inject` for dialog getters and callbacks

`setup_di(..., auto_inject=True)` sweeps handlers only; dialog getters and callbacks opt in one at a
time with `@modern_di_aiogram.dialog.inject`. The sweep works on handlers because a dispatcher owns
a registry of them, so `_inject_router` can walk `chain_tail` and every observer other than
`update`, rewriting the callback of each handler not already marked injected. Dialogs have no such
registry: getters and callbacks are attributes of `Window` and widget objects, reachable only by
traversing another library's object tree by structure, which is the one thing `dialog.py` avoids so
that it can stay free of a runtime `aiogram_dialog` import
([ADR-0001](0001-dialog-support-is-a-submodule.md)). The payoff would be smaller too: `auto_inject`
exists so an existing bot with many registered handlers needs no decorator added to each, while a
`Window` names its getter and callbacks at their definition site, where `@inject` is already where a
reader is looking.
