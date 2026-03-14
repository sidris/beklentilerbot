import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client

st.set_page_config(page_title="Forecast Tracker", layout="wide")
st.title("Forecast Tracker")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = st.secrets["SUPABASE_SERVICE_ROLE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

@st.cache_data(ttl=60)
def load_data():
    res = (
        supabase.table("forecast_entries")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    data = res.data or []
    df = pd.DataFrame(data)
    if not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"])
        df["target_period"] = pd.to_datetime(df["target_period"])
    return df

df = load_data()

if df.empty:
    st.info("Henüz kayıt yok.")
    st.stop()

col1, col2, col3 = st.columns(3)

with col1:
    selected_type = st.selectbox("Tahmin türü", ["all"] + sorted(df["forecast_type"].dropna().unique().tolist()))
with col2:
    selected_source = st.selectbox("Kaynak", ["all"] + sorted(df["source_name"].dropna().unique().tolist()))
with col3:
    selected_period = st.selectbox(
        "Hedef dönem",
        ["all"] + sorted(df["target_period"].dt.strftime("%Y-%m").unique().tolist())
    )

filtered = df.copy()

if selected_type != "all":
    filtered = filtered[filtered["forecast_type"] == selected_type]

if selected_source != "all":
    filtered = filtered[filtered["source_name"] == selected_source]

if selected_period != "all":
    filtered = filtered[filtered["target_period"].dt.strftime("%Y-%m") == selected_period]

st.subheader("Ham kayıtlar")
st.dataframe(filtered.sort_values("created_at", ascending=False), use_container_width=True)

st.subheader("Revizyon zaman serisi")
if not filtered.empty:
    fig = px.line(
        filtered.sort_values("created_at"),
        x="created_at",
        y="value",
        color="source_name",
        markers=True,
        hover_data=["forecast_type", "target_period"]
    )
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Isı haritası: son tahmin")
latest = (
    df.sort_values("created_at")
      .groupby(["source_name", "forecast_type", "target_period"], as_index=False)
      .tail(1)
)

if selected_type != "all":
    latest = latest[latest["forecast_type"] == selected_type]

heat = latest.pivot_table(
    index="source_name",
    columns=latest["target_period"].dt.strftime("%Y-%m"),
    values="value",
    aggfunc="last"
)

if not heat.empty:
    fig2 = px.imshow(
        heat,
        aspect="auto",
        text_auto=True
    )
    st.plotly_chart(fig2, use_container_width=True)