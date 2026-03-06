(function () {
  const DEFAULT_SCAN_MS = 1000;
  const MIN_SCAN_MS = 800;
  const MAX_SCAN_MS = 1500;
  const DEFAULT_FEED_INSET_PX = 0;

  class FaceActionController {
    constructor(options = {}) {
      this.button = options.buttonElement || document.getElementById('analyzeFaceBtn');
      this.overlay = options.overlayElement || document.getElementById('scanOverlay');
      this.stage = options.stageElement || document.getElementById('cameraStage');
      this.video = options.videoElement || document.getElementById('videoFeed');
      this.onResult = options.onResult;

      this.scanDurationMs = Number(options.scanDurationMs || DEFAULT_SCAN_MS);
      this.prefersReducedMotion =
        !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

      this.status = {};
      this.localBusy = false;

      if (!this.button || !this.overlay || !this.stage || !this.video) {
        this.available = false;
        return;
      }

      this.available = true;
      this.button.addEventListener('click', () => {
        this.handleAnalyzeClick();
      });

      this.setButtonState('idle');
      this.button.setAttribute('aria-busy', 'false');
    }

    updateStatus(status = {}) {
      this.status = status;
      if (!this.available) {
        return;
      }

      if (this.localBusy) {
        return;
      }

      const serverBusy = Boolean(status.analysis_busy);
      if (serverBusy) {
        this.button.disabled = true;
        this.button.setAttribute('aria-busy', 'true');
        this.setButtonState('scanning');
        return;
      }

      this.button.disabled = !this.isReady(status);
      this.button.setAttribute('aria-busy', 'false');
      this.setButtonState('idle');
    }

    isReady(status = this.status) {
      return status.camera === 'online' && status.model === 'loaded' && !status.analysis_busy;
    }

    setButtonState(state) {
      this.button.classList.remove('is-idle', 'is-scanning', 'is-success', 'is-error');
      this.button.classList.add(`is-${state}`);
    }

    setOverlayState(state) {
      this.overlay.classList.remove('is-scanning', 'is-success', 'is-error');
      this.overlay.classList.add(`is-${state}`);
    }

    showOverlay(rect, state = 'scanning') {
      this.overlay.style.left = `${rect.left}px`;
      this.overlay.style.top = `${rect.top}px`;
      this.overlay.style.width = `${rect.width}px`;
      this.overlay.style.height = `${rect.height}px`;
      this.overlay.classList.remove('is-hidden');
      this.setOverlayState(state);
      requestAnimationFrame(() => {
        this.overlay.classList.add('is-visible');
      });
    }

    hideOverlay() {
      this.overlay.classList.remove('is-visible', 'is-scanning', 'is-success', 'is-error');
      window.setTimeout(() => {
        if (!this.localBusy) {
          this.overlay.classList.add('is-hidden');
        }
      }, 160);
    }

    randomScanDuration() {
      if (this.prefersReducedMotion) {
        return MIN_SCAN_MS;
      }
      const clampedBase = Math.min(MAX_SCAN_MS, Math.max(MIN_SCAN_MS, this.scanDurationMs));
      const jitter = Math.floor(Math.random() * 141) - 70;
      return Math.min(MAX_SCAN_MS, Math.max(MIN_SCAN_MS, clampedBase + jitter));
    }

    async handleAnalyzeClick() {
      if (!this.available || this.localBusy || this.button.disabled) {
        return;
      }

      this.localBusy = true;
      this.button.disabled = true;
      this.button.setAttribute('aria-busy', 'true');
      this.setButtonState('scanning');

      const overlayRect = this.computeOverlayRect();
      this.showOverlay(overlayRect, 'scanning');

      const minDurationMs = this.randomScanDuration();
      const minDelay = this.sleep(minDurationMs);

      let statusCode = 0;
      let payload = null;

      try {
        const response = await fetch('/api/recognize', { method: 'POST' });
        statusCode = response.status;
        payload = await response.json();
      } catch (error) {
        payload = {
          ok: false,
          event: 'camera_error',
          result: 'REQUEST_FAILED',
          user_id: null,
          user_name: null,
          confidence: null,
          timestamp: Math.floor(Date.now() / 1000),
          analysis_busy: false,
          face_detected: false,
          face_bbox: null,
        };
      }

      await minDelay;

      const event = payload?.event || (statusCode === 409 ? 'busy' : 'camera_error');
      const visualState = event === 'authorized' ? 'success' : 'error';

      this.setButtonState(visualState);
      this.setOverlayState(visualState);

      await this.sleep(this.prefersReducedMotion ? 60 : 220);
      this.localBusy = false;
      this.hideOverlay();
      this.setButtonState('idle');
      this.button.disabled = !this.isReady(this.status);
      this.button.setAttribute('aria-busy', 'false');

      if (typeof this.onResult === 'function') {
        await this.onResult(payload, statusCode);
      }
    }

    getFeedInset() {
      const rawInset = window.getComputedStyle(this.stage).getPropertyValue('--camera-feed-inset');
      const parsedInset = Number.parseFloat(rawInset);
      if (!Number.isFinite(parsedInset)) {
        return DEFAULT_FEED_INSET_PX;
      }
      return Math.max(0, parsedInset);
    }

    computeOverlayRect() {
      const stageWidth = this.stage.clientWidth;
      const stageHeight = this.stage.clientHeight;
      const inset = this.getFeedInset();

      const visibleLeft = inset;
      const visibleTop = inset;
      const visibleWidth = Math.max(1, stageWidth - inset * 2);
      const visibleHeight = Math.max(1, stageHeight - inset * 2);

      const bbox = this.status?.face_bbox;
      if (!bbox || !this.status?.face_detected) {
        return this.defaultOverlayRect(visibleLeft, visibleTop, visibleWidth, visibleHeight);
      }

      const frameWidth = Number(this.status.camera_frame_width) || 640;
      const frameHeight = Number(this.status.camera_frame_height) || 480;
      const scale = Math.max(visibleWidth / frameWidth, visibleHeight / frameHeight);

      const drawnWidth = frameWidth * scale;
      const drawnHeight = frameHeight * scale;
      const drawnLeft = visibleLeft + (visibleWidth - drawnWidth) / 2;
      const drawnTop = visibleTop + (visibleHeight - drawnHeight) / 2;

      const xNorm = this.clamp(Number(bbox.x) || 0, 0, 1);
      const yNorm = this.clamp(Number(bbox.y) || 0, 0, 1);
      const wNorm = this.clamp(Number(bbox.w) || 0.15, 0.02, 1);
      const hNorm = this.clamp(Number(bbox.h) || 0.15, 0.02, 1);

      let left = drawnLeft + xNorm * frameWidth * scale;
      let top = drawnTop + yNorm * frameHeight * scale;
      let width = Math.max(56, wNorm * frameWidth * scale);
      let height = Math.max(56, hNorm * frameHeight * scale);

      const maxRight = visibleLeft + visibleWidth;
      const maxBottom = visibleTop + visibleHeight;

      left = this.clamp(left, visibleLeft, maxRight - 30);
      top = this.clamp(top, visibleTop, maxBottom - 30);
      if (left + width > maxRight) {
        width = Math.max(30, maxRight - left);
      }
      if (top + height > maxBottom) {
        height = Math.max(30, maxBottom - top);
      }

      return {
        left: Math.round(left),
        top: Math.round(top),
        width: Math.round(width),
        height: Math.round(height),
      };
    }

    defaultOverlayRect(visibleLeft, visibleTop, visibleWidth, visibleHeight) {
      const size = Math.max(86, Math.min(visibleWidth, visibleHeight) * 0.34);
      return {
        left: Math.round(visibleLeft + (visibleWidth - size) / 2),
        top: Math.round(visibleTop + (visibleHeight - size) / 2),
        width: Math.round(size),
        height: Math.round(size),
      };
    }

    clamp(value, min, max) {
      return Math.min(max, Math.max(min, value));
    }

    sleep(ms) {
      return new Promise((resolve) => {
        window.setTimeout(resolve, ms);
      });
    }
  }

  function create(options = {}) {
    const controller = new FaceActionController(options);
    return controller.available ? controller : null;
  }

  window.CameraPIFaceAction = {
    create,
  };
})();
