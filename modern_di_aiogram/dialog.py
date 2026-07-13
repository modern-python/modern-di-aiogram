"""modern-di dialog-aware injection for aiogram-dialog.

aiogram-dialog runs inside aiogram's dispatch, so ``modern_di_aiogram.setup_di``'s
middleware already builds the per-update ``Scope.REQUEST`` child. This module adds
an ``inject`` for aiogram-dialog getters and callbacks that finds that child by the
call shape aiogram-dialog uses and resolves ``FromDI`` params. It imports nothing
from ``aiogram_dialog`` (the lookup is structural), so aiogram-dialog is a test
dependency only.
"""

import functools
import typing

from modern_di import Container, integrations

from modern_di_aiogram.main import _CHILD_CONTAINER_KEY, FromDI


__all__ = [
    "FromDI",
    "inject",
]

_ON_DIALOG_EVENT_ARGS = 2


def _container_from_call(args: tuple[typing.Any, ...], kwargs: dict[str, typing.Any]) -> Container:
    if not args:
        # getter: aiogram-dialog calls it as getter(**manager.middleware_data)
        return typing.cast(Container, kwargs[_CHILD_CONTAINER_KEY])
    # callbacks carry a DialogManager positionally: (data, manager) or (event, widget, manager[, item])
    manager = args[-1] if len(args) == _ON_DIALOG_EVENT_ARGS else args[2]
    return typing.cast(Container, manager.middleware_data[_CHILD_CONTAINER_KEY])


def inject(
    func: typing.Callable[..., typing.Awaitable[typing.Any]],
) -> typing.Callable[..., typing.Awaitable[typing.Any]]:
    """Resolve ``FromDI`` params of an aiogram-dialog getter or callback.

    Finds the per-update child container by call shape (getter kwargs, or the
    ``DialogManager``'s ``middleware_data`` for callbacks) and appends the resolved
    dependencies as keywords. A getter/callback with no ``FromDI`` is returned
    unchanged.
    """
    di_params = integrations.parse_markers(func)
    if not di_params:
        return func

    @functools.wraps(func)
    async def wrapper(*args: typing.Any, **kwargs: typing.Any) -> typing.Any:  # noqa: ANN401
        container = _container_from_call(args, kwargs)
        resolved = integrations.resolve_markers(container, di_params)
        return await func(*args, **kwargs, **resolved)

    return wrapper
