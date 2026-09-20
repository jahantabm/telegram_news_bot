import os
import re
import time
import html
import requests

from urllib.parse import urlparse
from bs4 import BeautifulSoup
from openai import OpenAI

from googlenewsdecoder import (
    gnewsdecoder,
    decoderv1,
    decoderv2,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL = os.getenv("CHANNEL", "@jahantab_news")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

LOGO_FILE = "jahantab_logo_transparent-1.png"
FALLBACK_FILE = "fallback_news.jpg"
SENT_FILE = "sent_links.txt"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/140 Safari/537.36"
)

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


# ============================================================
# منابع مجاز
# ============================================================

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


# ============================================================
# موضوعات
# ============================================================

QUERIES = [
    "Iran OR ایران",
    "Iran Israel OR ایران اسرائیل",
    "Iran US OR ایران آمریکا",
    "Iran Iraq OR ایران عراق",
    "Gaza Hamas Palestine OR غزه حماس فلسطین",
    "Hezbollah Lebanon OR حزب الله لبنان",
    "Yemen Houthis OR یمن حوثی",
    "Middle East war OR جنگ خاورمیانه",
]

KEYWORDS = [
    "iran", "iranian", "ایران", "ایرانی",
    "iraq", "iraqi", "عراق",
    "hashd", "pmu", "حشد",
    "lebanon", "لبنان",
    "hezbollah", "حزب الله", "حزب‌الله",
    "palestine", "فلسطین",
    "gaza", "غزه",
    "hamas", "حماس",
    "yemen", "یمن",
    "houthi", "houthis", "حوثی",
    "ansar allah", "انصارالله",
    "israel", "israeli", "اسرائیل",
    "america", "american", "usa", "u.s.",
    "آمریکا", "ایالات متحده",
    "war", "جنگ",
    "attack", "attacks", "حمله",
    "strike", "strikes",
    "missile", "missiles", "موشک",
    "rocket", "راکت",
    "drone", "پهپاد",
    "explosion", "انفجار",
    "ceasefire", "آتش بس", "آتش‌بس",
    "nuclear", "هسته ای", "هسته‌ای",
    "military", "نظامی",
    "killed", "کشته",
    "sanctions", "تحریم",
    "conflict", "درگیری",
]


# ============================================================
# ابزار
# ============================================================

def clean(text):
    if not text:
        return ""

    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def domain(url):
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def allowed_source(url):
    d = domain(url)

    for allowed_domain, name in SOURCES.items():
        if d == allowed_domain or d.endswith("." + allowed_domain):
            return name

    return None


def relevant(title, description):
    text = f"{title} {description}".lower()

    return any(
        word.lower() in text
        for word in KEYWORDS
    )


def urgency(title, description):
    text = f"{title} {description}".lower()

    words = [
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
        "جنگ",
        "حمله",
        "موشک",
        "پهپاد",
        "انفجار",
        "کشته",
        "فوری",
        "آتش‌بس",
        "آتش بس",
        "هسته‌ای",
        "نظامی",
    ]

    return sum(
        1 for word in words
        if word.lower() in text
    )


# ============================================================
# خبرهای ارسال شده
# ============================================================

def load_sent():
    if not os.path.exists(SENT_FILE):
        return set()

    try:
        with open(
            SENT_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            return {
                x.strip()
                for x in f
                if x.strip()
            }

    except Exception:
        return set()


def save_sent(items):
    with open(
        SENT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        for item in sorted(items):
            f.write(item + "\n")


# ============================================================
# تشخیص منبع RSS
# ============================================================

def rss_source(item):

    source = item.find("source")

    if source is None:
        return None

    source_url = source.get("url", "")

    # اول URL منبع
    if source_url:
        detected = allowed_source(source_url)

        if detected:
            return detected

    # سپس نام منبع
    source_name = clean(
        source.get_text()
    ).lower()

    for _, name in SOURCES.items():

        if source_name == name.lower():
            return name

    return None


# ============================================================
# Google News → لینک واقعی
# ============================================================

def decode_google(url):

    if "news.google.com" not in url:
        return url

    print("Trying Google News decoder...")

    decoders = [
        ("decoderv1", lambda: decoderv1(url)),
        ("decoderv2", lambda: decoderv2(url)),
        (
            "gnewsdecoder",
            lambda: gnewsdecoder(
                url,
                interval=1
            )
        ),
    ]

    for name, decoder in decoders:

        try:

            result = decoder()

            if isinstance(result, str):
                candidate = result

            elif isinstance(result, dict):
                candidate = result.get(
                    "decoded_url"
                )

            else:
                candidate = None

            if (
                candidate
                and "news.google.com" not in candidate
                and candidate.startswith("http")
            ):
                print(
                    f"Decoded with {name}:"
                )
                print(candidate)

                return candidate

        except Exception as e:
            print(
                f"{name} failed:",
                str(e)[:200]
            )

    print("ALL GOOGLE DECODERS FAILED")

    return None


# ============================================================
# دریافت مقاله
# ============================================================

def get_article(url):

    try:

        response = session.get(
            url,
            timeout=20,
            allow_redirects=True,
        )

        if response.status_code >= 400:
            print(
                "Article HTTP:",
                response.status_code
            )
            return None

        final_url = response.url

        if "news.google.com" in final_url:
            return None

        source = allowed_source(
            final_url
        )

        if not source:
            print(
                "Rejected source:",
                domain(final_url)
            )
            return None

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        def meta(name):

            tag = soup.find(
                "meta",
                attrs={
                    "property": name
                }
            )

            if not tag:
                tag = soup.find(
                    "meta",
                    attrs={
                        "name": name
                    }
                )

            if tag:
                return clean(
                    tag.get(
                        "content",
                        ""
                    )
                )

            return ""

        title = (
            meta("og:title")
            or meta("twitter:title")
        )

        description = (
            meta("og:description")
            or meta("description")
            or meta(
                "twitter:description"
            )
        )

        image = (
            meta("og:image")
            or meta("twitter:image")
        )

        if not title and soup.title:
            title = clean(
                soup.title.get_text()
            )

        paragraphs = []

        for p in soup.find_all("p"):

            text = clean(
                p.get_text(
                    " ",
                    strip=True
                )
            )

            if len(text) >= 40:
                paragraphs.append(text)

        article_text = " ".join(
            paragraphs
        )[:7000]

        return {
            "url": final_url,
            "source": source,
            "title": title,
            "description": description,
            "image": image,
            "text": article_text,
        }

    except Exception as e:

        print(
            "Article error:",
            str(e)[:300]
        )

        return None


# ============================================================
# تصویر
# ============================================================

def download_image(url):

    if not url:
        return None

    # هیچ تصویر Google را قبول نکن
    image_domain = domain(url)

    blocked = [
        "google.com",
        "googleusercontent.com",
        "gstatic.com",
        "googleapis.com",
    ]

    if any(
        image_domain == x
        or image_domain.endswith("." + x)
        for x in blocked
    ):
        print(
            "Google image rejected."
        )
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

        filename = "news_original.jpg"

        with open(
            filename,
            "wb"
        ) as f:

            for chunk in response.iter_content(
                8192
            ):

                if chunk:
                    f.write(chunk)

        if os.path.getsize(filename) < 1000:
            return None

        print(
            "Original article image downloaded."
        )

        return filename

    except Exception as e:

        print(
            "Image error:",
            str(e)[:200]
        )

        return None


# ============================================================
# لوگو
# ============================================================

def add_logo(image_file):

    if not image_file:
        return None

    if not os.path.exists(LOGO_FILE):
        return image_file

    try:

        from PIL import Image

        base = Image.open(
            image_file
        ).convert("RGBA")

        logo = Image.open(
            LOGO_FILE
        ).convert("RGBA")

        max_width = int(
            base.width * 0.20
        )

        if logo.width > max_width:

            ratio = (
                max_width /
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

        margin = max(
            15,
            int(
                base.width *
                0.025
            )
        )

        x = (
            base.width -
            logo.width -
            margin
        )

        y = margin

        base.alpha_composite(
            logo,
            (x, y)
        )

        output = "final_news.jpg"

        base.convert(
            "RGB"
        ).save(
            output,
            "JPEG",
            quality=92,
        )

        return output

    except Exception as e:

        print(
            "Logo error:",
            str(e)[:200]
        )

        return image_file


# ============================================================
# ترجمه و خلاصه فارسی
# ============================================================

def make_persian(
    title,
    description,
    article_text,
    source
):

    if not OPENAI_API_KEY:
        return None

    client = OpenAI(
        api_key=OPENAI_API_KEY
    )

    prompt = f"""
تو سردبیر یک کانال خبری فارسی هستی.

خبر زیر را برای انتشار در تلگرام به فارسی روان تبدیل کن.

منبع:
{source}

عنوان اصلی:
{title}

توضیح:
{description}

متن خبر:
{article_text}

قوانین:
- عنوان حتماً فارسی باشد.
- خلاصه دقیقاً 3 تا 4 جمله باشد.
- هیچ اطلاعاتی اضافه یا حدس زده نشود.
- لحن کاملاً خبری و خنثی باشد.
- اگر خبر ادعا یا گزارش یک طرف است، آن را به عنوان ادعا/گزارش همان منبع بیان کن.
- خروجی انگلیسی نباشد.

فقط این قالب:

TITLE:
عنوان فارسی

SUMMARY:
خلاصه فارسی
"""

    try:

        response = client.responses.create(
            model="gpt-5.6-luna",
            input=prompt,
            max_output_tokens=700,
        )

        output = (
            response.output_text
            .strip()
        )

        title_match = re.search(
            r"TITLE:\s*(.*?)(?:\n|$)",
            output,
            re.I,
        )

        summary_match = re.search(
            r"SUMMARY:\s*(.*)",
            output,
            re.I | re.S,
        )

        if not title_match:
            print(
                "Persian title missing."
            )
            return None

        if not summary_match:
            print(
                "Persian summary missing."
            )
            return None

        fa_title = clean(
            title_match.group(1)
        )

        fa_summary = clean(
            summary_match.group(1)
        )

        if not re.search(
            r"[\u0600-\u06FF]",
            fa_title
        ):
            print(
                "Title is not Persian."
            )
            return None

        if not re.search(
            r"[\u0600-\u06FF]",
            fa_summary
        ):
            print(
                "Summary is not Persian."
            )
            return None

        return {
            "title": fa_title,
            "summary": fa_summary,
        }

    except Exception as e:

        if (
            getattr(
                e,
                "status_code",
                None
            ) == 429
            or "429" in str(e)
        ):

            print(
                "OPENAI LIMIT REACHED."
            )

        else:

            print(
                "OPENAI ERROR:",
                str(e)[:300]
            )

        return None


# ============================================================
# ارسال تلگرام
# ============================================================

def send_photo(
    image,
    title,
    summary,
    source,
    url
):

    api = (
        f"https://api.telegram.org/bot"
        f"{BOT_TOKEN}/sendPhoto"
    )

    # لینک بلند در متن نمایش داده نمی‌شود
    link = (
        f'<a href="{html.escape(url)}">'
        f"🔗 مشاهده خبر اصلی"
        f"</a>"
    )

    caption = (
        f"📰 <b>{html.escape(title)}</b>\n\n"
        f"{html.escape(summary)}\n\n"
        f"منبع: {html.escape(source)}\n"
        f"{link}"
    )

    # محدودیت کپشن تلگرام
    if len(caption) > 1024:

        allowed = (
            1024 -
            len(
                f"📰 <b>{html.escape(title)}</b>\n\n"
                f"\n\nمنبع: {html.escape(source)}\n"
                f"{link}"
            )
        )

        summary = summary[:max(
            100,
            allowed
        )]

        caption = (
            f"📰 <b>{html.escape(title)}</b>\n\n"
            f"{html.escape(summary)}\n\n"
            f"منبع: {html.escape(source)}\n"
            f"{link}"
        )

    try:

        with open(
            image,
            "rb"
        ) as photo:

            response = requests.post(
                api,
                data={
                    "chat_id": CHANNEL,
                    "caption": caption,
                    "parse_mode": "HTML",
                },
                files={
                    "photo": photo
                },
                timeout=30,
            )

        result = response.json()

        if result.get("ok"):
            return True

        print(
            "Telegram error:",
            result
        )

    except Exception as e:

        print(
            "Telegram error:",
            str(e)[:300]
        )

    return False


# ============================================================
# RSS
# ============================================================

def get_candidates():

    candidates = []

    for query in QUERIES:

        print(
            "Fetching:",
            query
        )

        url = (
            "https://news.google.com/rss/search?"
            f"q={requests.utils.quote(query)}"
            "&hl=en-US"
            "&gl=US"
            "&ceid=US:en"
        )

        try:

            response = session.get(
                url,
                timeout=20,
            )

            if response.status_code != 200:
                continue

            soup = BeautifulSoup(
                response.content,
                "xml"
            )

            for item in soup.find_all(
                "item"
            )[:20]:

                title = clean(
                    item.title.text
                    if item.title
                    else ""
                )

                description = clean(
                    item.description.text
                    if item.description
                    else ""
                )

                link = clean(
                    item.link.text
                    if item.link
                    else ""
                )

                source = rss_source(
                    item
                )

                # فقط منابع مجاز
                if not source:
                    continue

                if not relevant(
                    title,
                    description
                ):
                    continue

                candidates.append({
                    "title": title,
                    "description": description,
                    "google_url": link,
                    "source": source,
                    "score": urgency(
                        title,
                        description
                    ),
                })

        except Exception as e:

            print(
                "RSS error:",
                str(e)[:200]
            )

        time.sleep(1)

    unique = {}

    for item in candidates:
        unique[
            item["google_url"]
        ] = item

    result = list(
        unique.values()
    )

    result.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return result


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("JAHANTAB TELEGRAM NEWS BOT")
    print("NEW VERSION")
    print("=" * 60)

    sent = load_sent()

    print(
        "Already sent:",
        len(sent)
    )

    candidates = get_candidates()

    print(
        "Candidates:",
        len(candidates)
    )

    for item in candidates:

        google_url = item[
            "google_url"
        ]

        if not google_url:
            continue

        if google_url in sent:
            continue

        print("-" * 60)
        print(
            "Candidate:",
            item["title"]
        )
        print(
            "RSS source:",
            item["source"]
        )

        # ----------------------------------------------------
        # لینک واقعی
        # ----------------------------------------------------

        direct_url = decode_google(
            google_url
        )

        if not direct_url:

            print(
                "SKIP: no direct URL"
            )
            continue

        # ----------------------------------------------------
        # منبع واقعی را از URL تشخیص بده
        # ----------------------------------------------------

        real_source = allowed_source(
            direct_url
        )

        if not real_source:

            print(
                "SKIP: source not allowed:",
                domain(direct_url)
            )
            continue

        print(
            "Real source:",
            real_source
        )

        # ----------------------------------------------------
        # مقاله واقعی
        # ----------------------------------------------------

        article = get_article(
            direct_url
        )

        if not article:
            continue

        final_url = article[
            "url"
        ]

        # دوباره چک
        if "news.google.com" in final_url:
            print(
                "SKIP: Google URL"
            )
            continue

        if final_url in sent:
            continue

        # ----------------------------------------------------
        # متن فارسی
        # ----------------------------------------------------

        fa = make_persian(
            article["title"]
            or item["title"],

            article["description"]
            or item["description"],

            article["text"],

            real_source,
        )

        if not fa:

            print(
                "SKIP: no Persian text"
            )
            continue

        print(
            "Persian title:",
            fa["title"]
        )

        # ----------------------------------------------------
        # تصویر واقعی
        # ----------------------------------------------------

        image = None

        if article["image"]:

            image = download_image(
                article["image"]
            )

        if not image:

            print(
                "Using fallback image."
            )

            if os.path.exists(
                FALLBACK_FILE
            ):
                image = FALLBACK_FILE

        if not image:
            continue

        # ----------------------------------------------------
        # لوگو
        # ----------------------------------------------------

        image = add_logo(
            image
        )

        if not image:
            continue

        # ----------------------------------------------------
        # ارسال
        # ----------------------------------------------------

        print(
            "Sending..."
        )

        success = send_photo(
            image,
            fa["title"],
            fa["summary"],
            real_source,
            final_url,
        )

        if success:

            print(
                "SENT SUCCESSFULLY"
            )

            sent.add(
                final_url
            )

            sent.add(
                google_url
            )

            save_sent(
                sent
            )

            print("=" * 60)
            print("DONE")
            print("=" * 60)

            return

    print("=" * 60)
    print("NO NEWS PUBLISHED")
    print("=" * 60)


if __name__ == "__main__":
    main()