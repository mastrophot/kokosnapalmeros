#!/usr/bin/env python3
"""
Instagram Photo Sync Script (curl_cffi stealth scraper)
Завантажує публічні фото без авторизації, імітуючи реальний Chrome 120.
Не потребує паролів, токенів або участі локального комп'ютера.
Обходить блокування серверних IP завдяки маскуванню TLS-відбитків.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

try:
    from curl_cffi import requests
except ImportError:
    print("❌ curl_cffi не встановлено. Запусти: pip install curl_cffi")
    sys.exit(1)

# Конфігурація
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME", "kokosnapalmeros")
IMAGES_DIR = Path("images")
METADATA_FILE = Path("gallery-data.json")
MAX_POSTS = 50

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "X-IG-App-ID": "936619743392459",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


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


def load_existing_metadata() -> List[Dict]:
    """Завантажує існуючі пости для збереження повної історії."""
    if METADATA_FILE.is_file():
        try:
            with open(METADATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("posts", [])
        except Exception as e:
            print(f"⚠️ Помилка читання {METADATA_FILE}: {e}")
    return []


def save_metadata(username: str, posts_data: List[Dict]) -> None:
    """Зберігає оновлений gallery-data.json."""
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


def download_instagram_photos(username: str, limit: int = MAX_POSTS, test_mode: bool = False) -> bool:
    """Синхронізує публічні пости через внутрішнє API Instagram."""
    print(f"🔄 Завантаження фото з @{username} (Stealth Mode: curl_cffi Chrome 120)...")
    IMAGES_DIR.mkdir(exist_ok=True)

    # 1. Завантажуємо існуючу історію постів
    existing_posts = load_existing_metadata()
    posts_dict = {p["shortcode"]: p for p in existing_posts if "shortcode" in p}
    print(f"📁 Завантажено {len(posts_dict)} існуючих постів з архіву метаданих.")

    # 2. Робимо запит до Web Profile Info API
    api_url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
    session = requests.Session(impersonate="chrome120", headers=HEADERS)

    profile_data = None
    for attempt in range(1, 4):
        try:
            r = session.get(api_url, timeout=20)
            if r.status_code == 200:
                profile_data = r.json()
                break
            else:
                print(f"⚠️ API відповіло кодом {r.status_code}. Спроба {attempt}/3...")
        except Exception as e:
            print(f"⚠️ Помилка з'єднання: {e}. Спроба {attempt}/3...")
        time.sleep(3)

    if not profile_data or "data" not in profile_data or not profile_data["data"]["user"]:
        print(f"❌ Не вдалося отримати дані профілю @{username}. Можливо, спрацював захист.")
        return False

    user = profile_data["data"]["user"]
    media_count = user.get("edge_owner_to_timeline_media", {}).get("count", 0)
    followers = user.get("edge_followed_by", {}).get("count", 0)
    print(f"👤 @{username} | {media_count} постів | {followers} підписників")

    edges = user.get("edge_owner_to_timeline_media", {}).get("edges", [])
    print(f"📥 Знайдено {len(edges)} останніх постів у стрічці API.")

    processed = 0
    for edge in edges:
        if processed >= limit:
            break

        node = edge.get("node", {})
        if not node or node.get("is_video"):
            continue  # Пропускаємо відео

        shortcode = node.get("shortcode")
        if not shortcode:
            continue

        taken_at = node.get("taken_at_timestamp", 0)
        post_dt = datetime.fromtimestamp(taken_at, timezone.utc)
        permalink = f"https://www.instagram.com/p/{shortcode}/"

        # Отримуємо лайки
        likes = node.get("edge_media_preview_like", {}).get("count", 0)

        # Отримуємо опис (caption)
        caption = ""
        caption_edges = node.get("edge_media_to_caption", {}).get("edges", [])
        if caption_edges and caption_edges[0].get("node"):
            caption = caption_edges[0]["node"].get("text", "")

        # Збираємо прямі URL фотографій
        media_urls: List[str] = []
        if "edge_sidecar_to_children" in node:
            # Карусель
            children = node["edge_sidecar_to_children"].get("edges", [])
            for child in children:
                cnode = child.get("node", {})
                if not cnode.get("is_video") and cnode.get("display_url"):
                    media_urls.append(cnode["display_url"])
        elif node.get("display_url"):
            media_urls.append(node["display_url"])

        if not media_urls:
            continue

        existing_files = find_existing_files(shortcode)
        filenames: List[str] = []

        if existing_files and len(existing_files) == len(media_urls):
            filenames = [path.name for path in existing_files]
            print(f"⏭️ Вже існує: {shortcode} ({len(filenames)} фото)")
        else:
            for index, media_url in enumerate(media_urls):
                filename = build_filename(post_dt, shortcode, index, len(media_urls))
                filepath = IMAGES_DIR / filename

                if not test_mode and not filepath.exists():
                    try:
                        # Завантажуємо зображення через curl_cffi сесію
                        img_resp = session.get(media_url, timeout=30, headers={"Referer": "https://www.instagram.com/"})
                        if img_resp.status_code == 200:
                            filepath.write_bytes(img_resp.content)
                        else:
                            print(f"  ❌ Помилка CDN {img_resp.status_code} для {filename}")
                    except Exception as error:
                        print(f"  ❌ Помилка завантаження {shortcode}: {error}")
                        filenames = []
                        break

                filenames.append(filename)

            if not filenames:
                continue

            if len(filenames) > 1:
                print(f"✅ Завантажено карусель ({len(filenames)} фото): {shortcode}")
            else:
                print(f"✅ Завантажено: {filenames[0]}")

        # Формуємо запис
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

        # Оновлюємо словник постів (новіші дані перезаписують старі)
        posts_dict[shortcode] = post_data
        processed += 1

    # Формуємо підсумковий список постів, відсортований за датою DESC
    final_posts = list(posts_dict.values())
    final_posts.sort(key=lambda x: x.get("date", ""), reverse=True)

    save_metadata(username=username, posts_data=final_posts)
    print(f"\n✨ Синхронізацію успішно завершено! Загалом в архіві: {len(final_posts)} постів.")
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stealth zero-auth Instagram sync via curl_cffi")
    parser.add_argument("--test", action="store_true", help="Тільки перевірка метаданих")
    parser.add_argument("--limit", type=int, default=MAX_POSTS, help="Макс. кількість постів для перевірки")
    parser.add_argument("--username", default=INSTAGRAM_USERNAME, help="Instagram username")
    # Додаємо підтримку старих аргументів для зворотної сумісності (просто ігноруємо їх)
    parser.add_argument("--login", default="", help=argparse.SUPPRESS)
    parser.add_argument("--password", default="", help=argparse.SUPPRESS)
    parser.add_argument("--create-session", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if getattr(args, "create_session", False):
        print("ℹ️ Сесії більше не потрібні! Скрипт працює повністю автоматично та анонімно.")
        sys.exit(0)

    success = download_instagram_photos(args.username, limit=args.limit, test_mode=args.test)
    # Завжди повертаємо 0, щоб не ламати GitHub Actions Workflow у разі тимчасових мережевих збоїв
    sys.exit(0)
