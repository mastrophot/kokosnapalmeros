#!/usr/bin/env python3
"""
Instagram Photo Sync Script (instaloader)
Завантажує фото через instaloader — працює з session file або username/password.

Для CI (GitHub Actions):
  1. Запусти локально: python3 sync-instagram.py --create-session
  2. Скопіюй вивід (base64 строку) в GitHub Secret IG_SESSION
  3. Workflow автоматично відновить сесію з цього секрету

Для локального використання:
  python3 sync-instagram.py --login YOUR_USER --password YOUR_PASS
"""

import argparse
import base64
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
IG_SESSION_B64 = os.getenv("IG_SESSION", "")
IMAGES_DIR = Path("images")
METADATA_FILE = Path("gallery-data.json")
SESSION_FILE = Path(".instaloader-session/session")
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


def create_and_export_session(login_user: str, login_pass: str) -> None:
    """
    Створює інтерактивну сесію (з можливістю 2FA) та експортує як base64.
    Запускати ТІЛЬКИ локально!
    """
    loader = instaloader.Instaloader()

    print(f"🔐 Логін як @{login_user}...")
    try:
        loader.login(login_user, login_pass)
    except instaloader.exceptions.TwoFactorAuthRequiredException:
        code = input("📱 Введи 2FA код: ").strip()
        loader.two_factor_login(code)

    SESSION_FILE.parent.mkdir(exist_ok=True)
    loader.save_session_to_file(str(SESSION_FILE))

    # Читаємо та кодуємо в base64
    session_bytes = SESSION_FILE.read_bytes()
    session_b64 = base64.b64encode(session_bytes).decode("ascii")

    print(f"\n✅ Сесія створена!")
    print(f"📋 Скопіюй цю строку як GitHub Secret 'IG_SESSION':\n")
    print(session_b64)
    print(f"\n💡 gh secret set IG_SESSION --repo mastrophot/kokosnapalmeros <<< '{session_b64}'")


def setup_loader_with_session(loader: instaloader.Instaloader) -> bool:
    """Відновлює сесію з base64-секрету або файлу."""
    # Варіант 1: base64-секрет (CI)
    if IG_SESSION_B64:
        try:
            SESSION_FILE.parent.mkdir(exist_ok=True)
            SESSION_FILE.write_bytes(base64.b64decode(IG_SESSION_B64))
            # Визначаємо ім'я користувача з сесії
            login_user = IG_LOGIN_USER or INSTAGRAM_USERNAME
            loader.load_session_from_file(login_user, str(SESSION_FILE))
            print(f"✅ Сесія відновлена з IG_SESSION секрету")
            return True
        except Exception as error:
            print(f"⚠️  Помилка відновлення сесії: {error}")
            return False

    # Варіант 2: існуючий файл сесії (локально)
    if SESSION_FILE.exists():
        try:
            login_user = IG_LOGIN_USER or INSTAGRAM_USERNAME
            loader.load_session_from_file(login_user, str(SESSION_FILE))
            print(f"✅ Сесія завантажена з файлу")
            return True
        except Exception as error:
            print(f"⚠️  Сесія протухла: {error}")
            return False

    # Варіант 3: логін/пароль
    if IG_LOGIN_USER and IG_LOGIN_PASS:
        try:
            loader.login(IG_LOGIN_USER, IG_LOGIN_PASS)
            SESSION_FILE.parent.mkdir(exist_ok=True)
            loader.save_session_to_file(str(SESSION_FILE))
            print(f"✅ Логін успішний для @{IG_LOGIN_USER}")
            return True
        except Exception as error:
            print(f"⚠️  Помилка логіну: {error}")
            return False

    print("ℹ️  Без авторизації")
    return False


def download_instagram_photos(
    username: str,
    limit: int = MAX_POSTS,
    test_mode: bool = False,
) -> bool:
    """Синхронізує фото через instaloader."""
    print(f"🔄 Завантаження фото з @{username} через instaloader...")

    IMAGES_DIR.mkdir(exist_ok=True)

    loader = instaloader.Instaloader(
        download_pictures=True,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        post_metadata_txt_pattern="",
        max_connection_attempts=5,
        request_timeout=60,
        quiet=False,
    )

    logged_in = setup_loader_with_session(loader)
    if not logged_in:
        print("⚠️  Продовжуємо без авторизації (може бути rate limited)...")

    try:
        # Retry profile loading — Instagram може повертати 403 на перший запит
        import time as _time
        profile = None
        for attempt in range(1, 4):
            try:
                profile = instaloader.Profile.from_username(loader.context, username)
                break
            except (instaloader.exceptions.ProfileNotExistsException,
                    instaloader.exceptions.ConnectionException,
                    instaloader.exceptions.QueryReturnedNotFoundException) as retry_err:
                if attempt < 3:
                    delay = attempt * 10
                    print(f"⚠️  Спроба {attempt}/3 невдала: {retry_err}")
                    print(f"    Retry через {delay}с...")
                    _time.sleep(delay)
                else:
                    raise

        if profile is None:
            print(f"❌ Не вдалося завантажити профіль @{username} після 3 спроб")
            return False

        print(f"👤 @{profile.username} | {profile.mediacount} постів | {profile.followers} підписників")

        posts_data: List[Dict] = []
        processed = 0

        for post in profile.get_posts():
            if processed >= limit:
                break

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
                for node in post.get_sidecar_nodes():
                    if not node.is_video and node.display_url:
                        media_urls.append(node.display_url)
            elif post.typename == "GraphImage":
                if post.url:
                    media_urls.append(post.url)

            if not media_urls:
                continue

            existing_files = find_existing_files(shortcode)
            filenames: List[str] = []

            if existing_files:
                filenames = [path.name for path in existing_files]
                print(f"⏭️  Вже є: {shortcode} ({len(filenames)} фото)")
            else:
                for index, media_url in enumerate(media_urls):
                    filename = build_filename(post_dt, shortcode, index, len(media_urls))
                    filepath = IMAGES_DIR / filename

                    if not test_mode and not filepath.exists():
                        try:
                            import urllib.request
                            req = urllib.request.Request(media_url, headers={
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                            })
                            with urllib.request.urlopen(req, timeout=30) as resp:
                                filepath.write_bytes(resp.read())
                        except Exception as error:
                            print(f"  ❌ Помилка: {error}")
                            filenames = []
                            break

                    filenames.append(filename)

                if not filenames:
                    continue

                if len(filenames) > 1:
                    print(f"✅ Карусель ({len(filenames)} фото): {shortcode}")
                else:
                    print(f"✅ {filenames[0]}")

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
        print(f"\n✨ Оброблено {len(posts_data)} постів")
        print(f"📄 Метадані: {METADATA_FILE}")
        return True

    except instaloader.exceptions.ProfileNotExistsException as error:
        print(f"❌ Профіль @{username} не знайдено: {error}")
        import traceback
        traceback.print_exc()
        return False
    except instaloader.exceptions.ConnectionException as error:
        print(f"❌ Помилка з'єднання: {error}")
        if "403" in str(error):
            print(f"   Instagram блокує запити з цього IP.")
            print(f"   Сесія можливо протухла — перестворіть:")
            print(f"   python3 sync-instagram.py --create-session --login YOUR_USER")
        import traceback
        traceback.print_exc()
        return False
    except instaloader.exceptions.QueryReturnedNotFoundException as error:
        print(f"❌ Профіль @{username} не знайдено або приватний: {error}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as error:
        print(f"❌ Несподівана помилка: {type(error).__name__}: {error}")
        import traceback
        traceback.print_exc()
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Instagram photos via instaloader")
    parser.add_argument("--test", action="store_true", help="Тільки metadata, без завантаження")
    parser.add_argument("--limit", type=int, default=MAX_POSTS, help="Макс. кількість постів")
    parser.add_argument("--username", default=INSTAGRAM_USERNAME, help="Instagram username")
    parser.add_argument("--login", default=IG_LOGIN_USER, help="Login username")
    parser.add_argument("--password", default=IG_LOGIN_PASS, help="Login password")
    parser.add_argument("--create-session", action="store_true",
                        help="Створити session file та вивести base64 для GitHub Secret")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.create_session:
        if not args.login:
            print("❌ Вкажи --login YOUR_USER")
            sys.exit(1)
        password = args.password
        if not password:
            import getpass
            password = getpass.getpass("Пароль: ")
        create_and_export_session(args.login, password)
    else:
        # Якщо передано login/password через CLI — зберігаємо в env
        if args.login:
            os.environ["IG_USERNAME"] = args.login
            IG_LOGIN_USER = args.login
        if args.password:
            os.environ["IG_PASSWORD"] = args.password
            IG_LOGIN_PASS = args.password

        success = download_instagram_photos(
            args.username,
            limit=args.limit,
            test_mode=args.test,
        )
        sys.exit(0 if success else 1)
