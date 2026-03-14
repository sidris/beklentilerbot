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

ENTRY_TYPE, SURVEY, NAME, FTYPE, PERIOD, VALUE = range(6)

SURVEYS = [
    "Bloomberg HT",
    "Reuters",
    "Matriks",
    "AA Finans",
    "ForInvest",
    "CNBC-E",
]


# ---------- start ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "Yeni tahmin girmek için /new yaz."
    )


# ---------- entry type ----------

async def new_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [
        [
            InlineKeyboardButton("Anket", callback_data="entry_survey"),
            InlineKeyboardButton("Kişi", callback_data="entry_person"),
        ]
    ]

    await update.message.reply_text(
        "Hangi türde giriş yapacaksınız?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return ENTRY_TYPE


async def entry_type_select(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    entry_type = query.data.replace("entry_", "")
    context.user_data["entry_type"] = entry_type

    if entry_type == "survey":

        keyboard = [
            [InlineKeyboardButton(name, callback_data=f"survey_{name}")]
            for name in SURVEYS
        ]

        await query.edit_message_text(
            "Hangi anket?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

        return SURVEY

    else:

        await query.edit_message_text("Kişi adı gir:")

        return NAME


# ---------- survey select ----------

async def survey_select(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    name = query.data.replace("survey_", "")

    context.user_data["source_name"] = name

    await query.edit_message_text("Tahmin türü gir: ppk / tufe")

    return FTYPE


# ---------- person name ----------

async def name_step(update: Update, context: ContextTypes.DEFAULT_TYPE):

    name = update.message.text.title()

    context.user_data["source_name"] = name

    await update.message.reply_text("Tahmin türü gir: ppk / tufe")

    return FTYPE


# ---------- type ----------

async def type_step(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data["forecast_type"] = update.message.text.lower()

    await update.message.reply_text("Hedef dönem gir (YYYY-MM)")

    return PERIOD


# ---------- period ----------

async def period_step(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:
        dt = datetime.strptime(update.message.text, "%Y-%m")
        period = dt.strftime("%Y-%m-01")
    except:
        await update.message.reply_text("Örnek: 2026-04")
        return PERIOD

    context.user_data["target_period"] = period

    await update.message.reply_text("Tahmin değeri gir")

    return VALUE


# ---------- value ----------

async def value_step(update: Update, context: ContextTypes.DEFAULT_TYPE):

    value = float(update.message.text.replace(",", "."))

    payload = {
        "entry_type": context.user_data["entry_type"],
        "source_name": context.user_data["source_name"],
        "forecast_type": context.user_data["forecast_type"],
        "target_period": context.user_data["target_period"],
        "value": value,
        "telegram_user": update.effective_user.username,
        "telegram_chat_id": str(update.effective_chat.id),
    }

    supabase.table("forecast_entries").upsert(payload).execute()

    await update.message.reply_text("Tahmin kaydedildi ✅")

    context.user_data.clear()

    return ConversationHandler.END


# ---------- setup ----------

def build_app():

    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("new", new_entry)],
        states={
            ENTRY_TYPE: [CallbackQueryHandler(entry_type_select)],
            SURVEY: [CallbackQueryHandler(survey_select)],
            NAME: [MessageHandler(filters.TEXT, name_step)],
            FTYPE: [MessageHandler(filters.TEXT, type_step)],
            PERIOD: [MessageHandler(filters.TEXT, period_step)],
            VALUE: [MessageHandler(filters.TEXT, value_step)],
        },
        fallbacks=[],
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
