// Thank-you page after a WayForPay donation: GA4 "donation" and the Google Ads conversion, once per order.
// WayForPay returns here as /dyakuyemo-za-vnesok/?cur=UAH or /en/thank-you-donation/?cur=EUR (+ orderReference / amount when it passes them).
// Consent follows the site-wide defaults in <head>: in the EEA/UK/CH measurement waits for «Погоджуюсь».
(function () {
  var q = new URLSearchParams(location.search);
  var cur = (q.get('cur') || q.get('currency') || '').toUpperCase();
  if (cur !== 'UAH' && cur !== 'EUR') cur = document.documentElement.lang === 'en' ? 'EUR' : 'UAH';
  var value = parseFloat((q.get('amount') || '').replace(',', '.'));
  var tid = q.get('orderReference') || q.get('order') || '';
  var key = 'bentegy-donation-' + (tid || 'x');
  var sent = false;
  try { sent = sessionStorage.getItem(key) === '1'; } catch (e) {}
  function fire() {
    if (sent || typeof window.gtag !== 'function') return;
    var p = { currency: cur };
    if (value > 0) p.value = value; // the amount is free, so value goes only when WayForPay passes it
    if (tid) p.transaction_id = tid;
    window.gtag('event', 'donation', p);
    var ads = window.BENTEGY_ADS && window.BENTEGY_ADS.donation;
    if (ads) {
      var c = { send_to: ads, currency: cur };
      if (value > 0) c.value = value;
      if (tid) c.transaction_id = tid;
      window.gtag('event', 'conversion', c);
    }
    sent = true;
    try { sessionStorage.setItem(key, '1'); } catch (e) {}
  }
  if (document.readyState === 'complete') fire(); else window.addEventListener('load', fire);
})();
