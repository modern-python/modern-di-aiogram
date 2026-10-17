import asyncio
import contextlib
import functools
import inspect
import logging
import typing

import aiogram
from aiogram import BaseMiddleware, Dispatcher
from aiogram.dispatcher.event.handler import HandlerObject
from aiogram.types import TelegramObject, Update
from aiogram.types.update import UpdateTypeLookupError
from modern_di import Container, Scope, integrations, providers


aiogram_update_provider = providers.ContextProvider(Update, scope=Scope.REQUEST)
aiogram_event_provider = providers.ContextProvider(TelegramObject, scope=Scope.REQUEST)
_CONNECTION_PROVIDERS = (aiogram_update_provider, aiogram_event_provider)

# Root container in the dispatcher's workflow-data; per-update child in the
# per-update ``data`` dict (also the keyword-only param name ``inject`` adds).
# Named constants keep writer and reader in provable agreement.
_ROOT_CONTAINER_KEY = "modern_di_root_container"
_CHILD_CONTAINER_KEY = "modern_di_container"

logger = logging.getLogger(__name__)


def _fetch_child_container(data: typing.Mapping[str, typing.Any]) -> Container:
    try:
        return typing.cast(Container, data[_CHILD_CONTAINER_KEY])
    except KeyError:
        msg = (
            "No modern-di container found for this update. "
            "Call setup_di(dispatcher, container) so updates pass through the modern-di middleware "
            "before using @inject."
        )
        raise RuntimeError(msg) from None


class _DiMiddleware(BaseMiddleware):
    def __init__(self, container: Container) -> None:
        self.container = container
        self.in_flight = 0
        self._idle: asyncio.Event | None = None

    async def __call__(
        self,
        handler: typing.Callable[[TelegramObject, dict[str, typing.Any]], typing.Awaitable[typing.Any]],
        event: TelegramObject,
        data: dict[str, typing.Any],
    ) -> typing.Any:  # noqa: ANN401
        context: dict[type[typing.Any], typing.Any] = {Update: event}
        with contextlib.suppress(UpdateTypeLookupError):
            context[TelegramObject] = typing.cast("Update", event).event
        self.in_flight += 1
        try:
            async with self.container.build_child_container(scope=Scope.REQUEST, context=context) as child_container:
                data[_CHILD_CONTAINER_KEY] = child_container
                return await handler(event, data)
        finally:
            self.in_flight -= 1
            if not self.in_flight and self._idle is not None:
                self._idle.set()

    async def wait_idle(self) -> None:
        if not self.in_flight:
            return
        self._idle = asyncio.Event()
        try:
            await self._idle.wait()
        finally:
            self._idle = None


def setup_di(
    dispatcher: Dispatcher,
    container: Container,
    *,
    auto_inject: bool = False,
    manage_lifespan: bool = True,
    shutdown_timeout: float | None = None,
) -> Container:
    dispatcher[_ROOT_CONTAINER_KEY] = container
    container.add_providers(*_CONNECTION_PROVIDERS)
    middleware = _DiMiddleware(container)
    if manage_lifespan:

        async def wait_in_flight() -> None:
            try:
                async with asyncio.timeout(shutdown_timeout):
                    await middleware.wait_idle()
            except TimeoutError:
                logger.warning("Stopped waiting with %d update(s) still in flight", middleware.in_flight)

        async def close_root() -> None:
            await container.close_async()

        dispatcher.shutdown.register(wait_in_flight)
        dispatcher.shutdown.register(close_root)
        close_observer = dispatcher.shutdown

        def open_root() -> None:
            nonlocal close_observer
            container.open()
            dispatcher.shutdown.handlers = [
                HandlerObject(callback=wait_in_flight),
                *(handler for handler in dispatcher.shutdown.handlers if handler.callback is not wait_in_flight),
            ]
            close_observer.handlers = [
                handler for handler in close_observer.handlers if handler.callback is not close_root
            ]
            *_, last_router = dispatcher.chain_tail
            close_observer = last_router.shutdown
            close_observer.register(close_root)

        dispatcher.startup.register(open_root)
    dispatcher.update.outer_middleware(middleware)
    if auto_inject:
        dispatcher.startup.register(functools.partial(_inject_router, dispatcher))
    return container


def fetch_di_container(dispatcher: Dispatcher) -> Container:
    return typing.cast(Container, dispatcher[_ROOT_CONTAINER_KEY])


T = typing.TypeVar("T")


FromDI = integrations.from_di


def inject(func: typing.Callable[..., T]) -> typing.Callable[..., T]:
    di_params = integrations.parse_markers(func)
    if not di_params:
        integrations.mark_injected(func)
        return func

    original_signature = inspect.signature(func)
    visible_params = [p for name, p in original_signature.parameters.items() if name not in di_params]
    container_param_injected = _CHILD_CONTAINER_KEY not in original_signature.parameters
    if container_param_injected:
        has_var_keyword = bool(visible_params) and visible_params[-1].kind is inspect.Parameter.VAR_KEYWORD
        visible_params.insert(
            len(visible_params) - has_var_keyword,
            inspect.Parameter(_CHILD_CONTAINER_KEY, kind=inspect.Parameter.KEYWORD_ONLY, annotation=Container),
        )

    def resolve(kwargs: dict[str, typing.Any]) -> dict[str, typing.Any]:
        container = _fetch_child_container(kwargs)
        if container_param_injected:
            del kwargs[_CHILD_CONTAINER_KEY]
        for name in di_params:
            kwargs.pop(name, None)
        return integrations.resolve_markers(container, di_params)

    wrapper: typing.Callable[..., typing.Any]
    if inspect.iscoroutinefunction(func):

        async def async_wrapper(*args: typing.Any, **kwargs: typing.Any) -> typing.Any:  # noqa: ANN401
            resolved = resolve(kwargs)
            return await func(*args, **kwargs, **resolved)

        wrapper = async_wrapper
    else:

        def sync_wrapper(*args: typing.Any, **kwargs: typing.Any) -> T:  # noqa: ANN401
            resolved = resolve(kwargs)
            return func(*args, **kwargs, **resolved)

        wrapper = sync_wrapper

    # NOT functools.wraps: aiogram unwraps __wrapped__ and would defeat __signature__.
    wrapper.__name__ = func.__name__  # ty: ignore[unresolved-attribute]
    wrapper.__qualname__ = func.__qualname__  # ty: ignore[unresolved-attribute]
    wrapper.__doc__ = func.__doc__
    wrapper.__module__ = func.__module__
    wrapper.__signature__ = original_signature.replace(parameters=visible_params)  # ty: ignore[invalid-assignment]
    integrations.mark_injected(wrapper)
    return typing.cast(typing.Callable[..., T], wrapper)


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
                    handler.awaitable = wrapped.awaitable
                    handler.params = wrapped.params
                    handler.varkw = wrapped.varkw
