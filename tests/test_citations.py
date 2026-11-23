from __future__ import annotations

import json

from rmdstudio.citations import parse_bibtex, parse_csl_json


def test_parse_bibtex():
    text = """
    @article{doe2024,
      author = {Doe, Jane and Smith, John},
      title = {A {Study} of Testing},
      year = {2024},
      doi = {10.1234/example}
    }
    @book{other2020,
      author = {Example, Alex},
      title = {Another Book},
      year = {2020}
    }
    """
    items = parse_bibtex(text)
    assert [item.key for item in items] == ["doe2024", "other2020"]
    assert items[0].title == "A Study of Testing"
    assert items[0].authors == "Doe & Smith"
    assert items[0].year == "2024"
    assert items[1].authors == "Example"


def test_parse_csl_json():
    text = json.dumps([
        {
            "id": "doe2024",
            "title": "A Study",
            "author": [{"family": "Doe", "given": "Jane"}],
            "issued": {"date-parts": [[2024]]},
            "type": "article-journal",
        }
    ])
    items = parse_csl_json(text)
    assert len(items) == 1
    assert items[0].key == "doe2024"
    assert items[0].authors == "Doe"
    assert items[0].display().startswith("Doe · 2024")
