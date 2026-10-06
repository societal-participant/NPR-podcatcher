#!/usr/bin/env python3
"""
gui.py - Touchscreen interface for the NPR podcatcher, on the Waveshare
2.8" DPI capacitive touchscreen.

Screens:
  SPLASH       - "NPR podcatcher" title, colored like the NPR logo, for a
                 few seconds on startup.
  MAIN_MENU    - logo, plus "Listen to Recorded Shows" and "Check for New
                 Episodes". (A "Now Playing" button appears too while an
                 episode is loaded.)
  NOW_PLAYING  - Title + play status, Play/Pause, and buttons to Shows and
                 the Main Menu.
  SHOWS        - list of shows you have downloaded episodes for.
  EPISODES     - a show's episodes. Tap to select (for queueing or
                 deleting); Play Selected and Delete Selected act on
                 whatever's checked.
  CHECKING     - brief status screen while a feed check runs in the
                 background.

Reuses player.py's existing mpv-control functions directly (send_mpv,
play, start_queue, cleanup_played, etc.) rather than duplicating that
logic - importing player.py as a module runs none of its REPL code,
only defines its functions/constants, so this is safe.
"""

import collections
import os

os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")
os.environ.setdefault("SDL_FBDEV", "/dev/fb0")

import sys
import sqlite3
import threading
import time
import contextlib
import io

import pygame

import player
import downloader

# --- Display setup, confirmed correct on this hardware ---
ROTATE = 90
LOGICAL_WIDTH = 640
LOGICAL_HEIGHT = 480

# --- Colors ---
BG = (15, 15, 18)
PANEL_BG = (28, 29, 33)
PANEL_SELECTED = (24, 48, 70)
BORDER = (60, 62, 68)
TEXT = (235, 235, 238)
TEXT_DIM = (150, 152, 158)
DISABLED_BG = (22, 22, 24)
DISABLED_TEXT = (85, 85, 88)

NPR_RED = (214, 32, 33)
NPR_BLACK = (0, 0, 0)
NPR_BLUE = (35, 123, 189)
WHITE = (255, 255, 255)

ACCENT = NPR_BLUE
DANGER = NPR_RED

SPLASH_SECONDS = 5

DB = player.DB


# ---------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------

def get_shows():
    conn = sqlite3.connect(DB)
    rows = conn.execute(
        """
        SELECT DISTINCT show_name
        FROM episodes
        WHERE downloaded = 1
        ORDER BY show_name
        """
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_episodes(show_name):
    conn = sqlite3.connect(DB)
    rows = conn.execute(
        """
        SELECT id, title, played, position
        FROM episodes
        WHERE show_name = ? AND downloaded = 1
        ORDER BY id DESC
        """,
        (show_name,),
    ).fetchall()
    conn.close()
    return rows


def episode_status_text(played, position):
    if played:
        return "PLAYED"
    if position and position > 0:
        minutes = int(position // 60)
        seconds = int(position % 60)
        return f"{minutes}:{seconds:02d}"
    return "NEW"


def get_episode_title(ep_id):
    conn = sqlite3.connect(DB)
    row = conn.execute("SELECT title FROM episodes WHERE id = ?", (ep_id,)).fetchone()
    conn.close()
    return row[0] if row else "Unknown episode"


def delete_episodes(ep_ids):
    conn = sqlite3.connect(DB)
    for ep_id in ep_ids:
        row = conn.execute(
            "SELECT filename FROM episodes WHERE id = ?", (ep_id,)
        ).fetchone()
        if row and row[0] and os.path.exists(row[0]):
            try:
                os.remove(row[0])
            except OSError:
                pass
        # Keep the row (marked played, file gone) so the downloader still
        # recognises the GUID and never fetches this episode again.
        conn.execute(
            "UPDATE episodes SET downloaded = 0, played = 1, position = 0 "
            "WHERE id = ?",
            (ep_id,),
        )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------
# Playback state (reads player.py's live state, doesn't duplicate it)
# ---------------------------------------------------------------------

def format_clock(seconds):
    """63.4 -> '1:03', 3725 -> '1:02:05'. None -> '--:--'."""
    if seconds is None:
        return "--:--"
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def get_playback_status():
    """Returns (title_or_None, status_text)."""
    ep_id = player.current_episode_id
    if ep_id is None:
        return None, "Nothing playing"

    title = get_episode_title(ep_id)

    result = player.send_mpv(["get_property", "pause"])
    paused = bool(result and result.get("data"))

    status = "Paused" if paused else "Playing"
    if player.play_queue:
        status += f"  ({len(player.play_queue)} queued)"

    return title, status


# ---------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------

def wrap_text(text, font, max_width):
    words = text.split(" ")
    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        if font.size(test)[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_wrapped_text(canvas, text, font, color, rect, center=True):
    lines = wrap_text(text, font, rect.width)
    line_height = font.get_linesize()
    total_height = line_height * len(lines)
    y = rect.centery - total_height // 2 if center else rect.top
    for line in lines:
        surf = font.render(line, True, color)
        x = rect.centerx - surf.get_width() // 2 if center else rect.left
        canvas.blit(surf, (x, y))
        y += line_height


class ProgressCapture:
    """A stdout-like object that captures whatever downloader.py prints and
    hands each completed line to a callback, while still echoing to the
    real terminal (so SSH debugging still works as normal). Splits on both
    '\\n' and '\\r' since download_episode() uses '\\r' for its live
    percentage updates -- without handling '\\r' too, those updates would
    never reach the screen until the download finished."""

    def __init__(self, on_line):
        self.on_line = on_line
        self._buffer = ""

    def write(self, text):
        sys.__stdout__.write(text)
        self._buffer += text
        while "\n" in self._buffer or "\r" in self._buffer:
            for sep in ("\n", "\r"):
                if sep in self._buffer:
                    line, self._buffer = self._buffer.split(sep, 1)
                    break
            line = line.strip()
            if line:
                self.on_line(line)

    def flush(self):
        sys.__stdout__.flush()


def truncate_to_width(text, font, max_width):
    """Cuts text down with a trailing '...' until it fits max_width. Used
    for the checking-screen log, where lines scroll by fast enough that a
    bouncing marquee for all 6 at once would be more distracting than
    helpful -- a plain truncation is easier to read at a glance."""
    if font.size(text)[0] <= max_width:
        return text
    ellipsis = "..."
    while text and font.size(text + ellipsis)[0] > max_width:
        text = text[:-1]
    return text + ellipsis


# All marquees share one start time. Resetting it (on every screen change
# and list scroll) makes long titles sit still for INITIAL_HOLD seconds
# first, so you can read the beginning before anything starts moving.
INITIAL_HOLD = 3.0
_marquee_epoch = time.time()


def reset_marquee():
    global _marquee_epoch
    _marquee_epoch = time.time()


def draw_marquee_text(canvas, text, font, color, rect, align="center",
                       hold_seconds=1.5, scroll_seconds=4.0):
    """Draws text within rect. If it fits, drawn once (centered or
    left-aligned per `align`). If it's too wide, bounces back and forth
    horizontally: pause at the start, scroll to the end, pause there,
    scroll back -- rather than continuously reversing with no pause."""
    surf = font.render(text, True, color)
    y = rect.centery - surf.get_height() // 2

    if surf.get_width() <= rect.width:
        if align == "center":
            canvas.blit(surf, surf.get_rect(center=rect.center))
        else:
            canvas.blit(surf, (rect.left, y))
        return

    overflow = surf.get_width() - rect.width
    period = 2 * hold_seconds + 2 * scroll_seconds
    elapsed = time.time() - _marquee_epoch
    if elapsed < INITIAL_HOLD:
        t = 0
    else:
        # Continue the normal cycle right at the start of the first scroll.
        t = (elapsed - INITIAL_HOLD + hold_seconds) % period

    if t < hold_seconds:
        offset = 0
    elif t < hold_seconds + scroll_seconds:
        offset = (t - hold_seconds) / scroll_seconds * overflow
    elif t < 2 * hold_seconds + scroll_seconds:
        offset = overflow
    else:
        progress = (t - (2 * hold_seconds + scroll_seconds)) / scroll_seconds
        offset = overflow * (1 - progress)

    prev_clip = canvas.get_clip()
    canvas.set_clip(rect)
    canvas.blit(surf, (rect.left - offset, y))
    canvas.set_clip(prev_clip)


class Button:
    def __init__(self, rect, label, action, enabled=True, danger=False):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.action = action
        self.enabled = enabled
        self.danger = danger

    def draw(self, canvas, font):
        bg = PANEL_BG if self.enabled else DISABLED_BG
        border = (DANGER if self.danger else ACCENT) if self.enabled else BORDER
        fg = TEXT if self.enabled else DISABLED_TEXT

        pygame.draw.rect(canvas, bg, self.rect, border_radius=10)
        pygame.draw.rect(canvas, border, self.rect, width=2, border_radius=10)

        text_rect = self.rect.inflate(-24, -12)
        draw_marquee_text(canvas, self.label, font, fg, text_rect, align="center")

    def hit(self, pos):
        return self.enabled and self.rect.collidepoint(pos)


# ---------------------------------------------------------------------
# App
# ---------------------------------------------------------------------

class App:
    def __init__(self):
        pygame.init()
        pygame.mouse.set_visible(False)

        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        self.native_width, self.native_height = self.screen.get_size()
        self.canvas = pygame.Surface((LOGICAL_WIDTH, LOGICAL_HEIGHT))

        self.font_title = pygame.font.SysFont(None, 40)
        self.font_logo_small = pygame.font.SysFont(None, 32)
        self.font_large = pygame.font.SysFont(None, 34)
        self.font_medium = pygame.font.SysFont(None, 26)
        self.font_small = pygame.font.SysFont(None, 20)

        self.state = "SPLASH"
        self.splash_start = time.time()

        self.selected_show = None
        self.selected_ids = set()
        self.scroll_offset = {"SHOWS": 0, "EPISODES": 0}

        self.confirm_delete = False

        # Short-lived banner shown after Cleanup Played: (text, expiry time)
        self.toast_text = ""
        self.toast_until = 0

        # Latest playback info for the Now Playing screen, refreshed by a
        # background thread so a slow mpv reply can never freeze the UI.
        self.np_info = {"pos": None, "dur": None, "paused": False}
        threading.Thread(target=self._np_poll_loop, daemon=True).start()

        self.check_thread = None
        self.check_log = collections.deque(maxlen=6)

        self.buttons = []
        self._drag_start = None
        self._drag_scroll_start = 0
        self._dragged = False

        # mpv is started from run(), in a background thread, so the splash
        # is on screen the whole time mpv is starting up.
        self.mpv_ready = False
        self.mpv_failed = False
        self.mpv_thread = None

    def _np_poll_loop(self):
        while True:
            try:
                if (self.state == "NOW_PLAYING"
                        and player.current_episode_id is not None):
                    pos = player.get_position()
                    dur = player.get_duration()
                    reply = player.send_mpv(["get_property", "pause"])
                    self.np_info = {
                        "pos": pos,
                        "dur": dur,
                        "paused": bool(reply and reply.get("data")),
                    }
                else:
                    self.np_info = {"pos": None, "dur": None, "paused": False}
            except Exception:
                pass
            time.sleep(0.5)

    def _start_mpv_background(self):
        """Start mpv without blocking the UI thread."""
        def worker():
            try:
                ok = player.start_mpv()
            except Exception as e:
                print(f"[gui] start_mpv raised: {e}")
                ok = False
            if ok:
                player.start_position_monitor()
                self.mpv_ready = True
            else:
                self.mpv_failed = True

        self.mpv_thread = threading.Thread(target=worker, daemon=True)
        self.mpv_thread.start()

    # -- coordinate mapping (mirrors screen_test.py, verified working) --

    def native_to_logical(self, nx, ny):
        angle = ROTATE % 360
        if angle == 0:
            return nx, ny
        elif angle == 90:
            return LOGICAL_WIDTH - 1 - ny, nx
        elif angle == 180:
            return LOGICAL_WIDTH - 1 - nx, LOGICAL_HEIGHT - 1 - ny
        elif angle == 270:
            return ny, LOGICAL_HEIGHT - 1 - nx
        raise ValueError("ROTATE must be 0, 90, 180, or 270")

    def render(self):
        rotated = pygame.transform.rotate(self.canvas, ROTATE)
        self.screen.blit(rotated, (0, 0))
        pygame.display.flip()

    # -- screen switch helpers --

    def go_to(self, state):
        self.state = state
        reset_marquee()
        self.confirm_delete = False

    def go_to_shows(self):
        self.selected_ids = set()
        self.go_to("SHOWS")

    def go_to_episodes(self, show_name):
        self.selected_show = show_name
        self.selected_ids = set()
        self.go_to("EPISODES")

    def go_main_menu(self):
        self.selected_ids = set()
        self.go_to("MAIN_MENU")

    def go_now_playing(self):
        self.selected_ids = set()
        self.go_to("NOW_PLAYING")

    def start_check(self):
        self.go_to("CHECKING")
        self.check_log.clear()
        self.check_log.append("Starting...")

        def update(line):
            self.check_log.append(line)

        def run():
            capture = ProgressCapture(update)
            try:
                with contextlib.redirect_stdout(capture):
                    downloader.main()
            except Exception as e:
                self.check_log.append(f"Check failed: {e}")
                time.sleep(2)
                self.go_main_menu()
                return
            self.check_log.append("Done.")
            time.sleep(1.5)
            self.go_main_menu()

        self.check_thread = threading.Thread(target=run, daemon=True)
        self.check_thread.start()

    def toggle_play_pause(self):
        if player.current_episode_id is not None:
            player.send_mpv(["cycle", "pause"])

    def seek(self, seconds):
        """Jump forward (+) or back (-) by the given number of seconds."""
        if player.current_episode_id is not None:
            player.send_mpv(["seek", seconds, "relative"])

    def toggle_selected(self, ep_id):
        if ep_id in self.selected_ids:
            self.selected_ids.discard(ep_id)
        else:
            self.selected_ids.add(ep_id)

    def play_selected(self):
        if not self.selected_ids:
            return
        rows = get_episodes(self.selected_show)
        ordered_ids = [r[0] for r in rows if r[0] in self.selected_ids]
        player.start_queue(ordered_ids)
        self.go_now_playing()

    def request_delete_selected(self):
        if self.selected_ids:
            self.confirm_delete = True

    def confirm_delete_selected(self):
        delete_episodes(self.selected_ids)
        self.selected_ids = set()
        self.confirm_delete = False

    def run_cleanup(self):
        # cleanup_played() reports by printing, so capture that to count
        # what happened, then echo it so it still reaches the log.
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            player.cleanup_played()
        output = buf.getvalue()
        print(output, end="")

        deleted = sum(
            1 for ln in output.splitlines() if ln.strip().startswith("Deleted:")
        )
        errors = sum(
            1 for ln in output.splitlines() if ln.strip().startswith("ERROR")
        )
        skipped = sum(
            1 for ln in output.splitlines() if "Skipping currently" in ln
        )

        if errors:
            text = f"Cleanup had {errors} error(s)"
        elif deleted:
            text = f"Deleted {deleted} played episode(s)"
        elif skipped:
            text = "Only the episode now playing is played"
        else:
            text = "No played episodes to delete"

        self.selected_ids = set()
        self.toast_text = text
        self.toast_until = time.time() + 3

    # -- drawing per screen --

    def draw_logo(self, top_y, box_size, letter_font):
        """Three adjoining NPR-colored squares with 'podcatcher' beneath,
        centered horizontally. Returns the y of the subtitle's bottom edge
        so callers can lay out content below it."""
        letters = [("n", NPR_RED), ("p", NPR_BLACK), ("r", NPR_BLUE)]
        start_x = LOGICAL_WIDTH // 2 - (box_size * 3) // 2

        for i, (letter, color) in enumerate(letters):
            rect = pygame.Rect(start_x + i * box_size, top_y, box_size, box_size)
            pygame.draw.rect(self.canvas, color, rect)
            letter_surf = letter_font.render(letter, True, WHITE)
            self.canvas.blit(letter_surf, letter_surf.get_rect(center=rect.center))

        outline = pygame.Rect(start_x, top_y, box_size * 3, box_size)
        pygame.draw.rect(self.canvas, TEXT_DIM, outline, width=2)

        subtitle = self.font_large.render("podcatcher", True, TEXT)
        subtitle_rect = subtitle.get_rect(
            center=(LOGICAL_WIDTH // 2, top_y + box_size + 36)
        )
        self.canvas.blit(subtitle, subtitle_rect)
        return subtitle_rect.bottom

    def draw_splash(self):
        self.canvas.fill((25, 25, 28))
        self.draw_logo(LOGICAL_HEIGHT // 2 - 35 - 30, 70, self.font_title)

        if self.mpv_failed:
            print("Could not start mpv - exiting.")
            pygame.quit()
            sys.exit(1)

        # Leave the splash once the minimum time has passed AND mpv is up
        # (if mpv takes longer than SPLASH_SECONDS, the splash just stays).
        if (time.time() - self.splash_start >= SPLASH_SECONDS
                and self.mpv_ready):
            self.go_to("MAIN_MENU")

    def draw_main_menu(self):
        self.canvas.fill(BG)
        self.buttons = []

        self.draw_logo(28, 56, self.font_logo_small)

        playing = player.current_episode_id is not None

        if playing:
            rows = [
                (195, 80, "Listen to Recorded Shows", self.go_to_shows, self.font_large),
                (290, 80, "Check for New Episodes", self.start_check, self.font_large),
                (385, 70, "Now Playing", self.go_now_playing, self.font_medium),
            ]
        else:
            rows = [
                (225, 95, "Listen to Recorded Shows", self.go_to_shows, self.font_large),
                (335, 95, "Check for New Episodes", self.start_check, self.font_large),
            ]

        for y, h, label, action, font in rows:
            btn = Button((100, y, 440, h), label, action)
            btn.draw(self.canvas, font)
            self.buttons.append(btn)

    def draw_now_playing(self):
        self.canvas.fill(BG)
        self.buttons = []

        ep_id = player.current_episode_id
        title = get_episode_title(ep_id) if ep_id is not None else None
        info = self.np_info
        if ep_id is None:
            status = "Nothing playing"
        else:
            status = "Paused" if info["paused"] else "Playing"
            if player.play_queue:
                status += f"  ({len(player.play_queue)} queued)"

        title_rect = pygame.Rect(30, 30, LOGICAL_WIDTH - 60, 150)
        if title:
            draw_wrapped_text(self.canvas, title, self.font_large, TEXT, title_rect)
        else:
            no_title = self.font_large.render("No episode selected", True, TEXT_DIM)
            self.canvas.blit(no_title, no_title.get_rect(center=title_rect.center))

        status_surf = self.font_medium.render(status, True, TEXT_DIM)
        self.canvas.blit(
            status_surf, status_surf.get_rect(center=(LOGICAL_WIDTH // 2, 200))
        )

        if ep_id is not None:
            clock = f"{format_clock(info['pos'])} / {format_clock(info['dur'])}"
            clock_surf = self.font_large.render(clock, True, TEXT)
            self.canvas.blit(
                clock_surf, clock_surf.get_rect(center=(LOGICAL_WIDTH // 2, 243))
            )

        play_btn = Button(
            (LOGICAL_WIDTH // 2 - 90, 280, 180, 70),
            "Play / Pause",
            self.toggle_play_pause,
            enabled=player.current_episode_id is not None,
        )
        play_btn.draw(self.canvas, self.font_medium)
        self.buttons.append(play_btn)

        has_ep = player.current_episode_id is not None
        back_btn = Button(
            (30, 280, 170, 70), "- 30s", lambda: self.seek(-30), enabled=has_ep
        )
        back_btn.draw(self.canvas, self.font_medium)
        self.buttons.append(back_btn)

        fwd_btn = Button(
            (LOGICAL_WIDTH - 200, 280, 170, 70), "+ 30s",
            lambda: self.seek(30), enabled=has_ep,
        )
        fwd_btn.draw(self.canvas, self.font_medium)
        self.buttons.append(fwd_btn)

        shows_btn = Button((30, 390, 220, 70), "Shows", self.go_to_shows)
        shows_btn.draw(self.canvas, self.font_medium)
        self.buttons.append(shows_btn)

        menu_btn = Button(
            (LOGICAL_WIDTH - 250, 390, 220, 70), "Main Menu", self.go_main_menu
        )
        menu_btn.draw(self.canvas, self.font_medium)
        self.buttons.append(menu_btn)

    def draw_list_screen(self, items, title, row_labels, on_row_tap,
                          extra_buttons, scroll_key, empty_message):
        self.canvas.fill(BG)
        self.buttons = []

        back_btn = Button((15, 8, 120, 60), "< Back", self._back_action())
        back_btn.draw(self.canvas, self.font_medium)
        self.buttons.append(back_btn)

        title_shown = truncate_to_width(title, self.font_title, LOGICAL_WIDTH - 160)
        title_surf = self.font_title.render(title_shown, True, TEXT)
        self.canvas.blit(title_surf, (150, 18))

        list_top = 80
        # Shows has no bottom action bar, so it can use nearly the full
        # remaining height for the list; Episodes needs room reserved
        # below for Play/Delete/Cleanup.
        list_bottom = LOGICAL_HEIGHT - (95 if extra_buttons else 15)
        row_height = 88
        visible_height = list_bottom - list_top

        max_scroll = max(0, len(items) * row_height - visible_height)
        self.scroll_offset[scroll_key] = max(
            0, min(self.scroll_offset[scroll_key], max_scroll)
        )
        offset = self.scroll_offset[scroll_key]

        clip_rect = pygame.Rect(0, list_top, LOGICAL_WIDTH, visible_height)
        prev_clip = self.canvas.get_clip()
        self.canvas.set_clip(clip_rect)

        row_rects = []
        if not items:
            empty_surf = self.font_medium.render(empty_message, True, TEXT_DIM)
            self.canvas.blit(
                empty_surf,
                empty_surf.get_rect(
                    center=(LOGICAL_WIDTH // 2, list_top + visible_height // 2)
                ),
            )

        for i, item in enumerate(items):
            y = list_top + i * row_height - offset
            if y + row_height < list_top or y > list_bottom:
                row_rects.append(None)
                continue

            row_rect = pygame.Rect(15, y, LOGICAL_WIDTH - 30, row_height - 8)
            row_rects.append(row_rect)

            selected = on_row_tap == self.toggle_selected and item[0] in self.selected_ids
            bg = PANEL_SELECTED if selected else PANEL_BG
            pygame.draw.rect(self.canvas, bg, row_rect, border_radius=8)
            pygame.draw.rect(self.canvas, BORDER, row_rect, width=1, border_radius=8)

            main_text, sub_text = row_labels(item)

            # Episodes rows get a real checkbox in its own column, so it
            # stays put while a long title scrolls beside it.
            has_checkbox = on_row_tap == self.toggle_selected
            text_left = row_rect.left + 15
            if has_checkbox:
                box = pygame.Rect(0, 0, 36, 36)
                box.midleft = (row_rect.left + 15, row_rect.centery)
                pygame.draw.rect(
                    self.canvas, ACCENT if selected else BG, box, border_radius=6
                )
                pygame.draw.rect(self.canvas, ACCENT, box, width=2, border_radius=6)
                if selected:
                    pygame.draw.lines(
                        self.canvas, TEXT, False,
                        [
                            (box.left + 8, box.centery),
                            (box.left + 15, box.bottom - 10),
                            (box.right - 8, box.top + 9),
                        ],
                        4,
                    )
                text_left = box.right + 14
            text_width = row_rect.right - 15 - text_left

            title_line_height = self.font_large.get_linesize()
            if sub_text:
                # Two-line layout (Episodes): title on top, status below.
                title_rect = pygame.Rect(
                    text_left, row_rect.top + 6, text_width, title_line_height,
                )
            else:
                # Single-line layout (Shows): center the title in the
                # whole row instead of leaving it pinned near the top.
                title_rect = pygame.Rect(
                    text_left, row_rect.top, text_width, row_rect.height,
                )

            draw_marquee_text(
                self.canvas, main_text, self.font_large, TEXT, title_rect, align="left"
            )

            if sub_text:
                sub_surf = self.font_medium.render(sub_text, True, TEXT_DIM)
                self.canvas.blit(sub_surf, (text_left, title_rect.bottom + 4))

        self.canvas.set_clip(prev_clip)

        for btn in extra_buttons:
            btn.draw(self.canvas, self.font_medium)
            self.buttons.append(btn)

        return row_rects, list_top, offset, row_height

    def draw_shows(self):
        shows = get_shows()
        row_rects, list_top, offset, row_height = self.draw_list_screen(
            items=[(s,) for s in shows],
            title="Shows",
            row_labels=lambda item: (item[0], None),
            on_row_tap=lambda item: self.go_to_episodes(item[0]),
            extra_buttons=[],
            scroll_key="SHOWS",
            empty_message="No shows downloaded yet.",
        )
        self._current_rows = [(s,) for s in shows]
        self._current_row_rects = row_rects
        self._current_row_action = lambda item: self.go_to_episodes(item[0])

    def draw_episodes(self):
        episodes = get_episodes(self.selected_show)

        def labels(ep):
            ep_id, title, played, position = ep
            status = episode_status_text(played, position)
            return title, status

        play_btn = Button(
            (15, LOGICAL_HEIGHT - 80, 200, 65),
            f"Play ({len(self.selected_ids)})",
            self.play_selected,
            enabled=len(self.selected_ids) > 0,
        )
        delete_btn = Button(
            (225, LOGICAL_HEIGHT - 80, 200, 65),
            f"Delete ({len(self.selected_ids)})",
            self.request_delete_selected,
            enabled=len(self.selected_ids) > 0,
            danger=True,
        )
        cleanup_btn = Button(
            (435, LOGICAL_HEIGHT - 80, 190, 65),
            "Cleanup Played",
            self.run_cleanup,
        )

        row_rects, list_top, offset, row_height = self.draw_list_screen(
            items=episodes,
            title=self.selected_show,
            row_labels=labels,
            on_row_tap=self.toggle_selected,
            extra_buttons=[play_btn, delete_btn, cleanup_btn],
            scroll_key="EPISODES",
            empty_message="No episodes downloaded for this show.",
        )
        self._current_rows = episodes
        self._current_row_rects = row_rects
        self._current_row_action = lambda ep: self.toggle_selected(ep[0])

        if self.confirm_delete:
            self._draw_confirm_delete()

        self._draw_toast()

    def _draw_toast(self):
        if not self.toast_text or time.time() > self.toast_until:
            return
        rect = pygame.Rect(60, LOGICAL_HEIGHT - 160, LOGICAL_WIDTH - 120, 56)
        pygame.draw.rect(self.canvas, PANEL_BG, rect, border_radius=10)
        pygame.draw.rect(self.canvas, ACCENT, rect, width=2, border_radius=10)
        shown = truncate_to_width(self.toast_text, self.font_medium, rect.width - 30)
        surf = self.font_medium.render(shown, True, TEXT)
        self.canvas.blit(surf, surf.get_rect(center=rect.center))

    def _draw_confirm_delete(self):
        overlay = pygame.Surface((LOGICAL_WIDTH, LOGICAL_HEIGHT))
        overlay.set_alpha(220)
        overlay.fill((10, 10, 10))
        self.canvas.blit(overlay, (0, 0))

        msg = self.font_large.render(
            f"Delete {len(self.selected_ids)} episode(s)?", True, TEXT
        )
        self.canvas.blit(
            msg, msg.get_rect(center=(LOGICAL_WIDTH // 2, LOGICAL_HEIGHT // 2 - 50))
        )

        yes_btn = Button(
            (LOGICAL_WIDTH // 2 - 210, LOGICAL_HEIGHT // 2, 200, 60),
            "Yes, Delete",
            self.confirm_delete_selected,
            danger=True,
        )
        cancel_btn = Button(
            (LOGICAL_WIDTH // 2 + 10, LOGICAL_HEIGHT // 2, 200, 60),
            "Cancel",
            lambda: setattr(self, "confirm_delete", False),
        )
        yes_btn.draw(self.canvas, self.font_medium)
        cancel_btn.draw(self.canvas, self.font_medium)
        self.buttons.append(yes_btn)
        self.buttons.append(cancel_btn)

    def draw_checking(self):
        self.canvas.fill(BG)
        self.buttons = []

        header = self.font_medium.render("Checking Feeds", True, TEXT_DIM)
        self.canvas.blit(header, header.get_rect(center=(LOGICAL_WIDTH // 2, 60)))

        # Last 6 lines of whatever downloader.py has printed, oldest on
        # top and newest on the bottom (like a terminal scrolling by),
        # so you can see exactly where the process is, not just the
        # single most recent line.
        log_top = 105
        line_height = 48
        max_width = LOGICAL_WIDTH - 60
        lines = list(self.check_log)

        for i, line in enumerate(lines):
            is_newest = i == len(lines) - 1
            color = TEXT if is_newest else TEXT_DIM
            font = self.font_medium if is_newest else self.font_small
            shown = truncate_to_width(line, font, max_width)
            surf = font.render(shown, True, color)
            self.canvas.blit(surf, (30, log_top + i * line_height))

        # A heartbeat independent of any actual network activity: three
        # dots that pulse based on wall-clock time. This is the fix for
        # "is it stuck?" specifically -- there can be real gaps of a
        # second or more between printed lines (a slow DNS lookup, a TCP
        # handshake, waiting on the first bytes of a response) where
        # nothing new has happened to show, but the app is still alive.
        # Constant motion here is worth more than any speed improvement
        # for that particular worry.
        dot_count = int(time.time() * 2) % 4
        dots = "." * dot_count
        pulse = self.font_medium.render(dots, True, ACCENT)
        self.canvas.blit(pulse, (LOGICAL_WIDTH // 2 - 20, LOGICAL_HEIGHT - 60))

    def _back_action(self):
        if self.state == "EPISODES":
            return self.go_to_shows
        return self.go_main_menu

    # -- main loop --

    def draw(self):
        if self.state == "SPLASH":
            self.draw_splash()
        elif self.state == "MAIN_MENU":
            self.draw_main_menu()
        elif self.state == "NOW_PLAYING":
            self.draw_now_playing()
        elif self.state == "SHOWS":
            self.draw_shows()
        elif self.state == "EPISODES":
            self.draw_episodes()
        elif self.state == "CHECKING":
            self.draw_checking()

        self.render()

    def handle_tap(self, lx, ly):
        if self.confirm_delete:
            for btn in self.buttons:
                if btn.hit((lx, ly)):
                    btn.action()
            return

        for btn in self.buttons:
            if btn.hit((lx, ly)):
                btn.action()
                return

        if self.state in ("SHOWS", "EPISODES"):
            rects = getattr(self, "_current_row_rects", [])
            rows = getattr(self, "_current_rows", [])
            for rect, item in zip(rects, rows):
                if rect and rect.collidepoint((lx, ly)):
                    self._current_row_action(item)
                    return

    def handle_scroll(self, dy):
        key = "EPISODES" if self.state == "EPISODES" else "SHOWS"
        if self.state in ("SHOWS", "EPISODES"):
            self.scroll_offset[key] -= dy
            reset_marquee()

    def run(self):
        clock = pygame.time.Clock()
        running = True

        # The splash timer and mpv startup begin together, right here,
        # just before the first frame is drawn.
        self.splash_start = time.time()
        print(f"[gui] splash timer started at {self.splash_start:.2f}")
        self._start_mpv_background()

        try:
            while running:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False

                    elif event.type == pygame.FINGERDOWN:
                        nx = int(event.x * self.native_width)
                        ny = int(event.y * self.native_height)
                        lx, ly = self.native_to_logical(nx, ny)
                        self._drag_start = (lx, ly)
                        self._drag_scroll_start = self.scroll_offset.get(
                            self.state, 0
                        )
                        self._dragged = False

                    elif event.type == pygame.FINGERMOTION and self._drag_start:
                        nx = int(event.x * self.native_width)
                        ny = int(event.y * self.native_height)
                        lx, ly = self.native_to_logical(nx, ny)
                        dy = ly - self._drag_start[1]
                        if abs(dy) > 10:
                            self._dragged = True
                            self.handle_scroll(dy)
                            self._drag_start = (lx, ly)

                    elif event.type == pygame.FINGERUP and self._drag_start:
                        nx = int(event.x * self.native_width)
                        ny = int(event.y * self.native_height)
                        lx, ly = self.native_to_logical(nx, ny)
                        if not self._dragged:
                            self.handle_tap(lx, ly)
                        self._drag_start = None

                self.draw()
                # The splash is static; don't let it hog the Zero W's single
                # core while mpv is starting up.
                clock.tick(5 if self.state == "SPLASH" else 30)

        except KeyboardInterrupt:
            pass
        finally:
            pygame.quit()


if __name__ == "__main__":
    App().run()
