import os
import re
import html
import xml.etree.ElementTree as ET
from io import BytesIO
from urllib.parse import urljoin, quote_plus
from datetime import datetime, timezone, timedelta

import requests
from PIL import Image, ImageDraw, ImageFont
from openai import OpenAI


# =========================================================
# SETTINGS
# =========================================================

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL = os.environ["CHANNEL"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

LOGO_FILE = "jahantab_logo_transparent-1.png"
FALLBACK_FILE = "fallback_news.jpg"
SENT_FILE = "sent_links.txt"

CHANNEL_TEXT = "@jahantab_news"

MAX_POSTS_PER_RUN = 1
MAX_AGE_HOURS = 48

RSS_TIMEOUT = 15
ARTICLE_TIMEOUT = 10
IMAGE_TIMEOUT = 10
TELEGRAM_TIMEOUT = 25
OPENAI_TIMEOUT = 25


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 Chrome/120 Safari/537.36"
    )
}


# =========================================================
# SOURCES
# =========================================================

SOURCE_DOMAINS = {
    "reuters.com",
    "apnews.com",
    "cnn.com",
    "sputniknews.com",
    "ir.sputniknews.com",

    "farsnews.ir",
    "mehrnews.com",
    "irna.ir",
    "isna.ir",
    "tasnimnews.com",

    "khabaronline.ir",
    "khabarfouri.com",
    "khabarfoori.com",

    "almanar.com.lb",

    # New sources
    "aljazeera.net",
    "hamshahrionline.ir",
}


SOURCE_NAMES = {
    "reuters",
    "reuters.com",
    "associated press",
    "ap",
    "ap news",
    "cnn",

    "sputnik",

    "فارس",
    "خبرگزاری فارس",

    "مهر",
    "خبرگزاری مهر",

    "ایرنا",
    "خبرگزاری جمهوری اسلامی",

    "ایسنا",
    "خبرگزاری ایسنا",

    "تسنیم",
    "خبرگزاری تسنیم",

    "خبرآنلاین",

    "خبر فوری",

    "المنار",
    "al-manar",

    # New sources
    "الجزیره",
    "الجزيره",
    "al jazeera",
    "aljazeera",

    "همشهری",
    "همشهری آنلاین",
    "hamshahri",
}


# =========================================================
# TOPIC FILTER
# =========================================================

TOPIC_KEYWORDS = [
    "ایران",
    "تهران",
    "iran",
    "tehran",

    "عراق",
    "حشد الشعبی",
    "حشد",
    "hashd",
    "iraq",
    "pmf",

    "لبنان",
    "حزب الله",
    "حزب‌الله",
    "hezbollah",
    "lebanon",

    "فلسطین",
    "غزه",
    "حماس",
    "hamas",
    "gaza",
    "palestine",

    "یمن",
    "انصارالله",
    "انصار الله",
    "حوثی",
    "حوثی‌ها",
    "حوثی ها",
    "houthis",
    "houthi",
    "ansarallah",
    "ansar allah",
    "yemen",

    "آمریکا",
    "امریکا",
    "ایالات متحده",
    "united states",
    "israel",
    "اسرائیل",
    "usa",
    "u.s.",
    "iran-us",
    "iran us",

    "سوریه",
    "syria",

    "تنگه هرمز",
    "hormuz",
]


URGENCY_KEYWORDS = [
    "فوری",
    "خبر فوری",
    "breaking",
    "urgent",

    "حمله",
    "حمله هوایی",
    "حمله موشکی",
    "موشک",
    "موشکی",
    "پهپاد",

    "انفجار",
    "انفجارها",

    "درگیری",
    "درگیری‌ها",
    "درگیری ها",

    "جنگ",

    "آتش بس",
    "آتش‌بس",

    "تلفات",
    "کشته",
    "کشته شد",
    "کشته شدند",
    "زخمی",
    "مجروح",

    "عملیات",
    "عملیات نظامی",

    "رهگیری",
    "پدافند",

    "موشک‌باران",
    "موشک باران",
    "بمباران",

    "حمله آمریکا",
    "حمله اسرائیل",
    "حمله ایران",

    "ترور",
    "هشدار",

    "مذاکرات",
    "توافق",

    "تحریم",
    "تحریم جدید",

    "رزمایش",
    "ناو",
    "ناو هواپیمابر",

    "مرز",
    "بسته شدن",
    "بستن",

    "تحولات",
]


# =========================================================
# OPENAI
# =========================================================

client = OpenAI(
    api_key=OPENAI_API_KEY,
    timeout=OPENAI_TIMEOUT,
)


# =========================================================
# TEXT HELPERS
# =========================================================

def clean(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def normalize(text):
    text = clean(text).lower()
    text = text.replace("ي", "ی")
    text = text.replace("ك", "ک")
    return text


# =========================================================
# SENT LINKS
# =========================================================

def load_sent():
    if not os.path.exists(SENT_FILE):
        return set()

    try:
        with open(SENT_FILE, "r", encoding="utf-8") as f:
            return {x.strip() for x in f if x.strip()}
    except Exception as e:
        print("Sent file error:", e)
        return set()


def save_sent(link):
    try:
        with open(SENT_FILE, "a", encoding="utf-8") as f:
            f.write(link.strip() + "\n")
    except Exception as e:
        print("Save sent error:", e)


# =========================================================
# DATE
# =========================================================

def parse_date(item):
    date_text = (
        item.findtext("pubDate")
        or item.findtext(
            "{http://purl.org/dc/elements/1.1/}date"
        )
        or ""
    )

    if not date_text:
        return datetime.now(timezone.utc)

    try:
        from email.utils import parsedate_to_datetime

        dt = parsedate_to_datetime(date_text)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except Exception:
        return datetime.now(timezone.utc)


# =========================================================
# SOURCE CHECK
# =========================================================

def source_info(item, link):
    source_name = clean(
        item.findtext("source") or ""
    )

    domain = ""

    match = re.search(
        r"https?://([^/]+)",
        link or "",
    )

    if match:
        domain = match.group(1).lower()

        if domain.startswith("www."):
            domain = domain[4:]

    return source_name, domain


def is_allowed_source(item, link):
    source_name, domain = source_info(
        item,
        link,
    )

    if domain in SOURCE_DOMAINS:
        return True

    source_lower = normalize(
        source_name
    )

    for name in SOURCE_NAMES:
        if normalize(name) in source_lower:
            return True

    return False


# =========================================================
# TOPIC FILTER
# =========================================================

def topic_score(text):
    t = normalize(text)

    return sum(
        1
        for keyword in TOPIC_KEYWORDS
        if normalize(keyword) in t
    )


def urgency_score(text):
    t = normalize(text)

    return sum(
        1
        for keyword in URGENCY_KEYWORDS
        if normalize(keyword) in t
    )


def is_relevant_news(title, description):
    text = f"{title} {description}"

    topics = topic_score(text)
    urgency = urgency_score(text)

    return topics >= 1 and urgency >= 1


# =========================================================
# RSS URL
# =========================================================

def build_rss_url():
    topics = (
        "ایران OR Iran OR "
        "عراق OR Iraq OR حشد OR Hashd OR "
        "لبنان OR Lebanon OR حزب الله OR Hezbollah OR "
        "فلسطین OR Palestine OR غزه OR Gaza OR حماس OR Hamas OR "
        "یمن OR Yemen OR انصارالله OR Houthis OR "
        "آمریکا OR USA OR Israel OR اسرائیل OR "
        "تنگه هرمز OR Hormuz"
    )

    sites = " OR ".join(
        f"site:{domain}"
        for domain in sorted(SOURCE_DOMAINS)
    )

    query = f"({topics}) ({sites})"

    return (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}"
        "&hl=fa"
        "&gl=IR"
        "&ceid=IR:fa"
    )


# =========================================================
# RSS
# =========================================================

def fetch_rss():
    url = build_rss_url()

    print("Fetching RSS...")

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=RSS_TIMEOUT,
    )

    response.raise_for_status()

    root = ET.fromstring(
        response.content
    )

    return root.findall(
        "./channel/item"
    )


# =========================================================
# IMAGE
# =========================================================

def find_image_url(item):
    for child in item:
        tag = child.tag.lower()

        if (
            tag.endswith("content")
            or tag.endswith("thumbnail")
        ):
            url = child.attrib.get("url")

            if url:
                return html.unescape(url)

    enclosure = item.find(
        "enclosure"
    )

    if enclosure is not None:
        url = enclosure.attrib.get(
            "url"
        )

        if url:
            return html.unescape(url)

    description = (
        item.findtext("description")
        or ""
    )

    match = re.search(
        r'<img[^>]+src=["\']([^"\']+)',
        description,
        re.IGNORECASE,
    )

    if match:
        return html.unescape(
            match.group(1)
        )

    return None


def find_article_image(link):
    if not link:
        return None

    try:
        response = requests.get(
            link,
            headers=HEADERS,
            timeout=ARTICLE_TIMEOUT,
        )

        response.raise_for_status()

        text = response.text

        patterns = [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
            r'<meta[^>]+content=["\']([^"\']+)[^>]+property=["\']og:image',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
            r'<meta[^>]+content=["\']([^"\']+)[^>]+name=["\']twitter:image',
        ]

        for pattern in patterns:
            match = re.search(
                pattern,
                text,
                re.IGNORECASE,
            )

            if match:
                return urljoin(
                    response.url,
                    html.unescape(
                        match.group(1)
                    ),
                )

    except Exception as e:
        print(
            "Article image error:",
            type(e).__name__,
        )

    return None


def download_image(url):
    if not url:
        return None

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=IMAGE_TIMEOUT,
        )

        response.raise_for_status()

        image = Image.open(
            BytesIO(response.content)
        ).convert("RGBA")

        if (
            image.width < 250
            or image.height < 150
        ):
            return None

        return image

    except Exception as e:
        print(
            "Image download error:",
            type(e).__name__,
        )

    return None


def load_logo():
    try:
        if not os.path.exists(
            LOGO_FILE
        ):
            return None

        return Image.open(
            LOGO_FILE
        ).convert("RGBA")

    except Exception as e:
        print(
            "Logo error:",
            e,
        )

    return None


def load_fallback():
    try:
        if not os.path.exists(
            FALLBACK_FILE
        ):
            print(
                "Fallback file not found."
            )
            return None

        return Image.open(
            FALLBACK_FILE
        ).convert("RGBA")

    except Exception as e:
        print(
            "Fallback error:",
            e,
        )

    return None


# =========================================================
# FONT
# =========================================================

def get_font(size):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ]

    for path in paths:
        try:
            return ImageFont.truetype(
                path,
                size,
            )
        except Exception:
            pass

    return ImageFont.load_default()


# =========================================================
# BRANDING
# =========================================================

def add_branding(image):
    image = image.convert("RGBA")

    draw = ImageDraw.Draw(image)

    logo = load_logo()

    margin = max(
        18,
        int(image.width * 0.025),
    )

    panel_height = max(
        105,
        int(image.height * 0.16),
    )

    panel = Image.new(
        "RGBA",
        (
            image.width,
            panel_height,
        ),
        (0, 0, 0, 155),
    )

    image.alpha_composite(
        panel,
        (
            0,
            image.height - panel_height,
        ),
    )

    if logo:
        max_logo_width = int(
            image.width * 0.22
        )

        ratio = (
            max_logo_width
            / logo.width
        )

        logo = logo.resize(
            (
                int(
                    logo.width * ratio
                ),
                int(
                    logo.height * ratio
                ),
            ),
            Image.LANCZOS,
        )

        max_logo_height = (
            panel_height
            - margin * 2
        )

        if logo.height > max_logo_height:
            ratio = (
                max_logo_height
                / logo.height
            )

            logo = logo.resize(
                (
                    int(
                        logo.width * ratio
                    ),
                    int(
                        logo.height * ratio
                    ),
                ),
                Image.LANCZOS,
            )

        logo_x = (
            image.width
            - logo.width
            - margin
        )

        logo_y = (
            image.height
            - logo.height
            - margin
        )

        image.alpha_composite(
            logo,
            (
                logo_x,
                logo_y,
            ),
        )

    font = get_font(
        max(
            24,
            int(
                image.width * 0.026
            ),
        )
    )

    text = CHANNEL_TEXT

    bbox = draw.textbbox(
        (0, 0),
        text,
        font=font,
    )

    text_width = (
        bbox[2] - bbox[0]
    )

    text_height = (
        bbox[3] - bbox[1]
    )

    text_x = margin

    text_y = (
        image.height
        - panel_height
        + (
            panel_height
            - text_height
        ) // 2
    )

    padding_x = 14
    padding_y = 9

    draw.rounded_rectangle(
        (
            text_x - padding_x,
            text_y - padding_y,
            text_x
            + text_width
            + padding_x,
            text_y
            + text_height
            + padding_y,
        ),
        radius=14,
        fill=(0, 0, 0, 175),
    )

    draw.text(
        (
            text_x,
            text_y,
        ),
        text,
        font=font,
        fill="white",
    )

    return image


def prepare_image(item, link):
    # 1. RSS image
    image = download_image(
        find_image_url(item)
    )

    if image is not None:
        print(
            "Using RSS image."
        )
        return add_branding(
            image
        )

    # 2. Article image
    article_image_url = (
        find_article_image(link)
    )

    image = download_image(
        article_image_url
    )

    if image is not None:
        print(
            "Using article image."
        )
        return add_branding(
            image
        )

    # 3. Fallback image
    image = load_fallback()

    if image is not None:
        print(
            "Using fallback image."
        )
        return add_branding(
            image
        )

    # 4. Last resort
    image = Image.new(
        "RGBA",
        (1280, 720),
        (30, 35, 45, 255),
    )

    return add_branding(
        image
    )


# =========================================================
# SUMMARY
# =========================================================

def make_summary(title, description):
    description = clean(
        description
    )

    if not description:
        description = title

    source = (
        f"عنوان خبر:\n"
        f"{title}\n\n"
        f"متن خبر:\n"
        f"{description[:6000]}"
    )

    try:
        print(
            "Calling OpenAI..."
        )

        response = client.responses.create(
            model="gpt-5.6-luna",
            instructions=(
                "تو یک سردبیر خبری فارسی‌زبان هستی. "
                "خبر را فقط بر اساس اطلاعات متن منبع "
                "در 2 تا 3 جمله کوتاه و دقیق خلاصه کن. "
                "بی‌طرف و factual باش. "
                "هیچ اطلاعات یا تحلیل خارج از متن اضافه نکن. "
                "از زبان تبلیغاتی یا احساسی استفاده نکن. "
                "فقط خلاصه فارسی را بنویس."
            ),
            input=source,
        )

        result = (
            response.output_text
            or ""
        ).strip()

        if result:
            return result

    except Exception as e:
        print(
            "OpenAI error:",
            type(e).__name__,
            str(e)[:200],
        )

    print(
        "Using source text as fallback."
    )

    return (
        description[:700]
        or title
    )


# =========================================================
# TELEGRAM
# =========================================================

def make_caption(
    title,
    summary,
    link,
):
    title = html.escape(
        title
    )

    summary = html.escape(
        summary
    )

    link = html.escape(
        link,
        quote=True,
    )

    caption = (
        f"<b>{title}</b>\n\n"
        f"📝 <b>خلاصه خبر</b>\n"
        f"{summary}\n\n"
        f'🔗 <a href="{link}">'
        f"خبر اصلی"
        f"</a>"
    )

    if len(caption) <= 1024:
        return caption

    fixed = (
        f"<b>{title}</b>\n\n"
        f"📝 <b>خلاصه خبر</b>\n\n"
        f'🔗 <a href="{link}">'
        f"خبر اصلی"
        f"</a>"
    )

    available = max(
        100,
        1024 - len(fixed) - 10,
    )

    summary = (
        summary[:available]
        .rstrip()
    )

    return (
        f"<b>{title}</b>\n\n"
        f"📝 <b>خلاصه خبر</b>\n"
        f"{summary}\n\n"
        f'🔗 <a href="{link}">'
        f"خبر اصلی"
        f"</a>"
    )


def send_photo(
    image,
    title,
    summary,
    link,
):
    buffer = BytesIO()

    image.convert(
        "RGB"
    ).save(
        buffer,
        "JPEG",
        quality=90,
        optimize=True,
    )

    buffer.seek(0)

    print(
        "Sending to Telegram..."
    )

    response = requests.post(
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendPhoto",
        data={
            "chat_id": CHANNEL,
            "caption": make_caption(
                title,
                summary,
                link,
            ),
            "parse_mode": "HTML",
        },
        files={
            "photo": (
                "jahantab_news.jpg",
                buffer,
                "image/jpeg",
            )
        },
        timeout=TELEGRAM_TIMEOUT,
    )

    print(
        "Telegram status:",
        response.status_code,
    )

    response.raise_for_status()


# =========================================================
# SELECT NEWS
# =========================================================

def select_news(
    items,
    sent,
):
    now = datetime.now(
        timezone.utc
    )

    candidates = []

    for item in items:
        title = clean(
            item.findtext(
                "title"
            )
            or ""
        )

        link = clean(
            item.findtext(
                "link"
            )
            or ""
        )

        description = clean(
            item.findtext(
                "description"
            )
            or ""
        )

        if not title or not link:
            continue

        if link in sent:
            continue

        if not is_allowed_source(
            item,
            link,
        ):
            continue

        pub_date = parse_date(
            item
        )

        age = now - pub_date

        if age > timedelta(
            hours=MAX_AGE_HOURS
        ):
            continue

        if age < timedelta(
            minutes=-10
        ):
            continue

        if not is_relevant_news(
            title,
            description,
        ):
            continue

        candidates.append(
            {
                "item": item,
                "title": title,
                "link": link,
                "description": description,
                "date": pub_date,
            }
        )

    candidates.sort(
        key=lambda x: x["date"],
        reverse=True,
    )

    return candidates


# =========================================================
# MAIN
# =========================================================

def main():
    print("=" * 60)
    print(
        "JAHANTAB TELEGRAM NEWS BOT"
    )
    print("Starting...")
    print("=" * 60)

    sent = load_sent()

    print(
        "Already sent:",
        len(sent),
    )

    try:
        items = fetch_rss()

    except Exception as e:
        print(
            "RSS ERROR:",
            type(e).__name__,
            str(e)[:300],
        )
        print(
            "Bot finished safely."
        )
        return

    print(
        "RSS items:",
        len(items),
    )

    candidates = select_news(
        items,
        sent,
    )

    print(
        "Matching new news:",
        len(candidates),
    )

    if not candidates:
        print(
            "No new relevant news found."
        )
        print(
            "Bot finished safely."
        )
        return

    selected = candidates[
        :MAX_POSTS_PER_RUN
    ]

    for news in selected:
        title = news["title"]
        link = news["link"]
        description = news[
            "description"
        ]

        source_name, domain = (
            source_info(
                news["item"],
                link,
            )
        )

        print("-" * 60)
        print(
            "Selected news:",
            title,
        )
        print(
            "Source:",
            source_name,
        )
        print(
            "Domain:",
            domain,
        )
        print(
            "Link:",
            link,
        )

        try:
            summary = make_summary(
                title,
                description,
            )

            image = prepare_image(
                news["item"],
                link,
            )

            send_photo(
                image,
                title,
                summary,
                link,
            )

            save_sent(link)

            print(
                "Published successfully."
            )

        except Exception as e:
            print(
                "PUBLISH ERROR:",
                type(e).__name__,
                str(e)[:300],
            )

    print("=" * 60)
    print(
        "BOT FINISHED"
    )
    print("=" * 60)


if __name__ == "__main__":
    main()