(function () {
  const ROUTES = {
    // En esta app, /admin funciona como panel si hay sesión y como login si no.
    config: '/admin',
    login: '/admin',
  };

  function getAuthStateFromGlobalStore() {
    try {
      if (window.useAuthStore?.getState) {
        const state = window.useAuthStore.getState();
        return Boolean(
          state?.isAuthenticated
          || state?.session?.isAuthenticated
          || state?.token
          || state?.accessToken
        );
      }
      if (window.authStore?.getState) {
        const state = window.authStore.getState();
        return Boolean(state?.isAuthenticated || state?.token || state?.session?.active);
      }
      if (window.AuthContext?.isAuthenticated != null) {
        return Boolean(window.AuthContext.isAuthenticated);
      }
    } catch (error) {
      console.warn('No se pudo leer estado global de autenticación', error);
    }
    return null;
  }

  function hasAuthTokenInStorage() {
    const authKeyPattern = /(token|auth|session|admin_user|current_user|jwt|bearer)/i;
    const hasTokenIn = (storage) => {
      if (!storage) return false;
      const keys = Object.keys(storage);
      return keys.some((key) => {
        if (!authKeyPattern.test(key)) return false;
        const value = storage.getItem(key);
        return Boolean(value && String(value).trim() && String(value).trim() !== 'null');
      });
    };

    try {
      if (hasTokenIn(window.localStorage)) return true;
    } catch (error) {
      console.warn('No se pudo leer localStorage para auth', error);
    }

    try {
      if (hasTokenIn(window.sessionStorage)) return true;
    } catch (error) {
      console.warn('No se pudo leer sessionStorage para auth', error);
    }

    return false;
  }

  async function hasActiveAdminSession() {
    try {
      const response = await fetch('/api/config', {
        method: 'GET',
        credentials: 'same-origin',
      });
      return response.ok;
    } catch (error) {
      console.warn('No se pudo validar sesión administrativa', error);
      return false;
    }
  }

  async function isUserAuthenticated() {
    const storeState = getAuthStateFromGlobalStore();
    if (storeState !== null) {
      return storeState;
    }

    if (hasAuthTokenInStorage()) {
      return true;
    }

    return hasActiveAdminSession();
  }

  function navigate(route) {
    // Compatibilidad si el frontend migra a Next.js.
    if (window.next?.router?.push) {
      window.next.router.push(route);
      return;
    }
    window.location.assign(route);
  }

  async function handleLogoClick(event) {
    event?.preventDefault?.();
    const authenticated = await isUserAuthenticated();
    const targetRoute = authenticated ? ROUTES.config : ROUTES.login;
    navigate(targetRoute);
  }

  function bindLogoClick() {
    const logoButtons = document.querySelectorAll('.logo-clickable');
    logoButtons.forEach((button) => {
      button.addEventListener('click', handleLogoClick);
    });
  }

  window.CameraPIAuth = {
    isUserAuthenticated,
  };
  window.handleLogoClick = handleLogoClick;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindLogoClick);
  } else {
    bindLogoClick();
  }
})();
