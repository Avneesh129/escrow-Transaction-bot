from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
import uuid
from datetime import datetime

BOT_TOKEN = "YOUR_BOT_TOKEN"
ADMIN_IDS = {123456789}

ESCROWS = {}  # demo in-memory store


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


async def new_escrow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /new_escrow @buyer @seller amount
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("Usage: /new_escrow @buyer @seller amount")
        return

    buyer, seller, amount = args[0], args[1], args[2]
    escrow_id = str(uuid.uuid4())[:8]
    ESCROWS[escrow_id] = {
        "id": escrow_id,
        "buyer": buyer,
        "seller": seller,
        "amount": amount,
        "status": "PENDING_PAYMENT",
        "proof": None,
        "approved_by": None,
        "approved_at": None,
        "cancelled_by": None,
        "cancel_reason": None,
    }

    await update.message.reply_text(
        f"Escrow {escrow_id} created.\n"
        f"Buyer: {buyer}\nSeller: {seller}\nAmount: {amount}\n"
        "Buyer, pay off‑bot and then send: proof <id> <txid or note>"
    )


async def handle_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # text format: "proof <escrow_id> <txid or note>"
    text = update.message.text or ""
    parts = text.split(maxsplit=2)
    if len(parts) < 3 or parts[0].lower() != "proof":
        return

    _, escrow_id, proof_text = parts
    e = ESCROWS.get(escrow_id)
    if not e:
        await update.message.reply_text("Unknown escrow ID.")
        return

    e["proof"] = proof_text
    e["status"] = "AWAITING_APPROVAL"

    # Send inline keyboard to admins (here: same chat; in real use, send to admin group)
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve release", callback_data=f"approve:{escrow_id}"),
            InlineKeyboardButton("❌ Cancel & refund", callback_data=f"cancel:{escrow_id}"),
        ]
    ])

    await update.message.reply_text(
        f"Proof received for escrow {escrow_id}.\n"
        f"Amount: {e['amount']}\nProof: {proof_text}\n"
        "Waiting for admin decision.",
        reply_markup=keyboard,
    )


async def approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("You are not allowed to approve/cancel this escrow.")
        return

    data = query.data  # e.g. "approve:ABCD1234"
    action, escrow_id = data.split(":", 1)
    e = ESCROWS.get(escrow_id)
    if not e:
        await query.edit_message_text("Escrow not found.")
        return

    # Prevent double decisions
    if e["status"] in ("RELEASED", "CANCELLED"):
        await query.edit_message_text(f"Escrow {escrow_id} already {e['status']}.")
        return

    if action == "approve":
        e["status"] = "RELEASED"
        e["approved_by"] = query.from_user.id
        e["approved_at"] = datetime.utcnow().isoformat()
        text = (
            f"✅ Escrow {escrow_id} RELEASED by admin {query.from_user.id}.\n"
            f"Amount: {e['amount']}\n"
            "Admin should now send funds to seller (if not already handled)."
        )
    else:
        e["status"] = "CANCELLED"
        e["cancelled_by"] = query.from_user.id
        e["cancel_reason"] = "Admin-button"
        text = (
            f"❌ Escrow {escrow_id} CANCELLED by admin {query.from_user.id}.\n"
            "Buyer should be refunded off‑bot."
        )

    await query.edit_message_text(text)


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("new_escrow", new_escrow))
    app.add_handler(CallbackQueryHandler(approval_callback))  # for inline buttons
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_proof))

    app.run_polling()


if __name__ == "__main__":
    main()
