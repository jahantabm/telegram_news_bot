import os
import requests
import xml.etree.ElementTree as ET
import subprocess

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL = os.environ["CHANNEL"]

RSS_URL = (
    "https://news.google.com/rss/search?"
    "q=%D8%A7%DB%8C%D8%B1%D8%A7%D9%86+OR+%D8%B9%D8%B1%D8%A7%D9%82+OR+%D8%B3%D9%88%D8%B1%DB%8C%D9%87+"
    "OR+%D9%84%D8%A8%D9%86%D8%A7%D9%86+OR+%D8%BA%D8%B2%D9%87&hl=fa&gl=IR&ceid=IR:fa"
)

SENT_FILE = "sent_links.txt"


def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": CHANNEL,
            "text": text,
            "disable_web_page_preview": False,
        },
        timeout=20,
    )

    response.raise_for_status()


def load_sent_links():
    if not os.path.exists(SENT_FILE):
        return set()

    with open(SENT_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def save_sent_link(link):
    with open(SENT_FILE, "a", encoding="utf-8") as f:
        f.write(link + "\n")


def main():
    response = requests.get(RSS_URL, timeout=20)
    response.raise_for_status()

    root = ET.fromstring(response.text)
    items = root.findall("./channel/item")

    sent_links = load_sent_links()

    for item in items:
        title = item.findtext("title")
        link = item.findtext("link")

        if not title or not link:
            continue

        if link in sent_links:
            continue

        message = (
            f"🚨 {title}\n\n"
            f"🔗 منبع خبر:\n{link}\n\n"
            f"جهان تاب تحولات جهان\n"
            f"@jahantab_news"
        )

        send_message(message)

        save_sent_link(link)

        break


if __name__ == "__main__":
    main()
