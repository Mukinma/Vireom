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

const faceGuide = document.getElementById('faceGuide');
const cameraBadge = document.getElementById('cameraBadge');
const cameraBadgeText = document.getElementById('cameraBadgeText');
const infoTitle = document.getElementById('infoTitle');
const infoDesc = document.getElementById('infoDesc');
const cameraTitle = document.getElementById('cameraTitle');

const AUTO_TRIGGER_COOLDOWN_MS = 4000;
let lastAutoTriggerMs = 0;
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
  if (faceIndicator) {
    faceIndicator.classList.remove('idle', 'tracking', 'granted', 'denied', 'blocked');
    if (stateKey === 'granted') faceIndicator.classList.add('granted');
    else if (stateKey === 'denied' || stateKey === 'unrecognized') faceIndicator.classList.add('denied');
    else if (stateKey === 'blocked') faceIndicator.classList.add('blocked');
    else if (stateKey === 'processing') faceIndicator.classList.add('tracking');
    else faceIndicator.classList.add('idle');
  }

  if (faceGuide) {
    faceGuide.classList.remove('is-idle', 'is-tracking', 'is-granted', 'is-denied');
    if (stateKey === 'granted') faceGuide.classList.add('is-granted');
    else if (stateKey === 'denied' || stateKey === 'unrecognized' || stateKey === 'blocked') faceGuide.classList.add('is-denied');
    else if (stateKey === 'processing') faceGuide.classList.add('is-tracking');
    else faceGuide.classList.add('is-idle');
  }

  if (cameraBadge && cameraBadgeText) {
    cameraBadge.classList.remove('is-idle', 'is-tracking', 'is-granted', 'is-denied', 'is-blocked');
    const badgeCfg = {
      granted:      { text: 'Acceso concedido',    cls: 'is-granted'  },
      denied:       { text: 'Acceso denegado',     cls: 'is-denied'   },
      blocked:      { text: 'Acceso restringido',  cls: 'is-blocked'  },
      unrecognized: { text: 'No reconocido',       cls: 'is-denied'   },
      processing:   { text: 'Rostro detectado',    cls: 'is-tracking' },
      noface:       { text: 'Esperando detección', cls: 'is-idle'     },
      cameraError:  { text: 'Error de cámara',     cls: 'is-denied'   },
      initializing: { text: 'Cargando modelo',     cls: 'is-idle'     },
      nomodel:      { text: 'Sin modelo',          cls: 'is-idle'     },
    };
    const cfg = badgeCfg[stateKey] || badgeCfg.initializing;
    cameraBadgeText.textContent = cfg.text;
    cameraBadge.classList.add(cfg.cls);
  }

  if (infoTitle) {
    const titleMap = {
      granted:      'Acceso<br>concedido',
      denied:       'Acceso<br>denegado',
      blocked:      'Acceso<br>restringido',
      unrecognized: 'No<br>reconocido',
      processing:   'Validando<br>identidad',
      noface:       'Esperando<br>detección',
      cameraError:  'Error de<br>cámara',
      initializing: 'Cargando<br>modelo',
      nomodel:      'Sin<br>modelo',
    };
    infoTitle.innerHTML = titleMap[stateKey] || titleMap.processing;
  }

  if (infoDesc) {
    const descMap = {
      granted:      'Identidad verificada<br><strong>acceso autorizado</strong>',
      denied:       'Identidad no autorizada<br><strong>acceso denegado</strong>',
      blocked:      'Demasiados intentos<br><strong>acceso restringido</strong>',
      unrecognized: 'Rostro no registrado<br><strong>en el sistema</strong>',
      processing:   'Espera un momento mientras<br><strong>verificamos tu acceso</strong>',
      noface:       'Coloca tu rostro frente<br><strong>a la cámara</strong>',
      cameraError:  'Verifique la conexión<br><strong>del dispositivo</strong>',
      initializing: 'Cargando modelo<br><strong>de reconocimiento</strong>',
      nomodel:      'Entrena un modelo desde<br><strong>el panel de administración</strong>',
    };
    infoDesc.innerHTML = descMap[stateKey] || descMap.processing;
  }

  if (cameraTitle) {
    const ctMap = {
      granted:      'Acceso concedido',
      denied:       'Acceso denegado',
      blocked:      'Acceso restringido',
      unrecognized: 'No reconocido',
      processing:   'Validando identidad',
      noface:       'Esperando detección',
      cameraError:  'Error de cámara',
      initializing: 'Cargando modelo',
      nomodel:      'Sin modelo',
    };
    cameraTitle.textContent = ctMap[stateKey] || ctMap.processing;
  }

  const authProgressBar = document.getElementById('authProgressBar');
  if (authProgressBar) {
    if (stateKey === 'granted') {
      authProgressBar.style.width = '100%';
      authProgressBar.style.backgroundColor = 'var(--success)';
    } else if (['denied', 'unrecognized', 'blocked'].includes(stateKey)) {
      authProgressBar.style.width = '100%';
      authProgressBar.style.backgroundColor = 'var(--danger)';
    } else if (stateKey === 'processing') {
      authProgressBar.style.width = '85%';
      authProgressBar.style.backgroundColor = 'rgba(255, 255, 255, 0.95)';
    } else {
      authProgressBar.style.width = '0%';
      authProgressBar.style.backgroundColor = 'rgba(255, 255, 255, 0.95)';
    }
  }
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
  const modelLoaded = data.model === 'loaded';

  if (data.camera === 'error' || data.camera === 'offline' || data.camera === 'degraded') {
    return { key: 'cameraError', badge: ['Error de cámara', 'state-error'] };
  }

  if (analysisBusy) {
    return { key: 'processing', badge: ['Analizando', 'state-processing'] };
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

  if (!modelLoaded) {
    return { key: 'nomodel', badge: ['Sin modelo', 'state-warning'] };
  }

  if (!faceDetected) {
    return { key: 'noface', badge: ['Esperando detección', 'state-neutral'] };
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

    if (data.face_detected && !data.analysis_busy && faceAction && !faceAction.localBusy && faceAction.isReady(data)) {
      const now = Date.now();
      if (now - lastAutoTriggerMs >= AUTO_TRIGGER_COOLDOWN_MS) {
        lastAutoTriggerMs = now;
        faceAction.handleAnalyzeClick();
      }
    }
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

(function initAdminShortcut() {
  const header = document.querySelector('.kiosk-header');
  if (!header) return;

  let tapCount = 0;
  let tapTimer = null;

  header.addEventListener('click', () => {
    tapCount++;
    if (tapTimer) clearTimeout(tapTimer);

    if (tapCount >= 3) {
      tapCount = 0;
      window.location.href = '/admin';
      return;
    }

    tapTimer = setTimeout(() => { tapCount = 0; }, 1200);
  });
})();
