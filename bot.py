# -*- coding: utf-8 -*-

"""
JAHANTAB Telegram News Bot

ویژگی‌ها:
- منابع فارسی
- RSS + HTML fallback
- فیلتر سخت‌گیرانه اخبار جنگ ایران و منطقه
- حذف اخبار قدیمی
- حذف اخبار تحلیلی
- حذف خبرهای تکراری با لینک
- حذف خبرهای تکراری با عنوان
- حذف خبرهای مشابه بین منابع مختلف
- ذخیره دائمی خبرهای ارسال‌شده
- افزودن لوگو روی عکس
- ارسال عکس + کپشن به Telegram
"""

import os
import re
import time
import html
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

# فایل دوم برای جلوگیری از تکرار عنوان
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
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0 Safari/537.36 "
    "JAHANTAB-NewsBot/3.0"
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

        log.info(
            "SAVED SENT ITEM | %s",
            url
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
        now
        - dt.astimezone(
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

                if isinstance(
                    rel,
                    list
                ):
                    rel_text = " ".join(
                        rel
                    ).lower()
                else:
                    rel_text = str(
                        rel
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

        url = urljoin(
            feed_url,
            url
        )

        if not same_domain(
            url,
            source["domain"]
        ):
            continue

        summary = clean_html(
            entry.get(
                "summary",
                ""
            )
            or entry.get(
                "description",
                ""
            )
            or ""
        )

        published = None

        for key in [
            "published_parsed",
            "updated_parsed",
            "created_parsed",
        ]:
            published = parse_datetime(
                entry.get(key)
            )

            if published:
                break

        items.append(
            {
                "source": source["name"],
                "domain": source["domain"],
                "title": title,
                "summary": summary,
                "url": url,
                "image": extract_entry_image(
                    entry
                ),
                "published": published,
                "method": "rss",
            }
        )

    return items


# ============================================================
# HTML
# ============================================================

def is_probable_article_url(url):
    if not url:
        return False

    path = urlparse(
        url
    ).path.lower()

    bad_parts = [
        "/tag/",
        "/tags/",
        "/category/",
        "/categories/",
        "/author/",
        "/search",
        "/page/",
        "/login",
        "/register",
        "/contact",
        "/about",
        "/gallery",
    ]

    for bad in bad_parts:
        if bad in path:
            return False

    if len(
        path.strip("/")
    ) < 5:
        return False

    return True


def scrape_homepage(source):
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
    except Exception:
        return []

    items = []
    seen = set()

    anchors = []

    for article in soup.find_all(
        "article"
    ):
        anchors.extend(
            article.find_all(
                "a",
                href=True
            )
        )

    anchors.extend(
        soup.find_all(
            "a",
            href=True
        )
    )

    for a in anchors:
        href = a.get(
            "href"
        )

        title = clean_html(
            a.get_text(
                " ",
                strip=True
            )
        )

        if not href or not title:
            continue

        url = urljoin(
            response.url,
            href
        )

        if not same_domain(
            url,
            source["domain"]
        ):
            continue

        if not is_probable_article_url(
            url
        ):
            continue

        url = canonical_url(
            url
        )

        if url in seen:
            continue

        seen.add(url)

        if len(title) < 15:
            continue

        if len(title) > 300:
            continue

        items.append(
            {
                "source": source["name"],
                "domain": source["domain"],
                "title": title,
                "summary": "",
                "url": url,
                "image": "",
                "published": None,
                "method": "html",
            }
        )

        if len(items) >= MAX_ITEMS_PER_SOURCE:
            break

    return items


# ============================================================
# ARTICLE
# ============================================================

def extract_meta(
    soup,
    *names
):
    for name in names:
        tag = soup.find(
            "meta",
            attrs={
                "name": name
            }
        )

        if (
            tag
            and tag.get("content")
        ):
            return clean_html(
                tag.get("content")
            )

        tag = soup.find(
            "meta",
            attrs={
                "property": name
            }
        )

        if (
            tag
            and tag.get("content")
        ):
            return clean_html(
                tag.get("content")
            )

    return ""


def extract_article_page(item):
    response = safe_get(
        item["url"]
    )

    if not response or not response.ok:
        return item

    try:
        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )
    except Exception:
        return item

    title = extract_meta(
        soup,
        "og:title",
        "twitter:title",
    )

    if not title and soup.title:
        title = clean_html(
            soup.title.get_text()
        )

    if title:
        item["title"] = title

    description = extract_meta(
        soup,
        "description",
        "og:description",
        "twitter:description",
    )

    if description:
        item["summary"] = description

    image = extract_meta(
        soup,
        "og:image",
        "twitter:image",
    )

    if image:
        item["image"] = urljoin(
            response.url,
            image
        )

    if len(
        item.get(
            "summary",
            ""
        )
    ) < 80:

        paragraphs = []

        selectors = [
            "article p",
            ".article-body p",
            ".article-content p",
            ".news-body p",
            ".news-content p",
            ".body p",
            ".content p",
            "main p",
        ]

        for selector in selectors:
            found = soup.select(
                selector
            )

            if found:
                for p in found[:8]:
                    text = clean_html(
                        p.get_text(
                            " ",
                            strip=True
                        )
                    )

                    if len(text) >= 30:
                        paragraphs.append(
                            text
                        )

                if paragraphs:
                    break

        if paragraphs:
            item["summary"] = " ".join(
                paragraphs[:4]
            )

    if not item.get(
        "image"
    ):
        for img in soup.find_all(
            "img"
        ):
            src = (
                img.get(
                    "data-src"
                )
                or img.get(
                    "data-original"
                )
                or img.get(
                    "src"
                )
            )

            if not src:
                continue

            src = urljoin(
                response.url,
                src
            )

            if src.startswith(
                (
                    "http://",
                    "https://"
                )
            ):
                item["image"] = src
                break

    return item


# ============================================================
# SCORING
# ============================================================

def calculate_score(item):
    title = normalize_text(
        item.get(
            "title",
            ""
        )
    )

    summary = normalize_text(
        item.get(
            "summary",
            ""
        )
    )

    text = (
        title
        + " "
        + summary
    ).strip()

    score = 0

    matched_entities = []
    matched_actions = []
    matched_major = []
    matched_urgent = []

    for phrase, value in CORE_ENTITIES.items():
        if normalize_text(
            phrase
        ) in text:
            score += value
            matched_entities.append(
                phrase
            )

    if not matched_entities:
        return {
            "score": -999,
            "entities": [],
            "actions": [],
            "major": [],
            "urgent": [],
        }

    for phrase, value in MILITARY_ACTIONS.items():
        if normalize_text(
            phrase
        ) in text:
            score += value
            matched_actions.append(
                phrase
            )

    for phrase, value in MAJOR_EVENTS.items():
        if normalize_text(
            phrase
        ) in text:
            score += value
            matched_major.append(
                phrase
            )

    for phrase, value in URGENT_TERMS.items():
        if normalize_text(
            phrase
        ) in text:
            score += value
            matched_urgent.append(
                phrase
            )

    for phrase, value in CASUALTY_TERMS.items():
        if normalize_text(
            phrase
        ) in text:
            score += value

    for phrase, value in ANALYSIS_TERMS.items():
        if normalize_text(
            phrase
        ) in text:
            score += value

    for phrase, value in EXCLUDE_TERMS.items():
        if normalize_text(
            phrase
        ) in text:
            score += value

    if (
        not matched_actions
        and not matched_major
    ):
        score -= 25

    analysis_found = any(
        normalize_text(
            phrase
        ) in text
        for phrase in [
            "تحلیل",
            "یادداشت",
            "کارشناس",
            "چرا",
            "چگونه",
            "پیش بینی",
            "پیش‌بینی",
        ]
    )

    if (
        analysis_found
        and not matched_major
        and len(
            matched_actions
        ) < 2
    ):
        score -= 15

    hours = age_hours(
        item.get(
            "published"
        )
    )

    if hours <= URGENT_HOURS:
        score += 8
    elif hours <= 12:
        score += 4
    elif hours <= MAX_AGE_HOURS:
        score += 1

    return {
        "score": score,
        "entities": matched_entities,
        "actions": matched_actions,
        "major": matched_major,
        "urgent": matched_urgent,
    }


def is_relevant(item):
    info = calculate_score(
        item
    )

    item["score"] = info["score"]

    item["matched_entities"] = (
        info["entities"]
    )

    item["matched_actions"] = (
        info["actions"]
    )

    item["matched_major"] = (
        info["major"]
    )

    item["matched_urgent"] = (
        info["urgent"]
    )

    if info["score"] < MIN_SCORE:
        return False

    if (
        not info["actions"]
        and not info["major"]
    ):
        return False

    return True


# ============================================================
# TITLE FINGERPRINT
# ============================================================

def title_fingerprint(title):
    text = normalize_text(
        title
    )

    text = re.sub(
        r"[^\w\sآ-ی]",
        " ",
        text
    )

    stopwords = {
        "خبر",
        "جدید",
        "آخرین",
        "اعلام",
        "شد",
        "شدند",
        "کرد",
        "کردند",
        "کرده",
        "می",
        "شود",
        "شده",
        "در",
        "به",
        "از",
        "با",
        "برای",
        "و",
        "یک",
        "این",
        "آن",
        "را",
        "که",
        "بر",
        "تا",
        "اما",
        "نیز",
    }

    words = [
        word
        for word in text.split()
        if word not in stopwords
    ]

    # مرتب‌سازی باعث می‌شود
    # تفاوت جزئی ترتیب کلمات هم
    # باعث عبور خبر تکراری نشود.
    words = sorted(
        set(words)
    )

    return " ".join(
        words[:30]
    )


def title_tokens(title):
    fingerprint = title_fingerprint(
        title
    )

    return set(
        fingerprint.split()
    )


def titles_are_similar(
    title1,
    title2,
    threshold=0.72
):
    tokens1 = title_tokens(
        title1
    )

    tokens2 = title_tokens(
        title2
    )

    if not tokens1 or not tokens2:
        return False

    intersection = len(
        tokens1 & tokens2
    )

    union = len(
        tokens1 | tokens2
    )

    if union == 0:
        return False

    similarity = (
        intersection
        / union
    )

    return similarity >= threshold


# ============================================================
# DEDUPLICATION
# ============================================================

def dedupe_items(
    items,
    sent_links,
    sent_titles
):
    result = []

    seen_urls = set()
    seen_titles = set()

    # خبرهای با امتیاز بالاتر
    # زودتر بررسی می‌شوند.
    items = sorted(
        items,
        key=lambda x: (
            x.get(
                "score",
                0
            ),
            -age_hours(
                x.get(
                    "published"
                )
            ),
        ),
        reverse=True,
    )

    for item in items:

        url = canonical_url(
            item.get(
                "url",
                ""
            )
        )

        title = clean_html(
            item.get(
                "title",
                ""
            )
        )

        if not url or not title:
            continue

        # ----------------------------------------------------
        # لینک قبلاً ارسال شده
        # ----------------------------------------------------

        if url in sent_links:
            log.info(
                "DUPLICATE LINK | %s",
                title
            )
            continue

        # ----------------------------------------------------
        # عنوان قبلاً ارسال شده
        # ----------------------------------------------------

        fingerprint = title_fingerprint(
            title
        )

        if (
            fingerprint
            and fingerprint in sent_titles
        ):
            log.info(
                "DUPLICATE TITLE HISTORY | %s",
                title
            )
            continue

        # ----------------------------------------------------
        # تکراری داخل همین اجرای Bot
        # ----------------------------------------------------

        if url in seen_urls:
            continue

        if (
            fingerprint
            and fingerprint in seen_titles
        ):
            log.info(
                "DUPLICATE CURRENT RUN | %s",
                title
            )
            continue

        # ----------------------------------------------------
        # شباهت عنوان با خبرهای همین اجرا
        # ----------------------------------------------------

        similar = False

        for old_item in result:
            old_title = old_item.get(
                "title",
                ""
            )

            if titles_are_similar(
                title,
                old_title,
                threshold=0.72
            ):
                log.info(
                    "SIMILAR NEWS | %s | %s",
                    title,
                    old_title
                )

                similar = True
                break

        if similar:
            continue

        seen_urls.add(
            url
        )

        if fingerprint:
            seen_titles.add(
                fingerprint
            )

        result.append(
            item
        )

    return result


# ============================================================
# COLLECT
# ============================================================

def collect_from_source(
    source,
    sent_links,
    sent_titles
):
    items = []

    feeds = discover_feeds(
        source
    )

    for feed_url in feeds:
        try:
            rss_items = parse_feed(
                source,
                feed_url
            )

            if rss_items:
                items.extend(
                    rss_items
                )
                break

        except Exception as e:
            log.debug(
                "RSS error | %s | %s",
                source["name"],
                e
            )

    if not items:
        items = scrape_homepage(
            source
        )

    fresh = []

    for item in items:
        url = canonical_url(
            item.get(
                "url",
                ""
            )
        )

        title = item.get(
            "title",
            ""
        )

        if not url:
            continue

        if url in sent_links:
            continue

        fingerprint = title_fingerprint(
            title
        )

        if (
            fingerprint
            and fingerprint in sent_titles
        ):
            continue

        fresh.append(
            item
        )

    return fresh


def collect_all_news(
    sent_links,
    sent_titles
):
    all_items = []

    for source in SOURCES:
        try:
            log.info(
                "SOURCE | %s",
                source["name"]
            )

            items = collect_from_source(
                source,
                sent_links,
                sent_titles
            )

            log.info(
                "FOUND | %s | %d",
                source["name"],
                len(items)
            )

            all_items.extend(
                items
            )

        except Exception as e:
            log.exception(
                "SOURCE ERROR | %s | %s",
                source["name"],
                e
            )

    return all_items


# ============================================================
# ENRICH
# ============================================================

def enrich_candidates(items):
    candidates = []

    for item in items:
        quick = calculate_score(
            item
        )

        if quick["score"] < 5:
            continue

        candidates.append(
            item
        )

    candidates.sort(
        key=lambda x: (
            calculate_score(
                x
            )["score"],
            -age_hours(
                x.get(
                    "published"
                )
            ),
        ),
        reverse=True,
    )

    candidates = candidates[:80]

    result = []

    for item in candidates:
        try:
            item = extract_article_page(
                item
            )

            if is_relevant(
                item
            ):
                result.append(
                    item
                )

        except Exception as e:
            log.debug(
                "ARTICLE ERROR | %s | %s",
                item.get("url"),
                e
            )

    return result


# ============================================================
# IMAGE
# ============================================================

def find_logo_file():
    candidates = [
        LOGO_FILE,
        os.path.join(
            BASE_DIR,
            "logo.png"
        ),
        os.path.join(
            BASE_DIR,
            "logo.jpg"
        ),
        os.path.join(
            BASE_DIR,
            "logo.jpeg"
        ),
    ]

    for path in candidates:
        if os.path.isfile(
            path
        ):
            return path

    return None


def download_image(url):
    if not url:
        return None

    response = safe_get(
        url,
        timeout=15,
        headers={
            **HEADERS,
            "Accept": (
                "image/avif,"
                "image/webp,"
                "image/apng,"
                "image/svg+xml,"
                "image/*,"
                "*/*;q=0.8"
            ),
        },
    )

    if not response or not response.ok:
        log.warning(
            "IMAGE DOWNLOAD FAILED | %s",
            url
        )
        return None

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
        and not response.content.startswith(
            (
                b"\xff\xd8",
                b"\x89PNG",
                b"RIFF"
            )
        )
    ):
        return None

    if len(
        response.content
    ) > 15 * 1024 * 1024:
        log.warning(
            "IMAGE TOO LARGE | %s",
            url
        )
        return None

    return response.content


def watermark_image(
    image_bytes
):
    if not image_bytes:
        return image_bytes

    if Image is None:
        log.error(
            "Pillow is not installed."
        )
        return image_bytes

    logo_path = find_logo_file()

    if not logo_path:
        log.error(
            "LOGO NOT FOUND | searched in %s",
            BASE_DIR
        )
        return image_bytes

    try:
        from io import BytesIO

        base = Image.open(
            BytesIO(image_bytes)
        ).convert(
            "RGBA"
        )

        logo = Image.open(
            logo_path
        ).convert(
            "RGBA"
        )

        if (
            logo.width <= 0
            or logo.height <= 0
        ):
            return image_bytes

        target_width = max(
            140,
            int(
                base.width * 0.22
            )
        )

        target_width = min(
            target_width,
            int(
                base.width * 0.35
            )
        )

        ratio = (
            target_width
            / logo.width
        )

        target_height = max(
            1,
            int(
                logo.height * ratio
            )
        )

        logo = logo.resize(
            (
                target_width,
                target_height
            ),
            Image.LANCZOS
        )

        # کمی شفاف‌تر تا عکس اصلی دیده شود.
        alpha = logo.getchannel(
            "A"
        )

        alpha = alpha.point(
            lambda p: int(
                p * 0.90
            )
        )

        logo.putalpha(
            alpha
        )

        margin = max(
            15,
            int(
                base.width * 0.025
            )
        )

        x = (
            base.width
            - logo.width
            - margin
        )

        y = (
            base.height
            - logo.height
            - margin
        )

        base.alpha_composite(
            logo,
            (
                x,
                y
            )
        )

        output = BytesIO()

        base.convert(
            "RGB"
        ).save(
            output,
            format="JPEG",
            quality=95,
            optimize=True
        )

        result = output.getvalue()

        log.info(
            "LOGO ADDED | %s",
            logo_path
        )

        return result

    except Exception as e:
        log.exception(
            "WATERMARK ERROR | %s",
            e
        )

        return image_bytes


# ============================================================
# TELEGRAM
# ============================================================

def telegram_api(
    method,
    data=None,
    files=None
):
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is not set."
        )

    url = (
        "https://api.telegram.org/bot"
        + BOT_TOKEN
        + "/"
        + method
    )

    try:
        return requests.post(
            url,
            data=data,
            files=files,
            timeout=30
        )

    except requests.RequestException as e:
        log.error(
            "Telegram request failed | %s",
            e
        )
        return None


def send_message(text):
    response = telegram_api(
        "sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "false",
        }
    )

    if not response:
        return False

    if not response.ok:
        log.error(
            "sendMessage failed | %s",
            response.text[:500]
        )
        return False

    return True


def send_photo(
    image_bytes,
    caption
):
    if not image_bytes:
        return send_message(
            caption
        )

    files = {
        "photo": (
            "jahantab.jpg",
            image_bytes,
            "image/jpeg"
        )
    }

    data = {
        "chat_id": CHAT_ID,
        "caption": caption,
        "parse_mode": "HTML",
    }

    response = telegram_api(
        "sendPhoto",
        data=data,
        files=files
    )

    if not response:
        return False

    if not response.ok:
        log.error(
            "sendPhoto failed | %s",
            response.text[:500]
        )
        return False

    return True


# ============================================================
# CAPTION
# ============================================================

def build_caption(item):
    title = clean_html(
        item.get(
            "title",
            ""
        )
    )

    summary = clean_html(
        item.get(
            "summary",
            ""
        )
    )

    source = clean_html(
        item.get(
            "source",
            ""
        )
    )

    url = item.get(
        "url",
        ""
    )

    if summary:
        summary = shorten(
            summary,
            500
        )
    else:
        summary = (
            "جزئیات بیشتر "
            "در لینک خبر."
        )

    caption = (
        "🟥 <b>خبر فوری</b>\n\n"
        f"<b>{html.escape(title)}</b>\n\n"
        f"{html.escape(summary)}\n\n"
        f"📰 منبع: "
        f"<b>{html.escape(source)}</b>\n"
        f"🔗 <a href=\""
        f"{html.escape(url, quote=True)}"
        f"\">مشاهده خبر اصلی</a>\n\n"
        "— @jahantab_news"
    )

    if len(caption) > 1024:
        summary = shorten(
            summary,
            300
        )

        caption = (
            "🟥 <b>خبر فوری</b>\n\n"
            f"<b>{html.escape(title)}</b>\n\n"
            f"{html.escape(summary)}\n\n"
            f"📰 منبع: "
            f"<b>{html.escape(source)}</b>\n"
            f"🔗 <a href=\""
            f"{html.escape(url, quote=True)}"
            f"\">خبر اصلی</a>\n\n"
            "— @jahantab_news"
        )

    return caption[:1024]


# ============================================================
# FINAL SELECTION
# ============================================================

def final_sort_key(item):
    score = item.get(
        "score",
        0
    )

    hours = age_hours(
        item.get(
            "published"
        )
    )

    freshness_bonus = max(
        0,
        24 - hours
    )

    return (
        score * 10
        + freshness_bonus,
        -hours
    )


def select_best(
    items,
    sent_links,
    sent_titles
):
    items = dedupe_items(
        items,
        sent_links,
        sent_titles
    )

    items.sort(
        key=final_sort_key,
        reverse=True
    )

    return items[
        :MAX_POSTS_PER_RUN
    ]


# ============================================================
# MAIN
# ============================================================

def main():
    log.info(
        "=" * 70
    )

    log.info(
        "JAHANTAB NEWS BOT START"
    )

    log.info(
        "BASE DIR | %s",
        BASE_DIR
    )

    log.info(
        "CHAT ID | %s",
        CHAT_ID
    )

    logo = find_logo_file()

    log.info(
        "LOGO | %s",
        logo or "NOT FOUND"
    )

    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN environment variable is missing."
        )

    sent_links = load_sent_links()
    sent_titles = load_sent_titles()

    log.info(
        "SENT LINKS | %d",
        len(sent_links)
    )

    log.info(
        "SENT TITLES | %d",
        len(sent_titles)
    )

    # --------------------------------------------------------
    # جمع‌آوری
    # --------------------------------------------------------

    candidates = collect_all_news(
        sent_links,
        sent_titles
    )

    log.info(
        "RAW CANDIDATES | %d",
        len(candidates)
    )

    if not candidates:
        log.info(
            "NO NEW CANDIDATES"
        )
        return

    # --------------------------------------------------------
    # استخراج اطلاعات کامل خبر
    # --------------------------------------------------------

    relevant = enrich_candidates(
        candidates
    )

    log.info(
        "RELEVANT | %d",
        len(relevant)
    )

    if not relevant:
        log.info(
            "NO IMPORTANT WAR NEWS"
        )
        return

    # --------------------------------------------------------
    # حذف تکراری
    # --------------------------------------------------------

    selected = select_best(
        relevant,
        sent_links,
        sent_titles
    )

    log.info(
        "SELECTED | %d",
        len(selected)
    )

    if not selected:
        log.info(
            "NOTHING NEW TO PUBLISH"
        )
        return

    # --------------------------------------------------------
    # ارسال
    # --------------------------------------------------------

    sent_count = 0

    for item in selected:

        try:
            title = item.get(
                "title",
                ""
            )

            url = item.get(
                "url",
                ""
            )

            log.info(
                "PUBLISH | score=%s | source=%s | title=%s",
                item.get("score"),
                item.get("source"),
                title
            )

            # یک بررسی نهایی درست قبل از ارسال
            current_sent_links = (
                load_sent_links()
            )

            current_sent_titles = (
                load_sent_titles()
            )

            if (
                canonical_url(url)
                in current_sent_links
            ):
                log.info(
                    "SKIP - ALREADY SENT | %s",
                    title
                )
                continue

            fingerprint = title_fingerprint(
                title
            )

            if (
                fingerprint
                and fingerprint
                in current_sent_titles
            ):
                log.info(
                    "SKIP - TITLE ALREADY SENT | %s",
                    title
                )
                continue

            caption = build_caption(
                item
            )

            image_bytes = None

            if item.get(
                "image"
            ):
                image_bytes = download_image(
                    item["image"]
                )

            if image_bytes:
                image_bytes = watermark_image(
                    image_bytes
                )

                success = send_photo(
                    image_bytes,
                    caption
                )

            else:
                success = send_message(
                    caption
                )

            # فقط اگر Telegram موفق بود
            # خبر به عنوان ارسال‌شده ثبت می‌شود.
            if success:

                if save_sent_item(
                    url,
                    title
                ):
                    sent_count += 1

                log.info(
                    "PUBLISHED SUCCESSFULLY | %s",
                    url
                )

                time.sleep(2)

            else:
                log.error(
                    "PUBLISH FAILED | %s",
                    url
                )

        except Exception as e:
            log.exception(
                "PUBLISH ERROR | %s | %s",
                item.get("url"),
                e
            )

    log.info(
        "=" * 70
    )

    log.info(
        "PUBLISHED TOTAL | %d",
        sent_count
    )

    log.info(
        "JAHANTAB NEWS BOT END"
    )

    log.info(
        "=" * 70
    )


if __name__ == "__main__":
    main()