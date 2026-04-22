# Bot Güncelleme Notu

Mevcut `bot.py` dosyan çalışır durumda ama sadece `ppk` ve `tufe` forecast_type'ını destekliyor. Yeni şemada `tufe_aylik`, `tufe_yillik`, `yilsonu_enf`, `yilsonu_faiz` gibi daha fazla tür var.

## Opsiyon 1: Hiç dokunma (kolay yol)

Bot'un mevcut haliyle devam et, sadece dashboard üzerinden yeni türleri gör. Bot `ppk` ve `tufe` verisi toplar, dashboard bunlarla çalışır.

Ama bu durumda `forecast_type='tufe'` kayıtlar şemada gereksiz jenerik. Dashboard'un liderlik tablosu bunun TÜFE aylık mı yıllık mı olduğunu bilemez. İki seçenek var:

### A. Bot'ta `tufe` → `tufe_aylik` olarak etiketle

`bot.py`'nin `forecast_type` fonksiyonunda:

```python
async def forecast_type(update, context):
    query = update.callback_query
    await query.answer()
    # Eski:    context.user_data["forecast_type"] = query.data
    # Yeni:
    mapping = {"ppk": "ppk", "tufe": "tufe_aylik"}
    context.user_data["forecast_type"] = mapping.get(query.data, query.data)
    ...
```

### B. Bot'a daha çok tür butonu ekle (önerilen)

`bot.py`'de `new_entry` → `entry_type` akışından sonra, `source` fonksiyonunda keyboard'u genişlet:

```python
async def source(update, context):
    # ... mevcut kod ...

    keyboard = [
        [InlineKeyboardButton("PPK Faizi", callback_data="ppk")],
        [InlineKeyboardButton("Aylık TÜFE", callback_data="tufe_aylik"),
         InlineKeyboardButton("Yıllık TÜFE", callback_data="tufe_yillik")],
        [InlineKeyboardButton("Yıl Sonu Enf", callback_data="yilsonu_enf"),
         InlineKeyboardButton("Yıl Sonu Faiz", callback_data="yilsonu_faiz")],
    ]

    await safe_reply(msg, "Tahmin türü seç:", InlineKeyboardMarkup(keyboard))
    return FTYPE
```

## Opsiyon 2: Dinamik tür listesi (en esnek)

Bot Supabase'den `forecast_types` tablosunu okuyup butonları otomatik üretsin:

```python
def get_forecast_type_buttons():
    """forecast_types tablosundan buton listesi üret."""
    res = supabase.table("forecast_types").select("code, label_tr").order("sort_order").execute()
    buttons = []
    row = []
    for t in (res.data or []):
        row.append(InlineKeyboardButton(t["label_tr"], callback_data=t["code"]))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return buttons


async def source(update, context):
    # ... mevcut kod ...
    keyboard = get_forecast_type_buttons()
    await safe_reply(msg, "Tahmin türü seç:", InlineKeyboardMarkup(keyboard))
    return FTYPE
```

Bu şekilde dashboard'dan yeni tür eklediğinde bot otomatik tanır, deploy etmen gerekmez.

## Kolon ismi değişikliği

Mevcut `bot.py`'de anket için `min` ve `max` field'ları var:

```python
payload = {
    ...
    "min": context.user_data.get("min"),
    "max": context.user_data.get("max"),
}
```

Yeni schema'da `min` → `min_val`, `max` → `max_val` oldu (`min` ve `max` Python built-in ismiyle çakışmasın diye). Bot'taki bu iki satırı değiştir:

```python
payload = {
    ...
    "min_val": context.user_data.get("min"),
    "max_val": context.user_data.get("max"),
}
```

## entry_date kolonu (opsiyonel ama önerilen)

Şema'da revizyon mantığı için `entry_date` kolonu var. Default değeri bugün, yani bot hiçbir şey yazmasa da çalışır. Ama gün içinde aynı kaynak aynı tahmin türünü yeniden girerse **duplicate key** hatası alır.

Bot'un insert'inde `entry_date` yazarsan ve aynı gün güncelleme olursa, bot `upsert` mantığı kullanmalı:

```python
from datetime import date

# insert yerine upsert
payload["entry_date"] = date.today().isoformat()

supabase.table("forecast_entries").upsert(
    payload,
    on_conflict="source_name,forecast_type,target_period,entry_date"
).execute()
```

Bu sayede aynı gün içinde aynı kombinasyon tekrar girilirse güncellenir, farklı gün olunca yeni satır olur.

## Özet

**Minimum yapman gereken:**
1. Bot'ta `"min"` → `"min_val"` ve `"max"` → `"max_val"` değişikliği (2 satır).
2. Bot'ta `forecast_type="tufe"` yerine `"tufe_aylik"` kullan (1 satır) — ya da B şıkkındaki gibi genişlet.
3. (Önerilen) Bot `insert` yerine `upsert(on_conflict=...)` kullansın ki gün içinde duplicate hatası çıkmasın.

Geri kalan her şey mevcut kodla uyumlu çalışır.
