"""Testes unitários e de contrato para o código consolidado de ETL e modelagem."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config import get_project_paths
from src.etl import (
    add_bar_features,
    build_bars,
    build_taker_orders,
    clean_trades,
    fill_bar_gaps,
    validate_trades,
)
from src.modeling import (
    build_lagged_features,
    build_targets,
    daily_walk_forward_folds,
    prepare_modeling_dataset,
)


def _sample_raw_trades() -> pd.DataFrame:
    base_ms = int(pd.Timestamp("2025-02-19 00:00:00", tz="UTC").timestamp() * 1000)
    return pd.DataFrame(
        {
            "exchange": ["binance"] * 5,
            "symbol": ["BTCUSDT"] * 5,
            "trade_id": ["100", "101", "102", "103", "104"],
            "exchange_ts": [base_ms, base_ms + 100, base_ms + 100, base_ms + 3000, base_ms + 65000],
            "ingest_ts": [1964796000000] * 5,  # data futura inválida (2032)
            "price": [95000.0, 95001.0, 95002.0, 95010.0, 95005.0],
            "quantity": [0.001, 0.002, 0.003, 0.004, 0.005],
            "aggressor_side": [1, -1, -1, 1, -1],
            "raw_side": ["buy", "sell", "sell", "buy", "sell"],
        }
    )


def test_clean_and_validate_trades_contract():
    raw = _sample_raw_trades()
    cleaned = clean_trades(raw)

    assert "ingest_ts" not in cleaned.columns
    assert "exchange" not in cleaned.columns
    assert cleaned.attrs["exchange"] == "binance"
    assert cleaned.attrs["symbol"] == "BTCUSDT"
    assert list(cleaned["side"]) == ["buy", "sell", "sell", "buy", "sell"]

    report = validate_trades(cleaned)
    assert (report["passou?"] == "✅").all()


def test_build_bars_and_fill_bar_gaps_no_lookahead():
    cleaned = clean_trades(_sample_raw_trades())
    start = pd.Timestamp("2025-02-19 00:00:00", tz="UTC")
    end = pd.Timestamp("2025-02-19 00:02:00", tz="UTC")

    bars_raw = build_bars(cleaned, "1s", start=start, end=end)
    assert len(bars_raw) == 120
    # Segundo 00:00:01 e 00:00:02 não têm negócios
    assert bars_raw.iloc[1].isna().all()

    filled = fill_bar_gaps(bars_raw)
    # Segundo 00:00:01 deve herdar o close do segundo 00:00:00 (95002.0), nunca o futuro (95010.0)
    assert not filled.loc[start + pd.Timedelta(seconds=1), "has_trades"]
    assert filled.loc[start + pd.Timedelta(seconds=1), "close"] == 95002.0
    assert filled.loc[start + pd.Timedelta(seconds=1), "open"] == 95002.0
    assert filled.loc[start + pd.Timedelta(seconds=1), "volume_usd"] == 0.0

    featured = add_bar_features(filled)
    assert featured.loc[start + pd.Timedelta(seconds=1), "ofi"] == 0.0
    assert featured.loc[start + pd.Timedelta(seconds=1), "vwap"] == 95002.0


def test_build_taker_orders_merges_consecutive_same_ts_and_side():
    cleaned = clean_trades(_sample_raw_trades())
    orders = build_taker_orders(cleaned)
    # Trades 101 e 102 têm o mesmo timestamp (+100ms) e lado (sell) -> 4 ordens no total
    assert len(orders) == 4
    assert orders.iloc[1]["n_fills"] == 2
    assert np.isclose(orders.iloc[1]["quantity"], 0.005)
    assert orders.iloc[1]["book_walk_bps"] > 0


def test_build_lagged_features_strictly_causal_no_lookahead():
    idx = pd.date_range("2025-02-19", periods=200, freq="1min", tz="UTC")
    rng = np.random.default_rng(7)
    close = 95000.0 + np.cumsum(rng.normal(0, 10, size=len(idx)))
    bars = pd.DataFrame(
        {
            "open": close - 2.0,
            "high": close + 5.0,
            "low": close - 5.0,
            "close": close,
            "volume_btc": rng.uniform(1, 50, size=len(idx)),
            "volume_usd": rng.uniform(1e5, 5e6, size=len(idx)),
            "n_trades": rng.integers(100, 3000, size=len(idx)),
            "buy_volume_btc": rng.uniform(0.5, 25, size=len(idx)),
        },
        index=idx,
    )
    bars = add_bar_features(bars)

    feats_orig, _ = build_lagged_features(bars)
    # Altera drasticamente todas as barras após t = 120
    bars_perturbed = bars.copy()
    bars_perturbed.iloc[121:, bars_perturbed.columns.get_loc("close")] *= 2.0
    bars_perturbed.iloc[121:, bars_perturbed.columns.get_loc("ofi")] = -1.0
    bars_perturbed.iloc[121:, bars_perturbed.columns.get_loc("volume_usd")] *= 100.0
    feats_pert, _ = build_lagged_features(bars_perturbed)

    # Nenhuma feature até o índice 120 pode mudar com perturbações futuras
    pd.testing.assert_frame_equal(feats_orig.iloc[:121], feats_pert.iloc[:121])


def test_daily_walk_forward_folds_chronological():
    idx = pd.date_range("2025-02-19", periods=4 * 1440, freq="1min", tz="UTC")
    folds = daily_walk_forward_folds(idx, min_train_days=2)
    assert len(folds) == 2
    for test_day, train_mask, test_mask in folds:
        assert idx[train_mask].max() < test_day
        assert (idx[test_mask].floor("D") == test_day).all()


def test_prepare_modeling_dataset_shapes():
    idx = pd.date_range("2025-02-19", periods=300, freq="1min", tz="UTC")
    rng = np.random.default_rng(42)
    close = 95000.0 + np.cumsum(rng.normal(0, 15, size=len(idx)))
    bars = add_bar_features(
        pd.DataFrame(
            {
                "open": close,
                "high": close + 8.0,
                "low": close - 8.0,
                "close": close,
                "volume_btc": rng.uniform(1, 30, size=len(idx)),
                "volume_usd": rng.uniform(1e5, 3e6, size=len(idx)),
                "n_trades": rng.integers(50, 2000, size=len(idx)),
                "buy_volume_btc": rng.uniform(0.5, 15, size=len(idx)),
            },
            index=idx,
        )
    )
    feats, targets, fsets = prepare_modeling_dataset(bars)
    assert not feats.isna().any().any()
    assert not targets.isna().any().any()
    assert set(fsets["apenas_ofi"]).issubset(feats.columns)
    assert set(fsets["completo"]).issubset(feats.columns)
    assert len(feats) == len(targets)


def test_streamlit_dashboard_renders_without_errors():
    paths = get_project_paths()
    if not (paths.processed_dir / "bars_1min.parquet").exists():
        pytest.skip("Parquets processados ausentes; pule o teste do dashboard.")
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(paths.base_dir / "app" / "dashboard.py"), default_timeout=60).run()
    assert len(at.exception) == 0
    assert len(at.metric) == 5
    assert len(at.tabs) == 4

