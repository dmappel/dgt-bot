# DGT Cita Previa Bot

Automated availability checker for DGT appointment slots (*citas previas*) for driving licence exchanges (*canjes de permisos de conducción*). When a slot opens up, the bot triggers a sound alarm so you can jump to the browser and book it manually.

---

## How it works

The bot reproduces the exact flow a human would do on the DGT website, step by step:

1. **Navigates** to the DGT Cita Previa start page
2. **Selects** your office (*centro*) and the *Canjes* service area, then clicks *Continuar*
3. **Clicks** *Pedir cita* under *Canje de permisos* on the service catalog
4. **Authenticates** via Cl@ve Móvil — it clicks the modal and waits for you to scan the QR code in the browser window
5. **Fills in** your personal data (date of birth, country, localizador / confirmation code) automatically
6. **Clicks** *Pedir cita* and *Seleccionar centro* to reach the availability page
7. **Checks** whether the page matches the known *"no citas disponibles"* state — if it looks different, the bot treats it as a possible slot and fires an alarm

Once authenticated, the Cl@ve session lasts ~60 minutes. The bot reuses it for multiple checks (default: every 10 minutes), so you only need to scan the QR roughly once per hour.

---

## Prerequisites

- Python 3.11+
- macOS (alerts use `osascript` and `afplay`; the core bot logic works on any OS but sound alerts are macOS-only)

---

## Setup

### 1. Clone the repo and create a virtual environment

```bash
git clone <repo-url>
cd dgt-bot
python -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

### 3. Configure your `.env`

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

Open `.env` and fill in each variable — see the [Configuration](#configuration) section below. The bot will refuse to start if any required variable is missing.

---

## Running the bot

```bash
source .venv/bin/activate   # if not already active
python bot.py
```

A Chromium browser window will open. Leave it visible — you will need to scan the Cl@ve QR code when prompted.

**What to expect:**

| Event | What happens |
|---|---|
| Bot starts | Prints startup summary and begins the first check |
| QR scan needed | 3 short beeps + macOS notification banner — switch to the browser and scan |
| No slots found | Prints status, waits for the configured interval, then rechecks |
| Slot found | Continuous alarm + macOS notification — press **Enter** in the terminal to stop the alarm and take over the browser to book |
| Outside operating hours | Bot sleeps and auto-resumes at the configured start hour |
| `Ctrl+C` | Graceful shutdown, browser closes |

---

## Configuration

All settings live in `.env` (gitignored — never committed). Use `.env.example` as the template.

| Variable | Description | Example |
|---|---|---|
| `FECHA_NACIMIENTO` | Date of birth in `dd/mm/yyyy` format | `18/10/1985` |
| `PAIS` | Country of your foreign licence, in Spanish | `Alemania` |
| `LOCALIZADOR` | DGT application reference number (8-char code) | `90ed07b4` |
| `CONFIRMATION_CODE` | Confirmation / expediente code from DGT | `ABC-12345` |
| `CENTRO` | DGT office city | `Barcelona` |
| `CHECK_INTERVAL_MINUTES` | How often to poll for slots (minutes) | `10` |
| `START_HOUR` | Bot active from this hour (0–23, CET) | `8` |
| `END_HOUR` | Bot active until this hour (0–23, CET) | `22` |

---

## Project structure

| File | Purpose |
|---|---|
| `bot.py` | Entry point — scheduling loop, session state, orchestrates each check cycle |
| `automation.py` | All browser interactions: navigation, form filling, JS-based clicks, availability detection |
| `config.py` | Loads and validates config from `.env`; defines DGT URL constants |
| `alerts.py` | Sound and macOS notification alerts (QR needed, cita found, errors) |
| `.env` | Your personal configuration — **gitignored, never commit** |
| `.env.example` | Safe template to copy from |
| `requirements.txt` | Python dependencies |

---

## Dependencies

| Library | Purpose |
|---|---|
| `playwright` | Drives a Chromium browser to interact with the DGT website |
| `python-dotenv` | Loads environment variables from `.env` |

---

## Notes

- The DGT site uses JavaServer Faces (JSF) with AJAX polling that continuously mutates the DOM. All clicks go through `page.evaluate()` with plain JavaScript to avoid stale element reference errors.
- The availability check uses a conservative approach: if the page does **not** contain any of the known *"no citas"* phrases, the bot assumes something may have changed and fires an alarm. False alarms are preferable to missed slots.
- The browser runs in **non-headless mode** so you can interact with it for QR scans and manual booking.
