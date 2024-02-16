from typing import Callable, Optional, Any
import asyncio
import dataclasses
import logging
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)
import telegram


@dataclasses.dataclass
class TgIncomingMsg:
    user_id: int
    user_name: str
    text: str
    keyboard_callback: str | None = None


@dataclasses.dataclass
class InlineKeyboardButton:
    text: str
    callback_data: str


@dataclasses.dataclass
class TgOutgoingMsg:
    user_id: int
    user_name: str | None
    text: str
    inline_keyboard: list[list[InlineKeyboardButton]] | None = None
    keyboard_below: Optional[str] = None
    parse_mode: Optional[str] = None


OnMessageType = Callable[[TgIncomingMsg], Optional[str]]


class Tg:
    @property
    def on_message(self) -> OnMessageType:
        return self._on_message

    @on_message.setter
    def on_message(self, value: OnMessageType) -> None:
        self._on_message = value

    def send_message(self, m: TgOutgoingMsg):
        raise NotImplementedError()


class TelegramMock(Tg):
    def __init__(self):
        super().__init__()
        self.outgoing: list[TgOutgoingMsg] = []  # type: ignore
        self.incoming: list[TgIncomingMsg] = []  # type: ignore
        self.admin_contacts: Optional[list[str]] = None  # type: ignore

    def send_message(self, m: TgOutgoingMsg):
        if not isinstance(m, TgOutgoingMsg):
            raise ValueError()
        self.outgoing.append(m)

    def emulate_incoming_message(
        self,
        from_user_id: int,
        from_user_name: str,
        text: str,
        keyboard_callback: str | None = None,
    ):
        m = TgIncomingMsg(from_user_id, from_user_name, text, keyboard_callback)
        self.incoming.append(m)
        if self.on_message is not None:
            self.on_message(m)


class TelegramReal(Tg):
    def __init__(self, token: str):
        self.application: Application = Application.builder().token(token).build()
        self.application.add_handler(
            MessageHandler(filters.TEXT, self._default_handler)
        )
        self.application.add_handler(CallbackQueryHandler(self._callback_query_handler))
        self.admin_contacts: Optional[list[str]] = None

    def run_forever(self):
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

    async def _default_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        if (
            update.effective_chat is None
            or update.effective_chat.username is None
            or update.message is None
            or update.message.text is None
        ):
            logging.warning(f"got invalid message. Update: {update}")
            return
        message = TgIncomingMsg(
            update.effective_chat.id,
            update.effective_chat.username,
            update.message.text,
        )
        try:
            self.on_message(message)
        except ValueError as e:
            await update.message.reply_text(f"Error: {str(e)}")

    async def _callback_query_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        # logging.info(f"got callback query. Update: {update}")
        query = update.callback_query
        if query is None:
            logging.warning(f"got invalid callback query. Update: {update}")
            return

        if update.effective_chat is None or update.effective_chat.username is None:
            logging.warning(f"got invalid query callback update. Update: {update}")
            return
        message = TgIncomingMsg(
            update.effective_chat.id,
            update.effective_chat.username,
            "",
            keyboard_callback=query.data,
        )

        replace_text: Optional[str] = None
        try:
            replace_text = self.on_message(message)
        except ValueError as e:
            logging.error(f"Error: {str(e)}")

        # CallbackQueries need to be answered, even if no notification to the user is needed
        # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
        await query.answer()
        if replace_text is not None:
            lines = []
            if (
                update.callback_query is not None
                and update.callback_query.message is not None
                and update.callback_query.message.text is not None
            ):
                lines += [update.callback_query.message.text, ""]
            s = "PREV + " if lines else ""
            logging.info(f"replacing text: {s}{replace_text}")
            lines.append(replace_text)
            text = "\n".join(lines)
            await query.edit_message_text(text=text, parse_mode="Markdown")

    def send_message(self, m: TgOutgoingMsg):
        reply_markup: Any = None
        if m.keyboard_below is not None:
            assert isinstance(m.keyboard_below, list)
            reply_markup = (
                telegram.ReplyKeyboardMarkup(
                    m.keyboard_below, resize_keyboard=True, one_time_keyboard=True
                )
                if len(m.keyboard_below) > 0
                else ReplyKeyboardRemove()
            )
        elif m.inline_keyboard:
            keyboard = [
                [
                    telegram.InlineKeyboardButton(
                        button.text, callback_data=button.callback_data
                    )
                    for button in row
                ]
                for row in m.inline_keyboard
            ]
            reply_markup = telegram.InlineKeyboardMarkup(keyboard)

        asyncio.create_task(
            self.application.bot.send_message(
                m.user_id, m.text, parse_mode=m.parse_mode, reply_markup=reply_markup
            )
        )
