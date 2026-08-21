# Clipboard Familiar

A local daemon that watches your clipboard and quietly reacts to whatever you
copy — an error traceback gets a fix, a foreign sentence gets translated, messy
JSON gets pretty-printed, a math expression gets evaluated — all as a desktop
notification, no window-switching.

## The flow

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
  DeepSeek-V4-Flash            ← does the actual reasoning for each clip
        │  hosted on…
        ▼
  DigitalOcean Serverless Inference   ← the endpoint Hermes is pointed at
        │  result flows back up…
        ▼
  desktop notification
```

## Which tool is used where

- **Your laptop** — `clipboard_familiar.py` is the *only* piece that runs
  locally. It watches the clipboard (`pyperclip`) and shows notifications. It
  does zero thinking. This is the "deploy on your own laptop" part.
- **Hermes Agent** — the orchestrator. The daemon shells out to `hermes chat -q`;
  Hermes loads `clipboard-familiar/SKILL.md`, applies persistent **memory**
  (dedupe repeats, learn your "stop reacting to X" preferences), and can use
  `skill_manage` to **write itself new categories** when it sees clip types the
  skill doesn't cover.
- **DeepSeek-V4-Flash** — the model that classifies each clip and produces the
  reaction. Chosen because the daemon fires on *every* copy, so per-call latency
  and cost have to be tiny — Flash's home turf.
- **DigitalOcean Serverless Inference** — where Flash runs. Hermes is configured
  to treat it as a custom OpenAI-compatible provider
  (`https://inference.do-ai.run/v1`), authenticated with a DO Model Access Key.

## Install

```bash
export DO_MODEL_ACCESS_KEY=your-do-model-access-key
bash setup.sh
python3 clipboard_familiar.py
```

## Knobs (env vars)

| Var               | Default | Meaning                              |
|-------------------|---------|--------------------------------------|
| `CF_POLL_SECONDS` | `0.7`   | how often to check the clipboard     |
| `CF_MIN_CHARS`    | `3`     | ignore copies shorter than this      |
| `CF_MAX_CHARS`    | `8000`  | skip copies larger than this         |
| `CF_TIMEOUT`      | `45`    | seconds to wait on Hermes per clip   |
| `HERMES_BIN`      | `hermes`| path to the hermes binary            |

## Notes / things to verify on your machine

- The exact DigitalOcean slug for V4-Flash: `setup.sh` prints the matching slugs
  from the live catalog. Override with `export DO_MODEL_SLUG=...` if needed.
- Hermes' provider config key names can vary by version — confirm with
  `hermes config show`. What must be true: base_url points at
  `https://inference.do-ai.run/v1`, the model access key is set, and the default
  model is your DO slug.
- Secrets safety is handled in the skill: anything credential-shaped is ignored
  and never echoed, stored, or written back to the clipboard.
