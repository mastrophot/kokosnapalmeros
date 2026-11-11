# kokosnapalmeros — Візуальний Фотоархів

Статична автономна веб-галерея з автоматичною щоденною синхронізацією фото з публічного Instagram-профілю [@kokosnapalmeros](https://www.instagram.com/kokosnapalmeros/) на базі GitHub Actions та GitHub Pages.

Живий сайт: https://mastrophot.github.io/kokosnapalmeros/

## Архітектура

- **Дворівневий пайплайн синхронізації (`sync-instagram.py`):**
  1. **Основний канал:** авторизований пагінований GraphQL-запит профілю (`IG_SESSION`) через `curl_cffi` з актуальною TLS-імперсонацією Chrome.
  2. **Резервний канал:** анонімний парсинг HTML Relay Preloader без куків.
  3. **Автооновлення аватара:** автоматична перевірка й оновлення `images/avatar.jpg`.
- **Дворівневе зберігання зображень:**
  - `images/` — некропнуті оригінали максимальної роздільної здатності з вирізаним другим потоком Ultra-HDR GainMap (`MPF` / `hdrgm`) для плавного рендеру без втрати якості SDR-кадру.
  - `thumbs/` — оптимізовані легкі прев'ю (`640px`–`720px`) для миттєвого завантаження сітки.
- **Zero-dependency генератор статики (`update-gallery.js`):** працює на вбудованих модулях Node.js (`fs`, `path`, `crypto`), генеруючи `index.html`, `gallery-items.js` та `sitemap.xml` із контентним хешуванням (`?v=sha256`) проти застарілого кешу.
- **Повністю автономний фронтенд (`script.js` + `styles.css` + `vendor/`):** локально вендорований Fancybox 5.0.36 без зовнішніх CDN, строгий `Content-Security-Policy` (`script-src 'self'`), перемикання режимів **`Кадри` (дефолт)** / **`Серії`**, щільність сітки (`3` / `4` колонки), нескінченний скрол (`IntersectionObserver`) та фільтрація за роками (`?year=YYYY`).

## Локальний запуск

```bash
# Встановлення Python-залежності (curl_cffi)
pip install -r requirements.txt

# Перевірка синхронізації без запису на диск
npm run sync:test

# Повна синхронізація нових постів та перегенерація HTML/JS
npm run build

# Перегенерація лише HTML, бандла та sitemap з наявних фото
npm run update-gallery
```

## Автоматизація GitHub Actions

Воркфлоу `.github/workflows/sync-instagram.yml` запускається щодня о `04:17 UTC` (або вручну через `workflow_dispatch`):
1. Встановлює `curl_cffi` з кешем `pip`.
2. Запускає `python3 sync-instagram.py --limit 50`.
3. Оновлює `index.html`, `gallery-items.js` та `sitemap.xml` через `node update-gallery.js`.
4. Робить коміт і `git push` лише за наявності реальних змін у файлах.

### Налаштування GitHub Secrets / Variables

- Secret `IG_SESSION` *(рекомендовано)* — значення куки `sessionid` Instagram для стабільного доступу до пагінованого GraphQL з IP-адрес GitHub Actions.
- Variable `INSTAGRAM_USERNAME` *(опційно)* — за замовчуванням `kokosnapalmeros`.

## Структура проєкту

```text
.
├── images/                         # Повнорозмірні оригінали фото + avatar.jpg
├── thumbs/                         # Легкі прев'ю для швидкої сітки
├── vendor/                         # Локально вендорований Fancybox 5.0.36 (CSS + JS)
├── gallery-data.json               # Метадані синхронізованих постів
├── gallery-items.js                # Згенерований компактний індекс усіх кадрів
├── index.html                      # Згенерована головна сторінка
├── sitemap.xml / robots.txt        # Індексація пошуковими системами
├── .nojekyll                       # Прямий деплой GitHub Pages без збірки Jekyll
├── styles.css                      # Дизайн-система та адаптивна сітка
├── script.js                       # Режими Кадри/Серії, роки, скрол та лайтбокс
├── sync-instagram.py               # Скрипт синхронізації з Instagram
├── update-gallery.js               # Генератор статики з хешами асетів
└── .github/workflows/              # Конфігурація щоденного авто-синку
```

## Ліцензія

MIT
