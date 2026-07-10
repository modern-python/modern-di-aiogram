import typing

from aiogram import Bot, Dispatcher
from aiogram.types import Message
from modern_di import Container

from modern_di_aiogram import FromDI, setup_di
from tests.dependencies import Dependencies, SimpleCreator
from tests.factories import make_message_update


async def test_auto_inject_resolves_without_decorator(bot: Bot) -> None:
    dispatcher = Dispatcher()
    setup_di(dispatcher, Container(groups=[Dependencies], validate=True), auto_inject=True)
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
