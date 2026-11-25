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
ALL_EVENTS = []
for p in sorted(glob.glob(f"{ROOT}/content/events/*.yml")):
    d = load(p)
    if not d.get("date"):
        continue
    if isinstance(d["date"], str):
        d["date"] = dt.date.fromisoformat(d["date"])
    # price steps (early bird etc.): the step whose date has come sets the current price; the daily build switches it
    for st in sorted(d.get("price_steps") or [], key=lambda x: str(x.get("from"))):
        f = st.get("from")
        f = dt.date.fromisoformat(f) if isinstance(f, str) else f
        if f and f <= TODAY and st.get("price"):
            d["price"] = st["price"]
            d["price_from"] = f
    if d.get("price") and d.get("price_max") and int(d["price"]) >= int(d["price_max"]):
        d.pop("price_max")
    ALL_EVENTS.append(d)  # every performance, past ones too (structured data on show pages)
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
# «Про нас пишуть»: публікації з press.yml → coverage теж ідуть у Медіа (без дублів за адресою)
_seen = {d.get("url") for d in MEDIA if d["type"] == "article"}
for _i, _x in enumerate(PRESS.get("coverage") or []):
    if not _x.get("url") or _x["url"] in _seen:
        continue
    try:
        _d = dt.date.fromisoformat(str(_x.get("date"))[:10])
    except ValueError:
        continue
    MEDIA.append({"type": "article", "listing": True, "slug": f"coverage-{_i}", "date": _d, "url": _x["url"],
                  "title_uk": _x.get("title_uk") or _x.get("title", ""), "title_en": _x.get("title_en") or _x.get("title", ""),
                  "outlet_uk": _x.get("outlet_uk") or _x.get("outlet", ""), "outlet_en": _x.get("outlet_en") or _x.get("outlet", "")})
    _seen.add(_x["url"])
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
    "article": ("publikatsii", "coverage", "Про нас пишуть", "Coverage", "Публікація", "Coverage"),
    "release": ("presrelizy", "press-releases", "Пресрелізи", "Press releases", "Пресреліз", "Press release"),
    "news": ("novyny", "news", "Новини", "News", "Новина", "News"),
}
NAV = ["afisha", "shows", "process", "media", "about", "contact"]
FOOT = ["support", "opportunities", "press", "producer"]
T = {
    "uk": dict(name="Театр Бентеги", nav=dict(afisha="Афіша", shows="Вистави", process="Процес", producer="Продюсер", about="Про театр", org="Організація", contact="Контакти", support="Підтримати", opportunities="Можливості", press="Преса", media="Медіа", team="Команда"),
               tickets="Квитки", menu="Меню", skip="До змісту", other="EN", soon="Продаж скоро", free="Вхід вільний", sold="Квитки продано",
               all_dates="Уся афіша", all_shows="Усі вистави", next="Найближчі покази", repertoire="Репертуар", produced="Продюсування",
               upcoming_tag="Прем'єра скоро", produced_tag="За продюсування Бентег", nodates="Нові дати зʼявляться найближчим часом. <a href=\"#nl\">Підпишіться на розсилку</a>, щоб дізнатися першими, або стежте за Instagram.",
               genre="Жанр", premiere="Прем'єра", duration="Тривалість", age="Вік", credits="Команда", dates="Дати показів", photos="Фото",
               producer_cta="Співпраця з продюсером", about_producer="Засновник і продюсер", read_more="Детальніше", time="Час",
               legal="Діє через Громадську організацію «В РЕСУРСІ» | код ЄДРПОУ 44977435", sections="Розділи", connect="Звʼязок", org_h="Організація"),
    "en": dict(name="Bentegy Theatre", nav=dict(afisha="Schedule", process="Process", shows="Productions", producer="Producer", about="About", org="Organisation", contact="Contact", support="Support us", opportunities="Opportunities", press="Press", media="Media", team="Team"),
               tickets="Tickets", menu="Menu", skip="Skip to content", other="UA", soon="On sale soon", free="Free entry", sold="Sold out",
               all_dates="Full schedule", all_shows="All productions", next="Coming up", repertoire="Repertoire", produced="Producing",
               upcoming_tag="Premiering soon", produced_tag="Produced by Bentegy", nodates="New dates will be announced soon. <a href=\"#nl\">Subscribe to our newsletter</a> to hear first, or follow us on Instagram.",
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


def plural_uk(n, one, few, many):
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


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


# One graph: every entity has a stable @id shared by both languages; pages reference each other instead of repeating objects.
ORG_ID = SITE + R["home"][0] + "#organization"
PERSON_ID = SITE + R["producer"][0] + "#person"
NGO_ID = SITE + R["about"][0] + "#ngo"  # /orhanizatsiia/ redirects to the «Організація» block of /pro-teatr/
PAVLO = ("Павло Коваль", "Pavlo Koval")
# Pavlo's profiles and pages about him (from the structured-data brief of 24.11.2026); add Wikidata first when it exists
PERSON_SAME_AS = ["https://www.instagram.com/pavel_koval_/"]
PERSON_SUBJECT_OF = ["https://ui.org.ua/news/news-performing-arts/znajomymo-z-uchasnykamy-yczyamy-speczialnoyi-prodyuserskoyi-programy-na-festyvali-sirenos/"]
ORG_WORDS = ("театр", "theatre", "проєкт", "project", "бентег", "bentegy", "студент", "student", "клуб", "club")


def play_id(slug):
    return SITE + show_url(slug, "uk") + "#play"


def org_ref(lang):
    return {"@type": "TheaterGroup", "@id": ORG_ID, "name": T[lang]["name"], "url": SITE + url("home", lang)}


def person_ref(lang):
    return {"@type": "Person", "@id": PERSON_ID, "name": L(PRODUCER, "name", lang)}


def ld_person_name(n, lang):
    return person_ref(lang) if n.strip() in PAVLO else {"@type": "Person", "name": n.strip()}


def ld_org(lang):
    c = SETTINGS["contacts"]
    o = SETTINGS["organization"]
    return {
        "@context": "https://schema.org", "@type": "TheaterGroup", "@id": ORG_ID,
        "name": T[lang]["name"], "alternateName": ["Театр Бентеги", "Bentegy Theatre", "Бентеги"],
        "url": SITE + url("home", lang), "logo": SITE + "/press/bentegy-znak.png",
        "image": SITE + OG_DONE.get(f"bentegy-{lang}", ""), "description": L(SETTINGS, "tagline", lang) if lang == "uk" else L(ABOUT, "lead", lang),
        "email": c.get("theatre") or c["team"], "telephone": c["phone"].replace(" ", ""),
        "contactPoint": [{"@type": "ContactPoint", "contactType": ct, "email": em} for ct, em in (("customer support", c.get("theatre")), ("partnerships", c.get("team")), ("press", c.get("press"))) if em],
        "address": {"@type": "PostalAddress", "addressLocality": "Kyiv", "addressCountry": "UA"},
        "foundingDate": "2025", "founder": person_ref(lang),
        "sameAs": [x for x in (c["instagram"], c["telegram"], c.get("youtube")) if x],
        "parentOrganization": {"@type": "NGO", "@id": NGO_ID, "name": L(o, "name", lang), "taxID": o["edrpou"]},
    }


def ld_about(lang):
    return {"@context": "https://schema.org", "@type": "AboutPage", "url": SITE + url("about", lang), "inLanguage": lang, "mainEntity": org_ref(lang)}


def ld_ngo(lang):
    o = SETTINGS["organization"]
    return {"@context": "https://schema.org", "@type": "NGO", "@id": NGO_ID, "name": L(o, "name", lang),
            "alternateName": ["ГО «В РЕСУРСІ»", "NGO “In the Resource”", "V RESURSI"], "url": SITE + url("about", lang) + "#organisation",
            "taxID": o["edrpou"], "foundingDate": str(o.get("registered") or ""),
            "address": {"@type": "PostalAddress", "streetAddress": "проспект Героїв АТО, 7Б" if lang == "uk" else "7B Heroiv ATO Ave.",
                        "postalCode": "51937", "addressLocality": "Камʼянське" if lang == "uk" else "Kamianske",
                        "addressRegion": "Дніпропетровська обл." if lang == "uk" else "Dnipropetrovsk region", "addressCountry": "UA"},
            "subOrganization": org_ref(lang)}


def ld_person(lang):
    pr = PRODUCER
    uk = lang == "uk"
    bio = " ".join(str(L(pr, "bio", lang)).split())
    first = bio.split(". ")[0].rstrip(".") + "."
    p = {
        "@type": "Person", "@id": PERSON_ID, "name": L(pr, "name", lang),
        "alternateName": [x for x in PAVLO if x != L(pr, "name", lang)],
        "jobTitle": "Театральний продюсер і режисер" if uk else "Theatre producer and director",
        "description": first, "url": SITE + url("producer", lang),
        "email": SETTINGS["contacts"].get("producer") or "pavlo@bentegy.org",
        "worksFor": org_ref(lang),  # founding is stated on the organisation (TheaterGroup.founder); Person has no "founder"
        "nationality": {"@type": "Country", "name": "Україна" if uk else "Ukraine"},
        "alumniOf": {"@type": "CollegeOrUniversity", "name": "Київський національний університет культури і мистецтв" if uk else "Kyiv National University of Culture and Arts"},
        "sameAs": PERSON_SAME_AS,
        "subjectOf": [{"@type": "CreativeWork", "url": u} for u in PERSON_SUBJECT_OF],
    }
    if pr.get("photo") and img_url(pr["photo"]):
        p["image"] = SITE + img_url(pr["photo"])
    return {"@context": "https://schema.org", "@type": "ProfilePage", "url": SITE + url("producer", lang), "inLanguage": lang, "mainEntity": p}


def ld_article(m, lang):
    tp = m.get("type")
    authors = [ld_person_name(person_name(a, lang), lang) for a in (m.get("authors") or [])]
    if L(m, "guest_author", lang):
        authors.append({"@type": "Person", "name": L(m, "guest_author", lang)})
    d = {
        "@context": "https://schema.org", "@type": "NewsArticle" if tp in ("news", "release") else "Article",
        "headline": L(m, "title", lang), "description": short_desc(L(m, "lead", lang), 200),
        "inLanguage": lang, "datePublished": m["date"].isoformat(),
        "mainEntityOfPage": SITE + media_url(m["slug"], lang),
        "publisher": {**org_ref(lang), "logo": {"@type": "ImageObject", "url": SITE + "/press/bentegy-znak.png"}},
    }
    if m.get("cover"):
        d["image"] = SITE + img_url(m["cover"])
    if authors:
        d["author"] = authors[0] if len(authors) == 1 else authors
    else:
        d["author"] = org_ref(lang)
    about = [{"@id": ORG_ID}] + ([{"@id": play_id(m["production"])}] if m.get("production") in BY_SLUG else [])
    d["about"] = about
    return d


def ld_coverage(items, lang):
    """«Про нас пишуть»: each external piece as a NewsArticle about the theatre and, where known, the production."""
    out = []
    for i, m in enumerate(items, 1):
        if not m.get("url"):
            continue
        a = {"@type": "NewsArticle", "headline": re.sub(r"\s*\((?:німецькою|українською|англійською|in [A-Z][a-z]+)\)$", "", L(m, "title", lang)),
             "datePublished": m["date"].isoformat(), "url": m["url"],
             "publisher": {"@type": "Organization", "name": L(m, "outlet", lang)},
             "about": [{"@id": ORG_ID}] + ([{"@id": play_id(m["production"])}] if m.get("production") in BY_SLUG else [])}
        out.append({"@type": "ListItem", "position": len(out) + 1, "item": a})
    return {"@context": "https://schema.org", "@type": "ItemList", "itemListElement": out} if out else None


UK_MONTH = {m: i + 1 for i, m in enumerate(MONTHS["uk"])}


def premiere_date(p):
    """'11 червня 2026, Collider, Київ' -> date(2026, 6, 11); anything else -> None."""
    mt = re.match(r"\s*(\d{1,2})\s+(\S+)\s+(\d{4})", p.get("premiere_uk") or "")
    if mt and mt.group(2) in UK_MONTH:
        return dt.date(int(mt.group(3)), UK_MONTH[mt.group(2)], int(mt.group(1)))
    return None


CREDIT_MAP = (("director", ("direct",)), ("actor", ("perform", "cast")), ("author", ("written", "playwright")), ("composer", ("music", "composer")))
# Play (CreativeWork) has author/creator/contributor; director/actor/composer exist only on events (validator.schema.org)
PLAY_PROP = {"director": "creator", "actor": "contributor", "author": "author", "composer": "contributor"}


def credit_people(p, lang):
    """{'director': [...], 'actor': [...], ...} from the page's credits; organisations and collectives are left out."""
    out = {}
    for c in p.get("credits") or []:
        role = (c.get("role_en") or "").lower()
        names = [n for n in (c.get(f"names_{lang}") or c.get("names") or "").split(",") if n.strip() and not any(w in n.lower() for w in ORG_WORDS)]
        for prop, keys in CREDIT_MAP:
            if any(k in role for k in keys):
                for n in names:
                    ref = ld_person_name(n, lang)
                    if ref not in out.setdefault(prop, []):
                        out[prop].append(ref)
    return out


def ld_play(p, lang):
    """The production itself as a work (Play); НАОСЛІП-type evenings as an Event. People come only from the page's credits."""
    is_ev = p.get("status") == "event"
    title = L(p, "title", lang)
    d = {"@context": "https://schema.org", "@type": "Event" if is_ev else "Play", "@id": play_id(p["slug"]),
         "name": title, "url": SITE + show_url(p["slug"], lang), "description": L(p, "summary", lang)}
    alt = L(p, "title", other(lang))
    if alt and alt != title:
        d["alternateName"] = alt
    if L(p, "genre", lang):
        d["genre"] = L(p, "genre", lang)
    if img_url(p.get("cover")):
        d["image"] = [SITE + img_url(p.get("cover"))]
    pd = premiere_date(p)
    if is_ev:
        parts = [x.strip() for x in (L(p, "premiere", "uk") if lang == "uk" else L(p, "premiere", "en")).split(",")]
        if not pd:
            return None
        d.update({"startDate": pd.isoformat(), "eventStatus": "https://schema.org/EventScheduled",
                  "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode", "organizer": org_ref(lang), "inLanguage": lang})
        if len(parts) >= 3:
            d["location"] = {"@type": "Place", "name": ", ".join(parts[1:-1]),
                             "address": {"@type": "PostalAddress", "addressLocality": parts[-1], "addressCountry": "UA"}}
        else:
            return None
    else:
        d["producer"] = org_ref(lang)
        if pd and pd <= TODAY:  # premiere already happened
            d["datePublished"] = pd.isoformat()
        for prop, people in credit_people(p, lang).items():
            lst = d.setdefault(PLAY_PROP[prop], [])
            lst.extend(x for x in people if x not in lst)
    return d


def ld_event(ev, lang):
    if ev.get("date_note_uk") or ev.get("date_note_en"):
        return None
    p = BY_SLUG.get(ev.get("production"), {})
    st, has_time = ev_start(ev)
    start = st.isoformat()
    mins = duration_min(p)
    end = (st + dt.timedelta(minutes=mins)).isoformat() if has_time and mins else start
    vname, street = venue_parts(ev, lang)
    perf = {"@type": "PerformingGroup", "name": L(p, "performer", lang), "url": SITE + show_url(p["slug"], lang)} if p and L(p, "performer", lang) else org_ref(lang)
    place = {"@type": "Place", "address": {"@type": "PostalAddress", **({"streetAddress": street} if street else {}), "addressLocality": L(ev, "city", lang), "addressCountry": ev.get("country") or "UA"}}
    if not ev.get("venue_tba"):  # a placeholder like «Майданчик оголосимо згодом» must not become a place name
        place = {"@type": "Place", "name": vname or L(ev, "venue", lang), "address": place["address"]}
    d = {
        "@context": "https://schema.org", "@type": "TheaterEvent",
        "name": L(p, "title", lang) or L(ev, "title", lang), "startDate": start, "endDate": end,
        "eventStatus": "https://schema.org/EventScheduled",
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "location": place, "organizer": org_ref(lang), "performer": perf,
        "description": L(p, "summary", lang),
        "inLanguage": lang,
    }
    if p:
        d["@id"] = SITE + show_url(p["slug"], "uk") + "#event-" + ev["date"].isoformat()
        d["workPerformed"] = {"@id": play_id(p["slug"])}
        for prop, people in credit_people(p, lang).items():
            if prop != "author":
                d[prop] = people
        d["url"] = SITE + show_url(p["slug"], lang)
        ims = [SITE + x for x in (img_url(p.get("cover"), 1600), OG_DONE.get(f"{p['slug']}-{lang}")) if x]
        if ims:
            d["image"] = ims
    buy = ev.get("ticket_url") or concert_url(ev)
    if buy and ev.get("price") and ev["date"] >= TODAY:
        vf = ev.get("price_from") or ev.get("sale_start") or (ev["date"] - dt.timedelta(days=30))
        d["offers"] = {"@type": "Offer", "url": buy, "price": str(ev["price"]), "priceCurrency": "UAH",
                       "validFrom": vf.isoformat() if hasattr(vf, "isoformat") else str(vf),
                       "availability": "https://schema.org/SoldOut" if ev.get("status") == "sold_out" else "https://schema.org/InStock"}
    return d


def ld_events(evs, lang):
    return [x for x in (ld_event(ev, lang) for ev in evs) if x]


def ld_production(p, evs, lang):
    """Show page: the work plus every performance of it (past ones included), linked by workPerformed."""
    play = ld_play(p, lang)
    return ([play] if play else []) + ld_events(evs, lang) or None


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
                # Outside the EEA/UK/CH: measurement on by default (visitor can switch it off in the banner). Ad personalisation is never enabled.
                "gtag('consent','default',{ad_storage:'granted',ad_user_data:'granted',ad_personalization:'denied',analytics_storage:'granted'});"
                "try{var c=localStorage.getItem('bentegy-consent');if(c){var g=c==='yes'?'granted':'denied';gtag('consent','update',{analytics_storage:g,ad_storage:g,ad_user_data:g});}}catch(e){}"
                f"gtag('js',new Date());gtag('config','{e(ga)}');"
                + (f"gtag('config','{e(aw)}');window.BENTEGY_ADS={{purchase:'{e(aw)}/{e(SETTINGS.get('ads_conv_purchase') or '')}',ticket:'{e(aw)}/{e(SETTINGS.get('ads_conv_ticket') or '')}'{(",donate:'" + e(aw) + "/" + e(SETTINGS.get('ads_conv_donate')) + "'") if SETTINGS.get('ads_conv_donate') else ''}{(",donation:'" + e(aw) + "/" + e(SETTINGS.get('ads_conv_donation')) + "'") if SETTINGS.get('ads_conv_donation') else ''}}};" if aw else "")
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


def lang_switch(lang, other_href):
    """Always-visible UA/EN toggle: the current language is highlighted, the other one links to this page's translation."""
    items = []
    for code, label, name in (("uk", "UA", "Українська"), ("en", "EN", "English")):
        if code == lang:
            items.append(f'<span class="on" aria-current="true" lang="{code}">{label}</span>')
        else:
            items.append(f'<a href="{e(other_href)}" hreflang="{code}" lang="{code}" title="{name}">{label}</a>')
    return f'<div class="lsw" role="group" aria-label="Мова / Language">{"".join(items)}</div>'


def head(lang, key, title, desc, paths, body_cls="", og="", ld=None, noindex=False, tix=None):
    t = T[lang]
    # header «Квитки»: on a show page with tickets on sale it leads straight to the ticket page (counted as ticket_click)
    tix_a = f'<a class="tix" href="{e(tix["ticket_url"])}" target="_blank" rel="noopener" data-provider="{provider(tix["ticket_url"])}" data-show="{e(tix.get("production") or "")}">{t["tickets"]}</a>' if tix else f'<a class="tix" href="{url("afisha", lang)}">{t["tickets"]}</a>'
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
<link rel="alternate" hreflang="x-default" href="{SITE}{paths[0] if lang == 'uk' else paths[1]}">
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
<link rel="icon" href="/favicon.ico" sizes="48x48"><link rel="icon" href="/brand/icon-192.png" type="image/png" sizes="192x192">
<link rel="apple-touch-icon" href="/brand/apple-touch-icon.png">
<link rel="preload" href="/fonts/inter-tight-cyrillic-900-normal.woff2" as="font" type="font/woff2" crossorigin>
<style>{CSS_INLINE}</style>
</head>
<body class="{body_cls}">
<a class="skip" href="#main">{t['skip']}</a>
<header class="hd" id="hd"><div class="in gut max">
  <a class="mk" href="{url('home', lang)}" aria-label="{t['name']}"><img src="/brand/mark-solid.png" alt="" width="40" height="39"><span class="wm">{'Театр Бентеги' if lang == 'uk' else 'Bentegy Theatre'}</span></a>
  <nav aria-label="{'Головне меню' if lang == 'uk' else 'Main menu'}">{nav}</nav>
  <a class="sup" href="{url('support', lang)}"{" aria-current=page" if key == 'support' else ""}>{t['nav']['support']}</a>
  {lang_switch(lang, paths[1])}
  <details class="burger"><summary>{t['menu']}</summary><div class="panel">{nav}{extra_links(lang, key)}
    <div class="row"><a href="{paths[1]}" hreflang="{o}" lang="{o}">{'English' if lang == 'uk' else 'Українська'}</a>{tix_a}</div></div></details>
  {tix_a}
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
  {newsletter_form(lang)}
  <div class="cols">
    <div><h2>{t['sections']}</h2><ul>{links}</ul></div>
    <div><h2>{t['connect']}</h2><ul>
      <li><small>{'Театр' if lang == 'uk' else 'Theatre'}</small><a href="mailto:{c.get('theatre') or c['team']}">{c.get('theatre') or c['team']}</a></li>
      <li><small>{'Співпраця й команда' if lang == 'uk' else 'Partnerships'}</small><a href="mailto:{c['team']}">{c['team']}</a></li>
      <li><small>{'Преса' if lang == 'uk' else 'Press'}</small><a href="mailto:{c['press']}">{c['press']}</a></li>
      <li><small>{'Продюсер' if lang == 'uk' else 'Producer'}</small><a href="mailto:{c['producer']}">{c['producer']}</a></li>
      <li><small>{'Телефон' if lang == 'uk' else 'Phone'}</small><a href="tel:{c['phone'].replace(' ', '')}">{c['phone']}</a></li>
      <li><small>Telegram</small><a href="{c['telegram']}">@{c['telegram'].rstrip('/').rsplit('/', 1)[-1]}</a></li></ul></div>
    <div><h2>{'Соцмережі' if lang == 'uk' else 'Follow'}</h2><ul>
      <li><a href="{c['instagram']}">Instagram</a></li>{yt_li}</ul></div>
    <div><h2>{t['org_h']}</h2><ul>
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


def newsletter_form(lang, sid="nl"):
    """Brevo double opt-in sign-up (content/site.yml → newsletter.action_uk / action_en). /site.js posts it in the
    background and shows the message; without JS the browser posts to Brevo directly."""
    action = ((SETTINGS.get("newsletter") or {}).get(f"action_{lang}") or "").strip()
    if not action:
        return ""
    uk = lang == "uk"
    ok = ("Дякуємо! Перевірте пошту й підтвердьте підписку за посиланням у листі. Лист може потрапити в «Спам» чи «Промоакції»."
          if uk else "Thank you! Check your inbox and confirm your subscription with the link in the email. It may land in Spam or Promotions.")
    err = ("Сталася помилка. Спробуйте ще раз або напишіть на theatre@bentegy.org."
           if uk else "Something went wrong. Please try again or write to theatre@bentegy.org.")
    return f"""<section class="nl" id="{sid}" aria-labelledby="{sid}-h">
  <div class="nlt"><h2 id="{sid}-h">{'Розсилка' if uk else 'Newsletter'}</h2><p>{'Першими дізнавайтеся про прем’єри, покази й open calls.' if uk else 'Be the first to hear about premieres, performances and open calls.'}</p></div>
  <form class="nlf" method="POST" action="{e(action)}" data-lang="{lang}">
    <div class="nlr"><label class="vh" for="{sid}-e">{'Електронна пошта' if uk else 'Email'}</label><input id="{sid}-e" type="email" name="EMAIL" required autocomplete="email" inputmode="email" placeholder="{'Ваша пошта' if uk else 'Your email'}"><button type="submit" class="tix">{'Підписатися' if uk else 'Subscribe'}</button></div>
    <input type="text" name="email_address_check" value="" tabindex="-1" autocomplete="off" class="nlhp" aria-hidden="true">
    <input type="hidden" name="locale" value="en"><input type="hidden" name="html_type" value="simple">
    <p class="nln">{'Надішлемо лист для підтвердження. Відписатися можна будь-коли, посиланням у кожному листі.' if uk else 'We will send you an email to confirm. Unsubscribe any time with the link in every email.'} <a href="{url('privacy', lang)}#newsletter">{'Як ми працюємо з даними' if uk else 'How we handle your data'}</a></p>
    <p class="nlm" role="status" aria-live="polite" hidden data-ok="{e(ok)}" data-err="{e(err)}"></p>
  </form>
</section>"""


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
    pcr = (("фото " if lang == "uk" else "photo ") + n["image_credit"]) if n.get("image") and n.get("image_credit") else ""
    meta = " | ".join(x for x in (L(n, "kind", lang), f"{d.day:02d}.{d.month:02d}.{d.year}", L(n, "place", lang), pcr) if x)
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


def people_block(lang, inner=False):
    core = [x for x in TEAM if (x.get("group") or "team") == "team" and x.get("photo")]
    if not core:
        return ""
    uk = lang == "uk"
    cards = "".join(f'<a class="pp" href="{url("about", lang)}#{x["slug"]}">{img(x.get("photo"), L(x, "name", lang), "(max-width:760px) 50vw, 20vw")}<b>{e(L(x, "name", lang))}</b><span class="mono">{e(L(x, "role", lang))}</span></a>' for x in core)
    if inner:
        return f'<div class="people5" style="margin-top:clamp(36px,5vw,64px)">{cards}</div>'
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
  {people_block(lang, inner=True)}
</section>"""
    tix_note = (f"Театр Бентеги працює як неприбуткова {e(org['name_uk'][:1].lower() + org['name_uk'][1:])}: кошти від квитків і внесків ідуть на статутну діяльність — нові вистави, гонорари команди, покази й гастролі."
                if uk else
                "Bentegy Theatre operates through the non-profit In the Resource NGO: income from tickets and donations supports its statutory work: new productions, fair pay for the team, performances and touring.")
    body = f"""
<section class="hero" aria-label="{t['name']}">
  {slides}
  <div class="top gut"><a class="mkb" href="{url('home', lang)}" aria-label="{t['name']}"><img src="/brand/mark-solid.png" alt="" width="56" height="55"></a>
    {lang_switch(lang, url('home', o))}<a class="tix" href="{url('afisha', lang)}">{t['tickets']}</a></div>
  <div class="poster gut">
    <div class="now"><p>{e(L(SETTINGS, 'tagline', lang))}</p>
      <a class="cap" id="cap" href="{e(loc_href(first.get('link') or '', lang) or url('shows', lang))}">{'На фото' if lang == 'uk' else 'Pictured'}<b>{e(L(first, 'caption', lang))}</b><span class="ticks" aria-hidden="true">{ticks}</span></a></div>
    <h1 class="vh">{t['name']}</h1><p class="word" aria-hidden="true">{'Бентеги' if lang == 'uk' else 'Bentegy'}<span class="dot">.</span></p>
    <nav class="hmenu" aria-label="{'Розділи сайту' if lang == 'uk' else 'Site sections'}" style="--n:{len(hv)}">{hmenu}</nav>
  </div>
</section>
<section class="sec gut max">
  <div class="sh"><h2>{t['nav']['afisha']}</h2><a class="more" href="{url('afisha', lang)}">{t['all_dates']}</a></div>
  {schedule(EVENTS[:5], lang, group=False)}
</section>
<section class="sec gut max">
  <div class="sh"><h2>{t['nav']['shows']}</h2><a class="more" href="{url('shows', lang)}">{t['all_shows']}</a></div>
  <div class="rep">{''.join(card(p, lang) for p in rep)}</div>
</section>
{who}
{media_strip([m for m in MEDIA if m["type"] in ("text", "article") and not m.get("listing")][:3], lang, t['nav']['media'], url('media', lang), 'Усе з медіа' if lang == 'uk' else 'All media') if MEDIA else ''}
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
{f'<section class="sec gut max" id="visit"><div class="sh"><h2>{"Перед візитом" if lang == "uk" else "Before you go"}</h2></div><div class="two"><span></span><div class="prose">{mdh(L(p, "visit", lang))}</div></div></section>' if L(p, "visit", lang) and nxt else ''}
<section class="sec gut max"><div class="sh"><h2>{('Про подію' if is_ev else 'Про виставу') if lang == 'uk' else 'About'}</h2></div>
  <div class="two"><span></span><div><div class="prose">{mdh(L(p, 'description', lang))}</div>{clips_html(p, lang)}</div></div></section>
{support_box(p, lang)}
{f'<section class="sec gut max" style="padding-top:0"><div class="sh"><h2>{"Історія проєкту" if lang == "uk" else "The story so far"}</h2></div><div class="two"><span></span><div class="prose">{mdh(L(p, "history", lang))}</div></div></section>' if L(p, "history", lang) else ''}
{show_quotes(p, lang)}
{'' if not evs and p.get('status') not in ('repertoire', 'upcoming') else f"""<section class="sec gut max" id="dates" style="padding-top:0"><div class="sh"><h2>{t['dates']}</h2><a class="more" href="{url('afisha', lang)}">{t['all_dates']}</a></div>{schedule(evs, lang, group=False)}</section>"""}
{f'<section class="sec gut max" style="padding-top:0"><div class="sh"><h2>{("Учасники й команда" if lang == "uk" else "Participants and team") if is_ev else t["credits"]}</h2></div><dl class="credits" style="margin-top:28px">{credits}</dl></section>' if credits else ''}
{funding_box(p, lang)}
{f'<section class="sec gut max" style="padding-top:0"><div class="sh"><h2>{t["photos"]}</h2></div><div class="gal">{"".join(gal_items)}</div>{pc}</section>' if gal_items else ''}
{media_strip([m for m in MEDIA if m.get("production") == p["slug"]], lang, t['nav']['media'], url('media', lang), 'Усе з медіа' if lang == 'uk' else 'All media', top0=True)}
{presenters_box(p, lang)}
"""
    paths = (show_url(p["slug"], lang), show_url(p["slug"], other(lang)))
    uk = lang == "uk"
    kind = p.get(f"seo_kind_{lang}") or (("подія" if uk else "event") if is_ev else ("вистава" if uk else "performance"))
    seo_title = f"{title}: {kind} {'в Києві' if uk else 'in Kyiv'}" if p.get("status") in ("repertoire", "upcoming", "produced") else title
    desc = L(p, "summary", lang)
    up = [x for x in evs if x["date"] >= TODAY]
    if up and p.get("status") == "upcoming":
        nx = up[0]
        when = f"{nx['date'].day} {MONTHS[lang][nx['date'].month - 1]}, {L(nx, 'city', lang)}"
        seo_title = f"{title}: {'прем' + chr(39) + 'єра' if uk else 'premiere'} {when}"
        more = (f"Другий показ — {up[1]['date'].day} {MONTHS[lang][up[1]['date'].month - 1]}. " if uk else f"Second performance: {up[1]['date'].day} {MONTHS[lang][up[1]['date'].month - 1]}. ") if len(up) > 1 else ""
        desc = (f"Прем'єра — {when}. " if uk else f"Premiere: {when}. ") + more + desc
    elif up:
        nx = up[0]
        desc = desc.rstrip(".") + ". " + (f"Найближчий показ — {nx['date'].day} {MONTHS[lang][nx['date'].month - 1]}, {L(nx, 'city', lang)}." if uk else f"Next performance: {nx['date'].day} {MONTHS[lang][nx['date'].month - 1]}, {L(nx, 'city', lang)}.")
    sale = [x for x in up if x.get("ticket_url") and (x.get("status") or "soon") not in ("sold_out", "free", "info")]
    return head(lang, "shows", seo_title, desc, paths, og=OG_DONE.get(f"{p['slug']}-{lang}"), ld=ld_production(p, [x for x in ALL_EVENTS if x.get("production") == p["slug"]], lang), tix=sale[0] if sale else None) + body + foot(lang)


def support_box(p, lang):
    sb = p.get("support_box") or {}
    u = sb.get(f"url_{lang}")
    if not sb or not u:
        return ""
    alt = L(sb, "alt", lang)
    alt_h = f'<a class="go" href="{url("support", lang)}">{e(alt)} →</a>' if alt else ""
    return f"""<section class="sbox gut max" aria-label="{e(L(sb, 'title', lang))}"><div class="sbi">
  <div><h2 class="sbt">{e(L(sb, 'title', lang))}</h2><p class="sbx">{e(L(sb, 'text', lang))}</p><p class="sbn">{e(L(sb, 'note', lang))}</p></div>
  <div class="sbb"><a class="tix big" href="{e(u)}" target="_blank" rel="noopener">{e(L(sb, 'button', lang))}</a>{alt_h}</div></div></section>"""


def clips_html(p, lang):
    """Show pages: silent black-and-white loops under the description (production yml → clips; `until` hides a clip after that date)."""
    out = []
    for c in p.get("clips") or []:
        path, until = c.get("video", ""), c.get("until")
        if isinstance(until, str):
            until = dt.date.fromisoformat(until[:10])
        if not path.endswith(".mp4") or poster_of(path) not in IMG_DONE or (until and TODAY > until):
            continue
        cap = L(c, "caption", lang)
        pw, ph = IMG_DONE[poster_of(path)][2]
        out.append(f'<figure class="clip"><video src="{e(path)}" poster="{img_url(poster_of(path), 800)}" width="{pw}" height="{ph}" muted loop playsinline preload="none" data-inview aria-label="{e(cap)}"></video>{f"<figcaption>{e(cap)}</figcaption>" if cap else ""}</figure>')
    return f'<div class="clips n{len(out)}">{"".join(out)}</div>' if out else ""


def funding_box(p, lang):
    fd = p.get("funding") or {}
    logos = fd.get("logos") or []
    if not logos:
        return ""
    def one(x):
        h = int(x.get("h") or 48)
        return f'<img src="{e(x["file"])}" alt="{e(x.get("alt", ""))}" style="--h:{h}px" loading="lazy" decoding="async">'
    eu = "".join(one(x) for x in logos if x.get("eu"))
    rest = "".join(one(x) for x in logos if not x.get("eu"))
    plate = f'<div class="fpl">{f"<div class=fpe>{eu}</div>" if eu else ""}<div class="fpo">{rest}</div></div>'
    txt = f'<p class="fdt">{e(L(fd, "text", lang))}</p>' if L(fd, "text", lang) else ""
    dis = f'<p class="fdd">{e(L(fd, "disclaimer", lang))}</p>' if L(fd, "disclaimer", lang) else ""
    return f"""<section class="sec gut max fund" id="funding" style="padding-top:0"><div class="sh"><h2>{e(L(fd, 'title', lang) or ('Фінансування' if lang == 'uk' else 'Funding'))}</h2></div>
  {plate}{dis}{txt}</section>"""


def presenters_box(p, lang):
    pr = p.get("presenters") or {}
    if not pr or not L(pr, "title", lang) or (lang == "uk" and not pr.get("title_uk")):
        return ""
    rows = "".join(f"<dt>{e(a)}</dt><dd>{e(b)}</dd>" for a, b in (pr.get(f"rows_{lang}") or []))
    mail = pr.get("email", "")
    contact = f'<p class="prc">{"Contact" if lang == "en" else "Контакт"}: <a href="mailto:{e(mail)}">{e(mail)}</a></p>' if mail else ""
    note = f'<p class="sbn">{e(L(pr, "note", lang))}</p>' if L(pr, "note", lang) else ""
    return f"""<section class="sec gut max" id="presenters"><div class="sh"><h2>{e(L(pr, 'title', lang))}</h2></div>
  <p class="sbx" style="margin-top:22px">{e(L(pr, 'text', lang))}</p><dl class="credits" style="margin-top:22px">{rows}</dl>{contact}{note}</section>"""


def show_quotes(p, lang):
    qs = p.get("quotes") or []
    if not qs:
        return ""
    def role(x):
        r = e(L(x, 'role', lang))
        if r and x.get('url'):
            r = f'<a href="{e(x["url"])}" target="_blank" rel="noopener">{r}</a>'
        return (', ' + r) if r else ''
    items = "".join(f"""<blockquote><p>{e(L(x, 'text', lang))}</p><footer>{e(x.get('author', ''))}{role(x)}</footer></blockquote>""" for x in qs)
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
    return head(lang, "producer", name, L(pr, "bio", lang)[:160], (url("producer", lang), url("producer", other(lang))), og=img_url(pr.get("photo")), ld=ld_person(lang)) + body + foot(lang)


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
    return head(lang, "about", t["nav"]["about"], L(a, "lead", lang), (url("about", lang), url("about", other(lang))), ld=[ld_about(lang), ld_ngo(lang)]) + body + foot(lang)


def redirect_page(lang, to):
    return f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="robots" content="noindex"><link rel="canonical" href="{SITE}{to}"><meta http-equiv="refresh" content="0;url={to}"><title>Bentegy</title></head><body><a href="{to}">{to}</a></body></html>"""


def short_link_page(key, cfg):
    """bentegy.org/<key>/ -> target page with UTM tags; noindex, kept out of the sitemap."""
    from urllib.parse import urlencode
    q = {"utm_source": cfg.get("source") or key, "utm_medium": cfg.get("medium") or "link",
         "utm_campaign": cfg.get("campaign") or SETTINGS.get("short_links_campaign") or key}
    if cfg.get("content"):
        q["utm_content"] = cfg["content"]
    clean = cfg.get("to") or "/"
    to = clean + ("&" if "?" in clean else "?") + urlencode(q)
    a = to.replace("&", "&amp;")
    return (f"""<!doctype html><html lang="uk"><head><meta charset="utf-8"><meta name="robots" content="noindex">"""
            f"""<link rel="canonical" href="{SITE}{clean}"><meta http-equiv="refresh" content="0;url={a}">"""
            f"""<script>location.replace({json.dumps(to)})</script><title>Театр Бентеги</title></head>"""
            f"""<body><a href="{a}">bentegy.org{clean}</a></body></html>""")


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
            "Bentegy Theatre operates through the youth NGO “In the Resource”. It is non-profit, non-partisan and independent, and is listed in the Register of Non-Profit Institutions of the State Tax Service of Ukraine.")
    purpose = ("Розбудова активного громадянського суспільства; всебічний розвиток культури й мистецтва в Україні; підтримка театрального, музичного, літературного, візуального й перформативного мистецтва; формування нових культурних практик та інституцій; розвиток неформальної та громадянської освіти, самовизначення й самореалізація молоді, її змістовне дозвілля."
               if uk else
               "Building an active civil society; the comprehensive development of culture and the arts in Ukraine; supporting theatre, music, literary, visual and performing arts; shaping new cultural practices and institutions; developing non-formal and civic education; the self-determination, self-realisation and meaningful leisure of young people.")
    funding = ("Організація існує завдяки грантам, власним надходженням від квитків і партнерствам з майданчиками. Документи організації надаємо на запит."
               if uk else
               "The organisation is funded by grants, box-office income and in-kind partnerships with venues. Organisational documents are available on request.")
    partners = "".join(f"<span>{e(bi(x, lang))}</span>" for x in SETTINGS.get("partners", []))
    body = page_head(t["nav"]["org"], lead) + f"""
<section class="sec gut max" style="padding-top:clamp(32px,4vw,56px)"><div class="sh"><h2>{'Реквізити' if uk else 'Details'}</h2></div><dl class="req">{dl}</dl></section>
<section class="sec gut max" style="padding-top:0"><div class="sh"><h2>{'Мета' if uk else 'Purpose'}</h2></div><div class="two"><span></span><div class="prose"><p>{purpose}</p><p class="mu" style="font-size:15px">{'Статут затверджено рішенням Загальних зборів, протокол № 5 від 1 серпня 2025 року.' if uk else 'The statute was approved by the General Meeting, Protocol No. 5 of 1 August 2025. English text is a courtesy translation.'}</p></div></div></section>
<section class="sec gut max" style="padding-top:0"><div class="sh"><h2>{'Напрями' if uk else 'Activities'}</h2></div><ol class="goals">{goals}</ol></section>
<section class="sec gut max" style="padding-top:0"><div class="sh"><h2>{'Фінансування' if uk else 'Funding'}</h2></div><div class="two"><span></span><div><p class="prose">{funding}</p><div class="chips" style="margin-top:24px">{partners}</div></div></div></section>
"""
    return head(lang, "org", t["nav"]["org"], lead, (url("org", lang), url("org", other(lang))), ld=ld_ngo(lang)) + body + foot(lang)


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


def support_goal(lang):
    """The goal on top of «Підтримати» (support.yml → goal_production / goal_until): (production, its support_box, still live?).
    The donation thank-you page reads the same goal, so the two texts stay in step."""
    gp = BY_SLUG.get(SUPPORT.get("goal_production") or "")
    until = SUPPORT.get("goal_until")
    if isinstance(until, str):
        until = dt.date.fromisoformat(until[:10])
    sb = (gp or {}).get("support_box") or {}
    return gp, sb, bool(gp and sb.get(f"url_{lang}") and (not until or TODAY <= until))


def page_support(lang):
    t = T[lang]
    uk = lang == "uk"
    sp = SUPPORT
    b = sp.get("bank") or {}
    mail = SETTINGS["contacts"]["team"]
    org = SETTINGS["organization"]
    cur = "uah" if uk else "eur"
    sym = "₴" if uk else "€"

    def money(v):
        n = "{:,}".format(int(v or 0)).replace(",", " ")
        return f"{n} {sym}" if uk else f"{sym}{n}"
    # 1. one goal on top: the premiere we raise money for now (support.yml → goal_production / goal_until), then a general donation
    gp, sb, live = support_goal(lang)
    free = sp.get(f"free_url_{cur}")
    if live:
        g_url, g_btn = sb[f"url_{lang}"], L(sb, "button", lang)
        g_k = f'{"Зараз збираємо на" if uk else "Now raising funds for"} <a href="{show_url(gp["slug"], lang)}">{e(L(gp, "title", lang))}</a>'
        g_h, g_x = L(sb, "title", lang), L(sb, "text", lang)
        g_img = img(gp.get("cover"), L(gp, "title", lang), "(max-width:760px) 100vw, 40vw")
    else:
        g_url, g_btn = free, ("Підтримати театр" if uk else "Support the theatre")
        g_k, g_h = ("Онлайн-внесок" if uk else "Donate online"), ("Кожен внесок стає виставою" if uk else "Every gift becomes a performance")
        g_x = "Кожна гривня йде на вистави, команду й покази." if uk else "Every euro goes to productions, the team and performances."
        g_img = img((SETTINGS.get("hero") or [{}])[0].get("image"), t["name"], "(max-width:760px) 100vw, 40vw")
    alt = (f'<a class="go" href="{url("support", "en")}">Donate in euro from abroad →</a>' if uk and sp.get("free_url_eur")
           else f'<a class="go" href="{url("support", "uk")}">Donate in hryvnia →</a>' if not uk and sp.get("free_url_uah") else "")
    hints = [x for x in (sp.get("tiers") or []) if x.get("hint")]
    amts = "".join(f"<div><b>{money(x.get(f'amount_{cur}'))}</b><span>{e(L(x, 'text', lang))}</span></div>" for x in hints)
    goal = ""
    if g_url:
        goal = f"""<section class="sec gut max" style="padding-top:clamp(32px,4vw,56px)"><div class="goal">
  <div class="im">{g_img}</div>
  <div><p class="k">{g_k}</p><h2>{e(g_h)}</h2><p class="x">{e(g_x)}</p>
    <div class="bb"><a class="tix big" href="{e(g_url)}" target="_blank" rel="noopener">{e(g_btn)}</a>{alt}</div>
    {f'<div class="amts" aria-label="{"Що можна зробити внеском" if uk else "What a gift does"}">{amts}</div>' if amts else ''}
    <p class="n">{e(L(sp, 'online_note', lang))}</p></div></div></section>"""
    # 2. other ways: bank transfer (details folded), partners, transparency
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
    bank = ""
    if any(b.get(k) for k in ("iban_uah", "iban_usd", "iban_eur")):
        dl = ""
        for i, (a, v) in enumerate(rows):
            if not v:
                continue
            if a.startswith("IBAN"):
                dl += f'<dt>{a}</dt><dd><span id="iban-{lang}-{i}">{e(v)}</span> {copy_btn(lang, f"iban-{lang}-{i}")}</dd>'
            else:
                dl += f"<dt>{a}</dt><dd>{e(v)}</dd>"
        foreign = "" if not uk else ("<p class='mu' style='margin-top:14px'>Для переказів з-за кордону — реквізити SWIFT на <a href='" + url("support", "en") + "'>англійській версії сторінки</a>.</p>" if (b.get("iban_usd") or b.get("iban_eur")) else "")
        if not uk and b.get("correspondents"):
            corr = "".join(f"<dt>{e(c.get('bank', ''))}</dt><dd>SWIFT {e(c.get('swift', ''))} | Account {e(str(c.get('account', '')))}</dd>" for c in b["correspondents"])
            foreign = f'<details class="corr"><summary>Correspondent banks (EUR)</summary><dl class="req tight">{corr}</dl></details>'
        bank = f"""<div><h3>{'Переказ на рахунок' if uk else 'Bank transfer'}</h3><p>{'Гривневий рахунок ГО «В РЕСУРСІ» у ПриватБанку.' if uk else 'Euro and hryvnia accounts of the NGO “In the Resource” at PrivatBank.'}</p>
  <details class="bankd"><summary>{'Показати реквізити' if uk else 'Show bank details'}</summary><dl class="req tight">{dl}</dl>{foreign}</details></div>"""
    partner = f"""<div><h3>{'Партнерам' if uk else 'Partners'}</h3><p>{'Партнерство сезону чи вистави, підтримка в натуральній формі (майданчик, світло й звук, друк, перевезення, проживання на гастролях) або особиста підтримка з подякою на сайті й у програмках.' if uk else 'Season or production partnership, in-kind support (rehearsal space, lighting and sound, printing, transport, accommodation on tour) or personal patronage, with thanks on the website and in programmes if you wish.'}</p>
  <a class="go" href="mailto:{mail}">{mail}</a></div>"""
    trust = (f"Внески отримує {e(org['name_uk'])}, код ЄДРПОУ {org['edrpou']}. Організація неприбуткова (ознака 0032) і використовує кошти лише на статутну діяльність. Звіт про використання надсилаємо на запит."
             if uk else
             f"Donations are received by {e(org['name_en'])}, EDRPOU {org['edrpou']}, a registered non-profit (code 0032) that uses funds only for its statutory activities. A report on how funds were used is available on request.")
    clear = f"""<div><h3>{'Прозорість' if uk else 'Transparency'}</h3><p>{trust}</p><a class="go" href="{url('about', lang) + '#organisation'}">{'Реквізити організації' if uk else 'Organisation details'}</a></div>"""
    uses = "".join(f"<div><h3>{e(x['title'])}</h3><p>{e(x['text'])}</p></div>" for x in sp.get(f"uses_{lang}", []))
    # 2. Абонемент: monthly gifts through the same WayForPay pages (their monthly «Абонемент» types)
    ab = sp.get("abonement") or {}
    abo = ""
    if ab and free:
        lv = "".join(f'<div class="abl"><p class="k">{e(L(x, "title", lang))}</p><p class="amt">{money(x.get(f"amount_{cur}"))}<small>{"на місяць" if uk else "a month"}</small></p><p>{e(L(x, "text", lang))}</p></div>' for x in ab.get("levels") or [])
        perks = "".join(f"<li>{e(x)}</li>" for x in ab.get(f"perks_{lang}") or [])
        abo = f"""<section class="sec gut max" id="abonement" style="padding-top:0"><div class="sh"><h2>{e(L(ab, 'title', lang))}</h2></div>
  <p class="sbx" style="margin-top:22px;max-width:60ch">{e(L(ab, 'lead', lang))}</p>
  <div class="abo">{lv}</div>
  <div class="abf"><div><p class="k">{"Абонентам" if uk else "Subscribers get"}</p><ul>{perks}</ul></div>
    <div><a class="tix big" href="{e(free)}" target="_blank" rel="noopener">{e(L(ab, 'button', lang))}</a><p class="n">{e(L(ab, 'stop', lang))}</p></div></div></section>"""
    body = page_head(t["nav"]["support"], L(sp, "lead", lang)) + goal + abo + f"""
<section class="sec gut max" style="padding-top:0"><div class="sh"><h2>{'Інші способи' if uk else 'Other ways to help'}</h2></div><div class="alt3">{bank}{partner}{clear}</div></section>
<section class="sec gut max" style="padding-top:0"><div class="sh"><h2>{'На що йдуть кошти' if uk else 'Where it goes'}</h2></div><div class="uses5">{uses}</div></section>
"""
    return head(lang, "support", t["nav"]["support"], L(sp, "lead", lang), (url("support", lang), url("support", other(lang)))) + body + foot(lang)


def press_preview(path):
    """Small PNG for the logo grid on the press page; the full-size file stays behind the Download link."""
    src = f"{ROOT}/static{path}"
    if not path.startswith("/press/") or not os.path.exists(src):
        return path
    name = os.path.basename(path)
    dst = f"{OUT}/press/prev/{name}"
    if not os.path.exists(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        im = Image.open(src)
        im.thumbnail((640, 640), Image.LANCZOS)
        im.convert("RGBA").quantize(64, method=Image.FASTOCTREE).save(dst, optimize=True)
    return f"/press/prev/{name}"


def page_press(lang):
    t = T[lang]
    uk = lang == "uk"
    pr = PRESS
    c = SETTINGS["contacts"]
    texts = f"""<div class="bp"><div class="bh"><h3>{'Коротко' if uk else 'Short'}</h3>{copy_btn(lang, 'bp-short')}</div><div class="prose" id="bp-short"><p>{e(L(pr, 'about_short', lang))}</p></div></div>
<div class="bp"><div class="bh"><h3>{'Детально' if uk else 'Long'}</h3>{copy_btn(lang, 'bp-long')}</div><div class="prose" id="bp-long">{mdh(L(pr, 'about_long', lang))}</div></div>
<div class="bp"><div class="bh"><h3>{'Засновник' if uk else 'Founder'}: {e(L(PRODUCER, 'name', lang))}</h3>{copy_btn(lang, 'bp-bio')}</div><div class="prose" id="bp-bio">{mdh(L(PRODUCER, 'bio', lang))}</div></div>"""
    logos = "".join(f"""<figure class="lg-{x.get('bg', 'light')}"><div class="lgim"><img src="{e(press_preview(x['file']))}" alt="{e(L(x, 'title', lang))}" loading="lazy"></div><figcaption><span>{e(L(x, 'title', lang))}<small>PNG</small></span><a href="{e(x['file'])}" download>{'Завантажити' if uk else 'Download'} ↓</a></figcaption></figure>""" for x in pr.get("logos", []))
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
    n_cov = len([m for m in MEDIA if m["type"] == "article"])
    cov_link = f'''<section class="sec gut max" style="padding-top:0"><div class="sh"><h2>{"Про нас пишуть" if uk else "Coverage"}</h2><a class="more" href="{mtype_url("article", lang)}">{(f"{n_cov} {plural_uk(n_cov, 'публікація', 'публікації', 'публікацій')} у розділі «Медіа»" if uk else f"{n_cov} {'article' if n_cov == 1 else 'articles'} in the Media section")} →</a></div></section>''' if n_cov else ""
    qs = ""
    if pr.get("quotes"):
        qs = '<section class="sec gut max" style="padding-top:0"><div class="sh"><h2>' + ("Відгуки" if uk else "Quotes") + '</h2></div><div class="quotes">' + "".join(
            f"""<blockquote><p>{e(L(x, 'text', lang))}</p><footer>{e(x.get('author', ''))}{', ' if x.get('author') and x.get('outlet') else ''}{f'<a href="{e(x["url"])}" target="_blank" rel="noopener">{e(x.get("outlet", ""))}</a>' if x.get('url') else e(x.get('outlet', ''))}</footer></blockquote>""" for x in pr["quotes"]) + "</div></section>"
    body = page_head(t["nav"]["press"], L(pr, "lead", lang)) + f"""
<section class="gut max"><div class="cgrid"><div class="cr"><div><small>{'Контакт для преси' if uk else 'Press contact'}</small><p>{'Акредитації, інтервʼю, запити на фото й відео.' if uk else 'Accreditation, interviews, photo and video requests.'}</p></div><a href="mailto:{c['press']}">{c['press']}</a></div></div></section>
<section class="sec gut max" style="padding-top:clamp(40px,5vw,72px)"><div class="sh"><h2>{'Про театр' if uk else 'About'}</h2></div><div class="bps">{texts}</div></section>
<section class="sec gut max" style="padding-top:0"><div class="sh"><h2>{'Логотипи' if uk else 'Logos'}</h2><a class="more" href="/press/bentegy-logos.zip" download>{'Повний пакет PNG + SVG .zip' if uk else 'Full package PNG + SVG .zip'}</a></div><div class="dl logos">{logos}</div></section>
{media_strip([m for m in MEDIA if m["type"] == "release"], lang, "Пресрелізи" if uk else "Press releases", "", "", top0=True, sid="releases", limit=99)}
{cov_link}{qs}
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


def media_strip(items, lang, title, more_href, more_label, top0=False, sid="", limit=6):
    if not items:
        return ""
    st = ' style="padding-top:0"' if top0 else ""
    more = f'<a class="more" href="{more_href}">{e(more_label)}</a>' if more_href else ""
    idh = f' id="{sid}"' if sid else ""
    return f'<section class="sec gut max"{idh}{st}><div class="sh"><h2>{e(title)}</h2>{more}</div><div class="mlist">{"".join(media_item(m, lang) for m in items[:limit])}</div></section>'


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
    # «Усе»: тексти й відібрані публікації; повний список згадок у медіа — на вкладці «Про нас пишуть»
    items = [m for m in MEDIA if (m["type"] == tp if tp else (m["type"] != "release" and not m.get("listing")))]
    lead = ({"text": "Критичні тексти й есеї команди та запрошених авторів.",
             "article": "Вагомі публікації про вистави й події Бентег у медіа.",
             "release": "Пресрелізи про прем'єри, гастролі й події, з фото для медіа.",
             "news": "Новини компанії."}.get(tp, "Критичні тексти й есеї команди та запрошених авторів і те, що пишуть про театр. Пресрелізи, логотипи й фото для медіа — у розділі «Преса».")
            if uk else {"text": "Essays and criticism by our team and guest authors.",
                        "article": "Key coverage of Bentegy productions in the media.",
                        "release": "Press releases on premieres, tours and events, with photos for media.",
                        "news": "News from the company."}.get(tp, "Essays and criticism by our team and guest authors, and what others write about the company. Press releases, logos and photos for media are in the Press section."))
    tabs = [(None, "Усе" if uk else "All", url("media", lang))] + [(k, MTYPE[k][2 if uk else 3], mtype_url(k, lang)) for k in MTYPE if k != "release" and any(m["type"] == k for m in MEDIA)]
    tabs_h = "".join(f'<a href="{h}"{" aria-current=page" if k == tp else ""}>{e(n)}<sup>{len([m for m in MEDIA if (m["type"] == k if k else (m["type"] != "release" and not m.get("listing")))])}</sup></a>' for k, n, h in tabs)
    tabs_h += f'<a href="{url("press", lang)}#releases">{"Пресрелізи" if uk else "Press releases"} →</a>'
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
    return head(lang, "media", title, lead, (path, alt), ld=ld_coverage(items, lang) if tp == "article" else None) + body + foot(lang)



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

FIG_RE = re.compile(r"^!\[([^\]]*)\]\((/uploads/[^)\s]+)\)\s*$")


def poster_of(path):
    return path[:-4] + ".jpg" if path.endswith(".mp4") else path


def md_figs(text):
    """Text pages: a paragraph made only of ![caption](/uploads/x.jpg) lines becomes a responsive figure (two or more lines: side by side)."""
    out = []
    for block in re.split(r"\n\s*\n", text or ""):
        lines = [x.strip() for x in block.strip().splitlines() if x.strip()]
        ms = [FIG_RE.match(x) for x in lines]
        if not lines or not all(ms) or not all(poster_of(m_.group(2)) in IMG_DONE for m_ in ms):
            out.append(block)
            continue
        many = len(ms) > 1
        figs = []
        for m_ in ms:
            cap, path = m_.group(1), m_.group(2)
            if path.endswith(".mp4"):  # silent looping clip: plays while on screen (site.js), poster = same name .jpg
                pw, ph = IMG_DONE[poster_of(path)][2]
                media = f'<video src="{e(path)}" poster="{img_url(poster_of(path), 800)}" width="{pw}" height="{ph}" muted loop playsinline preload="none" data-inview aria-label="{e(cap)}"></video>'
            else:
                sz = "(max-width:560px) 100vw, (max-width:860px) 50vw, 360px" if many else "(max-width:860px) 100vw, 720px"
                media = img(path, cap, sz)
            figs.append(f'<figure class="afig">{media}<figcaption>{e(cap)}</figcaption></figure>')
        w, h = IMG_DONE[poster_of(ms[0].group(2))][2]
        cls = "afigs" + ("" if many else " one" + (" pt" if h > w else ""))
        out.append(f'<div class="{cls}">{"".join(figs)}</div>')
    return "\n\n".join(out)


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
    bodyh = mdh(md_figs(L(m, "body", lang)))
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
    return head(lang, "media", title, L(m, "lead", lang), paths, og=img_url(m.get("cover")) if m.get("cover") else "", ld=ld_article(m, lang)) + body + foot(lang)


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
    arows = "".join(f"""<article class="tl" id="{x['slug']}"><h3>{e(L(x, 'name', lang))}</h3><p class="tr">{len(by_author(x['slug']))} {plural_uk(len(by_author(x['slug'])), "текст", "тексти", "текстів") if uk else ("piece" if len(by_author(x['slug'])) == 1 else "pieces")}</p><p class="tb">{e(L(x, 'bio', lang))}</p>{links(x)}</article>""" for x in auth)

    def sec(h, inner, cls):
        return f'<section class="sec gut max" style="padding-top:clamp(32px,4vw,56px)"><div class="sh"><h2>{h}</h2></div><div class="{cls}">{inner}</div></section>' if inner else ""
    body = page_head(t["nav"]["team"], lead) + sec("Команда театру" if uk else "Company", cards, "tgrid") + sec("Постійні співпрацівники" if uk else "Collaborators", rows, "tlist") + sec("Автори медіа" if uk else "Contributors", arows, "tlist")
    return head(lang, "team", t["nav"]["team"], lead, (url("team", lang), url("team", other(lang)))) + body + foot(lang)


R["thanks"] = ("/dyakuyemo/", "/en/thank-you/")
R["opportunities"] = ("/mozhlyvosti/", "/en/opportunities/")
OPPS = load(f"{ROOT}/content/pages/opportunities.yml") if os.path.exists(f"{ROOT}/content/pages/opportunities.yml") else {}


def page_opportunities(lang):
    """Open calls and ways to work together: what is open now, the formats (pitch, castings, co-productions), contact."""
    t = T[lang]
    uk = lang == "uk"
    op = OPPS
    c = SETTINGS["contacts"]
    now = []
    for x in op.get("open") or []:
        dl = x.get("deadline")
        if isinstance(dl, str):
            dl = dt.date.fromisoformat(dl[:10])
        if dl and TODAY > dl:
            continue
        btn = f'<a class="tix" href="{e(x["url"])}" target="_blank" rel="noopener">{e(L(x, "button", lang) or ("Подати заявку" if uk else "Apply"))}</a>' if x.get("url") else ""
        now.append(f'<div class="rw"><h3>{e(L(x, "title", lang))}</h3><div><p>{e(L(x, "text", lang))}</p>{f"<p class=mu>{"Дедлайн" if uk else "Deadline"}: {fdate(dl, lang)}</p>" if dl else ""}{btn}</div></div>')
    socials = "".join(f'<a class="go" href="{e(c[k])}" target="_blank" rel="noopener">{n}</a>' for k, n in (("instagram", "Instagram"),) if c.get(k))
    open_h = (f'<div class="rows" style="margin-top:28px">{"".join(now)}</div>' if now else
              f'<div class="two"><span></span><div><p class="big-lead">{e(L(op, "next", lang))}</p><div class="bact" style="margin-top:28px">{socials}</div></div></div>')
    fm = []
    for x in op.get("formats") or []:
        links = []
        p = BY_SLUG.get(x.get("show") or "")
        if p:
            links.append(f'<a class="go" href="{show_url(p["slug"], lang)}">{e(L(p, "title", lang))} →</a>')
        m = next((m for m in MEDIA if m["slug"] == x.get("media")), None)
        if m and m["type"] != "article":
            links.append(f'<a class="go" href="{media_url(m["slug"], lang)}">{e(mlabel(m, lang))} →</a>')
        case = f'<p style="margin-top:12px;color:var(--mu)">{e(L(x, "case", lang))}</p>' if L(x, "case", lang) else ""
        fm.append(f'<div class="rw"><h3>{e(L(x, "title", lang))}</h3><div><p>{e(L(x, "text", lang))}</p>{case}{f"<div class=bact style=margin-top:16px>{"".join(links)}</div>" if links else ""}</div></div>')
    body = page_head(t["nav"]["opportunities"], L(op, "lead", lang), small=True) + f"""
<section class="sec gut max" style="padding-top:clamp(32px,4vw,56px)"><div class="sh"><h2>{'Зараз відкрито' if uk else 'Open now'}</h2></div>{open_h}</section>
<section class="sec gut max" style="padding-top:0"><div class="sh"><h2>{'Формати' if uk else 'Formats'}</h2></div><div class="rows" style="margin-top:28px">{"".join(fm)}</div></section>
<section class="gut max" style="padding-bottom:clamp(60px,8vw,120px)"><div class="cgrid"><div class="cr"><div><small>{'Пітчинги, копродукції, стажування' if uk else 'Pitches, co-productions, internships'}</small><p>{'Розкажіть про свій проєкт чи про себе — відповімо й запропонуємо формат.' if uk else 'Tell us about your project or about yourself, and we will suggest a format.'}</p></div><a href="mailto:{c['team']}">{c['team']}</a></div></div></section>"""
    return head(lang, "opportunities", t["nav"]["opportunities"], L(op, "lead", lang), (url("opportunities", lang), url("opportunities", other(lang)))) + body + foot(lang)
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


R["subscribed"] = ("/pidpysku-pidtverdzheno/", "/en/subscribed/")


def page_subscribed(lang):
    """Where Brevo sends people after they click the confirmation link. noindex, kept out of the sitemap and menus."""
    uk = lang == "uk"
    c = SETTINGS["contacts"]
    title = "Ви в розсилці" if uk else "You’re subscribed"
    lead = ("Дякуємо, підписку підтверджено. Ми писатимемо, коли буде привід: прем’єра, нові дати чи open call."
            if uk else "Thank you, your subscription is confirmed. We will write when there is news: a premiere, new dates or an open call.")
    body = page_head(title, lead, small=True) + f"""
<section class="gut max" style="padding-bottom:clamp(60px,8vw,120px)"><div class="bact"><a class="tix big" href="{url('afisha', lang)}">{T[lang]['all_dates']}</a><a class="go" href="{url('shows', lang)}">{T[lang]['all_shows']}</a><a class="go" href="{c['instagram']}" target="_blank" rel="noopener">Instagram</a></div></section>"""
    return head(lang, "subscribed", title, lead, (url("subscribed", lang), url("subscribed", other(lang))), noindex=True) + body + foot(lang)


R["thanks_donation"] = ("/dyakuyemo-za-vnesok/", "/en/thank-you-donation/")


def page_thanks_donation(lang):
    """After a WayForPay donation (WayForPay returns here with ?cur=UAH|EUR): thanks, where the gift goes, the show page, socials.
    /thanks-donation.js sends GA4 "donation" and the Ads conversion once per order. noindex, kept out of the sitemap and menus."""
    uk = lang == "uk"
    c = SETTINGS["contacts"]
    gp, sb, live = support_goal(lang)
    show = gp or BY_SLUG.get("under-the-uniform")
    lead = ("Внесок отримано. Він стає репетиціями, світлом і гонорарами для людей, які створюють вистави. Підтвердження оплати WayForPay надішле на вашу пошту."
            if uk else "Your gift has arrived. It becomes rehearsals, light on stage and fair pay for the people who make the work. WayForPay will email you a payment confirmation.")
    if live:
        g_h, g_x = L(gp, "title", lang), L(sb, "text", lang)
        g_img = img(gp.get("cover"), L(gp, "title", lang), "(max-width:760px) 100vw, 40vw")
    else:
        g_h = "Нові вистави" if uk else "New productions"
        g_x = "Кожна гривня йде на вистави, команду й покази." if uk else "Every euro goes to productions, the team and performances."
        g_img = img((SETTINGS.get("hero") or [{}])[0].get("image"), T[lang]["name"], "(max-width:760px) 100vw, 40vw")
    btn = (f'<a class="tix big" href="{show_url(show["slug"], lang)}">{("До вистави «" + L(show, "title", lang) + "»") if uk else ("Go to " + L(show, "title", lang))}</a>' if show else "")
    socials = "".join(f'<a class="go" href="{e(c[k])}" target="_blank" rel="noopener">{n}</a>' for k, n in (("instagram", "Instagram"), ("youtube", "YouTube")) if c.get(k))
    body = page_head("Дякуємо" if uk else "Thank you", lead) + f"""
<section class="sec gut max" style="padding-top:clamp(32px,4vw,56px)"><div class="goal">
  <div class="im">{g_img}</div>
  <div><p class="k">{"Ваш внесок іде на" if uk else "Your gift goes to"}</p><h2>{e(g_h)}</h2><p class="x">{e(g_x)}</p>
    <div class="bb">{btn}</div>
    <p class="n">{"Хочете підтримувати щомісяця?" if uk else "Want to give every month?"} <a href="{url('support', lang)}#abonement">{"Абонемент" if uk else "Monthly subscription"} →</a></p>
    <p class="n">{"Стежте за роботою команди:" if uk else "Follow the team at work:"}</p><div class="bb" style="margin-top:14px">{socials}</div></div></div></section>
<script src="/thanks-donation.js" defer></script>"""
    return head(lang, "thanks_donation", "Дякуємо за внесок" if uk else "Thank you for your gift", lead,
                (url("thanks_donation", lang), url("thanks_donation", other(lang))), noindex=True) + body + foot(lang)


GOALS = {
    "uk": ["Сприяння розвитку культури, театрального, перформативного, музичного, візуального, кіно-, літературного й мультидисциплінарного мистецтва в Україні.",
           "Створення умов для розвитку молодих митців і представників культурного, креативного та освітнього секторів.",
           "Підтримка й реалізація культурних, мистецьких і освітніх проєктів, фестивалів, резиденцій, воркшопів і лабораторій.",
           "Підтримка створення індивідуальних і колективних мистецьких творів, зокрема театральних постановок.",
           "Організація освітніх і культурних заходів: лекцій, тренінгів, майстер-класів, відкритих дискусій, читань.",
           "Розвиток критичного мислення, інклюзивності та міждисциплінарної співпраці в культурі й мистецтві.",
           "Сприятливе середовище для співпраці культурних і громадських організацій, держави, бізнесу та міжнародних партнерів."],
    "en": ["Promoting the development of culture and of theatre, performing, musical, visual, film, literary and multidisciplinary arts in Ukraine.",
           "Creating conditions for the development of young artists and people working in the cultural, creative and educational sectors.",
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
    for d in ("fonts", "brand", "funders"):
        shutil.copytree(f"{ROOT}/static/{d}", f"{OUT}/{d}")
    shutil.copytree(f"{ROOT}/admin", f"{OUT}/admin")
    shutil.copytree(f"{ROOT}/static/uploads", f"{OUT}/uploads")
    shutil.copytree(f"{ROOT}/static/press", f"{OUT}/press")
    shutil.copy(f"{ROOT}/static/favicon.ico", f"{OUT}/favicon.ico")
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
    shutil.copy(f"{ROOT}/build/thanks-donation.js", f"{OUT}/thanks-donation.js")
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
                if tp == "release":  # пресрелізи тепер на сторінці «Преса»; стара адреса веде туди
                    write(mtype_url(tp, lang), redirect_page(lang, url("press", lang) + "#releases"))
                elif any(m["type"] == tp for m in MEDIA):
                    write(mtype_url(tp, lang), page_media_index(lang, tp)); urls.append(mtype_url(tp, lang))
            for m in MEDIA:
                if m["type"] == "article":
                    continue
                write(media_url(m["slug"], lang), page_media(m, lang)); urls.append(media_url(m["slug"], lang))
        write(url("team", lang), redirect_page(lang, url("about", lang) + "#team"))
        write(url("org", lang), redirect_page(lang, url("about", lang) + "#organisation"))
        write(url("thanks", lang), page_thanks(lang))  # noindex, kept out of the sitemap
        write(url("thanks_donation", lang), page_thanks_donation(lang))  # noindex, kept out of the sitemap
        write(url("subscribed", lang), page_subscribed(lang))  # noindex, kept out of the sitemap
        if PRIVACY:
            write(url("privacy", lang), page_privacy(lang)); urls.append(url("privacy", lang))
        if OPPS:
            write(url("opportunities", lang), page_opportunities(lang)); urls.append(url("opportunities", lang))
    for key, cfg in (SETTINGS.get("short_links") or {}).items():  # noindex, kept out of the sitemap
        write(f"/{key}/", short_link_page(key, cfg or {}))
    write("/404.html", page_404())
    open(f"{OUT}/CNAME", "w").write("bentegy.org\n")
    open(f"{OUT}/.nojekyll", "w").close()
    open(f"{OUT}/robots.txt", "w").write(f"User-agent: *\nDisallow: /admin/\nDisallow: /dyakuyemo/\nDisallow: /en/thank-you/\nDisallow: /dyakuyemo-za-vnesok/\nDisallow: /en/thank-you-donation/\nDisallow: /pidpysku-pidtverdzheno/\nDisallow: /en/subscribed/\nSitemap: {SITE}/sitemap.xml\n")
    open(f"{OUT}/sitemap.xml", "w").write('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' +
                                          "".join(f"<url><loc>{SITE}{u}</loc></url>" for u in urls) + "</urlset>")
    print(f"built {len(urls)} pages, {len(IMG_DONE)} images, {len(EVENTS)} events")


if __name__ == "__main__":
    build()
