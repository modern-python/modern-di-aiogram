from aiogram import Dispatcher
from modern_di import Container

import modern_di_aiogram
from modern_di_aiogram import fetch_di_container
from tests.dependencies import Dependencies


def test_fetch_returns_the_same_container(dispatcher: Dispatcher) -> None:
    assert isinstance(fetch_di_container(dispatcher), Container)


def test_setup_di_returns_the_container() -> None:
    dispatcher = Dispatcher()
    container = Container(groups=[Dependencies], validate=True)
    assert modern_di_aiogram.setup_di(dispatcher, container) is container


async def test_startup_opens_and_shutdown_closes(dispatcher: Dispatcher) -> None:
    container = fetch_di_container(dispatcher)
    await container.close_async()
    assert container.closed is True
    await dispatcher.emit_startup()
    assert container.closed is False  # startup wiring reopened it
    await dispatcher.emit_shutdown()
    assert container.closed is True


async def test_restart_reopens_without_error(dispatcher: Dispatcher) -> None:
    container = fetch_di_container(dispatcher)
    await dispatcher.emit_startup()
    await dispatcher.emit_shutdown()
    assert container.closed is True
    await dispatcher.emit_startup()  # second cycle must not raise ContainerClosedError
    assert container.closed is False
    await dispatcher.emit_shutdown()
