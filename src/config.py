"""Configurações, constantes de domínio e caminhos do projeto A3."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# --- Fonte dos dados (reprodutibilidade) --------------------------------------
HF_REPO = "jalvart/bitcoin-tick-level-trade-data-free-sample"
HF_REVISION = "c90f6087f5975daec7fe80e6ed110dd19108bd5c"
FILE_NAME = "sample_BTC_2025-02-19_to_2025-02-26.parquet"
DATA_URL = f"https://huggingface.co/datasets/{HF_REPO}/resolve/{HF_REVISION}/data/{FILE_NAME}"
EXPECTED_SHA256 = "2a6602489e57e8fcde945e082eba0a60ea95484ee8cfe3333ea1fe166d44070a"

DATASET_PUBLISHED_AT = pd.Timestamp("2026-10-25 10:12:10", tz="UTC")
PERIOD_START = pd.Timestamp("2025-02-19", tz="UTC")
PERIOD_END_DECLARED = pd.Timestamp("2025-02-26", tz="UTC")
BINANCE_KLINES_URL = "https://data.binance.vision/data/spot/daily/klines/BTCUSDT/1m"

# --- Regras de negócio e categorização ----------------------------------------
STRESS_RANGE_THRESHOLD = 0.04  # amplitude intradiária > 4% define dia de estresse

SIZE_BINS = [0, 100, 1_000, 10_000, 100_000, np.inf]
SIZE_LABELS = [
    "< US$ 100",
    "US$ 100–1 mil",
    "US$ 1–10 mil",
    "US$ 10–100 mil",
    "≥ US$ 100 mil",
]

DIAS_PT = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]

# Paleta compartilhada (consistente com o notebook do CP2)
PALETTE = {
    "surface": "#fcfcfb",
    "ink": "#0b0b0b",
    "ink_2": "#52514e",
    "muted": "#898781",
    "grid": "#e1e0d9",
    "axis": "#c3c2b7",
    "neutral": "#f0efec",
    "blue": "#2a78d6",
    "orange": "#eb6834",
    "red": "#e34948",
    "teal": "#1baf7a",
}

DAY_COLORS = {
    "estresse": PALETTE["blue"],
    "dia útil": PALETTE["axis"],
    "fim de semana": PALETTE["grid"],
}


@dataclass(frozen=True)
class ProjectPaths:
    """Diretórios principais do projeto."""

    base_dir: Path
    raw_dir: Path
    external_dir: Path
    processed_dir: Path

    def ensure_dirs(self) -> None:
        for folder in (self.raw_dir, self.external_dir, self.processed_dir):
            folder.mkdir(parents=True, exist_ok=True)


def get_project_paths(base_dir: Path | str | None = None) -> ProjectPaths:
    """Resolve os diretórios de dados a partir da raiz do repositório."""
    if base_dir is None:
        root = Path(__file__).resolve().parent.parent
    else:
        root = Path(base_dir).resolve()
    return ProjectPaths(
        base_dir=root,
        raw_dir=root / "data" / "raw",
        external_dir=root / "data" / "external",
        processed_dir=root / "data" / "processed",
    )


def day_label(ts: pd.Timestamp) -> str:
    """Formata um timestamp UTC como rótulo curto em português (ex.: 'sex 21/02')."""
    return f"{DIAS_PT[ts.day_of_week]} {ts:%d/%m}"
