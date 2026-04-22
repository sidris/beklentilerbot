"""
utils.py — Forecast Tracker için tüm yardımcılar.

İçindekiler:
- Supabase bağlantı + secrets
- Login helper'ları
- CRUD: forecast_entries, forecast_types, surveys
- Query helper'ları: latest_snapshot, as_of, consensus, leaderboard
- EVDS (TÜFE hibrit) + BIS (PPK) piyasa verisi
- Demo veri üretici + tam sıfırlama
- UI tema + helper bileşenler
"""

from __future__ import annotations

import io
import random
from datetime import date, datetime, timedelta
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import requests
import streamlit as st
from supabase import Client, create_client


# =============================================================
# SABİTLER
# =============================================================
TABLE_ENTRIES = "forecast_entries"
TABLE_TYPES = "forecast_types"
TABLE_SURVEYS = "surveys"

ENTRY_TYPES = ["survey", "person", "institution"]
ENTRY_TYPE_LABELS = {
    "survey": "Anket",
    "person": "Kişi",
    "institution": "Kurum",
}

# TÜFE serileri — önceki projeden aynı hibrit mantık
EVDS_TUFE_OLD = "TP.FE.OKTG01"          # 2003=100, geçmiş
EVDS_TUFE_NEW = "TP.TUKFIY2025.GENEL"   # 2025=100, 2026+
BIS_PPK_URL = "https://stats.bis.org/api/v1/data/WS_CBPOL/D.TR?format=csv&startPeriod={start}&endPeriod={end}"


# =============================================================
# SECRETS & SUPABASE
# =============================================================
def _get_secret(key: str, default=None):
    """
    Secrets okuma — hem düz format (SUPABASE_URL) hem iç içe format
    ([supabase] url=...) destekli. Eski bot dosyaları farklı isimler
    kullanıyor olabilir (SUPABASE_SERVICE_ROLE_KEY vs SUPABASE_KEY).
    """
    if key in st.secrets:
        return st.secrets[key]
    # İç içe: [supabase]
    if "supabase" in st.secrets and key.lower().replace("supabase_", "") in st.secrets["supabase"]:
        return st.secrets["supabase"][key.lower().replace("supabase_", "")]
    return default


def _get_supabase_creds() -> tuple[str, str]:
    url = _get_secret("SUPABASE_URL")
    # Tercih: service role (tam erişim). Yoksa anon'a düş.
    key = (
        _get_secret("SUPABASE_SERVICE_ROLE_KEY")
        or _get_secret("SUPABASE_KEY")
        or _get_secret("SUPABASE_ANON_KEY")
    )
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL ve SUPABASE_SERVICE_ROLE_KEY (veya SUPABASE_KEY) "
            "secrets içinde tanımlı olmalı."
        )
    return url, key


@st.cache_resource
def get_supabase() -> Client:
    url, key = _get_supabase_creds()
    return create_client(url, key)


def get_app_password() -> str:
    pwd = _get_secret("APP_PASSWORD")
    if not pwd:
        raise RuntimeError("APP_PASSWORD secrets içinde tanımlı değil.")
    return pwd


def get_admin_password() -> Optional[str]:
    return _get_secret("ADMIN_PASSWORD")


def get_evds_key() -> Optional[str]:
    return _get_secret("EVDS_KEY")


# =============================================================
# OTURUM / LOGIN
# =============================================================
def check_login() -> bool:
    if "giris_yapildi" not in st.session_state:
        st.session_state["giris_yapildi"] = False
    return bool(st.session_state["giris_yapildi"])


def check_admin() -> bool:
    if "admin_yapildi" not in st.session_state:
        st.session_state["admin_yapildi"] = False
    return bool(st.session_state["admin_yapildi"])


def require_login_page():
    """pages/*.py başında çağır — giriş yoksa sidebar'ı gizler, uyarır, durur."""
    if not check_login():
        st.markdown(
            """
            <style>
              [data-testid="stSidebar"] {display: none;}
              [data-testid="stSidebarCollapsedControl"] {display: none;}
            </style>
            """,
            unsafe_allow_html=True,
        )
        st.warning("🔒 Bu sayfaya erişmek için giriş yapmanız gerekiyor.")
        st.info("Ana sayfaya dönüp şifreyi girin.")
        st.stop()


# =============================================================
# FORECAST_TYPES & SURVEYS
# =============================================================
@st.cache_data(ttl=300)
def get_forecast_types() -> pd.DataFrame:
    """Tüm tahmin türlerini sıralı olarak getirir."""
    sb = get_supabase()
    res = sb.table(TABLE_TYPES).select("*").order("sort_order").execute()
    return pd.DataFrame(res.data or [])


def get_type_label(code: str) -> str:
    """forecast_type kodundan Türkçe etikete çevirir."""
    try:
        df = get_forecast_types()
        if df.empty:
            return code
        row = df[df["code"] == code]
        if not row.empty:
            return row.iloc[0]["label_tr"]
    except Exception:
        pass
    return code


def get_realized_col(code: str) -> Optional[str]:
    """forecast_type için EVDS/BIS karşılık kolonunu döner (varsa)."""
    try:
        df = get_forecast_types()
        if df.empty:
            return None
        row = df[df["code"] == code]
        if not row.empty:
            val = row.iloc[0]["realized_col"]
            return val if pd.notna(val) else None
    except Exception:
        pass
    return None


def add_forecast_type(code: str, label_tr: str, unit: str = "%",
                     realized_col: Optional[str] = None,
                     sort_order: int = 999) -> Tuple[bool, str]:
    sb = get_supabase()
    try:
        sb.table(TABLE_TYPES).insert({
            "code": code,
            "label_tr": label_tr,
            "unit": unit,
            "realized_col": realized_col,
            "sort_order": sort_order,
        }).execute()
        get_forecast_types.clear()
        return True, "Eklendi."
    except Exception as e:
        return False, str(e)


@st.cache_data(ttl=300)
def get_surveys() -> list[str]:
    sb = get_supabase()
    try:
        res = sb.table(TABLE_SURVEYS).select("name").eq("active", True).order("sort_order").execute()
        return [r["name"] for r in (res.data or [])]
    except Exception:
        return []


# =============================================================
# FORECAST ENTRIES — CRUD + QUERIES
# =============================================================
def _clean_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    for c in ("value", "median", "min_val", "max_val"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "n_participants" in df.columns:
        df["n_participants"] = pd.to_numeric(df["n_participants"], errors="coerce")

    for c in ("target_period", "created_at", "updated_at"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")

    return df


@st.cache_data(ttl=120)
def get_all_entries(limit: int = 50000) -> pd.DataFrame:
    sb = get_supabase()
    res = (
        sb.table(TABLE_ENTRIES)
        .select("*")
        .order("updated_at", desc=True)
        .limit(limit)
        .execute()
    )
    return _clean_df(pd.DataFrame(res.data or []))


def upsert_entry(
    entry_type: str,
    source_name: str,
    forecast_type: str,
    target_period,   # str "YYYY-MM" veya date
    value: Optional[float] = None,
    median: Optional[float] = None,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
    n_participants: Optional[int] = None,
    source_link: Optional[str] = None,
    note: Optional[str] = None,
    on_date: Optional[date] = None,   # None → bugün (aynı gün revizyon için)
) -> Tuple[bool, str]:
    """
    Revizyon mantığı: aynı (source, forecast_type, target_period, date)
    varsa UPDATE, yoksa INSERT. Farklı gün yeni satır olur.
    """
    sb = get_supabase()

    # target_period normalize et
    if isinstance(target_period, str):
        tp = pd.to_datetime(target_period + "-01" if len(target_period) == 7 else target_period,
                            errors="coerce")
    else:
        tp = pd.to_datetime(target_period, errors="coerce")
    if pd.isna(tp):
        return False, "target_period okunamadı."
    tp_str = tp.strftime("%Y-%m-01")

    payload = {
        "entry_type": entry_type,
        "source_name": source_name.strip(),
        "forecast_type": forecast_type,
        "target_period": tp_str,
        "value": value,
        "median": median,
        "min_val": min_val,
        "max_val": max_val,
        "n_participants": n_participants,
        "source_link": source_link,
        "note": note,
    }
    # None'ları at (Postgres default'ları için)
    payload = {k: v for k, v in payload.items() if v is not None}

    today_date = (on_date or date.today()).isoformat()
    payload["entry_date"] = today_date

    try:
        # Aynı gün içinde aynı kombinasyon var mı?
        existing = (
            sb.table(TABLE_ENTRIES)
            .select("id")
            .eq("source_name", payload["source_name"])
            .eq("forecast_type", forecast_type)
            .eq("target_period", tp_str)
            .eq("entry_date", today_date)
            .limit(1)
            .execute()
        )
        if existing.data:
            row_id = existing.data[0]["id"]
            sb.table(TABLE_ENTRIES).update(payload).eq("id", row_id).execute()
            msg = f"Aynı gün için güncellendi (id={row_id})"
        else:
            sb.table(TABLE_ENTRIES).insert(payload).execute()
            msg = "Yeni kayıt eklendi."

        get_all_entries.clear()
        return True, msg
    except Exception as e:
        return False, str(e)


def delete_entries_by_ids(ids: list) -> Tuple[bool, str]:
    sb = get_supabase()
    try:
        sb.table(TABLE_ENTRIES).delete().in_("id", ids).execute()
        get_all_entries.clear()
        return True, f"{len(ids)} kayıt silindi."
    except Exception as e:
        return False, str(e)


def update_entry_by_id(row_id: int, updates: dict) -> Tuple[bool, str]:
    sb = get_supabase()
    try:
        sb.table(TABLE_ENTRIES).update(updates).eq("id", row_id).execute()
        get_all_entries.clear()
        return True, "Güncellendi."
    except Exception as e:
        return False, str(e)


def reset_all_data(include_types: bool = False) -> Tuple[bool, str]:
    """
    Tüm tahminleri siler. include_types=True ise forecast_types ve surveys'i
    de siler — dikkat, demo sonrası temiz başlangıç için.
    """
    sb = get_supabase()
    try:
        sb.table(TABLE_ENTRIES).delete().gte("id", 0).execute()
        msg = "Tüm tahminler silindi."
        if include_types:
            sb.table(TABLE_TYPES).delete().neq("code", "").execute()
            sb.table(TABLE_SURVEYS).delete().neq("name", "").execute()
            msg += " (Tür ve anket listeleri de silindi.)"
        get_all_entries.clear()
        get_forecast_types.clear()
        get_surveys.clear()
        return True, msg
    except Exception as e:
        return False, str(e)


# =============================================================
# QUERY HELPERS
# =============================================================
def latest_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    """
    Her (source_name, forecast_type, target_period) için
    en son updated_at olan satırı döner.
    """
    if df is None or df.empty:
        return df
    return (
        df.sort_values("updated_at")
        .drop_duplicates(
            subset=["source_name", "forecast_type", "target_period"],
            keep="last",
        )
    )


def as_of_snapshot(df: pd.DataFrame, as_of: str) -> pd.DataFrame:
    """
    Belirli bir ayın (YYYY-MM) sonuna kadar girilen tahminlerden,
    her (kaynak, tür, hedef) için en sonuncusu.
    """
    if df is None or df.empty:
        return df
    as_of_ts = pd.Timestamp(f"{as_of}-01") + pd.offsets.MonthEnd(0)
    as_of_ts = as_of_ts.tz_localize("UTC")
    filtered = df[df["updated_at"] <= as_of_ts]
    if filtered.empty:
        return filtered
    return (
        filtered.sort_values("updated_at")
        .drop_duplicates(
            subset=["source_name", "forecast_type", "target_period"],
            keep="last",
        )
    )


def consensus_by_period(df: pd.DataFrame, forecast_type: str) -> pd.DataFrame:
    """
    Verilen forecast_type için her hedef döneme göre medyan, Q1, Q3, n kaynak.
    """
    if df is None or df.empty:
        return pd.DataFrame(
            columns=["target_period", "median", "q1", "q3", "n"]
        )

    sub = df[df["forecast_type"] == forecast_type].copy()
    # Anketlerde 'median', diğerlerinde 'value' kullanılır — birleştir
    sub["_val"] = sub["value"].fillna(sub["median"])
    sub = sub.dropna(subset=["_val"])
    if sub.empty:
        return pd.DataFrame(
            columns=["target_period", "median", "q1", "q3", "n"]
        )

    grp = sub.groupby("target_period")["_val"]
    out = pd.DataFrame({
        "median": grp.median(),
        "q1": grp.quantile(0.25),
        "q3": grp.quantile(0.75),
        "n": grp.count(),
    }).reset_index().sort_values("target_period")
    return out


def leaderboard_for_period(
    df: pd.DataFrame,
    forecast_type: str,
    target_period: str,
    realized_value: float,
    top_n: int = 5,
) -> pd.DataFrame:
    """
    Belirli (tür, dönem) için gerçekleşene en yakın tahminciler.
    """
    if df is None or df.empty or pd.isna(realized_value):
        return pd.DataFrame()

    target_ts = pd.to_datetime(target_period + "-01"
                                if len(str(target_period)) == 7
                                else target_period)

    sub = df[
        (df["forecast_type"] == forecast_type)
        & (df["target_period"] == target_ts)
    ].copy()
    if sub.empty:
        return pd.DataFrame()

    # Her katılımcının o döneme verdiği en son tahmin
    sub = sub.sort_values("updated_at").drop_duplicates(
        subset=["source_name"], keep="last"
    )

    # value yoksa median kullan
    sub["_val"] = sub["value"].fillna(sub["median"])
    sub = sub.dropna(subset=["_val"])
    if sub.empty:
        return pd.DataFrame()

    sub["sapma"] = (sub["_val"] - realized_value).abs()
    return sub.sort_values("sapma").head(top_n)[
        ["source_name", "entry_type", "_val", "sapma", "updated_at"]
    ].rename(columns={"_val": "tahmin"})


def revision_history(
    df: pd.DataFrame,
    source_name: str,
    forecast_type: str,
    target_period: str,
) -> pd.DataFrame:
    """Bir kaynağın belirli hedef dönem için verdiği tüm tahminler (zaman sırasıyla)."""
    if df is None or df.empty:
        return df
    target_ts = pd.to_datetime(target_period + "-01"
                                if len(str(target_period)) == 7
                                else target_period)
    sub = df[
        (df["source_name"] == source_name)
        & (df["forecast_type"] == forecast_type)
        & (df["target_period"] == target_ts)
    ].sort_values("updated_at")
    sub = sub.copy()
    sub["_val"] = sub["value"].fillna(sub["median"])
    return sub


# =============================================================
# PİYASA VERİSİ — EVDS (TÜFE hibrit) + BIS (PPK)
# =============================================================
def _evds_to_pct(evds_client, series_code: str,
                 fetch_start: str, fetch_end: str) -> pd.DataFrame:
    try:
        raw = evds_client.get_data(
            [series_code],
            startdate=fetch_start,
            enddate=fetch_end,
            frequency=5,
        )
        if raw is None or raw.empty:
            return pd.DataFrame()

        raw["dt"] = pd.to_datetime(raw["Tarih"], format="%Y-%m", errors="coerce")
        raw = raw.dropna(subset=["dt"]).sort_values("dt").reset_index(drop=True)

        val_col = [c for c in raw.columns if c not in ("Tarih", "dt")][0]
        raw[val_col] = pd.to_numeric(raw[val_col], errors="coerce")
        raw = raw.dropna(subset=[val_col])

        raw["Aylık TÜFE"] = raw[val_col].pct_change(1) * 100
        raw["Yıllık TÜFE"] = raw[val_col].pct_change(12) * 100
        raw["Donem"] = raw["dt"].dt.strftime("%Y-%m")
        return raw[["Donem", "Aylık TÜFE", "Yıllık TÜFE"]].copy()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def fetch_market_data(start_date, end_date) -> Tuple[pd.DataFrame, Optional[str]]:
    """
    Hibrit TÜFE (EVDS) + PPK Faizi (BIS) → aylık master tablo.
    Kolonlar: Donem (YYYY-MM), Aylık TÜFE, Yıllık TÜFE, PPK Faizi
    """
    empty = pd.DataFrame(columns=["Donem", "Aylık TÜFE", "Yıllık TÜFE", "PPK Faizi"])
    api_key = get_evds_key()

    if not api_key:
        return empty, "EVDS_KEY secrets içinde tanımlı değil."

    # TÜFE (hibrit)
    df_inf = pd.DataFrame()
    try:
        from evds import evdsAPI
        client = evdsAPI(api_key)
        ts_start = pd.Timestamp(start_date)
        ts_end = pd.Timestamp(end_date)

        fetch_start_old = (ts_start - pd.DateOffset(months=13)).replace(day=1).strftime("%d-%m-%Y")
        df_old = _evds_to_pct(client, EVDS_TUFE_OLD, fetch_start_old, "01-12-2025")

        fetch_end_new = ts_end.replace(day=1).strftime("%d-%m-%Y")
        df_new = _evds_to_pct(client, EVDS_TUFE_NEW, "01-01-2025", fetch_end_new)
        if not df_new.empty:
            df_new = df_new[df_new["Donem"] >= "2026-01"].copy()

        df_all = pd.concat([df_old, df_new], ignore_index=True)
        df_all = df_all.drop_duplicates(subset=["Donem"], keep="last").sort_values("Donem")

        cutoff = ts_start.strftime("%Y-%m")
        end_cutoff = ts_end.strftime("%Y-%m")
        df_inf = df_all[
            (df_all["Donem"] >= cutoff) & (df_all["Donem"] <= end_cutoff)
        ].copy()
        df_inf["Aylık TÜFE"] = pd.to_numeric(df_inf["Aylık TÜFE"], errors="coerce").round(2)
        df_inf["Yıllık TÜFE"] = pd.to_numeric(df_inf["Yıllık TÜFE"], errors="coerce").round(2)
        df_inf = df_inf.dropna(subset=["Aylık TÜFE", "Yıllık TÜFE"]).reset_index(drop=True)
    except Exception as e:
        return empty, f"EVDS hatası: {e}"

    # PPK (BIS)
    df_pol = pd.DataFrame()
    try:
        s = pd.Timestamp(start_date).strftime("%Y-%m-%d")
        e = pd.Timestamp(end_date).strftime("%Y-%m-%d")
        r = requests.get(BIS_PPK_URL.format(start=s, end=e), timeout=20)
        if r.status_code == 200:
            tmp = pd.read_csv(
                io.StringIO(r.content.decode("utf-8")),
                usecols=["TIME_PERIOD", "OBS_VALUE"],
            )
            tmp["dt"] = pd.to_datetime(tmp["TIME_PERIOD"])
            tmp["Donem"] = tmp["dt"].dt.strftime("%Y-%m")
            tmp["PPK Faizi"] = pd.to_numeric(tmp["OBS_VALUE"], errors="coerce")
            df_pol = (
                tmp.sort_values("dt").groupby("Donem").last().reset_index()
                [["Donem", "PPK Faizi"]]
            )
    except Exception:
        pass

    if not df_inf.empty and not df_pol.empty:
        master = pd.merge(df_inf, df_pol, on="Donem", how="left")
        master["PPK Faizi"] = master["PPK Faizi"].ffill()
    elif not df_inf.empty:
        master = df_inf.copy()
    elif not df_pol.empty:
        master = df_pol.copy()
    else:
        return empty, "Veri bulunamadı."

    for c in ["Aylık TÜFE", "Yıllık TÜFE", "PPK Faizi"]:
        if c not in master.columns:
            master[c] = np.nan

    return master.sort_values("Donem").reset_index(drop=True), None


# =============================================================
# DEMO VERİ ÜRETİCİ
# =============================================================
DEMO_SURVEYS = ["Reuters", "Bloomberg HT", "AA Finans"]
DEMO_INSTITUTIONS = [
    "Ak Yatırım", "Garanti BBVA", "İş Yatırım",
    "Yapı Kredi Yatırım", "QNB Finansinvest",
    "HSBC", "Goldman Sachs", "JP Morgan",
]
DEMO_PEOPLE = [
    "Haluk Bürümcekçi", "Enver Erkan", "Özlem Derici Şengül",
    "Mahfi Eğilmez", "Uğur Gürses",
]


def _round_step(x: float, step: float = 0.25) -> float:
    return round(round(x / step) * step, 2)


def generate_demo_data(seed: int = 42) -> Tuple[int, str]:
    """Son 12 ay için gerçekçi demo veri üretir (batch insert)."""
    rng = np.random.default_rng(seed)
    random.seed(seed)

    today = date.today()
    months = []
    for i in range(12, 0, -1):
        d = today.replace(day=15) - timedelta(days=30 * i)
        months.append(d.replace(day=15))

    # Baseline: PPK %50→40, aylık enf %3.5→2, yıllık %70→45
    baselines = {}
    for i, m in enumerate(months):
        t = i / max(1, len(months) - 1)
        baselines[m.strftime("%Y-%m")] = {
            "ppk": 50 - 10 * t + rng.normal(0, 0.8),
            "tufe_aylik": max(0.3, 3.5 - 1.5 * t + rng.normal(0, 0.4)),
            "tufe_yillik": 70 - 25 * t + rng.normal(0, 1.5),
            "yilsonu_enf": 38 + rng.normal(0, 2),
            "yilsonu_faiz": 32 + rng.normal(0, 1.5),
        }

    all_payloads = []

    def _bias(name: str) -> float:
        return {
            "Goldman Sachs": -0.5, "HSBC": -0.3, "JP Morgan": -0.4,
            "Haluk Bürümcekçi": 0.5, "Uğur Gürses": 0.3,
        }.get(name, 0.0)

    for forecast_month in months:
        month_key = forecast_month.strftime("%Y-%m")
        base = baselines[month_key]

        # Hedef dönemler: o ay, +1, +3, yıl sonu
        targets = list(dict.fromkeys([
            forecast_month.strftime("%Y-%m-01"),
            (forecast_month + pd.DateOffset(months=1)).strftime("%Y-%m-01"),
            (forecast_month + pd.DateOffset(months=3)).strftime("%Y-%m-01"),
            f"{forecast_month.year}-12-01",
        ]))

        # Tüm katılımcılar
        participants = (
            [("survey", s) for s in DEMO_SURVEYS]
            + [("institution", s) for s in DEMO_INSTITUTIONS]
            + [("person", s) for s in DEMO_PEOPLE]
        )

        for etype, name in participants:
            bias = _bias(name)

            if etype == "person":
                # Bireyseller ay içinde 2-3 kez
                n_updates = int(rng.integers(2, 4))
                days = sorted(rng.choice(range(1, 28), size=n_updates, replace=False))
                dates = [forecast_month.replace(day=int(d)) for d in days]
            elif etype == "survey":
                dates = [forecast_month.replace(day=15)]
            else:  # institution
                dates = [forecast_month.replace(day=int(rng.choice([5, 10, 15, 20])))]

            for fdate in dates:
                for ftype in ["ppk", "tufe_aylik", "tufe_yillik",
                              "yilsonu_enf", "yilsonu_faiz"]:
                    for tp in targets:
                        months_ahead = (
                            pd.Timestamp(tp).to_period("M").ordinal
                            - pd.Timestamp(month_key + "-01").to_period("M").ordinal
                        )
                        noise = 1.0 + 0.3 * abs(months_ahead)
                        b = base[ftype]
                        val = _round_step(
                            b + bias + rng.normal(0, 1.0) * noise, 0.25
                        )

                        payload = {
                            "entry_type": etype,
                            "source_name": name,
                            "forecast_type": ftype,
                            "target_period": tp,
                            "created_at": fdate.isoformat() + "T12:00:00+00:00",
                            "updated_at": fdate.isoformat() + "T12:00:00+00:00",
                            "entry_date": fdate.isoformat(),
                        }

                        if etype == "survey":
                            spread = abs(rng.normal(2, 0.5))
                            payload["median"] = val
                            payload["min_val"] = _round_step(val - spread, 0.25)
                            payload["max_val"] = _round_step(val + spread, 0.25)
                            payload["n_participants"] = int(rng.integers(15, 30))
                        else:
                            payload["value"] = val

                        all_payloads.append(payload)

    # Dedupe (unique index ile çakışmasın)
    seen = {}
    for p in all_payloads:
        k = (p["source_name"], p["forecast_type"], p["target_period"],
             p["entry_date"])
        seen[k] = p
    all_payloads = list(seen.values())

    # Batch insert
    sb = get_supabase()
    added = 0
    errors = []
    BATCH = 500
    for i in range(0, len(all_payloads), BATCH):
        chunk = all_payloads[i:i + BATCH]
        try:
            sb.table(TABLE_ENTRIES).insert(chunk).execute()
            added += len(chunk)
        except Exception as e:
            errors.append(str(e)[:200])
            # fallback: tek tek dene
            for p in chunk:
                try:
                    sb.table(TABLE_ENTRIES).insert(p).execute()
                    added += 1
                except Exception:
                    pass

    get_all_entries.clear()
    msg = f"{added} kayıt eklendi."
    if errors:
        msg += f" ({len(errors)} batch hatası; örn: {errors[0][:100]})"
    return added, msg


# =============================================================
# UI TEMA
# =============================================================
def apply_theme():
    st.markdown(
        """
        <style>
          html, body, [class*="css"] {
            font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", sans-serif;
          }
          h1, h2, h3 { letter-spacing: -0.02em; }
          .main .block-container {
            padding-top: 2rem;
            padding-bottom: 3rem;
            max-width: 1400px;
          }

          [data-testid="stMetric"] {
            background: linear-gradient(135deg, rgba(30,41,59,0.5), rgba(15,23,42,0.4));
            padding: 16px 20px;
            border-radius: 12px;
            border: 1px solid rgba(148,163,184,0.15);
          }
          [data-testid="stMetricLabel"] { color: #94A3B8 !important; font-size: 13px !important; font-weight: 500; }
          [data-testid="stMetricValue"] { font-size: 28px !important; font-weight: 700; }

          :root {
            --accent: #3B82F6;
            --success: #10B981;
            --warning: #F59E0B;
            --danger: #EF4444;
            --surface: rgba(15,23,42,0.55);
            --surface-strong: rgba(15,23,42,0.85);
            --border: rgba(148,163,184,0.18);
          }

          .soft-card {
            padding: 20px 22px;
            border-radius: 16px;
            border: 1px solid var(--border);
            background: var(--surface);
            box-shadow: 0 4px 16px rgba(0,0,0,0.10);
            margin-bottom: 14px;
          }
          .soft-card h3 { margin: 0 0 10px 0; font-size: 17px; font-weight: 600; }
          .soft-card ul { margin: 0; padding-left: 18px; color: rgba(226,232,240,0.88); }
          .soft-card li { margin: 4px 0; }

          .leader-card {
            padding: 14px 16px;
            border-radius: 12px;
            background: linear-gradient(135deg, rgba(59,130,246,0.08), rgba(16,185,129,0.05));
            border: 1px solid rgba(148,163,184,0.15);
            margin-bottom: 8px;
          }
          .leader-rank { font-size: 22px; margin-right: 6px; }
          .leader-name { font-weight: 600; font-size: 15px; }
          .leader-meta {
            color: #94A3B8; font-size: 12px; margin-top: 2px;
            font-variant-numeric: tabular-nums;
          }

          .page-header {
            margin-bottom: 22px;
            padding-bottom: 14px;
            border-bottom: 1px solid var(--border);
          }
          .page-header h1 { margin: 0; font-size: 28px; font-weight: 700; }
          .page-header .sub { color: #94A3B8; font-size: 14px; margin-top: 4px; }

          .badge {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 600;
          }
          .badge-survey      { background: rgba(59,130,246,0.18); color: #93C5FD; }
          .badge-institution { background: rgba(16,185,129,0.18); color: #6EE7B7; }
          .badge-person      { background: rgba(245,158,11,0.18); color: #FCD34D; }

          .actual-box {
            background: linear-gradient(135deg, rgba(239,68,68,0.10), rgba(239,68,68,0.04));
            border-left: 3px solid #EF4444;
            padding: 10px 14px;
            border-radius: 8px;
            margin-bottom: 10px;
            font-variant-numeric: tabular-nums;
          }

          [data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }

          .stButton button { border-radius: 10px; font-weight: 500; }
          .stButton button[kind="primary"] {
            box-shadow: 0 2px 8px rgba(59,130,246,0.25);
          }

          .app-title {
            text-align: center;
            font-size: 36px;
            font-weight: 700;
            margin: 20px 0 6px;
            background: linear-gradient(90deg, #60A5FA, #A78BFA);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
          }
          .app-subtitle { text-align: center; color: #94A3B8; font-size: 16px; margin-bottom: 28px; }
          .login-box {
            padding: 24px;
            border-radius: 16px;
            border: 1px solid var(--border);
            background: var(--surface-strong);
            box-shadow: 0 10px 30px rgba(0,0,0,0.25);
          }
          .hint { color: #94A3B8; font-size: 13px; text-align: center; margin-top: 10px; }

          .danger-zone {
            padding: 16px 18px;
            border-radius: 12px;
            border: 1px dashed rgba(239,68,68,0.4);
            background: rgba(239,68,68,0.05);
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(title: str, subtitle: str = ""):
    st.markdown(
        f"""
        <div class="page-header">
          <h1>{title}</h1>
          {f'<div class="sub">{subtitle}</div>' if subtitle else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def entry_type_badge(entry_type: str) -> str:
    cls_map = {
        "survey": "badge-survey",
        "institution": "badge-institution",
        "person": "badge-person",
    }
    label = ENTRY_TYPE_LABELS.get(entry_type, entry_type)
    cls = cls_map.get(entry_type, "badge-person")
    return f'<span class="badge {cls}">{label}</span>'
