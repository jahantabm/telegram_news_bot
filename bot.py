
import os
import requests
import xml.etree.ElementTree as ET

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL = os.environ["CHANNEL"]

RSS_URL = (
    "https://news.google.com/rss/search?"
    "q=%D8%A7%DB%8C%D8%B1%D8%A7%D9%86+OR+%D8%B9%D8%B1%D8%A7%D9%82+OR+%D8%B3%D9%88%D8%B1%DB%8C%D9%87+"
    "OR+%D9%84%D8%A8%D9%86%D8%A7%D9%86+OR+%D8%BA%D8%B2%D9%87&hl=fa&gl=IR&ceid=IR:fa"
)

def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(
        url,
        data={
            "chat_id": CHANNEL,
            "text": text,
            "disable_web_page_preview": False,
        },
        timeout=20,
    )

def main():
    response = requests.get(RSS_URL, timeout=20)
    root = ET.fromstring(response.text)

    items = root.findall("./channel/item")

    for item in items[:5]:
        title = item.findtext("title")
        link = item.findtext("link")

        if title and link:
            message = f"🚨 خبر فوری\n\n{title}\n\n🔗 {link}"
            send_message(message)

if __name__ == "__main__":
    main()
