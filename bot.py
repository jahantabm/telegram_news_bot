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


def sent_links():
    if not os.path.exists(SENT_FILE):
        return set()
    with open(SENT_FILE, encoding="utf-8") as f:
        return {x.strip() for x in f if x.strip()}


def save_link(link):
    with open(SENT_FILE, "a", encoding="utf-8") as f:
        f.write(link + "\n")


def summary(title, description):
    text = f"عنوان: {title}\nمتن: {clean(description)}"

    try:
        r = client.responses.create(
            model="gpt-5.6-luna",
            instructions=(
                "خبر را به فارسی خلاصه کن. "
                "فقط 2 تا 3 جمله کوتاه و دقیق بنویس. "
                "بی‌طرف باش و اطلاعات جدید اضافه نکن."
            ),
            input=text,
        )
        if r.output_text.strip():
            return r.output_text.strip()
    except Exception as e:
        print("OpenAI error:", e)

    return clean(description)[:500] or title


def image_url(item):
    for x in item:
        tag = x.tag.lower()
        if tag.endswith("content") or tag.endswith("thumbnail"):
            u = x.attrib.get("url")
            if u:
                return u

    enc = item.find("enclosure")
    if enc is not None and enc.attrib.get("url"):
        return enc.attrib["url"]

    d = item.findtext("description") or ""
    m = re.search(r'<img[^>]+src=["\']([^"\']+)', d, re.I)
    return html.unescape(m.group(1)) if m else None


def article_image(link):
    try:
        r = requests.get(link, headers=HEADERS, timeout=20)
        r.raise_for_status()

        patterns = [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
            r'<meta[^>]+content=["\']([^"\']+)[^>]+property=["\']og:image',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
        ]

        for p in patterns:
            m = re.search(p, r.text, re.I)
            if m:
                return urljoin(r.url, html.unescape(m.group(1)))
    except Exception as e:
        print("Article image error:", e)

    return None


def download(url):
    if not url:
        return None

    try:
        r = requests.get(
            url,
            headers=HEADERS,
            timeout=20
        )
        r.raise_for_status()

        im = Image.open(
            BytesIO(r.content)
        ).convert("RGBA")

        if im.width < 250 or im.height < 150:
            return None

        return im
    except Exception as e:
        print("Download image error:", e)
        return None


def logo():
    try:
        return Image.open(LOGO_FILE).convert("RGBA")
    except Exception:
        return None


def branding(im):
    im = im.convert("RGBA")
    draw = ImageDraw.Draw(im)
    L = logo()

    strip = max(90, int(im.height * 0.15))

    dark = Image.new(
        "RGBA",
        (im.width, strip),
        (0, 0, 0, 140)
    )

    im.alpha_composite(
        dark,
        (0, im.height - strip)
    )

    margin = max(18, int(im.width * 0.025))

    if L:
        max_w = int(im.width * 0.20)
        ratio = max_w / L.width
        L = L.resize(
            (int(L.width * ratio),
             int(L.height * ratio)),
            Image.LANCZOS
        )

        max_h = strip - margin * 2

        if L.height > max_h:
            ratio = max_h / L.height
            L = L.resize(
                (int(L.width * ratio),
                 int(L.height * ratio)),
                Image.LANCZOS
            )

        im.alpha_composite(
            L,
            (
                im.width - L.width - margin,
                im.height - L.height - margin
            )
        )

    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            max(24, int(im.width * 0.025))
        )
    except Exception:
        font = ImageFont.load_default()

    draw.text(
        (margin, im.height - strip + margin),
        CHANNEL_TEXT,
        font=font,
        fill="white"
    )

    return im


def fallback(title):
    im = Image.new(
        "RGBA",
        (1280, 720),
        (25, 30, 40, 255)
    )

    draw = ImageDraw.Draw(im)
    L = logo()

    if L:
        ratio = 350 / L.width
        L = L.resize(
            (int(L.width * ratio),
             int(L.height * ratio)),
            Image.LANCZOS
        )

        im.alpha_composite(
            L,
            ((1280 - L.width) // 2, 70)
        )

    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            42
        )
    except Exception:
        font = ImageFont.load_default()

    draw.text(
        (640, 360),
        title[:100],
        font=font,
        fill="white",
        anchor="mm"
    )

    draw.text(
        (640, 650),
        CHANNEL_TEXT,
        font=font,
        fill="white",
        anchor="mm"
    )

    return im


def make_image(item, link, title):
    im = download(image_url(item))

    if im is None:
        im = download(article_image(link))

    if im is None:
        im = fallback(title)

    return branding(im)


def caption(title, text, link):
    title = html.escape(title)
    text = html.escape(text)
    link = html.escape(link, quote=True)

    result = (
        f"🚨 <b>{title}</b>\n\n"
        f"📝 <b>خلاصه خبر:</b>\n"
        f"{text}\n\n"
        f'🔗 <a href="{link}">مشاهده خبر</a>'
    )

    return result[:1024]


def send(im, title, text, link):
    buf = BytesIO()
    im.convert("RGB").save(
        buf,
        "JPEG",
        quality=92
    )
    buf.seek(0)

    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
        data={
            "chat_id": CHANNEL,
            "caption": caption(title, text, link),
            "parse_mode": "HTML"
        },
        files={
            "photo": (
                "news.jpg",
                buf,
                "image/jpeg"
            )
        },
        timeout=40
    )

    print("Telegram:", r.status_code, r.text[:300])
    r.raise_for_status()


def main():
    print("Starting Telegram News Bot...")

    r = requests.get(
        RSS_URL,
        headers=HEADERS,
        timeout=30
    )
    r.raise_for_status()

    root = ET.fromstring(r.text)
    items = root.findall("./channel/item")

    old = sent_links()

    print("RSS items:", len(items))

    for item in items:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = item.findtext("description") or ""

        if not title or not link:
            continue

        if link in old:
            continue

        print("New article:", title)

        text = summary(
            title,
            description
        )

        im = make_image(
            item,
            link,
            title
        )

        send(
            im,
            title,
            text,
            link
        )

        save_link(link)

        print("Published successfully.")
        break


if __name__ == "__main__":
    main()
