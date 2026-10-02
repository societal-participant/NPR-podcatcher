#!/usr/bin/env python3

import concurrent.futures
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import time
from datetime import datetime

import feedparser
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_DIR = os.path.expanduser("~/npr")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
DB_FILE = os.path.join(BASE_DIR, "npr.db")


def load_config():
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)


def init_database():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            show_id TEXT NOT NULL,
            show_name TEXT NOT NULL,
            guid TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            published TEXT,
            audio_url TEXT NOT NULL,
            filename TEXT,
            downloaded INTEGER DEFAULT 0,
            played INTEGER DEFAULT 0,
            position REAL DEFAULT 0,
            duration REAL,
            added_at TEXT NOT NULL
        )
    """)

    # Upgrade databases created by older versions without losing existing data.
    columns = {row[1] for row in conn.execute("PRAGMA table_info(episodes)")}
    if "duration" not in columns:
        conn.execute("ALTER TABLE episodes ADD COLUMN duration REAL")
        conn.commit()

    # Tracks ETag/Last-Modified per show so an unchanged feed can be
    # skipped with a cheap conditional GET instead of a full re-download
    # and re-parse every single check.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feed_state (
            show_id TEXT PRIMARY KEY,
            etag TEXT,
            last_modified TEXT
        )
    """)

    return conn


def get_feed_state(conn, show_id):
    row = conn.execute(
        "SELECT etag, last_modified FROM feed_state WHERE show_id = ?",
        (show_id,),
    ).fetchone()
    return row if row else (None, None)


def save_feed_state(conn, show_id, etag, last_modified):
    conn.execute(
        """
        INSERT INTO feed_state (show_id, etag, last_modified)
        VALUES (?, ?, ?)
        ON CONFLICT(show_id) DO UPDATE SET
            etag = excluded.etag,
            last_modified = excluded.last_modified
        """,
        (show_id, etag, last_modified),
    )
    conn.commit()


def safe_filename(text):
    text = re.sub(r'[<>:"/\\|?*]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()[:180]


def make_filename(title, guid):
    """Make a readable filename with a stable suffix to avoid title collisions."""
    base = safe_filename(title) or "Untitled episode"
    suffix = hashlib.sha1(str(guid).encode("utf-8")).hexdigest()[:8]
    return f"{base[:170].rstrip()} [{suffix}].mp3"


def get_audio_duration(filename):
    """Return duration in seconds, or None if ffprobe cannot read it."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                filename,
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return float(result.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def download_episode(url, filename, timeout, session=None):
    temp_filename = filename + ".part"
    print("      Downloading...")
    http = session or requests

    try:
        with http.get(
            url,
            stream=True,
            timeout=timeout,
            headers={"User-Agent": "NPR-Pi/1.0"},
        ) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length", 0))
            downloaded = 0
            last_percent = -1

            with open(temp_filename, "wb") as f:
                for chunk in response.iter_content(chunk_size=262144):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        if total:
                            percent = int(downloaded * 100 / total)
                            if percent != last_percent:
                                print(
                                    f"\r      Progress: {percent}% "
                                    f"({downloaded // 1048576} / "
                                    f"{total // 1048576} MB)",
                                    end="",
                                    flush=True,
                                )
                                last_percent = percent

            if total:
                print()

        # A "successful" request can still hand back an empty or cut-off
        # body. Treat that as a failure so it never gets saved as the
        # episode (and the .part file is cleaned up below).
        if downloaded == 0 or (total and downloaded < total):
            raise IOError(
                f"incomplete download ({downloaded} of "
                f"{total if total else 'unknown'} bytes)"
            )

        os.replace(temp_filename, filename)
        return True

    except Exception as e:
        print(f"\n      ERROR: {e}")
        if os.path.exists(temp_filename):
            try:
                os.remove(temp_filename)
            except OSError:
                pass
        return False


def read_feed_head(response, max_items):
    """Read just enough of a streamed RSS response to capture its first
    max_items <item> elements, then stop and hang up. Some feeds have
    hundreds of episodes (megabytes of XML) and we only ever use the
    newest few, so downloading and parsing the rest is pure waste -- and on
    a Zero W it is the slowest part of checking. If the feed turns out to
    be shorter than max_items (or isn't RSS-style), we simply end up
    reading all of it, same as before."""
    end_tag = b"</item>"
    buf = bytearray()
    search_from = 0
    found = 0

    for chunk in response.iter_content(chunk_size=16384):
        if not chunk:
            continue
        buf.extend(chunk)

        while True:
            pos = buf.find(end_tag, search_from)
            if pos == -1:
                break
            found += 1
            search_from = pos + len(end_tag)
            if found >= max_items:
                response.close()
                # Close the tags we cut off so the XML is well-formed.
                return bytes(buf[:search_from]) + b"</channel></rss>"

    return bytes(buf)


def fetch_feed(feed_url, timeout, etag=None, last_modified=None,
               session=None, max_items=3):
    """Fetch the top of an RSS feed, using conditional GET (ETag /
    Last-Modified) so an unchanged feed costs one small round trip
    instead of a download and a parse. Returns:
        (feed_or_None, new_etag, new_last_modified, unchanged)
    feed is None only when unchanged is True.
    """
    headers = {"User-Agent": "NPR-Pi/1.0"}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    response = (session or requests).get(
        feed_url, timeout=timeout, headers=headers, stream=True
    )

    try:
        if response.status_code == 304:
            return None, etag, last_modified, True

        response.raise_for_status()

        feed = feedparser.parse(read_feed_head(response, max_items))
        new_etag = response.headers.get("ETag", etag)
        new_last_modified = response.headers.get("Last-Modified", last_modified)
        return feed, new_etag, new_last_modified, False
    finally:
        response.close()


def check_feed(show_id, show, settings, etag, last_modified, session=None):
    """Runs in a worker thread: network + parsing only. No DB access and
    no printing here - concurrent prints from multiple threads interleave
    and garble the console, and sqlite connections aren't safe to share
    across threads. Returns a plain result tuple for the main thread to
    act on once all checks have finished."""
    try:
        feed, new_etag, new_last_modified, unchanged = fetch_feed(
            show["feed"],
            settings.get("feed_timeout", 15),
            etag,
            last_modified,
            session,
            settings.get("initial_downloads", 3),
        )
        return show_id, feed, new_etag, new_last_modified, unchanged, None
    except requests.RequestException as e:
        return show_id, None, etag, last_modified, False, e


def process_show(conn, show_id, show, settings, feed, session=None):
    """Downloads new/retry episodes from an already-fetched feed. The feed
    itself is fetched separately (and possibly concurrently, across shows)
    by check_feed; this function only ever runs on the main thread, since
    it touches the shared sqlite connection."""

    if not feed.entries:
        print("      ERROR: No episodes found.")
        return

    limit = settings.get("initial_downloads", 3)
    episodes = feed.entries[:limit]
    audio_directory = settings["audio_directory"]
    show_directory = os.path.join(audio_directory, show_id)
    os.makedirs(show_directory, exist_ok=True)

    new_count = 0
    downloaded_count = 0
    retry_count = 0

    for episode in episodes:
        guid = episode.get("id") or episode.get("guid")
        if not guid:
            print("      Skipping episode with no GUID.")
            continue

        existing = conn.execute(
            """
            SELECT id, downloaded, filename, played, duration
            FROM episodes
            WHERE guid = ?
            """,
            (guid,),
        ).fetchone()

        if existing:
            ep_id, downloaded, filepath, played, duration = existing

            # A played episode stays in the database but is never redownloaded.
            if played:
                continue

            # Already downloaded and still present.
            if (downloaded and filepath and os.path.exists(filepath)
                    and os.path.getsize(filepath) > 0):
                continue

            print()
            print(f"      RETRY: {episode.get('title', 'Untitled episode')}")
            audio_url = episode.enclosures[0].href if episode.enclosures else None
            if not audio_url:
                print("      No audio URL available.")
                continue

            success = download_episode(
                audio_url,
                filepath,
                settings.get("download_timeout", 300),
                session,
            )

            if success:
                duration = get_audio_duration(filepath)
                conn.execute(
                    """
                    UPDATE episodes
                    SET downloaded = 1, duration = ?
                    WHERE id = ?
                    """,
                    (duration, ep_id),
                )
                conn.commit()
                downloaded_count += 1
                retry_count += 1
                print(f"      SAVED: {filepath}")
            continue

        if not episode.enclosures:
            print(f"      No audio: {episode.get('title', 'Untitled episode')}")
            continue

        audio_url = episode.enclosures[0].href
        title = episode.get("title", "Untitled episode")
        published = episode.get("published", "")
        filename = make_filename(title, guid)
        filepath = os.path.join(show_directory, filename)

        print()
        print(f"      NEW: {title}")

        success = download_episode(
            audio_url,
            filepath,
            settings.get("download_timeout", 300),
            session,
        )
        duration = get_audio_duration(filepath) if success else None
        now = datetime.now().isoformat(timespec="seconds")

        conn.execute(
            """
            INSERT INTO episodes (
                show_id,
                show_name,
                guid,
                title,
                published,
                audio_url,
                filename,
                downloaded,
                duration,
                added_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                show_id,
                show["name"],
                guid,
                title,
                published,
                audio_url,
                filepath,
                1 if success else 0,
                duration,
                now,
            ),
        )
        conn.commit()
        new_count += 1

        if success:
            downloaded_count += 1
            print(f"      SAVED: {filepath}")

    print()
    print(
        f"      {new_count} new episode(s), "
        f"{retry_count} retried, "
        f"{downloaded_count} downloaded."
    )


def main():
    config = load_config()
    conn = init_database()

    print()
    print("========================================")
    print("        NPR PI LIBRARY UPDATER")
    print("========================================")

    try:
        enabled_shows = {}
        for show_id, show in config["shows"].items():
            if not show.get("enabled", False):
                continue
            if not show.get("feed"):
                print(f"Skipping {show.get('name', show_id)}: no feed configured.")
                continue
            enabled_shows[show_id] = show

        if not enabled_shows:
            print()
            print("No enabled shows with a feed configured.")
            return

        # Feed state (etag/last-modified) is read/written here, on the
        # main thread only, since sqlite connections aren't safe to share
        # across threads. The fetches themselves are pure network I/O
        # though, so those run concurrently below - this is what actually
        # speeds up "checking": without it, a slow feed makes every other
        # show wait behind it instead of being checked at the same time.
        feed_states = {
            show_id: get_feed_state(conn, show_id) for show_id in enabled_shows
        }

        print()
        print(f"Checking {len(enabled_shows)} feed(s)...")
        for show in enabled_shows.values():
            print(f"  - {show['name']}")

        # One shared session for the whole run: connections to the same
        # host get reused (HTTP keep-alive) instead of paying for a fresh
        # TCP + TLS handshake on every request -- a real cost on the
        # Zero W's single slow core. Safe to share across the feed-check
        # threads because these are plain stateless GETs (no cookies/auth).
        session = requests.Session()
        # Retry dropped/failed connections (e.g. a TLS "EOF" from a flaky
        # WiFi link or the server closing a connection) with a short
        # backoff, instead of failing the whole check on the first hiccup.
        retry = Retry(
            total=4,
            connect=4,
            read=3,
            backoff_factor=1.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        adapter = HTTPAdapter(max_retries=retry, pool_maxsize=8)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        results = {}
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(8, len(enabled_shows))
        ) as pool:
            futures = {
                pool.submit(
                    check_feed, show_id, show, config["settings"], *feed_states[show_id], session
                ): show_id
                for show_id, show in enabled_shows.items()
            }
            # Checks run concurrently, but we still print as each one
            # finishes (in whatever order they complete, not necessarily
            # the order above) so there's visible progress the whole time
            # rather than silence until every single one is done.
            for future in concurrent.futures.as_completed(futures):
                show_id, feed, new_etag, new_last_modified, unchanged, error = future.result()
                results[show_id] = (feed, new_etag, new_last_modified, unchanged, error)

                name = enabled_shows[show_id]["name"]
                if error:
                    print(f"  {name}: check failed ({error})")
                elif unchanged:
                    print(f"  {name}: unchanged")
                elif not feed.entries:
                    print(f"  {name}: feed has no episodes")
                else:
                    print(f"  {name}: latest episodes read")

        # Process in the original config order, sequentially, so output
        # stays readable and every download/DB write happens single-threaded.
        for show_id, show in enabled_shows.items():
            feed, new_etag, new_last_modified, unchanged, error = results[show_id]

            print()
            print("=" * 60)
            print(show["name"])
            print("=" * 60)

            if error:
                print(f"      ERROR: Could not fetch feed: {error}")
                continue

            if unchanged:
                print("      Feed unchanged since last check - skipping.")
                continue

            save_feed_state(conn, show_id, new_etag, new_last_modified)
            process_show(conn, show_id, show, config["settings"], feed, session)

        print()
        print("========================================")
        print("             UPDATE COMPLETE")
        print("========================================")
        print()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
