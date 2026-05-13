import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { JSDOM } from 'jsdom';

const ADMIN_SOURCE = readFileSync(
  resolve(process.cwd(), 'frontend/static/js/admin.js'),
  'utf8',
);

const activeWindows = new Set();

<<<<<<< HEAD
function createResponse(data, ok = true, status = ok ? 200 : 400) {
  return {
    ok,
    status,
    async json() {
      return data;
    },
    async text() {
      return typeof data === 'string' ? data : JSON.stringify(data);
=======
function responseJson(payload, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async json() {
      return payload;
    },
    async text() {
      return JSON.stringify(payload);
>>>>>>> origin/Cris
    },
  };
}

<<<<<<< HEAD
function createAdminDom({ users = [] } = {}) {
=======
async function flushAsyncWork() {
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
}

async function createAdminDom({ users = [] } = {}) {
>>>>>>> origin/Cris
  const dom = new JSDOM(
    `<!doctype html>
    <html lang="es">
      <head>
<<<<<<< HEAD
        <meta name="csrf-token" content="csrf-token" />
        <meta name="admin-user" content="admin" />
      </head>
      <body>
        <main>
          <input id="newUserName" />
          <button id="createUserBtn" type="button">Crear</button>
          <p id="createResult" hidden></p>
          <p id="personasListSummary"></p>
          <input id="userSearch" />
          <div id="usersList"></div>
          <aside id="personDetailPanel" hidden></aside>
          <div id="logsList"></div>

          <span id="statToday"></span><span id="statGranted"></span><span id="statDenied"></span><span id="statManual"></span>
          <section id="resumenHero"><div class="resumen-layout"></div></section>
          <span id="resumenStatusChip"></span><span id="resumenStatusLabel"></span><span id="resumenStatusTitle"></span>
          <span id="resumenStatusMeta"></span><span id="resumenStatusCaption"></span>
          <div id="resumenInlineAlert" hidden><span id="resumenInlineAlertBadge"></span><span id="resumenInlineAlertText"></span></div>
          <span id="resumenMetricActiveUsers"></span><span id="resumenMetricToday"></span><span id="resumenMetricSuccess"></span><span id="resumenMetricManual"></span>
          <span id="resumenActionHint"></span>
          <div id="resumenActionStack">
            <button id="resumenActionAccesos" data-quick="accesos" type="button"></button>
            <button id="resumenActionPersonas" data-quick="personas" type="button"></button>
          </div>

          <select id="logFilterResult"></select>
          <button id="logAdvancedToggle" type="button"></button>
          <div id="logAdvancedPanel" hidden></div>
          <button id="logAdvancedReset" type="button"></button>
          <input id="logSearch" /><input id="logDateFrom" /><input id="logDateTo" />
          <input id="logConfidenceMin" /><input id="logConfidenceMax" />

          <input id="cfgThreshold" />
          <div id="recogSegment"></div>
          <span id="recogPresetSummary"></span><span id="recogCustomValue"></span>
          <span id="maxAttemptsValue"></span><span id="openSecValue"></span><span id="doorTimeSummary"></span>
          <span id="diagnosticsSummary"></span><span id="diagnosticsRootIcon"></span><div id="diagnosticsDetailList"></div>
          <span id="accountDisplayName"></span><span id="accountUsernameSummary"></span>
          <button id="manualOpenAdminBtn" type="button"></button>

          <div id="adminToast" class="is-hidden"><span id="adminToastText"></span><span id="adminToastSub"></span></div>
          <div id="adminDialog" class="is-hidden" aria-hidden="true">
            <button id="adminDialogBackdrop" type="button"></button>
            <section id="adminDialogPanel" tabindex="-1">
              <p id="adminDialogEyebrow"></p><h2 id="adminDialogTitle"></h2><p id="adminDialogText"></p>
              <button id="adminDialogCancel" type="button"></button><button id="adminDialogConfirm" type="button"></button>
            </section>
          </div>
        </main>
=======
        <meta name="csrf-token" content="test-csrf" />
        <meta name="admin-user" content="admin" />
      </head>
      <body>
        <section id="view-personas">
          <h1 id="personasTitle">Personas</h1>
          <p id="personasSubtitle"></p>
          <p id="personasSummary"></p>
          <div id="personasSearchWrap">
            <input id="userSearch" type="text" />
          </div>
          <input id="newUserName" type="text" />
          <button id="createUserBtn" type="button"></button>
          <p id="createResult" hidden></p>
          <div id="usersList"></div>
        </section>
>>>>>>> origin/Cris
      </body>
    </html>`,
    {
      runScripts: 'outside-only',
      url: 'https://example.test/admin#personas',
    },
  );

<<<<<<< HEAD
  const { window } = dom;
  window.i18n = { t: (value) => value };
  window.CameraPIAdminLayout = { navigateToView: vi.fn() };
  window.CameraPIEnrollment = { startForUser: vi.fn(async () => {}) };
  window.requestAnimationFrame = (callback) => window.setTimeout(callback, 0);
  window.fetch = vi.fn(async (url, options = {}) => {
    if (url === '/api/users' && options.method === 'POST') return createResponse({ id: 12 });
    if (url === '/api/users') return createResponse(users);
    if (typeof url === 'string' && url.startsWith('/api/users/')) {
      const userId = Number(url.split('/')[3]);
      const user = users.find((candidate) => Number(candidate.id) === userId);
      if (user) return createResponse({ user, samples_count: user.samples_count || 0, recent_logs: [] });
    }
    if (url === '/api/access-logs?limit=200') return createResponse([]);
    if (url === '/api/status') return createResponse({ camera: 'online', model: 'loaded', door: 'ready' });
    if (url === '/api/config') return createResponse({ umbral_confianza: 70, max_intentos: 3, tiempo_apertura_seg: 5 });
    if (url === '/api/system/diagnostics') return createResponse({ summary: 'Todo en orden', all_ok: true, checks: {} });
    return createResponse({}, false, 404);
  });

  window.eval(ADMIN_SOURCE);
  activeWindows.add(window);
  return { window, document: window.document };
}

async function flushAsync() {
  await Promise.resolve();
  await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
}

afterEach(() => {
  activeWindows.forEach((windowRef) => windowRef.close());
=======
  const endpoints = new Map([
    ['/api/users', users],
    ['/api/access-logs?limit=200', []],
    ['/api/status', { camera: 'online', model: 'loaded', door: 'ready' }],
    ['/api/config', { umbral_confianza: 70, tiempo_apertura_seg: 5, max_intentos: 3 }],
    ['/api/system/diagnostics', { summary: 'Todo listo', all_ok: true, checks: {} }],
  ]);

  dom.window.fetch = vi.fn(async (url) => responseJson(endpoints.get(String(url)) ?? {}));
  dom.window.setInterval = vi.fn();
  dom.window.requestAnimationFrame = (callback) => callback();
  dom.window.CameraPITheme = {
    initTheme: vi.fn(),
    bindToggleButtons: vi.fn(),
  };

  dom.window.eval(ADMIN_SOURCE);
  activeWindows.add(dom.window);
  await flushAsyncWork();

  return dom;
}

afterEach(() => {
  activeWindows.forEach((windowObject) => windowObject.close());
>>>>>>> origin/Cris
  activeWindows.clear();
  vi.restoreAllMocks();
});

<<<<<<< HEAD
describe('admin personas redesigned UX', () => {
  it('renders visual person cards with thumbnail and primary action instead of a table', async () => {
    const { document } = createAdminDom({
      users: [
        {
          id: 7,
          nombre: 'Ada Lovelace',
          activo: true,
          samples_count: 35,
          needs_training: false,
          thumbnail_url: '/api/users/7/thumbnail',
          last_access_result: 'AUTORIZADO',
        },
      ],
    });

    await flushAsync();

    expect(document.querySelector('#usersList table')).toBeNull();
    const card = document.querySelector('[data-person-card="7"]');
    expect(card).not.toBeNull();
    expect(card.querySelector('img').getAttribute('src')).toBe('/api/users/7/thumbnail');
    expect(card.querySelector('.person-card__name').textContent).toContain('Ada Lovelace');
    expect(card.querySelector('.person-card__primary').textContent).toContain('Ver');
  });

  it('creates a person and immediately starts guided enrollment', async () => {
    const { document, window } = createAdminDom();
    await flushAsync();

    document.getElementById('newUserName').value = 'Grace Hopper';
    document.getElementById('createUserBtn').click();
    await flushAsync();
    await flushAsync();

    expect(window.fetch).toHaveBeenCalledWith('/api/users', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ nombre: 'Grace Hopper' }),
    }));
    expect(window.CameraPIAdminLayout.navigateToView).toHaveBeenCalledWith('enrolamiento');
    expect(window.CameraPIEnrollment.startForUser).toHaveBeenCalledWith(12);
  });

  it('keeps the person detail primary action aligned with inactive state', async () => {
    const { document, window } = createAdminDom({
      users: [
        {
          id: 4,
          nombre: 'Mario Ruiz',
          activo: false,
          samples_count: 0,
          needs_training: true,
          thumbnail_url: null,
        },
      ],
    });

    await flushAsync();
    await window.openPersonDetail(4);
    await flushAsync();

    const detailActions = document.querySelector('.person-detail-actions');
    expect(detailActions.querySelector('.btn-primary').textContent).toContain('Activar');
    expect(detailActions.textContent).not.toContain('Registrar rostro');
    expect(detailActions.textContent).not.toContain('Entrenar');
    expect([...document.querySelectorAll('#personDetailPanel button')]
      .filter((button) => button.textContent.includes('Activar'))).toHaveLength(1);
=======
describe('admin personas view', () => {
  it('renders a guided first-use empty state instead of an empty table', async () => {
    const dom = await createAdminDom({ users: [] });
    const { document } = dom.window;

    expect(document.getElementById('personasTitle')?.textContent).toBe('Agrega la primera persona');
    expect(document.getElementById('personasSubtitle')?.textContent).toContain('Empieza con el nombre');
    expect(document.getElementById('personasSearchWrap')?.hidden).toBe(true);
    expect(document.querySelector('#usersList table')).toBeNull();
    expect(document.querySelector('.personas-empty-state')?.textContent).toContain('Aún no hay personas');
  });

  it('renders registered people as action-led cards without status badges', async () => {
    const dom = await createAdminDom({
      users: [
        { id: 12, nombre: 'María López', activo: 1 },
        { id: 13, nombre: 'Jorge Pérez', activo: 0 },
      ],
    });
    const { document } = dom.window;

    const cards = document.querySelectorAll('.person-card');
    expect(cards).toHaveLength(2);
    expect(document.querySelector('#usersList table')).toBeNull();
    expect(document.querySelector('#usersList .badge')).toBeNull();

    expect(cards[0].textContent).toContain('María López');
    expect(cards[0].textContent).toContain('Activa · ID 12');
    expect(cards[0].querySelector('.person-card__primary')?.textContent).toContain('Registrar rostro');
    expect(cards[0].querySelector('.person-card__more')?.getAttribute('aria-label')).toBe('Más acciones para María López');

    expect(cards[1].textContent).toContain('Jorge Pérez');
    expect(cards[1].textContent).toContain('Inactiva · ID 13');
    expect(cards[1].querySelector('.person-card__primary')?.textContent).toContain('Activar persona');
  });

  it('keeps card rendering when search filters the people list', async () => {
    const dom = await createAdminDom({
      users: [
        { id: 12, nombre: 'María López', activo: 1 },
        { id: 13, nombre: 'Jorge Pérez', activo: 1 },
      ],
    });
    const { document, Event } = dom.window;
    const search = document.getElementById('userSearch');

    search.value = 'jorge';
    search.dispatchEvent(new Event('input', { bubbles: true }));

    const cards = document.querySelectorAll('.person-card');
    expect(cards).toHaveLength(1);
    expect(cards[0].textContent).toContain('Jorge Pérez');
    expect(document.querySelector('#usersList table')).toBeNull();
>>>>>>> origin/Cris
  });
});
