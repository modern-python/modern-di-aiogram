# aiogram-dialog support is a submodule, not a separate package

**Decision:** DI for [aiogram-dialog](https://github.com/Tishka17/aiogram_dialog) getters and
callbacks ships as `modern_di_aiogram.dialog` inside this package; we will not publish a separate
`modern-di-aiogram-dialog` distribution, and aiogram-dialog stays a test dependency only.

The alternative — its own repository and PyPI package, matching how every other framework
integration in `modern-python` is packaged — was rejected because aiogram-dialog is not another
entrypoint. It runs *inside* aiogram's dispatch, so the container lifecycle it needs already
exists: `setup_di`'s middleware has built the per-update child container and put it in the
per-update `data`, which is the same dict aiogram-dialog hands getters as `**kwargs` and exposes on
`DialogManager.middleware_data`. What is left to write is a dialog-aware `inject` that locates that
container by call shape. A separate package for that is disproportionate, and it would have to
re-export this package's marker and private child-container key across a distribution boundary,
turning both into public API for the sake of the split.

Keeping it here is what makes the runtime dependency avoidable: the lookup is structural
(duck-typed on `.middleware_data`), `dialog.py` imports nothing from `aiogram_dialog`, and a user
who never touches dialogs pays nothing for the module existing. A separate package would have had
to declare the dependency it exists for.

**Revisit trigger:** dialog support needs setup of its own — its own container lifecycle, its own
middleware, or a runtime import of `aiogram_dialog` — or it grows large enough that its release
cadence stops matching the handler integration's. At that point the boundary is real and a separate
package earns its keep.
