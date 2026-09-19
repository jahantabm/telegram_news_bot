import os
import re
import html
import json
import xml.etree.ElementTree as ET
from io import BytesIO
from urllib.parse import quote_plus, urljoin

import requests
from PIL import Image, ImageDraw, ImageFont
from openai import OpenAI


BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL = os.environ["CHANNEL"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]


# موضوعات خبری موردنظر
RSS_QUERY = (
    '("ایران" OR "حشد الشعبی" OR "حزب الله" OR "حماس" OR '
    '"انصارالله" OR "حوثی" OR "غزه" OR "لبنان" OR "یمن") '
    '(جنگ OR حمله OR موشک OR پهپاد OR درگیری OR آتش‌بس OR مذاکره OR '
    'آمریکا OR اسرائیل OR عملیات OR حملات)'
)

RSS_URL = (
    "https://news.google.com/rss/search?q="
    + quote_plus(RSS_QUERY)
    + "&hl=fa&gl=IR&ceid=IR:fa"
)


LOGO_FILE = "jahantab_logo_transparent-1.png"
FALLBACK_FILE = "fallback_news.jpg"
SENT_FILE = "sent_links.txt"
CHANNEL_TEXT = "@jahantab_news"


client = OpenAI(api_key=OPENAI_API_KEY)


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 Chrome/120 Safari/537.36"
    )
}


def clean(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def load_sent():
    if not os.path.exists(SENT_FILE):
        return set()

    with open(SENT_FILE, encoding="utf-8") as f:
        return {x.strip() for x in f if x.strip()}


def save_sent(link):
    with open(SENT_FILE, "a", encoding="utf-8") as f:
        f.write(link + "\n")


def classify_news(title, description):
    text = (
        f"عنوان: {clean(title)}\n"
        f"توضیح: {clean(description)}"
    )

    instructions = """
تو یک سردبیر خبر فارسی هستی که فقط وظیفه‌ات تشخیص ارتباط و اهمیت خبر است.

موضوعات موردنظر:

- ایران و تحولات مستقیم جنگ یا درگیری ایران و آمریکا
- حملات، پاسخ‌های نظامی، موشکی و پهپادی مرتبط با ایران و منطقه
- حشد الشعبی عراق و تحولات امنیتی مهم مرتبط با آن
- حزب‌الله لبنان و تحولات مهم مرتبط با درگیری لبنان
- حماس و جنگ و تحولات مهم غزه و فلسطین
- انصارالله/حوثی‌ها و تحولات مهم یمن، دریای سرخ و باب‌المندب
- تحولات مهم دیپلماتیک، آتش‌بس یا مذاکرات مستقیم مرتبط با این پرونده‌ها

خبر فقط وقتی قابل انتشار است که:

1. به یکی از موضوعات بالا ارتباط مستقیم داشته باشد.
2. یک تحول خبری قابل‌توجه داشته باشد؛
   مثل حمله، پاسخ، درگیری مهم، تصمیم مهم دولتی یا نظامی،
   مذاکره مهم، آتش‌بس یا تحول امنیتی جدی.

خبرهای ورزشی، سرگرمی، اقتصادی عادی، اجتماعی عادی
و خبرهای عمومی ایران که ارتباط مستقیمی با موضوعات بالا ندارند
باید حذف شوند.

فقط یکی از این سه کلمه را برگردان:

PUBLISH
SKIP
URGENT

URGENT فقط وقتی است که خبر طبق متن ارائه‌شده
ماهیت فوری، در حال وقوع یا بسیار تازه داشته باشد.

هیچ توضیح دیگری ننویس.
"""

    try:
        response = client.responses.create(
            model="gpt-5.6-luna",
            instructions=instructions,
            input=text,
        )

        result = response.output_text.strip().upper()

        if result.startswith("URGENT"):
            return "URGENT"

        if result.startswith("PUBLISH"):
            return "PUBLISH"

    except Exception as e:
        print("Classifier error:", e)

    return "SKIP"


def make_summary(title, description):
    source = (
        f"عنوان خبر:\n{title}\n\n"
        f"متن خبر:\n{clean(description)}"
    )

    try:
        response = client.responses.create(
            model="gpt-5.6-luna",
            instructions=(
                "تو سردبیر خبری فارسی‌زبان هستی. "
                "خبر را در 2 تا 3 جمله کوتاه، دقیق و بی‌طرف خلاصه کن. "
                "هیچ اطلاعاتی خارج از متن اضافه نکن. "
                "فقط خلاصه را بنویس."
            ),
            input=source,
        )

        result = response.output_text.strip()

        if result:
            return result

    except Exception as e:
        print("Summary error:", e)

    return clean(description)[:500] or title


def find_rss_image_url(item):
    candidates = []

    for child in item:
        tag = child.tag.lower()

        if tag.endswith("content") or tag.endswith("thumbnail"):
            url = child.attrib.get("url")

            if url:
                candidates.append(url)

    enclosure = item.find("enclosure")

    if enclosure is not None:
        url = enclosure.attrib.get("url")

        if url:
            candidates.append(url)

    description = item.findtext("description") or ""

    match = re.search(
        r'<img[^>]+src=["\']([^"\']+)',
        description,
        re.IGNORECASE,
    )

    if match:
        candidates.append(
            html.unescape(match.group(1))
        )

    return candidates


def extract_meta_images(page_text, final_url):
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
                    html.unescape(match.group(1)),
                )
            )

    # JSON-LD
    for block in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        page_text,
        re.IGNORECASE | re.DOTALL,
    ):
        try:
            data = json.loads(
                html.unescape(block)
            )

            def collect_images(obj):
                found = []

                if isinstance(obj, dict):
                    value = obj.get("image")

                    if isinstance(value, str):
                        found.append(value)

                    elif isinstance(value, dict):
                        url = (
                            value.get("url")
                            or value.get("contentUrl")
                        )

                        if isinstance(url, str):
                            found.append(url)

                    elif isinstance(value, list):
                        for item in value:
                            if isinstance(item, str):
                                found.append(item)

                            elif isinstance(item, dict):
                                url = (
                                    item.get("url")
                                    or item.get("contentUrl")
                                )

                                if isinstance(url, str):
                                    found.append(url)

                    for value in obj.values():
                        found.extend(
                            collect_images(value)
                        )

                elif isinstance(obj, list):
                    for item in obj:
                        found.extend(
                            collect_images(item)
                        )

                return found

            for image_url in collect_images(data):
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
                html.unescape(match.group(1)),
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
            .get("content-type", "")
            .lower()
        )

        if (
            content_type
            and not content_type.startswith("image/")
        ):
            return None

        image = Image.open(
            BytesIO(response.content)
        ).convert("RGBA")

        if (
            image.width < minimum_width
            or image.height < minimum_height
        ):
            return None

        ratio = image.width / image.height

        if ratio < 0.35 or ratio > 3.2:
            return None

        return image

    except Exception as e:
        print("Image error:", e)

    return None


def find_best_article_image(link):
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
            "Article page error:",
            e,
        )

    return None


def prepare_image(item, link):
    # اول عکس اصلی منبع خبر
    image = find_best_article_image(link)

    if image is not None:
        return image

    # بعد عکس RSS / Google News
    for image_url in find_rss_image_url(item):
        image = download_image(
            image_url
        )

        if image is not None:
            print(
                "RSS image selected:",
                image_url,
            )

            return image

    # عکس پیش‌فرض اختصاصی
    if os.path.exists(FALLBACK_FILE):
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
                "Fallback image error:",
                e,
            )

    return create_fallback()


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
            max_logo_width /
            logo.width
        )

        logo = logo.resize(
            (
                int(logo.width * ratio),
                int(logo.height * ratio),
            ),
            Image.LANCZOS,
        )

        max_logo_height = (
            panel_height - margin * 2
        )

        if logo.height > max_logo_height:
            ratio = (
                max_logo_height /
                logo.height
            )

            logo = logo.resize(
                (
                    int(logo.width * ratio),
                    int(logo.height * ratio),
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
            int(image.width * 0.026),
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
            text_x + text_width + padding_x,
            text_y + text_height + padding_y,
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


def create_fallback():
    width = 1280
    height = 720

    image = Image.new(
        "RGBA",
        (
            width,
            height,
        ),
        (25, 31, 42, 255),
    )

    draw = ImageDraw.Draw(image)

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


def make_caption(
    title,
    summary,
    link,
    status,
):
    title = html.escape(title)
    summary = html.escape(summary)
    link = html.escape(
        link,
        quote=True,
    )

    prefix = (
        "🚨 <b>فوری</b>\n"
        if status == "URGENT"
        else ""
    )

    caption = (
        f"{prefix}"
        f"📰 <b>{title}</b>\n\n"
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
        f"📝 <b>خلاصه خبر</b>\n\n"
        f'🔗 <a href="{link}">'
        f"مشاهده خبر اصلی"
        f"</a>"
    )

    available = max(
        100,
        1024 - len(fixed) - 10,
    )

    summary = summary[:available].rstrip()

    return (
        f"{prefix}"
        f"📰 <b>{title}</b>\n\n"
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
):
    buffer = BytesIO()

    image.convert("RGB").save(
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


def main():
    print(
        "Starting Telegram News Bot..."
    )

    response = requests.get(
        RSS_URL,
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

    sent = load_sent()

    print(
        "RSS items:",
        len(items),
    )

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
            item.findtext("description")
            or ""
        )

        if not title or not link:
            continue

        if link in sent:
            continue

        print(
            "Checking:",
            title,
        )

        status = classify_news(
            title,
            description,
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
        )

        save_sent(link)

        print(
            "Published successfully."
        )

        break


if __name__ == "__main__":
    main()
