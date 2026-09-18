import os
import requests
import xml.etree.ElementTree as ET
import re
import html
from io import BytesIO
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
LOGO_FILE = "jahantab_logo_transparent.png"

client = OpenAI(api_key=OPENAI_API_KEY)


def load_sent_links():
    if not os.path.exists(SENT_FILE):
        return set()

    with open(SENT_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


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

    source_text = f"""
عنوان خبر:
{title}

توضیحات خبر:
{description}
"""

    response = client.responses.create(
        model="gpt-5.6-luna",
        instructions=(
            "تو یک سردبیر خبری فارسی‌زبان هستی. "
            "برای خبر زیر یک خلاصه کوتاه و دقیق به فارسی بنویس. "
            "خلاصه باید فقط 2 تا 3 جمله باشد. "
            "بی‌طرفانه بنویس و هیچ اطلاعاتی خارج از متن ورودی اضافه نکن. "
            "اگر اطلاعات کافی وجود ندارد، حدس نزن. "
            "فقط خود خلاصه را برگردان و هیچ عنوان یا توضیح اضافه ننویس."
        ),
        input=source_text,
    )

    return response.output_text.strip()


def find_image_url(item):
    # روش اول: media:content
    for child in item:
        tag = child.tag.lower()

        if tag.endswith("content") or tag.endswith("thumbnail"):
            url = child.attrib.get("url")
            if url:
                return url

    # روش دوم: enclosure
    enclosure = item.find("enclosure")
    if enclosure is not None:
        url = enclosure.attrib.get("url")
        if url:
            return url

    # روش سوم: عکس داخل description
    description = item.findtext("description") or ""

    match = re.search(
        r'<img[^>]+src=["\']([^"\']+)["\']',
        description,
        re.IGNORECASE
    )

    if match:
        return html.unescape(match.group(1))

    return None


def download_image(url):
    if not url:
        return None

    try:
        response = requests.get(
            url,
            timeout=20,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        response.raise_for_status()

        image = Image.open(BytesIO(response.content)).convert("RGBA")
        return image

    except Exception:
        return None


def add_branding(image):
    image = image.convert("RGBA")

    # اندازه لوگو
    logo = Image.open(LOGO_FILE).convert("RGBA")

    max_logo_width = int(image.width * 0.22)

    ratio = max_logo_width / logo.width
    logo = logo.resize(
        (
            int(logo.width * ratio),
            int(logo.height * ratio)
        ),
        Image.LANCZOS
    )

    # جای لوگو: پایین سمت راست
    margin = int(image.width * 0.035)

    x = image.width - logo.width - margin
    y = image.height - logo.height - margin

    image.alpha_composite(logo, (x, y))

    # آدرس کانال
    draw = ImageDraw.Draw(image)

    channel_text = "@jahantab_news"

    font_size = max(24, int(image.width * 0.025))

    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            font_size
        )
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), channel_text, font=font)

    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    text_x = margin
    text_y = image.height - text_height - margin

    # زمینه نیمه‌شفاف برای خوانایی
    padding = 10

    overlay = Image.new(
        "RGBA",
        (
            text_width + padding * 2,
            text_height + padding * 2
        ),
        (0, 0, 0, 150)
    )

    image.alpha_composite(
        overlay,
        (
            text_x - padding,
            text_y - padding
        )
    )

    draw = ImageDraw.Draw(image)

    draw.text(
        (text_x, text_y),
        channel_text,
        font=font,
        fill="white"
    )

    return image


def send_photo(image, title, summary, link):
    buffer = BytesIO()

    image.convert("RGB").save(
        buffer,
        format="JPEG",
        quality=92
    )

    buffer.seek(0)

    caption = (
        f"🚨 {title}\n\n"
        f"📝 خلاصه خبر:\n"
        f"{summary}\n\n"
        f'🔗 <a href="{link}">مشاهده خبر</a>\n\n'
        f"جهان تاب تحولات جهان\n"
        f"@jahantab_news"
    )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

    response = requests.post(
        url,
        data={
            "chat_id": CHANNEL,
            "caption": caption,
            "parse_mode": "HTML",
        },
        files={
            "photo": (
                "news.jpg",
                buffer,
                "image/jpeg"
            )
        },
        timeout=30,
    )

    response.raise_for_status()


def send_text(title, summary, link):
    caption = (
        f"🚨 {title}\n\n"
        f"📝 خلاصه خبر:\n"
        f"{summary}\n\n"
        f'🔗 <a href="{link}">مشاهده خبر</a>\n\n'
        f"جهان تاب تحولات جهان\n"
        f"@jahantab_news"
    )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": CHANNEL,
            "text": caption,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        timeout=20,
    )

    response.raise_for_status()


def main():
    response = requests.get(RSS_URL, timeout=20)
    response.raise_for_status()

    root = ET.fromstring(response.text)
    items = root.findall("./channel/item")

    sent_links = load_sent_links()

    for item in items:
        title = item.findtext("title")
        link = item.findtext("link")
        description = item.findtext("description")

        if not title or not link:
            continue

        if link in sent_links:
            continue

        summary = create_persian_summary(
            title,
            description
        )

        image_url = find_image_url(item)
        image = download_image(image_url)

        if image is not None:
            image = add_branding(image)
            send_photo(
                image,
                title,
                summary,
                link
            )
        else:
            send_text(
                title,
                summary,
                link
            )

        save_sent_link(link)

        break


if __name__ == "__main__":
    main()
