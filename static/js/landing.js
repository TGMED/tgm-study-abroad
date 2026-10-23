// TGM landing — scroll reveal + count-up. Self-contained, no deps.
(function () {
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // ---- Reveal on scroll ----
  var reveals = document.querySelectorAll('.reveal');
  if (reduce || !('IntersectionObserver' in window)) {
    reveals.forEach(function (el) { el.classList.add('in'); });
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
      });
    }, { threshold: 0.14, rootMargin: '0px 0px -8% 0px' });
    reveals.forEach(function (el) { io.observe(el); });
  }

  // ---- Count-up stats ----
  function countUp(el) {
    var target = parseFloat(el.getAttribute('data-count')) || 0;
    var suffix = el.getAttribute('data-suffix') || '';
    if (reduce) { el.textContent = format(target) + suffix; return; }
    var dur = 1400, start = performance.now();
    function tick(now) {
      var p = Math.min((now - start) / dur, 1);
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = format(Math.round(target * eased)) + suffix;
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }
  function format(n) { return n >= 1000 ? n.toLocaleString('en-US') : String(n); }

  var nums = document.querySelectorAll('.lp-stats .num');
  if (!('IntersectionObserver' in window)) {
    nums.forEach(countUp);
  } else {
    var statIO = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { countUp(e.target); statIO.unobserve(e.target); }
      });
    }, { threshold: 0.6 });
    nums.forEach(function (el) { statIO.observe(el); });
  }
})();
