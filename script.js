document.addEventListener('DOMContentLoaded', () => {
    const MONTHS_UK = [
        'січ', 'лют', 'бер', 'кві', 'тра', 'чер',
        'лип', 'сер', 'вер', 'жов', 'лис', 'гру'
    ];

    const gallery = document.querySelector('.gallery');
    const backToTopBtn = document.getElementById('backToTop');
    const densityBtns = document.querySelectorAll('[data-set-density]');
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

    // 2. Форматування доступного підпису (alt / aria-label) з імені файлу
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

    // 3. Плавна поява карток при скролі
    const fadeObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.remove('fade-init');
                observer.unobserve(entry.target);
            }
        });
    }, {
        threshold: 0,
        rootMargin: '0px 0px 100px 0px',
    });

    // 4. Нескінченний скрол та фільтрація за роками (із синхронізацією в URL ?year=YYYY)
    const allRawItems = Array.isArray(window.GALLERY_ALL) ? window.GALLERY_ALL : [];
    const allParsed = allRawItems.map(parseEntry);
    const validYears = new Set(Array.from(yearPills).map(p => p.dataset.year).filter(Boolean));

    let activeYear = 'all';
    let filteredList = allParsed;
    const initialDomCount = gallery ? gallery.querySelectorAll('.gallery-item-wrapper').length : 0;
    let currentIndex = initialDomCount;
    const BATCH_SIZE = 24;

    const createCardElement = (entry, listIndex, eager = false) => {
        const link = document.createElement('a');
        link.href = entry.fullSrc;
        link.dataset.index = String(listIndex);
        link.dataset.year = entry.year;
        link.setAttribute('aria-label', entry.label);
        link.className = eager ? 'gallery-item-wrapper' : 'gallery-item-wrapper fade-init';

        const img = document.createElement('img');
        img.src = entry.thumbSrc;
        img.alt = entry.label;
        img.className = 'gallery-item';
        img.decoding = 'async';
        if (eager) {
            img.fetchPriority = 'high';
        } else {
            img.loading = 'lazy';
        }

        link.appendChild(img);
        return link;
    };

    const loadMorePhotos = () => {
        if (!gallery || currentIndex >= filteredList.length) return;

        const fragment = document.createDocumentFragment();
        const nextBatch = filteredList.slice(currentIndex, currentIndex + BATCH_SIZE);
        const toObserve = [];

        nextBatch.forEach((entry, idx) => {
            const listIndex = currentIndex + idx;
            const isEager = currentIndex === 0 && idx < 6;
            const card = createCardElement(entry, listIndex, isEager);
            fragment.appendChild(card);
            if (!isEager) {
                toObserve.push(card);
            }
        });

        gallery.appendChild(fragment);
        toObserve.forEach(el => fadeObserver.observe(el));
        currentIndex += BATCH_SIZE;
    };

    const applyYearFilter = (year, updateUrl = true) => {
        const targetYear = validYears.has(year) ? year : 'all';
        if (targetYear === activeYear) return;

        activeYear = targetYear;
        yearPills.forEach(p => {
            const isSelected = p.dataset.year === targetYear;
            p.classList.toggle('active', isSelected);
            p.setAttribute('aria-pressed', isSelected ? 'true' : 'false');
        });

        filteredList = targetYear === 'all'
            ? allParsed
            : allParsed.filter(item => item.year === targetYear);

        if (gallery) {
            gallery.innerHTML = '';
            currentIndex = 0;
            loadMorePhotos();
        }

        if (updateUrl) {
            const url = new URL(window.location.href);
            if (targetYear === 'all') {
                url.searchParams.delete('year');
            } else {
                url.searchParams.set('year', targetYear);
            }
            window.history.replaceState(null, '', url.pathname + url.search + url.hash);
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
    };

    if (yearPills.length > 0 && allParsed.length > 0) {
        yearPills.forEach(pill => {
            pill.addEventListener('click', () => {
                applyYearFilter(pill.dataset.year || 'all', true);
            });
        });

        const urlYear = new URLSearchParams(window.location.search).get('year');
        if (urlYear && urlYear !== 'all' && validYears.has(urlYear)) {
            applyYearFilter(urlYear, false);
        }
    }

    // 5. Повноцінний лайтбокс Fancybox 5 по всьому відфільтрованому архіву (без обриву на межі DOM-батча)
    if (gallery) {
        gallery.addEventListener('click', (e) => {
            if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
            const card = e.target.closest('.gallery-item-wrapper');
            if (!card || !window.Fancybox || filteredList.length === 0) return;

            e.preventDefault();
            const parsedIndex = parseInt(card.dataset.index || '0', 10);
            const startIndex = Number.isNaN(parsedIndex)
                ? 0
                : Math.max(0, Math.min(parsedIndex, filteredList.length - 1));

            const renderedCards = gallery.querySelectorAll('.gallery-item-wrapper');
            const slides = filteredList.map((item, idx) => ({
                src: item.fullSrc,
                thumbSrc: item.thumbSrc,
                type: 'image',
                alt: item.label,
                triggerEl: idx < renderedCards.length ? renderedCards[idx] : undefined,
            }));

            window.Fancybox.show(slides, {
                startIndex,
                animated: true,
                showClass: 'fancybox-fadeIn',
                hideClass: 'fancybox-fadeOut',
                dragToClose: true,
                compact: false,
                caption: () => '',
                Images: {
                    zoom: true,
                    Panzoom: {
                        maxScale: 3.5,
                    },
                },
                Thumbs: {
                    type: 'modern',
                    autoStart: false,
                },
                Toolbar: {
                    display: {
                        left: ['infobar'],
                        middle: [],
                        right: ['iterateZoom', 'thumbs', 'fullscreen', 'close'],
                    },
                },
            });
        });
    }

    // 6. Sentinel для автоматичного довантаження при скролі
    if (gallery && allParsed.length > 0) {
        const sentinel = document.createElement('div');
        sentinel.className = 'scroll-sentinel';
        sentinel.setAttribute('aria-hidden', 'true');
        gallery.after(sentinel);

        const scrollObserver = new IntersectionObserver((entries) => {
            if (entries[0].isIntersecting) {
                loadMorePhotos();
            }
        }, {
            rootMargin: '600px 0px',
            threshold: 0,
        });

        scrollObserver.observe(sentinel);
    }

    // 7. Кнопка «Нагору»
    if (backToTopBtn) {
        window.addEventListener('scroll', () => {
            backToTopBtn.classList.toggle('visible', window.scrollY > 700);
        }, { passive: true });

        backToTopBtn.addEventListener('click', () => {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }
});
