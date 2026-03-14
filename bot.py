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

ENTRY_TYPE, SURVEY, NAME, FTYPE, PERIOD, VALUE = range(6)

SURVEYS = [
    "Bloomberg HT",
    "Reuters",
    "Matriks",
    "AA Finans",
    "ForInvest",
    "CNBC-E",
]


def normalize_period(text: str) -> str | None:
    try:
        dt = datetime.strptime(text.strip(), "%Y-%m")
        return dt.strftime("%Y-%m-01")
    except ValueError:
        return None


def normalize_value(text: str) -> float | None:
    try:
        return float(text.strip().replace(",", "."))
    except ValueError:
        return None


def normalize_forecast_type(text: str) -> str | None:
    t = text.strip().lower()
    if t in ["ppk", "faiz", "policy"]:
        return "ppk"
    if t in ["tufe", "tüfe", "cpi", "enflasyon"]:
        return "tufe"
    return None


def title_case_name(name: str) -> str:
    return " ".join(word.capitalize() for word in name.strip().split())


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Merhaba.\n\nYeni tahmin girmek için /new yaz."
    )


async def new_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[
        InlineKeyboardButton("Anket", callback_data="entry_survey"),
        InlineKeyboardButton("Kişi", callback_data="entry_person"),
    ]]

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

    await query.edit_message_text("Kişi adı gir:")
    return NAME


async def survey_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    source_name = query.data.replace("survey_", "")
    context.user_data["source_name"] = source_name

    keyboard = [[
        InlineKeyboardButton("PPK", callback_data="ftype_ppk"),
        InlineKeyboardButton("TÜFE", callback_data="ftype_tufe"),
    ]]

    await query.edit_message_text(
        f"Kaynak: {source_name}\n\nTahmin türünü seç:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return FTYPE


async def name_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    source_name = title_case_name(update.message.text)
    context.user_data["source_name"] = source_name

    keyboard = [[
        InlineKeyboardButton("PPK", callback_data="ftype_ppk"),
        InlineKeyboardButton("TÜFE", callback_data="ftype_tufe"),
    ]]

    await update.message.reply_text(
        f"Kişi: {source_name}\n\nTahmin türünü seç:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return FTYPE


async def type_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    forecast_type = query.data.replace("ftype_", "")
    context.user_data["forecast_type"] = forecast_type

    await query.edit_message_text("Hedef dönem gir (YYYY-MM)\nÖrnek: 2026-04")
    return PERIOD


async def period_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    period = normalize_period(update.message.text)
    if not period:
        await update.message.reply_text("Geçersiz dönem. Örnek: 2026-04")
        return PERIOD

    context.user_data["target_period"] = period
    await update.message.reply_text("Tahmin değeri gir:")
    return VALUE


async def value_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    value = normalize_value(update.message.text)
    if value is None:
        await update.message.reply_text("Geçersiz sayı. Örnek: 42.5")
        return VALUE

    payload = {
        "entry_type": context.user_data["entry_type"],
        "source_name": context.user_data["source_name"],
        "forecast_type": context.user_data["forecast_type"],
        "target_period": context.user_data["target_period"],
        "value": value,
        "telegram_user": update.effective_user.username or str(update.effective_user.id),
        "telegram_chat_id": str(update.effective_chat.id),
        "updated_at": datetime.utcnow().isoformat(),
    }

    supabase.table("forecast_entries").upsert(
        payload,
        on_conflict="entry_type,source_name,forecast_type,target_period"
    ).execute()

    await update.message.reply_text(
        "Tahmin kaydedildi ✅\n\n"
        f"Tür: {payload['entry_type']}\n"
        f"Kaynak: {payload['source_name']}\n"
        f"Tahmin tipi: {payload['forecast_type']}\n"
        f"Dönem: {payload['target_period']}\n"
        f"Değer: {payload['value']}"
    )

    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("İşlem iptal edildi.")
    return ConversationHandler.END


def build_app():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("new", new_entry)],
        states={
            ENTRY_TYPE: [CallbackQueryHandler(entry_type_select, pattern="^entry_")],
            SURVEY: [CallbackQueryHandler(survey_select, pattern="^survey_")],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_step)],
            FTYPE: [CallbackQueryHandler(type_select, pattern="^ftype_")],
            PERIOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, period_step)],
            VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, value_step)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
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
