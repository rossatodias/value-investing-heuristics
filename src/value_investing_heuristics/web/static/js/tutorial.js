/* =============================================================
   VIH — Tutorial Page
   Renders manual.md with sidebar TOC and text search
   ============================================================= */

(function () {
  'use strict';

  let cachedManual = null;
  let tocItems = [];

  async function renderTutorial(container) {
    container.innerHTML = `
      <div class="page-header">
        <h1 class="page-header__title">Manual de Uso</h1>
        <p class="page-header__description">
          Documentacao completa do pipeline Value Investing Heuristics.
        </p>
      </div>
      <div id="tutorial-loading" class="empty-state">
        <div class="spinner" style="width:32px;height:32px;margin-bottom:var(--space-md)"></div>
        <p class="empty-state__title">Carregando manual...</p>
      </div>
      <div id="tutorial-content" style="display:none"></div>
    `;

    try {
      if (!cachedManual) {
        const res = await fetch(VIH.API_BASE + '/api/manual');
        if (!res.ok) throw new Error('Nao foi possivel carregar o manual.');
        cachedManual = await res.text();
      }

      const html = VIH.simpleMarkdown(cachedManual);
      tocItems = extractTOC(cachedManual);

      const loadingEl = document.getElementById('tutorial-loading');
      const contentEl = document.getElementById('tutorial-content');

      loadingEl.style.display = 'none';
      contentEl.style.display = 'block';

      contentEl.innerHTML = `
        <div class="tutorial-layout">
          <aside class="tutorial-sidebar">
            <div class="tutorial-sidebar__search">
              <div style="position:relative">
                <span style="position:absolute;left:12px;top:50%;transform:translateY(-50%);color:var(--text-muted);width:14px;height:14px">
                  ${VIH.Icons.search}
                </span>
                <input type="text" class="input-field" id="tutorial-search"
                       placeholder="Buscar no manual..." style="padding-left:36px;width:100%">
              </div>
            </div>
            <ul class="tutorial-nav" id="tutorial-nav">
              ${renderTOC(tocItems)}
            </ul>
          </aside>
          <main class="card">
            <div class="card__body">
              <div class="markdown-body" id="tutorial-body">
                ${html}
              </div>
            </div>
          </main>
        </div>
      `;

      attachTutorialListeners();

    } catch (err) {
      document.getElementById('tutorial-loading').innerHTML = `
        ${VIH.Icons.alertTriangle}
        <p class="empty-state__title">Erro ao carregar manual</p>
        <p class="empty-state__desc">${VIH.escapeHtml(err.message)}</p>
      `;
    }
  }

  function extractTOC(markdown) {
    const items = [];
    const lines = markdown.split('\n');
    let counter = 0;
    let inCodeBlock = false;
    for (const line of lines) {
      if (/^```/.test(line)) {
        inCodeBlock = !inCodeBlock;
        continue;
      }
      if (inCodeBlock) continue;
      const match = line.match(/^(#{1,3})\s+(.+)$/);
      if (match) {
        const level = match[1].length;
        const text = match[2].trim();
        const id = 'section-' + counter++;
        items.push({ level, text, id });
      }
    }
    return items;
  }

  function renderTOC(items) {
    return items.map(item => {
      let levelClass = '';
      if (item.level === 2) levelClass = ' tutorial-nav__item--sub';
      else if (item.level === 3) levelClass = ' tutorial-nav__item--subsub';
      return `
        <li class="tutorial-nav__item${levelClass}" data-section="${item.id}">
          ${item.text}
        </li>`;
    }).join('');
  }

  function attachTutorialListeners() {
    // Assign IDs to headings in the rendered HTML
    const body = document.getElementById('tutorial-body');
    if (body) {
      const headings = body.querySelectorAll('h1, h2, h3');
      let i = 0;
      headings.forEach(h => {
        if (i < tocItems.length) {
          h.id = tocItems[i].id;
          i++;
        }
      });
    }

    // TOC click navigation
    document.querySelectorAll('.tutorial-nav__item').forEach(item => {
      item.addEventListener('click', () => {
        const sectionId = item.dataset.section;
        const el = document.getElementById(sectionId);
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'start' });
          // Update active state
          document.querySelectorAll('.tutorial-nav__item').forEach(i => i.classList.remove('active'));
          item.classList.add('active');
        }
      });
    });

    // Search
    const searchInput = document.getElementById('tutorial-search');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase().trim();
        filterTOC(query);
        if (query.length >= 2) {
          highlightSearch(query);
        } else {
          clearHighlight();
        }
      });
    }
  }

  function filterTOC(query) {
    const body = document.getElementById('tutorial-body');
    document.querySelectorAll('.tutorial-nav__item').forEach(item => {
      if (!query) {
        item.style.display = '';
        return;
      }
      const sectionId = item.dataset.section;
      const heading = body ? body.querySelector('#' + sectionId) : null;
      if (!heading) {
        item.style.display = 'none';
        return;
      }
      // Collect text content from heading + all siblings until the next heading
      let sectionText = heading.textContent.toLowerCase();
      let sibling = heading.nextElementSibling;
      while (sibling && !/^H[1-3]$/.test(sibling.tagName)) {
        sectionText += ' ' + sibling.textContent.toLowerCase();
        sibling = sibling.nextElementSibling;
      }
      item.style.display = sectionText.includes(query) ? '' : 'none';
    });
  }

  function highlightSearch(query) {
    clearHighlight();
    const body = document.getElementById('tutorial-body');
    if (!body) return;

    const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT, null, false);
    const matches = [];

    while (walker.nextNode()) {
      const node = walker.currentNode;
      const idx = node.textContent.toLowerCase().indexOf(query);
      if (idx >= 0) {
        matches.push({ node, idx, length: query.length });
      }
    }

    // Only highlight first 20 matches for performance
    matches.slice(0, 20).reverse().forEach(m => {
      const range = document.createRange();
      range.setStart(m.node, m.idx);
      range.setEnd(m.node, m.idx + m.length);
      const mark = document.createElement('mark');
      mark.style.background = 'rgba(245, 158, 11, 0.3)';
      mark.style.color = 'var(--accent-amber)';
      mark.style.borderRadius = '2px';
      mark.className = 'search-highlight';
      range.surroundContents(mark);
    });

    // Scroll to first match
    const firstMark = body.querySelector('.search-highlight');
    if (firstMark) {
      firstMark.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }

  function clearHighlight() {
    document.querySelectorAll('.search-highlight').forEach(mark => {
      const parent = mark.parentNode;
      parent.replaceChild(document.createTextNode(mark.textContent), mark);
      parent.normalize();
    });
  }

  // Expose
  window.VIH = window.VIH || {};
  window.VIH.renderTutorial = renderTutorial;
})();
