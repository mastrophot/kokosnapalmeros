#!/usr/bin/env python3
"""
Instagram Photo Sync Script (instaloader)
Завантажує фото через instaloader — працює з username/password.
Не потребує Facebook Developer Account чи Graph API.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

try:
    import instaloader
except ImportError:
    print("❌ instaloader не встановлено. Запусти: pip install instaloader")
    sys.exit(1)

# Конфігурація
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME", "kokosnapalmeros")
IG_LOGIN_USER = os.getenv("IG_USERNAME", "")
IG_LOGIN_PASS = os.getenv("IG_PASSWORD", "")
IMAGES_DIR = Path("images")
METADATA_FILE = Path("gallery-data.json")
SESSION_DIR = Path(".instaloader-session")
MAX_POSTS = 50


def get_photo_number(path: Path) -> int:
    """Повертає номер фото з імені файлу (_1, _2, ...)."""
    match = re.search(r"_(\d+)\.[^.]+$", path.name)
    return int(match.group(1)) if match else 0


def find_existing_files(shortcode: str) -> List[Path]:
    """Шукає вже завантажені фото поста за shortcode."""
    valid_ext = {".jpg", ".jpeg", ".png", ".webp"}
    files = [
        path
        for path in IMAGES_DIR.iterdir()
        if path.is_file() and shortcode in path.name and path.suffix.lower() in valid_ext
    ]
    files.sort(key=lambda path: (get_photo_number(path), path.name))
    return files


def build_filename(post_dt: datetime, shortcode: str, index: int, total: int) -> str:
    """Генерує ім'я файлу у форматі YYYY-MM-DD_HH-MM-SS_UTC_shortcode[_N].jpg."""
    timestamp = post_dt.strftime("%Y-%m-%d_%H-%M-%S")
    if total > 1:
        return f"{timestamp}_UTC_{shortcode}_{index + 1}.jpg"
    return f"{timestamp}_UTC_{shortcode}.jpg"


def save_metadata(username: str, posts_data: List[Dict]) -> None:
    """Зберігає gallery-data.json."""
    with open(METADATA_FILE, "w", encoding="utf-8") as file:
        json.dump(
            {
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "username": username,
                "posts": posts_data,
            },
            file,
            ensure_ascii=False,
            indent=2,
        )


def download_image(url: str, filepath: Path, loader: instaloader.Instaloader) -> bool:
    """Завантажує зображення по URL."""
    try:
        loader.context.get_and_write_raw(url, filepath)
        return True
    except Exception as error:
        print(f"  ❌ Помилка завантаження: {error}")
        return False


def download_instagram_photos(
    username: str,
    limit: int = MAX_POSTS,
    test_mode: bool = False,
    login_user: str = "",
    login_pass: str = "",
) -> bool:
    """
    Синхронізує фото через instaloader.

    Args:
        username: Instagram username профілю для синхронізації
        limit: Максимальна кількість постів
        test_mode: Якщо True, тільки формує metadata без завантаження файлів
        login_user: Username для авторизації (для приватних акаунтів або обходу rate limits)
        login_pass: Password для авторизації
    """
    print(f"🔄 Завантаження фото з @{username} через instaloader...")

    IMAGES_DIR.mkdir(exist_ok=True)
    SESSION_DIR.mkdir(exist_ok=True)

    # Ініціалізуємо instaloader
    loader = instaloader.Instaloader(
        download_pictures=True,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        post_metadata_txt_pattern="",
        max_connection_attempts=3,
        request_timeout=30,
        quiet=True,
    )

    # Авторизація (опціонально, але допомагає уникнути rate limits)
    session_file = SESSION_DIR / f"session-{login_user}"
    if login_user and login_pass:
        try:
            # Спробуємо завантажити збережену сесію
            if session_file.exists():
                loader.load_session_from_file(login_user, str(session_file))
                print(f"✅ Сесія завантажена для @{login_user}")
            else:
                loader.login(login_user, login_pass)
                loader.save_session_to_file(str(session_file))
                print(f"✅ Авторизація успішна для @{login_user}")
        except instaloader.exceptions.BadCredentialsException:
            print("❌ Невірний логін або пароль")
            return False
        except instaloader.exceptions.TwoFactorAuthRequiredException:
            print("❌ Потрібна 2FA — для CI потрібно використовувати session file")
            print("   Запустіть локально: instaloader --login YOUR_USER")
            print("   Потім скопіюйте session file в CI")
            return False
        except Exception as error:
            print(f"⚠️  Помилка авторизації: {error}")
            print("   Продовжуємо без авторизації (може бути rate limited)...")
    else:
        print("ℹ️  Без авторизації (для публічних профілів)")

    try:
        # Завантажуємо профіль
        profile = instaloader.Profile.from_username(loader.context, username)
        print(f"👤 Профіль: @{profile.username} | {profile.mediacount} постів | {profile.followers} підписників")

        posts_data: List[Dict] = []
        processed = 0

        for post in profile.get_posts():
            if processed >= limit:
                break

            # Пропускаємо відео
            if post.typename == "GraphVideo":
                continue

            shortcode = post.shortcode
            post_dt = post.date_utc.replace(tzinfo=timezone.utc)
            caption = post.caption or ""
            likes = post.likes
            permalink = f"https://www.instagram.com/p/{shortcode}/"

            # Збираємо URL зображень
            media_urls: List[str] = []
            if post.typename == "GraphSidecar":
                # Карусель
                for node in post.get_sidecar_nodes():
                    if not node.is_video and node.display_url:
                        media_urls.append(node.display_url)
            elif post.typename == "GraphImage":
                if post.url:
                    media_urls.append(post.url)

            if not media_urls:
                continue

            # Перевіряємо чи вже завантажено
            existing_files = find_existing_files(shortcode)
            filenames: List[str] = []

            if existing_files:
                filenames = [path.name for path in existing_files]
                print(f"⏭️  Вже існує: {shortcode} ({len(filenames)} фото)")
            else:
                for index, media_url in enumerate(media_urls):
                    filename = build_filename(post_dt, shortcode, index, len(media_urls))
                    filepath = IMAGES_DIR / filename

                    if not test_mode and not filepath.exists():
                        try:
                            # Завантажуємо через requests бо instaloader.context може не мати потрібного методу
                            import urllib.request
                            req = urllib.request.Request(media_url, headers={
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                            })
                            with urllib.request.urlopen(req, timeout=30) as resp:
                                filepath.write_bytes(resp.read())
                        except Exception as error:
                            print(f"  ❌ Помилка завантаження {shortcode}: {error}")
                            filenames = []
                            break

                    filenames.append(filename)

                if not filenames:
                    continue

                if len(filenames) > 1:
                    print(f"✅ Карусель ({len(filenames)} фото): {shortcode}")
                else:
                    print(f"✅ Завантажено: {filenames[0]}")

            post_data = {
                "filename": filenames[0],
                "caption": caption,
                "date": post_dt.isoformat(),
                "likes": likes,
                "shortcode": shortcode,
                "url": permalink,
                "images": filenames,
            }

            if len(filenames) > 1:
                post_data["is_carousel"] = True

            posts_data.append(post_data)
            processed += 1

        save_metadata(username=username, posts_data=posts_data)
        print(f"\n✨ Завершено! Оброблено {len(posts_data)} постів")
        print(f"📄 Метадані збережено в {METADATA_FILE}")
        return True

    except instaloader.exceptions.ProfileNotExistsException:
        print(f"❌ Профіль @{username} не знайдено")
        return False
    except instaloader.exceptions.ConnectionException as error:
        print(f"❌ Помилка з'єднання: {error}")
        return False
    except instaloader.exceptions.QueryReturnedNotFoundException:
        print(f"❌ Профіль @{username} не знайдено або приватний")
        return False
    except Exception as error:
        print(f"❌ Несподівана помилка: {error}")
        import traceback
        traceback.print_exc()
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Instagram photos via instaloader")
    parser.add_argument("--test", action="store_true", help="Тільки metadata, без завантаження файлів")
    parser.add_argument("--limit", type=int, default=MAX_POSTS, help="Максимальна кількість постів")
    parser.add_argument("--username", default=INSTAGRAM_USERNAME, help="Instagram username для синхронізації")
    parser.add_argument("--login", default=IG_LOGIN_USER, help="Username для авторизації")
    parser.add_argument("--password", default=IG_LOGIN_PASS, help="Password для авторизації")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    success = download_instagram_photos(
        args.username,
        limit=args.limit,
        test_mode=args.test,
        login_user=args.login,
        login_pass=args.password,
    )
    sys.exit(0 if success else 1)
