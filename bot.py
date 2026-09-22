import asyncio
import aiohttp
import random
import json
import os
from datetime import datetime
from aiohttp import web
from telegram import Bot
from telegram.constants import ParseMode

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]
PORT = int(os.environ.get("PORT", 8080))

POST_INTERVAL = 1800
POSTS_PER_CYCLE = 1
SEEN_FILE = "seen.json"

CATEGORIES = [
    {"name": "Смартфоны", "query": "смартфон"},
    {"name": "Наушники", "query": "наушники"},
    {"name": "Кроссовки", "query": "кроссовки"},
    {"name": "Косметика", "query": "косметика"},
    {"name": "Игрушки", "query": "игрушки"},
    {"name": "Часы", "query": "часы"},
    {"name": "Сумки", "query": "сумка женская"},
    {"name": "Парфюм", "query": "парфюм"},
    {"name": "Кофты", "query": "кофта"},
    {"name": "Джинсы", "query": "джинсы"},
    {"name": "Посуда", "query": "посуда"},
    {"name": "Постельное", "query": "постельное бельё"},
    {"name": "Рюкзаки", "query": "рюкзак"},
    {"name": "Книги", "query": "книги"},
    {"name": "Спорт", "query": "спортивные товары"},
    {"name": "Зарядки", "query": "зарядное устройство"},
    {"name": "Чехлы", "query": "чехол для телефона"},
    {"name": "Витамины", "query": "витамины"},
    {"name": "Для кухни", "query": "кухонные принадлежности"},
    {"name": "Полотенца", "query": "полотенце"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
}

bot = Bot(token=BOT_TOKEN)
stats = {"posted": 0, "started": datetime.now().strftime("%Y-%m-%d %H:%M")}


def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            return set(json.load(open(SEEN_FILE)))
        except Exception:
            return set()
    return set()


def save_seen(seen):
    try:
        json.dump(list(seen)[-3000:], open(SEEN_FILE, "w"))
    except Exception as e:
        print("save_seen error:", e)


async def search_wb(session, query):
    url = "https://search.wb.ru/exactmatch/ru/common/v5/search"
    params = {
        "appType": "1", "curr": "rub", "dest": "-1257786",
        "query": query, "resultset": "catalog",
        "sort": "popular", "spp": "30",
    }
    try:
        async with session.get(url, params=params, headers=HEADERS) as r:
            if r.status != 200:
                print(f"WB status {r.status}")
                return []
            data = await r.json()
        return data.get("data", {}).get("products", [])
    except Exception as e:
        print("search error:", e)
        return []


def image_url(p):
    pid = p["id"]
    vol, part = pid // 100000, pid // 1000
    limits = [143, 287, 431, 719, 1007, 1061, 1115, 1169, 1313,
              1601, 1655, 1919, 2045, 2189, 2405, 2621, 2837,
              3053, 3269, 3485, 3701, 3917]
    basket = "23"
    for i, lim in enumerate(limits, 1):
        if vol <= lim:
            basket = f"{i:02d}"
            break
    return (f"https://basket-{basket}.wbbasket.ru/"
            f"vol{vol}/part{part}/{pid}/images/big/1.webp")


async def send_product(p):
    name = p.get("name", "Товар")
    brand = p.get("brand", "")
    price = p.get("salePriceU", 0) / 100
    rating = p.get("reviewRating", 0)
    feedbacks = p.get("feedbacks", 0)
    pid = p["id"]
    link = f"https://www.wildberries.ru/catalog/{pid}/detail.aspx"

    caption = f"🛍 <b>{name}</b>\n"
    if brand:
        caption += f"🏷 {brand}\n"
    caption += f"💰 <b>{price:.0f} ₽</b>\n"
    if rating:
        caption += f"⭐ {rating} ({feedbacks} отзывов)\n"
    caption += f"\n🔗 <a href='{link}'>Открыть на Wildberries</a>"

    try:
        await bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=image_url(p),
            caption=caption,
            parse_mode=ParseMode.HTML,
        )
        return True
    except Exception as e:
        print(f"send {pid} err: {e}")
        return False
async def handle_root(request):
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>WB Bot</title></head><body style="font-family:sans-serif;padding:40px">
<h1>🤖 WB Bot работает</h1>
<p>Опубликовано: <b>{stats['posted']}</b></p>
<p>Запущен: {stats['started']}</p>
</body></html>"""
    return web.Response(text=html, content_type="text/html")


async def start_web():
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_get("/health", lambda r: web.Response(text="ok"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"🌐 Web server на порту {PORT}")


async def main():
    asyncio.create_task(start_web())
    seen = load_seen()
    print(f"✅ Старт. Опубликовано ранее: {len(seen)}")
    cycle = 0

    async with aiohttp.ClientSession() as session:
        while True:
            cat = CATEGORIES[cycle % len(CATEGORIES)]
            print(f"\n🔎 Цикл {cycle+1}: {cat['name']}")
            products = await search_wb(session, cat["query"])
            print(f"   Найдено: {len(products)}")
            fresh = [p for p in products if p["id"] not in seen]
            print(f"   Новых: {len(fresh)}")

            if fresh:
                random.shuffle(fresh)
                posted = 0
                for p in fresh:
                    if posted >= POSTS_PER_CYCLE:
                        break
                    if await send_product(p):
                        seen.add(p["id"])
                        save_seen(seen)
                        stats["posted"] += 1
                        posted += 1
                        print(f"   ✅ Опубликован {p['id']}")
                        await asyncio.sleep(POST_INTERVAL)

            cycle += 1
            await asyncio.sleep(60)


if name == "__main__":
    asyncio.run(main())
