# -*- coding: utf-8 -*-
"""
🌐 JAHANTAB | جهان‌تاب
اخبار مهم و ویژه جنگ ایران و آمریکا و اخبار مرتبط

• اجرای خودکار هر ۵ دقیقه
• فقط منابع داخلی مجوزدار
• فقط اخبار مهم و ویژه
• عکس در ابتدای خبر
• دکمهٔ شیشه‌ای «مشاهده خبر» در پایین
• «جهان‌تاب | آخرین تحولات جهان» فقط در انتهای خبر
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

try:
    import feedparser
except ImportError:
    feedparser = None

try:
    from PIL import Image
except ImportError:
    Image = None


# ════════════════════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════════════════════

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = (
    os.getenv("CHAT_ID", "").strip()
    or os.getenv("CHANNEL", "").strip()
    or "@jahantab_news"
)

# ── زمان‌بندی ────────────────────────────────────────────────
RUN_INTERVAL_SEC   = int(os.getenv("RUN_INTERVAL_SEC", "300"))     # ۵ دقیقه
MAX_AGE_HOURS      = int(os.getenv("MAX_AGE_HOURS", "12"))
URGENT_HOURS       = int(os.getenv("URGENT_HOURS", "6"))

# ── آستانه‌های سختگیرانه ─────────────────────────────────────
MIN_SCORE          = int(os.getenv("MIN_SCORE", "20"))
URGENT_MIN_SCORE   = int(os.getenv("URGENT_MIN_SCORE", "14"))
MAX_POSTS_PER_RUN  = int(os.getenv("MAX_POSTS_PER_RUN", "3"))
URGENT_SLOTS       = int(os.getenv("URGENT_SLOTS", "2"))

MAX_ITEMS_PER_SOURCE = int(os.getenv("MAX_ITEMS_PER_SOURCE", "15"))
HTTP_TIMEOUT         = int(os.getenv("HTTP_TIMEOUT", "20"))
POST_DELAY           = float(os.getenv("POST_DELAY", "2"))

DUP_TITLE_SIM     = float(os.getenv("DUP_TITLE_SIM", "0.62"))
DUP_CONTENT_SIM   = float(os.getenv("DUP_CONTENT_SIM", "0.42"))
DUP_IMPORTANT_SIM = float(os.getenv("DUP_IMPORTANT_SIM", "0.40"))

BASE_DIR         = os.path.dirname(os.path.abspath(__file__))
SENT_FILE        = os.path.join(BASE_DIR, os.getenv("SENT_FILE", "sent_links.txt"))
SENT_TITLES_FILE = os.path.join(BASE_DIR, os.getenv("SENT_TITLES_FILE", "sent_titles.txt"))
SENT_EVENTS_FILE = os.path.join(BASE_DIR, os.getenv("SENT_EVENTS_FILE", "sent_events.txt"))
LOGO_FILE        = os.path.join(BASE_DIR, os.getenv("LOGO_FILE", "logo.jpg"))

CHANNEL_SIGNATURE = "🌐 <b>جهان‌تاب</b> | آخرین تحولات جهان"
PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


# ════════════════════════════════════════════════════════════
# LOGGING
# ════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("JAHANTAB")


# ════════════════════════════════════════════════════════════
# HTTP SESSION
# ════════════════════════════════════════════════════════════

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0 Safari/537.36 JAHANTAB/8.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/*;q=0.8",
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.5",
})


# ════════════════════════════════════════════════════════════
# DATA MODEL
# ════════════════════════════════════════════════════════════

@dataclass(slots=True)
class Source:
    name: str
    domain: str
    url: str


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    domain: str
    description: str = ""
    image: str = ""
    published: Optional[datetime] = None
    score: int = 0
    matched: list[str] = field(default_factory=list)
    urgency: int = 0
    is_urgent: bool = False
    event_key: str = ""
    topic: str = ""
    flag: str = ""


# ════════════════════════════════════════════════════════════
# SOURCES  —  فقط منابع داخلی مجوزدار
# ════════════════════════════════════════════════════════════

SOURCES: list[Source] = [
    Source("تابناک",                "tabnak.ir",           "https://www.tabnak.ir/"),
    Source("فرارو",                 "fararu.com",          "https://fararu.com/"),
    Source("همشهری آنلاین",         "hamshahrionline.ir",  "https://www.hamshahrionline.ir/"),
    Source("آخرین خبر",             "akharinkhabar.ir",    "https://akharinkhabar.ir/"),
    Source("خبر فوری",              "khabarfoori.com",     "https://www.khabarfoori.com/"),
    Source("خبرآنلاین",             "khabaronline.ir",     "https://www.khabaronline.ir/"),
    Source("مهر",                   "mehrnews.com",        "https://www.mehrnews.com/"),
    Source("فارس",                  "farsnews.ir",         "https://www.farsnews.ir/"),
    Source("ایرنا",                 "irna.ir",             "https://www.irna.ir/"),
    Source("ایسنا",                 "isna.ir",             "https://www.isna.ir/"),
    Source("صدا و سیما",            "iribnews.ir",         "https://www.iribnews.ir/"),
    Source("باشگاه خبرنگاران جوان", "yjc.ir",              "https://www.yjc.ir/"),
    Source("تسنیم",                 "tasnimnews.com",      "https://www.tasnimnews.com/fa"),
    Source("عصر ایران",             "asriran.com",         "https://www.asriran.com/"),
    Source("مشرق نیوز",             "mashreghnews.ir",     "https://www.mashreghnews.ir/"),
    Source("انتخاب",                "entekhab.ir",         "https://www.entekhab.ir/"),
    Source("الف",                   "alef.ir",             "https://www.alef.ir/"),
    Source("ایلنا",                 "ilna.ir",             "https://www.ilna.ir/"),
]

TRUSTED_SOURCES = {"ایرنا", "ایسنا", "فارس", "تسنیم", "مهر", "صدا و سیما"}


# ════════════════════════════════════════════════════════════
# KEYWORDS  —  تمرکز ویژه روی جنگ ایران و آمریکا
# ════════════════════════════════════════════════════════════

# ── هسته اصلی: جنگ ایران و آمریکا (وزن بالا) ────────────────
IRAN_US_WAR = {
    "ایران": 8,
    "جمهوری اسلامی": 8,
    "آمریکا": 9,
    "ایالات متحده": 9,
    "واشنگتن": 7,
    "ترامپ": 8,
    "کاخ سفید": 7,
    "پنتاگون": 9,
    "سنتکام": 10,
    "سنت‌کام": 10,
    "نیروهای آمریکایی": 11,
    "پایگاه آمریکایی": 12,
    "پایگاه آمریکا": 12,
    "حمله ایران به آمریکا": 20,
    "حمله آمریکا به ایران": 20,
    "پاسخ ایران": 15,
    "پاسخ موشکی ایران": 18,
    "حمله موشکی": 14,
    "حمله پهپادی": 14,
    "سپاه پاسداران": 11,
    "سپاه": 8,
    "ارتش ایران": 10,
    "موشک بالستیک": 12,
    "موشک کروز": 12,
    "موشک هایپرسونیک": 13,
    "پدافند هوایی": 10,
    "پدافند": 8,
    "رادار": 7,
    "شبکه الدفاع": 8,
    "تحریم نفتی": 8,
    "تحریم بانکی": 7,
    "تحریم جدید": 6,
    "قطعنامه": 6,
    "شورای امنیت": 6,
    "برجام": 7,
    "توافق هسته‌ای": 8,
    "آژانس انرژی اتمی": 7,
    "غنی‌سازی": 8,
    "غنی سازی": 8,
    "بمب اتمی": 10,
    "سلاح هسته‌ای": 10,
    "پاسخ قاطع": 10,
    "انتقام": 10,
    "عملیات وعده صادق": 15,
    "وعده صادق": 14,
    "عملیات نظامی": 10,
    "رزمایش": 7,
    "مانور نظامی": 7,
    "ناو آمریکایی": 12,
    "ناوگروه": 10,
    "نیروی دریایی سپاه": 11,
    "نیروی دریایی ارتش": 9,
    "جنگ": 12,
    "درگیری": 10,
    "تشدید تنش": 8,
}

# ── خلیج فارس و تنگه هرمز ───────────────────────────────────
GULF_HORMUZ = {
    "خلیج فارس": 12,
    "خلیج‌فارس": 12,
    "تنگه هرمز": 15,
    "تنگه‌ی هرمز": 15,
    "هرمز": 9,
    "دریای عمان": 9,
    "باب المندب": 9,
    "باب‌المندب": 9,
    "دریای سرخ": 8,
    "خلیج عدن": 8,
    "توقیف نفتکش": 12,
    "ربایش نفتکش": 12,
    "نفتکش": 8,
    "کشتی تجاری": 7,
    "بسته شدن تنگه": 16,
    "بازگشایی تنگه": 13,
    "عبور ناو": 9,
    "بندرعباس": 7,
    "بوشهر": 6,
    "قشم": 7,
    "هرمزگان": 7,
    "خارک": 8,
}

# ── محور مقاومت ─────────────────────────────────────────────
RESISTANCE_AXIS = {
    "حزب الله": 12,
    "حزب‌الله": 12,
    "نصرالله": 10,
    "لبنان": 9,
    "بیروت": 8,
    "ضاحیه": 9,
    "جنوب لبنان": 9,
    "حماس": 12,
    "جهاد اسلامی": 12,
    "سرایا القدس": 10,
    "فلسطین": 9,
    "غزه": 11,
    "نوار غزه": 11,
    "رژیم صهیونیستی": 9,
    "اسرائیل": 9,
    "نتانیاهو": 8,
    "قدس": 8,
    "کرانه باختری": 8,
    "انصارالله": 12,
    "انصار الله": 12,
    "حوثی": 10,
    "حوثی‌ها": 10,
    "یمن": 9,
    "صنعا": 8,
    "حشد الشعبی": 12,
    "حشدالشعبی": 12,
    "الحشد الشعبی": 12,
    "کتائب حزب الله": 10,
    "نجباء": 8,
    "عراق": 7,
    "بغداد": 7,
    "محور مقاومت": 15,
    "مقاومت اسلامی": 13,
    "مقاومت": 9,
    "سوریه": 7,
    "دمشق": 7,
}

# ── رویدادهای مهم ───────────────────────────────────────────
MAJOR_EVENTS = {
    "آتش بس": 12, "آتش‌بس": 12,
    "پایان جنگ": 14, "آغاز جنگ": 18, "اعلام جنگ": 18,
    "ورود به جنگ": 15, "گسترش جنگ": 12,
    "تشدید درگیری": 10, "تشدید تنش": 8,
    "حمله گسترده": 14, "عملیات گسترده": 13,
    "حمله مستقیم": 15, "حمله متقابل": 13,
    "پاسخ موشکی": 14, "پاسخ نظامی": 11,
    "ترور": 12, "ترور شد": 12,
    "شهادت": 10, "به شهادت رسید": 12,
    "انفجار": 10,
    "سرنگونی": 11,
}

# ── ترم‌های فوری ────────────────────────────────────────────
URGENT_TERMS = {
    "فوری": 10, "خبر فوری": 15,
    "لحظاتی پیش": 13, "دقایقی پیش": 13,
    "همین الان": 13,
    "هم‌اکنون": 13, "هم اکنون": 13,
    "خبر مهم": 10, "لحظه به لحظه": 8,
    "تازه‌ترین": 6, "تازه ترین": 6,
    "اختصاصی": 8,
    "تکمیلی": 5,
}

# ── تلفات ───────────────────────────────────────────────────
CASUALTY_TERMS = {
    "کشته": 9, "کشته‌ها": 9, "کشته شد": 10,
    "شهید": 9, "شهید شد": 10,
    "مجروح": 7, "زخمی": 7,
    "تلفات": 9, "تلفات سنگین": 12,
    "اسیر": 8,
}

# ── تحلیلی (امتیاز منفی) ────────────────────────────────────
ANALYSIS_TERMS = {
    "تحلیل": -10, "یادداشت": -12,
    "کارشناس": -8, "کارشناسان": -8,
    "گفتگو": -8, "گفت‌وگو": -8, "گفت و گو": -8,
    "بررسی": -7, "چرا": -7, "چگونه": -7,
    "روایت": -6,
    "تحلیلگر": -10, "تحلیل‌گر": -10,
    "سناریو": -9,
    "پیش بینی": -9, "پیش‌بینی": -9,
    "آینده جنگ": -8,
    "نگاهی به": -7,
    "گزارش تحلیلی": -12,
    "پرونده": -6,
}

# ── حذف کامل (نامرتبط) ──────────────────────────────────────
EXCLUDE_TERMS = {
    "ورزش": -30, "فوتبال": -30, "والیبال": -30,
    "لیگ": -25, "تیم ملی": -25,
    "سینما": -30, "تلویزیون": -30, "موسیقی": -30,
    "بازیگر": -30, "فیلم": -25,
    "سلامت": -20, "پزشکی": -20, "کرونا": -25,
    "کنکور": -30, "دانشگاه": -20, "دانشجو": -20,
    "هواشناسی": -20, "بارش": -20, "برف": -20,
    "بورس": -20, "دلار": -15, "طلا": -15, "سکه": -15,
    "خودرو": -25, "مسکن": -25, "اجاره": -20,
    "اقتصاد": -15, "بازنشستگی": -20, "یارانه": -15,
    "طبیعت": -20, "حیات وحش": -25,
    "آشپزی": -30, "سفر": -25, "گردشگری": -25,
    "فناوری": -20, "موبایل": -25, "اینترنت": -15,
}

ALL_SCORING_DICTS = [
    IRAN_US_WAR, GULF_HORMUZ, RESISTANCE_AXIS,
    MAJOR_EVENTS, URGENT_TERMS, CASUALTY_TERMS,
    ANALYSIS_TERMS, EXCLUDE_TERMS,
]

STOPWORDS = {
    "از", "به", "در", "با", "برای", "که", "و", "را",
    "این", "آن", "یک", "های", "کرد", "شد", "است", "بر",
    "تا", "وی", "او", "نیز", "اما", "هم", "یا", "پس",
}

_IMPORTANT_KEYWORDS = tuple(
    list(IRAN_US_WAR) + list(GULF_HORMUZ) + list(RESISTANCE_AXIS) + list(MAJOR_EVENTS)
)

TOPIC_FLAGS = {
    "iran_us":    ("🇮🇷", "جنگ ایران و آمریکا"),
    "gulf":       ("🌊", "خلیج فارس و تنگه هرمز"),
    "hezbollah":  ("🇱🇧", "حزب‌الله لبنان"),
    "palestine":  ("🇵🇸", "فلسطین و غزه"),
    "yemen":      ("🇾🇪", "انصارالله یمن"),
    "iraq":       ("🇮🇶", "حشد الشعبی عراق"),
    "resistance": ("✊", "محور مقاومت"),
}

TOPIC_KEYWORDS = {
    "iran_us":    list(IRAN_US_WAR.keys()),
    "gulf":       list(GULF_HORMUZ.keys()),
    "hezbollah":  ["حزب الله", "حزب‌الله", "نصرالله", "لبنان", "بیروت"],
    "palestine":  ["حماس", "فلسطین", "غزه", "قدس", "جهاد اسلامی", "نتانیاهو"],
    "yemen":      ["انصارالله", "انصار الله", "حوثی", "یمن", "صنعا"],
    "iraq":       ["حشد الشعبی", "حشدالشعبی", "کتائب حزب الله", "نجباء", "بغداد"],
}


# ════════════════════════════════════════════════════════════
# TEXT UTILITIES
# ════════════════════════════════════════════════════════════

_AR_TO_FA = {
    "ي": "ی", "ى": "ی", "ك": "ک",
    "ۀ": "ه", "ة": "ه", "ؤ": "و",
    "إ": "ا", "أ": "ا", "ٱ": "ا",
    "ـ": "",
    "\u200c": " ", "\u200f": " ", "\u200e": " ", "\ufeff": " ",
}


def normalize(text: Optional[str]) -> str:
    if not text:
        return ""
    text = html.unescape(str(text))
    for a, b in _AR_TO_FA.items():
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text).strip().lower()


def clean_html(text: Optional[str]) -> str:
    if not text:
        return ""
    soup = BeautifulSoup(str(text), "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return re.sub(r"\s+", " ", html.unescape(soup.get_text(" ", strip=True))).strip()


def shorten(text: str, max_len: int) -> str:
    text = clean_html(text)
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" .،؛:") + "…"


def to_persian_digits(text: str) -> str:
    return str(text).translate(PERSIAN_DIGITS)


def escape(text: str) -> str:
    return html.escape(str(text or ""), quote=False)


# ════════════════════════════════════════════════════════════
# URL UTILITIES
# ════════════════════════════════════════════════════════════

def canonical_url(url: str) -> str:
    if not url:
        return ""
    try:
        p = urlparse(url)
        scheme = (p.scheme or "https").lower()
        netloc = p.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = p.path or "/"
        if path != "/" and path.endswith("/"):
            path = path[:-1]
        return urlunparse((scheme, netloc, path, "", "", ""))
    except Exception:
        return url.strip()


def same_domain(url: str, domain: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        domain = domain.lower().removeprefix("www.")
        return host == domain or host.endswith("." + domain)
    except Exception:
        return False


# ════════════════════════════════════════════════════════════
# HTTP
# ════════════════════════════════════════════════════════════

def safe_get(url: str, **kwargs) -> Optional[requests.Response]:
    try:
        timeout = kwargs.pop("timeout", HTTP_TIMEOUT)
        return SESSION.get(url, timeout=timeout, allow_redirects=True, **kwargs)
    except requests.RequestException as e:
        log.warning("GET failed │ %s │ %s", url, e)
        return None


# ════════════════════════════════════════════════════════════
# FINGERPRINTS
# ════════════════════════════════════════════════════════════

def _words(text: str) -> set[str]:
    words = re.findall(r"[\wآ-ی]+", normalize(text))
    return {w for w in words if len(w) > 2 and w not in STOPWORDS}


def title_fingerprint(title: str) -> str:
    text = normalize(title)
    text = re.sub(r"[^\w\sآ-ی]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def title_hash(title: str) -> str:
    return hashlib.sha1(normalize(title).encode("utf-8")).hexdigest()[:16]


def event_fingerprint(item: "NewsItem") -> str:
    text = normalize(f"{item.title} {item.description}")
    important = sorted({kw for kw in _IMPORTANT_KEYWORDS if normalize(kw) in text})
    content = sorted(_words(text))[:15]
    raw = "|".join(important) + "::" + "|".join(content)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


# ════════════════════════════════════════════════════════════
# PERSISTENT STORAGE
# ════════════════════════════════════════════════════════════

def _load_lines(path: str) -> set[str]:
    if not os.path.exists(path):
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return {line.strip() for line in f if line.strip()}
    except OSError as e:
        log.warning("Cannot read %s │ %s", path, e)
        return set()


def load_sent_links() -> set[str]:
    return {canonical_url(x) for x in _load_lines(SENT_FILE)}


def load_sent_titles() -> set[str]:
    return _load_lines(SENT_TITLES_FILE)


def load_sent_events() -> set[str]:
    return _load_lines(SENT_EVENTS_FILE)


def save_sent_item(item: "NewsItem") -> bool:
    try:
        with open(SENT_FILE, "a", encoding="utf-8") as f:
            f.write(canonical_url(item.url) + "\n")

        fp = title_fingerprint(item.title)
        th = title_hash(item.title)
        ev = item.event_key or event_fingerprint(item)

        with open(SENT_TITLES_FILE, "a", encoding="utf-8") as f:
            if fp:
                f.write(fp + "\n")
            f.write("H:" + th + "\n")

        with open(SENT_EVENTS_FILE, "a", encoding="utf-8") as f:
            f.write(ev + "\n")
        return True
    except OSError as e:
        log.error("Cannot save sent item │ %s", e)
        return False


# ════════════════════════════════════════════════════════════
# DATE UTILITIES
# ════════════════════════════════════════════════════════════

def parse_datetime(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        if hasattr(value, "tm_year"):
            return datetime(
                value.tm_year, value.tm_mon, value.tm_mday,
                value.tm_hour, value.tm_min, value.tm_sec,
                tzinfo=timezone.utc,
            )
    except Exception:
        pass
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None \
            else value.astimezone(timezone.utc)
    return None


def age_hours(dt: Optional[datetime]) -> float:
    if not dt:
        return 999_999
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt.astimezone(timezone.utc)
    return max(0, delta.total_seconds() / 3600)


def format_time(dt: Optional[datetime]) -> str:
    if not dt:
        return "نامشخص"
    try:
        return to_persian_digits(dt.astimezone(timezone.utc).strftime("%H:%M"))
    except Exception:
        return "نامشخص"


# ════════════════════════════════════════════════════════════
# RSS + HTML COLLECTION
# ════════════════════════════════════════════════════════════

_FEED_PATHS = [
    "/rss", "/rss/", "/feed", "/feed/",
    "/rss.xml", "/feed.xml", "/atom.xml",
    "/fa/rss", "/fa/rss/", "/fa/feed", "/fa/feed/",
]


def discover_feeds(source: Source) -> list[str]:
    feeds: list[str] = [urljoin(source.url, p) for p in _FEED_PATHS]

    resp = safe_get(source.url)
    if resp and resp.ok:
        try:
            soup = BeautifulSoup(resp.text, "html.parser")
            for link in soup.find_all("link"):
                rel = link.get("rel", [])
                rel_text = " ".join(rel).lower() if isinstance(rel, list) else str(rel).lower()
                typ = (link.get("type") or "").lower()
                if "alternate" in rel_text and any(x in typ for x in ("rss", "atom", "xml")):
                    href = link.get("href")
                    if href:
                        feeds.insert(0, urljoin(resp.url, href))
        except Exception:
            pass

    seen: list[str] = []
    for url in feeds:
        cu = canonical_url(url)
        if cu and cu not in seen:
            seen.append(cu)
    return seen[:20]


def _entry_image(entry) -> str:
    candidates: list[str] = []
    for media in entry.get("media_content", []) or []:
        if isinstance(media, dict):
            candidates.append(media.get("url"))
    for media in entry.get("media_thumbnail", []) or []:
        if isinstance(media, dict):
            candidates.append(media.get("url"))
    for enc in entry.get("enclosures", []) or []:
        if isinstance(enc, dict):
            candidates.append(enc.get("href") or enc.get("url"))
    for c in candidates:
        if c and c.startswith(("http://", "https://")):
            return c
    return ""


def parse_feed(source: Source, feed_url: str) -> list[NewsItem]:
    if feedparser is None:
        return []
    resp = safe_get(feed_url, headers={
        "Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml,text/html"
    })
    if not resp or not resp.ok:
        return []

    try:
        parsed = feedparser.parse(resp.content)
    except Exception:
        return []

    items: list[NewsItem] = []
    for entry in parsed.entries[:MAX_ITEMS_PER_SOURCE]:
        title = clean_html(entry.get("title", ""))
        url = entry.get("link", "")
        if not title or not url:
            continue

        published = None
        for field in ("published_parsed", "updated_parsed", "created_parsed"):
            published = parse_datetime(entry.get(field))
            if published:
                break

        items.append(NewsItem(
            title=title,
            url=canonical_url(url),
            description=clean_html(entry.get("summary", "")),
            image=_entry_image(entry),
            published=published,
            source=source.name,
            domain=source.domain,
        ))
    return items


def html_fallback(source: Source) -> list[NewsItem]:
    resp = safe_get(source.url)
    if not resp or not resp.ok:
        return []
    try:
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception:
        return []

    items: list[NewsItem] = []
    for a in soup.find_all("a", href=True):
        title = clean_html(a.get_text(" ", strip=True))
        href = urljoin(resp.url, a["href"])
        if len(title) < 20:
            continue
        if not href.startswith(("http://", "https://")):
            continue
        if not same_domain(href, source.domain):
            continue
        items.append(NewsItem(
            title=title, url=canonical_url(href),
            source=source.name, domain=source.domain,
        ))
        if len(items) >= MAX_ITEMS_PER_SOURCE:
            break
    return items


# ════════════════════════════════════════════════════════════
# SCORING + TOPIC + URGENCY
# ════════════════════════════════════════════════════════════

def score_text(text: str) -> tuple[int, list[str]]:
    text = normalize(text)
    score = 0
    matched: list[str] = []

    for dic in ALL_SCORING_DICTS:
        for keyword, value in dic.items():
            if normalize(keyword) in text:
                score += value
                matched.append(keyword)
    return score, matched


def detect_topic(text: str) -> tuple[str, str]:
    text = normalize(text)

    priority_order = ["iran_us", "gulf", "hezbollah", "palestine", "yemen", "iraq"]

    for topic in priority_order:
        for kw in TOPIC_KEYWORDS[topic]:
            if normalize(kw) in text:
                emoji, _ = TOPIC_FLAGS[topic]
                return topic, emoji

    emoji, _ = TOPIC_FLAGS["resistance"]
    return "resistance", emoji


def compute_urgency(item: NewsItem) -> int:
    text = normalize(f"{item.title} {item.description}")
    urgency = 0

    for kw, val in URGENT_TERMS.items():
        if normalize(kw) in text:
            urgency += val
    for kw, val in MAJOR_EVENTS.items():
        if normalize(kw) in text:
            urgency += val
    for kw, val in CASUALTY_TERMS.items():
        if normalize(kw) in text:
            urgency += val

    age = age_hours(item.published)
    if age <= 1:
        urgency += 20
    elif age <= 2:
        urgency += 15
    elif age <= 3:
        urgency += 10
    elif age <= URGENT_HOURS:
        urgency += 5

    return urgency


def is_analysis(text: str) -> bool:
    text = normalize(text)
    return sum(1 for kw in ANALYSIS_TERMS if normalize(kw) in text) >= 2


def is_excluded(text: str) -> bool:
    text = normalize(text)
    return any(normalize(kw) in text for kw in EXCLUDE_TERMS)


def evaluate(item: NewsItem) -> bool:
    combined = f"{item.title} {item.description}"

    if is_excluded(combined) or is_analysis(combined):
        return False

    item.score, item.matched = score_text(combined)
    item.urgency = compute_urgency(item)
    item.topic, item.flag = detect_topic(combined)

    urgent_age_ok = age_hours(item.published) <= URGENT_HOURS
    item.is_urgent = urgent_age_ok and item.urgency >= URGENT_MIN_SCORE

    if item.is_urgent and item.score >= max(8, MIN_SCORE - 8):
        return True
    return item.score >= MIN_SCORE


# ════════════════════════════════════════════════════════════
# SIMILARITY
# ════════════════════════════════════════════════════════════

def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _important_hits(item: NewsItem) -> set[str]:
    text = normalize(f"{item.title} {item.description}")
    return {kw for kw in _IMPORTANT_KEYWORDS if normalize(kw) in text}


def is_same_event(a: NewsItem, b: NewsItem) -> bool:
    title_sim = _jaccard(_words(a.title), _words(b.title))
    if title_sim >= DUP_TITLE_SIM:
        return True

    content_sim = _jaccard(
        _words(f"{a.title} {a.description}"),
        _words(f"{b.title} {b.description}"),
    )
    important_sim = _jaccard(_important_hits(a), _important_hits(b))

    if content_sim >= DUP_CONTENT_SIM and important_sim >= DUP_IMPORTANT_SIM:
        return True
    if title_sim >= 0.45 and important_sim >= 0.55:
        return True
    return False


def item_priority(item: NewsItem) -> float:
    freshness = max(0, 12 - age_hours(item.published))
    trust = 2 if item.source in TRUSTED_SOURCES else 0
    return item.urgency * 1.5 + item.score + freshness + trust


def dedupe_cross_source(items: Iterable[NewsItem]) -> list[NewsItem]:
    result: list[NewsItem] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    seen_hashes: set[str] = set()
    seen_events: set[str] = set()

    for item in sorted(items, key=item_priority, reverse=True):
        url = canonical_url(item.url)
        if not url or url in seen_urls:
            continue

        tf = title_fingerprint(item.title)
        th = title_hash(item.title)
        ev = event_fingerprint(item)
        item.event_key = ev

        if tf and tf in seen_titles:
            continue
        if th in seen_hashes:
            continue
        if ev in seen_events:
            continue

        duplicate = False
        for existing in result:
            if is_same_event(item, existing):
                log.info("dup-sim │ %s ⇄ %s", item.source, existing.source)
                duplicate = True
                break
        if duplicate:
            continue

        seen_urls.add(url)
        if tf:
            seen_titles.add(tf)
        seen_hashes.add(th)
        seen_events.add(ev)
        result.append(item)
    return result


# ════════════════════════════════════════════════════════════
# IMAGE
# ════════════════════════════════════════════════════════════

def find_article_image(item: NewsItem) -> str:
    if item.image:
        return item.image

    resp = safe_get(item.url)
    if not resp or not resp.ok:
        return ""
    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            return urljoin(resp.url, og["content"])
        tw = soup.find("meta", attrs={"name": "twitter:image"})
        if tw and tw.get("content"):
            return urljoin(resp.url, tw["content"])
        for img in soup.find_all("img", src=True):
            src = urljoin(resp.url, img["src"])
            if src.startswith(("http://", "https://")):
                return src
    except Exception:
        pass
    return ""


def download_image(url: str) -> str:
    if not url:
        return ""
    try:
        resp = safe_get(url, timeout=15)
        if not resp or not resp.ok:
            return ""
        ctype = resp.headers.get("content-type", "").lower()
        if "image" not in ctype and not url.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            return ""
        path = os.path.join(BASE_DIR, "_news_image.jpg")
        with open(path, "wb") as f:
            f.write(resp.content)
        return path
    except Exception as e:
        log.warning("Image download failed │ %s", e)
        return ""


def add_logo(image_path: str) -> str:
    if Image is None or not image_path or not os.path.exists(LOGO_FILE):
        return image_path
    try:
        base = Image.open(image_path).convert("RGBA")
        logo = Image.open(LOGO_FILE).convert("RGBA")
        max_w = max(80, int(base.width * 0.18))
        ratio = max_w / logo.width
        logo = logo.resize((max_w, int(logo.height * ratio)), Image.LANCZOS)
        margin = 20
        pos = (base.width - logo.width - margin,
               base.height - logo.height - margin)
        base.alpha_composite(logo, pos)
        out = os.path.join(BASE_DIR, "_news_final.jpg")
        base.convert("RGB").save(out, "JPEG", quality=92)
        return out
    except Exception as e:
        log.warning("Logo failed │ %s", e)
        return image_path


# ════════════════════════════════════════════════════════════
# CAPTION  —  جهان‌تاب فقط در انتهای خبر
# ════════════════════════════════════════════════════════════

DIVIDER = "━━━━━━━━━━━━━━━━━━"


def build_caption(item: NewsItem) -> str:
    # سرصفحه بدون نام کانال
    if item.is_urgent:
        header = "🚨🔴 <b>خبر فوری</b>"
    elif item.urgency >= URGENT_MIN_SCORE - 5:
        header = "⚡ <b>خبر مهم</b>"
    else:
        header = "📰 <b>خبر ویژه</b>"

    topic_label = TOPIC_FLAGS.get(item.topic, ("✊", "محور مقاومت"))[1]
    flag = item.flag or "🌐"

    title = escape(shorten(item.title, 220))
    desc = escape(shorten(item.description, 400))
    source = escape(item.source)
    time_text = format_time(item.published)

    lines = [
        header,
        "",
        f"{flag}  <b>{title}</b>",
        "",
        DIVIDER,
        f"🎯  <b>موضوع:</b>  {escape(topic_label)}",
        f"📡  <b>منبع:</b>  {source}",
        f"🕐  <b>ساعت:</b>  {time_text}",
        DIVIDER,
    ]

    if desc:
        lines.extend(["", desc])

    # پایان خبر ← امضای کانال
    lines.extend([
        "",
        DIVIDER,
        CHANNEL_SIGNATURE,
    ])
    return "\n".join(lines)


# ════════════════════════════════════════════════════════════
# TELEGRAM
# ════════════════════════════════════════════════════════════

def _tg_endpoint(method: str) -> str:
    return f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"


def tg_request(method: str, payload=None, files=None) -> dict:
    try:
        resp = requests.post(_tg_endpoint(method), data=payload, files=files, timeout=30)
        data = resp.json()
        if not data.get("ok"):
            log.error("Telegram │ %s", data)
        return data
    except Exception as e:
        log.error("Telegram request failed │ %s", e)
        return {"ok": False, "description": str(e)}


def send_post(image_path: str, caption: str, article_url: str) -> bool:
    # دکمهٔ شیشه‌ای در پایین پست
    keyboard = {"inline_keyboard": [[
        {"text": "🔗  مشاهده خبر", "url": article_url}
    ]]}
    reply_markup = json.dumps(keyboard, ensure_ascii=False)
    payload = {
        "chat_id": CHAT_ID,
        "caption": caption,
        "parse_mode": "HTML",
        "reply_markup": reply_markup,
    }

    try:
        if image_path and os.path.exists(image_path):
            # عکس در ابتدای خبر (sendPhoto)
            with open(image_path, "rb") as photo:
                result = tg_request("sendPhoto", payload=payload, files={"photo": photo})
        else:
            # اگر عکس نبود، فقط متن با دکمه
            result = tg_request("sendMessage", payload={
                "chat_id": CHAT_ID,
                "text": caption,
                "parse_mode": "HTML",
                "reply_markup": reply_markup,
            })
        return bool(result.get("ok"))
    except Exception as e:
        log.error("Send failed │ %s", e)
        return False


# ════════════════════════════════════════════════════════════
# PIPELINE
# ════════════════════════════════════════════════════════════

def collect_items() -> list[NewsItem]:
    all_items: list[NewsItem] = []
    for source in SOURCES:
        log.info("→ %s", source.name)

        source_items: list[NewsItem] = []
        for feed in discover_feeds(source):
            parsed = parse_feed(source, feed)
            if parsed:
                source_items.extend(parsed)
                if len(source_items) >= MAX_ITEMS_PER_SOURCE:
                    break

        if not source_items:
            source_items = html_fallback(source)

        unique: dict[str, NewsItem] = {}
        for item in source_items:
            key = canonical_url(item.url)
            if key and key not in unique:
                unique[key] = item

        all_items.extend(list(unique.values())[:MAX_ITEMS_PER_SOURCE])
    return all_items


def filter_items(items: list[NewsItem]) -> list[NewsItem]:
    sent_links  = load_sent_links()
    sent_titles = load_sent_titles()
    sent_events = load_sent_events()

    result: list[NewsItem] = []
    for item in items:
        url = canonical_url(item.url)
        tf  = title_fingerprint(item.title)
        th  = title_hash(item.title)
        ev  = event_fingerprint(item)
        item.event_key = ev

        if not url or url in sent_links:
            continue
        if tf and tf in sent_titles:
            continue
        if ("H:" + th) in sent_titles:
            continue
        if ev in sent_events:
            continue
        if age_hours(item.published) > MAX_AGE_HOURS:
            continue
        if not evaluate(item):
            continue

        result.append(item)
    return result


def sort_items(items: list[NewsItem]) -> list[NewsItem]:
    return sorted(
        items,
        key=lambda x: (1 if x.is_urgent else 0, item_priority(x)),
        reverse=True,
    )


def select_items(items: list[NewsItem]) -> list[NewsItem]:
    urgent = [x for x in items if x.is_urgent]
    normal = [x for x in items if not x.is_urgent]

    selected = urgent[:URGENT_SLOTS]
    remaining = MAX_POSTS_PER_RUN - len(selected)
    if remaining > 0:
        selected.extend(normal[:remaining])

    if len(selected) < MAX_POSTS_PER_RUN and len(urgent) > URGENT_SLOTS:
        extra = MAX_POSTS_PER_RUN - len(selected)
        selected.extend(urgent[URGENT_SLOTS:URGENT_SLOTS + extra])

    return selected


# ════════════════════════════════════════════════════════════
# RUN ONCE
# ════════════════════════════════════════════════════════════

def run_once() -> int:
    log.info("┌─ cycle start ─────────────────────────")

    items = collect_items()
    log.info("│ collected     │ %d", len(items))

    items = filter_items(items)
    log.info("│ after filter  │ %d", len(items))

    items = dedupe_cross_source(items)
    log.info("│ after dedupe  │ %d", len(items))

    items = sort_items(items)
    items = select_items(items)
    log.info("│ selected      │ %d  (urgent=%d)",
             len(items), sum(1 for x in items if x.is_urgent))

    sent = 0
    for item in items:
        try:
            image_path = download_image(find_article_image(item))
            if image_path:
                image_path = add_logo(image_path)

            caption = build_caption(item)

            if send_post(image_path, caption, item.url):
                save_sent_item(item)
                sent += 1
                tag = "🚨" if item.is_urgent else "✅"
                log.info("│ %s posted │ %s │ %s",
                         tag, item.source, item.title[:55])
                time.sleep(POST_DELAY)
            else:
                log.error("│ ❌ failed │ %s", item.title[:55])
        except Exception as e:
            log.exception("Item processing failed │ %s", e)

    log.info("└─ cycle done    │ sent=%d", sent)
    return sent


# ════════════════════════════════════════════════════════════
# MAIN LOOP  —  هر ۵ دقیقه
# ════════════════════════════════════════════════════════════

def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN تنظیم نشده است.")

    log.info("═" * 55)
    log.info("🌐 JAHANTAB Bot v8  │  channel: %s", CHAT_ID)
    log.info("⏱  interval: %d ثانیه  │  max posts: %d  │  urgent slots: %d",
             RUN_INTERVAL_SEC, MAX_POSTS_PER_RUN, URGENT_SLOTS)
    log.info("📡  sources: %d منبع داخلی مجوزدار", len(SOURCES))
    log.info("🎯  focus: جنگ ایران و آمریکا و اخبار مرتبط")
    log.info("═" * 55)

    while True:
        try:
            run_once()
        except KeyboardInterrupt:
            log.info("🛑 stopped by user")
            return
        except Exception as e:
            log.exception("Cycle failed │ %s", e)

        log.info("💤 خواب %d ثانیه...\n", RUN_INTERVAL_SEC)
        try:
            time.sleep(RUN_INTERVAL_SEC)
        except KeyboardInterrupt:
            log.info("🛑 stopped by user")
            return


if __name__ == "__main__":
    main()