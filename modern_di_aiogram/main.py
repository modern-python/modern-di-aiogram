import functools
import inspect
import typing

import aiogram
from aiogram import BaseMiddleware, Dispatcher
from aiogram.dispatcher.event.handler import HandlerObject
from aiogram.types import TelegramObject, Update
from modern_di import Container, Scope, integrations, providers


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
        async with self.container.build_child_container(
            scope=Scope.REQUEST,
            context={Update: event, TelegramObject: typing.cast("Update", event).event},
        ) as child_container:
            data[_CHILD_CONTAINER_KEY] = child_container
            return await handler(event, data)


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


FromDI = integrations.from_di


def inject(func: typing.Callable[..., typing.Awaitable[T]]) -> typing.Callable[..., typing.Awaitable[T]]:
    di_params = integrations.parse_markers(func)
    if not di_params:
        integrations.mark_injected(func)
        return func

    original_signature = inspect.signature(func)
    visible_params = [p for name, p in original_signature.parameters.items() if name not in di_params]
    container_param_injected = _CHILD_CONTAINER_KEY not in original_signature.parameters
    if container_param_injected:
        visible_params.append(
            inspect.Parameter(_CHILD_CONTAINER_KEY, kind=inspect.Parameter.KEYWORD_ONLY, annotation=Container),
        )

    async def wrapper(*args: typing.Any, **kwargs: typing.Any) -> T:  # noqa: ANN401
        container: Container = (
            kwargs.pop(_CHILD_CONTAINER_KEY) if container_param_injected else kwargs[_CHILD_CONTAINER_KEY]
        )
        resolved = integrations.resolve_markers(container, di_params)
        return await func(*args, **kwargs, **resolved)

    # NOT functools.wraps: aiogram unwraps __wrapped__ and would defeat __signature__.
    wrapper.__name__ = func.__name__  # ty: ignore[unresolved-attribute]
    wrapper.__qualname__ = func.__qualname__  # ty: ignore[unresolved-attribute]
    wrapper.__doc__ = func.__doc__
    wrapper.__module__ = func.__module__
    wrapper.__signature__ = original_signature.replace(parameters=visible_params)  # ty: ignore[unresolved-attribute]
    integrations.mark_injected(wrapper)
    return wrapper


def _inject_router(router: aiogram.Router) -> None:
    for sub_router in router.chain_tail:
        for observer in sub_router.observers.values():
            if observer.event_name == "update":
                continue
            for handler in observer.handlers:
                if not integrations.is_injected(handler.callback):
                    wrapped = HandlerObject(
                        callback=inject(handler.callback),
                        filters=handler.filters,
                        flags=handler.flags,
                    )
                    handler.callback = wrapped.callback
                    handler.params = wrapped.params
