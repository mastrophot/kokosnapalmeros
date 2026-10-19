document.addEventListener('DOMContentLoaded', () => {
    // Ініціалізація FancyBox
    Fancybox.bind('[data-fancybox="gallery"]', {
        animated: true,
        showClass: "fancybox-fadeIn",
        hideClass: "fancybox-fadeOut",
        dragToClose: false,
        Image: {
            zoom: true,
        },
        toolbar: {
            display: {
                left: [],
                middle: [],
                right: ['close'],
            },
        },
    });

    // Легкий IntersectionObserver без інлайнових transform та тисяч setTimeout
    const fadeObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.remove('fade-init');
                observer.unobserve(entry.target);
            }
        });
    }, {
        threshold: 0,
        rootMargin: '0px 0px 80px 0px'
    });

    const setupFadeAnimation = (elements) => {
        elements.forEach(item => {
            item.classList.add('fade-init');
            fadeObserver.observe(item);
        });
    };

    // Infinite Scroll Implementation
    const gallery = document.querySelector('.gallery');

    if (window.GALLERY_ITEMS && window.GALLERY_ITEMS.length > 0) {
        let currentIndex = 0;
        const BATCH_SIZE = 12;

        const loadMorePhotos = () => {
            if (currentIndex >= window.GALLERY_ITEMS.length) return;

            const fragment = document.createDocumentFragment();
            const nextBatch = window.GALLERY_ITEMS.slice(currentIndex, currentIndex + BATCH_SIZE);
            const newElements = [];

            nextBatch.forEach(item => {
                const isString = typeof item === 'string';
                const src = isString ? `./images/${item}` : item.src;
                const alt = isString
                    ? item.replace(/\.(jpg|jpeg|png)$/i, '').replace(/[_-]/g, ' ')
                    : (item.caption || '');

                const link = document.createElement('a');
                link.href = src;
                link.dataset.fancybox = "gallery";
                link.className = "gallery-item-wrapper fade-init";

                const img = document.createElement('img');
                img.src = src;
                img.alt = alt;
                img.className = "gallery-item";
                img.loading = "lazy";
                img.decoding = "async";

                link.appendChild(img);
                fragment.appendChild(link);
                newElements.push(link);
            });

            gallery.appendChild(fragment);
            newElements.forEach(el => fadeObserver.observe(el));

            currentIndex += BATCH_SIZE;

            if (currentIndex >= window.GALLERY_ITEMS.length) {
                if (scrollObserver) scrollObserver.disconnect();
                const sentinel = document.querySelector('.scroll-sentinel');
                if (sentinel) sentinel.remove();
            }
        };

        // Create sentinel for scrolling
        const sentinel = document.createElement('div');
        sentinel.className = 'scroll-sentinel';
        sentinel.style.cssText = 'width: 100%; height: 50px; clear: both;';
        gallery.after(sentinel);

        const scrollObserver = new IntersectionObserver((entries) => {
            if (entries[0].isIntersecting) {
                loadMorePhotos();
            }
        }, {
            rootMargin: '500px',
            threshold: 0
        });

        scrollObserver.observe(sentinel);
    }
});