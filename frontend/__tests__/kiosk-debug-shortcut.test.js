import { describe, it, expect } from 'vitest';
import { shouldTriggerDebugShortcut } from '../static/js/lockscreen-controller.js';

describe('debug shortcut detection', () => {
  it('accepts Ctrl+Shift+L', () => {
    const event = { key: 'L', ctrlKey: true, metaKey: false, shiftKey: true };
    expect(shouldTriggerDebugShortcut(event)).toBe(true);
  });

  it('accepts Cmd+Shift+L', () => {
    const event = { key: 'l', ctrlKey: false, metaKey: true, shiftKey: true };
    expect(shouldTriggerDebugShortcut(event)).toBe(true);
  });

  it('rejects other key combinations', () => {
    const event = { key: 'k', ctrlKey: true, metaKey: false, shiftKey: true };
    expect(shouldTriggerDebugShortcut(event)).toBe(false);
  });
});
