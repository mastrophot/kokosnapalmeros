#!/usr/bin/env python3
"""
Instagram Photo Sync Script (Modern HTML Relay Parser + API Fallback)
Підтримує отримання останніх публічних постів напряму з HTML-відповіді Instagram
(через вбудований Relay Preloader) без потреби в авторизації, а також має
fallback на внутрішнє API за наявності IG_SESSION.
"""

import argparse
import base64
import json
import os
import pickle
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
}


def find_key(obj: Any, target_key: str) -> Any:
    """Рекурсивний пошук ключа в складних структурах JSON/dict/list."""
    if isinstance(obj, dict):
        if target_key in obj:
            return obj[target_key]
        for v in obj.values():
            res = find_key(v, target_key)
            if res is not None:
                return res
    elif isinstance(obj, list):
        for item in obj:
            res = find_key(item, target_key)
            if res is not None:
                return res
    return None


def get_photo_number(path: Path) -> int:
    """Повертає номер фото з імені файлу (_1, _2, ...)."""
    match = re.search(r"_(\d+)\.[^.]+$", path.name)
    return int(match.group(1)) if match else 0


def find_existing_files(shortcode: str) -> List[Path]:
    """Шукає вже завантажені фото поста за shortcode."""
    if not IMAGES_DIR.exists():
        return []
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


def fetch_post_page_details(
    session: requests.Session,
    code: str,
    default_display_uri: Optional[str] = None,
) -> Tuple[List[str], int, Optional[int]]:
    """
    Завантажує сторінку поста /p/{code}/ для отримання всіх фото каруселі,
    кількості лайків та точного timestamp (taken_at).
    """
    media_urls: List[str] = []
    likes = 0
    taken_at = None

    try:
        r = session.get(f"https://www.instagram.com/p/{code}/", headers=BROWSER_HEADERS, timeout=20)
        if r.status_code == 200:
            for script in re.findall(r"<script[^>]*>(.*?)</script>", r.text, re.DOTALL):
                if "carousel_media" in script or "xdt_shortcode_media" in script or "like_count" in script:
                    try:
                        data = json.loads(script)
                        if not likes:
                            l = find_key(data, "like_count")
                            if l is not None:
                                likes = int(l)

                        if not taken_at:
                            t = find_key(data, "taken_at")
                            if t is not None:
                                taken_at = int(t)

                        if not media_urls:
                            items = find_key(data, "carousel_media")
                            if items and isinstance(items, list):
                                for it in items:
                                    uri = it.get("display_uri")
                                    if not uri and "image_versions2" in it:
                                        candidates = it["image_versions2"].get("candidates", [])
                                        if candidates:
                                            uri = candidates[0].get("url")
                                    if uri:
                                        media_urls.append(uri)
                    except Exception:
                        continue
    except Exception as e:
        print(f"  ⚠️ Помилка запиту до поста {code}: {e}")

    if not media_urls and default_display_uri:
        media_urls = [default_display_uri]

    return media_urls, likes, taken_at


def extract_timeline_from_html(session: requests.Session, username: str) -> Optional[List[Dict]]:
    """Парсить стрічку постів безпосередньо з HTML-коду профілю Instagram."""
    print(f"🌐 Запит до сторінки профілю https://www.instagram.com/{username}/ ...")
    profile_url = f"https://www.instagram.com/{username}/"

    try:
        r = session.get(profile_url, headers=BROWSER_HEADERS, timeout=25)
        if r.status_code != 200:
            print(f"⚠️ Отримано статус {r.status_code} для сторінки профілю")
            return None

        timeline = None
        for script in re.findall(r"<script[^>]*>(.*?)</script>", r.text, re.DOTALL):
            if "polaris_ordered_timeline_connection" in script:
                try:
                    data = json.loads(script)
                    timeline = find_key(data, "polaris_ordered_timeline_connection")
                    if timeline:
                        break
                except Exception:
                    continue

        if not timeline:
            print("⚠️ Не знайдено polaris_ordered_timeline_connection в HTML скриптах.")
            return None

        edges = timeline.get("edges", [])
        print(f"✅ Знайдено {len(edges)} постів у стрічці профілю (HTML Relay Preloader).")
        return edges
    except Exception as e:
        print(f"⚠️ Помилка отримання HTML профілю: {e}")
        return None


def download_instagram_photos(
    username: str,
    limit: int = MAX_POSTS,
    test_mode: bool = False,
) -> bool:
    """Синхронізує публічні пости через сучасний HTML Relay парсер."""
    print(f"🔄 Синхронізація фото для @{username}...")
    IMAGES_DIR.mkdir(exist_ok=True)

    # 1. Завантажуємо існуючу історію постів
    existing_posts = load_existing_metadata()
    posts_dict = {p["shortcode"]: p for p in existing_posts if "shortcode" in p}
    print(f"📁 Завантажено {len(posts_dict)} існуючих постів з архіву.")

    session = requests.Session(impersonate="chrome120")

    # 2. Отримуємо останні пости з профілю
    edges = extract_timeline_from_html(session, username)
    if not edges:
        print(f"❌ Не вдалося отримати пости для @{username}.")
        return False

    processed = 0
    new_downloaded = 0

    for edge in edges:
        if processed >= limit:
            break

        node = edge.get("node", {})
        if not node:
            continue

        # Пропускаємо відео
        if (
            node.get("is_video")
            or node.get("media_type") == 2
            or node.get("product_type") in ["clips", "video"]
        ):
            continue

        shortcode = node.get("code")
        if not shortcode:
            continue

        caption = ""
        c_obj = node.get("caption")
        if isinstance(c_obj, dict):
            caption = c_obj.get("text", "")
        elif isinstance(c_obj, str):
            caption = c_obj

        default_display_uri = node.get("display_uri")
        is_carousel = (
            node.get("__typename") == "XIGPolarisCarouselMedia"
            or node.get("carousel_media_count", 1) > 1
        )

        permalink = f"https://www.instagram.com/p/{shortcode}/"

        # Перевіряємо, чи цей пост уже повністю завантажено в metadata
        if shortcode in posts_dict and posts_dict[shortcode].get("images"):
            existing_imgs = posts_dict[shortcode]["images"]
            # Перевіряємо, чи файли існують на диску (якщо images присутня)
            if not IMAGES_DIR.exists() or all((IMAGES_DIR / f).exists() for f in existing_imgs):
                print(f"⏭️ Вже є в архіві: {shortcode} ({len(existing_imgs)} фото)")
                processed += 1
                continue

        print(f"🔍 Опрацювання нового поста: {shortcode} ...")
        # Отримуємо деталі поста та всі зображення каруселі
        media_urls, likes, taken_at = fetch_post_page_details(
            session=session,
            code=shortcode,
            default_display_uri=default_display_uri,
        )

        if not media_urls:
            print(f"  ❌ Не вдалося отримати URL фото для {shortcode}")
            continue

        # Визначаємо дату
        if taken_at:
            post_dt = datetime.fromtimestamp(taken_at, timezone.utc)
        else:
            pk = int(node.get("pk", 0))
            if pk:
                ts_ms = (pk >> 23) + 1314220021721
                post_dt = datetime.fromtimestamp(ts_ms / 1000, timezone.utc)
            else:
                post_dt = datetime.now(timezone.utc)

        filenames: List[str] = []
        for index, media_url in enumerate(media_urls):
            filename = build_filename(post_dt, shortcode, index, len(media_urls))
            filepath = IMAGES_DIR / filename

            if not test_mode and not filepath.exists():
                try:
                    img_resp = session.get(
                        media_url,
                        timeout=30,
                        headers={"Referer": "https://www.instagram.com/"},
                    )
                    if img_resp.status_code == 200:
                        filepath.write_bytes(img_resp.content)
                    else:
                        print(f"  ❌ Помилка завантаження фото {img_resp.status_code} для {filename}")
                except Exception as error:
                    print(f"  ❌ Помилка скачування {filename}: {error}")
                    filenames = []
                    break

            filenames.append(filename)

        if not filenames:
            continue

        new_downloaded += len(filenames)
        if len(filenames) > 1:
            print(f"  ✅ Завантажено карусель ({len(filenames)} фото): {shortcode}")
        else:
            print(f"  ✅ Завантажено фото: {filenames[0]}")

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

        posts_dict[shortcode] = post_data
        processed += 1
        time.sleep(1)

    # Формуємо підсумковий список постів, відсортований за датою DESC
    final_posts = list(posts_dict.values())
    final_posts.sort(key=lambda x: x.get("date", ""), reverse=True)

    save_metadata(username=username, posts_data=final_posts)
    print(
        f"\n✨ Синхронізацію успішно завершено! Завантажено нових файлів: {new_downloaded}. Загалом в архіві: {len(final_posts)} постів."
    )
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Instagram sync via modern HTML Relay parser")
    parser.add_argument("--test", action="store_true", help="Тільки перевірка метаданих")
    parser.add_argument("--limit", type=int, default=MAX_POSTS, help="Макс. кількість постів")
    parser.add_argument("--username", default=INSTAGRAM_USERNAME, help="Instagram username")
    parser.add_argument("--session", default="", help=argparse.SUPPRESS)
    parser.add_argument("--login", default="", help=argparse.SUPPRESS)
    parser.add_argument("--password", default="", help=argparse.SUPPRESS)
    parser.add_argument("--create-session", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if getattr(args, "create_session", False):
        print("ℹ️ Авторизація більше не потрібна. Парсер працює автоматично.")
        sys.exit(0)

    success = download_instagram_photos(
        username=args.username,
        limit=args.limit,
        test_mode=args.test,
    )
    if not success:
        sys.exit(1)
    sys.exit(0)
