"""Dashboard interativo — Microestrutura BTC/USDT (Projeto A3 · Checkpoint 3).

Execução local:
    streamlit run app/dashboard.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import DAY_COLORS, PALETTE, SIZE_LABELS, day_label  # noqa: E402
from src.data_loader import (  # noqa: E402
    compute_daily_summary,
    compute_hourly_profile,
    compute_lag_correlations,
    compute_trade_size_summary,
    load_bars,
    load_taker_orders,
)
from src.modeling import (  # noqa: E402
    prepare_modeling_dataset,
    run_direction_walk_forward,
    run_volatility_walk_forward,
    summarize_walk_forward,
)

st.set_page_config(
    page_title="A3 · Microestrutura BTC/USDT",
    page_icon="₿",
    layout="wide",
    initial_sidebar_state="expanded",
)


def fmt_br(value: float, decimals: int = 0) -> str:
    s = f"{value:,.{decimals}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


@st.cache_data(show_spinner="Carregando barras de 1 minuto...")
def get_bars_1min() -> pd.DataFrame:
    return load_bars("1min", ROOT_DIR)


@st.cache_data(show_spinner="Carregando resumo diário e faixas de tamanho...")
def get_core_summaries() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    bars_1m = get_bars_1min()
    daily = compute_daily_summary(bars_1m)
    size_hourly = compute_trade_size_summary(ROOT_DIR, use_cache=True)
    orders = load_taker_orders(
        ROOT_DIR,
        columns=["ts", "side", "n_fills", "notional_usd", "book_walk_bps", "size_bucket"],
    )
    orders["date_str"] = orders["ts"].dt.strftime("%Y-%m-%d")
    orders["hour_utc"] = orders["ts"].dt.hour
    orders_summary = (
        orders.groupby(["date_str", "hour_utc", "size_bucket"], observed=True)
        .agg(
            ordens=("notional_usd", "size"),
            volume_usd=("notional_usd", "sum"),
            ordens_100k=("notional_usd", lambda s: int((s >= 100_000).sum())),
            vol_100k=("notional_usd", lambda s: float(s[s >= 100_000].sum())),
            book_walk_medio_bps=("book_walk_bps", "mean"),
        )
        .reset_index()
    )
    return daily, size_hourly, orders_summary


@st.cache_data(show_spinner="Executando validação walk-forward (1 min)...")
def get_walk_forward_results() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    bars_1m = get_bars_1min()
    feats, targets, fsets = prepare_modeling_dataset(bars_1m)
    vol_folds, vol_preds = run_volatility_walk_forward(feats, targets, fsets, target_col="target_range_bps")
    dir_folds, dir_preds = run_direction_walk_forward(feats, targets, fsets)
    vol_summary = summarize_walk_forward(vol_folds, ["mae_bps", "rmse_bps", "r2", "spearman"])
    dir_summary = summarize_walk_forward(
        dir_folds,
        ["accuracy", "balanced_acc", "roc_auc", "log_loss", "retorno_bruto_bps", "retorno_top10_bps"],
    )
    return vol_summary, vol_folds, dir_summary, dir_folds


def main() -> None:
    try:
        bars_1m = get_bars_1min()
        daily_all, size_hourly, orders_summary = get_core_summaries()
    except FileNotFoundError as exc:
        st.error(
            f"Dados processados não encontrados em `data/processed/`.\n\n"
            f"Execute antes `python -m src.etl` (ou rode o notebook do CP2).\n\nDetalhes: {exc}"
        )
        st.stop()

    # --- Sidebar: Filtros interativos -----------------------------------------
    st.sidebar.title("Filtros da Mesa")
    tz_choice = st.sidebar.radio(
        "Fuso horário",
        options=["UTC", "BRT (UTC−3)"],
        index=0,
        help="Alterna todos os horários de barras, perfis e mapas de calor entre UTC e Brasília (UTC−3).",
    )
    tz_offset = 0 if tz_choice == "UTC" else -3
    tz_short = "UTC" if tz_offset == 0 else "BRT"

    day_options = daily_all["date_str"].tolist()
    day_display = dict(zip(daily_all["date_str"], daily_all["day_label"] + " · " + daily_all["tipo"]))

    preset = st.sidebar.selectbox(
        "Recorte rápido de dias",
        options=[
            "Semana completa (19–25/02)",
            "Apenas dias de estresse (21, 24, 25/02)",
            "Apenas dias calmos (19, 20, 22, 23/02)",
            "Seleção manual",
        ],
    )
    if preset == "Semana completa (19–25/02)":
        default_days = day_options
    elif preset == "Apenas dias de estresse (21, 24, 25/02)":
        default_days = daily_all.loc[daily_all["tipo"] == "estresse", "date_str"].tolist()
    elif preset == "Apenas dias calmos (19, 20, 22, 23/02)":
        default_days = daily_all.loc[daily_all["tipo"] != "estresse", "date_str"].tolist()
    else:
        default_days = day_options

    selected_days = st.sidebar.multiselect(
        "Dias incluídos",
        options=day_options,
        default=default_days,
        format_func=lambda d: day_display[d],
    )
    if not selected_days:
        st.warning("Selecione pelo menos um dia no menu lateral.")
        st.stop()

    hour_range = st.sidebar.slider(
        f"Janela horária ({tz_short})",
        min_value=0,
        max_value=23,
        value=(0, 23),
        format="%02dh",
    )

    selected_buckets = st.sidebar.multiselect(
        "Faixas de tamanho (P2)",
        options=SIZE_LABELS,
        default=SIZE_LABELS,
    )
    if not selected_buckets:
        selected_buckets = SIZE_LABELS

    st.sidebar.markdown("---")
    st.sidebar.caption(
        "Fonte: Binance Spot BTC/USDT via Hugging Face (`c90f6087`), "
        "reconciliada 100 % com candles oficiais da Binance."
    )

    # --- Aplicação dos filtros ------------------------------------------------
    bars_view = bars_1m.copy()
    bars_view["date_str"] = bars_view.index.strftime("%Y-%m-%d")
    bars_view["hour_sel"] = (bars_view.index.hour + tz_offset) % 24
    mask_bars = (
        bars_view["date_str"].isin(selected_days)
        & bars_view["hour_sel"].between(hour_range[0], hour_range[1])
    )
    bars_filt = bars_view.loc[mask_bars].copy()

    size_filt = size_hourly.copy()
    size_filt["hour_sel"] = (size_filt["hour_utc"] + tz_offset) % 24
    size_filt = size_filt[
        size_filt["date_str"].isin(selected_days)
        & size_filt["hour_sel"].between(hour_range[0], hour_range[1])
        & size_filt["size_bucket"].isin(selected_buckets)
    ]

    orders_filt = orders_summary.copy()
    orders_filt["hour_sel"] = (orders_filt["hour_utc"] + tz_offset) % 24
    orders_filt = orders_filt[
        orders_filt["date_str"].isin(selected_days)
        & orders_filt["hour_sel"].between(hour_range[0], hour_range[1])
        & orders_filt["size_bucket"].isin(selected_buckets)
    ]

    daily_filt = daily_all[daily_all["date_str"].isin(selected_days)].copy()

    # --- Cabeçalho e KPIs dinâmicos -------------------------------------------
    st.title("BTC/USDT — Microestrutura da Calmaria ao Estresse")
    st.caption(
        f"Painel de apoio à mesa de execução · Filtro atual: **{len(selected_days)} dia(s)** · "
        f"Janela **{hour_range[0]:02d}h–{hour_range[1]:02d}h {tz_short}** · "
        f"**{fmt_br(len(bars_filt))} minutos**"
    )

    total_vol_bi = bars_filt["volume_usd"].sum() / 1e9
    total_trades_mi = bars_filt["n_trades"].sum() / 1e6
    med_range_bps = bars_filt["range_bps"].median()
    price_high = bars_filt["high"].max()
    price_low = bars_filt["low"].min()
    net_flow_pct = (
        (bars_filt["buy_volume_btc"].sum() * 2 - bars_filt["volume_btc"].sum())
        / max(bars_filt["volume_btc"].sum(), 1e-12)
        * 100.0
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Volume negociado", f"US$ {fmt_br(total_vol_bi, 2)} bi")
    c2.metric("Negócios executados", f"{fmt_br(total_trades_mi, 2)} mi")
    c3.metric("Amplitude mediana (1 min)", f"{fmt_br(med_range_bps, 2)} bps")
    c4.metric("Faixa de preço", f"US$ {fmt_br(price_low)} – {fmt_br(price_high)}")
    c5.metric("Saldo comprador líquido", f"{fmt_br(net_flow_pct, 1)} %")

    tab_story, tab_p1, tab_p2, tab_p3 = st.tabs(
        [
            "📖 Da Calmaria ao Estresse",
            "⏱️ P1 · Liquidez Intradiária",
            "⚡ P2 · Estresse & Faixas de Tamanho",
            "📈 P3 · Fluxo (OFI) & Modelagem",
        ]
    )

    # === TAB 1: NARRATIVA & VISÃO EXECUTIVA ===================================
    with tab_story:
        st.subheader("Ato I–III: Preço, choque da Bybit e explosão de volume")
        hourly_ts = bars_filt.resample("1h").agg(
            close=("close", "last"),
            volume_usd=("volume_usd", "sum"),
            range_bps=("range_bps", "median"),
        ).dropna(subset=["close"])
        hourly_ts["date_str"] = hourly_ts.index.strftime("%Y-%m-%d")
        type_map = daily_all.set_index("date_str")["tipo"].to_dict()
        hourly_ts["tipo"] = hourly_ts["date_str"].map(type_map)
        ts_display = hourly_ts.index + pd.Timedelta(hours=tz_offset)

        fig_price = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.07,
            row_heights=[0.65, 0.35],
            subplot_titles=(
                f"Preço de fechamento (1h, {tz_short})",
                "Volume por hora colorido por regime do dia (US$ milhões)",
            ),
        )
        fig_price.add_trace(
            go.Scatter(
                x=ts_display,
                y=hourly_ts["close"],
                mode="lines",
                name="Preço BTC/USDT",
                line=dict(color=PALETTE["blue"], width=2),
            ),
            row=1,
            col=1,
        )
        fig_price.add_trace(
            go.Bar(
                x=ts_display,
                y=hourly_ts["volume_usd"] / 1e6,
                marker_color=hourly_ts["tipo"].map(DAY_COLORS).tolist(),
                name="Volume horário",
            ),
            row=2,
            col=1,
        )
        fig_price.update_layout(
            height=480,
            template="plotly_white",
            showlegend=False,
            margin=dict(l=20, r=20, t=40, b=20),
        )
        fig_price.update_yaxes(title_text="USDT", row=1, col=1)
        fig_price.update_yaxes(title_text="US$ mi", row=2, col=1)
        st.plotly_chart(fig_price, width="stretch")

        st.markdown("### Plano de Ação para a Mesa de Execução")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.info(
                "**1. Janela TWAP/VWAP (P1)**\n\n"
                "Liquidez concentra-se entre **14h–16h UTC (11h–13h BRT)** — pico às 15h UTC "
                "(4,2× o vale das 06h UTC). Ordens grandes devem ser fatiadas nessa janela, "
                "evitando lotes únicos nos minutos de maior volatilidade."
            )
        with col_b:
            st.warning(
                "**2. Limites e Capacidade em Estresse (P2)**\n\n"
                "Em dias de amplitude > 4 %, o volume médio sobe **2,7×** e a volatilidade realizada **2,0×**. "
                "O dia 25/02 processou **10,3 milhões de negócios** (37 % da semana) e quase 10 mil ordens "
                "agressoras ≥ US$ 100 mil."
            )
        with col_c:
            st.success(
                "**3. Uso Realista de Sinais Preditivos (P3)**\n\n"
                "A **volatilidade** do próximo minuto é previsível fora da amostra (*walk-forward*) e "
                "serve para calibrar limites dinâmicos. Já a **direção do retorno** tem sinal fraco, "
                "inviável frente às taxas *taker* (2–10 bps)."
            )

    # === TAB 2: P1 LIQUIDEZ INTRADIÁRIA =======================================
    with tab_p1:
        st.subheader(f"Perfil horário de liquidez e volatilidade ({tz_short})")
        by_hour = compute_hourly_profile(bars_filt, tz_offset_hours=tz_offset)

        fig_p1 = make_subplots(
            rows=3,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.08,
            subplot_titles=(
                "Volume por minuto (mediana, US$ mil)",
                "Negócios por minuto (mediana)",
                "Amplitude intraminuto (mediana, bps)",
            ),
        )
        hours_idx = by_hour.index.tolist()
        top3 = set(by_hour["volume_usd_med"].nlargest(3).index.tolist())
        bar_colors = [PALETTE["blue"] if h in top3 else "#9ec5f4" for h in hours_idx]

        fig_p1.add_trace(
            go.Bar(x=hours_idx, y=by_hour["volume_usd_med"] / 1e3, marker_color=bar_colors, name="Vol US$ mil"),
            row=1,
            col=1,
        )
        fig_p1.add_trace(
            go.Bar(x=hours_idx, y=by_hour["negocios_med"], marker_color=bar_colors, name="Negócios"),
            row=2,
            col=1,
        )
        fig_p1.add_trace(
            go.Bar(x=hours_idx, y=by_hour["range_bps_med"], marker_color=bar_colors, name="Amplitude bps"),
            row=3,
            col=1,
        )
        fig_p1.update_xaxes(tickvals=hours_idx, ticktext=[f"{h:02d}h" for h in hours_idx], row=3, col=1)
        fig_p1.update_layout(height=540, template="plotly_white", showlegend=False, margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig_p1, width="stretch")

        col_hm, col_sc = st.columns([1.35, 1])
        with col_hm:
            bars_hm = bars_filt.copy()
            bars_hm["day_lbl"] = bars_hm.index.floor("D").map(day_label)
            heat = bars_hm.pivot_table(
                index="day_lbl", columns="hour_sel", values="volume_usd", aggfunc="sum"
            ) / 1e6
            # Ordenar dias cronologicamente conforme daily_filt
            ordered_lbls = [lbl for lbl in daily_filt["day_label"] if lbl in heat.index]
            heat = heat.reindex(ordered_lbls)
            fig_hm = px.imshow(
                heat,
                labels=dict(x=f"Hora ({tz_short})", y="Dia", color="US$ mi"),
                color_continuous_scale="Blues",
                aspect="auto",
                title=f"Mapa de calor: volume horário por dia (US$ milhões, {tz_short})",
            )
            fig_hm.update_layout(height=360, margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig_hm, width="stretch")

        with col_sc:
            rho_hr = by_hour["volume_usd_med"].corr(by_hour["range_bps_med"], method="spearman")
            fig_to = px.scatter(
                by_hour.reset_index(),
                x=by_hour["volume_usd_med"] / 1e3,
                y="range_bps_med",
                text=[f"{h:02d}h" for h in by_hour.index],
                title=f"Trade-off Liquidez × Volatilidade (Spearman ρ = {fmt_br(rho_hr, 2)})",
                labels={"x": "Volume mediano (US$ mil/min)", "range_bps_med": "Amplitude mediana (bps)"},
            )
            fig_to.update_traces(textposition="top center", marker=dict(size=9, color=PALETTE["blue"]))
            fig_to.update_layout(height=360, template="plotly_white", margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig_to, width="stretch")

    # === TAB 3: P2 DIAS DE ESTRESSE & FAIXAS DE TAMANHO ========================
    with tab_p2:
        st.subheader("Comparação de regimes e concentração por tamanho")
        col_d1, col_d2 = st.columns([1.2, 1])
        with col_d1:
            fig_days = make_subplots(
                rows=1,
                cols=2,
                subplot_titles=("Volume diário (US$ bi)", "Volatilidade realizada diária (%)"),
            )
            colors_day = daily_filt["tipo"].map(DAY_COLORS).tolist()
            fig_days.add_trace(
                go.Bar(x=daily_filt["day_label"], y=daily_filt["volume_usd"] / 1e9, marker_color=colors_day),
                row=1,
                col=1,
            )
            fig_days.add_trace(
                go.Bar(x=daily_filt["day_label"], y=daily_filt["vol_realizada_pct"], marker_color=colors_day),
                row=1,
                col=2,
            )
            fig_days.update_layout(height=350, template="plotly_white", showlegend=False, margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig_days, width="stretch")

        with col_d2:
            regime_tbl = (
                daily_filt.groupby("tipo")[["volume_usd", "negocios", "amplitude_pct", "vol_realizada_pct"]]
                .mean()
                .assign(volume_bi=lambda d: d["volume_usd"] / 1e9, negocios_mi=lambda d: d["negocios"] / 1e6)
                [["volume_bi", "negocios_mi", "amplitude_pct", "vol_realizada_pct"]]
            )
            regime_tbl.columns = ["Vol. médio (US$ bi)", "Negócios (mi)", "Amplitude (%)", "Vol. realizada (%)"]
            st.dataframe(regime_tbl.style.format("{:.2f}"), width="stretch")

        st.markdown("#### Concentração por faixa de tamanho (Negócios individuais vs Ordens agressoras)")
        by_size = (
            size_filt.groupby("size_bucket", observed=True)[["negocios", "volume_usd"]]
            .sum()
            .reindex(selected_buckets)
            .fillna(0.0)
        )
        by_size["pct_negocios"] = by_size["negocios"] / max(by_size["negocios"].sum(), 1) * 100
        by_size["pct_volume"] = by_size["volume_usd"] / max(by_size["volume_usd"].sum(), 1) * 100

        by_ord = (
            orders_filt.groupby("size_bucket", observed=True)[["ordens", "volume_usd"]]
            .sum()
            .reindex(selected_buckets)
            .fillna(0.0)
        )
        by_ord["pct_ordens"] = by_ord["ordens"] / max(by_ord["ordens"].sum(), 1) * 100
        by_ord["pct_volume"] = by_ord["volume_usd"] / max(by_ord["volume_usd"].sum(), 1) * 100

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            fig_sz = go.Figure()
            fig_sz.add_trace(
                go.Bar(
                    y=by_size.index.astype(str),
                    x=by_size["pct_negocios"],
                    name="% dos negócios",
                    orientation="h",
                    marker_color="#9ec5f4",
                )
            )
            fig_sz.add_trace(
                go.Bar(
                    y=by_size.index.astype(str),
                    x=by_size["pct_volume"],
                    name="% do volume US$",
                    orientation="h",
                    marker_color=PALETTE["blue"],
                )
            )
            fig_sz.update_layout(
                barmode="group",
                title="Negócios individuais: contagem vs valor financeiro",
                xaxis_title="% no recorte filtrado",
                height=340,
                template="plotly_white",
                margin=dict(l=10, r=10, t=40, b=10),
            )
            st.plotly_chart(fig_sz, width="stretch")

        with col_s2:
            ord_big = (
                orders_filt.groupby("date_str")[["ordens_100k", "vol_100k"]]
                .sum()
                .reindex(daily_filt["date_str"])
                .fillna(0)
            )
            ord_big["day_label"] = daily_filt.set_index("date_str").loc[ord_big.index, "day_label"]
            fig_big = px.bar(
                ord_big,
                x="day_label",
                y="ordens_100k",
                title="Ordens agressoras institucionais (≥ US$ 100 mil) por dia",
                labels={"day_label": "Dia", "ordens_100k": "Qtd. de ordens ≥ US$ 100 mil"},
                color_discrete_sequence=[PALETTE["orange"]],
            )
            fig_big.update_layout(height=340, template="plotly_white", margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig_big, width="stretch")

    # === TAB 4: P3 FLUXO (OFI) & MODELAGEM WALK-FORWARD ======================
    with tab_p3:
        st.subheader("Pressão compradora/vendedora (OFI) e poder preditivo")
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            fig_flow = go.Figure()
            fig_flow.add_trace(
                go.Bar(
                    x=daily_filt["day_label"],
                    y=daily_filt["saldo_fluxo_pct"],
                    marker_color=[PALETTE["blue"] if v > 0 else PALETTE["orange"] for v in daily_filt["saldo_fluxo_pct"]],
                    text=[f"{fmt_br(v, 1)} %" for v in daily_filt["saldo_fluxo_pct"]],
                    textposition="outside",
                )
            )
            fig_flow.update_layout(
                title="Saldo líquido diário de fluxo agressor (% do volume)",
                yaxis_title="Saldo (%)",
                height=340,
                template="plotly_white",
                margin=dict(l=10, r=10, t=40, b=10),
            )
            st.plotly_chart(fig_flow, width="stretch")

        with col_f2:
            lag_df = compute_lag_correlations(bars_filt.dropna(subset=["log_return"]), max_lag=10)
            signif = 1.96 / np.sqrt(max(bars_filt["ofi"].notna().sum(), 1))
            fig_lag = go.Figure()
            fig_lag.add_hrect(y0=-signif, y1=signif, fillcolor=PALETTE["grid"], opacity=0.6, line_width=0)
            fig_lag.add_trace(
                go.Bar(
                    x=["mesmo min"] + [f"+{k}" for k in lag_df.index if k > 0],
                    y=lag_df["pearson"],
                    marker_color=[PALETTE["blue"]] + ["#9ec5f4"] * (len(lag_df) - 1),
                    text=[fmt_br(v, 3) for v in lag_df["pearson"]],
                    textposition="outside",
                )
            )
            fig_lag.update_layout(
                title="Correlação de Pearson: OFI(t) × Retorno(t + k) no recorte",
                yaxis_title="Correlação de Pearson",
                height=340,
                template="plotly_white",
                margin=dict(l=10, r=10, t=40, b=10),
            )
            st.plotly_chart(fig_lag, width="stretch")

        st.markdown("### Resultados da Modelagem Preditiva (Walk-Forward em barras de 1 min)")
        st.caption(
            "Treino expansivo dia a dia (mínimo de 2 dias iniciais → avaliação estritamente fora da amostra de 21/02 a 25/02, "
            "sem vazamento de futuro)."
        )
        vol_sum, vol_folds, dir_sum, dir_folds = get_walk_forward_results()

        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.markdown("**Tarefa A — Previsão de Volatilidade (`range_bps` de t+1)**")
            st.dataframe(
                vol_sum.style.format(
                    {"mae_bps": "{:.2f}", "rmse_bps": "{:.2f}", "r2": "{:.3f}", "spearman": "{:.3f}"}
                ),
                width="stretch",
                hide_index=True,
            )
        with col_m2:
            st.markdown("**Tarefa B — Direção do Retorno (`log_return_{t+1} > 0`)**")
            st.dataframe(
                dir_sum.style.format(
                    {
                        "accuracy": "{:.3f}",
                        "balanced_acc": "{:.3f}",
                        "roc_auc": "{:.3f}",
                        "log_loss": "{:.3f}",
                        "retorno_bruto_bps": "{:.3f}",
                        "retorno_top10_bps": "{:.3f}",
                    }
                ),
                width="stretch",
                hide_index=True,
            )


if __name__ == "__main__":
    main()
