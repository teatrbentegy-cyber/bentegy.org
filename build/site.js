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
