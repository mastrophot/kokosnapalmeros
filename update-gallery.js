#!/usr/bin/env node
/**
 * Gallery Update Script
 * Генерує статичний index.html, компактний бандл gallery-items.js та sitemap.xml
 * без зовнішніх npm-залежностей (чисті вбудовані fs, path, crypto).
 */

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const ROOT_DIR = __dirname;
const METADATA_FILE = path.join(ROOT_DIR, "gallery-data.json");
const HTML_FILE = path.join(ROOT_DIR, "index.html");
const BUNDLE_FILE = path.join(ROOT_DIR, "gallery-items.js");
const SITEMAP_FILE = path.join(ROOT_DIR, "sitemap.xml");
const IMAGES_DIR = path.join(ROOT_DIR, "images");
const THUMBS_DIR = path.join(ROOT_DIR, "thumbs");
const VENDOR_DIR = path.join(ROOT_DIR, "vendor");
const AVATAR_FILE = path.join(IMAGES_DIR, "avatar.jpg");
const SITE_URL = "https://mastrophot.github.io/kokosnapalmeros/";

const SAFE_FILENAME_RE = /^\d{4}[-_]\d{2}[-_]\d{2}_\d{2}-\d{2}-\d{2}_UTC(?:_[A-Za-z0-9_-]+)?\.jpg$/i;

const MONTHS_EN = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
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

function fileHash(filePath) {
    try {
        const buf = fs.readFileSync(filePath);
        return crypto.createHash("sha256").update(buf).digest("hex").slice(0, 8);
    } catch {
        return "1";
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

function getSeriesKey(filename) {
    return filename.replace(/_\d+\.jpg$/i, "").replace(/\.jpg$/i, "");
}

function escapeAttr(str) {
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/"/g, "&quot;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}

function formatPhotoLabel(filename) {
    const m = filename.match(/^(\d{4})[-_](\d{2})[-_](\d{2})/);
    if (!m) return "Photo by @kokosnapalmeros";
    const year = m[1];
    const monthIdx = parseInt(m[2], 10) - 1;
    const day = parseInt(m[3], 10);
    const monthName = MONTHS_EN[monthIdx] || m[2];
    const numMatch = filename.match(/_(\d+)\.jpg$/i);
    const suffix = numMatch ? `, frame ${numMatch[1]}` : "";
    return `Photo by @kokosnapalmeros — ${monthName} ${day}, ${year}${suffix}`;
}

function formatNumberSpaces(num) {
    return String(num).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function updateHTML(galleryData) {
    try {
        const allFiles = fs.readdirSync(IMAGES_DIR).filter(f => SAFE_FILENAME_RE.test(f));

        const shortcodePrefixes = buildShortcodePrefixes(allFiles);
        const instagramPhotos = new Set();

        if (galleryData && Array.isArray(galleryData.posts)) {
            galleryData.posts.forEach(post => {
                const images = post.images || [post.filename];
                images.forEach(filename => {
                    if (
                        typeof filename === "string" &&
                        SAFE_FILENAME_RE.test(filename) &&
                        fs.existsSync(path.join(IMAGES_DIR, filename))
                    ) {
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

        const seriesMap = new Map();
        const sortedSeries = [];
        sortedPhotos.forEach(filename => {
            const key = getSeriesKey(filename);
            let group = seriesMap.get(key);
            if (!group) {
                group = {
                    key,
                    year: filename.slice(0, 4),
                    items: [],
                };
                seriesMap.set(key, group);
                sortedSeries.push(group);
            }
            group.items.push(filename);
        });

        const yearFrameCounts = new Map();
        sortedPhotos.forEach(f => {
            const yr = f.slice(0, 4);
            yearFrameCounts.set(yr, (yearFrameCounts.get(yr) || 0) + 1);
        });

        const yearSeriesCounts = new Map();
        sortedSeries.forEach(group => {
            yearSeriesCounts.set(group.year, (yearSeriesCounts.get(group.year) || 0) + 1);
        });

        const sortedYears = Array.from(yearFrameCounts.keys()).sort((a, b) => b.localeCompare(a));
        const minYear = sortedYears[sortedYears.length - 1] || "2014";
        const maxYear = sortedYears[0] || "2026";
        const totalFramesFormatted = formatNumberSpaces(sortedPhotos.length);
        const totalSeriesFormatted = formatNumberSpaces(sortedSeries.length);

        const compactAll = sortedPhotos.map(filename =>
            fs.existsSync(path.join(THUMBS_DIR, filename)) ? `*${filename}` : filename
        );
        const bundleJs = `window.GALLERY_ALL = ${JSON.stringify(compactAll)};\n`;
        fs.writeFileSync(BUNDLE_FILE, bundleJs, "utf-8");

        const cssVer = fileHash(path.join(ROOT_DIR, "styles.css"));
        const jsVer = fileHash(path.join(ROOT_DIR, "script.js"));
        const bundleVer = fileHash(BUNDLE_FILE);
        const fbCssVer = fileHash(path.join(VENDOR_DIR, "fancybox.css"));
        const fbJsVer = fileHash(path.join(VENDOR_DIR, "fancybox.umd.js"));
        const avatarVer = fileHash(AVATAR_FILE);

        const svgGridComfy = `<svg class="icon-svg" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><rect x="1.5" y="1.5" width="5.5" height="5.5" rx="1.2"/><rect x="9" y="1.5" width="5.5" height="5.5" rx="1.2"/><rect x="1.5" y="9" width="5.5" height="5.5" rx="1.2"/><rect x="9" y="9" width="5.5" height="5.5" rx="1.2"/></svg>`;
        const svgGridCompact = `<svg class="icon-svg" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><rect x="1" y="1" width="3.8" height="3.8" rx="0.8"/><rect x="6.1" y="1" width="3.8" height="3.8" rx="0.8"/><rect x="11.2" y="1" width="3.8" height="3.8" rx="0.8"/><rect x="1" y="6.1" width="3.8" height="3.8" rx="0.8"/><rect x="6.1" y="6.1" width="3.8" height="3.8" rx="0.8"/><rect x="11.2" y="6.1" width="3.8" height="3.8" rx="0.8"/><rect x="1" y="11.2" width="3.8" height="3.8" rx="0.8"/><rect x="6.1" y="11.2" width="3.8" height="3.8" rx="0.8"/><rect x="11.2" y="11.2" width="3.8" height="3.8" rx="0.8"/></svg>`;
        const svgInstagram = `<svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="2" width="20" height="20" rx="5" ry="5"/><path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"/><line x1="17.5" y1="6.5" x2="17.51" y2="6.5"/></svg>`;
        const svgArrowUp = `<svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 19V5"/><path d="m5 12 7-7 7 7"/></svg>`;

        // Дефолтний режим — Кадри (перші 18 окремих знімків у SSR)
        const INITIAL_BATCH_SIZE = 18;
        const initialPhotos = sortedPhotos.slice(0, INITIAL_BATCH_SIZE);

        const cardsHtml = initialPhotos.map((filename, idx) => {
            const hasThumb = fs.existsSync(path.join(THUMBS_DIR, filename));
            const fullSrc = `./images/${filename}`;
            const thumbSrc = hasThumb ? `./thumbs/${filename}` : fullSrc;
            const year = filename.slice(0, 4);
            const safeLabel = escapeAttr(formatPhotoLabel(filename));
            const loadAttrs = idx < 6
                ? 'fetchpriority="high" decoding="async"'
                : 'loading="lazy" decoding="async"';

            return `          <a href="${fullSrc}" data-index="${idx}" data-year="${year}" aria-label="${safeLabel}" class="gallery-item-wrapper">
            <img src="${thumbSrc}" alt="${safeLabel}" class="gallery-item is-loaded" ${loadAttrs}>
          </a>`;
        }).join("\n");

        const yearPillsHtml = [
            `<button type="button" class="year-pill active" data-year="all" data-series-count="${sortedSeries.length}" data-frames-count="${sortedPhotos.length}" aria-pressed="true">All <span class="year-count">${sortedPhotos.length}</span></button>`,
            ...sortedYears.map(yr => {
                const sCount = yearSeriesCounts.get(yr) || 0;
                const fCount = yearFrameCounts.get(yr) || 0;
                return `<button type="button" class="year-pill" data-year="${yr}" data-series-count="${sCount}" data-frames-count="${fCount}" aria-pressed="false">${yr} <span class="year-count">${fCount}</span></button>`;
            })
        ].join("\n          ");

        const hasAvatar = fs.existsSync(AVATAR_FILE);
        const avatarHtml = hasAvatar
            ? `<img src="./images/avatar.jpg?v=${avatarVer}" alt="" width="48" height="48" decoding="async" class="brand-avatar">`
            : `<span class="brand-avatar brand-monogram" aria-hidden="true">K</span>`;

        const stamp = escapeAttr((galleryData && galleryData.last_updated) ? galleryData.last_updated : "synced");
        const metaDescription = escapeAttr(`Visual photo archive by @kokosnapalmeros — ${totalFramesFormatted} photos across ${totalSeriesFormatted} series (${minYear}–${maxYear}).`);
        const ogCover = sortedPhotos[0] ? `images/${sortedPhotos[0]}` : "images/background.jpg";
        const ogImageUrl = `${SITE_URL}${ogCover}`;

        const faviconSvg = `data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🥥</text></svg>`;

        const cspPolicy = [
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: blob:",
            "font-src 'self'",
            "connect-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'none'"
        ].join("; ");

        const fullHtml = `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <meta http-equiv="Content-Security-Policy" content="${cspPolicy}">
    <meta name="referrer" content="strict-origin-when-cross-origin">
    <meta name="theme-color" content="#09090b">
    <title>kokosnapalmeros — Photo Archive</title>
    <meta name="description" content="${metaDescription}">
    <link rel="canonical" href="${SITE_URL}">
    <meta property="og:type" content="website">
    <meta property="og:site_name" content="kokosnapalmeros">
    <meta property="og:locale" content="en_US">
    <meta property="og:title" content="kokosnapalmeros — Photo Archive">
    <meta property="og:description" content="${metaDescription}">
    <meta property="og:url" content="${SITE_URL}">
    <meta property="og:image" content="${ogImageUrl}">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="kokosnapalmeros — Photo Archive">
    <meta name="twitter:description" content="${metaDescription}">
    <meta name="twitter:image" content="${ogImageUrl}">
    <link rel="icon" href="${faviconSvg}">
    <link rel="stylesheet" href="styles.css?v=${cssVer}">
    <link rel="stylesheet" href="vendor/fancybox.css?v=${fbCssVer}">
    <script src="vendor/fancybox.umd.js?v=${fbJsVer}" defer></script>
  </head>
  <body>
    <div class="site-bg" aria-hidden="true"></div>
    <header class="site-header">
      <div class="header-inner">
        <div class="header-top">
          <a href="./" class="brand" id="brandHome" aria-label="kokosnapalmeros — back to archive start">
            ${avatarHtml}
            <div class="brand-text">
              <span class="brand-title">kokosnapalmeros</span>
              <span class="brand-subtitle">${totalFramesFormatted} photos · ${totalSeriesFormatted} series · ${minYear}–${maxYear}</span>
            </div>
          </a>
          <div class="header-actions">
            <div class="control-group" role="group" aria-label="View mode">
              <button type="button" class="ctrl-btn active" data-set-view="frames" aria-pressed="true" title="Show all individual frames">Frames</button>
              <button type="button" class="ctrl-btn" data-set-view="series" aria-pressed="false" title="Group carousels into series">Series</button>
            </div>
            <div class="control-group" role="group" aria-label="Grid density">
              <button type="button" class="ctrl-btn active" data-set-density="comfy" aria-label="Standard grid" aria-pressed="true" title="Standard grid">${svgGridComfy}</button>
              <button type="button" class="ctrl-btn" data-set-density="compact" aria-label="Compact grid" aria-pressed="false" title="Compact grid">${svgGridCompact}</button>
            </div>
            <a href="https://www.instagram.com/kokosnapalmeros/" target="_blank" rel="noopener noreferrer" class="ig-btn" aria-label="Instagram @kokosnapalmeros">
              ${svgInstagram}
              <span>@kokosnapalmeros</span>
            </a>
          </div>
        </div>
        <nav class="year-nav" aria-label="Filter by year">
          ${yearPillsHtml}
        </nav>
      </div>
    </header>

    <main>
      <section id="portfolio">
        <div class="gallery" id="gallery">
${cardsHtml}
        </div>
        <!-- Last updated: ${stamp} -->
      </section>
    </main>

    <button type="button" id="backToTop" class="back-to-top" aria-label="Back to top" title="Back to top">
      ${svgArrowUp}
    </button>

    <script src="gallery-items.js?v=${bundleVer}" defer></script>
    <script src="script.js?v=${jsVer}" defer></script>
  </body>
</html>
`;

        fs.writeFileSync(HTML_FILE, fullHtml, "utf-8");

        const latestDate = sortedPhotos[0]
            ? sortedPhotos[0].slice(0, 10).replace(/_/g, "-")
            : "2026-11-10";
        const sitemapXml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>${SITE_URL}</loc>
    <lastmod>${latestDate}</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>
`;
        fs.writeFileSync(SITEMAP_FILE, sitemapXml, "utf-8");

        const thumbsCount = compactAll.filter(x => x.startsWith("*")).length;
        console.log(`✅ HTML оновлено: ${initialPhotos.length} стартових кадрів у DOM (дефолт: Кадри)`);
        console.log(`📦 gallery-items.js: ${compactAll.length} фото у ${sortedSeries.length} серіях (${thumbsCount} із прев'ю в thumbs/)`);
        console.log(`📊 Всього в галереї: ${sortedPhotos.length} фото / ${sortedSeries.length} серій (${sortedYears.length} років)`);
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
        if (galleryData && Array.isArray(galleryData.posts)) {
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
