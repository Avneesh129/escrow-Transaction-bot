import logging
import uuid
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import os
BOT_TOKEN = os.getenv("BOT_TOKEN")

ADMIN_IDS = {5550057048, 5986685988, 6115650303, 7088910329, 1742254233}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

ESCROWS = {}


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Manual Escrow Bot me welcome!\n\n"
        "/new_escrow @buyer @seller amount terms...\n"
        "/my_escrows  – tumhare saare deals\n\n"
        "Buyer payment proof bhejne ke liye message likhe:\n"
        "proof <escrow_id> <txid ya note>"
    )
    await update.message.reply_text(text)


async def new_escrow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 3:
        await update.message.reply_text(
            "Usage: /new_escrow @buyer @seller amount terms..."
        )
        return

    buyer_username = args[0]
    seller_username = args[1]
    amount = args[2]
    terms = " ".join(args[3:]) if len(args) > 3 else ""

    escrow_id = str(uuid.uuid4())[:8]

    ESCROWS[escrow_id] = {
        "id": escrow_id,
        "creator_id": update.effective_user.id,
        "buyer_username": buyer_username,
        "seller_username": seller_username,
        "amount": amount,
        "terms": terms,
        "status": "PENDING_PAYMENT",
        "proof": None,
        "approved_by": None,
        "approved_at": None,
        "cancelled_by": None,
        "cancel_reason": None,
        "created_at": datetime.utcnow().isoformat(),
    }

    text = (
        f"Escrow ban gaya.\n\n"
        f"ID: {escrow_id}\n"
        f"Buyer: {buyer_username}\n"
        f"Seller: {seller_username}\n"
        f"Amount: {amount}\n"
        f"Status: PENDING_PAYMENT\n"
        f"Terms: {terms}\n\n"
        "Buyer payment ke baad yeh message bheje:\n"
        f"proof {escrow_id} <txid ya note>"
    )
    await update.message.reply_text(text)


async def my_escrows(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uname = f"@{user.username}" if user.username else None

    lines = []
    for e in ESCROWS.values():
        if (
            e["creator_id"] == user.id
            or (uname and (e["buyer_username"] == uname or e["seller_username"] == uname))
        ):
            lines.append(
                f"{e['id']}: {e['buyer_username']} -> {e['seller_username']} "
                f"{e['amount']} [{e['status']}]"
            )

    if not lines:
        await update.message.reply_text("Tumhare naam ka koi escrow nahi mila.")
    else:
        await update.message.reply_text("\n".join(lines))


async def handle_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    parts = text.split(maxsplit=2)
    if len(parts) < 3 or parts[0].lower() != "proof":
        return

    _, escrow_id, proof_text = parts
    e = ESCROWS.get(escrow_id)
    if not e:
        await update.message.reply_text("Galat escrow ID.")
        return

    e["proof"] = proof_text
    e["status"] = "AWAITING_ADMIN_APPROVAL"

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Release (Approve)", callback_data=f"approve:{escrow_id}"
                ),
                InlineKeyboardButton(
                    "❌ Cancel & Refund", callback_data=f"cancel:{escrow_id}"
                ),
            ]
        ]
    )

    text = (
        f"Proof mil gaya escrow {escrow_id} ke liye.\n\n"
        f"Buyer: {e['buyer_username']}\n"
        f"Seller: {e['seller_username']}\n"
        f"Amount: {e['amount']}\n"
        f"Proof: {proof_text}\n\n"
        "Admin approval ka wait ho raha hai."
    )

    await update.message.reply_text(text, reply_markup=keyboard)


async def approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.edit_message_text("Tum admin nahi ho, approve/cancel nahi kar sakte.")
        return

    data = query.data
    action, escrow_id = data.split(":", 1)

    e = ESCROWS.get(escrow_id)
    if not e:
        await query.edit_message_text("Escrow nahi mila.")
        return

    if e["status"] in ("RELEASED", "CANCELLED"):
        await query.edit_message_text(
            f"Escrow {escrow_id} already {e['status']} hai."
        )
        return

    if action == "approve":
        e["status"] = "RELEASED"
        e["approved_by"] = user_id
        e["approved_at"] = datetime.utcnow().isoformat()
        text = (
            f"✅ Escrow {escrow_id} RELEASED.\n\n"
            f"Amount: {e['amount']}\n"
            f"Buyer: {e['buyer_username']}\n"
            f"Seller: {e['seller_username']}\n\n"
            "Admin ne release approve kar diya.\n"
            "Funds seller ko off‑bot de do agar abhi nahi diye."
        )
    else:
        e["status"] = "CANCELLED"
        e["cancelled_by"] = user_id
        e["cancel_reason"] = "Admin cancelled via button"
        text = (
            f"❌ Escrow {escrow_id} CANCELLED.\n\n"
            f"Buyer: {e['buyer_username']}\n"
            f"Seller: {e['seller_username']}\n\n"
            "Admin ne deal cancel kar di.\n"
            "Buyer ko off‑bot refund karna hai."
        )

    await query.edit_message_text(text)


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("new_escrow", new_escrow))
    app.add_handler(CommandHandler("my_escrows", my_escrows))
    app.add_handler(CallbackQueryHandler(approval_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_proof))

    app.run_polling()


if __name__ == "__main__":
    main()
