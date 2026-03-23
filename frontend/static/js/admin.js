const usersList = document.getElementById('usersList');
const logsList = document.getElementById('logsList');
const createUserBtn = document.getElementById('createUserBtn');
const newUserName = document.getElementById('newUserName');
const captureUserId = document.getElementById('captureUserId');
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

let adminToastTimer = null;
let allLogs = [];

function showAdminToast({
  text = 'Notificación',
  sub = '',
  cls = 'processing',
  timeout = 2600,
} = {}) {
  if (!adminToast || !adminToastText || !adminToastSub) {
    return;
  }

  adminToastText.textContent = text;
  adminToastSub.textContent = sub;
  adminToast.classList.remove('is-hidden', 'success', 'error', 'warning', 'processing');
  adminToast.classList.add(cls, 'is-visible');

  if (adminToastTimer) {
    clearTimeout(adminToastTimer);
  }

  adminToastTimer = setTimeout(() => {
    adminToast.classList.remove('is-visible');
    setTimeout(() => adminToast.classList.add('is-hidden'), 180);
  }, timeout);
}

function getErrorMessage(error, fallback = 'No se pudo completar la operación') {
  const raw = String(error?.message || '').trim();
  if (!raw || raw.startsWith('<')) {
    return fallback;
  }
  return raw.length > 120 ? `${raw.slice(0, 117)}...` : raw;
}

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

function renderUsers(users) {
  const rows = users.map((u) => `
    <tr>
      <td>${u.id}</td>
      <td>${u.nombre}</td>
      <td>${u.activo ? 'Sí' : 'No'}</td>
      <td class="user-actions-cell">
        <button class="btn btn-secondary" onclick="toggleUser(${u.id}, ${u.activo ? 'false' : 'true'})">
          ${u.activo ? 'Desactivar' : 'Activar'}
        </button>
        <button class="btn-delete-user" onclick="deleteUser(${u.id}, '${u.nombre.replace(/'/g, "\\'")}')" title="Eliminar usuario" aria-label="Eliminar ${u.nombre}">
          <svg class="icon" aria-hidden="true"><use href="/static/icons/lucide/lucide-sprite.svg#x"></use></svg>
        </button>
      </td>
    </tr>
  `).join('');

  usersList.innerHTML = `
    <table>
      <thead><tr><th>ID</th><th>Nombre</th><th>Activo</th><th>Acción</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function renderLogs(logs) {
  const rows = logs.map((l) => `
    <tr>
      <td>${l.id}</td>
      <td>${l.fecha}</td>
      <td>${l.nombre || '-'}</td>
      <td>${l.confianza == null ? '-' : Number(l.confianza).toFixed(2)}</td>
      <td>${l.resultado}</td>
    </tr>
  `).join('');

  logsList.innerHTML = `
    <table>
      <thead><tr><th>ID</th><th>Fecha</th><th>Usuario</th><th>Confianza</th><th>Resultado</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

async function loadUsers() {
  const users = await api('/api/users');
  renderUsers(users);
}

async function loadLogs() {
  allLogs = await api('/api/access-logs?limit=500');
  applyLogFilters();
}

function applyLogFilters() {
  const filterDate = document.getElementById('filterDate')?.value || '';
  const filterUserId = document.getElementById('filterUserId')?.value || '';

  let filtered = allLogs;

  if (filterDate) {
    filtered = filtered.filter((l) => l.fecha && l.fecha.startsWith(filterDate));
  }

  if (filterUserId) {
    const uid = Number(filterUserId);
    filtered = filtered.filter((l) => l.usuario_id === uid);
  }

  renderLogs(filtered);
}

async function loadConfig() {
  const cfg = await api('/api/config');
  cfgThreshold.value = cfg.umbral_confianza;
  cfgOpenSec.value = cfg.tiempo_apertura_seg;
  cfgMaxAttempts.value = cfg.max_intentos;
}

window.toggleUser = async function(userId, active) {
  const action = active ? 'activar' : 'desactivar';
  if (!confirm(`¿Estás seguro de que deseas ${action} al usuario ID ${userId}?`)) return;
  try {
    await api(`/api/users/${userId}`, {
      method: 'PATCH',
      body: JSON.stringify({ activo: active }),
    });
    await loadUsers();
    showAdminToast({
      text: active ? 'Usuario activado' : 'Usuario desactivado',
      sub: `ID ${userId} actualizado`,
      cls: 'success',
    });
  } catch (error) {
    console.error(error);
    showAdminToast({
      text: 'No se pudo actualizar',
      sub: getErrorMessage(error),
      cls: 'error',
      timeout: 3200,
    });
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
    await api('/api/users', {
      method: 'POST',
      body: JSON.stringify({ nombre }),
    });
    newUserName.value = '';
    await loadUsers();
    showAdminToast({
      text: 'Usuario creado',
      sub: `Registro de ${nombre} completado`,
      cls: 'success',
    });
  } catch (error) {
    console.error(error);
    showAdminToast({
      text: 'No se pudo crear usuario',
      sub: getErrorMessage(error),
      cls: 'error',
      timeout: 3200,
    });
  }
});

captureBtn?.addEventListener('click', async () => {
  const userId = Number(captureUserId.value);
  if (!userId) return;
  captureBtn.disabled = true;
  captureBtn.innerHTML = '<svg class="icon spin" aria-hidden="true"><use href="/static/icons/lucide/lucide-sprite.svg#loader"></use></svg> Capturando...';
  showAdminToast({
    text: 'Capturando muestras...',
    sub: 'Mirá la cámara, esto puede tardar unos segundos',
    cls: 'processing',
    timeout: 15000,
  });
  try {
    const result = await api(`/api/users/${userId}/capture?count=30`, { method: 'POST' });
    showAdminToast({
      text: 'Captura finalizada',
      sub: `Muestras guardadas: ${result.saved}/${result.requested}`,
      cls: 'success',
      timeout: 3200,
    });
  } catch (error) {
    console.error(error);
    showAdminToast({
      text: 'Error en captura',
      sub: getErrorMessage(error),
      cls: 'error',
      timeout: 3200,
    });
  } finally {
    captureBtn.disabled = false;
    captureBtn.textContent = 'Capturar 30 muestras';
  }
});

trainBtn?.addEventListener('click', async () => {
  if (!confirm('¿Deseas reentrenar el modelo LBPH? Esto reemplazará el modelo actual.')) return;
  trainBtn.disabled = true;
  trainBtn.innerHTML = '<svg class="icon spin" aria-hidden="true"><use href="/static/icons/lucide/lucide-sprite.svg#loader"></use></svg> Entrenando...';
  showAdminToast({
    text: 'Entrenando modelo...',
    sub: 'Esto puede tardar unos segundos',
    cls: 'processing',
    timeout: 15000,
  });
  try {
    const result = await api('/api/train', { method: 'POST' });
    trainResult.textContent = `Entrenado con ${result.samples_used} muestras de ${result.unique_users} usuarios.`;
    showAdminToast({
      text: 'Entrenamiento completado',
      sub: `${result.samples_used} muestras de ${result.unique_users} usuarios`,
      cls: 'success',
      timeout: 3200,
    });
  } catch (error) {
    console.error(error);
    trainResult.textContent = getErrorMessage(error, 'No se pudo entrenar el modelo.');
    showAdminToast({
      text: 'Error de entrenamiento',
      sub: getErrorMessage(error),
      cls: 'error',
      timeout: 3400,
    });
  } finally {
    trainBtn.disabled = false;
    trainBtn.textContent = 'Entrenar modelo LBPH';
  }
});

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
    showAdminToast({
      text: 'Configuración guardada',
      sub: 'Parámetros aplicados correctamente',
      cls: 'success',
    });
  } catch (error) {
    console.error(error);
    showAdminToast({
      text: 'No se pudo guardar',
      sub: getErrorMessage(error),
      cls: 'error',
      timeout: 3200,
    });
  }
});

restartBtn?.addEventListener('click', async () => {
  if (!confirm('¿Estás seguro de que deseas reiniciar el sistema? Se interrumpirá el servicio momentáneamente.')) return;
  try {
    await api('/api/restart', { method: 'POST' });
    showAdminToast({
      text: 'Reinicio solicitado',
      sub: 'El sistema iniciará el proceso de reinicio',
      cls: 'warning',
      timeout: 3400,
    });
  } catch (error) {
    console.error(error);
    showAdminToast({
      text: 'Error al reiniciar',
      sub: getErrorMessage(error),
      cls: 'error',
      timeout: 3200,
    });
  }
});

manualOpenAdminBtn?.addEventListener('click', async () => {
  try {
    await api('/api/manual-open', { method: 'POST' });
    showAdminToast({
      text: 'Apertura manual ejecutada',
      sub: 'Comando enviado al actuador',
      cls: 'processing',
    });
  } catch (error) {
    console.error(error);
    showAdminToast({
      text: 'No se pudo abrir',
      sub: getErrorMessage(error),
      cls: 'error',
      timeout: 3200,
    });
  }
});

async function init() {
  window.CameraPITheme?.initTheme();
  window.CameraPITheme?.bindToggleButtons();

  const filterDate = document.getElementById('filterDate');
  const filterUserId = document.getElementById('filterUserId');
  const clearFiltersBtn = document.getElementById('clearFiltersBtn');

  filterDate?.addEventListener('change', applyLogFilters);
  filterUserId?.addEventListener('input', applyLogFilters);
  clearFiltersBtn?.addEventListener('click', () => {
    if (filterDate) filterDate.value = '';
    if (filterUserId) filterUserId.value = '';
    applyLogFilters();
  });

  await loadUsers();
  await loadLogs();
  await loadConfig();
  setInterval(() => {
    loadLogs().catch((error) => {
      console.error(error);
    });
  }, 2500);
}

init().catch((err) => {
  console.error(err);
  showAdminToast({
    text: 'Sesión inválida o error de carga',
    sub: 'Vuelve a iniciar sesión administrativa',
    cls: 'error',
    timeout: 3600,
  });
});
