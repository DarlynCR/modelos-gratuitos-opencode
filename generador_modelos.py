#!/usr/bin/env python3
"""
generador_modelos.py — OpenCode Zen Free Models Generator
-----------------------------------------------------------
Scrapes https://opencode.ai/docs/zen/#pricing daily, detects free models,
and dynamically rewrites infografia_interactiva.html with updated cards,
decision matrix mappings, and notifications on change.

Usage:
    python generador_modelos.py          # normal run
    python generador_modelos.py --force  # force update even if no changes
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

# =============================================================================
# CONFIGURATION
# =============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE_DIR, "index.html")
STATE_PATH = os.path.join(BASE_DIR, "estado_modelos.json")
PRICING_URL = "https://opencode.ai/docs/zen/#pricing"

# Timezone offset in hours (UTC-5 = -5). Set TZ_OFFSET env var in GitHub Actions if needed.
TZ_OFFSET = int(os.environ.get("TZ_OFFSET", "-5"))

def now_local():
    return datetime.now(timezone.utc) + timedelta(hours=TZ_OFFSET)

MONTHS_ES = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]

MODEL_CONFIGS = {
    "deepseek-v4-flash-free": {
        "name": "DeepSeek V4 Flash",
        "color": "cyan",
        "tag": "DEF DEVEL",
        "rating": "9.5",
        "description": "El rey del formato interactivo. Coherencia impecable y rapidez insuperable.",
        "traits": {"Razonamiento": 4, "Formatos": 5, "Soporte Git": 5}
    },
    "big-pickle": {
        "name": "Big Pickle",
        "color": "emerald",
        "tag": "STEALTH",
        "rating": "8.8",
        "description": "Gran todoterreno. Capacidades rotativas de prueba. Excelente para planificar.",
        "traits": {"Razonamiento": 4, "Estructura": 4, "Explicación": 5}
    },
    "mimo-v2.5-free": {
        "name": "MiMo V2.5",
        "color": "amber",
        "tag": "CONTEXT",
        "rating": "8.0",
        "description": "Ventana de contexto enorme de Xiaomi. Ultra veloz procesando archivos completos.",
        "traits": {"Contexto": 5, "Velocidad": 5, "Precisión": 3}
    },
    "north-mini-code-free": {
        "name": "North Mini Code",
        "color": "pink",
        "tag": "COMPLEMENTO",
        "rating": "7.2",
        "description": "Pequeño, rápido y ágil. Ideal para tareas repetitivas y código rápido.",
        "traits": {"Razonamiento": 3, "Velocidad": 4, "Lógica": 3}
    },
    "nemotron-3-ultra-free": {
        "name": "Nemotron 3 Ultra",
        "color": "lime",
        "tag": "AUXILIAR",
        "rating": "6.0",
        "description": "Modelo de Nvidia. Gran capacidad cruda, pero suele descuidar formatos de salida locales.",
        "traits": {"Capacidad": 4, "Formatos": 2, "Idioma": 3}
    }
}

# Task -> preferred model list (ordered by priority)
TASK_PREFERENCES = {
    "1": ["deepseek-v4-flash-free", "big-pickle", "north-mini-code-free"],
    "2": ["deepseek-v4-flash-free", "big-pickle", "north-mini-code-free"],
    "3": ["big-pickle", "deepseek-v4-flash-free", "north-mini-code-free"],
    "4": ["deepseek-v4-flash-free", "big-pickle", "north-mini-code-free"],
    "5": ["mimo-v2.5-free", "deepseek-v4-flash-free", "big-pickle"],
    "6": ["big-pickle", "deepseek-v4-flash-free", "north-mini-code-free"],
    "7": ["north-mini-code-free", "deepseek-v4-flash-free", "big-pickle"]
}

# Color mapping for unknown models
FALLBACK_COLORS = ["blue", "indigo", "purple", "teal", "sky"]

# =============================================================================
# SCRAPING
# =============================================================================
class PricingTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_thead = False
        self.in_tbody = False
        self.in_cell = False
        self._capture = False
        self.headers = []
        self.rows = []
        self.current_row = []
        self.current_cell = ""

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.in_table = True
            self._capture = False
            self.headers = []
        if not self.in_table:
            return
        if tag == "thead":
            self.in_thead = True
        if tag == "tbody":
            self.in_tbody = True
        if tag == "tr":
            self.current_row = []
        if tag in ("th", "td"):
            self.in_cell = True
            self.current_cell = ""

    def handle_endtag(self, tag):
        if tag == "table":
            self.in_table = False
        if not self.in_table:
            return
        if tag == "thead":
            self.in_thead = False
            # Detect if this is the pricing table
            h_lower = [h.lower() for h in self.headers]
            self._capture = "input" in h_lower and "output" in h_lower
            if self._capture:
                self.rows = []
        if tag == "tbody":
            self.in_tbody = False
        if tag in ("th", "td"):
            self.in_cell = False
            self.current_row.append(self.current_cell.strip())
        if tag == "tr":
            if self.in_thead:
                self.headers = [h for h in self.current_row if h]
            elif self.in_tbody and self.current_row and self._capture:
                self.rows.append(list(self.current_row))
            self.current_row = []

    def handle_data(self, data):
        if self.in_cell:
            self.current_cell += data


def fetch_pricing_html():
    req = urllib.request.Request(
        PRICING_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/125.0.0.0 Safari/537.36"
        }
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse_free_models(html):
    parser = PricingTableParser()
    parser.feed(html)

    free_models = []
    for row in parser.rows:
        if len(row) < 3:
            continue
        model_name = row[0].strip()
        input_price = row[1].strip().lower()
        output_price = row[2].strip().lower()
        if input_price == "free" and output_price == "free":
            free_models.append(model_name)

    return free_models


def normalize_model_name(name):
    name = name.strip().lower()
    name = name.replace(" ", "-").replace("_", "-")
    name = re.sub(r"[^a-z0-9.-]", "", name)
    return name


def fetch_models_api():
    req = urllib.request.Request(
        "https://opencode.ai/zen/v1/models",
        headers={"User-Agent": "opencode-zen-generator/1.0"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return [item["id"] for item in data.get("data", [])]


def resolve_free_model_ids(scraped_names, all_model_ids):
    scraped_normalized = {}
    for name in scraped_names:
        key = normalize_model_name(name)
        scraped_normalized[key] = name

    all_normalized = {}
    for mid in all_model_ids:
        key = normalize_model_name(mid)
        all_normalized[key] = mid

    resolved = []
    for key, original_name in scraped_normalized.items():
        if key in all_normalized:
            resolved.append(all_normalized[key])
        else:
            print(f"[WARN] '{original_name}' not found in API model list, using normalized ID '{key}'")
            resolved.append(key)

    return resolved


# =============================================================================
# STATE MANAGEMENT
# =============================================================================
def load_previous_state():
    if not os.path.exists(STATE_PATH):
        return {"free_models": [], "last_updated": None}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"free_models": [], "last_updated": None}


def save_current_state(free_models):
    state = {
        "free_models": sorted(free_models),
        "last_updated": now_local().isoformat()
    }
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    return state


def detect_changes(previous, current):
    prev_set = set(previous.get("free_models", []))
    curr_set = set(current)

    added = curr_set - prev_set
    removed = prev_set - curr_set

    return added, removed


# =============================================================================
# HTML GENERATION
# =============================================================================
def stars_html(count, color):
    filled = "★" * count
    empty = "☆" * (5 - count)
    return f'<span class="text-{color}-400">{filled}</span>{empty}'


def generate_card_html(model_id):
    cfg = MODEL_CONFIGS.get(model_id)
    if not cfg:
        return generate_fallback_card(model_id)

    c = cfg["color"]
    traits_html = "".join(
        f'<div class="flex justify-between"><span>{trait}:</span> {stars_html(val, c)}</div>\n            '
        for trait, val in cfg["traits"].items()
    )

    return f"""<div class="bg-brand-card border border-{c}-500/20 rounded-xl p-4 flex flex-col justify-between hover:border-{c}-500/50 transition-all duration-300">
          <div>
            <div class="flex items-center justify-between mb-3">
              <span class="text-[9px] font-bold text-{c}-400 px-2 py-0.5 bg-{c}-950/60 border border-{c}-800 rounded">{cfg["tag"]}</span>
              <span class="text-xs font-bold text-slate-300">★ {cfg["rating"]}</span>
            </div>
            <h3 class="mono text-base font-bold text-white mb-1">{cfg["name"]}</h3>
            <p class="text-[11px] text-slate-400 mb-4 leading-normal">{cfg["description"]}</p>
          </div>
          <div class="space-y-1 text-[10px] text-slate-300 border-t border-slate-900 pt-3">
            {traits_html}
          </div>
        </div>"""


def generate_fallback_card(model_id):
    c = FALLBACK_COLORS[hash(model_id) % len(FALLBACK_COLORS)]
    return f"""<div class="bg-brand-card border border-{c}-500/20 rounded-xl p-4 flex flex-col justify-between hover:border-{c}-500/50 transition-all duration-300">
          <div>
            <div class="flex items-center justify-between mb-3">
              <span class="text-[9px] font-bold text-{c}-400 px-2 py-0.5 bg-{c}-950/60 border border-{c}-800 rounded">FREE</span>
              <span class="text-xs font-bold text-slate-300">★ —</span>
            </div>
            <h3 class="mono text-base font-bold text-white mb-1">{model_id}</h3>
            <p class="text-[11px] text-slate-400 mb-4 leading-normal">Modelo gratuito detectado automáticamente desde la tabla de precios oficial.</p>
          </div>
          <div class="space-y-1 text-[10px] text-slate-300 border-t border-slate-900 pt-3">
            <div class="flex justify-between"><span>Estado:</span> <span class="text-{c}-400">Gratuito ✓</span></div>
          </div>
        </div>"""


def pick_best_model(task_id, available):
    for preferred in TASK_PREFERENCES.get(task_id, []):
        if preferred in available:
            return preferred
    if available:
        return available[0]
    return None


def update_html(free_models, force=False):
    if not free_models:
        print("[WARN] No free models found. Skipping HTML update.")
        return False

    if not os.path.exists(HTML_PATH):
        print(f"[ERROR] HTML file not found: {HTML_PATH}")
        return False

    with open(HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    now = now_local()
    now_local = now.strftime("%d/%m/%Y %H:%M")
    month_name = MONTHS_ES[now.month]
    year = now.year

    # Always: update month/year badge
    html = re.sub(
        r'(⚡\s*Datos Oficiales Actualizados\s*[•·]\s*)[^<]+',
        f'\\1{month_name} {year}',
        html
    )

    # Always: update last-run timestamp
    html = re.sub(
        r'(<p id="ultima-actualizacion"[^>]*>)[^<]+(</p>)',
        f'\\1🔄 Última actualización: {now_local}\\2',
        html
    )

    # Cards & matrix: only update on force or real model changes
    if force:
        cards_html = "\n".join(generate_card_html(mid) for mid in free_models)
        card_pattern = r'(<div id="contenedor-tarjetas-modelos" class="grid[^>]*>)\s*.*?(?=</div>\s*</section>)'
        html = re.sub(
            card_pattern,
            lambda m: m.group(1) + "\n" + cards_html + "\n        ",
            html,
            flags=re.DOTALL
        )

        available = set(free_models)
        for task_num in TASK_PREFERENCES:
            best = pick_best_model(task_num, available)
            if best is None:
                continue
            span_id = f"optimo-tarea-{task_num}"
            cfg = MODEL_CONFIGS.get(best)
            color = cfg["color"] if cfg else FALLBACK_COLORS[hash(best) % len(FALLBACK_COLORS)]
            id_pattern = rf'(<span id="{span_id}" class="mono text-xs font-bold )text-\w+(-\d+)?("[^>]*>)[^<]+(</span>)'
            html = re.sub(id_pattern, rf'\1text-{color}-400\3{best}\4', html)

        for cmd_id, (default_model, default_color) in {
            "cmd-ds": ("deepseek-v4-flash-free", "cyan"),
            "cmd-pickle": ("big-pickle", "emerald"),
            "cmd-mimo": ("mimo-v2.5-free", "amber"),
        }.items():
            if default_model in available:
                m = default_model
                cfg = MODEL_CONFIGS.get(m)
                c = cfg["color"] if cfg else default_color
            elif available:
                m = sorted(available)[0]
                cfg = MODEL_CONFIGS.get(m)
                c = cfg["color"] if cfg else default_color
            else:
                continue
            cmd_text = f"/model opencode/{m}"
            cmd_pattern = rf'(<code class="mono text-\[11px\] )text-\w+(-\d+)?( bg-\w+-950/30 px-2\.5 py-1\.5 rounded border border-\w+-900/50" id="{cmd_id}">)[^<]+(</code>)'
            html = re.sub(cmd_pattern, rf'\1text-{c}-400\3{cmd_text}\4', html)

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    return True


# =============================================================================
# NOTIFICATIONS
# =============================================================================
def send_notification(title, message):
    try:
        subprocess.run(
            [
                "powershell",
                "-Command",
                f'''
                [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
                $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
                $textNodes = $template.GetElementsByTagName("text")
                $textNodes.Item(0).AppendChild($template.CreateTextNode("{title}")) > $null
                $textNodes.Item(1).AppendChild($template.CreateTextNode("{message}")) > $null
                $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
                $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("OpenCode Zen Generator")
                $notifier.Show($toast)
                '''
            ],
            capture_output=True, timeout=15
        )
        print(f"[NOTIFICATION] {title}: {message}")
    except Exception as e:
        print(f"[NOTIFICATION FALLBACK] {title}: {message} (error: {e})")
        try:
            subprocess.run(
                ["powershell", "-Command", f'msg * "{title}: {message}"'],
                capture_output=True, timeout=10
            )
        except Exception:
            pass


# =============================================================================
# MAIN
# =============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="OpenCode Zen Free Models Generator — "
                    "scrapes pricing page, detects changes, updates HTML"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Force update HTML even if no changes detected"
    )
    parser.add_argument(
        "--no-notify", action="store_true",
        help="Skip desktop notification"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  OpenCode Zen Free Models Generator")
    print(f"  {now_local().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Step 1: Scrape pricing page
    print("\n[1/4] Scraping pricing page...")
    try:
        html = fetch_pricing_html()
        scraped_names = parse_free_models(html)
        print(f"  Found {len(scraped_names)} free models in pricing table")
    except Exception as e:
        print(f"  [ERROR] Failed to scrape: {e}")
        sys.exit(1)

    if not scraped_names:
        print("  [ERROR] No free models found in pricing table")
        sys.exit(1)

    # Step 2: Resolve names to model IDs
    print("[2/4] Resolving model IDs...")
    try:
        all_model_ids = fetch_models_api()
        free_models = resolve_free_model_ids(scraped_names, all_model_ids)
        print(f"  Resolved {len(free_models)} model(s): {', '.join(free_models)}")
    except Exception as e:
        print(f"  [WARN] API fetch failed ({e}), using scraped names as IDs")
        free_models = [normalize_model_name(n) for n in scraped_names]

    # Step 3: Detect changes
    print("[3/4] Detecting changes...")
    previous = load_previous_state()
    added, removed = detect_changes(previous, free_models)

    if added:
        print(f"  [CHANGE] New free models: {', '.join(sorted(added))}")
    if removed:
        print(f"  [CHANGE] Models no longer free: {', '.join(sorted(removed))}")
    if not added and not removed:
        print("  No changes detected")

    has_changes = bool(added or removed)

    # Step 4: Update HTML (timestamps always, cards only on changes/force)
    print("[4/4] Updating HTML...")
    updated = update_html(free_models, force=(has_changes or args.force))
    if updated:
        print(f"  HTML updated: {HTML_PATH}")

    # Save current state
    save_current_state(free_models)
    print(f"  State saved: {STATE_PATH}")

    # Notification
    if has_changes and not args.no_notify:
        title = "OpenCode Zen — Modelos Gratuitos Actualizados"
        parts = []
        if added:
            parts.append(f"Nuevos: {', '.join(sorted(added))}")
        if removed:
            parts.append(f"Ya no gratis: {', '.join(sorted(removed))}")
        message = " | ".join(parts)
        send_notification(title, message)

    print("\n[DONE]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
