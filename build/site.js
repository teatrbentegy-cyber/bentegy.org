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
  var sel = '.rep .c, .gal figure';
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

// колір проступає плямами, як фарба з лінориту: ч/б → колір при наведенні (на телефоні — коли фото на екрані)
(function () {
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  var NS = 'http://www.w3.org/2000/svg';
  var sel = '.cover, .rep .im, .pw .im, .gal figure, .pc .im, .pp, .series .im, .feat .im, .mf .im, .tc .im, .mn .im, .proc figure, .prog';
  var hover = window.matchMedia && window.matchMedia('(hover: hover)').matches;
  var uid = 0;
  function setup(box) {
    var im = box.querySelector('img');
    if (!im || box.__ink) return null;
    var r = im.getBoundingClientRect();
    var br = box.getBoundingClientRect();
    if (!r.width || !r.height) return null;
    var w = Math.round(r.width), h = Math.round(r.height), id = 'ink' + (++uid);
    var svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('class', 'ink'); svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h); svg.setAttribute('aria-hidden', 'true');
    svg.style.left = (r.left - br.left) + 'px'; svg.style.top = (r.top - br.top) + 'px';
    svg.style.width = w + 'px'; svg.style.height = h + 'px';
    var seed = Math.floor(Math.random() * 90) + 1;
    svg.innerHTML = '<defs><filter id="' + id + 'f" x="-20%" y="-20%" width="140%" height="140%"><feTurbulence type="fractalNoise" baseFrequency="' + (12 / Math.max(w, 300)).toFixed(4) + '" numOctaves="3" seed="' + seed + '" result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="' + Math.round(Math.max(w, h) * 0.08) + '" xChannelSelector="R" yChannelSelector="G"/></filter>' +
      '<mask id="' + id + 'm" maskUnits="userSpaceOnUse" x="0" y="0" width="' + w + '" height="' + h + '"><g filter="url(#' + id + 'f)" fill="#fff"></g></mask></defs>' +
      '<image href="' + (im.currentSrc || im.src) + '" x="0" y="0" width="' + w + '" height="' + h + '" preserveAspectRatio="xMidYMid slice" mask="url(#' + id + 'm)"/>';
    var g = svg.querySelector('g');
    var blobs = [], n = 7 + Math.floor(Math.random() * 6), D = Math.hypot(w, h);
    for (var i = 0; i < n; i++) {
      var c = document.createElementNS(NS, 'circle');
      c.setAttribute('cx', Math.random() * w); c.setAttribute('cy', Math.random() * h); c.setAttribute('r', 0);
      g.appendChild(c);
      blobs.push({ c: c, delay: Math.random() * 1.1, speed: D * (0.12 + Math.random() * 0.16), max: D * (0.3 + Math.random() * 0.3), r: 0 });
    }
    if (getComputedStyle(box).position === 'static') box.style.position = 'relative';
    box.appendChild(svg); box.classList.add('ink-on');
    var st = { t: 0, dir: 0, raf: 0, last: 0 };
    function frame(ts) {
      var dt = st.last ? (ts - st.last) / 1000 : 0; st.last = ts;
      st.t = Math.max(0, st.t + dt * (st.dir > 0 ? 1 : -1.6));
      var alive = false;
      blobs.forEach(function (b) {
        var k = Math.max(0, st.t - b.delay);
        b.r = Math.min(b.max, k * b.speed); b.c.setAttribute('r', b.r.toFixed(1));
        if (st.dir > 0 ? b.r < b.max : b.r > 0) alive = true;
      });
      if (alive) st.raf = requestAnimationFrame(frame); else { st.raf = 0; st.last = 0; }
    }
    box.__ink = function (dir) { st.dir = dir; if (!st.raf) { st.last = 0; st.raf = requestAnimationFrame(frame); } };
    return box.__ink;
  }
  var boxes = document.querySelectorAll(sel);
  if (hover) {
    boxes.forEach(function (box) {
      var host = box.closest('a') || box;
      host.addEventListener('mouseenter', function () { var f = box.__ink || setup(box); if (f) f(1); });
      host.addEventListener('mouseleave', function () { if (box.__ink) box.__ink(-1); });
    });
  } else if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (en) {
        var box = en.target;
        if (en.isIntersecting && en.intersectionRatio > 0.55) { var f = box.__ink || setup(box); if (f) f(1); }
        else if (!en.isIntersecting && box.__ink) box.__ink(-1);
      });
    }, { threshold: [0, 0.6] });
    boxes.forEach(function (b) { io.observe(b); });
  }
})();
