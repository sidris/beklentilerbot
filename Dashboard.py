import datetime
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import utils

st.set_page_config(page_title="Dashboard", layout="wide")
utils.apply_theme()
utils.require_login_page()

utils.page_header("📈 Dashboard", "Liderlik, konsensüs ve ısı haritası")

# --- Veriler ---
with st.spinner("Veriler yükleniyor..."):
    df_all = utils.get_all_entries()
    types_df = utils.get_forecast_types()

    start = datetime.date(datetime.date.today().year - 3, 1, 1)
    end = datetime.date.today()
    realized_df, real_err = utils.fetch_market_data(start, end)

if df_all.empty:
    st.info(
        "Henüz tahmin yok. Telegram bot'undan veri girmeye başlayın "
        "veya **Admin** sayfasından demo veri üretin."
    )
    st.stop()

if types_df.empty:
    st.error(
        "`forecast_types` tablosu boş. `schema.sql` dosyasını Supabase'de "
        "çalıştırmayı unutmuş olabilirsiniz."
    )
    st.stop()


# =============================================================
# KONTROL PANELİ
# =============================================================
st.markdown("### 🎛️ Görünüm")
c1, c2, c3 = st.columns([1, 1, 2])

with c1:
    # Tahmin türü seç
    ftype_options = types_df["code"].tolist()
    ftype_labels = {row["code"]: row["label_tr"] for _, row in types_df.iterrows()}
    sel_ftype = st.selectbox(
        "Tahmin türü",
        ftype_options,
        format_func=lambda x: ftype_labels.get(x, x),
        key="dash_ftype",
    )

with c2:
    as_of_mode = st.radio(
        "Görünüm",
        ["En güncel", "As-of ayı"],
        horizontal=True,
        label_visibility="collapsed",
        key="asof_mode",
    )

with c3:
    all_months_updated = sorted(
        df_all["updated_at"].dt.strftime("%Y-%m").unique(),
        reverse=True,
    )
    if as_of_mode == "As-of ayı" and all_months_updated:
        as_of_month = st.selectbox(
            "Hangi ayın sonuna kadar verilen tahminler?",
            all_months_updated,
            index=0,
        )
        df_latest = utils.as_of_snapshot(df_all, as_of_month)
        st.caption(f"💡 {as_of_month} sonuna kadar verilen tahminlerin en son hali.")
    else:
        as_of_month = None
        df_latest = utils.latest_snapshot(df_all)

st.markdown("---")

# =============================================================
# 🏆 LİDERLİK TABLOSU
# =============================================================
st.markdown(f"### 🏆 Liderlik: {ftype_labels.get(sel_ftype, sel_ftype)}")

realized_col = utils.get_realized_col(sel_ftype)

if not realized_col:
    st.info(
        f"Bu tahmin türü için gerçekleşen karşılığı tanımlı değil "
        f"(`{sel_ftype}` için `realized_col` null). Liderlik tablosu gösterilemiyor."
    )
elif realized_df is None or realized_df.empty:
    st.warning(f"Piyasa verisi çekilemedi: {real_err or 'bilinmeyen hata'}")
else:
    # Gerçekleşeni olan dönemler
    if realized_col not in realized_df.columns:
        st.warning(f"`{realized_col}` piyasa verisinde yok.")
    else:
        valid = realized_df.dropna(subset=[realized_col])["Donem"].sort_values(
            ascending=False
        ).unique().tolist()

        if not valid:
            st.warning("Karşılaştırılacak gerçekleşme verisi yok.")
        else:
            lc1, lc2 = st.columns([1, 3])
            sel_period_str = lc1.selectbox("Dönem", valid, index=0, key="ld_period")

            real_row = realized_df[realized_df["Donem"] == sel_period_str].iloc[0]
            real_val = real_row[realized_col]

            lb = utils.leaderboard_for_period(
                df_latest, sel_ftype, sel_period_str, real_val, top_n=5
            )

            lc2.markdown(
                f"<div class='actual-box' style='margin-top:4px;'>"
                f"<b>Gerçekleşen</b> ({sel_period_str}): "
                f"<span style='font-size:20px;font-weight:700;'>{real_val:.2f}%</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

            if lb.empty:
                st.info("Bu dönem için tahmin bulunamadı.")
            else:
                medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
                cols = st.columns(min(5, len(lb)))
                for i, (_, row) in enumerate(lb.iterrows()):
                    with cols[i]:
                        medal = medals[i] if i < 5 else f"{i+1}."
                        st.markdown(
                            f"""
                            <div class="leader-card">
                              <div><span class="leader-rank">{medal}</span>
                                <span class="leader-name">{row['source_name']}</span></div>
                              <div style="margin-top:4px;">
                                {utils.entry_type_badge(row['entry_type'])}
                              </div>
                              <div class="leader-meta">
                                Tahmin: <b>{row['tahmin']:.2f}</b><br>
                                Sapma: <b>{row['sapma']:.2f}</b>
                              </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

st.markdown("---")

# =============================================================
# GRAFİKLER
# =============================================================
tab1, tab2, tab3 = st.tabs(["📊 Konsensüs Zaman Serisi", "🔥 Isı Haritası", "📈 Revizyon"])

# ---- TAB 1: Konsensüs ----
with tab1:
    consensus = utils.consensus_by_period(df_latest, sel_ftype)

    if consensus.empty:
        st.info("Bu tür için konsensüs hesaplanamadı.")
    else:
        fig = go.Figure()

        # IQR bandı
        fig.add_trace(go.Scatter(
            x=list(consensus["target_period"]) + list(consensus["target_period"][::-1]),
            y=list(consensus["q3"]) + list(consensus["q1"][::-1]),
            fill="toself",
            fillcolor="rgba(59,130,246,0.15)",
            line=dict(width=0),
            name="Q1-Q3 bandı",
            hoverinfo="skip",
        ))

        # Medyan
        fig.add_trace(go.Scatter(
            x=consensus["target_period"],
            y=consensus["median"],
            mode="lines+markers",
            name="Konsensüs (medyan)",
            line=dict(color="#3B82F6", width=3),
            marker=dict(size=8),
        ))

        # Gerçekleşen
        if realized_col and realized_df is not None and not realized_df.empty:
            if realized_col in realized_df.columns:
                real_plot = realized_df.dropna(subset=[realized_col]).copy()
                real_plot["target_period"] = pd.to_datetime(real_plot["Donem"] + "-01")
                real_plot = real_plot[
                    real_plot["target_period"].isin(consensus["target_period"])
                ]
                if not real_plot.empty:
                    fig.add_trace(go.Scatter(
                        x=real_plot["target_period"],
                        y=real_plot[realized_col],
                        mode="lines+markers",
                        name="Gerçekleşen",
                        line=dict(color="#EF4444", width=3, dash="dot"),
                        marker=dict(symbol="x", size=11, color="#EF4444"),
                    ))

        fig.update_layout(
            title=f"{ftype_labels.get(sel_ftype, sel_ftype)} — Konsensüs vs Gerçekleşen",
            hovermode="x unified",
            legend=dict(orientation="h", y=1.1),
            height=450,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(gridcolor="rgba(148,163,184,0.12)"),
            yaxis=dict(gridcolor="rgba(148,163,184,0.12)", title="%"),
            margin=dict(l=10, r=10, t=60, b=40),
        )
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("📊 Konsensüs detayları (tablo)"):
            display = consensus.copy()
            display["target_period"] = display["target_period"].dt.strftime("%Y-%m")
            st.dataframe(
                display.rename(columns={
                    "target_period": "Hedef Dönem",
                    "median": "Medyan",
                    "q1": "Q1",
                    "q3": "Q3",
                    "n": "Kaynak Sayısı",
                }).style.format({
                    "Medyan": "{:.2f}",
                    "Q1": "{:.2f}",
                    "Q3": "{:.2f}",
                }),
                use_container_width=True,
                hide_index=True,
            )

# ---- TAB 2: Isı Haritası ----
with tab2:
    st.markdown(
        "Her hücre, satırdaki kaynağın sütundaki hedef döneme verdiği "
        + ("**en son tahmini** gösterir." if as_of_month is None
           else f"**{as_of_month} sonuna kadar** verdiği en son tahmini gösterir.")
    )

    hc1, hc2 = st.columns([1, 1])
    etype_filter = hc1.multiselect(
        "Katılımcı türü",
        utils.ENTRY_TYPES,
        default=utils.ENTRY_TYPES,
        format_func=lambda x: utils.ENTRY_TYPE_LABELS.get(x, x),
    )

    # Sadece seçili forecast_type ve katılımcı türü
    df_heat = df_latest[
        (df_latest["forecast_type"] == sel_ftype)
        & (df_latest["entry_type"].isin(etype_filter))
    ].copy()

    if df_heat.empty:
        st.info("Bu kombinasyon için veri yok.")
    else:
        df_heat["_val"] = df_heat["value"].fillna(df_heat["median"])
        df_heat["_period"] = df_heat["target_period"].dt.strftime("%Y-%m")

        pivot = df_heat.pivot_table(
            index="source_name", columns="_period",
            values="_val", aggfunc="last",
        )
        pivot = pivot.reindex(columns=sorted(pivot.columns)).sort_index()

        if pivot.empty:
            st.info("Gösterilecek veri yok.")
        else:
            st.dataframe(
                pivot.style.background_gradient(cmap="RdYlGn_r", axis=None)
                    .format("{:.2f}", na_rep="—"),
                use_container_width=True,
                height=min(600, 60 + 35 * len(pivot)),
            )
            st.caption(
                f"📊 {len(pivot)} kaynak × {len(pivot.columns)} dönem • "
                f"Renk: **kırmızı = yüksek**, **yeşil = düşük**"
            )

# ---- TAB 3: Revizyon ----
with tab3:
    st.markdown("Bir kaynağın aynı hedef dönem için zaman içindeki tahmin değişimi.")

    rc1, rc2 = st.columns([2, 1])
    all_sources = sorted(df_all["source_name"].unique())
    sel_source = rc1.selectbox("Kaynak", all_sources, key="rev_src")

    src_df = df_all[
        (df_all["source_name"] == sel_source)
        & (df_all["forecast_type"] == sel_ftype)
    ]
    targets = sorted(src_df["target_period"].dropna().dt.strftime("%Y-%m").unique())

    if not targets:
        st.info("Bu kaynağın bu tür için verisi yok.")
    else:
        sel_target = rc2.selectbox("Hedef dönem", targets, key="rev_tgt")

        rev = utils.revision_history(df_all, sel_source, sel_ftype, sel_target)

        if rev.empty or rev["_val"].isna().all():
            st.info("Bu kombinasyon için veri yok.")
        else:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=rev["updated_at"], y=rev["_val"],
                mode="lines+markers+text",
                line=dict(color="#3B82F6", width=2),
                marker=dict(size=9),
                text=[f"{v:.2f}" for v in rev["_val"]],
                textposition="top center",
                name=sel_source,
            ))

            if realized_col and realized_df is not None and not realized_df.empty:
                real_row = realized_df[realized_df["Donem"] == sel_target]
                if not real_row.empty and realized_col in real_row.columns:
                    rv = real_row[realized_col].iloc[0]
                    if pd.notna(rv):
                        fig.add_hline(
                            y=rv, line_dash="dot", line_color="#EF4444",
                            annotation_text=f"Gerçekleşen: {rv:.2f}",
                            annotation_position="right",
                        )

            fig.update_layout(
                title=f"{sel_source} — {sel_target} hedefi için "
                      f"{ftype_labels.get(sel_ftype, sel_ftype)} revizyonu",
                hovermode="x unified",
                height=420,
                showlegend=False,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(title="Tahmin Tarihi", gridcolor="rgba(148,163,184,0.12)"),
                yaxis=dict(title="Değer (%)", gridcolor="rgba(148,163,184,0.12)"),
                margin=dict(l=10, r=10, t=60, b=40),
            )
            st.plotly_chart(fig, use_container_width=True)

            show = rev[["updated_at", "_val", "source_link", "note"]].rename(columns={
                "updated_at": "Tarih", "_val": "Değer",
                "source_link": "Kaynak", "note": "Not",
            })
            st.dataframe(show, use_container_width=True, hide_index=True)
