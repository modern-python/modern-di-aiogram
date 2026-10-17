import inspect
import typing
import warnings

from aiogram import Bot, Dispatcher
from aiogram.types import Message
from modern_di import Container

from modern_di_aiogram import FromDI, inject, setup_di
from tests.dependencies import Dependencies, SimpleCreator
from tests.factories import make_message_update


async def test_auto_inject_resolves_without_decorator(bot: Bot) -> None:
    dispatcher = Dispatcher()
    setup_di(dispatcher, Container(groups=[Dependencies]), auto_inject=True)
    seen: dict[str, typing.Any] = {}

    @dispatcher.message()
    async def handler(
        message: Message,  # noqa: ARG001
        app_instance: typing.Annotated[SimpleCreator, FromDI(SimpleCreator)],
    ) -> None:
        seen["dep1"] = app_instance.dep1

    await dispatcher.emit_startup()  # auto_inject wraps handlers here
    await dispatcher.feed_update(bot, make_message_update())
    await dispatcher.emit_shutdown()

    assert seen == {"dep1": "original"}


async def test_auto_inject_skips_already_injected(bot: Bot) -> None:
    dispatcher = Dispatcher()
    setup_di(dispatcher, Container(groups=[Dependencies]), auto_inject=True)
    seen: dict[str, typing.Any] = {}

    @dispatcher.message()
    @inject
    async def handler(
        message: Message,  # noqa: ARG001
        app: typing.Annotated[SimpleCreator, FromDI(SimpleCreator)],
    ) -> None:
        seen["app"] = app.dep1

    await dispatcher.emit_startup()
    await dispatcher.feed_update(bot, make_message_update())
    await dispatcher.emit_shutdown()

    assert seen == {"app": "original"}


async def test_auto_inject_runs_sync_handler(bot: Bot) -> None:
    dispatcher = Dispatcher()
    setup_di(dispatcher, Container(groups=[Dependencies]), auto_inject=True)
    seen: dict[str, typing.Any] = {}

    @dispatcher.message()
    def handler(
        message: Message,  # noqa: ARG001
        app_instance: typing.Annotated[SimpleCreator, FromDI(SimpleCreator)],
    ) -> None:
        seen["dep1"] = app_instance.dep1

    await dispatcher.emit_startup()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        await dispatcher.feed_update(bot, make_message_update())
    await dispatcher.emit_shutdown()

    assert seen == {"dep1": "original"}


async def test_auto_inject_keeps_handler_object_in_sync_with_callback() -> None:
    dispatcher = Dispatcher()
    setup_di(dispatcher, Container(groups=[Dependencies]), auto_inject=True)

    @dispatcher.message()
    def sync_handler(
        message: Message,
        app_instance: typing.Annotated[SimpleCreator, FromDI(SimpleCreator)],
    ) -> None: ...

    @dispatcher.message()
    async def async_handler(
        message: Message,
        app_instance: typing.Annotated[SimpleCreator, FromDI(SimpleCreator)],
    ) -> None: ...

    await dispatcher.emit_startup()
    await dispatcher.emit_shutdown()

    assert [h.awaitable for h in dispatcher.message.handlers] == [
        inspect.iscoroutinefunction(h.callback) for h in dispatcher.message.handlers
    ]
