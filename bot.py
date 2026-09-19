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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
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


def relevant(title):
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
                timeout=(5, 12)
            )

            if r.status_code == 503:
                print("Google RSS 503 - retry...")
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
        print("XML ERROR:", str(e))
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
            node = item.find("source")
            if node is not None:
                source = clean(node.text)

        if not source:
            continue

        if not relevant(title):
            continue

        results.append({
            "title": title,
            "google_url": link,
            "desc": desc,
            "source": source
        })

    return results


def resolve_url(google_url):
    try:
        print("Resolving Google News link...")

        r = requests.get(
            google_url,
            headers=HEADERS,
            timeout=(5, 12),
            allow_redirects=True
        )

        final = r.url

        print("Resolved URL:", final)

        if "news.google.com" not in final:
            return final

    except Exception as e:
        print("URL RESOLVE ERROR:", str(e))

    return google_url


def get_article(url):
    try:
        r = requests.get(
            url,
            headers=HEADERS,
            timeout=(5, 10),
            allow_redirects=True
        )

        text = r.text

        title = None
        description = None
        image = None

        m = re.search(
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
            text,
            re.I
        )
        if m:
            title = clean(m.group(1))

        m = re.search(
            r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)',
            text,
            re.I
        )
        if m:
            description = clean(m.group(1))

        m = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
            text,
            re.I
        )
        if m:
            image = html.unescape(m.group(1))

        return {
            "url": r.url,
            "title": title,
            "description": description,
            "image": image
        }

    except Exception as e:
        print("ARTICLE ERROR:", str(e))
        return {
            "url": url,
            "title": None,
            "description": None,
            "image": None
        }


def make_image(image_url):
    try:
        if image_url:
            r = requests.get(
                image_url,
                headers=HEADERS,
                timeout=(5, 10)
            )

            img = Image.open(
                BytesIO(r.content)
            ).convert("RGB")
        else:
            raise ValueError("No image")

    except Exception:
        print("Using fallback image.")
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
        except Exception as e:
            print("Logo error:", str(e))

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


def make_persian_news(title, description, source):
    if not OPENAI_KEY:
        return title, description

    try:
        client = OpenAI(
            api_key=OPENAI_KEY,
            timeout=20
        )

        prompt = f"""
یک خبر را برای انتشار در کانال خبری فارسی آماده کن.

خروجی فقط شامل دو بخش باشد:

TITLE:
یک عنوان فارسی کوتاه و دقیق.

SUMMARY:
یک خلاصه فارسی 3 تا 4 جمله‌ای.

قوانین:
- کاملاً بی‌طرف و خبری باش.
- هیچ شعار، تبلیغ یا نظر شخصی اضافه نکن.
- اطلاعاتی که در متن نیست اختراع نکن.
- نام کشورها، سازمان‌ها و افراد را دقیق ترجمه کن.
- متن انگلیسی را تکرار نکن.

منبع: {source}

عنوان اصلی:
{title}

توضیحات خبر:
{description}
"""

        result = client.responses.create(
            model="gpt-5.6-luna",
            input=prompt
        )

        text = result.output_text.strip()

        m1 = re.search(
            r"TITLE:\s*(.*?)(?:\n|$)",
            text,
            re.I
        )

        m2 = re.search(
            r"SUMMARY:\s*(.*)",
            text,
            re.I | re.S
        )

        fa_title = m1.group(1).strip() if m1 else title
        summary = m2.group(1).strip() if m2 else text

        return fa_title, summary[:1800]

    except Exception as e:
        print("OPENAI ERROR:", str(e))

        return title, description[:900]


def send(photo, caption):
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
        print("BOT_TOKEN missing")
        return

    sent = get_sent()

    print("Already sent:", len(sent))

    news = []

    for query in QUERIES:
        data = fetch_rss(query)

        if data:
            news.extend(parse_rss(data))

        if len(news) >= 10:
            break

    unique = []
    seen = set()

    for item in news:
        if item["google_url"] in seen:
            continue

        if item["google_url"] in sent:
            continue

        seen.add(item["google_url"])
        unique.append(item)

    if not unique:
        print("No new relevant news.")
        return

    item = unique[0]

    google_url = item["google_url"]
    source = item["source"]

    print("Selected:", item["title"])
    print("Source:", source)

    real_url = resolve_url(google_url)

    article = get_article(real_url)

    final_url = article["url"]

    if "news.google.com" in final_url:
        print("Direct URL unavailable; keeping Google URL.")
        final_url = google_url

    original_title = (
        article["title"]
        or item["title"]
    )

    description = (
        article["description"]
        or item["desc"]
        or original_title
    )

    print("Final URL:", final_url)

    fa_title, summary = make_persian_news(
        original_title,
        description,
        source
    )

    print("Persian title:", fa_title)

    photo = make_image(
        article["image"]
    )

    caption = (
        f"📰 {fa_title}\n\n"
        f"{summary}\n\n"
        f"منبع: {source}\n"
        f"🔗 {final_url}"
    )

    send(photo, caption)

    save_sent(google_url)

    if final_url != google_url:
        save_sent(final_url)

    print("Sent successfully.")
    print("=" * 60)


if __name__ == "__main__":
    main()