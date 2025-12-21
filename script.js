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

    // Observer for fade-in animation
    const fadeObserverOptions = {
        threshold: 0,
        rootMargin: '0px 0px 50px 0px' // Trigger slightly before entering viewport
    };

    const fadeObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
                observer.unobserve(entry.target);
            }
        });
    }, fadeObserverOptions);

    // Function to setup fade animation for new items
    const setupFadeAnimation = (elements) => {
        elements.forEach(item => {
            // Check if already visible (e.g. from previous load)
            if (item.style.opacity === '1') return;
            
            item.style.opacity = '0';
            item.style.transform = 'translateY(30px)'; // Reduced for smoother feel
            item.style.transition = 'opacity 0.8s ease-out, transform 0.8s ease-out';
            fadeObserver.observe(item);
            
            // Fallback: Show after 2 seconds if observer fails
            setTimeout(() => {
                if (item.style.opacity === '0') {
                    item.style.opacity = '1';
                    item.style.transform = 'translateY(0)';
                }
            }, 2000);
        });
    };

    // Initial setup for existing items
    const initialItems = document.querySelectorAll('.gallery-item-wrapper');
    setupFadeAnimation(initialItems);

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
                const link = document.createElement('a');
                link.href = item.src;
                link.dataset.fancybox = "gallery";
                link.className = "gallery-item-wrapper";

                const img = document.createElement('img');
                img.src = item.src;
                img.alt = item.caption;
                img.className = "gallery-item";
                img.loading = "lazy"; // Native lazy loading support
                
                link.appendChild(img);
                fragment.appendChild(link);
                newElements.push(link);
            });

            gallery.appendChild(fragment);
            setupFadeAnimation(newElements);
            
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
            rootMargin: '400px', // Load much earlier
            threshold: 0 
        });

        scrollObserver.observe(sentinel);
    }
});