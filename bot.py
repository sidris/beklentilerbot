import logging
import os
import asyncio
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from supabase import create_client

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ["BOT_TOKEN"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
WEBHOOK_URL = os.environ["WEBHOOK_URL"]

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

SOURCE, FTYPE, PERIOD, VALUE = range(4)

# Kurum listesi
INSTITUTIONS = [
    "Goldman Sachs",
    "JP Morgan",
    "Morgan Stanley",
    "Deutsche Bank",
    "HSBC",
    "TCMB",
]


# ---------- yardımcı fonksiyonlar ----------

def normalize_period(text):
    try:
        dt = datetime.strptime(text, "%Y-%m")
        return dt.strftime("%Y-%m-01")
    except:
        return None


def normalize_value(text):
    text = text.replace(",", ".")
    try:
        return float(text)
    except:
        return None


# ---------- komutlar ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Merhaba 👋\n\nYeni tahmin girmek için /new yaz."
    )


# ---------- kurum seç ----------

async def new_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"src_{name}")]
        for name in INSTITUTIONS
    ]

    await update.message.reply_text(
        "Kurum seç:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return SOURCE


async def source_select(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    source = query.data.replace("src_", "")
    context.user_data["source_name"] = source

    keyboard = [
        [
            InlineKeyboardButton("PPK", callback_data="type_ppk"),
            InlineKeyboardButton("TÜFE", callback_data="type_tufe"),
        ]
    ]

    await query.edit_message_text(
        f"Kurum: {source}\n\nTahmin türünü seç:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return FTYPE


# ---------- tür seç ----------

async def type_select(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    if query.data == "type_ppk":
        context.user_data["forecast_type"] = "ppk"
    else:
        context.user_data["forecast_type"] = "tufe"

    await query.edit_message_text(
        "Hedef dönem gir (YYYY-MM)\n\nÖrnek: 2026-04"
    )

    return PERIOD


# ---------- dönem ----------

async def period_step(update: Update, context: ContextTypes.DEFAULT_TYPE):

    period = normalize_period(update.message.text)

    if not period:
        await update.message.reply_text("Geçersiz tarih. Örnek: 2026-04")
        return PERIOD

    context.user_data["target_period"] = period

    await update.message.reply_text("Tahmin değeri gir:")

    return VALUE


# ---------- değer ----------

async def value_step(update: Update, context: ContextTypes.DEFAULT_TYPE):

    value = normalize_value(update.message.text)

    if value is None:
        await update.message.reply_text("Geçersiz sayı.")
        return VALUE

    payload = {
        "source_name": context.user_data["source_name"],
        "source_type": "institution",
        "forecast_type": context.user_data["forecast_type"],
        "target_period": context.user_data["target_period"],
        "value": value,
        "telegram_user": update.effective_user.username
        or str(update.effective_user.id),
        "telegram_chat_id": str(update.effective_chat.id),
    }

    supabase.table("forecast_entries").insert(payload).execute()

    await update.message.reply_text(
        "✅ Tahmin kaydedildi\n\n"
        f"Kurum: {payload['source_name']}\n"
        f"Tür: {payload['forecast_type']}\n"
        f"Dönem: {payload['target_period']}\n"
        f"Değer: {payload['value']}"
    )

    context.user_data.clear()

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("İşlem iptal edildi.")
    return ConversationHandler.END


# ---------- bot setup ----------

def build_app():

    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("new", new_entry)],
        states={
            SOURCE: [CallbackQueryHandler(source_select)],
            FTYPE: [CallbackQueryHandler(type_select)],
            PERIOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, period_step)],
            VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, value_step)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)

    return app


app = build_app()


# ---------- webhook ----------

async def main():

    port = int(os.environ.get("PORT", "8000"))

    await app.initialize()
    await app.start()

    await app.bot.set_webhook(f"{WEBHOOK_URL}/telegram")

    await app.updater.start_webhook(
        listen="0.0.0.0",
        port=port,
        url_path="telegram",
        webhook_url=f"{WEBHOOK_URL}/telegram",
    )

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
