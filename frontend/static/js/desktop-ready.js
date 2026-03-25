export const DESKTOP_READY_EVENT = 'vireom:desktop-ready';
export const DESKTOP_LAUNCH_PARAM = 'desktop-launch';

export function isDesktopLaunchPending(windowObject = window) {
  if (!windowObject) {
    return false;
  }

  if (windowObject.__VIREOM_DESKTOP_PENDING__ === true) {
    return true;
  }

  try {
    const search = typeof windowObject.location?.search === 'string' ? windowObject.location.search : '';
    return new URLSearchParams(search).get(DESKTOP_LAUNCH_PARAM) === '1';
  } catch (_error) {
    return false;
  }
}

export function bindDesktopReady({ windowObject = window, enabled = false, onReady }) {
  if (!enabled || !windowObject?.addEventListener || typeof onReady !== 'function') {
    return () => {};
  }

  let consumed = false;

  const handler = () => {
    if (consumed) {
      return;
    }
    consumed = true;
    onReady();
  };

  windowObject.addEventListener(DESKTOP_READY_EVENT, handler);
  return () => windowObject.removeEventListener(DESKTOP_READY_EVENT, handler);
}
