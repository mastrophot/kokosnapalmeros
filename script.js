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
        threshold: 0.1
    };

    const fadeObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
                observer.unobserve(entry.target); // Stop observing once visible
            }
        });
    }, fadeObserverOptions);

    // Function to setup fade animation for new items
    const setupFadeAnimation = (elements) => {
        elements.forEach(item => {
            item.style.opacity = '0';
            item.style.transform = 'translateY(50px)';
            item.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
            fadeObserver.observe(item);
        });
    };

    // Initial setup for existing items
    const initialItems = document.querySelectorAll('.gallery-item-wrapper');
    setupFadeAnimation(initialItems);

    // Infinite Scroll Implementation
    const gallery = document.querySelector('.gallery');
    
    // Check if we have more items to load
    if (window.GALLERY_ITEMS && window.GALLERY_ITEMS.length > 0) {
        let currentIndex = 0;
        const BATCH_SIZE = 12;

        const loadMorePhotos = () => {
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
                
                link.appendChild(img);
                fragment.appendChild(link);
                newElements.push(link);
            });

            gallery.appendChild(fragment);
            setupFadeAnimation(newElements);
            
            currentIndex += BATCH_SIZE;

            // Stop observing if no more items
            if (currentIndex >= window.GALLERY_ITEMS.length) {
                scrollObserver.disconnect();
                if (sentinel) sentinel.remove();
            }
        };

        // Create sentinel for scrolling
        const sentinel = document.createElement('div');
        sentinel.className = 'scroll-sentinel';
        sentinel.style.width = '100%';
        sentinel.style.height = '100px'; 
        // sentinel.style.backgroundColor = 'red'; // Debug
        gallery.after(sentinel);

        const scrollObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                   loadMorePhotos();
                }
            });
        }, { rootMargin: '200px' });

        scrollObserver.observe(sentinel);
    }
});