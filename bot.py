import os
import re
import time
import html
import requests
import feedparser
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from openai import OpenAI
from googlenewsdecoder import gnewsdecoder

# ============================================================
# JAHANTAB TELEGRAM NEWS BOT
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL = os.getenv("CHANNEL", "@jahantab_news")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

LOGO_FILE = "jahantab_logo_transparent-1.png"
FALLBACK_FILE = "fallback_news.jpg"
SENT_FILE = "sent_links.txt"

# ------------------------------------------------------------
# منابع مجاز
# ------------------------------------------------------------

SOURCES = {
    "reuters.com": "Reuters",
    "apnews.com": "Associated Press",
    "cnn.com": "CNN",
    "sputniknews.com": "Sputnik",
    "ir.sputniknews.com": "Sputnik",
    "farsnews.ir": "Fars News",
    "mehrnews.com": "Mehr News",
    "irna.ir": "IRNA",
    "isna.ir": "ISNA",
    "tasnimnews.com": "Tasnim",
    "khabaronline.ir": "Khabar Online",
    "khabarfouri.com": "Khabar فوری",
    "khabarfoori.com": "Khabar فوری",
    "almanar.com.lb": "Al-Manar",
    "aljazeera.net": "Al Jazeera",
    "hamshahrionline.ir": "Hamshahri",
}

# ------------------------------------------------------------
# موضوعات موردنظر
# ------------------------------------------------------------

QUERIES = [
    "Iran OR ایران",
    "Iran Iraq OR ایران عراق",
    "Iran Israel OR ایران اسرائیل",
    "Gaza Palestine Hamas OR غزه فلسطین حماس",
    "Hezbollah Lebanon OR حزب الله لبنان",
    "Yemen Houthis Ansar Allah OR یمن انصارالله",
    "Iran US OR ایران آمریکا",
    "Middle East war OR جنگ خاورمیانه",
]

KEYWORDS = [
    "iran", "iranian", "ایران", "ایرانی",
    "iraq", "iraqi", "عراق",
    "hashd", "pmu", "حشد",
    "lebanon", "lebanese", "لبنان",
    "hezbollah", "حزب الله",
    "palestine", "palestinian", "فلسطین",
    "gaza", "غزه",
    "hamas", "حماس",
    "yemen", "یمن",
    "houthi", "houthis", "حوثی",
    "ansar allah", "انصارالله",
    "israel", "israeli", "اسرائیل",
    "united states", "u.s.", "usa", "america",
    "آمریکا", "ایالات متحده",
    "war", "جنگ",
    "attack", "attacks", "حمله",
    "strike", "strikes", "حمله هوایی",
    "missile", "missiles", "موشک",
    "rocket", "راکت",
    "drone", "پهپاد",
    "explosion", "انفجار",
    "ceasefire", "آتش بس", "آتش‌بس",
    "negotiation", "مذاکرات",
    "nuclear", "هسته ای", "هسته‌ای",
    "sanctions", "تحریم",
    "killed", "کشته",
    "death", "مرگ",
    "military", "نظامی",
    "conflict", "درگیری",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/140 Safari/537.36"
)

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


# ============================================================
# ابزارها
# ============================================================

def clean_text(text):
    if not text:
        return ""

    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def domain_of(url):
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def allowed_source_from_domain(url):
    domain = domain_of(url)

    for allowed_domain, name in SOURCES.items():
        if domain == allowed_domain or domain.endswith("." + allowed_domain):
            return name

    return None


def allowed_source_from_rss(item):
    source = item.find("source")

    if source is None:
        return None

    source_name = clean_text(source.text)
    source_url = source.get("url", "")

    # اول از روی URL منبع تشخیص بده
    if source_url:
        detected = allowed_source_from_domain(source_url)

        if detected:
            return detected

    # بعد از روی نام دقیق منبع
    source_lower = source_name.lower()

    for allowed_domain, name in SOURCES.items():
        if source_lower == name.lower():
            return name

    return None


def is_relevant(title, description=""):
    text = f"{title} {description}".lower()

    for keyword in KEYWORDS:
        if keyword.lower() in text:
            return True

    return False


def urgency_score(title, description=""):
    text = f"{title} {description}".lower()

    urgent = [
        "breaking",
        "urgent",
        "war",
        "attack",
        "strike",
        "missile",
        "rocket",
        "drone",
        "explosion",
        "killed",
        "ceasefire",
        "nuclear",
        "military",
        "حمله",
        "جنگ",
        "موشک",
        "پهپاد",
        "انفجار",
        "کشته",
        "فوری",
        "مهم",
        "آتش‌بس",
        "آتش بس",
        "هسته‌ای",
        "هسته ای",
        "نظامی",
    ]

    return sum(1 for word in urgent if word.lower() in text)


# ============================================================
# خبرهای قبلی
# ============================================================

def load_sent():
    if not os.path.exists(SENT_FILE):
        return set()

    try:
        with open(SENT_FILE, "r", encoding="utf-8") as f:
            return {
                line.strip()
                for line in f
                if line.strip()
            }
    except Exception:
        return set()


def save_sent(sent):
    with open(SENT_FILE, "w", encoding="utf-8") as f:
        for url in sorted(sent):
            f.write(url + "\n")


# ============================================================
# Google News → لینک مستقیم
# ============================================================

def resolve_google_news(url):
    if "news.google.com" not in url:
        return url

    print("Resolving Google News link...")

    try:
        result = gnewsdecoder(url, interval=1)

        if isinstance(result, dict):
            if result.get("status") and result.get("decoded_url"):
                direct = result["decoded_url"]

                if "news.google.com" not in direct:
                    print("Direct URL found:")
                    print(direct)
                    return direct

    except Exception as e:
        print("Google News decoder error:", e)

    print("Could not decode Google News URL.")
    return None


# ============================================================
# دریافت اطلاعات خبر
# ============================================================

def get_article(url):
    try:
        response = session.get(
            url,
            timeout=15,
            allow_redirects=True,
        )

        if response.status_code >= 400:
            print("Article HTTP error:", response.status_code)
            return None

        final_url = response.url

        # اگر دوباره Google News بود، معتبر نیست
        if "news.google.com" in final_url:
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        def meta_content(property_name):
            tag = soup.find(
                "meta",
                attrs={"property": property_name}
            )

            if not tag:
                tag = soup.find(
                    "meta",
                    attrs={"name": property_name}
                )

            if tag:
                return clean_text(tag.get("content", ""))

            return ""

        title = (
            meta_content("og:title")
            or meta_content("twitter:title")
        )

        description = (
            meta_content("og:description")
            or meta_content("description")
            or meta_content("twitter:description")
        )

        image = (
            meta_content("og:image")
            or meta_content("twitter:image")
        )

        # اگر عنوان متا نبود
        if not title and soup.title:
            title = clean_text(soup.title.get_text())

        # استخراج مقداری از متن مقاله
        paragraphs = []

        for p in soup.find_all("p"):
            text = clean_text(p.get_text(" ", strip=True))

            if len(text) >= 40:
                paragraphs.append(text)

        article_text = " ".join(paragraphs)

        article_text = article_text[:7000]

        return {
            "url": final_url,
            "title": title,
            "description": description,
            "image": image,
            "text": article_text,
        }

    except Exception as e:
        print("Article extraction error:", e)
        return None


# ============================================================
# تصویر
# ============================================================

def download_image(url, filename="news_image.jpg"):
    if not url:
        return None

    try:
        response = session.get(
            url,
            timeout=15,
            stream=True,
        )

        if response.status_code != 200:
            return None

        content_type = response.headers.get(
            "content-type",
            ""
        ).lower()

        if "image" not in content_type:
            return None

        with open(filename, "wb") as f:
            for chunk in response.iter_content(8192):
                if chunk:
                    f.write(chunk)

        if os.path.getsize(filename) < 1000:
            return None

        return filename

    except Exception as e:
        print("Image download error:", e)
        return None


# ============================================================
# لوگو روی تصویر
# ============================================================

def add_logo(image_file):
    if not image_file:
        return None

    if not os.path.exists(LOGO_FILE):
        return image_file

    try:
        from PIL import Image

        base = Image.open(image_file).convert("RGBA")
        logo = Image.open(LOGO_FILE).convert("RGBA")

        # اندازه لوگو
        max_width = int(base.width * 0.20)

        if logo.width > max_width:
            ratio = max_width / logo.width
            logo = logo.resize(
                (
                    int(logo.width * ratio),
                    int(logo.height * ratio),
                ),
                Image.LANCZOS,
            )

        # فاصله از لبه
        margin = max(15, int(base.width * 0.025))

        x = base.width - logo.width - margin
        y = margin

        base.alpha_composite(logo, (x, y))

        output = "final_news_image.jpg"

        base.convert("RGB").save(
            output,
            "JPEG",
            quality=92,
        )

        return output

    except Exception as e:
        print("Logo error:", e)
        return image_file


# ============================================================
# ساخت متن فارسی با OpenAI
# ============================================================

def make_persian_news(
    original_title,
    description,
    article_text,
    source_name,
):
    if not OPENAI_API_KEY:
        print("OPENAI_API_KEY is missing.")
        return None

    client = OpenAI(
        api_key=OPENAI_API_KEY
    )

    context = (
        f"عنوان اصلی:\n{original_title}\n\n"
        f"توضیح:\n{description}\n\n"
        f"متن خبر:\n{article_text}\n"
    )

    prompt = f"""
تو یک سردبیر خبر فارسی هستی.

خبر زیر را به فارسی روان، کوتاه و کاملاً خبری بازنویسی کن.

منبع خبر: {source_name}

قوانین:
- عنوان را حتماً فارسی بنویس.
- خلاصه را در 3 تا 4 جمله فارسی بنویس.
- فقط اطلاعات موجود در متن را بیان کن.
- هیچ اطلاعاتی را حدس نزن.
- نظر شخصی، تبلیغات و تحلیل سیاسی اضافه نکن.
- اگر موضوع هنوز قطعی نیست، با عباراتی مثل «به گزارش...» یا
  «بر اساس گزارش...» بیان کن.
- متن باید مناسب انتشار در کانال خبری تلگرام باشد.

فقط با این قالب پاسخ بده:

TITLE:
عنوان فارسی

SUMMARY:
خلاصه فارسی 3 تا 4 جمله‌ای

خبر:
{context}
"""

    try:
        response = client.responses.create(
            model="gpt-5.6-luna",
            input=prompt,
            max_output_tokens=700,
        )

        output = response.output_text.strip()

        if not output:
            return None

        title_match = re.search(
            r"TITLE:\s*(.*?)(?:\n|$)",
            output,
            re.IGNORECASE,
        )

        summary_match = re.search(
            r"SUMMARY:\s*(.*)",
            output,
            re.IGNORECASE | re.DOTALL,
        )

        if not title_match or not summary_match:
            print("OpenAI output format invalid.")
            return None

        title = clean_text(title_match.group(1))
        summary = clean_text(summary_match.group(1))

        # حذف احتمالی بخش اضافه
        summary = re.split(
            r"\n(?:TITLE|SUMMARY|خبر):",
            summary,
            flags=re.IGNORECASE,
        )[0].strip()

        # حتماً فارسی باشد
        if not re.search(r"[\u0600-\u06FF]", title):
            print("Title is not Persian.")
            return None

        if not re.search(r"[\u0600-\u06FF]", summary):
            print("Summary is not Persian.")
            return None

        return {
            "title": title,
            "summary": summary,
        }

    except Exception as e:
        status = getattr(e, "status_code", None)

        if status == 429 or "429" in str(e):
            print("OPENAI 429: Daily/request limit reached.")
            print("News will NOT be published.")

        else:
            print("OPENAI ERROR:", e)

        return None


# ============================================================
# ارسال به تلگرام
# ============================================================

def send_photo(photo, caption):
    url = (
        f"https://api.telegram.org/bot"
        f"{BOT_TOKEN}/sendPhoto"
    )

    try:
        with open(photo, "rb") as f:
            response = requests.post(
                url,
                data={
                    "chat_id": CHANNEL,
                    "caption": caption,
                },
                files={
                    "photo": f,
                },
                timeout=30,
            )

        data = response.json()

        if data.get("ok"):
            return True

        print("Telegram error:", data)

    except Exception as e:
        print("Telegram send error:", e)

    return False


# ============================================================
# کپشن
# ============================================================

def make_caption(title, summary, source, url):
    footer = (
        f"\n\n"
        f"منبع: {source}\n"
        f"🔗 {url}"
    )

    prefix = f"📰 {title}\n\n"

    available = 1024 - len(prefix) - len(footer)

    if available < 100:
        summary = summary[:100]
    else:
        summary = summary[:available]

    return prefix + summary + footer


# ============================================================
# دریافت RSS
# ============================================================

def fetch_candidates():
    candidates = []

    for query in QUERIES:

        print("Fetching:", query)

        rss_url = (
            "https://news.google.com/rss/search?"
            f"q={requests.utils.quote(query)}"
            "&hl=en-US"
            "&gl=US"
            "&ceid=US:en"
        )

        try:
            response = session.get(
                rss_url,
                timeout=20,
            )

            if response.status_code != 200:
                print(
                    "RSS error:",
                    response.status_code
                )
                continue

            root = BeautifulSoup(
                response.content,
                "xml",
            )

            items = root.find_all("item")

            for item in items[:15]:

                title = clean_text(
                    item.find("title").text
                    if item.find("title")
                    else ""
                )

                description = clean_text(
                    item.find("description").text
                    if item.find("description")
                    else ""
                )

                link = (
                    item.find("link").text.strip()
                    if item.find("link")
                    else ""
                )

                source_name = allowed_source_from_rss(
                    item
                )

                # فقط منابع مجاز
                if not source_name:
                    continue

                # فقط موضوعات مجاز
                if not is_relevant(
                    title,
                    description,
                ):
                    continue

                score = urgency_score(
                    title,
                    description,
                )

                candidates.append({
                    "title": title,
                    "description": description,
                    "google_url": link,
                    "source": source_name,
                    "score": score,
                })

        except Exception as e:
            print("RSS fetch error:", e)

        time.sleep(1)

    # حذف لینک‌های تکراری
    unique = {}
    for item in candidates:
        unique[item["google_url"]] = item

    candidates = list(unique.values())

    # اول خبرهای مهم‌تر، سپس ترتیب RSS
    candidates.sort(
        key=lambda x: x["score"],
        reverse=True,
    )

    return candidates


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("JAHANTAB TELEGRAM NEWS BOT")
    print("Starting...")
    print("=" * 60)

    if not BOT_TOKEN:
        print("BOT_TOKEN is missing.")
        return

    if not OPENAI_API_KEY:
        print("OPENAI_API_KEY is missing.")
        return

    sent = load_sent()

    print("Already sent:", len(sent))

    candidates = fetch_candidates()

    print(
        "Candidates found:",
        len(candidates),
    )

    if not candidates:
        print("No suitable news found.")
        return

    # --------------------------------------------------------
    # یکی یکی امتحان می‌کنیم تا اولین خبر معتبر پیدا شود
    # --------------------------------------------------------

    for candidate in candidates:

        google_url = candidate["google_url"]

        if not google_url:
            continue

        if google_url in sent:
            continue

        print("-" * 60)

        print(
            "Selected:",
            candidate["title"]
        )

        print(
            "Source:",
            candidate["source"]
        )

        # ----------------------------------------------------
        # تبدیل Google News به لینک اصلی
        # ----------------------------------------------------

        direct_url = resolve_google_news(
            google_url
        )

        if not direct_url:
            print(
                "Skipping: direct URL unavailable."
            )
            continue

        # ----------------------------------------------------
        # بررسی دوباره منبع لینک اصلی
        # ----------------------------------------------------

        direct_source = allowed_source_from_domain(
            direct_url
        )

        if not direct_source:
            print(
                "Skipping: decoded URL is not "
                "from an allowed source."
            )
            continue

        # ----------------------------------------------------
        # دریافت اطلاعات مقاله
        # ----------------------------------------------------

        article = get_article(
            direct_url
        )

        if not article:
            print(
                "Skipping: article unavailable."
            )
            continue

        final_url = article["url"]

        print("Final URL:")
        print(final_url)

        # ----------------------------------------------------
        # مطمئن شو لینک واقعی است
        # ----------------------------------------------------

        if "news.google.com" in final_url:
            print(
                "Skipping: still a Google News URL."
            )
            continue

        # ----------------------------------------------------
        # جلوگیری از تکرار با لینک اصلی
        # ----------------------------------------------------

        if final_url in sent:
            print(
                "Already sent direct URL."
            )
            continue

        # ----------------------------------------------------
        # ساخت متن فارسی
        # ----------------------------------------------------

        fa = make_persian_news(
            article["title"]
            or candidate["title"],

            article["description"]
            or candidate["description"],

            article["text"],

            direct_source,
        )

        if not fa:
            print(
                "Skipping: Persian text was not created."
            )
            continue

        print(
            "Persian title:",
            fa["title"]
        )

        # ----------------------------------------------------
        # تصویر
        # ----------------------------------------------------

        image_file = None

        if article.get("image"):
            print("Downloading article image...")

            image_file = download_image(
                article["image"]
            )

        if not image_file:
            print(
                "Article image unavailable."
            )

            if os.path.exists(FALLBACK_FILE):
                image_file = FALLBACK_FILE

        if not image_file:
            print(
                "Skipping: no image available."
            )
            continue

        # ----------------------------------------------------
        # اضافه کردن لوگو
        # ----------------------------------------------------

        final_image = add_logo(
            image_file
        )

        if not final_image:
            continue

        # ----------------------------------------------------
        # کپشن
        # ----------------------------------------------------

        caption = make_caption(
            fa["title"],
            fa["summary"],
            direct_source,
            final_url,
        )

        # ----------------------------------------------------
        # ارسال
        # ----------------------------------------------------

        print("Sending to Telegram...")

        success = send_photo(
            final_image,
            caption,
        )

        if success:

            print("Sent successfully.")

            sent.add(final_url)

            # Google URL را هم ذخیره می‌کنیم
            # تا همان خبر دوباره انتخاب نشود
            sent.add(google_url)

            save_sent(sent)

            print("=" * 60)
            print("DONE")
            print("=" * 60)

            return

        else:
            print(
                "Telegram send failed."
            )

    print("=" * 60)
    print("No news was published this run.")
    print("=" * 60)


if __name__ == "__main__":
    main()