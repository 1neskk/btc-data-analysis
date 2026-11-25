"""Funções reutilizáveis de extração, transformação, validação e agregação (ETL).

Extraídas e consolidadas a partir do notebook do Checkpoint 2
(`notebooks/A3_CP2_auditoria_etl_eda.ipynb`).
"""

from __future__ import annotations

import gc
import hashlib
import shutil
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa

from src.config import (
    DATA_URL,
    DATASET_PUBLISHED_AT,
    EXPECTED_SHA256,
    FILE_NAME,
    PERIOD_END_DECLARED,
    PERIOD_START,
    SIZE_BINS,
    SIZE_LABELS,
    get_project_paths,
)


def sha256_of(path: Path | str, chunk_size: int = 1 << 20) -> str:
    """Calcula o digest SHA-256 de um arquivo em blocos para manter baixo uso de memória."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def download_file(
    url: str,
    dest: Path | str,
    expected_sha256: str | None = None,
    timeout: int = 300,
) -> Path:
    """Baixa `url` para `dest` (se ainda não existir) e valida o SHA-256 quando informado."""
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if not dest_path.exists():
        tmp_path = dest_path.with_name(dest_path.name + ".part")
        with urllib.request.urlopen(url, timeout=timeout) as resp, open(tmp_path, "wb") as out:
            shutil.copyfileobj(resp, out)
        tmp_path.replace(dest_path)

    if expected_sha256 is not None:
        digest = sha256_of(dest_path)
        if digest != expected_sha256:
            dest_path.unlink(missing_ok=True)
            raise ValueError(
                f"SHA-256 divergente em {dest_path.name}: {digest} != {expected_sha256}"
            )
    return dest_path


def clean_trades(
    df_raw: pd.DataFrame,
    published_at: pd.Timestamp = DATASET_PUBLISHED_AT,
    in_place: bool = False,
) -> pd.DataFrame:
    """Aplica o pipeline de limpeza do CP2 aos negócios brutos.

    Etapas:
      1. Adequação de tipos (`trade_id` -> int64, `exchange_ts` -> `ts` UTC, `aggressor_side` -> `side` categórica).
      2. Invalidação de `ingest_ts` fora de `[ts, published_at]` e remoção da coluna se 100% inválida.
      3. Preservação de `exchange` e `symbol` em `attrs` e remoção de colunas constantes/redundantes.
      4. Deduplicação idempotente pela chave `trade_id` (mantendo duplicatas aparentes de execuções parciais).
      5. Engenharia de `notional_usd` e `size_bucket`.
    """
    trades = df_raw if in_place else df_raw.copy()

    if not trades["aggressor_side"].isin([-1, 1]).all():
        raise ValueError("Coluna aggressor_side contém valores fora de {-1, +1}.")
    if (~trades["trade_id"].astype(str).str.fullmatch(r"\d+")).any():
        raise ValueError("Coluna trade_id contém valores não numéricos.")

    trades["trade_id"] = trades["trade_id"].astype("int64")
    trades["exchange_ts"] = pd.to_datetime(trades["exchange_ts"], unit="ms", utc=True)
    trades = trades.rename(columns={"exchange_ts": "ts"})
    trades["side"] = pd.Categorical.from_codes(
        trades["aggressor_side"].eq(-1).astype("int8"),
        categories=["buy", "sell"],
    )

    if "ingest_ts" in trades.columns:
        ingest = pd.to_datetime(trades["ingest_ts"], unit="ms", utc=True)
        is_valid = ingest.between(trades["ts"], published_at)
        trades["ingest_ts"] = ingest.where(is_valid)
        if trades["ingest_ts"].isna().all():
            trades = trades.drop(columns="ingest_ts")

    attrs_meta: dict[str, str] = {"fonte": DATA_URL, "sha256": EXPECTED_SHA256}
    for const_col in ("exchange", "symbol"):
        if const_col in trades.columns:
            attrs_meta[const_col] = str(trades[const_col].iloc[0])

    drop_cols = [c for c in ("exchange", "symbol", "raw_side", "aggressor_side") if c in trades.columns]
    trades = trades.drop(columns=drop_cols)
    trades.attrs.update(attrs_meta)

    trades = (
        trades.drop_duplicates(subset="trade_id", keep="first")
        .sort_values("trade_id")
        .reset_index(drop=True)
    )

    trades["notional_usd"] = trades["price"] * trades["quantity"]
    trades["size_bucket"] = pd.cut(
        trades["notional_usd"],
        bins=SIZE_BINS,
        labels=SIZE_LABELS,
        right=False,
    )
    return trades


def validate_trades(
    df: pd.DataFrame,
    period_start: pd.Timestamp = PERIOD_START,
    period_end: pd.Timestamp = PERIOD_END_DECLARED,
) -> pd.DataFrame:
    """Valida o contrato de qualidade pós-limpeza da tabela de negócios.

    Lança `AssertionError` caso qualquer invariante seja violada.
    """
    checks = {
        "sem nulos": bool(df.notna().all().all()),
        "trade_id único": bool(df["trade_id"].is_unique),
        "trade_id contíguo (sem buracos)": bool((df["trade_id"].diff().iloc[1:] == 1).all())
        if len(df) > 1
        else True,
        "ts em ordem cronológica": bool(df["ts"].is_monotonic_increasing),
        "ts dentro de [19/02, 26/02) UTC": bool(
            df["ts"].between(period_start, period_end, inclusive="left").all()
        ),
        "price > 0": bool((df["price"] > 0).all()),
        "quantity > 0": bool((df["quantity"] > 0).all()),
        "side ∈ {buy, sell}": bool(df["side"].isin(["buy", "sell"]).all()),
        "notional_usd = price × quantity": bool(
            np.allclose(df["notional_usd"], df["price"] * df["quantity"])
        ),
        "tipos esperados": (
            str(df["trade_id"].dtype) == "int64"
            and pd.api.types.is_datetime64_any_dtype(df["ts"])
            and isinstance(df["side"].dtype, pd.CategoricalDtype)
        ),
    }
    report = pd.Series(checks, name="passou?")
    assert report.all(), f"Contrato violado: {report[~report].index.tolist()}"
    return report.map({True: "✅", False: "❌"}).to_frame()


def build_bars(
    df: pd.DataFrame,
    freq: str,
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Agrega negócios em barras OHLCV na frequência `freq` sobre uma grade temporal contínua.

    Intervalos sem negócio aparecem com `NaN` em todas as colunas até o tratamento
    por `fill_bar_gaps`.
    """
    if df.empty:
        raise ValueError("DataFrame de negócios vazio; não é possível construir barras.")

    key = df["ts"].dt.floor(freq).rename("ts")
    bars = df.groupby(key).agg(
        open=("price", "first"),
        high=("price", "max"),
        low=("price", "min"),
        close=("price", "last"),
        volume_btc=("quantity", "sum"),
        volume_usd=("notional_usd", "sum"),
        n_trades=("price", "size"),
    )
    bars["buy_volume_btc"] = df["quantity"].where(df["side"] == "buy", 0.0).groupby(key).sum()

    grid_start = start if start is not None else df["ts"].min().floor("D")
    if end is not None:
        grid_end = end
    else:
        ts_max = df["ts"].max()
        ceil_day = ts_max.ceil("D")
        grid_end = ceil_day + pd.Timedelta(days=1) if ceil_day == ts_max else ceil_day

    full_grid = pd.date_range(grid_start, grid_end, freq=freq, inclusive="left", name="ts")
    return bars.reindex(full_grid)


def fill_bar_gaps(bars: pd.DataFrame) -> pd.DataFrame:
    """Preenche lacunas estruturais (intervalos sem negócio) sem viés de antecipação (look-ahead).

    Regras:
      - `has_trades`: preserva a flag booleana indicando se houve negócio no intervalo;
      - `volume_*`, `n_trades`: preenchidos com 0;
      - `close`: preenchido por `ffill()` (último preço executado antes da lacuna);
      - `open`, `high`, `low`: iguais ao `close` preenchido (barra plana).
    """
    filled = bars.copy()
    filled["has_trades"] = filled["n_trades"].notna()
    for col in ("volume_btc", "volume_usd", "n_trades", "buy_volume_btc"):
        filled[col] = filled[col].fillna(0)
    filled["close"] = filled["close"].ffill()
    for col in ("open", "high", "low"):
        filled[col] = filled[col].fillna(filled["close"])
    filled["n_trades"] = filled["n_trades"].astype("int64")
    return filled


def add_bar_features(bars: pd.DataFrame) -> pd.DataFrame:
    """Adiciona variáveis derivadas de microestrutura às barras OHLCV."""
    out = bars.copy()
    out["vwap"] = (out["volume_usd"] / out["volume_btc"]).where(out["volume_btc"] > 0, out["close"])
    out["sell_volume_btc"] = out["volume_btc"] - out["buy_volume_btc"]
    out["ofi"] = (
        (out["buy_volume_btc"] - out["sell_volume_btc"]) / out["volume_btc"]
    ).where(out["volume_btc"] > 0, 0.0)
    out["log_return"] = np.log(out["close"]).diff()
    out["abs_return_bps"] = out["log_return"].abs() * 1e4
    out["range_bps"] = (out["high"] / out["low"] - 1) * 1e4
    out["avg_trade_usd"] = (out["volume_usd"] / out["n_trades"]).where(out["n_trades"] > 0, 0.0)
    return out


def build_taker_orders(trades: pd.DataFrame) -> pd.DataFrame:
    """Reconstrói ordens agressoras aproximadas agrupando execuções consecutivas de mesmo `ts` e `side`."""
    new_order = trades["ts"].ne(trades["ts"].shift()) | trades["side"].ne(trades["side"].shift())
    order_id = new_order.cumsum().rename("order_id")

    orders = trades.groupby(order_id).agg(
        ts=("ts", "first"),
        side=("side", "first"),
        first_trade_id=("trade_id", "first"),
        n_fills=("trade_id", "size"),
        quantity=("quantity", "sum"),
        notional_usd=("notional_usd", "sum"),
        price_first=("price", "first"),
        price_last=("price", "last"),
    )
    orders["book_walk_bps"] = (orders["price_last"] / orders["price_first"] - 1).abs() * 1e4
    orders["size_bucket"] = pd.cut(
        orders["notional_usd"],
        bins=SIZE_BINS,
        labels=SIZE_LABELS,
        right=False,
    )
    return orders


def run_etl_pipeline(
    base_dir: Path | str | None = None,
    force: bool = False,
    verbose: bool = True,
) -> dict[str, Path]:
    """Executa o pipeline completo de ETL e grava os Parquets em `data/processed/`."""
    paths = get_project_paths(base_dir)
    paths.ensure_dirs()

    output_names = ("trades_clean", "bars_1min", "bars_1s", "taker_orders")
    output_paths = {name: paths.processed_dir / f"{name}.parquet" for name in output_names}

    if not force and all(p.exists() for p in output_paths.values()):
        if verbose:
            print("Todos os arquivos em data/processed/ já existem. Use force=True para regerar.")
        return output_paths

    pa.set_memory_pool(pa.system_memory_pool())
    t0 = time.time()

    raw_path = download_file(DATA_URL, paths.raw_dir / FILE_NAME, EXPECTED_SHA256)
    if verbose:
        print(f"Dado bruto verificado: {raw_path} ({time.time() - t0:.1f}s)")

    df_raw = pd.read_parquet(raw_path)
    pa.default_memory_pool().release_unused()

    trades = clean_trades(df_raw, in_place=True)
    del df_raw
    gc.collect()

    validate_trades(trades)
    trades.to_parquet(output_paths["trades_clean"], compression="zstd", index=False)
    if verbose:
        print(f"Salvo trades_clean.parquet ({len(trades):,} linhas)")

    bars_1m = add_bar_features(build_bars(trades, "1min", start=PERIOD_START, end=PERIOD_END_DECLARED))
    bars_1m["n_trades"] = bars_1m["n_trades"].astype("int64")
    bars_1m.to_parquet(output_paths["bars_1min"], compression="zstd", index=True)

    bars_1s = add_bar_features(
        fill_bar_gaps(build_bars(trades, "1s", start=PERIOD_START, end=PERIOD_END_DECLARED))
    )
    bars_1s.to_parquet(output_paths["bars_1s"], compression="zstd", index=True)

    taker_orders = build_taker_orders(trades)
    taker_orders.to_parquet(output_paths["taker_orders"], compression="zstd", index=True)

    del trades, bars_1m, bars_1s, taker_orders
    gc.collect()
    pa.default_memory_pool().release_unused()

    if verbose:
        print(f"Pipeline ETL concluído em {time.time() - t0:.1f}s.")
    return output_paths


if __name__ == "__main__":
    run_etl_pipeline(verbose=True)
