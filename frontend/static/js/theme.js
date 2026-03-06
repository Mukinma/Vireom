(function () {
  const STORAGE_KEY = 'camerapi_theme';
  const THEMES = ['theme-light', 'theme-dark'];

  function normalizeTheme(theme) {
    return THEMES.includes(theme) ? theme : null;
  }

  function getPreferredTheme() {
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    return prefersDark ? 'theme-dark' : 'theme-light';
  }

  function getCurrentTheme() {
    const root = document.documentElement;
    return root.classList.contains('theme-dark') ? 'theme-dark' : 'theme-light';
  }

  function setThemeAttributes(theme) {
    const isDark = theme === 'theme-dark';
    const label = isDark ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro';

    document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
      button.setAttribute('aria-label', label);
      button.setAttribute('aria-pressed', isDark ? 'true' : 'false');
      button.dataset.theme = isDark ? 'dark' : 'light';
    });

    document.querySelectorAll('[data-theme-logo]').forEach((logo) => {
      const lightSrc = logo.dataset.logoLight;
      const darkSrc = logo.dataset.logoDark;
      const nextSrc = isDark ? darkSrc : lightSrc;
      if (nextSrc) {
        logo.setAttribute('src', nextSrc);
      }
    });
  }

  function applyTheme(theme, options = {}) {
    const { persist = true } = options;
    const normalized = normalizeTheme(theme) || getPreferredTheme();
    const root = document.documentElement;

    root.classList.remove(...THEMES);
    root.classList.add(normalized);

    if (persist) {
      try {
        localStorage.setItem(STORAGE_KEY, normalized);
      } catch (error) {
        console.warn('No se pudo persistir el tema', error);
      }
    }

    setThemeAttributes(normalized);
    return normalized;
  }

  function initTheme() {
    let savedTheme = null;

    try {
      savedTheme = normalizeTheme(localStorage.getItem(STORAGE_KEY));
    } catch (error) {
      console.warn('No se pudo leer el tema persistido', error);
    }

    applyTheme(savedTheme || getPreferredTheme(), { persist: false });
  }

  function toggleTheme() {
    const nextTheme = getCurrentTheme() === 'theme-dark' ? 'theme-light' : 'theme-dark';
    return applyTheme(nextTheme, { persist: true });
  }

  function bindToggleButtons() {
    document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
      if (button.dataset.themeBound === 'true') {
        return;
      }

      button.dataset.themeBound = 'true';
      button.addEventListener('click', () => {
        toggleTheme();
      });
    });

    setThemeAttributes(getCurrentTheme());
  }

  function bootstrap() {
    initTheme();
    bindToggleButtons();
  }

  window.CameraPITheme = {
    STORAGE_KEY,
    initTheme,
    applyTheme,
    toggleTheme,
    bindToggleButtons,
    getCurrentTheme,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootstrap, { once: true });
  } else {
    bootstrap();
  }
})();
