"""Shared rendering/export logic for the HTML/CSS CV pipeline.

Used by generate-cv-web.py (CLI) and serve-editor.py (local edit UI).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from io import StringIO
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import FoldedScalarString, LiteralScalarString

# Not every entry point that imports this module also puts src/ on
# sys.path (serve-editor.py does; generate-cv-web.py doesn't), so ensure
# it ourselves before pulling in the new-item placeholder content.
_SRC_DIR = str(Path(__file__).resolve().parent.parent / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
from cvbuilder import new_item_content

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "cv" / "web"
DATA_FILE = WEB_DIR / "data.yaml"
TEMPLATE_NAME = "template.html.j2"

_yaml = YAML()
_yaml.preserve_quotes = True
# Effectively unlimited: ruamel re-wraps *every* scalar (including plain,
# untouched bullets) to fit `width` on each dump, so any finite value causes
# large incidental diffs unrelated to what was actually edited. Folded (">")
# fields lose their original hand-wrapped line breaks either way (that
# formatting isn't semantically part of the YAML), so this just means they
# come back as one long line instead of a differently-wrapped one.
_yaml.width = 1_000_000
_yaml.indent(mapping=2, sequence=4, offset=2)


def find_chrome() -> str:
    """Return a Chrome/Chromium binary path from env or PATH."""
    env_bin = os.environ.get("CHROME_BIN")
    if env_bin and Path(env_bin).is_file():
        return env_bin
    for name in ("google-chrome", "chromium", "chromium-browser", "google-chrome-stable"):
        path = shutil.which(name)
        if path:
            return path
    sys.exit("No Chrome/Chromium binary found on PATH")


def load_data_text(text: str) -> Any:
    """Parse CV YAML from text without reading ``DATA_FILE``."""
    return _yaml.load(text)


def load_data() -> Any:
    """Load CV YAML from the configured filesystem data file."""
    with DATA_FILE.open(encoding="utf-8") as f:
        return _yaml.load(f)


def save_data(data: Any) -> None:
    """Write CV YAML to the configured filesystem data file."""
    with DATA_FILE.open("w", encoding="utf-8") as f:
        _yaml.dump(data, f)


def dump_data_text(data: Any) -> str:
    """Serialize ``data`` to YAML text without writing the file."""
    buffer = StringIO()
    _yaml.dump(data, buffer)
    return buffer.getvalue()


def read_data_text() -> str:
    """Return the raw YAML text of the CV data file."""
    return DATA_FILE.read_text(encoding="utf-8")


def write_data_text(text: str) -> None:
    """Overwrite the CV data file with ``text``."""
    DATA_FILE.write_text(text, encoding="utf-8")


class EditHistory:
    """Persisted undo/redo stacks of ``data.yaml`` snapshots.

    Each mutating editor write should call :meth:`push_before_change` with
    the file contents *before* the write. Undo restores the previous
    snapshot and parks the overwritten state on the redo stack.
    """

    def __init__(
        self,
        path: Optional[Path] = None,
        max_entries: int = 50,
    ) -> None:
        """Initialise history storage.

        Args:
            path: JSON file for the stacks. Defaults to
                ``data/edit-history.json`` under the repo root.
            max_entries: Maximum undo (and redo) depth.
        """
        self.path = path or (REPO_ROOT / "data" / "edit-history.json")
        self.max_entries = max_entries

    def status(self) -> dict[str, Any]:
        """Return whether undo/redo are available and current depths."""
        state = self._load()
        return {
            "can_undo": bool(state["undo"]),
            "can_redo": bool(state["redo"]),
            "undo_depth": len(state["undo"]),
            "redo_depth": len(state["redo"]),
        }

    def push_before_change(
        self, label: str = "edit", text: Optional[str] = None
    ) -> None:
        """Snapshot file contents onto the undo stack (clears redo).

        Args:
            label: Short description of the impending change.
            text: Snapshot text; defaults to the current file contents.
        """
        snapshot = text if text is not None else (
            read_data_text() if DATA_FILE.is_file() else ""
        )
        if not snapshot:
            return
        state = self._load()
        state["undo"].append({"label": label, "text": snapshot})
        if len(state["undo"]) > self.max_entries:
            state["undo"] = state["undo"][-self.max_entries :]
        state["redo"] = []
        self._save(state)

    def undo(self) -> dict[str, Any]:
        """Restore the previous snapshot.

        Returns:
            Status dict including the restored label.

        Raises:
            ValueError: If there is nothing to undo.
        """
        state = self._load()
        if not state["undo"]:
            raise ValueError("nothing to undo")
        entry = state["undo"].pop()
        state["redo"].append(
            {"label": entry.get("label", "edit"), "text": read_data_text()}
        )
        if len(state["redo"]) > self.max_entries:
            state["redo"] = state["redo"][-self.max_entries :]
        write_data_text(entry["text"])
        self._save(state)
        result = self.status()
        result["label"] = entry.get("label", "edit")
        return result

    def redo(self) -> dict[str, Any]:
        """Re-apply the most recently undone snapshot.

        Returns:
            Status dict including the restored label.

        Raises:
            ValueError: If there is nothing to redo.
        """
        state = self._load()
        if not state["redo"]:
            raise ValueError("nothing to redo")
        entry = state["redo"].pop()
        state["undo"].append(
            {"label": entry.get("label", "edit"), "text": read_data_text()}
        )
        if len(state["undo"]) > self.max_entries:
            state["undo"] = state["undo"][-self.max_entries :]
        write_data_text(entry["text"])
        self._save(state)
        result = self.status()
        result["label"] = entry.get("label", "edit")
        return result

    def _load(self) -> dict[str, list[dict[str, str]]]:
        """Load stacks from disk, or return empty stacks."""
        if not self.path.is_file():
            return {"undo": [], "redo": []}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            return {"undo": [], "redo": []}
        undo = raw.get("undo") if isinstance(raw, dict) else None
        redo = raw.get("redo") if isinstance(raw, dict) else None
        if not isinstance(undo, list):
            undo = []
        if not isinstance(redo, list):
            redo = []
        return {
            "undo": [e for e in undo if isinstance(e, dict) and "text" in e],
            "redo": [e for e in redo if isinstance(e, dict) and "text" in e],
        }

    def _save(self, state: dict[str, list[dict[str, str]]]) -> None:
        """Persist stacks to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(state, ensure_ascii=False),
            encoding="utf-8",
        )


def edit_history(path: Optional[Path] = None) -> EditHistory:
    """Return an :class:`EditHistory` for the active data file."""
    return EditHistory(path=path)


def render_cv_body(data: Optional[Any] = None, *, edit_mode: bool = False) -> str:
    """Render ``cv_body.html.j2`` with CV data and no page chrome."""
    if data is None:
        data = load_data()
    env = Environment(loader=FileSystemLoader(str(WEB_DIR)))
    return env.get_template("cv_body.html.j2").render(
        edit_mode=edit_mode,
        **data,
    )


def render_html(data: Optional[Any] = None, edit_mode: bool = False) -> str:
    """Render the standalone CV HTML document for print and export."""
    if data is None:
        data = load_data()
    env = Environment(loader=FileSystemLoader(str(WEB_DIR)))
    return env.get_template(TEMPLATE_NAME).render(edit_mode=edit_mode, **data)


def print_to_pdf(html_path: Path, out_pdf: Path) -> None:
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    chrome = find_chrome()
    subprocess.run(
        [
            chrome,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--print-to-pdf-no-header",
            "--no-pdf-header-footer",
            f"--print-to-pdf={out_pdf}",
            str(html_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def export_pdf(out_pdf: Path, data: Optional[Any] = None) -> None:
    """Render the CV from a dict, YAML text, or the filesystem fallback."""
    if isinstance(data, str):
        data = load_data_text(data)
    html = render_html(data=data, edit_mode=False)
    out_html = WEB_DIR / "_rendered.html"
    out_html.write_text(html, encoding="utf-8")
    try:
        print_to_pdf(out_html, out_pdf)
    finally:
        out_html.unlink(missing_ok=True)


# ---------- data-path get/set (used by the editor's save endpoint) ----------

_TOKEN_RE = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def _walk(data: Any, path: str) -> tuple[Any, Any]:
    """Return (parent_container, key_or_index) for a data-path like
    'experience[1].subsections[0].bullets[2]'."""
    node = data
    parent, key = None, None
    for m in _TOKEN_RE.finditer(path):
        name, idx = m.groups()
        key = name if name is not None else int(idx)
        parent = node
        node = node[key]
    if parent is None:
        raise ValueError(f"empty path: {path!r}")
    return parent, key


def set_leaf(data: Any, path: str, new_value: str) -> None:
    """Set a leaf scalar at ``path``, preserving YAML scalar style."""
    parent, key = _walk(data, path)
    old_value = parent[key]
    if isinstance(old_value, LiteralScalarString):
        new_value = LiteralScalarString(new_value)
    elif isinstance(old_value, FoldedScalarString):
        new_value = FoldedScalarString(new_value)
    parent[key] = new_value


def replace_item(data: Any, path: str, value: Any) -> None:
    """Replace the node at ``path`` with ``value`` (any YAML-compatible value).

    Unlike :func:`set_leaf`, this accepts non-scalar values such as maps,
    which is needed when swapping whole subsections.
    """
    parent, key = _walk(data, path)
    parent[key] = value


def subsection_from_text(heading: str, content: str) -> CommentedMap:
    """Build a subsection map from flattened snippet text.

    Inverts ``SnippetImporter._format_subsection``: blank-line-separated
    blocks become paragraphs, and lines prefixed with ``- `` become bullets.

    Args:
        heading: Subsection heading (may be empty).
        content: Flattened snippet content.

    Returns:
        A subsection mapping with heading/paragraphs/bullets as needed.
    """
    paragraphs: list[str] = []
    bullets: list[str] = []
    for block in content.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith("- "):
            for line in block.splitlines():
                text = line.strip()
                if text.startswith("- "):
                    text = text[2:].strip()
                if text:
                    bullets.append(text)
        else:
            paragraphs.append(" ".join(block.split()))
    subsection = CommentedMap()
    if heading.strip():
        subsection["heading"] = heading.strip()
    if paragraphs:
        subsection["paragraphs"] = CommentedSeq(
            FoldedScalarString(p) for p in paragraphs
        )
    if bullets:
        subsection["bullets"] = CommentedSeq(bullets)
    return subsection


def _default_insert_value(list_path: str, value: Any) -> Any:
    """Choose a sensible default insert value for a list path.

    Structural only: this decides *which* placeholder shape a given list
    path gets (a bare string, a job, a subsection, ...). The actual
    wording lives in :mod:`cvbuilder.new_item_content`.
    """
    if value is not None:
        return value
    if list_path.endswith(".bullets") or list_path.endswith(".paragraphs"):
        return new_item_content.GENERIC_ITEM
    if list_path.endswith("skills.technical") or list_path.endswith(
        "skills.functional"
    ):
        return new_item_content.SKILL
    if list_path == "bio":
        return FoldedScalarString(new_item_content.BIO_PARAGRAPH)
    if list_path == "education":
        return new_item_content.EDUCATION_ENTRY
    if list_path == "experience":
        job = CommentedMap()
        job.update(new_item_content.JOB)
        job["subsections"] = CommentedSeq()
        subsection = CommentedMap()
        subsection["heading"] = new_item_content.NEW_JOB_SUBSECTION_HEADING
        subsection["bullets"] = CommentedSeq([new_item_content.BULLET])
        job["subsections"].append(subsection)
        return job
    if list_path.endswith(".subsections"):
        subsection = CommentedMap()
        subsection["heading"] = new_item_content.NEW_SUBSECTION_HEADING
        subsection["bullets"] = CommentedSeq([new_item_content.BULLET])
        return subsection
    if list_path == "panels":
        panel = CommentedMap()
        panel.update(new_item_content.PANEL)
        panel["items"] = CommentedSeq([new_item_content.GENERIC_ITEM])
        return panel
    if list_path == "person.profiles":
        profile = CommentedMap()
        profile.update(new_item_content.PROFILE)
        return profile
    return new_item_content.GENERIC_ITEM


def insert_item(
    data: Any,
    list_path: str,
    index: Optional[int] = None,
    value: Any = None,
) -> None:
    """Insert ``value`` into the sequence at ``list_path``.

    Args:
        data: Root YAML document.
        list_path: Path to a sequence (e.g. ``experience[0].subsections``).
        index: Insertion index; defaults to append.
        value: Value to insert; a sensible default is used when None.

    Raises:
        ValueError: If the path does not resolve to a sequence.
    """
    if not list_path:
        raise ValueError("list_path is required")
    tokens = list(_TOKEN_RE.finditer(list_path))
    if not tokens:
        raise ValueError(f"empty path: {list_path!r}")
    node: Any = data
    for match in tokens:
        name, idx = match.groups()
        key = name if name is not None else int(idx)
        if (
            name is not None
            and match is tokens[-1]
            and (key not in node or node[key] is None)
        ):
            node[key] = CommentedSeq()
        node = node[key]
    if not isinstance(node, (list, CommentedSeq)):
        raise ValueError(f"not a list path: {list_path!r}")
    insert_value = _default_insert_value(list_path, value)
    at = len(node) if index is None else max(0, min(int(index), len(node)))
    node.insert(at, insert_value)


def delete_item(data: Any, path: str) -> None:
    """Delete the item at ``path`` from its parent sequence.

    Args:
        data: Root YAML document.
        path: Full path to the item (e.g. ``bio[1]``).

    Raises:
        ValueError: If the parent is not a sequence.
    """
    parent, key = _walk(data, path)
    if not isinstance(parent, (list, CommentedSeq)):
        raise ValueError(f"parent is not a list for path: {path!r}")
    if not isinstance(key, int):
        raise ValueError(f"path must address a list index: {path!r}")
    del parent[key]


def move_item(data: Any, path: str, offset: int) -> None:
    """Move the item at ``path`` by ``offset`` positions within its list.

    Args:
        data: Root YAML document.
        path: Full path to the item.
        offset: Relative move (+1 down, -1 up).

    Raises:
        ValueError: If the move would leave the list bounds or parent is not a list.
    """
    parent, key = _walk(data, path)
    if not isinstance(parent, (list, CommentedSeq)):
        raise ValueError(f"parent is not a list for path: {path!r}")
    if not isinstance(key, int):
        raise ValueError(f"path must address a list index: {path!r}")
    new_index = key + int(offset)
    if new_index < 0 or new_index >= len(parent):
        raise ValueError(
            f"move out of bounds: index {key} + {offset} in list of {len(parent)}"
        )
    item = parent.pop(key)
    parent.insert(new_index, item)
