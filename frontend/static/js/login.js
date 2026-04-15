/* ══════════════════════════════════════════════════════
   OSVIUM — LOGIN  ·  Submit interceptor + access animation
   ══════════════════════════════════════════════════════ */

(function () {
  'use strict';

  const form    = document.querySelector('.login-card');
  const overlay = document.querySelector('.login-access-overlay');

  if (!form) return;

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ── Navigate to admin after animation completes ──── */
  function navigateToAdmin() {
    window.location.assign('/admin');
  }

  /* ── Inyectar anillo de onda de choque (tercer scan ring) */
  function injectShockwaveRing() {
    const badge = document.querySelector('.login-icon-badge');
    if (!badge) return;
    const ring = document.createElement('span');
    ring.className = 'shockwave-ring';
    badge.appendChild(ring);
  }

  /* ── Calcular delta real badge → centro del card ──── */
  function computeIrisDelta() {
    const badge = document.querySelector('.login-icon-badge');
    const card  = document.querySelector('.login-card');
    if (!badge || !card) return;

    const bR = badge.getBoundingClientRect();
    const cR = card.getBoundingClientRect();

    const badgeCX = bR.left + bR.width  / 2;
    const badgeCY = bR.top  + bR.height / 2;
    const cardCX  = cR.left + cR.width  / 2;
    const cardCY  = cR.top  + cR.height / 2;

    document.documentElement.style.setProperty('--iris-dx', (cardCX - badgeCX) + 'px');
    document.documentElement.style.setProperty('--iris-dy', (cardCY - badgeCY) + 'px');
  }

  /* ── Play success animation then navigate ─────────── */
  function playSuccessAndNavigate() {
    if (reducedMotion) {
      // Accesibilidad: solo fade rápido
      document.body.classList.add('login-access-granted', 'login-reduced-motion');
      setTimeout(navigateToAdmin, 200);
      return;
    }

    computeIrisDelta();
    injectShockwaveRing();
    document.body.classList.add('login-access-granted');

    // Navegar al terminar el flash del overlay (último beat de la animación)
    if (overlay) {
      // El overlay tiene delay 580ms + duración 320ms = 900ms total
      // Usamos animationend como señal precisa
      overlay.addEventListener('animationend', navigateToAdmin, { once: true });

      // Seguro de fallback: si animationend no dispara (ej. tab oculto)
      setTimeout(navigateToAdmin, 1100);
    } else {
      setTimeout(navigateToAdmin, 920);
    }
  }

  /* ── Mostrar error sin recargar ────────────────────── */
  function showError() {
    document.body.classList.add('login-access-denied');

    // Redirige al error del servidor tras el shake (360ms)
    setTimeout(function () {
      window.location.assign('/admin?error=1');
    }, 420);
  }

  /* ── Submit handler principal ──────────────────────── */
  form.addEventListener('submit', function (e) {
    e.preventDefault();

    // Deshabilitar botón para evitar doble submit
    const btn = form.querySelector('.login-submit');
    if (btn) btn.disabled = true;

    const body = new FormData(form);

    fetch('/auth/login', {
      method: 'POST',
      body: body,
      credentials: 'same-origin',
      redirect: 'follow',        // sigue el 303 automáticamente
    })
      .then(function (res) {
        // Si la URL final NO tiene ?error=1 → credenciales válidas
        const url = res.url || '';
        if (url.includes('error=1')) {
          showError();
        } else {
          playSuccessAndNavigate();
        }
      })
      .catch(function () {
        // Fetch falló (red, CORS, etc.) → fallback al submit nativo
        if (btn) btn.disabled = false;
        form.submit();
      });
  });

})();
