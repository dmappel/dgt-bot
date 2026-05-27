import subprocess
import sys
import threading
import time

_alarm_active = False


def _notify_macos(title: str, message: str, sound: str = "Hero"):
    """Send a macOS notification banner with sound."""
    subprocess.run(
        [
            "osascript",
            "-e",
            f'display notification "{message}" with title "{title}" sound name "{sound}"',
        ],
        capture_output=True,
    )


def _beep_macos(sound: str = "Ping"):
    subprocess.run(
        ["afplay", f"/System/Library/Sounds/{sound}.aiff"],
        capture_output=True,
    )


def _beep_fallback():
    sys.stdout.write("\a")
    sys.stdout.flush()


def beep(sound: str = "Ping"):
    if sys.platform == "darwin":
        _beep_macos(sound)
    else:
        _beep_fallback()


def alert_qr_needed():
    """3 short beeps + macOS notification: user needs to scan QR."""
    print("\n" + "=" * 60)
    print("  [!] CL@VE QR SCAN NEEDED -- CHECK THE BROWSER WINDOW")
    print("=" * 60 + "\n")
    _notify_macos(
        "DGT Bot - QR Scan Needed",
        "Open the browser and scan the Cl@ve Móvil QR code",
        "Glass",
    )
    for _ in range(3):
        beep("Glass")
        time.sleep(0.5)


def alert_cita_found():
    """Continuous loud alarm + macOS notification until user presses Enter."""
    global _alarm_active
    _alarm_active = True

    print("\n" + "=" * 60)
    print("  [!!!] CITA AVAILABLE -- GO TO THE BROWSER NOW!")
    print("=" * 60 + "\n")

    _notify_macos(
        "DGT Bot - CITA FOUND!",
        "Available appointment detected! Go to the browser NOW!",
        "Hero",
    )

    def _alarm_loop():
        while _alarm_active:
            beep("Hero")
            time.sleep(1.5)

    t = threading.Thread(target=_alarm_loop, daemon=True)
    t.start()
    input(">>> Press ENTER to stop the alarm and take over <<<\n")
    _alarm_active = False


def alert_error(message: str):
    """Single beep + error message."""
    print(f"\n[ERROR] {message}")
    beep()
