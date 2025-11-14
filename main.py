import argparse
import copy
import os
import re
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
SVG_FILE = BASE_DIR / "svgs.html"
DEFAULT_LAUNCHER_PATH = r"C:\Users\jyeal\Desktop\The Sims 4.bat"
RAW_LAUNCHER_PATH = os.environ.get("SIMS4_BAT_PATH", DEFAULT_LAUNCHER_PATH)
DISABLE_PREFIX = "-disablepacks:"
DISABLE_REGEX = re.compile(r"-disablepacks:[^\s]+", re.IGNORECASE)

with open('raw.txt', 'r') as f:
    RAW_CHECKLIST = f.read()


def _resolve_launcher_path(raw_path: str) -> Path:
    normalized = raw_path.strip().strip('"')
    if not normalized:
        return Path(normalized)
    candidate = Path(normalized)
    if candidate.exists():
        return candidate
    sanitized = normalized.replace("\\", "/")
    if len(sanitized) > 1 and sanitized[1] == ":":
        drive = sanitized[0].lower()
        remainder = sanitized[2:].lstrip("/").replace("\\", "/")
        return Path("/mnt") / drive / Path(remainder)
    return candidate


LAUNCHER_BAT = _resolve_launcher_path(RAW_LAUNCHER_PATH)


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
_launcher_mtime: float | None = None


def flatten_items(categories: List[Dict]) -> List[Dict]:
    return [item for category in categories for item in category["items"]]


def extract_disable_argument(raw_text: str) -> str | None:
    match = DISABLE_REGEX.search(raw_text)
    if not match:
        return None
    snippet = match.group(0)
    canonical, _ = parse_disable_argument(snippet)
    return canonical


def parse_disable_argument(argument: str) -> Tuple[str, List[str]]:
    if not argument:
        raise ValueError("Disable argument cannot be empty.")
    text = argument.strip()
    prefix_index = text.lower().find(DISABLE_PREFIX)
    if prefix_index == -1:
        raise ValueError("Disable argument must include '-disablepacks:' prefix.")
    codes_part = text[prefix_index + len(DISABLE_PREFIX) :]
    codes = [
        code.strip().upper()
        for code in codes_part.split(",")
        if code.strip()
    ]
    canonical = DISABLE_PREFIX + ",".join(codes)
    return canonical, codes


def build_disable_argument(categories: List[Dict]) -> str:
    disabled_codes = [
        item["code"]
        for item in flatten_items(categories)
        if not item.get("enabled", False)
    ]
    return "-disablepacks:" + ",".join(disabled_codes)


def apply_disabled_codes(disabled_codes: set[str]) -> bool:
    changed = False
    flat_items = flatten_items(_state_categories)
    for item in flat_items:
        next_enabled = item["code"] not in disabled_codes
        if item.get("enabled", False) != next_enabled:
            item["enabled"] = next_enabled
            changed = True
    return changed


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
    return markdown, disable_arg


def sync_launcher_argument(disable_argument: str) -> None:
    global _launcher_mtime  # pylint: disable=global-statement
    if not disable_argument or not str(LAUNCHER_BAT):
        return
    try:
        content = LAUNCHER_BAT.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    newline = "\r\n" if "\r\n" in content else "\n"
    normalized = content.replace("\r\n", "\n")
    updated, count = DISABLE_REGEX.subn(disable_argument, normalized, count=1)
    if count == 0:
        lines = normalized.split("\n")
        replaced = False
        for idx, raw_line in enumerate(lines):
            lower_line = raw_line.lower()
            if "-disablepacks" in lower_line:
                start = lower_line.index("-disablepacks")
                lines[idx] = raw_line[:start] + disable_argument
                replaced = True
                break
        if not replaced:
            lines.append(f"set ARGS={disable_argument}")
        updated = "\n".join(lines)
    if updated == normalized:
        return
    updated = updated.replace("\n", newline)
    try:
        LAUNCHER_BAT.write_text(updated, encoding="utf-8")
    except OSError:
        return
    try:
        _launcher_mtime = LAUNCHER_BAT.stat().st_mtime
    except OSError:
        _launcher_mtime = None


def sync_state_from_launcher(force: bool = False) -> bool:
    global _launcher_mtime  # pylint: disable=global-statement
    if not str(LAUNCHER_BAT):
        return False
    try:
        stat_result = LAUNCHER_BAT.stat()
    except OSError:
        _launcher_mtime = None
        return False
    if not force and _launcher_mtime is not None and stat_result.st_mtime <= _launcher_mtime:
        return False
    try:
        content = LAUNCHER_BAT.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        _launcher_mtime = stat_result.st_mtime
        return False
    argument = extract_disable_argument(content)
    if not argument:
        _launcher_mtime = stat_result.st_mtime
        return False
    _, codes = parse_disable_argument(argument)
    disabled_codes = set(codes)
    with STATE_LOCK:
        if not _state_categories:
            _launcher_mtime = stat_result.st_mtime
            return False
        changed = apply_disabled_codes(disabled_codes)
        if changed:
            persist_state(_state_categories, write_state=True)
    _launcher_mtime = stat_result.st_mtime
    return changed


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
    sync_state_from_launcher()
    with STATE_LOCK:
        return _build_payload_locked()


def apply_disable_argument(
    argument: str, *, write_state: bool = True, sync_launcher_file: bool = True
) -> Dict:
    canonical, codes = parse_disable_argument(argument)
    disabled_codes = set(codes)
    with STATE_LOCK:
        apply_disabled_codes(disabled_codes)
        markdown, disable_arg = persist_state(_state_categories, write_state=write_state)
        payload = _build_payload_locked(markdown)
    if sync_launcher_file:
        sync_launcher_argument(disable_arg)
    return payload


def update_item_state(code: str, enabled: bool) -> Dict:
    normalized = code.strip().upper()
    with STATE_LOCK:
        if normalized not in _code_index:
            raise KeyError(normalized)
        stored = _code_index[normalized]
        stored["enabled"] = enabled
        markdown, disable_arg = persist_state(_state_categories, write_state=True)
        payload = _build_payload_locked(markdown)
    sync_launcher_argument(disable_arg)
    return payload


def reset_state_to_default() -> Dict:
    global _state_categories, _code_index  # pylint: disable=global-statement
    with STATE_LOCK:
        _state_categories = copy.deepcopy(DEFAULT_CATEGORIES)
        _code_index = build_code_index(_state_categories)
        markdown, disable_arg = persist_state(_state_categories, write_state=True)
        payload = _build_payload_locked(markdown)
    sync_launcher_argument(disable_arg)
    return payload


def bootstrap_state() -> None:
    ensure_output_files()
    refresh_state_from_disk()
    sync_state_from_launcher(force=True)


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


@app.route("/api/disable", methods=["POST"])
def api_disable_argument():
    data = request.get_json(silent=True) or {}
    argument = str(data.get("argument", "")).strip()
    if not argument:
        return jsonify({"error": "Missing -disablepacks argument."}), 400
    try:
        payload = apply_disable_argument(argument, write_state=True, sync_launcher_file=True)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
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
        print(f"State synced to {STATE_MD.name}")
        return

    run_server(args.host, args.port, args.debug)


if __name__ == "__main__":
    main()
