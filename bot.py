import logging
import os
from datetime import datetime

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from supabase import create_client, Client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
WEBHOOK_URL = os.environ["https://beklentilerbot.onrender.com"]  # örn: https://your-bot.onrender.com

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

SOURCE, FTYPE, PERIOD, VALUE = range(4)

def normalize_forecast_type(text: str) -> str | None:
    t = text.strip().lower()
    if t in ["ppk", "faiz", "policy"]:
        return "ppk"
    if t in ["tufe", "tüfe", "cpi", "enflasyon"]:
        return "tufe"
    return None

def normalize_period(text: str) -> str | None:
    text = text.strip()
    try:
        dt = datetime.strptime(text, "%Y-%m")
        return dt.strftime("%Y-%m-01")
    except ValueError:
        return None

def normalize_value(text: str) -> float | None:
    text = text.strip().replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Merhaba. Yeni kayıt için /new yaz.\n"
        "Örnek akış: kaynak adı → tür (ppk/tufe) → dönem (YYYY-MM) → değer"
    )

async def new_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Kaynak adı gir. Örnek: Goldman Sachs")
    return SOURCE

async def source_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["source_name"] = update.message.text.strip()
    await update.message.reply_text("Tahmin türü gir: ppk veya tufe")
    return FTYPE

async def type_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ftype = normalize_forecast_type(update.message.text)
    if not ftype:
        await update.message.reply_text("Geçersiz tür. Lütfen ppk veya tufe yaz.")
        return FTYPE

    context.user_data["forecast_type"] = ftype
    await update.message.reply_text("Hedef dönem gir: YYYY-MM  (ör. 2026-04)")
    return PERIOD

async def period_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    period = normalize_period(update.message.text)
    if not period:
        await update.message.reply_text("Geçersiz dönem. Örnek: 2026-04")
        return PERIOD

    context.user_data["target_period"] = period
    await update.message.reply_text("Tahmin değeri gir. Örnek: 42.50")
    return VALUE

async def value_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    val = normalize_value(update.message.text)
    if val is None:
        await update.message.reply_text("Geçersiz sayı. Örnek: 42.50")
        return VALUE

    payload = {
        "source_name": context.user_data["source_name"],
        "source_type": "institution",
        "forecast_type": context.user_data["forecast_type"],
        "target_period": context.user_data["target_period"],
        "value": val,
        "telegram_user": update.effective_user.username or str(update.effective_user.id),
        "telegram_chat_id": str(update.effective_chat.id),
    }

    supabase.table("forecast_entries").insert(payload).execute()

    await update.message.reply_text(
        "Kayıt alındı ✅\n"
        f"Kaynak: {payload['source_name']}\n"
        f"Tür: {payload['forecast_type']}\n"
        f"Dönem: {payload['target_period']}\n"
        f"Değer: {payload['value']}"
    )
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("İşlem iptal edildi.")
    return ConversationHandler.END

async def post_init(application: Application) -> None:
    await application.bot.set_webhook(url=f"{WEBHOOK_URL}/telegram")

def build_app() -> Application:
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("new", new_entry)],
        states={
            SOURCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, source_step)],
            FTYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, type_step)],
            PERIOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, period_step)],
            VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, value_step)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv)

    return application

app = build_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        webhook_url=f"{WEBHOOK_URL}/telegram",
        url_path="telegram",
        drop_pending_updates=True,
    )
