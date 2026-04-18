(function () {
  const MIN_SCAN_MS = 600;
  const MAX_SCAN_MS = 1200;

  class FaceActionController {
    constructor(options = {}) {
      this.stage = options.stageElement || document.getElementById('cameraStage');
      this.video = options.videoElement || document.getElementById('videoFeed');
      this.onResult = options.onResult;
      this.status = {};
      this.localBusy = false;
      this.available = !!(this.stage && this.video);
    }

    updateStatus(status = {}) {
      this.status = status;
    }

    isReady(status = this.status) {
      return status.camera === 'online' && status.model === 'loaded' && !status.analysis_busy;
    }

    async handleAnalyzeClick() {
      if (!this.available || this.localBusy) {
        return;
      }

      this.localBusy = true;

      const minDelay = this.sleep(MIN_SCAN_MS + Math.floor(Math.random() * (MAX_SCAN_MS - MIN_SCAN_MS)));

      let statusCode = 0;
      let payload = null;

      try {
        const token = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
        const response = await fetch('/api/recognize', {
          method: 'POST',
          credentials: 'same-origin',
          headers: token ? { 'x-csrf-token': token } : {},
        });
        statusCode = response.status;
        payload = await response.json();
      } catch (error) {
        payload = {
          ok: false,
          event: 'camera_error',
          result: 'REQUEST_FAILED',
          timestamp: Math.floor(Date.now() / 1000),
          analysis_busy: false,
          face_detected: false,
        };
      }

      await minDelay;
      this.localBusy = false;

      if (typeof this.onResult === 'function') {
        await this.onResult(payload, statusCode);
      }
    }

    sleep(ms) {
      return new Promise((resolve) => setTimeout(resolve, ms));
    }
  }

  function create(options = {}) {
    const controller = new FaceActionController(options);
    return controller.available ? controller : null;
  }

  window.CameraPIFaceAction = { create };
})();
