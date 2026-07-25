import typing

import pytest
from aiogram import Bot
from aiogram.methods import TelegramMethod

from examples.app import dispatcher
from tests.factories import make_message_update


async def test_example_greets_using_real_di(bot: Bot, monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, typing.Any] = {}

    async def fake_call(
        _self: Bot,
        method: TelegramMethod[typing.Any],
        _request_timeout: int | None = None,
    ) -> None:
        sent["text"] = method.text  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

    # Only the transport (Bot's outgoing API call) is a double; DI resolution below is real.
    monkeypatch.setattr(Bot, "__call__", fake_call)

    await dispatcher.emit_startup()
    await dispatcher.feed_update(bot, make_message_update())
    await dispatcher.emit_shutdown()

    assert sent == {"text": "Hello, Tester!"}
