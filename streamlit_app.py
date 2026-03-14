import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client

PASSWORD = st.secrets["APP_PASSWORD"]

pwd = st.text_input("Şifre", type="password")

if pwd != PASSWORD:
    st.stop()

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_SERVICE_ROLE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

res = supabase.table("forecast_entries").select("*").execute()

df = pd.DataFrame(res.data)

st.dataframe(df)

fig = px.line(
    df,
    x="created_at",
    y="value",
    color="source_name",
)

st.plotly_chart(fig)
