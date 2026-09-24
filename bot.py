# ============================================================
# JAHANTAB TELEGRAM NEWS BOT - V2.6
# ============================================================

import os
import re
import html
import json
import time
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageEnhance, UnidentifiedImageError
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ============================================================
# CONFIG
# ============================================================

VERSION = "JAHANTAB TELEGRAM NEWS BOT - V2.6"

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "@jahantab_news").strip()

BASE_DIR = Path(__file__).resolve().parent
STATE_DIR = BASE_DIR / "state"

SENT_LINKS_FILE = STATE_DIR / "sent_links.txt"
SENT_TITLES_FILE = STATE_DIR / "sent_titles.txt"
SOURCE_HISTORY_FILE = STATE_DIR / "source_history.txt"
LAST_PUBLISH_FILE = STATE_DIR / "last_publish.txt"

IMAGE_FILE = BASE_DIR / "news_original.jpg"
FINAL_IMAGE_FILE = BASE_DIR / "final_news.jpg"

# لوگوهای احتمالی موجود در مخزن
LOGO_FILES = [
    BASE_DIR / "jahantab_logo_transparent-1.png",
    BASE_DIR / "jahantab_logo.png",
    BASE_DIR / "logo.png",
]

MAX_NEWS_AGE_HOURS = 12
REQUEST_TIMEOUT = 15

# فاصله انتشار معمولی
NORMAL_INTERVAL = 15 * 60

# خبر بسیار مهم می‌تواند زودتر منتشر شود
MAJOR_INTERVAL = 10 * 60

USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 10) "
    "AppleWebKit/537.36 "
    "Chrome/130 Safari/537.36 "
    "JAHANTAB-NewsBot/2.6"
)

SIGNATURE = (
    "🌐 جهان تاب | آخرین تحولات جهان\n"
    "🌐 @jahantab_news"
)

SEPARATOR = "━━━━━━━━━━━━"


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

log = logging.getLogger("jahantab")


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
    Source("ایرنا", "irna.ir", "https://www.irna.ir/", 5),
    Source("ایسنا", "isna.ir", "https://www.isna.ir/", 5),
    Source("فارس", "farsnews.ir", "https://www.farsnews.ir/", 5),
    Source("تسنیم", "tasnimnews.com", "https://www.tasnimnews.com/fa", 5),
    Source("مهر", "mehrnews.com", "https://www.mehrnews.com/", 5),
    Source("ایلنا", "ilna.ir", "https://www.ilna.ir/", 5),
    Source("صدا و سیما", "iribnews.ir", "https://www.iribnews.ir/", 5),
    Source("باشگاه خبرنگاران جوان", "yjc.ir", "https://www.yjc.ir/", 4),

    Source("تابناک", "tabnak.ir", "https://www.tabnak.ir/", 4),
    Source("فرارو", "fararu.com", "https://fararu.com/", 4),
    Source("همشهری آنلاین", "hamshahrionline.ir",
           "https://www.hamshahrionline.ir/", 4),
    Source("آخرین خبر", "akharinkhabar.ir",
           "https://akharinkhabar.ir/", 4),
    Source("خبر فوری", "khabarfoori.com",
           "https://www.khabarfoori.com/", 4),
    Source("خبرآنلاین", "khabaronline.ir",
           "https://www.khabaronline.ir/", 4),
    Source("عصر ایران", "asriran.com",
           "https://www.asriran.com/", 3),
    Source("مشرق نیوز", "mashreghnews.ir",
           "https://www.mashreghnews.ir/", 3),
    Source("انتخاب", "entekhab.ir",
           "https://www.entekhab.ir/", 3),
    Source("الف", "alef.ir",
           "https://www.alef.ir/", 3),
    Source("روز پلاس", "roozplus.com",
           "https://www.roozplus.com/", 3),
]

ALLOWED_DOMAINS = {
    s.domain.lower()
    for s in SOURCES
}


# ============================================================
# HTTP
# ============================================================

session = requests.Session()

retry = Retry(
    total=2,
    connect=2,
    read=2,
    backoff_factor=0.5,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET", "POST"],
)

adapter = HTTPAdapter(
    max_retries=retry,
    pool_connections=10,
    pool_maxsize=10,
)

session.mount("http://", adapter)
session.mount("https://", adapter)

session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept-Language": "fa-IR,fa;q=0.9",
})


# ============================================================
# TEXT
# ============================================================

def normalize_text(text):
    text = html.unescape(text or "")

    replacements = {
        "\u200c": " ",
        "\u200f": " ",
        "\u202a": " ",
        "\u202b": " ",
        "\u202c": " ",
        "\ufeff": " ",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_title(text):
    text = normalize_text(text).lower()

    replacements = {
        "ي": "ی",
        "ك": "ک",
        "ۀ": "ه",
        "ة": "ه",
        "ؤ": "و",
        "إ": "ا",
        "أ": "ا",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"[^\w\sآ-ی]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def strip_html(text):
    soup = BeautifulSoup(
        text or "",
        "html.parser",
    )
    return normalize_text(
        soup.get_text(" ")
    )


def shorten_text(text, max_length):
    text = normalize_text(text)

    if len(text) <= max_length:
        return text

    result = text[:max_length]
    position = result.rfind(" ")

    if position > max_length * 0.70:
        result = result[:position]

    return result.rstrip(
        " .،؛:!-"
    ) + "…"


def escape_html(text):
    return html.escape(
        normalize_text(text),
        quote=False,
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
            normalize_text(x)
            for x in path.read_text(
                encoding="utf-8"
            ).splitlines()
            if normalize_text(x)
        }
    except Exception as e:
        log.warning(
            "STATE READ ERROR %s: %s",
            path,
            e,
        )
        return set()


def write_lines(path, values):
    ensure_state()

    try:
        path.write_text(
            "\n".join(sorted(values))
            + ("\n" if values else ""),
            encoding="utf-8",
        )
    except Exception as e:
        log.warning(
            "STATE WRITE ERROR %s: %s",
            path,
            e,
        )


class State:

    def __init__(self):

        ensure_state()

        self.sent_links = read_lines(
            SENT_LINKS_FILE
        )

        self.sent_titles = read_lines(
            SENT_TITLES_FILE
        )

        self.source_history = read_lines(
            SOURCE_HISTORY_FILE
        )

        self.last_publish = self.read_last()

    def read_last(self):

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

        LAST_PUBLISH_FILE.write_text(
            str(self.last_publish),
            encoding="utf-8",
        )

    def mark_sent(self, article):

        self.sent_links.add(
            normalize_text(article.link)
        )

        self.sent_titles.add(
            normalize_title(article.title)
        )

        # نگهداری تاریخچه منبع
        # فقط آخرین 12 منبع کافی است
        self.source_history.add(
            article.source.domain
        )

        if len(self.source_history) > 12:
            self.source_history = set(
                list(self.source_history)[-12:]
            )

        self.last_publish = time.time()

        self.save()


# ============================================================
# URL / SOURCE
# ============================================================

def source_for_url(url):

    try:
        host = urlparse(url).netloc.lower()
        host = host.split(":")[0]

        for source in SOURCES:

            if (
                host == source.domain
                or host.endswith(
                    "." + source.domain
                )
            ):
                return source

    except Exception:
        pass

    return None


def allowed_url(url):

    return source_for_url(url) is not None


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

    # اول مسیرهای رایج را امتحان می‌کنیم.
    # فقط در صورت شکست، صفحه اصلی را بررسی می‌کنیم.
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

    # کشف RSS از صفحه اصلی
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
                    link.get("rel", [])
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
                        "rss" in content_type
                        or "atom" in content_type
                        or "xml" in content_type
                    )
                ):

                    url = urljoin(
                        response.url,
                        link["href"],
                    )

                    if allowed_url(url):
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
    major: bool = False


def entry_timestamp(entry):

    for key in (
        "published_parsed",
        "updated_parsed",
        "created_parsed",
    ):

        value = entry.get(key)

        if value:

            try:
                return time.mktime(value)
            except Exception:
                pass

    return 0


def age_hours(timestamp):

    if not timestamp:
        return 999999

    return max(
        0,
        (time.time() - timestamp) / 3600,
    )


def extract_entry_image(entry):

    candidates = []

    for key in (
        "media_content",
        "media_thumbnail",
        "enclosures",
    ):

        items = entry.get(key, [])

        if isinstance(items, dict):
            items = [items]

        for item in items:

            if isinstance(item, dict):

                url = (
                    item.get("url")
                    or item.get("href")
                )

                if url:
                    candidates.append(url)

    for value in (
        entry.get("summary", ""),
        entry.get("description", ""),
    ):

        soup = BeautifulSoup(
            value or "",
            "html.parser",
        )

        image = soup.find("img")

        if image and image.get("src"):
            candidates.append(
                image["src"]
            )

    for url in candidates:

        if url and url.startswith(
            ("http://", "https://")
        ):
            return url

    return ""


# ============================================================
# FILTER WORDS
# ============================================================

DIRECT_TOPICS = [
    "جنگ",
    "حمله",
    "موشک",
    "موشکی",
    "پهپاد",
    "انفجار",
    "ترور",
    "حمله هوایی",
    "حمله موشکی",
    "حمله پهپادی",
    "تحریم",
    "تحریم جدید",
    "مذاکره",
    "مذاکرات",
    "برجام",
    "پرونده هسته‌ای",
    "هسته‌ای",
    "آژانس بین‌المللی انرژی اتمی",
    "شورای امنیت",
    "سازمان ملل",
    "تنگه هرمز",
    "هرمز",
    "خلیج فارس",
    "حزب الله",
    "حزب‌الله",
    "لبنان",
    "حماس",
    "غزه",
    "فلسطین",
    "انصارالله",
    "انصار الله",
    "حوثی",
    "حوثی‌ها",
    "یمن",
    "آمریکا",
    "ترامپ",
    "اسرائیل",
    "رژیم صهیونیستی",
    "زلزله",
    "سیل",
    "آتش سوزی",
    "آتش‌سوزی",
    "هواپیما",
    "قطار",
    "اتوبوس",
    "تصادف",
    "سقوط",
    "استان",
    "سیستان و بلوچستان",
    "زاهدان",
    "چابهار",
    "ایرانشهر",
    "سراوان",
    "خاش",
    "کنارک",
    "نیکشهر",
    "راسک",
    "میرجاوه",
    "دشتیاری",
    "زابل",
    "زهک",
]


URGENT_WORDS = [
    "فوری",
    "خبر فوری",
    "لحظه‌ای",
    "لحظه ای",
    "آنی",
    "مهم",
    "اضطراری",
    "هشدار",
    "هشدار فوری",
    "اعلام شد",
    "تایید شد",
    "تأیید شد",
]


MAJOR_WORDS = [
    "حمله",
    "حمله موشکی",
    "حمله هوایی",
    "حمله پهپادی",
    "جنگ",
    "انفجار",
    "ترور",
    "موشک",
    "موشکی",
    "تنگه هرمز",
    "آژانس بین‌المللی انرژی اتمی",
    "شورای امنیت",
    "زلزله",
    "سقوط هواپیما",
]


REGIONAL_COMBOS = [
    ("ایران", "آمریکا"),
    ("ایران", "ترامپ"),
    ("ایران", "اسرائیل"),
    ("ایران", "حمله"),
    ("ایران", "جنگ"),
    ("ایران", "موشک"),
    ("ایران", "انفجار"),
    ("ایران", "ترور"),
    ("ایران", "تحریم"),
    ("ایران", "مذاکره"),
    ("ایران", "هسته‌ای"),
    ("ایران", "آژانس"),
    ("ایران", "شورای امنیت"),
    ("حزب‌الله", "لبنان"),
    ("حزب الله", "لبنان"),
    ("انصارالله", "یمن"),
    ("انصار الله", "یمن"),
    ("حوثی", "یمن"),
    ("حماس", "غزه"),
    ("فلسطین", "غزه"),
    ("تنگه", "هرمز"),
]


# مطالب تجمیعی / کم‌ارزش
ROUNDUP_WORDS = [
    "بسته خبری",
    "بسته اخبار",
    "بسته خبری صبحانه",
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
]


# ============================================================
# SCORING
# ============================================================

def contains(text, word):

    text = normalize_title(text)
    word = normalize_title(word)

    return (
        re.search(
            rf"(?<!\w){re.escape(word)}(?!\w)",
            text,
        )
        is not None
    )


def any_contains(text, words):
    return any(
        contains(text, word)
        for word in words
    )


def combo(text, first, second):
    return (
        contains(text, first)
        and contains(text, second)
    )


def is_roundup(title):

    return any_contains(
        title,
        ROUNDUP_WORDS,
    )


def score_article(article):

    title = normalize_text(
        article.title
    )

    description = normalize_text(
        article.description
    )

    full = title + " " + description

    score = 0
    major = False

    # موضوعات مهم در عنوان
    for word in DIRECT_TOPICS:

        if contains(title, word):
            score += 4

        elif contains(description, word):
            score += 1

    # فوریت
    for word in URGENT_WORDS:

        if contains(title, word):
            score += 5

    # خبر بزرگ
    for word in MAJOR_WORDS:

        if contains(title, word):
            score += 5
            major = True

    # ترکیب‌های مهم
    for first, second in REGIONAL_COMBOS:

        if combo(title, first, second):

            score += 8
            major = True

        elif combo(full, first, second):

            score += 3

    # سیستان و بلوچستان
    if (
        contains(full, "سیستان")
        and contains(full, "بلوچستان")
    ):
        score += 7

    province_words = [
        "زاهدان",
        "چابهار",
        "ایرانشهر",
        "سراوان",
        "خاش",
        "کنارک",
        "نیکشهر",
        "راسک",
        "میرجاوه",
        "دشتیاری",
        "زابل",
        "زهک",
    ]

    if any_contains(
        title,
        province_words,
    ):
        score += 8

    # زلزله بزرگ
    if contains(full, "زلزله"):

        match = re.search(
            r"(?:بزرگی|قدرت|بزرگای?)\s*"
            r"(?:حدود\s*)?"
            r"(\d+(?:[.,]\d+)?)",
            full,
        )

        if match:

            try:

                value = float(
                    match.group(1)
                    .replace(",", ".")
                )

                if value >= 6:
                    score += 12
                    major = True

                elif value >= 5:
                    score += 7

            except Exception:
                pass

    # اولویت منبع
    score += article.source.priority

    # ایران به تنهایی خبر محسوب نمی‌شود
    if (
        contains(title, "ایران")
        and not any_contains(
            full,
            DIRECT_TOPICS,
        )
    ):
        score -= 8

    article.score = score
    article.major = major

    return article


def accept_article(article):

    title = normalize_text(
        article.title
    )

    if age_hours(
        article.published
    ) > MAX_NEWS_AGE_HOURS:
        return False

    if len(title) < 15:
        return False

    if is_roundup(title):
        log.info(
            "SKIP ROUNDUP: %s",
            title,
        )
        return False

    if any_contains(
        title,
        REJECT_WORDS,
    ):
        return False

    # عنوان‌های خیلی تبلیغاتی
    if (
        title.count("!") >= 3
        or title.count("؟") >= 4
    ):
        return False

    return article.score >= 7


# ============================================================
# FEED PARSING
# ============================================================

def parse_feed(source, feed_url):

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

        # فقط چند خبر اول؛ سرعت بسیار بهتر می‌شود
        for entry in feed.entries[:12]:

            title = normalize_text(
                entry.get("title", "")
            )

            link = normalize_text(
                entry.get("link", "")
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

            published = entry_timestamp(
                entry
            )

            if (
                age_hours(published)
                > MAX_NEWS_AGE_HOURS
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

            score_article(article)

            if accept_article(article):
                articles.append(article)

    except Exception as e:

        log.warning(
            "FEED ERROR | %s | %s | %s",
            source.name,
            feed_url,
            e,
        )

    return articles


def collect_news(state):

    all_articles = []

    # هر منبع فقط یک RSS
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

        all_articles.extend(items)

    return all_articles


# ============================================================
# DEDUP
# ============================================================

def title_similarity(a, b):

    from difflib import SequenceMatcher

    return SequenceMatcher(
        None,
        normalize_title(a),
        normalize_title(b),
    ).ratio()


def same_event(a, b):

    similarity = title_similarity(
        a.title,
        b.title,
    )

    if similarity >= 0.78:
        return True

    words_a = set(
        normalize_title(
            a.title
        ).split()
    )

    words_b = set(
        normalize_title(
            b.title
        ).split()
    )

    if not words_a or not words_b:
        return False

    overlap = len(
        words_a & words_b
    ) / max(
        1,
        min(
            len(words_a),
            len(words_b),
        ),
    )

    return (
        similarity >= 0.58
        and overlap >= 0.70
    )


def deduplicate(articles, state):

    result = []

    articles = sorted(
        articles,
        key=lambda x: (
            x.major,
            x.score,
            x.source.priority,
            x.published,
        ),
        reverse=True,
    )

    for article in articles:

        if article.link in state.sent_links:
            continue

        if (
            normalize_title(article.title)
            in state.sent_titles
        ):
            continue

        duplicate = False

        for existing in result:

            if same_event(
                article,
                existing,
            ):
                duplicate = True
                break

        if not duplicate:
            result.append(article)

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

    # اگر منبع اخیراً استفاده شده،
    # امتیاز آن کم می‌شود.
    if source_was_recently_used(
        article,
        state,
    ):

        if article.major:
            return 5

        return 12

    return 0


def select_best_article(
    articles,
    state,
):

    articles = deduplicate(
        articles,
        state,
    )

    if not articles:
        return None

    now = time.time()

    normal_elapsed = (
        now - state.last_publish
    )

    # ابتدا امتیاز نهایی را با تنوع منبع محاسبه می‌کنیم
    ranked = []

    for article in articles:

        adjusted = (
            article.score
            - source_penalty(
                article,
                state,
            )
        )

        ranked.append(
            (
                adjusted,
                article,
            )
        )

    ranked.sort(
        key=lambda x: (
            x[1].major,
            x[0],
            x[1].published,
        ),
        reverse=True,
    )

    for adjusted, article in ranked:

        interval = (
            MAJOR_INTERVAL
            if article.major
            else NORMAL_INTERVAL
        )

        if (
            state.last_publish
            and normal_elapsed < interval
        ):
            continue

        # اگر منبع قبلی است، فقط وقتی منتشر شود
        # که واقعاً خبر مهم و امتیاز بالا داشته باشد.
        if source_was_recently_used(
            article,
            state,
        ):

            if not (
                article.major
                and article.score >= 18
            ):
                log.info(
                    "SOURCE COOLDOWN: %s | %s",
                    article.source.name,
                    article.title,
                )
                continue

        return article

    return None


# ============================================================
# ARTICLE DETAIL
# فقط برای خبر منتخب، نه همه خبرها
# ============================================================

def enrich_article(article):

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

        # متن
        paragraphs = []

        for p in soup.find_all("p"):

            text = normalize_text(
                p.get_text(" ")
            )

            if len(text) >= 35:
                paragraphs.append(text)

            if len(paragraphs) >= 8:
                break

        if paragraphs:

            article.description = " ".join(
                paragraphs
            )

        # تصویر با اولویت OG
        image_candidates = []

        for attr, value in [
            ("property", "og:image"),
            ("name", "twitter:image"),
        ]:

            tag = soup.find(
                "meta",
                attrs={attr: value},
            )

            if tag and tag.get("content"):

                image_candidates.append(
                    urljoin(
                        article.link,
                        tag["content"],
                    )
                )

        # تصاویر مقاله
        for img in soup.find_all(
            "img",
            src=True,
        )[:15]:

            image_candidates.append(
                urljoin(
                    article.link,
                    img["src"],
                )
            )

        # ابتدا تصویر فعلی RSS
        if article.image_url:
            image_candidates.insert(
                0,
                article.image_url,
            )

        for image_url in image_candidates:

            if image_url.startswith(
                ("http://", "https://")
            ):

                article.image_url = image_url
                break

    except Exception as e:

        log.warning(
            "ENRICH ERROR: %s",
            e,
        )

    return article


# ============================================================
# IMAGE QUALITY
# ============================================================

def download_good_image(url):

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
        ) as f:

            for chunk in response.iter_content(
                chunk_size=16384
            ):

                if not chunk:
                    continue

                total += len(chunk)

                if total > 8 * 1024 * 1024:
                    return ""

                f.write(chunk)

        try:

            with Image.open(
                IMAGE_FILE
            ) as image:

                width, height = image.size

                # عکس‌های خیلی کوچک رد شوند
                if width < 800 or height < 450:
                    log.info(
                        "LOW QUALITY IMAGE: %sx%s",
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

        return str(IMAGE_FILE)

    except Exception as e:

        log.warning(
            "IMAGE ERROR: %s",
            e,
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
    logo
):

    """
    رنگ اصلی لوگو را به آبی آسمانی روشن نزدیک می‌کند
    بدون از بین بردن شفافیت.
    """

    try:

        logo = logo.convert("RGBA")

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

                r, g, b, a = pixels[x, y]

                if a == 0:
                    continue

                # بخش‌های غیرشفاف لوگو
                # به آبی آسمانی منتقل می‌شوند.
                brightness = (
                    0.30 * r
                    + 0.59 * g
                    + 0.11 * b
                )

                factor = (
                    0.65
                    + 0.35
                    * (brightness / 255)
                )

                pixels[x, y] = (
                    int(target[0] * factor),
                    int(target[1] * factor),
                    int(target[2] * factor),
                    a,
                )

        return logo

    except Exception:
        return logo


def add_logo_to_image(
    image_path
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
        ).convert("RGBA")

        logo = Image.open(
            logo_path
        ).convert("RGBA")

        logo = tint_logo_to_sky_blue(
            logo
        )

        # حدود لوگو: حدود 18 درصد عرض تصویر
        target_width = max(
            100,
            int(
                base.width * 0.18
            ),
        )

        ratio = (
            target_width
            / logo.width
        )

        target_height = max(
            1,
            int(
                logo.height * ratio
            ),
        )

        logo = logo.resize(
            (
                target_width,
                target_height,
            ),
            Image.LANCZOS,
        )

        # کمی شفاف‌تر برای ظاهر حرفه‌ای
        alpha = logo.getchannel(
            "A"
        )

        alpha = alpha.point(
            lambda p: int(p * 0.82)
        )

        logo.putalpha(alpha)

        margin = max(
            18,
            int(
                base.width * 0.018
            ),
        )

        position = (
            margin,
            margin,
        )

        base.alpha_composite(
            logo,
            position,
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

    except Exception as e:

        log.warning(
            "LOGO ERROR: %s",
            e,
        )

        return image_path


# ============================================================
# SUMMARY
# ============================================================

def build_summary(article):

    text = normalize_text(
        article.description
    )

    if not text:
        return (
            "جزئیات بیشتر در منبع اصلی خبر."
        )

    # حذف برخی متن‌های تکراری
    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    sentences = re.split(
        r"(?<=[.!؟])\s+",
        text,
    )

    clean = []

    for sentence in sentences:

        sentence = normalize_text(
            sentence
        )

        if len(sentence) >= 25:
            clean.append(sentence)

        if len(clean) >= 4:
            break

    if clean:
        result = " ".join(clean)
    else:
        result = text

    return shorten_text(
        result,
        700,
    )


# ============================================================
# CAPTION
# ============================================================

def build_caption(article):

    title = escape_html(
        shorten_text(
            article.title,
            250,
        )
    )

    summary = escape_html(
        build_summary(article)
    )

    source = escape_html(
        article.source.name
    )

    caption = (
        f"<b>📰 {title}</b>\n\n"
        f"{summary}\n\n"
        f"🔗 منبع خبر: {source}\n\n"
        f"{SEPARATOR}\n"
        f"{SIGNATURE}"
    )

    if len(caption) <= 1024:
        return caption

    fixed = (
        f"<b>📰 {title}</b>\n\n"
        f"\n\n"
        f"🔗 منبع خبر: {source}\n\n"
        f"{SEPARATOR}\n"
        f"{SIGNATURE}"
    )

    available = max(
        150,
        1024 - len(fixed) - 10,
    )

    summary = escape_html(
        shorten_text(
            build_summary(article),
            available,
        )
    )

    return (
        f"<b>📰 {title}</b>\n\n"
        f"{summary}\n\n"
        f"🔗 منبع خبر: {source}\n\n"
        f"{SEPARATOR}\n"
        f"{SIGNATURE}"
    )


# ============================================================
# TELEGRAM
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

            if response.status_code == 429:

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

        except Exception as e:

            log.warning(
                "TELEGRAM ERROR %d: %s",
                attempt + 1,
                e,
            )

            time.sleep(
                2 ** attempt
            )

    return None


def reply_markup(article):

    return json.dumps(
        {
            "inline_keyboard": [
                [
                    {
                        "text": "مشاهده خبر",
                        "url": article.link,
                    }
                ]
            ]
        },
        ensure_ascii=False,
    )


# ============================================================
# SEND
# ============================================================

def send_message(article):

    text = (
        f"📰 {article.title}\n\n"
        f"{build_summary(article)}\n\n"
        f"🔗 منبع خبر: "
        f"{article.source.name}\n\n"
        f"{SEPARATOR}\n"
        f"{SIGNATURE}"
    )

    text = text[:4096]

    response = telegram_request(
        "sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": text,
            "reply_markup": reply_markup(
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


def send_photo(article):

    image_path = ""

    # تصویر فقط برای خبر منتخب دانلود می‌شود
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
                    "reply_markup": reply_markup(
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

                if result.get("ok"):
                    return True

                log.warning(
                    "sendPhoto failed: %s",
                    result,
                )

            except Exception:
                pass

    except Exception as e:

        log.warning(
            "SEND PHOTO ERROR: %s",
            e,
        )

    # اگر ارسال عکس شکست خورد، متن ارسال شود
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
        len(state.sent_links),
    )

    log.info(
        "Recent sources: %s",
        ", ".join(
            sorted(
                state.source_history
            )
        ) or "none",
    )

    articles = collect_news(
        state
    )

    log.info(
        "TOTAL CANDIDATES: %d",
        len(articles),
    )

    if not articles:

        log.info(
            "NO NEWS PUBLISHED"
        )

        return

    best = select_best_article(
        articles,
        state,
    )

    if not best:

        log.info(
            "NO SUITABLE NEWS"
        )

        return

    log.info(
        "SELECTED: %s | %s | score=%s | major=%s",
        best.source.name,
        best.title,
        best.score,
        best.major,
    )

    # فقط خبر انتخاب‌شده را از صفحه اصلی کامل می‌خوانیم
    best = enrich_article(
        best
    )

    success = send_photo(
        best
    )

    if success:

        state.mark_sent(
            best
        )

        log.info(
            "PUBLISHED SUCCESSFULLY"
        )

    else:

        log.error(
            "PUBLISH FAILED - STATE NOT UPDATED"
        )

    cleanup()


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        log.info(
            "STOPPED"
        )

    except Exception as e:

        log.exception(
            "FATAL ERROR: %s",
            e,
        )

        raise