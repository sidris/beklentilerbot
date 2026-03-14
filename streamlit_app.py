import streamlit as st
import pandas as pd
from supabase import create_client

from dashboard_queries import load_forecasts, latest_snapshot, consensus_by_period
from dashboard_charts import revision_chart, consensus_chart, heatmap_chart

st.set_page_config(page_title="Beklenti Takip", layout="wide")

APP_PASSWORD = st.secrets["APP_PASSWORD"]

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("Giriş")
    pwd = st.text_input("Şifre", type="password")
    if st.button("Giriş Yap"):
        if pwd == APP_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Şifre yanlış")
    st.stop()

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = st.secrets["SUPABASE_SERVICE_ROLE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

st.title("Beklenti Takip Dashboard")

@st.cache_data(ttl=60)
def get_data():
    return load_forecasts(supabase)

df = get_data()

if df.empty:
    st.info("Henüz kayıt yok.")
    st.stop()

col1, col2, col3, col4 = st.columns(4)

with col1:
    entry_type_filter = st.selectbox(
        "Giriş türü",
        ["all"] + sorted(df["entry_type"].dropna().unique().tolist())
    )

with col2:
    source_filter = st.selectbox(
        "Kaynak",
        ["all"] + sorted(df["source_name"].dropna().unique().tolist())
    )

with col3:
    forecast_type_filter = st.selectbox(
        "Tahmin tipi",
        ["all"] + sorted(df["forecast_type"].dropna().unique().tolist())
    )

with col4:
    period_options = sorted(df["target_period"].dt.strftime("%Y-%m").unique().tolist())
    period_filter = st.selectbox("Dönem", ["all"] + period_options)

filtered = df.copy()

if entry_type_filter != "all":
    filtered = filtered[filtered["entry_type"] == entry_type_filter]

if source_filter != "all":
    filtered = filtered[filtered["source_name"] == source_filter]

if forecast_type_filter != "all":
    filtered = filtered[filtered["forecast_type"] == forecast_type_filter]

if period_filter != "all":
    filtered = filtered[filtered["target_period"].dt.strftime("%Y-%m") == period_filter]

tab1, tab2, tab3, tab4 = st.tabs(["Son Tahminler", "Revizyon", "Consensus", "Ham Veri"])

with tab1:
    latest = latest_snapshot(filtered)
    st.subheader("Son Tahminler")

    latest_display = latest.copy()
    if not latest_display.empty:
        latest_display["target_period"] = latest_display["target_period"].dt.strftime("%Y-%m")
        latest_display["updated_at"] = latest_display["updated_at"].dt.strftime("%Y-%m-%d %H:%M:%S")

    st.dataframe(
        latest_display.sort_values("updated_at", ascending=False),
        use_container_width=True
    )

    heat_source = latest.copy()
    if not heat_source.empty:
        pivot = heat_source.pivot_table(
            index="source_name",
            columns=heat_source["target_period"].dt.strftime("%Y-%m"),
            values="value",
            aggfunc="last"
        )
        fig = heatmap_chart(pivot)
        if fig:
            st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.subheader("Revizyon Grafiği")
    fig = revision_chart(filtered)
    if fig:
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Grafik için veri yok.")

with tab3:
    st.subheader("Consensus")
    cons = consensus_by_period(filtered)
    fig = consensus_chart(cons)
    if fig:
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Consensus için veri yok.")

with tab4:
    st.subheader("Ham Veri")
    raw = filtered.copy()
    raw["target_period"] = raw["target_period"].dt.strftime("%Y-%m")
    raw["created_at"] = raw["created_at"].dt.strftime("%Y-%m-%d %H:%M:%S")
    raw["updated_at"] = raw["updated_at"].dt.strftime("%Y-%m-%d %H:%M:%S")
    st.dataframe(raw.sort_values("updated_at", ascending=False), use_container_width=True)
