import os
import random
import re
from typing import Optional
import httpx
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

load_dotenv()

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

# Города для поиска заведений (русскоязычные регионы)
CITIES = [
    "Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань",
    "Нижний Новгород", "Челябинск", "Самара", "Омск", "Ростов-на-Дону",
    "Уфа", "Красноярск", "Воронеж", "Пермь", "Волгоград",
    "Краснодар", "Сочи", "Тюмень", "Иркутск", "Владивосток",
    "Минск", "Алматы", "Астана", "Ташкент", "Киев", "Одесса", "Харьков",
    "Баку", "Тбилиси", "Ереван", "Бишкек", "Душанбе"
]

# Типы заведений (без больниц)
PLACE_TYPES = ["restaurant", "cafe", "bar", "hotel", "store", "gym", "spa"]

MIN_WORDS = 30  # Минимум слов в отзыве
MAX_CHARS = 1000  # Максимум символов в отзыве


def count_words(text: str) -> int:
    """Подсчёт слов в тексте."""
    return len(text.split())


def is_russian(text: str) -> bool:
    """Проверка, что текст на русском языке."""
    russian_chars = len(re.findall(r'[а-яёА-ЯЁ]', text))
    total_letters = len(re.findall(r'[a-zA-Zа-яёА-ЯЁ]', text))
    if total_letters == 0:
        return False
    return russian_chars / total_letters > 0.7


async def search_places(city: str, place_type: str) -> list:
    """Поиск заведений в городе."""
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.googleMapsUri"
    }
    data = {
        "textQuery": f"{place_type} в {city}",
        "languageCode": "ru",
        "maxResultCount": 20
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=data, headers=headers)
        if response.status_code == 200:
            result = response.json()
            return result.get("places", [])
    return []


# Перевод типов заведений
PLACE_TYPE_NAMES = {
    "restaurant": "Ресторан",
    "cafe": "Кафе",
    "bar": "Бар",
    "hotel": "Отель",
    "store": "Магазин",
    "hospital": "Больница",
    "gym": "Тренажёрный зал",
    "spa": "Спа",
    "bakery": "Пекарня",
    "shopping_mall": "ТЦ",
    "supermarket": "Супермаркет",
    "pharmacy": "Аптека",
    "bank": "Банк",
    "beauty_salon": "Салон красоты",
    "hair_salon": "Парикмахерская",
    "dentist": "Стоматология",
    "doctor": "Клиника",
    "clothing_store": "Магазин одежды",
}


async def get_place_reviews(place_id: str) -> tuple:
    """Получение отзывов для заведения."""
    url = f"https://places.googleapis.com/v1/places/{place_id}"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": "id,displayName,reviews,googleMapsUri,primaryType,addressComponents"
    }
    params = {"languageCode": "ru"}

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=params)
        if response.status_code == 200:
            result = response.json()

            # Извлекаем город и страну из addressComponents
            city = ""
            country = ""
            for comp in result.get("addressComponents", []):
                types = comp.get("types", [])
                if "locality" in types:
                    city = comp.get("longText", "")
                elif "country" in types:
                    country = comp.get("longText", "")

            place_type = result.get("primaryType", "")

            return (
                result.get("reviews", []),
                result.get("displayName", {}).get("text", ""),
                result.get("googleMapsUri", ""),
                city,
                country,
                place_type
            )
    return [], "", "", "", "", ""


async def find_toxic_review() -> Optional[dict]:
    """Поиск негативного отзыва на русском языке."""
    attempts = 0
    max_attempts = 15

    while attempts < max_attempts:
        attempts += 1
        city = random.choice(CITIES)
        place_type = random.choice(PLACE_TYPES)

        places = await search_places(city, place_type)
        if not places:
            continue

        random.shuffle(places)

        for place in places[:5]:
            place_id = place.get("id")
            if not place_id:
                continue

            reviews, place_name, maps_url, place_city, place_country, primary_type = await get_place_reviews(place_id)
            if not reviews:
                continue

            # Фильтруем негативные отзывы (1-2 звезды)
            negative_reviews = [
                r for r in reviews
                if r.get("rating", 5) <= 2
            ]

            # Фильтруем по длине и языку
            good_reviews = []
            for review in negative_reviews:
                text = review.get("text", {}).get("text", "") if isinstance(review.get("text"), dict) else review.get("text", "")
                if count_words(text) >= MIN_WORDS and len(text) <= MAX_CHARS and is_russian(text):
                    good_reviews.append({
                        "text": text,
                        "rating": review.get("rating", 1),
                        "author": review.get("authorAttribution", {}).get("displayName", "Аноним"),
                        "author_url": review.get("authorAttribution", {}).get("uri", ""),
                        "city": place_city,
                        "country": place_country,
                        "place_type": PLACE_TYPE_NAMES.get(primary_type, primary_type),
                        "place_name": place_name,
                        "maps_url": maps_url,
                        "relative_time": review.get("relativePublishTimeDescription", "")
                    })

            if good_reviews:
                # Берём самый негативный (сортируем по рейтингу, потом по длине)
                good_reviews.sort(key=lambda x: (x["rating"], -count_words(x["text"])))
                return good_reviews[0]

    return None


def format_review(review: dict) -> str:
    """Форматирование отзыва для отправки."""
    # Название заведения (жирное и кликабельное)
    text = f"🏢 <b><a href=\"{review['maps_url']}\">{review['place_name']}</a></b>"
    if review.get('place_type'):
        text += f" ({review['place_type']})"
    text += "\n"

    # Город и страна
    location_parts = []
    if review.get('city'):
        location_parts.append(review['city'])
    if review.get('country'):
        location_parts.append(review['country'])
    if location_parts:
        text += f"📍 {', '.join(location_parts)}\n"

    # Автор (кликабельный) и время
    if review.get('author_url'):
        text += f"👤 <a href=\"{review['author_url']}\">{review['author']}</a>"
    else:
        text += f"👤 {review['author']}"
    if review.get('relative_time'):
        text += f" • {review['relative_time']}"
    text += "\n\n"

    # Текст отзыва
    text += f"{review['text']}"

    return text


def get_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой 'Ещё'."""
    keyboard = [[InlineKeyboardButton("🔄 Ещё отзыв", callback_data="more")]]
    return InlineKeyboardMarkup(keyboard)


def get_start_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для стартового сообщения."""
    keyboard = [[InlineKeyboardButton("🚀 Погнали!", callback_data="more")]]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start."""
    await update.message.reply_text(
        "👋 Привет!\n"
        "Я бот, который собирает реальные негативные отзывы на русском языке из Google Maps.\n\n"
        "Здесь — честные эмоции, неожиданные формулировки и тот самый пользовательский опыт без прикрас. "
        "Иногда это просто полезно, а иногда — удивительно выразительно и талантливо.\n\n"
        "Нажми кнопку ниже, чтобы получить случайный отзыв от недовольного клиента 👇",
        reply_markup=get_start_keyboard()
    )


async def send_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправка отзыва."""
    query = update.callback_query
    await query.answer()

    # Убираем кнопку из старого сообщения
    await query.edit_message_reply_markup(reply_markup=None)

    # Отправляем статус поиска
    status_msg = await query.message.reply_text("🔍 Ищу токсичный отзыв...")

    review = await find_toxic_review()

    if review:
        await status_msg.edit_text(
            format_review(review),
            parse_mode="HTML",
            reply_markup=get_keyboard(),
            disable_web_page_preview=True
        )
    else:
        await status_msg.edit_text(
            "😔 Не удалось найти подходящий отзыв. Попробуй ещё раз!",
            reply_markup=get_keyboard()
        )


async def review_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /review."""
    msg = await update.message.reply_text("🔍 Ищу токсичный отзыв...")

    review = await find_toxic_review()

    if review:
        await msg.edit_text(
            format_review(review),
            parse_mode="HTML",
            reply_markup=get_keyboard(),
            disable_web_page_preview=True
        )
    else:
        await msg.edit_text(
            "😔 Не удалось найти подходящий отзыв. Попробуй ещё раз!",
            reply_markup=get_keyboard()
        )


def main() -> None:
    """Запуск бота."""
    if not TELEGRAM_TOKEN:
        print("Ошибка: TELEGRAM_TOKEN не установлен")
        return
    if not GOOGLE_API_KEY:
        print("Ошибка: GOOGLE_API_KEY не установлен")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("review", review_command))
    application.add_handler(CallbackQueryHandler(send_review, pattern="^more$"))

    print("Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
