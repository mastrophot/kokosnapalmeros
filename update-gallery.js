#!/usr/bin/env node
/**
 * Gallery Update Script
 * Оновлює index.html новими фото з gallery-data.json
 */

const fs = require("fs");
const path = require("path");
const cheerio = require("cheerio");

const METADATA_FILE = "gallery-data.json";
const HTML_FILE = "index.html";
const IMAGES_DIR = "images";

/**
 * Читає метадані галереї
 */
function readGalleryData() {
  try {
    const data = fs.readFileSync(METADATA_FILE, "utf-8");
    return JSON.parse(data);
  } catch (error) {
    console.error("❌ Помилка читання gallery-data.json:", error.message);
    return null;
  }
}

/**
 * Збирає множину відомих shortcode-файлів з metadata,
 * щоб відфільтрувати дублі без shortcode.
 */
function buildKnownShortcodeFiles(galleryData) {
  const known = new Set();
  if (galleryData && galleryData.posts) {
    galleryData.posts.forEach(post => {
      const images = post.images || [post.filename];
      images.forEach(f => known.add(f));
    });
  }
  return known;
}

/**
 * Перевіряє, чи файл є дублем (без shortcode),
 * коли існує відповідний файл із shortcode.
 * Наприклад: 2025-11-08_17-22-19_UTC_1.jpg — дубль,
 * якщо є     2025-11-08_17-22-19_UTC_DQzb7fiiLkt_1.jpg
 */
function isDuplicateWithoutShortcode(filename, allFiles) {
  // Файли без shortcode мають формат: YYYY-MM-DD_HH-MM-SS_UTC_N.jpg
  const match = filename.match(/^(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_UTC)_(\d+)\.jpg$/i);
  if (!match) return false;

  const prefix = match[1]; // 2025-11-08_17-22-19_UTC
  // Шукаємо файл із тим самим prefix, але зі shortcode між UTC_ та _N
  // Формат: prefix_SHORTCODE_N.jpg
  return allFiles.some(f => {
    if (f === filename) return false;
    return f.startsWith(prefix + '_') && f !== filename && !f.match(/^(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_UTC)_\d+\.jpg$/i);
  });
}

/**
 * Оновлює HTML файл з новими фото
 */
function updateHTML(galleryData) {
    try {
        // Читаємо HTML
        const html = fs.readFileSync(HTML_FILE, 'utf-8');
        const $ = cheerio.load(html);

        // Знаходимо контейнер галереї
        const gallery = $('.gallery');

        if (gallery.length === 0) {
            console.error('❌ Не знайдено елемент .gallery в HTML');
            return false;
        }

        // Очищаємо галерею для повного оновлення
        gallery.empty();

        // Збираємо всі фото
        const instagramPhotos = new Set();
        const files = fs.readdirSync(IMAGES_DIR);

        // Спочатку додаємо фото з метаданих (якщо існують на диску)
        const knownFiles = buildKnownShortcodeFiles(galleryData);
        if (galleryData && galleryData.posts) {
            galleryData.posts.forEach(post => {
                const images = post.images || [post.filename];
                images.forEach(filename => {
                    if (fs.existsSync(path.join(IMAGES_DIR, filename))) {
                        instagramPhotos.add(filename);
                    }
                });
            });
        }

        // Додаємо фото з папки, яких немає в метаданих, але ТІЛЬКИ якщо це не дуплікати
        files.forEach(file => {
            if (file.match(/^\d{4}[-_]\d{2}[-_]\d{2}.*\.jpg$/i)) {
                // Пропускаємо файли без shortcode, якщо є відповідний файл із shortcode
                if (isDuplicateWithoutShortcode(file, files)) {
                    return; // skip duplicate
                }
                instagramPhotos.add(file);
            }
        });

        // Конвертуємо Set назад у масив
        const photosArray = Array.from(instagramPhotos);

        // Кастомне сортування:
        // 1. Пости сортуємо за часом (filename без суфікса) - DESC (спадання)
        // 2. Фото всередині посту (за суфіксом _1, _2) - ASC (зростання)
        const sortedPhotos = photosArray.sort((a, b) => {
            const getBaseName = (name) => name.replace(/_\d+\.jpg$/i, '.jpg');
            const baseA = getBaseName(a);
            const baseB = getBaseName(b);

            if (baseA > baseB) return -1;
            if (baseA < baseB) return 1;

            const getNum = (name) => {
                const match = name.match(/_(\d+)\.jpg$/i);
                return match ? parseInt(match[1]) : 0;
            };

            return getNum(a) - getNum(b);
        });

        // Розділяємо на початкове завантаження і відкладене
        const INITIAL_BATCH_SIZE = 15;
        const initialPhotos = sortedPhotos.slice(0, INITIAL_BATCH_SIZE);
        const deferredPhotos = sortedPhotos.slice(INITIAL_BATCH_SIZE);

        // Додаємо початкові фото в HTML
        let addedCount = 0;
        initialPhotos.forEach(filename => {
            const imagePath = `./images/${filename}`;
            const caption = filename.replace(/\.(jpg|jpeg|png)$/i, '').replace(/[_-]/g, ' ');

            const galleryItem = `
                <a href="${imagePath}" data-fancybox="gallery" class="gallery-item-wrapper">
                    <img src="${imagePath}" alt="${caption}" class="gallery-item" loading="lazy">
                </a>`;

            gallery.append(galleryItem);
            addedCount++;
        });

        console.log(`✅ HTML оновлено: додано перші ${addedCount} фото`);

        // Зберігаємо решту фото в JS файл для лінивого завантаження
        if (deferredPhotos.length > 0) {
            const galleryItems = deferredPhotos.map(filename => ({
                src: `./images/${filename}`,
                thumb: `./images/${filename}`,
                caption: filename.replace(/\.(jpg|jpeg|png)$/i, '').replace(/[_-]/g, ' ')
            }));

            const jsContent = `window.GALLERY_ITEMS = ${JSON.stringify(galleryItems, null, 2)};`;
            fs.writeFileSync('gallery-items.js', jsContent, 'utf-8');
            console.log(`📦 Створено gallery-items.js з ${deferredPhotos.length} додатковими фото`);
        } else {
             // Якщо фото мало, створюємо пустий масив
             fs.writeFileSync('gallery-items.js', 'window.GALLERY_ITEMS = [];', 'utf-8');
        }

        // Один коментар з датою оновлення (всередині .gallery, без дублювання)
        const updateComment = `\n    <!-- Останнє оновлення: ${new Date().toLocaleString('uk-UA')} -->`;
        gallery.append(updateComment);

        // Зберігаємо оновлений HTML
        fs.writeFileSync(HTML_FILE, $.html(), 'utf-8');

        console.log(`\n✨ Галерею оновлено!`);
        console.log(`📄 Файл ${HTML_FILE} збережено`);

        return true;

    } catch (error) {
        console.error('❌ Помилка оновлення HTML:', error.message);
        return false;
    }
}

/**
 * Перевіряє наявність фото в папці images
 */
function verifyImages(galleryData) {
  let missingCount = 0;

  galleryData.posts.forEach((post) => {
    const imagePath = path.join(IMAGES_DIR, post.filename);
    if (!fs.existsSync(imagePath)) {
      console.warn(`⚠️  Файл не знайдено: ${post.filename}`);
      missingCount++;
    }
  });

  if (missingCount > 0) {
    console.warn(
      `\n⚠️  Відсутні ${missingCount} файлів. Запустіть 'npm run sync' для завантаження.`
    );
  }

  return missingCount === 0;
}

// Головна функція
function main() {
  console.log("🔄 Оновлення галереї...\n");

  // Перевіряємо наявність метаданих (опціонально)
  let galleryData = null;
  if (fs.existsSync(METADATA_FILE)) {
    galleryData = readGalleryData();
    if (galleryData) {
      console.log(
        `📊 Знайдено ${galleryData.posts.length} постів від @${galleryData.username}\n`
      );
    }
  } else {
    console.log(
      "ℹ️  Файл gallery-data.json не знайдено, додаємо всі Instagram фото з папки images\n"
    );
  }

  // Оновлюємо HTML
  const success = updateHTML(galleryData);

  process.exit(success ? 0 : 1);
}

// Запуск
if (require.main === module) {
  main();
}

module.exports = { updateHTML, readGalleryData };
