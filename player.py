#!/usr/bin/env python3

import json
import os
import re
import socket
import sqlite3
import subprocess
import threading
import time

DB = "/home/pi/npr/npr.db"

SOCKET = "/tmp/npr-mpv.sock"

BASE_DIR = os.path.expanduser("~/npr")

CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# Default audio shaping for small class-D speakers like the PAM8302 amp.
# These tend to have a harsh, boxy resonance somewhere in the 2-6kHz range
# and almost no body below ~300Hz, which can read as "tin can" - but
# overcorrecting swings the other way into "muffled," and a boost anywhere
# in the 200-500Hz "boxy/muddy" zone specifically hurts deep voices, since
# that's where their fundamental and low harmonics live. This version:
#
#   highpass    - cuts rumble/handling noise below what the driver can
#                 reproduce cleanly.
#   bass        - low-shelf cut below ~200Hz for overall bass level. This
#                 is a broad tone control (mirrors "treble" below) - use
#                 it for "too much/little bass overall," separate from
#                 the narrower boxy-resonance fix just below.
#   equalizer 1 - cuts the 350Hz boxy/muddy zone specifically.
#   equalizer 2 - small boost around 1.8kHz for consonant definition and
#                 speech intelligibility, without touching the harsh zone.
#   equalizer 3 - pulls down the main harsh resonant peak around 3kHz.
#   treble      - a gentle high-shelf boost above ~7kHz for "air."
#   acompressor - evens out loudness across quiet/loud speech.
#   alimiter    - final safety ceiling so nothing clips.
#
# Retuned by ear for the PAM8302 + bare speaker: heavy low-end cut for
# boomy low voices, then boosts at 1.3kHz and 2.2kHz for body and
# consonant clarity, a small lift at 3.5kHz, and a treble shelf from 5kHz.
#
# Override this per your actual hardware by setting "audio_filter" under
# "settings" in config.json - no code changes needed to retune it.
DEFAULT_AUDIO_FILTER = (
    "highpass=f=160,"
    "bass=g=-10:f=220:width_type=o:width=0.8,"
    "equalizer=f=300:width_type=o:width=1.2:g=-5,"
    "equalizer=f=2200:width_type=o:width=1.2:g=7,"
    "equalizer=f=1300:width_type=o:width=1.2:g=4,"
    "equalizer=f=3500:width_type=o:width=1.0:g=1,"
    "treble=g=5:f=5000:width_type=o:width=0.7,"
    "acompressor=threshold=0.12:ratio=3:attack=15:release=250:makeup=2,"
    "alimiter=limit=0.95"
)

current_episode_id = None

position_thread_running = False

# Remaining episode ids to auto-play after the current one finishes.
# The currently-playing episode is NOT in this list; it lives in
# current_episode_id.
play_queue = []

def load_audio_filter():
    """Read a custom audio filter chain from config.json's
    settings.audio_filter, if present; otherwise use the default tuned
    for small class-D speaker kits. Never raises - falls back silently
    on any config problem so a bad edit can't stop playback."""

    try:

        with open(CONFIG_FILE, "r") as f:

            config = json.load(f)

        custom = config.get("settings", {}).get("audio_filter")

        if custom:

            return custom

    except (OSError, ValueError):

        pass

    return DEFAULT_AUDIO_FILTER

def send_mpv(command):

    if not os.path.exists(SOCKET):

        return None

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

    try:

        sock.connect(SOCKET)

        message = {

            "command": command

        }

        sock.sendall(

            (json.dumps(message) + "\n").encode()

        )

        sock.settimeout(1)

        try:

            response = sock.recv(4096)

            if response:

                return json.loads(response.decode())

        except socket.timeout:

            return None

    except Exception:

        return None

    finally:

        sock.close()

def start_mpv():

    # First, see if an existing mpv is already usable.

    if os.path.exists(SOCKET):

        try:

            sock = socket.socket(

                socket.AF_UNIX,

                socket.SOCK_STREAM

            )

            sock.connect(SOCKET)

            sock.close()

            print("Connected to existing mpv.")

            return True

        except OSError:

            try:

                os.remove(SOCKET)

            except OSError:

                pass

    # Remove any stale socket before starting mpv.

    try:

        os.remove(SOCKET)

    except OSError:

        pass

    print("Starting mpv...")

    audio_filter = load_audio_filter()

    process = subprocess.Popen(

        [

            "mpv",

            "--idle=yes",

            "--no-video",

            "--really-quiet",

            "--audio-device=alsa/plughw:CARD=Device,DEV=0",

            "--volume=100",

            f"--af=lavfi=[{audio_filter}]",

            f"--input-ipc-server={SOCKET}",

        ],

        stdin=subprocess.DEVNULL,

        stdout=subprocess.DEVNULL,

        stderr=subprocess.PIPE,

        text=True,

    )

    # Wait for mpv to create a working IPC socket.

    # mpv can take well over 10s to start on a Pi Zero W, especially while
    # the GUI is also running, so allow up to 60s.
    for _ in range(600):

        if process.poll() is not None:

            error = process.stderr.read().strip()

            print()

            print("ERROR: mpv exited before the IPC socket started.")

            if error:

                print("mpv:", error)

            return False

        try:

            sock = socket.socket(

                socket.AF_UNIX,

                socket.SOCK_STREAM

            )

            sock.settimeout(0.5)

            sock.connect(SOCKET)

            sock.close()

            print("Connected to mpv.")

            return True

        except OSError:

            time.sleep(0.1)

    print("ERROR: mpv IPC socket did not start.")

    # If mpv is still running, terminate it cleanly.

    if process.poll() is None:

        process.terminate()

        try:

            process.wait(timeout=3)

            error = process.stderr.read().strip()

            if error:

                print("mpv:", error)

        except Exception:

            pass

    return False

def get_episode(ep_id):

    conn = sqlite3.connect(DB)

    row = conn.execute(

        """

        SELECT id, show_name, title, played, position, filename

        FROM episodes

        WHERE id = ?

        """,

        (ep_id,),

    ).fetchone()

    conn.close()

    return row

def save_position(ep_id, position, played=False):

    conn = sqlite3.connect(DB)

    if played:

        conn.execute(

            """

            UPDATE episodes

            SET played = 1,

                position = 0

            WHERE id = ?

            """,

            (ep_id,),

        )

    else:

        conn.execute(

            """

            UPDATE episodes

            SET position = ?

            WHERE id = ?

            """,

            (position, ep_id),

        )

    conn.commit()

    conn.close()

def get_position():

    result = send_mpv(

        [

            "get_property",

            "time-pos",

        ]

    )

    if not result:

        return None

    if result.get("error") != "success":

        return None

    return result.get("data")

def get_duration():

    result = send_mpv(

        [

            "get_property",

            "duration",

        ]

    )

    if not result:

        return None

    if result.get("error") != "success":

        return None

    return result.get("data")

def position_monitor():
    global position_thread_running
    global current_episode_id

    last_ep = None
    last_pos = 0
    last_dur = None

    while position_thread_running:
        ep_id = current_episode_id

        if ep_id != last_ep:
            last_ep, last_pos, last_dur = ep_id, 0, None

        if ep_id is not None:
            position = get_position()
            duration = get_duration()

            # Playback may change while MPV is being queried. Never save
            # one episode's position against a different episode.
            if ep_id != current_episode_id:
                time.sleep(0.1)
                continue

            if position is not None:
                last_pos = position
                if duration:
                    last_dur = duration

                if duration and position >= duration - 15:
                    save_position(ep_id, 0, played=True)
                    advance_queue()
                else:
                    save_position(ep_id, position)

            elif last_dur and last_pos >= last_dur - 30:
                # mpv has no position because the file already ended
                # between checks - treat that as finished, not unfinished.
                save_position(ep_id, 0, played=True)
                last_pos = 0
                advance_queue()

        time.sleep(5)

def advance_queue():
    """Called when the current track has just finished. Starts the next
    queued episode, if any."""

    global play_queue

    if play_queue:

        next_id = play_queue.pop(0)

        print()
        print(f"Queue: advancing to episode {next_id}...")

        play(next_id)

def start_position_monitor():

    global position_thread_running

    position_thread_running = True

    thread = threading.Thread(

        target=position_monitor,

        daemon=True,

    )

    thread.start()

def stop_position_monitor():

    global position_thread_running

    position_thread_running = False

def list_episodes():

    conn = sqlite3.connect(DB)

    rows = conn.execute(

        """

        SELECT id, show_name, title, played, position, duration

        FROM episodes

        WHERE downloaded = 1

        ORDER BY id DESC

        """

    ).fetchall()

    conn.close()

    print()

    print("NPR LIBRARY")

    print("=" * 70)

    for ep_id, show, title, played, position, duration in rows:

        if duration:

            minutes = int(duration // 60)

            seconds = int(duration % 60)

            length = f"{minutes}:{seconds:02d}"

        else:

            length = "--:--"

        if played:

            status = "PLAYED"

        elif position and position > 0:

            pos_minutes = int(position // 60)

            pos_seconds = int(position % 60)

            status = f"{pos_minutes}:{pos_seconds:02d}"

        else:

            status = "NEW"

        print(

            f"[{ep_id}] {status:8} "

            f"[{length:>5}] "

            f"{show}: {title}"

        )

    print()

def play(ep_id):

    global current_episode_id

    episode = get_episode(ep_id)

    if not episode:

        print("Episode not found.")

        return

    (

        _,

        show,

        title,

        played,

        position,

        filename,

    ) = episode

    if not os.path.exists(filename):

        print("Audio file not found:")

        print(filename)

        return

    current_episode_id = ep_id

    print()

    print("Playing:")

    print(show)

    print(title)

    if position and not played:

        minutes = int(position // 60)

        seconds = int(position % 60)

        print(

            f"Resuming at {minutes}:{seconds:02d}"

        )

    print()

    result = send_mpv(

        [

            "loadfile",

            filename,

            "replace",

        ]

    )

    print("mpv:", result)

    if (

        position

        and not played

        and result

        and result.get("error") == "success"

    ):

        time.sleep(0.5)

        send_mpv(

            [

                "set_property",

                "time-pos",

                position,

            ]

        )

def parse_episode_ids(args):
    """Parse a play-command argument string into a list of episode ids.

    Accepts individual ids, comma and/or whitespace separated, and ranges
    written as "start-end" (inclusive, either direction). For example:
    "13, 14, 15", "13 14 15", "10-15", and "10-12, 15" are all valid.
    Raises ValueError on anything that doesn't parse.
    """

    parts = [p for p in re.split(r"[,\s]+", args) if p]

    if not parts:
        raise ValueError("no ids given")

    ids = []

    for part in parts:

        match = re.match(r"^(\d+)-(\d+)$", part)

        if match:

            start, end = int(match.group(1)), int(match.group(2))

            step = 1 if end >= start else -1

            ids.extend(range(start, end + step, step))

        else:

            ids.append(int(part))

    return ids

def start_queue(ids):
    """Play a list of episode ids back-to-back. The first plays immediately;
    the rest are picked up automatically by the position monitor as each
    track finishes."""

    global play_queue

    if not ids:
        return

    play_queue = list(ids[1:])

    if len(ids) > 1:
        print()
        print(f"Queued: {', '.join(str(i) for i in ids[1:])}")

    play(ids[0])

def cleanup_played():

    conn = sqlite3.connect(DB)

    rows = conn.execute("""

        SELECT id, show_name, title, filename

        FROM episodes

        WHERE played = 1

          AND downloaded = 1

    """).fetchall()

    if not rows:

        print()

        print("No played tracks to delete.")

        print()

        conn.close()

        return

    deleted = 0

    print()

    for ep_id, show_name, title, filename in rows:
        if ep_id == current_episode_id:
            print(f"  Skipping currently playing: {show_name}: {title}")
            continue

        try:

            if os.path.exists(filename):

                os.remove(filename)

            conn.execute("""

                UPDATE episodes

                SET downloaded = 0

                WHERE id = ?

            """, (ep_id,))

            print(f"  Deleted: {show_name}: {title}")

            deleted += 1

        except Exception as e:

            print(f"  ERROR: {title}: {e}")

    conn.commit()

    conn.close()

    print()

    print(f"Deleted {deleted} played track(s).")

    print("Played status remains saved in the database.")

    print()

def status():

    position = get_position()

    duration = get_duration()

    paused = send_mpv(

        [

            "get_property",

            "pause",

        ]

    )

    print()

    print("Position:", position)

    print("Duration:", duration)

    if position is not None and duration:

        remaining = duration - position

        print(

            "Remaining:",

            int(remaining // 60),

            ":",

            f"{int(remaining % 60):02d}",

            sep="",

        )

    print("Paused:", paused)

    print()

def stop():

    global current_episode_id, play_queue

    if current_episode_id is not None:

        position = get_position()

        if position is not None:

            save_position(

                current_episode_id,

                position,

            )

    send_mpv(["stop"])

    current_episode_id = None

    play_queue = []

def delete_episode(ep_id):

    conn = sqlite3.connect(DB)

    row = conn.execute(

        """

        SELECT id, title, played, filename

        FROM episodes

        WHERE id = ?

        """,

        (ep_id,)

    ).fetchone()

    if not row:

        print(f"No episode found with ID {ep_id}.")

        conn.close()

        return

    episode_id, title, played, filename = row

    if episode_id == current_episode_id:
        print("Cannot delete the episode that is currently playing. Stop it first.")
        conn.close()
        return

    if played:

        print("Cannot delete this episode because it is marked PLAYED.")

        conn.close()

        return

    print()

    print(f"Deleting: {title}")

    if filename and os.path.exists(filename):

        try:

            os.remove(filename)

            print(f"Deleted file: {filename}")

        except Exception as e:

            print(f"ERROR deleting file: {e}")

            conn.close()

            return

    else:

        print("Audio file not found.")

    conn.execute(

        "DELETE FROM episodes WHERE id = ?",

        (episode_id,)

    )

    conn.commit()

    conn.close()

    print("Episode removed from database.")

def main():

    global current_episode_id

    if not start_mpv():

        return

    start_position_monitor()

    print()

    print("========================================")

    print("           NPR PLAYER")

    print("========================================")

    print()

    print("Commands:")

    print("  list")

    print("  play <id> [, <id> | <id>-<id> ...]")

    print("  queue")

    print("  delete <id>")

    print("  pause")

    print("  resume")

    print("  toggle")

    print("  stop")

    print("  status")

    print("  cleanup")

    print("  forward")

    print("  back")

    print("  louder")

    print("  quieter")

    print("  quit")

    print()

    try:

        while True:

            try:

                command = input("npr> ").strip()

            except (KeyboardInterrupt, EOFError):

                print()

                if current_episode_id is not None:

                    position = get_position()

                    if position is not None:

                        save_position(

                            current_episode_id,

                            position,

                        )

                send_mpv(["quit"])

                break

            if command == "list":

                list_episodes()

            elif command.startswith("play "):

                args = command[len("play "):].strip()

                try:

                    ids = parse_episode_ids(args)

                except ValueError:

                    print("Usage: play <id> [, <id> | <id>-<id> ...]")

                else:

                    start_queue(ids)

            elif command == "queue":

                print()

                if play_queue:

                    print(
                        "Up next:",
                        ", ".join(str(i) for i in play_queue),
                    )

                else:

                    print("Queue is empty.")

                print()

            elif command == "pause":

                send_mpv(

                    [

                        "set_property",

                        "pause",

                        True,

                    ]

                )

            elif command == "resume":

                send_mpv(

                    [

                        "set_property",

                        "pause",

                        False,

                    ]

                )

            elif command == "toggle":

                send_mpv(

                    [

                        "cycle",

                        "pause",

                    ]

                )

            elif command == "stop":

                stop()

            elif command == "status":

                status()

            elif command.startswith("delete "):

                try:

                    ep_id = int(command.split()[1])

                    delete_episode(ep_id)

                except (ValueError, IndexError):

                    print("Usage: delete <id>")

            elif command == "cleanup":

                cleanup_played()

            elif command == "forward":

                send_mpv(

                    [

                        "seek",

                        30,

                        "relative",

                    ]

                )

            elif command == "back":

                send_mpv(

                    [

                        "seek",

                        -15,

                        "relative",

                    ]

                )

            elif command == "louder":

                send_mpv(

                    [

                        "add",

                        "volume",

                        5,

                    ]

                )

            elif command == "quieter":

                send_mpv(

                    [

                        "add",

                        "volume",

                        -5,

                    ]

                )

            elif command in (

                "quit",

                "exit",

            ):

                if current_episode_id is not None:

                    position = get_position()

                    if position is not None:

                        save_position(

                            current_episode_id,

                            position,

                        )

                send_mpv(["quit"])

                break

            elif command:

                print("Unknown command.")

    finally:

        stop_position_monitor()

if __name__ == "__main__":

    main()
