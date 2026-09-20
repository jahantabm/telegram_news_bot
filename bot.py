# -*- coding: utf-8 -*-

"""
JAHANTAB Telegram News Bot
--------------------------------
هدف:
فقط انتشار خبرهای فوری و مهم درباره:
- جنگ ایران
- حملات و عملیات نظامی مرتبط با ایران
- اسرائیل / آمریکا در ارتباط مستقیم با جنگ ایران
- حزب‌الله / لبنان
- حماس / غزه / فلسطین
- انصارالله / حوثی‌ها / یمن
- نیروهای مسلح همسو در عراق و سوریه
- تنگه هرمز / باب‌المندب / پایگاه‌های نظامی منطقه

ویژگی‌ها:
- بدون OpenAI
- بدون ترجمه
- بدون Google News
- منابع فارسی
- RSS در صورت وجود
- fallback به scraping صفحه اصلی
- استخراج عنوان، خلاصه و تصویر
- امتیازدهی اهمیت و فوریت
- حذف اخبار تحلیلی/غیرمرتبط
- حذف اخبار تکراری
- محدودیت زمانی
- ارسال عکس + کپشن به Telegram
- پشتیبانی اختیاری از logo.jpg
"""

import os
import re
import time
import html
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

try:
    import feedparser
except ImportError:
    feedparser = None

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = None


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()

# چند ساعت گذشته بررسی شود
MAX_AGE_HOURS = int(os.getenv("MAX_AGE_HOURS", "24"))

# برای خبرهای واقعاً فوری، ترجیحاً در این بازه امتیاز بالاتر می‌گیرند
URGENT_HOURS = int(os.getenv("URGENT_HOURS", "6"))

# حداقل امتیاز برای انتشار
MIN_SCORE = int(os.getenv("MIN_SCORE", "16"))

# حداکثر تعداد خبرهایی که در هر اجرای Workflow ارسال می‌شود
MAX_POSTS_PER_RUN = int(os.getenv("MAX_POSTS_PER_RUN", "3"))

# تعداد خبرهای اولیه از هر سایت
MAX_ITEMS_PER_SOURCE = int(os.getenv("MAX_ITEMS_PER_SOURCE", "12"))

# Timeout
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "20"))

# فایل لینک‌های ارسال‌شده
SENT_FILE = os.getenv("SENT_FILE", "sent_links.txt")

# اگر فایل logo.jpg در کنار bot.py وجود داشته باشد،
# در صورت امکان روی عکس خبر watermark می‌شود.
LOGO_FILE = os.getenv("LOGO_FILE", "logo.jpg")

# User Agent
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0 Safari/537.36 "
    "JAHANTAB-NewsBot