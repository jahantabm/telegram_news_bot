# ============================================================
# JAHANTAB TELEGRAM NEWS BOT - STRICT FILTER V2.5
# منابع داخلی ایران - خبرهای مهم و فوری
# ============================================================

import os
import re
import html
import time
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
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

LOGO_FILE = BASE_DIR / "jahantab_logo_transparent-1.png"
FALLBACK_IMAGE = BASE_DIR / "fallback_news.jpg"

MAX_POSTS_PER_RUN = 1

# فاصله انتشار
NORMAL_INTERVAL = 15 * 60
MAJOR_INTERVAL = 10 * 60

# حداکثر سن خبر
MAX_NEWS_AGE_HOURS = 12

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
# SOURCE MODEL
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

    # خبرگزاری‌ها / رسانه‌های ملی و سراسری
    Source("ایرنا", "irna.ir", "https://www.irna.ir/", 5),
    Source("ایسنا", "isna.ir", "https://www.isna.ir/", 5),
    Source("فارس", "farsnews.ir", "https://www.farsnews.ir/", 5),
    Source("تسنیم", "tasnimnews.com", "https://www.tasnimnews.com/fa", 5),
    Source("مهر", "mehrnews.com", "https://www.mehrnews.com/", 5),
    Source("ایلنا", "ilna.ir", "https://www.ilna.ir/", 5),
    Source("صدا و سیما", "iribnews.ir", "https://www.iribnews.ir/", 5),
    Source("باشگاه خبرنگاران جوان", "yjc.ir", "https://www.yjc.ir/", 4),

    # رسانه‌های داخلی منتخب
    Source("تابناک", "tabnak.ir", "https://www.tabnak.ir/", 4),
    Source("فرارو", "fararu.com", "https://fararu.com/", 4),
    Source("همشهری آنلاین", "hamshahrionline.ir", "https://www.hamshahrionline.ir/", 4),
    Source("آخرین خبر", "akharinkhabar.ir", "https://akharinkhabar.ir/", 4),
    Source("خبر فوری", "khabarfoori.com", "https://www.khabarfoori.com/", 4),
    Source("خبرآنلاین", "khabaronline.ir", "https://www.khabaronline.ir/", 4),
    Source("عصر ایران", "asriran.com", "https://www.asriran.com/", 3),
    Source("مشرق نیوز", "mashreghnews.ir", "https://www.mashreghnews.ir/", 3),
    Source("انتخاب", "entekhab.ir", "https://www.entekhab.ir/", 3),
    Source("الف", "alef.ir", "https://www.alef.ir/", 3),
    Source("روز پلاس", "roozplus.com", "https://www.roozplus.com/", 3),
]


ALLOWED_DOMAINS = {s.domain.lower() for s in SOURCES}


# ============================================================
# SESSION
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
# STATE
# ============================================================

def ensure_state_dir():
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def normalize_text(text: str) -> str:
    text = html.unescape(text or "")
    text = text.replace("\u200c", " ")
    text = text.replace("\u200f", " ")
    text = text.replace("\u202a", " ")
    text = text.replace("\u202b", " ")
    text = text.replace("\u202c", " ")
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


def read_lines(path: Path):
    if not path.exists():
        return set()

    try:
        return {
            normalize_text(x)
            for x in path.read_text(encoding="utf-8").splitlines()
            if normalize_text(x)
        }
    except Exception as e:
        log.warning("STATE READ ERROR %s: %s", path, e)
        return set()


def write_lines(path: Path, values):
    ensure_state_dir()

    try:
        ordered = list(values)
        path.write_text(
            "\n".join(ordered) + ("\n" if ordered else ""),
            encoding="utf-8",
        )
    except Exception as e:
        log.error("STATE WRITE ERROR %s: %s", path, e)


def migrate_old_state():
    """
    برای سازگاری با نسخه‌های قدیمی.
    اگر فایل‌های قدیمی در ریشه پروژه وجود داشته باشند،
    اطلاعات آنها به state/ منتقل می‌شود.
    """

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
                    old_path.read_text(encoding="utf-8"),
                    encoding="utf-8",
                )

                log.info(
                    "Migrated old state: %s -> %s",
                    old_path.name,
                    new_path,
                )

            except Exception as e:
                log.warning("Migration failed %s: %s", old_path, e)


class StateStore:

    def __init__(self):
        ensure_state_dir()
        migrate_old_state()

        self.sent_links = read_lines(SENT_LINKS_FILE)
        self.sent_hashes = read_lines(SENT_HASHES_FILE)
        self.sent_titles = read_lines(SENT_TITLES_FILE)

        self.last_publish = self._read_last_publish()

        log.info(
            "STATE | links=%d titles=%d hashes=%d",
            len(self.sent_links),
            len(self.sent_titles),
            len(self.sent_hashes),
        )

    def _read_last_publish(self):
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
            sorted(self.sent_links),
        )

        write_lines(
            SENT_HASHES_FILE,
            sorted(self.sent_hashes),
        )

        write_lines(
            SENT_TITLES_FILE,
            sorted(self.sent_titles),
        )

        LAST_PUBLISH_FILE.write_text(
            str(self.last_publish),
            encoding="utf-8",
        )

    def mark_sent(self, link, title):
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

def get_source_for_url(url: str):
    try:
        host = urlparse(url).netloc.lower()
        host = host.split(":")[0]

        for source in SOURCES:
            if host == source.domain or host.endswith("." + source.domain):
                return source

    except Exception:
        pass

    return None


def is_allowed_url(url: str):
    return get_source_for_url(url) is not None


# ============================================================
# RSS DISCOVERY
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


def discover_feeds(source: Source):

    candidates = []

    try:
        r = session.get(
            source.homepage,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        if r.ok:
            soup = BeautifulSoup(
                r.text,
                "html.parser",
            )

            for link in soup.find_all(
                "link",
                href=True,
            ):

                rel = " ".join(
                    link.get("rel", [])
                ).lower()

                typ = (
                    link.get("type", "")
                    .lower()
                )

                href = link.get("href")

                if (
                    "alternate" in rel
                    and (
                        "rss" in typ
                        or "atom" in typ
                        or "xml" in typ
                    )
                ):
                    full = urljoin(
                        r.url,
                        href,
                    )

                    if is_allowed_url(full):
                        candidates.append(full)

    except Exception as e:
        log.debug(
            "RSS LINK DISCOVERY FAILED %s: %s",
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

    # حذف تکراری‌ها
    result = []

    seen = set()

    for url in candidates:

        if url in seen:
            continue

        seen.add(url)
        result.append(url)

    return result


# ============================================================
# ARTICLE MODEL
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
# TIME
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
# TEXT EXTRACTION
# ============================================================

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


def extract_image_from_entry(entry):

    candidates = []

    for key in (
        "media_content",
        "media_thumbnail",
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
                candidates.append(url)

    description = entry.get(
        "summary",
        "",
    )

    soup = BeautifulSoup(
        description,
        "html.parser",
    )

    img = soup.find("img")

    if img and img.get("src"):
        candidates.append(
            img.get("src")
        )

    for url in candidates:

        if url and url.startswith(("http://", "https://")):
            return url

    return ""


# ============================================================
# ARTICLE PAGE EXTRACTION
# ============================================================

def extract_article_data(article: Article):

    try:

        r = session.get(
            article.link,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        if not r.ok:
            return article

        soup = BeautifulSoup(
            r.text,
            "html.parser",
        )

        # ----------------------------------------------------
        # Description
        # ----------------------------------------------------

        paragraphs = []

        for p in soup.find_all("p"):

            txt = normalize_text(
                p.get_text(" ")
            )

            if (
                len(txt) >= 30
                and txt not in paragraphs
            ):
                paragraphs.append(txt)

            if len(paragraphs) >= 8:
                break

        if paragraphs:

            article.description = " ".join(
                paragraphs
            )

        # ----------------------------------------------------
        # Image
        # ----------------------------------------------------

        if not article.image_url:

            meta_candidates = [
                (
                    "property",
                    "og:image",
                ),
                (
                    "name",
                    "twitter:image",
                ),
            ]

            for attr, value in meta_candidates:

                tag = soup.find(
                    "meta",
                    attrs={
                        attr: value
                    },
                )

                if tag and tag.get("content"):

                    candidate = urljoin(
                        article.link,
                        tag["content"],
                    )

                    if candidate.startswith(
                        ("http://", "https://")
                    ):
                        article.image_url = candidate
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
# WORD MATCHING
# ============================================================

def contains_word(text: str, word: str):

    text = normalize_title(text)
    word = normalize_title(word)

    if not word:
        return False

    return re.search(
        rf"(?<!\w){re.escape(word)}(?!\w)",
        text,
    ) is not None


def any_word(text, words):

    return any(
        contains_word(text, word)
        for word in words
    )


def has_combo(text, a, b):

    return (
        contains_word(text, a)
        and contains_word(text, b)
    )


# ============================================================
# NEWS FILTER
# ============================================================

# موضوعات مهم داخلی / منطقه‌ای
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
    "تحریم‌های جدید",
    "تحریم جدید",

    "مذاکره",
    "مذاکرات",
    "مذاکرات ایران و آمریکا",

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


IRAN_COMBO_TERMS = [
    "ایران",
    "ایرانی",
    "تهران",
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


def score_article(article: Article):

    title = normalize_text(article.title)
    desc = normalize_text(article.description)

    full = f"{title} {desc}"

    score = 0
    major = False

    # --------------------------------------------------------
    # عنوان مهم‌تر از متن
    # --------------------------------------------------------

    for word in DIRECT_TOPICS:

        if contains_word(title, word):
            score += 4

        elif contains_word(desc, word):
            score += 1

    # --------------------------------------------------------
    # خبر فوری
    # --------------------------------------------------------

    for word in URGENT_WORDS:

        if contains_word(title, word):
            score += 5

    # --------------------------------------------------------
    # رویدادهای بسیار مهم
    # --------------------------------------------------------

    for word in MAJOR_WORDS:

        if contains_word(title, word):
            score += 5
            major = True

    # --------------------------------------------------------
    # ترکیب‌های مهم
    # --------------------------------------------------------

    for a, b in REGIONAL_COMBOS:

        if has_combo(title, a, b):

            score += 8
            major = True

        elif has_combo(full, a, b):

            score += 3

    # --------------------------------------------------------
    # زلزله
    # --------------------------------------------------------

    if contains_word(full, "زلزله"):

        magnitude = re.search(
            r"(?:بزرگی|قدرت|با بزرگای?)\s*(?:حدود\s*)?(\d+(?:[.,]\d+)?)",
            full,
        )

        if magnitude:

            try:
                mag = float(
                    magnitude.group(1)
                    .replace(",", ".")
                )

                if mag >= 6:
                    score += 12
                    major = True

                elif mag >= 5:
                    score += 7

            except Exception:
                pass

    # --------------------------------------------------------
    # حوادث سنگین
    # --------------------------------------------------------

    if any_word(title, ACCIDENT_WORDS):

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

    # --------------------------------------------------------
    # منبع معتبر
    # --------------------------------------------------------

    score += article.source.priority

    # --------------------------------------------------------
    # خبرهایی که فقط کلمه ایران دارند رد شوند
    # --------------------------------------------------------

    title_has_iran = any_word(
        title,
        IRAN_COMBO_TERMS,
    )

    has_specific_topic = any_word(
        full,
        DIRECT_TOPICS,
    )

    if title_has_iran and not has_specific_topic:

        score -= 8

    article.score = score
    article.major = major

    return article


def accept_article(article: Article):

    age = age_hours(
        article.published
    )

    if age > MAX_NEWS_AGE_HOURS:
        return False

    title = normalize_text(
        article.title
    )

    if len(title) < 12:
        return False

    # عنوان‌هایی که فقط جنبه عمومی/تبلیغاتی دارند
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

    if any_word(title, reject_words):
        return False

    # حداقل امتیاز
    if article.score < 7:
        return False

    return True


# ============================================================
# EVENT DEDUPLICATION
# ============================================================

STOP_WORDS = {
    "ایران",
    "ایرانی",
    "امروز",
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
        w
        for w in words
        if len(w) >= 3
        and w not in STOP_WORDS
    }


def same_event(a: Article, b: Article):

    ta = normalize_title(a.title)
    tb = normalize_title(b.title)

    if ta == tb:
        return True

    similarity = SequenceMatcher(
        None,
        ta,
        tb,
    ).ratio()

    tokens_a = title_tokens(a.title)
    tokens_b = title_tokens(b.title)

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

    # عنوان‌های بسیار مشابه
    if similarity >= 0.78:
        return True

    # برای عنوان‌های خبری نسبتاً مشابه
    if similarity >= 0.58 and overlap >= 0.70:
        return True

    # اگر ترکیب کلیدی یکسان داشته باشند
    for x, y in REGIONAL_COMBOS:

        if (
            has_combo(ta, x, y)
            and has_combo(tb, x, y)
            and overlap >= 0.55
        ):
            return True

    return False


def deduplicate_articles(
    articles,
    state: StateStore,
):

    result = []

    # ابتدا امتیاز بالاتر
    articles = sorted(
        articles,
        key=lambda x: (
            x.score,
            x.source.priority,
            x.published,
        ),
        reverse=True,
    )

    for article in articles:

        if article.link in state.sent_links:
            continue

        title_norm = normalize_title(
            article.title
        )

        if title_norm in state.sent_titles:
            continue

        duplicate = False

        for selected in result:

            if same_event(
                article,
                selected,
            ):
                duplicate = True
                break

        if duplicate:
            continue

        result.append(article)

    return result


# ============================================================
# RSS COLLECTION
# ============================================================

def parse_feed(
    source: Source,
    feed_url: str,
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

        parsed = feedparser.parse(
            response.content
        )

        for entry in parsed.entries[:30]:

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

            # فقط دامنه‌های مجاز
            if not is_allowed_url(link):
                continue

            # لینک گوگل یا واسطه‌ای رد شود
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

            # فقط اخبار جدید
            if age_hours(
                published
            ) > MAX_NEWS_AGE_HOURS:
                continue

            article = extract_article_data(
                article
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

        source_articles = []

        for feed_url in feeds[:6]:

            items = parse_feed(
                source,
                feed_url,
            )

            source_articles.extend(
                items
            )

        all_articles.extend(
            source_articles
        )

        log.info(
            "%s -> %d candidates",
            source.name,
            len(source_articles),
        )

    return all_articles


# ============================================================
# IMAGE DOWNLOAD
# ============================================================

def download_image(url: str):

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

        with open(
            IMAGE_FILE,
            "wb",
        ) as f:

            size = 0

            for chunk in response.iter_content(
                chunk_size=8192
            ):

                if not chunk:
                    continue

                size += len(chunk)

                # حداکثر 8MB
                if size > 8 * 1024 * 1024:
                    return ""

                f.write(chunk)

        # اعتبارسنجی واقعی تصویر
        try:

            with Image.open(
                IMAGE_FILE
            ) as img:

                img.verify()

        except (
            UnidentifiedImageError,
            OSError,
        ):

            try:
                IMAGE_FILE.unlink()
            except Exception:
                pass

            return ""

        return str(IMAGE_FILE)

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


# ============================================================
# IMAGE PROCESSING
# ============================================================

def prepare_final_image(image_path):

    if not image_path:
        return ""

    try:

        with Image.open(
            image_path
        ) as img:

            img = img.convert(
                "RGB"
            )

            max_width = 1280

            if img.width > max_width:

                ratio = (
                    max_width
                    / img.width
                )

                img = img.resize(
                    (
                        max_width,
                        int(
                            img.height
                            * ratio
                        ),
                    ),
                    Image.LANCZOS,
                )

            img.save(
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
# HTML HELPERS
# ============================================================

def escape_html(text):

    return html.escape(
        normalize_text(text),
        quote=False,
    )


def strip_html_for_telegram(text):

    soup = BeautifulSoup(
        text or "",
        "html.parser",
    )

    return normalize_text(
        html.unescape(
            soup.get_text(" ")
        )
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

    cut = text[:max_length]

    pos = cut.rfind(" ")

    if pos > max_length * 0.70:
        cut = cut[:pos]

    return cut.rstrip(
        " .،؛:!-"
    ) + "…"


# ============================================================
# AI-LIKE SUMMARY
# ============================================================

def build_summary(article: Article):

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
        normalize_text(x)
        for x in sentences
        if len(normalize_text(x)) >= 25
    ]

    if not sentences:
        return shorten_text(
            text,
            500,
        )

    selected = sentences[:4]

    summary = " ".join(
        selected
    )

    return shorten_text(
        summary,
        650,
    )


# ============================================================
# CAPTION
# ============================================================

SIGNATURE = (
    "🌐 جهان تاب | آخرین تحولات جهان\n"
    "🌐 @jahantab_news"
)


def build_caption(article: Article):

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

    # Telegram sendPhoto caption limit
    if len(caption) > 1024:

        allowed_summary = (
            1024
            - len(
                f"<b>📰 {title}</b>\n\n"
                f"\n\n🔗 منبع: {source}\n\n"
                f"{SIGNATURE}"
            )
            - 10
        )

        if allowed_summary < 100:
            allowed_summary = 100

        summary = escape_html(
            shorten_text(
                build_summary(article),
                allowed_summary,
            )
        )

        caption = (
            f"<b>📰 {title}</b>\n\n"
            f"{summary}\n\n"
            f"🔗 منبع: {source}\n\n"
            f"{SIGNATURE}"
        )

    return caption


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
                        .get("parameters", {})
                        .get("retry_after", 10)
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
                "Telegram request error attempt=%d: %s",
                attempt + 1,
                e,
            )

            time.sleep(
                2 ** attempt
            )

    return None


def send_photo(article: Article):

    caption = build_caption(
        article
    )

    image_path = ""

    if article.image_url:

        image_path = download_image(
            article.image_url
        )

        if image_path:

            image_path = prepare_final_image(
                image_path
            )

    # --------------------------------------------------------
    # عکس
    # --------------------------------------------------------

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
                        "reply_markup": (
                            '{"inline_keyboard":'
                            '[[{"text":"مشاهده خبر",'
                            f'"url":"{article.link}"}]]}'
                        ),
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

                # اگر مشکل HTML بود، دوباره بدون HTML
                description = (
                    strip_html_for_telegram(
                        build_summary(article)
                    )
                )

                plain_caption = (
                    f"📰 {article.title}\n\n"
                    f"{description}\n\n"
                    f"🔗 منبع: {article.source.name}\n\n"
                    f"{SIGNATURE}"
                )

                with open(
                    image_path,
                    "rb",
                ) as photo:

                    response2 = telegram_request(
                        "sendPhoto",
                        data={
                            "chat_id": CHAT_ID,
                            "caption": plain_caption[:1024],
                            "reply_markup": (
                                '{"inline_keyboard":'
                                '[[{"text":"مشاهده خبر",'
                                f'"url":"{article.link}"}]]}'
                            ),
                        },
                        files={
                            "photo": photo,
                        },
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

    # --------------------------------------------------------
    # بدون عکس
    # --------------------------------------------------------

    return send_message(
        article
    )


def send_message(article: Article):

    summary = strip_html_for_telegram(
        build_summary(article)
    )

    text = (
        f"📰 {article.title}\n\n"
        f"{summary}\n\n"
        f"🔗 منبع: {article.source.name}\n\n"
        f"{SIGNATURE}"
    )

    text = text[:4096]

    try:

        response = telegram_request(
            "sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": text,
                "disable_web_page_preview": "false",
                "reply_markup": (
                    '{"inline_keyboard":'
                    '[[{"text":"مشاهده خبر",'
                    f'"url":"{article.link}"}]]}'
                ),
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
    state: StateStore,
    major: bool,
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
            "PUBLISH BLOCKED | remaining=%ss",
            remaining,
        )

        return False

    return True


# ============================================================
# SELECT BEST NEWS
# ============================================================

def select_best_article(
    articles,
    state,
):

    articles = deduplicate_articles(
        articles,
        state,
    )

    if not articles:
        return None

    # مرتب‌سازی نهایی
    articles.sort(
        key=lambda x: (
            x.major,
            x.score,
            x.source.priority,
            x.published,
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
# CLEAN TEMP FILES
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