/* =============================================================
   VIH — Dashboard Page
   Plots, KPI cards, metrics tables, selections, and report
   ============================================================= */

(function () {
  'use strict';

  const DISPLAY_COLUMNS = [
    'fold_id', 'strategy', 'test_periods', 'cumulative_return',
    'annualized_return', 'annualized_volatility', 'sharpe',
    'sharpe_ci_lower', 'sharpe_ci_upper', 'deflated_sharpe_proxy',
    'sortino', 'max_drawdown', 'avg_assets', 'avg_turnover',
    'risk_free_rate',
  ];

  const SELECTION_COLUMNS = [
    'fold_id', 'strategy', 'periodo', 'selected', 'n_assets',
    'turnover', 'relaxed_rules',
  ];

  const MAIN_PLOTS = [
    { file: 'cumulative_returns.png', title: 'Retorno Acumulado', iconKey: 'lineChart' },
    { file: 'drawdown.png', title: 'Drawdown', iconKey: 'trendingDown' },
    { file: 'sharpe_comparison.png', title: 'Comparacao Sharpe', iconKey: 'barChart' },
    { file: 'portfolio_composition.png', title: 'Composicao do Portfolio', iconKey: 'layers' },
  ];

  async function renderDashboard(container) {
    container.innerHTML = `
      <div class="page-header">
        <h1 class="page-header__title">Dashboard de Resultados</h1>
        <p class="page-header__description">
          Visualizacao dos resultados do backtest walk-forward purgado com embargo.
        </p>
      </div>
      <div id="dashboard-loading" class="empty-state">
        <div class="spinner" style="width:32px;height:32px;margin-bottom:var(--space-md)"></div>
        <p class="empty-state__title">Carregando dados...</p>
      </div>
      <div id="dashboard-content" style="display:none"></div>
    `;

    try {
      const [summaryData, selectionsData, reportData] = await Promise.all([
        fetchCSV('/api/outputs/backtest_summary.csv'),
        fetchCSV('/api/outputs/backtest_selections.csv'),
        fetchText('/api/outputs/backtest_report.md'),
      ]);

      const dashEl = document.getElementById('dashboard-content');
      const loadingEl = document.getElementById('dashboard-loading');

      if (!summaryData || summaryData.rows.length === 0) {
        loadingEl.innerHTML = `
          ${VIH.Icons.barChart}
          <p class="empty-state__title">Sem dados de backtest</p>
          <p class="empty-state__desc">Execute o pipeline completo para gerar os resultados.</p>
          <button class="btn btn--primary" style="margin-top:var(--space-md)" onclick="VIH.navigate('pipeline')">
            ${VIH.Icons.play} Ir para Pipeline
          </button>
        `;
        return;
      }

      loadingEl.style.display = 'none';
      dashEl.style.display = 'block';

      // Build dashboard sections
      dashEl.innerHTML = `
        ${renderKPIs(summaryData)}
        ${renderMainPlots()}
        ${renderConvergencePlots(summaryData)}
        <div class="section-divider"></div>
        ${renderMetricsTable(summaryData)}
        <div class="section-divider"></div>
        ${renderSelectionsTable(selectionsData)}
        <div class="section-divider"></div>
        ${renderReport(reportData)}
      `;

      // Make tables sortable
      VIH.makeTableSortable('summary-table');
      VIH.makeTableSortable('selections-table');
      attachTabListeners();
      attachLightbox();
      attachCollapsibles();

    } catch (err) {
      document.getElementById('dashboard-loading').innerHTML = `
        ${VIH.Icons.alertTriangle}
        <p class="empty-state__title">Erro ao carregar dados</p>
        <p class="empty-state__desc">${VIH.escapeHtml(err.message)}</p>
        <p class="empty-state__desc" style="margin-top:var(--space-sm)">Verifique se o servidor API esta rodando.</p>
      `;
    }
  }

  // --- KPI Cards ---
  function renderKPIs(data) {
    // Get "chosen" strategy averages
    const chosenRows = data.rows.filter(r => {
      const stratIdx = data.headers.indexOf('strategy');
      return stratIdx >= 0 && r[stratIdx] && r[stratIdx].startsWith('chosen_');
    });

    const getAvg = (colName) => {
      const idx = data.headers.indexOf(colName);
      if (idx < 0) return NaN;
      const vals = chosenRows.map(r => parseFloat(r[idx])).filter(v => !isNaN(v));
      return vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : NaN;
    };

    const avgReturn = getAvg('cumulative_return');
    const avgSharpe = getAvg('sharpe');
    const avgDrawdown = getAvg('max_drawdown');
    const avgSortino = getAvg('sortino');
    const avgDSP = getAvg('deflated_sharpe_proxy');
    const avgRf = getAvg('risk_free_rate');

    return `
      <div class="kpi-grid">
        ${VIH.createKpiCard(
          'Retorno Acumulado',
          VIH.formatPercent(avgReturn),
          'Estrategia escolhida (media folds)',
          avgReturn >= 0 ? 'green' : 'red',
          avgReturn >= 0 ? 'trendingUp' : 'trendingDown'
        )}
        ${VIH.createKpiCard(
          'Sharpe Ratio',
          VIH.formatNumber(avgSharpe, 2),
          'Media dos folds (c/ CDI como Rf)',
          'indigo',
          'barChart'
        )}
        ${VIH.createKpiCard(
          'Max Drawdown',
          VIH.formatPercent(avgDrawdown),
          'Pior queda pico-vale',
          'red',
          'trendingDown'
        )}
        ${VIH.createKpiCard(
          'Sortino Ratio',
          VIH.formatNumber(avgSortino, 2),
          'Penaliza apenas volatilidade negativa',
          'violet',
          'activity'
        )}
        ${VIH.createKpiCard(
          'Deflated Sharpe Proxy',
          VIH.formatNumber(avgDSP, 4),
          'Sharpe penalizado por n. tentativas',
          'amber',
          'shield'
        )}
        ${VIH.createKpiCard(
          'Taxa Rf (CDI)',
          VIH.formatPercent(avgRf),
          'CDI medio anualizado (serie 4389)',
          'cyan',
          'dollarSign'
        )}
      </div>
    `;
  }

  // --- Main Plots (tabbed, one at a time) ---
  function renderMainPlots() {
    const tabs = MAIN_PLOTS.map((p, i) =>
      `<button class="tabs__tab ${i === 0 ? 'active' : ''}" data-tab="main-plot-${i}">${p.title}</button>`
    ).join('');

    const panels = MAIN_PLOTS.map((p, i) => `
      <div class="tab-content ${i === 0 ? 'active' : ''}" id="main-plot-${i}">
        <div class="plot-card">
          <div class="plot-card__title">
            ${VIH.Icons[p.iconKey] || ''}
            ${p.title}
          </div>
          <img src="${VIH.API_BASE}/api/outputs/plots/${p.file}"
               alt="${p.title}"
               loading="lazy"
               style="cursor:pointer"
               onerror="this.parentElement.innerHTML='<div class=\\'empty-state\\'><p class=\\'text-muted\\'>Plot nao disponivel</p></div>'">
        </div>
      </div>`).join('');

    return `
      <div class="card" style="margin-bottom:var(--space-xl)">
        <div class="card__header">
          <div class="card__header-title">
            <span style="color:var(--accent-blue)">${VIH.Icons.image}</span>
            Graficos Principais
          </div>
        </div>
        <div class="card__body">
          <div class="tabs" id="main-plots-tabs">
            ${tabs}
          </div>
          <div style="margin-top:var(--space-md)">
            ${panels}
          </div>
        </div>
      </div>`;
  }

  // --- Convergence Plots (tabbed by fold) ---
  function renderConvergencePlots(data) {
    // Discover folds
    const foldIdx = data.headers.indexOf('fold_id');
    const folds = [...new Set(data.rows.map(r => r[foldIdx]))].filter(Boolean).sort();

    if (folds.length === 0) return '';

    const tabs = folds.map((f, i) =>
      `<button class="tabs__tab ${i === 0 ? 'active' : ''}" data-tab="conv-fold-${f}">Fold ${f}</button>`
    ).join('');

    const panels = folds.map((f, i) => {
      return `
        <div class="tab-content ${i === 0 ? 'active' : ''}" id="conv-fold-${f}">
          <div class="plot-gallery">
            <div class="plot-card">
              <div class="plot-card__title">
                ${VIH.Icons.lineChart}
                Convergencia AG - Fold ${f}
              </div>
              <img src="${VIH.API_BASE}/api/outputs/plots/convergence_fold${f}_ga.png"
                   alt="Convergencia AG Fold ${f}"
                   loading="lazy"
                   onerror="this.parentElement.innerHTML='<div class=\\'empty-state\\'><p class=\\'text-muted\\'>Plot nao disponivel</p></div>'">
            </div>
            <div class="plot-card">
              <div class="plot-card__title">
                ${VIH.Icons.activity}
                Trajetoria SA - Fold ${f}
              </div>
              <img src="${VIH.API_BASE}/api/outputs/plots/sa_trajectory_fold${f}_sa.png"
                   alt="Trajetoria SA Fold ${f}"
                   loading="lazy"
                   onerror="this.parentElement.innerHTML='<div class=\\'empty-state\\'><p class=\\'text-muted\\'>Plot nao disponivel</p></div>'">
            </div>
          </div>
        </div>`;
    }).join('');

    return `
      <div class="card" style="margin-bottom:var(--space-xl)">
        <div class="card__header">
          <div class="card__header-title">
            <span style="color:var(--accent-blue)">${VIH.Icons.zap}</span>
            Convergencia dos Otimizadores
          </div>
        </div>
        <div class="card__body">
          <div class="tabs" id="convergence-tabs">
            ${tabs}
          </div>
          <div style="margin-top:var(--space-md)">
            ${panels}
          </div>
        </div>
      </div>`;
  }

  // --- Metrics Table ---
  function renderMetricsTable(data) {
    const filteredHeaders = [];
    const filteredIndices = [];
    DISPLAY_COLUMNS.forEach(col => {
      const idx = data.headers.indexOf(col);
      if (idx >= 0) {
        filteredHeaders.push(col);
        filteredIndices.push(idx);
      }
    });

    const filteredRows = data.rows.map(row =>
      filteredIndices.map(i => {
        const val = row[i];
        const num = parseFloat(val);
        if (!isNaN(num) && filteredHeaders[filteredIndices.indexOf(i)] !== 'fold_id') {
          if (filteredHeaders[filteredIndices.indexOf(i)].includes('return') ||
              filteredHeaders[filteredIndices.indexOf(i)].includes('drawdown') ||
              filteredHeaders[filteredIndices.indexOf(i)].includes('risk_free') ||
              filteredHeaders[filteredIndices.indexOf(i)].includes('turnover')) {
            return VIH.formatPercent(num);
          }
          return VIH.formatNumber(num, 4);
        }
        return val;
      })
    );

    const table = VIH.createDataTable(filteredHeaders, filteredRows, 'summary-table');

    return `
      <div class="card card--collapsible card--collapsed">
        <div class="card__header card__header--toggle">
          <div class="card__header-title">
            <span style="color:var(--accent-blue)">${VIH.Icons.table}</span>
            Metricas do Backtest
          </div>
          <div style="display:flex;align-items:center;gap:var(--space-md)">
            <span class="badge badge--blue">backtest_summary.csv</span>
            <span class="card__chevron">${VIH.Icons.chevronDown}</span>
          </div>
        </div>
        <div class="card__body" style="padding:0">
          ${table}
        </div>
      </div>`;
  }

  // --- Selections Table ---
  function renderSelectionsTable(data) {
    if (!data || data.rows.length === 0) {
      return `
        <div class="card">
          <div class="card__header">
            <div class="card__header-title">
              ${VIH.Icons.target}
              Acoes Selecionadas
            </div>
          </div>
          <div class="card__body">
            <div class="empty-state">
              ${VIH.Icons.target}
              <p class="empty-state__title">Sem selecoes</p>
              <p class="empty-state__desc">Nenhuma acao foi selecionada nos periodos de teste.</p>
            </div>
          </div>
        </div>`;
    }

    const filteredHeaders = [];
    const filteredIndices = [];
    SELECTION_COLUMNS.forEach(col => {
      const idx = data.headers.indexOf(col);
      if (idx >= 0) {
        filteredHeaders.push(col);
        filteredIndices.push(idx);
      }
    });

    const filteredRows = data.rows.map(row =>
      filteredIndices.map(i => row[i])
    );

    const table = VIH.createDataTable(filteredHeaders, filteredRows, 'selections-table');

    return `
      <div class="card card--collapsible card--collapsed">
        <div class="card__header card__header--toggle">
          <div class="card__header-title">
            <span style="color:var(--accent-blue)">${VIH.Icons.target}</span>
            Acoes Selecionadas por Periodo
          </div>
          <div style="display:flex;align-items:center;gap:var(--space-md)">
            <span class="badge badge--blue">backtest_selections.csv</span>
            <span class="card__chevron">${VIH.Icons.chevronDown}</span>
          </div>
        </div>
        <div class="card__body" style="padding:0">
          ${table}
        </div>
      </div>`;
  }

  // --- Report Renderer ---
  function renderReport(markdown) {
    if (!markdown) return '';
    const html = VIH.simpleMarkdown(markdown);
    return `
      <div class="card card--collapsible card--collapsed" style="margin-top:var(--space-xl)">
        <div class="card__header card__header--toggle">
          <div class="card__header-title">
            <span style="color:var(--accent-blue)">${VIH.Icons.fileText}</span>
            Relatorio do Backtest
          </div>
          <div style="display:flex;align-items:center;gap:var(--space-md)">
            <span class="badge badge--blue">backtest_report.md</span>
            <span class="card__chevron">${VIH.Icons.chevronDown}</span>
          </div>
        </div>
        <div class="card__body">
          <div class="markdown-body">
            ${html}
          </div>
        </div>
      </div>`;
  }

  // --- Tab switching ---
  function attachTabListeners() {
    document.querySelectorAll('.tabs').forEach(tabGroup => {
      tabGroup.querySelectorAll('.tabs__tab').forEach(tab => {
        tab.addEventListener('click', () => {
          const targetId = tab.dataset.tab;
          // Deactivate siblings
          tabGroup.querySelectorAll('.tabs__tab').forEach(t => t.classList.remove('active'));
          tab.classList.add('active');
          // Show/hide panels
          const parent = tabGroup.parentElement;
          parent.querySelectorAll('.tab-content').forEach(panel => {
            panel.classList.toggle('active', panel.id === targetId);
          });
        });
      });
    });
  }

  // --- Collapsible cards ---
  function attachCollapsibles() {
    document.querySelectorAll('.card--collapsible .card__header--toggle').forEach(header => {
      header.addEventListener('click', (e) => {
        // Ignore clicks on the badge (allows selecting the filename text)
        if (e.target.closest('.badge')) return;
        header.closest('.card--collapsible').classList.toggle('card--collapsed');
      });
    });
  }

  // --- Lightbox fullscreen ---
  function attachLightbox() {
    // Create lightbox overlay if not exists
    let overlay = document.getElementById('lightbox-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'lightbox-overlay';
      overlay.style.cssText = `
        position:fixed;inset:0;z-index:300;background:rgba(0,0,0,0.9);
        display:none;align-items:center;justify-content:center;
        cursor:pointer;backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);
      `;
      overlay.innerHTML = `
        <button id="lightbox-close" style="
          position:absolute;top:20px;right:20px;background:rgba(255,255,255,0.1);
          border:1px solid rgba(255,255,255,0.2);border-radius:8px;color:#fff;
          width:40px;height:40px;display:flex;align-items:center;justify-content:center;
          cursor:pointer;transition:background 0.2s;
        "><span style="width:20px;height:20px;display:flex">${VIH.Icons.x}</span></button>
        <img id="lightbox-img" style="
          max-width:95vw;max-height:90vh;border-radius:8px;
          box-shadow:0 8px 32px rgba(0,0,0,0.5);background:#fff;
        " alt="">
      `;
      document.body.appendChild(overlay);

      // Close on overlay click
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay || e.target.closest('#lightbox-close')) {
          overlay.style.display = 'none';
        }
      });

      // Close on Escape
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && overlay.style.display === 'flex') {
          overlay.style.display = 'none';
        }
      });
    }

    // Attach click to all plot images
    document.querySelectorAll('.plot-card img').forEach(img => {
      img.style.cursor = 'pointer';
      img.addEventListener('click', () => {
        const lightboxImg = document.getElementById('lightbox-img');
        lightboxImg.src = img.src;
        lightboxImg.alt = img.alt;
        overlay.style.display = 'flex';
      });
    });
  }

  // --- Fetch helpers ---
  async function fetchCSV(path) {
    try {
      const res = await fetch(VIH.API_BASE + path);
      if (!res.ok) return null;
      const text = await res.text();
      return VIH.parseCSV(text);
    } catch (e) {
      return null;
    }
  }

  async function fetchText(path) {
    try {
      const res = await fetch(VIH.API_BASE + path);
      if (!res.ok) return null;
      return await res.text();
    } catch (e) {
      return null;
    }
  }

  // Expose
  window.VIH = window.VIH || {};
  window.VIH.renderDashboard = renderDashboard;
})();
