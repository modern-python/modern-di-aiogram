import dataclasses
import functools
import inspect
import typing

import aiogram
from aiogram import BaseMiddleware, Dispatcher
from aiogram.dispatcher.event.handler import HandlerObject
from aiogram.types import TelegramObject, Update
from modern_di import Container, Scope, providers


aiogram_update_provider = providers.ContextProvider(Update, scope=Scope.REQUEST)
aiogram_event_provider = providers.ContextProvider(TelegramObject, scope=Scope.REQUEST)
_CONNECTION_PROVIDERS = (aiogram_update_provider, aiogram_event_provider)

# Root container in the dispatcher's workflow-data; per-update child in the
# per-update ``data`` dict (also the keyword-only param name ``inject`` adds).
# Named constants keep writer and reader in provable agreement.
_ROOT_CONTAINER_KEY = "modern_di_root_container"
_CHILD_CONTAINER_KEY = "modern_di_container"


class _DiMiddleware(BaseMiddleware):
    def __init__(self, container: Container) -> None:
        self.container = container

    async def __call__(
        self,
        handler: typing.Callable[[TelegramObject, dict[str, typing.Any]], typing.Awaitable[typing.Any]],
        event: TelegramObject,
        data: dict[str, typing.Any],
    ) -> typing.Any:  # noqa: ANN401
        child_container = self.container.build_child_container(
            scope=Scope.REQUEST,
            context={Update: event, TelegramObject: typing.cast("Update", event).event},
        )
        data[_CHILD_CONTAINER_KEY] = child_container
        try:
            return await handler(event, data)
        finally:
            await child_container.close_async()


def setup_di(dispatcher: Dispatcher, container: Container, *, auto_inject: bool = False) -> Container:
    dispatcher[_ROOT_CONTAINER_KEY] = container
    container.add_providers(*_CONNECTION_PROVIDERS)
    dispatcher.startup.register(container.open)
    dispatcher.shutdown.register(container.close_async)
    dispatcher.update.outer_middleware(_DiMiddleware(container))
    if auto_inject:
        dispatcher.startup.register(functools.partial(_inject_router, dispatcher))
    return container


def fetch_di_container(dispatcher: Dispatcher) -> Container:
    return typing.cast(Container, dispatcher[_ROOT_CONTAINER_KEY])


T = typing.TypeVar("T")
T_co = typing.TypeVar("T_co", covariant=True)


@dataclasses.dataclass(slots=True, frozen=True)
class _FromDI(typing.Generic[T_co]):
    dependency: providers.AbstractProvider[T_co] | type[T_co]


def FromDI(dependency: providers.AbstractProvider[T] | type[T]) -> T:  # noqa: N802
    return typing.cast(T, _FromDI(dependency))


def _parse_inject_params(func: typing.Callable[..., typing.Any]) -> dict[str, _FromDI[typing.Any]]:
    hints = typing.get_type_hints(func, include_extras=True)
    di_params: dict[str, _FromDI[typing.Any]] = {}
    for name, hint in hints.items():
        if name == "return":
            continue
        if typing.get_origin(hint) is typing.Annotated:
            for meta in typing.get_args(hint)[1:]:
                if isinstance(meta, _FromDI):
                    di_params[name] = meta
                    break
    return di_params


def inject(func: typing.Callable[..., typing.Awaitable[T]]) -> typing.Callable[..., typing.Awaitable[T]]:
    di_params = _parse_inject_params(func)
    if not di_params:
        func.__modern_di_injected__ = True  # ty: ignore[unresolved-attribute]
        return func

    original_signature = inspect.signature(func)
    visible_params = [p for name, p in original_signature.parameters.items() if name not in di_params]
    if _CHILD_CONTAINER_KEY not in original_signature.parameters:
        visible_params.append(
            inspect.Parameter(_CHILD_CONTAINER_KEY, kind=inspect.Parameter.KEYWORD_ONLY, annotation=Container),
        )

    async def wrapper(*args: typing.Any, **kwargs: typing.Any) -> T:  # noqa: ANN401
        container: Container = kwargs.pop(_CHILD_CONTAINER_KEY)
        resolved = {name: container.resolve_dependency(marker.dependency) for name, marker in di_params.items()}
        return await func(*args, **kwargs, **resolved)

    # NOT functools.wraps: aiogram unwraps __wrapped__ and would defeat __signature__.
    wrapper.__name__ = func.__name__  # ty: ignore[unresolved-attribute]
    wrapper.__qualname__ = func.__qualname__  # ty: ignore[unresolved-attribute]
    wrapper.__doc__ = func.__doc__
    wrapper.__module__ = func.__module__
    wrapper.__signature__ = original_signature.replace(parameters=visible_params)  # ty: ignore[unresolved-attribute]
    wrapper.__modern_di_injected__ = True  # ty: ignore[unresolved-attribute]
    return wrapper


def _inject_router(router: aiogram.Router) -> None:
    for sub_router in router.chain_tail:
        for observer in sub_router.observers.values():
            if observer.event_name == "update":
                continue
            for handler in observer.handlers:
                if not getattr(handler.callback, "__modern_di_injected__", False):
                    wrapped = HandlerObject(
                        callback=inject(handler.callback),
                        filters=handler.filters,
                        flags=handler.flags,
                    )
                    handler.callback = wrapped.callback
                    handler.params = wrapped.params
