/* =============================================================
   VIH — SPA Router & Global State
   ============================================================= */

(function () {
  'use strict';

  const API_BASE = window.VIH_API_BASE || '';

  const state = {
    currentPage: 'pipeline',
    pipelineSteps: [
      { id: 1, status: 'idle', label: 'Preparacao', command: 'prepare' },
      { id: 2, status: 'idle', label: 'Mapeamento', command: 'fetch-mapping' },
      { id: 3, status: 'idle', label: 'Precos', command: 'fetch-prices' },
      { id: 4, status: 'idle', label: 'Dados Aux.', command: 'fetch-aux' },
      { id: 5, status: 'idle', label: 'Backtest', command: 'backtest' },
    ],
    activeStep: 0,
    costBps: 10,
    fileStatus: {},
  };

  // --- API helper ---
  async function api(path, options = {}) {
    const url = API_BASE + path;
    const res = await fetch(url, options);
    if (!res.ok) {
      const err = await res.text();
      throw new Error(err || `HTTP ${res.status}`);
    }
    return res;
  }

  async function apiJson(path, options = {}) {
    const res = await api(path, options);
    return res.json();
  }

  // --- File status check ---
  async function checkFileStatus() {
    try {
      const data = await apiJson('/api/status');
      state.fileStatus = data;
      updateFileStatusUI();
    } catch (e) {
      console.warn('Could not check file status:', e);
    }
  }

  function updateFileStatusUI() {
    // Update step badges based on output existence
    const stepFiles = {
      1: 'fundamentals',
      2: 'mapping',
      3: 'prices',
      4: 'cdi',
      5: 'summary',
    };
    Object.entries(stepFiles).forEach(([stepId, key]) => {
      const exists = state.fileStatus[key];
      const stepEl = document.querySelector(`.stepper__step[data-step="${stepId}"]`);
      if (stepEl && exists && state.pipelineSteps[stepId - 1].status === 'idle') {
        state.pipelineSteps[stepId - 1].status = 'completed';
        renderStepper();
      }
    });
  }

  // --- Router ---
  function navigate(page) {
    state.currentPage = page;
    // Update nav buttons
    document.querySelectorAll('.topbar__nav-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.page === page);
    });
    // Render page
    const container = document.getElementById('page-content');
    container.style.opacity = '0';
    setTimeout(() => {
      switch (page) {
        case 'pipeline':
          window.VIH.renderPipeline(container, state);
          break;
        case 'dashboard':
          window.VIH.renderDashboard(container, state);
          break;
        case 'tutorial':
          window.VIH.renderTutorial(container, state);
          break;
        default:
          window.VIH.renderPipeline(container, state);
      }
      container.style.opacity = '1';
    }, 150);
  }

  // --- Stepper render ---
  function renderStepper() {
    const stepperEl = document.getElementById('pipeline-stepper');
    if (!stepperEl) return;
    window.VIH.updateStepper(stepperEl, state);
  }

  // --- Theme toggle ---
  function setupThemeToggle() {
    const btn = document.getElementById('theme-toggle');
    if (!btn) return;
    btn.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme') || 'dark';
      const next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      try { localStorage.setItem('vih-theme', next); } catch (e) { /* ignore */ }
    });
  }

  // --- Init ---
  function init() {
    // Theme toggle
    setupThemeToggle();

    // Set up nav listeners
    document.querySelectorAll('.topbar__nav-btn').forEach(btn => {
      btn.addEventListener('click', () => navigate(btn.dataset.page));
    });

    // Read hash
    const hash = window.location.hash.replace('#', '') || 'pipeline';
    navigate(hash);

    // Check file status
    checkFileStatus();

    // Hash change listener
    window.addEventListener('hashchange', () => {
      const page = window.location.hash.replace('#', '') || 'pipeline';
      navigate(page);
    });
  }

  // Expose
  window.VIH = window.VIH || {};
  window.VIH.state = state;
  window.VIH.api = api;
  window.VIH.apiJson = apiJson;
  window.VIH.navigate = navigate;
  window.VIH.checkFileStatus = checkFileStatus;
  window.VIH.API_BASE = API_BASE;

  document.addEventListener('DOMContentLoaded', init);
})();
