# Data Storytelling — "Da Calmaria ao Estresse" (Mesa de Execução BTC/USDT)

**Projeto A3 · Análise de Dados e Big Data (0005073)**  
**Período analisado:** 19 a 25 de fevereiro de 2025 (27.925.338 negócios · 10.080 minutos · 604.800 segundos · 4.555.252 ordens agressoras)

---

## O Problema da Mesa
Uma mesa de execução institucional que recebe ordens grandes de BTC/USDT na Binance precisa responder a três perguntas práticas:
1. **Quando executar?** (P1 — liquidez vs. volatilidade ao longo do dia)
2. **Quanto o risco e a carga mudam em dias de pânico?** (P2 — regimes de estresse e concentração de tamanho)
3. **O fluxo comprador/vendedor antecipa o preço?** (P3 — utilidade operacional de sinais preditivos)

---

## Ato I — O Ritmo da Calmaria: Onde Está a Liquidez (P1)
Em condições normais, o mercado de BTC/USDT funciona 24/7, mas a liquidez **não é uniforme**:
- O volume mediano por minuto às **15h UTC (12h BRT)** atinge **US$ 2,13 milhões/min**, contra **US$ 0,51 milhão/min** às **06h UTC (03h BRT)** — uma razão pico/vale de **4,2×**.
- O horário mais ativo coincide diretamente com a janela logo após a abertura do mercado acionário americano (14h–16h UTC / 11h–13h BRT).
- **O dilema da mesa (*trade-off*):** liquidez e volatilidade caminham juntas (**Spearman ρ = 0,83** entre as 24 horas e **0,79** minuto a minuto). Entrar às 15h UTC reduz o impacto de livro, mas expõe uma ordem única a oscilações maiores.
- **Decisão:** executar ordens institucionais dentro da janela líquida **sempre em lotes fatiados (TWAP/VWAP)**, nunca em ordem única a mercado.

---

## Ato II — O Choque (Bybit 21/02) e a Escalada ao Pânico (24–25/02) (P2)
Na sexta-feira **21/02**, o ataque hacker à corretora Bybit (≈ US$ 1,5 bilhão em ETH) desencadeou uma mudança abrupta de regime. O BTC caiu de **US$ 99.475** (21/02) para **US$ 86.051** (25/02), uma queda de **−13,5 %** em quatro dias, com **saldo vendedor líquido em todos os 7 dias**.

| Métrica | Comparação Estresse (21, 24, 25/02) vs. Dia Útil | Implicação para a Mesa |
|---|---|---|
| **Volume financeiro diário** | **2,7×** o de um dia útil normal (25/02 atingiu US$ 7 bi) | Maior profundidade absoluta, porém acompanhada de fluxo unidirecional |
| **Volatilidade realizada diária** | **2,0×** a de um dia útil normal | Limites fixos em bps ou dólar quebram em dias de estresse |
| **Contagem de negócios** | **25/02 teve 10,3 milhões de negócios** (37 % da semana em 1 dia) | Sistemas de ingestão precisam suportar picos **≥ 4×** a carga normal |
| **Ordens agressoras ≥ US$ 100 mil** | Quase **10 mil ordens** em 25/02 (**4,5×** um dia útil normal) | Fluxo institucional acelera na venda e consome múltiplos níveis do livro |

Além disso, a microestrutura revela **concentração extrema**:
- **83 %** dos negócios individuais valem menos de US$ 100 (mediana de ≈ US$ 6, dominada por robôs), somando apenas **1,5 %** do valor.
- Negócios **≥ US$ 10 mil** são apenas **1,42 %** da contagem, mas concentram **59,8 %** de todo o volume financeiro.
- Em dias normais ou de estresse, a distribuição de retornos tem caudas muito mais pesadas que a Normal: **1,87 %** dos minutos superam $3\sigma$ — **≈ 7×** mais que os 0,27 % previstos pela curva normal.

---

## Ato III — Fluxo (OFI), Modelos Preditivos e Limites da Eficiência (P3)
Testamos se o desequilíbrio comprador/vendedor (*Order Flow Imbalance*, OFI) e atributos de atividade e volatilidade permitem antecipar o próximo intervalo ($t+1$) em validação **walk-forward expansiva** (21/02 a 25/02 fora da amostra, sem *look-ahead*):

1. **O que NÃO gera lucro direcional (eficiência de mercado):**
   - No **mesmo minuto**, OFI e retorno têm correlação de Pearson **0,388** (Spearman ≈ 0,55): o fluxo agressor empurra o preço no instante da execução.
   - No **minuto seguinte**, a correlação cai para **0,022** ($r^2 \approx 0{,}05\,\%$). O melhor modelo direcional em `1min` (`Logit apenas OFI`) atinge ROC-AUC **0,536** e retorno bruto de **+0,36 bps** mesmo nos 10 % de sinais mais confiantes.
   - Em barras de **1 segundo (`1s`)**, o modelo não linear (`HistGradientBoosting completo`) atinge **78,1 % de acurácia** e **ROC-AUC de 0,837** nos segundos com variação de preço — mas esse acerto captura apenas o **rebote microestrutural (*bid-ask bounce*)** de ~1 tick, rendendo apenas **+0,11 bps brutos** por operação.
   - Frente às taxas *taker* da Binance spot (**2 a 10 bps** por perna), **nenhum sinal direcional sobrevive aos custos de transação**.

2. **O que FUNCIONA e gera valor imediato (previsão de volatilidade):**
   - A amplitude do próximo minuto (`range_bps`) é altamente previsível fora da amostra: `Ridge (completo)` alcança **$R^2 = 0{,}385$** e **Spearman $= 0{,}616$**, superando a média móvel de 15 min ($R^2 = 0{,}353$) e modelos baseados em árvores (`HGBR`: $R^2 = 0{,}314$), pois o modelo linear consegue **extrapolar choques extremos** durante o pânico de 25/02 além do máximo visto nos dias de treino.
   - Em `1s`, `Ridge (completo)` e `HGBR (completo)` também superam os baselines ingênuos (Spearman **0,43** vs. **0,35** da persistência).

---

## Matriz de Decisão Executiva para a Mesa

| Decisão da Mesa | Recomendação Baseada em Evidência |
|---|---|
| **Quando fatiar (TWAP/VWAP)** | Priorizar **14h–16h UTC (11h–13h BRT)** em dias normais; em dias de choque, monitorar deslocamentos fora do horário (ex.: pico da semana às 07h UTC de 25/02). |
| **Como calibrar risco e *slippage*** | Substituir limites estáticos por **limites dinâmicos indexados à volatilidade prevista (`Ridge`)** e realizada, preparados para saltos de **2×** na volatilidade e eventos $> 3\sigma$ 7× mais frequentes que a Normal. |
| **Como dimensionar infraestrutura** | Garantir capacidade de ingestão e roteamento para **4×–5×** o volume de negócios de um dia útil normal (10,3 milhões de *ticks*/dia). |
| **Como usar o OFI** | **Não** usar para *trading* direcional proprietário; usar apenas como **filtro passivo de *timing*** (evitar cruzar o *spread* no sentido oposto durante picos extremos de fluxo). |
