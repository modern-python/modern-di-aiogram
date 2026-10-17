import dataclasses
import typing
from collections.abc import Callable

import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message
from modern_di import Container, Group, Scope, providers

import modern_di_aiogram
from modern_di_aiogram import FromDI, fetch_di_container, inject
from tests.dependencies import Dependencies
from tests.factories import make_message_update


def test_fetch_returns_the_same_container(dispatcher: Dispatcher) -> None:
    assert isinstance(fetch_di_container(dispatcher), Container)


def test_setup_di_returns_the_container() -> None:
    dispatcher = Dispatcher()
    container = Container(groups=[Dependencies])
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


@dataclasses.dataclass(kw_only=True)
class Resource:
    closed_count: int = 0


def close_resource(resource: Resource) -> None:
    resource.closed_count += 1


class Resources(Group):
    app_resource = providers.Factory(
        scope=Scope.APP, creator=Resource, bound_type=None, cache=providers.CacheSettings(finalizer=close_resource)
    )
    request_resource = providers.Factory(
        scope=Scope.REQUEST, creator=Resource, bound_type=None, cache=providers.CacheSettings(finalizer=close_resource)
    )


def _register_capturing_handler(dispatcher: Dispatcher, seen: dict[str, Resource]) -> None:
    @dispatcher.message()
    @inject
    async def handler(
        message: Message,  # noqa: ARG001
        app_resource: typing.Annotated[Resource, FromDI(Resources.app_resource)],
        request_resource: typing.Annotated[Resource, FromDI(Resources.request_resource)],
    ) -> None:
        seen["app"] = app_resource
        seen["request"] = request_resource


async def test_manage_lifespan_false_leaves_the_root_alone(bot: Bot) -> None:
    dispatcher = Dispatcher()
    container = modern_di_aiogram.setup_di(dispatcher, Container(groups=[Resources]), manage_lifespan=False)
    seen: dict[str, Resource] = {}
    _register_capturing_handler(dispatcher, seen)

    await dispatcher.emit_startup()
    await dispatcher.feed_update(bot, make_message_update())
    await dispatcher.emit_shutdown()

    assert container.closed is False
    assert seen["app"].closed_count == 0
    assert seen["request"].closed_count == 1
    await container.close_async()


async def test_manage_lifespan_false_lets_the_user_own_the_root(bot: Bot) -> None:
    dispatcher = Dispatcher()
    container = modern_di_aiogram.setup_di(dispatcher, Container(groups=[Resources]), manage_lifespan=False)
    seen: dict[str, Resource] = {}
    _register_capturing_handler(dispatcher, seen)

    async with container:
        await dispatcher.emit_startup()
        await dispatcher.feed_update(bot, make_message_update())
        await dispatcher.emit_shutdown()
        assert seen["app"].closed_count == 0

    assert container.closed is True
    assert seen["app"].closed_count == 1
    assert seen["request"].closed_count == 1


class _CloseCountingContainer(Container):
    close_calls = 0

    async def close_async(self) -> None:
        self.close_calls += 1
        await super().close_async()


def _shutdown_on_dispatcher(dispatcher: Dispatcher) -> Router:
    return dispatcher


def _shutdown_on_sub_router(dispatcher: Dispatcher) -> Router:
    return dispatcher.include_router(Router())


def _shutdown_on_nested_router(dispatcher: Dispatcher) -> Router:
    router = dispatcher.include_router(Router())
    router.include_router(Router())
    return router


@pytest.mark.parametrize("pick_router", [_shutdown_on_dispatcher, _shutdown_on_sub_router, _shutdown_on_nested_router])
@pytest.mark.parametrize("register_before_setup_di", [False, True])
async def test_shutdown_handlers_see_the_open_root(
    pick_router: Callable[[Dispatcher], Router], register_before_setup_di: bool
) -> None:
    dispatcher = Dispatcher()
    container = _CloseCountingContainer(groups=[Resources])
    seen: list[tuple[Resource, int]] = []

    async def user_hook() -> None:
        resource = container.resolve_provider(Resources.app_resource)
        seen.append((resource, resource.closed_count))

    if register_before_setup_di:
        pick_router(dispatcher).shutdown.register(user_hook)
        modern_di_aiogram.setup_di(dispatcher, container)
    else:
        modern_di_aiogram.setup_di(dispatcher, container)
        pick_router(dispatcher).shutdown.register(user_hook)

    for cycle in (1, 2):
        await dispatcher.emit_startup()
        await dispatcher.emit_shutdown()
        assert [(resource.closed_count, at_hook) for resource, at_hook in seen] == [(1, 0)] * cycle
        assert container.closed is True
        assert container.close_calls == cycle


async def test_router_included_between_runs_sees_the_open_root() -> None:
    dispatcher = Dispatcher()
    container = _CloseCountingContainer(groups=[Resources])
    modern_di_aiogram.setup_di(dispatcher, container)
    dispatcher.include_router(Router())
    await dispatcher.emit_startup()
    await dispatcher.emit_shutdown()
    seen: list[tuple[Resource, int]] = []

    @dispatcher.include_router(Router()).shutdown()
    async def user_hook() -> None:
        resource = container.resolve_provider(Resources.app_resource)
        seen.append((resource, resource.closed_count))

    await dispatcher.emit_startup()
    await dispatcher.emit_shutdown()

    assert [(resource.closed_count, at_hook) for resource, at_hook in seen] == [(1, 0)]
    assert container.close_calls == 2  # noqa: PLR2004


async def test_shutdown_without_startup_closes_the_root() -> None:
    dispatcher = Dispatcher()
    container = modern_di_aiogram.setup_di(dispatcher, _CloseCountingContainer(groups=[Resources]))
    dispatcher.include_router(Router())
    resource = container.resolve_provider(Resources.app_resource)

    await dispatcher.emit_shutdown()

    assert container.closed is True
    assert resource.closed_count == 1
