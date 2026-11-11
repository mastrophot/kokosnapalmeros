#!/usr/bin/env python3
"""
Instagram Photo Sync Script (Full-Res GraphQL + HTML Relay Fallback)
Завантажує публічні фото у максимальній оригінальній роздільній здатності
(image_versions2.candidates) + легкі прев'ю (thumbs/), підтримуючи пагінований
авторизований GraphQL-запит (IG_SESSION) та анонімний HTML Relay Preloader.
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
    print("❌ curl_cffi не встановлено. Запусти: pip install -r requirements.txt")
    sys.exit(1)

ROOT_DIR = Path(__file__).resolve().parent
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME", "kokosnapalmeros")
IMAGES_DIR = ROOT_DIR / "images"
THUMBS_DIR = ROOT_DIR / "thumbs"
AVATAR_FILE = IMAGES_DIR / "avatar.jpg"
METADATA_FILE = ROOT_DIR / "gallery-data.json"
MAX_POSTS = 50
DEFAULT_GRAPHQL_DOC_ID = "28858033960505345"

VALID_USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")
VALID_SHORTCODE_RE = re.compile(r"^[A-Za-z0-9_-]{5,32}$")
ALLOWED_MEDIA_SUFFIXES = (".cdninstagram.com", ".fbcdn.net", ".instagram.com", "instagram.com")

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
}


def create_browser_session(cookies: Optional[Dict[str, str]] = None) -> requests.Session:
    """Створює сесію curl_cffi з актуальним TLS-профілем Chrome."""
    for profile in ("chrome", "chrome120"):
        try:
            return requests.Session(impersonate=profile, cookies=cookies)
        except Exception:
            continue
    return requests.Session(cookies=cookies)


def is_safe_media_url(url: str) -> bool:
    """Перевіряє, що URL веде по HTTPS виключно на офіційні CDN Instagram/Meta."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            return False
        host = parsed.hostname.lower()
        return any(host == s or host.endswith(s) for s in ALLOWED_MEDIA_SUFFIXES)
    except Exception:
        return False


def find_key(obj: Any, target_key: str) -> Any:
    """Рекурсивний пошук ключа у вкладених JSON-структурах."""
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
    залишаючи чистий однопотоковий SDR JPEG у 100% оригінальній роздільній здатності.
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


def is_valid_jpeg(data: bytes) -> bool:
    """Перевіряє базову бінарну цілісність JPEG-файлу (захист від HTML-заглушок та обривів)."""
    return len(data) > 512 and data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9")


def download_jpeg(session: requests.Session, url: str, retries: int = 3) -> Optional[bytes]:
    """Безпечно скачує JPEG із CDN з ретраями, валідацією сигнатури та очищенням GainMap."""
    if not is_safe_media_url(url):
        print(f"  ❌ Відхилено недовірений медіа-URL: {url[:80]}")
        return None

    for attempt in range(1, retries + 1):
        try:
            resp = session.get(
                url,
                timeout=30,
                headers={"Referer": "https://www.instagram.com/"},
            )
            if resp.status_code == 200 and resp.content:
                cleaned = strip_gainmap_jpeg(resp.content)
                if is_valid_jpeg(cleaned):
                    return cleaned
                print(f"  ⚠️ Отримано невалідний JPEG (спроба {attempt}/{retries})")
            else:
                print(f"  ⚠️ Статус CDN {resp.status_code} (спроба {attempt}/{retries})")
        except Exception as err:
            print(f"  ⚠️ Помилка мережі при скачуванні (спроба {attempt}/{retries}): {err}")
        if attempt < retries:
            time.sleep(1.5 * attempt)

    return None


def get_best_image_url(item: Dict[str, Any]) -> Optional[str]:
    """Повертає URL фото у максимальній оригінальній роздільній здатності без кропу."""
    if not isinstance(item, dict):
        return None

    img_v2 = item.get("image_versions2")
    if isinstance(img_v2, dict):
        candidates = img_v2.get("candidates", [])
        if isinstance(candidates, list) and candidates:
            valid = [c for c in candidates if isinstance(c, dict) and c.get("url")]
            non_cropped = [
                c for c in valid if not re.search(r"stp=c\d+\.", c["url"])
            ] or valid

            with_dims = [c for c in non_cropped if c.get("width") and c.get("height")]
            if with_dims:
                return max(with_dims, key=lambda c: int(c["width"]) * int(c["height"]))["url"]
            if non_cropped:
                return non_cropped[0]["url"]

    return item.get("display_uri") or item.get("display_url")


def get_thumb_image_url(item: Dict[str, Any]) -> Optional[str]:
    """Повертає легке прев'ю (480px–750px) для швидкої сітки галереї."""
    if not isinstance(item, dict):
        return None

    img_v2 = item.get("image_versions2")
    if isinstance(img_v2, dict):
        candidates = img_v2.get("candidates", [])
        if isinstance(candidates, list) and candidates:
            valid = [c for c in candidates if isinstance(c, dict) and c.get("url")]
            non_cropped = [
                c for c in valid if not re.search(r"stp=c\d+\.", c["url"])
            ] or valid

            with_dims = [c for c in non_cropped if c.get("width") and c.get("height")]
            if with_dims:
                medium = [c for c in with_dims if 480 <= int(c["width"]) <= 750]
                if medium:
                    return max(medium, key=lambda c: int(c["width"]))["url"]
                return min(with_dims, key=lambda c: abs(int(c["width"]) - 640))["url"]

            for c in non_cropped:
                if "640x640" in c["url"] or "720x720" in c["url"]:
                    return c["url"]

    return item.get("display_uri") or item.get("display_url") or get_best_image_url(item)


def build_filename(post_dt: datetime, shortcode: str, index: int, total: int) -> str:
    """Генерує ім'я файлу у форматі YYYY-MM-DD_HH-MM-SS_UTC_shortcode[_N].jpg."""
    timestamp = post_dt.strftime("%Y-%m-%d_%H-%M-%S")
    if total > 1:
        return f"{timestamp}_UTC_{shortcode}_{index + 1}.jpg"
    return f"{timestamp}_UTC_{shortcode}.jpg"


def load_existing_metadata() -> List[Dict]:
    """Завантажує існуючі пости з gallery-data.json."""
    if METADATA_FILE.is_file():
        try:
            with open(METADATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("posts", [])
        except Exception as e:
            print(f"⚠️ Помилка читання {METADATA_FILE}: {e}")
    return []


def save_metadata(username: str, posts_data: List[Dict]) -> None:
    """Атомарно записує оновлений gallery-data.json."""
    tmp_file = METADATA_FILE.with_suffix(".json.tmp")
    with open(tmp_file, "w", encoding="utf-8") as file:
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
    tmp_file.replace(METADATA_FILE)


def fetch_post_page_details(
    session: requests.Session,
    code: str,
    default_display_uri: Optional[str] = None,
) -> Tuple[List[str], List[str], int, Optional[int]]:
    """Завантажує сторінку поста /p/{code}/ для отримання фото у повній якості та прев'ю."""
    media_urls: List[str] = []
    thumb_urls: List[str] = []
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
                                    if it.get("media_type") == 2:
                                        continue
                                    uri = get_best_image_url(it)
                                    if uri:
                                        media_urls.append(uri)
                                        thumb_urls.append(get_thumb_image_url(it) or uri)
                            else:
                                single_v2 = find_key(data, "image_versions2")
                                if isinstance(single_v2, dict):
                                    wrapped = {"image_versions2": single_v2}
                                    uri = get_best_image_url(wrapped)
                                    if uri:
                                        media_urls.append(uri)
                                        thumb_urls.append(get_thumb_image_url(wrapped) or uri)
                    except Exception:
                        continue
    except Exception as e:
        print(f"  ⚠️ Помилка запиту до поста {code}: {e}")

    if not media_urls and default_display_uri:
        media_urls = [default_display_uri]
        thumb_urls = [default_display_uri]

    return media_urls, thumb_urls, likes, taken_at


def extract_timeline_via_graphql(
    session: requests.Session,
    username: str,
    limit: int = MAX_POSTS,
) -> Optional[List[Dict]]:
    """
    Отримує стрічку постів через GraphQL-запит профілю з підтримкою пагінації до limit.
    """
    profile_url = f"https://www.instagram.com/{username}/"
    try:
        r = session.get(profile_url, headers=BROWSER_HEADERS, timeout=25)
        if r.status_code != 200:
            print(f"⚠️ Статус сторінки профілю (GraphQL init): {r.status_code}")
            return None

        dtsg_m = re.search(r'"DTSGInitialData",\[\],\{"token":"([^"]+)"', r.text)
        lsd_m = re.search(r'"LSD",\[\],\{"token":"([^"]+)"', r.text)
        csrf_m = re.search(r'"csrf_token":"([^"]+)"', r.text)

        if not (dtsg_m and lsd_m and csrf_m):
            return None

        dtsg = dtsg_m.group(1)
        lsd = lsd_m.group(1)
        csrf = csrf_m.group(1)
        session.cookies["csrftoken"] = csrf

        # Динамічний пошук doc_id у HTML за наявності, фолбек на перевірений DEFAULT_GRAPHQL_DOC_ID
        doc_id_m = re.search(
            r'PolarisProfilePostsTabContentQuery_connection[^0-9]{1,80}"([0-9]{15,25})"',
            r.text,
        )
        doc_id = doc_id_m.group(1) if doc_id_m else DEFAULT_GRAPHQL_DOC_ID

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

        all_edges: List[Dict] = []
        after_cursor: Optional[str] = None

        while len(all_edges) < limit:
            page_size = min(max(limit - len(all_edges), 12), 24)
            variables = {
                "after": after_cursor,
                "before": None,
                "data": {
                    "count": page_size,
                    "include_relationship_info": True,
                    "latest_besties_reel_media": True,
                    "latest_reel_media": True,
                },
                "first": page_size,
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
                    "doc_id": doc_id,
                    "variables": json.dumps(variables),
                },
                timeout=25,
            )
            if resp.status_code != 200:
                break

            data = resp.json()
            conn = data.get("data", {}).get("xdt_api__v1__feed__user_timeline_graphql_connection")
            if not conn or "edges" not in conn:
                break

            edges = conn.get("edges") or []
            if not edges:
                break

            all_edges.extend(edges)
            page_info = conn.get("page_info") or {}
            if not page_info.get("has_next_page") or not page_info.get("end_cursor"):
                break
            after_cursor = page_info["end_cursor"]
            time.sleep(0.8)

        if all_edges:
            print(f"✅ Отримано {len(all_edges)} постів у повній якості через GraphQL API.")
            return all_edges
    except Exception as e:
        print(f"⚠️ GraphQL запит не вдався: {e}")

    return None


def extract_timeline_from_html_anonymous(username: str) -> Tuple[Optional[List[Dict]], requests.Session]:
    """Fallback: парсить стрічку постів із анонімного HTML-коду профілю Instagram."""
    print(f"🌐 Fallback: анонімний запит до https://www.instagram.com/{username}/ ...")
    anon_session = create_browser_session()
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
    """Синхронізує публічні пости у максимальній роздільній здатності + прев'ю в thumbs/."""
    if not VALID_USERNAME_RE.fullmatch(username):
        print(f"❌ Некоректне ім'я користувача Instagram: {username!r}")
        return False

    print(f"🔄 Синхронізація фото для @{username}...")
    IMAGES_DIR.mkdir(exist_ok=True)
    THUMBS_DIR.mkdir(exist_ok=True)

    existing_posts = load_existing_metadata()
    posts_dict = {p["shortcode"]: p for p in existing_posts if "shortcode" in p}
    print(f"📁 Завантажено {len(posts_dict)} існуючих постів з архіву.")

    edges = None
    active_session = None

    session_val = os.getenv("IG_SESSION", "").strip()
    if session_val:
        cookies = {"sessionid": session_val}
        raw_sid = urllib.parse.unquote(session_val)
        if ":" in raw_sid:
            cookies["ds_user_id"] = raw_sid.split(":")[0]
        auth_session = create_browser_session(cookies=cookies)
        edges = extract_timeline_via_graphql(auth_session, username, limit=limit)
        if edges:
            active_session = auth_session

    if not edges:
        edges, active_session = extract_timeline_from_html_anonymous(username)

    if not edges or not active_session:
        print(f"❌ Не вдалося отримати пости для @{username}.")
        return False

    if not test_mode:
        first_node = edges[0].get("node", {}) if edges else {}
        user_obj = first_node.get("user") or first_node.get("owner") or {}
        avatar_url = user_obj.get("profile_pic_url") if isinstance(user_obj, dict) else None
        if isinstance(avatar_url, str) and is_safe_media_url(avatar_url):
            avatar_bytes = download_jpeg(active_session, avatar_url)
            if avatar_bytes and (not AVATAR_FILE.is_file() or AVATAR_FILE.read_bytes() != avatar_bytes):
                tmp_avatar = AVATAR_FILE.with_suffix(".jpg.tmp")
                tmp_avatar.write_bytes(avatar_bytes)
                tmp_avatar.replace(AVATAR_FILE)
                print("🖼️ Оновлено фото аватара профілю: images/avatar.jpg")

    processed = 0
    new_downloaded = 0

    for edge in edges:
        if processed >= limit:
            break

        node = edge.get("node", {})
        if not node:
            continue

        if (
            node.get("is_video")
            or node.get("media_type") == 2
            or node.get("product_type") in ["clips", "video"]
        ):
            continue

        shortcode = str(node.get("code") or "")
        if not VALID_SHORTCODE_RE.fullmatch(shortcode):
            continue

        caption = ""
        c_obj = node.get("caption")
        if isinstance(c_obj, dict):
            caption = c_obj.get("text", "")
        elif isinstance(c_obj, str):
            caption = c_obj

        permalink = f"https://www.instagram.com/p/{shortcode}/"

        if shortcode in posts_dict and posts_dict[shortcode].get("images"):
            existing_imgs = posts_dict[shortcode]["images"]
            if test_mode or (
                IMAGES_DIR.exists()
                and all((IMAGES_DIR / f).exists() for f in existing_imgs)
            ):
                print(f"⏭️ Вже є в архіві: {shortcode} ({len(existing_imgs)} фото)")
                processed += 1
                continue

        print(f"🔍 Опрацювання поста: {shortcode} ...")

        media_urls: List[str] = []
        thumb_urls: List[str] = []
        likes = int(node.get("like_count") or 0)
        taken_at = node.get("taken_at")

        if node.get("carousel_media") and isinstance(node["carousel_media"], list):
            for item in node["carousel_media"]:
                if item.get("media_type") == 2:
                    continue
                u = get_best_image_url(item)
                if u:
                    media_urls.append(u)
                    thumb_urls.append(get_thumb_image_url(item) or u)
        elif node.get("image_versions2"):
            u = get_best_image_url(node)
            if u:
                media_urls.append(u)
                thumb_urls.append(get_thumb_image_url(node) or u)

        if not media_urls:
            media_urls, thumb_urls, page_likes, page_taken_at = fetch_post_page_details(
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
        newly_written_paths: List[Path] = []

        for index, media_url in enumerate(media_urls):
            filename = build_filename(post_dt, shortcode, index, len(media_urls))
            filepath = IMAGES_DIR / filename
            thumbpath = THUMBS_DIR / filename
            thumb_url = thumb_urls[index] if index < len(thumb_urls) else media_url

            if not test_mode:
                if not filepath.exists():
                    full_bytes = download_jpeg(active_session, media_url)
                    if full_bytes is None:
                        print(f"  ❌ Скасовано пост {shortcode}: не вдалося скачати {filename}")
                        for p in newly_written_paths:
                            p.unlink(missing_ok=True)
                        filenames = []
                        break
                    filepath.write_bytes(full_bytes)
                    newly_written_paths.append(filepath)

                if not thumbpath.exists():
                    thumb_bytes = download_jpeg(active_session, thumb_url)
                    if thumb_bytes is not None:
                        thumbpath.write_bytes(thumb_bytes)
                        newly_written_paths.append(thumbpath)
                    elif filepath.exists():
                        thumbpath.write_bytes(filepath.read_bytes())
                        newly_written_paths.append(thumbpath)

            filenames.append(filename)

        if not filenames:
            continue

        if not test_mode:
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

    if not test_mode and (new_downloaded > 0 or not METADATA_FILE.is_file()):
        save_metadata(username=username, posts_data=final_posts)

    mode_label = " [TEST MODE]" if test_mode else ""
    print(
        f"\n✨ Синхронізацію завершено{mode_label}! "
        f"Завантажено нових кадрів: {new_downloaded}. Загалом в архіві: {len(final_posts)} постів."
    )
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Instagram full-res photo archive sync")
    parser.add_argument("--test", action="store_true", help="Перевірка без запису файлів на диск")
    parser.add_argument("--limit", type=int, default=MAX_POSTS, help="Макс. кількість постів для перевірки")
    parser.add_argument("--username", default=INSTAGRAM_USERNAME, help="Instagram username")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    ok = download_instagram_photos(
        username=args.username,
        limit=max(1, min(args.limit, 200)),
        test_mode=args.test,
    )
    sys.exit(0 if ok else 1)
