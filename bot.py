"""
bot.py — Forecast Tracker Telegram bot.

Değişiklikler (önceki versiyondan):
- Kolon isimleri: min → min_val, max → max_val
- forecast_type dinamik: forecast_types tablosundan okunur
- surveys listesi dinamik: surveys tablosundan okunur
- insert yerine upsert: aynı gün aynı (kaynak, tür, hedef) güncellenir
- entry_date kolonu explicit olarak yazılır
"""

import os
import asyncio
from datetime import datetime, date, timezone

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
from telegram.error import RetryAfter
from supabase import create_client


BOT_TOKEN = os.environ["BOT_TOKEN"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
WEBHOOK_URL = os.environ["WEBHOOK_URL"]

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# Conversation states
ENTRY_TYPE, SOURCE, FTYPE, PERIOD, MEDIAN, MINVAL, MAXVAL, VALUE, NPART = range(9)


# =============================================================
# DİNAMİK LİSTELER (Supabase'den okur)
# =============================================================
def load_surveys() -> list[str]:
    """surveys tablosundan aktif anketleri sırayla getir."""
    try:
        res = (
            supabase.table("surveys")
            .select("name")
            .eq("active", True)
            .order("sort_order")
            .execute()
        )
        return [r["name"] for r in (res.data or [])]
    except Exception as e:
        print(f"load_surveys error: {e}")
        # Fallback: statik liste
        return ["Reuters", "Bloomberg HT", "AA Finans", "Matriks", "ForInvest"]


def load_forecast_types() -> list[tuple[str, str]]:
    """
    forecast_types tablosundan (code, label_tr) listesi getir.
    Dashboard'dan yeni tür eklenirse bot otomatik tanır.
    """
    try:
        res = (
            supabase.table("forecast_types")
            .select("code, label_tr")
            .order("sort_order")
            .execute()
        )
        data = res.data or []
        return [(r["code"], r["label_tr"]) for r in data]
    except Exception as e:
        print(f"load_forecast_types error: {e}")
        # Fallback: temel türler
        return [
            ("ppk", "PPK Politika Faizi"),
            ("tufe_aylik", "Aylık TÜFE"),
            ("tufe_yillik", "Yıllık TÜFE"),
            ("yilsonu_enf", "Yıl Sonu Enflasyon"),
            ("yilsonu_faiz", "Yıl Sonu Politika Faizi"),
        ]


# =============================================================
# YARDIMCI
# =============================================================
async def safe_reply(message, text, reply_markup=None):
    try:
        await message.reply_text(text, reply_markup=reply_markup)
    except RetryAfter as e:
        await asyncio.sleep(e.retry_after)
        await message.reply_text(text, reply_markup=reply_markup)


def normalize_period(text: str):
    """'2026-04' → '2026-04-01'"""
    try:
        dt = datetime.strptime(text.strip(), "%Y-%m")
        return dt.strftime("%Y-%m-01")
    except Exception:
        return None


def normalize_value(text: str):
    t = text.strip().lower()
    if t in ["yok", "-", "bos", "skip", "yok ", ""]:
        return None
    try:
        return float(text.replace(",", "."))
    except Exception:
        return None


def normalize_int(text: str):
    t = text.strip().lower()
    if t in ["yok", "-", "bos", "skip", ""]:
        return None
    try:
        return int(float(text.replace(",", ".")))
    except Exception:
        return None


def title_name(name: str) -> str:
    return " ".join([w.capitalize() for w in name.split()])


def upsert_entry(payload: dict):
    """
    Aynı gün aynı (kaynak, tür, hedef) varsa günceller, yoksa yeni kayıt.
    entry_date field'ını ekler, on_conflict ile upsert yapar.
    """
    payload["entry_date"] = date.today().isoformat()
    now_iso = datetime.now(timezone.utc).isoformat()
    payload["updated_at"] = now_iso

    return (
        supabase.table("forecast_entries")
        .upsert(
            payload,
            on_conflict="source_name,forecast_type,target_period,entry_date",
        )
        .execute()
    )


# =============================================================
# HANDLERS
# =============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_reply(
        update.message,
        "Forecast Tracker 📊\n\nYeni tahmin girmek için /new yaz."
    )


async def new_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[
        InlineKeyboardButton("📋 Anket", callback_data="survey"),
        InlineKeyboardButton("🧑 Kişi", callback_data="person"),
        InlineKeyboardButton("🏢 Kurum", callback_data="institution"),
    ]]
    await safe_reply(
        update.message,
        "Hangi türde giriş?",
        InlineKeyboardMarkup(keyboard),
    )
    return ENTRY_TYPE


async def entry_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["entry_type"] = query.data

    if query.data == "survey":
        surveys = load_surveys()
        keyboard = [
            [InlineKeyboardButton(s, callback_data=f"survey_{s}")]
            for s in surveys
        ]
        await query.edit_message_text(
            "Hangi anket?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return SOURCE
    else:
        label = "Kişinin adını" if query.data == "person" else "Kurum adını"
        await query.edit_message_text(f"{label} yaz:")
        return SOURCE


async def source(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        context.user_data["source_name"] = query.data.replace("survey_", "")
        msg = query.message
    else:
        context.user_data["source_name"] = title_name(update.message.text)
        msg = update.message

    # Dinamik forecast_type butonları
    ftypes = load_forecast_types()
    keyboard = []
    row = []
    for code, label in ftypes:
        row.append(InlineKeyboardButton(label, callback_data=code))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    await safe_reply(msg, "Tahmin türü seç:", InlineKeyboardMarkup(keyboard))
    return FTYPE


async def forecast_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["forecast_type"] = query.data
    await query.edit_message_text("Hedef dönem (YYYY-MM formatında):")
    return PERIOD


async def period(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p = normalize_period(update.message.text)
    if not p:
        await safe_reply(update.message, "❌ Format hatalı. Örnek: 2026-04")
        return PERIOD

    context.user_data["target_period"] = p

    if context.user_data["entry_type"] == "survey":
        await safe_reply(update.message, "Medyan değeri (yoksa 'yok' yaz):")
        return MEDIAN
    else:
        await safe_reply(update.message, "Tahmin değeri:")
        return VALUE


async def median(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["median"] = normalize_value(update.message.text)
    await safe_reply(update.message, "Min değeri (yoksa 'yok'):")
    return MINVAL


async def minval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["min_val"] = normalize_value(update.message.text)
    await safe_reply(update.message, "Max değeri (yoksa 'yok'):")
    return MAXVAL


async def maxval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["max_val"] = normalize_value(update.message.text)
    await safe_reply(update.message, "Katılımcı sayısı N (yoksa 'yok'):")
    return NPART


async def npart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["n_participants"] = normalize_int(update.message.text)

    payload = {
        "entry_type": "survey",
        "source_name": context.user_data["source_name"],
        "forecast_type": context.user_data["forecast_type"],
        "target_period": context.user_data["target_period"],
        "median": context.user_data.get("median"),
        "min_val": context.user_data.get("min_val"),
        "max_val": context.user_data.get("max_val"),
        "n_participants": context.user_data.get("n_participants"),
    }
    # None'ları at (column default'ları için)
    payload = {k: v for k, v in payload.items() if v is not None}
    # Ama entry_type ve source_name zorunlu
    payload["entry_type"] = "survey"
    payload["source_name"] = context.user_data["source_name"]
    payload["forecast_type"] = context.user_data["forecast_type"]
    payload["target_period"] = context.user_data["target_period"]

    try:
        result = upsert_entry(payload)
        print("SUPABASE RESULT:", result)

        await safe_reply(
            update.message,
            f"""Anket kaydedildi ✅

Kaynak: {payload['source_name']}
Tahmin: {payload['forecast_type']}
Dönem: {payload['target_period']}

Medyan: {payload.get('median', '—')}
Min: {payload.get('min_val', '—')}
Max: {payload.get('max_val', '—')}
N: {payload.get('n_participants', '—')}

Yeni tahmin için /new
"""
        )
    except Exception as e:
        print("SUPABASE ERROR:", e)
        await safe_reply(update.message, f"❌ Supabase hata: {e}")

    context.user_data.clear()
    return ConversationHandler.END


async def value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = normalize_value(update.message.text)

    if val is None:
        await safe_reply(update.message, "❌ Geçerli bir sayı gir.")
        return VALUE

    payload = {
        "entry_type": context.user_data["entry_type"],
        "source_name": context.user_data["source_name"],
        "forecast_type": context.user_data["forecast_type"],
        "target_period": context.user_data["target_period"],
        "value": val,
    }

    try:
        result = upsert_entry(payload)
        print("SUPABASE RESULT:", result)

        await safe_reply(
            update.message,
            f"""Tahmin kaydedildi ✅

Tür: {payload['entry_type']}
Kaynak: {payload['source_name']}
Tahmin: {payload['forecast_type']}
Dönem: {payload['target_period']}
Değer: {payload['value']}

Yeni tahmin için /new
"""
        )
    except Exception as e:
        print("SUPABASE ERROR:", e)
        await safe_reply(update.message, f"❌ Supabase hata: {e}")

    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await safe_reply(update.message, "İptal edildi. Yeni tahmin için /new")
    return ConversationHandler.END


# =============================================================
# APP
# =============================================================
def build_app():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("new", new_entry)],
        states={
            ENTRY_TYPE: [CallbackQueryHandler(entry_type)],
            SOURCE: [
                CallbackQueryHandler(source, pattern="^survey_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, source),
            ],
            FTYPE: [CallbackQueryHandler(forecast_type)],
            PERIOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, period)],
            MEDIAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, median)],
            MINVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, minval)],
            MAXVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, maxval)],
            NPART: [MessageHandler(filters.TEXT & ~filters.COMMAND, npart)],
            VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, value)],
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
    await app.bot.set_webhook(f"{WEBHOOK_URL}/telegram")
    await app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path="telegram",
        webhook_url=f"{WEBHOOK_URL}/telegram",
    )


if __name__ == "__main__":
    asyncio.run(main())
