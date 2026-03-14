import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_SERVICE_ROLE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

APP_PASSWORD = st.secrets["APP_PASSWORD"]
ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]

pwd = st.text_input("Şifre", type="password")

if pwd != APP_PASSWORD:
    st.stop()

res = supabase.table("forecast_entries").select("*").execute()

df = pd.DataFrame(res.data)

if df.empty:
    st.write("Henüz kayıt yok.")
    st.stop()

df["target_period"] = pd.to_datetime(df["target_period"])
df["created_at"] = pd.to_datetime(df["created_at"])

st.title("Forecast Tracker")

tab1, tab2, tab3, tab4 = st.tabs([
    "Revizyon",
    "Heatmap",
    "Veri",
    "Admin"
])

with tab1:

    fig = px.line(
        df,
        x="created_at",
        y="value",
        color="source_name"
    )

    st.plotly_chart(fig)


with tab2:

    pivot = df.pivot_table(
        index="source_name",
        columns=df["target_period"].dt.strftime("%Y-%m"),
        values="value",
        aggfunc="last"
    )

    st.dataframe(pivot)


with tab3:

    st.dataframe(df)


with tab4:

    admin = st.text_input("Admin şifre", type="password")

    if admin != ADMIN_PASSWORD:
        st.stop()

    id_select = st.selectbox("Kayıt seç", df["id"])

    row = df[df["id"] == id_select].iloc[0]

    new_value = st.number_input(
        "Yeni değer",
        value=float(row["value"])
    )

    if st.button("Güncelle"):

        supabase.table("forecast_entries").update(
            {"value": new_value}
        ).eq("id", int(id_select)).execute()

        st.success("Güncellendi")

    if st.button("Sil"):

        supabase.table("forecast_entries").delete().eq(
            "id", int(id_select)
        ).execute()

        st.success("Silindi")
