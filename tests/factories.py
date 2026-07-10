import datetime

from aiogram.types import Chat, Message, Update, User


def make_message_update(text: str = "hi", update_id: int = 1) -> Update:
    return Update(
        update_id=update_id,
        message=Message(
            message_id=1,
            date=datetime.datetime.now(tz=datetime.timezone.utc),
            chat=Chat(id=1, type="private"),
            from_user=User(id=1, is_bot=False, first_name="Tester"),
            text=text,
        ),
    )
