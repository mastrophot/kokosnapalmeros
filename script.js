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

    // Плавна анімація при появі
    const items = document.querySelectorAll('.gallery-item-wrapper');
    const observerOptions = {
        threshold: 0.1
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }
        });
    }, observerOptions);

    items.forEach(item => {
        item.style.opacity = '0';
        item.style.transform = 'translateY(50px)';
        item.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
        observer.observe(item);
    });
});