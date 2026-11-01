import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
from bs4 import BeautifulSoup
import aiohttp
from fake_useragent import UserAgent

BOT_TOKEN = "9050912306:AAFuWt9zUAn95ABZYscFJovfI7mAYALL4YU"
ADMIN_ID = 1617564728

CHECK_INTERVAL = 45

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
ua = UserAgent()

state = {
    "url": None,
    "task": None,
    "seen_ids": set()
}

kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Статус"), KeyboardButton(text="⏹ Остановить")]
    ],
    resize_keyboard=True
)

async def fetch_page(session: aiohttp.ClientSession, url: str) -> str:
    headers = {
        "User-Agent": ua.random,
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        async with session.get(url, headers=headers, timeout=15) as resp:
            if resp.status == 200:
                return await resp.text()
    except Exception as e:
        logging.error(f"Ошибка запроса: {e}")
    return ""

def parse_items(html: str):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    cards = soup.find_all("div", {"data-marker": "item"})
    for card in cards:
        item_id = card.get("data-item-id")
        title_tag = card.find("a", {"data-marker": "item-title"})
        price_tag = card.find("meta", {"itemprop": "price"})
        
        if not item_id or not title_tag:
            continue
            
        items.append({
            "id": item_id,
            "title": title_tag.get("title", "").strip() or title_tag.text.strip(),
            "price": f"{price_tag.get('content')} ₽" if price_tag else "Не указана",
            "link": "https://www.avito.ru" + title_tag.get("href", "")
        })
    return items

async def tracker_loop(chat_id: int):
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        initial_html = await fetch_page(session, state["url"])
        if initial_html:
            for item in parse_items(initial_html):
                state["seen_ids"].add(item["id"])
        
        await bot.send_message(
            chat_id, 
            f"✅ <b>Мониторинг запущен!</b>\n"
            f"Запомнено объявлений: {len(state['seen_ids'])}\n"
            f"Интервал: {CHECK_INTERVAL} сек.\n"
            f"Жду свежие объявления...", 
            parse_mode="HTML"
        )
        
        while True:
            await asyncio.sleep(CHECK_INTERVAL)
            html = await fetch_page(session, state["url"])
            if not html:
                continue

            items = parse_items(html)
            for item in reversed(items):
                if item["id"] not in state["seen_ids"]:
                    state["seen_ids"].add(item["id"])
                    text = (
                        f"🔔 <b>Новое объявление!</b>\n\n"
                        f"📌 <b>{item['title']}</b>\n"
                        f"💰 {item['price']}\n\n"
                        f"🔗 <a href='{item['link']}'>Открыть на Авито</a>"
                    )
                    await bot.send_message(chat_id, text, parse_mode="HTML")
                    await asyncio.sleep(1)

@dp.message(CommandStart())
async def cmd_start(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        "👋 Привет! Отправь мне **ссылку на поиск Авито** (с выставленной сортировкой «По дате»).\n\n"
        "Я сразу начну следить за ней и присылать каждое новое объявление.",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@dp.message(F.text == "⏹ Остановить")
async def stop_tracking(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    if state["task"] and not state["task"].done():
        state["task"].cancel()
        state["task"] = None
        state["url"] = None
        state["seen_ids"].clear()
        await message.answer("🛑 Мониторинг остановлен. Отправьте новую ссылку для перезапуска.")
    else:
        await message.answer("Сейчас мониторинг не работает.")

@dp.message(F.text == "📊 Статус")
async def check_status(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    if state["task"] and not state["task"].done():
        await message.answer(
            f"🟢 <b>Мониторинг активен</b>\n\n"
            f"🔗 <b>Ссылка:</b> {state['url']}\n"
            f"📦 <b>В памяти:</b> {len(state['seen_ids'])} шт.",
            parse_mode="HTML"
        )
    else:
        await message.answer("⚪ Мониторинг выключен. Отправьте ссылку на Авито.")

@dp.message(F.text.startswith("http"))
async def receive_link(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    url = message.text.strip()
    if "avito.ru" not in url:
        await message.answer("❌ Ссылка должна вести на avito.ru!")
        return

    if state["task"] and not state["task"].done():
        state["task"].cancel()

    state["url"] = url
    state["seen_ids"].clear()
    state["task"] = asyncio.create_task(tracker_loop(message.chat.id))
    await message.answer("⏳ Анализирую страницу и включаю отслеживание...")

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
