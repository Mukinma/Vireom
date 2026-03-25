import { describe, expect, it, vi } from 'vitest';
import {
  DESKTOP_READY_EVENT,
  bindDesktopReady,
  isDesktopLaunchPending,
} from '../static/js/desktop-ready.js';

describe('desktop-ready helpers', () => {
  it('detecta pending desktop por query param', () => {
    const windowObject = {
      location: { search: '?desktop-launch=1' },
    };

    expect(isDesktopLaunchPending(windowObject)).toBe(true);
  });

  it('permite forzar pending por flag global', () => {
    const windowObject = {
      __VIREOM_DESKTOP_PENDING__: true,
      location: { search: '' },
    };

    expect(isDesktopLaunchPending(windowObject)).toBe(true);
  });

  it('ejecuta onReady solo una vez', () => {
    const listeners = new Map();
    const onReady = vi.fn();
    const windowObject = {
      addEventListener: vi.fn((eventName, handler) => {
        listeners.set(eventName, handler);
      }),
      removeEventListener: vi.fn((eventName) => {
        listeners.delete(eventName);
      }),
    };

    bindDesktopReady({
      windowObject,
      enabled: true,
      onReady,
    });

    listeners.get(DESKTOP_READY_EVENT)?.();
    listeners.get(DESKTOP_READY_EVENT)?.();

    expect(onReady).toHaveBeenCalledTimes(1);
  });
});
