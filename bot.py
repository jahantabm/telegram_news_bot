# -*- coding: utf-8 -*-
"""JAHANTAB News Bot - final version Telegram news collector with strict relevance filtering, event deduplication, image/logo support, and an inline glass-style "مشاهده خبر" button. """
import os, re, time, html, logging, hashlib
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urlunparse
import requests
from bs4 import BeautifulSoup
try:
    import feedparser
except ImportError:
    feedparser = None
try:
    from PIL import Image
except ImportError:
    Image = None

BOT_TOKEN=os.getenv("BOT_TOKEN","").strip()
CHAT_ID=os.getenv("CHAT_ID","").strip() or os.getenv("CHANNEL","").strip() or "@jahantab_news"
MAX_AGE_HOURS=int(os.getenv("MAX_AGE_HOURS","24")); URGENT_HOURS=int(os.getenv("URGENT_HOURS","6"))
MIN_SCORE=int(os.getenv("MIN_SCORE","18")); MAX_POSTS_PER_RUN=int(os.getenv("MAX_POSTS_PER_RUN","3"))
MAX_ITEMS_PER_SOURCE=int(os.getenv("MAX_ITEMS_PER_SOURCE","12")); HTTP_TIMEOUT=int(os.getenv("HTTP_TIMEOUT","20"))
POST_DELAY=float(os.getenv("POST_DELAY","2")); SIMILARITY_THRESHOLD=float(os.getenv("SIMILARITY_THRESHOLD","0.62"))
BASE_DIR=os.path.dirname(os.path.abspath(__file__))
SENT_FILE=os.path.join(BASE_DIR,os.getenv("SENT_FILE","sent_links.txt"))
SENT_TITLES_FILE=os.path.join(BASE_DIR,os.getenv("SENT_TITLES_FILE","sent_titles.txt"))
SENT_EVENTS_FILE=os.path.join(BASE_DIR,os.getenv("SENT_EVENTS_FILE","sent_events.txt"))
LOGO_FILE=os.path.join(BASE_DIR,os.getenv("LOGO_FILE","logo.jpg"))

USER_AGENT="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36 JAHANTAB-NewsBot/6.0"
HEADERS={"User-Agent":USER_AGENT,"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8","Accept-Language":"fa-IR,fa;q=0.9,en;q=0.5"}
logging.basicConfig(level=logging.INFO,format="%(asctime)s | %(levelname)s | %(message)s"); log=logging.getLogger("JAHANTAB")
SESSION=requests.Session(); SESSION.headers.update(HEADERS)

SOURCES=[
("خبرآنلاین","khabaronline.ir","https://www.khabaronline.ir/"),("فرارو","fararu.com","https://fararu.com/"),("تابناک","tabnak.ir","https://www.tabnak.ir/"),("مشرق نیوز","mashreghnews.ir","https://www.mashreghnews.ir/"),("عصر ایران","asriran.com","https://www.asriran.com/"),("الف","alef.ir","https://www.alef.ir/"),("انتخاب","entekhab.ir","https://www.entekhab.ir/"),("شرق","sharghdaily.com","https://www.sharghdaily.com/"),("همشهری آنلاین","hamshahrionline.ir","https://www.hamshahrionline.ir/"),("روزنامه ایران","irannewspaper.ir","https://www.irannewspaper.ir/"),("اطلاعات","ettelaat.com","https://www.ettelaat.com/"),("کیهان","kayhan.ir","https://kayhan.ir/"),("اعتماد","etemadnewspaper.ir","https://www.etemadnewspaper.ir/"),("رسالت","resalat-news.com","https://resalat-news.com/"),("ابتکار","ebtekarnews.com","https://www.ebtekarnews.com/"),("وطن امروز","vatanemrooz.ir","https://vatanemrooz.ir/"),("ایرنا","irna.ir","https://www.irna.ir/"),("ایسنا","isna.ir","https://www.isna.ir/"),("فارس","farsnews.ir","https://www.farsnews.ir/"),("تسنیم","tasnimnews.com","https://www.tasnimnews.com/fa"),("مهر","mehrnews.com","https://www.mehrnews.com/"),("IRIB","iribnews.ir","https://www.iribnews.ir/"),("باشگاه خبرنگاران جوان","yjc.ir","https://www.yjc.ir/"),("ایلنا","ilna.ir","https://www.ilna.ir/"),("ایکنا","iqna.ir","https://iqna.ir/"),("خبر فوری","khabarfoori.com","https://www.khabarfoori.com/"),("آخرین خبر","akharinkhabar.ir","https://akharinkhabar.ir/"),("روزپلاس","roozplus.com","https://roozplus.com/")]

CORE={"ایران":5,"جمهوری اسلامی":5,"اسرائیل":4,"رژیم صهیونیستی":4,"آمریکا":3,"ایالات متحده":3,"سپاه":5,"سپاه پاسداران":5,"ارتش":4,"حزب الله":5,"حزب‌الله":5,"لبنان":3,"حماس":5,"فلسطین":3,"غزه":4,"یمن":3,"حوثی":5,"حوثی‌ها":5,"انصارالله":5,"عراق":2,"سوریه":2,"مقاومت":4,"محور مقاومت":5,"هرمز":5,"تنگه هرمز":6,"باب المندب":5,"باب‌المندب":5}
ACTIONS={"حمله":7,"حملات":7,"حمله هوایی":9,"بمباران":8,"موشک":8,"موشکی":8,"موشکباران":9,"موشک‌باران":9,"پهپاد":7,"پهپادی":7,"شلیک":7,"اصابت":8,"رهگیری":6,"انفجار":7,"عملیات":6,"عملیات نظامی":8,"درگیری":7,"درگیری نظامی":8,"تبادل آتش":8,"هدف قرار داد":8,"هدف قرار گرفت":8,"سرنگونی":8,"توقیف":7,"حمله موشکی":9,"حمله پهپادی":9,"پایگاه":6,"پایگاه نظامی":8,"تاسیسات نظامی":7,"تأسیسات نظامی":7,"تاسیسات هسته‌ای":8,"تأسیسات هسته ای":8,"نیروهای آمریکایی":6,"نیروهای اسرائیلی":6,"ارتش اسرائیل":6,"نیروی هوایی":5,"نیروی دریایی":5}
MAJOR={"آتش بس":10,"آتش‌بس":10,"پایان جنگ":12,"آغاز جنگ":12,"اعلام جنگ":12,"ورود به جنگ":11,"گسترش جنگ":8,"تشدید درگیری":8,"تشدید تنش":5,"حمله گسترده":10,"عملیات گسترده":9,"حمله مستقیم":10,"حمله متقابل":9,"پاسخ موشکی":9,"پاسخ نظامی":8,"بسته شدن تنگه هرمز":15,"بازگشایی تنگه هرمز":12,"پایگاه آمریکایی":9,"پایگاه آمریکا":9,"پایگاه اسرائیل":9}
URGENT={"فوری":8,"خبر فوری":12,"لحظاتی پیش":10,"دقایقی پیش":10,"همین الان":10,"هم‌اکنون":10,"هم اکنون":10,"خبر مهم":7,"لحظه به لحظه":7,"اولین خبر":5,"تازه‌ترین":4,"تازه ترین":4}
CASUALTY={"کشته":7,"کشته‌ها":7,"کشته شد":8,"مجروح":6,"زخمی":6,"تلفات":7,"تلفات سنگین":9,"انفجار":7,"آتش سوزی":5,"آتش‌سوزی":5}
ANALYSIS={"تحلیل":-10,"یادداشت":-10,"کارشناس":-7,"کارشناسان":-7,"گفتگو":-7,"گفت‌وگو":-7,"گفت و گو":-7,"بررسی":-6,"چرا":-5,"چگونه":-5,"روایت":-5,"تحلیلگر":-8,"تحلیل‌گر":-8,"سناریو":-7,"پیش بینی":-8,"پیش‌بینی":-8,"آینده جنگ":-7,"نگاهی به":-6,"گزارش تحلیلی":-10}
EXCLUDE={"ورزش":-25,"فوتبال":-25,"والیبال":-25,"بسکتبال":-25,"سینما":-25,"تلویزیون":-25,"موسیقی":-25,"سلامت":-20,"پزشکی":-20,"کنکور":-25,"دانشگاه":-20,"هواشناسی":-20,"بورس":-18,"دلار":-14,"طلا":-14,"سکه":-14,"خودرو":-20,"مسکن":-20,"بازنشستگی":-20}
# موارد محلی/کم‌اهمیت که نباید صرفاً به دلیل یک واژه نظامی وارد شوند
LOW_IMPORTANCE={"آتش سوزی":-12,"آتش‌سوزی":-12,"حادثه رانندگی":-15,"تصادف":-15,"سرقت":-18,"نزاع":-18,"حریق یک ساختمان":-12}


def norm(s):
    if not s:return ""
    s=html.unescape(str(s)); mp={"ي":"ی","ى":"ی","ك":"ک","ۀ":"ه","ة":"ه","ؤ":"و","إ":"ا","أ":"ا","ٱ":"ا","ـ":"","\u200c":" ","\u200f":" ","\u200e":" ","\ufeff":" "}
    for a,b in mp.items():s=s.replace(a,b)
    return re.sub(r"\s+"," ",s).strip().lower()
def clean(s):
    if not s:return ""
    soup=BeautifulSoup(str(s),"html.parser")
    for x in soup(["script","style","noscript"]):x.decompose()
    return re.sub(r"\s+"," ",html.unescape(soup.get_text(" ",strip=True))).strip()
def shorten(s,n):
    s=clean(s)
    if len(s)<=n:return s
    x=s[:n]
    return x.rsplit(" ",1)[0].rstrip(" .،؛:")+"…"
def canonical(u):
    try:
        p=urlparse(u); host=p.netloc.lower().removeprefix("www."); path=p.path or "/"
        if path!="/":path=path.rstrip("/")
        return urlunparse((p.scheme.lower() or "https",host,path,"","",""))
    except:return u.strip() if u else ""
def safe_get(u,**kw):
    try:return SESSION.get(u,timeout=kw.pop("timeout",HTTP_TIMEOUT),allow_redirects=True,**kw)
    except requests.RequestException as e:log.warning("GET failed %s | %s",u,e);return None

def load_set(path):
    try:
        with open(path,encoding="utf-8") as f:return {x.strip() for x in f if x.strip()}
    except:return set()
def fingerprint(t):
    return re.sub(r"\s+"," ",re.sub(r"[^\w\sآ-ی]"," ",norm(t))).strip()
def save_sent(item):
    try:
        with open(SENT_FILE,"a",encoding="utf-8") as f:f.write(canonical(item["url"])+"\n")
        with open(SENT_TITLES_FILE,"a",encoding="utf-8") as f:f.write(fingerprint(item["title"])+"\n")
        with open(SENT_EVENTS_FILE,"a",encoding="utf-8") as f:f.write(item["event_key"]+"\n")
    except Exception as e:log.error("save sent: %s",e)

def parse_dt(v):
    if isinstance(v,datetime):return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)
    try:return datetime(v.tm_year,v.tm_mon,v.tm_mday,v.tm_hour,v.tm_min,v.tm_sec,tzinfo=timezone.utc)
    except:return None
def age(dt):return 999999 if not dt else max(0,(datetime.now(timezone.utc)-dt).total_seconds()/3600)

def discover_feeds(source):
    name,domain,home=source; out=[urljoin(home,p) for p in ["/rss","/rss/","/feed","/feed/","/rss.xml","/feed.xml","/atom.xml","/fa/rss","/fa/feed"]]
    r=safe_get(home)
    if r and r.ok:
        try:
            soup=BeautifulSoup(r.text,"html.parser")
            for l in soup.find_all("link"):
                typ=(l.get("type") or "").lower(); rel=" ".join(l.get("rel",[])).lower() if isinstance(l.get("rel",[]),list) else str(l.get("rel","")).lower()
                if "alternate" in rel and any(x in typ for x in ("rss","atom","xml")) and l.get("href"):out.insert(0,urljoin(r.url,l["href"]))
        except:pass
    seen=[]
    for u in out:
        u=canonical(u)
        if u and u not in seen:seen.append(u)
    return seen[:20]
def entry_image(e):
    vals=[]
    for k in ("media_content","media_thumbnail","enclosures"):
        for x in e.get(k,[]) or []:
            if isinstance(x,dict):vals += [x.get("url"),x.get("href")]
    return next((x for x in vals if x and x.startswith(("http://","https://"))),"")
def parse_feed(source,url):
    if feedparser is None:return []
    r=safe_get(url,headers={**HEADERS,"Accept":"application/rss+xml,application/atom+xml,application/xml,text/xml,text/html"})
    if not r or not r.ok:return []
    try:p=feedparser.parse(r.content)
    except:return []
    out=[]
    for e in p.entries[:MAX_ITEMS_PER_SOURCE]:
        title=clean(e.get("title","")); link=canonical(e.get("link", ""))
        if not title or not link:continue
        dt=parse_dt(e.get("published_parsed") or e.get("updated_parsed") or e.get("created_parsed"))
        desc=clean(e.get("summary","") or e.get("description",""))
        out.append({"title":title,"url":link,"description":desc,"dt":dt,"image":entry_image(e),"source":source[0],"domain":source[1]})
    return out

def html_fallback(source):
    name,domain,home=source;r=safe_get(home)
    if not r or not r.ok:return []
    soup=BeautifulSoup(r.text,"html.parser");out=[];seen=set()
    for a in soup.find_all("a",href=True):
        href=canonical(urljoin(r.url,a["href"]));title=clean(a.get_text(" ",strip=True))
        if not href or href in seen or not title or len(title)<15:continue
        if domain not in urlparse(href).netloc:continue
        if any(x in href.lower() for x in ("/tag/","/category/","/author/","javascript:")):continue
        seen.add(href);out.append({"title":title,"url":href,"description":"","dt":None,"image":"","source":name,"domain":domain})
        if len(out)>=MAX_ITEMS_PER_SOURCE:break
    return out

def score(item):
    text=norm(item["title"]+" "+item.get("description",""));s=0;hits=[]
    for group in (CORE,ACTIONS,MAJOR,URGENT,CASUALTY,ANALYSIS,EXCLUDE,LOW_IMPORTANCE):
        for k,v in group.items():
            if norm(k) in text:s+=v;hits.append(k)
    a=age(item.get("dt"));
    if a<=URGENT_HOURS:s+=5
    elif a>MAX_AGE_HOURS:s-=30
    # خبر مهم باید هم «موضوع منطقه‌ای/ایران» داشته باشد و هم نشانه رخداد/اهمیت؛ صرف چین/آتش‌سوزی پذیرفته نشود.
    core_hits=sum(1 for k in CORE if norm(k) in text)
    action_hits=sum(1 for k in ACTIONS if norm(k) in text)
    major_hits=sum(1 for k in MAJOR if norm(k) in text)
    important=major_hits>0 or (core_hits>=1 and action_hits>=1) or (core_hits>=2 and action_hits>=0)
    if not important:s-=18
    if "چین" in text and not any(norm(k) in text for k in ("ایران","اسرائیل","آمریکا","جنگ","موشک","حمله","تنگه هرمز")):s-=30
    return s,hits

def tokens(t):
    stop={"این","آن","یک","از","به","در","با","برای","که","و","را","شد","شدند","است","کرد","کرده","روی","بر","تا","اما"}
    return {x for x in re.findall(r"[آ-یa-z0-9]{2,}",norm(t)) if x not in stop}
def similarity(a,b):
    A=tokens(a);B=tokens(b)
    if not A or not B:return 0
    return len(A&B)/len(A|B)
def event_key(item):
    t=norm(item["title"])
    # حذف کلمات خبری عمومی تا یک رویداد واحد بین منابع مختلف کلید مشابه بگیرد.
    generic={"خبر","فوری","مهم","گزارش","اظهارات","آخرین","جدید","تازه","اعلام","شد","کرد","درباره","درخصوص","بیان"}
    ts=sorted(tokens(t)-generic)
    return hashlib.sha1(" ".join(ts[:18]).encode("utf-8")).hexdigest()[:20]

def rank_and_dedupe(items,sent_links,sent_titles,sent_events):
    pool=[]
    for x in items:
        x["url"]=canonical(x["url"]);x["score"],x["hits"]=score(x);x["event_key"]=event_key(x)
        if not x["url"] or x["url"] in sent_links:continue
        fp=fingerprint(x["title"])
        if fp and fp in sent_titles:continue
        if x["event_key"] in sent_events:continue
        if x["score"]<MIN_SCORE:continue
        pool.append(x)
    pool.sort(key=lambda x:(x["score"],-(age(x.get("dt")) if x.get("dt") else 999999)),reverse=True)
    selected=[]
    for x in pool:
        duplicate=False
        for y in selected:
            if x["event_key"]==y["event_key"] or similarity(x["title"],y["title"])>=SIMILARITY_THRESHOLD:
                duplicate=True;break
        if not duplicate:selected.append(x)
        if len(selected)>=MAX_POSTS_PER_RUN:break
    return selected

def download_image(url):
    if not url:return None
    try:
        r=safe_get(url,timeout=15,headers={**HEADERS,"Accept":"image/avif,image/webp,image/jpeg,image/png,*/*"})
        if not r or not r.ok:return None
        path=os.path.join(BASE_DIR,".jahantab_img.jpg");open(path,"wb").write(r.content)
        if Image:
            im=Image.open(path).convert("RGB"); im.thumbnail((1600,1600)); im.save(path,"JPEG",quality=90)
        return path
    except Exception:return None

def add_logo(img_path):
    if not img_path or not Image or not os.path.exists(LOGO_FILE):return img_path
    try:
        base=Image.open(img_path).convert("RGBA");logo=Image.open(LOGO_FILE).convert("RGBA")
        logo.thumbnail((max(120,base.width//6),max(120,base.height//6)))
        margin=max(15,base.width//50);base.alpha_composite(logo,(base.width-logo.width-margin,base.height-logo.height-margin));base.convert("RGB").save(img_path,"JPEG",quality=92)
    except Exception as e:log.warning("logo: %s",e)
    return img_path

def telegram(method,data=None,files=None):
    u=f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    try:
        r=requests.post(u,data=data,files=files,timeout=30);j=r.json()
        if not j.get("ok"):log.error("Telegram %s: %s",method,j)
        return j
    except Exception as e:log.error("Telegram request: %s",e);return {}

def format_caption(x):
    tm=x.get("dt").astimezone().strftime("%H:%M") if x.get("dt") else "--:--"
    # عنوان اولویت دارد؛ نام برند همیشه در انتها می‌آید.
    return (f"📰 <b>{html.escape(x['title'])}</b>\n\n"
            f"━━━━━━━━━━━━━━\n"
            f"🗞 منبع: {html.escape(x['source'])}\n"
            f"🕐 زمان: {tm}\n"
            f"━━━━━━━━━━━━━━\n\n"
            f"🌐 <b>جهان‌تاب | آخرین تحولات جهان</b>")

def post(x):
    kb={"inline_keyboard":[[{"text":"🔗 مشاهده خبر","url":x["url"]}]]}
    cap=format_caption(x)
    img=add_logo(download_image(x.get("image","")))
    if img and os.path.exists(img):
        with open(img,"rb") as f:
            res=telegram("sendPhoto",{"chat_id":CHAT_ID,"caption":cap,"parse_mode":"HTML","reply_markup":__import__("json").dumps(kb,ensure_ascii=False)}, {"photo":f})
    else:
        res=telegram("sendMessage",{"chat_id":CHAT_ID,"text":cap,"parse_mode":"HTML","disable_web_page_preview":"false","reply_markup":__import__("json").dumps(kb,ensure_ascii=False)})
    return bool(res.get("ok"))

def main():
    if not BOT_TOKEN:raise SystemExit("BOT_TOKEN is empty")
    sent_links={canonical(x) for x in load_set(SENT_FILE)};sent_titles=load_set(SENT_TITLES_FILE);sent_events=load_set(SENT_EVENTS_FILE)
    all_items=[]
    for source in SOURCES:
        got=[]
        for feed in discover_feeds(source):
            got=parse_feed(source,feed)
            if got:break
        if not got:got=html_fallback(source)
        all_items.extend(got)
        log.info("%s: %d items",source[0],len(got))
    selected=rank_and_dedupe(all_items,sent_links,sent_titles,sent_events)
    log.info("selected=%d",len(selected))
    for x in selected:
        if post(x):
            save_sent(x);time.sleep(POST_DELAY)

if __name__=="__main__":main()