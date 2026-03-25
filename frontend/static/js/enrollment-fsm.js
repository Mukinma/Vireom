/**
 * enrollment-fsm.js — Pure state machine for the guided facial enrollment flow.
 *
 * Loaded as a regular <script> in admin.html. Exposes everything via
 * window.CameraPIEnrollmentFSM. Also provides ES module exports for
 * unit testing with vitest.
 */

(function (root) {

  var STATES = {
    IDLE: 'IDLE',
    INSTRUCTIONS: 'INSTRUCTIONS',
    STEP_ACTIVE: 'STEP_ACTIVE',
    HOLDING: 'HOLDING',
    CAPTURING: 'CAPTURING',
    STEP_COMPLETE: 'STEP_COMPLETE',
    COMPLETED: 'COMPLETED',
    FACE_LOST: 'FACE_LOST',
    LOW_LIGHT: 'LOW_LIGHT',
    ERROR: 'ERROR',
  };

  var EVENTS = {
    START: 'START',
    DISMISS_INSTRUCTIONS: 'DISMISS_INSTRUCTIONS',
    BACKEND_STATUS: 'BACKEND_STATUS',
    ABORT: 'ABORT',
    RETRY: 'RETRY',
    ERROR: 'ERROR',
  };

  var EFFECTS = {
    START_POLLING: 'START_POLLING',
    STOP_POLLING: 'STOP_POLLING',
    SHOW_INSTRUCTIONS: 'SHOW_INSTRUCTIONS',
    HIDE_INSTRUCTIONS: 'HIDE_INSTRUCTIONS',
    UPDATE_OVERLAY: 'UPDATE_OVERLAY',
    UPDATE_PROGRESS: 'UPDATE_PROGRESS',
    SHOW_STEP_GUIDE: 'SHOW_STEP_GUIDE',
    SHOW_HOLD_FEEDBACK: 'SHOW_HOLD_FEEDBACK',
    SHOW_CAPTURE_FLASH: 'SHOW_CAPTURE_FLASH',
    SHOW_STEP_SUCCESS: 'SHOW_STEP_SUCCESS',
    SHOW_COMPLETION: 'SHOW_COMPLETION',
    SHOW_FACE_WARNING: 'SHOW_FACE_WARNING',
    HIDE_FACE_WARNING: 'HIDE_FACE_WARNING',
    SHOW_LIGHT_WARNING: 'SHOW_LIGHT_WARNING',
    HIDE_LIGHT_WARNING: 'HIDE_LIGHT_WARNING',
    UPDATE_MESSAGE: 'UPDATE_MESSAGE',
  };

  function createInitialContext() {
    return {
      state: STATES.IDLE,
      backendState: null,
      prevBackendState: null,
      prevStep: -1,
      prevSamplesThisStep: 0,
      effects: [],
    };
  }

  function withEffects(ctx, effects) {
    return Object.assign({}, ctx, { effects: effects });
  }

  function ignored(ctx) {
    return withEffects(ctx, []);
  }

  /**
   * Map a backend status snapshot to FSM state + effects.
   */
  function mapBackendStatus(ctx, status) {
    var effects = [EFFECTS.UPDATE_OVERLAY, EFFECTS.UPDATE_PROGRESS, EFFECTS.UPDATE_MESSAGE];
    var prevState = ctx.state;
    var prevStep = ctx.prevStep;
    var prevSamples = ctx.prevSamplesThisStep;
    var newState = ctx.state;

    var bs = status.state; // backend FSM state string

    // ── Terminal states ──
    if (bs === 'completed') {
      newState = STATES.COMPLETED;
      effects.push(EFFECTS.SHOW_COMPLETION, EFFECTS.STOP_POLLING);
      return withEffects(
        Object.assign({}, ctx, { state: newState, backendState: status, prevStep: status.current_step, prevSamplesThisStep: status.samples_this_step }),
        effects
      );
    }

    if (bs === 'error') {
      newState = STATES.ERROR;
      effects.push(EFFECTS.STOP_POLLING);
      return withEffects(
        Object.assign({}, ctx, { state: newState, backendState: status, prevStep: status.current_step, prevSamplesThisStep: status.samples_this_step }),
        effects
      );
    }

    // ── Face lost ──
    if (bs === 'face_lost') {
      newState = STATES.FACE_LOST;
      effects.push(EFFECTS.SHOW_FACE_WARNING);
      return withEffects(
        Object.assign({}, ctx, { state: newState, backendState: status, prevStep: status.current_step, prevSamplesThisStep: status.samples_this_step }),
        effects
      );
    }

    // ── Low light ──
    if (bs === 'low_light') {
      newState = STATES.LOW_LIGHT;
      effects.push(EFFECTS.SHOW_LIGHT_WARNING);
      return withEffects(
        Object.assign({}, ctx, { state: newState, backendState: status, prevStep: status.current_step, prevSamplesThisStep: status.samples_this_step }),
        effects
      );
    }

    // Clear warnings if we recovered
    if (prevState === STATES.FACE_LOST) effects.push(EFFECTS.HIDE_FACE_WARNING);
    if (prevState === STATES.LOW_LIGHT) effects.push(EFFECTS.HIDE_LIGHT_WARNING);

    // ── Step change detection ──
    if (status.current_step !== prevStep && prevStep >= 0) {
      effects.push(EFFECTS.SHOW_STEP_SUCCESS, EFFECTS.SHOW_STEP_GUIDE);
    }

    // ── Sample captured detection ──
    if (status.samples_this_step > prevSamples && status.current_step === prevStep) {
      effects.push(EFFECTS.SHOW_CAPTURE_FLASH);
    }

    // ── Map backend state to frontend state ──
    if (bs === 'holding') {
      newState = STATES.HOLDING;
      effects.push(EFFECTS.SHOW_HOLD_FEEDBACK);
    } else if (bs === 'capturing') {
      newState = STATES.CAPTURING;
    } else if (bs === 'step_complete') {
      newState = STATES.STEP_COMPLETE;
      effects.push(EFFECTS.SHOW_STEP_SUCCESS);
    } else {
      // step_active or other
      newState = STATES.STEP_ACTIVE;
      effects.push(EFFECTS.SHOW_STEP_GUIDE);
    }

    return withEffects(
      Object.assign({}, ctx, { state: newState, backendState: status, prevStep: status.current_step, prevSamplesThisStep: status.samples_this_step }),
      effects
    );
  }

  function transition(context, event) {
    var ctx = Object.assign({}, context, { effects: [] });
    var type = event && event.type;

    if (!type) return ignored(ctx);

    // ── ABORT from any state ──
    if (type === EVENTS.ABORT) {
      return withEffects(
        Object.assign({}, ctx, { state: STATES.IDLE, backendState: null, prevStep: -1, prevSamplesThisStep: 0 }),
        [EFFECTS.STOP_POLLING, EFFECTS.HIDE_FACE_WARNING, EFFECTS.HIDE_LIGHT_WARNING]
      );
    }

    // ── ERROR from any state ──
    if (type === EVENTS.ERROR) {
      return withEffects(
        Object.assign({}, ctx, { state: STATES.ERROR }),
        [EFFECTS.STOP_POLLING]
      );
    }

    // ── IDLE ──
    if (ctx.state === STATES.IDLE) {
      if (type === EVENTS.START) {
        return withEffects(
          Object.assign({}, ctx, { state: STATES.INSTRUCTIONS }),
          [EFFECTS.SHOW_INSTRUCTIONS]
        );
      }
      return ignored(ctx);
    }

    // ── INSTRUCTIONS ──
    if (ctx.state === STATES.INSTRUCTIONS) {
      if (type === EVENTS.DISMISS_INSTRUCTIONS) {
        return withEffects(
          Object.assign({}, ctx, { state: STATES.STEP_ACTIVE }),
          [EFFECTS.HIDE_INSTRUCTIONS, EFFECTS.START_POLLING, EFFECTS.SHOW_STEP_GUIDE]
        );
      }
      return ignored(ctx);
    }

    // ── Active enrollment states — driven by backend status ──
    if (type === EVENTS.BACKEND_STATUS && event.status) {
      return mapBackendStatus(ctx, event.status);
    }

    // ── RETRY ──
    if (type === EVENTS.RETRY) {
      return withEffects(
        Object.assign({}, ctx, { state: STATES.STEP_ACTIVE }),
        [EFFECTS.SHOW_STEP_GUIDE]
      );
    }

    return ignored(ctx);
  }

  // ── Expose globally ──
  var exports = {
    STATES: STATES,
    EVENTS: EVENTS,
    EFFECTS: EFFECTS,
    createInitialContext: createInitialContext,
    transition: transition,
  };

  if (typeof root !== 'undefined' && root !== null) {
    root.CameraPIEnrollmentFSM = exports;
  }

  // Support ES module re-export for vitest
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = exports;
  }

})(typeof window !== 'undefined' ? window : this);
