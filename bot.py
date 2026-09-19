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

LOGO_FILE = "jahantab_logo_transparent-1.png"
SENT_FILE = "sent_links.txt"
CHANNEL_TEXT = "@jahantab_news"

client = OpenAI(api_key=OPENAI_API_KEY)

HEADERS = {
    "User-Agent": "Mozilla/5.0 Chrome/120 Safari/537.36"
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


def make_summary(title, description):
    source = (
        f"عنوان خبر:\n{title}\n\n"
        f"متن خبر:\n{clean(description)}"
    )

    try:
        r = client.responses.create(
            model="gpt-5.6-luna",
            instructions=(
                "تو سردبیر خبری فارسی‌زبان هستی. "
                "خبر را در 2 تا 3 جمله کوتاه و دقیق خلاصه کن. "
                "بی‌طرف باش و هیچ اطلاعاتی خارج از متن اضافه نکن. "
                "فقط خلاصه را بنویس."
            ),
            input=source,
        )

        result = r.output_text.strip()

        if result:
            return result

    except Exception as e:
        print("OpenAI error:", e)

    return clean(description)[:500] or title


def find_image_url(item):
    for child in item:
        tag = child.tag.lower()

        if tag.endswith("content") or tag.endswith("thumbnail"):
            url = child.attrib.get("url")

            if url:
                return url

    enclosure = item.find("enclosure")

    if enclosure is not None:
        url = enclosure.attrib.get("url")

        if url:
            return url

    description = item.findtext("description") or ""

    match = re.search(
        r'<img[^>]+src=["\']([^"\']+)',
        description,
        re.IGNORECASE,
    )

    if match:
        return html.unescape(match.group(1))

    return None


def find_article_image(link):
    try:
        r = requests.get(
            link,
            headers=HEADERS,
            timeout=20,
        )

        r.raise_for_status()

        patterns = [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
            r'<meta[^>]+content=["\']([^"\']+)[^>]+property=["\']og:image',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
        ]

        for pattern in patterns:
            match = re.search(
                pattern,
                r.text,
                re.IGNORECASE,
            )

            if match:
                return urljoin(
                    r.url,
                    html.unescape(match.group(1)),
                )

    except Exception as e:
        print("Article image error:", e)

    return None


def download_image(url):
    if not url:
        return None

    try:
        r = requests.get(
            url,
            headers=HEADERS,
            timeout=20,
        )

        r.raise_for_status()

        image = Image.open(
            BytesIO(r.content)
        ).convert("RGBA")

        if image.width < 250 or image.height < 150:
            return None

        return image

    except Exception as e:
        print("Image error:", e)

    return None


def load_logo():
    try:
        return Image.open(
            LOGO_FILE
        ).convert("RGBA")
    except Exception as e:
        print("Logo error:", e)
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

    # Bottom elegant dark gradient-like panel
    panel_height = max(
        105,
        int(image.height * 0.16),
    )

    panel = Image.new(
        "RGBA",
        (image.width, panel_height),
        (0, 0, 0, 155),
    )

    image.alpha_composite(
        panel,
        (0, image.height - panel_height),
    )

    # Logo
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
            (logo_x, logo_y),
        )

    # Channel address
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

    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    text_x = margin
    text_y = (
        image.height
        - panel_height
        + (
            panel_height
            - text_height
        ) // 2
    )

    # Small rounded background behind address
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
        (text_x, text_y),
        text,
        font=font,
        fill="white",
    )

    return image


def create_fallback(title):
    width = 1280
    height = 720

    image = Image.new(
        "RGBA",
        (width, height),
        (25, 31, 42, 255),
    )

    draw = ImageDraw.Draw(image)

    logo = load_logo()

    if logo:
        ratio = 350 / logo.width

        logo = logo.resize(
            (
                int(logo.width * ratio),
                int(logo.height * ratio),
            ),
            Image.LANCZOS,
        )

        image.alpha_composite(
            logo,
            (
                (width - logo.width) // 2,
                70,
            ),
        )

    font = get_font(42)

    draw.text(
        (width // 2, 360),
        title[:100],
        font=font,
        fill="white",
        anchor="mm",
    )

    draw.text(
        (width // 2, 640),
        CHANNEL_TEXT,
        font=font,
        fill="white",
        anchor="mm",
    )

    return image


def prepare_image(item, link, title):
    image = download_image(
        find_image_url(item)
    )

    if image is None:
        image = download_image(
            find_article_image(link)
        )

    if image is None:
        image = create_fallback(title)

    return add_branding(image)


def make_caption(title, summary, link):
    title = html.escape(title)
    summary = html.escape(summary)
    link = html.escape(
        link,
        quote=True,
    )

    caption = (
        f"🚨 <b>{title}</b>\n\n"
        f"📝 <b>خلاصه خبر</b>\n"
        f"{summary}\n\n"
        f'🔗 <a href="{link}">مشاهده خبر اصلی</a>'
    )

    if len(caption) <= 1024:
        return caption

    # Keep the caption inside Telegram's limit
    available = max(
        100,
        1024 - len(
            f"🚨 <b>{title}</b>\n\n"
            f"📝 <b>خلاصه خبر</b>\n\n"
            f'🔗 <a href="{link}">مشاهده خبر اصلی</a>'
        ) - 10,
    )

    summary = summary[:available].rstrip()

    return (
        f"🚨 <b>{title}</b>\n\n"
        f"📝 <b>خلاصه خبر</b>\n"
        f"{summary}\n\n"
        f'🔗 <a href="{link}">مشاهده خبر اصلی</a>'
    )


def send_photo(image, title, summary, link):
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
    print("Starting Telegram News Bot...")

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
            "New article:",
            title,
        )

        news_summary = make_summary(
            title,
            description,
        )

        image = prepare_image(
            item,
            link,
            title,
        )

        send_photo(
            image,
            title,
            news_summary,
            link,
        )

        save_sent(link)

        print(
            "Published successfully."
        )

        break


if __name__ == "__main__":
    main()
