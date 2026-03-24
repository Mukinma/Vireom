/* ── DOM References ── */

const usersList = document.getElementById('usersList');
const logsList = document.getElementById('logsList');
const createUserBtn = document.getElementById('createUserBtn');
const newUserName = document.getElementById('newUserName');
const createResult = document.getElementById('createResult');
const captureUserSelect = document.getElementById('captureUserSelect');
const captureBtn = document.getElementById('captureBtn');
const trainBtn = document.getElementById('trainBtn');
const trainResult = document.getElementById('trainResult');
const cfgThreshold = document.getElementById('cfgThreshold');
const cfgOpenSec = document.getElementById('cfgOpenSec');
const cfgMaxAttempts = document.getElementById('cfgMaxAttempts');
const saveConfigBtn = document.getElementById('saveConfigBtn');
const restartBtn = document.getElementById('restartBtn');
const manualOpenAdminBtn = document.getElementById('manualOpenAdminBtn');
const adminToast = document.getElementById('adminToast');
const adminToastText = document.getElementById('adminToastText');
const adminToastSub = document.getElementById('adminToastSub');

const statToday = document.getElementById('statToday');
const statGranted = document.getElementById('statGranted');
const statDenied = document.getElementById('statDenied');
const statManual = document.getElementById('statManual');

const resumenHero = document.getElementById('resumenHero');
const resumenStatusChip = document.getElementById('resumenStatusChip');
const resumenStatusLabel = document.getElementById('resumenStatusLabel');
const resumenStatusTitle = document.getElementById('resumenStatusTitle');
const resumenStatusMeta = document.getElementById('resumenStatusMeta');
const resumenStatusCaption = document.getElementById('resumenStatusCaption');
const resumenInlineAlert = document.getElementById('resumenInlineAlert');
const resumenInlineAlertBadge = document.getElementById('resumenInlineAlertBadge');
const resumenInlineAlertText = document.getElementById('resumenInlineAlertText');
const resumenMetricActiveUsers = document.getElementById('resumenMetricActiveUsers');
const resumenMetricToday = document.getElementById('resumenMetricToday');
const resumenMetricSuccess = document.getElementById('resumenMetricSuccess');
const resumenMetricManual = document.getElementById('resumenMetricManual');
const resumenActionHint = document.getElementById('resumenActionHint');
const resumenActionStack = document.getElementById('resumenActionStack');
const resumenTimelineList = document.getElementById('resumenTimelineList');
const resumenTimelineMeta = document.getElementById('resumenTimelineMeta');

const resumenActionButtons = {
  registro: document.getElementById('resumenActionRegistro'),
  accesos: document.getElementById('resumenActionAccesos'),
  personas: document.getElementById('resumenActionPersonas'),
};

const userSearch = document.getElementById('userSearch');
const logFilterResult = document.getElementById('logFilterResult');

let adminToastTimer = null;
let cachedUsers = [];
let cachedLogs = [];
let cachedStatus = {};
let dashboardReady = false;

/* ── Toast ── */

function showAdminToast({
  text = 'Notificacion',
  sub = '',
  cls = 'processing',
  timeout = 2600,
} = {}) {
  if (!adminToast || !adminToastText || !adminToastSub) return;

  adminToastText.textContent = text;
  adminToastSub.textContent = sub;
  adminToast.classList.remove('is-hidden', 'success', 'error', 'warning', 'processing');
  adminToast.classList.add(cls, 'is-visible');

  if (adminToastTimer) clearTimeout(adminToastTimer);

  adminToastTimer = setTimeout(() => {
    adminToast.classList.remove('is-visible');
    setTimeout(() => adminToast.classList.add('is-hidden'), 180);
  }, timeout);
}

function getErrorMessage(error, fallback = 'No se pudo completar la operacion') {
  const raw = String(error?.message || '').trim();
  if (!raw || raw.startsWith('<')) return fallback;
  return raw.length > 120 ? `${raw.slice(0, 117)}...` : raw;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/* ── API helper ── */

async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!response.ok) {
    const txt = await response.text();
    throw new Error(txt || 'Error de API');
  }
  if (response.status === 204) return null;
  return response.json();
}

/* ── Helpers ── */

function parseDateTime(raw) {
  if (!raw) return null;
  const match = String(raw).trim().match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?$/);
  if (!match) return null;
  const [, year, month, day, hour = '00', minute = '00', second = '00'] = match;
  return new Date(
    Number(year),
    Number(month) - 1,
    Number(day),
    Number(hour),
    Number(minute),
    Number(second),
  );
}

function formatLogMoment(raw) {
  const date = parseDateTime(raw);
  if (!date || Number.isNaN(date.getTime())) return 'sin hora';

  const now = new Date();
  const sameDay = (
    date.getFullYear() === now.getFullYear()
    && date.getMonth() === now.getMonth()
    && date.getDate() === now.getDate()
  );

  return sameDay
    ? new Intl.DateTimeFormat('es-MX', { hour: '2-digit', minute: '2-digit' }).format(date)
    : new Intl.DateTimeFormat('es-MX', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(date);
}

function formatPercent(value) {
  if (value == null || Number.isNaN(value)) return '—';
  return `${Math.round(value * 100)}%`;
}

function formatConfidence(value) {
  if (value == null || value === '') return 'Sin confianza';
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return 'Sin confianza';
  return `${numeric.toFixed(1)}% confianza`;
}

function getDoorState(status) {
  return String(status?.door || status?.gpio || '').trim().toLowerCase();
}

function getAccessResultMeta(result) {
  const normalized = String(result || '').trim().toLowerCase();

  if (normalized.includes('autorizado') || normalized.includes('granted')) {
    return {
      label: 'Reconocido',
      badgeClass: 'badge--active',
      timelineTone: 'is-success',
      isGranted: true,
      isDenied: false,
      isManual: false,
      isBlocked: false,
      filterKey: 'autorizado',
    };
  }

  if (normalized.includes('manual')) {
    return {
      label: 'Manual',
      badgeClass: 'badge--manual',
      timelineTone: 'is-manual',
      isGranted: false,
      isDenied: false,
      isManual: true,
      isBlocked: false,
      filterKey: 'manual',
    };
  }

  if (normalized.includes('bloqueo')) {
    return {
      label: 'Bloqueado',
      badgeClass: 'badge--blocked',
      timelineTone: 'is-blocked',
      isGranted: false,
      isDenied: true,
      isManual: false,
      isBlocked: true,
      filterKey: 'rechazado',
    };
  }

  if (
    normalized.includes('rechazado')
    || normalized.includes('denegado')
    || normalized.includes('denied')
    || normalized.includes('desconocido')
    || normalized.includes('error')
  ) {
    return {
      label: 'Rechazado',
      badgeClass: 'badge--inactive',
      timelineTone: 'is-danger',
      isGranted: false,
      isDenied: true,
      isManual: false,
      isBlocked: false,
      filterKey: 'rechazado',
    };
  }

  return {
    label: result || 'Sin dato',
    badgeClass: 'badge--neutral',
    timelineTone: 'is-neutral',
    isGranted: false,
    isDenied: false,
    isManual: false,
    isBlocked: false,
    filterKey: '',
  };
}

function getCameraSummary(state) {
  const normalized = String(state || '').toLowerCase();
  if (normalized === 'online') return 'Camara en linea';
  if (normalized === 'degraded') return 'camara degradada';
  if (normalized === 'error') return 'camara con error';
  return 'camara fuera de linea';
}

function getModelSummary(state) {
  const normalized = String(state || '').toLowerCase();
  if (normalized === 'loaded') return 'modelo cargado';
  if (normalized === 'error') return 'modelo con error';
  return 'modelo no cargado';
}

function getDoorSummary(state) {
  if (state === 'ready' || state === 'closed') return 'puerta lista';
  if (state === 'mock') return 'puerta en simulacion';
  if (state) return 'puerta con alerta';
  return 'puerta sin estado';
}

function formatSystemCaption(status) {
  return `${getCameraSummary(status?.camera)}, ${getModelSummary(status?.model)} y ${getDoorSummary(getDoorState(status))}.`;
}

function upperFirst(value) {
  const text = String(value || '').trim();
  if (!text) return '';
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/* ── Render: Users table ── */

function renderUsers(users) {
  if (!usersList) return;
  const rows = users.map((user) => `
    <tr>
      <td>${user.id}</td>
      <td>${escapeHtml(user.nombre)}</td>
      <td><span class="badge ${user.activo ? 'badge--active' : 'badge--inactive'}">${user.activo ? 'Activo' : 'Inactivo'}</span></td>
      <td>
        <button class="btn btn--sm btn-secondary" onclick="toggleUser(${user.id}, ${user.activo ? 'false' : 'true'})">
          ${user.activo ? 'Desactivar' : 'Activar'}
        </button>
        <button class="btn-delete-user" onclick="deleteUser(${u.id}, '${u.nombre.replace(/'/g, "\\'")}')" title="Eliminar usuario" aria-label="Eliminar ${u.nombre}">
          <svg class="icon" aria-hidden="true"><use href="/static/icons/lucide/lucide-sprite.svg#x"></use></svg>
        </button>
      </td>
    </tr>
  `).join('');

  usersList.innerHTML = `
    <table>
      <thead><tr><th>ID</th><th>Nombre</th><th>Estado</th><th>Accion</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="4" class="text-center muted">Sin personas registradas</td></tr>'}</tbody>
    </table>
  `;
}

/* ── Render: Logs table ── */

function renderLogs(logs) {
  if (!logsList) return;
  const rows = logs.map((log) => {
    const resultMeta = getAccessResultMeta(log.resultado);
    return `
    <tr>
      <td>${escapeHtml(log.fecha || '-')}</td>
      <td>${escapeHtml(log.nombre || '-')}</td>
      <td>${log.confianza == null ? '-' : Number(log.confianza).toFixed(1)}</td>
      <td><span class="badge ${resultMeta.badgeClass}">${escapeHtml(resultMeta.label)}</span></td>
    </tr>`;
  }).join('');

  logsList.innerHTML = `
    <table>
      <thead><tr><th>Fecha</th><th>Persona</th><th>Confianza</th><th>Resultado</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="4" class="text-center muted">Sin registros</td></tr>'}</tbody>
    </table>
  `;
}

/* ── Populate person selector (Registro facial) ── */

function populateUserSelect(users) {
  if (!captureUserSelect) return;
  const options = users
    .filter((user) => user.activo)
    .map((user) => `<option value="${user.id}">${escapeHtml(user.nombre)} (ID ${user.id})</option>`)
    .join('');
  captureUserSelect.innerHTML = `<option value="">Seleccionar persona...</option>${options}`;
}

/* ── Stats & Summary ── */

function computeLogStats(logs) {
  const now = new Date();
  const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  let today = 0;
  let granted = 0;
  let denied = 0;
  let manual = 0;

  logs.forEach((log) => {
    const isToday = log.fecha && String(log.fecha).startsWith(todayStr);
    if (!isToday) return;

    const resultMeta = getAccessResultMeta(log.resultado);
    today += 1;
    if (resultMeta.isGranted) granted += 1;
    else if (resultMeta.isManual) manual += 1;
    else if (resultMeta.isDenied) denied += 1;
  });

  return { today, granted, denied, manual };
}

function renderLogStats(stats) {
  if (statToday) statToday.textContent = stats.today;
  if (statGranted) statGranted.textContent = stats.granted;
  if (statDenied) statDenied.textContent = stats.denied;
  if (statManual) statManual.textContent = stats.manual;
}

function buildActionPlan(model) {
  if (model.isOnboarding) {
    return {
      primary: 'personas',
      secondary: ['registro', 'accesos'],
      hint: 'Crea la primera identidad activa.',
    };
  }

  if (!model.modelReady) {
    return {
      primary: 'registro',
      secondary: ['personas', 'accesos'],
      hint: 'Completa muestras y actualiza el modelo.',
    };
  }

  if (model.alertState === 'critical' || model.alertState === 'warning') {
    return {
      primary: 'accesos',
      secondary: ['registro', 'personas'],
      hint: 'Revisa lo ultimo antes de seguir.',
    };
  }

  return {
    primary: 'registro',
    secondary: ['accesos', 'personas'],
    hint: 'Refuerza el reconocimiento o valida el dia.',
  };
}

function buildAlertCopy(model) {
  if (model.isCritical) {
    const issues = [];
    if (!model.cameraReady) issues.push(getCameraSummary(model.status.camera));
    if (!model.modelReady) issues.push(getModelSummary(model.status.model));
    if (!model.doorReady) issues.push(getDoorSummary(model.doorState));

    return {
      visible: true,
      badge: 'Critico',
      message: model.lastEvent
        ? `${upperFirst(issues.join(' · '))}. Ultimo evento ${formatLogMoment(model.lastEvent.fecha)}.`
        : `${upperFirst(issues.join(' · '))}. Corrige la falla antes de seguir.`,
    };
  }

  if (model.isOnboarding) {
    return {
      visible: true,
      badge: 'Preparacion',
      message: 'Agrega la primera identidad para habilitar reconocimiento.',
    };
  }

  if (model.alertState === 'warning') {
    const lastResult = model.lastEvent ? getAccessResultMeta(model.lastEvent.resultado) : null;
    const warningLead = lastResult?.isBlocked
      ? 'Ultimo intento bloqueado'
      : lastResult?.isDenied
        ? 'Ultimo intento rechazado'
        : 'Actividad que conviene revisar';
    const streakText = model.failedAttemptsConsecutive > 0
      ? ` · ${model.failedAttemptsConsecutive} fallos seguidos`
      : model.todayDenied > 0
        ? ` · ${model.todayDenied} rechazo(s) hoy`
        : '';

    return {
      visible: true,
      badge: 'Revision',
      message: `${warningLead}${streakText}.`,
    };
  }

  return {
    visible: false,
    badge: '',
    message: '',
  };
}

function computeResumenModel(users, logs, status) {
  const activeUsers = users.filter((user) => user.activo).length;
  const stats = computeLogStats(logs);
  const lastEvent = logs[0] || null;
  const doorState = getDoorState(status);
  const cameraReady = String(status?.camera || '').toLowerCase() === 'online';
  const modelReady = String(status?.model || '').toLowerCase() === 'loaded';
  const doorReady = doorState === 'ready' || doorState === 'closed' || doorState === 'mock';
  const failedAttemptsConsecutive = Number(status?.failed_attempts_consecutive || 0);
  const successRateToday = (stats.granted + stats.denied) > 0
    ? stats.granted / (stats.granted + stats.denied)
    : null;
  const lastResult = lastEvent ? getAccessResultMeta(lastEvent.resultado) : null;

  let alertState = 'ok';
  if (!cameraReady || !modelReady || !doorReady) {
    alertState = 'critical';
  } else if (failedAttemptsConsecutive > 0 || lastResult?.isDenied) {
    alertState = 'warning';
  }

  const isOnboarding = activeUsers === 0;
  const heroHeadline = alertState === 'critical'
    ? 'Atencion inmediata'
    : (alertState === 'warning' || isOnboarding)
      ? 'Revision recomendada'
      : 'Sistema listo';

  const heroMetaParts = [
    `${activeUsers} ${activeUsers === 1 ? 'persona' : 'personas'}`,
    stats.today > 0 ? `${stats.today} hoy` : 'sin actividad hoy',
    `${stats.granted} reconocidos`,
  ];

  if (lastEvent) {
    heroMetaParts.push(`ultimo evento ${formatLogMoment(lastEvent.fecha)}`);
  }

  const tone = alertState === 'critical' ? 'critical' : ((alertState === 'warning' || isOnboarding) ? 'warning' : 'ok');
  const statusChipText = alertState === 'critical'
    ? 'Critico'
    : (alertState === 'warning' ? 'Vigilar' : (isOnboarding ? 'Preparacion' : 'Estable'));

  return {
    status,
    doorState,
    cameraReady,
    modelReady,
    doorReady,
    isCritical: alertState === 'critical',
    isOnboarding,
    alertState,
    tone,
    statusChipText,
    heroLabel: 'Estado del sistema',
    heroHeadline,
    heroMeta: heroMetaParts.join(' · '),
    statusCaption: formatSystemCaption(status),
    activeUsers,
    todayTotal: stats.today,
    todayGranted: stats.granted,
    todayDenied: stats.denied,
    todayManual: stats.manual,
    successRateToday,
    lastEvent,
    failedAttemptsConsecutive,
    attemptsProcessed: Number(status?.attempts_processed || 0),
    gpioActivations: Number(status?.gpio_activations || 0),
    actionPlan: buildActionPlan({
      isOnboarding,
      modelReady,
      alertState,
    }),
    timeline: logs.slice(0, 5),
  };
}

function renderResumenTimeline(items) {
  if (!resumenTimelineList) return;
  if (resumenTimelineMeta) {
    resumenTimelineMeta.textContent = items.length ? `${items.length} eventos` : 'Sin movimiento';
  }

  if (!items.length) {
    resumenTimelineList.innerHTML = '<p class="resumen-empty-state">Sin accesos recientes.</p>';
    return;
  }

  resumenTimelineList.innerHTML = items.map((item) => {
    const resultMeta = getAccessResultMeta(item.resultado);
    const confidenceMarkup = item.confianza == null
      ? ''
      : `<span class="resumen-timeline__confidence">${escapeHtml(formatConfidence(item.confianza))}</span>`;

    return `
      <article class="resumen-timeline__item ${resultMeta.timelineTone}">
        <div class="resumen-timeline__marker" aria-hidden="true"></div>
        <div class="resumen-timeline__content">
          <div class="resumen-timeline__row">
            <strong>${escapeHtml(item.nombre || 'Desconocido')}</strong>
            <span class="badge ${resultMeta.badgeClass}">${escapeHtml(resultMeta.label)}</span>
          </div>
          <div class="resumen-timeline__row resumen-timeline__row--meta">
            <span class="resumen-timeline__time">${escapeHtml(formatLogMoment(item.fecha))}</span>
            ${confidenceMarkup}
          </div>
        </div>
      </article>
    `;
  }).join('');
}

function renderResumenActions(actionPlan) {
  if (!resumenActionStack) return;

  Object.values(resumenActionButtons).forEach((button) => {
    button?.classList.remove('is-primary', 'is-secondary', 'is-tertiary');
  });

  [actionPlan.primary, ...actionPlan.secondary].forEach((key, index) => {
    const button = resumenActionButtons[key];
    if (!button) return;
    button.classList.add(index === 0 ? 'is-primary' : (index === 1 ? 'is-secondary' : 'is-tertiary'));
    resumenActionStack.appendChild(button);
  });

  if (resumenActionHint) resumenActionHint.textContent = actionPlan.hint;
}

function renderResumen(model) {
  if (!resumenHero) return;

  const alertCopy = buildAlertCopy(model);

  resumenHero.classList.remove('is-ok', 'is-warning', 'is-critical');
  resumenHero.classList.add(`is-${model.tone}`);
  resumenHero.classList.toggle('has-inline-alert', Boolean(alertCopy.visible));

  if (resumenStatusChip) resumenStatusChip.textContent = model.statusChipText;
  if (resumenStatusLabel) resumenStatusLabel.textContent = model.heroLabel;
  if (resumenStatusTitle) resumenStatusTitle.textContent = model.heroHeadline;
  if (resumenStatusMeta) resumenStatusMeta.textContent = model.heroMeta;
  if (resumenStatusCaption) resumenStatusCaption.textContent = model.statusCaption;
  if (resumenInlineAlert) resumenInlineAlert.hidden = !alertCopy.visible;
  if (resumenInlineAlertBadge) resumenInlineAlertBadge.textContent = alertCopy.badge;
  if (resumenInlineAlertText) resumenInlineAlertText.textContent = alertCopy.message;

  if (resumenMetricActiveUsers) resumenMetricActiveUsers.textContent = model.activeUsers;
  if (resumenMetricToday) resumenMetricToday.textContent = model.todayTotal;
  if (resumenMetricSuccess) resumenMetricSuccess.textContent = formatPercent(model.successRateToday);
  if (resumenMetricManual) resumenMetricManual.textContent = model.todayManual;

  renderResumenActions(model.actionPlan);
  renderResumenTimeline(model.timeline);
  resumenHero.closest('.resumen-layout')?.classList.add('is-live');
}

function renderDashboardFromCache() {
  const stats = computeLogStats(cachedLogs);
  const resumenModel = computeResumenModel(cachedUsers, cachedLogs, cachedStatus);
  renderLogStats(stats);
  renderResumen(resumenModel);
}

/* ── Search & Filter ── */

function applyUserSearch() {
  const q = (userSearch?.value || '').trim().toLowerCase();
  if (!q) {
    renderUsers(cachedUsers);
    return;
  }
  renderUsers(cachedUsers.filter((user) => user.nombre.toLowerCase().includes(q) || String(user.id).includes(q)));
}

function applyLogFilter() {
  const filter = (logFilterResult?.value || '').toLowerCase();
  if (!filter) {
    renderLogs(cachedLogs);
    return;
  }

  renderLogs(cachedLogs.filter((log) => {
    const resultMeta = getAccessResultMeta(log.resultado);
    return resultMeta.filterKey === filter;
  }));
}

userSearch?.addEventListener('input', applyUserSearch);
logFilterResult?.addEventListener('change', applyLogFilter);

/* ── Data loaders ── */

async function loadUsers() {
  cachedUsers = await api('/api/users');
  renderUsers(cachedUsers);
  populateUserSelect(cachedUsers);
  if (dashboardReady) renderDashboardFromCache();
  return cachedUsers;
}

async function loadLogs() {
  cachedLogs = await api('/api/access-logs?limit=200');
  applyLogFilter();
  if (dashboardReady) renderDashboardFromCache();
  return computeLogStats(cachedLogs);
}

async function loadStatus() {
  cachedStatus = await api('/api/status');
  if (dashboardReady) renderDashboardFromCache();
  return cachedStatus;
}

async function loadConfig() {
  const cfg = await api('/api/config');
  if (cfgThreshold) cfgThreshold.value = cfg.umbral_confianza;
  if (cfgOpenSec) cfgOpenSec.value = cfg.tiempo_apertura_seg;
  if (cfgMaxAttempts) cfgMaxAttempts.value = cfg.max_intentos;
}

/* ── Actions: Users ── */

window.toggleUser = async function (userId, active) {
  const action = active ? 'activar' : 'desactivar';
  if (!confirm(`¿Estas seguro de que deseas ${action} al usuario ID ${userId}?`)) return;
  try {
    await api(`/api/users/${userId}`, {
      method: 'PATCH',
      body: JSON.stringify({ activo: active }),
    });
    await loadUsers();
    showAdminToast({
      text: active ? 'Persona activada' : 'Persona desactivada',
      sub: `ID ${userId} actualizado`,
      cls: 'success',
    });
  } catch (error) {
    console.error(error);
    showAdminToast({ text: 'No se pudo actualizar', sub: getErrorMessage(error), cls: 'error', timeout: 3200 });
  }
};

window.deleteUser = async function(userId, nombre) {
  if (!confirm(`¿Eliminar al usuario "${nombre}" (ID ${userId})? Se borrarán sus muestras y se desvinculará de los accesos. Esta acción no se puede deshacer.`)) return;
  try {
    await api(`/api/users/${userId}`, { method: 'DELETE' });
    await loadUsers();
    showAdminToast({
      text: 'Usuario eliminado',
      sub: `${nombre} (ID ${userId}) fue eliminado`,
      cls: 'success',
    });
  } catch (error) {
    console.error(error);
    showAdminToast({
      text: 'No se pudo eliminar',
      sub: getErrorMessage(error),
      cls: 'error',
      timeout: 3200,
    });
  }
};

createUserBtn?.addEventListener('click', async () => {
  const nombre = (newUserName.value || '').trim();
  if (!nombre) return;
  try {
    const user = await api('/api/users', {
      method: 'POST',
      body: JSON.stringify({ nombre }),
    });
    newUserName.value = '';
    await loadUsers();

    if (createResult) {
      const uid = user?.id ?? '';
      createResult.hidden = false;
      createResult.innerHTML = `<svg class="icon" aria-hidden="true"><use href="/static/icons/lucide/lucide-sprite.svg#check-filled"></use></svg> ${escapeHtml(nombre)} registrado${uid ? ` (ID ${uid})` : ''}. <a href="#registro" class="link">Ir a registro facial -></a>`;
      setTimeout(() => { createResult.hidden = true; }, 10000);
    }

    showAdminToast({ text: 'Persona registrada', sub: `${nombre} fue agregado`, cls: 'success' });
  } catch (error) {
    console.error(error);
    showAdminToast({ text: 'No se pudo crear', sub: getErrorMessage(error), cls: 'error', timeout: 3200 });
  }
});

/* ── Actions: Capture & Train ── */

captureBtn?.addEventListener('click', async () => {
  const userId = Number(captureUserSelect?.value);
  if (!userId) {
    showAdminToast({ text: 'Selecciona una persona', sub: 'Elige a quien quieres capturar', cls: 'warning', timeout: 2400 });
    return;
  }
  captureBtn.disabled = true;
  captureBtn.innerHTML = '<svg class="icon spin" aria-hidden="true"><use href="/static/icons/lucide/lucide-sprite.svg#loader"></use></svg> <span>Capturando...</span>';
  showAdminToast({ text: 'Capturando muestras...', sub: 'Mira la camara', cls: 'processing', timeout: 15000 });
  try {
    const result = await api(`/api/users/${userId}/capture?count=30`, { method: 'POST' });
    showAdminToast({ text: 'Captura finalizada', sub: `Muestras: ${result.saved}/${result.requested}`, cls: 'success', timeout: 3200 });
  } catch (error) {
    console.error(error);
    showAdminToast({ text: 'Error en captura', sub: getErrorMessage(error), cls: 'error', timeout: 3200 });
  } finally {
    captureBtn.disabled = false;
    captureBtn.innerHTML = '<svg class="icon" aria-hidden="true"><use href="/static/icons/lucide/lucide-sprite.svg#focus-filled"></use></svg> <span>Tomar 30 fotos del rostro</span>';
  }
});

trainBtn?.addEventListener('click', async () => {
  if (!confirm('¿Deseas reentrenar el modelo? Esto reemplazara el modelo actual.')) return;
  trainBtn.disabled = true;
  trainBtn.innerHTML = '<svg class="icon spin" aria-hidden="true"><use href="/static/icons/lucide/lucide-sprite.svg#loader"></use></svg> <span>Procesando...</span>';
  showAdminToast({ text: 'Entrenando modelo...', sub: 'Esto puede tardar unos segundos', cls: 'processing', timeout: 15000 });
  try {
    const result = await api('/api/train', { method: 'POST' });
    if (trainResult) trainResult.textContent = `Entrenado con ${result.samples_used} muestras de ${result.unique_users} personas.`;
    await loadStatus();
    showAdminToast({ text: 'Entrenamiento completado', sub: `${result.samples_used} muestras de ${result.unique_users} personas`, cls: 'success', timeout: 3200 });
  } catch (error) {
    console.error(error);
    if (trainResult) trainResult.textContent = getErrorMessage(error, 'No se pudo entrenar el modelo.');
    showAdminToast({ text: 'Error de entrenamiento', sub: getErrorMessage(error), cls: 'error', timeout: 3400 });
  } finally {
    trainBtn.disabled = false;
    trainBtn.innerHTML = '<svg class="icon" aria-hidden="true"><use href="/static/icons/lucide/lucide-sprite.svg#refresh-filled"></use></svg> <span>Actualizar reconocimiento</span>';
  }
});

/* ── Actions: Config ── */

saveConfigBtn?.addEventListener('click', async () => {
  try {
    await api('/api/config', {
      method: 'PUT',
      body: JSON.stringify({
        umbral_confianza: Number(cfgThreshold.value),
        tiempo_apertura_seg: Number(cfgOpenSec.value),
        max_intentos: Number(cfgMaxAttempts.value),
      }),
    });
    showAdminToast({ text: 'Configuracion guardada', sub: 'Parametros aplicados', cls: 'success' });
  } catch (error) {
    console.error(error);
    showAdminToast({ text: 'No se pudo guardar', sub: getErrorMessage(error), cls: 'error', timeout: 3200 });
  }
});

/* ── Actions: Maintenance ── */

restartBtn?.addEventListener('click', async () => {
  if (!confirm('¿Estas seguro? Se interrumpira brevemente el servicio.')) return;
  try {
    await api('/api/restart', { method: 'POST' });
    showAdminToast({ text: 'Reinicio solicitado', sub: 'El sistema se reiniciara', cls: 'warning', timeout: 3400 });
  } catch (error) {
    console.error(error);
    showAdminToast({ text: 'Error al reiniciar', sub: getErrorMessage(error), cls: 'error', timeout: 3200 });
  }
});

manualOpenAdminBtn?.addEventListener('click', async () => {
  try {
    await api('/api/manual-open', { method: 'POST' });
    await loadStatus();
    showAdminToast({ text: 'Puerta abierta', sub: 'Comando enviado al actuador', cls: 'processing' });
  } catch (error) {
    console.error(error);
    showAdminToast({ text: 'No se pudo abrir', sub: getErrorMessage(error), cls: 'error', timeout: 3200 });
  }
});

/* ── Init ── */

async function init() {
  window.CameraPITheme?.initTheme();
  window.CameraPITheme?.bindToggleButtons();

  await Promise.all([
    loadUsers(),
    loadLogs(),
    loadStatus(),
    loadConfig(),
  ]);

  dashboardReady = true;
  renderDashboardFromCache();

  setInterval(() => {
    Promise.all([loadLogs(), loadStatus()]).catch((error) => {
      console.error(error);
    });
  }, 3000);
}

init().catch((err) => {
  console.error(err);
  showAdminToast({
    text: 'Sesion invalida o error de carga',
    sub: 'Vuelve a iniciar sesion administrativa',
    cls: 'error',
    timeout: 3600,
  });
});

