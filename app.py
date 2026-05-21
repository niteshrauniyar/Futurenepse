import datetime
import pandas as pd
import requests

# Base URL for the NEPSE Unofficial API backend
# (Can be adjusted to your local or self-hosted instance if needed)
BASE_URL = "https://nepseapi.surajrimal07.me/api"  


def get_live_floorsheet(symbol: str, max_pages: int = 5) -> pd.DataFrame:
    """Fetches real-time floorsheet (completed trades) data for a specific scrip."""
    all_trades = []

    for page in range(1, max_pages + 1):
        try:
            url = f"{BASE_URL}/get_floorsheet"
            params = {"symbol": symbol.upper(), "page": page, "limit": 100}
            response = requests.get(url, params=params, timeout=10)

            if response.status_code != 200:
                break

            data = response.json()
            # Handle paginated wrapper if present, or assume raw list
            trades = data.get("items", data) if isinstance(data, dict) else data

            if not trades:
                break

            all_trades.extend(trades)
        except Exception as e:
            print(f"Error fetching floorsheet page {page}: {e}")
            break

    if not all_trades:
        return pd.DataFrame()

    df = pd.DataFrame(all_trades)
    # Ensure correct data types for mathematical computations
    if "rate" in df.columns:
        df["rate"] = pd.to_numeric(df["rate"])
    if "quantity" in df.columns:
        df["quantity"] = pd.to_numeric(df["quantity"])
    if "amount" in df.columns:
        df["amount"] = pd.to_numeric(df["amount"])

    return df


def get_historical_metrics(symbol: str, days: int = 30) -> pd.DataFrame:
    """Fetches historical data to calculate Amihud Illiquidity over a historical lookback window.

    Amihud Illiquidity = |Return| / (Price * Volume)
    High values mean a small volume moves the price drastically (illiquid).
    Low values mean huge volume is absorbed with minor price changes (Institutional Accumulation/Distribution).
    """
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=days)

    url = f"{BASE_URL}/get_historical_data"
    params = {
        "symbol": symbol.upper(),
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            print(f"Failed to fetch historical data for {symbol}")
            return pd.DataFrame()

        data = response.json()
        df = pd.DataFrame(data)

        if df.empty:
            return df

        # Map API keys to computational names (adjust based on raw payload structures)
        df["close"] = pd.to_numeric(df["closePrice"] if "closePrice" in df.columns else df["close"])
        df["volume"] = pd.to_numeric(df["totalTradedQuantity"] if "totalTradedQuantity" in df.columns else df["volume"])
        df["turnover"] = pd.to_numeric(df["totalTurnover"] if "totalTurnover" in df.columns else df["turnover"])

        # Calculate daily absolute returns
        df["pct_return"] = df["close"].pct_change().abs()

        # Calculate Amihud Illiquidity Ratio
        # Avoid division by zero by protecting zero volume days
        df["amihud_illiquidity"] = df.apply(
            lambda row: row["pct_return"] / row["turnover"] if row["turnover"] > 0 else 0,
            axis=1,
        )

        return df
    except Exception as e:
        print(f"Error calculating historical metrics: {e}")
        return pd.DataFrame()


def analyze_big_players(symbol: str):
    """Integrates real-time order blocks and historic liquidity trends to trace composite order flow."""
    print(f"========== ANALYZING LIVE ORDER FLOW: {symbol.upper()} ==========")

    # 1. Fetch live transaction data
    floorsheet_df = get_live_floorsheet(symbol)

    if floorsheet_df.empty:
        print("[-] No live transaction data found for this scrip today.")
    else:
        # Sort out transaction sizes to locate large market footprints
        large_trades = floorsheet_df[
            floorsheet_df["amount"] > floorsheet_df["amount"].median() * 5
        ]
        print(f"\n[+] Total Live Trades Captured: {len(floorsheet_df)}")
        print(f"[+] Large Blocks Detected (>5x median size): {len(large_trades)}")

        if not large_trades.empty:
            print("\n--- Recent Large Footprints ---")
            print(
                large_trades[["buyerBroker", "sellerBroker", "quantity", "rate", "amount"]]
                .head(10)
                .to_string(index=False)
            )

    # 2. Fetch market impact and institutional absorption data
    hist_df = get_historical_metrics(symbol)

    if not hist_df.empty:
        avg_illiquidity = hist_df["amihud_illiquidity"].mean()
        recent_illiquidity = hist_df["amihud_illiquidity"].iloc[-1]

        print("\n--- Market Impact & Liquidity Characteristics ---")
        print(f"Historical Avg Illiquidity Ratio: {avg_illiquidity:.12f}")
        print(f"Latest Session Illiquidity Ratio: {recent_illiquidity:.12f}")

        if recent_illiquidity < avg_illiquidity * 0.5 and hist_df["volume"].iloc[-1] > hist_df["volume"].mean():
            print(
                "\n[!] ALERT: High volume accompanied by unusually low price impact detected."
            )
            print(
                "    This behavior highly correlates with Institutional Absorption/Accumulation zones."
            )
        else:
            print("\n[+] Order flow distribution matches standard liquidity baseline ranges.")


if __name__ == "__main__":
    # Test script with a major NEPSE symbol (e.g., NICA, HDL, UPPER)
    # Ensure your endpoint server is up or replace with your active base API address.
    target_scrip = "NICA"
    analyze_big_players(target_scrip)
