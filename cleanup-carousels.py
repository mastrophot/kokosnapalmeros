#!/usr/bin/env python3
"""
Cleanup script - видаляє всі фото з каруселей, залишаючи тільки перше
"""

from pathlib import Path
import re

IMAGES_DIR = Path("images")

def cleanup_carousel_photos():
    """Видаляє всі фото крім першого з кожного поста"""
    
    # Групуємо фото за постами
    posts = {}
    
    for file in IMAGES_DIR.glob("20*.jpg"):
        # Шукаємо патерн: YYYY-MM-DD_HH-MM-SS_UTC_N.jpg або YYYY-MM-DD_HH-MM-SS_UTC.jpg
        match = re.match(r'(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_UTC)(_\d+)?\.jpg', file.name)
        
        if match:
            post_base = match.group(1)
            photo_num = match.group(2) if match.group(2) else "_1"
            
            if post_base not in posts:
                posts[post_base] = []
            posts[post_base].append((file, photo_num))
    
    # Для кожного поста залишаємо тільки перше фото
    deleted_count = 0
    for post_base, files in posts.items():
        # Сортуємо за номером фото
        files.sort(key=lambda x: x[1])
        
        # Видаляємо всі крім першого
        for file, num in files[1:]:
            file.unlink()
            print(f"🗑️  Видалено: {file.name}")
            deleted_count += 1
    
    print(f"\n✨ Очищено! Видалено {deleted_count} додаткових фото з каруселей")
    
    # Підраховуємо скільки постів залишилось
    remaining = len(posts)
    print(f"📊 Залишилось {remaining} унікальних постів")

if __name__ == "__main__":
    cleanup_carousel_photos()
