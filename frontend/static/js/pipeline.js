/* =============================================================
   VIH — Pipeline Stepper Page
   5-step execution flow with real-time logs
   ============================================================= */

(function () {
  'use strict';

  const STEPS = [
    {
      id: 1,
      label: 'Preparacao de Dados',
      command: 'prepare',
      description: 'Processa ITRs da CVM e calcula indicadores fundamentalistas (P/L, P/VPA, ROE, etc.).',
      input: 'itr_completo.csv',
      output: 'data/processed/fundamentals.csv',
      iconKey: 'database',
    },
    {
      id: 2,
      label: 'Mapeamento CNPJ → Ticker',
      command: 'fetch-mapping',
      description: 'Resolve CNPJ para ticker via scraping do Fundamentus. Validar manualmente se houver pendencias.',
      input: 'data/processed/fundamentals.csv',
      output: 'data/raw/cnpj_ticker_map.csv',
      iconKey: 'link',
      warning: 'Linhas com status "pending" nao tem correspondencia exata. Revise manualmente.',
    },
    {
      id: 3,
      label: 'Precos Ajustados',
      command: 'fetch-prices',
      description: 'Baixa precos ajustados de fechamento via Yahoo Finance para todos os tickers mapeados + benchmark (^BVSP).',
      input: 'data/raw/cnpj_ticker_map.csv',
      output: 'data/raw/prices.csv',
      iconKey: 'dollarSign',
    },
    {
      id: 4,
      label: 'Dados Auxiliares (CDI + IBrX-100)',
      command: 'fetch-aux',
      description: 'Baixa serie CDI (taxa livre de risco, BCB) e composicao historica do IBrX-100 (B3).',
      input: 'APIs publicas (BCB + B3)',
      output: 'data/processed/cdi.csv, ibrx100_history.csv',
      iconKey: 'download',
    },
    {
      id: 5,
      label: 'Backtest Walk-Forward',
      command: 'backtest',
      description: 'Executa backtesting purgado com embargo, otimizacao heuristica (AG + SA) e comparacao com baseline Graham.',
      input: 'Todos os dados preparados',
      output: 'outputs/ (summary, selections, report, plots)',
      iconKey: 'activity',
      hasConfig: true,
    },
  ];

  const CONFIG_CARDS = [
    {
      title: 'Estrategia',
      value: 'Long-Only, igualmente ponderada',
      desc: 'Todos os ativos selecionados recebem peso igual no portfolio.',
      iconKey: 'target',
    },
    {
      title: 'Protocolo Walk-Forward',
      value: 'Treino → Embargo → Validacao → Embargo → Teste',
      desc: 'Divisao rigorosa para evitar data leakage entre conjuntos.',
      iconKey: 'shield',
    },
    {
      title: 'Otimizadores',
      value: 'AG + SA, P/VPA em [0.3, 0.7]',
      desc: 'Algoritmo Genetico e Simulated Annealing buscam o limiar otimo. Validacao escolhe o melhor.',
      iconKey: 'zap',
    },
    {
      title: 'Baseline Graham',
      value: 'P/VPA <= 1.5 (fixo, nao otimizado)',
      desc: 'Criterio classico de Benjamin Graham (The Intelligent Investor, Cap. 14) para comparacao.',
      iconKey: 'bookOpen',
    },
    {
      title: 'Taxa Livre de Risco',
      value: 'CDI (serie 4389 / BCB)',
      desc: 'Taxa CDI anualizada base 252 dias uteis, obtida da API publica do Banco Central.',
      iconKey: 'dollarSign',
    },
    {
      title: 'Survivorship Bias',
      value: 'Filtro IBrX-100',
      desc: 'Universo filtrado pela composicao historica do indice, quando disponivel.',
      iconKey: 'layers',
    },
  ];

  let activeStepIdx = 0;

  function renderPipeline(container, state) {
    activeStepIdx = state.activeStep || 0;

    container.innerHTML = `
      <div class="page-header">
        <h1 class="page-header__title">Pipeline de Execucao</h1>
        <p class="page-header__description">
          Execute as 5 etapas sequenciais para processar dados, otimizar e rodar o backtest.
        </p>
      </div>

      <div class="stepper" id="pipeline-stepper">
        ${renderStepperNodes(state)}
      </div>

      <div id="step-detail-container">
        ${renderStepDetail(activeStepIdx, state)}
      </div>
    `;

    attachStepperListeners(state);
  }

  function renderStepperNodes(state) {
    return STEPS.map((step, i) => {
      const stepState = state.pipelineSteps[i];
      const statusClass = stepState.status === 'completed' ? 'stepper__step--completed'
        : stepState.status === 'running' ? 'stepper__step--running'
        : stepState.status === 'error' ? 'stepper__step--error'
        : i === activeStepIdx ? 'stepper__step--active'
        : '';

      const circleContent = stepState.status === 'completed'
        ? VIH.Icons.check
        : stepState.status === 'error'
        ? VIH.Icons.x
        : step.id;

      const connector = i > 0
        ? `<div class="stepper__connector"></div>`
        : '';

      return `
        ${connector}
        <div class="stepper__step ${statusClass}" data-step="${step.id}" data-index="${i}">
          <div class="stepper__node">
            <div class="stepper__circle">${circleContent}</div>
            <div class="stepper__label">${step.label}</div>
          </div>
        </div>`;
    }).join('');
  }

  function renderStepDetail(idx, state) {
    const step = STEPS[idx];
    const stepState = state.pipelineSteps[idx];
    const isRunning = stepState.status === 'running';
    const isCompleted = stepState.status === 'completed';

    let configSection = '';
    if (step.hasConfig) {
      configSection = `
        <div class="section-divider"></div>
        <h4 style="margin-bottom: var(--space-md); font-size: 0.9rem; font-weight: 600; display: flex; align-items: center; gap: var(--space-sm);">
          <span style="width:18px;height:18px;flex-shrink:0;color:var(--accent-blue);display:inline-flex">${VIH.Icons.settings}</span>
          Configuracoes do Backtest
        </h4>
        <div class="config-grid">
          ${CONFIG_CARDS.map(c => `
            <div class="config-card">
              <div class="config-card__title">
                ${VIH.Icons[c.iconKey] || ''}
                ${c.title}
              </div>
              <div class="config-card__value">${c.value}</div>
              <div class="config-card__desc">${c.desc}</div>
            </div>`).join('')}
        </div>

        <div class="input-group" style="max-width: 280px; margin-bottom: var(--space-lg);">
          <label class="input-group__label">Custo de Transacao (bps)</label>
          <input type="number" class="input-field" id="cost-bps-input" value="${state.costBps}"
                 min="0" max="100" step="1" placeholder="Ex: 10">
        </div>`;
    }

    let warningSection = '';
    if (step.warning) {
      warningSection = VIH.createAlert(step.warning, 'warning');
    }

    return `
      <div class="card step-detail" style="margin-top: var(--space-lg);">
        <div class="card__body">
          <div class="step-detail__header">
            <div class="step-detail__number">${step.id}</div>
            <div class="step-detail__info">
              <h3>${step.label}</h3>
              <p>${step.description}</p>
            </div>
          </div>

          ${warningSection}

          <div class="step-detail__meta">
            <div class="step-detail__meta-item">
              ${VIH.Icons.folder}
              <span class="step-detail__meta-label">Input:</span>
              <span class="step-detail__meta-value">${step.input}</span>
            </div>
            <div class="step-detail__meta-item">
              ${VIH.Icons.fileText}
              <span class="step-detail__meta-label">Output:</span>
              <span class="step-detail__meta-value">${step.output}</span>
            </div>
          </div>

          ${configSection}

          <div class="step-detail__actions">
            <button class="btn btn--primary ${isRunning ? 'btn--disabled' : ''}" id="btn-run-step"
                    ${isRunning ? 'disabled' : ''}>
              ${isRunning ? '<span class="spinner spinner--sm"></span> Executando...' : VIH.Icons.play + ' Executar Etapa'}
            </button>
            ${isCompleted ? VIH.createBadge('Concluido', 'green') : ''}
            ${stepState.status === 'error' ? VIH.createBadge('Erro', 'red') : ''}
          </div>

          ${VIH.createTerminal('step-terminal', `vih ${step.command}`)}
        </div>

        <div class="card__footer">
          ${idx > 0 ? `<button class="btn btn--ghost btn--sm" id="btn-prev-step">${VIH.Icons.arrowRight.replace('points="12 5 19 12 12 19"', 'points="12 19 5 12 12 5"').replace('x1="5" y1="12" x2="19"', 'x1="19" y1="12" x2="5"')} Anterior</button>` : ''}
          <div style="flex:1"></div>
          ${idx < STEPS.length - 1 ? `<button class="btn btn--secondary btn--sm" id="btn-next-step">Proxima ${VIH.Icons.arrowRight}</button>` : `<button class="btn btn--success btn--sm" id="btn-go-dashboard">${VIH.Icons.barChart} Ir para Dashboard</button>`}
        </div>
      </div>`;
  }

  function attachStepperListeners(state) {
    // Step click
    document.querySelectorAll('.stepper__step').forEach(el => {
      el.addEventListener('click', () => {
        const idx = parseInt(el.dataset.index);
        activeStepIdx = idx;
        state.activeStep = idx;
        document.getElementById('step-detail-container').innerHTML = renderStepDetail(idx, state);
        // Re-render stepper active state
        document.getElementById('pipeline-stepper').innerHTML = renderStepperNodes(state);
        attachStepperListeners(state);
        attachDetailListeners(state);
      });
    });

    attachDetailListeners(state);
  }

  function attachDetailListeners(state) {
    const btnRun = document.getElementById('btn-run-step');
    const btnPrev = document.getElementById('btn-prev-step');
    const btnNext = document.getElementById('btn-next-step');
    const btnDash = document.getElementById('btn-go-dashboard');
    const costInput = document.getElementById('cost-bps-input');

    if (costInput) {
      costInput.addEventListener('change', (e) => {
        state.costBps = parseFloat(e.target.value) || 10;
      });
    }

    if (btnRun) {
      btnRun.addEventListener('click', () => runStep(activeStepIdx, state));
    }

    if (btnPrev) {
      btnPrev.addEventListener('click', () => {
        if (activeStepIdx > 0) {
          activeStepIdx--;
          state.activeStep = activeStepIdx;
          document.getElementById('step-detail-container').innerHTML = renderStepDetail(activeStepIdx, state);
          document.getElementById('pipeline-stepper').innerHTML = renderStepperNodes(state);
          attachStepperListeners(state);
        }
      });
    }

    if (btnNext) {
      btnNext.addEventListener('click', () => {
        if (activeStepIdx < STEPS.length - 1) {
          activeStepIdx++;
          state.activeStep = activeStepIdx;
          document.getElementById('step-detail-container').innerHTML = renderStepDetail(activeStepIdx, state);
          document.getElementById('pipeline-stepper').innerHTML = renderStepperNodes(state);
          attachStepperListeners(state);
        }
      });
    }

    if (btnDash) {
      btnDash.addEventListener('click', () => {
        window.location.hash = '#dashboard';
        VIH.navigate('dashboard');
      });
    }
  }

  async function runStep(idx, state) {
    const step = STEPS[idx];
    const stepState = state.pipelineSteps[idx];

    stepState.status = 'running';
    document.getElementById('step-detail-container').innerHTML = renderStepDetail(idx, state);
    document.getElementById('pipeline-stepper').innerHTML = renderStepperNodes(state);
    attachStepperListeners(state);

    VIH.clearTerminal('step-terminal');
    VIH.appendTerminalLine('step-terminal', `Executando: vih ${step.command}...`, '');

    const body = { command: step.command };
    if (step.command === 'backtest') {
      body.cost_bps = state.costBps;
    }

    try {
      const response = await fetch(VIH.API_BASE + '/api/run-step', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      // SSE-like: read stream line by line
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // Keep incomplete line

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.type === 'output') {
                VIH.appendTerminalLine('step-terminal', data.text, '');
              } else if (data.type === 'error') {
                VIH.appendTerminalLine('step-terminal', data.text, 'error');
              } else if (data.type === 'done') {
                if (data.success) {
                  stepState.status = 'completed';
                  VIH.appendTerminalLine('step-terminal', 'Etapa concluida com sucesso.', 'success');
                } else {
                  stepState.status = 'error';
                  VIH.appendTerminalLine('step-terminal', `Erro: ${data.error || 'Falha na execucao'}`, 'error');
                }
              }
            } catch (e) {
              VIH.appendTerminalLine('step-terminal', line, '');
            }
          }
        }
      }

      // Process remaining buffer
      if (buffer.trim()) {
        if (buffer.startsWith('data: ')) {
          try {
            const data = JSON.parse(buffer.slice(6));
            if (data.type === 'done') {
              stepState.status = data.success ? 'completed' : 'error';
            }
          } catch(e) { /* ignore */ }
        }
      }

      // If still running after stream ends, mark as completed
      if (stepState.status === 'running') {
        stepState.status = 'completed';
        VIH.appendTerminalLine('step-terminal', 'Etapa concluida.', 'success');
      }

    } catch (err) {
      stepState.status = 'error';
      VIH.appendTerminalLine('step-terminal', `Erro de conexao: ${err.message}`, 'error');
      VIH.appendTerminalLine('step-terminal', 'Verifique se o servidor API esta rodando (python api_server.py).', 'warn');
    }

    // Update UI
    document.getElementById('step-detail-container').innerHTML = renderStepDetail(idx, state);
    document.getElementById('pipeline-stepper').innerHTML = renderStepperNodes(state);
    attachStepperListeners(state);
    VIH.checkFileStatus();
  }

  function updateStepper(stepperEl, state) {
    stepperEl.innerHTML = renderStepperNodes(state);
    attachStepperListeners(state);
  }

  // Expose
  window.VIH = window.VIH || {};
  window.VIH.renderPipeline = renderPipeline;
  window.VIH.updateStepper = updateStepper;
})();
