(function () {
  const lockScreen = document.getElementById('lockScreen');
  if (!lockScreen) return;

  const lockDay = document.getElementById('lockDay');
  const lockNumber = document.getElementById('lockNumber');
  const lockMonth = document.getElementById('lockMonth');
  const lockTime = document.getElementById('lockTime');

  const DAYS = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];

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

  updateLockClock();
  const clockInterval = setInterval(updateLockClock, 1000);

  function dismiss() {
    lockScreen.classList.add('is-dismissed');
    clearInterval(clockInterval);

    lockScreen.removeEventListener('click', dismiss);
    lockScreen.removeEventListener('touchstart', dismiss);
    document.removeEventListener('keydown', dismiss);

    lockScreen.addEventListener('transitionend', function onEnd() {
      lockScreen.removeEventListener('transitionend', onEnd);
      lockScreen.remove();
    });
  }

  lockScreen.addEventListener('click', dismiss);
  lockScreen.addEventListener('touchstart', dismiss, { passive: true });
  document.addEventListener('keydown', dismiss);
})();
