# TODO — Projeto A3 (BTC/USDT Microestrutura)

Checklist de entregas e pendências do projeto **Análise de Dados e Big Data (0005073)**, organizado com base em [`README.md`](README.md), [`CHECKPOINT_1.md`](CHECKPOINT_1.md) e [`notebooks/A3_CP2_auditoria_etl_eda.ipynb`](notebooks/A3_CP2_auditoria_etl_eda.ipynb).

---

## Concluído (Checkpoints 1 e 2)

- [x] **Checkpoint 1 — Diagnóstico & Escopo** ([`CHECKPOINT_1.md`](CHECKPOINT_1.md))
  - [x] Definição de cenário (mesa de execução), período (19–25/02/2025) e perguntas de negócio (P1–P3)
  - [x] Documentação da base do Hugging Face (commit `c90f6087` e SHA-256) e dicionário de dados
  - [x] Visão preliminar de ética, licença e LGPD
- [x] **Checkpoint 2 — Auditoria, ETL & EDA Inicial** ([`notebooks/A3_CP2_auditoria_etl_eda.ipynb`](notebooks/A3_CP2_auditoria_etl_eda.ipynb))
  - [x] Extração com verificação de integridade (SHA-256)
  - [x] Auditoria de qualidade do dado bruto (`ingest_ts` futuro, tipos, redundâncias e duplicatas aparentes de execuções parciais)
  - [x] Transformação, criação de variáveis derivadas e contrato de qualidade pós-limpeza
  - [x] Validação cruzada minuto a minuto contra os candles oficiais da Binance (10.080/10.080 minutos)
  - [x] Geração dos Parquets em `data/processed/` (`trades_clean`, `bars_1min`, `bars_1s`, `taker_orders`)
  - [x] EDA inicial e respostas preliminares para P1, P2 e P3

---

## Pendências de Documentação (CP1 e CP2)

- [ ] Preencher nomes, RAs e papéis dos integrantes em [`CHECKPOINT_1.md`](CHECKPOINT_1.md)
- [ ] Preencher nomes e RAs dos integrantes no cabeçalho de [`notebooks/A3_CP2_auditoria_etl_eda.ipynb`](notebooks/A3_CP2_auditoria_etl_eda.ipynb)

---

## Checkpoint 3 — Entrega Final & Defesa

### 1. Código Consolidado
- [ ] Extrair e consolidar funções reutilizáveis do ETL (`build_bars`, `fill_bar_gaps`, `validate_trades`) a partir do notebook
- [ ] Consumir os arquivos já processados em `data/processed/` na etapa de modelagem e dashboard
- [ ] Atualizar [`requirements.txt`](requirements.txt) caso novas bibliotecas sejam adotadas no CP3 (ex.: modelagem e dashboard)

### 2. Modelagem Preditiva
- [ ] Definir alvo e formulação do problema:
  - [ ] Previsão de volatilidade do próximo intervalo (regressão)
  - [ ] Previsão de direção do retorno (classificação)
- [ ] Construir *features* defasadas (OFI, volume, amplitude, etc.) sem vazamento de futuro (*look-ahead*)
- [ ] Testar horizontes mais curtos (barras de `1s` além de `1min`), combinações de variáveis e modelos não lineares
- [ ] Implementar validação temporal (*walk-forward*)
- [ ] Avaliar métricas e discutir viabilidade operacional do sinal para a mesa de execução

### 3. Dashboard Interativo
- [ ] Implementar dashboard interativo com os indicadores de **P1** (liquidez intradiária), **P2** (dias de estresse e faixas de tamanho) e **P3** (OFI e retornos)
- [ ] Adicionar filtros interativos por dia e hora (UTC / BRT)
- [ ] Documentar instruções de execução do dashboard no [`README.md`](README.md)

### 4. Data Storytelling
- [ ] Estruturar a narrativa **"da calmaria ao estresse"** voltada às decisões da mesa de execução
- [ ] Consolidar gráficos e principais métricas/achados (janelas de execução TWAP/VWAP, limites por volatilidade realizada e capacidade operacional)

### 5. Ética, Licença e LGPD
- [ ] Aprofundar análise de conformidade com a **LGPD** (ausência de dados pessoais / art. 5º, I)
- [ ] Formalizar conformidade com a licença da fonte (uso acadêmico, sem redistribuição de `data/`)
- [ ] Documentar vieses e limitações (semana atípica de estresse, única corretora Binance, único par BTC/USDT, 7 observações por hora, reconstrução aproximada de ordens agressoras) e riscos do uso de sinais de mercado

### 6. Slides e Entrega Final
- [ ] Criar apresentação (slides) para a defesa final
- [ ] Atualizar a tabela de entregas e a estrutura de pastas no [`README.md`](README.md)
- [ ] Revisar reprodutibilidade de ponta a ponta (notebook(s), código consolidado e dashboard) antes da entrega
