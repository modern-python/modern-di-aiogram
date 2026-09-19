# aiogram-dialog support is a submodule, not a separate package

DI for [aiogram-dialog](https://github.com/Tishka17/aiogram_dialog) getters and callbacks ships as
`modern_di_aiogram.dialog`, not as its own repository and PyPI distribution the way every other
`modern-di` framework integration is packaged. aiogram-dialog is not another entrypoint: it runs
inside aiogram's dispatch, so `setup_di`'s middleware has already built the per-update child
container and put it in the per-update `data`, which is the same dict aiogram-dialog hands getters
as `**kwargs` and exposes on `DialogManager.middleware_data`. What is left to write is an `inject`
that locates that container by call shape, and a distribution for that would have to re-export this
package's marker and its private container lookup across a release boundary, turning both into
public API for the sake of the split. Staying here is also what keeps the runtime dependency
avoidable: the lookup is duck-typed on `.middleware_data`, `dialog.py` imports nothing from
`aiogram_dialog`, and aiogram-dialog stays a test dependency only.
