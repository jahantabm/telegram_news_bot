# -*- coding: utf-8 -*-

import os
import re
import json
import time
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from html import unescape
from urllib.parse import urljoin, urlparse, urlunparse

import requests
import feedparser
from bs4 import BeautifulSoup
from PIL import Image


# =========================================================
# JAHANTAB TELEGRAM NEWS BOT
# STRICT FILTER VERSION 2.0
# =========================================================

VERSION = "JAHANTAB TELEGRAM NEWS BOT - STRICT FILTER V2.0"

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()

# فقط یک خبر در هر اجرای GitHub
MAX_POSTS_PER_RUN = 1

MAX_ITEMS_PER_SOURCE = 15
MAX_AGE_HOURS = 12

# حداقل امتیاز
MIN_SCORE = 16

# فاصله بین ارسال‌های داخل یک اجرا
POST_DELAY = 2

# فایل‌های ضدتکرار
SENT_LINKS_FILE = "sent_links.txt"
SENT_TITLES_FILE = "sent_titles.txt"

# ثبت آخرین ارسال
LAST_PUBLISH_FILE = "last_publish.txt"

REQUEST_TIMEOUT = 20

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/131.0 Safari/537.36 "
    "JAHANTAB-News-Bot/2.0"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.5",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# =========================================================
# DATA STRUCTURES
# =========================================================

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
    published: datetime | None = None

    score: int = 0
    event_score: int = 0
    urgency_score: int = 0

    is_major: bool = False
    is_very_major: bool = False


# =========================================================
# SOURCES
# =========================================================

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

    Source(
        "روز پلاس",
        "roozplus.com",
        "https://www.roozplus.com/"
    ),
]


TRUSTED_SOURCES = {
    "ایرنا",
    "ایسنا",
    "فارس",
    "تسنیم",
    "مهر",
    "صدا و سیما",
    "ایلنا",
}


# =========================================================
# DIRECT IMPORTANT TOPICS
# =========================================================

# نکته:
# فقط وجود کلمه «ایران»، «آمریکا»، «اسرائیل»،
# «خلیج فارس» و... به تنهایی کافی نیست.


IRAN_DIRECT = {
    "حمله به ایران",
    "حمله آمریکا به ایران",
    "حمله اسرائیل به ایران",
    "حمله ایران به آمریکا",
    "حمله ایران به اسرائیل",
    "حمله موشکی به ایران",
    "حمله هوایی به ایران",
    "پاسخ ایران",
    "پاسخ موشکی ایران",
    "عملیات ایران",
    "عملیات علیه ایران",
    "درگیری ایران و آمریکا",
    "درگیری ایران و اسرائیل",
    "جنگ ایران و آمریکا",
    "جنگ ایران و اسرائیل",
    "نیروهای آمریکایی در ایران",
    "پایگاه آمریکایی",
    "پایگاه آمریکا",
    "سنتکام",
    "پنتاگون",
    "نیروهای آمریکایی",
    "تأسیسات هسته‌ای ایران",
    "تاسیسات هسته‌ای ایران",
    "برنامه هسته‌ای ایران",
    "حمله به تأسیسات هسته‌ای",
    "حمله به تاسیسات هسته‌ای",
    "تحریم آمریکا علیه ایران",
}


ISRAEL_REGION_DIRECT = {
    "حمله اسرائیل",
    "حمله به اسرائیل",
    "حمله ایران به اسرائیل",
    "حمله اسرائیل به ایران",
    "درگیری اسرائیل",
    "جنگ اسرائیل",
    "عملیات اسرائیل",
    "ارتش اسرائیل",
    "حمله اسرائیل به غزه",
    "حمله اسرائیل به لبنان",
}


RESISTANCE_DIRECT = {
    "حزب‌الله",
    "حزب الله",
    "حمله حزب‌الله",
    "حمله حزب الله",
    "عملیات حزب‌الله",
    "عملیات حزب الله",

    "حماس",
    "حمله حماس",
    "عملیات حماس",

    "جنگ غزه",
    "حمله به غزه",

    "حمله به لبنان",

    "انصارالله",
    "انصار الله",
    "حوثی‌ها",
    "حوثی ها",
    "حمله حوثی‌ها",
    "حمله حوثی ها",
    "عملیات انصارالله",
    "عملیات انصار الله",

    "حشدالشعبی",
    "حشد الشعبی",
    "عملیات حشدالشعبی",
}


MARITIME_DIRECT = {
    "تنگه هرمز",
    "بستن تنگه هرمز",
    "انسداد تنگه هرمز",
    "بازگشایی تنگه هرمز",

    "خلیج فارس",
    "حمله در خلیج فارس",
    "درگیری در خلیج فارس",

    "نفتکش",
    "نفت‌کش",
    "توقیف نفتکش",
    "توقیف نفت‌کش",
    "حمله به نفتکش",
    "حمله به نفت‌کش",

    "کشتیرانی در خلیج فارس",

    "باب‌المندب",
    "باب المندب",

    "حمله در دریای سرخ",
    "کشتیرانی دریای سرخ",
}


# =========================================================
# MAJOR EVENT TERMS
# =========================================================

MAJOR_EVENT_TERMS = {
    "حمله": 5,
    "حمله موشکی": 8,
    "حمله هوایی": 7,
    "انفجار": 7,
    "انفجار بزرگ": 10,

    "عملیات نظامی": 8,
    "عملیات": 4,

    "شلیک موشک": 8,
    "پاسخ نظامی": 8,

    "آتش‌بس": 7,
    "آتش بس": 7,

    "اعلام جنگ": 12,
    "آغاز جنگ": 12,
    "پایان جنگ": 10,

    "ترور": 8,

    "کشته": 4,
    "کشته شدند": 6,
    "تلفات": 5,

    "مجروح": 4,
    "مجروح شدند": 5,

    "رهگیری": 6,
    "انهدام": 6,
    "سقوط": 4,
    "توقیف": 6,
    "اسارت": 6,

    "اولتیماتوم": 6,
}


# =========================================================
# LOCAL INCIDENTS
# =========================================================

ACCIDENT_TERMS = {
    "تصادف",
    "سانحه رانندگی",
    "حادثه رانندگی",
    "واژگونی",

    "غرق شد",
    "غرق شدند",
    "غرق شدن",

    "آتش‌سوزی",
    "آتش سوزی",

    "انفجار",

    "ریزش ساختمان",
    "ریزش آوار",
    "فروریختن ساختمان",

    "سیل",

    "زلزله",

    "رانش زمین",

    "معدن",
    "حادثه معدن",
}


SEVERE_ACCIDENT_TERMS = {
    "کشته",
    "کشته شدند",
    "جان باخت",
    "جان باختند",
    "فوت",
    "تلفات",

    "مصدوم",
    "مصدومان",

    "مجروح",
    "مجروحان",

    "نجات",
    "عملیات امداد",

    "مفقود",
    "مفقودان",

    "خسارت سنگین",
    "خسارت گسترده",
    "خسارات سنگین",
}


# =========================================================
# GENERAL EXCLUSIONS
# =========================================================

EXCLUDE_TERMS = {
    "فوتبال",
    "لیگ برتر",
    "استقلال",
    "پرسپولیس",
    "ورزشی",

    "سینما",
    "بازیگر",
    "فیلم",
    "موسیقی",
    "کنسرت",

    "پزشکی",
    "سلامت",
    "بیمارستان",

    "دانشگاه",
    "دانشجو",

    "مدرسه",
    "مدارس",
    "آموزش",
    "تعطیلی مدارس",
    "مجازی شد",
    "غیرحضوری",

    "هواشناسی",
    "آب و هوا",

    "بورس",
    "قیمت دلار",
    "قیمت طلا",

    "خودرو",
    "مسکن",

    "گردشگری",

    "تکنولوژی",
    "اینترنت",

    "فال",
    "آشپزی",
    "سبک زندگی",

    "چهره",
    "سلبریتی",
}


ANALYSIS_TERMS = {
    "تحلیل",
    "یادداشت",
    "گفتگو",
    "گفت‌وگو",
    "بررسی",
    "سناریو",
    "پیش‌بینی",
    "آینده جنگ",
    "پرونده",
}


# =========================================================
# TEXT FUNCTIONS
# =========================================================

def normalize_text(text: str) -> str:

    if not text:
        return ""

    text = unescape(str(text))

    replacements = {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ۀ": "ه",
        "ة": "ه",
        "ؤ": "و",
        "إ": "ا",
        "أ": "ا",
        "\u200c": " ",
        "\u200f": " ",
        "\u200e": " ",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    text = re.sub(
        r"https?://\S+",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def clean_title(title: str) -> str:

    title = normalize_text(title)

    title = re.sub(
        r"^(خبر فوری|فوری|اختصاصی|لحظه به لحظه)"
        r"\s*[:：\-–—]*\s*",
        "",
        title,
        flags=re.IGNORECASE,
    )

    return title.strip()


def words(text: str):

    return {
        word
        for word in re.findall(
            r"[\w\u0600-\u06FF]+",
            normalize_text(text).lower()
        )
        if len(word) >= 2
    }


def similarity(a: str, b: str):

    return SequenceMatcher(
        None,
        normalize_text(a),
        normalize_text(b)
    ).ratio()


def jaccard(a: str, b: str):

    a_words = words(a)
    b_words = words(b)

    if not a_words or not b_words:
        return 0.0

    return len(
        a_words & b_words
    ) / len(
        a_words | b_words
    )


def shorten(text: str, limit: int):

    text = normalize_text(text)

    if len(text) <= limit:
        return text

    text = text[:limit]

    if " " in text:
        text = text.rsplit(
            " ",
            1
        )[0]

    return text.rstrip(
        "،؛,:- "
    ) + "..."


def escape_html(text: str):

    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def contains_any(text, terms):

    return any(
        term in text
        for term in terms
    )


# =========================================================
# URL
# =========================================================

def canonical_url(url: str):

    if not url:
        return ""

    try:

        parsed = urlparse(url)

        scheme = parsed.scheme.lower()

        netloc = parsed.netloc.lower()

        if netloc.startswith("www."):
            netloc = netloc[4:]

        path = re.sub(
            r"/+",
            "/",
            parsed.path
        )

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


def same_domain(
    url: str,
    domain: str
):

    try:

        host = urlparse(
            url
        ).netloc.lower()

        if host.startswith("www."):
            host = host[4:]

        return (
            host == domain
            or host.endswith(
                "." + domain
            )
        )

    except Exception:

        return False


# =========================================================
# DATE
# =========================================================

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

    return None


def age_hours(dt):

    if not dt:
        return 999999

    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=timezone.utc
        )

    return max(
        0,
        (
            datetime.now(timezone.utc)
            - dt
        ).total_seconds() / 3600
    )


# =========================================================
# HTTP
# =========================================================

def get_url(url: str):

    try:

        response = SESSION.get(
            url,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        if response.status_code >= 400:
            return None

        return response

    except Exception as exc:

        print(
            f"REQUEST ERROR: {url} -> {exc}"
        )

        return None


# =========================================================
# RSS DISCOVERY
# =========================================================

FEED_PATHS = [
    "/rss",
    "/rss.xml",
    "/feed",
    "/feed.xml",
    "/fa/rss",
]


def discover_feeds(
    source: Source
):

    found = []

    for path in FEED_PATHS:

        found.append(
            urljoin(
                source.url,
                path
            )
        )

    response = get_url(
        source.url
    )

    if response:

        try:

            soup = BeautifulSoup(
                response.text,
                "html.parser"
            )

            for link in soup.find_all(
                "link",
                href=True
            ):

                rel = " ".join(
                    link.get(
                        "rel",
                        []
                    )
                ).lower()

                typ = (
                    link.get(
                        "type",
                        ""
                    )
                    .lower()
                )

                if (
                    "alternate" in rel
                    and (
                        "rss" in typ
                        or "atom" in typ
                        or "xml" in typ
                    )
                ):

                    found.insert(
                        0,
                        urljoin(
                            source.url,
                            link["href"]
                        )
                    )

        except Exception:
            pass

    result = []

    for url in found:

        url = canonical_url(
            url
        )

        if (
            url
            and url not in result
        ):
            result.append(url)

    return result[:8]


# =========================================================
# RSS PARSER
# =========================================================

def parse_feed(
    feed_url: str,
    source: Source
):

    response = get_url(
        feed_url
    )

    if not response:
        return []

    try:

        parsed = feedparser.parse(
            response.content
        )

    except Exception:

        return []

    result = []

    for entry in parsed.entries[
        :MAX_ITEMS_PER_SOURCE
    ]:

        title = clean_title(
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

        description = normalize_text(
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

        published = (
            parse_datetime(
                entry.get(
                    "published_parsed"
                )
            )
            or parse_datetime(
                entry.get(
                    "updated_parsed"
                )
            )
        )

        image = ""

        for media in entry.get(
            "media_content",
            []
        ):

            candidate = (
                media.get("url")
                or media.get("href")
            )

            if candidate:

                image = urljoin(
                    url,
                    candidate
                )

                break

        if not image:

            thumbnails = entry.get(
                "media_thumbnail",
                []
            )

            if thumbnails:

                image = thumbnails[
                    0
                ].get(
                    "url",
                    ""
                )

        result.append(
            NewsItem(
                title=title,
                url=url,
                source=source.name,
                domain=source.domain,
                description=description,
                image=image,
                published=published,
            )
        )

    return result


# =========================================================
# ARTICLE DATA
# =========================================================

def extract_article_data(
    item: NewsItem
):

    response = get_url(
        item.url
    )

    if not response:
        return item

    try:

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        # تصویر OpenGraph
        if not item.image:

            meta = soup.find(
                "meta",
                property="og:image"
            )

            if (
                meta
                and meta.get("content")
            ):

                item.image = urljoin(
                    item.url,
                    meta["content"]
                )

        # تصویر Twitter
        if not item.image:

            meta = soup.find(
                "meta",
                attrs={
                    "name": "twitter:image"
                }
            )

            if (
                meta
                and meta.get("content")
            ):

                item.image = urljoin(
                    item.url,
                    meta["content"]
                )

        # خلاصه
        if not item.description:

            meta = soup.find(
                "meta",
                attrs={
                    "name": "description"
                }
            )

            if (
                meta
                and meta.get("content")
            ):

                item.description = normalize_text(
                    meta["content"]
                )

        # تاریخ
        if not item.published:

            meta = soup.find(
                "meta",
                property="article:published_time"
            )

            if (
                meta
                and meta.get("content")
            ):

                try:

                    value = (
                        meta["content"]
                        .replace(
                            "Z",
                            "+00:00"
                        )
                    )

                    dt = datetime.fromisoformat(
                        value
                    )

                    if dt.tzinfo is None:

                        dt = dt.replace(
                            tzinfo=timezone.utc
                        )

                    item.published = dt

                except Exception:
                    pass

    except Exception as exc:

        print(
            f"ARTICLE ERROR: "
            f"{item.url} -> {exc}"
        )

    return item


# =========================================================
# EARTHQUAKE
# =========================================================

EARTHQUAKE_PATTERNS = [
    r"زلزله[^.]{0,100}"
    r"([6-9](?:\.\d+)?)\s*"
    r"(?:ریشتر|درجه)",

    r"([6-9](?:\.\d+)?)\s*"
    r"(?:ریشتر|درجه)"
    r"[^.\n]{0,40}"
    r"زلزله",

    r"زلزله[^.]{0,100}"
    r"مقیاس\s*"
    r"([6-9](?:\.\d+)?)",
]


def earthquake_magnitude(
    text
):

    text = normalize_text(
        text
    )

    for pattern in EARTHQUAKE_PATTERNS:

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE
        )

        if match:

            try:

                return float(
                    match.group(1)
                )

            except Exception:
                pass

    return None


# =========================================================
# DIRECT TOPIC SCORE
# =========================================================

def direct_topic_score(
    title: str,
    description: str
):

    title = normalize_text(
        title
    )

    body = normalize_text(
        description
    )

    score = 0
    matched = []

    groups = [
        IRAN_DIRECT,
        ISRAEL_REGION_DIRECT,
        RESISTANCE_DIRECT,
        MARITIME_DIRECT,
    ]

    for group in groups:

        for term in group:

            if term in title:

                score += 12

                matched.append(
                    term
                )

            elif term in body:

                score += 5

                matched.append(
                    term
                )

    return score, matched


# =========================================================
# LOCAL INCIDENT SCORE
# =========================================================

def local_accident_score(
    title: str,
    description: str
):

    title = normalize_text(
        title
    )

    body = normalize_text(
        description
    )

    full = (
        title
        + " "
        + body
    )

    if not contains_any(
        full,
        ACCIDENT_TERMS
    ):
        return 0

    severity = 0

    for term in SEVERE_ACCIDENT_TERMS:

        if term in title:

            severity += 8

        elif term in body:

            severity += 3

    # زلزله
    magnitude = earthquake_magnitude(
        full
    )

    if magnitude is not None:

        if magnitude >= 6:

            return 40

        if magnitude >= 5.5:

            return 15

    return severity


# =========================================================
# SCORING
# =========================================================

def calculate_score(
    item: NewsItem
):

    title = normalize_text(
        item.title
    )

    body = normalize_text(
        item.description
    )

    full = (
        title
        + " "
        + body
    )

    direct_score, matched = (
        direct_topic_score(
            title,
            body
        )
    )

    event_score = 0

    for term, weight in (
        MAJOR_EVENT_TERMS.items()
    ):

        if term in title:

            event_score += (
                weight * 2
            )

        elif term in body:

            event_score += weight

    accident_score = local_accident_score(
        title,
        body
    )

    # موضوع مستقیم + رویداد
    major = (
        direct_score >= 12
        and event_score >= 5
    )

    # حادثه مهم
    local_major = (
        accident_score >= 12
    )

    item.is_major = (
        major
        or local_major
    )

    score = (
        direct_score
        + event_score
        + accident_score
    )

    # اعتبار منبع
    if item.source in TRUSTED_SOURCES:

        score += 2

    # تازگی
    age = age_hours(
        item.published
    )

    if age <= 1:

        score += 6

    elif age <= 3:

        score += 4

    elif age <= 6:

        score += 2

    item.score = score

    item.event_score = (
        event_score
    )

    # -----------------------------------------
    # VERY MAJOR
    # -----------------------------------------

    very_major = False

    magnitude = earthquake_magnitude(
        full
    )

    if (
        magnitude is not None
        and magnitude >= 6
    ):

        very_major = True

    if accident_score >= 30:

        very_major = True

    if (
        direct_score >= 20
        and event_score >= 12
        and age <= 3
    ):

        very_major = True

    item.is_very_major = (
        very_major
    )

    item.urgency_score = (
        event_score
        + direct_score
        + accident_score
    )

    return item


# =========================================================
# FILTER
# =========================================================

def is_analysis(
    item: NewsItem
):

    title = normalize_text(
        item.title
    )

    return any(
        term in title
        for term in ANALYSIS_TERMS
    )


def is_excluded(
    item: NewsItem
):

    title = normalize_text(
        item.title
    )

    body = normalize_text(
        item.description
    )

    full = (
        title
        + " "
        + body
    )

    # خبر مهم واقعی نباید صرفاً
    # به خاطر یک کلمه عمومی حذف شود.
    if item.is_major:

        return False

    return any(
        term in full
        for term in EXCLUDE_TERMS
    )


def evaluate(
    item: NewsItem
):

    if not item.title:

        return False

    if is_analysis(item):

        return False

    if is_excluded(item):

        return False

    # خبر قدیمی
    if (
        item.published
        and age_hours(
            item.published
        ) > MAX_AGE_HOURS
    ):

        return False

    title = normalize_text(
        item.title
    )

    body = normalize_text(
        item.description
    )

    direct_score, _ = (
        direct_topic_score(
            title,
            body
        )
    )

    accident_score = (
        local_accident_score(
            title,
            body
        )
    )

    # خبر مستقیم منطقه‌ای /
    # بین‌المللی مرتبط با ایران
    if direct_score >= 12:

        return (
            item.score >= MIN_SCORE
        )

    # حادثه مهم محلی
    if accident_score >= 12:

        return (
            item.score >= MIN_SCORE
        )

    # زلزله 6 ریشتر و بالاتر
    magnitude = earthquake_magnitude(
        title + " " + body
    )

    if (
        magnitude is not None
        and magnitude >= 6
    ):

        return True

    return False


# =========================================================
# DEDUPLICATION
# =========================================================

def load_lines(
    filename
):

    if not os.path.exists(
        filename
    ):

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

    except Exception:

        return set()


def append_line(
    filename,
    value
):

    try:

        with open(
            filename,
            "a",
            encoding="utf-8"
        ) as f:

            f.write(
                value.strip()
                + "\n"
            )

    except Exception as exc:

        print(
            f"FILE WRITE ERROR: {exc}"
        )


def title_fingerprint(
    title
):

    normalized = normalize_text(
        title
    ).lower()

    normalized = re.sub(
        r"[^\w\u0600-\u06FF ]+",
        " ",
        normalized
    )

    normalized = re.sub(
        r"\s+",
        " ",
        normalized
    ).strip()

    return hashlib.sha1(
        normalized.encode(
            "utf-8"
        )
    ).hexdigest()


def same_event(
    a: NewsItem,
    b: NewsItem
):

    if similarity(
        a.title,
        b.title
    ) >= 0.76:

        return True

    if jaccard(
        a.title,
        b.title
    ) >= 0.60:

        return True

    a_text = (
        a.title
        + " "
        + a.description
    )

    b_text = (
        b.title
        + " "
        + b.description
    )

    if similarity(
        a_text,
        b_text
    ) >= 0.73:

        return True

    return False


def dedupe_cross_source(
    items
):

    items = sorted(
        items,
        key=lambda x: (
            x.is_very_major,
            x.score,
            x.source in TRUSTED_SOURCES,
        ),
        reverse=True,
    )

    result = []

    for item in items:

        duplicate = False

        for old in result:

            if (
                canonical_url(
                    item.url
                )
                ==
                canonical_url(
                    old.url
                )
            ):

                duplicate = True
                break

            if (
                title_fingerprint(
                    item.title
                )
                ==
                title_fingerprint(
                    old.title
                )
            ):

                duplicate = True
                break

            if same_event(
                item,
                old
            ):

                duplicate = True
                break

        if not duplicate:

            result.append(item)

    return result


# =========================================================
# IMAGE
# =========================================================

def find_logo_file():

    for filename in [
        "jahantab_logo_transparent-1.png",
        "logo.png",
        "logo.jpg",
        "logo.jpeg",
    ]:

        if os.path.exists(
            filename
        ):

            return filename

    return ""


LOGO_FILE = find_logo_file()


def download_image(
    url,
    filename="_news_image.jpg"
):

    if not url:

        return ""

    try:

        response = SESSION.get(
            url,
            timeout=REQUEST_TIMEOUT,
            stream=True
        )

        if response.status_code >= 400:

            return ""

        content_type = (
            response.headers
            .get(
                "Content-Type",
                ""
            )
            .lower()
        )

        if (
            "image"
            not in content_type
            and not url.lower().endswith(
                (
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                )
            )
        ):

            return ""

        with open(
            filename,
            "wb"
        ) as f:

            for chunk in response.iter_content(
                chunk_size=8192
            ):

                if chunk:

                    f.write(chunk)

        image = Image.open(
            filename
        )

        image.verify()

        return filename

    except Exception as exc:

        print(
            f"IMAGE ERROR: {exc}"
        )

        try:

            if os.path.exists(
                filename
            ):

                os.remove(
                    filename
                )

        except Exception:
            pass

        return ""


def add_logo(
    image_path
):

    if not LOGO_FILE:

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
            base.width // 6
        )

        ratio = (
            max_width
            / logo.width
        )

        new_height = int(
            logo.height
            * ratio
        )

        logo = logo.resize(
            (
                max_width,
                new_height
            ),
            Image.LANCZOS
        )

        margin = max(
            10,
            base.width // 100
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
            (x, y)
        )

        output = (
            "_final_news_image.jpg"
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

        print(
            f"LOGO ERROR: {exc}"
        )

        return image_path


# =========================================================
# TELEGRAM CAPTION
# =========================================================

def build_caption(
    item: NewsItem
):

    title = escape_html(
        shorten(
            item.title,
            220
        )
    )

    description = escape_html(
        shorten(
            item.description,
            550
        )
    )

    source = escape_html(
        item.source
    )

    lines = []

    # عنوان
    lines.append(
        f"📰 <b>{title}</b>"
    )

    lines.append("")

    # خلاصه
    if description:

        lines.append(
            description
        )

        lines.append("")

    # منبع
    lines.append(
        f"🔗 منبع: {source}"
    )

    # جداکننده
    lines.append(
        "━━━━━━━━━━━━━━━━━━"
    )

    # امضای جهان تاب
    lines.append(
        "🌐 <b>جهان تاب</b> | "
        "<i>آخرین تحولات جهان</i>"
    )

    caption = "\n".join(
        lines
    )

    if len(caption) > 1000:

        caption = (
            caption[:997]
            + "..."
        )

    return caption


# =========================================================
# TELEGRAM API
# =========================================================

def telegram_api(
    method
):

    return (
        "https://api.telegram.org/bot"
        f"{BOT_TOKEN}/{method}"
    )


def send_photo(
    item: NewsItem,
    image_path
):

    if (
        not BOT_TOKEN
        or not CHAT_ID
    ):

        print(
            "ERROR: BOT_TOKEN "
            "or CHAT_ID missing."
        )

        return False

    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "مشاهده خبر",
                    "url": item.url,
                }
            ]
        ]
    }

    data = {
        "chat_id": CHAT_ID,

        "caption": build_caption(
            item
        ),

        "parse_mode": "HTML",

        "reply_markup": json.dumps(
            keyboard,
            ensure_ascii=False
        ),
    }

    try:

        with open(
            image_path,
            "rb"
        ) as photo:

            response = SESSION.post(
                telegram_api(
                    "sendPhoto"
                ),

                data=data,

                files={
                    "photo": photo
                },

                timeout=40,
            )

        if response.ok:

            result = response.json()

            if result.get(
                "ok"
            ):

                print(
                    f"SENT: {item.title}"
                )

                return True

        print(
            "TELEGRAM ERROR:",
            response.status_code,
            response.text[:1000]
        )

    except Exception as exc:

        print(
            f"TELEGRAM SEND ERROR: {exc}"
        )

    return False


# =========================================================
# COLLECT NEWS
# =========================================================

def collect_items():

    all_items = []

    for source in SOURCES:

        print(
            f"\n========== "
            f"{source.name} "
            f"=========="
        )

        feeds = discover_feeds(
            source
        )

        if not feeds:

            print(
                "No feeds discovered."
            )

            continue

        source_items = []

        for feed_url in feeds:

            print(
                f"Checking: "
                f"{feed_url}"
            )

            parsed = parse_feed(
                feed_url,
                source
            )

            source_items.extend(
                parsed
            )

            if (
                len(source_items)
                >= MAX_ITEMS_PER_SOURCE
            ):

                break

        # حذف URL تکراری
        unique = []

        seen = set()

        for item in source_items:

            key = canonical_url(
                item.url
            )

            if key in seen:

                continue

            seen.add(key)

            unique.append(
                item
            )

        # ارزیابی اولیه
        for item in unique:

            calculate_score(
                item
            )

        # فقط تعداد محدودی صفحه را
        # برای تصویر/خلاصه باز می‌کنیم
        for item in unique[:10]:

            extract_article_data(
                item
            )

            calculate_score(
                item
            )

        accepted = 0

        for item in unique:

            if evaluate(item):

                all_items.append(
                    item
                )

                accepted += 1

            else:

                print(
                    f"FILTERED: "
                    f"{item.title}"
                )

        print(
            f"Accepted from "
            f"{source.name}: "
            f"{accepted}"
        )

    return all_items


# =========================================================
# LAST PUBLISH STATE
# =========================================================

def load_last_publish():

    if not os.path.exists(
        LAST_PUBLISH_FILE
    ):

        return None

    try:

        with open(
            LAST_PUBLISH_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            value = f.read().strip()

        return float(value)

    except Exception:

        return None


def save_last_publish():

    try:

        with open(
            LAST_PUBLISH_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            f.write(
                str(time.time())
            )

    except Exception as exc:

        print(
            f"LAST PUBLISH ERROR: {exc}"
        )


def can_publish_now(
    has_very_major=False
):

    last = load_last_publish()

    # اولین ارسال
    if last is None:

        return True

    elapsed = (
        time.time()
        - last
    ) / 60

    # حادثه فوق مهم:
    # حداقل 10 دقیقه
    if has_very_major:

        print(
            f"Minutes since last "
            f"publish: {elapsed:.1f}"
        )

        return elapsed >= 10

    # حالت عادی:
    # حداقل 15 دقیقه
    print(
        f"Minutes since last "
        f"publish: {elapsed:.1f}"
    )

    return elapsed >= 15


# =========================================================
# SELECT ONE NEWS
# =========================================================

def select_items(
    items,
    sent_links,
    sent_titles
):

    candidates = []

    for item in items:

        link = canonical_url(
            item.url
        )

        title_hash = (
            title_fingerprint(
                item.title
            )
        )

        if link in sent_links:

            continue

        if title_hash in sent_titles:

            continue

        candidates.append(
            item
        )

    candidates = dedupe_cross_source(
        candidates
    )

    candidates.sort(
        key=lambda x: (
            x.is_very_major,
            x.score,
            x.event_score,
            x.source in TRUSTED_SOURCES,
        ),
        reverse=True,
    )

    if not candidates:

        return []

    # اگر خبر خیلی مهم وجود داشته باشد،
    # فاصله 10 دقیقه‌ای ملاک است.
    very_major_exists = any(
        x.is_very_major
        for x in candidates
    )

    if not can_publish_now(
        very_major_exists
    ):

        print(
            "WAIT: publish interval "
            "has not arrived."
        )

        return []

    # فقط یک خبر
    return [
        candidates[0]
    ]


# =========================================================
# SAVE SENT
# =========================================================

def save_sent(
    item: NewsItem
):

    append_line(
        SENT_LINKS_FILE,
        canonical_url(
            item.url
        )
    )

    append_line(
        SENT_TITLES_FILE,
        title_fingerprint(
            item.title
        )
    )


# =========================================================
# RUN
# =========================================================

def run_once():

    print(
        "=========================================="
    )

    print(
        VERSION
    )

    print(
        "=========================================="
    )

    if not BOT_TOKEN:

        print(
            "ERROR: BOT_TOKEN missing."
        )

        return

    if not CHAT_ID:

        print(
            "ERROR: CHAT_ID missing."
        )

        return

    sent_links = load_lines(
        SENT_LINKS_FILE
    )

    sent_titles = load_lines(
        SENT_TITLES_FILE
    )

    print(
        f"Already sent links: "
        f"{len(sent_links)}"
    )

    print(
        f"Already sent titles: "
        f"{len(sent_titles)}"
    )

    print(
        "Collecting and filtering news..."
    )

    items = collect_items()

    print(
        f"Accepted candidates: "
        f"{len(items)}"
    )

    selected = select_items(
        items,
        sent_links,
        sent_titles
    )

    print(
        f"Selected: "
        f"{len(selected)}"
    )

    if not selected:

        print(
            "NO NEW NEWS TO PUBLISH"
        )

        return

    for item in selected:

        print(
            "------------------------------------------"
        )

        print(
            f"Publishing: "
            f"{item.title}"
        )

        print(
            f"Source: "
            f"{item.source}"
        )

        print(
            f"Score: "
            f"{item.score}"
        )

        print(
            f"VERY MAJOR: "
            f"{item.is_very_major}"
        )

        if not item.image:

            extract_article_data(
                item
            )

        image_path = download_image(
            item.image
        )

        if not image_path:

            print(
                "No valid image."
            )

            print(
                "News will not be published."
            )

            continue

        final_image = add_logo(
            image_path
        )

        if send_photo(
            item,
            final_image
        ):

            # ذخیره خبر ارسال‌شده
            save_sent(
                item
            )

            # ثبت زمان ارسال
            save_last_publish()

            sent_links.add(
                canonical_url(
                    item.url
                )
            )

            sent_titles.add(
                title_fingerprint(
                    item.title
                )
            )

            time.sleep(
                POST_DELAY
            )

        # پاک کردن فایل‌های موقت
        for filename in (
            "_news_image.jpg",
            "_final_news_image.jpg",
        ):

            try:

                if os.path.exists(
                    filename
                ):

                    os.remove(
                        filename
                    )

            except Exception:
                pass

    print(
        "=========================================="
    )

    print(
        "RUN FINISHED"
    )

    print(
        "=========================================="
    )


# =========================================================
# MAIN
# =========================================================

def main():

    run_once()


if __name__ == "__main__":

    main()