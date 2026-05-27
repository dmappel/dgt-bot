# DGT Cita Previa Availability Bot -- Features

## Overview

Automated bot that monitors the DGT (Dirección General de Tráfico) website for available appointment slots at DGT Barcelona for "Canjes de permisos de conducción" (driving license exchanges). When a slot becomes available, it alerts the user with a sound notification so they can manually complete the booking.

## Features

### 1. Automated Navigation Flow
The bot reproduces the full user flow on the DGT Cita Previa website:
1. Navigates to `https://sedeclave.dgt.gob.es/WEB_CITE_CONSULTA/paginas/inicio.faces`
2. Selects centro (Barcelona) and area (Canjes)
3. Clicks "Continuar" → lands on `catalogo.faces` (service catalog)
4. Clicks "Pedir cita" under "Canje de permisos"
5. Handles Cl@ve Móvil authentication (with user interaction for QR scan)
6. Fills personal data: fecha de nacimiento, país, localizador
7. Clicks "Pedir cita" and "Seleccionar centro"
8. Checks whether the page matches the known "no citas" state; if it looks different, assumes citas may be available

### 2. Session Reuse (Aggressive Strategy)
- Cl@ve sessions last ~60 minutes
- The bot checks every 12 minutes (configurable), getting ~5 checks per session
- Re-authentication only happens when the session actually expires (detected by redirect to `pasarela.clave.gob.es`)
- This minimises the number of QR scans the user needs to do per hour

### 3. Operating Hours
- Active between 08:00 and 22:00 CET (configurable via `.env`)
- Automatically sleeps outside these hours and resumes when the window opens

### 4. Sound Alerts
- **QR scan needed**: 3 short beeps when the bot needs the user to scan the Cl@ve Móvil QR code in the browser
- **Cita found**: Continuous alarm sound that repeats until the user presses Enter in the terminal

### 5. Non-Headless Browser
- Runs Chromium in visible mode so the user can see the page and scan QR codes when needed

### 6. JSF AJAX Compatibility
- The DGT site uses JavaServer Faces with AJAX polling that continuously mutates the DOM
- All button clicks use `page.evaluate()` with JavaScript to avoid stale element references
- After clicking "Pedir cita", the page may render raw XML; the bot handles this with an automatic `page.reload()`

## Application Structure

| File | Purpose |
|---|---|
| `bot.py` | Main entry point. Runs the scheduling loop, manages session state, orchestrates the check cycle. |
| `automation.py` | All Playwright browser interactions: navigation, form filling, button clicks (via JS), availability detection. |
| `config.py` | Loads configuration from `.env` file and defines URL constants. |
| `alerts.py` | Sound notification utilities: short beeps for QR needed, continuous alarm for cita found. |
| `.env` | User-specific configuration (fecha, país, localizador, schedule settings). Gitignored. |
| `requirements.txt` | Python dependencies. |

## Libraries

| Library | Purpose |
|---|---|
| `playwright` | Browser automation. Drives a Chromium instance to interact with the DGT website. |
| `python-dotenv` | Loads environment variables from `.env` file. |
| `schedule` | Listed as a dependency but not used in the current implementation (the bot uses a simple time.sleep loop instead, which is more appropriate for the aggressive session-reuse strategy). |

## Configuration

All settings are in `.env` (gitignored). Copy `.env.example` to get started. All variables are required — the bot raises a clear error on startup if any are missing.

| Variable | Description |
|---|---|
| `FECHA_NACIMIENTO` | Date of birth in `dd/mm/yyyy` format |
| `PAIS` | Country of your foreign licence, in Spanish |
| `LOCALIZADOR` | DGT application reference number (8-char code) |
| `CONFIRMATION_CODE` | Confirmation / expediente code from DGT |
| `CENTRO` | DGT office city |
| `CHECK_INTERVAL_MINUTES` | Minutes between checks |
| `START_HOUR` | Start of daily operating window (0–23, CET) |
| `END_HOUR` | End of daily operating window (0–23, CET) |

## How to Run

```bash
cd dgt-bot
pip install -r requirements.txt
python -m playwright install chromium
python bot.py
```

The bot will open a browser window, start the flow, and alert you when QR scanning is needed. Keep the terminal visible to see status messages and hear alerts.
