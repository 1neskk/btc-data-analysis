"""Carregamento e agregações reutilizáveis a partir de `data/processed/`."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.config import (
    DIAS_PT,
    PERIOD_START,
    SIZE_LABELS,
    STRESS_RANGE_THRESHOLD,
    day_label,
    get_project_paths,
)


def _ensure_utc_index(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("Esperado DatetimeIndex nas barras.")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    return df


def load_bars(freq: str = "1min", base_dir: Path | str | None = None) -> pd.DataFrame:
    """Carrega `bars_1min.parquet` ou `bars_1s.parquet` de `data/processed/`."""
    paths = get_project_paths(base_dir)
    filename = "bars_1min.parquet" if freq == "1min" else "bars_1s.parquet"
    path = paths.processed_dir / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {path}. Execute o notebook do CP2 ou `python -m src.etl`."
        )
    df = pd.read_parquet(path)
    return _ensure_utc_index(df)


def load_taker_orders(
    base_dir: Path | str | None = None,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """Carrega `taker_orders.parquet` de `data/processed/`."""
    paths = get_project_paths(base_dir)
    path = paths.processed_dir / "taker_orders.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {path}. Execute o notebook do CP2 ou `python -m src.etl`."
        )
    df = pd.read_parquet(path, columns=columns)
    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def load_trades_clean(
    base_dir: Path | str | None = None,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """Carrega `trades_clean.parquet` (colunas selecionadas recomendadas para economizar RAM)."""
    paths = get_project_paths(base_dir)
    path = paths.processed_dir / "trades_clean.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {path}. Execute o notebook do CP2 ou `python -m src.etl`."
        )
    df = pd.read_parquet(path, columns=columns)
    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def compute_daily_summary(
    bars_1m: pd.DataFrame,
    stress_threshold: float = STRESS_RANGE_THRESHOLD,
) -> pd.DataFrame:
    """Resume métricas diárias e classifica cada dia em estresse, dia útil ou fim de semana."""
    day_floor = bars_1m.index.floor("D")
    daily = bars_1m.groupby(day_floor).agg(
        abertura=("open", "first"),
        maxima=("high", "max"),
        minima=("low", "min"),
        fechamento=("close", "last"),
        volume_usd=("volume_usd", "sum"),
        negocios=("n_trades", "sum"),
        compra_btc=("buy_volume_btc", "sum"),
        volume_btc=("volume_btc", "sum"),
    )
    daily["retorno_pct"] = (daily["fechamento"] / daily["abertura"] - 1.0) * 100.0
    daily["amplitude_pct"] = (daily["maxima"] / daily["minima"] - 1.0) * 100.0
    daily["vol_realizada_pct"] = (
        bars_1m["log_return"].pow(2).groupby(day_floor).sum().pow(0.5) * 100.0
    )
    daily["compra_agressora_pct"] = daily["compra_btc"] / daily["volume_btc"] * 100.0
    daily["saldo_fluxo_pct"] = (
        (daily["compra_btc"] * 2.0 - daily["volume_btc"]) / daily["volume_btc"] * 100.0
    )
    daily["tipo"] = np.where(
        daily["amplitude_pct"] > stress_threshold * 100.0,
        "estresse",
        np.where(daily.index.day_of_week >= 5, "fim de semana", "dia útil"),
    )
    daily["day_label"] = [day_label(d) for d in daily.index]
    daily["date_str"] = [f"{d:%Y-%m-%d}" for d in daily.index]
    return daily


def compute_hourly_profile(
    bars_1m: pd.DataFrame,
    tz_offset_hours: int = 0,
) -> pd.DataFrame:
    """Agrega mediana e média horárias de liquidez e volatilidade (UTC ou BRT)."""
    shifted_hours = (bars_1m.index.hour + tz_offset_hours) % 24
    by_hour = bars_1m.groupby(shifted_hours).agg(
        volume_usd_med=("volume_usd", "median"),
        volume_usd_mean=("volume_usd", "mean"),
        negocios_med=("n_trades", "median"),
        abs_ret_bps_med=("abs_return_bps", "median"),
        range_bps_med=("range_bps", "median"),
        range_bps_mean=("range_bps", "mean"),
    )
    by_hour.index.name = "hora"
    return by_hour


def compute_trade_size_summary(
    base_dir: Path | str | None = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    """Calcula (e opcionalmente armazena em cache) a distribuição por dia, hora UTC e `size_bucket`."""
    paths = get_project_paths(base_dir)
    cache_path = paths.processed_dir / "trade_size_hourly.parquet"
    if use_cache and cache_path.exists():
        grouped = pd.read_parquet(cache_path)
    else:
        trades = load_trades_clean(base_dir, columns=["ts", "notional_usd", "size_bucket"])
        trades["date_str"] = trades["ts"].dt.strftime("%Y-%m-%d")
        trades["hour_utc"] = trades["ts"].dt.hour
        grouped = (
            trades.groupby(["date_str", "hour_utc", "size_bucket"], observed=True)
            .agg(negocios=("notional_usd", "size"), volume_usd=("notional_usd", "sum"))
            .reset_index()
        )
        if use_cache:
            paths.ensure_dirs()
            grouped.to_parquet(cache_path, compression="zstd", index=False)

    grouped["size_bucket"] = pd.Categorical(
        grouped["size_bucket"], categories=SIZE_LABELS, ordered=True
    )
    return grouped


def compute_lag_correlations(
    bars: pd.DataFrame,
    max_lag: int = 10,
) -> pd.DataFrame:
    """Calcula correlação de Pearson e Spearman entre `ofi_t` e `log_return_{t+k}`."""
    rows = []
    for k in range(0, max_lag + 1):
        shifted = bars["log_return"].shift(-k)
        rows.append(
            {
                "lag": k,
                "pearson": float(bars["ofi"].corr(shifted, method="pearson")),
                "spearman": float(bars["ofi"].corr(shifted, method="spearman")),
            }
        )
    return pd.DataFrame(rows).set_index("lag")


def attach_day_type(
    df: pd.DataFrame,
    daily: pd.DataFrame,
    ts_col: str | None = "ts",
) -> pd.Series:
    """Mapeia cada registro para o tipo de dia ('estresse', 'dia útil', 'fim de semana')."""
    ts_vals = df[ts_col] if ts_col is not None else df.index
    day_keys = pd.to_datetime(ts_vals, utc=True).dt.floor("D") if ts_col is not None else ts_vals.floor("D")
    type_map = daily["tipo"].to_dict()
    return day_keys.map(type_map)
