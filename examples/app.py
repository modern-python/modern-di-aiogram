# Minimal modern-di + aiogram example.
# Run for real (needs a real bot token): BOT_TOKEN=<token> python -m examples.app
import asyncio
import dataclasses
import os
import typing

from aiogram import Bot, Dispatcher
from aiogram.types import Message
from modern_di import Container, Group, Scope, providers

from modern_di_aiogram import FromDI, inject, setup_di


@dataclasses.dataclass(kw_only=True)
class Settings:
    greeting: str = "Hello"


@dataclasses.dataclass(kw_only=True)
class GreetingService:
    settings: Settings  # auto-injected by type

    def greet(self, name: str) -> str:
        return f"{self.settings.greeting}, {name}!"


class Dependencies(Group):
    settings = providers.Factory(scope=Scope.APP, creator=Settings)
    service = providers.Factory(scope=Scope.REQUEST, creator=GreetingService)


dispatcher = Dispatcher()
container = Container(groups=[Dependencies], validate=True)
setup_di(dispatcher, container)


@dispatcher.message()
@inject
async def greet(
    message: Message,
    service: typing.Annotated[GreetingService, FromDI(Dependencies.service)],
) -> None:
    name = message.from_user.first_name if message.from_user else "there"
    await message.answer(service.greet(name))


async def _run() -> None:  # pragma: no cover
    bot = Bot(token=os.environ["BOT_TOKEN"])
    await dispatcher.start_polling(bot)


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_run())
