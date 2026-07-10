import dataclasses

from aiogram.types import TelegramObject
from modern_di import Group, Scope, providers


@dataclasses.dataclass(kw_only=True, slots=True)
class SimpleCreator:
    dep1: str


@dataclasses.dataclass(kw_only=True, slots=True)
class DependentCreator:
    dep1: SimpleCreator


def fetch_event_type(event: TelegramObject | None = None) -> str:
    # Optional-with-default so construction-time validate=True treats the event
    # as optional (the providers are only registered by setup_di); the real
    # event still injects at runtime.
    return type(event).__name__ if event else ""


class Dependencies(Group):
    app_factory = providers.Factory(creator=SimpleCreator, kwargs={"dep1": "original"})
    request_factory = providers.Factory(scope=Scope.REQUEST, creator=DependentCreator, bound_type=None)
    event_type = providers.Factory(scope=Scope.REQUEST, creator=fetch_event_type)
