# Toxic Reviews Bot

Telegram-бот, который находит реальные негативные отзывы на русском языке из Google Maps.

**Попробовать:** [@ToxicReviewsBot](https://t.me/ToxicReviewsBot)

## Что делает

- Ищет заведения (рестораны, кафе, отели, магазины и др.) в странах СНГ
- Фильтрует отзывы: только 1-2 звезды, минимум 30 слов, максимум 1000 символов, на русском языке
- Показывает название заведения, город, автора и текст отзыва
- Кнопка "Ещё" для следующего случайного отзыва

## Технологии

- Python + python-telegram-bot
- Google Places API (New)
- JSONBin.io для статистики
- Деплой на Railway

## Переменные окружения

```
TELEGRAM_TOKEN=токен от @BotFather
GOOGLE_API_KEY=ключ Google Places API
JSONBIN_API_KEY=ключ JSONBin.io (опционально)
JSONBIN_BIN_ID=ID bin для статистики (опционально)
```

## Запуск локально

```bash
pip install -r requirements.txt
# Создай .env файл с токенами
python bot.py
```
