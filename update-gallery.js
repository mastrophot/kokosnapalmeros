#!/usr/bin/env node
/**
 * Gallery Update Script (October 2026 Edition)
 * Генерує сучасний адаптивний інтерфейс index.html та компактний бандл gallery-items.js
 * з підтримкою дворівневих зображень (thumbs/ для сітки 120fps + images/ для 100% оригіналів у Fancybox).
 */

const fs = require("fs");
const path = require("path");

const METADATA_FILE = "gallery-data.json";
const HTML_FILE = "index.html";
const IMAGES_DIR = "images";
const THUMBS_DIR = "thumbs";

const MONTHS_UK = [
    "січ", "лют", "бер", "кві", "тра", "чер",
    "лип", "сер", "вер", "жов", "лис", "гру"
];

function readGalleryData() {
    try {
        const data = fs.readFileSync(METADATA_FILE, "utf-8");
        return JSON.parse(data);
    } catch (error) {
        console.error("❌ Помилка читання gallery-data.json:", error.message);
        return null;
    }
}

function buildShortcodePrefixes(allFiles) {
    const prefixes = new Set();
    const shortcodePattern = /^(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_UTC)_[A-Za-z]/;
    allFiles.forEach(f => {
        const m = f.match(shortcodePattern);
        if (m) prefixes.add(m[1]);
    });
    return prefixes;
}

function isDuplicateWithoutShortcode(filename, shortcodePrefixes) {
    const match = filename.match(/^(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_UTC)_\d+\.jpg$/i);
    if (!match) return false;
    return shortcodePrefixes.has(match[1]);
}

function formatReadableDate(filename) {
    const m = filename.match(/^(\d{4})[-_](\d{2})[-_](\d{2})/);
    if (!m) return "";
    const year = m[1];
    const monthIdx = parseInt(m[2], 10) - 1;
    const day = parseInt(m[3], 10);
    const monthName = MONTHS_UK[monthIdx] || m[2];
    return `${day} ${monthName} ${year}`;
}

function extractShortcode(filename) {
    const m = filename.match(/^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_UTC_([A-Za-z0-9_-]+?)(?:_\d+)?\.jpg$/i);
    return m ? m[1] : null;
}

function escapeAttr(str) {
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/"/g, "&quot;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}

function buildCaptionHtml(filename, dateLabel, postsMeta) {
    const code = extractShortcode(filename);
    const post = code && postsMeta[code] ? postsMeta[code] : null;
    const parts = [];
    if (post && post.c) {
        const safeText = post.c
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\n/g, "<br>");
        parts.push(`<div>${safeText}</div>`);
    }
    const metaLine = [];
    if (dateLabel) metaLine.push(`<span>${dateLabel}</span>`);
    if (code) {
        metaLine.push(`<a href="https://www.instagram.com/p/${code}/" target="_blank" rel="noopener">Instagram ↗</a>`);
    }
    if (metaLine.length > 0) {
        parts.push(`<div style="margin-top:4px;font-size:0.8rem;color:#a1a1aa;">${metaLine.join(" · ")}</div>`);
    }
    return parts.join("");
}

function updateHTML(galleryData) {
    try {
        const allFiles = fs.readdirSync(IMAGES_DIR).filter(f =>
            f.match(/^\d{4}[-_]\d{2}[-_]\d{2}.*\.jpg$/i)
        );

        const shortcodePrefixes = buildShortcodePrefixes(allFiles);
        const instagramPhotos = new Set();
        const postsMeta = {};

        if (galleryData && galleryData.posts) {
            galleryData.posts.forEach(post => {
                if (post.shortcode && post.caption) {
                    postsMeta[post.shortcode] = { c: post.caption };
                }
                const images = post.images || [post.filename];
                images.forEach(filename => {
                    if (fs.existsSync(path.join(IMAGES_DIR, filename))) {
                        instagramPhotos.add(filename);
                    }
                });
            });
        }

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

        const sortedPhotos = Array.from(instagramPhotos).sort((a, b) => {
            const getBaseName = (name) => name.replace(/_\d+\.jpg$/i, ".jpg");
            const baseA = getBaseName(a);
            const baseB = getBaseName(b);
            if (baseA > baseB) return -1;
            if (baseA < baseB) return 1;
            const getNum = (name) => {
                const match = name.match(/_(\d+)\.jpg$/i);
                return match ? parseInt(match[1], 10) : 0;
            };
            return getNum(a) - getNum(b);
        });

        // Підрахунок по роках для навігації
        const yearCounts = new Map();
        sortedPhotos.forEach(f => {
            const yr = f.slice(0, 4);
            yearCounts.set(yr, (yearCounts.get(yr) || 0) + 1);
        });
        const sortedYears = Array.from(yearCounts.keys()).sort((a, b) => b.localeCompare(a));
        const minYear = sortedYears[sortedYears.length - 1] || "2014";
        const maxYear = sortedYears[0] || "2026";
        const totalFormatted = sortedPhotos.length.toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");

        // Перші 18 фото рендеримо прямо в HTML
        const INITIAL_BATCH_SIZE = 18;
        const initialPhotos = sortedPhotos.slice(0, INITIAL_BATCH_SIZE);

        const cardsHtml = initialPhotos.map((filename, idx) => {
            const hasThumb = fs.existsSync(path.join(THUMBS_DIR, filename));
            const fullSrc = `./images/${filename}`;
            const thumbSrc = hasThumb ? `./thumbs/${filename}` : fullSrc;
            const year = filename.slice(0, 4);
            const loadAttrs = idx < 6
                ? 'fetchpriority="high" decoding="async"'
                : 'loading="lazy" decoding="async"';

            return `          <a href="${fullSrc}" data-fancybox="gallery" data-year="${year}" class="gallery-item-wrapper">
            <img src="${thumbSrc}" alt="" class="gallery-item" ${loadAttrs}>
          </a>`;
        }).join("\n");

        const yearPillsHtml = [
            `<button type="button" class="year-pill active" data-year="all">Усі <span class="year-count">${sortedPhotos.length}</span></button>`,
            ...sortedYears.map(yr => `<button type="button" class="year-pill" data-year="${yr}">${yr} <span class="year-count">${yearCounts.get(yr)}</span></button>`)
        ].join("\n          ");

        const stamp = (galleryData && galleryData.last_updated) ? galleryData.last_updated : "synced";

        const fullHtml = `<!DOCTYPE html>
<html lang="uk">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <meta name="theme-color" content="#09090b">
    <title>kokosnapalmeros</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🥥</text></svg>">
    <link rel="stylesheet" href="styles.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@fancyapps/ui@5.0/dist/fancybox/fancybox.css">
    <script src="https://cdn.jsdelivr.net/npm/@fancyapps/ui@5.0/dist/fancybox/fancybox.umd.js" defer></script>
  </head>
  <body>
    <header class="site-header">
      <div class="header-inner">
        <div class="header-top">
          <a href="https://www.instagram.com/kokosnapalmeros/" target="_blank" rel="noopener" class="brand">
            <div class="brand-avatar">🥥</div>
            <div class="brand-text">
              <span class="brand-title">kokosnapalmeros</span>
              <span class="brand-subtitle">${totalFormatted} Photo · ${minYear}–${maxYear}</span>
            </div>
          </a>
          <div class="header-actions">
            <div class="control-group" role="group" aria-label="Щільність сітки">
              <button type="button" class="ctrl-btn active" data-set-density="comfy" title="Стандартна сітка"><i class="fas fa-th-large"></i></button>
              <button type="button" class="ctrl-btn" data-set-density="compact" title="Щільна сітка"><i class="fas fa-th"></i></button>
            </div>
            <a href="https://www.instagram.com/kokosnapalmeros/" target="_blank" rel="noopener" class="ig-btn" aria-label="Instagram @kokosnapalmeros">
              <i class="fab fa-instagram"></i>
              <span>@kokosnapalmeros</span>
            </a>
          </div>
        </div>
        <nav class="year-nav" aria-label="Фільтр за роками">
          ${yearPillsHtml}
        </nav>
      </div>
    </header>

    <main>
      <section id="portfolio">
        <div class="gallery" id="gallery">
${cardsHtml}
        </div>
        <!-- Останнє оновлення: ${stamp} -->
      </section>
    </main>

    <button type="button" id="backToTop" class="back-to-top" aria-label="Нагору">
      <i class="fas fa-arrow-up"></i>
    </button>

    <script src="gallery-items.js" defer></script>
    <script src="script.js" defer></script>
  </body>
</html>
`;

        // Записуємо компактний бандл: префікс "*" означає наявність швидкого прев'ю у thumbs/
        const compactAll = sortedPhotos.map(filename =>
            fs.existsSync(path.join(THUMBS_DIR, filename)) ? `*${filename}` : filename
        );

        const bundleJs = `window.GALLERY_ALL = ${JSON.stringify(compactAll)};\n`;
        fs.writeFileSync("gallery-items.js", bundleJs, "utf-8");
        fs.writeFileSync(HTML_FILE, fullHtml, "utf-8");

        console.log(`✅ HTML оновлено: ${initialPhotos.length} стартових фото в DOM`);
        console.log(`📦 gallery-items.js: ${compactAll.length} фото (компактний формат + метадані)`);
        console.log(`📊 Всього в галереї: ${sortedPhotos.length} фото (${sortedYears.length} років)`);
        console.log(`\n✨ Галерею оновлено!`);
        return true;
    } catch (error) {
        console.error("❌ Помилка оновлення HTML:", error.message);
        return false;
    }
}

function main() {
    console.log("🔄 Оновлення галереї...\n");
    let galleryData = null;
    if (fs.existsSync(METADATA_FILE)) {
        galleryData = readGalleryData();
        if (galleryData && galleryData.posts) {
            console.log(`📊 Знайдено ${galleryData.posts.length} постів від @${galleryData.username}\n`);
        }
    }
    const success = updateHTML(galleryData);
    process.exit(success ? 0 : 1);
}

if (require.main === module) {
    main();
}

module.exports = { updateHTML, readGalleryData };
