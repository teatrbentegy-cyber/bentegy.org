// Thank-you page after WayForPay payment: shows the performance, calendar links, sends GA4 "purchase".
(function () {
  var q = new URLSearchParams(location.search);
  var shows = window.BENTEGY_SHOWS || {};
  var slug = q.get('show') || q.get('item') || '';
  var s = shows[slug];
  if (!s) { // try to recognise the production from WayForPay order reference / product name
    var hint = (q.get('orderReference') || q.get('productName') || '').toLowerCase().replace(/[^a-z]/g, '');
    Object.keys(shows).forEach(function (k) { if (!s && hint && hint.indexOf(k.replace(/[^a-z]/g, '')) === 0) { s = shows[k]; slug = k; } });
  }
  var box = document.getElementById('thx-show');
  if (s && s.start && box) {
    document.getElementById('thx-title').textContent = s.title;
    document.getElementById('thx-when').textContent = s.when;
    document.getElementById('thx-venue').textContent = s.venue + (s.city ? ', ' + s.city : '');
    var st = new Date(s.start), en = new Date(st.getTime() + (s.mins || 90) * 60000);
    var f = function (d) { return d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, ''); };
    var dates = s.has_time ? f(st) + '/' + f(en) : s.start.replace(/-/g, '') + '/' + s.start.replace(/-/g, '');
    var where = s.venue + (s.city ? ', ' + s.city : '');
    var link = location.origin + s.url;
    document.getElementById('thx-gcal').href = 'https://calendar.google.com/calendar/render?action=TEMPLATE&text=' + encodeURIComponent(s.title) +
      '&dates=' + dates + '&location=' + encodeURIComponent(where) + '&details=' + encodeURIComponent(link);
    var ics = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Bentegy//UA', 'BEGIN:VEVENT', 'UID:' + slug + '-' + dates + '@bentegy.org',
      'DTSTAMP:' + f(new Date()), s.has_time ? 'DTSTART:' + f(st) : 'DTSTART;VALUE=DATE:' + s.start.replace(/-/g, ''),
      s.has_time ? 'DTEND:' + f(en) : 'DTEND;VALUE=DATE:' + s.start.replace(/-/g, ''),
      'SUMMARY:' + s.title, 'LOCATION:' + where.replace(/,/g, '\\,'), 'URL:' + link, 'END:VEVENT', 'END:VCALENDAR'].join('\r\n');
    document.getElementById('thx-ics').href = 'data:text/calendar;charset=utf-8,' + encodeURIComponent(ics);
    box.hidden = false;
  }
  // GA4 purchase (once per order)
  var tid = q.get('orderReference') || q.get('order') || '';
  var amount = parseFloat(q.get('amount') || '') || (s && s.price) || 0;
  var key = 'bentegy-purchase-' + (tid || slug || 'x');
  var sent = false;
  try { sent = sessionStorage.getItem(key) === '1'; } catch (e) {}
  function fire() {
    if (sent || typeof window.gtag !== 'function') return;
    var p = { currency: q.get('currency') || 'UAH', value: amount, items: [{ item_id: slug || 'ticket', item_name: s ? s.title : 'Квиток', price: amount, quantity: 1 }] };
    if (tid) p.transaction_id = tid;
    window.gtag('event', 'purchase', p);
    if (window.BENTEGY_ADS) window.gtag('event', 'conversion', { send_to: window.BENTEGY_ADS.purchase, value: amount, currency: p.currency, transaction_id: tid });
    sent = true;
    try { sessionStorage.setItem(key, '1'); } catch (e) {}
  }
  if (document.readyState === 'complete') fire(); else window.addEventListener('load', fire);
})();
