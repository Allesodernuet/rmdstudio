from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtGui import QTextDocument

from rmdstudio import external
from rmdstudio.model.importer import import_rmd, split_code_blocks
from rmdstudio.model.markdown import SerializeOptions, serialize_rmd
from rmdstudio.model.style import Defaults, block_kind

SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "Welcome.Rmd"


def test_split_code_blocks():
    body = """Before

```{r setup, echo=FALSE}
x <- 1
```

After

```python
print(1)
```
"""
    prose, segments = split_code_blocks(body)
    assert len(segments) == 2
    chunk = next(value for value in segments.values() if hasattr(value, "header"))
    assert chunk.header == "{r setup, echo=FALSE}"
    assert "x <- 1" in chunk.code
    assert "RmdStudioChunk" in prose


@pytest.mark.skipif(external.find_pandoc() is None, reason="Pandoc is not installed")
def test_import_roundtrip(qapp):
    text = SAMPLE.read_text(encoding="utf-8")
    doc = QTextDocument()
    yaml, result = import_rmd(doc, text, Defaults(), SAMPLE.parent)
    assert result.used_pandoc
    assert result.warnings == []
    blocks = []
    block = doc.begin()
    while block.isValid():
        blocks.append(block)
        block = block.next()
    texts = [block.text() for block in blocks]
    assert "The Quiet Machine" in texts
    assert any(block_kind(block) == "chunk_header" for block in blocks)
    assert any(block.textList() is not None for block in blocks)
    serialized = serialize_rmd(doc, yaml, SerializeOptions(preserve_visual=True, defaults=Defaults(),
                                                           document_dir=SAMPLE.parent))
    markdown = serialized.markdown
    assert "# The Quiet Machine" in markdown
    assert "## Why another editor?" in markdown
    assert "```{r setup, echo=FALSE}" in markdown
    assert "| Statistic | Value |" in markdown
    assert "[underlined text]{.underline}" in markdown
