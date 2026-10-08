const counters = document.querySelectorAll('[data-target]');

const animateCounter = (el) => {
  const target = Number(el.dataset.target);
  const duration = 1200;
  const start = performance.now();

  const tick = (now) => {
    const progress = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    const current = Math.round(target * eased);
    el.textContent = current + (target >= 100 ? '%' : '');

    if (progress < 1) {
      requestAnimationFrame(tick);
    } else {
      el.textContent = target + (target >= 100 ? '%' : '');
    }
  };

  requestAnimationFrame(tick);
};

counters.forEach((counter) => {
  animateCounter(counter);
});
