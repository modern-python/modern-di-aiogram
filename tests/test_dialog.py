import typing

import pytest
from aiogram import Dispatcher
from aiogram.filters import CommandStart
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from aiogram_dialog import Dialog, DialogManager, StartMode, Window, setup_dialogs
from aiogram_dialog.test_tools import BotClient, MockMessageManager
from aiogram_dialog.test_tools.keyboard import InlineButtonTextLocator
from aiogram_dialog.widgets.kbd import Button
from aiogram_dialog.widgets.text import Const, Format
from modern_di import Container, Group, Scope, providers

from modern_di_aiogram import setup_di
from modern_di_aiogram.dialog import FromDI, inject
from tests.dependencies import Dependencies, SimpleCreator


_TOKEN = "123456:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"  # noqa: S105

trace: list[typing.Any] = []


class MainSG(StatesGroup):
    window = State()


class SubSG(StatesGroup):
    window = State()


@inject
async def on_start(
    start_data: typing.Any,  # noqa: ANN401, ARG001
    manager: DialogManager,  # noqa: ARG001
    app: typing.Annotated[SimpleCreator, FromDI(SimpleCreator)],
) -> None:
    trace.append(("on_start", isinstance(app, SimpleCreator)))


@inject
async def on_process_result(
    start_data: typing.Any,  # noqa: ANN401, ARG001
    result: typing.Any,  # noqa: ANN401
    manager: DialogManager,  # noqa: ARG001
    app: typing.Annotated[SimpleCreator, FromDI(SimpleCreator)],
) -> None:
    trace.append(("on_process_result", isinstance(app, SimpleCreator), result))


@inject
async def main_getter(
    dialog_manager: DialogManager,  # noqa: ARG001
    app: typing.Annotated[SimpleCreator, FromDI(SimpleCreator)],
    **_kwargs: typing.Any,  # noqa: ANN401
) -> dict[str, str]:
    return {"name": app.dep1}


async def go_sub(_callback: typing.Any, _button: typing.Any, manager: DialogManager) -> None:  # noqa: ANN401
    await manager.start(SubSG.window)


@inject
async def sub_finish(
    _callback: typing.Any,  # noqa: ANN401
    _button: typing.Any,  # noqa: ANN401
    manager: DialogManager,
    app: typing.Annotated[SimpleCreator, FromDI(SimpleCreator)],
) -> None:
    trace.append(("on_click", isinstance(app, SimpleCreator)))
    await manager.done(result="RESULT")


async def _start_command(_message: Message, dialog_manager: DialogManager) -> None:
    await dialog_manager.start(MainSG.window, mode=StartMode.RESET_STACK)


@pytest.fixture
def dialog_setup() -> tuple[BotClient, MockMessageManager]:
    # Build the mock in the fixture so tests can read the rendered message; BotClient
    # exposes the dispatcher as `.dp`. Dialog/Window are aiogram Routers, which can be
    # attached to only one Dispatcher ever, so they're built fresh per test here rather
    # than as module-level singletons shared across the function-scoped fixture calls.
    trace.clear()
    main_dialog = Dialog(
        Window(
            Format("Main {name}"),
            Button(Const("ToSub"), id="tosub", on_click=go_sub),
            state=MainSG.window,
            getter=main_getter,
        ),
        on_start=on_start,
        on_process_result=on_process_result,
    )
    sub_dialog = Dialog(
        Window(
            Const("Sub"),
            Button(Const("Finish"), id="finish", on_click=sub_finish),
            state=SubSG.window,
        ),
    )
    dispatcher = Dispatcher()
    dispatcher.message.register(_start_command, CommandStart())
    dispatcher.include_router(main_dialog)
    dispatcher.include_router(sub_dialog)
    setup_di(dispatcher, Container(groups=[Dependencies], validate=True))
    mock = MockMessageManager()
    setup_dialogs(dispatcher, message_manager=mock)
    return BotClient(dispatcher), mock


async def test_getter_and_on_start_resolve(dialog_setup: tuple[BotClient, MockMessageManager]) -> None:
    client, mock = dialog_setup
    await client.dp.emit_startup()
    await client.send("/start")
    assert mock.last_message().text == "Main original"  # getter's FromDI shaped the text
    assert ("on_start", True) in trace  # 2-arg dialog-event callback resolved
    await client.dp.emit_shutdown()


async def test_on_click_and_on_process_result_resolve(
    dialog_setup: tuple[BotClient, MockMessageManager],
) -> None:
    client, mock = dialog_setup
    await client.dp.emit_startup()
    await client.send("/start")
    await client.click(mock.last_message(), InlineButtonTextLocator("ToSub"))  # go_sub -> start sub
    await client.click(mock.last_message(), InlineButtonTextLocator("Finish"))  # sub_finish -> done
    await client.dp.emit_shutdown()
    assert ("on_click", True) in trace  # 3-arg widget callback resolved
    assert ("on_process_result", True, "RESULT") in trace  # 3-arg dialog-event callback resolved


async def test_inject_passthrough_without_fromdi() -> None:
    async def getter(dialog_manager: DialogManager, **_kwargs: typing.Any) -> dict[str, str]:  # noqa: ARG001, ANN401
        return {}

    assert inject(getter) is getter
    assert await getter(None) == {}


async def test_child_closed_per_update() -> None:
    teardowns: list[str] = []

    class Boom(Group):
        resource = providers.Factory(
            scope=Scope.REQUEST,
            creator=SimpleCreator,
            kwargs={"dep1": "x"},
            bound_type=None,
            cache=providers.CacheSettings(finalizer=lambda _: teardowns.append("closed")),
        )

    class SG(StatesGroup):
        window = State()

    @inject
    async def getter(
        dialog_manager: DialogManager,  # noqa: ARG001
        _res: typing.Annotated[SimpleCreator, FromDI(Boom.resource)],
        **_kwargs: typing.Any,  # noqa: ANN401
    ) -> dict[str, str]:
        return {}

    dialog = Dialog(Window(Const("x"), state=SG.window, getter=getter))

    async def _start(_message: Message, dialog_manager: DialogManager) -> None:
        await dialog_manager.start(SG.window, mode=StartMode.RESET_STACK)

    dispatcher = Dispatcher()
    dispatcher.message.register(_start, CommandStart())
    dispatcher.include_router(dialog)
    setup_di(dispatcher, Container(groups=[Boom], validate=True))
    setup_dialogs(dispatcher, message_manager=MockMessageManager())
    client = BotClient(dispatcher)
    await client.dp.emit_startup()
    await client.send("/start")  # getter resolves Boom.resource; middleware closes the child after
    await client.dp.emit_shutdown()

    assert teardowns == ["closed"]
