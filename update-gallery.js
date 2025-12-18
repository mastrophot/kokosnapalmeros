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

        // Отримуємо всі Instagram фото з папки images
        const instagramPhotos = [];
        const files = fs.readdirSync(IMAGES_DIR);

        files.forEach(file => {
            // Шукаємо файли з датою в форматі YYYY-MM-DD або YYYY (Instagram фото)
            if (file.match(/^\d{4}[-_]\d{2}[-_]\d{2}.*\.jpg$/i)) {
                instagramPhotos.push(file);
            }
        });

        // Сортуємо за датою (найновіші спочатку)
        instagramPhotos.sort().reverse();

        // Розділяємо на початкове завантаження і відкладене
        const INITIAL_BATCH_SIZE = 15;
        const initialPhotos = instagramPhotos.slice(0, INITIAL_BATCH_SIZE);
        const deferredPhotos = instagramPhotos.slice(INITIAL_BATCH_SIZE);

        // Додаємо початкові фото в HTML
        let addedCount = 0;
        initialPhotos.forEach(filename => {
            const imagePath = `./images/${filename}`;
            const caption = filename.replace(/\.(jpg|jpeg|png)$/i, '').replace(/[_-]/g, ' ');

            const galleryItem = `
                <a href="${imagePath}" data-fancybox="gallery" class="gallery-item-wrapper">
                    <img src="${imagePath}" alt="${caption}" class="gallery-item">
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

        // Додаємо коментар з датою оновлення
        const updateComment = `\n    <!-- Останнє оновлення: ${new Date().toLocaleString('uk-UA')} -->`;
        gallery.after(updateComment);

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
