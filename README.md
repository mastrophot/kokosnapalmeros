# kokosnapalmeros - Автоматична Instagram Галерея

Фотогалерея з автоматичною синхронізацією фото з Instagram профілю [@kokosnapalmeros](https://instagram.com/kokosnapalmeros).

Ця версія працює через **офіційний Instagram Graph API** (без неофіційного scraper), тому значно стабільніша для GitHub Actions.

## Швидкий старт

### 1) Встановлення

```bash
# Python залежностей немає (std lib), але команда безпечна:
pip install -r requirements.txt

# Node.js залежності для генерації HTML
npm install
```

### 2) Налаштування змінних оточення (локально)

```bash
export IG_USER_ID="YOUR_IG_BUSINESS_ACCOUNT_ID"
export IG_ACCESS_TOKEN="YOUR_PAGE_OR_USER_TOKEN"
export INSTAGRAM_USERNAME="kokosnapalmeros"  # опційно
```

### 3) Синхронізація

```bash
# Завантажити останні 20 постів (тільки фото, без відео/reels)
npm run sync

# Тестовий режим (тільки metadata, без запису файлів)
npm run sync:test

# Оновити HTML галерею
npm run update-gallery

# Повний цикл
npm run build
```

## GitHub Actions (автоматично)

Workflow `.github/workflows/sync-instagram.yml` запускається раз на 12 годин і робить:
1. Завантаження фото через Graph API
2. Генерацію `index.html` + `gallery-items.js`
3. Commit + push змін

### Required GitHub Secrets

Додай у репозиторій:
- `IG_USER_ID` - ID Instagram Business Account
- `IG_ACCESS_TOKEN` - Access token для Graph API

Опційно:
- Repository variable `INSTAGRAM_USERNAME` (якщо не задано, використовується `kokosnapalmeros`)

## Як отримати IG_USER_ID і IG_ACCESS_TOKEN (безкоштовно)

Потрібно один раз налаштувати Meta:
1. Instagram акаунт має бути `Professional` і прив'язаний до Facebook Page.
2. Створи застосунок на Meta for Developers (тип `Business`).
3. Отримай short-lived user token з правами `instagram_basic`, `pages_show_list`, `pages_read_engagement`.
4. Обміняй на long-lived user token:

```bash
curl "https://graph.facebook.com/v22.0/oauth/access_token?grant_type=fb_exchange_token&client_id=$APP_ID&client_secret=$APP_SECRET&fb_exchange_token=$SHORT_LIVED_USER_TOKEN"
```

5. Отримай сторінки і page access token:

```bash
curl "https://graph.facebook.com/v22.0/me/accounts?access_token=$LONG_LIVED_USER_TOKEN"
```

6. Отримай IG user id:

```bash
curl "https://graph.facebook.com/v22.0/$PAGE_ID?fields=instagram_business_account&access_token=$PAGE_ACCESS_TOKEN"
```

7. Значення `instagram_business_account.id` використовуй як `IG_USER_ID`, а page token як `IG_ACCESS_TOKEN`.

## Структура проекту

```text
.
├── images/              # Зображення
├── index.html           # Сторінка галереї
├── gallery-items.js     # Відкладене завантаження фото
├── gallery-data.json    # Метадані постів
├── sync-instagram.py    # Синхронізація через Graph API
├── update-gallery.js    # Оновлення HTML
└── .github/workflows/   # Автоматичний запуск
```

## Важливо

- Скрипт завантажує тільки `IMAGE` і фото з `CAROUSEL_ALBUM`.
- `VIDEO`/`REELS` пропускаються.
- Не зберігай токени у файлах репозиторію, тільки в GitHub Secrets.

## Ліцензія

MIT
