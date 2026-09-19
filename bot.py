import os
import re
import html
import time
import requests
import xml.etree.ElementTree as ET
from io import BytesIO
from urllib.parse import quote_plus
from PIL import Image, ImageDraw
from openai import OpenAI

TOKEN = os.getenv("BOT_TOKEN")
CHANNEL = os.getenv("CHANNEL", "@jahantab_news")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

FALLBACK = "fallback_news.jpg"
LOGO = "jahantab_logo_transparent-1.png"
SENT_FILE = "sent_links.txt"

SOURCES = {
    "reuters.com": "Reuters",
    "apnews.com": "AP",
    "cnn.com": "CNN",
    "sputniknews.com": "Sputnik",
    "ir.sputniknews.com": "Sputnik",
    "farsnews.ir": "Fars",
    "mehrnews.com": "Mehr",
    "irna.ir": "IRNA",
    "isna.ir": "ISNA",
    "tasnimnews.com": "Tasnim",
    "khabaronline.ir": "Khabar Online",
    "khabarfouri.com": "Khabar فوری",
    "khabarfoori.com": "Khabar فوری",
    "almanar.com.lb": "Al-Manar",
    "aljazeera.net": "Al Jazeera",
    "hamshahrionline.ir": "Hamshahri"
}

QUERIES = [
    "Iran OR ایران",
    "Iraq OR Lebanon OR Hezbollah OR حشد",
    "Gaza OR Palestine OR Hamas OR اسرائیل",
    "Yemen OR Houthis OR Ansar Allah"
]

TOPICS = [
    "iran", "ایران", "iraq", "عراق", "hashd", "حشد",
    "hezbollah", "حزب الله", "lebanon", "لبنان",
    "palestine", "فلسطین", "gaza", "غزه", "hamas",
    "حماس", "yemen", "یمن", "houthis", "حوثی",
    "ansar allah", "israel", "اسرائیل", "tehran",
    "iran us", "us iran", "middle east"
]

BAD = [
    "football", "soccer", "sport", "sports",
    "basketball", "tennis", "celebrity",
    "entertainment", "movie", "music"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; JAHANTAB-News-Bot/1.0)"
}


def clean(text):
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def get_sent():
    if not os.path.exists(SENT_FILE):
        return set()

    with open(SENT_FILE, "r", encoding="utf-8") as f:
        return set(x.strip() for x in f if x.strip())


def save_sent(url):
    with open(SENT_FILE, "a", encoding="utf-8") as f:
        f.write(url + "\n")


def source_name(url):
    u = url.lower()

    for domain, name in SOURCES.items():
        if domain in u:
            return name

    return None


def is_relevant(title):
    t = title.lower()

    if any(x in t for x in BAD):
        return False

    return any(x in t for x in TOPICS)


def fetch_rss(query):
    url = (
        "https://news.google.com/rss/search?q="
        + quote_plus(query)
        + "&hl=en-US&gl=US&ceid=US:en"
    )

    for attempt in range(3):
        try:
            print("Fetching:", query)

            r = requests.get(
                url,
                headers=HEADERS,
                timeout=(5, 10)
            )

            if r.status_code == 503:
                print("Google RSS 503 - retrying...")
                time.sleep(3 + attempt * 2)
                continue

            r.raise_for_status()
            return r.text

        except Exception as e:
            print("RSS ERROR:", str(e))
            time.sleep(2 + attempt)

    return None


def parse_rss(data):
    if not data:
        return []

    try:
        root = ET.fromstring(data)
    except Exception as e:
        print("RSS PARSE ERROR:", str(e))
        return []

    results = []

    for item in root.findall(".//item"):
        title = clean(item.findtext("title"))
        link = clean(item.findtext("link"))
        desc = clean(item.findtext("description"))

        if not title or not link:
            continue

        source = source_name(link)

        if not source:
            src = item.find("source")
            if src is not None and src.text:
                source = clean(src.text)

        if not source:
            continue

        if not is_relevant(title):
            continue

        results.append({
            "title": title,
            "link": link,
            "desc": desc,
            "source": source
        })

    return results


def find_news(sent):
    all_news = []

    for query in QUERIES:
        data = fetch_rss(query)

        if data:
            all_news.extend(parse_rss(data))

        if len(all_news) >= 10:
            break

    unique = []
    seen = set()

    for item in all_news:
        link = item["link"]

        if link in seen or link in sent:
            continue

        seen.add(link)
        unique.append(item)

    return unique


def find_image(url):
    try:
        r = requests.get(
            url,
            headers=HEADERS,
            timeout=(4, 7)
        )

        m = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
            r.text,
            re.I
        )

        if m:
            return html.unescape(m.group(1))

    except Exception:
        pass

    return None


def make_image(image_url):
    try:
        if image_url:
            r = requests.get(
                image_url,
                headers=HEADERS,
                timeout=(4, 8)
            )

            img = Image.open(
                BytesIO(r.content)
            ).convert("RGB")
        else:
            raise ValueError("No image")

    except Exception:
        img = Image.open(FALLBACK).convert("RGB")

    img.thumbnail((1200, 1200))

    canvas = Image.new(
        "RGB",
        (1280, 1280),
        "white"
    )

    x = (1280 - img.width) // 2
    y = (1280 - img.height) // 2

    canvas.paste(img, (x, y))

    if os.path.exists(LOGO):
        try:
            logo = Image.open(LOGO).convert("RGBA")
            logo.thumbnail((280, 280))
            canvas.paste(
                logo,
                (30, 30),
                logo
            )
        except Exception:
            pass

    draw = ImageDraw.Draw(canvas)
    draw.text(
        (35, 1235),
        CHANNEL,
        fill="black"
    )

    out = BytesIO()
    canvas.save(
        out,
        format="JPEG",
        quality=88
    )

    out.seek(0)
    return out


def summarize(title, desc, source):
    if not OPENAI_KEY:
        return desc[:900]

    try:
        client = OpenAI(
            api_key=OPENAI_KEY,
            timeout=20
        )

        prompt = f"""
این خبر را به فارسی کوتاه و دقیق خلاصه کن.

قوانین:
- کاملاً بی‌طرف باش.
- فقط اطلاعات موجود در خبر را بیان کن.
- هیچ شعار، تبلیغ، تحلیل شخصی یا پیش‌بینی اضافه نکن.
- حداکثر 4 جمله.
- نام اشخاص، کشورها و سازمان‌ها را دقیق نگه دار.

منبع: {source}
عنوان: {title}
متن: {desc}
"""

        result = client.responses.create(
            model="gpt-5.6-luna",
            input=prompt
        )

        return result.output_text.strip()[:1800]

    except Exception as e:
        print("OPENAI ERROR:", str(e))
        return desc[:900]


def send_to_telegram(photo, caption):
    url = (
        f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    )

    r = requests.post(
        url,
        data={
            "chat_id": CHANNEL,
            "caption": caption[:1024]
        },
        files={
            "photo": (
                "news.jpg",
                photo,
                "image/jpeg"
            )
        },
        timeout=(5, 20)
    )

    r.raise_for_status()


def main():
    print("=" * 60)
    print("JAHANTAB TELEGRAM NEWS BOT")
    print("Starting...")
    print("=" * 60)

    if not TOKEN:
        print("ERROR: BOT_TOKEN missing")
        return

    sent = get_sent()

    print("Already sent:", len(sent))

    news = find_news(sent)

    if not news:
        print("No new relevant news.")
        return

    item = news[0]

    title = item["title"]
    link = item["link"]
    desc = item["desc"]
    source = item["source"]

    print("Selected:", title)
    print("Source:", source)

    image_url = find_image(link)

    if image_url:
        print("Article image found.")
    else:
        print("Using fallback image.")

    photo = make_image(image_url)

    summary = summarize(
        title,
        desc,
        source
    )

    caption = (
        f"📰 {title}\n\n"
        f"{summary}\n\n"
        f"منبع: {source}\n"
        f"🔗 {link}"
    )

    send_to_telegram(
        photo,
        caption
    )

    save_sent(link)

    print("Sent successfully.")
    print("=" * 60)


if __name__ == "__main__":
    main()