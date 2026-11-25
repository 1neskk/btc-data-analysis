# Projeto A3 — Microestrutura do Bitcoin (BTC/USDT) em uma semana de estresse

Projeto analítico da unidade curricular **Análise de Dados e Big Data (0005073)**, semestre 2026/2.

Analisamos **27,9 milhões de negócios** de BTC/USDT na Binance entre 19 e 25/02/2025 (a semana do ataque hacker à Bybit e da queda de US$ 99,5 mil para US$ 86 mil) para apoiar as decisões de uma mesa de execução de criptoativos.

## Entregas

| Checkpoint | Status | Arquivo |
|---|---|---|
| 1 — Diagnóstico & Escopo | ✅ | [`CHECKPOINT_1.md`](CHECKPOINT_1.md): grupo, cenário, base, dicionário de dados, 3 perguntas de negócio |
| 2 — Auditoria & ETL | ✅ | [`notebooks/A3_CP2_auditoria_etl_eda.ipynb`](notebooks/A3_CP2_auditoria_etl_eda.ipynb): auditoria, limpeza, validação cruzada, EDA inicial |
| 3 — Entrega final & Defesa | ⏳ | código consolidado (`src/`), modelagem & storytelling (`notebooks/A3_CP3_modelagem_storytelling.ipynb`), dashboard (`app/dashboard.py`), ética/LGPD (`ETHICS_LGPD.md`); slides pendentes |

## Base de dados

- **Fonte:** [jalvart/bitcoin-tick-level-trade-data-free-sample](https://huggingface.co/datasets/jalvart/bitcoin-tick-level-trade-data-free-sample) (Hugging Face), fixada no commit `c90f6087` e conferida por SHA-256.
- **Validação:** reconciliada minuto a minuto com os candles oficiais da [Binance Public Data](https://data.binance.vision), com 100 % de concordância.
- **Licença:** uso pessoal e acadêmico, **sem redistribuição**. Por isso a pasta `data/` não é versionada: o notebook baixa tudo sozinho.

## Como executar

**Google Colab (recomendado):** *Arquivo → Fazer upload de notebook* → escolha o `.ipynb` → *Ambiente de execução → Executar tudo*. Leva ≈ 1–3 min e usa ≈ 6–9 GB de RAM, o que cabe no Colab gratuito.

**Localmente:**

```bash
python -m venv .venv && source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

```bash
cd notebooks && jupyter notebook A3_CP2_auditoria_etl_eda.ipynb
```

### Pipeline consolidado e Modelagem (Checkpoint 3)

```bash
# 1. Gerar/validar os Parquets em data/processed/ (caso ainda não existam)
python -m src.etl

# 2. Executar o notebook de modelagem preditiva e Data Storytelling
cd notebooks && jupyter notebook A3_CP3_modelagem_storytelling.ipynb
```

### Dashboard Interativo (Streamlit)

O dashboard consome os arquivos processados em `data/processed/` (caso ainda não tenham sido gerados, rode `python -m src.etl` ou o notebook do Checkpoint 2 primeiro) e oferece filtros por dia, janela horária, fuso (**UTC** ou **BRT**) e faixa de tamanho:

```bash
streamlit run app/dashboard.py
```

## Estrutura

```
.
├── CHECKPOINT_1.md                          # Diagnóstico & Escopo
├── ETHICS_LGPD.md                           # Análise de LGPD, licença, vieses e riscos de sinais
├── STORYTELLING.md                          # Narrativa executiva "da calmaria ao estresse"
├── src/                                     # Código consolidado reutilizável
│   ├── config.py                            # Parâmetros, paleta e caminhos
│   ├── etl.py                               # validate_trades, build_bars, fill_bar_gaps, run_etl_pipeline
│   ├── data_loader.py                       # Leitura de data/processed/ e agregações P1–P3
│   └── modeling.py                          # Atributos causais e validação walk-forward
├── app/
│   └── dashboard.py                         # Dashboard interativo (Streamlit + Plotly)
├── tests/
│   └── test_etl_and_modeling.py             # Testes unitários e de ausência de look-ahead
├── notebooks/
│   ├── A3_CP2_auditoria_etl_eda.ipynb       # Auditoria, ETL e EDA (executado, com saídas)
│   └── A3_CP3_modelagem_storytelling.ipynb  # Modelagem preditiva (1min/1s) e Storytelling
├── data/                                    # gerada pelo ETL/notebook (não versionada)
│   ├── raw/        # parquet original (SHA-256 conferido)
│   ├── external/   # candles oficiais da Binance (validação)
│   └── processed/  # trades_clean, bars_1min, bars_1s, taker_orders (.parquet)
├── requirements.txt
└── README.md
```

## Principais achados até aqui

- **Qualidade:** sem nulos e sem duplicatas reais, mas com problemas de verdade. `ingest_ts` está 100 % inválido (datas de 2032 a 2037), há tipos inadequados, colunas constantes e redundantes, e **41,7 % de duplicatas aparentes** que são execuções parciais legítimas e **não** devem ser apagadas.
- **P1 (liquidez):** volume e volatilidade têm pico às 15h UTC (12h BRT), ≈ 4× a hora mais fraca.
- **P2 (estresse):** em dias de estresse o volume é ≈ 2,7× o de um dia útil e a volatilidade ≈ 2×. Negócios acima de US$ 10 mil são 1,4 % da contagem e ≈ 60 % do valor.
- **P3 (fluxo):** o desequilíbrio comprador/vendedor explica o retorno do mesmo minuto (ρ ≈ 0,39), mas praticamente nada do minuto seguinte (ρ ≈ 0,02).
