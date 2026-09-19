import os
import re
import html
import xml.etree.ElementTree as ET
from io import BytesIO
from urllib.parse import urljoin

import requests
from PIL import Image, ImageDraw, ImageFont
from openai import OpenAI


BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL = os.environ["CHANNEL"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

RSS_URL = (
    "https://news.google.com/rss/search?"
    "q=%D8%A7%DB%8C%D8%B1%D8%A7%D9%86+OR+%D8%B9%D8%B1%D8%A7%D9%82+OR+%D8%B3%D9%88%D8%B1%D9%8A%D9%87+"
    "OR+%D9%84%D8%A8%D9%86%D8%A7%D9%86+OR+%D8%BA%D8%B2%D9%87&hl=fa&gl=IR&ceid=IR:fa"
)

SENT_FILE = "sent_links.txt"
LOGO_FILE = "jahantab_logo_transparent-1.png"

CHANNEL_TEXT = "@jahantab_news"
BRAND_TEXT = "جهان تاب | تحولات جهان"

client = OpenAI(api_key=OPENAI_API_KEY)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120 Safari/537.36"
    )
}


def load_sent_links():
    if not os.path.exists(SENT_FILE):
        return set()

    with open(SENT_FILE, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def save_sent_link(link):
    with open(SENT_FILE, "a", encoding="utf-8") as f:
        f.write(link + "\n")


def clean_html(text):
    if not text:
        return ""

    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def create_persian_summary(title, description):
    description = clean_html(description)

    source_text = (
        f"عنوان خبر:\n{title}\n\n"
        f"متن/توضیحات:\n{description}"
    )

    try:
        response = client.responses.create(
            model="gpt-5.6-luna",
            instructions=(
                "تو یک سردبیر خبری فارسی‌زبان هستی. "
                "برای خبر زیر یک خلاصه کوتاه و دقیق به فارسی بنویس. "
                "خلاصه فقط 2 تا 3 جمله باشد. "
                "بی‌طرفانه بنویس و هیچ اطلاعاتی خارج از متن ورودی اضافه نکن. "
                "اگر اطلاعات کافی وجود ندارد، حدس نزن. "
                "فقط خود خلاصه را برگردان."
            ),
            input=source_text,
        )

        result = response.output_text.strip()

        if result:
            return result

    except Exception as e:
        print(f"OpenAI summary error: {e}")

    fallback = (
        description
        or title
        or "جزئیات بیشتری در منبع خبر ارائه شده است."
    )

    return fallback[:600]


def find_image_url(item):
    # media:content / media:thumbnail
    for child in item:
        tag = child.tag.lower()

        if tag.endswith("content") or tag.endswith("thumbnail"):
            url = child.attrib.get("url")

            if url and url.startswith(("http://", "https://")):
                return url

    # enclosure
    enclosure = item.find("enclosure")

    if enclosure is not None:
        url = enclosure.attrib.get("url")

        if url and url.startswith(("http://", "https://")):
            return url

    # image inside RSS description
    description = item.findtext("description") or ""

    match = re.search(
        r'<img[^>]+(?:src|data-src)=["\']([^"\']+)["\']',
        description,
        re.IGNORECASE,
    )

    if match:
        return html.unescape(match.group(1))

    return None


def find_image_from_article(url):
    if not url:
        return None

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20,
            allow_redirects=True,
        )

        response.raise_for_status()

        page = response.text

        patterns = [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
        ]

        for pattern in patterns:
            match = re.search(
                pattern,
                page,
                re.IGNORECASE,
            )

            if match:
                image_url = html.unescape(match.group(1))
                return urljoin(response.url, image_url)

    except Exception as e:
        print(f"Article image lookup error: {e}")

    return None


def download_image(url):
    if not url:
        return None

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=25,
            allow_redirects=True,
        )

        response.raise_for_status()

        image = Image.open(
            BytesIO(response.content)
        ).convert("RGBA")

        # Reject tiny images / tracking pixels
        if image.width < 250 or image.height < 150:
            return None

        return image

    except Exception as e:
        print(f"Image download error: {e}")
        return None


def load_logo():
    if not os.path.exists(LOGO_FILE):
        print(f"Logo file not found: {LOGO_FILE}")
        return None

    try:
        return Image.open(LOGO_FILE).convert("RGBA")

    except Exception as e:
        print(f"Logo error: {e}")
        return None


def get_font(size, bold=True):
    candidates = []

    if bold:
        candidates.extend([
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ])
    else:
        candidates.append(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        )

    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass

    return ImageFont.load_default()


def add_branding(image):
    image = image.convert("RGBA")

    logo = load_logo()

    # Transparent dark strip at bottom
    strip_h = max(
        90,
        int(image.height * 0.14)
    )

    overlay = Image.new(
        "RGBA",
        (image.width, strip_h),
        (0, 0, 0, 125),
    )

    image.alpha_composite(
        overlay,
        (0, image.height - strip_h),
    )

    margin = max(
        18,
        int(image.width * 0.025)
    )

    # Logo on bottom-right
    if logo:

        max_logo_width = int(
            image.width * 0.20
        )

        ratio = max_logo_width / logo.width

        logo = logo.resize(
            (
                max(
                    1,
                    int(logo.width * ratio)
                ),
                max(
                    1,
                    int(logo.height * ratio)
                ),
            ),
            Image.LANCZOS,
        )

        max_logo_height = (
            strip_h - margin * 2
        )

        if logo.height > max_logo_height:

            ratio = (
                max_logo_height /
                logo.height
            )

            logo = logo.resize(
                (
                    max(
                        1,
                        int(logo.width * ratio)
                    ),
                    max(
                        1,
                        int(logo.height * ratio)
                    ),
                ),
                Image.LANCZOS,
            )

        x = (
            image.width
            - logo.width
            - margin
        )

        y = (
            image.height
            - logo.height
            - margin
        )

        image.alpha_composite(
            logo,
            (x, y),
        )

    # Channel address bottom-left
    draw = ImageDraw.Draw(image)

    font_size = max(
        24,
        int(image.width * 0.025)
    )

    font = get_font(
        font_size,
        bold=True
    )

    channel_bbox = draw.textbbox(
        (0, 0),
        CHANNEL_TEXT,
        font=font,
    )

    channel_w = (
        channel_bbox[2]
        - channel_bbox[0]
    )

    channel_h = (
        channel_bbox[3]
        - channel_bbox[1]
    )

    channel_y = (
        image.height
        - channel_h
        - margin
    )

    padding_x = 12
    padding_y = 8

    bg_bbox = (
        margin - padding_x,
        channel_y - padding_y,
        margin + channel_w + padding_x,
        channel_y + channel_h + padding_y,
    )

    draw.rounded_rectangle(
        bg_bbox,
        radius=12,
        fill=(0, 0, 0, 150),
    )

    draw.text(
        (margin, channel_y),
        CHANNEL_TEXT,
        font=font,
        fill="white",
    )

    return image


def make_fallback_image(title):
    width = 1280
    height = 720

    image = Image.new(
        "RGBA",
        (width, height),
        (24, 31, 42, 255),
    )

    draw = ImageDraw.Draw(image)

    logo = load_logo()

    if logo:

        max_w = 360

        ratio = (
            max_w /
            logo.width
        )

        logo = logo
