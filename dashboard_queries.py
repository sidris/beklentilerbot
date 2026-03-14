import pandas as pd


def load_forecasts(supabase):
    res = (
        supabase.table("forecast_entries")
        .select("*")
        .order("updated_at", desc=False)
        .execute()
    )

    df = pd.DataFrame(res.data or [])
    if not df.empty:
        df["target_period"] = pd.to_datetime(df["target_period"])
        df["created_at"] = pd.to_datetime(df["created_at"])
        df["updated_at"] = pd.to_datetime(df["updated_at"])
    return df


def latest_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    latest = (
        df.sort_values("updated_at")
          .groupby(["entry_type", "source_name", "forecast_type", "target_period"], as_index=False)
          .tail(1)
    )
    return latest


def consensus_by_period(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    out = (
        df.groupby(["forecast_type", "target_period"], as_index=False)["value"]
          .mean()
          .rename(columns={"value": "consensus"})
    )
    return out
