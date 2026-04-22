import time
import pandas as pd
import streamlit as st
import utils


def _safe_float(val, default=0.0):
    """None/NaN'i default'a çevirir, float döner."""
    if val is None:
        return default
    try:
        if pd.isna(val):
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def _has_value(val) -> bool:
    """Değer None veya NaN değilse True."""
    if val is None:
        return False
    try:
        return not pd.isna(val)
    except (TypeError, ValueError):
        return True

st.set_page_config(page_title="Admin", layout="wide")
utils.apply_theme()
utils.require_login_page()

utils.page_header("⚙️ Admin", "Demo üret, veri düzenle, sıfırla")

# =============================================================
# ADMIN LOGIN
# =============================================================
if not utils.check_admin():
    admin_pwd_configured = utils.get_admin_password()

    if not admin_pwd_configured:
        st.warning(
            "⚠️ `ADMIN_PASSWORD` secrets'ta tanımlı değil. "
            "Lütfen Streamlit Cloud → Settings → Secrets'a ekleyin."
        )
        st.info("Örnek secrets:\n```toml\nADMIN_PASSWORD = \"guclu-sifre\"\n```")
        st.stop()

    st.markdown("### 🔐 Admin Girişi")
    st.caption("Bu sayfa hassas işlemler içerir. Admin şifresi gereklidir.")

    with st.form("admin_login"):
        pwd = st.text_input("Admin Şifresi", type="password")
        submit = st.form_submit_button("Giriş", type="primary")

        if submit:
            if pwd == admin_pwd_configured:
                st.session_state["admin_yapildi"] = True
                st.success("Admin girişi başarılı!")
                time.sleep(0.3)
                st.rerun()
            else:
                st.error("Hatalı admin şifresi.")
    st.stop()

# Admin çıkış butonu (sidebar)
if st.sidebar.button("🔒 Admin Çıkışı", use_container_width=True):
    st.session_state["admin_yapildi"] = False
    st.rerun()

# =============================================================
# BÖLÜM 1: DEMO VERİSİ
# =============================================================
st.markdown("### 🎬 Demo Verisi Üret")

df_exist = utils.get_all_entries()
if not df_exist.empty:
    st.info(f"ℹ️ Şu an sistemde **{len(df_exist):,}** kayıt var.")

st.markdown(
    """
    Son 12 ay için gerçekçi demo veri üretir:
    - **16 kaynak** (3 anket, 8 kurum, 5 kişi)
    - **5 tahmin türü** (PPK, aylık/yıllık TÜFE, yıl sonu enflasyon & faiz)
    - Kişiler ayda 2-3 revizyon, kurumlar ve anketler 1
    - Anketler için medyan + min + max + N
    """
)

dc1, dc2 = st.columns([1, 3])
seed = dc1.number_input("Seed", value=42, step=1)

if dc2.button("🚀 Demo Verisi Üret", type="primary"):
    with st.spinner("Üretiliyor... (batch insert, ~5-15 sn)"):
        added, msg = utils.generate_demo_data(seed=int(seed))
    st.success(f"✅ {msg}")
    st.balloons()
    time.sleep(0.5)
    st.rerun()

st.markdown("---")

# =============================================================
# BÖLÜM 2: TAHMİN TÜRÜ EKLE
# =============================================================
st.markdown("### ➕ Yeni Tahmin Türü Ekle")
st.caption(
    "Yeni bir tahmin türü (örn: 'dolar_kuru', 'gsyih_buyume') eklemek için. "
    "Bot ve dashboard bu listeden okur."
)

tc1, tc2, tc3, tc4 = st.columns([1, 2, 1, 2])
new_code = tc1.text_input("Kod", placeholder="dolar_kuru", help="a-z, _, sayı").strip()
new_label = tc2.text_input("Etiket", placeholder="Dolar Kuru").strip()
new_unit = tc3.selectbox("Birim", ["%", "TL", "USD", "puan", "diğer"])

realized_options = ["(yok)", "Aylık TÜFE", "Yıllık TÜFE", "PPK Faizi"]
new_realized = tc4.selectbox(
    "Gerçekleşen kolonu (piyasa verisinde)",
    realized_options,
    help="Liderlik tablosu için EVDS/BIS'teki karşılık. Yoksa (yok).",
)

if st.button("➕ Ekle", disabled=not (new_code and new_label)):
    ok, msg = utils.add_forecast_type(
        code=new_code,
        label_tr=new_label,
        unit=new_unit,
        realized_col=None if new_realized == "(yok)" else new_realized,
    )
    if ok:
        st.success(f"✅ {msg}")
        time.sleep(0.5)
        st.rerun()
    else:
        st.error(f"❌ {msg}")

# Mevcut türleri göster
with st.expander("📋 Mevcut Tahmin Türleri"):
    types_df = utils.get_forecast_types()
    if not types_df.empty:
        st.dataframe(types_df, use_container_width=True, hide_index=True)

st.markdown("---")

# =============================================================
# BÖLÜM 3: VERİ DÜZENLE / SİL
# =============================================================
st.markdown("### ✏️ Veri Düzenle / Sil")

df = utils.get_all_entries()
if df.empty:
    st.info("Düzenlenecek veri yok.")
else:
    # Filtrele
    filt_col, _ = st.columns([2, 2])
    search = filt_col.text_input("🔍 Kaynak ara", placeholder="İsim yaz...")

    view = df.copy()
    if search:
        view = view[view["source_name"].str.contains(search, case=False, na=False)]

    # Silme için seçim
    st.markdown(f"**{len(view):,} kayıt** gösteriliyor.")

    df_sel = view.copy()
    df_sel.insert(0, "Sec", False)

    edited = st.data_editor(
        df_sel,
        column_config={"Sec": st.column_config.CheckboxColumn(required=True)},
        disabled=[c for c in df_sel.columns if c != "Sec"],
        hide_index=True,
        use_container_width=True,
        height=500,
        key="admin_editor",
    )

    selected = edited[edited["Sec"] == True]

    if not selected.empty:
        sc1, sc2 = st.columns([1, 3])
        sc1.metric("Seçili", len(selected))
        if sc2.button("🔥 Seçilenleri Sil", type="primary"):
            ids = selected["id"].tolist()
            ok, msg = utils.delete_entries_by_ids(ids)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    # Tek satır düzenleme
    with st.expander("✏️ Tek satır değer güncelle"):
        ids_available = view["id"].tolist()
        if ids_available:
            sel_id = st.selectbox("Kayıt ID", ids_available, key="edit_id")
            row = view[view["id"] == sel_id].iloc[0]

            uc1, uc2, uc3, uc4 = st.columns(4)
            new_val = uc1.number_input(
                "value",
                value=_safe_float(row.get("value")),
                step=0.25, format="%.2f",
            )
            new_median = uc2.number_input(
                "median",
                value=_safe_float(row.get("median")),
                step=0.25, format="%.2f",
            )
            new_min = uc3.number_input(
                "min",
                value=_safe_float(row.get("min_val")),
                step=0.25, format="%.2f",
            )
            new_max = uc4.number_input(
                "max",
                value=_safe_float(row.get("max_val")),
                step=0.25, format="%.2f",
            )

            if st.button("💾 Güncelle"):
                updates = {
                    "value": new_val if new_val != 0 else None,
                    "median": new_median if new_median != 0 else None,
                    "min_val": new_min if new_min != 0 else None,
                    "max_val": new_max if new_max != 0 else None,
                }
                ok, msg = utils.update_entry_by_id(int(sel_id), updates)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

st.markdown("---")

# =============================================================
# BÖLÜM 4: TAM SIFIRLAMA
# =============================================================
st.markdown("### 🔥 Tam Sıfırlama — Dikkat!")

st.markdown(
    """
    <div class="danger-zone">
    <b style="color:#FCA5A5;">⚠️ Tehlike Bölgesi</b><br>
    <span style="color:#94A3B8;font-size:13px;">
    Aşağıdaki işlemler <b>geri alınamaz</b>. Demo sonrası gerçek veriye geçmek istediğinde kullan.
    </span>
    </div>
    """,
    unsafe_allow_html=True,
)

st.write("")

with st.expander("🗑️ Sıfırlama Seçenekleri"):
    reset_mode = st.radio(
        "Ne silinsin?",
        ["Sadece tahminler", "Tahminler + tür ve anket listeleri"],
        key="reset_mode",
    )
    confirm = st.text_input(
        "Onaylamak için **SIL** yazınız",
        placeholder="SIL",
        key="reset_confirm",
    )

    if st.button("🔥 Sıfırla", type="primary", disabled=(confirm != "SIL")):
        include_types = (reset_mode == "Tahminler + tür ve anket listeleri")
        with st.spinner("Siliniyor..."):
            ok, msg = utils.reset_all_data(include_types=include_types)
        if ok:
            st.success(f"✅ {msg}")
            time.sleep(1)
            st.rerun()
        else:
            st.error(f"❌ {msg}")
    if confirm and confirm != "SIL":
        st.caption("❌ Tam olarak **SIL** yazınız (büyük harf).")
