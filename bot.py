# -*- coding: utf-8 -*-

"""
JAHANTAB Telegram News Bot
نسخه نهایی

🌐 جهان‌تاب | آخرین تحولات جهان

ویژگی‌ها:
- RSS + HTML fallback
- منابع متعدد فارسی
- فیلتر اخبار مرتبط با ایران و منطقه
- حذف اخبار قدیمی
- حذف اخبار تحلیلی
- حذف اخبار نامرتبط
- حذف تکراری بر اساس URL
- حذف تکراری بر اساس عنوان
- جلوگیری از انتشار یک رویداد از چند منبع
- تشخیص شباهت تیترهای متفاوت
- اولویت دادن به خبر جدیدتر و امتیاز بالاتر
- ذخیره دائمی خبرهای ارسال‌شده
- دریافت تصویر خبر
- افزودن لوگو روی تصویر
- کپشن حرفه‌ای
- دکمه شیشه‌ای «مشاهده خبر»
"""

import os
import re
import time
import html
import json
import logging
from datetime import datetime, timezone
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


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

CHAT_ID = (
    os.getenv("CHAT_ID", "").strip()
    or os.getenv("CHANNEL", "").strip()
    or "@jahantab_news"
)

MAX_AGE_HOURS = int(
    os.getenv("MAX_AGE_HOURS", "24")
)

URGENT_HOURS = int(
    os.getenv("URGENT_HOURS", "6")
)

MIN_SCORE = int(
    os.getenv("MIN_SCORE", "16")
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

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

SENT_FILE = os.path.join(
    BASE_DIR,
    os.getenv(
        "SENT_FILE",
        "sent_links.txt"
    )
)

SENT_TITLES_FILE = os.path.join(
    BASE_DIR,
    os.getenv(
        "SENT_TITLES_FILE",
        "sent_titles.txt"
    )
)

LOGO_FILE = os.path.join(
    BASE_DIR,
    os.getenv(
        "LOGO_FILE",
        "logo.jpg"
    )
)


# ============================================================
# USER AGENT
# ============================================================

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/128.0 Safari/537.36 "
    "JAHANTAB-NewsBot/5.0"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.5",
}


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

log = logging.getLogger("JAHANTAB")


# ============================================================
# SOURCES
# ============================================================

SOURCES = [
    {
        "name": "خبرآنلاین",
        "domain": "khabaronline.ir",
        "url": "https://www.khabaronline.ir/",
    },
    {
        "name": "فرارو",
        "domain": "fararu.com",
        "url": "https://fararu.com/",
    },
    {
        "name": "تابناک",
        "domain": "tabnak.ir",
        "url": "https://www.tabnak.ir/",
    },
    {
        "name": "مشرق نیوز",
        "domain": "mashreghnews.ir",
        "url": "https://www.mashreghnews.ir/",
    },
    {
        "name": "عصر ایران",
        "domain": "asriran.com",
        "url": "https://www.asriran.com/",
    },
    {
        "name": "الف",
        "domain": "alef.ir",
        "url": "https://www.alef.ir/",
    },
    {
        "name": "انتخاب",
        "domain": "entekhab.ir",
        "url": "https://www.entekhab.ir/",
    },
    {
        "name": "شرق",
        "domain": "sharghdaily.com",
        "url": "https://www.sharghdaily.com/",
    },
    {
        "name": "همشهری آنلاین",
        "domain": "hamshahrionline.ir",
        "url": "https://www.hamshahrionline.ir/",
    },
    {
        "name": "روزنامه ایران",
        "domain": "irannewspaper.ir",
        "url": "https://www.irannewspaper.ir/",
    },
    {
        "name": "اطلاعات",
        "domain": "ettelaat.com",
        "url": "https://www.ettelaat.com/",
    },
    {
        "name": "کیهان",
        "domain": "kayhan.ir",
        "url": "https://kayhan.ir/",
    },
    {
        "name": "اعتماد",
        "domain": "etemadnewspaper.ir",
        "url": "https://www.etemadnewspaper.ir/",
    },
    {
        "name": "رسالت",
        "domain": "resalat-news.com",
        "url": "https://resalat-news.com/",
    },
    {
        "name": "ابتکار",
        "domain": "ebtekarnews.com",
        "url": "https://www.ebtekarnews.com/",
    },
    {
        "name": "وطن امروز",
        "domain": "vatanemrooz.ir",
        "url": "https://vatanemrooz.ir/",
    },
    {
        "name": "ایرنا",
        "domain": "irna.ir",
        "url": "https://www.irna.ir/",
    },
    {
        "name": "ایسنا",
        "domain": "isna.ir",
        "url": "https://www.isna.ir/",
    },
    {
        "name": "فارس",
        "domain": "farsnews.ir",
        "url": "https://www.farsnews.ir/",
    },
    {
        "name": "تسنیم",
        "domain": "tasnimnews.com",
        "url": "https://www.tasnimnews.com/fa",
    },
    {
        "name": "مهر",
        "domain": "mehrnews.com",
        "url": "https://www.mehrnews.com/",
    },
    {
        "name": "IRIB",
        "domain": "iribnews.ir",
        "url": "https://www.iribnews.ir/",
    },
    {
        "name": "باشگاه خبرنگاران جوان",
        "domain": "yjc.ir",
        "url": "https://www.yjc.ir/",
    },
    {
        "name": "ایبنا",
        "domain": "ibna.ir",
        "url": "https://www.ibna.ir/",
    },
    {
        "name": "خبرگزاری میراث فرهنگی",
        "domain": "chn.ir",
        "url": "https://www.chn.ir/",
    },
    {
        "name": "ایلنا",
        "domain": "ilna.ir",
        "url": "https://www.ilna.ir/",
    },
    {
        "name": "ایکنا",
        "domain": "iqna.ir",
        "url": "https://iqna.ir/",
    },
    {
        "name": "خبر فوری",
        "domain": "khabarfoori.com",
        "url": "https://www.khabarfoori.com/",
    },
    {
        "name": "آخرین خبر",
        "domain": "akharinkhabar.ir",
        "url": "https://akharinkhabar.ir/",
    },
    {
        "name": "روزپلاس",
        "domain": "roozplus.com",
        "url": "https://roozplus.com/",
    },
]


# ============================================================
# KEYWORDS
# ============================================================

CORE_ENTITIES = {
    "ایران": 5,
    "جمهوری اسلامی": 5,
    "اسرائیل": 4,
    "رژیم صهیونیستی": 4,
    "آمریکا": 3,
    "ایالات متحده": 3,
    "سپاه": 5,
    "سپاه پاسداران": 5,
    "ارتش": 4,
    "حزب الله": 5,
    "حزب‌الله": 5,
    "لبنان": 3,
    "حماس": 5,
    "فلسطین": 3,
    "غزه": 4,
    "یمن": 3,
    "حوثی": 5,
    "حوثی‌ها": 5,
    "انصارالله": 5,
    "عراق": 2,
    "سوریه": 2,
    "مقاومت": 4,
    "محور مقاومت": 5,
    "هرمز": 5,
    "تنگه هرمز": 6,
    "باب المندب": 5,
    "باب‌المندب": 5,
}

MILITARY_ACTIONS = {
    "حمله": 7,
    "حملات": 7,
    "حمله هوایی": 9,
    "حملات هوایی": 9,
    "بمباران": 8,
    "موشک": 8,
    "موشکی": 8,
    "موشکباران": 9,
    "موشک‌باران": 9,
    "پهپاد": 7,
    "پهپادی": 7,
    "شلیک": 7,
    "اصابت": 8,
    "رهگیری": 6,
    "انفجار": 7,
    "عملیات": 6,
    "عملیات نظامی": 8,
    "درگیری": 7,
    "درگیری نظامی": 8,
    "تبادل آتش": 8,
    "هدف قرار داد": 8,
    "هدف قرار گرفت": 8,
    "سرنگونی": 8,
    "توقیف": 7,
    "حمله موشکی": 9,
    "حمله پهپادی": 9,
    "پایگاه": 6,
    "پایگاه نظامی": 8,
    "تاسیسات نظامی": 7,
    "تأسیسات نظامی": 7,
    "تاسیسات هسته‌ای": 8,
    "تأسیسات هسته‌ای": 8,
    "نیروهای آمریکایی": 6,
    "نیروهای اسرائیلی": 6,
    "ارتش اسرائیل": 6,
    "نیروی هوایی": 5,
    "نیروی دریایی": 5,
}

MAJOR_EVENTS = {
    "آتش بس": 10,
    "آتش‌بس": 10,
    "پایان جنگ": 12,
    "آغاز جنگ": 12,
    "اعلام جنگ": 12,
    "ورود به جنگ": 11,
    "گسترش جنگ": 8,
    "تشدید درگیری": 8,
    "تشدید تنش": 5,
    "حمله گسترده": 10,
    "عملیات گسترده": 9,
    "حمله مستقیم": 10,
    "حمله متقابل": 9,
    "پاسخ موشکی": 9,
    "پاسخ نظامی": 8,
    "تنگه هرمز": 10,
    "بسته شدن تنگه هرمز": 15,
    "بازگشایی تنگه هرمز": 12,
    "باب‌المندب": 9,
    "پایگاه آمریکایی": 9,
    "پایگاه آمریکا": 9,
    "پایگاه اسرائیل": 9,
}

URGENT_TERMS = {
    "فوری": 8,
    "خبر فوری": 12,
    "لحظاتی پیش": 10,
    "دقایقی پیش": 10,
    "همین الان": 10,
    "هم‌اکنون": 10,
    "هم اکنون": 10,
    "خبر مهم": 7,
    "لحظه به لحظه": 7,
    "اولین خبر": 5,
    "تازه‌ترین": 4,
    "تازه ترین": 4,
}

CASUALTY_TERMS = {
    "کشته": 7,
    "کشته‌ها": 7,
    "کشته شد": 8,
    "مجروح": 6,
    "زخمی": 6,
    "تلفات": 7,
    "تلفات سنگین": 9,
    "انفجار": 7,
    "آتش سوزی": 5,
    "آتش‌سوزی": 5,
}

ANALYSIS_TERMS = {
    "تحلیل": -8,
    "یادداشت": -9,
    "کارشناس": -6,
    "کارشناسان": -6,
    "گفتگو": -6,
    "گفت‌وگو": -6,
    "گفت و گو": -6,
    "بررسی": -5,
    "چرا": -5,
    "چگونه": -5,
    "روایت": -4,
    "تحلیلگر": -7,
    "تحلیل‌گر": -7,
    "سناریو": -6,
    "پیش بینی": -7,
    "پیش‌بینی": -7,
    "آینده جنگ": -6,
    "نگاهی به": -5,
    "گزارش تحلیلی": -9,
}

EXCLUDE_TERMS = {
    "ورزش": -20,
    "فوتبال": -20,
    "والیبال": -20,
    "بسکتبال": -20,
    "سینما": -20,
    "تلویزیون": -20,
    "موسیقی": -20,
    "سلامت": -15,
    "پزشکی": -15,
    "کنکور": -20,
    "دانشگاه": -15,
    "هواشناسی": -15,
    "بورس": -14,
    "دلار": -10,
    "طلا": -10,
    "سکه": -10,
    "خودرو": -15,
    "مسکن": -15,
    "اقتصاد": -10,
    "بازنشستگی": -15,
}


# ============================================================
# SESSION
# ============================================================

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# ============================================================
# TEXT
# ============================================================

def normalize_text(text):
    if not text:
        return ""

    text = html.unescape(str(text))

    replacements = {
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

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip().lower()


def clean_html(text):
    if not text:
        return ""

    soup = BeautifulSoup(
        str(text),
        "html.parser"
    )

    for tag in soup(
        ["script", "style", "noscript"]
    ):
        tag.decompose()

    result = soup.get_text(
        " ",
        strip=True
    )

    result = html.unescape(result)

    result = re.sub(
        r"\s+",
        " ",
        result
    )

    return result.strip()


def shorten(text, max_len):
    text = clean_html(text)

    if len(text) <= max_len:
        return text

    cut = text[:max_len]

    if " " in cut:
        cut = cut.rsplit(
            " ",
            1
        )[0]

    return cut.rstrip(
        " .،؛:"
    ) + "…"


# ============================================================
# URL
# ============================================================

def canonical_url(url):
    if not url:
        return ""

    try:
        parsed = urlparse(url)

        scheme = (
            parsed.scheme.lower()
            or "https"
        )

        netloc = parsed.netloc.lower()

        if netloc.startswith("www."):
            netloc = netloc[4:]

        path = parsed.path or "/"

        if (
            path != "/"
            and path.endswith("/")
        ):
            path = path[:-1]

        return urlunparse(
            (
                scheme,
                netloc,
                path,
                "",
                "",
                "",
            )
        )

    except Exception:
        return url.strip()


def same_domain(url, domain):
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
            or host.endswith(
                "." + domain
            )
        )

    except Exception:
        return False


# ============================================================
# HTTP
# ============================================================

def safe_get(url, **kwargs):
    try:
        timeout = kwargs.pop(
            "timeout",
            HTTP_TIMEOUT
        )

        return SESSION.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            **kwargs,
        )

    except requests.RequestException as e:
        log.warning(
            "GET failed | %s | %s",
            url,
            e
        )
        return None


# ============================================================
# SENT DATA
# ============================================================

def load_lines(filename):
    if not os.path.exists(filename):
        return set()

    try:
        with open(
            filename,
            "r",
            encoding="utf-8"
        ) as f:
            return {
                line.strip()
                for line in f
                if line.strip()
            }

    except Exception as e:
        log.warning(
            "Could not read %s | %s",
            filename,
            e
        )
        return set()


def load_sent_links():
    return {
        canonical_url(x)
        for x in load_lines(
            SENT_FILE
        )
    }


def load_sent_titles():
    return load_lines(
        SENT_TITLES_FILE
    )


def title_fingerprint(title):
    text = normalize_text(
        title
    )

    text = re.sub(
        r"[^\w\sآ-ی]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    return text


def save_sent_item(
    url,
    title
):
    try:
        with open(
            SENT_FILE,
            "a",
            encoding="utf-8"
        ) as f:
            f.write(
                canonical_url(url)
                + "\n"
            )

        fingerprint = title_fingerprint(
            title
        )

        if fingerprint:
            with open(
                SENT_TITLES_FILE,
                "a",
                encoding="utf-8"
            ) as f:
                f.write(
                    fingerprint
                    + "\n"
                )

        return True

    except Exception as e:
        log.error(
            "Could not save sent item | %s",
            e
        )
        return False


# ============================================================
# DATE
# ============================================================

def parse_datetime(value):
    if not value:
        return None

    try:
        if hasattr(
            value,
            "tm_year"
        ):
            return datetime(
                value.tm_year,
                value.tm_mon,
                value.tm_mday,
                value.tm_hour,
                value.tm_min,
                value.tm_sec,
                tzinfo=timezone.utc,
            )
    except Exception:
        pass

    if isinstance(
        value,
        datetime
    ):
        if value.tzinfo is None:
            return value.replace(
                tzinfo=timezone.utc
            )

        return value.astimezone(
            timezone.utc
        )

    return None


def age_hours(dt):
    if not dt:
        return 999999

    now = datetime.now(
        timezone.utc
    )

    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=timezone.utc
        )

    delta = (
        now -
        dt.astimezone(
            timezone.utc
        )
    )

    return max(
        0,
        delta.total_seconds() / 3600
    )


# ============================================================
# RSS
# ============================================================

def discover_feeds(source):
    feeds = []

    paths = [
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

    for path in paths:
        feeds.append(
            urljoin(
                source["url"],
                path
            )
        )

    response = safe_get(
        source["url"]
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
                    link.get(
                        "type"
                    )
                    or ""
                ).lower()

                rel_text = (
                    " ".join(rel)
                    if isinstance(
                        rel,
                        list
                    )
                    else str(rel)
                ).lower()

                if (
                    "alternate"
                    in rel_text
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
                        feeds.insert(
                            0,
                            urljoin(
                                response.url,
                                href
                            )
                        )

        except Exception:
            pass

    result = []

    for url in feeds:
        url = canonical_url(
            url
        )

        if (
            url
            and url not in result
        ):
            result.append(url)

    return result[:20]


def extract_entry_image(entry):
    candidates = []

    for media in entry.get(
        "media_content",
        []
    ):
        if isinstance(
            media,
            dict
        ):
            candidates.append(
                media.get("url")
            )

    for media in entry.get(
        "media_thumbnail",
        []
    ):
        if isinstance(
            media,
            dict
        ):
            candidates.append(
                media.get("url")
            )

    for enc in entry.get(
        "enclosures",
        []
    ):
        if isinstance(
            enc,
            dict
        ):
            candidates.append(
                enc.get("href")
            )
            candidates.append(
                enc.get("url")
            )

    for item in candidates:
        if item and item.startswith(
            (
                "http://",
                "https://"
            )
        ):
            return item

    return ""


def parse_feed(
    source,
    feed_url
):
    if feedparser is None:
        return []

    response = safe_get(
        feed_url,
        headers={
            **HEADERS,
            "Accept": (
                "application/rss+xml,"
                "application/atom+xml,"
                "application/xml,"
                "text/xml,"
                "text/html"
            ),
        },
    )

    if not response or not response.ok:
        return []

    try:
        parsed = feedparser.parse(
            response.content
        )
    except Exception:
        return []

    if not parsed.entries:
        return []

    items = []

    for entry in parsed.entries[
        :MAX_ITEMS_PER_SOURCE
    ]:

        title = clean_html(
            entry.get(
                "title",
                ""
            )
        )

        url = entry.get(
            "link",
            ""
        )

        if not title or not url:
            continue

        url = canonical_url(
            url
        )

        description = clean_html(
            entry.get(
                "summary",
                ""
            )
        )

        published = None

        for field in (
            "published_parsed",
            "updated_parsed",
            "created_parsed",
        ):
            published = parse_datetime(
                entry.get(field)
            )

            if published:
                break

        image = extract_entry_image(
            entry
        )

        items.append({
            "title": title,
            "url": url,
            "description": description,
            "published": published,
            "image": image,
            "source": source["name"],
            "domain": source["domain"],
        })

    return items


# ============================================================
# HTML FALLBACK
# ============================================================

def html_fallback(source):
    response = safe_get(
        source["url"]
    )

    if not response or not response.ok:
        return []

    try:
        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        items = []

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

            href = urljoin(
                response.url,
                a["href"]
            )

            if len(title) < 20:
                continue

            if not href.startswith(
                ("http://", "https://")
            ):
                continue

            if not same_domain(
                href,
                source["domain"]
            ):
                continue

            items.append({
                "title": title,
                "url": canonical_url(
                    href
                ),
                "description": "",
                "published": None,
                "image": "",
                "source": source["name"],
                "domain": source["domain"],
            })

            if (
                len(items)
                >= MAX_ITEMS_PER_SOURCE
            ):
                break

        return items

    except Exception:
        return []


# ============================================================
# SCORING
# ============================================================

def score_text(text):
    text = normalize_text(
        text
    )

    score = 0
    matched = []

    dictionaries = [
        CORE_ENTITIES,
        MILITARY_ACTIONS,
        MAJOR_EVENTS,
        URGENT_TERMS,
        CASUALTY_TERMS,
        ANALYSIS_TERMS,
        EXCLUDE_TERMS,
    ]

    for dictionary in dictionaries:
        for keyword, value in dictionary.items():

            normalized_keyword = (
                normalize_text(keyword)
            )

            if normalized_keyword in text:
                score += value
                matched.append(
                    keyword
                )

    return score, matched


def is_analysis(text):
    text = normalize_text(
        text
    )

    hits = 0

    for keyword in ANALYSIS_TERMS:
        if normalize_text(keyword) in text:
            hits += 1

    return hits >= 2


def is_excluded(text):
    text = normalize_text(
        text
    )

    for keyword in EXCLUDE_TERMS:
        if normalize_text(keyword) in text:
            return True

    return False


def is_relevant(item):
    combined = (
        item["title"]
        + " "
        + item.get(
            "description",
            ""
        )
    )

    if is_excluded(combined):
        return False

    if is_analysis(combined):
        return False

    score, matched = score_text(
        combined
    )

    item["score"] = score
    item["matched"] = matched

    return score >= MIN_SCORE


# ============================================================
# SIMILARITY
# ============================================================

STOPWORDS = {
    "از",
    "به",
    "در",
    "با",
    "برای",
    "که",
    "و",
    "را",
    "این",
    "آن",
    "یک",
    "های",
    "کرد",
    "شد",
    "است",
    "بر",
    "تا",
    "وی",
    "او",
    "نیز",
    "اما",
    "هم",
    "یا",
    "پس",
}


def title_words(title):
    text = normalize_text(
        title
    )

    words = re.findall(
        r"[\wآ-ی]+",
        text
    )

    return {
        x
        for x in words
        if len(x) > 2
        and x not in STOPWORDS
    }


def content_words(item):
    text = (
        item.get(
            "title",
            ""
        )
        + " "
        + item.get(
            "description",
            ""
        )
    )

    text = normalize_text(
        text
    )

    words = re.findall(
        r"[\wآ-ی]+",
        text
    )

    return {
        x
        for x in words
        if len(x) > 2
        and x not in STOPWORDS
    }


def jaccard(set_a, set_b):
    if not set_a or not set_b:
        return 0.0

    return len(
        set_a & set_b
    ) / len(
        set_a | set_b
    )


def title_similarity(a, b):
    return jaccard(
        title_words(a),
        title_words(b)
    )


def event_similarity(a, b):
    """
    تشخیص خبرهای مربوط به یک رویداد
    حتی وقتی تیترها کاملاً یکسان نیستند.
    """

    title_sim = title_similarity(
        a["title"],
        b["title"]
    )

    content_sim = jaccard(
        content_words(a),
        content_words(b)
    )

    combined_text_a = normalize_text(
        a["title"]
        + " "
        + a.get(
            "description",
            ""
        )
    )

    combined_text_b = normalize_text(
        b["title"]
        + " "
        + b.get(
            "description",
            ""
        )
    )

    important_hits_a = {
        keyword
        for keyword in (
            list(CORE_ENTITIES.keys())
            + list(MILITARY_ACTIONS.keys())
            + list(MAJOR_EVENTS.keys())
        )
        if normalize_text(keyword)
        in combined_text_a
    }

    important_hits_b = {
        keyword
        for keyword in (
            list(CORE_ENTITIES.keys())
            + list(MILITARY_ACTIONS.keys())
            + list(MAJOR_EVENTS.keys())
        )
        if normalize_text(keyword)
        in combined_text_b
    }

    important_sim = jaccard(
        important_hits_a,
        important_hits_b
    )

    # تیتر تقریباً یکسان
    if title_sim >= 0.70:
        return True

    # متن و کلیدواژه‌های اصلی بسیار نزدیک
    if (
        content_sim >= 0.48
        and important_sim >= 0.35
    ):
        return True

    # وقتی تیتر متفاوت است ولی عناصر اصلی یکسان‌اند
    if (
        title_sim >= 0.45
        and important_sim >= 0.55
    ):
        return True

    return False


def item_priority(item):
    """
    هرچه مقدار بیشتر باشد،
    خبر برای نگه‌داشتن اولویت بیشتری دارد.
    """

    score = item.get(
        "score",
        0
    )

    age = age_hours(
        item.get(
            "published"
        )
    )

    freshness_bonus = max(
        0,
        12 - age
    )

    source_bonus = {
        "ایرنا": 2,
        "ایسنا": 2,
        "فارس": 2,
        "تسنیم": 2,
        "مهر": 2,
        "IRIB": 2,
    }.get(
        item.get(
            "source"
        ),
        0
    )

    return (
        score
        + freshness_bonus
        + source_bonus
    )


def remove_cross_source_duplicates(items):
    """
    اگر چند خبر از منابع مختلف درباره یک رویداد باشند،
    فقط یک نسخه نگه داشته می‌شود.
    """

    result = []

    ordered = sorted(
        items,
        key=item_priority,
        reverse=True
    )

    for item in ordered:

        duplicate = False

        for existing in result:

            # اگر دقیقاً یک URL باشند
            if (
                canonical_url(
                    item["url"]
                )
                ==
                canonical_url(
                    existing["url"]
                )
            ):
                duplicate = True
                break

            # اگر یک رویداد باشند
            if event_similarity(
                item,
                existing
            ):
                duplicate = True

                log.info(
                    "CROSS SOURCE DUPLICATE | %s | %s | kept=%s",
                    item["source"],
                    item["title"],
                    existing["source"]
                )

                break

        if not duplicate:
            result.append(
                item
            )

    return result


# ============================================================
# ARTICLE IMAGE
# ============================================================

def find_article_image(item):

    if item.get("image"):
        return item["image"]

    response = safe_get(
        item["url"]
    )

    if not response or not response.ok:
        return ""

    try:
        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        og = soup.find(
            "meta",
            property="og:image"
        )

        if (
            og
            and og.get("content")
        ):
            return urljoin(
                response.url,
                og["content"]
            )

        twitter = soup.find(
            "meta",
            attrs={
                "name": "twitter:image"
            }
        )

        if (
            twitter
            and twitter.get(
                "content"
            )
        ):
            return urljoin(
                response.url,
                twitter["content"]
            )

        for img in soup.find_all(
            "img",
            src=True
        ):
            src = urljoin(
                response.url,
                img["src"]
            )

            if src.startswith(
                ("http://", "https://")
            ):
                return src

    except Exception:
        pass

    return ""


def download_image(url):

    if not url:
        return ""

    try:
        response = safe_get(
            url,
            timeout=15
        )

        if (
            not response
            or not response.ok
        ):
            return ""

        content_type = (
            response.headers.get(
                "content-type",
                ""
            ).lower()
        )

        if (
            "image"
            not in content_type
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

        filename = os.path.join(
            BASE_DIR,
            "_news_image.jpg"
        )

        with open(
            filename,
            "wb"
        ) as f:
            f.write(
                response.content
            )

        return filename

    except Exception as e:

        log.warning(
            "Image download failed | %s",
            e
        )

        return ""


# ============================================================
# LOGO
# ============================================================

def add_logo(image_path):

    if (
        Image is None
        or not image_path
        or not os.path.exists(
            LOGO_FILE
        )
    ):
        return image_path

    try:

        base = Image.open(
            image_path
        ).convert(
            "RGBA"
        )

        logo = Image.open(
            LOGO_FILE
        ).convert(
            "RGBA"
        )

        max_width = max(
            80,
            int(
                base.width * 0.18
            )
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
                ),
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
            - margin,
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

    except Exception as e:

        log.warning(
            "Logo failed | %s",
            e
        )

        return image_path


# ============================================================
# TELEGRAM CAPTION
# ============================================================

def escape_html(text):
    return html.escape(
        str(text or ""),
        quote=False
    )


def format_time(dt):

    if not dt:
        return "نامشخص"

    try:
        return dt.astimezone(
            timezone.utc
        ).strftime(
            "%H:%M"
        )

    except Exception:
        return "نامشخص"


def is_urgent(item):

    text = normalize_text(
        item["title"]
        + " "
        + item.get(
            "description",
            ""
        )
    )

    if (
        age_hours(
            item.get(
                "published"
            )
        )
        <= URGENT_HOURS
    ):

        for keyword in URGENT_TERMS:

            if (
                normalize_text(
                    keyword
                )
                in text
            ):
                return True

    return False


def build_caption(item):

    urgent = is_urgent(
        item
    )

    title = escape_html(
        shorten(
            item["title"],
            220
        )
    )

    description = shorten(
        item.get(
            "description",
            ""
        ),
        430
    )

    if description:
        description = escape_html(
            description
        )

    source = escape_html(
        item["source"]
    )

    time_text = format_time(
        item.get(
            "published"
        )
    )

    if urgent:
        header = (
            "🚨 <b>خبر فوری</b>"
        )
    else:
        header = (
            "📰 <b>خبر جدید</b>"
        )

    lines = [
        header,
        "",
        f"<b>{title}</b>",
        "",
        "━━━━━━━━━━━━━━",
        f"🗞 <b>منبع:</b> {source}",
        f"🕐 <b>زمان:</b> {time_text}",
        "━━━━━━━━━━━━━━",
    ]

    if description:
        lines.extend(
            [
                "",
                description,
            ]
        )

    lines.extend(
        [
            "",
            "━━━━━━━━━━━━━━",
            "🌐 <b>جهان‌تاب | آخرین تحولات جهان</b>",
        ]
    )

    return "\n".join(
        lines
    )


# ============================================================
# TELEGRAM API
# ============================================================

def telegram_url(method):

    return (
        "https://api.telegram.org/"
        f"bot{BOT_TOKEN}/{method}"
    )


def telegram_request(
    method,
    payload=None,
    files=None
):

    try:

        response = requests.post(
            telegram_url(
                method
            ),
            data=payload,
            files=files,
            timeout=30
        )

        data = response.json()

        if not data.get("ok"):

            log.error(
                "Telegram error | %s",
                data
            )

        return data

    except Exception as e:

        log.error(
            "Telegram request failed | %s",
            e
        )

        return {
            "ok": False,
            "description": str(e)
        }


def send_photo(
    image_path,
    caption,
    article_url
):

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

    payload = {
        "chat_id": CHAT_ID,
        "caption": caption,
        "parse_mode": "HTML",
        "reply_markup": reply_markup,
    }

    try:

        if (
            image_path
            and os.path.exists(
                image_path
            )
        ):

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

        else:

            result = telegram_request(
                "sendMessage",
                payload={
                    "chat_id": CHAT_ID,
                    "text": caption,
                    "parse_mode": "HTML",
                    "reply_markup": reply_markup,
                }
            )

        return result.get(
            "ok",
            False
        )

    except Exception as e:

        log.error(
            "Send failed | %s",
            e
        )

        return False


# ============================================================
# COLLECT
# ============================================================

def collect_items():

    all_items = []

    for source in SOURCES:

        log.info(
            "Checking source | %s",
            source["name"]
        )

        source_items = []

        feeds = discover_feeds(
            source
        )

        for feed in feeds:

            parsed = parse_feed(
                source,
                feed
            )

            if parsed:

                source_items.extend(
                    parsed
                )

                if (
                    len(source_items)
                    >= MAX_ITEMS_PER_SOURCE
                ):
                    break

        if not source_items:

            source_items = html_fallback(
                source
            )

        unique = {}

        for item in source_items:

            key = canonical_url(
                item["url"]
            )

            if key:
                unique[key] = item

        all_items.extend(
            list(
                unique.values()
            )[
                :MAX_ITEMS_PER_SOURCE
            ]
        )

    return all_items


# ============================================================
# FILTER
# ============================================================

def filter_items(items):

    sent_links = load_sent_links()
    sent_titles = load_sent_titles()

    result = []

    for item in items:

        url = canonical_url(
            item["url"]
        )

        fingerprint = title_fingerprint(
            item["title"]
        )

        if not url:
            continue

        if url in sent_links:
            continue

        if (
            fingerprint
            and fingerprint in sent_titles
        ):
            continue

        age = age_hours(
            item.get(
                "published"
            )
        )

        if age > MAX_AGE_HOURS:
            continue

        if not is_relevant(
            item
        ):
            continue

        result.append(
            item
        )

    return result


# ============================================================
# SORT
# ============================================================

def sort_items(items):

    return sorted(
        items,
        key=lambda x: (
            1 if is_urgent(x) else 0,
            item_priority(x),
        ),
        reverse=True
    )


# ============================================================
# MAIN
# ============================================================

def main():

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN تنظیم نشده است."
        )

    log.info(
        "========================================"
    )

    log.info(
        "JAHANTAB Telegram Bot started"
    )

    log.info(
        "Channel: %s",
        CHAT_ID
    )

    # --------------------------------------------------------
    # دریافت خبرها
    # --------------------------------------------------------

    items = collect_items()

    log.info(
        "Collected: %s",
        len(items)
    )

    # --------------------------------------------------------
    # فیلتر اولیه
    # --------------------------------------------------------

    items = filter_items(
        items
    )

    log.info(
        "After filtering: %s",
        len(items)
    )

    # --------------------------------------------------------
    # حذف خبرهای تکراری بین منابع
    # --------------------------------------------------------

    items = remove_cross_source_duplicates(
        items
    )

    log.info(
        "After cross-source duplicate filter: %s",
        len(items)
    )

    # --------------------------------------------------------
    # مرتب‌سازی
    # --------------------------------------------------------

    items = sort_items(
        items
    )

    items = items[
        :MAX_POSTS_PER_RUN
    ]

    log.info(
        "Selected: %s",
        len(items)
    )

    sent_count = 0

    # --------------------------------------------------------
    # ارسال
    # --------------------------------------------------------

    for item in items:

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

            success = send_photo(
                image_path,
                caption,
                item["url"]
            )

            if success:

                save_sent_item(
                    item["url"],
                    item["title"]
                )

                sent_count += 1

                log.info(
                    "POSTED | %s | %s",
                    item["source"],
                    item["title"]
                )

                time.sleep(
                    POST_DELAY
                )

            else:

                log.error(
                    "Could not post | %s",
                    item["title"]
                )

        except Exception as e:

            log.exception(
                "Item processing failed | %s",
                e
            )

    log.info(
        "========================================"
    )

    log.info(
        "Finished | sent=%s",
        sent_count
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()