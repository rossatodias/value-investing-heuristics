# Manual do Projeto — Value Investing Heuristics (PO-236)

## 1. Visao Geral

Este projeto implementa um pipeline completo de **selecao de acoes de valor** baseado em criterios
fundamentalistas inspirados em Benjamin Graham. O pipeline inclui:

1. **ETL** dos demonstrativos financeiros (ITRs) da CVM.
2. **Calculo de indicadores** fundamentalistas (P/L, P/VPA, ROE, etc.).
3. **Screening** de ativos segundo limiares parametrizaveis.
4. **Otimizacao heuristica** dos limiares via Algoritmo Genetico (AG) e Recozimento Simulado (SA).
5. **Backtesting walk-forward purgado** com embargo para evitar data leakage.
6. **Avaliacao estatistica** com bootstrap, Sharpe deflacionado, e comparacao contra benchmark (Ibovespa).
7. **Visualizacoes** academicas dos resultados.

---

## 2. Arquitetura dos Modulos

```
src/value_investing_heuristics/
├── __init__.py          # Pacote raiz
├── cli.py               # Interface de linha de comando (entry-point: vih)
├── config.py            # Constantes, bounds dos parametros, configuracao do backtest
├── data.py              # ETL: carga dos ITRs, normalizacao, signal dates
├── indicators.py        # Calculo de indicadores fundamentalistas
├── screening.py         # Filtro de ativos por limiares (theta)
├── mapping.py           # Mapeamento CNPJ -> ticker (Fundamentus + template)
├── prices.py            # Download de precos ajustados (Yahoo Finance)
├── cdi.py               # Busca da taxa CDI (BCB, serie 4389) para Rf
├── ibrx100.py           # Composicao historica do IBrX-100 (B3)
├── optimizers.py        # AG e SA com TrialLogger para auditoria
├── backtest.py          # Walk-forward purgado com embargo
├── metrics.py           # Sharpe, Sortino, drawdown, bootstrap CI, etc.
├── plotting.py          # Graficos (convergencia, retorno, drawdown, etc.)
└── reporting.py         # Geracao do relatorio markdown
```

### Fluxo de dados

```
itr_completo.csv
    │
    ▼
[data.py] ─── load_itr_csv + add_signal_dates
    │
    ▼
[indicators.py] ─── add_fundamental_indicators
    │
    ▼
fundamentals.csv (data/processed/)
    │
    ├──▶ [mapping.py] ─── CNPJ -> ticker
    │         │
    │         ▼
    │    cnpj_ticker_map.csv (data/raw/)
    │
    ├──▶ [prices.py] ─── Yahoo Finance
    │         │
    │         ▼
    │    prices.csv (data/raw/)
    │
    ├──▶ [cdi.py] ─── BCB API
    │         │
    │         ▼
    │    cdi.csv (data/processed/)
    │
    ├──▶ [ibrx100.py] ─── B3 API
    │         │
    │         ▼
    │    ibrx100_history.csv (data/processed/)
    │
    └──▶ [backtest.py]
              │
              ├── [screening.py] + [optimizers.py]
              │
              ▼
         backtest_summary.csv
         backtest_selections.csv
         backtest_trials.csv
         backtest_report.md
         outputs/plots/*.png
```

---

## 3. Arquivos de Entrada Necessarios

| Arquivo                | Descricao                                          | Como obter                               |
|------------------------|----------------------------------------------------|------------------------------------------|
| `itr_completo.csv`     | Demonstrativos ITR consolidados da CVM             | Baixar do portal de dados abertos da CVM |
| `data/raw/cnpj_ticker_map.csv` | Mapeamento CNPJ -> ticker na B3              | `vih fetch-mapping` (automatico)         |
| `data/raw/prices.csv`  | Precos ajustados (Yahoo Finance)                   | `vih fetch-prices` (automatico)          |
| `data/processed/cdi.csv` | Serie CDI anualizada (BCB)                       | `vih fetch-cdi` (automatico)             |
| `data/processed/ibrx100_history.csv` | Composicao historica IBrX-100      | `vih fetch-ibrx100` (automatico)         |

> **Nota:** Somente o `itr_completo.csv` precisa ser obtido manualmente. Todos os outros
> arquivos sao gerados automaticamente pelos subcomandos do `vih`.

---

## 4. Configuracao do Ambiente Virtual

### Linux / WSL

```bash
cd /home/rossato/comp/po236/ExameIA

# Criar ambiente virtual
python3 -m venv .venv

# Ativar
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Instalar o pacote em modo editavel (necessario para o entry-point 'vih')
pip install -e .

# Verificar que funciona
vih --help
```

### Windows PowerShell

```powershell
cd C:\caminho\para\ExameIA

python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
pip install -e .

vih --help
```

> Se `vih` nao for reconhecido apos `pip install -e .`, use:
> `python -m value_investing_heuristics.cli` no lugar de `vih`.

---

## 5. Guia de Execucao Completo (passo a passo)

### Passo 1: Preparar os dados fundamentalistas

```bash
vih prepare --input itr_completo.csv
```

- Le o CSV bruto dos ITRs da CVM.
- Calcula `signal_date = period_end + 45 dias` (lag regulatorio).
- Calcula indicadores fundamentalistas: P/L, P/VPA, ROE, margem liquida, etc.
- Salva em `data/processed/fundamentals.csv`.

### Passo 2: Mapear CNPJ para ticker

```bash
vih fetch-mapping
```

- Usa scraping do Fundamentus para resolver CNPJ -> ticker.
- Resultado: `data/raw/cnpj_ticker_map.csv`.
- **Importante:** validar manualmente o mapeamento. O scraper e conservador.

### Passo 3: Baixar precos ajustados

```bash
vih fetch-prices --start 2021-01-01
```

- Baixa precos ajustados de fechamento via Yahoo Finance para todos os tickers mapeados + benchmark (^BVSP).
- Resultado: `data/raw/prices.csv`.

### Passo 4: Baixar CDI (taxa livre de risco)

```bash
vih fetch-cdi --start 2020-01-01
```

- Busca a serie 4389 (CDI anualizada base 252) do BCB via API publica.
- Resultado: `data/processed/cdi.csv`.
- Se nao executado, o backtest usa Rf=0 (com aviso).

### Passo 5: Baixar composicao do IBrX-100

```bash
vih fetch-ibrx100 --start-year 2021
```

- Busca a carteira teorica do IBrX-100 (IBXX) da B3 para cada quadrimestre.
- Resultado: `data/processed/ibrx100_history.csv`.
- Se nao executado, o backtest nao filtra por survivorship bias (com aviso).
- **Nota:** a API da B3 pode nao retornar dados para anos muito antigos.

### Passo 6: Executar o backtest

```bash
vih backtest --cost-bps 10 --seed 42
```

Flags opcionais:
- `--cdi <caminho>` — caminho alternativo para o CSV de CDI.
- `--ibrx-history <caminho>` — caminho alternativo para o historico IBrX-100.
- `--no-plots` — pular geracao de graficos.
- `--plots-dir <pasta>` — pasta de destino dos graficos.
- `--cost-bps <valor>` — custo de transacao em basis points.

### Passo 7: Verificar resultados

Saidas geradas em `outputs/`:

| Arquivo                        | Conteudo                                                |
|--------------------------------|---------------------------------------------------------|
| `backtest_summary.csv`         | Metricas por fold/estrategia (Sharpe, retorno, etc.)    |
| `backtest_selections.csv`      | Ativos selecionados em cada periodo                     |
| `backtest_trials.csv`          | Log de todas tentativas do AG/SA (auditoria)            |
| `backtest_report.md`           | Relatorio markdown formatado                            |
| `plots/convergence_*.png`      | Curvas de convergencia do AG por fold                   |
| `plots/sa_trajectory_*.png`    | Trajetoria do SA (fitness + temperatura)                |
| `plots/cumulative_returns.png` | Retorno acumulado comparativo                           |
| `plots/drawdown.png`           | Drawdown por estrategia                                 |
| `plots/sharpe_comparison.png`  | Barras de Sharpe com IC 95% (bootstrap)                 |
| `plots/portfolio_composition.png` | N. de ativos e turnover por fold                     |

### Execucao completa (tudo de uma vez)

```bash
vih run-all --input itr_completo.csv --cost-bps 10
```

Executa `prepare` seguido de `backtest` com configuracoes padrao.

> **Pre-requisito:** os arquivos de mapeamento (`cnpj_ticker_map.csv`), precos
> (`prices.csv`), CDI (`cdi.csv`) e IBrX-100 (`ibrx100_history.csv`) devem existir.
> Execute os passos 2-5 antes do `run-all`.

---

## 6. Descricao dos Modulos

### config.py

Define constantes globais:
- `THETA_BOUNDS`: limites de busca para cada indicador (AG/SA).
  - `max_pvpa`: `(0.3, 0.7)` — margem de seguranca da proposta.
- `GRAHAM_BASELINE`: limiares fixos do baseline Graham classico.
  - `max_pvpa`: `1.5` — criterio classico (The Intelligent Investor, Cap. 14).
- `BacktestConfig`: numero de periodos de treino/embargo/validacao/teste.

### data.py

- `load_itr_csv()`: carrega e normaliza o CSV da CVM.
- `add_signal_dates()`: calcula `signal_date = period_end + lag_days`.
- `dataset_profile()`: resume o dataset (contagens, cobertura temporal).

### indicators.py

- `add_fundamental_indicators()`: calcula P/L, P/VPA, ROE, margem liquida,
  liquidez corrente, alavancagem (divida liquida / EBITDA proxy), dividend yield.
- `winsorize_training_frame()`: winsoriza indicadores no treino (percentis 1-99).

### screening.py

- `screen_period()`: filtra ativos por limiares (`theta`).
  - Aplica relaxamento progressivo se `n_assets < min_assets`.
  - Retorna `ScreeningResult` com tickers e regras relaxadas.

### mapping.py

- `fetch_fundamentus_mapping()`: scraping do Fundamentus para CNPJ -> ticker.
- `mapping_template()`: gera template CSV para preenchimento manual.
- `merge_mapping()`: adiciona coluna `ticker` ao DataFrame de fundamentals.

### prices.py

- `download_yahoo_prices()`: baixa precos ajustados via yfinance.
- `price_return()`: retorno entre duas datas para um ticker.
- `price_on_or_after()`: preco no dia ou primeiro dia util apos.

### cdi.py

- `fetch_cdi_series()`: busca serie 4389 do BCB (CDI anualizada, base 252).
- `cdi_annual_rate_for_year()`: media anualizada do CDI para um ano.
- `cdi_period_rate()`: media anualizada do CDI para um intervalo de datas.

### ibrx100.py

- `fetch_ibrx100_portfolio()`: busca composicao atual via API da B3.
- `fetch_ibrx100_history()`: busca composicoes para multiplos anos/segmentos.
- `filter_by_ibrx100()`: filtra fundamentals para manter apenas tickers do IBrX-100.
- `tickers_for_period()`: retorna tickers do IBrX-100 para dado ano/trimestre.

### optimizers.py

- `genetic_algorithm()`: AG com crossover, mutacao e elitismo.
- `simulated_annealing()`: SA com perturbacao e schedule exponencial.
- `TrialLogger`: registra cada tentativa em CSV para auditoria (data snooping).
- `OptimizerResult`: theta otimo, fitness, n. tentativas, historico de convergencia.

### backtest.py

- `make_purged_walk_forward_folds()`: gera folds com treino-embargo-validacao-embargo-teste.
- `period_returns()`: retornos por periodo para um dado theta.
- `run_backtest()`: executa o pipeline completo:
  - Filtra universo por IBrX-100 (se disponivel).
  - Para cada fold: treina AG + SA, valida, testa.
  - Calcula metricas com bootstrap e CDI como Rf.
  - Retorna `BacktestResult` com summary, selecoes, convergencia e retornos.

### metrics.py

- `sharpe_ratio()`, `sortino_ratio()`, `max_drawdown()`, etc.
- `bootstrap_sharpe_ci()`: IC 95% via 1000 reamostras bootstrap.
- `summarize_returns()`: agrega todas as metricas em um dicionario.
- `deflated_sharpe_proxy()`: penaliza Sharpe pelo numero de tentativas.

### plotting.py

- `plot_convergence()`: fitness vs geracao (AG).
- `plot_sa_trajectory()`: fitness + temperatura vs iteracao (SA).
- `plot_cumulative_returns()`: riqueza acumulada comparativa.
- `plot_drawdown()`: drawdown por estrategia.
- `plot_sharpe_comparison()`: barras de Sharpe com barras de erro (bootstrap).
- `plot_portfolio_composition()`: n. ativos e turnover por fold.
- `generate_all_plots()`: gera todos os graficos padrao.

### reporting.py

- `write_backtest_report()`: gera relatorio markdown com tabelas, notas e limitacoes.

---

## 7. Interpretacao dos Resultados

### Colunas do `backtest_summary.csv`

| Coluna                     | Descricao                                                  |
|----------------------------|------------------------------------------------------------|
| `fold_id`                  | Identificador do fold walk-forward                         |
| `strategy`                 | `ga`, `sa`, `graham_fixed`, ou `chosen_<ga|sa>`            |
| `cumulative_return`        | Retorno acumulado no periodo de teste                      |
| `annualized_return`        | Retorno anualizado                                         |
| `annualized_volatility`    | Volatilidade anualizada                                    |
| `sharpe`                   | Sharpe ratio (com CDI como Rf)                             |
| `sharpe_ci_lower`          | Limite inferior do IC 95% (bootstrap, 1000 reamostras)     |
| `sharpe_ci_upper`          | Limite superior do IC 95% (bootstrap)                      |
| `deflated_sharpe_proxy`    | Sharpe penalizado pelo numero de tentativas                |
| `sortino`                  | Sortino ratio                                              |
| `max_drawdown`             | Maximo drawdown (pior queda pico-vale)                     |
| `jensen_alpha`             | Alpha de Jensen vs benchmark                               |
| `beta_vs_benchmark`        | Beta vs Ibovespa                                           |
| `avg_assets`               | Numero medio de ativos no portfolio                        |
| `avg_turnover`             | Turnover medio entre periodos                              |
| `risk_free_rate`           | Taxa Rf usada (CDI medio anualizado)                       |
| `theta_*`                  | Valores dos limiares otimizados                            |

### Intervalos de confianca (bootstrap)

Os campos `sharpe_ci_lower` e `sharpe_ci_upper` representam o intervalo de confianca
de 95% do Sharpe ratio, calculado por **reamostragem bootstrap** (1000 iteracoes com
reposicao). Dado o numero limitado de periodos de teste (tipicamente 1-3 por fold),
esses intervalos devem ser interpretados com **cautela** e tem carater **exploratorio**.

---

## 8. Testes

```bash
pytest -v
```

Os testes unitarios estao em `tests/`. Para rodar um teste especifico:

```bash
pytest tests/test_metrics.py -v
```

---

## 9. Resolucao de Problemas

| Problema                          | Solucao                                                  |
|-----------------------------------|----------------------------------------------------------|
| `vih` nao encontrado              | Use `python -m value_investing_heuristics.cli`           |
| CDI file not found                | Execute `vih fetch-cdi` antes do backtest                |
| IBrX-100 history not found        | Execute `vih fetch-ibrx100` antes do backtest            |
| Erro de conexao ao BCB            | Verifique conectividade; a API tem rate limiting          |
| Erro de conexao a B3              | A API publica pode estar instavel; tente novamente        |
| Poucos ativos selecionados        | O screening relaxa regras automaticamente (ver `relaxed_rules`) |
| Graficos nao gerados              | Verifique que matplotlib esta instalado; use `--no-plots` para pular |
