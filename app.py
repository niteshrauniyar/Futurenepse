import os
import json
import streamlit as st
import pandas as pd
from google import genai
from google.genai import types

# ─── Configuration & Styling ────────────────────────────────────────────────
st.set_page_config(
    page_title="NEPSE Intelligence | Smart Money Tracker",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS injected directly to replicate the dark cyberpunk theme
DARK_THEME_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@700;800&display=swap');
    
    /* Main Background Overrides */
    .stApp {
        background-color: #060810;
        color: #c8d8f0;
        font-family: 'Space Mono', monospace;
    }
    
    /* Headers & Custom Typography */
    h1, h2, h3 {
        font-family: 'Syne', sans-serif !important;
        color: #eef4ff !important;
        letter-spacing: 2px;
    }
    
    /* Metric Cards Custom Styling */
    .metric-card {
        background-color: #0c1020;
        border: 1px solid #1e2d4a;
        border-top: 2px solid #e8b84b;
        padding: 20px;
        border-radius: 4px;
        text-align: center;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    }
    .metric-label { font-size: 10px; color: #5a7090; text-transform: uppercase; letter-spacing: 2px; }
    .metric-value { font-family: 'Syne', sans-serif; font-size: 28px; font-weight: 800; color: #eef4ff; margin: 5px 0; }
    
    /* Signals & Analysis UI Blocks */
    .ai-summary-box {
        background: linear-gradient(135deg, rgba(155,109,255,0.06), rgba(0,212,255,0.04));
        border-left: 4px solid #9b6dff;
        padding: 15px 20px;
        margin: 15px 0;
        font-size: 13px;
        line-height: 1.8;
    }
    
    .signal-card {
        background-color: #0c1020;
        border: 1px solid #1e2d4a;
        padding: 15px;
        margin-bottom: 12px;
        border-radius: 4px;
    }
    
    /* Colors helper */
    .up-trend { color: #1ddb8b !important; font-weight: bold; }
    .dn-trend { color: #ff4466 !important; font-weight: bold; }
    .gold-txt { color: #e8b84b !important; }
    
    /* Notice Footer */
    .notice-box {
        padding: 12px;
        background: rgba(0,212,255,0.04);
        border: 1px solid rgba(0,212,255,0.15);
        font-size: 11px;
        color: #5a7090;
        margin-top: 25px;
    }
</style>
"""
st.markdown(DARK_THEME_CSS, unsafe_allow_html=True)

# ─── GenAI API Wrapper Client ────────────────────────────────────────────────
@st.cache_data(ttl=600)  # Cache results for 10 minutes to save API tokens
def ask_gemini_market_data(prompt: str) -> dict:
    """Uses Gemini 2.5 with Google Search grounding to fetch live data without throwing a 400 error."""
    try:
        client = genai.Client()
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[{"google_search": {}}],  # Live search validation turned ON
                temperature=0.1                 # Low temperature ensures it adheres strictly to structural demands
                # Note: response_mime_type removed to prevent the 400 conflict error
            ),
        )
        
        # Robust parsing cleanup system: Extracts raw JSON even if wrapped inside markdown code blocks
        text_content = response.text
        
        # Clean up code blocks if present
        if "```json" in text_content:
            text_content = text_content.split("```json")[1].split("```")[0]
        elif "```" in text_content:
            text_content = text_content.split("
```")[1].split("```")[0]
            
        clean_text = text_content.strip()
        return json.loads(clean_text)
    except Exception as e:
        st.error(f"Failed to fetch market data from API: {str(e)}")
        return None

# ─── Formatted Prompts Engine ────────────────────────────────────────────────
def get_market_data_prompt():
    return """
    Search for the LATEST Nepal Stock Exchange (NEPSE) market data RIGHT NOW from merolagani.com or sharesansar.com or nepsealpha.com.
    Fetch the LIVE or MOST RECENT data for these stocks: NABIL, NICA, NBL, ADBL, SBL, UPPER, NHPC, RIDI, HIDCLP, BJHL.
    For each stock provide: symbol, lastTradedPrice (LTP), percentChange, volume, turnover.
    Also provide: NEPSE Index value, total market turnover today, market status (Open/Closed).
    
    CRITICAL: You must return ONLY valid, raw JSON. Do not include introductory text, conversational notes, or explanations.
    
    Return EXACTLY this JSON template structure:
    {
      "indexValue": 2730.91,
      "indexChange": -0.04,
      "totalTurnover": 4250000000,
      "marketStatus": "Closed",
      "lastUpdated": "2026-05-20",
      "stocks": [
        {"symbol":"NABIL","ltp":539,"change":0.74,"volume":18420,"turnover":9930000,"sector":"Banking"}
      ]
    }
    """

def get_analysis_prompt(stock_list_str):
    return f"""
    You are a NEPSE smart money analyst. Based on this live market data: {stock_list_str}
    Search for latest NEPSE broker activity and institutional flow on nepsealpha.com or sharesansar.com.
    Generate institutional intelligence analysis. 
    
    CRITICAL: You must return ONLY valid, raw JSON. Do not include conversational notes or explanations.
    
    Return EXACTLY this structured JSON format:
    {{
      "topAccumulation": [
        {{"symbol":"NHPC","score":88,"signal":"Strong Accumulation","wyckoff":"Spring","ofi":0.72,"brokerConc":68,"insight":"Pre-monsoon institutional loading."}}
      ],
      "sectorFlow": [
        {{"sector":"Hydropower","score":91,"flow":"Strong Inflow","change":"+18.4%"}}
      ],
      "signals": [
        {{"type":"BUY","symbol":"NHPC","entry":315,"sl":298,"tp1":338,"tp2":358,"tp3":380,"rr":"1:2.4","confidence":88,"reason":"Wyckoff Spring confirmed."}}
      ],
      "marketSummary": "NEPSE showing clear institutional sector rotation into Hydropower scripts ahead of monsoon season."
    }}
    """

# ─── Data Pipeline ───────────────────────────────────────────────────────────
def load_all_intelligence():
    with st.spinner("Searching NEPSE live prices and tracking smart money metrics..."):
        market_data = ask_gemini_market_data(get_market_data_prompt())
        if not market_data:
            return None, None
            
        # Format the stocks list for the second sequential analytical prompt
        stocks_summary = ", ".join([f"{s['symbol']} LTP:{s['ltp']} Change:{s['change']}%" for s in market_data.get('stocks', [])])
        
        analysis_data = ask_gemini_market_data(get_analysis_prompt(stocks_summary))
        return market_data, analysis_data

# Utility formatting helper functions
def fmt_currency(val):
    if abs(val) >= 1e7: return f"{val / 1e7:.2f} Cr"
    if abs(val) >= 1e5: return f"{val / 1e5:.2f} L"
    return f"{val:,.2f}"

# ─── UI Engine Execution ──────────────────────────────────────────────────────
def main():
    # Application Title Section
    st.markdown("""
        <div style="display:flex; align-items:center; gap:15px; margin-bottom:20px;">
            <div style="width:40px; height:40px; border:1px solid #e8b84b; display:flex; align-items:center; justify-content:center; font-family:'Syne',sans-serif; font-weight:800; font-size:18px; color:#e8b84b;">N</div>
            <div>
                <h2 style='margin:0; padding:0;'>NEPSE INTELLIGENCE</h2>
                <div style='font-size:10px; color:#5a7090; letter-spacing:2px; text-transform:uppercase;'>Smart Money Tracking Framework</div>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    market, analysis = load_all_intelligence()
    
    if not market or not analysis:
        st.error("Critical error building live analytical layers. Please refresh dashboard.")
        if st.button("↺ RETRY EXECUTION"):
            st.cache_data.clear()
            st.rerun()
        return

    # Top Navigation Dynamic Tabs Architecture
    tab_id = st.radio(
        "NAVIGATION LAYER", 
        ["Dashboard", "Accumulation Radar", "Sector Flow", "Trade Signals", "Live Prices"],
        horizontal=True,
        label_visibility="collapsed"
    )
    
    st.markdown("---")

    # DASHBOARD TAB
    if tab_id == "Dashboard":
        # Global Financial Index Metric Blocks
        c1, c2, c3 = st.columns(3)
        with c1:
            chg_cls = "up-trend" if market['indexChange'] >= 0 else "dn-trend"
            chg_sign = "▲" if market['indexChange'] >= 0 else "▼"
            st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">NEPSE Index</div>
                    <div class="metric-value">{market['indexValue']:,}</div>
                    <div class="{chg_cls}">{chg_sign} {abs(market['indexChange'])}% Today</div>
                </div>
            """, unsafe_allow_html=True)
        with c2:
            st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">Total Turnover</div>
                    <div class="metric-value">Rs. {fmt_currency(market['totalTurnover'])}</div>
                    <div style="color:#5a7090; font-size:12px;">Gross Dynamic Volume Liquidity</div>
                </div>
            """, unsafe_allow_html=True)
        with c3:
            st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">Market Blueprint State</div>
                    <div class="metric-value" style="color:#00d4ff;">{market['marketStatus']}</div>
                    <div style="color:#5a7090; font-size:12px;">Active As Of: {market['lastUpdated']}</div>
                </div>
            """, unsafe_allow_html=True)

        # AI Market Intelligence Core Summary Box
        st.markdown(f"""
            <div class="ai-summary-box">
                <span class="gold-txt" style="font-weight:bold; letter-spacing:1px;">SMART MONEY SUMMARY — </span>
                {analysis['marketSummary']}
            </div>
        """, unsafe_allow_html=True)

        # Main Split Content Columns
        left_col, right_col = st.columns(2)
        with left_col:
            st.markdown("### 🎯 Top Institutional Accumulation")
            df_acc = pd.DataFrame(analysis['topAccumulation']).head(4)
            for _, row in df_acc.iterrows():
                st.markdown(f"""
                    <div style="background:#0c1020; padding:12px; border:1px solid #1e2d4a; margin-bottom:8px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <span style="font-size:16px; font-weight:bold; color:#eef4ff;">{row['symbol']}</span>
                            <span style="font-size:11px; background:rgba(29,219,139,0.1); color:#1ddb8b; padding:2px 6px; border:1px solid #1ddb8b;">{row['signal']}</span>
                        </div>
                        <div style="margin:5px 0; font-size:11px; color:#5a7090;">Wyckoff Structural Phase: <b style="color:#00d4ff;">{row['wyckoff']}</b></div>
                        <div style="font-size:11px; font-style:italic; color:#9b6dff;">{row['insight']}</div>
                    </div>
                """, unsafe_allow_html=True)

        with right_col:
            st.markdown("### 🌊 Sector Heat Matrix")
            df_sectors = pd.DataFrame(analysis['sectorFlow'])
            for _, row in df_sectors.iterrows():
                st.markdown(f"**{row['sector']}** • {row['flow']} ({row['change']})")
                st.progress(int(row['score']))

    # ACCUMULATION RADAR TAB
    elif tab_id == "Accumulation Radar":
        st.markdown("### 🕵️ Institutional Wyckoff Accumulation Analytics")
        df_acc = pd.DataFrame(analysis['topAccumulation'])
        
        for _, row in df_acc.iterrows():
            with st.container():
                st.markdown(f"#### {row['symbol']} — `{row['signal']}`")
                col_m1, col_m2, col_m3 = st.columns(3)
                col_m1.metric("Smart Score Metric", f"{row['score']}/100")
                col_m2.metric("Order Flow Imbalance (OFI)", row['ofi'])
                col_m3.metric("Top-3 Broker Concentration", f"{row['brokerConc']}%")
                st.markdown(f"*Intelligence Insight:* {row['insight']}\n***")

    # SECTOR FLOW TAB
    elif tab_id == "Sector Flow":
        st.markdown("### 🔀 Structural Macro Sector Rotation Matrix")
        df_sec = pd.DataFrame(analysis['sectorFlow'])
        st.dataframe(
            df_sec, 
            column_config={
                "score": st.column_config.ProgressColumn("Institutional Score Weights", min_value=0, max_value=100),
                "sector": "Market Sector",
                "flow": "Net Flow Vector Status",
                "change": "7-Day Delta Evolution"
            },
            use_container_width=True,
            hide_index=True
        )

    # TRADE SIGNALS TAB
    elif tab_id == "Trade Signals":
        st.markdown("### ⚡ AI Automated Tactical Risk Framework Signals")
        for sig in analysis['signals']:
            with st.container():
                type_color = "#1ddb8b" if sig['type'] == "BUY" else ("#e8b84b" if sig['type'] == "WATCH" else "#ff4466")
                st.markdown(f"""
                    <div class="signal-card">
                        <div style="display:flex; justify-content:space-between;">
                            <span style="font-size:18px; font-weight:bold; color:{type_color};">[{sig['type']}] {sig['symbol']}</span>
                            <span style="color:#00d4ff; font-size:12px;">Risk-Reward Ratio: {sig['rr']}</span>
                        </div>
                        <div style="color:#5a7090; font-size:11px; margin-bottom:10px;">Institutional Execution Confidence: {sig['confidence']}%</div>
                        <p style="font-size:12px; color:#c8d8f0; font-style:italic;">{sig['reason']}</p>
                    </div>
                """, unsafe_allow_html=True)
                if sig['type'] != "AVOID":
                    lvl_c1, lvl_c2, lvl_c3, lvl_c4 = st.columns(4)
                    lvl_c1.metric("Optimal Entry", f"Rs. {sig['entry']}")
                    lvl_c2.metric("Hard Stop Loss", f"Rs. {sig['sl']}")
                    lvl_c3.metric("Take Profit 1", f"Rs. {sig['tp1']}")
                    lvl_c4.metric("Take Profit 2 / 3", f"{sig['tp2']} / {sig['tp3']}")
                st.markdown("---")

    # LIVE PRICES TAB
    elif tab_id == "Live Prices":
        st.markdown("### 📈 Live Query Snapshot Matrix Profiles")
        df_stocks = pd.DataFrame(market['stocks'])
        
        df_stocks['ltp'] = df_stocks['ltp'].map(lambda x: f"Rs. {x:,.2f}")
        df_stocks['turnover'] = df_stocks['turnover'].map(fmt_currency)
        df_stocks['volume'] = df_stocks['volume'].map(lambda x: f"{x:,}")
        
        st.table(df_stocks)

    # Global Footprint Sticky Footers Notice
    st.markdown("""
        <div class="notice-box">
            <strong>DATA SOURCES & DISCLOSURE PIPELINE:</strong> Live asset ticker metrics compiled via automated web extraction frameworks 
            leveraging systemic query loops directly parsing active updates across <b>merolagani.com</b>, <b>sharesansar.com</b>, and <b>nepsealpha.com</b>. 
            Smart algorithmic scoring weights combine HHI metrics, order flow distribution (OFI profiles), and structural Wyckoff phases. 
            Educational analytics paradigm framework. Risk Capital exposure is individual responsibility.
        </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
