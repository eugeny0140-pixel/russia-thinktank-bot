# russia_thinktank_bot.py
import os
import re
import time
import logging
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
import schedule
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@time_n_John")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не задан в переменных окружения")

# ================== ИСТОЧНИКИ С РАБОЧИМИ RSS ==================
# Включены ТОЛЬКО те, у кого есть публичная RSS-лента и которые доступны из ЕС/США
SOURCES = [
    # Основные (проверены вами как рабочие)
    {"name": "Foreign Affairs", "url": "https://www.foreignaffairs.com/rss.xml"},
    {"name": "Reuters Institute", "url": "https://reutersinstitute.politics.ox.ac.uk/rss.xml"},
    {"name": "Bruegel", "url": "https://www.bruegel.org/rss.xml"},
    {"name": "E3G", "url": "https://www.e3g.org/feed/"},
    
    # Дополнительные (работают на Render, но блокируются из РФ)
    {"name": "Chatham House", "url": "https://www.chathamhouse.org/rss.xml"},
    {"name": "CSIS", "url": "https://www.csis.org/rss.xml"},
    {"name": "Atlantic Council", "url": "https://www.atlanticcouncil.org/feed/"},
    {"name": "RAND Corporation", "url": "https://www.rand.org/rss.xml"},
    {"name": "CFR", "url": "https://www.cfr.org/rss/"},
    {"name": "Carnegie Endowment", "url": "https://carnegieendowment.org/rss.xml"},
    {"name": "The Economist", "url": "https://www.economist.com/latest/rss.xml"},
    {"name": "Bloomberg Politics", "url": "https://www.bloomberg.com/politics/feeds/site.xml"},
]

# ================== КЛЮЧЕВЫЕ СЛОВА ==================
KEYWORDS = [
    r"\brussia\b", r"\brussian\b", r"\bputin\b", r"\bmoscow\b", r"\bkremlin\b",
    r"\bukraine\b", r"\bukrainian\b", r"\bzelensky\b", r"\bkyiv\b", r"\bkiev\b",
    r"\bcrimea\b", r"\bdonbas\b", r"\bdonetsk\b", r"\bluhansk\b",
    r"\bsanction[s]?\b", r"\bembargo\b", r"\brestrict\b", r"\bprohibit\b",
    r"\bgazprom\b", r"\brosgaz\b", r"\bnord\s?stream\b", r"\byamal\b",
    r"\bwagner\b", r"\bprigozhin\b", r"\bshoigu\b", r"\bmedvedev\b", r"\bpeskov\b", r"\blavrov\b",
    r"\bnato\b", r"\beuropa\b", r"\beuropean\s?union\b", r"\bgermany\b", r"\bfrance\b", r"\busa\b", r"\buk\b",
    r"\bgeopolitic\b", r"\bsecurity\b", r"\bdefense\b", r"\bmilitary\b", r"\bwar\b", r"\bconflict\b",
    r"\bruble\b", r"\brub\b", r"\beconomy\b", r"\benergy\b", r"\boil\b", r"\bgas\b",
    r"\bmoscow\b", r"\bst\s?petersburg\b", r"\bchechnya\b", r"\bdagestan\b",
    r"\bsoviet\b", r"\bussr\b", r"\bpost\W?soviet\b"
]

MAX_SEEN = 5000
MAX_PER_RUN = 12  # увеличено из-за большего числа источников

# Глобальная история (в памяти, так как Render не сохраняет файлы)
seen_links = set()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ================== ФУНКЦИИ ==================

def clean_text(t):
    return re.sub(r"\s+", " ", t).strip()

def translate_to_russian(text):
    try:
        return GoogleTranslator(source='auto', target='ru').translate(text)
    except Exception as e:
        log.warning(f"⚠️ Перевод не удался: {e}")
        return text

def get_summary(title):
    low = title.lower()
    if re.search(r"sanction|embargo|restrict|prohibit", low):
        return "Введены новые санкции или ограничения."
    if re.search(r"attack|strike|bomb|war|invasion|conflict|combat", low):
        return "Сообщается о военных действиях или ударах."
    if re.search(r"putin|kremlin|peskov|moscow", low):
        return "Заявление или действие со стороны Кремля."
    if re.search(r"economy|rubl?e|oil|gas|gazprom|nord\s?stream|energy", low):
        return "Новости экономики, нефти, газа или рубля."
    if re.search(r"diplomat|talks|negotiat|meeting|lavrov|foreign\s?minist", low):
        return "Дипломатические переговоры или контакты."
    if re.search(r"wagner|prigozhin|shoigu|medvedev|defense|minist", low):
        return "События с российскими военными или политиками."
    if re.search(r"ukraine|zelensky|kyiv|kiev|crimea|donbas", low):
        return "События, связанные с Украиной и прилегающими регионами."
    if re.search(r"nato|europa|european\s?union|germany|france|usa|uk|biden|truss|sunak", low):
        return "Реакция западных стран или НАТО на события с участием России."
    return "Аналитика, связанная с Россией или постсоветским пространством."

def fetch_rss_news():
    global seen_links
    result = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    for src in SOURCES:
        if len(result) >= MAX_PER_RUN:
            break
        try:
            url = src["url"].strip()
            log.info(f"📡 {src['name']}")
            resp = requests.get(url, timeout=30, headers=headers)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "xml")

            for item in soup.find_all("item"):
                if len(result) >= MAX_PER_RUN:
                    break

                title = clean_text(item.title.get_text()) if item.title else ""
                link = (item.link.get_text() or item.guid.get_text()).strip() if item.link or item.guid else ""

                if not title or not link or link in seen_links:
                    continue

                if not any(re.search(kw, title, re.IGNORECASE) for kw in KEYWORDS):
                    continue

                ru_title = translate_to_russian(title)
                summary = get_summary(title)
                # Экранируем спецсимволы для Markdown
                safe_title = ru_title.replace("[", "\\[").replace("]", "\\]").replace("(", "\\(").replace(")", "\\)")
                msg = f"[{safe_title}]({link})\n\n{summary}"
                result.append({"msg": msg, "link": link})

        except Exception as e:
            log.error(f"❌ {src['name']}: {e}")

    return result

def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, data=payload, timeout=15)
        if r.status_code == 200:
            log.info("✅ Отправлено")
        else:
            log.error(f"❌ Telegram error: {r.text}")
    except Exception as e:
        log.error(f"❌ Исключение: {e}")

def job():
    global seen_links
    log.info("🔄 Проверка новостей по России и геополитике...")
    news = fetch_rss_news()
    if not news:
        log.info("📭 Нет релевантных публикаций.")
        return

    for item in news:
        send_to_telegram(item["msg"])
        seen_links.add(item["link"])
        if len(seen_links) > MAX_SEEN:
            seen_links = set(list(seen_links)[-4000:])
        time.sleep(1)

# ================== ЗАПУСК ==================
if __name__ == "__main__":
    log.info("🚀 Бот запущен на Render. Источников: %d", len(SOURCES))
    job()
    schedule.every(30).minutes.do(job)

    while True:
        schedule.run_pending()
        time.sleep(1)