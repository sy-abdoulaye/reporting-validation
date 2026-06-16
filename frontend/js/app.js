/* ================================================
   app.js — Shared utilities for Reporting App
   ================================================ */

// URL dynamique : suit l'hôte depuis lequel la page est servie
// (localhost en local, 203.0.113.141 en déploiement Docker, etc.)
const API = `${window.location.protocol}//${window.location.hostname}:8000/api/v1`;

/* ===== AUTH ===== */
const Auth = {
  token:        () => localStorage.getItem('access_token'),
  refreshToken: () => localStorage.getItem('refresh_token'),
  user:         () => JSON.parse(localStorage.getItem('user') || 'null'),
  save(access, refresh, user) {
    localStorage.setItem('access_token', access);
    if (refresh) localStorage.setItem('refresh_token', refresh);
    if (user)    localStorage.setItem('user', JSON.stringify(user));
  },
  clear() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
  },
  loggedIn:  () => !!localStorage.getItem('access_token'),
  superuser: () => (JSON.parse(localStorage.getItem('user') || '{}'))?.is_superuser === true,
};

/* ===== API FETCH ===== */
let _refreshing = null;

async function api(endpoint, opts = {}) {
  const url = `${API}${endpoint}`;
  const headers = { ...(opts.headers || {}) };
  if (Auth.token()) headers['Authorization'] = `Bearer ${Auth.token()}`;
  if (opts.json != null) {
    headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(opts.json);
    delete opts.json;
  }

  let res = await fetch(url, { ...opts, headers });

  if (res.status === 401 && Auth.refreshToken()) {
    if (!_refreshing) {
      _refreshing = _doRefresh().finally(() => { _refreshing = null; });
    }
    const ok = await _refreshing;
    if (ok) {
      headers['Authorization'] = `Bearer ${Auth.token()}`;
      res = await fetch(url, { ...opts, headers });
    }
  }

  if (res.status === 401) { Auth.clear(); window.location.href = 'login.html'; return null; }
  return res;
}

async function _doRefresh() {
  try {
    const r = await fetch(`${API}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: Auth.refreshToken() })
    });
    if (!r.ok) return false;
    const d = await r.json();
    Auth.save(d.access_token, d.refresh_token, d.user);
    return true;
  } catch { return false; }
}

async function apiJSON(endpoint, opts = {}) {
  const res = await api(endpoint, opts);
  if (!res) return null;
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Erreur ${res.status}`);
  }
  return res.json();
}

/* ===== HTMX AUTH HOOK ===== */
document.addEventListener('htmx:configRequest', evt => {
  if (Auth.token()) evt.detail.headers['Authorization'] = `Bearer ${Auth.token()}`;
});

/* ===== TOAST ===== */
const Toast = (() => {
  let box;
  const icons = { success: '✓', danger: '✕', warning: '⚠', info: 'ℹ' };

  function init() {
    if (!box) {
      box = document.getElementById('toasts');
      if (!box) { box = document.createElement('div'); box.id = 'toasts'; document.body.appendChild(box); }
    }
  }

  function show(msg, type = 'info', ms = 4500) {
    init();
    const t = document.createElement('div');
    t.className = `toast ${type}`;
    t.innerHTML = `<span class="toast-ico">${icons[type]||'ℹ'}</span><span class="toast-msg">${msg}</span><button class="toast-x" onclick="this.closest('.toast').remove()">×</button>`;
    box.appendChild(t);
    requestAnimationFrame(() => t.classList.add('in'));
    if (ms > 0) setTimeout(() => { t.classList.remove('in'); setTimeout(() => t.remove(), 300); }, ms);
  }

  return {
    success: m => show(m, 'success'),
    error:   m => show(m, 'danger', 6500),
    warn:    m => show(m, 'warning'),
    info:    m => show(m, 'info'),
  };
})();

/* ===== GUARDS ===== */
function requireAuth()  { if (!Auth.loggedIn())  { window.location.href = 'login.html';  return false; } return true; }
function requireGuest() { if (Auth.loggedIn())   { window.location.href = 'index.html';  return false; } return true; }
function requireAdmin() { if (!Auth.loggedIn())  { window.location.href = 'login.html';  return false; }
                          if (!Auth.superuser()) { window.location.href = 'index.html';  return false; } return true; }

/* ===== NAVBAR ===== */
function initNav() {
  const u = Auth.user();
  if (!u) return;
  const nm = document.getElementById('nav-name');
  const nr = document.getElementById('nav-role');
  const av = document.getElementById('nav-avatar');
  const al = document.getElementById('nav-admin');
  if (nm) nm.textContent = u.full_name || u.username;
  if (nr) nr.textContent = u.is_superuser ? 'Admin' : 'Utilisateur';
  if (av) av.textContent = (u.full_name || u.username || '?')[0].toUpperCase();
  if (al) al.style.display = u.is_superuser ? '' : 'none';

  const page = location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav-link[href]').forEach(a => {
    if (a.getAttribute('href') === page) a.classList.add('active');
  });
}

async function logout() {
  try { await api('/auth/logout', { method: 'POST' }); } catch {}
  Auth.clear();
  window.location.href = 'login.html';
}

/* ===== FORMATTERS ===== */
function fmtSize(b) {
  if (b == null) return '-';
  if (b < 1024)         return b + ' B';
  if (b < 1048576)      return (b / 1024).toFixed(1) + ' KB';
  return (b / 1048576).toFixed(1) + ' MB';
}

function fmtDate(iso) {
  if (!iso) return '-';
  return new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' });
}

function fmtRelative(iso) {
  if (!iso) return '-';
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1)  return 'à l\'instant';
  if (m < 60) return `il y a ${m}min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `il y a ${h}h`;
  return fmtDate(iso);
}

/* ===== API ERROR FORMATTER ===== */
// FastAPI peut retourner detail: string  OU  detail: [{loc, msg, type}] (Pydantic)
function fmtApiError(data) {
  if (!data) return 'Erreur inconnue.';
  const d = data.detail;
  if (!d) return data.message || JSON.stringify(data);
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map(e => e.msg || JSON.stringify(e)).join(' · ');
  return JSON.stringify(d);
}

/* ===== BADGE HELPERS ===== */
function statusBadge(s) {
  const map = { completed: 'success', success: 'success', failed: 'danger', pending: 'warning', processing: 'info' };
  const lbl = { completed: 'Terminé', success: 'Succès', failed: 'Échec', pending: 'En attente', processing: 'En cours' };
  return `<span class="badge badge-${map[s]||'secondary'}">${lbl[s]||s}</span>`;
}

function actionBadge(a) {
  const map = { upload: 'secondary', analyze: 'info', generate: 'primary', email: 'success' };
  const lbl = { upload: 'Upload', analyze: 'Analyse', generate: 'Génération', email: 'Email' };
  return `<span class="badge badge-${map[a]||'secondary'}">${lbl[a]||a}</span>`;
}

/* ===== NAVBAR SVG ICONS (inline) ===== */
const ICONS = {
  upload: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>`,
  history:`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="12 8 12 12 14 14"/><path d="M3.05 11a9 9 0 1 1 .5 4M3 21v-6h6"/></svg>`,
  user:   `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`,
  admin:  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>`,
  logout: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>`,
};
