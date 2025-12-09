import logging
import os
import uuid
from datetime import datetime

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME", "").lower()  # e.g. "@dvatransactionbot"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# deals: deal_id -> dict
DEALS = {}
# map message_id in group -> deal_id (so /Close as a reply works)
MSG_TO_DEAL = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type in ("group", "supergroup"):
        await update.message.reply_text(
            "👋🏻 Hi!\n"
            "I am a simple escrow helper bot.\n\n"
            "Use:\n"
            "/Add <amount> [short note]\n"
            "Then, when deal is completed, reply with /Close to close it."
        )
    else:
        await update.message.reply_text(
            "👋🏻 Hi!\n"
            "Add me to a supergroup and promote as admin.\n"
            "Then use /Add <amount> in that group."
        )


def parse_amount_and_note(args):
    if not args:
        return None, ""
    amount = args[0]
    note = " ".join(args[1:]) if len(args) > 1 else ""
    return amount, note


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    chat = msg.chat

    if chat.type not in ("group", "supergroup"):
        await msg.reply_text("Ye command sirf group / supergroup me use karo.")
        return

    # if command is like /Add@BotName, strip the bot mention
    if context.args and context.args[0].startswith("@") and context.args[0].lower() == BOT_USERNAME:
        args = context.args[1:]
    else:
        args = context.args

    amount, note = parse_amount_and_note(args)
    if amount is None:
        await msg.reply_text("Usage: /Add <amount> [short note]")
        return

    deal_id = str(uuid.uuid4())[:8]

    deal = {
        "id": deal_id,
        "chat_id": chat.id,
        "message_id": msg.message_id,
        "creator_id": msg.from_user.id,
        "amount": amount,
        "note": note,
        "status": "OPEN",
        "created_at": datetime.utcnow().isoformat(),
        "closed_at": None,
        "closed_by": None,
    }

    DEALS[deal_id] = deal
    MSG_TO_DEAL[(chat.id, msg.message_id)] = deal_id

    tagged_users = []
    if msg.entities:
        for ent in msg.entities:
            if ent.type == "mention":
                tagged_users.append(
                    msg.text[ent.offset : ent.offset + ent.length]
                )

    tags_str = " ".join(tagged_users) if tagged_users else ""

    reply_text = (
        f"📌 Escrow deal created.\n\n"
        f"ID: `{deal_id}`\n"
        f"Amount: {amount}\n"
        f"Note: {note or '-'}\n"
        f"Status: OPEN\n"
    )

    if tags_str:
        reply_text += f"\nParties: {tags_str}\n"

    reply_text += "\nDeal complete hone par is message ko reply karke /Close bhejo."

    await msg.reply_text(reply_text, parse_mode="Markdown")


async def cmd_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    chat = msg.chat

    if chat.type not in ("group", "supergroup"):
        await msg.reply_text("Ye command sirf group / supergroup me use karo.")
        return

    deal_id = None

    # Prefer reply: /Close as reply to /Add message
    if msg.reply_to_message:
        key = (chat.id, msg.reply_to_message.message_id)
        deal_id = MSG_TO_DEAL.get(key)

    # Fallback: /Close <deal_id>
    if not deal_id and context.args:
        deal_id = context.args[0]

    if not deal_id:
        await msg.reply_text(
            "Usage:\n"
            "- Reply to original /Add message with /Close\n"
            "  ya\n"
            "- /Close <deal_id>"
        )
        return

    deal = DEALS.get(deal_id)
    if not deal or deal["chat_id"] != chat.id:
        await msg.reply_text("Koi active deal nahi mila is ID ke saath.")
        return

    if deal["status"] == "CLOSED":
        await msg.reply_text("Ye deal pehle hi CLOSED hai.")
        return

    deal["status"] = "CLOSED"
    deal["closed_at"] = datetime.utcnow().isoformat()
    deal["closed_by"] = msg.from_user.id

    await msg.reply_text(
        f"✅ Deal CLOSED.\n\n"
        f"ID: `{deal_id}`\n"
        f"Amount: {deal['amount']}\n"
        f"Note: {deal['note'] or '-'}\n"
        f"Closed by: {msg.from_user.mention_html()}",
        parse_mode="HTML",
    )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN env var missing")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler(["Add", "add"], cmd_add))
    app.add_handler(CommandHandler(["Close", "close"], cmd_close))

    # optional: ignore all other text
    app.add_handler(MessageHandler(filters.COMMAND, lambda *_: None))

    app.run_polling()


if __name__ == "__main__":
    main()
