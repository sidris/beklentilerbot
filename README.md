# Forecast Tracker

Telegram bot + Streamlit dashboard — piyasa beklenti tahminlerini topla, analiz et, gerçekleşene karşı kıyasla.

## Mimari

```
Telegram Bot (bot.py)  ──┐
                         ├──► Supabase (forecast_entries tablosu)
Streamlit Dashboard ─────┘
  (streamlit_app.py)
```

Bot veri toplama, Streamlit analiz ve gösterim yapar. Her ikisi aynı Supabase projesini paylaşır.

## Klasör Yapısı

```
repo/
├── streamlit_app.py          ← Ana Streamlit dosyası (giriş + özet)
├── bot.py                    ← Telegram bot
├── utils.py                  ← Tüm yardımcılar + tema (Streamlit için)
├── schema.sql                ← Supabase şeması (SQL Editor'da çalıştır)
├── requirements.txt
├── README.md
└── pages/                    ← Streamlit alt sayfalar
    ├── Dashboard.py
    ├── Veri_Havuzu.py
    ├── Piyasa_Verileri.py
    └── Admin.py
```

## 1. Supabase Kurulumu

Supabase panelinde **SQL Editor**'ü aç, `schema.sql` içindeki tüm SQL'i yapıştır ve çalıştır.

Tablolar oluşur:
- `forecast_entries` — ana tahmin tablosu
- `forecast_types` — tahmin türleri (ppk, tufe_aylik, vs.) + başlangıç kayıtları
- `surveys` — anket listesi (Reuters, Bloomberg, vs.) + başlangıç kayıtları

## 2. Secrets

### Streamlit Cloud için

App Settings → Secrets kısmına:

```toml
SUPABASE_URL = "https://<proje-id>.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "eyJ..."
APP_PASSWORD = "kullanıcı-şifresi"
ADMIN_PASSWORD = "admin-şifresi"
EVDS_KEY = "tcmb-evds-anahtarı"
```

**Not:** Eski dosyalarınızda `SUPABASE_KEY` ismi varsa o da kabul ediliyor (utils.py iki ismi de tanıyor).

### Telegram Bot için (env)

Bot nerede deploy ediliyorsa (Railway, Render, vs.):

```bash
BOT_TOKEN=...
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
WEBHOOK_URL=https://your-bot-url.railway.app
```

## 3. Lokal Çalıştırma

```bash
pip install -r requirements.txt
# .streamlit/secrets.toml yaz (yukarıdaki örneğe göre)
streamlit run streamlit_app.py
```

## 4. Yeni Tahmin Türü Ekleme

Dashboard'un sol menüsünden **Admin → Yeni Tahmin Türü Ekle** bölümünden eklenir. Örneğin dolar kuru eklemek için:

- Kod: `dolar_kuru`
- Etiket: `USD/TRY`
- Birim: `TL`
- Gerçekleşen kolonu: `(yok)` (EVDS'den bunun için ayrı seri çekilmiyor)

Eklendikten sonra dashboard'daki tahmin türü dropdown'ında otomatik görünür. Bot'a da ekleme yapman lazım — `bot.py`'de `FTYPE` state'inde yeni buton ekle.

## 5. Demo Akışı (Yönetim Sunumu İçin)

1. Giriş yap → sol menüden **Admin**.
2. Admin şifresiyle ikinci girişi yap.
3. **🚀 Demo Verisi Üret** → ~15 saniyede ~3000 tahmin oluşur.
4. **Dashboard**'a geç:
   - Tahmin türünü değiştir → liderlik, konsensüs, ısı haritası güncellensin
   - As-of ayını değiştir → "o ayda piyasa ne bekliyordu?" göster
   - Revizyon sekmesinde bir kaynağın zaman içindeki değişimini göster
5. Sunum bitince **Admin → Sıfırlama**, "SIL" yaz, sıfırla.
6. Artık bot'tan gerçek veri girişine başla.

## 6. Veri Modeli

- Her satır = **bir kaynağın bir dönem için bir tür tahmini**.
- `entry_type`: `survey` | `institution` | `person`.
- `forecast_type`: dinamik kod (`ppk`, `tufe_aylik`, vs.) — `forecast_types` tablosundan okunur.
- **Revizyon mantığı:** aynı gün içinde aynı `(kaynak, tür, hedef)` yeniden girilirse UPDATE. Farklı günse yeni satır (tam geçmiş korunur).
- `value` → kişi/kurum tek değer verir.
- `median` + `min_val` + `max_val` + `n_participants` → anket için.

## 7. Piyasa Verisi

- **TÜFE hibrit:** `TP.FE.OKTG01` (2003=100, eski) + `TP.TUKFIY2025.GENEL` (2025=100, yeni). 2026 Ocak'tan itibaren otomatik yeni seriye geçer.
- **Politika faizi:** BIS `WS_CBPOL/D.TR` (EVDS yerine daha temiz).

## 8. Sık Karşılaşılan Sorunlar

- **`httpx.ConnectError`:** SUPABASE_URL yanlış veya Supabase projesi paused. Dashboard → Projeye git → Restore et.
- **`EVDS_KEY tanımlı değil`:** Secrets'a EVDS anahtarını ekle.
- **Demo yavaş:** Batch insert ~10-15 sn. Daha yavaşsa network latency.
- **Boş Dashboard:** `schema.sql` çalıştırılmamış olabilir. Özellikle `forecast_types` tablosunun dolu olduğunu kontrol et.
