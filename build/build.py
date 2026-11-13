#!/usr/bin/env python3
"""Builds bentegy.org from content/*.yml into public/.
Run: python3 build/build.py   (needs: pyyaml, markdown, pillow)"""
import datetime as dt
import glob
import html
import os
import sys
import urllib.parse
import re
import shutil

import markdown as md
import yaml
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "public")
SITE = "https://bentegy.org"
TODAY = dt.date.today()
e = html.escape


def load(p):
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


SETTINGS = load(f"{ROOT}/content/site.yml")
ABOUT = load(f"{ROOT}/content/pages/about.yml")
PRODUCER = load(f"{ROOT}/content/pages/producer.yml")
SUPPORT = load(f"{ROOT}/content/pages/support.yml")
PRESS = load(f"{ROOT}/content/pages/press.yml")
PRODUCTIONS = []
for p in sorted(glob.glob(f"{ROOT}/content/productions/*.yml")):
    d = load(p)
    d["slug"] = os.path.splitext(os.path.basename(p))[0]
    PRODUCTIONS.append(d)
PRODUCTIONS.sort(key=lambda d: (d.get("order") or 99, d["slug"]))
BY_SLUG = {p["slug"]: p for p in PRODUCTIONS}
EVENTS = []
for p in sorted(glob.glob(f"{ROOT}/content/events/*.yml")):
    d = load(p)
    if not d.get("date"):
        continue
    if isinstance(d["date"], str):
        d["date"] = dt.date.fromisoformat(d["date"])
    if d["date"] >= TODAY or d.get("date_note_uk"):
        EVENTS.append(d)
EVENTS.sort(key=lambda d: (d["date"], str(d.get("time") or "")))

EXTRA = os.environ.get("BENTEGY_EXTRA")  # optional folder with demo media/ and team/ (local previews only)


def load_dir(name):
    out = []
    for base in [f"{ROOT}/content"] + ([EXTRA] if EXTRA else []):
        for p in sorted(glob.glob(f"{base}/{name}/*.yml")):
            d = load(p)
            d["slug"] = os.path.splitext(os.path.basename(p))[0]
            out.append(d)
    return out


MEDIA = []
for d in load_dir("media"):
    if d.get("draft") or d.get("hidden") or not d.get("date") or not (d.get("title_uk") or d.get("title_en")):
        continue
    if isinstance(d["date"], str):
        d["date"] = dt.date.fromisoformat(d["date"][:10])
    elif isinstance(d["date"], dt.datetime):
        d["date"] = d["date"].date()
    d["type"] = d.get("type") if d.get("type") in ("text", "news", "release", "article") else "text"
    MEDIA.append(d)
MEDIA.sort(key=lambda d: (d["date"], d["slug"]), reverse=True)
# Розділ «Медіа» можна тимчасово сховати (site.yml → media_enabled: false): сторінки не збираються, посилання зникають
MEDIA_ALL = MEDIA
if SETTINGS.get("media_enabled") is False:
    MEDIA = []
GROUP_ORDER = {"team": 0, "collab": 1, "authors": 2}
# Показуємо лише людей з іменем: порожні ролі без імені виглядали б як заглушки
PROCESS = []
for d in load_dir("process"):
    if d.get("draft") or not d.get("date"):
        continue
    if isinstance(d["date"], str):
        d["date"] = dt.date.fromisoformat(d["date"][:10])
    PROCESS.append(d)
PROCESS.sort(key=lambda d: (d["date"], d["slug"]), reverse=True)

TEAM = [d for d in load_dir("team") if d.get("name_uk") or d.get("name_en")]
TEAM.sort(key=lambda d: (GROUP_ORDER.get(d.get("group") or "team", 3), d.get("order") or 99, d.get("name_uk") or ""))
TEAM_BY = {d["slug"]: d for d in TEAM}

# ------------------------------------------------------------------ i18n
MONTHS = {
    "uk": ["січня", "лютого", "березня", "квітня", "травня", "червня", "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
}
MONTHS_NOM = {
    "uk": ["Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень", "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень"],
    "en": MONTHS["en"],
}
DOW = {"uk": ["понеділок", "вівторок", "середа", "четвер", "пʼятниця", "субота", "неділя"],
       "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]}

R = {  # routes: key -> (uk, en)
    "home": ("/", "/en/"),
    "afisha": ("/afisha/", "/en/schedule/"),
    "shows": ("/vystavy/", "/en/productions/"),
    "producer": ("/prodiuser/", "/en/producer/"),
    "about": ("/pro-teatr/", "/en/about/"),
    "org": ("/orhanizatsiia/", "/en/organisation/"),
    "contact": ("/kontakty/", "/en/contact/"),
    "support": ("/pidtrymaty/", "/en/support/"),
    "press": ("/presa/", "/en/press/"),
    "media": ("/media/", "/en/media/"),
    "team": ("/komanda/", "/en/team/"),
    "process": ("/protses/", "/en/process/"),
}
MTYPE = {  # media type -> (uk path, en path, uk label, en label, uk singular, en singular)
    "text": ("teksty", "texts", "Критичні тексти та есеї", "Essays and criticism", "Текст", "Essay"),
    "article": ("publikatsii", "coverage", "Публікації", "Coverage", "Публікація", "Coverage"),
    "release": ("presrelizy", "press-releases", "Пресрелізи", "Press releases", "Пресреліз", "Press release"),
    "news": ("novyny", "news", "Новини", "News", "Новина", "News"),
}
NAV = ["afisha", "shows", "process", "media", "about", "contact"]
FOOT = ["support", "press", "producer"]
T = {
    "uk": dict(name="Театр Бентеги", nav=dict(afisha="Афіша", shows="Вистави", process="Процес", producer="Продюсер", about="Про театр", org="Організація", contact="Контакти", support="Підтримати", press="Преса", media="Медіа", team="Команда"),
               tickets="Квитки", menu="Меню", skip="До змісту", other="EN", soon="Продаж скоро", free="Вхід вільний", sold="Квитки продано",
               all_dates="Уся афіша", all_shows="Усі вистави", next="Найближчі покази", repertoire="Репертуар", produced="Продюсування",
               upcoming_tag="Прем'єра скоро", produced_tag="За продюсування Бентег", nodates="Нові дати зʼявляться найближчим часом. Стежте за анонсами в Instagram і Telegram.",
               genre="Жанр", premiere="Прем'єра", duration="Тривалість", age="Вік", credits="Команда", dates="Дати показів", photos="Фото",
               producer_cta="Співпраця з продюсером", about_producer="Засновник і продюсер", read_more="Детальніше", time="Час",
               legal="Діє через Громадську організацію «В РЕСУРСІ» | код ЄДРПОУ 44977435", sections="Розділи", connect="Звʼязок", org_h="Організація"),
    "en": dict(name="Bentegy Theatre", nav=dict(afisha="Schedule", process="Process", shows="Productions", producer="Producer", about="About", org="Organisation", contact="Contact", support="Support us", press="Press", media="Media", team="Team"),
               tickets="Tickets", menu="Menu", skip="Skip to content", other="UA", soon="On sale soon", free="Free entry", sold="Sold out",
               all_dates="Full schedule", all_shows="All productions", next="Coming up", repertoire="Repertoire", produced="Produced by Bentegy",
               upcoming_tag="Premiering soon", produced_tag="Bentegy production", nodates="New dates will be announced soon. Follow us on Instagram and Telegram.",
               genre="Form", premiere="Premiere", duration="Running time", age="Age rating", credits="Credits", dates="Dates", photos="Photos",
               producer_cta="Work with the producer", about_producer="Founder and producer", read_more="Read more", time="Time",
               legal="Operated by NGO “In the Resource” | EDRPOU 44977435", sections="Sections", connect="Contact", org_h="Organisation"),
}


_FALLBACK_WARNED = set()


def L(d, key, lang):
    """Localised field with fallback to the other language."""
    v = d.get(f"{key}_{lang}")
    if not v:
        v = d.get(f"{key}_{'en' if lang == 'uk' else 'uk'}") or ""
        if v and lang == "en" and key in ("body", "description", "lead", "title", "summary"):
            k = (d.get("slug") or id(d), key)
            if k not in _FALLBACK_WARNED:
                _FALLBACK_WARNED.add(k)
                print(f"warning: no {key}_en for {d.get('slug') or '?'}; the English page falls back to Ukrainian", file=sys.stderr)
    return v


def url(key, lang):
    return R[key][0 if lang == "uk" else 1]


def show_url(slug, lang):
    return f"{url('shows', lang)}{slug}/"


def loc_href(u, lang):
    """Map an internal Ukrainian path (e.g. /vystavy/slug/) to its English equivalent on /en/ pages."""
    if lang == "uk" or not u or not u.startswith("/") or u.startswith("/en/"):
        return u
    for uk_path, en_path in sorted(R.values(), key=lambda x: -len(x[0])):
        if uk_path != "/" and u.startswith(uk_path):
            return en_path + u[len(uk_path):]
    return url("home", lang) if u == "/" else u


def bi(text, lang):
    """«Українською / English» → потрібна мовна частина."""
    t = str(text or "")
    if " / " in t:
        a, b = t.split(" / ", 1)
        return a.strip() if lang == "uk" else b.strip()
    return t


def mdh(text):
    return md.markdown(text or "")


def media_url(slug, lang):
    return f"{url('media', lang)}{slug}/"


def mtype_url(tp, lang):
    return f"{url('media', lang)}{MTYPE[tp][0 if lang == 'uk' else 1]}/"


def fdate(d, lang):
    return f"{d.day} {MONTHS[lang][d.month - 1]} {d.year}"


def visible_nav():
    return [k for k in NAV if not (k == "media" and not MEDIA)]


# ------------------------------------------------------------------ images
SIZES = (800, 1200, 1600, 2400)
IMG_DONE = {}


def process_images():
    os.makedirs(f"{OUT}/img", exist_ok=True)
    for src in glob.glob(f"{ROOT}/static/uploads/*"):
        stem, ext = os.path.splitext(os.path.basename(src))
        if ext.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
            continue
        im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
        w, h = im.size
        made = []
        for s in SIZES:
            if s > w and made:
                break
            r = im if w <= s else im.resize((s, round(h * s / w)), Image.LANCZOS)
            r.save(f"{OUT}/img/{stem}-{s}.jpg", "JPEG", quality=85, optimize=True, progressive=True)
            r.save(f"{OUT}/img/{stem}-{s}.webp", "WEBP", quality=80, method=6)  # швидкість (PageSpeed): WebP ~30% легший
            made.append((s, r.size))
        IMG_DONE[f"/uploads/{stem}{ext}"] = (stem, made, (w, h))


def img(path, alt="", sizes="100vw", cls="", eager=False):
    if not path or path not in IMG_DONE:
        return ""
    stem, made, (w, h) = IMG_DONE[path]
    srcset = ", ".join(f"/img/{stem}-{s}.jpg {sz[0]}w" for s, sz in made)
    mid = made[min(1, len(made) - 1)][0]
    load = 'fetchpriority="high"' if eager else 'loading="lazy" decoding="async"'
    c = f' class="{cls}"' if cls else ""
    webp = ", ".join(f"/img/{stem}-{s}.webp {sz[0]}w" for s, sz in made)
    return (f'<picture><source type="image/webp" srcset="{webp}" sizes="{sizes}">'
            f'<img{c} src="/img/{stem}-{mid}.jpg" srcset="{srcset}" sizes="{sizes}" width="{w}" height="{h}" alt="{e(alt)}" {load}></picture>')


def img_url(path, size=1600):
    if path in IMG_DONE:
        stem, made, _ = IMG_DONE[path]
        s = max([m[0] for m in made if m[0] <= size] or [made[0][0]])
        return f"/img/{stem}-{s}.jpg"
    return ""


# ------------------------------------------------------------------ share images (Open Graph)
OG_DONE = {}


def _og_font(size, latin):
    sub = "latin" if latin else "cyrillic"
    return ImageFont.truetype(f"{ROOT}/static/fonts/inter-tight-{sub}-900-normal.woff2", size)


def _og_draw_text(draw, xy, text, size, fill, track=-0.045):
    """Draw text char by char, picking the Cyrillic or Latin subset font."""
    x, y = xy
    fc, fl = _og_font(size, False), _og_font(size, True)
    for ch in text:
        f = fc if 0x0400 <= ord(ch) <= 0x052F else fl
        draw.text((x, y), ch, font=f, fill=fill)
        x += f.getlength(ch) + size * track
    return x


def _og_width(text, size):
    fc, fl = _og_font(size, False), _og_font(size, True)
    return sum((fc if 0x0400 <= ord(ch) <= 0x052F else fl).getlength(ch) - size * 0.045 for ch in text)


def _og_lines(text, size, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if _og_width(t, size) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def og_image(key, photo, title, label):
    """1200x630 share image: B&W stage photo, dark gradient, giant title with a red dot."""
    W, H, pad = 1200, 630, 56
    if photo and os.path.exists(f"{ROOT}/static{photo}"):
        im = ImageOps.exif_transpose(Image.open(f"{ROOT}/static{photo}")).convert("L")
        im = ImageOps.fit(im, (W, H), Image.LANCZOS, centering=(0.5, 0.45))
        im = ImageOps.autocontrast(im, cutoff=1).convert("RGB")
    else:
        im = Image.new("RGB", (W, H), (0, 0, 0))
    grad = Image.linear_gradient("L").resize((W, H))
    shade = Image.new("RGB", (W, H), (0, 0, 0))
    im = Image.composite(shade, im, grad.point(lambda v: int(v * 0.92)))
    top = Image.linear_gradient("L").rotate(180).resize((W, 200)).point(lambda v: int(v * 0.5))
    im.paste(shade.crop((0, 0, W, 200)), (0, 0), top)
    d = ImageDraw.Draw(im)
    mk = Image.open(f"{ROOT}/static/brand/mark.png").convert("RGBA")
    mk.thumbnail((76, 76))
    im.paste(mk, (pad, pad), mk)
    text = title.upper()
    size = 132
    while size > 56:
        lines = _og_lines(text, size, W - 2 * pad - size * 0.4)
        if len(lines) <= 2:
            break
        size -= 8
    lh = size * 0.86
    y = H - pad - lh * len(lines) - 8
    d.rectangle((pad, y - 26, W - pad, y - 22), fill=(255, 255, 255))
    _og_draw_text(d, (pad, y - 64), label.upper(), 24, (220, 220, 220), track=0.08)
    for i, ln in enumerate(lines):
        x = _og_draw_text(d, (pad, y + i * lh - size * 0.18), ln, size, (255, 255, 255))
    d.text((x - size * 0.03, y + (len(lines) - 1) * lh - size * 0.18), ".", font=_og_font(size, True), fill=(179, 18, 12))
    os.makedirs(f"{OUT}/og", exist_ok=True)
    im.save(f"{OUT}/og/{key}.jpg", quality=86, optimize=True, progressive=True)
    OG_DONE[key] = f"/og/{key}.jpg"
    return OG_DONE[key]


def make_og_images():
    hero = (SETTINGS.get("hero") or [{}])[0].get("image")
    og_image("bentegy-uk", hero, "Бентеги", "Незалежний театр | Київ")
    og_image("bentegy-en", hero, "Bentegy", "Independent theatre | Kyiv")
    for p in PRODUCTIONS:
        pic = p.get("cover") or next((g["image"] for g in (p.get("gallery") or [])), None)
        og_image(f"{p['slug']}-uk", pic, L(p, "title", "uk"), "Театр Бентеги")
        og_image(f"{p['slug']}-en", pic, L(p, "title", "en"), "Bentegy Theatre")


# ------------------------------------------------------------------ structured data (schema.org)
import json
from zoneinfo import ZoneInfo


def ld_tag(data):
    if not data:
        return ""
    return '\n<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False).replace("</", "<\\/") + "</script>"


def ld_org(lang):
    c = SETTINGS["contacts"]
    o = SETTINGS["organization"]
    return {
        "@context": "https://schema.org", "@type": "TheaterGroup",
        "name": T[lang]["name"], "alternateName": ["Театр Бентеги", "Bentegy Theatre", "Бентеги"],
        "url": SITE + url("home", lang), "logo": SITE + "/press/bentegy-znak.png",
        "image": SITE + OG_DONE.get(f"bentegy-{lang}", ""), "description": L(SETTINGS, "tagline", lang) if lang == "uk" else L(ABOUT, "lead", lang),
        "email": c.get("theatre") or c["team"], "telephone": c["phone"].replace(" ", ""),
        "contactPoint": [{"@type": "ContactPoint", "contactType": ct, "email": em} for ct, em in (("customer support", c.get("theatre")), ("partnerships", c.get("team")), ("press", c.get("press"))) if em],
        "address": {"@type": "PostalAddress", "addressLocality": "Kyiv", "addressCountry": "UA"},
        "foundingDate": "2025", "founder": {"@type": "Person", "name": L(PRODUCER, "name", lang)},
        "sameAs": [x for x in (c["instagram"], c["telegram"], c.get("youtube")) if x],
        "parentOrganization": {"@type": "NGO", "name": L(o, "name", lang), "taxID": o["edrpou"]},
    }


def concert_url(ev):
    u = (ev.get("concert_url") or "").strip()
    if not u:
        return ""
    sep = "&" if "?" in u else "?"
    return f"{u}{sep}utm_source=bentegy&utm_medium=site&utm_campaign={ev.get('production') or 'bentegy'}"


def provider(u):
    u = (u or "").lower()
    return "wayforpay" if "wayforpay" in u else "concertua" if "concert.ua" in u else "other"


def ev_start(ev):
    """(datetime with Kyiv tz or date, has_time)"""
    if ev.get("time"):
        try:
            hh, mm = [int(x) for x in str(ev["time"]).split(":")[:2]]
            return dt.datetime(ev["date"].year, ev["date"].month, ev["date"].day, hh, mm, tzinfo=ZoneInfo(ev.get("timezone") or "Europe/Kyiv")), True
        except ValueError:
            pass
    return ev["date"], False


def duration_min(p):
    """Running time in minutes from "1 год 30 хв" / "55–65 хв" / "1 h 30 min"; interval notes and non-time numbers are ignored."""
    s = (p.get("duration_uk") or p.get("duration_en") or "").split("|")[0]
    s = re.split(r"з перерв|with an? \d*-?\s*min interval|with an interval|\(", s)[0]
    h = re.search(r"(\d+)\s*(?:год|h\b)", s)
    m = re.findall(r"(\d+)\s*(?:хв|min)", s)
    if h or m:
        return (int(h.group(1)) * 60 if h else 0) + (max(int(x) for x in m) if m else 0)
    nums = [int(x) for x in re.findall(r"\d+(?=[–-]\d+\s*(?:хв|min))", s)]
    return max(nums) if nums else 0


def venue_parts(ev, lang):
    v = L(ev, "venue", lang)
    if ev.get("street_address") is False:  # venue line has no street (e.g. "Theatre, Gallery"): keep it whole as the place name
        return v.strip(), ""
    name, _, street = v.partition(",")
    return name.strip(), (L(ev, "address", lang) or street).strip()


def ld_event(ev, lang):
    if ev.get("date_note_uk") or ev.get("date_note_en"):
        return None
    p = BY_SLUG.get(ev.get("production"), {})
    st, has_time = ev_start(ev)
    start = st.isoformat()
    mins = duration_min(p)
    end = (st + dt.timedelta(minutes=mins)).isoformat() if has_time and mins else start
    vname, street = venue_parts(ev, lang)
    theatre = {"@type": "PerformingGroup", "name": T[lang]["name"], "url": SITE}
    perf = {"@type": "PerformingGroup", "name": L(p, "performer", lang), "url": SITE + show_url(p["slug"], lang)} if p and L(p, "performer", lang) else theatre
    d = {
        "@context": "https://schema.org", "@type": "TheaterEvent",
        "name": L(p, "title", lang) or L(ev, "title", lang), "startDate": start, "endDate": end,
        "eventStatus": "https://schema.org/EventScheduled",
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "location": {"@type": "Place", "name": vname or L(ev, "venue", lang),
                     "address": {"@type": "PostalAddress", **({"streetAddress": street} if street else {}), "addressLocality": L(ev, "city", lang), "addressCountry": ev.get("country") or "UA"}},
        "organizer": theatre, "performer": perf,
        "description": L(p, "summary", lang),
        "inLanguage": lang,
    }
    if p:
        d["url"] = SITE + show_url(p["slug"], lang)
        ims = [SITE + x for x in (img_url(p.get("cover"), 1600), OG_DONE.get(f"{p['slug']}-{lang}")) if x]
        if ims:
            d["image"] = ims
    buy = ev.get("ticket_url") or concert_url(ev)
    if buy and ev.get("price"):
        vf = ev.get("sale_start") or (ev["date"] - dt.timedelta(days=30))
        d["offers"] = {"@type": "Offer", "url": buy, "price": str(ev["price"]), "priceCurrency": "UAH",
                       "validFrom": vf.isoformat() if hasattr(vf, "isoformat") else str(vf),
                       "availability": "https://schema.org/SoldOut" if ev.get("status") == "sold_out" else "https://schema.org/InStock"}
    return d


def ld_events(evs, lang):
    return [x for x in (ld_event(ev, lang) for ev in evs) if x]


def ld_production(p, evs, lang):
    return ld_events(evs, lang) or None


# ------------------------------------------------------------------ layout
def other(lang):
    return "en" if lang == "uk" else "uk"


def nav_links(lang, key):
    t = T[lang]
    return "".join(f'<a href="{url(k, lang)}"{" aria-current=page" if k == key else ""}>{t["nav"][k]}</a>' for k in visible_nav())


def analytics():
    out = ""
    ga = (SETTINGS.get("ga4") or "").strip()
    aw = (SETTINGS.get("google_ads") or "").strip()  # Google Ads (Ad Grants) conversions
    if ga:
        eea = "AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE IS LI NO GB CH".split()
        out += (f'\n<!-- Google tag (gtag.js): loaded after page load so it does not delay rendering (PageSpeed) -->'
                f'\n<script>addEventListener("load",function(){{setTimeout(function(){{var s=document.createElement("script");s.async=1;s.src="https://www.googletagmanager.com/gtag/js?id={e(ga)}";document.head.appendChild(s)}},1500)}});</script>'
                "\n<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}"
                f"gtag('consent','default',{{ad_storage:'denied',ad_user_data:'denied',ad_personalization:'denied',analytics_storage:'denied',region:{eea!r}}});"
                "gtag('consent','default',{ad_storage:'denied',ad_user_data:'denied',ad_personalization:'denied',analytics_storage:'granted'});"
                "try{var c=localStorage.getItem('bentegy-consent');if(c)gtag('consent','update',{analytics_storage:c==='yes'?'granted':'denied'});}catch(e){}"
                f"gtag('js',new Date());gtag('config','{e(ga)}');"
                + (f"gtag('config','{e(aw)}');window.BENTEGY_ADS={{purchase:'{e(aw)}/{e(SETTINGS.get('ads_conv_purchase') or '')}',ticket:'{e(aw)}/{e(SETTINGS.get('ads_conv_ticket') or '')}'}};" if aw else "")
                + "</script>")
    code = (SETTINGS.get("goatcounter") or "").strip()
    if code:
        out += f'\n<script data-goatcounter="https://{e(code)}.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>'
    return out


def extra_links(lang, key):
    t = T[lang]
    return "".join(f'<a class="sm" href="{url(k, lang)}"{" aria-current=page" if k == key else ""}>{t["nav"][k]}</a>' for k in ("support", "press", "producer") if k not in visible_nav())


def _min_css(css):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"\s*([{}:;,>])\s*", r"\1", css)
    return css.replace(";}", "}").strip()


# Увесь CSS вбудовано в <head>: прибирає запит, що блокує показ сторінки (PageSpeed, мобільний)
CSS_INLINE = _min_css(open(f"{ROOT}/build/fonts.css", encoding="utf-8").read() + open(f"{ROOT}/build/main.css", encoding="utf-8").read() + "picture{display:contents}")


def short_desc(t, n=158):
    t = " ".join(str(t or "").split())
    if len(t) <= n:
        return t
    cut = t[:n].rsplit(" ", 1)[0].rstrip(",;:—–- ")
    if "." in cut[n // 2:]:
        return cut[:cut.rindex(".") + 1]
    return cut + "…"


def head(lang, key, title, desc, paths, body_cls="", og="", ld=None, noindex=False):
    t = T[lang]
    o = other(lang)
    _tl = L(SETTINGS, 'tagline', lang).split('.')[0]
    full = f"{t['name']} — {_tl[:1].lower()}{_tl[1:]}" if key == "home" and not title else f"{title} — {t['name']}"
    if len(full) > 65:  # довгі заголовки (пресрелізи, есеї): без назви театру, обрізаємо по слову
        full = title
        if len(full) > 65:
            cut = max(full.rfind(" — ", 0, 65), full.rfind(": ", 0, 65))
            full = full[:cut] if cut >= 30 else full[:62].rsplit(" ", 1)[0].rstrip(":,—–- ") + "…"
    og_img = SITE + (og or OG_DONE.get(f"bentegy-{lang}", ""))
    nav = nav_links(lang, key)
    return f"""<!doctype html>
<html lang="{lang}">
<head>{analytics()}
<meta charset="utf-8">{'<meta name="robots" content="noindex,nofollow">' if noindex else ''}
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{e(full)}</title>
<meta name="description" content="{e(short_desc(desc))}">
<link rel="canonical" href="{SITE}{paths[0]}">
<link rel="alternate" hreflang="{lang}" href="{SITE}{paths[0]}">
<link rel="alternate" hreflang="{o}" href="{SITE}{paths[1]}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{t['name']}">
<meta property="og:title" content="{e(full)}">
<meta property="og:description" content="{e(short_desc(desc, 200))}">
<meta property="og:image" content="{og_img}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:url" content="{SITE}{paths[0]}">
<meta property="og:locale" content="{'uk_UA' if lang == 'uk' else 'en_GB'}">
<meta name="twitter:card" content="summary_large_image">{ld_tag(ld)}
<meta name="theme-color" content="#000000">
<link rel="icon" href="/brand/favicon.png" type="image/png">
<link rel="apple-touch-icon" href="/brand/apple-touch-icon.png">
<link rel="preload" href="/fonts/inter-tight-cyrillic-900-normal.woff2" as="font" type="font/woff2" crossorigin>
<style>{CSS_INLINE}</style>
</head>
<body class="{body_cls}">
<a class="skip" href="#main">{t['skip']}</a>
<header class="hd" id="hd"><div class="in gut max">
  <a class="mk" href="{url('home', lang)}" aria-label="{t['name']}"><img src="/brand/mark-solid.png" alt="" width="40" height="39"><span class="wm">{'Театр Бентеги' if lang == 'uk' else 'Bentegy Theatre'}</span></a>
  <nav aria-label="{t['menu']}">{nav}</nav>
  <a class="sup" href="{url('support', lang)}"{" aria-current=page" if key == 'support' else ""}>{t['nav']['support']}</a>
  <a class="lg" href="{paths[1]}" hreflang="{o}" lang="{o}">{t['other']}</a>
  <details class="burger"><summary>{t['menu']}</summary><div class="panel">{nav}{extra_links(lang, key)}
    <div class="row"><a href="{paths[1]}" hreflang="{o}" lang="{o}">{'English' if lang == 'uk' else 'Українська'}</a><a class="tix" href="{url('afisha', lang)}">{t['tickets']}</a></div></div></details>
  <a class="tix" href="{url('afisha', lang)}">{t['tickets']}</a>
</div></header>
<main id="main">
"""


def foot(lang):
    t = T[lang]
    c = SETTINGS["contacts"]
    o = SETTINGS["organization"]
    links = "".join(f'<li><a href="{url(k, lang)}">{t["nav"][k]}</a></li>' for k in visible_nav() + [x for x in FOOT if x not in visible_nav()])
    yt_li = f'<li><a href="{c["youtube"]}">YouTube</a></li>' if c.get("youtube") else ""
    return f"""</main>
<footer class="ft gut max">
  <p class="word" aria-hidden="true">{'Бентеги' if lang == 'uk' else 'Bentegy'}<span class="dot">.</span></p>
  <div class="cols">
    <div><h4>{t['sections']}</h4><ul>{links}</ul></div>
    <div><h4>{t['connect']}</h4><ul>
      <li><small>{'Театр' if lang == 'uk' else 'Theatre'}</small><a href="mailto:{c.get('theatre') or c['team']}">{c.get('theatre') or c['team']}</a></li>
      <li><small>{'Співпраця й команда' if lang == 'uk' else 'Partnerships'}</small><a href="mailto:{c['team']}">{c['team']}</a></li>
      <li><small>{'Преса' if lang == 'uk' else 'Press'}</small><a href="mailto:{c['press']}">{c['press']}</a></li>
      <li><small>{'Продюсер' if lang == 'uk' else 'Producer'}</small><a href="mailto:{c['producer']}">{c['producer']}</a></li>
      <li><small>{'Телефон' if lang == 'uk' else 'Phone'}</small><a href="tel:{c['phone'].replace(' ', '')}">{c['phone']}</a></li></ul></div>
    <div><h4>{'Соцмережі' if lang == 'uk' else 'Follow'}</h4><ul>
      <li><a href="{c['instagram']}">Instagram</a></li>
      <li><a href="{c['telegram']}">Telegram</a></li>{yt_li}</ul></div>
    <div><h4>{t['org_h']}</h4><ul>
      <li>{e(L(o, 'name', lang))}</li>
      <li>{'Код ЄДРПОУ' if lang == 'uk' else 'EDRPOU'} {o['edrpou']}</li>
      <li><a href="{url('about', lang) + '#organisation'}">{'Реквізити і документи' if lang == 'uk' else 'Details and documents'}</a></li></ul></div>
  </div>
  <div class="legal"><span>© {TODAY.year} {t['name']} | <a href="{url('privacy', lang)}">{'Політика конфіденційності' if lang == 'uk' else 'Privacy policy'}</a></span><span>{t['legal']}</span></div>
</footer>
{consent_banner(lang)}
<script src="/site.js" defer></script>
</body>
</html>
"""


def consent_banner(lang):
    if not (SETTINGS.get("ga4") or "").strip():
        return ""
    uk = lang == "uk"
    return f"""<div class="cookie" id="cookie" hidden role="dialog" aria-label="{'Згода на аналітику' if uk else 'Analytics consent'}"><p>{'Ми рахуємо відвідування через Google Analytics і вимірюємо ефективність реклами через Google Ads, щоб краще планувати покази. Дані знеособлені.' if uk else 'We count visits with Google Analytics and measure our ads with Google Ads to plan our performances better. We only see aggregated statistics.'} <a href="{url('privacy', lang)}">{'Детальніше' if uk else 'Details'}</a></p>
<div><button type="button" class="tix" data-consent="yes">{'Погоджуюсь' if uk else 'Accept'}</button><button type="button" class="tbo" data-consent="no">{'Лише необхідне' if uk else 'Essential only'}</button></div></div>"""


def page_head(title, lead="", small=False):
    lp = f'<div class="lead"><p>{e(lead)}</p></div>' if lead else ""
    st = ' style="font-size:clamp(44px,11.6vw,220px)"' if small else ""
    return f'<header class="ph gut max"><h1{st}>{e(title)}<span class="dot">.</span></h1>{lp}</header>'


# ------------------------------------------------------------------ fragments
def date_block(ev, lang):
    if ev.get(f"date_note_{lang}"):
        return f'<div class="d">{e(MONTHS_NOM[lang][ev["date"].month - 1])}<small>{e(L(ev, "date_note", lang))}</small></div>'
    d = ev["date"]
    tm = f", {ev['time']}" if ev.get("time") else ""
    return f'<div class="d">{d.day:02d}.{d.month:02d}<small>{DOW[lang][d.weekday()]}{tm}</small></div>'


def cta(ev, lang):
    t = T[lang]
    st = ev.get("status") or "soon"
    if st == "sold_out":
        return f'<span class="ghost">{t["sold"]}</span>'
    if st == "free":
        if ev.get("ticket_url"):
            return f'<a class="tix" href="{e(ev["ticket_url"])}" target="_blank" rel="noopener">{"Реєстрація" if lang == "uk" else "Register"}</a>'
        return f'<span class="ghost">{t["free"]}</span>'
    if st == "info":
        if ev.get("info_url"):
            return f'<a class="tbo" href="{e(ev["info_url"])}" target="_blank" rel="noopener">{e(L(ev, "cta_note", lang))}</a>'
        return f'<span class="ghost">{e(L(ev, "cta_note", lang))}</span>'
    if ev.get("ticket_url"):
        op = f'<small>{e(ev["ticket_operator"])}</small>' if ev.get("ticket_operator") else ""
        return f'<a class="tix" href="{e(ev["ticket_url"])}" target="_blank" rel="noopener" data-provider="{provider(ev["ticket_url"])}" data-show="{e(ev.get("production") or "")}">{t["tickets"]}</a>{op}'
    return f'<span class="ghost">{t["soon"]}</span>'


def event_row(ev, lang, show_title=True):
    p = BY_SLUG.get(ev.get("production"), {})
    title = L(p, "title", lang) or L(ev, "title", lang)
    tt = f'<a href="{show_url(p["slug"], lang)}">{e(title)}</a>' if p else e(title)
    lab = f'<span class="lab">{e(L(ev, "label", lang))}</span>' if L(ev, "label", lang) else ""
    return f"""<article class="it"><div class="dcol">{date_block(ev, lang)}{lab}</div>
  <div><h3>{tt}</h3></div>
  <div class="w"><b>{e(L(ev, 'venue', lang))}</b>{e(L(ev, 'city', lang))}</div>
  <div class="act">{cta(ev, lang)}</div></article>"""


def schedule(events, lang, group=True):
    if not events:
        return f'<p class="empty">{T[lang]["nodates"]}</p>'
    out, cur = [], None
    for ev in events:
        k = (ev["date"].year, ev["date"].month)
        if group and k != cur:
            cur = k
            out.append(f'<h2 class="month"><b>{MONTHS_NOM[lang][k[1] - 1]}</b><span>{k[0]}</span></h2>')
        out.append(event_row(ev, lang))
    return "\n".join(out)


def upcoming_tag(p, lang):
    """"Прем'єра 11 грудня" once a date is set, otherwise the generic "Прем'єра скоро"."""
    nxt = [ev for ev in EVENTS if ev.get("production") == p.get("slug")]
    if nxt:
        d = nxt[0]["date"]
        return (f"Прем'єра {d.day} {MONTHS['uk'][d.month - 1]}" if lang == "uk" else f"Premiere {d.day} {MONTHS['en'][d.month - 1]}")
    return T[lang]["upcoming_tag"]


def card(p, lang):
    t = T[lang]
    tag = ""
    if p.get("status") == "upcoming":
        tag = f'<span class="tag">{upcoming_tag(p, lang)}</span>'
    elif p.get("status") == "produced":
        tag = f'<span class="tag o">{t["produced_tag"]}</span>'
    elif p.get("status") == "development":
        tag = f'<span class="tag o">{"В розробці" if lang == "uk" else "In development"}</span>'
    elif p.get("status") == "event":
        tag = f'<span class="tag o">{"Подія" if lang == "uk" else "Event"}{" | " + str(p["year"]) if p.get("year") else ""}</span>'
    elif p.get("status") == "archive":
        tag = f'<span class="tag o">{"Архів" if lang == "uk" else "Archive"}{" | " + str(p["year"]) if p.get("year") else ""}</span>'
    pic = img(p.get("cover"), L(p, "title", lang), "(max-width:760px) 100vw, 58vw") or f'<span class="ty">{e(L(p, "title", lang))}</span>'
    return f"""<a class="c" href="{show_url(p['slug'], lang)}"><div class="im">{pic}</div>
  <div class="cap"><h3>{e(L(p, 'title', lang))}</h3><span>{e(L(p, 'hook', lang) or L(p, 'genre', lang))}</span></div>{tag}</a>"""


# ------------------------------------------------------------------ pages
def process_strip(lang, top0=False):
    items = ABOUT.get("process") or []
    if not items:
        return ""
    uk = lang == "uk"
    figs = "".join(f'<figure>{img(x["image"], L(x, "caption", lang), "(max-width:760px) 50vw, 25vw")}<figcaption>{e(L(x, "caption", lang))}</figcaption></figure>' for x in items)
    cr = bi(ABOUT.get("process_credit", ""), lang)
    st = ' style="padding-top:0"' if top0 else ''
    intro = ("Репетиції, читки, пошук мізансцени: як вистави Бентег стають виставами." if uk else "Rehearsals, table reads, blocking: how Bentegy productions take shape.")
    return f"""<section class="sec gut max"{st}><div class="sh"><h2>{'Процес' if uk else 'Process'}</h2></div>
  <p class="mu" style="max-width:62ch;margin-top:18px">{intro}</p>
  <div class="proc">{figs}</div>{f'<p class="credit-line">{e(cr)}</p>' if cr else ''}</section>"""


def process_card(n, lang):
    p = BY_SLUG.get(n.get("production"), {})
    d = n["date"]
    meta = " | ".join(x for x in (L(n, "kind", lang), f"{d.day:02d}.{d.month:02d}.{d.year}", L(n, "place", lang)) if x)
    title = L(p, "title", lang) or L(n, "title", lang)
    href = show_url(p["slug"], lang) if p else url("process", lang)
    pic = img(n.get("image"), title, "(max-width:760px) 100vw, 33vw") or '<span class="pmk"><img src="/brand/mark-solid.png" alt="" width="80" height="78"></span>'
    return f'<a class="pc" href="{href}"><div class="im">{pic}</div><p class="mono">{e(meta)}</p><h3>{e(title)}</h3><p>{e(L(n, "text", lang))}</p></a>'


def process_block(items, lang, home=False):
    if not items:
        return ""
    uk = lang == "uk"
    more = f'<a class="more" href="{url("process", lang)}">{"Увесь процес" if uk else "All process notes"}</a>' if home else ""
    title = ("Зараз у процесі" if uk else "Work in progress") if home else ("Нотатки" if uk else "Notes")
    return f'<section class="sec gut max"><div class="sh"><h2>{title}</h2>{more}</div><div class="proc3">{"".join(process_card(n, lang) for n in items)}</div></section>'


def series_block(lang):
    p = BY_SLUG.get("naoslip")
    if not p:
        return ""
    uk = lang == "uk"
    return f"""<section class="sec gut max"><div class="sh"><h2>{'Серія' if uk else 'Series'}</h2><a class="more" href="{show_url('naoslip', lang)}">{'Про НАОСЛІП' if uk else 'About NAOSLIP'}</a></div>
  <a class="series" href="{show_url('naoslip', lang)}"><div class="im">{img(p.get('cover'), L(p, 'title', lang), "(max-width:860px) 100vw, 58vw")}</div>
  <div><p class="mono">{'Вечір незалежного театру | 07.08.2026 | КультМотив, Київ' if uk else 'An evening of independent theatre | 07.08.2026 | KultMotyv, Kyiv'}</p><h3>{e(L(p, 'title', lang))}</h3><p>{e(L(p, 'summary', lang))}</p></div></a></section>"""


def people_block(lang):
    core = [x for x in TEAM if (x.get("group") or "team") == "team" and x.get("photo")]
    if not core:
        return ""
    uk = lang == "uk"
    cards = "".join(f'<a class="pp" href="{url("about", lang)}#{x["slug"]}">{img(x.get("photo"), L(x, "name", lang), "(max-width:760px) 50vw, 20vw")}<b>{e(L(x, "name", lang))}</b><span class="mono">{e(L(x, "role", lang))}</span></a>' for x in core)
    return f'<section class="sec gut max"><div class="sh"><h2>{"Люди" if uk else "People"}</h2><a class="more" href="{url("about", lang)}#team">{"Команда" if uk else "Team"}</a></div><div class="people5">{cards}</div></section>'


def partners_block(lang):
    ps = SETTINGS.get("partners", [])
    if not ps:
        return ""
    uk = lang == "uk"
    return f'<section class="sec gut max" style="padding-top:0"><div class="sh"><h2>{"Партнери" if uk else "Partners"}</h2></div><div class="plist">{"".join(f"<span>{e(bi(x, lang))}</span>" for x in ps)}</div></section>'


def page_process(lang):
    uk = lang == "uk"
    lead = ("Що відбувається всередині театру: репетиції, резиденції, нові версії вистав і проєкти в розробці." if uk
            else "What is happening inside the theatre: rehearsals, residencies, new versions of productions and work in development.")
    title = T[lang]["nav"]["process"]
    body = page_head(title, lead) + f'<section class="gut max" style="padding-bottom:clamp(60px,8vw,120px)"><div class="proc3">{"".join(process_card(n, lang) for n in PROCESS)}</div></section>'
    return head(lang, "process", title, lead, (url("process", lang), url("process", other(lang)))) + body + foot(lang)


def page_home(lang):
    t = T[lang]
    o = other(lang)
    hero = SETTINGS.get("hero", [])
    slides = "".join(
        f'<figure class="slide{" on" if i == 0 else ""}"{f' style="--pos:{e(s["pos"])}"' if s.get("pos") else ""} data-cap="{e(L(s, "caption", lang))}" data-href="{e(loc_href(s.get("link") or "", lang))}">{img(s["image"], L(s, "caption", lang), "100vw", eager=(i == 0))}</figure>'
        for i, s in enumerate(hero))
    first = hero[0] if hero else {}
    ticks = "".join(f'<i{" class=on" if i == 0 else ""}></i>' for i in range(len(hero))) if len(hero) > 1 else ""
    hv = visible_nav()
    hmenu = "".join(f'<a href="{url(k, lang)}">{t["nav"][k]}</a>' for k in hv)
    # на головній — лише вистави з фото: репертуар, далі продюсування
    rep = ([p for p in PRODUCTIONS if p.get("status") in ("repertoire", "upcoming") and p.get("cover")] + [p for p in PRODUCTIONS if p.get("status") == "produced" and p.get("cover")])[:4]
    pr = PRODUCER
    uk = lang == "uk"
    org = SETTINGS["organization"]
    who = f"""
<section class="sec gut max">
  <div class="sh"><h2>{'Хто ми' if uk else 'Who we are'}</h2><a class="more" href="{url('about', lang)}">{'Про театр' if uk else 'About us'}</a></div>
  <div class="two"><span></span><div>
    <p class="big-lead">{e(L(ABOUT, 'lead', lang))}</p>
  </div></div>
</section>"""
    tix_note = (f"Театр Бентеги працює як неприбуткова {e(org['name_uk'][:1].lower() + org['name_uk'][1:])}: кошти від квитків і внесків ідуть на статутну діяльність — нові вистави, гонорари команди, покази й гастролі."
                if uk else
                "Bentegy Theatre operates through the non-profit In the Resource NGO: income from tickets and donations supports its statutory work: new productions, fair pay for the team, performances and touring.")
    body = f"""
<section class="hero" aria-label="{t['name']}">
  {slides}
  <div class="top gut"><a class="mkb" href="{url('home', lang)}" aria-label="{t['name']}"><img src="/brand/mark-solid.png" alt="" width="56" height="55"></a>
    <a class="lg" href="{url('home', o)}" hreflang="{o}" lang="{o}">{t['other']}</a><a class="tix" href="{url('afisha', lang)}">{t['tickets']}</a></div>
  <div class="poster gut">
    <div class="now"><p>{e(L(SETTINGS, 'tagline', lang))}</p>
      <a class="cap" id="cap" href="{e(loc_href(first.get('link') or '', lang) or url('shows', lang))}">{'На фото' if lang == 'uk' else 'Pictured'}<b>{e(L(first, 'caption', lang))}</b><span class="ticks" aria-hidden="true">{ticks}</span></a></div>
    <h1 class="vh">{t['name']}</h1><p class="word" aria-hidden="true">{'Бентеги' if lang == 'uk' else 'Bentegy'}<span class="dot">.</span></p>
    <nav class="hmenu" aria-label="{t['menu']}" style="--n:{len(hv)}">{hmenu}</nav>
  </div>
</section>
<section class="sec gut max">
  <div class="sh"><h2>{t['nav']['afisha']}</h2><a class="more" href="{url('afisha', lang)}">{t['all_dates']}</a></div>
  {schedule(EVENTS[:5], lang, group=False)}
</section>
{process_block(PROCESS[:3], lang, home=True)}
<section class="sec gut max">
  <div class="sh"><h2>{t['nav']['shows']}</h2><a class="more" href="{url('shows', lang)}">{t['all_shows']}</a></div>
  <div class="rep">{''.join(card(p, lang) for p in rep)}</div>
</section>
{series_block(lang)}
{people_block(lang)}
{who}
{media_strip(([m for m in MEDIA if m["type"] in ("text", "article")] + [m for m in MEDIA if m["type"] not in ("text", "article")])[:3], lang, t['nav']['media'], url('media', lang), 'Усе з медіа' if lang == 'uk' else 'All media') if MEDIA else ''}
{partners_block(lang)}
<section class="band gut max"><div class="bin">
  <h2>{'Ваш вихід' if lang == 'uk' else 'Your cue'}<span class="dot">.</span></h2>
  <div><p>{'Кожна прем’єра Бентег починається задовго до першого глядача — з людей, які повірили в неї раніше за всіх. Ваш внесок стає репетиціями, світлом і новою виставою в Києві.' if lang == 'uk' else 'Every Bentegy premiere begins long before the first audience, with the people who believed in it first. Your gift becomes rehearsals, light on stage and a new production in Kyiv.'}</p>
    <div class="bact"><a class="tix big" href="{url('support', lang)}">{'Підтримати прем’єру' if lang == 'uk' else 'Back a premiere'}</a>
    <a class="go" href="{url('contact', lang)}">{'Стати партнером' if lang == 'uk' else 'Become a partner'}</a></div></div>
</div></section>
"""
    return head(lang, "home", "", L(ABOUT, "lead", lang), (url("home", lang), url("home", o)), "home", ld=[ld_org(lang)] + ld_events(EVENTS, lang)) + body + foot(lang)


def page_afisha(lang):
    t = T[lang]
    intro = ("Усі найближчі покази Театру Бентеги та вистав, які ми продюсуємо. Квитки продаються через різних операторів, кнопка біля кожної дати веде на потрібний сайт. Кошти від квитків ідуть на статутну діяльність неприбуткової ГО «В РЕСУРСІ»: нові вистави, гонорари команди й покази."
             if lang == "uk" else
             "All upcoming performances by Bentegy Theatre and the productions we produce. Tickets are sold through different operators; the button next to each date takes you to the right one. Ticket income supports the work of our non-profit, In the Resource: new productions, fair pay for the team, and performances.")
    body = page_head(t["nav"]["afisha"], intro) + f'<section class="gut max" style="padding-bottom:clamp(40px,6vw,80px)">{schedule(EVENTS, lang)}</section>'
    return head(lang, "afisha", t["nav"]["afisha"], intro, (url("afisha", lang), url("afisha", other(lang))), ld=ld_events(EVENTS, lang) or None) + body + foot(lang)


def page_shows(lang):
    t = T[lang]
    rep = [p for p in PRODUCTIONS if p.get("status") in ("repertoire", "upcoming")]
    prod = [p for p in PRODUCTIONS if p.get("status") == "produced"]
    arch = [p for p in PRODUCTIONS if p.get("status") == "archive"]
    dev = [p for p in PRODUCTIONS if p.get("status") == "development"]
    evp = [p for p in PRODUCTIONS if p.get("status") == "event"]
    intro = ("Вистави, які ми створюємо й продюсуємо: моновистава в стилі фізичного театру, вечір у справжньому барі, танець без жодного слова, ритуал, гра."
             if lang == "uk" else
             "Productions we make and produce: a physical-theatre solo, an evening in a working bar, wordless dance, a ritual, a game.")

    def sec(title, items):
        if not items:
            return ""
        return f'<section class="gut max shg"><div class="shl"><h2>{title}</h2><span>{len(items):02d}</span></div><div class="rep">{"".join(card(p, lang) for p in items)}</div></section>'
    body = page_head(t["nav"]["shows"], intro) + '<div class="shgs">' + sec("Вистави" if lang == "uk" else "Productions", rep + arch) + sec(t["produced"], prod) + sec("В розробці" if lang == "uk" else "In development", dev) + sec("Події" if lang == "uk" else "Events", evp) + '</div>' 
    return head(lang, "shows", t["nav"]["shows"], intro, (url("shows", lang), url("shows", other(lang)))) + body + foot(lang)


def page_show(p, lang):
    t = T[lang]
    title = L(p, "title", lang)
    kick = []
    if p.get("status") == "upcoming":
        kick.append(f'<span class="tag">{upcoming_tag(p, lang)}</span>')
    elif p.get("status") == "produced":
        kick.append(f'<span class="tag">{t["produced_tag"]}</span>')
    elif p.get("status") == "development":
        kick.append(f'<span class="tag">{"В розробці" if lang == "uk" else "In development"}</span>')
    elif p.get("status") == "event":
        kick.append(f'<span class="tag">{"Подія" if lang == "uk" else "Event"}</span>')
    elif p.get("status") == "archive":
        kick.append(f'<span class="tag">{"Архів" if lang == "uk" else "Archive"}{" | " + str(p["year"]) if p.get("year") else ""}</span>')
    if L(p, "genre", lang):
        kick.append(f"<span>{e(L(p, 'genre', lang))}</span>")
    kick_h = f'<p class="kick">{"".join(kick)}</p>' if kick else ""
    cover = p.get("cover")
    if cover and cover in IMG_DONE:
        cp = f' style="--cp:{e(p["cover_pos"])}"' if p.get("cover_pos") else ""
        top = f'<section class="cover"{cp}>{img(cover, title, "100vw", eager=True)}<div class="in gut max">{kick_h}<h1>{e(title)}</h1><p class="sum">{e(L(p, "summary", lang))}</p></div></section>'
    else:
        top = f'<header class="notitle gut max">{kick_h}<h1>{e(title)}</h1><p class="sum">{e(L(p, "summary", lang))}</p></header>'
    nxt = [ev for ev in EVENTS if ev.get("production") == p["slug"] and not ev.get(f"date_note_{lang}")]
    tixbox = ticket_box(nxt[0], p, lang, len(nxt)) if nxt else ""
    is_ev = p.get("status") == "event"
    facts = [(("Формат" if lang == "uk" else "Format") if is_ev else t["genre"], L(p, "genre", lang)), (("Дата і місце" if lang == "uk" else "Date and venue") if is_ev else t["premiere"], L(p, "premiere", lang)), (("Масштаб" if lang == "uk" else "At a glance") if is_ev else t["duration"], L(p, "duration", lang)), (t["age"], p.get("age") or "")]
    facts_h = "".join(f"<div><dt>{a}</dt><dd>{e(b)}</dd></div>" for a, b in facts if b)
    evs = [ev for ev in EVENTS if ev.get("production") == p["slug"]]
    credits = "".join(f"<dt>{e(L(c, 'role', lang))}</dt><dd>{e(c.get(f'names_{lang}') or c.get('names', ''))}</dd>" for c in (p.get("credits") or []))
    gal_items = []
    for g in (p.get("gallery") or []):
        cap = L(g, "caption", lang)
        fc = f"<figcaption>{e(cap)}</figcaption>" if cap else ""
        _d = IMG_DONE.get(g["image"])
        _v = ' class="v"' if _d and _d[2][1] > _d[2][0] else ''
        gal_items.append(f'<figure{_v}>{img(g["image"], cap or title, "(max-width:640px) 100vw, 50vw")}{fc}</figure>')
    pc = f'<p class="credit-line">{"Фото" if lang == "uk" else "Photo"}: {e(bi(p.get("photo_credit"), lang))}</p>' if p.get("photo_credit") else ""
    body = f"""{top}
{tixbox}
<div class="gut max"><dl class="facts">{facts_h}</dl></div>
<section class="sec gut max"><div class="sh"><h2>{('Про подію' if is_ev else 'Про виставу') if lang == 'uk' else 'About'}</h2></div>
  <div class="two"><span></span><div class="prose">{mdh(L(p, 'description', lang))}</div></div></section>
{f'<section class="sec gut max" style="padding-top:0"><div class="sh"><h2>{"Історія проєкту" if lang == "uk" else "The story so far"}</h2></div><div class="two"><span></span><div class="prose">{mdh(L(p, "history", lang))}</div></div></section>' if L(p, "history", lang) else ''}
{show_quotes(p, lang)}
{'' if not evs and p.get('status') not in ('repertoire', 'upcoming') else f"""<section class="sec gut max" id="dates" style="padding-top:0"><div class="sh"><h2>{t['dates']}</h2><a class="more" href="{url('afisha', lang)}">{t['all_dates']}</a></div>{schedule(evs, lang, group=False)}</section>"""}
{f'<section class="sec gut max" style="padding-top:0"><div class="sh"><h2>{("Учасники й команда" if lang == "uk" else "Participants and team") if is_ev else t["credits"]}</h2></div><dl class="credits" style="margin-top:28px">{credits}</dl></section>' if credits else ''}
{f'<section class="sec gut max" style="padding-top:0"><div class="sh"><h2>{t["photos"]}</h2></div><div class="gal">{"".join(gal_items)}</div>{pc}</section>' if gal_items else ''}
{media_strip([m for m in MEDIA if m.get("production") == p["slug"]], lang, t['nav']['media'], url('media', lang), 'Усе з медіа' if lang == 'uk' else 'All media', top0=True)}
"""
    paths = (show_url(p["slug"], lang), show_url(p["slug"], other(lang)))
    uk = lang == "uk"
    kind = p.get(f"seo_kind_{lang}") or (("подія" if uk else "event") if is_ev else ("вистава" if uk else "performance"))
    seo_title = f"{title}: {kind} {'в Києві' if uk else 'in Kyiv'}" if p.get("status") in ("repertoire", "upcoming", "produced") else title
    desc = L(p, "summary", lang)
    up = [x for x in evs if x["date"] >= TODAY]
    if up:
        nx = up[0]
        desc = desc.rstrip(".") + ". " + (f"Найближчий показ — {nx['date'].day} {MONTHS[lang][nx['date'].month - 1]}, {L(nx, 'city', lang)}." if uk else f"Next performance: {nx['date'].day} {MONTHS[lang][nx['date'].month - 1]}, {L(nx, 'city', lang)}.")
    return head(lang, "shows", seo_title, desc, paths, og=OG_DONE.get(f"{p['slug']}-{lang}"), ld=ld_production(p, evs, lang)) + body + foot(lang)


def show_quotes(p, lang):
    qs = p.get("quotes") or []
    if not qs:
        return ""
    items = "".join(f"""<blockquote><p>{e(L(x, 'text', lang))}</p><footer>{e(x.get('author', ''))}{(', ' + e(L(x, 'role', lang))) if L(x, 'role', lang) else ''}</footer></blockquote>""" for x in qs)
    return f'<section class="sec gut max" style="padding-top:0"><div class="sh"><h2>{"Відгуки" if lang == "uk" else "Responses"}</h2></div><div class="quotes">{items}</div></section>'


def ticket_box(ev, p, lang, count):
    uk = lang == "uk"
    d = ev["date"]
    tm = f" | {ev['time']}" if ev.get("time") else ""
    when = f"{d.day} {MONTHS[lang][d.month - 1]}, {DOW[lang][d.weekday()]}{tm}"
    _pr = f'{ev.get("price")}{"–" + str(ev["price_max"]) if ev.get("price_max") else ""}'
    price = (f'<p class="tbp">{_pr} ₴</p>' if uk else f'<p class="tbp">UAH {_pr}</p>') if ev.get("price") else ""
    btns = []
    if ev.get("ticket_url") and ev.get("status") != "sold_out":
        btns.append(f'<a class="tix big" href="{e(ev["ticket_url"])}" target="_blank" rel="noopener" data-provider="{provider(ev["ticket_url"])}" data-show="{p["slug"]}">{"Оплатити через WayForPay" if uk and provider(ev["ticket_url"]) == "wayforpay" else "Pay with WayForPay" if provider(ev["ticket_url"]) == "wayforpay" else T[lang]["tickets"]}</a>')
    if concert_url(ev) and ev.get("status") != "sold_out":
        btns.append(f'<a class="tbo" href="{e(concert_url(ev))}" target="_blank" rel="noopener" data-provider="concertua" data-show="{p["slug"]}">{"Купити на Concert.ua" if uk else "Buy on Concert.ua"}</a>')
    if not btns:
        btns.append(cta(ev, lang))
    more = f'<a class="go" href="#dates">{"Усі дати" if uk else "All dates"} ({count})</a>' if count > 1 else ""
    return f"""<section class="tbox gut max" aria-label="{T[lang]['tickets']}"><div class="tbi">
  <div class="tbw"><p class="tbl">{"Найближчий показ" if uk else "Next performance"}</p><p class="tbd">{e(when)}</p><p class="tbv">{e(L(ev, 'venue', lang))}</p></div>
  {price}<div class="tbb">{''.join(btns)}{more}</div></div></section>"""


PF_WORKS = [
    ("mizh-svitom-i-dusheyu", "2026", "Режисер, автор сценарію", "Director, scriptwriter"),
    ("under-the-uniform", "2026", "Режисер, драматург", "Director, playwright"),
    ("promova", "2026", "Режисер", "Director"),
    (None, "2026", "Продюсер, продакшн-менеджер", "Producer, production manager", "Троянські жінки", "Trojan Women", "Експериментальний театральний клуб «НАШі» | La MaMa ETC", "NASHi Experimental Theatre Club | La MaMa ETC"),
    ("naoslip", "2026", "Куратор, продюсер", "Curator, producer"),
    ("koni-za-viknom", "2026", "Продюсер", "Producer"),
    ("kinets-zminy", "2026", "Продюсер", "Producer"),
    ("the-inferior-play", "2026", "Продюсер", "Producer"),
    (None, "2026", "Продюсер компанії", "Company producer", "RUBICON", "RUBICON", "Anthill Dance Theater, Стокгольм", "Anthill Dance Theater, Stockholm"),
    ("promova-2025", "2025", "Режисер", "Director"),
]


def page_producer(lang):
    pr = PRODUCER
    uk = lang == "uk"
    name = L(pr, "name", lang)
    mail = SETTINGS["contacts"]["producer"]

    def work(w):
        slug, yr = w[0], w[1]
        role = w[2] if uk else w[3]
        if slug and slug in BY_SLUG:
            p = BY_SLUG[slug]
            title, href = L(p, "title", lang), show_url(slug, lang)
            pic = img(p.get("cover"), title, "(max-width:760px) 100vw, 33vw")
            note = ""
        else:
            title, href, pic = (w[4] if uk else w[5]), None, ""
            note = w[6] if uk else w[7]
        im = pic or f'<span class="mk">{e(title)}</span>'
        inner = f'<div class="im">{im}</div><p class="m">{e(yr)} | {e(role)}</p><h3>{e(title)}</h3>' + (f'<p class="nt">{e(note)}</p>' if note else "")
        return f'<a class="w" href="{href}">{inner}</a>' if href else f'<div class="w">{inner}</div>'

    def wrow(w):
        slug, yr = w[0], w[1]
        role = w[2] if uk else w[3]
        if slug and slug in BY_SLUG:
            p = BY_SLUG[slug]
            t = f'<a href="{show_url(slug, lang)}">{e(L(p, "title", lang))}</a>'
            nt = ((("Прем’єра " if uk else "Premiere ") + L(p, "premiere", lang)) if p.get("status") == "upcoming" and L(p, "premiere", lang) else "")
        else:
            t, nt = e(w[4] if uk else w[5]), (w[6] if uk else w[7])
        return f'<li><span>{e(yr)}</span><b>{t}</b><em>{e(role)}{(" | " + e(nt)) if nt else ""}</em></li>'

    def rows(items):
        return "".join(f'<li><span>{e(y)}</span><b>{e(t)}</b><em>{e(d)}</em></li>' for y, t, d in items)
    now = []
    for x in pr.get("now", []):
        t, _, d = x.get(lang, "").partition(" | ")
        now.append((x["year"], t, d))
    now.sort(key=lambda r: r[0], reverse=True)
    progs = [(c.get("year", ""), L(c, "title", lang) or c.get("title", ""), L(c, "text", lang)) for c in pr.get("programmes", [])]
    vis = "".join(f'<div><h3>{e(v["title"])}</h3><p>{e(v["text"])}</p></div>' for v in pr.get(f"vision_{lang}", []))
    prin = "".join(f"<li>{e(x)}</li>" for x in pr.get(f"principles_{lang}", []))
    voices = "".join(f"""<blockquote><p>{e(L(v, 'text', lang))}</p><footer><b>{e(v['author'])}</b>{e(L(v, 'role', lang))}</footer></blockquote>""" for v in pr.get("voices", []))

    def sec(title, inner, extra=""):
        return f'<section class="sec gut max grp"><div class="sh"><h2>{title}</h2>{extra}</div>{inner}</section>'
    body = f"""<section class="gut max pf2">
  <figure class="pp">{img(pr.get('photo'), name, "(max-width:860px) 100vw, 42vw", eager=True)}</figure>
  <div class="tx"><p class="role">{e(L(pr, 'role', lang))}</p><h1>{'<br>'.join(e(x) for x in name.split(' ', 1))}</h1>
  <div class="bio">{mdh(L(pr, "bio", lang))}</div>
  <p class="ct"><a class="tbo" href="mailto:{mail}">{mail}</a><a class="tbo" href="https://t.me/teatr_bentegy" target="_blank" rel="noopener">Telegram</a></p>
  <p class="credit-line">{e(bi(pr.get('photo_credit', ''), lang))}</p></div>
</section>
{sec('Роботи' if uk else 'Work', f'<div class="pw">{"".join(work(w) for w in PF_WORKS if w[0] and w[0] not in ("promova-2025", "the-inferior-play") and BY_SLUG.get(w[0], {}).get("cover"))}</div><ul class="pwl">{"".join(wrow(w) for w in PF_WORKS if not (w[0] and w[0] not in ("promova-2025", "the-inferior-play") and BY_SLUG.get(w[0], {}).get("cover")))}</ul>')}
{sec('Практика' if uk else 'Practice', f'<div class="vis">{vis}</div><ol class="prin pf2p">{prin}</ol>')}
{sec('Біографія' if uk else 'Biography', f'<div class="pcv"><div><p class="kk">{"Позиції" if uk else "Roles"}</p><ul>{rows(now)}</ul></div><div><p class="kk">{"Програми, резиденції, освіта" if uk else "Programmes, residencies, education"}</p><ul>{rows(progs)}</ul></div></div>')}
{sec('Голоси' if uk else 'Voices', f'<div class="voices">{voices}</div>', f'<span class="more">{e(L(pr, "voices_note", lang))}</span>')}
{media_strip(by_author("pavlo-koval"), lang, 'Тексти' if uk else 'Writing', mtype_url('text', lang), 'Усі тексти' if uk else 'All texts', top0=True)}
"""
    return head(lang, "producer", name, L(pr, "bio", lang)[:160], (url("producer", lang), url("producer", other(lang))), og=img_url(pr.get("photo"))) + body + foot(lang)


def team_cards(lang):
    uk = lang == "uk"

    def initials(x):
        return "".join(w[0] for w in L(x, "name", lang).split()[:2]).upper() or "—"

    def links(x):
        if x["slug"] == "pavlo-koval" or x.get("producer_page"):
            return f'<p class="tlinks"><a class="pf" href="{url("producer", lang)}">{"Портфоліо" if uk else "Portfolio"} →</a></p>'
        return ""
    core = [x for x in TEAM if (x.get("group") or "team") == "team"]
    return "".join(f"""<article class="tc" id="{x['slug']}"><div class="im">{img(x.get('photo'), L(x, 'name', lang), "(max-width:760px) 50vw, 20vw") or f'<span class="ini">{e(initials(x))}</span>'}</div>
  <p class="tr">{e(L(x, 'role', lang))}</p><h3>{e(L(x, 'name', lang))}</h3>{links(x)}</article>""" for x in core)


def org_block(lang):
    uk = lang == "uk"
    o = SETTINGS["organization"]
    reg = dt.date.fromisoformat(str(o["registered"]))
    regs = f"{reg.day} {MONTHS[lang][reg.month - 1]} {reg.year}" + (" року" if uk else "")
    mail = SETTINGS["contacts"].get("theatre") or SETTINGS["contacts"]["team"]
    rows = [
        ("Повна назва" if uk else "Legal name", e(L(o, "name", lang)) + (f" ({e(o['name_en'])})" if uk else f' (“V RESURSI”; in Ukrainian: <span lang="uk">{e(o["name_uk"])}</span>)')),
        ("Код ЄДРПОУ" if uk else "EDRPOU (registration code)", e(str(o["edrpou"]))),
        ("Зареєстровано" if uk else "Registered", e(regs)),
        ("Юридична адреса" if uk else "Registered address", e(L(o, "address", lang))),
        ("Керівник" if uk else "Head", e(L(o, "head", lang))),
        ("Неприбутковий статус" if uk else "Non-profit status", e(L(o, "nonprofit", lang))),
        ("Пошта" if uk else "Email", f'<a href="mailto:{mail}">{mail}</a>'),
    ]
    dl = "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in rows)
    lead = ("Театр Бентеги діє через молодіжну громадську організацію «В РЕСУРСІ» — неприбуткову, позапартійну й незалежну. Організація існує завдяки грантам, квиткам, внескам і партнерствам; документи надаємо на запит."
            if uk else
            "Bentegy Theatre operates through the youth NGO In the Resource: non-profit, non-partisan and independent. It is funded by grants, ticket income, donations and partnerships; documents are available on request.")
    return f"""<section class="sec gut max grp" id="organisation"><div class="sh"><h2>{'Організація' if uk else 'Organisation'}</h2></div>
  <div class="two"><span></span><div><p class="prose">{lead}</p><dl class="req" style="margin-top:24px">{dl}</dl></div></div></section>"""


def page_about(lang):
    t = T[lang]
    a = ABOUT
    uk = lang == "uk"
    partners = "".join(f"<span>{e(bi(x, lang))}</span>" for x in SETTINGS.get("partners", []))
    nao = BY_SLUG.get("naoslip")
    nao_h = ""
    if nao:
        nao_h = f"""<section class="sec gut max grp"><div class="sh"><h2>{'Подія сезону' if uk else 'Season highlight'}</h2></div>
  <a class="feat" href="{show_url('naoslip', lang)}"><div class="im">{img(nao.get('cover'), L(nao, 'title', lang), "(max-width:860px) 100vw, 55vw")}</div>
  <div class="tx"><p class="k">{'7 серпня 2026 | КультМотив, Київ' if uk else '7 August 2026 | KultMotyv, Kyiv'}</p><h3>{e(L(nao, 'title', lang))}</h3><p>{e(L(a, 'naoslip', lang))}</p><span class="go">{'Детальніше' if uk else 'Read more'} →</span></div></a></section>"""
    body = page_head(t["nav"]["about"], L(a, "lead", lang)) + f"""
<section class="sec gut max grp"><div class="sh"><h2>{'Місія' if uk else 'Mission'}</h2></div><div class="two"><span></span><p class="big-lead">{e(L(a, 'mission', lang))}</p></div></section>
{nao_h}
<section class="sec gut max grp"><div class="sh"><h2>{'Міжнародна співпраця' if uk else 'International work'}</h2><span class="more">{'Пріоритет 2027' if uk else 'Priority for 2027'}</span></div><div class="two"><span></span><div class="prose">{mdh(L(a, 'intl', lang))}</div></div></section>
<section class="sec gut max grp" id="team"><div class="sh"><h2>{'Команда' if uk else 'Team'}</h2></div><div class="tgrid">{team_cards(lang)}</div>
  <p class="mu" style="margin-top:20px;max-width:62ch">{'Над кожною виставою працюють запрошені режисери, актори, хореографи й художники.' if uk else 'Each production brings in guest directors, performers, choreographers and designers.'}</p></section>
<section class="sec gut max grp"><div class="sh"><h2>{'Партнери' if uk else 'Partners'}</h2></div><div class="chips" style="margin-top:24px">{partners}</div></section>
{org_block(lang)}
"""
    return head(lang, "about", t["nav"]["about"], L(a, "lead", lang), (url("about", lang), url("about", other(lang))), ld=ld_org(lang)) + body + foot(lang)


def redirect_page(lang, to):
    return f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="robots" content="noindex"><link rel="canonical" href="{SITE}{to}"><meta http-equiv="refresh" content="0;url={to}"><title>Bentegy</title></head><body><a href="{to}">{to}</a></body></html>"""


def page_org(lang):
    t = T[lang]
    o = SETTINGS["organization"]
    reg = dt.date.fromisoformat(str(o["registered"]))
    regs = f"{reg.day} {MONTHS[lang][reg.month - 1]} {reg.year}" + (" року" if lang == "uk" else "")
    uk = lang == "uk"
    rows = [
        ("Повна назва" if uk else "Legal name", L(o, "name", lang)),
        ("Назва англійською" if uk else "Name in Ukrainian", o["name_en"] if uk else o["name_uk"]),
        ("Код ЄДРПОУ" if uk else "EDRPOU (registration code)", o["edrpou"]),
        ("Дата реєстрації" if uk else "Registered", regs),
        ("Організаційна форма" if uk else "Legal form", "Молодіжна громадська організація" if uk else "Youth public association"),
        ("Юридична адреса" if uk else "Registered address", L(o, "address", lang)),
        ("Місце діяльності" if uk else "Based in", "Київ, Україна" if uk else "Kyiv, Ukraine"),
        ("Органи управління" if uk else "Governance", "Загальні збори, правління" if uk else "General Meeting, Board"),
        ("Керівник" if uk else "Head", L(o, "head", lang)),
        ("Неприбутковий статус" if uk else "Non-profit status", L(o, "nonprofit", lang)),
    ]
    dl = "".join(f"<dt>{a}</dt><dd>{e(str(b))}</dd>" for a, b in rows)
    mail = SETTINGS["contacts"].get("theatre") or SETTINGS["contacts"]["team"]
    dl += f'<dt>{"Електронна пошта" if uk else "Email"}</dt><dd><a href="mailto:{mail}">{mail}</a></dd>'
    goals = "".join(f"<li>{e(g)}</li>" for g in GOALS[lang])
    lead = ("Театр Бентеги діє через молодіжну громадську організацію «В РЕСУРСІ». Організація неприбуткова, позапартійна і незалежна, внесена до Реєстру неприбуткових установ та організацій."
            if uk else
            "Bentegy Theatre operates through the youth NGO In the Resource. It is non-profit, non-partisan and independent, and is listed in the Register of Non-Profit Institutions of the State Tax Service of Ukraine.")
    purpose = ("Розбудова активного громадянського суспільства; всебічний розвиток культури й мистецтва в Україні; підтримка театрального, музичного, літературного, візуального й перформативного мистецтва; формування нових культурних практик та інституцій; розвиток неформальної та громадянської освіти, самовизначення й самореалізація молоді, її змістовне дозвілля."
               if uk else
               "Building an active civil society; the comprehensive development of culture and the arts in Ukraine; supporting theatre, music, literary, visual and performing arts; contributing to new cultural practices and institutions; developing non-formal and civic education and the self-realisation and meaningful leisure of young people.")
    funding = ("Організація існує завдяки грантам, власним надходженням від квитків і партнерствам з майданчиками. Документи організації надаємо на запит."
               if uk else
               "The organisation is funded by grants, box-office income and in-kind partnerships with venues. Organisational documents are available on request.")
    partners = "".join(f"<span>{e(bi(x, lang))}</span>" for x in SETTINGS.get("partners", []))
    body = page_head(t["nav"]["org"], lead) + f"""
<section class="sec gut max" style="padding-top:clamp(32px,4vw,56px)"><div class="sh"><h2>{'Реквізити' if uk else 'Details'}</h2></div><dl class="req">{dl}</dl></section>
<section class="sec gut max" style="padding-top:0"><div class="sh"><h2>{'Мета' if uk else 'Purpose'}</h2></div><div class="two"><span></span><div class="prose"><p>{purpose}</p><p class="mu" style="font-size:15px">{'Статут затверджено рішенням Загальних зборів, протокол № 5 від 1 серпня 2025 року.' if uk else 'Statute approved by the General Meeting, Protocol No. 5 of 1 August 2025. English text is a courtesy translation.'}</p></div></div></section>
<section class="sec gut max" style="padding-top:0"><div class="sh"><h2>{'Напрями' if uk else 'Activities'}</h2></div><ol class="goals">{goals}</ol></section>
<section class="sec gut max" style="padding-top:0"><div class="sh"><h2>{'Фінансування' if uk else 'Funding'}</h2></div><div class="two"><span></span><div><p class="prose">{funding}</p><div class="chips" style="margin-top:24px">{partners}</div></div></div></section>
"""
    return head(lang, "org", t["nav"]["org"], lead, (url("org", lang), url("org", other(lang)))) + body + foot(lang)


def page_contact(lang):
    t = T[lang]
    c = SETTINGS["contacts"]
    uk = lang == "uk"
    items = [
        ("Театр і організація" if uk else "Theatre & organisation", f"mailto:{c.get('theatre') or c['team']}", c.get("theatre") or c["team"], "Офіційне листування, державні органи, грантодавці, договори й реквізити." if uk else "Official correspondence, public bodies, funders, contracts and legal details."),
        ("Співпраця" if uk else "Partnerships", f"mailto:{c['team']}", c["team"], "Партнерства, гастролі, продюсування молодих команд, меценатство." if uk else "Partnerships, touring, producing for emerging companies, patronage."),
        ("Медіа та преса" if uk else "Media & press", f"mailto:{c['press']}", c["press"], "Акредитації, інтервʼю, пресматеріали й фото." if uk else "Accreditation, interviews, press kits and photos."),
        ("Продюсер" if uk else "Producer", f"mailto:{c['producer']}", c["producer"], "Павло Коваль, засновник і продюсер. Для прямого звернення." if uk else "Pavlo Koval, founder and producer. For direct enquiries."),
        ("Телефон" if uk else "Phone", f"tel:{c['phone'].replace(' ', '')}", c["phone"], ""),
        ("Instagram", c["instagram"], "@teatr.bentegy", "Анонси вистав і квитки." if uk else "Announcements and tickets."),
        ("Telegram", c["telegram"], "@teatr_bentegy", ""),
        *([("YouTube", c["youtube"], "@BentegyTheatre", "Відео театру." if uk else "Theatre videos.")] if c.get("youtube") else []),
        ("Пресматеріали" if uk else "Press kit", url("press", lang), "bentegy.org" + url("press", lang), "Фото, логотипи, тексти про театр." if uk else "Photos, logos and texts about the theatre."),
    ]
    g = "".join(f"<div class='cr'><small>{a}</small><a href='{h}'>{e(v)}</a><p>{e(p)}</p></div>" for a, h, v, p in items)
    lead = "Пишіть нам щодо співпраці, гастролей, продюсування чи медіа. Відповідаємо українською та англійською." if uk else "Get in touch about collaborations, touring, producing or press. We reply in English and Ukrainian."
    body = page_head(t["nav"]["contact"], lead) + f'<section class="gut max" style="padding-bottom:clamp(48px,6vw,96px)"><div class="cgrid cmp">{g}</div></section>'
    return head(lang, "contact", t["nav"]["contact"], lead, (url("contact", lang), url("contact", other(lang)))) + body + foot(lang)



def copy_btn(lang, target):
    return f'<button type="button" class="copy" data-copy="{target}" data-done="{"Скопійовано" if lang == "uk" else "Copied"}">{"Скопіювати" if lang == "uk" else "Copy"}</button>'


def page_support(lang):
    t = T[lang]
    uk = lang == "uk"
    sp = SUPPORT
    b = sp.get("bank") or {}
    mail = SETTINGS["contacts"]["team"]
    org = SETTINGS["organization"]
    ways = []
    # 0. donation tiers (WayForPay buttons, UAH on the Ukrainian page, EUR on the English page)
    cur = "uah" if uk else "eur"
    sym = "₴" if uk else "€"
    tiers = [x for x in (sp.get("tiers") or []) if x.get(f"url_{cur}")]
    free = sp.get(f"free_url_{cur}")
    tiers_html = ""
    if tiers or free:
        cards = "".join(f"""<div class="tier"><p class="amt">{'' if uk else sym}{'{:,}'.format(int(x.get(f'amount_{cur}') or 0)).replace(',', ' ')}{' ' + sym if uk else ''}</p><h3>{e(L(x, 'title', lang))}</h3><p>{e(L(x, 'text', lang))}</p>
  <a class="tix" href="{e(x[f'url_{cur}'])}" target="_blank" rel="noopener">{'Підтримати' if uk else 'Donate'}</a></div>""" for x in tiers)
        if free:
            cards += f"""<div class="tier free"><p class="amt">{'Своя сума' if uk else 'Any amount'}</p><h3>{'Як вам зручно' if uk else 'Your choice'}</h3><p>{'Кожна гривня йде на вистави, команду й покази.' if uk else 'Every euro goes to productions, the team and performances.'}</p>
  <a class="tix" href="{e(free)}" target="_blank" rel="noopener">{'Обрати суму' if uk else 'Choose amount'}</a></div>"""
        alt = (f'<a class="go" href="{url("support", "en")}">Donate in euro from abroad →</a>' if uk and (sp.get("free_url_eur") or any(x.get("url_eur") for x in sp.get("tiers") or []))
               else f'<a class="go" href="{url("support", "uk")}">Donate in hryvnia (Ukrainian page) →</a>' if not uk and (sp.get("free_url_uah") or any(x.get("url_uah") for x in sp.get("tiers") or [])) else "")
        tiers_html = f"""<div class="tiers">{cards}</div><p class="tnote">{e(L(sp, 'online_note', lang))} {alt}</p>"""
    if tiers_html:
        ways.append(f"""<article class="way wide"><span class="n">01</span><div><h3>{'Онлайн-донат' if uk else 'Donate online'}</h3>{tiers_html}</div></article>""")
    # 1. online card payment
    if sp.get("online_url") and not tiers_html:
        ways.append(f"""<article class="way"><span class="n">01</span><div><h3>{'Онлайн карткою' if uk else 'Card payment online'}</h3>
  <p>{e(L(sp, 'online_note', lang))}</p></div>
  <div class="act"><a class="tix big" href="{e(sp['online_url'])}" target="_blank" rel="noopener">{'Зробити внесок' if uk else 'Donate'}</a><small>WayForPay</small></div></article>""")
    # 2. bank transfer
    def iban(v):
        v = (v or "").replace(" ", "")
        return " ".join(v[i:i + 4] for i in range(0, len(v), 4))
    rows = [(("Отримувач" if uk else "Beneficiary"), L(b, "recipient", lang)), ("Код ЄДРПОУ" if uk else "EDRPOU", b.get("edrpou", ""))]
    if uk:
        rows += [("IBAN (гривня)", iban(b.get("iban_uah"))), ("Банк", L(b, "bank", lang))]
    else:
        rows += [("IBAN (EUR)", iban(b.get("iban_eur"))), ("IBAN (USD)", iban(b.get("iban_usd"))), ("Bank", L(b, "bank", lang)), ("SWIFT / BIC", b.get("swift", "")),
                 ("Beneficiary address", b.get("address_en", "")), ("IBAN (UAH, transfers within Ukraine)", iban(b.get("iban_uah")))]
    rows.append(("Призначення платежу" if uk else "Payment reference", L(b, "purpose", lang)))
    has_acc = any(b.get(k) for k in ("iban_uah", "iban_usd", "iban_eur"))
    if has_acc:
        dl = ""
        for i, (a, v) in enumerate(rows):
            if not v:
                continue
            if a.startswith("IBAN"):
                dl += f'<dt>{a}</dt><dd><span id="iban-{lang}-{i}">{e(v)}</span> {copy_btn(lang, f"iban-{lang}-{i}")}</dd>'
            else:
                dl += f"<dt>{a}</dt><dd>{e(v)}</dd>"
        foreign = "" if not uk else ("<p class='mu'>Для переказів з-за кордону в євро — реквізити SWIFT на <a href='" + url("support", "en") + "'>англійській версії сторінки</a>.</p>" if (b.get("iban_usd") or b.get("iban_eur")) else "")
        if not uk and b.get("correspondents"):
            corr = "".join(f"<dt>{e(c.get('bank', ''))}</dt><dd>SWIFT {e(c.get('swift', ''))} | Account {e(str(c.get('account', '')))}</dd>" for c in b["correspondents"])
            foreign = f'<details class="corr"><summary>Correspondent banks (EUR)</summary><dl class="req tight">{corr}</dl></details>' 
        ways.append(f"""<article class="way"><span class="n">{len(ways) + 1:02d}</span><div><h3>{'Переказ на рахунок' if uk else 'Bank transfer'}</h3>
  <dl class="req tight">{dl}</dl>{foreign}</div><div class="act"></div></article>""")
    if not ways:
        ways.append(f"""<article class="way"><span class="n">01</span><div><h3>{'Реквізити для внеску' if uk else 'How to give'}</h3>
  <p>{'Напишіть нам, і ми надішлемо реквізити для переказу в гривні, доларах чи євро, а також договір благодійної пожертви для юридичних осіб.' if uk else 'Write to us and we will send bank details for transfers in hryvnia, US dollars or euro, and a donation agreement for companies and foundations.'}</p></div>
  <div class="act"><a class="tix big" href="mailto:{mail}?subject={'Підтримка театру' if uk else 'Supporting Bentegy'}">{'Написати' if uk else 'Write to us'}</a></div></article>""")
    uses = "".join(f"<div class='rw'><h3>{e(x['title'])}</h3><p>{e(x['text'])}</p></div>" for x in sp.get(f"uses_{lang}", []))
    parts = "".join(f"<div><h3>{e(x['title'])}</h3><p>{e(x['text'])}</p></div>" for x in sp.get(f"partners_{lang}", []))
    partners = "".join(f"<span>{e(bi(x, lang))}</span>" for x in SETTINGS.get("partners", []))
    trust = (f"Внески отримує {e(org['name_uk'])}, код ЄДРПОУ {org['edrpou']}. Організація неприбуткова (ознака 0032) і використовує кошти лише на статутну діяльність. Звіт про використання надсилаємо на запит."
             if uk else
             f"Donations are received by {e(org['name_en'])}, EDRPOU {org['edrpou']}, a registered non-profit (code 0032) that uses funds only for its statutory activities. A report on how funds were used is available on request.")
    body = page_head(t["nav"]["support"], L(sp, "lead", lang)) + f"""
<section class="sec gut max" style="padding-top:clamp(32px,4vw,56px)"><div class="sh"><h2>{'Як підтримати' if uk else 'How to give'}</h2></div>{''.join(ways)}</section>
<section class="sec gut max" style="padding-top:0"><div class="sh"><h2>{'На що йдуть кошти' if uk else 'Where it goes'}</h2></div><div class="rows" style="margin-top:28px">{uses}</div></section>
<section class="sec gut max" style="padding-top:0"><div class="sh"><h2>{'Партнерам' if uk else 'Partners'}</h2></div><div class="grid2">{parts}</div>
  <div class="cgrid" style="border-top:0"><div class="cr"><div><small>{'Партнерства й меценатство' if uk else 'Partnerships and patronage'}</small><p>{'Розкажемо про сезон, підготуємо пропозицію й договір.' if uk else 'We will share the season plan and prepare a proposal and agreement.'}</p></div><a href="mailto:{mail}">{mail}</a></div></div>
  <div class="chips" style="margin-top:28px">{partners}</div></section>
<section class="sec gut max" style="padding-top:0"><div class="sh"><h2>{'Прозорість' if uk else 'Transparency'}</h2><a class="more" href="{url('about', lang) + '#organisation'}">{'Реквізити організації' if uk else 'Organisation details'}</a></div>
  <div class="two"><span></span><p class="prose">{trust}</p></div></section>
"""
    return head(lang, "support", t["nav"]["support"], L(sp, "lead", lang), (url("support", lang), url("support", other(lang)))) + body + foot(lang)


def page_press(lang):
    t = T[lang]
    uk = lang == "uk"
    pr = PRESS
    c = SETTINGS["contacts"]
    texts = f"""<div class="bp"><div class="bh"><h3>{'Коротко' if uk else 'Short'}</h3>{copy_btn(lang, 'bp-short')}</div><div class="prose" id="bp-short"><p>{e(L(pr, 'about_short', lang))}</p></div></div>
<div class="bp"><div class="bh"><h3>{'Детально' if uk else 'Long'}</h3>{copy_btn(lang, 'bp-long')}</div><div class="prose" id="bp-long">{mdh(L(pr, 'about_long', lang))}</div></div>
<div class="bp"><div class="bh"><h3>{'Засновник' if uk else 'Founder'}: {e(L(PRODUCER, 'name', lang))}</h3>{copy_btn(lang, 'bp-bio')}</div><div class="prose" id="bp-bio">{mdh(L(PRODUCER, 'bio', lang))}</div></div>"""
    logos = "".join(f"""<figure class="lg-{x.get('bg', 'light')}"><div class="lgim"><img src="{e(x['file'])}" alt="{e(L(x, 'title', lang))}" loading="lazy"></div><figcaption><span>{e(L(x, 'title', lang))}<small>PNG</small></span><a href="{e(x['file'])}" download>{'Завантажити' if uk else 'Download'} ↓</a></figcaption></figure>""" for x in pr.get("logos", []))
    cov = ""
    if pr.get("coverage"):
        items = []
        for x in sorted(pr["coverage"], key=lambda z: str(z.get("date", "")), reverse=True):
            d = str(x.get("date", ""))
            try:
                dd = dt.date.fromisoformat(d)
                ds = f"{dd.day:02d}.{dd.month:02d}.{dd.year}"
            except ValueError:
                ds = d
            items.append(f"""<a class="cov" href="{e(x['url'])}" target="_blank" rel="noopener"><span class="d">{ds}</span><b>{e(x.get(f'outlet_{lang}') or x.get('outlet', ''))}</b><span class="t">{e(x.get(f'title_{lang}') or x.get('title', ''))}</span><span class="ar">→</span></a>""")
        cov = f'<section class="sec gut max" style="padding-top:0"><div class="sh"><h2>{"Публікації" if uk else "Coverage"}</h2></div>{"".join(items)}</section>'
    qs = ""
    if pr.get("quotes"):
        qs = '<section class="sec gut max" style="padding-top:0"><div class="sh"><h2>' + ("Відгуки" if uk else "Quotes") + '</h2></div><div class="quotes">' + "".join(
            f"""<blockquote><p>{e(L(x, 'text', lang))}</p><footer>{e(x.get('author', ''))}{', ' if x.get('author') and x.get('outlet') else ''}{f'<a href="{e(x["url"])}" target="_blank" rel="noopener">{e(x.get("outlet", ""))}</a>' if x.get('url') else e(x.get('outlet', ''))}</footer></blockquote>""" for x in pr["quotes"]) + "</div></section>"
    body = page_head(t["nav"]["press"], L(pr, "lead", lang)) + f"""
<section class="gut max"><div class="cgrid"><div class="cr"><div><small>{'Контакт для преси' if uk else 'Press contact'}</small><p>{'Акредитації, інтервʼю, запити на фото й відео.' if uk else 'Accreditation, interviews, photo and video requests.'}</p></div><a href="mailto:{c['press']}">{c['press']}</a></div></div></section>
<section class="sec gut max" style="padding-top:clamp(40px,5vw,72px)"><div class="sh"><h2>{'Про театр' if uk else 'About'}</h2></div><div class="bps">{texts}</div></section>
<section class="sec gut max" style="padding-top:0"><div class="sh"><h2>{'Логотипи' if uk else 'Logos'}</h2><a class="more" href="/press/bentegy-logos.zip" download>{'Повний пакет PNG + SVG .zip' if uk else 'Full package PNG + SVG .zip'}</a></div><div class="dl logos">{logos}</div></section>
{media_strip([m for m in MEDIA if m["type"] == "release"], lang, "Пресрелізи" if uk else "Press releases", mtype_url("release", lang), "Усі пресрелізи" if uk else "All press releases", top0=True)}
{cov}{qs}
"""
    return head(lang, "press", t["nav"]["press"], L(pr, "lead", lang), (url("press", lang), url("press", other(lang)))) + body + foot(lang)


# ------------------------------------------------------------------ media & team
def by_author(slug):
    return [m for m in MEDIA if slug in (m.get("authors") or [])]


def person_name(a, lang):
    p = TEAM_BY.get(a)
    if p:
        return L(p, "name", lang)
    if a == "pavlo-koval":
        return L(PRODUCER, "name", lang)
    return a


def person_href(a, lang):
    if a == "pavlo-koval":
        return url("producer", lang)
    if a in TEAM_BY:
        return f"{url('about', lang)}#team"
    return ""


def authors_html(m, lang, links=True):
    out = []
    for a in (m.get("authors") or []):
        n = e(person_name(a, lang))
        h = person_href(a, lang) if links else ""
        out.append(f'<a href="{h}">{n}</a>' if h else n)
    if L(m, "guest_author", lang):
        out.append(e(L(m, "guest_author", lang)))
    return ", ".join(out)


def mlabel(m, lang):
    i = 4 if lang == "uk" else 5
    return L(m, "rubric", lang) or MTYPE[m["type"]][i]


def read_min(m, lang):
    words = len((L(m, "body", lang) or "").split())
    n = max(1, round(words / 200))
    return f"{n} хв читання" if lang == "uk" else f"{n} min read"


def media_item(m, lang):
    tp = m["type"]
    au = authors_html(m, lang, links=False)
    meta = f'<span class="mk">{e(mlabel(m, lang))}</span><span>{fdate(m["date"], lang)}</span>' + (f"<span>{au}</span>" if au else "")
    title = e(L(m, "title", lang))
    lead = e(L(m, "lead", lang))
    if tp == "article":
        return f'<a class="mi mr ma" href="{e(m["url"])}" target="_blank" rel="noopener"><span class="md">{m["date"].day:02d}.{m["date"].month:02d}.{m["date"].year}</span><div><p class="mm"><span class="mk">{e(L(m, "outlet", lang))}</span></p><h3>{title}</h3>{f'<p class="ml">{lead}</p>' if lead else ''}</div><span class="ar">→</span></a>'
    href = media_url(m["slug"], lang)
    if tp == "text":
        return f'<a class="mi mt" href="{href}"><p class="mm">{meta}</p><h3>{title}</h3><p class="ml">{lead}</p><span class="ar">{"Читати" if lang == "uk" else "Read"} →</span></a>'
    if tp == "release":
        p = BY_SLUG.get(m.get("production"))
        pt = f'<span class="mp">{e(L(p, "title", lang))}</span>' if p else ""
        return f'<a class="mi mr" href="{href}"><span class="md">{m["date"].day:02d}.{m["date"].month:02d}.{m["date"].year}</span><div><p class="mm"><span class="mk">{e(mlabel(m, lang))}</span>{pt}</p><h3>{title}</h3></div><span class="ar">→</span></a>'
    pic = img(m.get("cover"), L(m, "title", lang), "(max-width:760px) 100vw, 30vw") or '<span class="ph0"></span>'
    return f'<a class="mi mn" href="{href}"><div class="im">{pic}</div><div><p class="mm">{meta}</p><h3>{title}</h3><p class="ml">{lead}</p></div></a>'


def media_strip(items, lang, title, more_href, more_label, top0=False):
    if not items:
        return ""
    st = ' style="padding-top:0"' if top0 else ""
    return f'<section class="sec gut max"{st}><div class="sh"><h2>{e(title)}</h2><a class="more" href="{more_href}">{e(more_label)}</a></div><div class="mlist">{"".join(media_item(m, lang) for m in items[:6])}</div></section>'


def media_feature(m, lang):
    au = authors_html(m, lang, links=False)
    pic = img(m.get("cover"), L(m, "title", lang), "(max-width:860px) 100vw, 58vw", eager=True)
    cls = "mf" + ("" if pic else " nopic")
    return f"""<a class="{cls}" href="{media_url(m['slug'], lang)}">{f'<div class="im">{pic}</div>' if pic else ''}
  <div class="tx"><p class="mm"><span class="mk">{e(mlabel(m, lang))}</span><span>{fdate(m['date'], lang)}</span>{f'<span>{au}</span>' if au else ''}</p>
  <h2>{e(L(m, 'title', lang))}</h2><p class="ml">{e(L(m, 'lead', lang))}</p></div></a>"""


def page_media_index(lang, tp=None):
    t = T[lang]
    uk = lang == "uk"
    items = [m for m in MEDIA if not tp or m["type"] == tp]
    lead = ({"text": "Критичні тексти й есеї команди та запрошених авторів.",
             "article": "Вагомі публікації про вистави й події Бентег у медіа.",
             "release": "Пресрелізи про прем'єри, гастролі й події, з фото для медіа.",
             "news": "Новини компанії."}.get(tp, "Критичні тексти й есеї команди та запрошених авторів, вагомі публікації про театр і наші пресрелізи.")
            if uk else {"text": "Essays and criticism by our team and guest authors.",
                        "article": "Key coverage of Bentegy productions in the media.",
                        "release": "Press releases on premieres, tours and events, with photos for media.",
                        "news": "News from the company."}.get(tp, "Essays and criticism by our team and guest authors, key coverage of the company and our press releases."))
    tabs = [(None, "Усе" if uk else "All", url("media", lang))] + [(k, MTYPE[k][2 if uk else 3], mtype_url(k, lang)) for k in MTYPE if any(m["type"] == k for m in MEDIA)]
    tabs_h = "".join(f'<a href="{h}"{" aria-current=page" if k == tp else ""}>{e(n)}<sup>{len([m for m in MEDIA if not k or m["type"] == k])}</sup></a>' for k, n, h in tabs)
    fi = next((m for m in items if m["type"] == "text"), None) or next((m for m in items if m["type"] != "article"), None)
    feat = media_feature(fi, lang) if fi else ""
    rest = "".join(media_item(m, lang) for m in items if m is not fi)
    empty = "" if items else f'<p class="empty">{"Перші матеріали зʼявляться найближчим часом." if uk else "First pieces coming soon."}</p>'
    c = SETTINGS["contacts"]
    pitch = f'<aside class="pitch"><p>{"Хочете запропонувати текст про театр — рецензію, есей, інтервʼю?" if uk else "Want to pitch a piece on theatre — a review, an essay, an interview?"}</p><a href="mailto:{c["press"]}">{c["press"]}</a></aside>'
    title = t["nav"]["media"] if not tp else MTYPE[tp][2 if uk else 3]
    body = page_head(t["nav"]["media"], lead) + f"""
<section class="gut max mwrap"><nav class="mtabs" aria-label="{t['nav']['media']}">{tabs_h}</nav>
  {feat}<div class="mlist">{rest}</div>{empty}{pitch}</section>"""
    path = url("media", lang) if not tp else mtype_url(tp, lang)
    alt = url("media", other(lang)) if not tp else mtype_url(tp, other(lang))
    return head(lang, "media", title, lead, (path, alt)) + body + foot(lang)



def photo_pack(m, lang):
    """Downloadable photos attached to a press release."""
    uk = lang == "uk"
    ph = [x for x in (m.get("photos") or []) if x.get("image")]
    if not ph and not m.get("photos_full_url"):
        return ""
    items = []
    for x in ph:
        cap = L(x, "caption", lang)
        cr = bi(x.get("credit", ""), lang)
        items.append(f"""<figure>{img(x['image'], cap or L(m, 'title', lang), "(max-width:640px) 100vw, 33vw")}<figcaption><span>{e(cap)}{f"<small>{'Фото' if uk else 'Photo'}: {e(cr)}</small>" if cr else ''}</span><a href="{e(x['image'])}" download>{'Завантажити' if uk else 'Download'} ↓</a></figcaption></figure>""")
    links = []
    if len(ph) > 1:
        links.append(f'<a class="more" href="/press/{m["slug"]}-foto.zip" download>{"Усі фото .zip" if uk else "All photos .zip"}</a>')
    full = f'<p style="margin-top:24px"><a class="tix" href="{e(m["photos_full_url"])}" target="_blank" rel="noopener">{"Фото в повній якості" if uk else "Full-resolution photos"}</a></p>' if m.get("photos_full_url") else ""
    note = f'<p class="dlnote">{"Фото можна вільно використовувати в публікаціях про подію із зазначенням автора." if uk else "Photos are free to use in coverage of the event, with photo credit."}</p>'
    return f"""<section class="sec gut max" id="foto" style="padding-top:0"><div class="sh"><h2>{'Фото для медіа' if uk else 'Photos for media'}</h2>{''.join(links)}</div>{note}<div class="dl">{''.join(items)}</div>{full}</section>"""

def page_media(m, lang):
    t = T[lang]
    uk = lang == "uk"
    tp = m["type"]
    title = L(m, "title", lang)
    au = authors_html(m, lang)
    p = BY_SLUG.get(m.get("production"))
    cover = img(m.get("cover"), title, "100vw", eager=True)
    cap = L(m, "cover_caption", lang)
    fig = f'<figure class="acov">{cover}{f"<figcaption>{e(cap)}</figcaption>" if cap else ""}</figure>' if cover else ""
    src = ""
    if m.get("source_url") or L(m, "source", lang):
        nm = e(L(m, "source", lang) or m.get("source_url"))
        src = f'<p class="src">{"Вперше опубліковано" if uk else "First published in"}: ' + (f'<a href="{e(m["source_url"])}" target="_blank" rel="noopener">{nm}</a>' if m.get("source_url") else nm) + "</p>"
    bodyh = mdh(L(m, "body", lang))
    prod = f'<a class="aprod" href="{show_url(p["slug"], lang)}">{img(p.get("cover"), L(p, "title", lang), "320px")}<span>{"Вистава" if uk else "Production"}<b>{e(L(p, "title", lang))}</b></span></a>' if p else ""
    related = [x for x in MEDIA if x["slug"] != m["slug"] and (x["type"] == tp or x.get("production") == m.get("production"))][:3]
    more = media_strip(related, lang, "Ще в медіа" if uk else "More", url("media", lang), "Усе з медіа" if uk else "All media")
    kicker = f'<p class="akick"><a href="{mtype_url(tp, lang)}">{e(mlabel(m, lang))}</a><span>{fdate(m["date"], lang)}</span></p>'
    if tp == "text":
        aside = f"""<aside class="ameta"><dl>
  {f'<div><dt>{"Автор" if uk else "Author"}</dt><dd>{au}</dd></div>' if au else ''}
  <div><dt>{"Дата" if uk else "Date"}</dt><dd>{fdate(m['date'], lang)}</dd></div>
  <div><dt>{"Читання" if uk else "Reading"}</dt><dd>{read_min(m, lang)}</dd></div></dl>{prod}</aside>"""
        top = f'<header class="ahead gut max">{kicker}<h1>{e(title)}</h1><p class="alead">{e(L(m, "lead", lang))}</p>{f"<p class=aby>{au}</p>" if au else ""}</header>'
        main = f'<div class="gut max">{fig}</div><div class="atext gut max">{aside}<article class="article">{bodyh}{src}</article></div>'
        cls = "rd rd-text"
    elif tp == "release":
        c = SETTINGS["contacts"]
        city = L(m, "city", lang) or ("Київ" if uk else "Kyiv")
        top = f'<header class="ahead rel gut max"><p class="stamp">{"Пресреліз" if uk else "Press release"}<span>{e(city)}, {fdate(m["date"], lang)}</span></p><h1>{e(title)}</h1></header>'
        aside = f"""<aside class="ameta">{prod}<dl><div><dt>{"Контакт для преси" if uk else "Press contact"}</dt><dd><a href="mailto:{c['press']}">{c['press']}</a></dd></div>
  {f'<div><dt>{"Фото" if uk else "Photos"}</dt><dd><a href="#foto">{"Фото для медіа" if uk else "Photos for media"} ↓</a></dd></div>' if (m.get("photos") or m.get("photos_full_url")) else ''}
  <div><dt>{"Логотипи й тексти" if uk else "Logos & texts"}</dt><dd><a href="{url('press', lang)}">{"Пресматеріали" if uk else "Press kit"} →</a></dd></div></dl>{copy_btn(lang, 'rel-text')}</aside>"""
        main = f'<div class="atext gut max">{aside}<article class="article" id="rel-text"><p class="alead">{e(L(m, "lead", lang))}</p>{bodyh}{src}</article></div>' + (photo_pack(m, lang) if (m.get("photos") or m.get("photos_full_url")) else f'<div class="gut max">{fig}</div>')
        cls = "rd rd-rel"
    else:
        top = f'<header class="ahead news gut max"><p class="nd">{m["date"].day:02d}.{m["date"].month:02d}<small>{m["date"].year}</small></p><div>{kicker}<h1>{e(title)}</h1><p class="alead">{e(L(m, "lead", lang))}</p></div></header>'
        main = f'<div class="gut max">{fig}</div><div class="atext gut max"><aside class="ameta">{prod}</aside><article class="article">{bodyh}{src}</article></div>'
        cls = "rd rd-news"
    body = f'<div class="{cls}">{top}{main}</div>{more}'
    paths = (media_url(m["slug"], lang), media_url(m["slug"], other(lang)))
    return head(lang, "media", title, L(m, "lead", lang), paths, og=img_url(m.get("cover")) if m.get("cover") else "") + body + foot(lang)


def page_team(lang):
    t = T[lang]
    uk = lang == "uk"
    lead = ("Люди, які роблять Театр Бентеги: постійна команда, співпрацівники з вистав і автори, що пишуть про театр."
            if uk else "The people behind Bentegy Theatre: the core team, collaborators on our productions and the authors who write about theatre.")

    def links(x):
        out = []
        for k, lab in (("email", "Email"), ("instagram", "Instagram"), ("website", "Web")):
            v = x.get(k)
            if v:
                out.append(f'<a href="{("mailto:" + v) if k == "email" else e(v)}"{"" if k == "email" else " target=_blank rel=noopener"}>{lab}</a>')
        if x["slug"] == "pavlo-koval" or x.get("producer_page"):
            out.insert(0, f'<a class="pf" href="{url("producer", lang)}">{"Портфоліо" if uk else "Portfolio"} →</a>')
        return f'<p class="tlinks">{"".join(out)}</p>' if out else ""

    def initials(x):
        return "".join(w[0] for w in L(x, "name", lang).split()[:2]).upper() or "—"

    core = [x for x in TEAM if (x.get("group") or "team") == "team"]
    collab = [x for x in TEAM if x.get("group") == "collab"]
    auth = [x for x in TEAM if x.get("group") == "authors"]
    cards = "".join(f"""<article class="tc" id="{x['slug']}"><div class="im">{img(x.get('photo'), L(x, 'name', lang), "(max-width:760px) 50vw, 25vw") or f'<span class="ini">{e(initials(x))}</span>'}</div>
  <p class="tr">{e(L(x, 'role', lang)) if L(x, 'name', lang) else ("Скоро в команді" if uk else "Joining soon")}</p><h3>{e(L(x, 'name', lang) or L(x, 'role', lang))}</h3>{f"<p class='tb'>{e(L(x, 'bio', lang))}</p>" if L(x, 'bio', lang) else ''}{links(x)}</article>""" for x in core)
    rows = "".join(f"""<article class="tl" id="{x['slug']}"><h3>{e(L(x, 'name', lang))}</h3><p class="tr">{e(L(x, 'role', lang))}</p><p class="tb">{e(L(x, 'projects', lang) or L(x, 'bio', lang))}</p>{links(x)}</article>""" for x in collab)
    arows = "".join(f"""<article class="tl" id="{x['slug']}"><h3>{e(L(x, 'name', lang))}</h3><p class="tr">{len(by_author(x['slug']))} {"тексти" if uk else "pieces"}</p><p class="tb">{e(L(x, 'bio', lang))}</p>{links(x)}</article>""" for x in auth)

    def sec(h, inner, cls):
        return f'<section class="sec gut max" style="padding-top:clamp(32px,4vw,56px)"><div class="sh"><h2>{h}</h2></div><div class="{cls}">{inner}</div></section>' if inner else ""
    body = page_head(t["nav"]["team"], lead) + sec("Команда театру" if uk else "Company", cards, "tgrid") + sec("Постійні співпрацівники" if uk else "Collaborators", rows, "tlist") + sec("Автори медіа" if uk else "Contributors", arows, "tlist")
    return head(lang, "team", t["nav"]["team"], lead, (url("team", lang), url("team", other(lang)))) + body + foot(lang)


R["thanks"] = ("/dyakuyemo/", "/en/thank-you/")
R["privacy"] = ("/pryvatnist/", "/en/privacy/")
PRIVACY = load(f"{ROOT}/content/pages/privacy.yml") if os.path.exists(f"{ROOT}/content/pages/privacy.yml") else {}


def page_privacy(lang):
    uk = lang == "uk"
    title = "Політика конфіденційності" if uk else "Privacy policy"
    lead = L(PRIVACY, "lead", lang)
    upd = PRIVACY.get("updated")
    upd_h = f'<p class="mu" style="margin-top:2em;font-size:15px">{"Оновлено" if uk else "Last updated"}: {fdate(upd, lang) if hasattr(upd, "year") else e(str(upd))}</p>' if upd else ""
    body = page_head("Приватність" if uk else "Privacy", lead, small=uk) + f'<section class="gut max" style="padding-bottom:clamp(60px,8vw,120px)"><div class="two"><span></span><div class="prose article">{mdh(L(PRIVACY, "body", lang))}{upd_h}</div></div></section>'
    return head(lang, "privacy", title, lead, (url("privacy", lang), url("privacy", other(lang)))) + body + foot(lang)


def page_404():
    return head("uk", "home", "404", "Сторінку не знайдено / Page not found", ("/", "/en/"), noindex=True) + f"""<header class="ph gut max"><h1>404<span class="dot">.</span></h1>
<div class="lead"><p>Схоже, адреса цієї сторінки змінилася. Почніть з <a href="/">головної</a> або <a href="/afisha/">афіші</a>.</p></div>
<div class="lead"><p lang="en">This address has changed. Go to the <a href="/en/">home page</a> or the <a href="/en/schedule/">schedule</a>.</p></div></header>
<section class="gut max" style="padding-bottom:clamp(60px,8vw,120px)"><div class="bact"><a class="tix big" href="/afisha/">Афіша</a><a class="go" href="/vystavy/">Вистави</a><a class="go" href="/en/">English</a></div></section>""" + foot("uk")


def page_thanks(lang):
    import json
    uk = lang == "uk"
    data = {}
    for p in PRODUCTIONS:
        evs = [ev for ev in EVENTS if ev.get("production") == p["slug"] and not ev.get("date_note_uk")]
        x = {"title": L(p, "title", lang), "url": show_url(p["slug"], lang), "mins": duration_min(p) or 90}
        if evs:
            ev = evs[0]
            st, has_time = ev_start(ev)
            x.update(start=st.isoformat(), has_time=has_time, venue=L(ev, "venue", lang), city=L(ev, "city", lang),
                     when=f"{ev['date'].day} {MONTHS[lang][ev['date'].month - 1]}, {DOW[lang][ev['date'].weekday()]}" + (f" | {ev['time']}" if ev.get("time") else ""),
                     price=ev.get("price") or 0)
        data[p["slug"]] = x
    c = SETTINGS["contacts"]
    lead = ("Оплату отримано. Чекаємо вас на виставі. Квиток і підтвердження прийдуть на пошту, яку ви вказали під час оплати."
            if uk else "Your payment has been received. We look forward to seeing you. Your ticket and confirmation will arrive at the email you used for payment.")
    body = page_head("Дякуємо" if uk else "Thank you", lead) + f"""
<section class="gut max thx"><div id="thx-show" class="tbox" hidden><div class="tbi">
  <div class="tbw"><p class="tbl">{"Ваша вистава" if uk else "Your performance"}</p><p class="tbd" id="thx-title"></p><p class="tbv" id="thx-when"></p><p class="tbv" id="thx-venue"></p></div>
  <div class="tbb"><a class="tix big" id="thx-gcal" target="_blank" rel="noopener" href="#">{"Додати в Google Календар" if uk else "Add to Google Calendar"}</a><a class="tbo" id="thx-ics" href="#" download="bentegy.ics">{"Додати в календар (.ics)" if uk else "Add to calendar (.ics)"} ↓</a></div></div></div>
  <div class="thx-links"><a class="go" href="{c['instagram']}" target="_blank" rel="noopener">Instagram</a><a class="go" href="{url('afisha', lang)}">{T[lang]['all_dates']}</a><a class="go" href="mailto:{c.get('theatre') or c['team']}">{c.get('theatre') or c['team']}</a></div>
</section>
<script>window.BENTEGY_SHOWS={json.dumps(data, ensure_ascii=False)};window.BENTEGY_LANG="{lang}";</script>
<script src="/thanks.js" defer></script>"""
    return head(lang, "thanks", "Дякуємо" if uk else "Thank you", lead, (url("thanks", lang), url("thanks", other(lang))), noindex=True) + body + foot(lang)


GOALS = {
    "uk": ["Сприяння розвитку культури, театрального, перформативного, музичного, візуального, кіно-, літературного й мультидисциплінарного мистецтва в Україні.",
           "Створення умов для розвитку молодих митців і представників культурного, креативного та освітнього секторів.",
           "Підтримка й реалізація культурних, мистецьких і освітніх проєктів, фестивалів, резиденцій, воркшопів і лабораторій.",
           "Підтримка створення індивідуальних і колективних мистецьких творів, зокрема театральних постановок.",
           "Організація освітніх і культурних заходів: лекцій, тренінгів, майстер-класів, відкритих дискусій, читань.",
           "Розвиток критичного мислення, інклюзивності та міждисциплінарної співпраці в культурі й мистецтві.",
           "Сприятливе середовище для співпраці культурних і громадських організацій, держави, бізнесу та міжнародних партнерів."],
    "en": ["Promoting culture and the theatre, performing, musical, visual, film, literary and multidisciplinary arts in Ukraine.",
           "Creating conditions for young artists and people in the cultural, creative and educational sectors.",
           "Supporting and running cultural, artistic and educational projects, festivals, residencies, workshops and laboratories.",
           "Supporting the creation of individual and collective works of art, including theatre productions.",
           "Organising educational and cultural events: lectures, training sessions, masterclasses, open discussions, readings.",
           "Fostering critical thinking, inclusiveness and interdisciplinary cooperation in culture and the arts.",
           "Building a supportive environment for cooperation between cultural and civil society organisations, the state, business and international partners."],
}




# ------------------------------------------------------------------ write
def write(path, content):
    full = os.path.join(OUT, path.strip("/"), "index.html") if path.endswith("/") else os.path.join(OUT, path.strip("/"))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)


def build():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    process_images()
    make_og_images()
    for d in ("fonts", "brand"):
        shutil.copytree(f"{ROOT}/static/{d}", f"{OUT}/{d}")
    shutil.copytree(f"{ROOT}/admin", f"{OUT}/admin")
    shutil.copytree(f"{ROOT}/static/uploads", f"{OUT}/uploads")
    shutil.copytree(f"{ROOT}/static/press", f"{OUT}/press")
    import zipfile
    # bentegy-logos.zip: full brand package (PNG + SVG) is kept in static/press
    for m in MEDIA:
        ph = [x["image"] for x in (m.get("photos") or []) if x.get("image")]
        if m.get("type") == "release" and len(ph) > 1:
            with zipfile.ZipFile(f"{OUT}/press/{m['slug']}-foto.zip", "w", zipfile.ZIP_STORED) as z:
                for im in ph:
                    src = f"{ROOT}/static{im}"
                    if os.path.exists(src):
                        z.write(src, os.path.basename(src))
    css = open(f"{ROOT}/build/fonts.css", encoding="utf-8").read() + open(f"{ROOT}/build/main.css", encoding="utf-8").read()
    open(f"{OUT}/main.css", "w", encoding="utf-8").write(css)
    shutil.copy(f"{ROOT}/build/site.js", f"{OUT}/site.js")
    shutil.copy(f"{ROOT}/build/thanks.js", f"{OUT}/thanks.js")
    os.makedirs(f"{OUT}/img", exist_ok=True)
    shutil.copy(f"{ROOT}/static/brand/sig-logo.png", f"{OUT}/img/sig-logo.png")  # used by the email signature
    urls = []
    for lang in ("uk", "en"):
        for key, fn in (("home", page_home), ("afisha", page_afisha), ("shows", page_shows), ("producer", page_producer),
                        ("about", page_about), ("contact", page_contact),
                        ("support", page_support), ("press", page_press), ("process", page_process)):
            write(url(key, lang), fn(lang))
            urls.append(url(key, lang))
        for p in PRODUCTIONS:
            write(show_url(p["slug"], lang), page_show(p, lang))
            urls.append(show_url(p["slug"], lang))
        if MEDIA:
            write(url("media", lang), page_media_index(lang)); urls.append(url("media", lang))
            for tp in MTYPE:
                if any(m["type"] == tp for m in MEDIA):
                    write(mtype_url(tp, lang), page_media_index(lang, tp)); urls.append(mtype_url(tp, lang))
            for m in MEDIA:
                if m["type"] == "article":
                    continue
                write(media_url(m["slug"], lang), page_media(m, lang)); urls.append(media_url(m["slug"], lang))
        write(url("team", lang), redirect_page(lang, url("about", lang) + "#team"))
        write(url("org", lang), redirect_page(lang, url("about", lang) + "#organisation"))
        write(url("thanks", lang), page_thanks(lang))  # noindex, kept out of the sitemap
        if PRIVACY:
            write(url("privacy", lang), page_privacy(lang)); urls.append(url("privacy", lang))
    write("/404.html", page_404())
    open(f"{OUT}/CNAME", "w").write("bentegy.org\n")
    open(f"{OUT}/.nojekyll", "w").close()
    open(f"{OUT}/robots.txt", "w").write(f"User-agent: *\nDisallow: /admin/\nDisallow: /dyakuyemo/\nDisallow: /en/thank-you/\nSitemap: {SITE}/sitemap.xml\n")
    open(f"{OUT}/sitemap.xml", "w").write('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' +
                                          "".join(f"<url><loc>{SITE}{u}</loc></url>" for u in urls) + "</urlset>")
    print(f"built {len(urls)} pages, {len(IMG_DONE)} images, {len(EVENTS)} events")


if __name__ == "__main__":
    build()
