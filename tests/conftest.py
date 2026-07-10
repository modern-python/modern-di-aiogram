import typing

import pytest
from aiogram import Bot, Dispatcher
from modern_di import Container

from modern_di_aiogram import setup_di
from tests.dependencies import Dependencies


# Valid token *format*; never used for network (no handler calls the bot).
_TOKEN = "123456:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"  # noqa: S105


@pytest.fixture
async def bot() -> typing.AsyncIterator[Bot]:
    bot_ = Bot(token=_TOKEN)
    yield bot_
    await bot_.session.close()


@pytest.fixture
def dispatcher() -> Dispatcher:
    dispatcher_ = Dispatcher()
    setup_di(dispatcher_, container=Container(groups=[Dependencies], validate=True))
    return dispatcher_
