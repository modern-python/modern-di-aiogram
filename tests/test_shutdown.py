import asyncio
import dataclasses
import logging
import typing

import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.methods import GetMe, TelegramMethod
from aiogram.types import Message, User
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from modern_di import Container, Group, Scope, providers
from modern_di.exceptions import ContainerClosedError

from modern_di_aiogram import setup_di
from tests.factories import make_message_update


@dataclasses.dataclass(kw_only=True)
class Resource:
    log: list[str] = dataclasses.field(default_factory=list)


def finalize_resource(resource: Resource) -> None:
    resource.log.append("finalized")


class Resources(Group):
    app_resource = providers.Factory(
        scope=Scope.APP, creator=Resource, bound_type=None, cache=providers.CacheSettings(finalizer=finalize_resource)
    )


@dataclasses.dataclass(kw_only=True)
class SlowHandler:
    started: asyncio.Event = dataclasses.field(default_factory=asyncio.Event)
    release: asyncio.Event = dataclasses.field(default_factory=asyncio.Event)
    shutdown_started: asyncio.Event = dataclasses.field(default_factory=asyncio.Event)
    seen: dict[str, Resource] = dataclasses.field(default_factory=dict)


def _make_dispatcher(slow: SlowHandler, **setup_kwargs: typing.Any) -> tuple[Dispatcher, Container]:  # noqa: ANN401
    dispatcher = Dispatcher()
    emit_shutdown = dispatcher.emit_shutdown

    async def mark_shutdown_started(*args: typing.Any, **kwargs: typing.Any) -> None:  # noqa: ANN401
        slow.shutdown_started.set()
        await emit_shutdown(*args, **kwargs)

    dispatcher.emit_shutdown = mark_shutdown_started  # ty: ignore[invalid-assignment]
    container = setup_di(dispatcher, Container(groups=[Resources]), **setup_kwargs)

    @dispatcher.message()
    async def handler(message: Message, modern_di_container: Container) -> None:  # noqa: ARG001
        slow.started.set()
        await slow.release.wait()
        resource = modern_di_container.resolve_provider(Resources.app_resource)
        resource.log.append("handled")
        slow.seen["app"] = resource

    return dispatcher, container


async def test_polling_waits_for_in_flight_update(bot: Bot, monkeypatch: pytest.MonkeyPatch) -> None:
    pending_updates = [make_message_update()]

    async def fake_call(
        _self: Bot,
        method: TelegramMethod[typing.Any],
        request_timeout: int | None = None,  # noqa: ARG001
    ) -> typing.Any:  # noqa: ANN401
        if isinstance(method, GetMe):
            return User(id=1, is_bot=True, first_name="Bot")
        if pending_updates:
            return [pending_updates.pop()]
        return await asyncio.get_running_loop().create_future()

    monkeypatch.setattr(Bot, "__call__", fake_call)
    slow = SlowHandler()
    dispatcher, container = _make_dispatcher(slow)

    polling = asyncio.create_task(
        dispatcher.start_polling(bot, handle_as_tasks=True, handle_signals=False, close_bot_session=False)
    )
    await slow.started.wait()
    stopping = asyncio.create_task(dispatcher.stop_polling())
    await slow.shutdown_started.wait()
    slow.release.set()
    await stopping
    await polling

    assert container.closed is True
    assert slow.seen["app"].log == ["handled", "finalized"]


@pytest.mark.parametrize("handle_in_background", [False, True])
async def test_webhook_waits_for_in_flight_update(bot: Bot, handle_in_background: bool) -> None:
    slow = SlowHandler()
    dispatcher, container = _make_dispatcher(slow)
    app = web.Application()
    SimpleRequestHandler(dispatcher, bot, handle_in_background=handle_in_background).register(app, path="/webhook")
    setup_application(app, dispatcher, bot=bot)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    posting = asyncio.create_task(
        client.post("/webhook", json=make_message_update().model_dump(mode="json", exclude_none=True))
    )
    await slow.started.wait()
    closing = asyncio.create_task(server.close())
    await slow.shutdown_started.wait()
    slow.release.set()
    await closing
    response = await posting
    response.release()
    await client.close()

    assert container.closed is True
    assert slow.seen["app"].log == ["handled", "finalized"]


async def test_shutdown_timeout_closes_root_and_warns(bot: Bot, caplog: pytest.LogCaptureFixture) -> None:
    slow = SlowHandler()
    dispatcher, container = _make_dispatcher(slow, shutdown_timeout=0.1)
    await dispatcher.emit_startup()
    feeding = asyncio.create_task(dispatcher.feed_update(bot, make_message_update()))
    await slow.started.wait()

    loop = asyncio.get_running_loop()
    started_at = loop.time()
    with caplog.at_level(logging.WARNING, logger="modern_di_aiogram"):
        # A separate task: on 3.11, coverage loses this frame's lines after the timeout cancels into it.
        await asyncio.create_task(dispatcher.emit_shutdown())
    elapsed = loop.time() - started_at

    assert container.closed is True
    assert 0.1 <= elapsed < 1  # noqa: PLR2004
    assert [record.getMessage() for record in caplog.records if record.name.startswith("modern_di_aiogram")] == [
        "Stopped waiting with 1 update(s) still in flight"
    ]
    slow.release.set()
    with pytest.raises(ContainerClosedError):
        await feeding


async def test_shutdown_does_not_wait_without_in_flight_updates(bot: Bot) -> None:
    slow = SlowHandler()
    slow.release.set()
    dispatcher, container = _make_dispatcher(slow, shutdown_timeout=None)

    for _ in range(2):
        await dispatcher.emit_startup()
        await dispatcher.feed_update(bot, make_message_update())
        async with asyncio.timeout(1):
            await dispatcher.emit_shutdown()
        assert container.closed is True

    assert slow.seen["app"].log == ["handled", "finalized"]


async def test_manage_lifespan_false_neither_waits_nor_closes(bot: Bot) -> None:
    slow = SlowHandler()
    dispatcher, container = _make_dispatcher(slow, manage_lifespan=False)

    async with container:
        await dispatcher.emit_startup()
        feeding = asyncio.create_task(dispatcher.feed_update(bot, make_message_update()))
        await slow.started.wait()
        async with asyncio.timeout(1):
            await dispatcher.emit_shutdown()
        assert container.closed is False
        slow.release.set()
        await feeding


@pytest.mark.parametrize("on_sub_router", [False, True])
@pytest.mark.parametrize("register_before_setup_di", [False, True])
async def test_shutdown_handlers_run_after_in_flight_updates(
    bot: Bot, on_sub_router: bool, register_before_setup_di: bool
) -> None:
    dispatcher = Dispatcher()
    router = dispatcher.include_router(Router()) if on_sub_router else dispatcher
    container = Container(groups=[Resources])
    release = asyncio.Event()

    async def user_hook() -> None:
        container.resolve_provider(Resources.app_resource).log.append("hook")

    if register_before_setup_di:
        router.shutdown.register(user_hook)
        setup_di(dispatcher, container)
    else:
        setup_di(dispatcher, container)
        router.shutdown.register(user_hook)

    @router.message()
    async def handler(message: Message, modern_di_container: Container) -> None:  # noqa: ARG001
        await release.wait()
        modern_di_container.resolve_provider(Resources.app_resource).log.append("handled")

    logs: list[list[str]] = []
    for _ in range(2):
        release.clear()
        await dispatcher.emit_startup()
        feeding = asyncio.create_task(dispatcher.feed_update(bot, make_message_update()))
        resource = container.resolve_provider(Resources.app_resource)
        shutdown = asyncio.create_task(dispatcher.emit_shutdown())
        for _ in range(10):
            await asyncio.sleep(0)
        release.set()
        await shutdown
        await feeding
        logs.append(resource.log)

    assert logs == [["handled", "hook", "finalized"]] * 2


def _timeout_warnings(caplog: pytest.LogCaptureFixture) -> int:
    return sum(record.name.startswith("modern_di_aiogram") for record in caplog.records)


@pytest.mark.parametrize("with_startup", [False, True])
async def test_shutdown_waits_once_per_cycle(bot: Bot, caplog: pytest.LogCaptureFixture, with_startup: bool) -> None:
    slow = SlowHandler()
    dispatcher, container = _make_dispatcher(slow, shutdown_timeout=0.01)
    dispatcher.include_router(Router())
    feeding = asyncio.create_task(dispatcher.feed_update(bot, make_message_update()))
    await slow.started.wait()

    with caplog.at_level(logging.WARNING, logger="modern_di_aiogram"):
        for cycle in (1, 2):
            if with_startup:
                await dispatcher.emit_startup()
            await asyncio.create_task(dispatcher.emit_shutdown())
            assert _timeout_warnings(caplog) == cycle
            assert container.closed is True
            dispatcher.include_router(Router())

    slow.release.set()
    with pytest.raises(ContainerClosedError):
        await feeding
