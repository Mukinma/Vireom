(function () {
  const shell = document.getElementById('adminShell');
  if (!shell) {
    return;
  }

  const sidebar = document.getElementById('adminSidebar');
  const sidebarToggle = document.getElementById('sidebarToggle');
  const sidebarBackdrop = document.getElementById('adminSidebarBackdrop');
  const logoutFallbackForm = document.getElementById('logoutFallbackForm');
  const navLinks = Array.from(shell.querySelectorAll('.admin-sidebar [data-nav-route]'));

  const mobileMedia = window.matchMedia('(max-width: 900px)');
  const collapseMedia = window.matchMedia('(max-width: 1280px)');

  function normalizePath(pathname) {
    if (!pathname) {
      return '/';
    }

    const noQuery = pathname.split('?')[0].split('#')[0];
    if (noQuery.length > 1 && noQuery.endsWith('/')) {
      return noQuery.slice(0, -1);
    }
    return noQuery || '/';
  }

  function findActiveLink(pathname) {
    const currentPath = normalizePath(pathname);
    let bestMatch = null;

    navLinks.forEach((link) => {
      const route = normalizePath(link.getAttribute('data-nav-route'));
      const isMatch = route === '/'
        ? currentPath === '/'
        : currentPath === route || currentPath.startsWith(`${route}/`);

      if (!isMatch) {
        return;
      }

      if (!bestMatch || route.length > bestMatch.route.length) {
        bestMatch = { link, route };
      }
    });

    return bestMatch?.link || null;
  }

  function syncActiveNavByRoute() {
    const activeLink = findActiveLink(window.location.pathname);

    navLinks.forEach((link) => {
      const isActive = link === activeLink;
      link.classList.toggle('active', isActive);
      link.classList.toggle('is-active', isActive);

      if (isActive) {
        link.setAttribute('aria-current', 'page');
      } else {
        link.removeAttribute('aria-current');
      }
    });
  }

  function setSidebarInteractiveState() {
    if (!sidebar) {
      return;
    }

    const hiddenForMobile = mobileMedia.matches && !shell.classList.contains('admin-drawer-open');
    sidebar.setAttribute('aria-hidden', hiddenForMobile ? 'true' : 'false');

    if ('inert' in sidebar) {
      sidebar.inert = hiddenForMobile;
    }
  }

  function updateToggleState() {
    if (!sidebarToggle) {
      return;
    }

    const expanded = mobileMedia.matches
      ? shell.classList.contains('admin-drawer-open')
      : !shell.classList.contains('admin-sidebar-collapsed');
    sidebarToggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
  }

  function showBackdrop() {
    if (!sidebarBackdrop) {
      return;
    }

    sidebarBackdrop.classList.remove('is-hidden');
  }

  function hideBackdrop() {
    if (!sidebarBackdrop) {
      return;
    }

    sidebarBackdrop.classList.add('is-hidden');
  }

  function openDrawer() {
    if (!mobileMedia.matches) {
      return;
    }

    shell.classList.add('admin-drawer-open');
    document.body.classList.add('admin-drawer-open');
    showBackdrop();
    updateToggleState();
    setSidebarInteractiveState();
  }

  function closeDrawer() {
    shell.classList.remove('admin-drawer-open');
    document.body.classList.remove('admin-drawer-open');
    hideBackdrop();
    updateToggleState();
    setSidebarInteractiveState();
  }

  function setCollapsed(collapsed) {
    shell.classList.toggle('admin-sidebar-collapsed', collapsed);
    updateToggleState();
  }

  function applyResponsiveLayout() {
    const isMobile = mobileMedia.matches;
    shell.classList.toggle('is-mobile', isMobile);

    if (isMobile) {
      shell.classList.remove('admin-sidebar-collapsed');
      closeDrawer();
    } else {
      closeDrawer();
      setCollapsed(collapseMedia.matches);
    }

    setSidebarInteractiveState();
  }

  function toggleSidebar() {
    if (mobileMedia.matches) {
      if (shell.classList.contains('admin-drawer-open')) {
        closeDrawer();
      } else {
        openDrawer();
      }
      return;
    }

    const nextCollapsed = !shell.classList.contains('admin-sidebar-collapsed');
    setCollapsed(nextCollapsed);
  }

  function clearStoredAuthState() {
    const themeStorageKey = window.CameraPITheme?.STORAGE_KEY || 'camerapi_theme';
    const authKeyPattern = /(token|auth|session|admin_user|current_user|jwt|bearer)/i;

    try {
      const localKeys = Object.keys(localStorage);
      localKeys.forEach((key) => {
        if (key === themeStorageKey) {
          return;
        }
        if (authKeyPattern.test(key)) {
          localStorage.removeItem(key);
        }
      });
    } catch (error) {
      console.warn('No se pudo limpiar localStorage de autenticación', error);
    }

    try {
      const sessionKeys = Object.keys(sessionStorage);
      sessionKeys.forEach((key) => {
        if (authKeyPattern.test(key)) {
          sessionStorage.removeItem(key);
        }
      });
    } catch (error) {
      console.warn('No se pudo limpiar sessionStorage de autenticación', error);
    }
  }

  async function logout() {
    clearStoredAuthState();

    try {
      const response = await fetch('/auth/logout', {
        method: 'POST',
        credentials: 'same-origin',
      });

      if (!response.ok) {
        throw new Error(`logout_http_${response.status}`);
      }

      window.location.assign('/admin');
    } catch (error) {
      console.warn('Logout por fetch falló, usando fallback de formulario', error);

      if (logoutFallbackForm) {
        logoutFallbackForm.submit();
        return;
      }

      window.location.assign('/admin');
    }
  }

  sidebarToggle?.addEventListener('click', toggleSidebar);
  sidebarBackdrop?.addEventListener('click', closeDrawer);

  navLinks.forEach((link) => {
    link.addEventListener('click', () => {
      if (mobileMedia.matches) {
        closeDrawer();
      }
    });
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && shell.classList.contains('admin-drawer-open')) {
      closeDrawer();
    }
  });

  const attachMediaListener = (mediaQuery, handler) => {
    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', handler);
      return;
    }
    if (typeof mediaQuery.addListener === 'function') {
      mediaQuery.addListener(handler);
    }
  };

  attachMediaListener(mobileMedia, applyResponsiveLayout);
  attachMediaListener(collapseMedia, applyResponsiveLayout);
  window.addEventListener('popstate', syncActiveNavByRoute);

  window.logout = logout;
  window.CameraPIAdminLayout = {
    syncActiveNavByRoute,
    initResponsiveSidebar: applyResponsiveLayout,
    openDrawer,
    closeDrawer,
    toggleSidebar,
    logout,
  };

  syncActiveNavByRoute();
  applyResponsiveLayout();
})();
