document.addEventListener('DOMContentLoaded', () => {
    const MONTHS_UK = [
        'січ', 'лют', 'бер', 'кві', 'тра', 'чер',
        'лип', 'сер', 'вер', 'жов', 'лис', 'гру'
    ];
    const SVG_NS = 'http://www.w3.org/2000/svg';

    const gallery = document.querySelector('.gallery');
    const brandHome = document.getElementById('brandHome');
    const backToTopBtn = document.getElementById('backToTop');
    const densityBtns = document.querySelectorAll('[data-set-density]');
    const viewBtns = document.querySelectorAll('[data-set-view]');
    const yearPills = document.querySelectorAll('.year-pill');

    // 1. Щільність сітки (comfy / compact)
    const savedDensity = localStorage.getItem('kokos_density') === 'compact' ? 'compact' : 'comfy';

    const applyDensity = (density) => {
        if (density === 'compact') {
            document.body.setAttribute('data-density', 'compact');
        } else {
            document.body.removeAttribute('data-density');
        }
        densityBtns.forEach(btn => {
            const isActive = btn.dataset.setDensity === density;
            btn.classList.toggle('active', isActive);
            btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        });
    };

    applyDensity(savedDensity);

    densityBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const val = btn.dataset.setDensity === 'compact' ? 'compact' : 'comfy';
            localStorage.setItem('kokos_density', val);
            applyDensity(val);
        });
    });

    // 2. Форматування підписів та групування серій із бандла
    const getSeriesKey = (filename) => filename.replace(/_\d+\.jpg$/i, '').replace(/\.jpg$/i, '');

    const formatPhotoLabel = (filename) => {
        const m = filename.match(/^(\d{4})[-_](\d{2})[-_](\d{2})/);
        if (!m) return 'Фото @kokosnapalmeros';
        const year = m[1];
        const monthIdx = parseInt(m[2], 10) - 1;
        const day = parseInt(m[3], 10);
        const monthName = MONTHS_UK[monthIdx] || m[2];
        const numMatch = filename.match(/_(\d+)\.jpg$/i);
        const suffix = numMatch ? `, кадр ${numMatch[1]}` : '';
        return `Фото @kokosnapalmeros — ${day} ${monthName} ${year}${suffix}`;
    };

    const formatSeriesLabel = (filename, count) => {
        const m = filename.match(/^(\d{4})[-_](\d{2})[-_](\d{2})/);
        if (!m) {
            return count > 1 ? `Серія @kokosnapalmeros (${count} фото)` : 'Фото @kokosnapalmeros';
        }
        const year = m[1];
        const monthIdx = parseInt(m[2], 10) - 1;
        const day = parseInt(m[3], 10);
        const monthName = MONTHS_UK[monthIdx] || m[2];
        if (count > 1) {
            return `Серія @kokosnapalmeros — ${day} ${monthName} ${year} (${count} фото)`;
        }
        return `Фото @kokosnapalmeros — ${day} ${monthName} ${year}`;
    };

    const parseEntry = (rawEntry) => {
        const hasThumb = typeof rawEntry === 'string' && rawEntry.startsWith('*');
        const filename = hasThumb ? rawEntry.slice(1) : String(rawEntry);
        return {
            filename,
            fullSrc: `./images/${filename}`,
            thumbSrc: hasThumb ? `./thumbs/${filename}` : `./images/${filename}`,
            year: filename.slice(0, 4),
            label: formatPhotoLabel(filename),
        };
    };

    const bindImageReveal = (img) => {
        if (img.complete && img.naturalWidth > 0) {
            img.classList.add('is-loaded');
            return;
        }
        const reveal = () => img.classList.add('is-loaded');
        img.addEventListener('load', () => {
            if (typeof img.decode === 'function') {
                img.decode().then(reveal, reveal);
            } else {
                reveal();
            }
        }, { once: true });
        img.addEventListener('error', reveal, { once: true });
    };

    if (gallery) {
        gallery.querySelectorAll('.gallery-item').forEach(bindImageReveal);
    }

    const allRawItems = Array.isArray(window.GALLERY_ALL) ? window.GALLERY_ALL : [];
    const allFrames = allRawItems.map(parseEntry);

    const seriesMap = new Map();
    const allSeries = [];
    allFrames.forEach(frame => {
        const key = getSeriesKey(frame.filename);
        let group = seriesMap.get(key);
        if (!group) {
            group = {
                key,
                year: frame.year,
                cover: frame,
                items: [],
                label: '',
            };
            seriesMap.set(key, group);
            allSeries.push(group);
        }
        group.items.push(frame);
    });
    allSeries.forEach(group => {
        group.label = formatSeriesLabel(group.cover.filename, group.items.length);
    });

    // 3. Стан подачі (series | frames) та фільтрації за роками (?year=YYYY)
    const validYears = new Set(Array.from(yearPills).map(p => p.dataset.year).filter(Boolean));
    const urlParams = new URLSearchParams(window.location.search);
    const initialUrlYear = urlParams.get('year');

    let viewMode = localStorage.getItem('kokos_view') === 'frames' ? 'frames' : 'series';
    if (urlParams.get('view') === 'frames') viewMode = 'frames';
    if (urlParams.get('view') === 'series') viewMode = 'series';

    let activeYear = initialUrlYear && validYears.has(initialUrlYear) ? initialUrlYear : 'all';
    let filteredList = [];
    const initialDomCount = gallery ? gallery.querySelectorAll('.gallery-item-wrapper').length : 0;
    let currentIndex = initialDomCount;
    const BATCH_SIZE = 24;

    const createSeriesBadge = (count) => {
        const badge = document.createElement('span');
        badge.className = 'series-badge';
        badge.setAttribute('aria-hidden', 'true');

        const svg = document.createElementNS(SVG_NS, 'svg');
        svg.setAttribute('class', 'series-icon');
        svg.setAttribute('viewBox', '0 0 16 16');
        svg.setAttribute('fill', 'none');
        svg.setAttribute('stroke', 'currentColor');
        svg.setAttribute('stroke-width', '1.65');
        svg.setAttribute('stroke-linecap', 'round');
        svg.setAttribute('stroke-linejoin', 'round');

        const rect = document.createElementNS(SVG_NS, 'rect');
        rect.setAttribute('x', '2');
        rect.setAttribute('y', '4.5');
        rect.setAttribute('width', '9.5');
        rect.setAttribute('height', '9.5');
        rect.setAttribute('rx', '2');

        const path = document.createElementNS(SVG_NS, 'path');
        path.setAttribute('d', 'M5.5 2h6.5a2 2 0 0 1 2 2v6.5');

        svg.appendChild(rect);
        svg.appendChild(path);

        const num = document.createElement('span');
        num.textContent = String(count);

        badge.appendChild(svg);
        badge.appendChild(num);
        return badge;
    };

    const createCardElement = (entry, listIndex, eager = false) => {
        const isSeries = viewMode === 'series';
        const media = isSeries ? entry.cover : entry;
        const label = entry.label;

        const link = document.createElement('a');
        link.href = media.fullSrc;
        link.dataset.index = String(listIndex);
        link.dataset.year = entry.year;
        link.setAttribute('aria-label', label);
        link.className = 'gallery-item-wrapper';

        const img = document.createElement('img');
        img.src = media.thumbSrc;
        img.alt = label;
        img.className = 'gallery-item';
        img.decoding = 'async';
        if (eager) {
            img.fetchPriority = 'high';
        } else {
            img.loading = 'lazy';
        }
        bindImageReveal(img);
        link.appendChild(img);

        if (isSeries && entry.items.length > 1) {
            link.appendChild(createSeriesBadge(entry.items.length));
        }

        return link;
    };

    const computeFilteredList = () => {
        const source = viewMode === 'frames' ? allFrames : allSeries;
        return activeYear === 'all'
            ? source
            : source.filter(item => item.year === activeYear);
    };

    const syncControlsState = () => {
        viewBtns.forEach(btn => {
            const isActive = btn.dataset.setView === viewMode;
            btn.classList.toggle('active', isActive);
            btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        });

        yearPills.forEach(pill => {
            const isSelected = pill.dataset.year === activeYear;
            pill.classList.toggle('active', isSelected);
            pill.setAttribute('aria-pressed', isSelected ? 'true' : 'false');
            const countEl = pill.querySelector('.year-count');
            if (countEl) {
                const nextCount = viewMode === 'frames'
                    ? pill.dataset.framesCount
                    : pill.dataset.seriesCount;
                if (nextCount) countEl.textContent = nextCount;
            }
        });
    };

    const syncUrlState = () => {
        const url = new URL(window.location.href);
        if (activeYear === 'all') {
            url.searchParams.delete('year');
        } else {
            url.searchParams.set('year', activeYear);
        }
        url.searchParams.delete('view');
        window.history.replaceState(null, '', url.pathname + url.search + url.hash);
    };

    const loadMorePhotos = () => {
        if (!gallery || currentIndex >= filteredList.length) return;

        const fragment = document.createDocumentFragment();
        const nextBatch = filteredList.slice(currentIndex, currentIndex + BATCH_SIZE);

        nextBatch.forEach((entry, idx) => {
            const listIndex = currentIndex + idx;
            const isEager = currentIndex === 0 && idx < 6;
            fragment.appendChild(createCardElement(entry, listIndex, isEager));
        });

        gallery.appendChild(fragment);
        currentIndex += BATCH_SIZE;
    };

    const rebuildGallery = (scrollToTop = false) => {
        filteredList = computeFilteredList();
        syncControlsState();
        if (gallery) {
            gallery.textContent = '';
            currentIndex = 0;
            loadMorePhotos();
        }
        if (scrollToTop) {
            window.scrollTo(0, 0);
        }
    };

    if (allFrames.length > 0) {
        if (viewMode === 'series' && activeYear === 'all') {
            filteredList = allSeries;
            syncControlsState();
        } else {
            rebuildGallery(false);
        }
    }

    viewBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const nextView = btn.dataset.setView === 'frames' ? 'frames' : 'series';
            if (nextView === viewMode) return;
            viewMode = nextView;
            localStorage.setItem('kokos_view', viewMode);
            rebuildGallery(true);
        });
    });

    yearPills.forEach(pill => {
        pill.addEventListener('click', () => {
            const targetYear = validYears.has(pill.dataset.year) ? pill.dataset.year : 'all';
            if (targetYear === activeYear) {
                if (window.scrollY > 0) {
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                }
                return;
            }
            activeYear = targetYear;
            syncUrlState();
            rebuildGallery(true);
        });
    });

    // Клік на логотип у шапці скидає фільтр року і повертає на початок архіву
    if (brandHome) {
        brandHome.addEventListener('click', (e) => {
            if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
            e.preventDefault();
            if (activeYear !== 'all') {
                activeYear = 'all';
                syncUrlState();
                rebuildGallery(true);
            } else if (window.scrollY > 0) {
                window.scrollTo({ top: 0, behavior: 'smooth' });
            }
        });
    }

    // 4. Високопродуктивний лайтбокс Fancybox 5 (Серії відкривають карусель поста, Кадри — весь зріз)
    if (gallery) {
        gallery.addEventListener('click', (e) => {
            if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
            const card = e.target.closest('.gallery-item-wrapper');
            if (!card || !window.Fancybox || filteredList.length === 0) return;

            e.preventDefault();
            const parsedIndex = parseInt(card.dataset.index || '0', 10);
            const safeIndex = Number.isNaN(parsedIndex)
                ? 0
                : Math.max(0, Math.min(parsedIndex, filteredList.length - 1));

            let slides;
            let startIndex;

            if (viewMode === 'series') {
                const group = filteredList[safeIndex];
                slides = group.items.map(item => ({
                    src: item.fullSrc,
                    type: 'image',
                    alt: item.label,
                }));
                startIndex = 0;
            } else {
                slides = filteredList.map(item => ({
                    src: item.fullSrc,
                    type: 'image',
                    alt: item.label,
                }));
                startIndex = safeIndex;
            }

            window.Fancybox.show(slides, {
                startIndex,
                animated: true,
                showClass: 'f-fadeIn',
                hideClass: 'f-fadeOut',
                dragToClose: true,
                compact: false,
                placeFocusBack: false,
                caption: () => '',
                Carousel: {
                    transition: 'crossfade',
                    infinite: false,
                },
                Images: {
                    zoom: false,
                    Panzoom: {
                        maxScale: 3.5,
                    },
                },
                Thumbs: false,
                Toolbar: {
                    display: {
                        left: ['infobar'],
                        middle: [],
                        right: ['iterateZoom', 'fullscreen', 'close'],
                    },
                },
            });
        });
    }

    // 5. Sentinel для автоматичного довантаження при скролі
    if (gallery && allFrames.length > 0) {
        const sentinel = document.createElement('div');
        sentinel.className = 'scroll-sentinel';
        sentinel.setAttribute('aria-hidden', 'true');
        gallery.after(sentinel);

        const scrollObserver = new IntersectionObserver((entries) => {
            if (entries[0].isIntersecting) {
                loadMorePhotos();
            }
        }, {
            rootMargin: '700px 0px',
            threshold: 0,
        });

        scrollObserver.observe(sentinel);
    }

    // 6. Кнопка «Нагору»
    if (backToTopBtn) {
        let isBtnVisible = false;
        window.addEventListener('scroll', () => {
            const shouldShow = window.scrollY > 700;
            if (shouldShow !== isBtnVisible) {
                isBtnVisible = shouldShow;
                backToTopBtn.classList.toggle('visible', shouldShow);
            }
        }, { passive: true });

        backToTopBtn.addEventListener('click', () => {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }
});
