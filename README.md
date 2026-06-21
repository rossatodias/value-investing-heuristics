# value-investing-heuristics

Projeto reprodutivel para selecao de acoes de valor com criterios inspirados em Benjamin Graham, busca heuristica e backtesting com controles contra erros comuns.

> Para instrucoes detalhadas de uso, consulte o [manual.md](manual.md).

## Ambiente

As dependencias sao gerenciadas exclusivamente pelo `pyproject.toml`. Instale o
pacote em modo editavel (inclui as libs de runtime e, com `[dev]`, o pytest):

```bash
# Linux / WSL
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

```powershell
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Interface web

```bash
python main.py            # ou: vih-web
# abre em http://localhost:5050  (porta configuravel via VIH_PORT)
```

A interface executa as etapas do pipeline e exibe os resultados. Para rodar
direto pela linha de comando, use a CLI `vih` abaixo.

## Pipeline pela CLI

```bash
vih prepare                  # 1. fundamentals a partir de data/raw/itr_completo.csv
vih fetch-mapping            # 2. mapeamento CNPJ -> ticker
vih fetch-prices             # 3. precos ajustados
vih fetch-cdi                # 4. dados auxiliares (CDI + IBrX-100)
vih fetch-ibrx100
vih backtest --cost-bps 10   # 5. backtest completo
```

## Decisoes implementadas

- `lucroOper` e usado como proxy de EBITDA em `divida_liquida_lucro_oper_proxy`.
- `lucroOper <= 0` invalida o indicador de alavancagem.
- Os sinais usam `signal_date = period_end + 45 dias`, salvo substituicao por data real de divulgacao.
- A execucao simulada ocorre somente no proximo fechamento depois de `signal_date`.
- O protocolo de backtesting usa treino, embargo, validacao, embargo e teste.
- O teste nao escolhe parametros; a validacao escolhe entre AG e SA.
- Todas as tentativas dos otimizadores sao registradas em `outputs/backtest_trials.csv`.
- A estrategia principal e long-only e igualmente ponderada.
- Custos de transacao entram por turnover em bps.
- **Bootstrap Sharpe:** intervalos de confianca do Sharpe sao calculados via bootstrap (1000 reamostras, IC 95%).
- **CDI como Rf:** a taxa livre de risco e obtida da serie 4389 do BCB (CDI anualizada base 252).
- **Survivorship bias:** o universo e filtrado pela composicao historica do IBrX-100 quando disponivel.

### Nota sobre P/VPA e baseline de Graham

O otimizador (AG/SA) busca o limiar de P/VPA no intervalo `[0.3, 0.7]`, conforme
definido na proposta de pesquisa para garantir margem de seguranca. Ja o baseline
fixo de Graham (`graham_fixed`) utiliza P/VPA <= 1.5, coerente com o criterio
classico de Benjamin Graham (*The Intelligent Investor*, Cap. 14). O baseline nao
e otimizado e nao esta sujeito aos bounds de busca do AG/SA. Essa divergencia e
intencional: o baseline serve como comparacao com a doutrina classica, enquanto o
otimizador explora limiares mais restritivos.

## Saidas

- `data/processed/fundamentals.csv`
- `data/processed/cdi.csv` — serie CDI anualizada do BCB
- `data/processed/ibrx100_history.csv` — composicao historica do IBrX-100
- `data/raw/cnpj_ticker_map.csv`
- `data/raw/prices.csv`
- `outputs/data_profile.json`
- `outputs/backtest_summary.csv`
- `outputs/backtest_selections.csv`
- `outputs/backtest_trials.csv`
- `outputs/backtest_report.md`
- `outputs/plots/` — graficos de convergencia, retorno acumulado, drawdown, etc.

## Observacoes

O de/para CNPJ -> ticker precisa ser validado. O scraper de Fundamentus e um fallback publico e conservador, mas qualquer linha sem correspondencia exata permanece marcada como pendente. O indicador `deflated_sharpe_proxy` e uma penalizacao conservadora pelo numero de tentativas, nao a formula completa do Deflated Sharpe Ratio.