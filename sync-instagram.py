#!/usr/bin/env python3
"""
Instagram Photo Sync Script
Завантажує останні фото з Instagram профілю та зберігає метадані
"""

import instaloader
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Конфігурація
INSTAGRAM_USERNAME = "kokosnapalmeros"
IMAGES_DIR = Path("images")
METADATA_FILE = Path("gallery-data.json")
MAX_POSTS = 20  # Максимальна кількість постів для завантаження

def download_instagram_photos(username, limit=MAX_POSTS, test_mode=False):
    """
    Завантажує фото з Instagram профілю
    
    Args:
        username: Instagram username
        limit: Максимальна кількість постів
        test_mode: Якщо True, завантажує тільки метадані без фото
    """
    print(f"🔄 Завантаження фото з @{username}...")
    
    # Створюємо папку для зображень, якщо не існує
    IMAGES_DIR.mkdir(exist_ok=True)
    
    # Ініціалізація Instaloader
    loader = instaloader.Instaloader(
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        post_metadata_txt_pattern='',
        dirname_pattern=str(IMAGES_DIR)
    )
    
    try:
        # Завантажуємо профіль
        profile = instaloader.Profile.from_username(loader.context, username)
        
        posts_data = []
        downloaded_count = 0
        
        # Перебираємо пости
        for post in profile.get_posts():
            if downloaded_count >= limit:
                break
                
            # Пропускаємо відео
            if post.is_video:
                continue
            
            # Генеруємо ім'я файлу для першого фото
            timestamp = post.date_utc.strftime("%Y%m%d_%H%M%S")
            filename = f"instagram_{timestamp}_{post.shortcode}.jpg"
            filepath = IMAGES_DIR / filename
            
            # Пропускаємо, якщо вже завантажено
            if filepath.exists():
                print(f"⏭️  Вже існує: {filename}")
                downloaded_count += 1
                
                # Додаємо до метаданих навіть якщо вже існує
                post_data = {
                    "filename": filename,
                    "caption": post.caption if post.caption else "",
                    "date": post.date_utc.isoformat(),
                    "likes": post.likes,
                    "shortcode": post.shortcode,
                    "url": f"https://www.instagram.com/p/{post.shortcode}/"
                }
                posts_data.append(post_data)
                continue
            
            # Завантажуємо пост (тільки якщо не тестовий режим)
            if not test_mode:
                try:
                    # Завантажуємо пост
                    loader.download_post(post, target=str(IMAGES_DIR / post.shortcode))
                    
                    # Знаходимо перше завантажене фото
                    downloaded_files = sorted(IMAGES_DIR.glob(f"*{post.shortcode}*.jpg"))
                    
                    if downloaded_files:
                        # Беремо тільки перше фото
                        first_photo = downloaded_files[0]
                        
                        # Перейменовуємо на наш формат
                        first_photo.rename(filepath)
                        
                        # Видаляємо інші фото з карусельного поста
                        for extra_file in downloaded_files[1:]:
                            if extra_file.exists():
                                extra_file.unlink()
                                print(f"🗑️  Видалено додаткове фото: {extra_file.name}")
                        
                        # Видаляємо txt файли з метаданими, якщо є
                        for txt_file in IMAGES_DIR.glob(f"*{post.shortcode}*.txt"):
                            txt_file.unlink()
                        
                        # Видаляємо json файли з метаданими, якщо є  
                        for json_file in IMAGES_DIR.glob(f"*{post.shortcode}*.json*"):
                            json_file.unlink()
                        
                        print(f"✅ Завантажено: {filename}")
                    else:
                        print(f"⚠️  Не знайдено фото для {post.shortcode}")
                        continue
                        
                except Exception as e:
                    print(f"❌ Помилка завантаження {post.shortcode}: {e}")
                    continue
            
            # Зберігаємо метадані
            post_data = {
                "filename": filename,
                "caption": post.caption if post.caption else "",
                "date": post.date_utc.isoformat(),
                "likes": post.likes,
                "shortcode": post.shortcode,
                "url": f"https://www.instagram.com/p/{post.shortcode}/"
            }
            posts_data.append(post_data)
            downloaded_count += 1
        
        # Зберігаємо метадані в JSON
        with open(METADATA_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "last_updated": datetime.now().isoformat(),
                "username": username,
                "posts": posts_data
            }, f, ensure_ascii=False, indent=2)
        
        print(f"\n✨ Завершено! Завантажено {downloaded_count} фото")
        print(f"📄 Метадані збережено в {METADATA_FILE}")
        
        return True
        
    except instaloader.exceptions.ProfileNotExistsException:
        print(f"❌ Профіль @{username} не знайдено")
        return False
    except instaloader.exceptions.ConnectionException as e:
        print(f"❌ Помилка з'єднання: {e}")
        return False
    except Exception as e:
        print(f"❌ Несподівана помилка: {e}")
        return False

if __name__ == "__main__":
    # Парсинг аргументів
    test_mode = "--test" in sys.argv
    limit = MAX_POSTS
    
    if "--limit" in sys.argv:
        try:
            limit_index = sys.argv.index("--limit") + 1
            limit = int(sys.argv[limit_index])
        except (IndexError, ValueError):
            print("⚠️  Невірний формат --limit, використовується значення за замовчуванням")
    
    # Запуск
    success = download_instagram_photos(
        INSTAGRAM_USERNAME, 
        limit=limit,
        test_mode=test_mode
    )
    
    sys.exit(0 if success else 1)
