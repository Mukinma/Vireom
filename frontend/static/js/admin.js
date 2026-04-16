/* ── DOM References ── */

const usersList = document.getElementById('usersList');
const logsList = document.getElementById('logsList');
const createUserBtn = document.getElementById('createUserBtn');
const newUserName = document.getElementById('newUserName');
const createResult = document.getElementById('createResult');
const trainBtn = document.getElementById('trainBtn');
const trainResult = document.getElementById('trainResult');
const manualOpenAdminBtn = document.getElementById('manualOpenAdminBtn');

// Settings — config refs
const cfgThreshold = document.getElementById('cfgThreshold');
const applyThresholdBtn = document.getElementById('applyThresholdBtn');
const recogSegment = document.getElementById('recogSegment');
const recogPresetSummary = document.getElementById('recogPresetSummary');
const recogCustomValue = document.getElementById('recogCustomValue');
const maxAttemptsStepper = document.getElementById('maxAttemptsStepper');
const maxAttemptsValue = document.getElementById('maxAttemptsValue');
const openSecStepper = document.getElementById('openSecStepper');
const openSecValue = document.getElementById('openSecValue');
const doorTimeSummary = document.getElementById('doorTimeSummary');

// Settings — diagnostics
const diagnosticsSummary = document.getElementById('diagnosticsSummary');
const diagnosticsRootIcon = document.getElementById('diagnosticsRootIcon');
const diagnosticsDetailList = document.getElementById('diagnosticsDetailList');

// Settings — account
const accountDisplayName = document.getElementById('accountDisplayName');
const accountUsernameSummary = document.getElementById('accountUsernameSummary');
const changePasswordBtn = document.getElementById('changePasswordBtn');
const passwordSheet = document.getElementById('passwordSheet');
const passwordSheetBackdrop = document.getElementById('passwordSheetBackdrop');
const currentPasswordInput = document.getElementById('currentPasswordInput');
const newPasswordInput = document.getElementById('newPasswordInput');
const passwordSheetError = document.getElementById('passwordSheetError');
const passwordSheetCancel = document.getElementById('passwordSheetCancel');
const passwordSheetConfirm = document.getElementById('passwordSheetConfirm');

// Settings — device info
const deviceInfoName = document.getElementById('deviceInfoName');
const deviceInfoVersion = document.getElementById('deviceInfoVersion');
const deviceInfoHostname = document.getElementById('deviceInfoHostname');
const deviceInfoIp = document.getElementById('deviceInfoIp');
const deviceInfoDisk = document.getElementById('deviceInfoDisk');
const deviceInfoUptime = document.getElementById('deviceInfoUptime');
const adminToast = document.getElementById('adminToast');
const adminToastText = document.getElementById('adminToastText');
const adminToastSub = document.getElementById('adminToastSub');
const adminDialog = document.getElementById('adminDialog');
const adminDialogBackdrop = document.getElementById('adminDialogBackdrop');
const adminDialogPanel = document.getElementById('adminDialogPanel');
const adminDialogEyebrow = document.getElementById('adminDialogEyebrow');
const adminDialogTitle = document.getElementById('adminDialogTitle');
const adminDialogText = document.getElementById('adminDialogText');
const adminDialogCancel = document.getElementById('adminDialogCancel');
const adminDialogConfirm = document.getElementById('adminDialogConfirm');

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
  accesos: document.getElementById('resumenActionAccesos'),
  personas: document.getElementById('resumenActionPersonas'),
};

const userSearch = document.getElementById('userSearch');
const logFilterResult = document.getElementById('logFilterResult');
const logAdvancedToggle = document.getElementById('logAdvancedToggle');
const logAdvancedPanel = document.getElementById('logAdvancedPanel');
const logAdvancedReset = document.getElementById('logAdvancedReset');
const logSearch = document.getElementById('logSearch');
const logDateFrom = document.getElementById('logDateFrom');
const logDateTo = document.getElementById('logDateTo');
const logConfidenceMin = document.getElementById('logConfidenceMin');
const logConfidenceMax = document.getElementById('logConfidenceMax');

let adminToastTimer = null;
let cachedUsers = [];
let cachedLogs = [];
let cachedStatus = {};
let dashboardReady = false;
let adminDialogResolver = null;
let adminDialogRestoreFocus = null;

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

function setAdminDialogTone(tone = 'warning') {
  if (!adminDialogPanel || !adminDialogConfirm) return;

  adminDialogPanel.classList.remove(
    'admin-dialog__panel--warning',
    'admin-dialog__panel--danger',
    'admin-dialog__panel--primary',
  );
  adminDialogPanel.classList.add(`admin-dialog__panel--${tone}`);

  adminDialogConfirm.classList.remove('btn-primary', 'btn-secondary', 'btn-danger');
  if (tone === 'danger') {
    adminDialogConfirm.classList.add('btn-danger');
    return;
  }
  if (tone === 'primary') {
    adminDialogConfirm.classList.add('btn-primary');
    return;
  }
  adminDialogConfirm.classList.add('btn-secondary');
}

function closeAdminDialog(confirmed) {
  if (!adminDialog || !adminDialogResolver) return;

  const resolve = adminDialogResolver;
  adminDialogResolver = null;

  adminDialog.classList.add('is-hidden');
  adminDialog.setAttribute('aria-hidden', 'true');

  if (adminDialogRestoreFocus?.focus) {
    adminDialogRestoreFocus.focus({ preventScroll: true });
  }
  adminDialogRestoreFocus = null;
  resolve(Boolean(confirmed));
}

function openAdminConfirm(options = {}) {
  const {
    eyebrow = 'Confirmar accion',
    title = 'Deseas continuar?',
    text = 'Esta accion requiere confirmacion.',
    confirmLabel = 'Continuar',
    cancelLabel = 'Cancelar',
    tone = 'warning',
  } = options;

  if (!adminDialog || !adminDialogPanel || !adminDialogConfirm || !adminDialogCancel) {
    return Promise.resolve(window.confirm(text || title));
  }

  if (adminDialogResolver) closeAdminDialog(false);

  adminDialogRestoreFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  adminDialogEyebrow.textContent = eyebrow;
  adminDialogTitle.textContent = title;
  adminDialogText.textContent = text;
  adminDialogCancel.textContent = cancelLabel;
  adminDialogConfirm.textContent = confirmLabel;
  setAdminDialogTone(tone);

  adminDialog.classList.remove('is-hidden');
  adminDialog.setAttribute('aria-hidden', 'false');

  return new Promise((resolve) => {
    adminDialogResolver = resolve;
    window.requestAnimationFrame(() => {
      adminDialogPanel.focus({ preventScroll: true });
    });
  });
}

function handleAdminDialogKeydown(event) {
  if (!adminDialogResolver) return;
  if (event.key !== 'Escape') return;
  event.preventDefault();
  closeAdminDialog(false);
}

adminDialogBackdrop?.addEventListener('click', () => closeAdminDialog(false));
adminDialogCancel?.addEventListener('click', () => closeAdminDialog(false));
adminDialogConfirm?.addEventListener('click', () => closeAdminDialog(true));
window.addEventListener('keydown', handleAdminDialogKeydown);

window.CameraPIConfirm = {
  open: openAdminConfirm,
};

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
  const rows = users.map((user) => {
    const escapedName = escapeHtml(user.nombre).replace(/'/g, "\\'");
    return `
    <tr>
      <td>${user.id}</td>
      <td>${escapeHtml(user.nombre)}</td>
      <td><span class="badge ${user.activo ? 'badge--active' : 'badge--inactive'}">${user.activo ? 'Activo' : 'Inactivo'}</span></td>
      <td class="table-actions">
        <button
          class="user-action-btn user-action-btn--primary"
          type="button"
          onclick="startEnrollForUser(${user.id}, '${escapedName}')"
          title="Registrar ${escapeHtml(user.nombre)}"
          aria-label="Registrar ${escapeHtml(user.nombre)}"
          ${user.activo ? '' : ' disabled'}
        >
          <svg class="icon" aria-hidden="true"><use href="/static/icons/lucide/lucide-sprite.svg#camera"></use></svg>
          <span>Registrar</span>
        </button>
        <button
          class="user-action-btn user-action-btn--neutral"
          type="button"
          onclick="toggleUser(${user.id}, ${user.activo ? 'false' : 'true'})"
          title="${user.activo ? 'Desactivar' : 'Activar'} ${escapeHtml(user.nombre)}"
          aria-label="${user.activo ? 'Desactivar' : 'Activar'} ${escapeHtml(user.nombre)}"
        >
          <svg class="icon" aria-hidden="true"><use href="/static/icons/lucide/lucide-sprite.svg#${user.activo ? 'lock' : 'unlock'}"></use></svg>
          <span>${user.activo ? 'Desactivar' : 'Activar'}</span>
        </button>
        <button
          class="user-action-btn user-action-btn--danger"
          type="button"
          onclick="deleteUser(${user.id}, '${escapedName}')"
          title="Eliminar usuario"
          aria-label="Eliminar ${escapeHtml(user.nombre)}"
        >
          <svg class="icon" aria-hidden="true"><use href="/static/icons/lucide/lucide-sprite.svg#x"></use></svg>
          <span>Eliminar</span>
        </button>
      </td>
    </tr>`;
  }).join('');

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

/* ── Stats & Summary ── */

function computeLogStats(logs) {
  const utcTodayStr = new Date().toISOString().slice(0, 10);
  let today = 0;
  let granted = 0;
  let denied = 0;
  let manual = 0;

  logs.forEach((log) => {
    const rawDate = String(log.fecha || '').trim();
    const isToday = rawDate.slice(0, 10) === utcTodayStr;
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
      secondary: ['accesos'],
      hint: 'Crea la primera identidad activa.',
    };
  }

  if (!model.modelReady) {
    return {
      primary: 'personas',
      secondary: ['accesos'],
      hint: 'Agrega identidad y valida actividad reciente.',
    };
  }

  if (model.alertState === 'critical' || model.alertState === 'warning') {
    return {
      primary: 'accesos',
      secondary: ['personas'],
      hint: 'Revisa lo ultimo antes de seguir.',
    };
  }

  return {
    primary: 'accesos',
    secondary: ['personas'],
    hint: 'Valida actividad y mantén actualizado el padrón.',
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
  const searchText = (logSearch?.value || '').trim().toLowerCase();
  const dateFrom = (logDateFrom?.value || '').trim();
  const dateTo = (logDateTo?.value || '').trim();
  const confidenceMinRaw = (logConfidenceMin?.value || '').trim();
  const confidenceMaxRaw = (logConfidenceMax?.value || '').trim();
  const confidenceMin = confidenceMinRaw === '' ? null : Number(confidenceMinRaw);
  const confidenceMax = confidenceMaxRaw === '' ? null : Number(confidenceMaxRaw);

  const filtered = cachedLogs.filter((log) => {
    const resultMeta = getAccessResultMeta(log.resultado);
    if (filter && resultMeta.filterKey !== filter) return false;

    const datePart = String(log.fecha || '').slice(0, 10);
    if (dateFrom && (!datePart || datePart < dateFrom)) return false;
    if (dateTo && (!datePart || datePart > dateTo)) return false;

    if (searchText) {
      const haystack = [
        log.nombre,
        log.usuario_id,
        log.id,
        log.resultado,
        log.motivo,
      ].map((value) => String(value || '').toLowerCase()).join(' ');
      if (!haystack.includes(searchText)) return false;
    }

    if (confidenceMin != null && !Number.isNaN(confidenceMin)) {
      const currentConfidence = Number(log.confianza);
      if (Number.isNaN(currentConfidence) || currentConfidence < confidenceMin) return false;
    }

    if (confidenceMax != null && !Number.isNaN(confidenceMax)) {
      const currentConfidence = Number(log.confianza);
      if (Number.isNaN(currentConfidence) || currentConfidence > confidenceMax) return false;
    }

    return true;
  });

  renderLogs(filtered);
}

userSearch?.addEventListener('input', applyUserSearch);
logFilterResult?.addEventListener('change', applyLogFilter);
logSearch?.addEventListener('input', applyLogFilter);
logDateFrom?.addEventListener('change', applyLogFilter);
logDateTo?.addEventListener('change', applyLogFilter);
logConfidenceMin?.addEventListener('input', applyLogFilter);
logConfidenceMax?.addEventListener('input', applyLogFilter);

logAdvancedToggle?.addEventListener('click', () => {
  const willOpen = logAdvancedPanel?.hasAttribute('hidden');
  if (!logAdvancedPanel) return;
  if (willOpen) logAdvancedPanel.removeAttribute('hidden');
  else logAdvancedPanel.setAttribute('hidden', '');
  logAdvancedToggle.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
});

logAdvancedReset?.addEventListener('click', () => {
  if (logSearch) logSearch.value = '';
  if (logDateFrom) logDateFrom.value = '';
  if (logDateTo) logDateTo.value = '';
  if (logConfidenceMin) logConfidenceMin.value = '';
  if (logConfidenceMax) logConfidenceMax.value = '';
  if (logFilterResult) logFilterResult.value = '';
  applyLogFilter();
});

/* ── Data loaders ── */

async function loadUsers() {
  cachedUsers = await api('/api/users');
  renderUsers(cachedUsers);
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

/* ── Settings helpers ── */

const PRESETS = { 50: 'Estricto', 70: 'Equilibrado', 95: 'Permisivo' };

function getPresetName(umbral) {
  const num = Number(umbral);
  return PRESETS[num] || null;
}

function applyPresetUI(umbral) {
  const num = Number(umbral);
  const name = getPresetName(num);
  if (recogSegment) {
    recogSegment.querySelectorAll('.settings-segment__btn').forEach((btn) => {
      const val = btn.dataset.preset;
      const isActive = val === String(num) || (val === 'custom' && !name);
      btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
      if (val === 'custom') {
        btn.hidden = Boolean(name);
        if (!name && recogCustomValue) recogCustomValue.textContent = num;
      }
    });
  }
  if (recogPresetSummary) {
    recogPresetSummary.textContent = name || `Personalizado (${num})`;
  }
  if (cfgThreshold) cfgThreshold.value = num;
}

function formatUptime(seconds) {
  const s = Number(seconds);
  if (Number.isNaN(s) || s < 0) return '—';
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}min`;
  return `${m}min`;
}

async function loadConfig() {
  const cfg = await api('/api/config');
  applyPresetUI(cfg.umbral_confianza);
  if (maxAttemptsValue) maxAttemptsValue.textContent = cfg.max_intentos;
  if (openSecValue) openSecValue.textContent = cfg.tiempo_apertura_seg;
  if (doorTimeSummary) doorTimeSummary.textContent = `${cfg.tiempo_apertura_seg} segundo${cfg.tiempo_apertura_seg !== 1 ? 's' : ''}`;
}

async function saveConfig(patch = {}) {
  // build full payload from current UI values
  const umbral = Number(cfgThreshold?.value || 70);
  const intentos = Number(maxAttemptsValue?.textContent || 3);
  const segundos = Number(openSecValue?.textContent || 5);
  try {
    await api('/api/config', {
      method: 'PUT',
      body: JSON.stringify({
        umbral_confianza: patch.umbral_confianza ?? umbral,
        tiempo_apertura_seg: patch.tiempo_apertura_seg ?? segundos,
        max_intentos: patch.max_intentos ?? intentos,
      }),
    });
    showAdminToast({ text: 'Ajuste guardado', sub: 'Configuración aplicada', cls: 'success' });
  } catch (error) {
    console.error(error);
    showAdminToast({ text: 'No se pudo guardar', sub: getErrorMessage(error), cls: 'error', timeout: 3200 });
  }
}

let configSaveTimer = null;
function debouncedSaveConfig(patch = {}) {
  if (configSaveTimer) clearTimeout(configSaveTimer);
  configSaveTimer = setTimeout(() => saveConfig(patch), 400);
}

async function loadDiagnostics() {
  try {
    const data = await api('/api/system/diagnostics');
    if (diagnosticsSummary) diagnosticsSummary.textContent = data.summary;
    if (diagnosticsRootIcon) {
      diagnosticsRootIcon.classList.toggle('is-warning', !data.all_ok);
    }
    if (diagnosticsDetailList) {
      diagnosticsDetailList.innerHTML = Object.entries(data.checks).map(([key, check], idx, arr) => {
        const labels = { camera: 'Cámara', model: 'Reconocimiento facial', door: 'Control de puerta', storage: 'Almacenamiento' };
        const label = labels[key] || key;
        const pillCls = check.ok ? 'settings-diag-pill--ok' : 'settings-diag-pill--warn';
        const icon = check.ok
          ? '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>'
          : '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"/><line x1="12" x2="12" y1="9" y2="13"/><line x1="12" x2="12.01" y1="17" y2="17"/>';
        const divider = idx < arr.length - 1 ? '<div class="settings-row-divider" style="margin-left:58px"></div>' : '';
        return `<div class="settings-diag-row">
          <div class="settings-diag-pill ${pillCls}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icon}</svg></div>
          <div class="settings-diag-body"><p class="settings-diag-title">${escapeHtml(label)}</p><p class="settings-diag-msg">${escapeHtml(check.message)}</p></div>
        </div>${divider}`;
      }).join('');
    }
  } catch (error) {
    console.error('loadDiagnostics failed:', error);
    const raw = String(error?.message || '');
    const isNotFound = raw.includes('Not Found') || raw.includes('404');
    const friendly = isNotFound
      ? 'Reinicia el servidor para activar diagnóstico'
      : 'No se pudo obtener el diagnóstico';
    if (diagnosticsSummary) diagnosticsSummary.textContent = friendly;
    if (diagnosticsRootIcon) diagnosticsRootIcon.classList.add('is-warning');
    if (diagnosticsDetailList) {
      const detail = isNotFound
        ? 'El servidor está corriendo una versión sin los nuevos endpoints. Reinicia el proceso (Ctrl+C y vuelve a ejecutar) para que carguen.'
        : `Detalle técnico: ${escapeHtml(getErrorMessage(error))}`;
      diagnosticsDetailList.innerHTML = `<div class="settings-diag-row">
        <div class="settings-diag-pill settings-diag-pill--warn"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"/><line x1="12" x2="12" y1="9" y2="13"/><line x1="12" x2="12.01" y1="17" y2="17"/></svg></div>
        <div class="settings-diag-body"><p class="settings-diag-title">${escapeHtml(friendly)}</p><p class="settings-diag-msg">${detail}</p></div>
      </div>`;
    }
  }
}

async function loadDeviceInfo() {
  try {
    const data = await api('/api/system/device-info');
    if (deviceInfoName) deviceInfoName.textContent = data.device_name || '—';
    if (deviceInfoVersion) deviceInfoVersion.textContent = data.software_version || '—';
    if (deviceInfoHostname) deviceInfoHostname.textContent = data.hostname || '—';
    if (deviceInfoIp) deviceInfoIp.textContent = data.local_ip || '—';
    if (deviceInfoDisk) deviceInfoDisk.textContent = data.disk_free_gb != null ? `${data.disk_free_gb} GB libres de ${data.disk_total_gb} GB` : '—';
    if (deviceInfoUptime) deviceInfoUptime.textContent = formatUptime(data.uptime_seconds);
  } catch (error) {
    console.error(error);
  }
}

/* ── Actions: Users ── */

window.toggleUser = async function (userId, active) {
  const action = active ? 'activar' : 'desactivar';
  const confirmed = await openAdminConfirm({
    eyebrow: 'Estado de persona',
    title: `${active ? 'Activar' : 'Desactivar'} usuario`,
    text: `Se actualizara el estado operativo de la persona con ID ${userId}.`,
    confirmLabel: active ? 'Activar' : 'Desactivar',
    tone: 'primary',
  });
  if (!confirmed) return;
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
  const confirmed = await openAdminConfirm({
    eyebrow: 'Accion irreversible',
    title: 'Eliminar usuario',
    text: `${nombre} (ID ${userId}) sera eliminado junto con sus muestras y su relacion con los accesos. Esta accion no se puede deshacer.`,
    confirmLabel: 'Eliminar',
    tone: 'danger',
  });
  if (!confirmed) return;
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
      createResult.innerHTML = `<svg class="icon" aria-hidden="true"><use href="/static/icons/lucide/lucide-sprite.svg#check-filled"></use></svg> ${escapeHtml(nombre)} registrado${uid ? ` (ID ${uid})` : ''}. <button class="link" onclick="startEnrollForUser(${uid}, '${escapeHtml(nombre).replace(/'/g, "\\'")}')">Registrar ahora &rarr;</button>`;
      setTimeout(() => { createResult.hidden = true; }, 10000);
    }

    showAdminToast({ text: 'Persona registrada', sub: `${nombre} fue agregado`, cls: 'success' });
  } catch (error) {
    console.error(error);
    showAdminToast({ text: 'No se pudo crear', sub: getErrorMessage(error), cls: 'error', timeout: 3200 });
  }
});

/* ── Actions: Train model (Sistema) ── */

trainBtn?.addEventListener('click', async () => {
  const confirmed = await openAdminConfirm({
    eyebrow: 'Reentrenamiento',
    title: 'Actualizar modelo facial',
    text: 'Se generara un nuevo modelo con las muestras actuales y reemplazara al modelo en uso.',
    confirmLabel: 'Reentrenar',
    tone: 'primary',
  });
  if (!confirmed) return;
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
    trainBtn.innerHTML = '<svg class="icon" aria-hidden="true"><use href="/static/icons/lucide/lucide-sprite.svg#refresh-filled"></use></svg> <span>Reentrenar modelo</span>';
  }
});

/* ── Settings: Preset segment ── */

recogSegment?.addEventListener('click', (e) => {
  const btn = e.target.closest('.settings-segment__btn');
  if (!btn || btn.dataset.preset === 'custom') return;
  const preset = Number(btn.dataset.preset);
  if (!PRESETS[preset]) return;
  applyPresetUI(preset);
  debouncedSaveConfig({ umbral_confianza: preset });
});

/* ── Settings: Steppers ── */

function initStepper(stepper, valueEl, onChange) {
  if (!stepper || !valueEl) return;
  const min = Number(stepper.dataset.min ?? 1);
  const max = Number(stepper.dataset.max ?? 20);

  function update(val) {
    const clamped = Math.min(max, Math.max(min, val));
    valueEl.textContent = clamped;
    stepper.querySelector('[data-action="dec"]').disabled = clamped <= min;
    stepper.querySelector('[data-action="inc"]').disabled = clamped >= max;
    return clamped;
  }

  stepper.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const current = Number(valueEl.textContent);
    const next = btn.dataset.action === 'inc' ? current + 1 : current - 1;
    const clamped = update(next);
    onChange(clamped);
  });

  update(Number(valueEl.textContent));
}

initStepper(maxAttemptsStepper, maxAttemptsValue, (val) => {
  debouncedSaveConfig({ max_intentos: val });
});

initStepper(openSecStepper, openSecValue, (val) => {
  if (doorTimeSummary) doorTimeSummary.textContent = `${val} segundo${val !== 1 ? 's' : ''}`;
  debouncedSaveConfig({ tiempo_apertura_seg: val });
});

/* ── Settings: Advanced threshold ── */

applyThresholdBtn?.addEventListener('click', () => {
  const val = Number(cfgThreshold?.value);
  if (!val || val < 1 || val > 200) return;
  applyPresetUI(val);
  debouncedSaveConfig({ umbral_confianza: val });
});

manualOpenAdminBtn?.addEventListener('click', async () => {
  const confirmed = await openAdminConfirm({
    eyebrow: 'Mantenimiento',
    title: 'Abrir puerta ahora',
    text: 'Se enviará un pulso al actuador para abrir la puerta manualmente.',
    confirmLabel: 'Abrir',
    tone: 'primary',
  });
  if (!confirmed) return;
  try {
    await api('/api/manual-open', { method: 'POST' });
    await loadStatus();
    showAdminToast({ text: 'Puerta abierta', sub: 'Comando enviado al actuador', cls: 'processing' });
  } catch (error) {
    console.error(error);
    showAdminToast({ text: 'No se pudo abrir', sub: getErrorMessage(error), cls: 'error', timeout: 3200 });
  }
});

/* ── Settings: Password sheet ── */

function openPasswordSheet() {
  if (!passwordSheet) return;
  if (currentPasswordInput) currentPasswordInput.value = '';
  if (newPasswordInput) newPasswordInput.value = '';
  if (passwordSheetError) { passwordSheetError.textContent = ''; passwordSheetError.hidden = true; }
  passwordSheet.classList.remove('is-hidden');
  passwordSheet.setAttribute('aria-hidden', 'false');
  setTimeout(() => currentPasswordInput?.focus(), 80);
}

function closePasswordSheet() {
  if (!passwordSheet) return;
  passwordSheet.classList.add('is-hidden');
  passwordSheet.setAttribute('aria-hidden', 'true');
}

changePasswordBtn?.addEventListener('click', openPasswordSheet);
passwordSheetCancel?.addEventListener('click', closePasswordSheet);
passwordSheetBackdrop?.addEventListener('click', closePasswordSheet);

passwordSheetConfirm?.addEventListener('click', async () => {
  const current = currentPasswordInput?.value || '';
  const next = newPasswordInput?.value || '';
  if (!current || !next) {
    if (passwordSheetError) { passwordSheetError.textContent = 'Completa ambos campos.'; passwordSheetError.hidden = false; }
    return;
  }
  if (next.length < 8) {
    if (passwordSheetError) { passwordSheetError.textContent = 'La nueva contraseña debe tener al menos 8 caracteres.'; passwordSheetError.hidden = false; }
    return;
  }
  if (passwordSheetError) passwordSheetError.hidden = true;
  passwordSheetConfirm.disabled = true;
  passwordSheetConfirm.textContent = 'Guardando…';
  try {
    await api('/api/admin/change-password', {
      method: 'POST',
      body: JSON.stringify({ current_password: current, new_password: next }),
    });
    closePasswordSheet();
    showAdminToast({ text: 'Contraseña actualizada', sub: 'Los cambios se aplicaron correctamente', cls: 'success' });
  } catch (error) {
    const msg = getErrorMessage(error, 'No se pudo cambiar la contraseña.');
    if (passwordSheetError) { passwordSheetError.textContent = msg; passwordSheetError.hidden = false; }
  } finally {
    passwordSheetConfirm.disabled = false;
    passwordSheetConfirm.textContent = 'Cambiar';
  }
});

/* ── Settings: back buttons ── */

document.querySelectorAll('[data-back]').forEach((btn) => {
  btn.addEventListener('click', () => {
    const target = btn.dataset.back;
    if (window.CameraPIAdminLayout?.navigateToView) {
      window.CameraPIAdminLayout.navigateToView(target);
    } else {
      window.location.hash = target;
    }
  });
});

/* ── Personas / Enrolamiento navigation ── */

function navigateToAdminView(viewId) {
  if (window.CameraPIAdminLayout?.navigateToView) {
    window.CameraPIAdminLayout.navigateToView(viewId);
    return;
  }
  window.location.hash = viewId;
}

window.showPersonasListMode = function showPersonasListMode() {
  if (window.CameraPIEnrollment) window.CameraPIEnrollment.reset();
  navigateToAdminView('personas');
};

window.startEnrollForUser = function (userId, userName) {
  navigateToAdminView('enrolamiento');
  window.requestAnimationFrame(() => {
    if (window.CameraPIEnrollment?.prefillUser) {
      window.CameraPIEnrollment.prefillUser(userId);
    } else {
      const enrollSelect = document.getElementById('enrollUserSelect');
      if (enrollSelect) enrollSelect.value = String(userId);
    }
    window.dispatchEvent(new Event('resize'));
  });
};

window.showAdminToast = showAdminToast;

/* ── Settings: view-change lazy load ── */

window.addEventListener('admin:viewchange', (e) => {
  const { viewId } = e.detail || {};
  if (viewId === 'sistema' || viewId === 'sistema-diagnostico') {
    loadDiagnostics().catch(console.error);
  }
  if (viewId === 'sistema-acerca') {
    loadDeviceInfo().catch(console.error);
  }
});

/* ── Init ── */

async function init() {
  window.CameraPITheme?.initTheme();
  window.CameraPITheme?.bindToggleButtons();

  // Populate account display from config username
  const adminUser = document.querySelector('meta[name="admin-user"]')?.content || 'admin';
  if (accountDisplayName) accountDisplayName.textContent = adminUser;
  if (accountUsernameSummary) accountUsernameSummary.textContent = adminUser;

  await Promise.all([
    loadUsers(),
    loadLogs(),
    loadStatus(),
    loadConfig(),
  ]);

  // Pre-load diagnostics in background
  loadDiagnostics().catch(console.error);

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
