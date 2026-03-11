import os
import sys
import logging
import asyncio
import random
from aiohttp import web
from telethon import TelegramClient, events, functions
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, ChatAdminRequiredError

# Подключаем читалку паролей
from dotenv import load_dotenv
load_dotenv()

# ==========================================
# 1. ЖУРНАЛ (ЛОГИ)
# ==========================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ArchiveBot")

# ==========================================
# 2. ПРОВЕРКА НАСТРОЕК
# ==========================================
def load_config():
    try:
        config = {
            "API_ID": int(os.environ.get("API_ID", 0)),
            "API_HASH": os.environ.get("API_HASH", ""),
            "SESSION": os.environ.get("STRING_SESSION", ""),
            "ARCHIVE_GROUP_ID": int(os.environ.get("ARCHIVE_GROUP_ID", 0)),
            "SECOND_GROUP_ID": int(os.environ.get("SECOND_ARCHIVE_GROUP_ID", 0)),
            "PORT": int(os.environ.get("PORT", 8080))
        }
    except ValueError as e:
        logger.error(f"Ошибка чтения настроек: {e}")
        sys.exit(1)

    if not all([config["API_ID"], config["API_HASH"], config["SESSION"], config["ARCHIVE_GROUP_ID"]]):
        logger.error("КРИТИЧЕСКАЯ ОШИБКА: Не заполнены все секретные переменные!")
        sys.exit(1)
        
    return config

CONFIG = load_config()
topics_cache = {}

# ==========================================
# 3. ВЕБ-СЕРВЕР (Для Render)
# ==========================================
async def handle_web_request(request):
    return web.Response(text="[OK] ArchiveBot is running 24/7.", status=200)

async def start_web_server():
    app = web.Application()
    app.add_routes([web.get('/', handle_web_request)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', CONFIG["PORT"])
    await site.start()
    logger.info(f"Веб-сервер запущен на порту {CONFIG['PORT']}")

# ==========================================
# 4. ЛОГИКА ПЕРЕСЫЛКИ (Обработчик)
# ==========================================
async def archive_message_handler(event):
    chat_id = event.chat_id
    client = event.client # Берем бота прямо из события

    # Игнорируем сообщения из самого Архива, системные сервисы, каналы и ГРУППЫ
    if chat_id == CONFIG["ARCHIVE_GROUP_ID"] or chat_id == 777000 or event.is_channel or event.is_group:
        return

    try:
        chat = await event.get_chat()
        sender_name = getattr(chat, 'title', getattr(chat, 'first_name', 'Неизвестный'))
        topic_title = f"{sender_name} [{chat_id}]"

        target_groups =[CONFIG.get("ARCHIVE_GROUP_ID", 0), CONFIG.get("SECOND_ARCHIVE_GROUP_ID", 0)]
        # Создаем тему, если ее нет
        for group_id in target_groups:
            if group_id == 0: 
                continue # Пропускаем, если ID группы не заполнен

            # Создаем тему в этой конкретной группе, если её еще нет в кэше
            cache_key = f"{chat_id}_{group_id}"
            if cache_key not in topics_cache:
                logger.info(f"Создаю тему в группе {group_id}...")
                try:
                    topic = await client(functions.channels.CreateForumTopicRequest(
                        channel=group_id,
                        title=topic_title,
                        icon_color=0x6FB9F0 
                    ))
                    topics_cache[cache_key] = topic.updates[0].id
                except ChatAdminRequiredError:
                    logger.error(f"Нет прав на создание тем в группе {group_id}! Проверьте права бота.")
                    continue # Идем к следующей группе, не прерывая работу
                except FloodWaitError as e:
                    logger.warning(f"Ждем {e.seconds} секунд от спам-фильтра...")
                    await asyncio.sleep(e.seconds)
                    continue

            target_topic_id = topics_cache[cache_key]

            # Пересылаем сообщение напрямую в эту группу и в эту тему
            await client(functions.messages.ForwardMessagesRequest(
                from_peer=chat_id,
                id=[event.message.id],
                to_peer=group_id,
                top_msg_id=target_topic_id,
                random_id=[random.randint(1, 999999999)]
            ))
        
        logger.info(f"Сообщение от {sender_name} успешно сохранено в архив.")

    except Exception as e:
        logger.error(f"Ошибка при пересылке: {e}")

# ==========================================
# 5. ГЛАВНЫЙ ЗАПУСК
# ==========================================
async def main():
    await start_web_server()
    client = TelegramClient(StringSession(CONFIG["SESSION"]), CONFIG["API_ID"], CONFIG["API_HASH"])
    client.add_event_handler(archive_message_handler, events.NewMessage())
    
    logger.info("Подключение к серверам Telegram...")
    await client.start()
    logger.info("Бот-архиватор успешно авторизован и готов к работе!")
    
    await client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:

        logger.info("Программа остановлена вручную.")
