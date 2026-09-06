import ast
import pathlib
import types

import modern_di_aiogram


_PACKAGE_ROOT = pathlib.Path(modern_di_aiogram.__file__).parent


def test_public_surface_is_the_six_documented_symbols() -> None:
    """INVARIANT: the package exports exactly the six symbols the README documents.

    Broken by promoting a helper to a public name, in ``__all__`` or as an unprefixed binding in
    ``__init__`` -- the latter is public whether or not it was meant to be. The surface is the whole
    semver contract of an adapter this thin: every name here is one a major release has to keep
    working, and an adapter that grows names has started to be a framework of its own.
    """
    public = sorted(
        name
        for name, value in vars(modern_di_aiogram).items()
        if not name.startswith("_") and not isinstance(value, types.ModuleType)
    )

    assert public == [
        "FromDI",
        "aiogram_event_provider",
        "aiogram_update_provider",
        "fetch_di_container",
        "inject",
        "setup_di",
    ]
    assert modern_di_aiogram.__all__ == public


def test_package_never_imports_aiogram_dialog() -> None:
    """INVARIANT: no module under ``modern_di_aiogram/`` imports ``aiogram_dialog``.

    Broken by reaching for a real ``DialogManager`` -- for a type annotation, an isinstance check,
    or a nicer error -- in ``dialog.py``. aiogram-dialog is a dev dependency here, so the suite
    keeps passing while every user who installed this package without it gets an ImportError at
    ``import modern_di_aiogram.dialog``. The dialog container lookup is duck-typed on
    ``.middleware_data`` precisely so that dependency stays optional. A ``TYPE_CHECKING``-guarded
    import trips this too, deliberately: it is inert at runtime, but it is the first step of the
    reach this module is designed never to make.
    """
    offenders = [
        module.relative_to(_PACKAGE_ROOT).as_posix()
        for module in sorted(_PACKAGE_ROOT.rglob("*.py"))
        for node in ast.walk(ast.parse(module.read_text()))
        if (isinstance(node, ast.Import) and any(a.name.split(".")[0] == "aiogram_dialog" for a in node.names))
        or (isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "aiogram_dialog")
    ]

    assert offenders == []
