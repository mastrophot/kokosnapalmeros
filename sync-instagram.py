#!/usr/bin/env python3
"""
Instagram Photo Sync Script (Full-Res GraphQL + HTML Relay Fallback)
Завантажує публічні фото у максимальній оригінальній роздільній здатності
(через image_versions2.candidates), підтримуючи як авторизований GraphQL-запит
для GitHub Actions (IG_SESSION), так і анонімний HTML Relay Preloader.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
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
DEFAULT_GRAPHQL_DOC_ID = "28858033960505345"

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


def strip_gainmap_jpeg(data: bytes) -> bytes:
    """
    Вирізає другий JPEG-потік (Ultra-HDR GainMap / MPF) та hdrgm XMP-метадані,
    залишаючи чистий однопотоковий SDR JPEG для швидкого рендерингу в браузері без GPU-лагів.
    """
    if not data.startswith(b"\xff\xd8"):
        return data
    out = bytearray(b"\xff\xd8")
    i = 2
    n = len(data)
    while i < n - 1:
        if data[i] != 0xFF:
            return data
        while i < n and data[i] == 0xFF:
            i += 1
        if i >= n:
            break
        marker = data[i]
        i += 1
        if marker == 0xD9:  # EOI
            out.extend(b"\xff\xd9")
            return bytes(out)
        if marker == 0xDA:  # SOS (Start of Scan)
            if i + 2 > n:
                return data
            seg_len = int.from_bytes(data[i : i + 2], "big")
            scan_start = i + seg_len
            eoi_pos = data.find(b"\xff\xd9", scan_start)
            if eoi_pos != -1:
                out.extend(b"\xff\xda")
                out.extend(data[i : eoi_pos + 2])
                return bytes(out)
            return data
        if marker in (0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0x01):
            out.extend(bytes([0xFF, marker]))
            continue
        if i + 2 > n:
            return data
        seg_len = int.from_bytes(data[i : i + 2], "big")
        seg_data = data[i : i + seg_len]
        if marker in (0xE1, 0xE2) and (
            b"hdrgm" in seg_data or b"GainMap" in seg_data or seg_data[2:6] == b"MPF\x00"
        ):
            i += seg_len
            continue
        out.extend(bytes([0xFF, marker]))
        out.extend(seg_data)
        i += seg_len
    return data


def get_best_image_url(item: Dict[str, Any]) -> Optional[str]:
    """
    Повертає оптимальний Full-HD (1080px, напр. 1080x1440 / 1080x1080) URL фото без кропу
    з image_versions2.candidates. Уникає як мильних 640px прев'ю (display_uri), так і
    важких 12-мегапіксельних (3072x4096) сирих зображень, що перевантажують браузер.
    """
    if not isinstance(item, dict):
        return None

    img_v2 = item.get("image_versions2")
    if isinstance(img_v2, dict):
        candidates = img_v2.get("candidates", [])
        if isinstance(candidates, list) and candidates:
            valid = [c for c in candidates if isinstance(c, dict) and c.get("url")]
            # Відсіюємо квадратні кропи неквадратних фото (stp=c0.512...)
            non_cropped = [
                c for c in valid if not re.search(r"stp=c\d+\.", c["url"])
            ] or valid

            # 1. Якщо є розміри (GraphQL): шукаємо стандартний 1080px по ширині (1080x1440 / 1080x1080)
            with_dims = [c for c in non_cropped if c.get("width") and c.get("height")]
            if with_dims:
                exact_1080 = [c for c in with_dims if int(c["width"]) == 1080]
                if exact_1080:
                    return max(exact_1080, key=lambda c: int(c["height"]))["url"]
                # Або найбільший кандидат, що не перевищує 1440px по довгій стороні
                reasonable = [
                    c for c in with_dims if max(int(c["width"]), int(c["height"])) <= 1440
                ]
                if reasonable:
                    return max(reasonable, key=lambda c: int(c["width"]) * int(c["height"]))["url"]
                return max(with_dims, key=lambda c: int(c["width"]) * int(c["height"]))["url"]

            # 2. Якщо розмірів немає (HTML Relay): шукаємо некропнутий p1080x1080 або s1080x1080
            for c in non_cropped:
                if "1080x1080" in c["url"]:
                    return c["url"]

            # 3. Fallback — перший некропнутий кандидат
            return non_cropped[0]["url"]

    return item.get("display_uri") or item.get("display_url")


def get_photo_number(path: Path) -> int:
    """Повертає номер фото з імені файлу (_1, _2, ...)."""
    match = re.search(r"_(\d+)\.[^.]+$", path.name)
    return int(match.group(1)) if match else 0


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
    Завантажує сторінку поста /p/{code}/ для отримання всіх фото у повній якості
    (image_versions2.candidates[0]), кількості лайків та точного timestamp.
    """
    media_urls: List[str] = []
    likes = 0
    taken_at = None

    try:
        r = session.get(f"https://www.instagram.com/p/{code}/", headers=BROWSER_HEADERS, timeout=20)
        if r.status_code == 200:
            for script in re.findall(r"<script[^>]*>(.*?)</script>", r.text, re.DOTALL):
                if "image_versions2" in script or "carousel_media" in script or "like_count" in script:
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
                                    uri = get_best_image_url(it)
                                    if uri:
                                        media_urls.append(uri)
                            else:
                                # Одиночне фото
                                single_v2 = find_key(data, "image_versions2")
                                if isinstance(single_v2, dict):
                                    uri = get_best_image_url({"image_versions2": single_v2})
                                    if uri:
                                        media_urls.append(uri)
                    except Exception:
                        continue
    except Exception as e:
        print(f"  ⚠️ Помилка запиту до поста {code}: {e}")

    if not media_urls and default_display_uri:
        media_urls = [default_display_uri]

    return media_urls, likes, taken_at


def extract_timeline_via_graphql(
    session: requests.Session,
    username: str,
    count: int = 12,
) -> Optional[List[Dict]]:
    """
    Отримує стрічку постів через офіційний GraphQL-запит профілю (працює з IG_SESSION у CI).
    Повертає одразу повні об'єкти постів включно з carousel_media та image_versions2.
    """
    profile_url = f"https://www.instagram.com/{username}/"
    try:
        r = session.get(profile_url, headers=BROWSER_HEADERS, timeout=25)
        if r.status_code != 200:
            print(f"⚠️ Статус сторінки профілю (GraphQL init): {r.status_code}")
            return None

        # Якщо у відповіді вже є вбудований Relay Preloader — теж можемо використати,
        # але якщо є токени сесії, GraphQL дає одразу всі каруселі та розміри в одному запиті
        dtsg_m = re.search(r'"DTSGInitialData",\[\],\{"token":"([^"]+)"', r.text)
        lsd_m = re.search(r'"LSD",\[\],\{"token":"([^"]+)"', r.text)
        csrf_m = re.search(r'"csrf_token":"([^"]+)"', r.text)

        if not (dtsg_m and lsd_m and csrf_m):
            return None

        dtsg = dtsg_m.group(1)
        lsd = lsd_m.group(1)
        csrf = csrf_m.group(1)
        session.cookies["csrftoken"] = csrf

        headers = {
            "User-Agent": BROWSER_HEADERS["User-Agent"],
            "X-IG-App-ID": "936619743392459",
            "X-ASBD-ID": "129477",
            "X-CSRFToken": csrf,
            "X-FB-LSD": lsd,
            "X-FB-Friendly-Name": "PolarisProfilePostsTabContentQuery_connection",
            "Referer": profile_url,
            "Content-Type": "application/x-www-form-urlencoded",
        }

        variables = {
            "after": None,
            "before": None,
            "data": {
                "count": count,
                "include_relationship_info": True,
                "latest_besties_reel_media": True,
                "latest_reel_media": True,
            },
            "first": count,
            "include_multi_captions": False,
            "last": None,
            "username": username,
            "__relay_internal__pv__PolarisMultiCaptionCarouselEnabledrelayprovider": False,
            "__relay_internal__pv__PolarisShortDramaEnabledrelayprovider": False,
            "__relay_internal__pv__PolarisThreadsStyleCommentsEnabledrelayprovider": False,
            "__relay_internal__pv__PolarisReelsRecoDebugOverlayEnabledrelayprovider": False,
        }

        resp = session.post(
            "https://www.instagram.com/graphql/query",
            headers=headers,
            data={
                "fb_dtsg": dtsg,
                "lsd": lsd,
                "doc_id": DEFAULT_GRAPHQL_DOC_ID,
                "variables": json.dumps(variables),
            },
            timeout=25,
        )
        if resp.status_code == 200:
            data = resp.json()
            conn = data.get("data", {}).get("xdt_api__v1__feed__user_timeline_graphql_connection")
            if conn and "edges" in conn:
                edges = conn["edges"]
                print(f"✅ Отримано {len(edges)} постів у повній якості через GraphQL API.")
                return edges
    except Exception as e:
        print(f"⚠️ GraphQL запит не вдався: {e}")

    return None


def extract_timeline_from_html_anonymous(username: str) -> Tuple[Optional[List[Dict]], requests.Session]:
    """
    Fallback: парсить стрічку постів із анонімного HTML-коду профілю Instagram (без куків).
    """
    print(f"🌐 Fallback: анонімний запит до https://www.instagram.com/{username}/ ...")
    anon_session = requests.Session(impersonate="chrome120")
    profile_url = f"https://www.instagram.com/{username}/"

    try:
        r = anon_session.get(profile_url, headers=BROWSER_HEADERS, timeout=25)
        if r.status_code != 200:
            print(f"⚠️ Отримано статус {r.status_code} для анонімної сторінки профілю")
            return None, anon_session

        for script in re.findall(r"<script[^>]*>(.*?)</script>", r.text, re.DOTALL):
            if "polaris_ordered_timeline_connection" in script:
                try:
                    data = json.loads(script)
                    timeline = find_key(data, "polaris_ordered_timeline_connection")
                    if timeline and "edges" in timeline:
                        edges = timeline["edges"]
                        print(f"✅ Знайдено {len(edges)} постів у стрічці профілю (HTML Relay Preloader).")
                        return edges, anon_session
                except Exception:
                    continue
    except Exception as e:
        print(f"⚠️ Помилка отримання HTML профілю: {e}")

    return None, anon_session


def download_instagram_photos(
    username: str,
    limit: int = MAX_POSTS,
    test_mode: bool = False,
) -> bool:
    """Синхронізує публічні пости у максимальній роздільній здатності."""
    print(f"🔄 Синхронізація фото для @{username}...")
    IMAGES_DIR.mkdir(exist_ok=True)

    existing_posts = load_existing_metadata()
    posts_dict = {p["shortcode"]: p for p in existing_posts if "shortcode" in p}
    print(f"📁 Завантажено {len(posts_dict)} існуючих постів з архіву.")

    edges = None
    active_session = None

    # 1. Якщо є IG_SESSION — пробуємо повноцінний GraphQL запит
    session_val = os.getenv("IG_SESSION", "").strip()
    if session_val:
        cookies = {"sessionid": session_val}
        raw_sid = urllib.parse.unquote(session_val)
        if ":" in raw_sid:
            cookies["ds_user_id"] = raw_sid.split(":")[0]
        auth_session = requests.Session(impersonate="chrome120", cookies=cookies)
        edges = extract_timeline_via_graphql(auth_session, username, count=min(limit, 24))
        if edges:
            active_session = auth_session

    # 2. Якщо GraphQL не спрацював або IG_SESSION немає — використовуємо чисту анонімну сесію
    if not edges:
        edges, active_session = extract_timeline_from_html_anonymous(username)

    if not edges or not active_session:
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

        permalink = f"https://www.instagram.com/p/{shortcode}/"

        # Перевіряємо, чи цей пост уже завантажено і всі його файли існують на диску
        if shortcode in posts_dict and posts_dict[shortcode].get("images"):
            existing_imgs = posts_dict[shortcode]["images"]
            if test_mode or (IMAGES_DIR.exists() and all((IMAGES_DIR / f).exists() for f in existing_imgs)):
                print(f"⏭️ Вже є в архіві: {shortcode} ({len(existing_imgs)} фото)")
                processed += 1
                continue

        print(f"🔍 Опрацювання поста: {shortcode} ...")

        # Перевіряємо, чи вже є повні дані image_versions2 безпосередньо у GraphQL-вузлі
        media_urls: List[str] = []
        likes = int(node.get("like_count") or 0)
        taken_at = node.get("taken_at")

        if node.get("carousel_media") and isinstance(node["carousel_media"], list):
            for item in node["carousel_media"]:
                if item.get("media_type") == 2:
                    continue
                u = get_best_image_url(item)
                if u:
                    media_urls.append(u)
        elif node.get("image_versions2"):
            u = get_best_image_url(node)
            if u:
                media_urls.append(u)

        # Якщо у вузлі немає image_versions2 (наприклад, анонімний HTML preloader),
        # завантажуємо сторінку поста /p/{shortcode}/ для отримання оригіналів
        if not media_urls:
            media_urls, page_likes, page_taken_at = fetch_post_page_details(
                session=active_session,
                code=shortcode,
                default_display_uri=get_best_image_url(node),
            )
            if not likes and page_likes:
                likes = page_likes
            if not taken_at and page_taken_at:
                taken_at = page_taken_at

        if not media_urls:
            print(f"  ❌ Не вдалося отримати URL фото для {shortcode}")
            continue

        # Визначаємо дату
        if taken_at:
            post_dt = datetime.fromtimestamp(int(taken_at), timezone.utc)
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
                    img_resp = active_session.get(
                        media_url,
                        timeout=30,
                        headers={"Referer": "https://www.instagram.com/"},
                    )
                    if img_resp.status_code == 200:
                        filepath.write_bytes(strip_gainmap_jpeg(img_resp.content))
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
            print(f"  ✅ Завантажено карусель у повній якості ({len(filenames)} фото): {shortcode}")
        else:
            print(f"  ✅ Завантажено фото у повній якості: {filenames[0]}")

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

    final_posts = list(posts_dict.values())
    final_posts.sort(key=lambda x: x.get("date", ""), reverse=True)

    if new_downloaded > 0 or not METADATA_FILE.is_file():
        save_metadata(username=username, posts_data=final_posts)
    print(
        f"\n✨ Синхронізацію успішно завершено! Завантажено у повній якості: {new_downloaded}. Загалом в архіві: {len(final_posts)} постів."
    )
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Instagram full-res sync")
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
    success = download_instagram_photos(
        username=args.username,
        limit=args.limit,
        test_mode=args.test,
    )
    if not success:
        sys.exit(1)
    sys.exit(0)
