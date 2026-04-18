import { describe, it, expect, vi } from 'vitest';
import { appendCacheBuster, createFramePreviewController } from '../static/js/frame-preview.js';

function createImage() {
  const attrs = { src: '' };
  const listeners = new Map();
  return {
    setAttribute: vi.fn((name, value) => {
      attrs[name] = value;
    }),
    getAttribute: vi.fn((name) => attrs[name] || ''),
    addEventListener: vi.fn((name, handler) => {
      listeners.set(name, handler);
    }),
    removeEventListener: vi.fn((name, handler) => {
      if (listeners.get(name) === handler) {
        listeners.delete(name);
      }
    }),
    dispatch(name) {
      listeners.get(name)?.();
    },
  };
}

describe('frame preview controller', () => {
  it('adds cache busting to stream URLs', () => {
    expect(appendCacheBuster('/api/stream', 123)).toBe('/api/stream?t=123');
    expect(appendCacheBuster('/api/stream?x=1', 'wake')).toBe('/api/stream?x=1&t=wake');
  });

  it('opens a continuous stream with cache busting on resume', () => {
    const image = createImage();
    const feed = createFramePreviewController({
      imageElement: image,
      streamUrl: '/api/stream',
      nowFn: () => 10,
    });

    expect(feed.resume('initial')).toBe(true);

    expect(image.getAttribute('src')).toBe('/api/stream?t=initial-10-1');
    expect(feed.isRunning()).toBe(true);
  });

  it('pause closes the browser stream connection', () => {
    const image = createImage();
    const feed = createFramePreviewController({
      imageElement: image,
      streamUrl: '/api/stream',
      nowFn: () => 20,
    });

    feed.resume('wake');
    expect(feed.pause()).toBe(true);

    expect(image.getAttribute('src')).toBe('');
    expect(feed.isRunning()).toBe(false);
  });

  it('ensureRunning does not reopen an already active stream', () => {
    const image = createImage();
    const feed = createFramePreviewController({
      imageElement: image,
      streamUrl: '/api/stream',
      nowFn: () => 30,
    });

    feed.resume('initial');
    const activeSrc = image.getAttribute('src');

    expect(feed.ensureRunning()).toBe(false);
    expect(image.getAttribute('src')).toBe(activeSrc);
  });

  it('ensureRunning opens the stream after pause', () => {
    const image = createImage();
    const feed = createFramePreviewController({
      imageElement: image,
      streamUrl: '/api/stream',
      nowFn: () => 40,
    });

    feed.resume('initial');
    feed.pause();

    expect(feed.ensureRunning()).toBe(true);
    expect(image.getAttribute('src')).toBe('/api/stream?t=ensure-40-2');
  });

  it('reports image load errors while running', () => {
    const image = createImage();
    const onError = vi.fn();
    const feed = createFramePreviewController({ imageElement: image, onError });

    feed.resume('initial');
    image.dispatch('error');

    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError.mock.calls[0][0].message).toBe('stream_error');
  });

  it('destroy removes the image error listener', () => {
    const image = createImage();
    const feed = createFramePreviewController({ imageElement: image });

    feed.destroy();

    expect(image.removeEventListener).toHaveBeenCalledWith('error', expect.any(Function));
  });
});
