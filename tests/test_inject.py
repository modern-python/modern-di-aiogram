import contextlib
import typing

from aiogram import Bot, Dispatcher
from aiogram.types import Message
from modern_di import Container, Group, Scope, providers

from modern_di_aiogram import FromDI, inject, setup_di
from tests.dependencies import Dependencies, DependentCreator, SimpleCreator
from tests.factories import make_message_update


async def test_inject_resolves_app_request_and_event(dispatcher: Dispatcher, bot: Bot) -> None:
    seen: dict[str, typing.Any] = {}

    @dispatcher.message()
    @inject
    async def handler(
        message: Message,  # noqa: ARG001
        app_instance: typing.Annotated[SimpleCreator, FromDI(SimpleCreator)],
        request_instance: typing.Annotated[DependentCreator, FromDI(Dependencies.request_factory)],
        event_type: typing.Annotated[str, FromDI(Dependencies.event_type)],
    ) -> None:
        seen["app_ok"] = isinstance(app_instance, SimpleCreator)
        seen["request_ok"] = isinstance(request_instance, DependentCreator)
        seen["distinct"] = request_instance.dep1 is not app_instance
        seen["event_type"] = event_type

    await dispatcher.emit_startup()
    await dispatcher.feed_update(bot, make_message_update())
    await dispatcher.emit_shutdown()

    assert seen == {"app_ok": True, "request_ok": True, "distinct": True, "event_type": "Message"}


async def test_inject_is_noop_without_fromdi(dispatcher: Dispatcher, bot: Bot) -> None:
    seen: dict[str, typing.Any] = {}

    @dispatcher.message()
    @inject
    async def handler(message: Message) -> None:
        seen["text"] = message.text

    await dispatcher.emit_startup()
    await dispatcher.feed_update(bot, make_message_update(text="plain"))
    await dispatcher.emit_shutdown()

    assert seen == {"text": "plain"}


async def test_child_container_closed_on_handler_error(bot: Bot) -> None:
    teardowns: list[str] = []

    class Boom(Group):
        resource = providers.Factory(
            scope=Scope.REQUEST,
            creator=SimpleCreator,
            kwargs={"dep1": "x"},
            bound_type=None,
            cache=providers.CacheSettings(finalizer=lambda _: teardowns.append("closed")),
        )

    dispatcher = Dispatcher()
    setup_di(dispatcher, Container(groups=[Boom], validate=True))

    @dispatcher.message()
    @inject
    async def handler(
        message: Message,  # noqa: ARG001
        _res: typing.Annotated[SimpleCreator, FromDI(Boom.resource)],
    ) -> None:
        msg = "boom"
        raise ValueError(msg)

    await dispatcher.emit_startup()
    with contextlib.suppress(ValueError):  # aiogram may re-raise an unhandled handler error
        await dispatcher.feed_update(bot, make_message_update())
    await dispatcher.emit_shutdown()

    assert teardowns == ["closed"]  # per-update child closed (finalizer ran) on the error path
