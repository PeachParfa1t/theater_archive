// ===== Searchable select (autocomplete) widget =====
// Markup: <div class="searchable-select" data-url="/api/artists" data-on-select="someGlobalFnName">
//           <input class="form-control ss-input" autocomplete="off">
//           <input type="hidden" class="ss-value" name="...">
//           <div class="ss-dropdown list-group position-absolute"></div>
//         </div>
// data-on-select (optional) names a global function called with the full selected item
// object (e.g. {id, label, positions: [...]}) whenever the user picks an option.
// The hidden .ss-value is optional: omit it for a plain "suggest as you type" text field
// (e.g. an optional free-text name filter) that doesn't need an exact id and isn't required
// by guardSearchableSelectForms().
function initSearchableSelect(root) {
  const input  = root.querySelector('.ss-input');
  const hidden = root.querySelector('.ss-value');
  const list   = root.querySelector('.ss-dropdown');
  const url    = root.dataset.url;
  let items = [];

  fetch(url).then(r => r.json()).then(data => { items = data; });

  // Universal clear (×) button — lets the user empty the text + hidden id in one click
  // instead of selecting all text and deleting it manually.
  if (getComputedStyle(root).position === 'static') root.style.position = 'relative';
  input.style.paddingRight = '28px';
  const clearBtn = document.createElement('button');
  clearBtn.type = 'button';
  clearBtn.className = 'btn-close ss-clear';
  clearBtn.setAttribute('aria-label', 'Очистить');
  clearBtn.style.cssText = 'position:absolute;top:50%;right:8px;transform:translateY(-50%);' +
                            'font-size:.6rem;display:none;z-index:5;';
  root.appendChild(clearBtn);
  function toggleClearBtn() { clearBtn.style.display = input.value ? 'block' : 'none'; }
  clearBtn.addEventListener('mousedown', e => {
    e.preventDefault();
    input.value = '';
    if (hidden) hidden.value = '';
    input.classList.remove('is-invalid');
    list.style.display = 'none';
    toggleClearBtn();
    input.focus();
  });
  toggleClearBtn();

  function render(filterText) {
    const f = filterText.toLowerCase();
    const filtered = items.filter(it => it.label.toLowerCase().includes(f)).slice(0, 50);
    list.innerHTML = '';
    if (!filtered.length) { list.style.display = 'none'; return; }
    filtered.forEach(it => {
      const row = document.createElement('div');
      row.className = 'list-group-item list-group-item-action py-1 px-2';
      row.style.cursor = 'pointer';
      row.textContent = it.label;
      row.addEventListener('mousedown', e => {
        e.preventDefault();
        input.value = (root.dataset.selectValue === 'name' && it.name) ? it.name : it.label;
        if (hidden) hidden.value = it.id;
        list.style.display = 'none';
        toggleClearBtn();
        const cbName = root.dataset.onSelect;
        if (cbName && typeof window[cbName] === 'function') window[cbName](it);
      });
      list.appendChild(row);
    });
    list.style.display = 'block';
  }

  input.addEventListener('input', () => { if (hidden) hidden.value = ''; toggleClearBtn(); render(input.value); });
  input.addEventListener('focus', () => render(input.value));
  document.addEventListener('click', e => { if (!root.contains(e.target)) list.style.display = 'none'; });
}

function initAllSearchableSelects(scope) {
  (scope || document).querySelectorAll('.searchable-select').forEach(root => {
    if (!root.dataset.ssInit) {
      root.dataset.ssInit = '1';
      initSearchableSelect(root);
    }
  });
}

// Validate searchable-select widgets on submit (hidden input can't use native `required`
// because it's display:none and browsers silently block submission without feedback)
function guardSearchableSelectForms() {
  document.querySelectorAll('form').forEach(form => {
    const widgets = form.querySelectorAll('.searchable-select');
    if (!widgets.length || form.dataset.ssGuard) return;
    form.dataset.ssGuard = '1';
    form.addEventListener('submit', e => {
      let ok = true;
      widgets.forEach(w => {
        const hidden = w.querySelector('.ss-value');
        if (!hidden) return; // no id to require — plain suggest-as-you-type text field
        const input = w.querySelector('.ss-input');
        if (!hidden.value) { input.classList.add('is-invalid'); ok = false; }
        else input.classList.remove('is-invalid');
      });
      if (!ok) e.preventDefault();
    });
  });
}

// ===== Generic live (instant, no page reload) filter for lists/tables/cards =====
// config: { itemSelector, filters: [{inputId, dataKey, event, mode}], countId, resetBtnId }
function initLiveFilter(config) {
  const items = Array.from(document.querySelectorAll(config.itemSelector));
  function apply() {
    let visible = 0;
    items.forEach(item => {
      let ok = true;
      config.filters.forEach(f => {
        const el = document.getElementById(f.inputId);
        if (!el) return;
        const val = el.value.trim().toLowerCase();
        if (!val) return;
        const data = (item.dataset[f.dataKey] || '').toLowerCase();
        if (f.mode === 'exact') { if (data !== val) ok = false; }
        else { if (!data.includes(val)) ok = false; }
      });
      item.style.display = ok ? '' : 'none';
      if (ok) visible++;
    });
    if (config.countId) {
      const c = document.getElementById(config.countId);
      if (c) c.textContent = visible;
    }
  }
  config.filters.forEach(f => {
    const el = document.getElementById(f.inputId);
    if (el) el.addEventListener(f.event || 'input', apply);
  });
  if (config.resetBtnId) {
    const btn = document.getElementById(config.resetBtnId);
    if (btn) btn.addEventListener('click', () => {
      config.filters.forEach(f => { const el = document.getElementById(f.inputId); if (el) el.value = ''; });
      apply();
    });
  }
  apply();
  return apply;
}

// ===== Quick text filter for a list of checkboxes (e.g. "link to artists") =====
function initCheckboxFilter(filterInputId, containerId) {
  const input = document.getElementById(filterInputId);
  const container = document.getElementById(containerId);
  if (!input || !container) return;
  input.addEventListener('input', () => {
    const q = input.value.trim().toLowerCase();
    container.querySelectorAll('.form-check').forEach(row => {
      const text = row.textContent.toLowerCase();
      row.style.display = !q || text.includes(q) ? '' : 'none';
    });
  });
}

// ===== Loading overlay fade-out =====
// Shown by default (see base.html); hidden with a smooth fade once the page (including
// images) has fully loaded, revealing the already-rendered content underneath.
window.addEventListener('load', () => {
  const overlay = document.getElementById('loadingOverlay');
  if (!overlay) return;
  overlay.classList.add('loading-hide');
  setTimeout(() => { overlay.style.display = 'none'; }, 450);
});

// ===== Year-input spinner fix =====
// Native <input type="number"> spinner arrows jump an empty field straight to 0 (or to `min`,
// once min/max are set) on the very first click. Add class "year-input" to any year field to
// have that first click/keypress fill in the current year instead.
function initYearInputFix(input) {
  let prevEmpty = input.value === '';
  input.addEventListener('input', () => {
    if (prevEmpty && (input.value === '0' || input.value === '1' || input.value === input.min)) {
      input.value = new Date().getFullYear();
    }
    prevEmpty = input.value === '';
  });
}

// ===== Restore the active Bootstrap tab from the URL hash after a redirect =====
// Server-side actions (add/delete material, document, libretto file, staging member...)
// redirect back to productions.detail with a "#tabId" suffix so the user lands back on the
// tab they were working in, instead of always seeing the first ("Состав") tab.
function activateTabFromHash() {
  if (!location.hash) return;
  const trigger = document.querySelector('[data-bs-toggle="tab"][href="' + location.hash + '"]');
  if (trigger && window.bootstrap) {
    new bootstrap.Tab(trigger).show();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initAllSearchableSelects();
  guardSearchableSelectForms();
  document.querySelectorAll('input.year-input').forEach(initYearInputFix);
  activateTabFromHash();
  // Re-run guard/init after Bootstrap collapse panels reveal new forms
  document.body.addEventListener('shown.bs.collapse', () => {
    initAllSearchableSelects();
    guardSearchableSelectForms();
  });
});
