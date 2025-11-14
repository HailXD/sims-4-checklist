import argparse
import copy
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from threading import Lock
from typing import Dict, List, Tuple

from PyQt6 import QtCore, QtGui, QtWidgets

try:
    from PyQt6.QtSvg import QSvgRenderer
except ImportError:  # pragma: no cover - QtSvg may be optional
    QSvgRenderer = None

BASE_DIR = Path(__file__).resolve().parent
STATE_MD = BASE_DIR / "state.md"
DEFAULT_MD = BASE_DIR / "default.md"
SVG_FILE = BASE_DIR / "svgs.html"
DEFAULT_LAUNCHER_PATH = r"C:\Users\jyeal\Desktop\The Sims 4.bat"
RAW_LAUNCHER_PATH = os.environ.get("SIMS4_BAT_PATH", DEFAULT_LAUNCHER_PATH)
DISABLE_PREFIX = "-disablepacks:"
DISABLE_REGEX = re.compile(r"-disablepacks:[^\s]*", re.IGNORECASE)
SVG_NS = "http://www.w3.org/2000/svg"
SVG_ICON_SIZE = 48
SVG_SYMBOLS: Dict[str, bytes] = {}
SVG_ICON_CACHE: Dict[str, QtGui.QIcon] = {}

ET.register_namespace("", SVG_NS)

with open('raw.txt', 'r') as f:
    RAW_CHECKLIST = f.read()


def _svg_tag(tag: str) -> str:
    return f"{{{SVG_NS}}}{tag}"


def _load_svg_symbols() -> Dict[str, bytes]:
    if not SVG_FILE.exists():
        return {}
    try:
        tree = ET.parse(SVG_FILE)
    except (ET.ParseError, OSError):
        return {}
    root = tree.getroot()
    symbols: Dict[str, bytes] = {}
    for symbol in root.findall(_svg_tag("symbol")):
        symbol_id = symbol.attrib.get("id")
        if not symbol_id:
            continue
        view_box = symbol.attrib.get("viewBox") or "0 0 256 256"
        svg_element = ET.Element(_svg_tag("svg"), attrib={"viewBox": view_box})
        for attr in ("width", "height"):
            value = symbol.attrib.get(attr)
            if value:
                svg_element.set(attr, value)
        for child in symbol:
            svg_element.append(copy.deepcopy(child))
        svg_bytes = ET.tostring(svg_element, encoding="utf-8")
        symbols[symbol_id.strip().upper()] = svg_bytes
    return symbols


def _render_svg_icon(svg_bytes: bytes, size: int = SVG_ICON_SIZE) -> QtGui.QIcon | None:
    if QSvgRenderer is None:
        return None
    renderer = QSvgRenderer(svg_bytes)
    if not renderer.isValid():
        return None
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    renderer.render(painter, QtCore.QRectF(0, 0, size, size))
    painter.end()
    icon = QtGui.QIcon(pixmap)
    return None if icon.isNull() else icon


def get_pack_icon(code: str) -> QtGui.QIcon | None:
    if not code:
        return None
    normalized = code.strip().upper()
    icon = SVG_ICON_CACHE.get(normalized)
    if icon:
        return icon
    svg_bytes = SVG_SYMBOLS.get(normalized)
    if not svg_bytes:
        return None
    icon = _render_svg_icon(svg_bytes)
    if icon:
        SVG_ICON_CACHE[normalized] = icon
    return icon


SVG_SYMBOLS = _load_svg_symbols()


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

class ChecklistWindow(QtWidgets.QMainWindow):
    """Simple desktop UI for browsing and updating the Sims 4 DLC checklist."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Sims 4 DLC Checklist")
        self.resize(1100, 750)
        self.checkbox_map: Dict[str, QtWidgets.QCheckBox] = {}
        self._build_ui()
        self.refresh_payload()

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_layout = QtWidgets.QVBoxLayout(central)
        main_layout.setSpacing(12)

        self.updated_label = QtWidgets.QLabel("Last updated: --")
        self.updated_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(self.updated_label)

        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.categories_container = QtWidgets.QWidget()
        self.categories_layout = QtWidgets.QVBoxLayout(self.categories_container)
        self.categories_layout.setContentsMargins(0, 0, 0, 0)
        self.categories_layout.setSpacing(10)
        self.scroll_area.setWidget(self.categories_container)
        main_layout.addWidget(self.scroll_area, stretch=1)

        disable_row = QtWidgets.QHBoxLayout()
        disable_label = QtWidgets.QLabel("Disable argument:")
        self.disable_line = QtWidgets.QLineEdit()
        self.disable_line.setPlaceholderText("-disablepacks:EP01,EP02,...")
        self.apply_argument_button = QtWidgets.QPushButton("Apply")
        self.apply_argument_button.clicked.connect(self.apply_disable_argument_from_ui)
        disable_row.addWidget(disable_label)
        disable_row.addWidget(self.disable_line, stretch=1)
        disable_row.addWidget(self.apply_argument_button)
        main_layout.addLayout(disable_row)

        button_row = QtWidgets.QHBoxLayout()
        self.refresh_button = QtWidgets.QPushButton("Refresh from Launcher")
        self.refresh_button.clicked.connect(self.refresh_from_launcher)
        self.reset_button = QtWidgets.QPushButton("Reset to Default")
        self.reset_button.clicked.connect(self.reset_state_to_default)
        button_row.addWidget(self.refresh_button)
        button_row.addWidget(self.reset_button)
        button_row.addStretch()
        main_layout.addLayout(button_row)

        self.markdown_edit = QtWidgets.QPlainTextEdit()
        self.markdown_edit.setReadOnly(True)
        self.markdown_edit.setPlaceholderText("Markdown view of the current checklist.")
        self.markdown_edit.setMinimumHeight(180)
        main_layout.addWidget(self.markdown_edit)

        self.setStatusBar(QtWidgets.QStatusBar())

    def _ensure_category_widgets(self, categories: List[Dict]) -> None:
        if self.checkbox_map:
            return
        for category in categories:
            group_box = QtWidgets.QGroupBox(category["title"])
            group_layout = QtWidgets.QGridLayout(group_box)
            group_layout.setHorizontalSpacing(12)
            group_layout.setVerticalSpacing(8)
            for col in range(3):
                group_layout.setColumnStretch(col, 1)
            for idx, item in enumerate(category["items"]):
                label = f"{item['name']} ({item['code']})"
                checkbox = QtWidgets.QCheckBox(label)
                icon = get_pack_icon(item["code"])
                if icon:
                    checkbox.setIcon(icon)
                    checkbox.setIconSize(QtCore.QSize(SVG_ICON_SIZE, SVG_ICON_SIZE))
                checkbox.setChecked(item.get("enabled", False))
                checkbox.stateChanged.connect(
                    partial(self.handle_checkbox_state_changed, item["code"])
                )
                row, col = divmod(idx, 3)
                group_layout.addWidget(checkbox, row, col)
                self.checkbox_map[item["code"]] = checkbox
            self.categories_layout.addWidget(group_box)
        self.categories_layout.addStretch()

    def _update_checkboxes(self, categories: List[Dict]) -> None:
        for category in categories:
            for item in category["items"]:
                checkbox = self.checkbox_map.get(item["code"])
                if checkbox is None:
                    continue
                block = checkbox.blockSignals(True)
                checkbox.setChecked(item.get("enabled", False))
                checkbox.blockSignals(block)

    def _apply_payload(self, payload: Dict) -> None:
        self._ensure_category_widgets(payload["categories"])
        self._update_checkboxes(payload["categories"])
        self.disable_line.setText(payload["disableArgument"])
        self.markdown_edit.setPlainText(payload["markdown"])
        self.updated_label.setText(f"Last updated: {payload['updatedAt']}")

    def refresh_payload(self) -> None:
        payload = build_payload()
        self._apply_payload(payload)

    def handle_checkbox_state_changed(self, code: str, state: int) -> None:
        enabled = QtCore.Qt.CheckState(state) == QtCore.Qt.CheckState.Checked
        try:
            payload = update_item_state(code, enabled)
        except KeyError:
            QtWidgets.QMessageBox.warning(
                self,
                "Unknown DLC Code",
                f"DLC code '{code}' could not be found.",
            )
            self.refresh_payload()
            return
        self._apply_payload(payload)
        action = "enabled" if enabled else "disabled"
        self.statusBar().showMessage(f"{code} {action}", 3000)

    def apply_disable_argument_from_ui(self) -> None:
        argument = self.disable_line.text().strip()
        if not argument:
            QtWidgets.QMessageBox.warning(
                self, "Missing Argument", "Enter a -disablepacks argument first."
            )
            return
        try:
            payload = apply_disable_argument(argument, write_state=True, sync_launcher_file=True)
        except ValueError as error:
            QtWidgets.QMessageBox.warning(self, "Invalid Argument", str(error))
            return
        self._apply_payload(payload)
        self.statusBar().showMessage("Disable argument applied.", 3000)

    def reset_state_to_default(self) -> None:
        payload = reset_state_to_default()
        self._apply_payload(payload)
        self.statusBar().showMessage("Checklist reset to defaults.", 3000)

    def refresh_from_launcher(self) -> None:
        changed = sync_state_from_launcher(force=True)
        self.refresh_payload()
        if changed:
            self.statusBar().showMessage("State synced from launcher file.", 3000)
        else:
            self.statusBar().showMessage("Launcher file already in sync.", 3000)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Launch a Sims 4 DLC checklist desktop UI."
    )
    parser.add_argument(
        "--init-only",
        action="store_true",
        help="Create markdown outputs and exit without starting the UI.",
    )
    args = parser.parse_args()

    if args.init_only:
        bootstrap_state()
        print(f"State synced to {STATE_MD.name}")
        return

    app = QtWidgets.QApplication(sys.argv)
    window = ChecklistWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
