export function isWakeReadyStatus(status, runtime) {
  if (!status || typeof status !== 'object') return false;
  if (runtime?.isPollingPaused) return false;
  if (runtime?.isScanPaused) return false;
  if (status.analysis_state === 'sleep') return false;
  return status.camera === 'online';
}

