# kokosnapalmeros — Візуальний Фотоархів

Статична веб-галерея з автоматичною щоденною синхронізацією фото з публічного Instagram-профілю [@kokosnapalmeros](https://www.instagram.com/kokosnapalmeros/) на базі GitHub Actions та GitHub Pages.

Живий сайт: https://mastrophot.github.io/kokosnapalmeros/

## Архітектура

- **Дворівневий пайплайн синхронізації (`sync-instagram.py`):**
  1. **Основний канал:** авторизований пагінований GraphQL-запит профілю (`IG_SESSION`) через `curl_cffi` з актуальною TLS-імперсонацією Chrome.
  2. **Резервний канал:** анонімний парсинг HTML Relay Preloader без куків.
- **Дворівневе зберігання зображень:**
  - `images/` — некропнуті оригінали максимальної роздільної здатності з вирізаним другим потоком Ultra-HDR GainMap (`MPF` / `hdrgm`) для плавного рендеру без втрати якості SDR-кадру.
  - `thumbs/` — оптимізовані легкі прев'ю (`640px`) для миттєвого завантаження сітки.
- **Zero-dependency генератор статики (`update-gallery.js`):** працює на чистих вбудованих модулях Node.js (`fs`, `path`) без зовнішніх npm-пакетів, генеруючи `index.html` та компактний індекс `gallery-items.js`.
- **Фронтенд (`script.js` + `styles.css`):** Vanilla JS/CSS, нескінченний скрол (`IntersectionObserver`), миттєва фільтрація за роками з синхронізацією у параметрі `?year=YYYY`, повноархівний лайтбокс Fancybox 5.0.36 із пінінгом SRI та строгим `Content-Security-Policy`.

## Локальний запуск

```bash
# Встановлення Python-залежності (curl_cffi)
pip install -r requirements.txt

# Перевірка синхронізації без запису на диск
npm run sync:test

# Повна синхронізація нових постів та перегенерація HTML/JS
npm run build

# Перегенерація лише HTML та бандла з наявних фото
npm run update-gallery
```

## Автоматизація GitHub Actions

Воркфлоу `.github/workflows/sync-instagram.yml` запускається щодня о `04:00 UTC` (або вручну через `workflow_dispatch`):
1. Встановлює `curl_cffi` з кешем `pip`.
2. Запускає `python3 sync-instagram.py --limit 50`.
3. Оновлює `index.html` та `gallery-items.js` через `node update-gallery.js`.
4. Робить коміт і `git push` лише за наявності реальних змін у файлах.

### Налаштування GitHub Secrets / Variables

- Secret `IG_SESSION` *(рекомендовано)* — значення куки `sessionid` Instagram для стабільного доступу до GraphQL з IP-адрес GitHub Actions.
- Variable `INSTAGRAM_USERNAME` *(опційно)* — за замовчуванням `kokosnapalmeros`.

## Структура проєкту

```text
.
├── images/                         # Повнорозмірні оригінали фото + background.jpg
├── thumbs/                         # Легкі прев'ю (640px) для швидкої сітки
├── gallery-data.json               # Метадані синхронізованих постів
├── gallery-items.js                # Згенерований компактний індекс усіх кадрів
├── index.html                      # Згенерована головна сторінка
├── styles.css                      # Дизайн-система та адаптивна сітка
├── script.js                       # Фільтрація за роками, скрол та Fancybox 5
├── sync-instagram.py               # Скрипт синхронізації з Instagram
├── update-gallery.js               # Генератор index.html та gallery-items.js
└── .github/workflows/              # Конфігурація щоденного авто-синку
```

## Ліцензія

MIT
