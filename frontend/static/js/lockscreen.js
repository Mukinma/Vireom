(function () {
  const lockScreen = document.getElementById('lockScreen');
  if (!lockScreen) return;

  const lockDay = document.getElementById('lockDay');
  const lockNumber = document.getElementById('lockNumber');
  const lockMonth = document.getElementById('lockMonth');
  const lockTime = document.getElementById('lockTime');
  const hint = lockScreen.querySelector('.lockscreen__hint');
  const DAYS = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
  let onTap = null;

  function updateLockClock() {
    const now = new Date();
    lockDay.textContent = DAYS[now.getDay()];
    lockNumber.textContent = now.getDate();

    const month = now.toLocaleDateString('es-ES', { month: 'long' });
    lockMonth.textContent = month.charAt(0).toUpperCase() + month.slice(1);

    const time = now.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    });
    lockTime.textContent = time.replace(/\./g, '').toUpperCase();
  }

  function isVisible() {
    return !lockScreen.classList.contains('is-dismissed');
  }

  function show() {
    lockScreen.classList.remove('is-dismissed');
  }

  function hide() {
    lockScreen.classList.add('is-dismissed');
  }

  function setHint(text) {
    if (hint) {
      hint.textContent = text || 'Toca para continuar';
    }
  }

  function handleTap(event) {
    if (!isVisible()) return;
    event.preventDefault();
    event.stopPropagation();
    if (typeof onTap === 'function') {
      onTap(event);
    }
  }

  lockScreen.addEventListener('click', handleTap);
  lockScreen.addEventListener('touchstart', handleTap, { passive: false });

  updateLockClock();
  setInterval(updateLockClock, 1000);

  window.CameraPILockscreen = {
    show,
    hide,
    isVisible,
    setHint,
    bindTap(handler) {
      onTap = typeof handler === 'function' ? handler : null;
    },
  };
})();
