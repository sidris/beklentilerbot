import os
import asyncio
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from supabase import create_client

BOT_TOKEN = os.environ["BOT_TOKEN"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
WEBHOOK_URL = os.environ["WEBHOOK_URL"]

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

ENTRY_TYPE, SOURCE, FTYPE, PERIOD, MEDIAN, MINVAL, MAXVAL, VALUE = range(8)

SURVEYS = [
    "Bloomberg HT",
    "Reuters",
    "Matriks",
    "AA Finans",
    "ForInvest",
    "CNBC-E",
]


def normalize_period(text):
    try:
        dt = datetime.strptime(text, "%Y-%m")
        return dt.strftime("%Y-%m-01")
    except:
        return None


def normalize_value(text):
    if text.lower() in ["yok", "boş", "skip"]:
        return None
    try:
        return float(text.replace(",", "."))
    except:
        return None


def title_name(name):
    return " ".join([w.capitalize() for w in name.split()])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Yeni tahmin için /new yaz.")


async def new_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [[
        InlineKeyboardButton("Anket", callback_data="survey"),
        InlineKeyboardButton("Kişi", callback_data="person"),
        InlineKeyboardButton("Kurum", callback_data="institution"),
    ]]

    await update.message.reply_text(
        "Hangi türde giriş yapacaksınız?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return ENTRY_TYPE


async def entry_type(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    entry_type = query.data
    context.user_data["entry_type"] = entry_type

    if entry_type == "survey":

        keyboard = [
            [InlineKeyboardButton(x, callback_data=f"survey_{x}")]
            for x in SURVEYS
        ]

        await query.edit_message_text(
            "Hangi anket?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        return SOURCE

    else:

        await query.edit_message_text("İsim gir:")
        return SOURCE


async def source(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.callback_query:

        query = update.callback_query
        await query.answer()

        name = query.data.replace("survey_", "")
        context.user_data["source_name"] = name

    else:

        name = title_name(update.message.text)
        context.user_data["source_name"] = name

    keyboard = [[
        InlineKeyboardButton("PPK", callback_data="ppk"),
        InlineKeyboardButton("TÜFE", callback_data="tufe"),
    ]]

    await update.effective_message.reply_text(
        "Tahmin türünü seç:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return FTYPE


async def forecast_type(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    context.user_data["forecast_type"] = query.data

    await query.edit_message_text("Hedef dönem gir (YYYY-MM)")

    return PERIOD


async def period(update: Update, context: ContextTypes.DEFAULT_TYPE):

    p = normalize_period(update.message.text)

    if not p:
        await update.message.reply_text("Örnek: 2026-04")
        return PERIOD

    context.user_data["target_period"] = p

    if context.user_data["entry_type"] == "survey":

        await update.message.reply_text("Median değeri (yoksa 'yok' yaz)")
        return MEDIAN

    else:

        await update.message.reply_text("Tahmin değeri")
        return VALUE


async def median(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data["median"] = normalize_value(update.message.text)

    await update.message.reply_text("Min değeri (yoksa 'yok' yaz)")
    return MINVAL


async def minval(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data["min"] = normalize_value(update.message.text)

    await update.message.reply_text("Max değeri (yoksa 'yok' yaz)")
    return MAXVAL


async def maxval(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data["max"] = normalize_value(update.message.text)

    payload = {
        "entry_type": "survey",
        "source_name": context.user_data["source_name"],
        "forecast_type": context.user_data["forecast_type"],
        "target_period": context.user_data["target_period"],
        "median": context.user_data.get("median"),
        "min": context.user_data.get("min"),
        "max": context.user_data.get("max"),
    }

    supabase.table("forecast_entries").upsert(
        payload,
        on_conflict="entry_type,source_name,forecast_type,target_period"
    ).execute()

    await update.message.reply_text(
        f"""
Anket kaydedildi ✅

Kaynak: {payload['source_name']}
Tahmin: {payload['forecast_type']}
Dönem: {payload['target_period']}

Median: {payload['median']}
Min: {payload['min']}
Max: {payload['max']}
"""
    )

    return ConversationHandler.END


async def value(update: Update, context: ContextTypes.DEFAULT_TYPE):

    val = normalize_value(update.message.text)

    payload = {
        "entry_type": context.user_data["entry_type"],
        "source_name": context.user_data["source_name"],
        "forecast_type": context.user_data["forecast_type"],
        "target_period": context.user_data["target_period"],
        "value": val,
    }

    supabase.table("forecast_entries").upsert(
        payload,
        on_conflict="entry_type,source_name,forecast_type,target_period"
    ).execute()

    await update.message.reply_text(
        f"""
Tahmin kaydedildi ✅

Tür: {payload['entry_type']}
Kaynak: {payload['source_name']}
Tahmin: {payload['forecast_type']}
Dönem: {payload['target_period']}
Değer: {payload['value']}
"""
    )

    return ConversationHandler.END


def build_app():

    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("new", new_entry)],
        states={
            ENTRY_TYPE: [CallbackQueryHandler(entry_type)],
            SOURCE: [
                CallbackQueryHandler(source, pattern="^survey_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, source)
            ],
            FTYPE: [CallbackQueryHandler(forecast_type)],
            PERIOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, period)],
            MEDIAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, median)],
            MINVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, minval)],
            MAXVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, maxval)],
            VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, value)],
        },
        fallbacks=[]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)

    return app


app = build_app()


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
