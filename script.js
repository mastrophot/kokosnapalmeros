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

    // Паралакс ефект
    const gallery = document.querySelector('.gallery');
    const items = document.querySelectorAll('.gallery-item-wrapper');

    window.addEventListener('scroll', () => {
        const scrolled = window.pageYOffset;
        
        items.forEach((item, index) => {
            const speed = 0.1 + (index * 0.05);
            const yPos = -(scrolled * speed);
            item.style.transform = `translateY(${yPos}px)`;
        });
    });

    // Плавна анімація при появі
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
        observer.observe(item);
    });
});