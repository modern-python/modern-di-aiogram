# modern-di-aiogram

[Modern-DI](https://github.com/modern-python/modern-di) integration for [aiogram](https://docs.aiogram.dev) 3.x.

## Quickstart

```python
import typing

from aiogram import Bot, Dispatcher
from aiogram.types import Message
from modern_di import Container, Group, Scope, providers
from modern_di_aiogram import FromDI, inject, setup_di


class Settings:
    def __init__(self) -> None:
        self.greeting = "hello"


class Dependencies(Group):
    settings = providers.Factory(scope=Scope.APP, creator=Settings)


dispatcher = Dispatcher()
setup_di(dispatcher, Container(groups=[Dependencies], validate=True))


@dispatcher.message()
@inject
async def greet(message: Message, settings: typing.Annotated[Settings, FromDI(Dependencies.settings)]) -> None:
    await message.answer(f"{settings.greeting}, {message.from_user.first_name}")
```

See the [documentation](https://modern-di.modern-python.org) for the full guide, including `auto_inject`.
