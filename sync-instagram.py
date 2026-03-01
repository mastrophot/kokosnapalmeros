#!/usr/bin/env python3
"""
Instagram Photo Sync Script
Завантажує фото через офіційний Instagram Graph API та зберігає метадані.
"""

import argparse
import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

# Конфігурація
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME", "kokosnapalmeros")
IMAGES_DIR = Path("images")
METADATA_FILE = Path("gallery-data.json")
MAX_POSTS = 20
GRAPH_API_BASE = os.getenv("IG_GRAPH_API_BASE", "https://graph.facebook.com")
GRAPH_API_VERSION = os.getenv("IG_GRAPH_API_VERSION", "v22.0")
IG_USER_ID = os.getenv("IG_USER_ID") or os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN") or os.getenv("INSTAGRAM_GRAPH_ACCESS_TOKEN")
REQUEST_TIMEOUT = int(os.getenv("IG_REQUEST_TIMEOUT_SEC", "30"))
MAX_RETRIES = int(os.getenv("IG_MAX_RETRIES", "4"))


class GraphAPIError(RuntimeError):
    """Помилка роботи з Graph API."""


@dataclass
class InstagramPost:
    shortcode: str
    caption: str
    timestamp: str
    permalink: str
    likes: int
    media_urls: List[str]


def build_graph_url(path: str, params: Optional[Dict[str, str]] = None) -> str:
    """Формує URL для Graph API."""
    base = f"{GRAPH_API_BASE.rstrip('/')}/{GRAPH_API_VERSION}/{path.lstrip('/')}"
    query = dict(params or {})
    query["access_token"] = IG_ACCESS_TOKEN or ""
    return f"{base}?{urlencode(query)}"


def request_json(url: str) -> Dict:
    """Виконує GET запит з retry/backoff для 429/5xx."""
    last_error: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            request = Request(url, headers={"User-Agent": "kokosnapalmeros-sync/2.0"})
            with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            retryable = error.code in {429, 500, 502, 503, 504}
            if retryable and attempt < MAX_RETRIES:
                delay = min(60, (2 ** attempt) + random.random())
                print(f"⚠️  HTTP {error.code}, retry через {delay:.1f}с...")
                time.sleep(delay)
                continue
            last_error = GraphAPIError(f"HTTP {error.code}: {body}")
            break
        except URLError as error:
            if attempt < MAX_RETRIES:
                delay = min(60, (2 ** attempt) + random.random())
                print(f"⚠️  Мережева помилка, retry через {delay:.1f}с...")
                time.sleep(delay)
                continue
            last_error = GraphAPIError(str(error))
            break
    raise last_error or GraphAPIError("Невідома помилка Graph API")


def request_bytes(url: str) -> bytes:
    """Завантажує файл по URL."""
    last_error: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            request = Request(url, headers={"User-Agent": "kokosnapalmeros-sync/2.0"})
            with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                return response.read()
        except HTTPError as error:
            retryable = error.code in {429, 500, 502, 503, 504}
            if retryable and attempt < MAX_RETRIES:
                delay = min(60, (2 ** attempt) + random.random())
                print(f"⚠️  Помилка завантаження файлу HTTP {error.code}, retry через {delay:.1f}с...")
                time.sleep(delay)
                continue
            last_error = error
            break
        except URLError as error:
            if attempt < MAX_RETRIES:
                delay = min(60, (2 ** attempt) + random.random())
                print(f"⚠️  Мережева помилка завантаження файлу, retry через {delay:.1f}с...")
                time.sleep(delay)
                continue
            last_error = error
            break
    raise last_error or RuntimeError("Невідома помилка завантаження файлу")


def parse_shortcode(permalink: str, media_id: str) -> str:
    """Витягує shortcode з permalink."""
    try:
        parts = urlparse(permalink).path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] in {"p", "reel", "tv"}:
            return parts[1]
    except Exception:
        pass
    # Fallback: останні символи ID, щоб ім'я файлу завжди було унікальним
    clean = re.sub(r"[^A-Za-z0-9]", "", media_id)
    return clean[-10:] if clean else "unknown"


def parse_timestamp(timestamp: str) -> datetime:
    """Парсить timestamp Graph API в UTC datetime."""
    formats = ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ")
    for fmt in formats:
        try:
            parsed = datetime.strptime(timestamp, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Unsupported timestamp format: {timestamp}")


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


def fetch_carousel_images(media_id: str) -> List[str]:
    """Отримує URL зображень для carousel."""
    images: List[str] = []
    after: Optional[str] = None

    while True:
        params = {
            "fields": "id,media_type,media_url",
            "limit": "50",
        }
        if after:
            params["after"] = after

        url = build_graph_url(f"{media_id}/children", params)
        payload = request_json(url)

        for child in payload.get("data", []):
            if child.get("media_type") == "IMAGE" and child.get("media_url"):
                images.append(child["media_url"])

        after = payload.get("paging", {}).get("cursors", {}).get("after")
        if not after:
            break

    return images


def fetch_posts(limit: int) -> List[InstagramPost]:
    """Отримує пости з Graph API."""
    posts: List[InstagramPost] = []
    after: Optional[str] = None

    while len(posts) < limit:
        params = {
            "fields": "id,caption,media_type,media_url,permalink,timestamp,like_count",
            "limit": "50",
        }
        if after:
            params["after"] = after

        payload = request_json(build_graph_url(f"{IG_USER_ID}/media", params))
        data = payload.get("data", [])

        if not data:
            break

        for item in data:
            media_type = item.get("media_type")
            media_id = item.get("id", "")
            permalink = item.get("permalink", "")
            timestamp = item.get("timestamp")

            if not timestamp:
                continue

            if media_type == "VIDEO":
                continue

            if media_type == "IMAGE":
                media_urls = [item.get("media_url")] if item.get("media_url") else []
            elif media_type == "CAROUSEL_ALBUM":
                media_urls = fetch_carousel_images(media_id)
            else:
                continue

            if not media_urls:
                continue

            posts.append(
                InstagramPost(
                    shortcode=parse_shortcode(permalink, media_id),
                    caption=item.get("caption") or "",
                    timestamp=timestamp,
                    permalink=permalink,
                    likes=int(item.get("like_count") or 0),
                    media_urls=media_urls,
                )
            )

            if len(posts) >= limit:
                break

        after = payload.get("paging", {}).get("cursors", {}).get("after")
        if not after:
            break

    return posts


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


def build_filename(post_dt: datetime, shortcode: str, index: int, total: int) -> str:
    """Генерує ім'я файлу у форматі YYYY-MM-DD_HH-MM-SS_UTC_shortcode[_N].jpg."""
    timestamp = post_dt.strftime("%Y-%m-%d_%H-%M-%S")
    if total > 1:
        return f"{timestamp}_UTC_{shortcode}_{index + 1}.jpg"
    return f"{timestamp}_UTC_{shortcode}.jpg"


def download_instagram_photos(username: str, limit: int = MAX_POSTS, test_mode: bool = False) -> bool:
    """
    Синхронізує фото через Graph API.

    Args:
        username: Відображуване ім'я профілю в metadata
        limit: Максимальна кількість постів
        test_mode: Якщо True, тільки формує metadata без завантаження файлів
    """
    print(f"🔄 Завантаження фото з @{username} через Graph API...")

    if not IG_USER_ID or not IG_ACCESS_TOKEN:
        print("❌ Відсутні змінні оточення IG_USER_ID та/або IG_ACCESS_TOKEN")
        print("   Додай їх у GitHub Secrets або export локально перед запуском.")
        return False

    IMAGES_DIR.mkdir(exist_ok=True)

    try:
        posts = fetch_posts(limit=limit)
        if not posts:
            print("⚠️  Graph API не повернув жодного поста.")

        posts_data: List[Dict] = []

        for post in posts:
            existing_files = find_existing_files(post.shortcode)
            filenames: List[str] = []

            if existing_files:
                filenames = [path.name for path in existing_files]
                print(f"⏭️  Вже існує: {post.shortcode} ({len(filenames)} фото)")
            else:
                post_dt = parse_timestamp(post.timestamp)
                for index, media_url in enumerate(post.media_urls):
                    filename = build_filename(post_dt, post.shortcode, index, len(post.media_urls))
                    filepath = IMAGES_DIR / filename

                    if not test_mode and not filepath.exists():
                        try:
                            filepath.write_bytes(request_bytes(media_url))
                        except Exception as error:
                            print(f"❌ Помилка завантаження {post.shortcode}: {error}")
                            filenames = []
                            break

                    filenames.append(filename)

                if not filenames:
                    continue

                if len(filenames) > 1:
                    print(f"✅ Завантажено карусель ({len(filenames)} фото): {post.shortcode}")
                else:
                    print(f"✅ Завантажено: {filenames[0]}")

            post_data = {
                "filename": filenames[0],
                "caption": post.caption,
                "date": parse_timestamp(post.timestamp).isoformat(),
                "likes": post.likes,
                "shortcode": post.shortcode,
                "url": post.permalink,
                "images": filenames,
            }

            if len(filenames) > 1:
                post_data["is_carousel"] = True

            posts_data.append(post_data)

        save_metadata(username=username, posts_data=posts_data)
        print(f"\n✨ Завершено! Оброблено {len(posts_data)} постів")
        print(f"📄 Метадані збережено в {METADATA_FILE}")
        return True
    except GraphAPIError as error:
        print(f"❌ Помилка Graph API: {error}")
        return False
    except Exception as error:
        print(f"❌ Несподівана помилка: {error}")
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Instagram photos via Graph API")
    parser.add_argument("--test", action="store_true", help="Тільки metadata, без завантаження файлів")
    parser.add_argument("--limit", type=int, default=MAX_POSTS, help="Максимальна кількість постів")
    parser.add_argument("--username", default=INSTAGRAM_USERNAME, help="Instagram username для metadata")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    success = download_instagram_photos(args.username, limit=args.limit, test_mode=args.test)
    sys.exit(0 if success else 1)
