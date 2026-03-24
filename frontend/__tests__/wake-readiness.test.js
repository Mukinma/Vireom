import { describe, it, expect } from 'vitest';
import { isWakeReadyStatus } from '../static/js/wake-readiness.js';

describe('wake readiness policy', () => {
  it('is ready when camera is online and loops resumed even without model loaded', () => {
    const status = {
      camera: 'online',
      model: 'missing',
      analysis_busy: false,
    };

    const ready = isWakeReadyStatus(status, {
      isPollingPaused: false,
      isScanPaused: false,
    });

    expect(ready).toBe(true);
  });

  it('is not ready when polling is paused', () => {
    const status = { camera: 'online' };
    const ready = isWakeReadyStatus(status, {
      isPollingPaused: true,
      isScanPaused: false,
    });
    expect(ready).toBe(false);
  });

  it('is not ready when backend analysis is sleeping', () => {
    const status = { camera: 'online', analysis_state: 'sleep' };
    const ready = isWakeReadyStatus(status, {
      isPollingPaused: false,
      isScanPaused: false,
    });
    expect(ready).toBe(false);
  });
});
