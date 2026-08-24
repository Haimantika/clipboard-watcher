# Clipboard Familiar

A local daemon that watches your clipboard and reacts intelligently to
whatever you copy — not just links. Copy a stack trace and get the fix. Copy
foreign text and get a translation. Copy messy JSON and get it pretty-printed
(and swapped back onto your clipboard). Copy a math expression and get the
answer. All as a desktop notification — no window-switching, no prompting.

## What it does

On every clipboard change, the copied text is classified into one of eight
kinds and given exactly one small, useful reaction:

| You copy...              | You get...                                            |
|---------------------------|--------------------------------------------------------|
| an error / stack trace    | the likely cause + a one-line fix                      |
| text not in English       | an English translation, source language noted          |
| messy / minified JSON     | a pretty-printed version (clipboard is auto-replaced)  |
| a code snippet            | a one-sentence explanation + a flagged bug/risk        |
| a math expression         | the evaluated result (clipboard is auto-replaced)      |
| a single URL              | a one-line guess at what the page/tool is              |
| an acronym / jargon term  | a one-line definition                                  |
| anything else, or secrets | ignored — no notification, nothing stored              |

Anything that looks credential-shaped (API keys, tokens, private keys,
passwords) is never reacted to, echoed, or stored — that's enforced by the
skill's own instructions.

## How it works

```
  you copy something
        │
        ▼
  clipboard_familiar.py        ← runs on your laptop (watch + notify only)
        │  passes the text to…
        ▼
  Hermes Agent                 ← loads the clipboard-familiar skill, adds memory,
        │  which calls…           can grow new skills itself
        ▼
  GPT-5.4 Nano                 ← does the actual reasoning for each clip
        │  hosted on…
        ▼
  DigitalOcean Serverless Inference   ← the endpoint Hermes is pointed at
        │  result flows back up…
        ▼
  desktop notification
```

The daemon itself does zero thinking — it just polls the clipboard
(`pyperclip`), shells out to `hermes chat -q` with the copied text, and turns
whatever JSON comes back into a notification. All the intelligence lives one
layer up, in the agent and the model behind it.

## Tools used

- **`clipboard_familiar.py` (your laptop)** — the only piece that runs
  locally. Watches the clipboard, enforces size limits, and shows
  notifications. No API keys live here.
- **Hermes Agent** — the orchestrator. Loads `clipboard-familiar/SKILL.md`,
  applies persistent memory (dedupes repeat clips, learns "stop reacting to
  X" preferences), and can use `skill_manage` to write itself new categories
  when it notices a recurring clip type the skill doesn't cover (e.g. hex
  colors, commit hashes).
- **DigitalOcean Serverless Inference** — where the model runs. Hermes treats
  it as a custom OpenAI-compatible provider
  (`https://inference.do-ai.run/v1`), authenticated with a DO Model Access
  Key.

## How to use it

**Prerequisites:** [Hermes](https://hermes.chat) installed (`hermes
--version` works) and a DigitalOcean Model Access Key (Control Panel →
Inference → Manage → Model Access Keys).

```bash
export DO_MODEL_ACCESS_KEY=your-do-model-access-key
bash setup.sh
python3 clipboard_familiar.py
```

`setup.sh` installs `pyperclip` (and `terminal-notifier` on macOS), points
Hermes at DigitalOcean Serverless Inference, and installs the
`clipboard-familiar` skill. Once it's done, just start the daemon and copy
things — reactions show up as desktop notifications, and everything logs to
`~/.hermes/clipboard/familiar.log`.

### Configuration (env vars)

| Var               | Default | Meaning                              |
|-------------------|---------|---------------------------------------|
| `CF_POLL_SECONDS` | `0.7`   | how often to check the clipboard      |
| `CF_MIN_CHARS`    | `3`     | ignore copies shorter than this       |
| `CF_MAX_CHARS`    | `8000`  | skip copies larger than this          |
| `CF_TIMEOUT`      | `45`    | seconds to wait on Hermes per clip    |
| `CF_ALWAYS_ALERT` | `0`     | also pop a focus-stealing modal alert (useful for demos) |
| `HERMES_BIN`      | `hermes`| path to the hermes binary             |

