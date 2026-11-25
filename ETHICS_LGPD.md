# Ética, Conformidade Legal (LGPD), Licença e Limitações — Projeto A3

Este documento consolida a análise de governança de dados, conformidade com a **Lei Geral de Proteção de Dados Pessoais (LGPD — Lei nº 13.709/2018)**, aderência à licença da fonte, vieses metodológicos e riscos operacionais do uso de sinais de mercado para o projeto **Microestrutura do Bitcoin (BTC/USDT) em uma semana de estresse**.

---

## 1. Conformidade com a LGPD (Lei nº 13.709/2018)

### 1.1 Ausência de dados pessoais (Art. 5º, I)
Nos termos do **art. 5º, inciso I, da LGPD**, dado pessoal é toda *"informação relacionada a pessoa natural identificada ou identificável"*. A base analisada (`sample_BTC_2025-02-19_to_2025-02-26.parquet`, 27.925.338 registros) contém exclusivamente registros públicos de execução no livro de ofertas à vista (*spot*) de BTC/USDT da Binance:

| Campo | Natureza jurídica / técnica | Contém dado pessoal? |
|---|---|---|
| `trade_id` | Número sequencial atribuído pelo motor de casamento (*matching engine*) da corretora | **Não.** Identifica um evento de execução pública de mercado, sem vínculo público com conta, CPF, CNPJ ou carteira |
| `exchange_ts` (`ts`) | Carimbo temporal (UTC, precisão de milissegundo) da execução pública | **Não.** Metadado temporal de mercado |
| `price`, `quantity` | Preço (USDT) e volume (BTC) executados no livro público | **Não.** Informação pública de formação de preço |
| `aggressor_side` (`side`) | Direção agregada do agressor (`buy` / `sell`) no casamento da ordem | **Não.** Dinâmica impessoal de oferta e demanda |
| `exchange`, `symbol` | Constantes técnicas (`binance`, `BTCUSDT`) convertidas em metadados | **Não.** |
| `ingest_ts` | Timestamp de coleta do fornecedor (100 % inválido: datas de 2032–2037) | **Não** — e descartado integralmente na etapa de limpeza |

**Conclusão jurídica:** Não há titular identificável nem dados pessoais sensíveis (art. 5º, II). O tratamento dos dados ocorre estritamente sobre **dados públicos de mercado anônimos e agregados** (art. 7º, §§ 3º e 4º, por analogia ao caráter público e não pessoal das cotações de bolsa/mercado à vista), estando fora do escopo de dados pessoais identificáveis da LGPD.

### 1.2 Risco residual de reidentificação por cruzamento externo
Embora a base isolada seja impessoal, em um ambiente real de mesa de execução institucional existe um risco conceitual de **reidentificação indireta** caso o registro público (`trade_id`, `ts`, `quantity`) seja cruzado internamente com:
- logs proprietários de ordens da própria mesa (OMS/EMS);
- registros internos de clientes (KYC/AML) em corretoras centralizadas;
- ou *clusters* *on-chain* associados a depósitos/saques próximos ao instante da ordem.

**Mitigação adotada no projeto:**
1. O projeto opera **exclusivamente** sobre o fluxo público anônimo, sem nenhum cruzamento com bases cadastrais, carteiras (*wallets*) ou logs de clientes.
2. As agregações analíticas (`bars_1min`, `bars_1s`) e o dashboard operam em nível temporal agregado, reduzindo ainda mais qualquer granularidade individual.
3. Mesmo a tabela `taker_orders` reconstrói apenas ordens agressoras anônimas por contiguidade temporal, sem atribuição de autoria.

### 1.3 Governança e minimização (Princípios da Necessidade e Segurança — Art. 6º)
Mesmo sem dados pessoais, aplicamos boas práticas de engenharia alinhadas aos princípios da **necessidade** e **qualidade**:
- Remoção de colunas constantes (`exchange`, `symbol`), redundantes (`raw_side`, `aggressor_side`) e corrompidas (`ingest_ts`).
- Contrato explícito de qualidade (`validate_trades`) antes de qualquer consumo analítico ou preditivo.
- Consumo nos produtos derivados (modelagem e dashboard) exclusivamente a partir dos Parquets tratados em `data/processed/`.

---

## 2. Conformidade com a Licença da Fonte e Reprodutibilidade

### 2.1 Termos da fonte primária e secundária
- **Base secundária (dataset):** [`jalvart/bitcoin-tick-level-trade-data-free-sample`](https://huggingface.co/datasets/jalvart/bitcoin-tick-level-trade-data-free-sample), publicada pelo fornecedor *The Glitch List* no Hugging Face, sob **licença de uso pessoal e acadêmico, com proibição de redistribuição**.
- **Fonte primária de validação:** [Binance Public Data (`data.binance.vision`)](https://data.binance.vision), utilizada exclusivamente para reconciliação minuto a minuto (candles oficiais de 1 minuto BTCUSDT) e verificação de integridade.

### 2.2 Controles técnicos implementados no repositório
1. **Sem redistribuição de dados:** o arquivo [`.gitignore`](.gitignore) bloqueia explicitamente a pasta `data/` (`data/raw/`, `data/external/`, `data/processed/`). Nenhum arquivo Parquet bruto ou processado é versionado no Git.
2. **Download direto na origem com imutabilidade:** o código ([`src/config.py`](src/config.py) e [`src/etl.py`](src/etl.py)) fixa o commit exato do repositório no Hugging Face (`c90f6087f5975daec7fe80e6ed110dd19108bd5c`) e valida o resumo criptográfico **SHA-256** (`2a660248...d44070a`) antes de qualquer processamento.
3. **Finalidade estritamente acadêmica:** todo o código, documentação e dashboard destinam-se à avaliação da unidade curricular *Análise de Dados e Big Data (0005073)* e à demonstração metodológica para cenário simulado de mesa de execução.

---

## 3. Vieses e Limitações dos Dados e do Método

| Dimensão | Limitação observada | Impacto na interpretação |
|---|---|---|
| **Viés de seleção temporal (semana atípica)** | O recorte cobre apenas 7 dias (19–25/02/2025), marcados pelo ataque à Bybit (21/02, ≈ US$ 1,5 bi) e queda de −13,5 % no BTC. Todos os 7 dias tiveram saldo vendedor líquido. | Padrões de volume, volatilidade e distribuição direcional **não representam** semanas neutras ou de alta (*bull market*). |
| **Única corretora (Binance Spot)** | Embora seja a maior corretora à vista em liquidez global, reflete apenas o perfil de fluxo de seus participantes. | Corretoras reguladas nos EUA (ex.: Coinbase) ou derivativos (perpétuos) podem apresentar horários de pico e profundidade distintos. |
| **Único par (BTC/USDT)** | Par mais líquido do mercado cripto, cotado contra *stablecoin* pareada ao dólar. | Altcoins e pares contra moeda fiduciária direta (BTC/USD, BTC/BRL) têm *spreads* e lacunas de liquidez muito mais severos. |
| **Amostra horária curta (n = 7 por hora)** | Para cada hora UTC do dia há apenas 7 observações diárias (sendo 3 de estresse). | As medianas horárias (ex.: pico às 15h UTC = 4,2× o vale às 06h UTC) são **indicativas**, não estatisticamente definitivas para todo o ano. |
| **Reconstrução aproximada de ordens agressoras** | `taker_orders` agrupa negócios consecutivos com mesmo `ts` (ms) e mesmo `side`. | Duas ordens independentes de participantes distintos executadas no mesmo milissegundo e mesmo lado são fundidas em uma única ordem sintética. |
| **Qualidade original do fornecedor (`ingest_ts`)** | `ingest_ts` veio 100 % corrompido (datas futuras entre 2032 e 2037) e o nome do arquivo declara `26/02` (data exclusiva). | Impede qualquer análise de latência de coleta; exigiu descarte formal e validação cruzada integral contra a Binance. |
| **Granularidade sem livro completo (L1/L2)** | A base contém apenas negócios executados (*tick trades*), sem cotações de melhor compra/venda (*BBO*) ou profundidade de livro (*order book*). | Não é possível medir diretamente o *bid-ask spread* cotado ou liquidez em repouso, apenas o impacto realizado (*book walk*) das ordens que consumiram o livro. |

---

## 4. Riscos do Uso de Sinais de Mercado e Modelos Preditivos

Mesmo em uma base limpa e validada, transformar análises estatísticas em decisões automatizadas de mesa envolve riscos críticos:

1. **Ilusão preditiva vs. custos de transação (*economic significance*):**
   - Como demonstrado na validação *walk-forward*, mesmo quando um modelo atinge acurácia ou ROC-AUC marginalmente acima de 50 % na previsão direcional (ou correlação OFI × retorno seguinte ≈ 0,02), o retorno bruto esperado por operação é ordens de grandeza inferior aos custos reais de execução (*taker fee* na Binance spot entre 2 e 10 bps por perna, somados a *slippage*).
   - **Risco:** operar sinais direcionais fracos gera prejuízo líquido garantido por excesso de giro (*overtrading*).
2. **Quebra de regime (*regime shift*):**
   - Modelos treinados em dias calmos (22–23/02) subestimam drasticamente a escala da volatilidade e o tamanho das ordens durante choques de cauda (24–25/02).
   - **Mitigação:** reavaliação contínua em janelas *walk-forward*, limites rígidos (*circuit breakers*) baseados em volatilidade realizada/prevista e nunca confiar apenas em médias históricas (como demonstrado pela falha da regra de IQR e pela razão média/mediana > 100× em `notional_usd`).
3. **Vazamento de futuro (*look-ahead bias*) e *data snooping*:**
   - Em microestrutura de alta frequência (1 s / 1 min), qualquer erro sutil — como interpolação linear em segundos vazios, normalização global antes da divisão treino/teste ou uso de `shift(-1)` em atributos — cria acurácia artificial que desaparece em produção.
   - **Mitigação:** o pipeline em [`src/modeling.py`](src/modeling.py) usa preenchimento causal (`ffill`), escalonamento restrito à dobra de treino (`Pipeline`) e testes automatizados garantindo invariância a perturbações futuras.
4. **Risco de impacto próprio e retroalimentação (*feedback loop*):**
   - Uma mesa que executa ordens grandes no mesmo horário de pico ou reage mecanicamente ao OFI sem fatiamento (TWAP/VWAP) passa a gerar ela própria o desequilíbrio observado, elevando seu *slippage*.
5. **Uso responsável pela mesa (Human-in-the-Loop):**
   - Os modelos deste projeto são recomendados **exclusivamente como apoio à decisão** (dimensionamento de janelas TWAP/VWAP e calibração dinâmica de limites de risco pela previsão de volatilidade), e **não** como motor autônomo de *trading* direcional.
