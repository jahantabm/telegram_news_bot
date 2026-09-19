import os
import re
import html
import json
import xml.etree.ElementTree as ET
from io import BytesIO
from datetime import datetime, timezone
from urllib.parse import quote_plus, urljoin

import requests
from PIL import Image, ImageDraw, ImageFont
from openai import OpenAI


BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL = os.environ["CHANNEL"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]


LOGO_FILE = "jahantab_logo_transparent-1.png"
FALLBACK_FILE = "fallback_news.jpg"
SENT_FILE = "sent_links.txt"
CHANNEL_TEXT = "@jahantab_news"


client = OpenAI(api_key=OPENAI_API_KEY)


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "Chrome/120 Safari/537.36"
    )
}


# ============================================================
# منابع مجاز
# ============================================================

SOURCES = {
    "Reuters": "reuters.com",
    "Sputnik": "sputniknews.com",
    "Associated Press": "apnews.com",
    "CNN": "cnn.com",
    "Fars": "farsnews.ir",
    "Mehr": "mehrnews.com",
    "IRNA": "irna.ir",
    "ISNA": "isna.ir",
    "Tasnim": "tasnimnews.com",
    "Khabar Online": "khabaronline.ir",
    "Khabar Foori": "khabarfarsi.com",
    "Al-Manar": "almanar.com.lb",
}


# نام‌هایی که ممکن است در RSS با شکل‌های مختلف بیایند
SOURCE_ALIASES = {
    "reuters": "Reuters",
    "رویترز": "Reuters",

    "sputnik": "Sputnik",
    "اسپوتنیک": "Sputnik",

    "associated press": "Associated Press",
    "ap": "Associated Press",
    "آسوشیتدپرس": "Associated Press",

    "cnn": "CNN",
    "سی ان ان": "CNN",

    "fars": "Fars",
    "fars news": "Fars",
    "فارس": "Fars",

    "mehr": "Mehr",
    "mehr news": "Mehr",
    "مهر": "Mehr",

    "irna": "IRNA",
    "irna news": "IRNA",
    "ایرنا": "IRNA",

    "isna": "ISNA",
    "ایسنا": "ISNA",

    "tasnim": "Tasnim",
    "tasnim news": "Tasnim",
    "تسنیم": "Tasnim",

    "khabar online": "Khabar Online",
    "خبرآنلاین": "Khabar Online",

    "khabar foori": "Khabar Foori",
    "خبر فوری": "Khabar Foori",

    "al-manar": "Al-Manar",
    "al manar": "Al-Manar",
    "المنار": "Al-Manar",
}


# ============================================================
# موضوعات
# ============================================================

RSS_TOPIC_QUERY = (
    '("ایران" OR "جنگ ایران" OR "آمریکا" OR '
    '"حشد الشعبی" OR "حزب الله" OR "حماس" OR '
    '"انصارالله" OR "حوثی" OR "غزه" OR "لبنان" OR "یمن") '
    '(جنگ OR حمله OR حملات OR موشک OR موشکی OR پهپاد OR '
    'درگیری OR آتش‌بس OR مذاکره OR عملیات OR اسرائیل OR آمریکا OR '
    'نیروهای آمریکایی OR پایگاه OR دریای سرخ OR باب‌المندب OR هرمز)'
)


def build_rss_url(domain):
    query = (
        f"site:{domain} "
        f"({RSS_TOPIC_QUERY})"
    )

    return (
        "https://news.google.com/rss/search?q="
        + quote_plus(query)
        + "&hl=fa&gl=IR&ceid=IR:fa"
    )


# ============================================================
# ابزارهای عمومی
# ============================================================

def clean(text):
    text = re.sub(
        r"<[^>]+>",
        " ",
        text or "",
    )

    text = html.unescape(text)

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def load_sent():
    if not os.path.exists(SENT_FILE):
        return set()

    with open(
        SENT_FILE,
        encoding="utf-8",
    ) as f:
        return {
            x.strip()
            for x in f
            if x.strip()
        }


def save_sent(link):
    with open(
        SENT_FILE,
        "a",
        encoding="utf-8",
    ) as f:
        f.write(link + "\n")


def normalize_source(source):
    source = clean(source).lower()

    for key, value in SOURCE_ALIASES.items():
        if key in source:
            return value

    return None


def get_source_name(item):
    source = item.find("source")

    if source is not None:
        name = (
            source.text
            or ""
        )

        normalized = normalize_source(name)

        if normalized:
            return normalized

    # اگر source وجود نداشت، از URL کمک می‌گیریم
    link = (
        item.findtext("link")
        or ""
    ).lower()

    for name, domain in SOURCES.items():
        if domain in link:
            return name

    return None


def get_pub_date(item):
    date_text = (
        item.findtext("pubDate")
        or ""
    ).strip()

    if not date_text:
        return datetime.min.replace(
            tzinfo=timezone.utc
        )

    try:
        from email.utils import parsedate_to_datetime

        value = parsedate_to_datetime(
            date_text
        )

        if value.tzinfo is None:
            value = value.replace(
                tzinfo=timezone.utc
            )

        return value

    except Exception:
        return datetime.min.replace(
            tzinfo=timezone.utc
        )


# ============================================================
# تشخیص اهمیت و ارتباط خبر
# ============================================================

def classify_news(
    title,
    description,
    source,
):
    text = (
        f"منبع: {source}\n"
        f"عنوان: {clean(title)}\n"
        f"توضیح: {clean(description)}"
    )

    instructions = """
تو سردبیر یک کانال خبری فارسی هستی.

فقط خبرهای مهم و مرتبط با این حوزه‌ها را انتخاب کن:

1. ایران و جنگ یا درگیری مستقیم ایران و آمریکا
2. حملات، پاسخ‌های نظامی، موشکی و پهپادی مرتبط با ایران
3. حشد الشعبی عراق و تحولات مهم امنیتی مرتبط با آن
4. حزب‌الله لبنان و تحولات مهم نظامی یا امنیتی لبنان
5. حماس، غزه و تحولات مهم جنگ و مذاکرات مرتبط با آن
6. انصارالله/حوثی‌های یمن
7. دریای سرخ، باب‌المندب و تحولات نظامی مرتبط
8. اسرائیل، فقط وقتی خبر مستقیماً به پرونده ایران،
   جنگ منطقه، غزه، لبنان یا گروه‌های ذکرشده مربوط باشد.
9. مذاکرات، آتش‌بس، تصمیم‌های مهم سیاسی یا نظامی
   که مستقیماً به این پرونده‌ها مربوط باشند.

خبرهای زیر را منتشر نکن:

- فوتبال و ورزش
- سینما و سرگرمی
- اقتصاد عادی
- قیمت‌ها و بازارهای عادی
- حوادث عادی
- اخبار اجتماعی عادی
- اخبار فناوری عادی
- اخبار ایران که ارتباطی با موضوعات بالا ندارند
- تحلیل‌های کم‌اهمیت
- خبرهای تکراری یا صرفاً حاشیه‌ای

فقط یکی از این سه عبارت را برگردان:

PUBLISH
URGENT
SKIP

URGENT یعنی خبر بسیار تازه و مهم است و
ماهیت فوری یا در حال وقوع دارد.

هیچ توضیح دیگری ننویس.
"""

    try:
        response = client.responses.create(
            model="gpt-5.6-luna",
            instructions=instructions,
            input=text,
        )

        result = (
            response.output_text
            .strip()
            .upper()
        )

        if result.startswith("URGENT"):
            return "URGENT"

        if result.startswith("PUBLISH"):
            return "PUBLISH"

    except Exception as e:
        print(
            "Classifier error:",
            e,
        )

    return "SKIP"


# ============================================================
# خلاصه خبر
# ============================================================

def make_summary(
    title,
    description,
):
    source = (
        f"عنوان خبر:\n"
        f"{title}\n\n"
        f"متن خبر:\n"
        f"{clean(description)}"
    )

    try:
        response = client.responses.create(
            model="gpt-5.6-luna",
            instructions=(
                "تو سردبیر خبری فارسی‌زبان هستی. "
                "خبر را در 2 تا 3 جمله کوتاه و دقیق خلاصه کن. "
                "بی‌طرف باش و هیچ اطلاعاتی خارج از متن اضافه نکن. "
                "فقط خلاصه را بنویس."
            ),
            input=source,
        )

        result = (
            response.output_text
            .strip()
        )

        if result:
            return result

    except Exception as e:
        print(
            "Summary error:",
            e,
        )

    return (
        clean(description)[:500]
        or title
    )


# ============================================================
# پیدا کردن عکس
# ============================================================

def find_rss_image_urls(item):
    candidates = []

    for child in item:
        tag = child.tag.lower()

        if (
            tag.endswith("content")
            or tag.endswith("thumbnail")
        ):
            url = child.attrib.get(
                "url"
            )

            if url:
                candidates.append(
                    url
                )

    enclosure = item.find(
        "enclosure"
    )

    if enclosure is not None:
        url = enclosure.attrib.get(
            "url"
        )

        if url:
            candidates.append(
                url
            )

    description = (
        item.findtext(
            "description"
        )
        or ""
    )

    match = re.search(
        r'<img[^>]+src=["\']([^"\']+)',
        description,
        re.IGNORECASE,
    )

    if match:
        candidates.append(
            html.unescape(
                match.group(1)
            )
        )

    return candidates


def extract_meta_images(
    page_text,
    final_url,
):
    candidates = []

    patterns = [
        r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)[^>]+property=["\']og:image(?::secure_url)?["\']',
        r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)[^>]+name=["\']twitter:image(?::src)?["\']',
    ]

    for pattern in patterns:
        for match in re.finditer(
            pattern,
            page_text,
            re.IGNORECASE,
        ):
            candidates.append(
                urljoin(
                    final_url,
                    html.unescape(
                        match.group(1)
                    ),
                )
            )

    # JSON-LD
    blocks = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        page_text,
        re.IGNORECASE | re.DOTALL,
    )

    for block in blocks:
        try:
            data = json.loads(
                html.unescape(block)
            )

            def collect_images(obj):
                found = []

                if isinstance(
                    obj,
                    dict,
                ):
                    image = obj.get(
                        "image"
                    )

                    if isinstance(
                        image,
                        str,
                    ):
                        found.append(
                            image
                        )

                    elif isinstance(
                        image,
                        dict,
                    ):
                        url = (
                            image.get("url")
                            or image.get(
                                "contentUrl"
                            )
                        )

                        if url:
                            found.append(
                                url
                            )

                    elif isinstance(
                        image,
                        list,
                    ):
                        for value in image:
                            if isinstance(
                                value,
                                str,
                            ):
                                found.append(
                                    value
                                )

                            elif isinstance(
                                value,
                                dict,
                            ):
                                url = (
                                    value.get(
                                        "url"
                                    )
                                    or value.get(
                                        "contentUrl"
                                    )
                                )

                                if url:
                                    found.append(
                                        url
                                    )

                    for value in obj.values():
                        found.extend(
                            collect_images(
                                value
                            )
                        )

                elif isinstance(
                    obj,
                    list,
                ):
                    for value in obj:
                        found.extend(
                            collect_images(
                                value
                            )
                        )

                return found

            for image_url in collect_images(
                data
            ):
                candidates.append(
                    urljoin(
                        final_url,
                        image_url,
                    )
                )

        except Exception:
            pass

    # تصاویر داخل صفحه
    for match in re.finditer(
        r'<img\b[^>]*(?:src|data-src|data-original)=["\']([^"\']+)',
        page_text,
        re.IGNORECASE,
    ):
        candidates.append(
            urljoin(
                final_url,
                html.unescape(
                    match.group(1)
                ),
            )
        )

    unique = []
    seen = set()

    for url in candidates:
        if url and url not in seen:
            seen.add(url)
            unique.append(url)

    return unique


def download_image(
    url,
    minimum_width=500,
    minimum_height=300,
):
    if not url:
        return None

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20,
        )

        response.raise_for_status()

        content_type = (
            response.headers
            .get(
                "content-type",
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
            return None

        image = Image.open(
            BytesIO(
                response.content
            )
        ).convert("RGBA")

        if (
            image.width < minimum_width
            or image.height < minimum_height
        ):
            return None

        ratio = (
            image.width /
            image.height
        )

        if (
            ratio < 0.35
            or ratio > 3.2
        ):
            return None

        return image

    except Exception as e:
        print(
            "Image error:",
            e,
        )

    return None


def find_article_image(link):
    try:
        response = requests.get(
            link,
            headers=HEADERS,
            timeout=25,
            allow_redirects=True,
        )

        response.raise_for_status()

        candidates = extract_meta_images(
            response.text,
            response.url,
        )

        for image_url in candidates:
            image = download_image(
                image_url
            )

            if image is not None:
                print(
                    "Article image selected:",
                    image_url,
                )

                return image

    except Exception as e:
        print(
            "Article image error:",
            e,
        )

    return None


def prepare_image(
    item,
    link,
):
    # 1. عکس اصلی خود منبع
    image = find_article_image(
        link
    )

    if image is not None:
        return image

    # 2. عکس RSS
    for image_url in find_rss_image_urls(
        item
    ):
        image = download_image(
            image_url
        )

        if image is not None:
            print(
                "RSS image selected:",
                image_url,
            )

            return image

    # 3. عکس پیش‌فرض خودمان
    if os.path.exists(
        FALLBACK_FILE
    ):
        try:
            image = Image.open(
                FALLBACK_FILE
            ).convert("RGBA")

            print(
                "Fallback image selected."
            )

            return image

        except Exception as e:
            print(
                "Fallback error:",
                e,
            )

    return create_fallback()


# ============================================================
# لوگو و ظاهر تصویر
# ============================================================

def load_logo():
    try:
        return Image.open(
            LOGO_FILE
        ).convert("RGBA")

    except Exception as e:
        print(
            "Logo error:",
            e,
        )

    return None


def get_font(size):
    try:
        return ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            size,
        )

    except Exception:
        return ImageFont.load_default()


def add_branding(image):
    image = image.convert("RGBA")

    draw = ImageDraw.Draw(
        image
    )

    logo = load_logo()

    margin = max(
        18,
        int(
            image.width * 0.025
        ),
    )

    panel_height = max(
        105,
        int(
            image.height * 0.16
        ),
    )

    panel = Image.new(
        "RGBA",
        (
            image.width,
            panel_height,
        ),
        (
            0,
            0,
            0,
            155,
        ),
    )

    image.alpha_composite(
        panel,
        (
            0,
            image.height
            - panel_height,
        ),
    )

    if logo:
        max_logo_width = int(
            image.width * 0.22
        )

        ratio = (
            max_logo_width /
            logo.width
        )

        logo = logo.resize(
            (
                int(
                    logo.width *
                    ratio
                ),
                int(
                    logo.height *
                    ratio
                ),
            ),
            Image.LANCZOS,
        )

        max_logo_height = (
            panel_height
            - margin * 2
        )

        if (
            logo.height
            > max_logo_height
        ):
            ratio = (
                max_logo_height /
                logo.height
            )

            logo = logo.resize(
                (
                    int(
                        logo.width *
                        ratio
                    ),
                    int(
                        logo.height *
                        ratio
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
                image.width
                * 0.026
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
            text_x
            - padding_x,
            text_y
            - padding_y,
            text_x
            + text_width
            + padding_x,
            text_y
            + text_height
            + padding_y,
        ),
        radius=14,
        fill=(
            0,
            0,
            0,
            175,
        ),
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


def create_fallback():
    width = 1280
    height = 720

    image = Image.new(
        "RGBA",
        (
            width,
            height,
        ),
        (
            25,
            31,
            42,
            255,
        ),
    )

    draw = ImageDraw.Draw(
        image
    )

    font = get_font(42)

    draw.text(
        (
            width // 2,
            height // 2,
        ),
        "جهان‌تاب",
        font=font,
        fill="white",
        anchor="mm",
    )

    return image


# ============================================================
# کپشن تلگرام
# ============================================================

def make_caption(
    title,
    summary,
    link,
    status,
    source,
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

    source = html.escape(
        source
    )

    prefix = ""

    if status == "URGENT":
        prefix = (
            "🚨 <b>خبر فوری</b>\n\n"
        )

    caption = (
        f"{prefix}"
        f"📰 <b>{title}</b>\n\n"
        f"📡 <b>منبع:</b> {source}\n\n"
        f"📝 <b>خلاصه خبر</b>\n"
        f"{summary}\n\n"
        f'🔗 <a href="{link}">'
        f"مشاهده خبر اصلی"
        f"</a>"
    )

    if len(caption) <= 1024:
        return caption

    fixed = (
        f"{prefix}"
        f"📰 <b>{title}</b>\n\n"
        f"📡 <b>منبع:</b> {source}\n\n"
        f"📝 <b>خلاصه خبر</b>\n\n"
        f'🔗 <a href="{link}">'
        f"مشاهده خبر اصلی"
        f"</a>"
    )

    available = max(
        100,
        1024
        - len(fixed)
        - 10,
    )

    summary = (
        summary[:available]
        .rstrip()
    )

    return (
        f"{prefix}"
        f"📰 <b>{title}</b>\n\n"
        f"📡 <b>منبع:</b> {source}\n\n"
        f"📝 <b>خلاصه خبر</b>\n"
        f"{summary}\n\n"
        f'🔗 <a href="{link}">'
        f"مشاهده خبر اصلی"
        f"</a>"
    )


def send_photo(
    image,
    title,
    summary,
    link,
    status,
    source,
):
    buffer = BytesIO()

    image.convert(
        "RGB"
    ).save(
        buffer,
        "JPEG",
        quality=92,
        optimize=True,
    )

    buffer.seek(0)

    response = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
        data={
            "chat_id": CHANNEL,
            "caption": make_caption(
                title,
                summary,
                link,
                status,
                source,
            ),
            "parse_mode": "HTML",
        },
        files={
            "photo": (
                "jahantab_news.jpg",
                buffer,
                "image/jpeg",
            ),
        },
        timeout=40,
    )

    print(
        "Telegram:",
        response.status_code,
        response.text[:300],
    )

    response.raise_for_status()


# ============================================================
# دریافت خبرها
# ============================================================

def fetch_source_items():
    all_items = []

    for source_name, domain in SOURCES.items():
        rss_url = build_rss_url(
            domain
        )

        print(
            "Fetching:",
            source_name,
        )

        try:
            response = requests.get(
                rss_url,
                headers=HEADERS,
                timeout=30,
            )

            response.raise_for_status()

            root = ET.fromstring(
                response.text
            )

            items = root.findall(
                "./channel/item"
            )

            for item in items:
                actual_source = get_source_name(
                    item
                )

                # فقط منبع‌های مجاز
                if not actual_source:
                    continue

                if actual_source != source_name:
                    continue

                all_items.append(
                    item
                )

        except Exception as e:
            print(
                "RSS error:",
                source_name,
                e,
            )

    # جدیدترین‌ها اول
    all_items.sort(
        key=get_pub_date,
        reverse=True,
    )

    return all_items


# ============================================================
# اجرای اصلی
# ============================================================

def main():
    print(
        "Starting Telegram News Bot..."
    )

    items = fetch_source_items()

    print(
        "Allowed-source items:",
        len(items),
    )

    sent = load_sent()

    for item in items:
        title = (
            item.findtext("title")
            or ""
        ).strip()

        link = (
            item.findtext("link")
            or ""
        ).strip()

        description = (
            item.findtext(
                "description"
            )
            or ""
        )

        source = get_source_name(
            item
        )

        if (
            not title
            or not link
            or not source
        ):
            continue

        if link in sent:
            continue

        print(
            "Checking:",
            source,
            "|",
            title,
        )

        status = classify_news(
            title,
            description,
            source,
        )

        print(
            "Classification:",
            status,
        )

        if status == "SKIP":
            continue

        summary = make_summary(
            title,
            description,
        )

        image = prepare_image(
            item,
            link,
        )

        image = add_branding(
            image
        )

        send_photo(
            image,
            title,
            summary,
            link,
            status,
            source,
        )

        save_sent(link)

        print(
            "Published successfully:",
            source,
            title,
        )

        break


if __name__ == "__main__":
    main()
