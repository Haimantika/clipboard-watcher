#!/usr/bin/env python3
"""
Clipboard Familiar
==================
A tiny local daemon that watches your clipboard and quietly reacts to whatever
you copy. It does no thinking itself -- it just detects a change and hands the
text off to your agent, then shows the result as a desktop notification.

The intelligence is layered like this:

  * THIS FILE (laptop)              -> watches the clipboard, shows notifications
  * Hermes Agent (Nous Research)    -> orchestration + memory + the triage skill
  * GPT-5.4 Nano                    -> the actual reasoning behind each reaction
  * DigitalOcean Serverless Inference -> hosts Nano (configured inside Hermes)

Why this only works with a fast/cheap model: it fires on *every* copy event, so
the model has to be quick and near-free per call. GPT-5.4 Nano fits that lane
and, unlike DeepSeek-V4-Flash (the original pick), reliably follows the
"JSON-only" output contract the skill depends on.
"""

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

try:
    import pyperclip
except ImportError:
    sys.exit("pyperclip is required. Install it with:  pip install pyperclip")

# --------------------------------------------------------------------- config
HERMES_BIN     = os.environ.get("HERMES_BIN", "hermes")
POLL_SECONDS   = float(os.environ.get("CF_POLL_SECONDS", "0.7"))   # how often to check
MIN_CHARS      = int(os.environ.get("CF_MIN_CHARS", "3"))          # ignore tiny copies
MAX_CHARS      = int(os.environ.get("CF_MAX_CHARS", "8000"))       # sanity cap per clip
HERMES_TIMEOUT = int(os.environ.get("CF_TIMEOUT", "45"))           # seconds per call

# Notification Center banners depend on OS-level permission that's easy to
# have silently un-granted (see README). Set CF_ALWAYS_ALERT=1 to *also* pop
# a modal AppleScript alert dialog on every reaction -- alerts don't go
# through Notification Center at all, so they always render, at the cost of
# stealing focus. Handy for demos/recordings where you need guaranteed,
# on-screen proof the reaction fired.
ALWAYS_ALERT = os.environ.get("CF_ALWAYS_ALERT", "0") == "1"

STATE_DIR = Path.home() / ".hermes" / "clipboard"
STATE_DIR.mkdir(parents=True, exist_ok=True)
CLIP_FILE = STATE_DIR / "current.txt"      # last clip, handy for debugging + memory
LOG_FILE  = STATE_DIR / "familiar.log"


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def notify(title: str, message: str) -> None:
    """Best-effort cross-platform desktop notification. Logs failures instead
    of swallowing them, since a notification that silently doesn't show is
    worse than no notification at all."""
    message = (message or "").strip()[:400]
    system = platform.system()
    try:
        if system == "Darwin":
            # terminal-notifier is far more reliable than `osascript -e
            # 'display notification'` -- it gets its own entry in System
            # Settings -> Notifications (osascript's shows up as the vague
            # "Script Editor" and is easy to have silently disabled/denied).
            proc = None
            if shutil.which("terminal-notifier"):
                # Note: -sender is deliberately omitted -- newer
                # terminal-notifier versions reject it outright since the
                # UserNotifications framework no longer allows spoofing the
                # calling bundle identity.
                proc = subprocess.run(
                    ["terminal-notifier", "-title", title, "-message", message],
                    check=False, capture_output=True, text=True,
                )
                if proc.returncode != 0:
                    log(f"terminal-notifier failed (rc={proc.returncode}): "
                        f"{proc.stderr.strip()[:200]} -- falling back to osascript")
                    proc = None
            if proc is None:
                # ensure_ascii=False matters here: the default \uXXXX escapes
                # (e.g. for emoji in titles like "🔗 GitHub repo") aren't
                # interpreted by AppleScript's string parser and break with a
                # cryptic "Expected '\"' but found unknown token" error.
                proc = subprocess.run(
                    ["osascript", "-e",
                     f"display notification {json.dumps(message, ensure_ascii=False)} "
                     f"with title {json.dumps(title, ensure_ascii=False)}"],
                    check=False, capture_output=True, text=True,
                )
            if proc.returncode != 0:
                log(f"notify command failed (rc={proc.returncode}): "
                    f"{proc.stderr.strip()[:200]}")
            if ALWAYS_ALERT:
                # `display alert` is a modal window, not a Notification
                # Center banner -- it needs no special OS permission and will
                # always render, which is why it's used here as a
                # guaranteed-visible option rather than the default path.
                subprocess.run(
                    ["osascript", "-e",
                     f"display alert {json.dumps(title, ensure_ascii=False)} "
                     f"message {json.dumps(message, ensure_ascii=False)} "
                     f"giving up after 8"],
                    check=False, capture_output=True, text=True,
                )
        elif system == "Linux" and shutil.which("notify-send"):
            subprocess.run(["notify-send", title, message], check=False)
        elif system == "Windows":
            ps = (
                "$ErrorActionPreference='SilentlyContinue';"
                "[reflection.assembly]::LoadWithPartialName('System.Windows.Forms')|Out-Null;"
                "$n=New-Object System.Windows.Forms.NotifyIcon;"
                "$n.Icon=[System.Drawing.SystemIcons]::Information;"
                "$n.Visible=$true;"
                f"$n.ShowBalloonTip(6000,{json.dumps(title)},{json.dumps(message)},"
                "[System.Windows.Forms.ToolTipIcon]::Info)"
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)
        else:
            log(f"NOTIFY: {title} -- {message}")
    except Exception as exc:  # never let a notification failure kill the loop
        log(f"notify failed: {exc}")


def extract_json(text: str):
    """Pull the first {...} object out of Hermes' stdout, tolerating markdown
    code fences (```json ... ```) and stray prose around the object."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass

    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        # Retry against progressively smaller windows in case there's a
        # second, malformed brace pair after the real JSON object.
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        return None
        return None


def ask_hermes(clip_text: str):
    """
    Hand the copied text to Hermes. We invoke the CLI in one-shot (-q) mode and
    force the `skills` toolset so the clipboard-familiar skill loads.

    The text is passed as an argv element (subprocess list form, no shell), so
    arbitrary content is safe -- no quoting or injection to worry about.
    """
    CLIP_FILE.write_text(clip_text, encoding="utf-8")  # for debugging / agent memory
    prompt = (
        "Apply the clipboard-familiar skill to the CLIPBOARD TEXT below and "
        "reply with ONLY the JSON object the skill specifies -- no prose.\n\n"
        "<<<CLIPBOARD\n" + clip_text + "\nCLIPBOARD>>>"
    )
    proc = subprocess.run(
        [HERMES_BIN, "chat", "--toolsets", "skills", "-q", prompt],
        capture_output=True, text=True, timeout=HERMES_TIMEOUT,
    )
    if proc.returncode != 0:
        log(f"hermes error: {proc.stderr.strip()[:300]}")
        return None
    return extract_json(proc.stdout)


def main() -> None:
    log("Clipboard Familiar is awake. Watching your clipboard...")
    notify("Clipboard Familiar", "Awake and watching your clipboard.")

    try:
        last = pyperclip.paste()
    except Exception:
        last = ""
    self_written = None  # text we placed on the clipboard ourselves (ignore it)

    while True:
        time.sleep(POLL_SECONDS)
        try:
            current = pyperclip.paste()
        except Exception as exc:
            log(f"clipboard read failed: {exc}")
            continue

        if current == last:
            continue
        last = current

        if current == self_written:
            continue

        text = current.strip()
        if len(text) < MIN_CHARS:
            continue
        if len(text) > MAX_CHARS:
            log(f"skip: {len(text)} chars (over CF_MAX_CHARS={MAX_CHARS})")
            continue

        log(f"clip changed ({len(text)} chars) -> Hermes...")
        t0 = time.time()
        try:
            result = ask_hermes(text)
        except subprocess.TimeoutExpired:
            log("hermes timed out")
            continue
        dt = time.time() - t0

        if not result:
            log(f"no usable result ({dt:.1f}s)")
            continue

        kind = result.get("kind", "ignore")
        if kind == "ignore":
            log(f"ignored ({dt:.1f}s)")
            continue

        title  = result.get("title") or "Clipboard Familiar"
        detail = result.get("detail") or ""
        log(f"{kind}: {title} ({dt:.1f}s)")
        notify(title, detail)

        replacement = result.get("replace_clipboard")
        if replacement:
            self_written = replacement
            pyperclip.copy(replacement)
            last = replacement
            log("clipboard replaced with the result")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nClipboard Familiar going back to sleep. Bye.")
