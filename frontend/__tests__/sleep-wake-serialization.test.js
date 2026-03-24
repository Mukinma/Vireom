import { describe, it, expect, vi } from 'vitest';

/**
 * Tests the contract: resumePolling must wait for sleepPromise to settle
 * before issuing /api/kiosk/wake. This is a unit-level simulation of
 * the serialization logic extracted from app.js.
 */
describe('sleep/wake serialization', () => {
  function createSleepWakeHarness() {
    const callOrder = [];
    let sleepPromise = null;
    let sleepResolve = null;

    function pausePolling() {
      sleepPromise = new Promise((resolve) => {
        sleepResolve = resolve;
      }).then((ok) => {
        callOrder.push('sleep_settled');
        sleepPromise = null;
        return ok;
      });
      callOrder.push('sleep_fired');
      return true;
    }

    async function resumePolling() {
      if (sleepPromise) {
        callOrder.push('wake_waiting_for_sleep');
        await sleepPromise;
      }
      callOrder.push('wake_fired');
      return true;
    }

    return {
      pausePolling,
      resumePolling,
      completeSleep: (ok = true) => sleepResolve(ok),
      callOrder,
    };
  }

  it('wake waits for sleep to settle before proceeding', async () => {
    const h = createSleepWakeHarness();

    h.pausePolling();

    const wakePromise = h.resumePolling();

    expect(h.callOrder).toEqual(['sleep_fired', 'wake_waiting_for_sleep']);

    h.completeSleep(true);
    await wakePromise;

    expect(h.callOrder).toEqual([
      'sleep_fired',
      'wake_waiting_for_sleep',
      'sleep_settled',
      'wake_fired',
    ]);
  });

  it('wake fires immediately when no sleep is pending', async () => {
    const h = createSleepWakeHarness();

    await h.resumePolling();

    expect(h.callOrder).toEqual(['wake_fired']);
  });

  it('wake proceeds even if sleep failed', async () => {
    const h = createSleepWakeHarness();

    h.pausePolling();
    const wakePromise = h.resumePolling();

    h.completeSleep(false);
    await wakePromise;

    expect(h.callOrder).toEqual([
      'sleep_fired',
      'wake_waiting_for_sleep',
      'sleep_settled',
      'wake_fired',
    ]);
  });
});
