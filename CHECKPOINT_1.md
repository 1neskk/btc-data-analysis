# Checkpoint 1 — Diagnóstico & Escopo

**Unidade Curricular:** Análise de Dados e Big Data (0005073) · Projeto Analítico A3 · Semestre 2026/2
**Tema:** Microestrutura do mercado de Bitcoin (BTC/USDT) em uma semana de estresse
**Eixo temático:** Mercado financeiro / criptoativos (tema livre; os eixos do guia são sugestões)

---

## 1. Definição do grupo

| Integrante | RA | Papel principal |
|---|---|---|
| _[Nome do(a) aluno(a) 1]_ | _[RA]_ | _[ex.: ETL e qualidade de dados]_ |
| _[Nome do(a) aluno(a) 2]_ | _[RA]_ | _[ex.: EDA e visualização]_ |
| _[Nome do(a) aluno(a) 3]_ | _[RA]_ | _[ex.: storytelling, ética e LGPD]_ |

---

## 2. Contexto e cenário

**Cenário.** Atuamos como o time de dados de uma **mesa de execução de criptoativos**: uma área que recebe ordens grandes de clientes (fundos, tesourarias de empresas, family offices) e precisa executá-las no mercado à vista de **BTC/USDT da Binance**, a corretora de maior liquidez do mundo. Executar mal custa caro. Uma ordem grande colocada no momento errado "anda o livro" (consome várias faixas de preço), paga *slippage* e fica exposta a movimentos bruscos.

**Período analisado.** A semana de **19 a 25 de fevereiro de 2025** foi de forte estresse. Em 21/02 a corretora Bybit sofreu o maior roubo de criptoativos já registrado (≈ US$ 1,5 bilhão em ETH). Nos dias seguintes o bitcoin, que havia tocado **US$ 99.475** em 21/02, caiu até **US$ 86.051** em 25/02 (−13,5 %). Em 25/02 houve **10,3 milhões de negócios**, 37 % de toda a semana em um único dia.

**Problema.** A mesa precisa de evidências, e não de intuição, para decidir **quando** e **como** executar ordens, e para **calibrar seus controles de risco** em dias de estresse. Dados de *tick* (cada negócio individual, com precisão de milissegundo) permitem medir liquidez, volatilidade e pressão compradora/vendedora com uma granularidade que candles diários escondem.

---

## 3. Base de dados

| Item | Valor |
|---|---|
| **Nome** | Bitcoin (BTC/USDT) Tick-Level Trade Data — Free Sample |
| **Link** | <https://huggingface.co/datasets/jalvart/bitcoin-tick-level-trade-data-free-sample> |
| **Arquivo** | `data/sample_BTC_2025-02-19_to_2025-02-26.parquet` (Apache Parquet, ZSTD, 103 MB) |
| **Versão fixada** | commit `c90f6087f5975daec7fe80e6ed110dd19108bd5c` · SHA-256 `2a6602489e57e8fcde945e082eba0a60ea95484ee8cfe3333ea1fe166d44070a` |
| **Origem primária** | Negócios públicos da Binance (spot), coletados e publicados pelo fornecedor *The Glitch List* |
| **Dimensão** | **27.925.338 registros × 9 colunas** |
| **Período** | 19/02/2025 00:00:00 → 25/02/2025 23:59:59 (UTC) |
| **Licença** | Uso pessoal e acadêmico; redistribuição proibida. Por isso o repositório **não** inclui os dados: o notebook baixa o arquivo da fonte e confere o hash. |

### 3.1 Aderência aos requisitos do guia

| Requisito | Situação |
|---|---|
| Base real e pública | ✅ Hugging Face, acesso aberto (sem *gate*) |
| ≥ 1.000 registros | ✅ 27,9 milhões |
| 8 a 10 colunas | ✅ 9 colunas |
| Tipos diferentes | ✅ numéricos (`price`, `quantity`, `trade_id`), categóricos (`exchange`, `symbol`, `aggressor_side`, `raw_side`), temporais (`exchange_ts`, `ingest_ts`) |
| Oportunidades reais de limpeza (GIGO) | ✅ ver seção 3.3 |

### 3.2 Confiabilidade

O fornecedor é um terceiro, então **não confiamos no arquivo às cegas**. No Checkpoint 2 reconstruímos candles de 1 minuto a partir dos *ticks* e os comparamos com os candles **oficiais** publicados pela própria Binance (<https://data.binance.vision>). Resultado: **10.080 de 10.080 minutos idênticos** em abertura, máxima, mínima, fechamento e número de negócios, com volumes iguais até a precisão de ponto flutuante. A base é fiel à fonte primária e está completa.

### 3.3 Problemas de qualidade identificados (prévia da auditoria)

A base parece limpa (zero nulos explícitos), mas a auditoria revelou problemas reais:

1. **`ingest_ts` inválido:** 100 % dos valores são datas **futuras** (2032 a 2037), com apenas 7 valores distintos (um por dia). Os valores são tratados como nulos e a coluna é descartada.
2. **Tipos inadequados:** `trade_id` é armazenado como texto (deveria ser inteiro) e `exchange_ts` como inteiro em milissegundos (deveria ser data-hora).
3. **Colunas sem informação:** `exchange` e `symbol` têm um único valor (cardinalidade 1).
4. **Redundância:** `raw_side` ("buy"/"sell") e `aggressor_side` (+1/−1) são a mesma informação (concordância de 100 %).
5. **Duplicatas aparentes:** 11,6 milhões de linhas (41,7 %) são idênticas em tudo exceto o `trade_id`. Elas **não** são erro: são execuções parciais de uma mesma ordem agressora contra várias ordens do livro. Um `drop_duplicates()` ingênuo apagaria 41,7 % dos negócios.
6. **Metadado inconsistente:** o nome do arquivo indica o período até 26/02, mas o último negócio é de 25/02 23:59:59 UTC.
7. **Inconsistência entre fontes:** os candles oficiais da Binance de 2025 usam timestamps em **microssegundos**, e os *ticks* em **milissegundos**. É preciso normalizar antes de cruzar.
8. **Nulos estruturais na reamostragem:** ao agregar em barras de 1 segundo, 6,6 % dos segundos não têm negócio. Isso exige uma estratégia de preenchimento sem viés de antecipação (*look-ahead*).
9. **Assimetria extrema / outliers:** a mediana de um negócio é ≈ US$ 6, enquanto o maior chega a US$ 5,4 milhões. São outliers legítimos, que não devem ser removidos.

---

## 4. Dicionário de dados

### 4.1 Colunas originais

| Coluna | Tipo no arquivo | Tipo lógico | Descrição | Valores observados | Problema → tratamento |
|---|---|---|---|---|---|
| `exchange` | `dictionary<string>` | Categórico nominal | Corretora onde o negócio ocorreu | `binance` (único) | Constante → vira metadado e sai da tabela |
| `symbol` | `dictionary<string>` | Categórico nominal | Par negociado | `BTCUSDT` (único) | Constante → vira metadado e sai da tabela |
| `trade_id` | `string` | Identificador (inteiro) | ID sequencial do negócio atribuído pela Binance | 4.570.646.084 a 4.598.571.421; único e contíguo | Texto → `int64` |
| `exchange_ts` | `int64` (epoch ms) | Temporal | Instante da execução na corretora (UTC) | 19/02/2025 00:00:00,219 a 25/02/2025 23:59:59,694 | Inteiro → `datetime64[UTC]` (`ts`) |
| `ingest_ts` | `int64` (epoch ms) | Temporal | Instante em que o fornecedor gravou o registro | 7 valores, de 05/04/2032 a 09/01/2037 | Datas futuras → nulo → coluna descartada |
| `price` | `double` | Numérico contínuo | Preço de execução em USDT por 1 BTC | 86.050,99 a 99.475,00 (passo 0,01) | OK |
| `quantity` | `double` | Numérico contínuo | Quantidade negociada em BTC | 0,00001 a 56,35 (passo 0,00001) | Cauda pesada → manter, analisar em escala log |
| `aggressor_side` | `int8` | Categórico binário | Lado de quem "agrediu" o livro: +1 compra, −1 venda | {−1: 14.471.136; +1: 13.454.202} | Convertido em `side` categórico |
| `raw_side` | `string` | Categórico binário | Mesmo lado do agressor, em texto original | {`sell`, `buy`} | Redundante → descartada |

> **Observação:** USDT é uma *stablecoin* pareada ao dólar (1 USDT ≈ US$ 1). Neste projeto, valores em USDT são lidos como dólares.

### 4.2 Variáveis derivadas (criadas no ETL)

| Variável | Nível | Definição |
|---|---|---|
| `ts` | negócio | `exchange_ts` convertido para data-hora UTC |
| `side` | negócio | `buy` / `sell` (categórico), a partir de `aggressor_side` |
| `notional_usd` | negócio | `price × quantity`: valor financeiro do negócio em US$ |
| `size_bucket` | negócio | Faixa de valor: < US$ 100 · 100–1 mil · 1 mil–10 mil · 10 mil–100 mil · ≥ 100 mil |
| `open`, `high`, `low`, `close` | barra (1 min / 1 s) | Primeiro, máximo, mínimo e último preço do intervalo |
| `volume_btc`, `volume_usd` | barra | Soma de `quantity` e de `notional_usd` |
| `n_trades` | barra | Número de negócios no intervalo |
| `buy_volume_btc` | barra | Volume em que o agressor foi comprador |
| `vwap` | barra | Preço médio ponderado por volume (`volume_usd / volume_btc`) |
| `ofi` | barra | *Order Flow Imbalance* = (compra − venda) / (compra + venda), de −1 a +1 |
| `log_return` | barra | `ln(close_t / close_{t−1})` |
| `n_fills` | ordem agressora | Número de execuções parciais de uma mesma ordem agressora (reconstrução aproximada) |

---

## 5. Perguntas de negócio

### P1 — Liquidez e janela de execução
> **Em quais horários do dia (UTC) o BTC/USDT concentra maior volume e número de negócios, e como a volatilidade acompanha essa liquidez?**

- **Decisão apoiada:** em que janela a mesa deve executar (ou fatiar) ordens grandes para reduzir impacto de preço.
- **Métricas:** volume em US$ e número de negócios por minuto, média e mediana por hora do dia; retorno absoluto médio (bps) por hora; mapa de calor dia × hora.
- **Hipótese:** a liquidez se concentra na abertura do mercado americano (≈ 14h30 UTC / 11h30 BRT), mas a volatilidade também, o que cria um *trade-off*.

### P2 — Comportamento em dias de estresse
> **Como volume, volatilidade e o perfil de tamanho dos negócios mudaram nos dias de estresse (21, 24 e 25/02) em comparação com os dias calmos (22 e 23/02)? Quem concentra o volume: muitos negócios pequenos ou poucos negócios grandes?**

- **Decisão apoiada:** calibrar limites de risco e alertas de volatilidade, e prever a capacidade operacional necessária em dias de estresse.
- **Métricas:** amplitude diária (%), volatilidade realizada diária, volume em US$, número de negócios; participação de cada faixa de tamanho no número de negócios e no volume financeiro (`groupby`).
- **Hipótese:** em dias de estresse o volume se multiplica e poucos negócios grandes concentram a maior parte do valor negociado.

### P3 — Pressão compradora/vendedora e preço
> **O desequilíbrio entre compras e vendas agressoras (*Order Flow Imbalance*, OFI) está associado ao retorno do preço no mesmo minuto? E ele antecipa o retorno do minuto seguinte?**

- **Decisão apoiada:** viabilidade de um sinal ou modelo preditivo de curto prazo (base para a etapa preditiva no Checkpoint 3).
- **Métricas:** OFI por minuto; correlação de Pearson/Spearman entre OFI e retorno no mesmo minuto e com defasagens de 1 a 10 minutos; saldo comprador/vendedor diário.
- **Hipótese:** forte associação no mesmo minuto (o fluxo "empurra" o preço), mas pouco ou nenhum poder preditivo para o minuto seguinte (eficiência de mercado).

---

## 6. Ética e LGPD (visão preliminar)

- **Dados pessoais:** a base **não contém** dados pessoais nem identificadores de clientes. Cada linha é um negócio anônimo. Não há titular identificável no sentido do art. 5º, I, da LGPD.
- **Licença:** respeitamos a licença do fornecedor (uso acadêmico; sem redistribuição). Os dados não são versionados no repositório e o notebook os obtém da fonte oficial.
- **Vieses e limites:** uma única corretora, um único par e **uma semana atípica (estresse)**. As conclusões não devem ser generalizadas para outros períodos sem validação. A discussão completa entra no Checkpoint 3.

---

## 7. Referências

- Fornecedor da base: The Glitch List — <https://huggingface.co/datasets/jalvart/bitcoin-tick-level-trade-data-free-sample>
- Fonte primária para validação: Binance Public Data — <https://data.binance.vision> (candles spot de 1 minuto, BTCUSDT)
- Cont, R.; Kukanov, A.; Stoikov, S. (2014). *The Price Impact of Order Book Events*. Journal of Financial Econometrics, 12(1), 47–88. (Fundamento do *Order Flow Imbalance*.)
- Lei nº 13.709/2018 — Lei Geral de Proteção de Dados Pessoais (LGPD).
