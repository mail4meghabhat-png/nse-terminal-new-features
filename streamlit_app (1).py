"""
NSE Stock Analysis Dashboard (Streamlit)
========================================
Front-end for the FastAPI service (nse_analysis_api.py).

REQUIREMENTS
    pip install streamlit requests pandas plotly

RUN
    1. Start the API:        uvicorn nse_analysis_api:app --port 8000
    2. Start the dashboard:  streamlit run streamlit_app.py

DEPLOY FREE
    Push this file + requirements.txt to GitHub, then deploy on
    Streamlit Community Cloud. In the app's Settings > Secrets add:
        API_URL = "https://your-api.onrender.com"
"""

import requests
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

st.set_page_config(page_title="NSE Stock Terminal", page_icon="📈", layout="wide")

# ── Config ────────────────────────────────────────────────────────────────
try:
    DEFAULT_API = st.secrets["API_URL"]
except Exception:
    DEFAULT_API = "http://127.0.0.1:8000"

DEFAULT_WATCHLIST = "RELIANCE,TCS,INFY,HDFCBANK,ICICIBANK"

with st.sidebar:
    st.title("📈 NSE Terminal")
    api_url = st.text_input("API URL", DEFAULT_API).rstrip("/")
    symbol = st.text_input("Stock symbol", "RELIANCE").upper().strip()
    months = st.slider("Chart history (months)", 1, 24, 6)
    st.caption(
        "Free-tier hosts sleep when idle, so the first request can take up to a minute."
    )
    st.caption("Educational analysis only, not investment advice.")


# ── API helpers (cached 5 min to avoid hammering Yahoo / your server) ─────
@st.cache_data(ttl=300, show_spinner=False)
def fetch(path: str, params: tuple = ()):
    r = requests.get(f"{api_url}{path}", params=dict(params), timeout=90)
    if r.status_code != 200:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        raise RuntimeError(detail)
    return r.json()


def fmt(v, suffix="", na="—"):
    return na if v is None else f"{v:,.2f}{suffix}"


# ── Simple rule-based labels ──────────────────────────────────────────────
def rsi_label(v):
    if v is None:
        return "n/a"
    if v >= 70:
        return "Overbought"
    if v <= 30:
        return "Oversold"
    return "Neutral"


def adx_label(v):
    if v is None:
        return "n/a"
    if v >= 40:
        return "Very strong trend"
    if v >= 25:
        return "Trending"
    return "Weak / ranging"


def bb_label(v):
    if v is None:
        return "n/a"
    if v > 1:
        return "Above upper band"
    if v < 0:
        return "Below lower band"
    return "Inside bands"


# ── Tabs ──────────────────────────────────────────────────────────────────
tab_overview, tab_chart, tab_watch = st.tabs(["Overview", "Chart", "Watchlist"])

# ═════════ OVERVIEW ═════════
with tab_overview:
    st.header(f"{symbol}")
    try:
        with st.spinner("Analyzing..."):
            data = fetch(f"/analyze/{symbol}")
    except Exception as e:
        st.error(f"Could not load {symbol}: {e}")
        data = None

    if data:
        t, f = data["technical"], data["fundamentals"]

        if data.get("corporate_action_flag"):
            st.warning(data["corporate_action_note"])

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Price (₹)", fmt(t["current_price"]))
        c2.metric("% of 52W high", fmt(t["pct_of_52w_high"], "%"))
        c3.metric("MA trend", (t["ma_trend"] or "n/a").title())
        c4.metric("Market cap (₹ Cr)", fmt(f["market_cap_cr"]))

        st.subheader("Technical indicators")
        tech_rows = [
            ("RSI (14)", fmt(t["rsi_14"]), rsi_label(t["rsi_14"])),
            ("ROC (12)", fmt(t["roc_12"], "%"), "Positive momentum" if (t["roc_12"] or 0) > 0 else "Negative momentum"),
            ("MACD histogram", fmt(t["macd_histogram"]), "Bullish" if (t["macd_histogram"] or 0) > 0 else "Bearish"),
            ("ADX (14)", fmt(t["adx_14"]), adx_label(t["adx_14"])),
            ("MA 50 / MA 200", f"{fmt(t['ma_50'])} / {fmt(t['ma_200'])}", (t["ma_trend"] or "n/a").title()),
            ("Bollinger %B", fmt(t["bollinger_percent_b"]), bb_label(t["bollinger_percent_b"])),
            ("Bollinger bandwidth", fmt(t["bollinger_bandwidth_pct"], "%"), ""),
        ]
        st.dataframe(
            pd.DataFrame(tech_rows, columns=["Indicator", "Value", "Reading"]),
            hide_index=True,
            use_container_width=True,
        )

        st.subheader("Fundamentals")
        g1, g2, g3, g4 = st.columns(4)
        g1.metric("YoY earnings growth", fmt(f["yoy_earnings_growth_pct"], "%"))
        g2.metric("YoY revenue growth", fmt(f["yoy_revenue_growth_pct"], "%"))
        g3.metric("Operating margin", fmt(f["operating_margin_pct"], "%"))
        g4.metric("Net margin", fmt(f["net_margin_pct"], "%"))
        h1, h2, _, _ = st.columns(4)
        h1.metric("ROE (approx.)", fmt(f["roe_pct"], "%"))
        h2.metric("Debt / Equity", fmt(f["debt_to_equity"]))
        st.caption(
            "ROE is annualized from the latest quarter, so treat it as a rough estimate. "
            "Banks and financials often show missing or unusual debt figures."
        )

# ═════════ CHART ═════════
with tab_chart:
    try:
        with st.spinner("Loading chart..."):
            chart = fetch(f"/chart/{symbol}", (("months", months),))
        df = pd.DataFrame(chart["data"])
        df["date"] = pd.to_datetime(df["date"])
    except Exception as e:
        st.error(f"Could not load chart for {symbol}: {e}")
        df = None

    if df is not None and not df.empty:
        show_ma = st.checkbox("Show moving averages", True)
        show_vol = st.checkbox("Show volume", True)

        fig = make_subplots(
            rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03,
            row_heights=[0.5, 0.12, 0.19, 0.19],
            subplot_titles=("Price", "Volume", "RSI (14)", "MACD"),
        )
        fig.add_trace(go.Candlestick(
            x=df["date"], open=df["open"], high=df["high"], low=df["low"],
            close=df["close"], name="Price"), row=1, col=1)

        if show_ma:
            fig.add_trace(go.Scatter(x=df["date"], y=df["ma_50"], name="MA 50",
                                     line=dict(width=1.5, color="orange")), row=1, col=1)
            fig.add_trace(go.Scatter(x=df["date"], y=df["ma_200"], name="MA 200",
                                     line=dict(width=1.5, color="royalblue")), row=1, col=1)
        if show_vol:
            colors = ["#26a69a" if c >= o else "#ef5350" for o, c in zip(df["open"], df["close"])]
            fig.add_trace(go.Bar(x=df["date"], y=df["volume"], marker_color=colors,
                                 name="Volume", showlegend=False), row=2, col=1)

        fig.add_trace(go.Scatter(x=df["date"], y=df["rsi"], name="RSI",
                                 line=dict(color="purple", width=1.5)), row=3, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)

        fig.add_trace(go.Scatter(x=df["date"], y=df["macd_line"], name="MACD",
                                 line=dict(width=1.5)), row=4, col=1)
        fig.add_trace(go.Scatter(x=df["date"], y=df["macd_signal"], name="Signal",
                                 line=dict(width=1.5, dash="dot")), row=4, col=1)

        fig.update_layout(
            height=850, xaxis_rangeslider_visible=False,
            margin=dict(l=10, r=10, t=40, b=10),
            legend=dict(orientation="h", y=1.04),
        )
        # hide weekends so there are no gaps
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("Raw data"):
            st.dataframe(df.sort_values("date", ascending=False), use_container_width=True)

# ═════════ WATCHLIST ═════════
with tab_watch:
    st.header("Watchlist")
    wl_input = st.text_input("Symbols (comma separated, max 10)", DEFAULT_WATCHLIST)
    if st.button("Refresh watchlist"):
        fetch.clear()

    if wl_input.strip():
        try:
            with st.spinner("Fetching watchlist..."):
                wl = fetch("/watchlist", (("symbols", wl_input),))
            wl_df = pd.DataFrame(wl["stocks"])
            if "error" in wl_df.columns and wl_df["error"].notna().any():
                st.warning("Some symbols failed: " + ", ".join(
                    wl_df.loc[wl_df["error"].notna(), "symbol"].tolist()))
            wl_df = wl_df.drop(columns=["error"], errors="ignore")
            if "current_price" in wl_df.columns:
                wl_df = wl_df.dropna(subset=["current_price"])
                st.dataframe(
                    wl_df,
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "symbol": "Symbol",
                        "current_price": st.column_config.NumberColumn("Price (₹)", format="%.2f"),
                        "rsi_14": st.column_config.ProgressColumn("RSI", min_value=0, max_value=100, format="%.1f"),
                        "macd_histogram": st.column_config.NumberColumn("MACD hist", format="%.2f"),
                        "ma_trend": "MA trend",
                        "pct_of_52w_high": st.column_config.NumberColumn("% of 52W high", format="%.1f"),
                        "corporate_action_flag": "Corp. action?",
                        "company_name": None,
                    },
                )
        except Exception as e:
            st.error(f"Watchlist failed: {e}")
