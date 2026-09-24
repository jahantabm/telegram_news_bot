# ============================================================
# JAHANTAB TELEGRAM NEWS BOT - STRICT FILTER V2.5
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
from difflib import SequenceMatcher
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup
from PIL import Image, UnidentifiedImageError
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ============================================================
# CONFIG
# ============================================================

VERSION = "JAHANTAB TELEGRAM NEWS BOT - STRICT FILTER V2.5"

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "@jahantab_news").strip()

BASE_DIR = Path(__file__).resolve().parent
STATE_DIR = BASE_DIR / "state"

SENT_LINKS_FILE = STATE_DIR / "sent_links.txt"
SENT_HASHES_FILE = STATE_DIR / "sent_hashes.txt"
SENT_TITLES_FILE = STATE_DIR / "sent_titles.txt"
LAST_PUBLISH_FILE = STATE_DIR / "last_publish.txt"

IMAGE_FILE = BASE_DIR / "news_original.jpg"
FINAL_IMAGE_FILE = BASE_DIR / "final_news.jpg"

MAX_NEWS_AGE_HOURS = 12

NORMAL_INTERVAL = 15 * 60
MAJOR_INTERVAL = 10 * 60

REQUEST_TIMEOUT = 20

USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 10) "
    "AppleWebKit/537.36 Chrome/130 Safari/537.36 "
    "JAHANTAB-NewsBot/2.5"
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

log = logging.getLogger("jahantab")


# ============================================================
# SOURCE
# ============================================================

@dataclass(frozen=True)
class Source:
    name: str
    domain: str
    homepage: str
    priority: int = 1


# ============================================================
# فقط منابع داخلی ایران
# ============================================================

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
    Source("عصر ایران", "asriran.com", "https://www.asriran.com/", 3),
    Source(
        "مشرق نیوز",
        "mashreghnews.ir",
        "https://www.mashreghnews.ir/",
        3,
    ),
    Source("انتخاب", "entekhab.ir", "https://www.entekhab.ir/", 3),
    Source("الف", "alef.ir", "https://www.alef.ir/", 3),
    Source("روز پلاس", "roozplus.com", "https://www.roozplus.com/", 3),
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
    total=3,
    connect=3,
    read=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET", "POST"],
)

adapter = HTTPAdapter(max_retries=retry)

session.mount("http://", adapter)
session.mount("https://", adapter)

session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.5",
})


# ============================================================
# TEXT HELPERS
# ============================================================

def normalize_text(text: str) -> str:
    text = html.unescape(text or "")

    replacements = {
        "\u200c": " ",
        "\u200f": " ",
        "\u202a": " ",
        "\u202b": " ",
        "\u202c": " ",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_title(text: str) -> str:
    text = normalize_text(text).lower()

    replacements = {
        "ي": "ی",
        "ك": "ک",
        "ۀ": "ه",
        "ة": "ه",
        "ؤ": "و",
        "إ": "ا",
        "أ": "ا",
        "ٱ": "ا",
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
        html.unescape(
            soup.get_text(" ")
        )
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

def ensure_state_dir():
    STATE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def read_lines(path: Path):
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

    except Exception as e:
        log.warning(
            "STATE READ ERROR %s: %s",
            path,
            e,
        )
        return set()


def write_lines(path: Path, values):
    ensure_state_dir()

    try:
        path.write_text(
            "\n".join(sorted(values))
            + ("\n" if values else ""),
            encoding="utf-8",
        )

    except Exception as e:
        log.error(
            "STATE WRITE ERROR %s: %s",
            path,
            e,
        )


def migrate_old_state():
    ensure_state_dir()

    migrations = [
        ("sent_links.txt", SENT_LINKS_FILE),
        ("sent_hashes.txt", SENT_HASHES_FILE),
        ("sent_titles.txt", SENT_TITLES_FILE),
        ("last_publish.txt", LAST_PUBLISH_FILE),
    ]

    for old_name, new_path in migrations:

        old_path = BASE_DIR / old_name

        if old_path.exists() and not new_path.exists():

            try:
                new_path.write_text(
                    old_path.read_text(
                        encoding="utf-8"
                    ),
                    encoding="utf-8",
                )

                log.info(
                    "Migrated old state: %s",
                    old_name,
                )

            except Exception as e:
                log.warning(
                    "Migration failed: %s",
                    e,
                )


class StateStore:

    def __init__(self):

        ensure_state_dir()
        migrate_old_state()

        self.sent_links = read_lines(
            SENT_LINKS_FILE
        )

        self.sent_hashes = read_lines(
            SENT_HASHES_FILE
        )

        self.sent_titles = read_lines(
            SENT_TITLES_FILE
        )

        self.last_publish = (
            self.read_last_publish()
        )

        log.info(
            "STATE | links=%d titles=%d hashes=%d",
            len(self.sent_links),
            len(self.sent_titles),
            len(self.sent_hashes),
        )

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

    def save(self):

        write_lines(
            SENT_LINKS_FILE,
            self.sent_links,
        )

        write_lines(
            SENT_HASHES_FILE,
            self.sent_hashes,
        )

        write_lines(
            SENT_TITLES_FILE,
            self.sent_titles,
        )

        LAST_PUBLISH_FILE.write_text(
            str(self.last_publish),
            encoding="utf-8",
        )

    def mark_sent(
        self,
        link,
        title,
    ):

        link = normalize_text(link)
        title = normalize_title(title)

        if link:
            self.sent_links.add(link)

        if title:
            self.sent_titles.add(title)

            self.sent_hashes.add(
                hashlib.sha256(
                    title.encode("utf-8")
                ).hexdigest()
            )

        self.last_publish = time.time()

        self.save()


# ============================================================
# SOURCE HELPERS
# ============================================================

def get_source_for_url(url):

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


def is_allowed_url(url):

    return (
        get_source_for_url(url)
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
    "/news/rss",
]


def discover_feeds(source):

    candidates = []

    try:

        response = session.get(
            source.homepage,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
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
                    )
                    .lower()
                )

                href = link.get("href")

                if (
                    "alternate" in rel
                    and (
                        "rss" in content_type
                        or "atom" in content_type
                        or "xml" in content_type
                    )
                ):

                    full_url = urljoin(
                        response.url,
                        href,
                    )

                    if is_allowed_url(
                        full_url
                    ):
                        candidates.append(
                            full_url
                        )

    except Exception as e:

        log.debug(
            "RSS discovery failed %s: %s",
            source.name,
            e,
        )

    for path in FEED_PATHS:

        candidates.append(
            urljoin(
                source.homepage,
                path,
            )
        )

    result = []
    seen = set()

    for url in candidates:

        if url in seen:
            continue

        seen.add(url)
        result.append(url)

    return result


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


# ============================================================
# DATE
# ============================================================

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
        (
            time.time() - timestamp
        ) / 3600,
    )


# ============================================================
# RSS IMAGE
# ============================================================

def extract_image_from_entry(entry):

    candidates = []

    for key in (
        "media_content",
        "media_thumbnail",
    ):

        items = entry.get(
            key,
            [],
        )

        if isinstance(items, dict):
            items = [items]

        for item in items:

            if isinstance(item, dict):

                url = (
                    item.get("url")
                    or item.get("href")
                )

                if url:
                    candidates.append(
                        url
                    )

    for enclosure in entry.get(
        "enclosures",
        [],
    ):

        if isinstance(enclosure, dict):

            url = (
                enclosure.get("href")
                or enclosure.get("url")
            )

            if url:
                candidates.append(
                    url
                )

    description = entry.get(
        "summary",
        "",
    )

    soup = BeautifulSoup(
        description,
        "html.parser",
    )

    image = soup.find("img")

    if image and image.get("src"):
        candidates.append(
            image.get("src")
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
# ARTICLE EXTRACTION
# ============================================================

def extract_article_data(article):

    try:

        response = session.get(
            article.link,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
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
                paragraph.get_text(" ")
            )

            if (
                len(text) >= 30
                and text not in paragraphs
            ):
                paragraphs.append(text)

            if len(paragraphs) >= 8:
                break

        if paragraphs:

            article.description = (
                " ".join(paragraphs)
            )

        if not article.image_url:

            meta_list = [
                (
                    "property",
                    "og:image",
                ),
                (
                    "name",
                    "twitter:image",
                ),
            ]

            for attribute, value in meta_list:

                tag = soup.find(
                    "meta",
                    attrs={
                        attribute: value
                    },
                )

                if tag and tag.get(
                    "content"
                ):

                    candidate = urljoin(
                        article.link,
                        tag["content"],
                    )

                    if candidate.startswith(
                        (
                            "http://",
                            "https://",
                        )
                    ):

                        article.image_url = (
                            candidate
                        )

                        break

        return article

    except Exception as e:

        log.debug(
            "ARTICLE EXTRACTION ERROR %s: %s",
            article.link,
            e,
        )

        return article


# ============================================================
# MATCHING
# ============================================================

def contains_word(
    text,
    word,
):

    text = normalize_title(text)
    word = normalize_title(word)

    if not word:
        return False

    return (
        re.search(
            rf"(?<!\w){re.escape(word)}(?!\w)",
            text,
        )
        is not None
    )


def any_word(text, words):

    return any(
        contains_word(text, word)
        for word in words
    )


def has_combo(
    text,
    first,
    second,
):

    return (
        contains_word(text, first)
        and contains_word(text, second)
    )


# ============================================================
# FILTER TERMS
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
    "تحریم‌های جدید",
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
    ("ایران", "موشکی"),
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
    ("خلیج فارس", "ایران"),
]


ACCIDENT_WORDS = [
    "سقوط",
    "واژگونی",
    "تصادف",
    "انفجار",
    "آتش‌سوزی",
    "آتش سوزی",
    "حادثه",
    "فوت",
    "کشته",
    "مصدوم",
]


# ============================================================
# SCORING
# ============================================================

def score_article(article):

    title = normalize_text(
        article.title
    )

    description = normalize_text(
        article.description
    )

    full_text = (
        title
        + " "
        + description
    )

    score = 0
    major = False

    for word in DIRECT_TOPICS:

        if contains_word(
            title,
            word,
        ):
            score += 4

        elif contains_word(
            description,
            word,
        ):
            score += 1

    for word in URGENT_WORDS:

        if contains_word(
            title,
            word,
        ):
            score += 5

    for word in MAJOR_WORDS:

        if contains_word(
            title,
            word,
        ):

            score += 5
            major = True

    for first, second in REGIONAL_COMBOS:

        if has_combo(
            title,
            first,
            second,
        ):

            score += 8
            major = True

        elif has_combo(
            full_text,
            first,
            second,
        ):

            score += 3

    if contains_word(
        full_text,
        "زلزله",
    ):

        magnitude = re.search(
            r"(?:بزرگی|قدرت|بزرگای?)\s*(?:حدود\s*)?"
            r"(\d+(?:[.,]\d+)?)",
            full_text,
        )

        if magnitude:

            try:

                value = float(
                    magnitude.group(1)
                    .replace(",", ".")
                )

                if value >= 6:
                    score += 12
                    major = True

                elif value >= 5:
                    score += 7

            except Exception:
                pass

    if any_word(
        title,
        ACCIDENT_WORDS,
    ):

        if any_word(
            title,
            [
                "کشته",
                "فوت",
                "جان باخت",
                "مصدوم",
            ],
        ):
            score += 6

    score += article.source.priority

    # «ایران» به تنهایی کافی نیست
    if (
        contains_word(
            title,
            "ایران",
        )
        and not any_word(
            full_text,
            DIRECT_TOPICS,
        )
    ):
        score -= 8

    article.score = score
    article.major = major

    return article


def accept_article(article):

    if (
        age_hours(article.published)
        > MAX_NEWS_AGE_HOURS
    ):
        return False

    title = normalize_text(
        article.title
    )

    if len(title) < 12:
        return False

    reject_words = [
        "فال",
        "هواشناسی روزانه",
        "قیمت روز",
        "جدول",
        "استخدام",
        "تبریک",
        "سرگرمی",
        "آشپزی",
        "فیلم سینمایی",
        "ورزش همگانی",
    ]

    if any_word(
        title,
        reject_words,
    ):
        return False

    return article.score >= 7


# ============================================================
# EVENT DEDUP
# ============================================================

STOP_WORDS = {
    "ایران",
    "ایرانی",
    "امروز",
    "خبر",
    "اعلام",
    "شد",
    "کرد",
    "کرده",
    "خواهد",
    "این",
    "آن",
    "برای",
    "با",
    "به",
    "از",
    "در",
    "که",
    "و",
    "یک",
    "را",
    "است",
    "شدند",
    "گفت",
    "گفته",
}


def title_tokens(title):

    words = normalize_title(
        title
    ).split()

    return {
        word
        for word in words
        if len(word) >= 3
        and word not in STOP_WORDS
    }


def same_event(
    first,
    second,
):

    title_a = normalize_title(
        first.title
    )

    title_b = normalize_title(
        second.title
    )

    if title_a == title_b:
        return True

    similarity = SequenceMatcher(
        None,
        title_a,
        title_b,
    ).ratio()

    tokens_a = title_tokens(
        first.title
    )

    tokens_b = title_tokens(
        second.title
    )

    if not tokens_a or not tokens_b:
        return False

    overlap = (
        len(tokens_a & tokens_b)
        / max(
            1,
            min(
                len(tokens_a),
                len(tokens_b),
            ),
        )
    )

    if similarity >= 0.78:
        return True

    if (
        similarity >= 0.58
        and overlap >= 0.70
    ):
        return True

    for first_term, second_term in REGIONAL_COMBOS:

        if (
            has_combo(
                title_a,
                first_term,
                second_term,
            )
            and has_combo(
                title_b,
                first_term,
                second_term,
            )
            and overlap >= 0.55
        ):
            return True

    return False


def deduplicate_articles(
    articles,
    state,
):

    selected = []

    articles = sorted(
        articles,
        key=lambda article: (
            article.score,
            article.source.priority,
            article.published,
        ),
        reverse=True,
    )

    for article in articles:

        if article.link in state.sent_links:
            continue

        title_normalized = normalize_title(
            article.title
        )

        if (
            title_normalized
            in state.sent_titles
        ):
            continue

        duplicate = False

        for existing in selected:

            if same_event(
                article,
                existing,
            ):

                duplicate = True
                break

        if duplicate:
            continue

        selected.append(
            article
        )

    return selected


# ============================================================
# FEED PARSER
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
            allow_redirects=True,
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

            if not is_allowed_url(
                link
            ):
                continue

            host = urlparse(
                link
            ).netloc.lower()

            if (
                "google." in host
                or "news.google." in host
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

            published = entry_timestamp(
                entry
            )

            if (
                age_hours(published)
                > MAX_NEWS_AGE_HOURS
            ):
                continue

            image_url = (
                extract_image_from_entry(
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

            article = extract_article_data(
                article
            )

            score_article(article)

            if accept_article(
                article
            ):
                articles.append(
                    article
                )

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

    for source in SOURCES:

        log.info(
            "FETCHING: %s",
            source.name,
        )

        feeds = discover_feeds(
            source
        )

        if not feeds:

            log.info(
                "NO RSS: %s",
                source.name,
            )

            continue

        source_count = 0

        for feed_url in feeds[:6]:

            items = parse_feed(
                source,
                feed_url,
            )

            all_articles.extend(
                items
            )

            source_count += len(items)

        log.info(
            "%s -> %d candidates",
            source.name,
            source_count,
        )

    return all_articles


# ============================================================
# IMAGE
# ============================================================

def download_image(url):

    if not url:
        return ""

    try:

        response = session.get(
            url,
            timeout=REQUEST_TIMEOUT,
            stream=True,
            allow_redirects=True,
        )

        if not response.ok:
            return ""

        content_type = (
            response.headers.get(
                "Content-Type",
                "",
            )
            .lower()
        )

        if (
            content_type
            and not content_type.startswith(
                "image/"
            )
        ):
            return ""

        total_size = 0

        with open(
            IMAGE_FILE,
            "wb",
        ) as image_file:

            for chunk in response.iter_content(
                chunk_size=8192
            ):

                if not chunk:
                    continue

                total_size += len(chunk)

                if total_size > 8 * 1024 * 1024:

                    try:
                        IMAGE_FILE.unlink()
                    except Exception:
                        pass

                    return ""

                image_file.write(chunk)

        try:

            with Image.open(
                IMAGE_FILE
            ) as image:

                image.verify()

        except (
            UnidentifiedImageError,
            OSError,
        ):

            try:
                IMAGE_FILE.unlink()
            except Exception:
                pass

            return ""

        return str(
            IMAGE_FILE
        )

    except Exception as e:

        log.debug(
            "IMAGE DOWNLOAD ERROR: %s",
            e,
        )

        try:

            if IMAGE_FILE.exists():
                IMAGE_FILE.unlink()

        except Exception:
            pass

        return ""


def prepare_final_image(
    image_path
):

    if not image_path:
        return ""

    try:

        with Image.open(
            image_path
        ) as image:

            image = image.convert(
                "RGB"
            )

            max_width = 1280

            if image.width > max_width:

                ratio = (
                    max_width
                    / image.width
                )

                image = image.resize(
                    (
                        max_width,
                        int(
                            image.height
                            * ratio
                        ),
                    ),
                    Image.LANCZOS,
                )

            image.save(
                FINAL_IMAGE_FILE,
                "JPEG",
                quality=88,
                optimize=True,
            )

        return str(
            FINAL_IMAGE_FILE
        )

    except Exception as e:

        log.warning(
            "IMAGE PREP ERROR: %s",
            e,
        )

        return ""


# ============================================================
# SUMMARY
# ============================================================

def build_summary(article):

    text = normalize_text(
        article.description
    )

    if not text:
        return "جزئیات بیشتر در منبع اصلی خبر."

    sentences = re.split(
        r"(?<=[.!؟])\s+",
        text,
    )

    sentences = [
        normalize_text(sentence)
        for sentence in sentences
        if len(
            normalize_text(sentence)
        ) >= 25
    ]

    if not sentences:

        return shorten_text(
            text,
            600,
        )

    return shorten_text(
        " ".join(
            sentences[:4]
        ),
        650,
    )


# ============================================================
# TELEGRAM CAPTION
# ============================================================

SIGNATURE = (
    "🌐 جهان تاب | آخرین تحولات جهان\n"
    "🌐 @jahantab_news"
)


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
        f"🔗 منبع: {source}\n\n"
        f"{SIGNATURE}"
    )

    if len(caption) <= 1024:
        return caption

    fixed_length = len(
        f"<b>📰 {title}</b>\n\n"
        f"\n\n🔗 منبع: {source}\n\n"
        f"{SIGNATURE}"
    )

    available = (
        1024
        - fixed_length
        - 10
    )

    available = max(
        100,
        available,
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
        f"🔗 منبع: {source}\n\n"
        f"{SIGNATURE}"
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

    for attempt in range(5):

        try:

            response = session.post(
                url,
                data=data,
                files=files,
                timeout=40,
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

                log.warning(
                    "Telegram flood wait: %ss",
                    retry_after,
                )

                time.sleep(
                    retry_after + 1
                )

                continue

            return response

        except Exception as e:

            log.warning(
                "Telegram request error "
                "attempt=%d: %s",
                attempt + 1,
                e,
            )

            time.sleep(
                2 ** attempt
            )

    return None


# ============================================================
# TELEGRAM KEYBOARD
# ============================================================

def build_reply_markup(
    article
):

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
# SEND PHOTO
# ============================================================

def send_photo(article):

    caption = build_caption(
        article
    )

    reply_markup = (
        build_reply_markup(
            article
        )
    )

    image_path = ""

    if article.image_url:

        image_path = download_image(
            article.image_url
        )

        if image_path:

            image_path = (
                prepare_final_image(
                    image_path
                )
            )

    if image_path:

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
                        "disable_web_page_preview": "true",
                        "reply_markup": reply_markup,
                    },
                    files={
                        "photo": photo,
                    },
                )

            if response is not None:

                try:
                    result = response.json()

                except Exception:
                    result = {}

                if result.get("ok"):

                    return True

                log.warning(
                    "sendPhoto failed: %s",
                    result,
                )

                # ارسال مجدد بدون HTML
                plain_summary = (
                    strip_html(
                        build_summary(
                            article
                        )
                    )
                )

                plain_caption = (
                    f"📰 {article.title}\n\n"
                    f"{plain_summary}\n\n"
                    f"🔗 منبع: "
                    f"{article.source.name}\n\n"
                    f"{SIGNATURE}"
                )

                with open(
                    image_path,
                    "rb",
                ) as photo:

                    response2 = (
                        telegram_request(
                            "sendPhoto",
                            data={
                                "chat_id": CHAT_ID,
                                "caption": plain_caption[:1024],
                                "reply_markup": reply_markup,
                            },
                            files={
                                "photo": photo,
                            },
                        )
                    )

                if response2 is not None:

                    try:

                        return bool(
                            response2.json().get(
                                "ok"
                            )
                        )

                    except Exception:
                        return False

        except Exception as e:

            log.warning(
                "SEND PHOTO ERROR: %s",
                e,
            )

    return send_message(
        article
    )


# ============================================================
# SEND MESSAGE WITHOUT PHOTO
# ============================================================

def send_message(article):

    summary = strip_html(
        build_summary(article)
    )

    text = (
        f"📰 {article.title}\n\n"
        f"{summary}\n\n"
        f"🔗 منبع: "
        f"{article.source.name}\n\n"
        f"{SIGNATURE}"
    )

    text = text[:4096]

    reply_markup = (
        build_reply_markup(
            article
        )
    )

    try:

        response = telegram_request(
            "sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": text,
                "disable_web_page_preview": "false",
                "reply_markup": reply_markup,
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

    except Exception as e:

        log.warning(
            "SEND MESSAGE ERROR: %s",
            e,
        )

        return False


# ============================================================
# PUBLISH INTERVAL
# ============================================================

def can_publish(
    state,
    major,
):

    if not state.last_publish:
        return True

    interval = (
        MAJOR_INTERVAL
        if major
        else NORMAL_INTERVAL
    )

    elapsed = (
        time.time()
        - state.last_publish
    )

    if elapsed < interval:

        remaining = int(
            interval - elapsed
        )

        log.info(
            "PUBLISH BLOCKED | "
            "remaining=%ss",
            remaining,
        )

        return False

    return True


# ============================================================
# SELECT BEST ARTICLE
# ============================================================

def select_best_article(
    articles,
    state,
):

    articles = (
        deduplicate_articles(
            articles,
            state,
        )
    )

    if not articles:
        return None

    articles.sort(
        key=lambda article: (
            article.major,
            article.score,
            article.source.priority,
            article.published,
        ),
        reverse=True,
    )

    for article in articles:

        if can_publish(
            state,
            article.major,
        ):
            return article

    return None


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

    ensure_state_dir()

    state = StateStore()

    log.info(
        "Already sent: %d",
        len(state.sent_links),
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

    success = send_photo(
        best
    )

    if success:

        state.mark_sent(
            best.link,
            best.title,
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
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        log.info(
            "STOPPED BY USER"
        )

    except Exception as e:

        log.exception(
            "FATAL ERROR: %s",
            e,
        )

        raise