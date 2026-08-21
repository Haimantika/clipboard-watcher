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

# --- 1. laptop-side dependency ------------------------------------------------
pip install --quiet pyperclip
echo "✓ pyperclip installed"

# --- 2. Hermes -> DigitalOcean Serverless Inference (DeepSeek-V4-Flash) --------
: "${DO_MODEL_ACCESS_KEY:?Set it first:  export DO_MODEL_ACCESS_KEY=your-key}"

# Discover the exact slug DigitalOcean uses for V4-Flash (slugs are lowercase-
# hyphenated, e.g. openai-gpt-5.5). Don't guess — read it from the catalog:
echo "Available DeepSeek slugs on DigitalOcean:"
curl -s https://inference.do-ai.run/v1/models \
  -H "Authorization: Bearer ${DO_MODEL_ACCESS_KEY}" \
  | grep -io '"id"[^,]*deepseek[^,]*' || echo "  (couldn't list — check your key)"

DO_MODEL_SLUG="${DO_MODEL_SLUG:-deepseek-v4-flash}"   # override if the slug above differs

# Point Hermes at DigitalOcean's OpenAI-compatible endpoint. DigitalOcean is just
# a custom OpenAI-compatible provider as far as Hermes is concerned.
#
# NOTE: confirm these key names against YOUR Hermes version with `hermes config show`
# — the provider namespace can vary. The values below are what matters:
#   base_url = https://inference.do-ai.run/v1
#   api_key  = your DO model access key   (Hermes routes this to ~/.hermes/.env)
#   model    = <provider>/<do-slug>
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
