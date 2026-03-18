(function () {
  'use strict';

  const tips = [
    'Mantén la mirada al frente y evita moverte durante el escaneo',
    'Si usas lentes, asegúrate de que no generen reflejos en la cámara',
    'La iluminación uniforme en tu rostro mejora la precisión del sistema',
    'Evita cubrir tu rostro con gorras, bufandas o cubrebocas',
    'Colócate a una distancia de entre 40 y 80 cm de la cámara',
    'El sistema funciona mejor con expresiones neutras y naturales',
    'Asegúrate de que tu rostro esté completamente dentro de la guía',
    'Evita fondos muy iluminados detrás de ti, generan contraluz',
    'Si el sistema no te reconoce, intenta ajustar tu posición',
    'Un rostro bien iluminado de frente se reconoce en menos de 1 segundo',
    'El reconocimiento es más preciso cuando ambos ojos son visibles',
    'Registra varias muestras desde distintos ángulos para mejor precisión',
  ];

  const INTERVAL_MS = 6000;
  const FADE_OUT_MS = 350;

  function shuffleArray(arr) {
    const a = arr.slice();
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  function initCarousel(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return null;

    const textEl = container.querySelector('.tips-carousel__text');
    if (!textEl) return null;

    const indicatorsContainer = container.querySelector('.tips-carousel__indicators');

    let queue = shuffleArray(tips);
    let index = 0;
    let indicatorEls = [];

    if (indicatorsContainer) {
      indicatorsContainer.innerHTML = '';
      for (let i = 0; i < queue.length; i++) {
        const dot = document.createElement('div');
        dot.className = 'tips-carousel__indicator';
        indicatorsContainer.appendChild(dot);
        indicatorEls.push(dot);
      }
    }

    function showNext() {
      if (index >= queue.length) {
        queue = shuffleArray(tips);
        index = 0;
      }

      textEl.style.opacity = '0';
      textEl.style.transform = 'translateY(5px)';

      setTimeout(() => {
        textEl.textContent = queue[index];

        if (indicatorEls.length > 0) {
          indicatorEls.forEach((el, i) => {
            el.classList.toggle('is-active', i === index);
          });
        }

        textEl.style.opacity = '';
        textEl.style.transform = '';
        textEl.style.animation = 'none';
        void textEl.offsetHeight;
        textEl.style.animation = '';
        index++;
      }, FADE_OUT_MS);
    }

    showNext();
    const timer = setInterval(showNext, INTERVAL_MS);
    return timer;
  }

  const prefersReduced = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;
  const interval = prefersReduced ? INTERVAL_MS * 2 : INTERVAL_MS;

  initCarousel('tipsCarouselCamera');
  initCarousel('tipsCarouselPanel');
})();
