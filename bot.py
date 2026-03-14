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

ENTRY_TYPE, SOURCE, METRIC, FTYPE, PERIOD, VALUE = range(6)

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
    try:
        return float(text.replace(",", "."))
    except:
        return None


def normalize_type(text):
    t = text.lower()

    if t in ["ppk", "faiz"]:
        return "ppk"

    if t in ["tufe", "tüfe", "enflasyon"]:
        return "tufe"

    return None


def title_name(name):
    return " ".join([w.capitalize() for w in name.split()])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Yeni tahmin girmek için /new yaz."
    )


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

        if context.user_data["entry_type"] == "survey":
        
            keyboard = [[
                InlineKeyboardButton("Median", callback_data="median"),
                InlineKeyboardButton("Min", callback_data="min"),
                InlineKeyboardButton("Max", callback_data="max"),
            ]]
        
            await update.callback_query.edit_message_text(
                "Anket metriği seç:",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        
            return METRIC


        if update.callback_query:
            await update.callback_query.edit_message_text(
                "Anket metriği seç:",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            await update.message.reply_text(
                "Anket metriği seç:",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

        return METRIC

    else:

        await update.message.reply_text("Tahmin türü gir (ppk / tufe)")

        return FTYPE


async def metric(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    metric = query.data
    context.user_data["survey_metric"] = metric

    await query.edit_message_text("Tahmin türü gir (ppk / tufe)")

    return FTYPE


async def forecast_type(update: Update, context: ContextTypes.DEFAULT_TYPE):

    ftype = normalize_type(update.message.text)

    if not ftype:
        await update.message.reply_text("ppk veya tufe yaz.")
        return FTYPE

    context.user_data["forecast_type"] = ftype

    await update.message.reply_text("Hedef dönem (YYYY-MM)")

    return PERIOD


async def period(update: Update, context: ContextTypes.DEFAULT_TYPE):

    p = normalize_period(update.message.text)

    if not p:
        await update.message.reply_text("Örnek: 2026-04")
        return PERIOD

    context.user_data["target_period"] = p

    await update.message.reply_text("Tahmin değeri gir")

    return VALUE


async def value(update: Update, context: ContextTypes.DEFAULT_TYPE):

    val = normalize_value(update.message.text)

    if val is None:
        await update.message.reply_text("Geçersiz sayı")
        return VALUE

    payload = {
        "entry_type": context.user_data["entry_type"],
        "source_name": context.user_data["source_name"],
        "forecast_type": context.user_data["forecast_type"],
        "target_period": context.user_data["target_period"],
        "value": val,
        "survey_metric": context.user_data.get("survey_metric"),
        "telegram_user": update.effective_user.username,
        "telegram_chat_id": str(update.effective_chat.id),
    }

    try:

        supabase.table("forecast_entries").upsert(
            payload,
            on_conflict="entry_type,source_name,forecast_type,target_period"
        ).execute()

        await update.message.reply_text("Tahmin kaydedildi ✅")

    except Exception as e:

        await update.message.reply_text(f"Hata: {e}")

    context.user_data.clear()

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
            METRIC: [CallbackQueryHandler(metric)],
            FTYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, forecast_type)],
            PERIOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, period)],
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
