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
 * Будує множину timestamp-префіксів, для яких існують файли з shortcode.
 * Це дозволяє відфільтрувати старі дублі без shortcode.
 *
 * Файл із shortcode:  2025-11-08_17-22-19_UTC_DQzb7fiiLkt_1.jpg
 * Prefix:             2025-11-08_17-22-19_UTC
 *
 * Старий дубль:       2025-11-08_17-22-19_UTC_1.jpg → skip, бо prefix є в множині
 */
function buildShortcodePrefixes(allFiles) {
  const prefixes = new Set();
  // Файл із shortcode: YYYY-MM-DD_HH-MM-SS_UTC_LETTERS..._N.jpg
  const shortcodePattern = /^(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_UTC)_[A-Za-z]/;
  allFiles.forEach(f => {
    const m = f.match(shortcodePattern);
    if (m) prefixes.add(m[1]);
  });
  return prefixes;
}

/**
 * Перевіряє, чи файл є дублем без shortcode
 */
function isDuplicateWithoutShortcode(filename, shortcodePrefixes) {
  // Файли без shortcode: YYYY-MM-DD_HH-MM-SS_UTC_N.jpg (число одразу після UTC_)
  const match = filename.match(/^(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_UTC)_\d+\.jpg$/i);
  if (!match) return false;
  return shortcodePrefixes.has(match[1]);
}

/**
 * Оновлює HTML файл з новими фото
 */
function updateHTML(galleryData) {
    try {
        const html = fs.readFileSync(HTML_FILE, 'utf-8');
        const $ = cheerio.load(html);

        const gallery = $('.gallery');
        if (gallery.length === 0) {
            console.error('❌ Не знайдено елемент .gallery в HTML');
            return false;
        }

        gallery.empty();

        const allFiles = fs.readdirSync(IMAGES_DIR).filter(f =>
            f.match(/^\d{4}[-_]\d{2}[-_]\d{2}.*\.jpg$/i)
        );

        // Будуємо множину префіксів із shortcode-файлів
        const shortcodePrefixes = buildShortcodePrefixes(allFiles);

        // Збираємо фото: з metadata + з диска (без дублів)
        const instagramPhotos = new Set();

        // Спочатку — фото з metadata
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

        // Потім — фото з диска, пропускаючи дублі
        let skippedDuplicates = 0;
        allFiles.forEach(file => {
            if (isDuplicateWithoutShortcode(file, shortcodePrefixes)) {
                skippedDuplicates++;
                return;
            }
            instagramPhotos.add(file);
        });

        if (skippedDuplicates > 0) {
            console.log(`🗑️  Пропущено ${skippedDuplicates} дублів без shortcode`);
        }

        const photosArray = Array.from(instagramPhotos);

        // Сортування: за timestamp DESC, всередині посту за номером ASC
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

        let addedCount = 0;
        initialPhotos.forEach(filename => {
            const imagePath = `./images/${filename}`;
            const caption = filename.replace(/\.(jpg|jpeg|png)$/i, '').replace(/[_-]/g, ' ');
            gallery.append(`
                <a href="${imagePath}" data-fancybox="gallery" class="gallery-item-wrapper">
                    <img src="${imagePath}" alt="${caption}" class="gallery-item" loading="lazy">
                </a>`);
            addedCount++;
        });

        console.log(`✅ HTML оновлено: ${addedCount} фото в DOM`);

        if (deferredPhotos.length > 0) {
            const galleryItems = deferredPhotos.map(filename => ({
                src: `./images/${filename}`,
                thumb: `./images/${filename}`,
                caption: filename.replace(/\.(jpg|jpeg|png)$/i, '').replace(/[_-]/g, ' ')
            }));
            fs.writeFileSync('gallery-items.js',
                `window.GALLERY_ITEMS = ${JSON.stringify(galleryItems, null, 2)};`, 'utf-8');
            console.log(`📦 gallery-items.js: ${deferredPhotos.length} додаткових фото`);
        } else {
            fs.writeFileSync('gallery-items.js', 'window.GALLERY_ITEMS = [];', 'utf-8');
        }

        console.log(`📊 Всього в галереї: ${sortedPhotos.length} фото`);

        gallery.append(`\n    <!-- Останнє оновлення: ${new Date().toLocaleString('uk-UA')} -->`);
        fs.writeFileSync(HTML_FILE, $.html(), 'utf-8');
        console.log(`\n✨ Галерею оновлено!`);

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
    console.warn(`\n⚠️  Відсутні ${missingCount} файлів.`);
  }
  return missingCount === 0;
}

function main() {
  console.log("🔄 Оновлення галереї...\n");

  let galleryData = null;
  if (fs.existsSync(METADATA_FILE)) {
    galleryData = readGalleryData();
    if (galleryData) {
      console.log(`📊 Знайдено ${galleryData.posts.length} постів від @${galleryData.username}\n`);
    }
  } else {
    console.log("ℹ️  gallery-data.json не знайдено, беремо всі фото з images/\n");
  }

  const success = updateHTML(galleryData);
  process.exit(success ? 0 : 1);
}

if (require.main === module) {
  main();
}

module.exports = { updateHTML, readGalleryData };
