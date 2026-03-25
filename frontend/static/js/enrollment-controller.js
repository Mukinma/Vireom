/**
 * enrollment-controller.js — UI controller for guided facial enrollment.
 *
 * Manages polling, canvas overlay drawing, step progression UI, and
 * all visual feedback (flash, warnings, completion).
 */

(function () {
  /* ── FSM reference ─────────────────────────────────────────────── */
  const FSM = window.CameraPIEnrollmentFSM;
  if (!FSM) return;

  const { STATES, EVENTS, EFFECTS, createInitialContext, transition } = FSM;

  /* ── DOM refs ──────────────────────────────────────────────────── */
  const viewport = document.getElementById('enrollViewport');
  const stream = document.getElementById('enrollStream');
  const overlay = document.getElementById('enrollOverlay');
  const hud = document.getElementById('enrollHud');
  const stepBadge = document.getElementById('enrollStepBadge');
  const instruction = document.getElementById('enrollInstruction');
  const message = document.getElementById('enrollMessage');
  const dotsContainer = document.getElementById('enrollDots');
  const faceWarning = document.getElementById('enrollFaceWarning');
  const lightWarning = document.getElementById('enrollLightWarning');
  const flash = document.getElementById('enrollFlash');
  const completion = document.getElementById('enrollCompletion');
  const completionSub = document.getElementById('enrollCompletionSub');
  const abortBtn = document.getElementById('enrollAbortBtn');
  const retryBtn = document.getElementById('enrollRetryBtn');
  const startBtn = document.getElementById('enrollStartBtn');
  const userSelect = document.getElementById('enrollUserSelect');
  const instructionsPanel = document.getElementById('enrollInstructionsPanel');
  const stepsPanel = document.getElementById('enrollStepsPanel');
  const stepsList = document.getElementById('enrollStepsList');
  const totalFill = document.getElementById('enrollTotalFill');
  const totalLabel = document.getElementById('enrollTotalLabel');

  if (!viewport || !overlay) return;

  /* ── State ─────────────────────────────────────────────────────── */
  let ctx = createInitialContext();
  let pollIntervalId = null;
  let userId = null;
  let animFrame = null;

  const POLL_MS = 200;

  /* ── Canvas setup ──────────────────────────────────────────────── */
  const canvasCtx = overlay.getContext('2d');

  function resizeCanvas() {
    const rect = viewport.getBoundingClientRect();
    overlay.width = rect.width;
    overlay.height = rect.height;
  }

  /* ── API helpers ───────────────────────────────────────────────── */

  async function api(url, options = {}) {
    const res = await fetch(url, { credentials: 'same-origin', ...options });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || body.error || `HTTP ${res.status}`);
    }
    return res.json();
  }

  async function loadUsers() {
    try {
      const users = await api('/api/users');
      if (!userSelect) return;
      const current = userSelect.value;
      userSelect.innerHTML = '<option value="">Seleccionar persona...</option>';
      users.forEach((u) => {
        const opt = document.createElement('option');
        opt.value = u.id;
        opt.textContent = `${u.nombre} (ID: ${u.id})`;
        userSelect.appendChild(opt);
      });
      if (current) userSelect.value = current;
    } catch (_) {}
  }

  /* ── Polling ───────────────────────────────────────────────────── */

  function startPolling() {
    stopPolling();
    pollIntervalId = setInterval(poll, POLL_MS);
  }

  function stopPolling() {
    if (pollIntervalId) {
      clearInterval(pollIntervalId);
      pollIntervalId = null;
    }
  }

  async function poll() {
    try {
      const status = await api('/api/enrollment/status');
      dispatch({ type: EVENTS.BACKEND_STATUS, status });
    } catch (err) {
      dispatch({ type: EVENTS.ERROR, error: err });
    }
  }

  /* ── FSM dispatch ──────────────────────────────────────────────── */

  function dispatch(event) {
    const next = transition(ctx, event);
    ctx = next;
    executeEffects(next.effects, next);
  }

  /* ── Effect executor ───────────────────────────────────────────── */

  function executeEffects(effects, state) {
    for (const effect of effects) {
      switch (effect) {
        case EFFECTS.START_POLLING:
          startPolling();
          break;
        case EFFECTS.STOP_POLLING:
          stopPolling();
          break;
        case EFFECTS.SHOW_INSTRUCTIONS:
          showInstructions();
          break;
        case EFFECTS.HIDE_INSTRUCTIONS:
          hideInstructions();
          break;
        case EFFECTS.UPDATE_OVERLAY:
          scheduleOverlayDraw();
          break;
        case EFFECTS.UPDATE_PROGRESS:
          updateProgress();
          break;
        case EFFECTS.UPDATE_MESSAGE:
          updateMessage();
          break;
        case EFFECTS.SHOW_STEP_GUIDE:
          updateStepGuide();
          break;
        case EFFECTS.SHOW_HOLD_FEEDBACK:
          updateMessage();
          scheduleOverlayDraw();
          break;
        case EFFECTS.SHOW_CAPTURE_FLASH:
          triggerFlash();
          break;
        case EFFECTS.SHOW_STEP_SUCCESS:
          updateProgress();
          break;
        case EFFECTS.SHOW_COMPLETION:
          showCompletion();
          break;
        case EFFECTS.SHOW_FACE_WARNING:
          faceWarning?.classList.remove('is-hidden');
          break;
        case EFFECTS.HIDE_FACE_WARNING:
          faceWarning?.classList.add('is-hidden');
          break;
        case EFFECTS.SHOW_LIGHT_WARNING:
          lightWarning?.classList.remove('is-hidden');
          break;
        case EFFECTS.HIDE_LIGHT_WARNING:
          lightWarning?.classList.add('is-hidden');
          break;
      }
    }
  }

  /* ── UI actions ────────────────────────────────────────────────── */

  function showInstructions() {
    if (instructionsPanel) instructionsPanel.hidden = false;
    if (stepsPanel) stepsPanel.hidden = true;
    if (completion) completion.classList.add('is-hidden');
    if (hud) hud.hidden = true;
    clearCanvas();
  }

  function hideInstructions() {
    if (instructionsPanel) instructionsPanel.hidden = true;
    if (stepsPanel) stepsPanel.hidden = false;
    if (hud) hud.hidden = false;
  }

  function updateStepGuide() {
    const bs = ctx.backendState;
    if (!bs) return;
    if (stepBadge) stepBadge.textContent = `Paso ${bs.current_step + 1} de ${bs.total_steps}`;
    if (instruction) instruction.textContent = bs.step_label;
    updateMessage();
  }

  function updateMessage() {
    const bs = ctx.backendState;
    if (!bs) return;
    if (message) message.textContent = bs.message || '';
    if (retryBtn) retryBtn.hidden = ctx.state !== STATES.STEP_ACTIVE;
  }

  function updateProgress() {
    const bs = ctx.backendState;
    if (!bs) return;

    // Dots
    renderDots(bs.steps_summary);

    // Steps list
    renderStepsList(bs.steps_summary);

    // Total progress bar
    const pct = bs.total_needed > 0
      ? Math.round((bs.total_captured / bs.total_needed) * 100)
      : 0;
    if (totalFill) totalFill.style.width = `${pct}%`;
    if (totalLabel) totalLabel.textContent = `${bs.total_captured} / ${bs.total_needed}`;
  }

  function renderDots(steps) {
    if (!dotsContainer) return;
    dotsContainer.innerHTML = '';
    steps.forEach((s, i) => {
      if (i > 0) {
        const line = document.createElement('span');
        line.className = 'enrollment-dot-line';
        if (s.status === 'complete' || steps[i - 1]?.status === 'complete') {
          line.style.background = 'var(--success)';
        }
        dotsContainer.appendChild(line);
      }
      const dot = document.createElement('span');
      dot.className = 'enrollment-dot';
      if (s.status === 'complete') dot.classList.add('is-complete');
      if (s.status === 'active') dot.classList.add('is-active');
      dotsContainer.appendChild(dot);
    });
  }

  function renderStepsList(steps) {
    if (!stepsList) return;
    stepsList.innerHTML = '';
    steps.forEach((s, i) => {
      const li = document.createElement('li');
      li.className = 'enrollment-step-item';
      if (s.status === 'active') li.classList.add('is-active');
      if (s.status === 'complete') li.classList.add('is-complete');

      const indicator = document.createElement('span');
      indicator.className = 'enrollment-step-item__indicator';
      indicator.textContent = s.status === 'complete' ? '\u2713' : String(i + 1);

      const label = document.createElement('span');
      label.className = 'enrollment-step-item__label';
      label.textContent = s.label;

      const samples = document.createElement('span');
      samples.className = 'enrollment-step-item__samples';
      samples.textContent = `${s.samples}/5`;

      li.appendChild(indicator);
      li.appendChild(label);
      li.appendChild(samples);
      stepsList.appendChild(li);
    });
  }

  function triggerFlash() {
    if (!flash) return;
    flash.classList.remove('is-active');
    void flash.offsetWidth; // force reflow
    flash.classList.add('is-active');
    setTimeout(() => flash.classList.remove('is-active'), 250);
  }

  function showCompletion() {
    const bs = ctx.backendState;
    if (completion) {
      completion.classList.remove('is-hidden');
      if (completionSub && bs) {
        completionSub.textContent = `${bs.total_captured} muestras capturadas`;
      }
    }
    if (hud) hud.hidden = true;
    clearCanvas();
    triggerAutoTrain();
  }

  async function triggerAutoTrain() {
    try {
      const result = await api('/api/train', { method: 'POST' });
      showAdminToastSafe({
        text: 'Modelo actualizado',
        sub: `${result.samples_used} muestras de ${result.unique_users} personas`,
        cls: 'success',
      });
    } catch (_) {
      showAdminToastSafe({
        text: 'Entrena manualmente desde Sistema',
        cls: 'warning',
      });
    }
  }

  /* ── Canvas overlay drawing ────────────────────────────────────── */

  function scheduleOverlayDraw() {
    if (animFrame) cancelAnimationFrame(animFrame);
    animFrame = requestAnimationFrame(drawOverlay);
  }

  function clearCanvas() {
    resizeCanvas();
    canvasCtx.clearRect(0, 0, overlay.width, overlay.height);
  }

  function drawOverlay() {
    resizeCanvas();
    const w = overlay.width;
    const h = overlay.height;
    const c = canvasCtx;

    c.clearRect(0, 0, w, h);

    const bs = ctx.backendState;
    if (!bs || ctx.state === STATES.COMPLETED || ctx.state === STATES.IDLE) return;

    const cx = w * 0.5;
    const cy = h * 0.42;
    const rx = w * 0.17;
    const ry = h * 0.24;

    // ── Guide ellipse ──
    c.save();
    c.beginPath();
    c.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);

    if (bs.pose_matched) {
      if (ctx.state === STATES.HOLDING || ctx.state === STATES.CAPTURING) {
        c.strokeStyle = 'rgba(34, 197, 94, 0.8)';   // green
        c.lineWidth = 3;
        c.shadowColor = 'rgba(34, 197, 94, 0.4)';
        c.shadowBlur = 16;
      } else {
        c.strokeStyle = 'rgba(var(--primary-rgb), 0.7)';
        c.strokeStyle = 'rgba(91, 140, 255, 0.7)';   // accent blue
        c.lineWidth = 2.5;
        c.shadowColor = 'rgba(91, 140, 255, 0.3)';
        c.shadowBlur = 12;
      }
    } else if (!bs.face_detected) {
      c.strokeStyle = 'rgba(148, 163, 184, 0.4)';    // gray
      c.lineWidth = 2;
      c.setLineDash([8, 6]);
      c.shadowBlur = 0;
    } else {
      c.strokeStyle = 'rgba(245, 158, 11, 0.7)';     // amber
      c.lineWidth = 2.5;
      c.shadowColor = 'rgba(245, 158, 11, 0.25)';
      c.shadowBlur = 10;
    }

    c.stroke();
    c.restore();

    // ── Hold progress arc ──
    if (ctx.state === STATES.HOLDING && bs.hold_progress > 0) {
      c.save();
      const angle = bs.hold_progress * Math.PI * 2;
      c.beginPath();
      c.ellipse(cx, cy, rx + 6, ry + 6, 0, -Math.PI / 2, -Math.PI / 2 + angle);
      c.strokeStyle = 'rgba(34, 197, 94, 0.9)';
      c.lineWidth = 4;
      c.lineCap = 'round';
      c.shadowColor = 'rgba(34, 197, 94, 0.5)';
      c.shadowBlur = 10;
      c.stroke();
      c.restore();
    }

    // ── Direction arrow ──
    if (bs.guidance_arrow && !bs.pose_matched) {
      drawArrow(c, cx, cy, rx, ry, bs.guidance_arrow);
    }
  }

  function drawArrow(c, cx, cy, rx, ry, direction) {
    const time = Date.now();
    const bounce = Math.sin(time / 200) * 6;
    const arrowSize = 18;
    let ax, ay, angle;

    switch (direction) {
      case 'left':
        ax = cx - rx - 30 + bounce;
        ay = cy;
        angle = Math.PI;
        break;
      case 'right':
        ax = cx + rx + 30 - bounce;
        ay = cy;
        angle = 0;
        break;
      case 'up':
        ax = cx;
        ay = cy - ry - 30 + bounce;
        angle = -Math.PI / 2;
        break;
      case 'down':
        ax = cx;
        ay = cy + ry + 30 - bounce;
        angle = Math.PI / 2;
        break;
      default:
        return;
    }

    c.save();
    c.translate(ax, ay);
    c.rotate(angle);
    c.beginPath();
    c.moveTo(arrowSize, 0);
    c.lineTo(-arrowSize * 0.4, -arrowSize * 0.6);
    c.lineTo(-arrowSize * 0.4, arrowSize * 0.6);
    c.closePath();
    c.fillStyle = 'rgba(245, 158, 11, 0.8)';
    c.shadowColor = 'rgba(245, 158, 11, 0.4)';
    c.shadowBlur = 8;
    c.fill();
    c.restore();
  }

  /* ── Event handlers ────────────────────────────────────────────── */

  startBtn?.addEventListener('click', async () => {
    const uid = userSelect?.value;
    if (!uid) {
      showAdminToastSafe({ text: 'Selecciona una persona', cls: 'warning' });
      return;
    }

    try {
      await api('/api/enrollment/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: parseInt(uid, 10) }),
      });
      userId = parseInt(uid, 10);
      dispatch({ type: EVENTS.START });
      dispatch({ type: EVENTS.DISMISS_INSTRUCTIONS });
    } catch (err) {
      showAdminToastSafe({ text: 'Error al iniciar', sub: err.message, cls: 'error' });
    }
  });

  abortBtn?.addEventListener('click', async () => {
    try {
      await api('/api/enrollment/abort', { method: 'POST' });
    } catch (_) {}
    dispatch({ type: EVENTS.ABORT });
    resetUI();
    if (typeof window.showPersonasListMode === 'function') window.showPersonasListMode();
  });

  retryBtn?.addEventListener('click', async () => {
    try {
      await api('/api/enrollment/retry-step', { method: 'POST' });
    } catch (_) {}
    dispatch({ type: EVENTS.RETRY });
  });

  /* Back buttons — return to personas list */
  const enrollBackBtn = document.getElementById('enrollBackBtn');
  const enrollBackToListBtn = document.getElementById('enrollBackToListBtn');

  enrollBackBtn?.addEventListener('click', () => {
    if (pollIntervalId) {
      api('/api/enrollment/abort', { method: 'POST' }).catch(() => {});
      dispatch({ type: EVENTS.ABORT });
    }
    resetUI();
    if (typeof window.showPersonasListMode === 'function') window.showPersonasListMode();
  });

  enrollBackToListBtn?.addEventListener('click', () => {
    resetUI();
    if (typeof window.showPersonasListMode === 'function') window.showPersonasListMode();
  });

  function resetUI() {
    ctx = createInitialContext();
    userId = null;
    showInstructions();
    clearCanvas();
    faceWarning?.classList.add('is-hidden');
    lightWarning?.classList.add('is-hidden');
    if (dotsContainer) dotsContainer.innerHTML = '';
    if (stepsList) stepsList.innerHTML = '';
    if (totalFill) totalFill.style.width = '0%';
    if (totalLabel) totalLabel.textContent = '0 / 35';
    if (retryBtn) retryBtn.hidden = true;
  }

  function showAdminToastSafe(opts) {
    if (typeof window.showAdminToast === 'function') {
      window.showAdminToast(opts);
    }
  }

  /* ── View lifecycle ────────────────────────────────────────────── */

  function onViewChange(e) {
    if (e.detail?.viewId === 'enrolamiento') {
      loadUsers();
      resizeCanvas();
    } else {
      // If we navigate away, stop polling but don't abort
      if (pollIntervalId && ctx.state !== STATES.COMPLETED) {
        stopPolling();
      }
    }
  }

  window.addEventListener('admin:viewchange', onViewChange);
  window.addEventListener('resize', resizeCanvas);

  /* ── Public API ────────────────────────────────────────────────── */

  window.CameraPIEnrollment = {
    reset: resetUI,
  };
})();
