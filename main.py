import argparse
import copy
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Dict, List, Tuple

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    send_from_directory,
    url_for,
)

BASE_DIR = Path(__file__).resolve().parent
STATE_MD = BASE_DIR / "state.md"
DEFAULT_MD = BASE_DIR / "default.md"
MAIN_TXT = BASE_DIR / "main.txt"
DISABLE_TXT = BASE_DIR / "main_disable.txt"
SVG_FILE = BASE_DIR / "svgs.html"

RAW_CHECKLIST = """# The Sims 4 DLC - Checklist

## Expansion Packs

- [x] EP01 - Get To Work
- [x] EP02 - Get Together
- [x] EP03 - City Living
- [ ] EP04 - Cats & Dogs
- [x] EP05 - Seasons
- [x] EP06 - Get Famous
- [x] EP07 - Island Living
- [x] EP08 - Discover University
- [x] EP09 - Eco Lifestyle
- [x] EP10 - Snowy Escape
- [x] EP11 - Cottage Living
- [x] EP12 - High School Years
- [ ] EP13 - Growing Together
- [ ] EP14 - Horse Ranch
- [x] EP15 - For Rent
- [x] EP16 - Lovestruck
- [ ] EP17 - Life & Death
- [ ] EP18 - Businesses & Hobbies
- [ ] EP19 - Enchanted by Nature
- [ ] EP20 - Adventure Awaits

## Game Packs

- [x] GP01 - Outdoor Retreat
- [x] GP02 - Spa Day
- [ ] GP03 - Dine Out
- [ ] GP04 - Vampires
- [ ] GP05 - Parenthood
- [ ] GP06 - Jungle Adventure
- [ ] GP07 - StrangerVille
- [ ] GP08 - Realm of Magic
- [ ] GP09 - Journey to Batuu
- [ ] GP10 - Dream Home Decorator
- [ ] GP11 - My Wedding Stories
- [ ] GP12 - Werewolves

## Stuff Packs

- [x] SP01 - Luxury Party
- [x] SP02 - Perfect Patio
- [ ] SP03 - Cool Kitchen
- [ ] SP04 - Spooky Stuff
- [x] SP05 - Movie Hangout
- [x] SP06 - Romantic Garden
- [ ] SP07 - Kids Room
- [x] SP08 - Backyard
- [ ] SP09 - Vintage Glamour
- [x] SP10 - Bowling Night
- [x] SP11 - Fitness
- [ ] SP12 - Toddler
- [x] SP13 - Laundry Day
- [ ] SP14 - My First Pet
- [x] SP15 - Moschino
- [x] SP16 - Tiny Living
- [ ] SP17 - Nifty Knitting
- [ ] SP18 - Paranormal
- [ ] SP46 - Home Chef Hustle
- [ ] SP49 - Crystal Creations

## Kits

- [ ] SP21 - Country Kitchen
- [ ] SP22 - Bust The Dust
- [ ] SP23 - Courtyard Oasis
- [ ] SP24 - Fashion Street
- [ ] SP25 - Industrial Loft
- [ ] SP26 - Incheon Arrivals
- [ ] SP28 - Modern Menswear
- [ ] SP29 - Blooming Rooms
- [x] SP30 - Carnaval Streetwear
- [ ] SP31 - Decor to the Max
- [ ] SP32 - Moonlight Chic
- [ ] SP33 - Little Campers
- [x] SP34 - First Fits
- [ ] SP35 - Desert Luxe
- [ ] SP36 - Pastel Pop
- [ ] SP37 - Everyday Clutter
- [x] SP38 - Simtimates Collection
- [ ] SP40 - Greenhouse Haven
- [x] SP41 - Basement Treasures
- [ ] SP42 - Grunge Revival
- [ ] SP43 - Book Nook
- [x] SP44 - Poolside Splash
- [ ] SP45 - Modern Luxe
- [ ] SP47 - Castle Estate
- [ ] SP48 - Goth Galore
- [ ] SP50 - Urban Homage
- [x] SP51 - Party Essentials
- [ ] SP52 - Riviera Retreat
- [ ] SP53 - Cozy Bistro
- [ ] SP54 - Artist Studio
- [ ] SP55 - Storybook Nursery
- [x] SP56 - Sweet Slumber Party
- [ ] SP57 - Cozy Kitsch
- [ ] SP58 - Comfy Gamer
- [ ] SP59 - Secret Sanctuary
- [ ] SP60 - Casanova Cave
- [ ] SP61 - Refined Living Room
- [ ] SP62 - Business Chic
- [ ] SP63 - Sleek Bathroom
- [x] SP64 - Sweet Allure
- [ ] SP66 - Golden Years
- [ ] SP67 - Kitchen Clutter
- [ ] SP69 - Autumn Apparel
- [ ] SP71 - Grange Mudroom
- [ ] SP72 - Essential Glam

## Free Stuff

- [x] FP01 - Holiday Celebration
"""


def parse_checklist(markdown: str) -> List[Dict]:
    categories: List[Dict] = []
    current: Dict | None = None
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("## Output"):
            break
        if line.startswith("## "):
            current = {"title": line[3:].strip(), "items": []}
            categories.append(current)
            continue
        if line.startswith("#"):
            continue
        if not line.startswith("- ["):
            continue
        if current is None:
            continue
        marker = line[3:6]
        enabled = "x" in marker.lower()
        try:
            remainder = line.split("] ", 1)[1]
            code, name = remainder.split(" - ", 1)
        except ValueError:
            continue
        item = {
            "code": code.strip().upper(),
            "name": name.strip(),
            "enabled": enabled,
        }
        current["items"].append(item)
    return categories


DEFAULT_CATEGORIES = parse_checklist(RAW_CHECKLIST)
STATE_LOCK = Lock()
_state_categories: List[Dict] = []
_code_index: Dict[str, Dict] = {}


def flatten_items(categories: List[Dict]) -> List[Dict]:
    return [item for category in categories for item in category["items"]]


def build_disable_argument(categories: List[Dict]) -> str:
    disabled_codes = [
        item["code"]
        for item in flatten_items(categories)
        if not item.get("enabled", False)
    ]
    return "-disablepacks:" + ",".join(disabled_codes)


def generate_markdown(categories: List[Dict]) -> str:
    lines: List[str] = ["# The Sims 4 DLC - Checklist", ""]
    for category in categories:
        lines.append(f"## {category['title']}")
        lines.append("")
        for item in category["items"]:
            mark = "x" if item.get("enabled", False) else " "
            lines.append(f"- [{mark}] {item['code']} - {item['name']}")
        lines.append("")
    lines.append("## Output")
    lines.append("")
    lines.append(build_disable_argument(categories))
    lines.append("")
    return "\n".join(lines)


def build_code_index(categories: List[Dict]) -> Dict[str, Dict]:
    return {item["code"]: item for item in flatten_items(categories)}


def persist_state(
    categories: List[Dict], *, write_state: bool = True
) -> Tuple[str, str]:
    markdown = generate_markdown(categories)
    disable_arg = build_disable_argument(categories)
    if write_state:
        STATE_MD.write_text(markdown, encoding="utf-8")
    MAIN_TXT.write_text(markdown, encoding="utf-8")
    DISABLE_TXT.write_text(disable_arg, encoding="utf-8")
    return markdown, disable_arg


def ensure_output_files() -> None:
    if not DEFAULT_MD.exists():
        DEFAULT_MD.write_text(generate_markdown(DEFAULT_CATEGORIES), encoding="utf-8")

    if STATE_MD.exists():
        parsed = parse_checklist(STATE_MD.read_text(encoding="utf-8"))
        target = parsed or copy.deepcopy(DEFAULT_CATEGORIES)
        write_state = not parsed
        persist_state(target, write_state=write_state)
    else:
        persist_state(copy.deepcopy(DEFAULT_CATEGORIES), write_state=True)


def refresh_state_from_disk() -> None:
    global _state_categories, _code_index  # pylint: disable=global-statement
    if STATE_MD.exists():
        parsed = parse_checklist(STATE_MD.read_text(encoding="utf-8"))
    else:
        parsed = []
    if not parsed:
        parsed = copy.deepcopy(DEFAULT_CATEGORIES)
        persist_state(parsed, write_state=True)
    _state_categories = parsed
    _code_index = build_code_index(_state_categories)


def _build_payload_locked(markdown: str | None = None) -> Dict:
    snapshot = copy.deepcopy(_state_categories)
    markdown_text = markdown or generate_markdown(snapshot)
    payload = {
        "categories": snapshot,
        "disableArgument": build_disable_argument(snapshot),
        "markdown": markdown_text,
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return payload


def build_payload() -> Dict:
    with STATE_LOCK:
        return _build_payload_locked()


def update_item_state(code: str, enabled: bool) -> Dict:
    normalized = code.strip().upper()
    with STATE_LOCK:
        if normalized not in _code_index:
            raise KeyError(normalized)
        stored = _code_index[normalized]
        stored["enabled"] = enabled
        markdown, _ = persist_state(_state_categories, write_state=True)
        return _build_payload_locked(markdown)


def reset_state_to_default() -> Dict:
    global _state_categories, _code_index  # pylint: disable=global-statement
    with STATE_LOCK:
        _state_categories = copy.deepcopy(DEFAULT_CATEGORIES)
        _code_index = build_code_index(_state_categories)
        markdown, _ = persist_state(_state_categories, write_state=True)
        return _build_payload_locked(markdown)


def bootstrap_state() -> None:
    ensure_output_files()
    refresh_state_from_disk()


bootstrap_state()

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["JSON_SORT_KEYS"] = False


@app.route("/", methods=["GET"])
def index():
    payload = build_payload()
    sprite_url = url_for("svg_sprite")
    return render_template("index.html", initial_payload=payload, sprite_url=sprite_url)


@app.route("/svgs.html", methods=["GET"])
def svg_sprite():
    if not SVG_FILE.exists():
        return jsonify({"error": "SVG sprite sheet is missing."}), 404
    return send_from_directory(BASE_DIR, "svgs.html", mimetype="image/svg+xml")


@app.route("/api/state", methods=["GET"])
def api_state():
    return jsonify(build_payload())


@app.route("/api/toggle", methods=["POST"])
def api_toggle():
    data = request.get_json(silent=True) or {}
    code = str(data.get("code", "")).strip().upper()
    if not code:
        return jsonify({"error": "Missing DLC code."}), 400
    if "enabled" not in data:
        return jsonify({"error": "Missing enabled flag."}), 400
    enabled = data["enabled"]
    if not isinstance(enabled, bool):
        enabled = str(enabled).strip().lower() in {"1", "true", "yes", "on"}
    try:
        payload = update_item_state(code, enabled)
    except KeyError:
        return jsonify({"error": f"DLC code '{code}' was not found."}), 404
    return jsonify(payload)


@app.route("/api/reset", methods=["POST"])
def api_reset():
    payload = reset_state_to_default()
    return jsonify(payload)


def run_server(host: str, port: int, debug: bool) -> None:
    app.run(host=host, port=port, debug=debug, use_reloader=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Serve a Sims 4 DLC checklist with persistence."
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind.")
    parser.add_argument("--port", type=int, default=5000, help="Port to listen on.")
    parser.add_argument(
        "--debug", action="store_true", help="Run Flask in debug mode (no reloader)."
    )
    parser.add_argument(
        "--init-only",
        action="store_true",
        help="Create markdown outputs and exit without starting the server.",
    )
    args = parser.parse_args()

    if args.init_only:
        bootstrap_state()
        print(f"State synced to {STATE_MD.name}, {MAIN_TXT.name}, and {DISABLE_TXT.name}.")
        return

    run_server(args.host, args.port, args.debug)


if __name__ == "__main__":
    main()
