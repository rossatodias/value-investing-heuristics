# VIH Frontend — Interface Web

Interface grafica para o CLI `vih` (Value Investing Heuristics).

**Nao altera a logica do backend.** Apenas invoca os comandos CLI via subprocess e exibe os resultados.

## Requisitos

- Python 3.11+
- Dependencias instaladas (`pip install -r requirements.txt` na raiz do projeto)
- Pacote `vih` instalado em modo editavel (`pip install -e .` na raiz)

## Como Executar

```bash
# A partir da raiz do projeto
cd frontend
python api_server.py
```

Abra no navegador: **http://localhost:5050**

Porta alternativa:
```bash
VIH_PORT=8080 python api_server.py
```

## Estrutura

```
frontend/
  api_server.py          # Servidor Flask (API bridge + static files)
  templates/
    index.html           # SPA entry point
  static/
    css/
      style.css          # Design system (Quant Dark theme)
    js/
      components.js      # Componentes reutilizaveis (icones, tabelas, terminal)
      app.js             # Router SPA e estado global
      pipeline.js        # Pagina Pipeline (5 etapas)
      dashboard.js       # Pagina Dashboard (plots, metricas, relatorio)
      tutorial.js        # Pagina Tutorial (manual.md renderizado)
```

## Telas

1. **Pipeline** — Execucao guiada das 5 etapas do CLI com logs em tempo real
2. **Dashboard** — KPIs, graficos, tabelas de metricas e relatorio do backtest
3. **Manual** — Documentacao completa com navegacao lateral e busca

## Endpoints da API

| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/` | Pagina principal (SPA) |
| GET | `/api/status` | Status dos arquivos de dados |
| GET | `/api/outputs/<path>` | Serve arquivos de `outputs/` |
| GET | `/api/manual` | Conteudo do `manual.md` |
| GET | `/api/data-profile` | Perfil do dataset (`data_profile.json`) |
| POST | `/api/run-step` | Executa uma etapa do pipeline (SSE streaming) |
