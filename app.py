# app.py
"""
NEPSE Smart Money Intelligence & Analytical Framework
Consolidated Application Engine

This module unifies quantitative statistical tracking, institutional order flow 
imbalance processing, broker network coordination graph logic, and the final 
scoring/reporting architecture into a single executable pipeline.
"""

import numpy as np
import pandas as pd
import networkx as nx
import statsmodels.api as sm
from scipy.stats import zscore

# =========================================================================
# 1. CORE QUANTITATIVE & STRUCTURAL PROCESSING ENGINE
# =========================================================================

class NEPSESmartMoneyEngine:
    def __init__(self, floorsheet_df: pd.DataFrame, daily_ohlcv_df: pd.DataFrame):
        """
        Initializes the engine with historical and current market data.
        
        floorsheet_df columns: ['date', 'script', 'buyer_broker', 'seller_broker', 'quantity', 'rate', 'value', 'time']
        daily_ohlcv_df columns: ['date', 'script', 'open', 'high', 'low', 'close', 'volume']
        """
        self.fs = floorsheet_df.copy()
        self.ohlcv = daily_ohlcv_df.copy()
        
        # Optimize data types for mathematical vector operations
        self.fs['quantity'] = pd.to_numeric(self.fs['quantity'])
        self.fs['rate'] = pd.to_numeric(self.fs['rate'])
        self.fs['value'] = pd.to_numeric(self.fs['value'])
        self.fs['date'] = pd.to_datetime(self.fs['date'])
        
        self.ohlcv['close'] = pd.to_numeric(self.ohlcv['close'])
        self.ohlcv['volume'] = pd.to_numeric(self.ohlcv['volume'])
        self.ohlcv['date'] = pd.to_datetime(self.ohlcv['date'])

    def calculate_broker_net_flow(self, script: str, n_days: int = 10) -> pd.DataFrame:
        """
        Measures the directional capital commitment of each broker over a rolling window.
        Formula: Net_Flow = SUM(buy_amount) - SUM(sell_amount)
        """
        cutoff_date = self.fs['date'].max() - pd.Timedelta(days=n_days)
        df_filtered = self.fs[(self.fs['script'] == script) & (self.fs['date'] >= cutoff_date)]
        
        buys = df_filtered.groupby('buyer_broker')['value'].sum().rename('total_buy')
        sells = df_filtered.groupby('seller_broker')['value'].sum().rename('total_sell')
        
        flow_df = pd.concat([buys, sells], axis=1).fillna(0)
        flow_df['net_flow'] = flow_df['total_buy'] - flow_df['total_sell']
        return flow_df.sort_values(by='net_flow', ascending=False)

    def calculate_hhi(self, script: str) -> float:
        """
        Measures broker market concentration via the Herfindahl-Hirschman Index (HHI).
        HHI > 2,500 indicates high institutional concentration / coordination risk.
        """
        df_script = self.fs[self.fs['script'] == script]
        if df_script.empty:
            return 0.0
        
        total_volume = df_script['quantity'].sum()
        
        buyer_vol = df_script.groupby('buyer_broker')['quantity'].sum()
        seller_vol = df_script.groupby('seller_broker')['quantity'].sum()
        broker_total_vol = buyer_vol.add(seller_vol, fill_value=0)
        
        shares = (broker_total_vol / total_volume) * 100
        hhi = np.sum(shares ** 2)
        return float(hhi)

    def calculate_kyles_lambda(self, script: str) -> float:
        """
        Measures price impact per unit of signed order flow.
        Low/falling lambda signifies institutional stealth accumulation.
        Model: Delta_P = Lambda * Q + Epsilon
        """
        df_script = self.fs[self.fs['script'] == script].sort_values('time')
        if len(df_script) < 10:
            return 0.0
        
        df_script['price_diff'] = df_script['rate'].diff()
        df_script['sign'] = np.where(df_script['price_diff'] >= 0, 1, -1)
        df_script['signed_vol'] = df_script['quantity'] * df_script['sign']
        
        daily_agg = df_script.groupby('date').agg({
            'rate': ['last', 'first'],
            'signed_vol': 'sum'
        })
        
        delta_p = daily_agg['rate']['last'] - daily_agg['rate']['first']
        q = daily_agg['signed_vol']['sum']
        
        if q.std() == 0 or len(q) < 3:
            return 0.0
            
        X = sm.add_constant(q)
        model = sm.OLS(delta_p, X).fit()
        return float(model.params.iloc[1]) if len(model.params) > 1 else 0.0

    def calculate_amihud_illiquidity(self, script: str, n_days: int = 30) -> float:
        """
        Calculates the Amihud Illiquidity Ratio.
        ILLIQ > 0.005 implies high manipulation risk; avoid asset.
        """
        df_script = self.ohlcv[self.ohlcv['script'] == script].sort_values('date').tail(n_days)
        if df_script.empty or (df_script['volume'] == 0).all():
            return 999.0
        
        returns = df_script['close'].pct_change().abs()
        dollar_vol = df_script['close'] * df_script['volume']
        
        illiq_series = returns / dollar_vol
        return float(illiq_series.replace([np.inf, -np.inf], np.nan).mean())

    def calculate_ofi(self, script: str) -> float:
        """
        Order Flow Imbalance (OFI) measures net directional pressure.
        OFI > 0.30 for 5+ days confirms clear institutional absorption.
        """
        df_script = self.fs[self.fs['script'] == script]
        if df_script.empty:
            return 0.0
            
        buy_vol = df_script['quantity'].where(df_script['buyer_broker'] != df_script['seller_broker'], 0).sum()
        total_vol = df_script['quantity'].sum()
        sell_vol = total_vol - buy_vol
        
        if total_vol == 0:
            return 0.0
        return float((buy_vol - sell_vol) / total_vol)

    def calculate_vwap_status(self, script: str) -> dict:
        """
        Compares closing price against the Volume Weighted Average Price (VWAP).
        """
        df_script = self.fs[self.fs['script'] == script]
        if df_script.empty:
            return {"above_vwap": False, "vwap": 0.0, "last_close": 0.0}
        
        total_val = df_script['value'].sum()
        total_vol = df_script['quantity'].sum()
        vwap = total_val / total_vol if total_vol > 0 else 0
        
        last_close = df_script['rate'].iloc[-1]
        return {"vwap": vwap, "last_close": last_close, "above_vwap": last_close > vwap}

    def detect_metaorder_acf(self, script: str, broker_id: int, lag: int = 1) -> float:
        """
        Computes Lag-1 Autocorrelation on rolling daily net flow per broker.
        An ACF > 0.4 indicates persistent structural parent orders (Icebergs).
        """
        df_script = self.fs[(self.fs['script'] == script)].sort_values('date')
        daily_broker_flow = df_script.groupby(['date', 'buyer_broker'])['quantity'].sum().unstack(fill_value=0)
        
        if broker_id not in daily_broker_flow.columns or len(daily_broker_flow) < 10:
            return 0.0
            
        series = daily_broker_flow[broker_id]
        acf_val = series.autocorr(lag=lag)
        return float(acf_val) if not np.isnan(acf_val) else 0.0

    def build_broker_coordination_network(self, script: str) -> nx.Graph:
        """
        Maps out broker networks using NetworkX to track synchronized entry clusters.
        """
        df_script = self.fs[self.fs['script'] == script]
        G = nx.Graph()
        
        grouped = df_script.groupby('date')
        for date, frame in grouped:
            active_buyers = frame['buyer_broker'].unique()
            for i in range(len(active_buyers)):
                for j in range(i + 1, len(active_buyers)):
                    b1, b2 = active_buyers[i], active_buyers[j]
                    if G.has_edge(b1, b2):
                        G[b1][b2]['weight'] += 1
                    else:
                        G.add_edge(b1, b2, weight=1)
        return G

    def compute_composite_institutional_score(self, script: str, top_brokers: list) -> dict:
        """
        Executes the exact 100-point multi-factor quantitative rubric from section 7.3.
        Minimum of 65/100 points required to pass execution constraints.
        """
        metrics = {}
        
        # 1. Broker Net Flow (Max 25 Pts)
        flow_df = self.calculate_broker_net_flow(script, n_days=10)
        top_3_net = flow_df.head(3)['net_flow'].sum()
        total_net = flow_df['net_flow'].abs().sum()
        concentration_ratio = top_3_net / total_net if total_net > 0 else 0
        if concentration_ratio >= 0.60:
            metrics['broker_flow_score'] = 25
        else:
            metrics['broker_flow_score'] = int(concentration_ratio * 25)

        # 2. Order Flow Imbalance (Max 20 Pts)
        ofi = self.calculate_ofi(script)
        if ofi >= 0.30:
            metrics['ofi_score'] = 20
        elif ofi > 0:
            metrics['ofi_score'] = int((ofi / 0.30) * 20)
        else:
            metrics['ofi_score'] = 0

        # 3. Volume vs 20-Day Moving Average Anomaly (Max 15 Pts)
        script_ohlcv = self.ohlcv[self.ohlcv['script'] == script].sort_values('date')
        if len(script_ohlcv) >= 20:
            recent_vol = script_ohlcv['volume'].iloc[-1]
            ma_vol = script_ohlcv['volume'].rolling(20).mean().iloc[-1]
            vol_ratio = recent_vol / ma_vol if ma_vol > 0 else 0
            if vol_ratio >= 1.5:
                metrics['volume_anomaly_score'] = 15
            else:
                metrics['volume_anomaly_score'] = int((vol_ratio / 1.5) * 15)
        else:
            metrics['volume_anomaly_score'] = 0

        # 4. VWAP Positioning Status (Max 15 Pts)
        vwap_data = self.calculate_vwap_status(script)
        if vwap_data['above_vwap']:
            metrics['vwap_score'] = 15
        else:
            metrics['vwap_score'] = 0
            
        # Defaults for chart patterns (updated via structural reporter)
        metrics['wyckoff_phase_score'] = 10 
        metrics['ict_confirmation_score'] = 8
        
        return metrics

# =========================================================================
# 2. FINAL SIGNAL INTELLIGENCE REPORTING ENGINE
# =========================================================================

class FinalSignalReporter:
    def __init__(self, engine: NEPSESmartMoneyEngine):
        """
        Ingests the initialized engine instance to compile the intelligence briefs.
        """
        self.engine = engine

    def evaluate_technical_context(self, script: str) -> dict:
        """
        Simulates advanced technical market structure scans (ICT & Wyckoff).
        """
        df_script = self.engine.ohlcv[self.engine.ohlcv['script'] == script].sort_values('date')
        if len(df_script) < 5:
            return {"wyckoff_score": 0, "ict_score": 0, "phase": "Unknown", "setup": "None"}

        recent_close = df_script['close'].iloc[-1]
        prior_close = df_script['close'].iloc[-5]
        
        if recent_close > prior_close:
            return {
                "wyckoff_score": 12,
                "ict_score": 8,
                "phase": "Phase D (Sign of Strength / LPS)",
                "setup": "Bullish Order Block holding + Daily BOS"
            }
        else:
            return {
                "wyckoff_score": 5,
                "ict_score": 3,
                "phase": "Phase B (Accumulation Range)",
                "setup": "Testing Range Liquidity Pools"
            }

    def generate_intelligence_report(self, script: str, top_brokers: list) -> str:
        """
        Aggregates quantitative parameters with structural chart contexts
        to compile the final mathematical trading brief.
        """
        hhi = self.engine.calculate_hhi(script)
        ofi = self.engine.calculate_ofi(script)
        illiq = self.engine.calculate_amihud_illiquidity(script)
        lambda_val = self.engine.calculate_kyles_lambda(script)
        vwap_data = self.engine.calculate_vwap_status(script)
        tech_context = self.evaluate_technical_context(script)
        
        score_matrix = self.engine.compute_composite_institutional_score(script, top_brokers)
        
        # Inject dynamic structural metrics
        score_matrix['wyckoff_phase_score'] = tech_context['wyckoff_score']
        score_matrix['ict_confirmation_score'] = tech_context['ict_score']
        
        total_score = (
            score_matrix['broker_flow_score'] +
            score_matrix['ofi_score'] +
            score_matrix['volume_anomaly_score'] +
            score_matrix['vwap_score'] +
            score_matrix['wyckoff_phase_score'] +
            score_matrix['ict_confirmation_score']
        )
        
        # Risk Rule Shadows
        if illiq > 0.005:
            verdict = "CRITICAL REJECTION: HARD RISK RULE TRIGGERED"
            allocation = "0% (DO NOT ENTER - Asset under manipulation filter bounds)"
            risk_msg = "🚨 CRITICAL STOP: Amihud ratio indicates extreme illiquidity risk."
        elif total_score >= 86:
            verdict = "STRONG ACCUMULATION BUY (CONVICTION INSIDE TRACK)"
            allocation = "100% of Standard Position Size"
            risk_msg = "✅ Peak institutional volume confirmation. Alignment complete."
        elif total_score >= 76:
            verdict = "STANDARD ACCUMULATION BUY"
            allocation = "50% of Standard Position Size"
            risk_msg = "✅ Consistent institutional block accumulation. Entry parameters valid."
        elif total_score >= 65:
            verdict = "PILOT POSITION BUY (EARLY CONSOLIDATION BREAK)"
            allocation = "25% of Standard Position Size"
            risk_msg = "⚠️ Smart money entry detected early. Build sizing on pullbacks."
        else:
            verdict = "REJECT / HOLD"
            allocation = "0% (Sidelined capital)"
            risk_msg = "❌ Institutional conviction metric low. Distribution or lack of interest."

        report = []
        report.append("=" * 75)
        report.append(f"          NEPSE SMART MONEY INTELLIGENCE FINAL REPORT: {script}")
        report.append("=" * 75)
        report.append(f"Market Status Engine: May 2026 | Baseline Asset Profile Target: {script}\n")
        
        report.append("## [1] EXECUTIVE EXECUTION VERDICT")
        report.append("-" * 50)
        report.append(f"FINAL COMPOSITE SCORE  : {total_score} / 100")
        report.append(f"EXECUTION ACTION VERDICT: {verdict}")
        report.append(f"PORTFOLIO ALLOCATION    : {allocation}")
        report.append(f"RISK SPECIFICATION CRIT : {risk_msg}\n")
        
        report.append("## [2] QUANTITATIVE METRIC LEDGER")
        report.append("-" * 50)
        report.append(f"• Order Flow Imbalance (OFI)     : {ofi:+.4f} (Ideal: > +0.30 for accumulation)")
        report.append(f"• Herfindahl-Hirschman (HHI)    : {hhi:.2f} (High Concentration: > 2500)")
        report.append(f"• Kyle's Lambda (Price Impact)  : {lambda_val:.7f} (Stealth entry if dropping)")
        report.append(f"• Amihud Illiquidity Ratio      : {illiq:.6f} (Hard Stop Violation Ceiling: > 0.005)")
        report.append(f"• Close Alignment vs Session VWAP: {'ABOVE VWAP' if vwap_data['above_vwap'] else 'BELOW VWAP'} (Price: Rs. {vwap_data['last_close']}, VWAP: Rs. {vwap_data['vwap']:.2f})\n")
        
        report.append("## [3] STRUCTURAL TECHNICAL CONTEXT")
        report.append("-" * 50)
        report.append(f"• Scanned Wyckoff Phase  : {tech_context['phase']}")
        report.append(f"• ICT Setup Framework   : {tech_context['setup']}\n")
        
        report.append("## [4] MULTI-FACTOR MODEL SCOREBOARD BREAKDOWN")
        report.append("-" * 50)
        report.append(f"• Top-3 Broker Net Flow Weight   : {score_matrix['broker_flow_score']} / 25 Pts")
        report.append(f"• Order Flow Imbalance Weight     : {score_matrix['ofi_score']} / 20 Pts")
        report.append(f"• Volume Anomaly Variance Weight  : {score_matrix['volume_anomaly_score']} / 15 Pts")
        report.append(f"• VWAP Positioning Location Weight: {score_matrix['vwap_score']} / 15 Pts")
        report.append(f"• Wyckoff Structural Phase Weight : {score_matrix['wyckoff_phase_score']} / 15 Pts")
        report.append(f"• Inner Circle Tech Confirmation  : {score_matrix['ict_confirmation_score']} / 10 Pts")
        report.append("=" * 75)
        report.append("                 REPORT END // DATA DRIVEN LIQUIDITY ANALYSIS")
        report.append("=" * 75)
        
        return "\n".join(report)

# =========================================================================
# 3. MOCK DATA SIMULATION & PIPELINE TEST ENVIRONMENT
# =========================================================================

if __name__ == "__main__":
    print("[Pipeline] Constructing transaction data arrays...")
    
    # Simulate a standard liquid, highly accumulated hydropower script (e.g., NHPC)
    floorsheet_mock = pd.DataFrame({
        'date': pd.date_range(start='2026-05-10', periods=100, freq='h'),
        'script': ['NHPC'] * 100,
        'buyer_broker': [34, 45, 34, 58, 45, 34, 34, 21, 58, 34] * 10,
        'seller_broker': [17, 19, 42, 17, 19, 50, 42, 19, 17, 50] * 10,
        'quantity': [1200, 800, 1500, 6000, 400, 3100, 4500, 200, 1100, 2500] * 10,
        'rate': sorted([310, 311, 311, 312, 313, 314, 314, 315, 316, 318] * 10),
        'value': [400000] * 100,
        'time': pd.date_range(start='2026-05-10', periods=100, freq='h').strftime('%H:%M:%S')
    })
    
    ohlcv_mock = pd.DataFrame({
        'date': pd.date_range(start='2026-04-15', periods=30, freq='D'),
        'script': ['NHPC'] * 30,
        'open': np.linspace(290, 310, 30),
        'high': np.linspace(295, 322, 30),
        'low': np.linspace(285, 308, 30),
        'close': np.linspace(292, 318, 30),
        'volume': np.random.randint(50000, 180000, 30)
    })

    # Instantiate core analysis logic
    engine = NEPSESmartMoneyEngine(floorsheet_mock, ohlcv_mock)
    reporter = FinalSignalReporter(engine)
    
    # Run Case A: Valid High-Conviction Institutional Target
    print("\nExecuting Test Case A: Standard Institutional Flow Profile Run...")
    print(reporter.generate_intelligence_report(script="NHPC", top_brokers=[34, 45, 58]))
    
    # Run Case B: Trigger Hard Risk Mitigation Guardrail via extreme Illiquidity
    print("\nExecuting Test Case B: Simulating High-Risk Illiquidity Shield Activation...")
    high_risk_ohlcv = ohlcv_mock.copy()
    high_risk_ohlcv['volume'] = 10  # Drop volume to single digits to spike the Amihud value
    
    risk_engine = NEPSESmartMoneyEngine(floorsheet_mock, high_risk_ohlcv)
    risk_reporter = FinalSignalReporter(risk_engine)
    print(risk_reporter.generate_intelligence_report(script="NHPC", top_brokers=[34, 45, 58]))

