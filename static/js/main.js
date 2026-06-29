// ===== Searchable select (autocomplete) widget =====
// Markup: <div class="searchable-select" data-url="/api/artists">
//           <input class="form-control ss-input" autocomplete="off">
//           <input type="hidden" class="ss-value" name="...">
//           <div class="ss-dropdown list-group position-absolute"></div>
//         </div>
function initSearchableSelect(root) {
  const input  = root.querySelector('.ss-input');
  const hidden = root.querySelector('.ss-value');
  const list   = root.querySelector('.ss-dropdown');
  const url    = root.dataset.url;
  let items = [];

  fetch(url).then(r => r.json()).then(data => { items = data; });

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
        input.value = it.label;
        hidden.value = it.id;
        list.style.display = 'none';
      });
      list.appendChild(row);
    });
    list.style.display = 'block';
  }

  input.addEventListener('input', () => { hidden.value = ''; render(input.value); });
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
        const input  = w.querySelector('.ss-input');
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

document.addEventListener('DOMContentLoaded', () => {
  initAllSearchableSelects();
  guardSearchableSelectForms();
  // Re-run guard/init after Bootstrap collapse panels reveal new forms
  document.body.addEventListener('shown.bs.collapse', () => {
    initAllSearchableSelects();
    guardSearchableSelectForms();
  });
});
