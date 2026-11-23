"""BibTeX/CSL JSON reading and the Zotero citation picker."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QWidget,
)

from .dialogs import BaseDialog


@dataclass
class Citation:
    key: str
    title: str = ""
    authors: str = ""
    year: str = ""
    kind: str = ""
    doi: str = ""

    def display(self) -> str:
        bits = [self.authors, self.year, self.title]
        return " · ".join(bit for bit in bits if bit) or self.key

    def search_text(self) -> str:
        return " ".join((self.key, self.title, self.authors, self.year, self.kind, self.doi)).lower()


def load_bibliography(path: Path) -> list[Citation]:
    text = path.read_text(encoding="utf-8", errors="replace")
    suffix = path.suffix.lower()
    if suffix == ".json" or text.lstrip().startswith(("[", "{")):
        return parse_csl_json(text)
    return parse_bibtex(text)


def parse_bibtex(text: str) -> list[Citation]:
    entries: list[Citation] = []
    index = 0
    length = len(text)
    while index < length:
        match = re.search(r"@\s*([A-Za-z]+)\s*[{(]", text[index:])
        if not match:
            break
        start = index + match.start()
        kind = match.group(1).lower()
        open_index = index + match.end() - 1
        open_char = text[open_index]
        close_char = "}" if open_char == "{" else ")"
        end = _matching_delimiter(text, open_index, open_char, close_char)
        if end < 0:
            break
        body = text[open_index + 1:end]
        index = end + 1
        if kind in ("comment", "string", "preamble"):
            continue
        comma = _top_level_comma(body)
        if comma < 0:
            continue
        key = body[:comma].strip()
        fields = _parse_fields(body[comma + 1:])
        if not key:
            continue
        entries.append(Citation(
            key=key,
            title=_clean_value(fields.get("title", "")),
            authors=_format_authors(fields.get("author", "")),
            year=_year_from(fields),
            kind=kind,
            doi=_clean_value(fields.get("doi", "")),
        ))
    return sorted(entries, key=lambda c: (c.authors.lower(), c.year, c.title.lower(), c.key.lower()))


def parse_csl_json(text: str) -> list[Citation]:
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("items", [])
    if not isinstance(data, list):
        return []
    result: list[Citation] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        key = str(item.get("id") or item.get("citation-key") or "").strip()
        if not key:
            continue
        title = str(item.get("title") or "").strip()
        authors = _format_csl_authors(item.get("author") or [])
        year = ""
        issued = item.get("issued")
        if isinstance(issued, dict):
            parts = issued.get("date-parts")
            if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
                year = str(parts[0][0])
        result.append(Citation(key=key, title=title, authors=authors, year=year,
                               kind=str(item.get("type") or ""), doi=str(item.get("DOI") or "")))
    return sorted(result, key=lambda c: (c.authors.lower(), c.year, c.title.lower(), c.key.lower()))


def _format_csl_authors(authors: list) -> str:
    names = []
    for author in authors:
        if not isinstance(author, dict):
            continue
        family = str(author.get("family") or "").strip()
        given = str(author.get("given") or "").strip()
        literal = str(author.get("literal") or "").strip()
        names.append(literal or family or given)
    if not names:
        return ""
    if len(names) > 2:
        return names[0] + " et al."
    return " & ".join(names)


def _matching_delimiter(text: str, start: int, opening: str, closing: str) -> int:
    depth = 0
    in_quote = False
    escaped = False
    for position in range(start, len(text)):
        char = text[position]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if opening == "{" and char == '"':
            in_quote = not in_quote
            continue
        if in_quote:
            continue
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return position
    return -1


def _top_level_comma(text: str) -> int:
    depth = 0
    in_quote = False
    escaped = False
    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_quote = not in_quote
            continue
        if in_quote:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            return index
    return -1


def _parse_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    index = 0
    length = len(text)
    while index < length:
        while index < length and (text[index].isspace() or text[index] == ","):
            index += 1
        name_start = index
        while index < length and text[index] not in "=,":
            index += 1
        name = text[name_start:index].strip().lower()
        if index >= length or text[index] != "=":
            break
        index += 1
        while index < length and text[index].isspace():
            index += 1
        if index >= length:
            break
        if text[index] == "{":
            end = _matching_delimiter(text, index, "{", "}")
            if end < 0:
                break
            value = text[index + 1:end]
            index = end + 1
        elif text[index] == '"':
            end = index + 1
            escaped = False
            while end < length:
                if escaped:
                    escaped = False
                elif text[end] == "\\":
                    escaped = True
                elif text[end] == '"':
                    break
                end += 1
            value = text[index + 1:end]
            index = min(length, end + 1)
        else:
            end = index
            while end < length and text[end] != ",":
                end += 1
            value = text[index:end]
            index = end
        if name:
            fields[name] = value.strip()
    return fields


def _clean_value(value: str) -> str:
    value = value.strip()
    value = re.sub(r"\\[A-Za-z]+\s*", "", value)
    value = value.replace("{", "").replace("}", "").replace("~", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _format_authors(value: str) -> str:
    if not value:
        return ""
    names = re.split(r"\s+and\s+", value)
    last_names = []
    for name in names:
        clean = _clean_value(name).strip(", ")
        if not clean:
            continue
        if "," in clean:
            last_names.append(clean.split(",", 1)[0].strip())
        else:
            parts = clean.split()
            last_names.append(parts[-1] if parts else clean)
    if not last_names:
        return ""
    if len(last_names) > 2:
        return last_names[0] + " et al."
    return " & ".join(last_names)


def _year_from(fields: dict[str, str]) -> str:
    year = _clean_value(fields.get("year", ""))
    if year:
        return year
    date = _clean_value(fields.get("date", ""))
    match = re.search(r"\b(1[5-9]\d\d|20\d\d)\b", date)
    return match.group(1) if match else ""


class CitationDialog(BaseDialog):
    def __init__(self, path: Path | None, parent: QWidget | None = None):
        super().__init__("Insert Zotero citation", parent, 660)
        self.bibliography_path = path
        self.citations: list[Citation] = []

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit(str(path) if path else "")
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText("Choose a Zotero/Better BibTeX .bib or CSL .json file")
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse)
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse)
        wrapper = QWidget()
        wrapper.setLayout(path_row)
        self.form.addRow("Bibliography", wrapper)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search author, title, year or citation key")
        self.search_edit.textChanged.connect(self._filter)
        self.form.addRow("Search", self.search_edit)
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list_widget.setMinimumHeight(260)
        self.list_widget.itemSelectionChanged.connect(self._update_detail)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self.accept())
        self.form.addRow("Results", self.list_widget)
        self.detail = QLabel("")
        self.detail.setObjectName("Hint")
        self.detail.setWordWrap(True)
        self._layout.addWidget(self.detail)
        hint = QLabel("Citations are inserted as [@key] (or [@key1; @key2] for multiple selections). "
                      "The bibliography path is added to YAML if needed.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        self._layout.addWidget(hint)
        self.add_buttons("Insert citation")
        self._load()

    def _browse(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Choose bibliography", str(self.bibliography_path.parent if self.bibliography_path else ""),
            "Bibliographies (*.bib *.json);;BibTeX (*.bib);;CSL JSON (*.json);;All files (*)"
        )
        if not filename:
            return
        self.bibliography_path = Path(filename)
        self.path_edit.setText(filename)
        self._load()

    def _load(self) -> None:
        self.list_widget.clear()
        self.citations = []
        self.detail.setText("")
        if self.bibliography_path is None or not self.bibliography_path.is_file():
            self.detail.setText("No bibliography selected. Choose a .bib or CSL .json file.")
            return
        try:
            self.citations = load_bibliography(self.bibliography_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self.detail.setText(f"Could not read bibliography: {exc}")
            return
        if not self.citations:
            self.detail.setText("No entries were found in this bibliography.")
            return
        self._populate(self.citations)
        self.detail.setText(f"{len(self.citations)} entries loaded.")

    def _populate(self, citations: list[Citation]) -> None:
        self.list_widget.clear()
        for citation in citations:
            item = QListWidgetItem(citation.display())
            item.setData(Qt.ItemDataRole.UserRole, citation.key)
            item.setToolTip(citation.key)
            self.list_widget.addItem(item)
        if citations:
            self.list_widget.setCurrentRow(0)

    def _filter(self, text: str) -> None:
        query = text.strip().lower()
        if not query:
            self._populate(self.citations)
            return
        matches = [citation for citation in self.citations if query in citation.search_text()]
        self._populate(matches)
        self.detail.setText(f"{len(matches)} matching entries.")

    def _update_detail(self) -> None:
        selected = self.selected_citations()
        if not selected:
            self.detail.setText("")
            return
        citation = selected[-1]
        bits = [citation.authors, citation.year, citation.title]
        self.detail.setText(" · ".join(bit for bit in bits if bit) or citation.key)

    def selected_citations(self) -> list[Citation]:
        by_key = {citation.key: citation for citation in self.citations}
        result = []
        for item in self.list_widget.selectedItems():
            key = str(item.data(Qt.ItemDataRole.UserRole) or "")
            citation = by_key.get(key)
            if citation is not None:
                result.append(citation)
        return result
