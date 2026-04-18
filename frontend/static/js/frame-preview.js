export function appendCacheBuster(src, value) {
  const separator = String(src).includes('?') ? '&' : '?';
  return `${src}${separator}t=${encodeURIComponent(value)}`;
}

export function createFramePreviewController(deps = {}) {
  const image = deps.imageElement || null;
  const streamUrl = deps.streamUrl || deps.frameUrl || '/api/stream';
  const nowFn = deps.nowFn || (() => Date.now());
  const onError = deps.onError || (() => {});

  let running = false;
  let openCounter = 0;

  function nextStreamSrc(reason) {
    openCounter += 1;
    const cacheKey = `${reason || 'stream'}-${nowFn()}-${openCounter}`;
    return appendCacheBuster(streamUrl, cacheKey);
  }

  function handleStreamError() {
    if (running) {
      running = false;
      image.setAttribute('src', '');
      onError(new Error('stream_error'));
    }
  }

  if (image && typeof image.addEventListener === 'function') {
    image.addEventListener('error', handleStreamError);
  }

  function resume(reason = 'stream') {
    if (!image) return false;
    running = true;
    image.setAttribute('src', nextStreamSrc(reason));
    return true;
  }

  function pause() {
    running = false;
    if (image) {
      image.setAttribute('src', '');
    }
    return Boolean(image);
  }

  function ensureRunning() {
    if (running) return false;
    return resume('ensure');
  }

  function isRunning() {
    return running;
  }

  function destroy() {
    pause();
    if (image && typeof image.removeEventListener === 'function') {
      image.removeEventListener('error', handleStreamError);
    }
  }

  return {
    resume,
    pause,
    ensureRunning,
    isRunning,
    destroy,
  };
}
