import typing

from aiogram import BaseMiddleware, Dispatcher
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


def setup_di(dispatcher: Dispatcher, container: Container) -> Container:
    dispatcher[_ROOT_CONTAINER_KEY] = container
    container.add_providers(*_CONNECTION_PROVIDERS)
    dispatcher.startup.register(container.open)
    dispatcher.shutdown.register(container.close_async)
    dispatcher.update.outer_middleware(_DiMiddleware(container))
    return container


def fetch_di_container(dispatcher: Dispatcher) -> Container:
    return typing.cast(Container, dispatcher[_ROOT_CONTAINER_KEY])
