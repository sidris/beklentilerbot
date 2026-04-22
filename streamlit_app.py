"""
streamlit_app.py — Forecast Tracker ana sayfa.
Giriş ekranı ve özet metrikler.
"""
import time
import streamlit as st
import utils

st.set_page_config(
    page_title="Forecast Tracker",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
utils.apply_theme()


def render_login():
    st.markdown("<div class='app-title'>📊 Forecast Tracker</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='app-subtitle'>Anket, kurum ve kişi tahminleri • karşılaştır • analiz et</div>",
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3, gap="large")
    with c1:
        st.markdown(
            """
            <div class="soft-card">
              <h3>🤖 Telegram Bot ile Giriş</h3>
              <ul>
                <li>/new komutuyla tahmin ekle</li>
                <li>Anket, Kurum, Kişi ayrımı</li>
                <li>PPK ve TÜFE tahminleri</li>
              </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            """
            <div class="soft-card">
              <h3>🏆 Performans Analizi</h3>
              <ul>
                <li>Dönem bazlı liderlik tabloları</li>
                <li>Gerçekleşene karşı kıyas</li>
                <li>Tahmin revizyon takibi</li>
              </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            """
            <div class="soft-card">
              <h3>📊 Canlı Piyasa Verisi</h3>
              <ul>
                <li>TCMB EVDS (hibrit TÜFE)</li>
                <li>BIS (politika faizi)</li>
                <li>Otomatik karşılaştırma</li>
              </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write("")
    left, mid, right = st.columns([1.2, 1, 1.2])
    with mid:
        st.markdown("<div class='login-box'>", unsafe_allow_html=True)
        with st.form("login_form", clear_on_submit=True):
            pwd = st.text_input("Erişim Şifresi", type="password")
            submit = st.form_submit_button("Giriş Yap", type="primary", use_container_width=True)
        if submit:
            if pwd == utils.get_app_password():
                st.session_state["giris_yapildi"] = True
                st.success("Giriş başarılı!")
                time.sleep(0.2)
                st.rerun()
            else:
                st.error("Hatalı şifre.")
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='hint'>Şifre girince tüm sayfalar açılır.</div>",
            unsafe_allow_html=True,
        )


# --- Giriş kontrolü ---
if not utils.check_login():
    st.markdown(
        """
        <style>
          [data-testid="stSidebar"] {display: none;}
          [data-testid="stSidebarCollapsedControl"] {display: none;}
        </style>
        """,
        unsafe_allow_html=True,
    )
    render_login()
    st.stop()

# --- Giriş yapıldıktan sonra ---
st.sidebar.markdown("### 📌 Menü")
st.sidebar.caption("Sayfalar için sol menüyü kullanın.")
st.sidebar.markdown("---")

if st.sidebar.button("🚪 Çıkış Yap", use_container_width=True):
    st.session_state["giris_yapildi"] = False
    st.session_state["admin_yapildi"] = False
    st.rerun()

st.markdown("<div class='app-title' style='font-size:32px;'>👋 Hoş geldiniz</div>",
            unsafe_allow_html=True)
st.markdown(
    "<div class='app-subtitle'>Aşağıda sistem özetini görebilir, sol menüden sayfalara geçebilirsiniz.</div>",
    unsafe_allow_html=True,
)

try:
    df = utils.get_all_entries()
    types_df = utils.get_forecast_types()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Toplam Tahmin", f"{len(df):,}")

    if not df.empty:
        c2.metric("Kaynak Sayısı", f"{df['source_name'].nunique()}")
        c3.metric("Tahmin Türü", f"{df['forecast_type'].nunique()}")
        c4.metric("Hedef Dönem", f"{df['target_period'].nunique()}")
    else:
        c2.metric("Kaynak", "—")
        c3.metric("Tür", "—")
        c4.metric("Dönem", "—")

    if not df.empty and "entry_type" in df.columns:
        st.markdown("#### Katılımcı Dağılımı")
        ec1, ec2, ec3 = st.columns(3)
        for col, etype in zip([ec1, ec2, ec3], ["survey", "institution", "person"]):
            n = int((df["entry_type"] == etype).sum())
            col.metric(utils.ENTRY_TYPE_LABELS[etype], f"{n:,}")
except Exception as e:
    st.error(f"Özet yüklenemedi: {e}")
    st.info(
        "İlk kurulumda bu normal. Supabase bağlantısını ve `schema.sql`'in "
        "çalıştırıldığını kontrol edin."
    )

st.markdown("---")

st.markdown("### ⚡ Hızlı Eylemler")
a1, a2, a3 = st.columns(3)
with a1:
    st.markdown(
        """
        <div class="soft-card">
          <h3>📈 Dashboard</h3>
          <div style="color:#94A3B8;font-size:13px;">
            Liderlik tablosu, konsensüs grafiği ve ısı haritası.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with a2:
    st.markdown(
        """
        <div class="soft-card">
          <h3>🔄 Revizyon Takibi</h3>
          <div style="color:#94A3B8;font-size:13px;">
            Bir katılımcının aynı hedefe verdiği tahminlerin zaman içindeki değişimi.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with a3:
    st.markdown(
        """
        <div class="soft-card">
          <h3>⚙️ Admin</h3>
          <div style="color:#94A3B8;font-size:13px;">
            Demo üret, veri düzenle/sil, tam sıfırlama.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
