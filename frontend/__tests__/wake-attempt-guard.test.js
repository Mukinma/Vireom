import { describe, it, expect } from 'vitest';
import { isCurrentWakeAttempt } from '../static/js/wake-attempt-guard.js';

describe('wake attempt guard', () => {
  it('returns true only for matching WAKING attempt', () => {
    const ok = isCurrentWakeAttempt({ state: 'WAKING', wakeAttemptId: 3 }, 3);
    expect(ok).toBe(true);
  });

  it('returns false when attempt id is stale', () => {
    const stale = isCurrentWakeAttempt({ state: 'WAKING', wakeAttemptId: 4 }, 3);
    expect(stale).toBe(false);
  });

  it('returns false when state is no longer WAKING', () => {
    const staleState = isCurrentWakeAttempt({ state: 'SLEEP_FORCED', wakeAttemptId: 3 }, 3);
    expect(staleState).toBe(false);
  });

  it('stale fail must not pass guard (regression: late error from attempt 1 while attempt 2 is active)', () => {
    const attempt2Active = { state: 'WAKING', wakeAttemptId: 2 };
    const staleAttempt1 = 1;

    const shouldAct = isCurrentWakeAttempt(attempt2Active, staleAttempt1);
    expect(shouldAct).toBe(false);
  });
});
