import { describe, it, expect, vi } from 'vitest';
import { createLockscreenController, EVENTS, STATES } from '../static/js/lockscreen-controller.js';

function createDeps() {
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
    setTimeoutFn: (fn) => setTimeout(fn, 0),
    clearTimeoutFn: (id) => clearTimeout(id),
  };
}

describe('lockscreen controller', () => {
  it('creates wakeAttemptId when waking from sleep', () => {
    const controller = createLockscreenController(createDeps());
    controller.dispatch({ type: EVENTS.IDLE_TIMEOUT_45S });
    controller.dispatch({ type: EVENTS.ENTER_SLEEP });
    controller.dispatch({ type: EVENTS.USER_TAP_OR_CLICK });

    const snapshot = controller.getSnapshot();
    expect(snapshot.state).toBe(STATES.WAKING);
    expect(snapshot.wakeAttemptId).toBe(1);
  });

  it('ignores stale WAKE_READY from previous attempt', () => {
    const controller = createLockscreenController(createDeps());
    controller.dispatch({ type: EVENTS.IDLE_TIMEOUT_45S });
    controller.dispatch({ type: EVENTS.ENTER_SLEEP });
    controller.dispatch({ type: EVENTS.USER_TAP_OR_CLICK }); // attempt 1
    controller.dispatch({ type: EVENTS.RESUME_FAIL, wakeAttemptId: 1 });
    controller.dispatch({ type: EVENTS.USER_TAP_OR_CLICK }); // attempt 2
    controller.dispatch({ type: EVENTS.WAKE_READY, wakeAttemptId: 1 }); // stale

    const snapshot = controller.getSnapshot();
    expect(snapshot.state).toBe(STATES.WAKING);
    expect(snapshot.wakeAttemptId).toBe(2);
  });

  it('emits idle reset callback after WAKE_READY', () => {
    const onResetIdleDeadline = vi.fn();
    const controller = createLockscreenController({
      ...createDeps(),
      onResetIdleDeadline,
    });

    controller.dispatch({ type: EVENTS.IDLE_TIMEOUT_45S });
    controller.dispatch({ type: EVENTS.ENTER_SLEEP });
    controller.dispatch({ type: EVENTS.USER_TAP_OR_CLICK });
    controller.dispatch({ type: EVENTS.WAKE_READY, wakeAttemptId: 1 });

    expect(controller.getSnapshot().state).toBe(STATES.ACTIVE_UNLOCKED);
    expect(onResetIdleDeadline).toHaveBeenCalledTimes(1);
  });

  it('logTransition includes durationMs and resumeContext on WAKE_READY', () => {
    const logTransition = vi.fn();
    const controller = createLockscreenController({
      ...createDeps(),
      logTransition,
    });

    controller.dispatch({ type: EVENTS.IDLE_TIMEOUT_45S });
    controller.dispatch({ type: EVENTS.ENTER_SLEEP });
    controller.dispatch({ type: EVENTS.USER_TAP_OR_CLICK });
    controller.dispatch({ type: EVENTS.WAKE_READY, wakeAttemptId: 1 });

    const wakingToActive = logTransition.mock.calls.find(
      ([arg]) => arg.fromState === STATES.WAKING && arg.toState === STATES.ACTIVE_UNLOCKED,
    );
    expect(wakingToActive).toBeDefined();
    const [entry] = wakingToActive;
    expect(typeof entry.durationMs).toBe('number');
    expect(entry.durationMs).toBeGreaterThanOrEqual(0);
    expect(entry.resumeContext).toBe('ok');
  });

  it('logTransition includes resumeContext=resume_fail on RESUME_FAIL', () => {
    const logTransition = vi.fn();
    const controller = createLockscreenController({
      ...createDeps(),
      logTransition,
    });

    controller.dispatch({ type: EVENTS.IDLE_TIMEOUT_45S });
    controller.dispatch({ type: EVENTS.ENTER_SLEEP });
    controller.dispatch({ type: EVENTS.USER_TAP_OR_CLICK });
    controller.dispatch({ type: EVENTS.RESUME_FAIL, wakeAttemptId: 1 });

    const wakingToSleep = logTransition.mock.calls.find(
      ([arg]) => arg.fromState === STATES.WAKING && arg.toState === STATES.SLEEP_FORCED,
    );
    expect(wakingToSleep).toBeDefined();
    const [entry] = wakingToSleep;
    expect(entry.resumeContext).toBe('resume_fail');
  });

  it('logs ignored events via callback with event type', () => {
    const onIgnoredEvent = vi.fn();
    const controller = createLockscreenController({
      ...createDeps(),
      onIgnoredEvent,
    });

    controller.dispatch({ type: EVENTS.USER_TAP_OR_CLICK });
    expect(onIgnoredEvent).toHaveBeenCalledTimes(1);
    expect(onIgnoredEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        state: STATES.ACTIVE_UNLOCKED,
        ignoredEvent: EVENTS.USER_TAP_OR_CLICK,
      }),
    );
  });
});
