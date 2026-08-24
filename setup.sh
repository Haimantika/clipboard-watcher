#!/usr/bin/env bash
#
# One-time setup for Clipboard Familiar.
#
# Wires three things together:
#   1. the local daemon's dependency (pyperclip)
#   2. Hermes  ->  DigitalOcean Serverless Inference  ->  DeepSeek-V4-Flash
#   3. the clipboard-familiar skill into Hermes
#
# Prereqs: Hermes already installed (`hermes --version` works) and a DigitalOcean
# Model Access Key created at: Control Panel -> Inference -> Manage -> Model Access Keys
#
set -euo pipefail

# --- 1. laptop-side dependencies ----------------------------------------------
pip install --quiet pyperclip
echo "✓ pyperclip installed"

# terminal-notifier is far more reliable than `osascript -e 'display
# notification'` on modern macOS -- it gets its own entry in System Settings ->
# Notifications, whereas osascript's shows up as the vague "Script Editor" and
# is easy to have silently denied/disabled.
if [[ "$(uname -s)" == "Darwin" ]] && command -v brew >/dev/null 2>&1; then
  brew list terminal-notifier &>/dev/null || brew install terminal-notifier
  echo "✓ terminal-notifier installed"
  echo "  NOTE: the first notification may need approval in"
  echo "  System Settings -> Notifications -> terminal-notifier (set to Allow)."
fi

# --- 2. Hermes -> DigitalOcean Serverless Inference ---------------------------
: "${DO_MODEL_ACCESS_KEY:?Set it first:  export DO_MODEL_ACCESS_KEY=your-key}"

# Don't guess slugs (they change) — read them from the live catalog:
echo "Available model slugs on DigitalOcean:"
curl -s https://inference.do-ai.run/v1/models \
  -H "Authorization: Bearer ${DO_MODEL_ACCESS_KEY}" \
  | grep -io '"id":[^,]*' || echo "  (couldn't list — check your key)"

# deepseek-v4-flash was the original pick for speed/cost, but in practice it
# frequently ignores the "JSON ONLY" instruction (prose, missing fields,
# truncated output), so a lot of clips silently produce "no usable result".
# GPT-5.4 Nano is just as fast/cheap on DO Serverless Inference and follows
# the strict-JSON contract far more reliably. Override DO_MODEL_SLUG with any
# id from the catalog above if you'd rather use something else.
DO_MODEL_SLUG="${DO_MODEL_SLUG:-openai-gpt-5.4-nano}"

hermes config set providers.digitalocean.base_url "https://inference.do-ai.run/v1"
hermes config set providers.digitalocean.api_key  "${DO_MODEL_ACCESS_KEY}"
hermes config set model.default                   "digitalocean/${DO_MODEL_SLUG}"
echo "✓ Hermes pointed at DigitalOcean Serverless Inference (${DO_MODEL_SLUG})"

# --- 3. install the skill -----------------------------------------------------
mkdir -p ~/.hermes/skills/clipboard-familiar ~/.hermes/clipboard
cp "$(dirname "$0")/SKILL.md" ~/.hermes/skills/clipboard-familiar/SKILL.md
echo "✓ clipboard-familiar skill installed"

echo
echo "Verify:   hermes config show"
echo "Smoke test the model+skill in isolation:"
echo "  hermes chat --toolsets skills -q 'Apply the clipboard-familiar skill. <<<CLIPBOARD"
echo "  Traceback (most recent call last): ZeroDivisionError: division by zero"
echo "  CLIPBOARD>>>'"
echo
echo "Then start the familiar:   python3 clipboard_familiar.py"
