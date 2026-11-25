"""Engenharia de atributos sem vazamento, validação walk-forward e avaliação operacional."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    log_loss,
    mean_absolute_error,
    r2_score,
    roc_auc_score,
    root_mean_squared_error,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

FEATURE_GROUPS: dict[str, list[str]] = {
    "apenas_ofi": [],
    "fluxo_e_atividade": [],
    "completo": [],
}


def build_lagged_features(
    bars: pd.DataFrame,
    lags: tuple[int, ...] = (0, 1, 2, 3, 5),
    windows: tuple[int, ...] = (5, 15, 60),
) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """Constrói features estritamente causais (<= t) para prever o intervalo t+1.

    Nenhuma operação usa `shift(-k)` ou janelas centralizadas, garantindo ausência
    de vazamento de futuro (look-ahead bias).
    """
    feats = pd.DataFrame(index=bars.index)

    log_vol = np.log1p(bars["volume_usd"].clip(lower=0.0))
    log_trades = np.log1p(bars["n_trades"].clip(lower=0.0))
    log_avg_trade = np.log1p(bars["avg_trade_usd"].clip(lower=0.0))
    ret_bps = bars["log_return"] * 1e4

    ofi_cols: list[str] = []
    activity_cols: list[str] = []
    vol_ret_cols: list[str] = []

    for lag in lags:
        suffix = f"t{lag}" if lag == 0 else f"lag{lag}"
        c_ofi = f"ofi_{suffix}"
        feats[c_ofi] = bars["ofi"].shift(lag)
        ofi_cols.append(c_ofi)

        c_lvol = f"log_vol_usd_{suffix}"
        c_ltrd = f"log_n_trades_{suffix}"
        feats[c_lvol] = log_vol.shift(lag)
        feats[c_ltrd] = log_trades.shift(lag)
        activity_cols.extend([c_lvol, c_ltrd])

        c_rng = f"range_bps_{suffix}"
        c_abs = f"abs_ret_bps_{suffix}"
        c_ret = f"ret_bps_{suffix}"
        feats[c_rng] = bars["range_bps"].shift(lag)
        feats[c_abs] = bars["abs_return_bps"].shift(lag)
        feats[c_ret] = ret_bps.shift(lag)
        vol_ret_cols.extend([c_rng, c_abs, c_ret])

    feats["log_avg_trade_t0"] = log_avg_trade
    activity_cols.append("log_avg_trade_t0")

    for w in windows:
        c_ofi_ma = f"ofi_ma_{w}"
        c_vol_ma = f"log_vol_ma_{w}"
        c_rng_ma = f"range_bps_ma_{w}"
        c_abs_ma = f"abs_ret_bps_ma_{w}"
        c_ret_std = f"ret_bps_std_{w}"
        feats[c_ofi_ma] = bars["ofi"].rolling(w, min_periods=w).mean()
        feats[c_vol_ma] = log_vol.rolling(w, min_periods=w).mean()
        feats[c_rng_ma] = bars["range_bps"].rolling(w, min_periods=w).mean()
        feats[c_abs_ma] = bars["abs_return_bps"].rolling(w, min_periods=w).mean()
        feats[c_ret_std] = ret_bps.rolling(w, min_periods=w).std()
        ofi_cols.append(c_ofi_ma)
        activity_cols.append(c_vol_ma)
        vol_ret_cols.extend([c_rng_ma, c_abs_ma, c_ret_std])

    # Interação OFI × atividade (fluxo ponderado por volume) e razão de aceleração de volatilidade
    feats["ofi_x_log_vol_t0"] = feats["ofi_t0"] * feats["log_vol_usd_t0"]
    activity_cols.append("ofi_x_log_vol_t0")

    feats["range_ratio_5_60"] = feats[f"range_bps_ma_{windows[0]}"] / (
        feats[f"range_bps_ma_{windows[-1]}"] + 1e-6
    )
    vol_ret_cols.append("range_ratio_5_60")

    # Sazonalidade intradiária conhecida deterministicamente
    hour_frac = bars.index.hour + bars.index.minute / 60.0
    feats["sin_hour"] = np.sin(2.0 * np.pi * hour_frac / 24.0)
    feats["cos_hour"] = np.cos(2.0 * np.pi * hour_frac / 24.0)
    vol_ret_cols.extend(["sin_hour", "cos_hour"])

    if "has_trades" in bars.columns:
        feats["has_trades_t0"] = bars["has_trades"].astype(float)
        activity_cols.append("has_trades_t0")

    feature_sets = {
        "apenas_ofi": ofi_cols,
        "fluxo_e_atividade": ofi_cols + activity_cols,
        "completo": ofi_cols + activity_cols + vol_ret_cols,
    }
    return feats, feature_sets


def build_targets(bars: pd.DataFrame) -> pd.DataFrame:
    """Constrói os alvos do intervalo t+1 alinhados ao índice t."""
    next_ret_bps = bars["log_return"].shift(-1) * 1e4
    targets = pd.DataFrame(
        {
            "target_range_bps": bars["range_bps"].shift(-1),
            "target_abs_ret_bps": bars["abs_return_bps"].shift(-1),
            "target_ret_bps": next_ret_bps,
            "target_dir": (next_ret_bps > 0.0).astype("float64"),
        },
        index=bars.index,
    )
    targets.loc[next_ret_bps.isna(), "target_dir"] = np.nan
    return targets


def prepare_modeling_dataset(
    bars: pd.DataFrame,
    lags: tuple[int, ...] = (0, 1, 2, 3, 5),
    windows: tuple[int, ...] = (5, 15, 60),
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, list[str]]]:
    """Combina features causais e alvos removendo apenas bordas com NaN."""
    feats, feature_sets = build_lagged_features(bars, lags=lags, windows=windows)
    targets = build_targets(bars)
    valid_mask = feats.notna().all(axis=1) & targets.notna().all(axis=1)
    return feats.loc[valid_mask], targets.loc[valid_mask], feature_sets


def daily_walk_forward_folds(
    index: pd.DatetimeIndex,
    min_train_days: int = 2,
) -> list[tuple[pd.Timestamp, np.ndarray, np.ndarray]]:
    """Gera dobras walk-forward expansivas dia a dia em ordem cronológica estrita."""
    days = pd.DatetimeIndex(index.floor("D").unique()).sort_values()
    if len(days) <= min_train_days:
        raise ValueError(
            f"São necessários mais de {min_train_days} dias para walk-forward (encontrados: {len(days)})."
        )

    day_floor = index.floor("D")
    folds: list[tuple[pd.Timestamp, np.ndarray, np.ndarray]] = []
    for i in range(min_train_days, len(days)):
        test_day = days[i]
        train_mask = np.asarray(day_floor < test_day)
        test_mask = np.asarray(day_floor == test_day)
        folds.append((test_day, train_mask, test_mask))
    return folds


@dataclass(frozen=True)
class ModelSpec:
    name: str
    family: str
    feature_set: str


def _make_regressor(kind: str):
    if kind == "ridge":
        return Pipeline([("scaler", StandardScaler()), ("model", Ridge(alpha=10.0))])
    if kind == "hgbr":
        return HistGradientBoostingRegressor(
            max_iter=150,
            max_depth=5,
            learning_rate=0.05,
            min_samples_leaf=50,
            random_state=42,
        )
    raise ValueError(f"Regressor desconhecido: {kind}")


def _make_classifier(kind: str):
    if kind == "logit":
        return Pipeline(
            [("scaler", StandardScaler()), ("model", LogisticRegression(C=0.5, max_iter=500))]
        )
    if kind == "hgbc":
        return HistGradientBoostingClassifier(
            max_iter=150,
            max_depth=5,
            learning_rate=0.05,
            min_samples_leaf=50,
            random_state=42,
        )
    raise ValueError(f"Classificador desconhecido: {kind}")


def run_volatility_walk_forward(
    feats: pd.DataFrame,
    targets: pd.DataFrame,
    feature_sets: dict[str, list[str]],
    target_col: str = "target_range_bps",
    min_train_days: int = 2,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Executa validação walk-forward para previsão de volatilidade (regressão)."""
    folds = daily_walk_forward_folds(feats.index, min_train_days=min_train_days)
    y = targets[target_col]

    experiments = [
        ("Persistência (t)", "baseline", "baseline_persistence"),
        ("Média móvel (15)", "baseline", "baseline_ma15"),
        ("Ridge (apenas OFI)", "linear", ("ridge", "apenas_ofi")),
        ("Ridge (completo)", "linear", ("ridge", "completo")),
        ("HistGradientBoosting (fluxo+ativ.)", "não linear", ("hgbr", "fluxo_e_atividade")),
        ("HistGradientBoosting (completo)", "não linear", ("hgbr", "completo")),
    ]

    fold_rows: list[dict] = []
    pred_frames: list[pd.DataFrame] = []

    for test_day, train_mask, test_mask in folds:
        y_train = y.iloc[train_mask].to_numpy()
        y_test = y.iloc[test_mask].to_numpy()
        day_str = f"{test_day:%Y-%m-%d}"

        for label, family, spec in experiments:
            if spec == "baseline_persistence":
                src_col = "range_bps_t0" if target_col == "target_range_bps" else "abs_ret_bps_t0"
                y_pred = feats.iloc[test_mask][src_col].to_numpy()
            elif spec == "baseline_ma15":
                src_col = (
                    "range_bps_ma_15"
                    if target_col == "target_range_bps"
                    else "abs_ret_bps_ma_15"
                )
                y_pred = feats.iloc[test_mask][src_col].to_numpy()
            else:
                kind, fset_name = spec
                cols = feature_sets[fset_name]
                model = _make_regressor(kind)
                model.fit(feats.iloc[train_mask][cols], y_train)
                y_pred = np.clip(model.predict(feats.iloc[test_mask][cols]), 0.0, None)

            spearman = float(pd.Series(y_test).corr(pd.Series(y_pred), method="spearman"))
            fold_rows.append(
                {
                    "modelo": label,
                    "família": family,
                    "dia_teste": day_str,
                    "n_treino": int(train_mask.sum()),
                    "n_teste": int(test_mask.sum()),
                    "mae_bps": float(mean_absolute_error(y_test, y_pred)),
                    "rmse_bps": float(root_mean_squared_error(y_test, y_pred)),
                    "r2": float(r2_score(y_test, y_pred)),
                    "spearman": spearman,
                }
            )
            pred_frames.append(
                pd.DataFrame(
                    {
                        "ts": feats.index[test_mask],
                        "dia_teste": day_str,
                        "modelo": label,
                        "y_true": y_test,
                        "y_pred": y_pred,
                    }
                )
            )

    return pd.DataFrame(fold_rows), pd.concat(pred_frames, ignore_index=True)


def run_direction_walk_forward(
    feats: pd.DataFrame,
    targets: pd.DataFrame,
    feature_sets: dict[str, list[str]],
    min_train_days: int = 2,
    exclude_zero_returns: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Executa validação walk-forward para previsão de direção do retorno (classificação)."""
    if exclude_zero_returns:
        nonzero = targets["target_ret_bps"] != 0.0
        feats = feats.loc[nonzero]
        targets = targets.loc[nonzero]

    folds = daily_walk_forward_folds(feats.index, min_train_days=min_train_days)
    y = targets["target_dir"].astype(int)
    ret_bps = targets["target_ret_bps"]

    experiments = [
        ("Classe majoritária", "baseline", "baseline_majority"),
        ("Persistência de sinal (t)", "baseline", "baseline_sign"),
        ("Logit (apenas OFI)", "linear", ("logit", "apenas_ofi")),
        ("Logit (completo)", "linear", ("logit", "completo")),
        ("HistGradientBoosting (fluxo+ativ.)", "não linear", ("hgbc", "fluxo_e_atividade")),
        ("HistGradientBoosting (completo)", "não linear", ("hgbc", "completo")),
    ]

    fold_rows: list[dict] = []
    pred_frames: list[pd.DataFrame] = []

    for test_day, train_mask, test_mask in folds:
        y_train = y.iloc[train_mask].to_numpy()
        y_test = y.iloc[test_mask].to_numpy()
        ret_test = ret_bps.iloc[test_mask].to_numpy()
        day_str = f"{test_day:%Y-%m-%d}"

        for label, family, spec in experiments:
            if spec == "baseline_majority":
                maj_prob = float(y_train.mean())
                y_prob = np.full(len(y_test), maj_prob, dtype=float)
            elif spec == "baseline_sign":
                prev_pos = (feats.iloc[test_mask]["ret_bps_t0"].to_numpy() > 0.0).astype(float)
                # Suavização leve só para log_loss finito
                y_prob = np.clip(prev_pos, 0.01, 0.99)
            else:
                kind, fset_name = spec
                cols = feature_sets[fset_name]
                model = _make_classifier(kind)
                model.fit(feats.iloc[train_mask][cols], y_train)
                y_prob = model.predict_proba(feats.iloc[test_mask][cols])[:, 1]

            y_hat = (y_prob >= 0.5).astype(int)
            # Retorno bruto médio por operação se operasse toda barra seguindo o sinal (+1 / -1)
            strategy_ret_bps = np.where(y_hat == 1, ret_test, -ret_test)
            # Top 10% de maior confiança (|p - 0.5| >= P90)
            conf = np.abs(y_prob - 0.5)
            thresh = np.quantile(conf, 0.90)
            top_mask = conf >= thresh
            top_gross_bps = float(np.mean(strategy_ret_bps[top_mask])) if top_mask.any() else 0.0

            try:
                auc = float(roc_auc_score(y_test, y_prob))
            except ValueError:
                auc = 0.5

            fold_rows.append(
                {
                    "modelo": label,
                    "família": family,
                    "dia_teste": day_str,
                    "n_treino": int(train_mask.sum()),
                    "n_teste": int(test_mask.sum()),
                    "accuracy": float(accuracy_score(y_test, y_hat)),
                    "balanced_acc": float(balanced_accuracy_score(y_test, y_hat)),
                    "roc_auc": auc,
                    "log_loss": float(log_loss(y_test, np.clip(y_prob, 1e-6, 1 - 1e-6))),
                    "retorno_bruto_bps": float(np.mean(strategy_ret_bps)),
                    "retorno_top10_bps": top_gross_bps,
                }
            )
            pred_frames.append(
                pd.DataFrame(
                    {
                        "ts": feats.index[test_mask],
                        "dia_teste": day_str,
                        "modelo": label,
                        "y_true": y_test,
                        "y_prob": y_prob,
                        "ret_bps": ret_test,
                    }
                )
            )

    return pd.DataFrame(fold_rows), pd.concat(pred_frames, ignore_index=True)


def summarize_walk_forward(fold_df: pd.DataFrame, metric_cols: list[str]) -> pd.DataFrame:
    """Agrega médias e desvios-padrão entre dobras do walk-forward."""
    summary = (
        fold_df.groupby(["modelo", "família"], sort=False)[metric_cols]
        .mean()
        .reset_index()
    )
    return summary
