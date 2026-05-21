import os
import json
import threading
import tempfile
import glob
from datetime import datetime

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, request
import requests
from yt_dlp import YoutubeDL
from youtube_search import YoutubeSearch

# ===== КОНФИГ =====
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8076231194:AAHlIZ6vVBd2lfM2IwBkEH37O2A73anHYTw')
HISTORY_FILE = 'history.json'
MAX_HISTORY = 15

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
history_lock = threading.Lock()

# ===== ИСТОРИЯ =====
def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_history(data):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_to_history(user_id, title, video_id, media_type):
    with history_lock:
        data = load_history()
        uid = str(user_id)
        if uid not in data:
            data[uid] = []
        data[uid] = [e for e in data[uid] if e['video_id'] != video_id]
        data[uid].insert(0, {
            'title': title,
            'video_id': video_id,
            'type': media_type,
            'date': datetime.now().strftime('%d.%m.%Y %H:%M')
        })
        data[uid] = data[uid][:MAX_HISTORY]
        save_history(data)

def get_history(user_id):
    with history_lock:
        data = load_history()
        return data.get(str(user_id), [])

# ===== ПОИСК =====
def search_music(query, max_results=5):
    try:
        results = YoutubeSearch(query, max_results=max_results).to_dict()
        return results
    except Exception as e:
        print(f"Ошибка поиска: {e}")
        return []

# ===== ОБЛОЖКА =====
def download_thumb(thumb_url, path):
    try:
        r = requests.get(thumb_url, timeout=10)
        with open(path, 'wb') as f:
            f.write(r.content)
        return True
    except Exception:
        return False

# ===== ОБРАБОТЧИКИ КОМАНД И СООБЩЕНИЙ =====
@bot.message_handler(commands=['start'])
def cmd_start(message):
    name = message.from_user.first_name
    text = (
        f"👋 Привет, *{name}*!\n\n"
        "🎵 Я музыкальный бот — ищу и скачиваю треки и видео с YouTube.\n\n"
        "📌 *Что я умею:*\n"
        "• Поиск и скачивание аудио 🎵\n"
        "• Скачивание видео с выбором качества 🎬\n"
        "• Скачивание целых плейлистов 📋\n"
        "• История твоих загрузок 📜\n"
        "• Топ трендовых треков 🔥\n\n"
        "🔍 Просто напиши название трека или исполнителя!"
    )
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🔥 Тренды", callback_data="trending"),
        InlineKeyboardButton("📜 История", callback_data="history"),
        InlineKeyboardButton("❓ Помощь", callback_data="help")
    )
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data == 'help')
def help_callback(call):
    text = (
        "📖 *Как пользоваться ботом:*\n\n"
        "1️⃣ Напиши название песни или исполнителя\n"
        "2️⃣ Выбери трек из результатов\n"
        "3️⃣ Выбери формат: 🎵 аудио или 🎬 видео\n"
        "4️⃣ Для видео — выбери качество\n\n"
        "📋 *Плейлисты:*\n"
        "Отправь ссылку на YouTube плейлист — скачаю всё аудио\n\n"
        "🔥 *Тренды:*\n"
        "Кнопка «Тренды» — популярные треки прямо сейчас\n\n"
        "📜 *История:*\n"
        "Кнопка «История» — твои последние загрузки"
    )
    bot.send_message(call.message.chat.id, text, parse_mode='Markdown')
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == 'history')
def history_callback(call):
    history = get_history(call.from_user.id)
    if not history:
        bot.send_message(call.message.chat.id, "📭 История пока пуста. Начни скачивать треки!")
        bot.answer_callback_query(call.id)
        return

    markup = InlineKeyboardMarkup()
    for entry in history:
        icon = '🎵' if entry['type'] == 'audio' else '🎬'
        short = entry['title'][:35] + '...' if len(entry['title']) > 35 else entry['title']
        markup.add(InlineKeyboardButton(
            text=f"{icon} {short} — {entry['date']}",
            callback_data=f"pick_{entry['video_id']}"
        ))
    bot.send_message(call.message.chat.id, "📜 *Твоя история загрузок:*\nНажми на трек чтобы скачать снова 👇",
                     parse_mode='Markdown', reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == 'trending')
def trending_callback(call):
    bot.send_chat_action(call.message.chat.id, 'typing')
    msg = bot.send_message(call.message.chat.id, "🔥 Ищу трендовые треки...")

    results = search_music("trending music 2025", max_results=8)

    if not results:
        bot.edit_message_text("❌ Не удалось загрузить тренды.", call.message.chat.id, msg.message_id)
        bot.answer_callback_query(call.id)
        return

    markup = InlineKeyboardMarkup()
    for res in results:
        short = res['title'][:38] + '...' if len(res['title']) > 38 else res['title']
        markup.add(InlineKeyboardButton(
            text=f"🎵 {short} ({res['duration']})",
            callback_data=f"pick_{res['id']}"
        ))

    bot.edit_message_text(
        "🔥 *Трендовые треки прямо сейчас:*\nВыбери и скачай 👇",
        call.message.chat.id, msg.message_id,
        parse_mode='Markdown',
        reply_markup=markup
    )
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: m.text and ('youtube.com/playlist' in m.text or ('list=' in m.text and 'youtube.com' in m.text)))
def handle_playlist(message):
    url = message.text.strip()
    chat_id = message.chat.id
    msg = bot.send_message(chat_id, "📋 Анализирую плейлист...")

    try:
        with YoutubeDL({'quiet': True, 'extract_flat': True, 'nocheckcertificate': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            entries = info.get('entries', [])
            pl_title = info.get('title', 'Плейлист')

        if not entries:
            bot.edit_message_text("❌ Плейлист пустой или недоступен.", chat_id, msg.message_id)
            return

        count = len(entries)
        bot.edit_message_text(
            f"📋 *{pl_title}*\n🎵 Треков: {count}\n\nНачинаю скачивание...",
            chat_id, msg.message_id, parse_mode='Markdown'
        )

        ok = 0
        fail = 0

        for i, entry in enumerate(entries, 1):
            video_id = entry.get('id')
            if not video_id:
                fail += 1
                continue

            video_url = f"https://www.youtube.com/watch?v={video_id}"
            uid_prefix = f"{message.from_user.id}_{video_id}_pl"
            tmp_dir = tempfile.gettempdir()
            outtmpl = os.path.join(tmp_dir, f"{uid_prefix}.%(ext)s")

            try:
                bot.send_chat_action(chat_id, 'upload_audio')
                bot.edit_message_text(
                    f"📋 *{pl_title}*\n⏳ Скачиваю {i}/{count}...",
                    chat_id, msg.message_id, parse_mode='Markdown'
                )

                ydl_opts = {
                    'format': 'bestaudio/best',
                    'outtmpl': outtmpl,
                    'nocheckcertificate': True,
                    'noplaylist': True,
                    'quiet': True,
                }

                with YoutubeDL(ydl_opts) as ydl:
                    track_info = ydl.extract_info(video_url, download=True)
                    title = track_info.get('title', 'Unknown')
                    performer = track_info.get('uploader', 'YouTube')
                    thumb_url = track_info.get('thumbnail')
                    duration = track_info.get('duration', 0)

                downloaded = glob.glob(os.path.join(tmp_dir, f"{uid_prefix}.*"))
                if not downloaded:
                    fail += 1
                    continue

                audio_file = downloaded[0]
                thumb_path = os.path.join(tmp_dir, f"{uid_prefix}_thumb.jpg")
                if not download_thumb(thumb_url, thumb_path):
                    thumb_path = None

                with open(audio_file, 'rb') as f:
                    thumb_obj = open(thumb_path, 'rb') if thumb_path and os.path.exists(thumb_path) else None
                    bot.send_audio(
                        chat_id, f,
                        caption=f"🎵 {i}/{count} — *{title}*",
                        parse_mode='Markdown',
                        title=title,
                        performer=performer,
                        duration=duration,
                        thumbnail=thumb_obj
                    )
                    if thumb_obj:
                        thumb_obj.close()

                add_to_history(message.from_user.id, title, video_id, 'audio')
                ok += 1

            except Exception as e:
                print(f"Ошибка трека {video_id}: {e}")
                fail += 1

            finally:
                for fp in glob.glob(os.path.join(tmp_dir, f"{uid_prefix}*")):
                    try:
                        os.remove(fp)
                    except Exception:
                        pass

        bot.edit_message_text(
            f"✅ Плейлист *{pl_title}* готов!\n\n"
            f"✔️ Успешно: {ok}\n❌ Пропущено: {fail}",
            chat_id, msg.message_id, parse_mode='Markdown'
        )

    except Exception as e:
        bot.send_message(chat_id, f"🛑 Ошибка плейлиста:\n`{str(e)}`", parse_mode='Markdown')

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    query = message.text.strip()
    bot.send_chat_action(message.chat.id, 'typing')
    results = search_music(query, max_results=5)

    if not results:
        bot.reply_to(message, "❌ Ничего не найдено. Попробуй другой запрос.")
        return

    markup = InlineKeyboardMarkup()
    for res in results:
        short = res['title'][:38] + '...' if len(res['title']) > 38 else res['title']
        markup.add(InlineKeyboardButton(
            text=f"🎵 {short} ({res['duration']})",
            callback_data=f"pick_{res['id']}"
        ))

    bot.send_message(
        message.chat.id,
        f"🔍 Результаты по запросу: *{query}*\nВыбери трек 👇",
        parse_mode='Markdown',
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith('pick_'))
def handle_pick(call):
    video_id = call.data.split('_', 1)[1]
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    bot.answer_callback_query(call.id, "⏳ Загружаю информацию...")

    try:
        with YoutubeDL({'quiet': True, 'nocheckcertificate': True}) as ydl:
            info = ydl.extract_info(video_url, download=False)
            title = info.get('title', 'Неизвестно')
            duration = info.get('duration', 0)
            thumb_url = info.get('thumbnail', '')
            uploader = info.get('uploader', '')
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Ошибка получения информации: {e}")
        return

    mins = duration // 60
    secs = duration % 60
    short = title[:50] + '...' if len(title) > 50 else title

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🎵 Аудио (лучшее качество)", callback_data=f"dl_audio_{video_id}"))
    markup.row(
        InlineKeyboardButton("🎬 360p", callback_data=f"dl_video_360_{video_id}"),
        InlineKeyboardButton("🎬 720p", callback_data=f"dl_video_720_{video_id}"),
        InlineKeyboardButton("🎬 1080p", callback_data=f"dl_video_1080_{video_id}"),
    )
    markup.add(InlineKeyboardButton("❌ Отмена", callback_data="cancel"))

    caption = (
        f"🎶 *{short}*\n"
        f"👤 {uploader}\n"
        f"⏱ {mins}:{secs:02d}\n\n"
        "Выбери формат 👇"
    )

    if thumb_url:
        try:
            img_data = requests.get(thumb_url, timeout=8).content
            bot.send_photo(
                call.message.chat.id,
                img_data,
                caption=caption,
                parse_mode='Markdown',
                reply_markup=markup
            )
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except Exception:
                pass
            return
        except Exception:
            pass

    try:
        bot.edit_message_text(caption, call.message.chat.id, call.message.message_id,
                              parse_mode='Markdown', reply_markup=markup)
    except Exception:
        bot.send_message(call.message.chat.id, caption, parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith('dl_'))
def handle_download(call):
    parts = call.data.split('_')
    if parts[1] == 'audio':
        media_type = 'audio'
        quality = None
        video_id = '_'.join(parts[2:])
    else:
        media_type = 'video'
        quality = parts[2]
        video_id = '_'.join(parts[3:])

    video_url = f"https://www.youtube.com/watch?v={video_id}"
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    uid_prefix = f"{user_id}_{video_id}"
    tmp_dir = tempfile.gettempdir()

    try:
        bot.answer_callback_query(call.id, "⏳ Начинаю загрузку...")
    except Exception:
        pass

    status_text = "⏳ Скачиваю аудио..." if media_type == 'audio' else f"⏳ Скачиваю видео {quality}p..."
    try:
        bot.edit_message_caption(status_text, chat_id, call.message.message_id)
    except Exception:
        try:
            bot.edit_message_text(status_text, chat_id, call.message.message_id)
        except Exception:
            pass

    if media_type == 'audio':
        outtmpl = os.path.join(tmp_dir, f"{uid_prefix}_audio.%(ext)s")
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': outtmpl,
            'nocheckcertificate': True,
            'noplaylist': True,
            'quiet': True,
        }
    else:
        quality_fmt = {
            '360': 'bestvideo[height<=360]+bestaudio/best[height<=360]/best',
            '720': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
            '1080': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best',
        }
        outtmpl = os.path.join(tmp_dir, f"{uid_prefix}_video.%(ext)s")
        ydl_opts = {
            'format': quality_fmt.get(quality, 'best'),
            'outtmpl': outtmpl,
            'nocheckcertificate': True,
            'noplaylist': True,
            'quiet': True,
            'merge_output_format': 'mp4',
        }

    media_file = None
    thumb_path = None

    try:
        bot.send_chat_action(chat_id, 'upload_audio' if media_type == 'audio' else 'upload_video')

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            title = info.get('title', 'Unknown')
            performer = info.get('uploader', 'YouTube')
            thumb_url = info.get('thumbnail')
            duration = info.get('duration', 0)

        suffix = 'audio' if media_type == 'audio' else 'video'
        pattern = os.path.join(tmp_dir, f"{uid_prefix}_{suffix}.*")
        downloaded = glob.glob(pattern)

        if not downloaded:
            bot.send_message(chat_id, "❌ Файл не найден после скачивания.")
            return

        media_file = downloaded[0]

        if thumb_url:
            thumb_path = os.path.join(tmp_dir, f"{uid_prefix}_thumb.jpg")
            if not download_thumb(thumb_url, thumb_path):
                thumb_path = None

        with open(media_file, 'rb') as f:
            thumb_obj = open(thumb_path, 'rb') if thumb_path and os.path.exists(thumb_path) else None

            if media_type == 'audio':
                bot.send_audio(
                    chat_id, f,
                    caption=f"✅ *{title}*",
                    parse_mode='Markdown',
                    title=title,
                    performer=performer,
                    duration=duration,
                    thumbnail=thumb_obj
                )
            else:
                bot.send_video(
                    chat_id, f,
                    caption=f"✅ *{title}* [{quality}p]",
                    parse_mode='Markdown',
                    duration=duration,
                    supports_streaming=True,
                    thumbnail=thumb_obj
                )

            if thumb_obj:
                thumb_obj.close()

        add_to_history(user_id, title, video_id, media_type)

    except Exception as e:
        bot.send_message(chat_id, f"🛑 Ошибка загрузки:\n`{str(e)}`", parse_mode='Markdown')

    finally:
        if media_file and os.path.exists(media_file):
            os.remove(media_file)
        if thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda c: c.data == 'cancel')
def handle_cancel(call):
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass
    bot.answer_callback_query(call.id, "❌ Отменено")

# ===== ВЕБХУК И ЗАПУСК =====
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL')  # Render сам задаёт эту переменную
if not WEBHOOK_URL:
    # fallback для локальной отладки
    WEBHOOK_URL = 'https://your-app.onrender.com'  # замените на реальный URL после деплоя

@app.route('/')
def index():
    return "Bot is running", 200

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    else:
        return '', 403

def set_webhook():
    bot.remove_webhook()
    webhook_url = f"{WEBHOOK_URL}/{BOT_TOKEN}"
    bot.set_webhook(url=webhook_url)
    print(f"Webhook установлен: {webhook_url}")

if __name__ == '__main__':
    # Устанавливаем вебхук при старте
    set_webhook()
    # Запускаем Flask-сервер
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
