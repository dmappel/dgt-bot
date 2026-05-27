"""
DGT Cita Previa browser automation using Playwright.

All interactions use page.evaluate() with getElementById() to avoid:
  1. Stale element references from JSF AJAX polling
  2. CSS selector failures from colons in JSF element IDs

Flow (as of March 2026):
  1. inicio.faces   - Select Centro (Barcelona) + Area (Canjes / CNJ) + Continuar
  2. catalogo.faces  - Click "Pedir cita" under "Canje de permisos"
  3. catalogo.faces  - Cl@ve modal appears -> authenticate via QR
  4. catalogo.faces  - Fill canjes form (fecha, pais, aceptar, localizador, pedir cita)
  5. cita.faces      - Seleccionar centro -> check availability

Verified element IDs (from live DOM inspection):
  Start page (inicio.faces):
    - Centro dropdown:     id starts with "formselectorCentro:" (suffix is dynamic)
    - Area dropdown:       (dynamic, loaded via AJAX after centro selection)
    - Continuar button:    (dynamic)
  Canjes form (catalogo.faces -- page title "DGT - Tus canjes"):
    - Fecha nacimiento:    forminicio:fechaNacimiento
    - Pais dropdown:       forminicio:pais
    - Aceptar button:      forminicio:j_id_2q
    - Localizador input:   forminicio:itemsol:0:idsolicitudcanje
    - Pedir cita button:   forminicio:itemsol:0:j_id_31
"""

import time
import config
import alerts

_IDS = {
    "fecha": "forminicio:fechaNacimiento",
    "pais": "forminicio:pais",
    "aceptar": "forminicio:j_id_2q",
    "localizador": "forminicio:itemsol:0:idsolicitudcanje",
    "pedir_cita": "forminicio:itemsol:0:j_id_31",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def js_click_id(page, element_id: str):
    page.evaluate(f"document.getElementById('{element_id}').click()")


def js_click_css(page, selector: str):
    page.evaluate(f"document.querySelector('{selector}').click()")


def js_set_value(page, element_id: str, value: str):
    """Set an input's value by ID and dispatch change event."""
    page.evaluate(f"""
        (() => {{
            const el = document.getElementById('{element_id}');
            if (!el) throw new Error('Element not found: {element_id}');
            el.value = '{value}';
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }})()
    """)


def js_select_option(page, element_id: str, *, value: str = None, label: str = None):
    """Select an option in a <select> by ID, matching by value or label text."""
    if value is not None:
        page.evaluate(f"""
            (() => {{
                const sel = document.getElementById('{element_id}');
                if (!sel) throw new Error('Select not found: {element_id}');
                sel.value = '{value}';
                sel.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }})()
        """)
    elif label is not None:
        page.evaluate(f"""
            (() => {{
                const sel = document.getElementById('{element_id}');
                if (!sel) throw new Error('Select not found: {element_id}');
                for (const opt of sel.options) {{
                    if (opt.text.includes('{label}')) {{
                        sel.value = opt.value;
                        sel.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        break;
                    }}
                }}
            }})()
        """)


def wait_for_domain(page, domain: str, timeout_s: int = 300, poll_s: int = 3, verbose: bool = False):
    """Poll until any page in the browser context has URL containing domain.

    Also checks all pages in case a popup/new tab was opened.
    Returns the page that matched, or False on timeout.
    """
    deadline = time.time() + timeout_s
    last_url = ""
    context = page.context
    while time.time() < deadline:
        # Check the main page
        try:
            current_url = page.url
        except Exception:
            current_url = ""

        if current_url != last_url:
            if verbose:
                print(f"    [poll] Main page URL: {current_url}")
            last_url = current_url

        if domain in current_url:
            return True

        # Check ALL pages in context (popup/new tab)
        try:
            for p in context.pages:
                p_url = p.url
                if domain in p_url:
                    if verbose:
                        print(f"    [poll] Found domain in other tab: {p_url}")
                    return True
        except Exception:
            pass

        time.sleep(poll_s)
    return False


def safe_wait(page, ms: int = 2000):
    """Wait for network to settle and add a small buffer."""
    try:
        page.wait_for_load_state("networkidle", timeout=ms)
    except Exception:
        pass
    time.sleep(1)


def is_on_canjes_page(page) -> bool:
    """Check if we're on the 'Tus canjes' form page.

    The canjes form now loads at catalogo.faces (title "DGT - Tus canjes")
    instead of the old canjes/inicio.faces.
    """
    try:
        title = page.title()
        return "canjes" in title.lower() or "tus canjes" in title.lower()
    except Exception:
        return False


def has_clave_modal(page) -> bool:
    """Check if the Cl@ve authentication modal is visible on the canjes page."""
    try:
        return page.evaluate("""
            (() => {
                const text = document.body.innerText;
                return text.includes('Autenticación en Cl@ve') ||
                       text.includes('redirigirá a la pantalla de autenticación');
            })()
        """)
    except Exception:
        return False


def is_authenticated_on_canjes(page) -> bool:
    """True only if on canjes page AND no Cl@ve modal (actually authenticated)."""
    if not is_on_canjes_page(page):
        return False
    if has_clave_modal(page):
        return False
    # Double-check: NIF/NIE field should have a value if authenticated
    try:
        nif_value = page.evaluate("""
            (() => {
                const el = document.querySelector('input[placeholder*="NIF"]');
                return el ? el.value : '';
            })()
        """)
        return bool(nif_value.strip())
    except Exception:
        return False


def is_on_cita_page(page) -> bool:
    return "cita.faces" in page.url


# ---------------------------------------------------------------------------
# Step 1: Navigate to start page
# ---------------------------------------------------------------------------

def navigate_to_start(page):
    print("[1] Navigating to DGT start page...")
    page.goto(config.DGT_START_URL, wait_until="domcontentloaded", timeout=30000)
    safe_wait(page, 3000)
    print(f"    URL: {page.url}")


# ---------------------------------------------------------------------------
# Step 2: Select centro + area, click Continuar
# ---------------------------------------------------------------------------

def select_centro_and_area(page):
    print("[2] Selecting centro and area...")

    # The centro dropdown's full JSF id ends with an auto-generated suffix
    # (e.g. "formselectorCentro:j_id_2h") that DGT bumps on every redeploy,
    # so we locate it by stable prefix + matching option text instead.
    found = page.evaluate(f"""
        (() => {{
            const target = {repr(config.CENTRO)};
            const selects = document.querySelectorAll('select');
            const trySelect = (s) => {{
                for (const opt of s.options) {{
                    if (opt.text.includes(target)) {{
                        s.value = opt.value;
                        s.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        return s.id || 'no-id';
                    }}
                }}
                return null;
            }};
            for (const s of selects) {{
                if (s.id && s.id.startsWith('formselectorCentro:')) {{
                    const r = trySelect(s);
                    if (r) return r;
                }}
            }}
            for (const s of selects) {{
                const r = trySelect(s);
                if (r) return r;
            }}
            return null;
        }})()
    """)
    if not found:
        raise RuntimeError(f"Centro dropdown with option '{config.CENTRO}' not found")
    print(f"    Selected Centro = {config.CENTRO} (element: {found})")
    safe_wait(page, 3000)

    # Area dropdown appears via AJAX after selecting centro.
    # Find it dynamically since its JSF ID is auto-generated.
    print("    Waiting for Area dropdown to load...")
    for attempt in range(10):
        found = page.evaluate("""
            (() => {
                const selects = document.querySelectorAll('select');
                for (const s of selects) {
                    for (const opt of s.options) {
                        if (opt.value === 'CNJ' || opt.text.includes('Canjes')) {
                            s.value = 'CNJ';
                            s.dispatchEvent(new Event('change', { bubbles: true }));
                            return s.id || 'found-no-id';
                        }
                    }
                }
                return null;
            })()
        """)
        if found:
            print(f"    Selected Area = Canjes (element: {found})")
            break
        time.sleep(1)
    else:
        raise RuntimeError("Area dropdown with 'Canjes' option not found after 10s")

    safe_wait(page, 2000)

    # Click Continuar button
    page.evaluate("""
        (() => {
            const btns = document.querySelectorAll('button, input[type="submit"]');
            for (const b of btns) {
                const txt = (b.textContent || b.value || '').trim();
                if (txt === 'Continuar') {
                    b.click();
                    return;
                }
            }
            throw new Error('Continuar button not found');
        })()
    """)
    print("    Clicked Continuar, waiting for catalog page...")

    safe_wait(page, 5000)

    # Wait for catalogo.faces to load
    for _ in range(10):
        if "catalogo.faces" in page.url:
            break
        time.sleep(1)

    print(f"    URL after Continuar: {page.url}")
    print(f"    Page title: {page.title()}")


# ---------------------------------------------------------------------------
# Step 2b: Click "Pedir cita" on the catalog page (catalogo.faces)
# ---------------------------------------------------------------------------

def click_catalog_pedir_cita(page):
    """On catalogo.faces, click the first 'Pedir cita' link (under 'Canje de permisos')."""
    print("[2b] Clicking 'Pedir cita' on catalog page...")
    safe_wait(page, 2000)

    if "catalogo.faces" not in page.url:
        print(f"    [WARN] Not on catalog page (URL: {page.url}), trying to continue...")

    page.evaluate("""
        (() => {
            const links = document.querySelectorAll('a');
            for (const a of links) {
                if ((a.textContent || '').trim() === 'Pedir cita') {
                    a.click();
                    return;
                }
            }
            throw new Error('"Pedir cita" link not found on catalog page');
        })()
    """)
    print("    Clicked 'Pedir cita', waiting for canjes page / Cl@ve modal...")

    safe_wait(page, 5000)

    # Wait for either Cl@ve modal or redirect to Cl@ve domain
    for _ in range(10):
        if is_on_canjes_page(page) or config.CLAVE_DOMAIN in page.url:
            break
        time.sleep(1)

    print(f"    URL: {page.url}")
    print(f"    Page title: {page.title()}")


# ---------------------------------------------------------------------------
# Step 3: Handle Cl@ve authentication
# ---------------------------------------------------------------------------

def handle_clave_auth(page) -> bool:
    """Returns True if fully authenticated. Handles Cl@ve modal + QR flow."""
    print("[3] Checking authentication...")

    # Check for Cl@ve error page (replay attack, etc.)
    try:
        body_text = page.evaluate("document.body.innerText")
        if "replay attack" in body_text.lower() or "se ha producido un error" in body_text.lower():
            print("    [ERROR] Cl@ve error page detected. Need fresh session.")
            return False
    except Exception:
        pass

    # Already fully authenticated: on canjes page, no modal, NIF filled
    if is_authenticated_on_canjes(page):
        print("    Already authenticated (session reuse), NIF present.")
        return True

    # On canjes page BUT Cl@ve modal is showing -- need to click modal Aceptar
    if is_on_canjes_page(page) and has_clave_modal(page):
        print("    Canjes page loaded but Cl@ve modal detected.")
        print("    Clicking modal Aceptar to start Cl@ve authentication...")
        try:
            # The modal Aceptar is typically a <button> inside a dialog/modal div
            page.evaluate("""
                (() => {
                    // Find buttons inside modal/dialog overlays
                    const modals = document.querySelectorAll(
                        '.ui-dialog, .modal, [role="dialog"], .ui-widget-overlay + div'
                    );
                    for (const modal of modals) {
                        const btn = modal.querySelector('button');
                        if (btn && (btn.textContent || '').trim() === 'Aceptar') {
                            btn.click();
                            return;
                        }
                    }
                    // Fallback: click any visible Aceptar button
                    const btns = document.querySelectorAll('button');
                    for (const b of btns) {
                        if ((b.textContent || '').trim() === 'Aceptar' && b.offsetParent !== null) {
                            b.click();
                            return;
                        }
                    }
                })()
            """)
        except Exception:
            pass

        safe_wait(page, 5000)

        # Should now redirect to Cl@ve
        for _ in range(5):
            if config.CLAVE_DOMAIN in page.url:
                break
            time.sleep(2)

        if config.CLAVE_DOMAIN in page.url:
            return _do_clave_auth(page)

        # Maybe it went through without Cl@ve (unlikely but check)
        if is_authenticated_on_canjes(page):
            print("    Authenticated after modal click.")
            return True

        print(f"    [WARN] After modal click: URL={page.url}")
        return False

    # Directly on Cl@ve domain (redirected without seeing canjes page)
    if config.CLAVE_DOMAIN in page.url:
        print("    On Cl@ve page, need to authenticate.")
        return _do_clave_auth(page)

    # Still on DGT start page -- something else is going on
    print(f"    [WARN] Unexpected state. URL: {page.url}, Title: {page.title()}")
    return False


def _do_clave_auth(page) -> bool:
    """Handle the Cl@ve Móvil QR flow."""
    print("    On Cl@ve identification page.")
    safe_wait(page, 2000)

    # Click the Cl@ve Móvil button.
    # Normalize @ -> a for matching since Spanish text uses "Cl@ve".
    clicked = page.evaluate("""
        (() => {
            const elements = document.querySelectorAll('button, a, div[role="button"]');
            for (const el of elements) {
                const txt = (el.textContent || '').toLowerCase().replace(/@/g, 'a');
                if (txt.includes('clave') && txt.includes('vil')) {
                    el.click();
                    return el.textContent.trim().substring(0, 60);
                }
            }
            return null;
        })()
    """)

    if clicked:
        print(f"    Clicked Cl@ve Móvil button: '{clicked}'")
    else:
        print("    [WARN] Could not find Cl@ve Móvil button automatically.")
        print("    Please click it manually in the browser.")

    safe_wait(page, 5000)

    # Check if already redirected back (auto re-auth within 60 min)
    real_url = _get_real_url(page)
    print(f"    Current URL: {real_url}")
    if config.DGT_DOMAIN in real_url:
        print("    Already redirected back to DGT (auto re-auth).")
        safe_wait(page, 3000)
        return True

    # Alert user to scan QR
    alerts.alert_qr_needed()

    # Wait for redirect to DGT using TWO methods:
    # 1. Playwright's wait_for_url (event-driven, catches navigations reliably)
    # 2. Fallback: poll window.location.href directly via JS (avoids stale page.url)
    print("    Waiting for QR scan + redirect to DGT (up to 5 minutes)...")

    # Method 1: try Playwright's built-in wait_for_url
    try:
        page.wait_for_url(
            f"**{config.DGT_DOMAIN}**",
            timeout=330_000,
            wait_until="domcontentloaded",
        )
        safe_wait(page, 3000)
        real_url = _get_real_url(page)
        print(f"    Authentication successful! URL: {real_url}")
        _do_clave_auth._result_page = page
        return True
    except Exception as e:
        print(f"    [WARN] wait_for_url did not match: {e}")

    # Method 2: poll via JS as fallback
    print("    Falling back to JS polling...")
    deadline = time.time() + 30
    while time.time() < deadline:
        real_url = _get_real_url(page)
        if config.DGT_DOMAIN in real_url:
            safe_wait(page, 3000)
            print(f"    Authentication successful (JS poll)! URL: {real_url}")
            _do_clave_auth._result_page = page
            return True
        time.sleep(2)

    # Method 3: check other tabs
    try:
        for p in page.context.pages:
            if p != page:
                p_url = _get_real_url(p)
                if config.DGT_DOMAIN in p_url:
                    p.bring_to_front()
                    safe_wait(p, 3000)
                    print(f"    Auth successful (other tab)! URL: {p_url}")
                    _do_clave_auth._result_page = p
                    return True
    except Exception:
        pass

    real_url = _get_real_url(page)
    print(f"    [ERROR] Authentication timed out. Final URL: {real_url}")
    return False


def _get_real_url(page) -> str:
    """Get the actual browser URL via JS, bypassing any stale Playwright cache."""
    try:
        return page.evaluate("window.location.href")
    except Exception:
        try:
            return page.url
        except Exception:
            return ""


# ---------------------------------------------------------------------------
# Step 4: Fill the canje form
# ---------------------------------------------------------------------------

def fill_canje_form(page):
    print("[4] Filling canje form...")
    safe_wait(page, 3000)

    if not is_on_canjes_page(page):
        print(f"    [ERROR] Not on canjes page! URL: {page.url}, Title: {page.title()}")
        raise RuntimeError("Not on canjes page, cannot fill form")

    # Verify the Cl@ve modal is gone and NIF is filled (truly authenticated)
    if has_clave_modal(page):
        raise RuntimeError("Cl@ve modal still visible -- not authenticated")

    nif = page.evaluate("""
        (() => {
            const el = document.querySelector('input[placeholder*="NIF"]');
            return el ? el.value : '';
        })()
    """)
    print(f"    NIF/NIE: {nif or '(empty)'}")
    if not nif.strip():
        raise RuntimeError("NIF/NIE is empty -- authentication likely failed")

    # Fecha de nacimiento
    try:
        js_set_value(page, _IDS["fecha"], config.FECHA_NACIMIENTO)
        print(f"    Filled fecha: {config.FECHA_NACIMIENTO}")
    except Exception as e:
        print(f"    [WARN] Could not fill fecha via ID: {e}")
        try:
            inp = page.wait_for_selector('input[placeholder="dd/mm/aaaa"]', timeout=5000)
            inp.fill(config.FECHA_NACIMIENTO)
            print(f"    Filled fecha via placeholder fallback.")
        except Exception:
            pass

    # Select country
    safe_wait(page, 1000)
    try:
        js_select_option(page, _IDS["pais"], label=config.PAIS)
        print(f"    Selected país: {config.PAIS}")
    except Exception as e:
        print(f"    [WARN] Could not select país: {e}")

    # Click Aceptar
    safe_wait(page, 1000)
    try:
        js_click_id(page, _IDS["aceptar"])
    except Exception:
        page.evaluate("""
            const btns = document.querySelectorAll('button, input[type="submit"]');
            for (const b of btns) {
                if ((b.textContent || '').trim() === 'Aceptar' || b.value === 'Aceptar') {
                    b.click();
                    break;
                }
            }
        """)
    safe_wait(page, 5000)
    print("    Clicked Aceptar, waiting for solicitudes table...")

    # Enter localizador
    safe_wait(page, 3000)
    try:
        js_set_value(page, _IDS["localizador"], config.LOCALIZADOR)
        print(f"    Filled localizador: {config.LOCALIZADOR}")
    except Exception as e:
        print(f"    [WARN] Could not fill localizador via ID: {e}")
        try:
            inp = page.wait_for_selector(
                'input[placeholder="Introduce localizador"]', timeout=5000
            )
            inp.fill(config.LOCALIZADOR)
            print("    Filled localizador via placeholder fallback.")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Step 5: Click "Pedir cita" (JS click + reload)
# ---------------------------------------------------------------------------

def click_pedir_cita(page):
    print("[5] Clicking 'Pedir cita'...")
    safe_wait(page, 2000)

    try:
        js_click_id(page, _IDS["pedir_cita"])
    except Exception:
        try:
            js_click_css(page, 'input[value="Pedir cita"]')
        except Exception:
            page.evaluate("""
                const inputs = document.querySelectorAll('input[type="submit"], button');
                for (const inp of inputs) {
                    if (inp.value === 'Pedir cita' || (inp.textContent || '').includes('Pedir cita')) {
                        inp.click();
                        break;
                    }
                }
            """)

    # Wait for the JSF form submission / navigation to finish before reloading.
    for _ in range(5):
        try:
            page.wait_for_load_state("domcontentloaded", timeout=5000)
            break
        except Exception:
            time.sleep(1)

    safe_wait(page, 3000)

    # The JSF response sometimes renders raw XML; reload to get proper HTML.
    print("    Reloading page after Pedir cita click...")
    try:
        page.reload(wait_until="domcontentloaded", timeout=15000)
    except Exception as e:
        print(f"    [WARN] Reload failed ({e}), waiting for page to settle...")
        time.sleep(3)

    safe_wait(page, 3000)
    print(f"    URL after Pedir cita: {page.url}")


# ---------------------------------------------------------------------------
# Step 6: Click "Seleccionar centro"
# ---------------------------------------------------------------------------

def click_seleccionar_centro(page):
    print("[6] Clicking 'Seleccionar centro'...")
    safe_wait(page, 2000)

    try:
        js_click_css(page, 'input[value="Seleccionar centro"]')
    except Exception:
        page.evaluate("""
            const inputs = document.querySelectorAll('input[type="submit"], button');
            for (const inp of inputs) {
                if (inp.value === 'Seleccionar centro') {
                    inp.click();
                    break;
                }
            }
        """)

    safe_wait(page, 5000)
    print(f"    URL after Seleccionar centro: {page.url}")


# ---------------------------------------------------------------------------
# Step 7: Check for available dates
# ---------------------------------------------------------------------------

def check_availability(page) -> bool:
    """Return True unless the page clearly says there are no appointments.

    Strategy: we know what the 'no citas' page looks like (it contains
    phrases like 'no hay citas disponibles').  If the page does NOT match
    that known state, something is different — assume citas may be
    available and alert the user.  A false alarm is far better than
    silently missing a real slot.
    """
    print("[7] Checking for available dates...")
    safe_wait(page, 3000)

    if not is_on_cita_page(page):
        print(f"    Not on the cita page (URL: {page.url}).")
        snippet = page.evaluate("document.body.innerText").strip()[:200].replace("\n", " | ")
        print(f"    Snippet: {snippet}")
        return False

    body_text = page.evaluate("document.body.innerText")
    body_lower = body_text.lower()

    _NO_CITAS_PHRASES = [
        "no hay citas",
        "no existen citas",
        "no disponible",
        "selecciona la sede",
    ]
    for phrase in _NO_CITAS_PHRASES:
        if phrase in body_lower:
            print(f"    No available dates (page contains '{phrase}').")
            return False

    reason = page.evaluate("""
        (() => {
            const cal = document.querySelectorAll(
                '.ui-datepicker td a, table.calendario td a, .fc-day a'
            );
            if (cal.length > 0) return 'calendar links';

            const hora = document.querySelectorAll(
                'select[name*="hora"], select[id*="hora"], input[name*="hora"]'
            );
            if (hora.length > 0) return 'time selector';

            const slots = document.querySelectorAll(
                '[class*="hora"], [class*="slot"], button[name*="hora"]'
            );
            if (slots.length > 0) return 'slot elements';

            return null;
        })()
    """)

    if reason:
        print(f"    >>> CITAS AVAILABLE! (detected: {reason}) <<<")
    else:
        snippet = body_text.strip()[:300].replace("\n", " | ")
        print(f"    >>> PAGE DIFFERS FROM KNOWN 'NO CITAS' STATE <<<")
        print(f"    >>> Snippet: {snippet}")
        print(f"    >>> Treating as POSSIBLE CITAS -- CHECK THE BROWSER! <<<")

    return True


# ---------------------------------------------------------------------------
# Session validity
# ---------------------------------------------------------------------------

def is_session_valid(page) -> bool:
    return config.DGT_DOMAIN in page.url


# ---------------------------------------------------------------------------
# Full flow and re-check
# ---------------------------------------------------------------------------

def _get_active_page(page):
    """After auth, the active page might have changed (popup/new tab)."""
    result_page = getattr(_do_clave_auth, '_result_page', None)
    if result_page and config.DGT_DOMAIN in result_page.url:
        _do_clave_auth._result_page = None
        return result_page
    return page


def run_full_flow(page) -> bool | None:
    """Full flow: start -> centro+area -> catalog -> auth -> form -> check.

    Returns True (cita found), False (no cita), or None (error).
    """
    try:
        navigate_to_start(page)
        select_centro_and_area(page)
        click_catalog_pedir_cita(page)

        if not handle_clave_auth(page):
            return None

        page = _get_active_page(page)
        fill_canje_form(page)
        click_pedir_cita(page)
        click_seleccionar_centro(page)
        return check_availability(page)

    except Exception as e:
        alerts.alert_error(f"Flow failed: {e}")
        return None


def run_recheck(page) -> bool | None:
    """Re-check with existing session. Returns None if session expired."""
    try:
        print("\n--- Re-checking with existing session ---")

        page.goto(config.DGT_START_URL, wait_until="domcontentloaded", timeout=30000)
        safe_wait(page, 3000)

        if config.CLAVE_DOMAIN in page.url:
            print("    Session expired, need re-authentication.")
            return None

        select_centro_and_area(page)
        click_catalog_pedir_cita(page)

        if not handle_clave_auth(page):
            return None

        page = _get_active_page(page)
        fill_canje_form(page)
        click_pedir_cita(page)
        click_seleccionar_centro(page)
        return check_availability(page)

    except Exception as e:
        alerts.alert_error(f"Re-check failed: {e}")
        return None
