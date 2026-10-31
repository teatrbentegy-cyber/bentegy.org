(function () {
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // home: the ruled header slides in once the hero has scrolled away
  var hd = document.getElementById('hd');
  var hero = document.querySelector('.hero');
  if (document.body.classList.contains('home') && hd && hero) {
    var onScroll = function () { hd.classList.toggle('show', window.scrollY > hero.offsetHeight - 80); };
    window.addEventListener('scroll', onScroll, { passive: true }); onScroll();
  }

  // hero slideshow with caption and ticks
  var slides = document.querySelectorAll('.hero .slide');
  if (slides.length > 1) {
    var i = 0, n = slides.length;
    var capB = document.querySelector('#cap b');
    var capA = document.getElementById('cap');
    var ticks = document.querySelectorAll('.hero .ticks i');
    var show = function (k) {
      slides[i].classList.remove('on'); if (ticks[i]) ticks[i].classList.remove('on');
      i = k;
      slides[i].classList.add('on'); if (ticks[i]) ticks[i].classList.add('on');
      if (capB) capB.textContent = slides[i].getAttribute('data-cap') || '';
      var h = slides[i].getAttribute('data-href');
      if (capA && h) capA.setAttribute('href', h);
    };
    if (!reduce) setInterval(function () { show((i + 1) % n); }, 7000);
  }

  // close mobile menu on navigation
  document.querySelectorAll('.burger .panel a').forEach(function (a) {
    a.addEventListener('click', function () { var d = a.closest('details'); if (d) d.removeAttribute('open'); });
  });
})();

// copy boilerplate texts
document.querySelectorAll('button.copy').forEach(function (b) {
  b.addEventListener('click', function () {
    var el = document.getElementById(b.getAttribute('data-copy'));
    if (!el || !navigator.clipboard) return;
    navigator.clipboard.writeText(el.innerText.trim()).then(function () {
      var t = b.textContent; b.textContent = b.getAttribute('data-done'); b.classList.add('ok');
      setTimeout(function () { b.textContent = t; b.classList.remove('ok'); }, 1800);
    });
  });
});

// GA4 conversion events (active only when a GA4 ID is set in the admin)
document.addEventListener('click', function (ev) {
  var a = ev.target.closest && ev.target.closest('a[href]');
  if (!a || typeof window.gtag !== 'function') return;
  var h = a.getAttribute('href') || '';
  if (h.indexOf('mailto:') === 0) {
    var addr = h.slice(7).split('?')[0];
    gtag('event', 'email_click', { address: addr.split('@')[0], email: addr });
  } else if (/wayforpay\.com\/donate/.test(h)) {
    gtag('event', 'donate_click', { link_url: h });
  } else if (a.getAttribute('data-provider') || /wayforpay\.com\/payment|concert\.ua/.test(h)) {
    var pr = a.getAttribute('data-provider') || (/concert\.ua/.test(h) ? 'concertua' : 'wayforpay');
    gtag('event', 'ticket_click', { provider: pr, show: a.getAttribute('data-show') || '', link_url: h });
    if (window.BENTEGY_ADS) gtag('event', 'conversion', { send_to: window.BENTEGY_ADS.ticket });
  } else if (/t\.me\//.test(h) || /instagram\.com/.test(h)) {
    gtag('event', 'social_click', { network: /t\.me/.test(h) ? 'telegram' : 'instagram', link_url: h });
  }
});

// analytics consent banner
(function () {
  var box = document.getElementById('cookie');
  if (!box) return;
  var get = function () { try { return localStorage.getItem('bentegy-consent'); } catch (e) { return null; } };
  var set = function (v) { try { localStorage.setItem('bentegy-consent', v); } catch (e) {} };
  if (!get()) box.hidden = false;
  box.addEventListener('click', function (ev) {
    var b = ev.target.closest('[data-consent]');
    if (!b) return;
    var v = b.getAttribute('data-consent');
    set(v);
    if (typeof window.gtag === 'function') gtag('consent', 'update', { analytics_storage: v === 'yes' ? 'granted' : 'denied' });
    box.hidden = true;
  });
  document.querySelectorAll('a[href="#cookie"]').forEach(function (a) {
    a.addEventListener('click', function (ev) { ev.preventDefault(); box.hidden = false; });
  });
})();

// поява блоків і відблиск заголовків під час прокрутки
(function () {
  if (!('IntersectionObserver' in window)) return;
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  var root = document.documentElement;
  root.classList.add('rv-on');
  var sel = '.ph, .sh, .shl, .rep .c, .feat, .tc, .it, .case, .mi, .mf, .gal figure, .credits, .facts, .two, .chips, .req, .bin, .stats';
  var els = document.querySelectorAll(sel);
  var io = new IntersectionObserver(function (es) {
    es.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add('is-in'); io.unobserve(en.target); } });
  }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
  var groups = new Map();
  els.forEach(function (el) {
    if (el.closest('.hero')) return;
    el.classList.add('rv');
    var p = el.parentElement, k = groups.get(p) || 0;
    if (/(^| )(c|tc|it|mi|case)( |$)/.test(el.className) || el.tagName === 'FIGURE') { el.style.setProperty('--d', Math.min(k, 5) * 0.08 + 's'); groups.set(p, k + 1); }
    io.observe(el);
  });
  // все, що вже на екрані, — одразу
  requestAnimationFrame(function () {
    els.forEach(function (el) { var r = el.getBoundingClientRect(); if (r.top < innerHeight && r.bottom > 0) el.classList.add('is-in'); });
  });
})();
