const shell = document.getElementById('kioskShell');
const sidebarToggle = document.getElementById('sidebarToggle');
const accessToast = document.getElementById('accessToast');
const accessToastText = document.getElementById('accessToastText');
const accessToastSub = document.getElementById('accessToastSub');
const faceIndicator = document.getElementById('faceIndicator');
const userOverlay = document.getElementById('userOverlay');
const userPhoto = document.getElementById('userPhoto');
const recognizedName = document.getElementById('recognizedName');
const recognizedId = document.getElementById('recognizedId');
const recognizedArea = document.getElementById('recognizedArea');
const confidence = document.getElementById('confidence');
const camState = document.getElementById('camState');
const modelState = document.getElementById('modelState');
const gpioState = document.getElementById('gpioState');
const fpsState = document.getElementById('fpsState');
const systemStateBadge = document.getElementById('systemStateBadge');
const clockTime = document.getElementById('clockTime');
const clockDate = document.getElementById('clockDate');
const fullscreenBtn = document.getElementById('fullscreenBtn');
const manualOpen = document.getElementById('manualOpen');
const videoFeed = document.getElementById('videoFeed');
const cameraShell = document.getElementById('cameraShell');
const cameraStage = document.getElementById('cameraStage');
const cameraRingHost = cameraShell || cameraStage;

let toastTimer = null;

const toastMap = {
  granted: { text: 'Acceso concedido', sub: 'Validación biométrica exitosa', cls: 'success', timeout: 2600 },
  denied: { text: 'Acceso denegado', sub: 'Identidad no válida para ingreso', cls: 'error', timeout: 2300 },
  blocked: { text: 'Acceso restringido', sub: 'Límite de intentos excedido', cls: 'warning', timeout: 3200 },
  processing: { text: 'Procesando', sub: 'Analizando biometría facial', cls: 'processing', timeout: 1400 },
  initializing: { text: 'Sistema inicializando', sub: 'Cargando cámara y modelo', cls: 'processing', timeout: 2000 },
  noface: { text: 'Sin rostro detectado', sub: 'Esperando frente a cámara', cls: 'warning', timeout: 1600 },
  unrecognized: { text: 'Rostro no reconocido', sub: 'No coincide con usuarios activos', cls: 'warning', timeout: 2200 },
  cameraError: { text: 'Error de cámara', sub: 'Verifique conexión del dispositivo', cls: 'error', timeout: 2800 },
  busy: { text: 'Análisis en curso', sub: 'Espere a que finalice el proceso actual', cls: 'warning', timeout: 1600 },
  manualOpen: { text: 'Apertura manual', sub: 'Comando enviado al actuador', cls: 'processing', timeout: 2400 },
  adminRequired: { text: 'Acceso administrativo requerido', sub: 'Inicie sesión para apertura manual', cls: 'warning', timeout: 3200 },
};

const analysisEventToToast = {
  authorized: 'granted',
  denied: 'denied',
  blocked: 'blocked',
  no_face: 'noface',
  camera_error: 'cameraError',
  model_not_loaded: 'initializing',
  busy: 'busy',
};

let faceAction = null;
const prefersReducedMotionQuery = window.matchMedia?.('(prefers-reduced-motion: reduce)') ?? null;

function setCameraStageActive(isActive) {
  if (!cameraRingHost) {
    return;
  }

  const active = Boolean(isActive);
  const allowPulse = active && !prefersReducedMotionQuery?.matches;

  cameraRingHost.classList.toggle('camera-active', active);
  cameraRingHost.classList.toggle('camera-pulse', allowPulse);
}

function showToast(type) {
  const config = toastMap[type] || toastMap.processing;

  accessToastText.textContent = config.text;
  accessToastSub.textContent = config.sub;
  accessToast.classList.remove('is-hidden', 'success', 'error', 'warning', 'processing');
  accessToast.classList.add(config.cls, 'is-visible');

  if (toastTimer) {
    clearTimeout(toastTimer);
  }

  toastTimer = setTimeout(() => {
    accessToast.classList.remove('is-visible');
    setTimeout(() => accessToast.classList.add('is-hidden'), 180);
  }, config.timeout);
}

function updateFaceIndicator(stateKey) {
  if (!faceIndicator) {
    return;
  }

  faceIndicator.classList.remove('idle', 'tracking', 'granted', 'denied', 'blocked');

  if (stateKey === 'granted') {
    faceIndicator.classList.add('granted');
    return;
  }

  if (stateKey === 'denied' || stateKey === 'unrecognized') {
    faceIndicator.classList.add('denied');
    return;
  }

  if (stateKey === 'blocked') {
    faceIndicator.classList.add('blocked');
    return;
  }

  if (stateKey === 'processing') {
    faceIndicator.classList.add('tracking');
    return;
  }

  faceIndicator.classList.add('idle');
}

function showUserOverlay(data) {
  const userName = data.last_user || '-';
  const hasKnownUser = userName !== '-' && userName.toLowerCase() !== 'desconocido';

  if (!hasKnownUser) {
    userOverlay.classList.remove('is-visible');
    userOverlay.classList.add('is-hidden');
    return;
  }

  const nameForCard = String(userName).trim().toUpperCase();
  const parts = nameForCard.split(/\s+/);
  if (parts.length >= 2) {
    recognizedName.textContent = `${parts[0]}\n${parts.slice(1).join(' ')}`;
  } else {
    recognizedName.textContent = nameForCard;
  }
  recognizedId.textContent = data.last_user_id || userName.replace(/\D+/g, '') || '-';
  recognizedArea.textContent = data.last_area || 'Acceso principal';
  confidence.textContent = data.last_confidence == null ? '-' : Number(data.last_confidence).toFixed(2);

  if (typeof data.last_user_photo === 'string' && data.last_user_photo.trim().length > 0) {
    userPhoto.src = data.last_user_photo;
  } else {
    userPhoto.src = '/static/images/user-placeholder.svg';
  }

  userOverlay.classList.remove('is-hidden');
  requestAnimationFrame(() => userOverlay.classList.add('is-visible'));
}

function updateClock() {
  if (!clockTime || !clockDate) {
    return;
  }

  const now = new Date();
  const formattedTime = now.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  });
  clockTime.textContent = formattedTime.replace(/\./g, '').toUpperCase();

  const dateParts = new Intl.DateTimeFormat('es-ES', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  }).formatToParts(now);
  const day = dateParts.find((part) => part.type === 'day')?.value ?? '--';
  const month = dateParts.find((part) => part.type === 'month')?.value ?? '---';
  const year = dateParts.find((part) => part.type === 'year')?.value ?? '----';
  clockDate.textContent = `${day} ${month} ${year}`;
}

function setSystemBadge(text, variant) {
  systemStateBadge.textContent = text;
  systemStateBadge.classList.remove('state-success', 'state-error', 'state-processing', 'state-warning', 'state-neutral');
  systemStateBadge.classList.add(variant);
}

function classifyState(data) {
  const result = String(data.last_result || 'INICIALIZANDO');
  const statusAge = Math.max(0, Math.floor(Date.now() / 1000) - Number(data.timestamp || 0));
  const faceDetected = Boolean(data.face_detected);
  const analysisBusy = Boolean(data.analysis_busy);

  if (data.camera === 'error' || data.camera === 'offline' || data.camera === 'degraded') {
    return { key: 'cameraError', badge: ['Error de cámara', 'state-error'] };
  }

  if (data.model !== 'loaded') {
    return { key: 'initializing', badge: ['Inicializando', 'state-processing'] };
  }

  if (analysisBusy) {
    return { key: 'processing', badge: ['Analizando', 'state-processing'] };
  }

  if (!faceDetected) {
    return { key: 'noface', badge: ['Sin rostro detectado', 'state-warning'] };
  }

  if (statusAge <= 3 && result.startsWith('AUTORIZADO')) {
    return { key: 'granted', badge: ['Acceso concedido', 'state-success'] };
  }

  if (statusAge <= 3 && result === 'DENEGADO_BLOQUEO') {
    return { key: 'blocked', badge: ['Acceso restringido', 'state-warning'] };
  }

  if (statusAge <= 3 && result.startsWith('DENEGADO')) {
    const userName = String(data.last_user || '').toLowerCase();
    if (userName && userName !== 'desconocido') {
      return { key: 'denied', badge: ['Acceso denegado', 'state-error'] };
    }

    return { key: 'unrecognized', badge: ['Rostro no reconocido', 'state-warning'] };
  }

  return { key: 'processing', badge: ['Rostro detectado', 'state-processing'] };
}

async function loadStatus() {
  try {
    const response = await fetch('/api/status');
    if (!response.ok) {
      throw new Error(`status_http_${response.status}`);
    }

    const data = await response.json();

    camState.textContent = data.camera || '-';
    modelState.textContent = data.model || '-';
    gpioState.textContent = data.gpio || '-';
    fpsState.textContent = data.fps ?? 0;
    setCameraStageActive(data.camera === 'online');

    const uiState = classifyState(data);
    setSystemBadge(uiState.badge[0], uiState.badge[1]);

    updateFaceIndicator(uiState.key);
    showUserOverlay(data);
    faceAction?.updateStatus(data);
  } catch (error) {
    console.error(error);
    setSystemBadge('Error de conexión', 'state-error');
    setCameraStageActive(false);
    showToast('cameraError');
    updateFaceIndicator('cameraError');
    userOverlay.classList.remove('is-visible');
    userOverlay.classList.add('is-hidden');
  }
}

function handleAnalysisResult(payload, statusCode) {
  const event = payload?.event || (statusCode === 409 ? 'busy' : 'camera_error');
  const toastKey = analysisEventToToast[event] || 'cameraError';
  showToast(toastKey);
}

function initializeResponsiveSidebar() {
  if (window.innerWidth <= 1366) {
    shell.classList.add('sidebar-collapsed');
  }
}

fullscreenBtn?.addEventListener('click', async () => {
  if (!document.fullscreenElement) {
    await document.documentElement.requestFullscreen();
  } else {
    await document.exitFullscreen();
  }
});

manualOpen?.addEventListener('click', async () => {
  try {
    const response = await fetch('/api/manual-open', { method: 'POST' });
    if (response.status === 401) {
      showToast('adminRequired');
      return;
    }
    if (!response.ok) {
      throw new Error(`manual_open_http_${response.status}`);
    }
    showToast('manualOpen');
  } catch (error) {
    console.error(error);
    showToast('cameraError');
  }
});

sidebarToggle?.addEventListener('click', () => {
  shell.classList.toggle('sidebar-collapsed');
});

videoFeed?.addEventListener('error', () => {
  setSystemBadge('Error de cámara', 'state-error');
  setCameraStageActive(false);
  showToast('cameraError');
  updateFaceIndicator('cameraError');
});

faceAction = window.CameraPIFaceAction?.create({
  stageElement: cameraStage,
  videoElement: videoFeed,
  onResult: async (payload, statusCode) => {
    handleAnalysisResult(payload, statusCode);
    await loadStatus();
  },
});

window.CameraPITheme?.initTheme();
window.CameraPITheme?.bindToggleButtons();
initializeResponsiveSidebar();
updateClock();
setInterval(updateClock, 1000);
setInterval(loadStatus, 600);
loadStatus();
