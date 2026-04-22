import streamlit as st
import utils

st.set_page_config(page_title="Veri Havuzu", layout="wide")
utils.apply_theme()
utils.require_login_page()

utils.page_header("🗃️ Veri Havuzu", "Tüm tahminleri filtrele ve görüntüle")

df = utils.get_all_entries()

if df.empty:
    st.warning("Henüz veri yok.")
    st.stop()

types_df = utils.get_forecast_types()
ftype_labels = (
    {r["code"]: r["label_tr"] for _, r in types_df.iterrows()}
    if not types_df.empty else {}
)

# Filtreler
st.markdown("#### 🔍 Filtreler")
fc1, fc2, fc3, fc4 = st.columns(4)

etypes = sorted(df["entry_type"].dropna().unique().tolist())
sel_etypes = fc1.multiselect(
    "Tür", etypes, default=etypes,
    format_func=lambda x: utils.ENTRY_TYPE_LABELS.get(x, x),
)

ftypes = sorted(df["forecast_type"].dropna().unique().tolist())
sel_ftypes = fc2.multiselect(
    "Tahmin Türü", ftypes,
    format_func=lambda x: ftype_labels.get(x, x),
)

sources = sorted(df["source_name"].dropna().unique().tolist())
sel_sources = fc3.multiselect("Kaynak", sources)

periods = sorted(df["target_period"].dropna().dt.strftime("%Y-%m").unique().tolist())
sel_periods = fc4.multiselect("Hedef Dönem", periods)

# Filtrele
view = df.copy()
if sel_etypes:
    view = view[view["entry_type"].isin(sel_etypes)]
if sel_ftypes:
    view = view[view["forecast_type"].isin(sel_ftypes)]
if sel_sources:
    view = view[view["source_name"].isin(sel_sources)]
if sel_periods:
    view = view[view["target_period"].dt.strftime("%Y-%m").isin(sel_periods)]

st.caption(f"📊 Gösterilen: **{len(view):,}** / {len(df):,} kayıt")

# Okunabilir kolon sırası
display_cols = [
    "id", "entry_type", "source_name", "forecast_type", "target_period",
    "value", "median", "min_val", "max_val", "n_participants",
    "source_link", "note", "created_at", "updated_at",
]
display_cols = [c for c in display_cols if c in view.columns]

st.dataframe(view[display_cols], use_container_width=True, height=600)

# İndirme
csv = view[display_cols].to_csv(index=False).encode("utf-8-sig")
st.download_button(
    "📥 CSV olarak indir",
    csv,
    file_name="forecast_entries.csv",
    mime="text/csv",
)
