# -*- coding: utf-8 -*-

"""
🌐 JAHANTAB | جهان‌تاب
ربات خبری تلگرام

ویژگی‌ها:
- اجرای یک چرخه در هر GitHub Actions
- زمان‌بندی توسط GitHub Actions
- منابع خبری داخلی
- تمرکز روی اخبار مهم و فوری ایران و منطقه
- جلوگیری از خبر تکراری
- حذف خبرهای مشابه چند منبع
- عکس خبر در ابتدای پست
- لوگوی جهان‌تاب روی عکس در صورت وجود
- منبع خبر
- امضای ظریف کانال
- دکمه شیشه‌ای «مشاهده خبر»
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import (
    parse_qsl,
    urlencode,
    urljoin,
    urlparse,
    urlunparse,
)

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


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

CHAT_ID = (
    os.getenv("CHAT_ID", "").strip()
    or os.getenv("CHANNEL", "").strip()
    or "@jahantab_news"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SENT_FILE = os.path.join(
    BASE_DIR,
    os.getenv("SENT_FILE", "sent_links.txt")
)

SENT_TITLES_FILE = os.path.join(
    BASE_DIR,
    os.getenv("SENT_TITLES_FILE", "sent_titles.txt")
)

SENT_EVENTS_FILE = os.path.join(
    BASE_DIR,
    os.getenv("SENT_EVENTS_FILE", "sent_events.txt")
)

LOGO_FILE = os.path.join(
    BASE_DIR,
    os.getenv("LOGO_FILE", "logo.jpg")
)

MAX_AGE_HOURS = int(os.getenv("MAX_AGE_HOURS", "12"))

MIN_SCORE = int(os.getenv("MIN_SCORE", "20"))

URGENT_MIN_SCORE = int(
    os.getenv("URGENT_MIN_SCORE", "14")
)

MAX_POSTS_PER_RUN = int(
    os.getenv("MAX_POSTS_PER_RUN", "3")
)

MAX_ITEMS_PER_SOURCE = int(
    os.getenv("MAX_ITEMS_PER_SOURCE", "12")
)

HTTP_TIMEOUT = int(
    os.getenv("HTTP_TIMEOUT", "20")
)

POST_DELAY = float(
    os.getenv("POST_DELAY", "2")
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)

log = logging.getLogger("JAHANTAB")


# ============================================================
# HTTP SESSION
# ============================================================

SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 "
        "(X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/128.0 Safari/537.36 "
        "JAHANTAB-News-Bot/9.0"
    ),
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.5",
})


# ============================================================
# DATA MODEL
# ============================================================

@dataclass
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
    urgency: int = 0

    matched: list[str] = None

    is_urgent: bool = False

    topic: str = ""
    flag: str = ""

    event_key: str = ""

    def __post_init__(self):
        if self.matched is None:
            self.matched = []


# ============================================================
# SOURCES
# ============================================================

SOURCES = [

    Source(
        "تابناک",
        "tabnak.ir",
        "https://www.tabnak.ir/"
    ),

    Source(
        "فرارو",
        "fararu.com",
        "https://fararu.com/"
    ),

    Source(
        "همشهری آنلاین",
        "hamshahrionline.ir",
        "https://www.hamshahrionline.ir/"
    ),

    Source(
        "آخرین خبر",
        "akharinkhabar.ir",
        "https://akharinkhabar.ir/"
    ),

    Source(
        "خبر فوری",
        "khabarfoori.com",
        "https://www.khabarfoori.com/"
    ),

    Source(
        "خبرآنلاین",
        "khabaronline.ir",
        "https://www.khabaronline.ir/"
    ),

    Source(
        "مهر",
        "mehrnews.com",
        "https://www.mehrnews.com/"
    ),

    Source(
        "فارس",
        "farsnews.ir",
        "https://www.farsnews.ir/"
    ),

    Source(
        "ایرنا",
        "irna.ir",
        "https://www.irna.ir/"
    ),

    Source(
        "ایسنا",
        "isna.ir",
        "https://www.isna.ir/"
    ),

    Source(
        "صدا و سیما",
        "iribnews.ir",
        "https://www.iribnews.ir/"
    ),

    Source(
        "باشگاه خبرنگاران جوان",
        "yjc.ir",
        "https://www.yjc.ir/"
    ),

    Source(
        "تسنیم",
        "tasnimnews.com",
        "https://www.tasnimnews.com/fa"
    ),

    Source(
        "عصر ایران",
        "asriran.com",
        "https://www.asriran.com/"
    ),

    Source(
        "مشرق نیوز",
        "mashreghnews.ir",
        "https://www.mashreghnews.ir/"
    ),

    Source(
        "انتخاب",
        "entekhab.ir",
        "https://www.entekhab.ir/"
    ),

    Source(
        "الف",
        "alef.ir",
        "https://www.alef.ir/"
    ),

    Source(
        "ایلنا",
        "ilna.ir",
        "https://www.ilna.ir/"
    ),
]


# منابع رسمی‌تر برای اولویت‌بندی در صورت گزارش یک رویداد مشابه
TRUSTED_SOURCES = {
    "ایرنا",
    "ایسنا",
    "فارس",
    "تسنیم",
    "مهر",
    "صدا و سیما",
}


SOURCE_PRIORITY = {
    "ایرنا": 100,
    "ایسنا": 98,
    "فارس": 96,
    "مهر": 94,
    "تسنیم": 92,
    "صدا و سیما": 90,
    "تابناک": 88,
    "فرارو": 86,
    "همشهری آنلاین": 84,
    "آخرین خبر": 82,
    "خبر فوری": 80,
    "خبرآنلاین": 78,
    "عصر ایران": 76,
    "مشرق نیوز": 74,
    "انتخاب": 72,
    "ایلنا": 70,
    "الف": 68,
    "باشگاه خبرنگاران جوان": 66,
}


# ============================================================
# KEYWORDS
# ============================================================

IRAN_KEYWORDS = {
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
    "حمله ایران": 15,
    "حمله آمریکا": 15,
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
    "عملیات": 7,
}


GULF_KEYWORDS = {
    "خلیج فارس": 12,
    "خلیج‌فارس": 12,
    "تنگه هرمز": 15,
    "تنگه‌ی هرمز": 15,
    "هرمز": 8,
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
    "بندرعباس": 7,
    "هرمزگان": 7,
    "بوشهر": 6,
    "قشم": 6,
    "خارک": 8,
}


RESISTANCE_KEYWORDS = {
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

    "اسرائیل": 9,
    "رژیم صهیونیستی": 9,
    "نتانیاهو": 8,

    "انصارالله": 12,
    "انصار الله": 12,
    "حوثی": 10,
    "حوثی‌ها": 10,
    "یمن": 9,
    "صنعا": 8,

    "حشد الشعبی": 12,
    "حشدالشعبی": 12,
    "کتائب حزب الله": 10,
    "نجباء": 8,
    "عراق": 7,
    "بغداد": 7,

    "محور مقاومت": 15,
    "مقاومت اسلامی": 13,
}


EVENT_KEYWORDS = {
    "آتش بس": 12,
    "آتش‌بس": 12,
    "پایان جنگ": 14,
    "آغاز جنگ": 18,
    "اعلام جنگ": 18,
    "ورود به جنگ": 15,
    "گسترش جنگ": 12,
    "تشدید درگیری": 10,
    "حمله گسترده": 14,
    "عملیات گسترده": 13,
    "حمله مستقیم": 15,
    "حمله متقابل": 13,
    "پاسخ موشکی": 14,
    "پاسخ نظامی": 11,
    "ترور": 12,
    "انفجار": 10,
    "سرنگونی": 11,
}


URGENT_KEYWORDS = {
    "فوری": 10,
    "خبر فوری": 15,
    "لحظاتی پیش": 13,
    "دقایقی پیش": 13,
    "همین الان": 13,
    "هم‌اکنون": 13,
    "هم اکنون": 13,
    "خبر مهم": 10,
    "لحظه به لحظه": 8,
    "تازه‌ترین": 6,
    "تازه ترین": 6,
    "اختصاصی": 8,
    "تکمیلی": 5,
}


CASUALTY_KEYWORDS = {
    "کشته": 9,
    "کشته شد": 10,
    "شهید": 9,
    "شهید شد": 10,
    "مجروح": 7,
    "زخمی": 7,
    "تلفات": 9,
    "تلفات سنگین": 12,
    "اسیر": 8,
}


ANALYSIS_TERMS = {
    "تحلیل",
    "یادداشت",
    "کارشناس",
    "کارشناسان",
    "گفتگو",
    "گفت‌وگو",
    "گفت و گو",
    "بررسی",
    "چرا",
    "چگونه",
    "روایت",
    "تحلیلگر",
    "تحلیل‌گر",
    "سناریو",
    "پیش بینی",
    "پیش‌بینی",
    "آینده جنگ",
    "نگاهی به",
    "گزارش تحلیلی",
    "پرونده",
}


EXCLUDE_TERMS = {
    "ورزش",
    "فوتبال",
    "والیبال",
    "لیگ",
    "تیم ملی",
    "سینما",
    "تلویزیون",
    "موسیقی",
    "بازیگر",
    "فیلم",
    "سلامت",
    "پزشکی",
    "کرونا",
    "کنکور",
    "دانشگاه",
    "دانشجو",
    "هواشناسی",
    "بارش",
    "برف",
    "بورس",
    "دلار",
    "طلا",
    "سکه",
    "خودرو",
    "مسکن",
    "اجاره",
    "بازنشستگی",
    "یارانه",
    "آشپزی",
    "گردشگری",
    "فناوری",
    "موبایل",
}


ALL_POSITIVE = [
    IRAN_KEYWORDS,
    GULF_KEYWORDS,
    RESISTANCE_KEYWORDS,
    EVENT_KEYWORDS,
    URGENT_KEYWORDS,
    CASUALTY_KEYWORDS,
]


TOPICS = {
    "iran": (
        "🇮🇷",
        "تحولات ایران"
    ),
    "gulf": (
        "🌊",
        "خلیج فارس و تنگه هرمز"
    ),
    "hezbollah": (
        "🇱🇧",
        "حزب‌الله لبنان"
    ),
    "palestine": (
        "🇵🇸",
        "فلسطین و غزه"
    ),
    "yemen": (
        "🇾🇪",
        "انصارالله یمن"
    ),
    "iraq": (
        "🇮🇶",
        "حشدالشعبی عراق"
    ),
}


# ============================================================
# TEXT UTILITIES
# ============================================================

AR_TO_FA = {
    "ي": "ی",
    "ى": "ی",
    "ك": "ک",
    "ۀ": "ه",
    "ة": "ه",
    "ؤ": "و",
    "إ": "ا",
    "أ": "ا",
    "ٱ": "ا",
    "ـ": "",
    "\u200c": " ",
    "\u200f": " ",
    "\u200e": " ",
    "\ufeff": " ",
}


STOPWORDS = {
    "از", "به", "در", "با", "برای",
    "که", "و", "را", "این", "آن",
    "یک", "های", "کرد", "شد",
    "است", "بر", "تا", "وی",
    "او", "نیز", "اما", "هم",
    "یا", "پس", "های",
}


def normalize(text: Optional[str]) -> str:

    if not text:
        return ""

    text = html.unescape(str(text))

    for a, b in AR_TO_FA.items():
        text = text.replace(a, b)

    text = text.lower()

    return re.sub(
        r"\s+",
        " ",
        text
    ).strip()


def clean_html(text: Optional[str]) -> str:

    if not text:
        return ""

    soup = BeautifulSoup(
        str(text),
        "html.parser"
    )

    for tag in soup([
        "script",
        "style",
        "noscript"
    ]):
        tag.decompose()

    return re.sub(
        r"\s+",
        " ",
        html.unescape(
            soup.get_text(
                " ",
                strip=True
            )
        )
    ).strip()


def shorten(text: str, limit: int) -> str:

    text = clean_html(text)

    if len(text) <= limit:
        return text

    cut = text[:limit]

    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]

    return cut.rstrip(
        " .،؛:"
    ) + "…"


def escape_html(text: str) -> str:
    return html.escape(
        str(text or ""),
        quote=False
    )


# ============================================================
# URL
# ============================================================

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "ref",
}


def canonical_url(url: str) -> str:

    if not url:
        return ""

    try:

        p = urlparse(url)

        scheme = (
            p.scheme or "https"
        ).lower()

        netloc = p.netloc.lower()

        if netloc.startswith("www."):
            netloc = netloc[4:]

        path = p.path or "/"

        if path != "/" and path.endswith("/"):
            path = path[:-1]

        query = [
            (k, v)
            for k, v in parse_qsl(
                p.query,
                keep_blank_values=True
            )
            if k.lower() not in TRACKING_PARAMS
        ]

        return urlunparse((
            scheme,
            netloc,
            path,
            "",
            urlencode(query),
            ""
        ))

    except Exception:
        return url.strip()


def same_domain(url: str, domain: str) -> bool:

    try:

        host = urlparse(
            url
        ).netloc.lower()

        if host.startswith("www."):
            host = host[4:]

        domain = domain.lower()

        if domain.startswith("www."):
            domain = domain[4:]

        return (
            host == domain
            or host.endswith("." + domain)
        )

    except Exception:
        return False


# ============================================================
# HTTP
# ============================================================

def safe_get(
    url: str,
    **kwargs
) -> Optional[requests.Response]:

    try:

        timeout = kwargs.pop(
            "timeout",
            HTTP_TIMEOUT
        )

        response = SESSION.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            **kwargs
        )

        return response

    except requests.RequestException as exc:

        log.warning(
            "GET failed │ %s │ %s",
            url,
            exc
        )

        return None


# ============================================================
# DATE
# ============================================================

def parse_datetime(value) -> Optional[datetime]:

    if not value:
        return None

    try:

        if hasattr(value, "tm_year"):

            return datetime(
                value.tm_year,
                value.tm_mon,
                value.tm_mday,
                value.tm_hour,
                value.tm_min,
                value.tm_sec,
                tzinfo=timezone.utc
            )

    except Exception:
        pass

    if isinstance(value, datetime):

        if value.tzinfo is None:
            return value.replace(
                tzinfo=timezone.utc
            )

        return value.astimezone(
            timezone.utc
        )

    return None


def age_hours(
    dt: Optional[datetime]
) -> float:

    if not dt:
        return 999999

    now = datetime.now(
        timezone.utc
    )

    return max(
        0,
        (
            now - dt.astimezone(
                timezone.utc
            )
        ).total_seconds() / 3600
    )


def format_time(
    dt: Optional[datetime]
) -> str:

    if not dt:
        return "نامشخص"

    try:

        return dt.astimezone(
            timezone.utc
        ).strftime("%H:%M")

    except Exception:

        return "نامشخص"


# ============================================================
# STORAGE
# ============================================================

def load_lines(path: str) -> set[str]:

    if not os.path.exists(path):
        return set()

    try:

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:

            return {
                line.strip()
                for line in f
                if line.strip()
            }

    except OSError:
        return set()


def load_sent_links() -> set[str]:

    return {
        canonical_url(x)
        for x in load_lines(SENT_FILE)
    }


def load_sent_titles() -> set[str]:

    return load_lines(
        SENT_TITLES_FILE
    )


def load_sent_events() -> set[str]:

    return load_lines(
        SENT_EVENTS_FILE
    )


def save_sent_item(
    item: NewsItem
) -> bool:

    try:

        with open(
            SENT_FILE,
            "a",
            encoding="utf-8"
        ) as f:

            f.write(
                canonical_url(item.url)
                + "\n"
            )

        with open(
            SENT_TITLES_FILE,
            "a",
            encoding="utf-8"
        ) as f:

            f.write(
                title_fingerprint(item.title)
                + "\n"
            )

            f.write(
                "H:"
                + title_hash(item.title)
                + "\n"
            )

        with open(
            SENT_EVENTS_FILE,
            "a",
            encoding="utf-8"
        ) as f:

            f.write(
                item.event_key
                + "\n"
            )

        return True

    except OSError as exc:

        log.error(
            "Save state failed │ %s",
            exc
        )

        return False


# ============================================================
# FINGERPRINTS
# ============================================================

def words(text: str) -> set[str]:

    result = re.findall(
        r"[\wآ-ی]+",
        normalize(text)
    )

    return {
        w
        for w in result
        if len(w) > 2
        and w not in STOPWORDS
    }


def title_fingerprint(
    title: str
) -> str:

    text = normalize(title)

    text = re.sub(
        r"[^\wآ-ی\s]",
        " ",
        text
    )

    return re.sub(
        r"\s+",
        " ",
        text
    ).strip()


def title_hash(title: str) -> str:

    return hashlib.sha1(
        normalize(title).encode(
            "utf-8"
        )
    ).hexdigest()[:20]


def important_keywords(
    item: NewsItem
) -> set[str]:

    text = normalize(
        f"{item.title} {item.description}"
    )

    found = set()

    for dictionary in ALL_POSITIVE:

        for keyword in dictionary:

            if normalize(keyword) in text:
                found.add(
                    normalize(keyword)
                )

    return found


def event_fingerprint(
    item: NewsItem
) -> str:

    text = normalize(
        f"{item.title} {item.description}"
    )

    important = sorted(
        important_keywords(item)
    )

    # چند کلمه محتوایی اصلی
    content_words = sorted(
        words(text)
    )[:20]

    raw = (
        "|".join(important)
        + "::"
        + "|".join(content_words)
    )

    return hashlib.sha1(
        raw.encode("utf-8")
    ).hexdigest()[:24]


# ============================================================
# RSS
# ============================================================

FEED_PATHS = [
    "/rss",
    "/rss/",
    "/feed",
    "/feed/",
    "/rss.xml",
    "/feed.xml",
    "/atom.xml",
    "/fa/rss",
    "/fa/rss/",
    "/fa/feed",
    "/fa/feed/",
]


def discover_feeds(
    source: Source
) -> list[str]:

    candidates = [
        urljoin(
            source.url,
            path
        )
        for path in FEED_PATHS
    ]

    response = safe_get(
        source.url
    )

    if response and response.ok:

        try:

            soup = BeautifulSoup(
                response.text,
                "html.parser"
            )

            for link in soup.find_all(
                "link"
            ):

                rel = link.get(
                    "rel",
                    []
                )

                typ = (
                    link.get("type")
                    or ""
                ).lower()

                rel_text = (
                    " ".join(rel)
                    if isinstance(rel, list)
                    else str(rel)
                ).lower()

                if (
                    "alternate" in rel_text
                    and (
                        "rss" in typ
                        or "atom" in typ
                        or "xml" in typ
                    )
                ):

                    href = link.get(
                        "href"
                    )

                    if href:
                        candidates.insert(
                            0,
                            urljoin(
                                response.url,
                                href
                            )
                        )

        except Exception:
            pass

    result = []

    for url in candidates:

        cu = canonical_url(url)

        if cu and cu not in result:
            result.append(cu)

    return result[:15]


def entry_image(entry) -> str:

    candidates = []

    for media in (
        entry.get(
            "media_content",
            []
        )
        or []
    ):

        if isinstance(
            media,
            dict
        ):

            candidates.append(
                media.get("url")
            )

    for media in (
        entry.get(
            "media_thumbnail",
            []
        )
        or []
    ):

        if isinstance(
            media,
            dict
        ):

            candidates.append(
                media.get("url")
            )

    for enc in (
        entry.get(
            "enclosures",
            []
        )
        or []
    ):

        if isinstance(
            enc,
            dict
        ):

            candidates.append(
                enc.get("href")
                or enc.get("url")
            )

    for url in candidates:

        if url and url.startswith(
            ("http://", "https://")
        ):
            return url

    return ""


def parse_feed(
    source: Source,
    feed_url: str
) -> list[NewsItem]:

    if feedparser is None:
        return []

    response = safe_get(
        feed_url,
        headers={
            "Accept": (
                "application/rss+xml,"
                "application/atom+xml,"
                "application/xml,"
                "text/xml"
            )
        }
    )

    if not response or not response.ok:
        return []

    try:

        feed = feedparser.parse(
            response.content
        )

    except Exception:
        return []

    result = []

    for entry in feed.entries[
        :MAX_ITEMS_PER_SOURCE
    ]:

        title = clean_html(
            entry.get(
                "title",
                ""
            )
        )

        url = canonical_url(
            entry.get(
                "link",
                ""
            )
        )

        if not title or not url:
            continue

        if not same_domain(
            url,
            source.domain
        ):
            continue

        published = None

        for field in (
            "published_parsed",
            "updated_parsed",
            "created_parsed"
        ):

            published = parse_datetime(
                entry.get(field)
            )

            if published:
                break

        description = clean_html(
            entry.get(
                "summary",
                ""
            )
        )

        result.append(
            NewsItem(
                title=title,
                url=url,
                source=source.name,
                domain=source.domain,
                description=description,
                image=entry_image(entry),
                published=published,
            )
        )

    return result


# ============================================================
# HTML FALLBACK
# ============================================================

def html_fallback(
    source: Source
) -> list[NewsItem]:

    response = safe_get(
        source.url
    )

    if not response or not response.ok:
        return []

    try:

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

    except Exception:
        return []

    result = []
    seen = set()

    for a in soup.find_all(
        "a",
        href=True
    ):

        title = clean_html(
            a.get_text(
                " ",
                strip=True
            )
        )

        if len(title) < 20:
            continue

        url = canonical_url(
            urljoin(
                response.url,
                a["href"]
            )
        )

        if not same_domain(
            url,
            source.domain
        ):
            continue

        if url in seen:
            continue

        seen.add(url)

        result.append(
            NewsItem(
                title=title,
                url=url,
                source=source.name,
                domain=source.domain,
            )
        )

        if len(result) >= MAX_ITEMS_PER_SOURCE:
            break

    return result


# ============================================================
# SCORING
# ============================================================

def score_text(
    text: str
) -> tuple[int, list[str]]:

    text = normalize(text)

    score = 0
    matched = []

    for dictionary in ALL_POSITIVE:

        for keyword, value in dictionary.items():

            if normalize(keyword) in text:

                score += value

                matched.append(
                    keyword
                )

    return score, matched


def is_analysis(
    text: str
) -> bool:

    text = normalize(text)

    count = sum(
        1
        for term in ANALYSIS_TERMS
        if normalize(term) in text
    )

    return count >= 2


def is_excluded(
    text: str
) -> bool:

    text = normalize(text)

    return any(
        normalize(term) in text
        for term in EXCLUDE_TERMS
    )


def detect_topic(
    text: str
) -> tuple[str, str]:

    text = normalize(text)

    # اولویت‌بندی موضوع
    checks = [

        (
            "iran",
            IRAN_KEYWORDS.keys()
        ),

        (
            "gulf",
            GULF_KEYWORDS.keys()
        ),

        (
            "hezbollah",
            [
                "حزب الله",
                "حزب‌الله",
                "نصرالله",
                "لبنان",
                "بیروت",
            ]
        ),

        (
            "palestine",
            [
                "حماس",
                "فلسطین",
                "غزه",
                "قدس",
                "جهاد اسلامی",
                "نتانیاهو",
            ]
        ),

        (
            "yemen",
            [
                "انصارالله",
                "انصار الله",
                "حوثی",
                "یمن",
                "صنعا",
            ]
        ),

        (
            "iraq",
            [
                "حشد الشعبی",
                "حشدالشعبی",
                "کتائب حزب الله",
                "نجباء",
                "بغداد",
            ]
        ),
    ]

    for topic, keywords in checks:

        for keyword in keywords:

            if normalize(keyword) in text:

                return (
                    topic,
                    TOPICS[topic][0]
                )

    return (
        "iran",
        "🇮🇷"
    )


def compute_urgency(
    item: NewsItem
) -> int:

    text = normalize(
        f"{item.title} {item.description}"
    )

    score = 0

    for keyword, value in (
        URGENT_KEYWORDS.items()
    ):

        if normalize(keyword) in text:
            score += value

    for keyword, value in (
        EVENT_KEYWORDS.items()
    ):

        if normalize(keyword) in text:
            score += value

    for keyword, value in (
        CASUALTY_KEYWORDS.items()
    ):

        if normalize(keyword) in text:
            score += value

    age = age_hours(
        item.published
    )

    if age <= 1:
        score += 20

    elif age <= 2:
        score += 15

    elif age <= 3:
        score += 10

    elif age <= 6:
        score += 5

    return score


def evaluate(
    item: NewsItem
) -> bool:

    combined = (
        f"{item.title} "
        f"{item.description}"
    )

    if is_excluded(
        combined
    ):
        return False

    if is_analysis(
        combined
    ):
        return False

    item.score, item.matched = score_text(
        combined
    )

    item.urgency = compute_urgency(
        item
    )

    item.topic, item.flag = detect_topic(
        combined
    )

    age = age_hours(
        item.published
    )

    item.is_urgent = (
        age <= 6
        and item.urgency >= URGENT_MIN_SCORE
    )

    if item.is_urgent:

        return item.score >= (
            MIN_SCORE - 8
        )

    return item.score >= MIN_SCORE


# ============================================================
# SIMILARITY
# ============================================================

def jaccard(
    a: set[str],
    b: set[str]
) -> float:

    if not a or not b:
        return 0.0

    return len(a & b) / len(a | b)


def same_event(
    a: NewsItem,
    b: NewsItem
) -> bool:

    title_a = words(a.title)
    title_b = words(b.title)

    title_similarity = jaccard(
        title_a,
        title_b
    )

    # عنوان تقریباً یکسان
    if title_similarity >= 0.62:
        return True

    content_a = words(
        f"{a.title} {a.description}"
    )

    content_b = words(
        f"{b.title} {b.description}"
    )

    content_similarity = jaccard(
        content_a,
        content_b
    )

    important_a = important_keywords(a)
    important_b = important_keywords(b)

    important_similarity = jaccard(
        important_a,
        important_b
    )

    # متن + موضوع مشترک
    if (
        content_similarity >= 0.45
        and important_similarity >= 0.40
    ):
        return True

    # عنوان نسبتاً مشابه + موضوع مشترک
    if (
        title_similarity >= 0.45
        and important_similarity >= 0.50
    ):
        return True

    return False


def item_priority(
    item: NewsItem
) -> float:

    freshness = max(
        0,
        12 - age_hours(
            item.published
        )
    )

    source_score = SOURCE_PRIORITY.get(
        item.source,
        50
    )

    return (
        item.score
        + item.urgency * 1.5
        + freshness
        + source_score / 10
    )


def dedupe_cross_source(
    items: list[NewsItem]
) -> list[NewsItem]:

    result = []

    seen_urls = set()
    seen_titles = set()
    seen_hashes = set()

    # بهترین خبرها اول
    items = sorted(
        items,
        key=item_priority,
        reverse=True
    )

    for item in items:

        url = canonical_url(
            item.url
        )

        if not url:
            continue

        if url in seen_urls:
            continue

        tf = title_fingerprint(
            item.title
        )

        th = title_hash(
            item.title
        )

        item.event_key = event_fingerprint(
            item
        )

        if tf in seen_titles:
            continue

        if th in seen_hashes:
            continue

        duplicate = False

        for existing in result:

            if same_event(
                item,
                existing
            ):

                log.info(
                    "duplicate │ %s ← %s",
                    item.source,
                    existing.source
                )

                duplicate = True
                break

        if duplicate:
            continue

        seen_urls.add(url)
        seen_titles.add(tf)
        seen_hashes.add(th)

        result.append(item)

    return result


# ============================================================
# ARTICLE IMAGE
# ============================================================

def find_article_image(
    item: NewsItem
) -> str:

    if item.image:
        return item.image

    response = safe_get(
        item.url
    )

    if not response or not response.ok:
        return ""

    try:

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        # OpenGraph
        for prop in (
            "og:image",
            "og:image:url"
        ):

            tag = soup.find(
                "meta",
                property=prop
            )

            if tag and tag.get(
                "content"
            ):

                return urljoin(
                    response.url,
                    tag["content"]
                )

        # Twitter
        tag = soup.find(
            "meta",
            attrs={
                "name": "twitter:image"
            }
        )

        if tag and tag.get(
            "content"
        ):

            return urljoin(
                response.url,
                tag["content"]
            )

        # تصاویر article
        article = soup.find(
            "article"
        )

        containers = (
            [article]
            if article
            else [soup]
        )

        for container in containers:

            for img in container.find_all(
                "img"
            ):

                src = (
                    img.get("src")
                    or img.get("data-src")
                    or img.get("data-lazy-src")
                )

                if not src:
                    continue

                src = urljoin(
                    response.url,
                    src
                )

                if src.startswith(
                    ("http://", "https://")
                ):

                    return src

    except Exception:
        pass

    return ""


def download_image(
    url: str
) -> str:

    if not url:
        return ""

    try:

        response = safe_get(
            url,
            timeout=15
        )

        if not response or not response.ok:
            return ""

        content_type = (
            response.headers
            .get(
                "content-type",
                ""
            )
            .lower()
        )

        if (
            "image" not in content_type
            and not url.lower().endswith(
                (
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp"
                )
            )
        ):
            return ""

        path = os.path.join(
            BASE_DIR,
            "_news_image.jpg"
        )

        with open(
            path,
            "wb"
        ) as f:

            f.write(
                response.content
            )

        return path

    except Exception as exc:

        log.warning(
            "image download failed │ %s",
            exc
        )

        return ""


# ============================================================
# LOGO
# ============================================================

def add_logo(
    image_path: str
) -> str:

    if (
        Image is None
        or not image_path
        or not os.path.exists(
            image_path
        )
        or not os.path.exists(
            LOGO_FILE
        )
    ):
        return image_path

    try:

        base = Image.open(
            image_path
        ).convert("RGBA")

        logo = Image.open(
            LOGO_FILE
        ).convert("RGBA")

        max_width = max(
            80,
            int(base.width * 0.18)
        )

        ratio = (
            max_width
            / logo.width
        )

        logo = logo.resize(
            (
                max_width,
                int(
                    logo.height
                    * ratio
                )
            ),
            Image.LANCZOS
        )

        margin = 20

        position = (
            base.width
            - logo.width
            - margin,

            base.height
            - logo.height
            - margin
        )

        base.alpha_composite(
            logo,
            position
        )

        output = os.path.join(
            BASE_DIR,
            "_news_final.jpg"
        )

        base.convert(
            "RGB"
        ).save(
            output,
            "JPEG",
            quality=92
        )

        return output

    except Exception as exc:

        log.warning(
            "logo failed │ %s",
            exc
        )

        return image_path


# ============================================================
# CAPTION
# ============================================================

DIVIDER = "━━━━━━━━━━━━━━━━━━"


def build_caption(
    item: NewsItem
) -> str:

    if item.is_urgent:

        header = (
            "🚨🔴 <b>خبر فوری</b>"
        )

    elif item.urgency >= (
        URGENT_MIN_SCORE - 5
    ):

        header = (
            "⚡ <b>خبر مهم</b>"
        )

    else:

        header = (
            "📰 <b>خبر ویژه</b>"
        )

    title = escape_html(
        shorten(
            item.title,
            220
        )
    )

    description = escape_html(
        shorten(
            item.description,
            420
        )
    )

    source = escape_html(
        item.source
    )

    topic_name = {
        "iran": "تحولات ایران",
        "gulf": "خلیج فارس و تنگه هرمز",
        "hezbollah": "حزب‌الله لبنان",
        "palestine": "فلسطین و غزه",
        "yemen": "انصارالله یمن",
        "iraq": "حشدالشعبی عراق",
    }.get(
        item.topic,
        "تحولات منطقه"
    )

    lines = [

        header,

        "",

        f"{item.flag}  <b>{title}</b>",

        "",

        description
        if description
        else "",

        "",

        DIVIDER,

        f"🎯 <b>موضوع:</b> {escape_html(topic_name)}",

        f"✍🏼 <b>منبع خبر:</b> {source}",

        f"🕐 <b>زمان:</b> {format_time(item.published)}",

        DIVIDER,

        "",

        "🌐 <b>جهان‌تاب</b>",

        "<i>آخرین تحولات جهان</i>",
    ]

    # خطوط خالی اضافه حذف شوند
    return "\n".join(lines)


# ============================================================
# TELEGRAM
# ============================================================

def telegram_endpoint(
    method: str
) -> str:

    return (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/{method}"
    )


def telegram_request(
    method: str,
    payload=None,
    files=None
) -> dict:

    try:

        response = requests.post(
            telegram_endpoint(method),
            data=payload,
            files=files,
            timeout=40
        )

        try:
            data = response.json()

        except Exception:
            data = {
                "ok": False,
                "description": response.text
            }

        if not data.get("ok"):

            log.error(
                "Telegram error │ %s",
                data
            )

        return data

    except Exception as exc:

        log.error(
            "Telegram request failed │ %s",
            exc
        )

        return {
            "ok": False,
            "description": str(exc)
        }


def send_post(
    image_path: str,
    caption: str,
    article_url: str
) -> bool:

    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "🔗 مشاهده خبر",
                    "url": article_url
                }
            ]
        ]
    }

    reply_markup = json.dumps(
        keyboard,
        ensure_ascii=False
    )

    if (
        image_path
        and os.path.exists(
            image_path
        )
    ):

        payload = {
            "chat_id": CHAT_ID,
            "caption": caption,
            "parse_mode": "HTML",
            "reply_markup": reply_markup,
        }

        try:

            with open(
                image_path,
                "rb"
            ) as photo:

                result = telegram_request(
                    "sendPhoto",
                    payload=payload,
                    files={
                        "photo": photo
                    }
                )

            return bool(
                result.get("ok")
            )

        except Exception as exc:

            log.error(
                "sendPhoto failed │ %s",
                exc
            )

    # fallback بدون عکس
    result = telegram_request(
        "sendMessage",
        payload={
            "chat_id": CHAT_ID,
            "text": caption,
            "parse_mode": "HTML",
            "reply_markup": reply_markup,
        }
    )

    return bool(
        result.get("ok")
    )


# ============================================================
# COLLECT
# ============================================================

def collect_items() -> list[NewsItem]:

    all_items = []

    for source in SOURCES:

        log.info(
            "→ %s",
            source.name
        )

        source_items = []

        for feed_url in discover_feeds(
            source
        ):

            parsed = parse_feed(
                source,
                feed_url
            )

            if parsed:

                source_items.extend(
                    parsed
                )

                if len(
                    source_items
                ) >= MAX_ITEMS_PER_SOURCE:

                    break

        if not source_items:

            source_items = html_fallback(
                source
            )

        unique = {}

        for item in source_items:

            key = canonical_url(
                item.url
            )

            if key and key not in unique:

                unique[key] = item

        all_items.extend(
            list(unique.values())[
                :MAX_ITEMS_PER_SOURCE
            ]
        )

    return all_items


# ============================================================
# FILTER
# ============================================================

def filter_items(
    items: list[NewsItem]
) -> list[NewsItem]:

    sent_links = load_sent_links()
    sent_titles = load_sent_titles()
    sent_events = load_sent_events()

    result = []

    for item in items:

        url = canonical_url(
            item.url
        )

        if not url:
            continue

        if url in sent_links:
            continue

        tf = title_fingerprint(
            item.title
        )

        if tf in sent_titles:
            continue

        th = title_hash(
            item.title
        )

        if "H:" + th in sent_titles:
            continue

        # خبر خیلی قدیمی
        if age_hours(
            item.published
        ) > MAX_AGE_HOURS:

            continue

        if not evaluate(item):
            continue

        item.event_key = event_fingerprint(
            item
        )

        if item.event_key in sent_events:
            continue

        result.append(item)

    return result


# ============================================================
# SORT
# ============================================================

def sort_items(
    items: list[NewsItem]
) -> list[NewsItem]:

    return sorted(
        items,
        key=lambda item: (
            1 if item.is_urgent else 0,
            item_priority(item)
        ),
        reverse=True
    )


# ============================================================
# RUN ONCE
# ============================================================

def run_once() -> int:

    log.info(
        "┌─ JAHANTAB cycle start"
    )

    collected = collect_items()

    log.info(
        "│ collected: %d",
        len(collected)
    )

    filtered = filter_items(
        collected
    )

    log.info(
        "│ after filter: %d",
        len(filtered)
    )

    deduped = dedupe_cross_source(
        filtered
    )

    log.info(
        "│ after cross-source dedupe: %d",
        len(deduped)
    )

    selected = sort_items(
        deduped
    )[
        :MAX_POSTS_PER_RUN
    ]

    log.info(
        "│ selected: %d",
        len(selected)
    )

    sent_count = 0

    for item in selected:

        try:

            image_url = find_article_image(
                item
            )

            image_path = download_image(
                image_url
            )

            if image_path:

                image_path = add_logo(
                    image_path
                )

            caption = build_caption(
                item
            )

            success = send_post(
                image_path,
                caption,
                item.url
            )

            if success:

                save_sent_item(
                    item
                )

                sent_count += 1

                log.info(
                    "│ ✅ SENT │ %s │ %s",
                    item.source,
                    item.title[:80]
                )

            else:

                log.error(
                    "│ ❌ SEND FAILED │ %s",
                    item.title[:80]
                )

        except Exception as exc:

            log.exception(
                "│ item failed │ %s",
                exc
            )

    log.info(
        "└─ cycle finished │ sent=%d",
        sent_count
    )

    return sent_count


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN تنظیم نشده است."
        )

    log.info("=" * 60)

    log.info(
        "🌐 JAHANTAB News Bot"
    )

    log.info(
        "📡 Channel: %s",
        CHAT_ID
    )

    log.info(
        "📰 Sources: %d",
        len(SOURCES)
    )

    log.info(
        "⏱ GitHub Actions mode: ONE CYCLE"
    )

    log.info("=" * 60)

    # مهم:
    # در GitHub Actions فقط یک بار اجرا می‌شود.
    # زمان‌بندی را خود GitHub Actions انجام می‌دهد.
    run_once()


if __name__ == "__main__":
    main()