import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createLockscreenController, EVENTS, STATES } from '../static/js/lockscreen-controller.js';

function createDeps(overrides = {}) {
  return {
    showLockscreen: vi.fn(),
    hideLockscreen: vi.fn(),
    pauseCamera: vi.fn(() => true),
    resumeCamera: vi.fn(() => true),
    pauseScan: vi.fn(() => true),
    resumeScan: vi.fn(() => true),
    pausePolling: vi.fn(() => true),
    resumePolling: vi.fn(() => true),
    logTransition: vi.fn(),
    onResetIdleDeadline: vi.fn(),
    onIgnoredEvent: vi.fn(),
    setTimeoutFn: vi.fn((fn, ms) => setTimeout(fn, ms)),
    clearTimeoutFn: vi.fn((id) => clearTimeout(id)),
    ...overrides,
  };
}

describe('lockscreen controller', () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('starts in LOCKSCREEN_VISIBLE and schedules ENTER_SLEEP via setTimeoutFn', () => {
    const deps = createDeps();
    const controller = createLockscreenController(deps);
    const snapshot = controller.getSnapshot();
    expect(snapshot.state).toBe(STATES.LOCKSCREEN_VISIBLE);
    expect(snapshot.sleepReason).toBe('boot');
    expect(deps.setTimeoutFn).toHaveBeenCalledTimes(1);
    expect(deps.setTimeoutFn).toHaveBeenCalledWith(expect.any(Function), 260);
    controller.destroy();
  });

  it('boot SCHEDULE_ENTER_SLEEP fires ENTER_SLEEP after lockEnterAnimMs', () => {
    const deps = createDeps();
    const controller = createLockscreenController(deps);

    expect(controller.getSnapshot().state).toBe(STATES.LOCKSCREEN_VISIBLE);
    vi.advanceTimersByTime(260);
    expect(controller.getSnapshot().state).toBe(STATES.SLEEP_FORCED);
    expect(deps.pauseCamera).toHaveBeenCalledTimes(1);
    expect(deps.pausePolling).toHaveBeenCalledTimes(1);
    controller.destroy();
  });

  it('creates wakeAttemptId when waking from sleep', () => {
    const controller = createLockscreenController(createDeps());
    vi.advanceTimersByTime(260);
    controller.dispatch({ type: EVENTS.USER_TAP_OR_CLICK });

    const snapshot = controller.getSnapshot();
    expect(snapshot.state).toBe(STATES.WAKING);
    expect(snapshot.wakeAttemptId).toBe(1);
    controller.destroy();
  });

  it('ignores stale WAKE_READY from previous attempt', () => {
    const controller = createLockscreenController(createDeps());
    vi.advanceTimersByTime(260);
    controller.dispatch({ type: EVENTS.USER_TAP_OR_CLICK }); // attempt 1
    controller.dispatch({ type: EVENTS.RESUME_FAIL, wakeAttemptId: 1 });
    controller.dispatch({ type: EVENTS.USER_TAP_OR_CLICK }); // attempt 2
    controller.dispatch({ type: EVENTS.WAKE_READY, wakeAttemptId: 1 }); // stale

    const snapshot = controller.getSnapshot();
    expect(snapshot.state).toBe(STATES.WAKING);
    expect(snapshot.wakeAttemptId).toBe(2);
    controller.destroy();
  });

  it('emits idle reset callback after WAKE_READY', () => {
    const deps = createDeps();
    const controller = createLockscreenController(deps);
    vi.advanceTimersByTime(260);

    controller.dispatch({ type: EVENTS.USER_TAP_OR_CLICK });
    controller.dispatch({ type: EVENTS.WAKE_READY, wakeAttemptId: 1 });

    expect(controller.getSnapshot().state).toBe(STATES.ACTIVE_UNLOCKED);
    expect(deps.onResetIdleDeadline).toHaveBeenCalledTimes(1);
    controller.destroy();
  });

  it('logTransition includes durationMs and resumeContext on WAKE_READY', () => {
    const deps = createDeps();
    const controller = createLockscreenController(deps);
    vi.advanceTimersByTime(260);

    controller.dispatch({ type: EVENTS.USER_TAP_OR_CLICK });
    vi.advanceTimersByTime(50);
    controller.dispatch({ type: EVENTS.WAKE_READY, wakeAttemptId: 1 });

    const wakingToActive = deps.logTransition.mock.calls.find(
      ([arg]) => arg.fromState === STATES.WAKING && arg.toState === STATES.ACTIVE_UNLOCKED,
    );
    expect(wakingToActive).toBeDefined();
    const [entry] = wakingToActive;
    expect(typeof entry.durationMs).toBe('number');
    expect(entry.durationMs).toBeGreaterThanOrEqual(0);
    expect(entry.resumeContext).toBe('ok');
    controller.destroy();
  });

  it('logTransition includes resumeContext=resume_fail on RESUME_FAIL', () => {
    const deps = createDeps();
    const controller = createLockscreenController(deps);
    vi.advanceTimersByTime(260);

    controller.dispatch({ type: EVENTS.USER_TAP_OR_CLICK });
    controller.dispatch({ type: EVENTS.RESUME_FAIL, wakeAttemptId: 1 });

    const wakingToSleep = deps.logTransition.mock.calls.find(
      ([arg]) => arg.fromState === STATES.WAKING && arg.toState === STATES.SLEEP_FORCED,
    );
    expect(wakingToSleep).toBeDefined();
    const [entry] = wakingToSleep;
    expect(entry.resumeContext).toBe('resume_fail');
    controller.destroy();
  });

  it('logTransition includes errorCode from RESUME_FAIL event', () => {
    const deps = createDeps();
    const controller = createLockscreenController(deps);
    vi.advanceTimersByTime(260);

    controller.dispatch({ type: EVENTS.USER_TAP_OR_CLICK });
    controller.dispatch({
      type: EVENTS.RESUME_FAIL,
      wakeAttemptId: 1,
      errorCode: 'wake_http_503',
    });

    const wakingToSleep = deps.logTransition.mock.calls.find(
      ([arg]) => arg.fromState === STATES.WAKING && arg.toState === STATES.SLEEP_FORCED,
    );
    expect(wakingToSleep).toBeDefined();
    const [entry] = wakingToSleep;
    expect(entry.errorCode).toBe('wake_http_503');
    controller.destroy();
  });

  it('logTransition omits errorCode when not present in event', () => {
    const deps = createDeps();
    const controller = createLockscreenController(deps);
    vi.advanceTimersByTime(260);

    controller.dispatch({ type: EVENTS.USER_TAP_OR_CLICK });
    controller.dispatch({ type: EVENTS.WAKE_READY, wakeAttemptId: 1 });

    const wakingToActive = deps.logTransition.mock.calls.find(
      ([arg]) => arg.fromState === STATES.WAKING && arg.toState === STATES.ACTIVE_UNLOCKED,
    );
    expect(wakingToActive).toBeDefined();
    const [entry] = wakingToActive;
    expect(entry.errorCode).toBeUndefined();
    controller.destroy();
  });

  it('logs ignored events via callback with event type', () => {
    const deps = createDeps();
    const controller = createLockscreenController(deps);

    controller.dispatch({ type: EVENTS.IDLE_TIMEOUT_45S });
    expect(deps.onIgnoredEvent).toHaveBeenCalledTimes(1);
    expect(deps.onIgnoredEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        state: STATES.LOCKSCREEN_VISIBLE,
        ignoredEvent: EVENTS.IDLE_TIMEOUT_45S,
      }),
    );
    controller.destroy();
  });

  it('destroy cancels pending enterSleep timer', () => {
    const deps = createDeps();
    const controller = createLockscreenController(deps);
    expect(controller.getSnapshot().state).toBe(STATES.LOCKSCREEN_VISIBLE);

    controller.destroy();
    vi.advanceTimersByTime(300);
    expect(controller.getSnapshot().state).toBe(STATES.LOCKSCREEN_VISIBLE);
  });

  it('destroy cancels pending wakeTimeout timer', () => {
    const deps = createDeps();
    const controller = createLockscreenController(deps);
    vi.advanceTimersByTime(260);
    controller.dispatch({ type: EVENTS.USER_TAP_OR_CLICK });
    expect(controller.getSnapshot().state).toBe(STATES.WAKING);

    controller.destroy();
    vi.advanceTimersByTime(5000);
    expect(controller.getSnapshot().state).toBe(STATES.WAKING);
  });
});
