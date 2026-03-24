import { describe, it, expect } from 'vitest';
import { createInitialContext, transition, STATES, EFFECTS } from '../static/js/lockscreen-fsm.js';

describe('lockscreen FSM transitions', () => {
  it('starts in LOCKSCREEN_VISIBLE with SCHEDULE_ENTER_SLEEP', () => {
    const ctx = createInitialContext();
    expect(ctx.state).toBe(STATES.LOCKSCREEN_VISIBLE);
    expect(ctx.sleepReason).toBe('boot');
    expect(ctx.effects).toContain(EFFECTS.SCHEDULE_ENTER_SLEEP);
  });

  it('moves to LOCKSCREEN_VISIBLE after IDLE_TIMEOUT_45S from ACTIVE', () => {
    const initial = createInitialContext();
    const sleeping = transition(initial, { type: 'ENTER_SLEEP' });
    const waking = transition(sleeping, { type: 'USER_TAP_OR_CLICK' });
    const active = transition(waking, { type: 'WAKE_READY', wakeAttemptId: waking.wakeAttemptId });

    const ctx = transition(active, { type: 'IDLE_TIMEOUT_45S' });
    expect(ctx.state).toBe(STATES.LOCKSCREEN_VISIBLE);
    expect(ctx.sleepReason).toBe('idle');
  });

  it('keeps ACTIVE_UNLOCKED on USER_ACTIVITY and asks for idle reset', () => {
    const initial = createInitialContext();
    const sleeping = transition(initial, { type: 'ENTER_SLEEP' });
    const waking = transition(sleeping, { type: 'USER_TAP_OR_CLICK' });
    const active = transition(waking, { type: 'WAKE_READY', wakeAttemptId: waking.wakeAttemptId });

    const ctx = transition(active, { type: 'USER_ACTIVITY' });
    expect(ctx.state).toBe(STATES.ACTIVE_UNLOCKED);
    expect(ctx.effects).toContain('RESET_IDLE_DEADLINE');
  });

  it('enters SLEEP_FORCED after ENTER_SLEEP', () => {
    const sleeping = transition(createInitialContext(), { type: 'ENTER_SLEEP' });
    expect(sleeping.state).toBe(STATES.SLEEP_FORCED);
  });

  it('waking only schedules backend wake + timeout (no early camera resume)', () => {
    const sleeping = transition(createInitialContext(), { type: 'ENTER_SLEEP' });
    const waking = transition(sleeping, { type: 'USER_TAP_OR_CLICK' });

    expect(waking.state).toBe(STATES.WAKING);
    expect(waking.effects).toContain(EFFECTS.RESUME_POLLING);
    expect(waking.effects).toContain(EFFECTS.START_WAKE_TIMEOUT);
    expect(waking.effects).not.toContain(EFFECTS.RESUME_CAMERA);
    expect(waking.effects).not.toContain(EFFECTS.RESUME_SCAN);
  });

  it('rejects WAKE_READY without wakeAttemptId (strict guard)', () => {
    const sleeping = transition(createInitialContext(), { type: 'ENTER_SLEEP' });
    const waking = transition(sleeping, { type: 'USER_TAP_OR_CLICK' });

    const result = transition(waking, { type: 'WAKE_READY' });
    expect(result.state).toBe(STATES.WAKING);
    expect(result.effects).toContain(EFFECTS.LOG_IGNORED_EVENT);
  });

  it('rejects RESUME_FAIL without wakeAttemptId (strict guard)', () => {
    const sleeping = transition(createInitialContext(), { type: 'ENTER_SLEEP' });
    const waking = transition(sleeping, { type: 'USER_TAP_OR_CLICK' });

    const result = transition(waking, { type: 'RESUME_FAIL' });
    expect(result.state).toBe(STATES.WAKING);
    expect(result.effects).toContain(EFFECTS.LOG_IGNORED_EVENT);
  });
});
