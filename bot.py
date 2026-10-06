# ============================================================
# JAHANTAB TELEGRAM ANALYSIS BOT - V2.7
# ============================================================
#
# جهان تاب | رصد و انتشار مقاله و تحلیل
#
# حداکثر 10 مطلب مناسب در روز
# 10 عدد سقف است، نه سهمیه.
#
# تمرکز:
# - جنگ ایران، آمریکا و اسرائیل
# - توان دفاعی و نظامی ایران
# - موشک و پهپاد
# - پدافند و بازدارندگی
# - یمن و انصارالله
# - حزب‌الله لبنان
# - عراق و محور مقاومت
# - تنگه هرمز و خلیج فارس
# - پرونده هسته‌ای و امنیتی
# - تحولات راهبردی منطقه
#
# فقط منابع داخلی ایران
#
# نسخه: V2.7
# ============================================================

import os
import re
import html
import json
import time
import logging
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse
from difflib import SequenceMatcher

import feedparser
import requests
from bs4 import BeautifulSoup
from PIL import Image, UnidentifiedImageError
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ============================================================
# CONFIG
# ============================================================

VERSION = "JAHANTAB TELEGRAM ANALYSIS BOT - V2.7"

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = os.getenv(
    "CHAT_ID",
    "@jahantab_news"
).strip()

BASE_DIR = Path(__file__).resolve().parent
STATE_DIR = BASE_DIR / "state"

SENT_LINKS_FILE = (
    STATE_DIR / "sent_links.txt"
)

SENT_TITLES_FILE = (
    STATE_DIR / "sent_titles.txt"
)

SOURCE_HISTORY_FILE = (
    STATE_DIR / "source_history.txt"
)

PUBLISHED_DAYS_FILE = (
    STATE_DIR / "published_days.json"
)

LAST_PUBLISH_FILE = (
    STATE_DIR / "last_publish.txt"
)

IMAGE_FILE = (
    BASE_DIR / "news_original.jpg"
)

FINAL_IMAGE_FILE = (
    BASE_DIR / "final_news.jpg"
)

LOGO_FILES = [
    BASE_DIR / "jahantab_logo_transparent-1.png",
    BASE_DIR / "jahantab_logo.png",
    BASE_DIR / "logo.png",
]


# ============================================================
# CHANNEL LINKS
# ============================================================

TELEGRAM_URL = (
    "https://t.me/jahantab_news"
)

BALE_URL = (
    "https://ble.ir/jahantabnews"
)

SOROUSH_URL = (
    "https://splus.ir/jahantabnews"
)


# ============================================================
# PUBLISH SETTINGS
# ============================================================

# حداکثر تعداد مطالب مناسب در هر روز
MAX_DAILY_ARTICLES = 10

# حداکثر سن مقاله
MAX_ARTICLE_AGE_HOURS = 48

# حداقل فاصله بین دو انتشار
MIN_PUBLISH_INTERVAL = 10 * 60

REQUEST_TIMEOUT = 15

USER_AGENT = (
    "Mozilla/5.0 "
    "(Linux; Android 10) "
    "AppleWebKit/537.36 "
    "Chrome/130 Safari/537.36 "
    "JAHANTAB-AnalysisBot/2.7"
)

SEPARATOR = "━━━━━━━━━━━━"


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(message)s"
    ),
)

log = logging.getLogger(
    "jahantab"
)


# ============================================================
# SOURCES
# ============================================================

@dataclass(frozen=True)
class Source:
    name: str
    domain: str
    homepage: str
    priority: int


SOURCES = [

    Source(
        "ایرنا",
        "irna.ir",
        "https://www.irna.ir/",
        5,
    ),

    Source(
        "ایسنا",
        "isna.ir",
        "https://www.isna.ir/",
        5,
    ),

    Source(
        "فارس",
        "farsnews.ir",
        "https://www.farsnews.ir/",
        5,
    ),

    Source(
        "تسنیم",
        "tasnimnews.com",
        "https://www.tasnimnews.com/fa",
        5,
    ),

    Source(
        "مهر",
        "mehrnews.com",
        "https://www.mehrnews.com/",
        5,
    ),

    Source(
        "ایلنا",
        "ilna.ir",
        "https://www.ilna.ir/",
        5,
    ),

    Source(
        "صدا و سیما",
        "iribnews.ir",
        "https://www.iribnews.ir/",
        5,
    ),

    Source(
        "باشگاه خبرنگاران جوان",
        "yjc.ir",
        "https://www.yjc.ir/",
        4,
    ),

    Source(
        "تابناک",
        "tabnak.ir",
        "https://www.tabnak.ir/",
        4,
    ),

    Source(
        "فرارو",
        "fararu.com",
        "https://fararu.com/",
        4,
    ),

    Source(
        "همشهری آنلاین",
        "hamshahrionline.ir",
        "https://www.hamshahrionline.ir/",
        4,
    ),

    Source(
        "آخرین خبر",
        "akharinkhabar.ir",
        "https://akharinkhabar.ir/",
        4,
    ),

    Source(
        "خبر فوری",
        "khabarfoori.com",
        "https://www.khabarfoori.com/",
        4,
    ),

    Source(
        "خبرآنلاین",
        "khabaronline.ir",
        "https://www.khabaronline.ir/",
        4,
    ),

    Source(
        "عصر ایران",
        "asriran.com",
        "https://www.asriran.com/",
        3,
    ),

    Source(
        "مشرق نیوز",
        "mashreghnews.ir",
        "https://www.mashreghnews.ir/",
        3,
    ),

    Source(
        "انتخاب",
        "entekhab.ir",
        "https://www.entekhab.ir/",
        3,
    ),

    Source(
        "الف",
        "alef.ir",
        "https://www.alef.ir/",
        3,
    ),

    Source(
        "روز پلاس",
        "roozplus.com",
        "https://www.roozplus.com/",
        3,
    ),
]

ALLOWED_DOMAINS = {
    source.domain.lower()
    for source in SOURCES
}


# ============================================================
# HTTP SESSION
# ============================================================

session = requests.Session()

retry = Retry(
    total=2,
    connect=2,
    read=2,
    backoff_factor=0.5,
    status_forcelist=[
        429,
        500,
        502,
        503,
        504,
    ],
    allowed_methods=[
        "GET",
        "POST",
    ],
)

adapter = HTTPAdapter(
    max_retries=retry,
    pool_connections=10,
    pool_maxsize=10,
)

session.mount(
    "http://",
    adapter,
)

session.mount(
    "https://",
    adapter,
)

session.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept-Language": (
            "fa-IR,fa;q=0.9"
        ),
    }
)


# ============================================================
# TEXT HELPERS
# ============================================================

def normalize_text(text):

    text = html.unescape(
        text or ""
    )

    replacements = {
        "\u200c": " ",
        "\u200f": " ",
        "\u202a": " ",
        "\u202b": " ",
        "\u202c": " ",
        "\ufeff": " ",
        "\xa0": " ",
    }

    for old, new in replacements.items():
        text = text.replace(
            old,
            new,
        )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def normalize_title(text):

    text = normalize_text(
        text
    ).lower()

    replacements = {
        "ي": "ی",
        "ك": "ک",
        "ۀ": "ه",
        "ة": "ه",
        "ؤ": "و",
        "إ": "ا",
        "أ": "ا",
        "‌": " ",
    }

    for old, new in replacements.items():
        text = text.replace(
            old,
            new,
        )

    text = re.sub(
        r"[^\w\sآ-ی]",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def strip_html(text):

    soup = BeautifulSoup(
        text or "",
        "html.parser",
    )

    return normalize_text(
        soup.get_text(" ")
    )


def shorten_text(
    text,
    max_length,
):

    text = normalize_text(
        text
    )

    if len(text) <= max_length:
        return text

    result = text[
        :max_length
    ]

    position = result.rfind(
        " "
    )

    if position > (
        max_length * 0.70
    ):
        result = result[
            :position
        ]

    return result.rstrip(
        " .،؛:!-"
    ) + "…"


def escape_html(text):

    return html.escape(
        normalize_text(text),
        quote=False,
    )


def contains(
    text,
    word,
):

    text = normalize_title(
        text
    )

    word = normalize_title(
        word
    )

    return (
        re.search(
            rf"(?<!\w)"
            rf"{re.escape(word)}"
            rf"(?!\w)",
            text,
        )
        is not None
    )


def any_contains(
    text,
    words,
):

    return any(
        contains(
            text,
            word,
        )
        for word in words
    )


# ============================================================
# STATE
# ============================================================

def ensure_state():

    STATE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def read_lines(path):

    if not path.exists():
        return set()

    try:

        return {
            normalize_text(line)
            for line in path.read_text(
                encoding="utf-8"
            ).splitlines()
            if normalize_text(line)
        }

    except Exception as exc:

        log.warning(
            "STATE READ ERROR | %s | %s",
            path,
            exc,
        )

        return set()


def write_lines(
    path,
    values,
):

    ensure_state()

    try:

        path.write_text(
            "\n".join(
                sorted(values)
            )
            + (
                "\n"
                if values
                else ""
            ),
            encoding="utf-8",
        )

    except Exception as exc:

        log.warning(
            "STATE WRITE ERROR | %s | %s",
            path,
            exc,
        )


def today_key():

    return time.strftime(
        "%Y-%m-%d",
        time.localtime(),
    )


class State:

    def __init__(self):

        ensure_state()

        self.sent_links = (
            read_lines(
                SENT_LINKS_FILE
            )
        )

        self.sent_titles = (
            read_lines(
                SENT_TITLES_FILE
            )
        )

        self.source_history = (
            read_lines(
                SOURCE_HISTORY_FILE
            )
        )

        self.published_days = (
            self.read_days()
        )

        self.last_publish = (
            self.read_last_publish()
        )

    def read_days(self):

        if not PUBLISHED_DAYS_FILE.exists():
            return {}

        try:

            data = json.loads(
                PUBLISHED_DAYS_FILE.read_text(
                    encoding="utf-8"
                )
            )

            if isinstance(
                data,
                dict,
            ):
                return data

        except Exception:
            pass

        return {}

    def read_last_publish(self):

        if not LAST_PUBLISH_FILE.exists():
            return 0

        try:

            return float(
                LAST_PUBLISH_FILE.read_text(
                    encoding="utf-8"
                ).strip()
            )

        except Exception:
            return 0

    def daily_count(self):

        try:

            return int(
                self.published_days.get(
                    today_key(),
                    0,
                )
            )

        except Exception:

            return 0

    def can_publish_today(self):

        return (
            self.daily_count()
            < MAX_DAILY_ARTICLES
        )

    def save(self):

        write_lines(
            SENT_LINKS_FILE,
            self.sent_links,
        )

        write_lines(
            SENT_TITLES_FILE,
            self.sent_titles,
        )

        write_lines(
            SOURCE_HISTORY_FILE,
            self.source_history,
        )

        PUBLISHED_DAYS_FILE.write_text(
            json.dumps(
                self.published_days,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        LAST_PUBLISH_FILE.write_text(
            str(
                self.last_publish
            ),
            encoding="utf-8",
        )

    def mark_sent(
        self,
        article,
    ):

        self.sent_links.add(
            normalize_text(
                article.link
            )
        )

        self.sent_titles.add(
            normalize_title(
                article.title
            )
        )

        self.source_history.add(
            article.source.domain
        )

        key = today_key()

        self.published_days[key] = (
            self.daily_count() + 1
        )

        self.last_publish = (
            time.time()
        )

        self.prune_days()

        self.save()

    def prune_days(self):

        keys = sorted(
            self.published_days.keys()
        )

        if len(keys) > 30:

            for old_key in keys[:-30]:

                del self.published_days[
                    old_key
                ]


# ============================================================
# SOURCE / URL
# ============================================================

def source_for_url(url):

    try:

        host = urlparse(
            url
        ).netloc.lower()

        host = host.split(
            ":"
        )[0]

        for source in SOURCES:

            if (
                host == source.domain
                or host.endswith(
                    "."
                    + source.domain
                )
            ):

                return source

    except Exception:
        pass

    return None


def allowed_url(url):

    return (
        source_for_url(url)
        is not None
    )


# ============================================================
# RSS
# ============================================================

FEED_PATHS = [
    "/rss",
    "/rss.xml",
    "/feed",
    "/feed.xml",
    "/fa/rss",
    "/fa/rss.xml",
]


def discover_feed(source):

    for path in FEED_PATHS:

        url = urljoin(
            source.homepage,
            path,
        )

        try:

            response = session.get(
                url,
                timeout=8,
                allow_redirects=True,
            )

            if response.ok:

                parsed = feedparser.parse(
                    response.content
                )

                if parsed.entries:

                    return url

        except Exception:
            continue

    try:

        response = session.get(
            source.homepage,
            timeout=8,
        )

        if response.ok:

            soup = BeautifulSoup(
                response.text,
                "html.parser",
            )

            for link in soup.find_all(
                "link",
                href=True,
            ):

                rel = " ".join(
                    link.get(
                        "rel",
                        [],
                    )
                ).lower()

                content_type = (
                    link.get(
                        "type",
                        "",
                    ).lower()
                )

                if (
                    "alternate" in rel
                    and (
                        "rss"
                        in content_type
                        or "atom"
                        in content_type
                        or "xml"
                        in content_type
                    )
                ):

                    url = urljoin(
                        response.url,
                        link["href"],
                    )

                    if allowed_url(
                        url
                    ):
                        return url

    except Exception:
        pass

    return ""


# ============================================================
# ARTICLE
# ============================================================

@dataclass
class Article:

    title: str
    link: str
    description: str
    source: Source
    published: float

    image_url: str = ""

    score: float = 0

    analysis_score: float = 0
    topic_score: float = 0

    is_analysis: bool = False
    is_major_analysis: bool = False


def entry_timestamp(
    entry,
):

    for key in (
        "published_parsed",
        "updated_parsed",
        "created_parsed",
    ):

        value = entry.get(
            key
        )

        if value:

            try:
                return time.mktime(
                    value
                )

            except Exception:
                pass

    return 0


def age_hours(
    timestamp,
):

    if not timestamp:
        return 999999

    return max(
        0,
        (
            time.time()
            - timestamp
        ) / 3600,
    )


def extract_entry_image(
    entry,
):

    candidates = []

    for key in (
        "media_content",
        "media_thumbnail",
        "enclosures",
    ):

        items = entry.get(
            key,
            [],
        )

        if isinstance(
            items,
            dict,
        ):
            items = [items]

        for item in items:

            if isinstance(
                item,
                dict,
            ):

                url = (
                    item.get("url")
                    or item.get("href")
                )

                if url:
                    candidates.append(
                        url
                    )

    for value in (
        entry.get(
            "summary",
            "",
        ),
        entry.get(
            "description",
            "",
        ),
    ):

        soup = BeautifulSoup(
            value or "",
            "html.parser",
        )

        image = soup.find(
            "img"
        )

        if (
            image
            and image.get("src")
        ):

            candidates.append(
                image["src"]
            )

    for url in candidates:

        if url and url.startswith(
            (
                "http://",
                "https://",
            )
        ):

            return url

    return ""


# ============================================================
# ANALYSIS DETECTION
# ============================================================

ANALYSIS_WORDS = [

    "تحلیل",
    "تحلیل راهبردی",
    "تحلیل نظامی",
    "تحلیل امنیتی",
    "تحلیل سیاسی",
    "تحلیل منطقه‌ای",
    "تحلیل منطقه ای",
    "تحلیل جنگ",
    "تحلیل دفاعی",

    "بررسی",
    "بررسی راهبردی",
    "بررسی نظامی",
    "بررسی امنیتی",
    "بررسی جنگ",

    "یادداشت",
    "یادداشت تحلیلی",

    "سرمقاله",
    "مقاله",

    "گزارش تحلیلی",
    "گزارش راهبردی",

    "دیدگاه",
    "دیدگاه کارشناسی",

    "گفت‌وگوی تحلیلی",
    "گفتگوی تحلیلی",

    "گفت‌وگو با کارشناس",
    "گفتگو با کارشناس",

    "کارشناس",
    "کارشناسی",
    "تحلیلگر",
    "تحلیل‌گر",

    "چرا",
    "چگونه",

    "بررسی ابعاد",
    "ابعاد",
    "پیامدها",
    "پیامد",
    "چشم‌انداز",
    "چشم انداز",
    "آینده",
    "راهبرد",
    "راهبردی",
    "بازدارندگی",
]


STRONG_ANALYSIS_WORDS = [

    "سرمقاله",
    "یادداشت تحلیلی",
    "تحلیل راهبردی",
    "تحلیل نظامی",
    "تحلیل امنیتی",
    "تحلیل جنگ",
    "گزارش تحلیلی",
    "گزارش راهبردی",
    "مقاله",
]


TOPIC_WORDS = [

    "ایران",
    "آمریکا",
    "ترامپ",
    "اسرائیل",
    "رژیم صهیونیستی",

    "جنگ",
    "حمله",

    "موشک",
    "موشکی",
    "پهپاد",

    "پدافند",
    "دفاع",
    "دفاعی",

    "نیروی هوافضا",
    "سپاه",
    "ارتش",

    "بازدارندگی",
    "توان نظامی",
    "توان دفاعی",
    "توان موشکی",
    "توان پهپادی",

    "هسته‌ای",
    "هسته ای",
    "آژانس",

    "تنگه هرمز",
    "هرمز",
    "خلیج فارس",

    "حزب‌الله",
    "حزب الله",
    "لبنان",

    "انصارالله",
    "انصار الله",
    "حوثی",
    "یمن",

    "عراق",

    "مقاومت",
    "گروه‌های مقاومت",
    "گروه های مقاومت",

    "فلسطین",
    "غزه",
    "حماس",

    "منطقه",
    "خاورمیانه",
]


MAJOR_COMBOS = [

    ("ایران", "آمریکا"),
    ("ایران", "اسرائیل"),
    ("ایران", "جنگ"),
    ("ایران", "موشک"),
    ("ایران", "پهپاد"),
    ("ایران", "بازدارندگی"),
    ("ایران", "توان دفاعی"),
    ("ایران", "توان نظامی"),
    ("ایران", "پدافند"),
    ("ایران", "هسته‌ای"),
    ("ایران", "آژانس"),

    ("آمریکا", "اسرائیل"),

    ("حزب‌الله", "اسرائیل"),
    ("حزب الله", "اسرائیل"),
    ("حزب‌الله", "لبنان"),

    ("انصارالله", "یمن"),
    ("انصار الله", "یمن"),
    ("حوثی", "یمن"),

    ("یمن", "آمریکا"),
    ("یمن", "اسرائیل"),

    ("عراق", "آمریکا"),
    ("عراق", "اسرائیل"),

    ("مقاومت", "اسرائیل"),

    ("هرمز", "ایران"),
]


NEWS_ONLY_WORDS = [

    "خبر فوری",
    "فوری",
    "لحظه‌ای",
    "لحظه ای",
    "اعلام شد",
    "تایید شد",
    "تأیید شد",

    "وقوع",
    "کشته شد",
    "زخمی شد",
    "مجروح شد",

    "انفجار",

    "حمله انجام شد",
    "حمله صورت گرفت",

    "شلیک شد",
    "اصابت کرد",
]


ROUNDUP_WORDS = [

    "بسته خبری",
    "بسته اخبار",

    "صبحانه خبری",
    "صبحانه اخبار",

    "مرور اخبار",
    "مروری بر اخبار",

    "گزیده اخبار",
    "گزیده‌ای از اخبار",

    "مهمترین اخبار امروز",
    "مهم‌ترین اخبار امروز",

    "آخرین اخبار امروز",
    "اخبار مهم امروز",

    "اخبار روز",
    "اخبار مهم روز",

    "اخبار لحظه به لحظه",

    "جمع‌بندی اخبار",
    "جمع بندی اخبار",

    "نگاهی به اخبار",
    "در یک نگاه",
]


REJECT_WORDS = [

    "فال",
    "استخدام",
    "تبریک",
    "سرگرمی",
    "آشپزی",
    "فیلم سینمایی",

    "قیمت روز",
    "جدول",
    "معما",
    "طالع بینی",

    "حاشیه",
    "ورزشی",
    "فوتبال",
    "مسابقه",
    "بازیگر",
    "سلبریتی",
]


# ============================================================
# ANALYSIS SCORE
# ============================================================

def analysis_score(
    article,
):

    title = normalize_text(
        article.title
    )

    description = normalize_text(
        article.description
    )

    full = (
        title
        + " "
        + description
    )

    score = 0

    for word in ANALYSIS_WORDS:

        if contains(
            title,
            word,
        ):

            score += 8

        elif contains(
            description,
            word,
        ):

            score += 3

    for word in STRONG_ANALYSIS_WORDS:

        if contains(
            title,
            word,
        ):

            score += 12

    analytical_patterns = [

        r"\bچرا\b",
        r"\bچگونه\b",

        r"چه خواهد شد",
        r"چه می‌شود",
        r"چه می شود",

        r"پیامد",
        r"آینده",
        r"چشم.?انداز",
        r"سناریو",
        r"معادله",

        r"راهبرد",
        r"بازدارندگی",
        r"موازنه",
        r"تغییر موازنه",
        r"ابعاد",
    ]

    for pattern in analytical_patterns:

        if re.search(
            pattern,
            title,
            flags=re.IGNORECASE,
        ):

            score += 5

    if len(
        description
    ) >= 400:

        score += 4

    if len(
        description
    ) >= 800:

        score += 4

    expert_words = [

        "کارشناس",
        "تحلیلگر",
        "تحلیل‌گر",
        "استاد دانشگاه",
        "پژوهشگر",
        "متخصص",
        "کارشناسان",
        "صاحب‌نظر",
        "صاحب نظر",
    ]

    for word in expert_words:

        if contains(
            full,
            word,
        ):

            score += 4

    url_text = normalize_title(
        article.link
    )

    url_analysis_words = [

        "analysis",
        "article",
        "note",
        "editorial",
        "opinion",
        "report",
        "gozaresh",
        "tahlil",
    ]

    for word in url_analysis_words:

        if word in url_text:

            score += 3

    news_only_count = 0

    for word in NEWS_ONLY_WORDS:

        if contains(
            title,
            word,
        ):

            news_only_count += 1

    if news_only_count >= 2:

        score -= 10

    article.analysis_score = score

    return score


# ============================================================
# TOPIC SCORE
# ============================================================

def topic_score(
    article,
):

    title = normalize_text(
        article.title
    )

    description = normalize_text(
        article.description
    )

    full = (
        title
        + " "
        + description
    )

    score = 0

    for word in TOPIC_WORDS:

        if contains(
            title,
            word,
        ):

            score += 3

        elif contains(
            description,
            word,
        ):

            score += 1

    for first, second in MAJOR_COMBOS:

        if (
            contains(
                title,
                first,
            )
            and contains(
                title,
                second,
            )
        ):

            score += 12

        elif (
            contains(
                full,
                first,
            )
            and contains(
                full,
                second,
            )
        ):

            score += 5

    defense_words = [

        "موشک",
        "موشکی",
        "پهپاد",
        "پدافند",
        "بازدارندگی",
        "توان دفاعی",
        "توان نظامی",
        "دفاع هوایی",
        "نیروی هوافضا",
        "ارتش",
        "سپاه",
    ]

    defense_count = sum(
        1
        for word in defense_words
        if contains(
            full,
            word,
        )
    )

    if defense_count >= 2:

        score += 8

    if (
        contains(
            full,
            "جنگ",
        )
        and (
            contains(
                full,
                "ایران",
            )
            or contains(
                full,
                "آمریکا",
            )
            or contains(
                full,
                "اسرائیل",
            )
        )
    ):

        score += 10

    if (
        contains(
            full,
            "یمن",
        )
        and (
            contains(
                full,
                "انصارالله",
            )
            or contains(
                full,
                "حوثی",
            )
            or contains(
                full,
                "آمریکا",
            )
            or contains(
                full,
                "اسرائیل",
            )
        )
    ):

        score += 10

    if (
        (
            contains(
                full,
                "حزب‌الله",
            )
            or contains(
                full,
                "حزب الله",
            )
        )
        and (
            contains(
                full,
                "لبنان",
            )
            or contains(
                full,
                "اسرائیل",
            )
        )
    ):

        score += 10

    if (
        contains(
            full,
            "عراق",
        )
        and (
            contains(
                full,
                "مقاومت",
            )
            or contains(
                full,
                "آمریکا",
            )
            or contains(
                full,
                "اسرائیل",
            )
        )
    ):

        score += 8

    article.topic_score = score

    return score


# ============================================================
# CLASSIFICATION
# ============================================================

def classify_article(
    article,
):

    a_score = analysis_score(
        article
    )

    t_score = topic_score(
        article
    )

    is_analysis = (
        a_score >= 12
    )

    topic_relevant = (
        t_score >= 8
    )

    article.score = (
        a_score
        + t_score
        + article.source.priority
    )

    article.is_analysis = (
        is_analysis
        and topic_relevant
    )

    article.is_major_analysis = (
        article.is_analysis
        and a_score >= 24
        and t_score >= 15
    )

    return article


# ============================================================
# ACCEPT
# ============================================================

def is_roundup(
    title,
):

    return any_contains(
        title,
        ROUNDUP_WORDS,
    )


def accept_article(
    article,
):

    title = normalize_text(
        article.title
    )

    if not title:
        return False

    if (
        age_hours(
            article.published
        )
        > MAX_ARTICLE_AGE_HOURS
    ):

        return False

    if len(title) < 20:
        return False

    if is_roundup(title):

        log.info(
            "SKIP ROUNDUP | %s",
            title,
        )

        return False

    if any_contains(
        title,
        REJECT_WORDS,
    ):

        return False

    if not article.is_analysis:

        log.info(
            "SKIP NOT ANALYSIS | %s",
            title,
        )

        return False

    if article.score < 28:

        log.info(
            "SKIP LOW SCORE | %s | score=%s",
            title,
            article.score,
        )

        return False

    return True


# ============================================================
# FEED PARSING
# ============================================================

def parse_feed(
    source,
    feed_url,
):

    articles = []

    try:

        response = session.get(
            feed_url,
            timeout=REQUEST_TIMEOUT,
        )

        if not response.ok:
            return articles

        feed = feedparser.parse(
            response.content
        )

        for entry in feed.entries[:30]:

            title = normalize_text(
                entry.get(
                    "title",
                    "",
                )
            )

            link = normalize_text(
                entry.get(
                    "link",
                    "",
                )
            )

            if not title or not link:
                continue

            if not allowed_url(link):
                continue

            host = urlparse(
                link
            ).netloc.lower()

            if "google." in host:
                continue

            published = (
                entry_timestamp(
                    entry
                )
            )

            if (
                age_hours(
                    published
                )
                > MAX_ARTICLE_AGE_HOURS
            ):

                continue

            description = strip_html(
                entry.get(
                    "summary",
                    entry.get(
                        "description",
                        "",
                    ),
                )
            )

            image_url = (
                extract_entry_image(
                    entry
                )
            )

            article = Article(
                title=title,
                link=link,
                description=description,
                source=source,
                published=published,
                image_url=image_url,
            )

            classify_article(
                article
            )

            if accept_article(
                article
            ):

                articles.append(
                    article
                )

    except Exception as exc:

        log.warning(
            "FEED ERROR | %s | %s | %s",
            source.name,
            feed_url,
            exc,
        )

    return articles


def collect_articles(
    state,
):

    all_articles = []

    for source in SOURCES:

        log.info(
            "FETCHING: %s",
            source.name,
        )

        feed_url = discover_feed(
            source
        )

        if not feed_url:

            log.info(
                "NO RSS: %s",
                source.name,
            )

            continue

        items = parse_feed(
            source,
            feed_url,
        )

        log.info(
            "%s -> %d candidates",
            source.name,
            len(items),
        )

        all_articles.extend(
            items
        )

    return all_articles


# ============================================================
# DEDUPLICATION
# ============================================================

def title_similarity(
    a,
    b,
):

    return SequenceMatcher(
        None,
        normalize_title(a),
        normalize_title(b),
    ).ratio()


def important_words(
    title,
):

    words = set(
        normalize_title(
            title
        ).split()
    )

    stopwords = {

        "از",
        "به",
        "در",
        "با",
        "برای",
        "که",
        "و",
        "یا",
        "این",
        "آن",
        "یک",
        "های",
        "را",
        "بر",
        "تا",
        "است",
        "شد",
        "می",
        "شود",
        "کرد",
        "کند",
        "خواهد",
    }

    return {
        word
        for word in words
        if len(word) >= 3
        and word not in stopwords
    }


def same_analysis_topic(
    a,
    b,
):

    similarity = title_similarity(
        a.title,
        b.title,
    )

    if similarity >= 0.76:
        return True

    words_a = important_words(
        a.title
    )

    words_b = important_words(
        b.title
    )

    if not words_a or not words_b:
        return False

    overlap = (
        len(
            words_a & words_b
        )
        / max(
            1,
            min(
                len(words_a),
                len(words_b),
            ),
        )
    )

    if (
        similarity >= 0.55
        and overlap >= 0.65
    ):

        return True

    return False


def deduplicate(
    articles,
    state,
):

    result = []

    articles = sorted(
        articles,
        key=lambda article: (
            article.is_major_analysis,
            article.score,
            article.analysis_score,
            article.topic_score,
            article.source.priority,
            article.published,
        ),
        reverse=True,
    )

    for article in articles:

        if (
            normalize_text(
                article.link
            )
            in state.sent_links
        ):

            continue

        if (
            normalize_title(
                article.title
            )
            in state.sent_titles
        ):

            continue

        duplicate = False

        for existing in result:

            if same_analysis_topic(
                article,
                existing,
            ):

                log.info(
                    "DUPLICATE ANALYSIS | %s | duplicate of | %s",
                    article.title,
                    existing.title,
                )

                duplicate = True

                break

        if not duplicate:

            result.append(
                article
            )

    return result


# ============================================================
# SOURCE DIVERSITY
# ============================================================

def source_was_recently_used(
    article,
    state,
):

    return (
        article.source.domain
        in state.source_history
    )


def source_penalty(
    article,
    state,
):

    if not source_was_recently_used(
        article,
        state,
    ):

        return 0

    if article.is_major_analysis:
        return 3

    return 8


# ============================================================
# SELECT BEST
# ============================================================

def select_best_article(
    articles,
    state,
):

    if not state.can_publish_today():

        log.info(
            "DAILY LIMIT REACHED | %d/%d",
            state.daily_count(),
            MAX_DAILY_ARTICLES,
        )

        return None

    articles = deduplicate(
        articles,
        state,
    )

    if not articles:
        return None

    if state.last_publish:

        elapsed = (
            time.time()
            - state.last_publish
        )

        if (
            elapsed
            < MIN_PUBLISH_INTERVAL
        ):

            log.info(
                "PUBLISH INTERVAL NOT REACHED | %.0f sec",
                elapsed,
            )

            return None

    ranked = []

    for article in articles:

        adjusted = (
            article.score
            - source_penalty(
                article,
                state,
            )
        )

        freshness_bonus = 0

        age = age_hours(
            article.published
        )

        if age <= 6:

            freshness_bonus = 5

        elif age <= 12:

            freshness_bonus = 3

        elif age <= 24:

            freshness_bonus = 1

        final_score = (
            adjusted
            + freshness_bonus
        )

        ranked.append(
            (
                final_score,
                article,
            )
        )

    ranked.sort(
        key=lambda item: (
            item[1].is_major_analysis,
            item[0],
            item[1].published,
        ),
        reverse=True,
    )

    for final_score, article in ranked:

        if source_was_recently_used(
            article,
            state,
        ):

            if not (
                article.is_major_analysis
                and article.score >= 50
            ):

                log.info(
                    "SOURCE DIVERSITY SKIP | %s | %s",
                    article.source.name,
                    article.title,
                )

                continue

        log.info(
            "RANKED | %s | score=%s | source=%s",
            article.title,
            final_score,
            article.source.name,
        )

        return article

    return None


# ============================================================
# ENRICH ARTICLE
# ============================================================

def enrich_article(
    article,
):

    try:

        response = session.get(
            article.link,
            timeout=REQUEST_TIMEOUT,
        )

        if not response.ok:
            return article

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        paragraphs = []

        for paragraph in soup.find_all(
            "p"
        ):

            text = normalize_text(
                paragraph.get_text(
                    " "
                )
            )

            if len(text) >= 35:

                paragraphs.append(
                    text
                )

            if len(
                paragraphs
            ) >= 20:

                break

        if paragraphs:

            article.description = (
                " ".join(
                    paragraphs
                )
            )

            classify_article(
                article
            )

        image_candidates = []

        for attr, value in [
            (
                "property",
                "og:image",
            ),
            (
                "name",
                "twitter:image",
            ),
        ]:

            tag = soup.find(
                "meta",
                attrs={
                    attr: value,
                },
            )

            if (
                tag
                and tag.get("content")
            ):

                image_candidates.append(
                    urljoin(
                        article.link,
                        tag["content"],
                    )
                )

        if article.image_url:

            image_candidates.insert(
                0,
                article.image_url,
            )

        for image in soup.find_all(
            "img",
            src=True,
        )[:20]:

            image_candidates.append(
                urljoin(
                    article.link,
                    image["src"],
                )
            )

        for image_url in image_candidates:

            if image_url.startswith(
                (
                    "http://",
                    "https://",
                )
            ):

                article.image_url = (
                    image_url
                )

                break

    except Exception as exc:

        log.warning(
            "ENRICH ERROR | %s",
            exc,
        )

    return article


# ============================================================
# SUMMARY
# ============================================================

def split_sentences(
    text,
):

    text = normalize_text(
        text
    )

    if not text:
        return []

    parts = re.split(
        r"(?<=[.!؟])\s+",
        text,
    )

    result = []

    for part in parts:

        part = normalize_text(
            part
        )

        if len(part) >= 35:

            result.append(
                part
            )

    return result


def build_summary(
    article,
):

    text = normalize_text(
        article.description
    )

    if not text:

        return (
            "جزئیات و متن کامل این "
            "مطلب در منبع اصلی قابل مطالعه است."
        )

    sentences = split_sentences(
        text
    )

    selected = []

    for sentence in sentences:

        if len(sentence) < 35:
            continue

        selected.append(
            sentence
        )

        if len(
            selected
        ) >= 5:

            break

    if len(selected) < 3:

        selected = sentences[:5]

    result = " ".join(
        selected
    )

    return shorten_text(
        result,
        900,
    )


# ============================================================
# IMAGE
# ============================================================

def download_good_image(
    url,
):

    if not url:
        return ""

    try:

        response = session.get(
            url,
            timeout=REQUEST_TIMEOUT,
            stream=True,
        )

        if not response.ok:
            return ""

        content_type = (
            response.headers.get(
                "Content-Type",
                "",
            ).lower()
        )

        if (
            content_type
            and not content_type.startswith(
                "image/"
            )
        ):

            return ""

        total = 0

        with open(
            IMAGE_FILE,
            "wb",
        ) as image_file:

            for chunk in response.iter_content(
                chunk_size=16384
            ):

                if not chunk:
                    continue

                total += len(
                    chunk
                )

                if (
                    total
                    > 8 * 1024 * 1024
                ):

                    return ""

                image_file.write(
                    chunk
                )

        try:

            with Image.open(
                IMAGE_FILE
            ) as image:

                width, height = (
                    image.size
                )

                if (
                    width < 800
                    or height < 450
                ):

                    log.info(
                        "LOW QUALITY IMAGE | %sx%s",
                        width,
                        height,
                    )

                    return ""

                image.verify()

        except (
            UnidentifiedImageError,
            OSError,
        ):

            return ""

        return str(
            IMAGE_FILE
        )

    except Exception as exc:

        log.warning(
            "IMAGE ERROR | %s",
            exc,
        )

        return ""


# ============================================================
# LOGO
# ============================================================

def find_logo():

    for path in LOGO_FILES:

        if path.exists():
            return path

    return None


def tint_logo_to_sky_blue(
    logo,
):

    try:

        logo = logo.convert(
            "RGBA"
        )

        pixels = logo.load()

        target = (
            110,
            207,
            246,
        )

        for y in range(
            logo.height
        ):

            for x in range(
                logo.width
            ):

                r, g, b, a = (
                    pixels[x, y]
                )

                if a == 0:
                    continue

                brightness = (
                    0.30 * r
                    + 0.59 * g
                    + 0.11 * b
                )

                factor = (
                    0.65
                    + 0.35
                    * (
                        brightness
                        / 255
                    )
                )

                pixels[x, y] = (
                    int(
                        target[0]
                        * factor
                    ),
                    int(
                        target[1]
                        * factor
                    ),
                    int(
                        target[2]
                        * factor
                    ),
                    a,
                )

        return logo

    except Exception:

        return logo


def add_logo_to_image(
    image_path,
):

    logo_path = find_logo()

    if not logo_path:

        log.warning(
            "JAHANTAB LOGO NOT FOUND"
        )

        return image_path

    try:

        base = Image.open(
            image_path
        ).convert(
            "RGBA"
        )

        logo = Image.open(
            logo_path
        ).convert(
            "RGBA"
        )

        logo = tint_logo_to_sky_blue(
            logo
        )

        target_width = max(
            100,
            int(
                base.width
                * 0.18
            ),
        )

        ratio = (
            target_width
            / logo.width
        )

        target_height = max(
            1,
            int(
                logo.height
                * ratio
            ),
        )

        logo = logo.resize(
            (
                target_width,
                target_height,
            ),
            Image.LANCZOS,
        )

        alpha = logo.getchannel(
            "A"
        )

        alpha = alpha.point(
            lambda p: int(
                p * 0.82
            )
        )

        logo.putalpha(
            alpha
        )

        margin = max(
            18,
            int(
                base.width
                * 0.018
            ),
        )

        base.alpha_composite(
            logo,
            (
                margin,
                margin,
            ),
        )

        base = base.convert(
            "RGB"
        )

        base.save(
            FINAL_IMAGE_FILE,
            "JPEG",
            quality=92,
            optimize=True,
        )

        return str(
            FINAL_IMAGE_FILE
        )

    except Exception as exc:

        log.warning(
            "LOGO ERROR | %s",
            exc,
        )

        return image_path


# ============================================================
# TELEGRAM LINK BUTTONS
# ============================================================

def channel_keyboard():

    return json.dumps(
        {
            "inline_keyboard": [

                [
                    {
                        "text": "🌐 تلگرام",
                        "url": TELEGRAM_URL,
                    },
                    {
                        "text": "🟦 بله",
                        "url": BALE_URL,
                    },
                    {
                        "text": "🟢 سروش",
                        "url": SOROUSH_URL,
                    },
                ],

            ]
        },
        ensure_ascii=False,
    )


def article_keyboard(
    article,
):

    return json.dumps(
        {
            "inline_keyboard": [

                [
                    {
                        "text": "🔗 مشاهده مطلب اصلی",
                        "url": article.link,
                    }
                ],

                [
                    {
                        "text": "🌐 تلگرام",
                        "url": TELEGRAM_URL,
                    },
                    {
                        "text": "🟦 بله",
                        "url": BALE_URL,
                    },
                    {
                        "text": "🟢 سروش",
                        "url": SOROUSH_URL,
                    },
                ],

            ]
        },
        ensure_ascii=False,
    )


# ============================================================
# CAPTION
# ============================================================

def build_caption(
    article,
):

    title = escape_html(
        shorten_text(
            article.title,
            250,
        )
    )

    summary = escape_html(
        build_summary(
            article
        )
    )

    source = escape_html(
        article.source.name
    )

    caption = (
        f"<b>📝 {title}</b>\n\n"
        f"{summary}\n\n"
        f"🔗 منبع اصلی: "
        f"{source}\n\n"
        f"{SEPARATOR}\n"
        f"🌐 جهان تاب | آخرین تحولات جهان\n"
        f"🌐 @jahantab_news"
    )

    if len(caption) <= 1024:

        return caption

    fixed = (
        f"<b>📝 {title}</b>\n\n"
        f"\n\n"
        f"🔗 منبع اصلی: "
        f"{source}\n\n"
        f"{SEPARATOR}\n"
        f"🌐 جهان تاب | آخرین تحولات جهان\n"
        f"🌐 @jahantab_news"
    )

    available = max(
        150,
        1024
        - len(fixed)
        - 10,
    )

    summary = escape_html(
        shorten_text(
            build_summary(
                article
            ),
            available,
        )
    )

    return (
        f"<b>📝 {title}</b>\n\n"
        f"{summary}\n\n"
        f"🔗 منبع اصلی: "
        f"{source}\n\n"
        f"{SEPARATOR}\n"
        f"🌐 جهان تاب | آخرین تحولات جهان\n"
        f"🌐 @jahantab_news"
    )


# ============================================================
# TELEGRAM API
# ============================================================

TELEGRAM_API = (
    "https://api.telegram.org/bot"
)


def telegram_request(
    method,
    data=None,
    files=None,
):

    url = (
        TELEGRAM_API
        + BOT_TOKEN
        + "/"
        + method
    )

    for attempt in range(4):

        try:

            response = session.post(
                url,
                data=data,
                files=files,
                timeout=35,
            )

            if (
                response.status_code
                == 429
            ):

                try:

                    retry_after = int(
                        response.json()
                        .get(
                            "parameters",
                            {},
                        )
                        .get(
                            "retry_after",
                            10,
                        )
                    )

                except Exception:

                    retry_after = 10

                time.sleep(
                    retry_after + 1
                )

                continue

            return response

        except Exception as exc:

            log.warning(
                "TELEGRAM ERROR %d | %s",
                attempt + 1,
                exc,
            )

            time.sleep(
                2 ** attempt
            )

    return None


# ============================================================
# SEND MESSAGE
# ============================================================

def send_message(
    article,
):

    text = (
        f"📝 {article.title}\n\n"
        f"{build_summary(article)}\n\n"
        f"🔗 منبع اصلی: "
        f"{article.source.name}\n\n"
        f"{SEPARATOR}\n"
        f"🌐 جهان تاب | آخرین تحولات جهان\n"
        f"🌐 @jahantab_news"
    )

    text = text[:4096]

    response = telegram_request(
        "sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": article_keyboard(
                article
            ),
            "disable_web_page_preview": "false",
        },
    )

    if response is None:
        return False

    try:

        return bool(
            response.json().get(
                "ok"
            )
        )

    except Exception:

        return False


def send_photo(
    article,
):

    image_path = ""

    if article.image_url:

        image_path = (
            download_good_image(
                article.image_url
            )
        )

        if image_path:

            image_path = (
                add_logo_to_image(
                    image_path
                )
            )

    if not image_path:

        return send_message(
            article
        )

    caption = build_caption(
        article
    )

    try:

        with open(
            image_path,
            "rb",
        ) as photo:

            response = telegram_request(
                "sendPhoto",
                data={
                    "chat_id": CHAT_ID,
                    "caption": caption,
                    "parse_mode": "HTML",
                    "reply_markup": article_keyboard(
                        article
                    ),
                },
                files={
                    "photo": photo,
                },
            )

        if response is not None:

            try:

                result = response.json()

                if result.get(
                    "ok"
                ):

                    return True

                log.warning(
                    "sendPhoto failed | %s",
                    result,
                )

            except Exception:
                pass

    except Exception as exc:

        log.warning(
            "SEND PHOTO ERROR | %s",
            exc,
        )

    return send_message(
        article
    )


# ============================================================
# CLEANUP
# ============================================================

def cleanup():

    for path in (
        IMAGE_FILE,
        FINAL_IMAGE_FILE,
    ):

        try:

            if path.exists():
                path.unlink()

        except Exception:
            pass


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print(VERSION)
    print("=" * 70)

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN is not set."
        )

    ensure_state()

    state = State()

    log.info(
        "Already sent: %d",
        len(
            state.sent_links
        ),
    )

    log.info(
        "Published today: %d/%d",
        state.daily_count(),
        MAX_DAILY_ARTICLES,
    )

    if not state.can_publish_today():

        log.info(
            "DAILY LIMIT REACHED - NO PUBLISH"
        )

        return

    log.info(
        "Recent sources: %s",
        ", ".join(
            sorted(
                state.source_history
            )
        )
        or "none",
    )

    # --------------------------------------------------------
    # جمع‌آوری
    # --------------------------------------------------------

    articles = collect_articles(
        state
    )

    log.info(
        "TOTAL ANALYSIS CANDIDATES: %d",
        len(articles),
    )

    if not articles:

        log.info(
            "NO SUITABLE ANALYSIS FOUND"
        )

        return

    # --------------------------------------------------------
    # انتخاب
    # --------------------------------------------------------

    best = select_best_article(
        articles,
        state,
    )

    if not best:

        log.info(
            "NO SUITABLE ANALYSIS TO PUBLISH"
        )

        return

    log.info(
        "SELECTED:"
        " source=%s | "
        "title=%s | "
        "score=%s | "
        "analysis=%s | "
        "topic=%s",
        best.source.name,
        best.title,
        best.score,
        best.analysis_score,
        best.topic_score,
    )

    # --------------------------------------------------------
    # دریافت متن کامل
    # --------------------------------------------------------

    best = enrich_article(
        best
    )

    classify_article(
        best
    )

    # --------------------------------------------------------
    # کنترل نهایی
    # --------------------------------------------------------

    if not best.is_analysis:

        log.warning(
            "REJECT AFTER ENRICH | NOT ANALYSIS | %s",
            best.title,
        )

        cleanup()

        return

    if best.topic_score < 8:

        log.warning(
            "REJECT AFTER ENRICH | LOW TOPIC SCORE | %s",
            best.title,
        )

        cleanup()

        return

    # --------------------------------------------------------
    # انتشار
    # --------------------------------------------------------

    success = send_photo(
        best
    )

    if success:

        state.mark_sent(
            best
        )

        log.info(
            "PUBLISHED SUCCESSFULLY | %d/%d TODAY",
            state.daily_count(),
            MAX_DAILY_ARTICLES,
        )

    else:

        log.error(
            "PUBLISH FAILED - STATE NOT UPDATED"
        )

    cleanup()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        log.info(
            "STOPPED"
        )

    except Exception as exc:

        log.exception(
            "FATAL ERROR: %s",
            exc,
        )

        raise