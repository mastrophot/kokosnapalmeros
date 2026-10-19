document.addEventListener('DOMContentLoaded', () => {
    const MONTHS_UK = [
        'січ', 'лют', 'бер', 'кві', 'тра', 'чер',
        'лип', 'сер', 'вер', 'жов', 'лис', 'гру'
    ];

    const gallery = document.querySelector('.gallery');
    const backToTopBtn = document.getElementById('backToTop');
    const densityBtns = document.querySelectorAll('[data-set-density]');
    const yearPills = document.querySelectorAll('.year-pill');

    // 1. Відновлення налаштувань щільності сітки (пропорції 4:5 завжди за замовчуванням)
    document.body.removeAttribute('data-aspect');
    localStorage.removeItem('kokos_aspect');
    const savedDensity = localStorage.getItem('kokos_density') || 'comfy';

    const applyDensity = (density) => {
        if (density === 'compact') {
            document.body.setAttribute('data-density', 'compact');
        } else {
            document.body.removeAttribute('data-density');
        }
        densityBtns.forEach(btn => {
            btn.classList.toggle('active', btn.dataset.setDensity === density);
        });
    };

    applyDensity(savedDensity);

    densityBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const val = btn.dataset.setDensity;
            localStorage.setItem('kokos_density', val);
            applyDensity(val);
        });
    });

    // 2. Ініціалізація Fancybox 5 (відкриває 100% оригінал з href="./images/...", без підписів)
    if (window.Fancybox) {
        Fancybox.bind('[data-fancybox="gallery"]', {
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
    }

    // 3. Допоміжні функції парсингу імені файлу
    const parseEntry = (rawEntry) => {
        if (typeof rawEntry !== 'string') {
            const filename = rawEntry.src.replace('./images/', '');
            return {
                filename,
                fullSrc: rawEntry.src,
                thumbSrc: rawEntry.thumb || rawEntry.src,
                year: filename.slice(0, 4),
            };
        }
        const hasThumb = rawEntry.startsWith('*');
        const filename = hasThumb ? rawEntry.slice(1) : rawEntry;
        return {
            filename,
            fullSrc: `./images/${filename}`,
            thumbSrc: hasThumb ? `./thumbs/${filename}` : `./images/${filename}`,
            year: filename.slice(0, 4),
        };
    };

    const formatReadableDate = (filename) => {
        const m = filename.match(/^(\d{4})[-_](\d{2})[-_](\d{2})/);
        if (!m) return '';
        const year = m[1];
        const monthIdx = parseInt(m[2], 10) - 1;
        const day = parseInt(m[3], 10);
        const monthName = MONTHS_UK[monthIdx] || m[2];
        return `${day} ${monthName} ${year}`;
    };

    // 4. Плавна поява карток при скролі
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

    // 5. Нескінченний скрол та миттєва фільтрація за роками
    const allRawItems = window.GALLERY_ALL || window.GALLERY_ITEMS || [];
    const allParsed = allRawItems.map(parseEntry);

    let activeYear = 'all';
    let filteredList = allParsed;
    const initialDomCount = gallery ? gallery.querySelectorAll('.gallery-item-wrapper').length : 0;
    let currentIndex = initialDomCount;
    const BATCH_SIZE = 24;

    const createCardElement = (entry, eager = false) => {
        const dateLabel = formatReadableDate(entry.filename);

        const link = document.createElement('a');
        link.href = entry.fullSrc;
        link.dataset.fancybox = 'gallery';
        link.dataset.year = entry.year;
        link.className = eager ? 'gallery-item-wrapper' : 'gallery-item-wrapper fade-init';

        const img = document.createElement('img');
        img.src = entry.thumbSrc;
        img.alt = dateLabel || entry.filename;
        img.className = 'gallery-item';
        img.decoding = 'async';
        if (eager) {
            img.fetchPriority = 'high';
        } else {
            img.loading = 'lazy';
        }

        const overlay = document.createElement('div');
        overlay.className = 'card-overlay';
        overlay.innerHTML = `<span class="card-date">${dateLabel}</span><span class="card-zoom-icon"><i class="fas fa-expand-alt"></i></span>`;

        link.appendChild(img);
        link.appendChild(overlay);
        return link;
    };

    const loadMorePhotos = () => {
        if (!gallery || currentIndex >= filteredList.length) return;

        const fragment = document.createDocumentFragment();
        const nextBatch = filteredList.slice(currentIndex, currentIndex + BATCH_SIZE);
        const toObserve = [];

        nextBatch.forEach((entry, idx) => {
            const isEager = currentIndex === 0 && idx < 6;
            const card = createCardElement(entry, isEager);
            fragment.appendChild(card);
            if (!isEager) {
                toObserve.push(card);
            }
        });

        gallery.appendChild(fragment);
        toObserve.forEach(el => fadeObserver.observe(el));
        currentIndex += BATCH_SIZE;
    };

    // Фільтрація за роками
    if (yearPills.length > 0 && allParsed.length > 0) {
        yearPills.forEach(pill => {
            pill.addEventListener('click', () => {
                const year = pill.dataset.year || 'all';
                if (year === activeYear) return;

                activeYear = year;
                yearPills.forEach(p => p.classList.toggle('active', p.dataset.year === year));

                filteredList = year === 'all'
                    ? allParsed
                    : allParsed.filter(item => item.year === year);

                gallery.innerHTML = '';
                currentIndex = 0;
                window.scrollTo({ top: 0, behavior: 'smooth' });
                loadMorePhotos();
            });
        });
    }

    // Sentinel для автоматичного довантаження при скролі
    if (gallery && allParsed.length > 0) {
        const sentinel = document.createElement('div');
        sentinel.className = 'scroll-sentinel';
        sentinel.style.cssText = 'width: 100%; height: 40px;';
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

    // 6. Кнопка «Нагору»
    if (backToTopBtn) {
        window.addEventListener('scroll', () => {
            backToTopBtn.classList.toggle('visible', window.scrollY > 700);
        }, { passive: true });

        backToTopBtn.addEventListener('click', () => {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }
});