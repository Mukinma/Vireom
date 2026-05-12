import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { JSDOM } from 'jsdom';

const ADMIN_SOURCE = readFileSync(
  resolve(process.cwd(), 'frontend/static/js/admin.js'),
  'utf8',
);

const activeWindows = new Set();

function responseJson(payload, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async json() {
      return payload;
    },
    async text() {
      return JSON.stringify(payload);
    },
  };
}

async function flushAsyncWork() {
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
}

async function createAdminDom({ users = [] } = {}) {
  const dom = new JSDOM(
    `<!doctype html>
    <html lang="es">
      <head>
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
      </body>
    </html>`,
    {
      runScripts: 'outside-only',
      url: 'https://example.test/admin#personas',
    },
  );

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
  activeWindows.clear();
  vi.restoreAllMocks();
});

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
  });
});
