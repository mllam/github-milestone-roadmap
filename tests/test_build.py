"""Tests for writing the static roadmap site."""

import json
from pathlib import Path

from github_milestone_roadmap.build import build_site
from github_milestone_roadmap.cli import main
from github_milestone_roadmap.config import load_config, parse_config_data

EXAMPLE_CONFIG = Path(__file__).parent.parent / "examples" / "roadmap.toml"


def test_build_writes_site(tmp_path: Path) -> None:
    """Building the example config writes all files with config values filled in."""
    output = tmp_path / "site" / "roadmap"
    written = build_site(load_config(EXAMPLE_CONFIG), output)

    assert sorted(path.name for path in written) == [
        "app.js",
        "config.json",
        "index.html",
        "styles.css",
    ]
    html = (output / "index.html").read_text(encoding="utf-8")
    assert "<title>MLLAM Roadmap</title>" in html
    assert '<a class="brand" href="/">MLLAM</a>' in html
    assert 'href="https://github.com/mllam"' in html
    assert '<a href="#neural-lam">neural-lam</a>' in html
    assert "${" not in html

    runtime = json.loads((output / "config.json").read_text(encoding="utf-8"))
    assert runtime["cache_key"] == "mllam-roadmap"
    assert runtime["repos"][0] == {
        "owner": "mllam",
        "name": "neural-lam",
        "description": "Machine learning weather model training and inference package.",
    }


def test_build_escapes_config_values(tmp_path: Path) -> None:
    """Config values cannot inject HTML into the page."""
    config = parse_config_data(
        {
            "title": "<script>alert(1)</script>",
            "subtitle": 'a "quoted" & <b>bold</b> line',
            "repos": [{"owner": "o", "name": "r"}],
        }
    )
    build_site(config, tmp_path)
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;b&gt;bold&lt;/b&gt;" in html


def test_build_without_source_url_or_subtitle(tmp_path: Path) -> None:
    """Optional page elements are left out when not configured."""
    config = parse_config_data({"title": "t", "repos": [{"owner": "o", "name": "r"}]})
    build_site(config, tmp_path)
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "github-link" not in html
    assert 'class="subtitle"' not in html


def test_cli_build(tmp_path: Path) -> None:
    """The ``build`` subcommand writes the site and exits 0."""
    exit_code = main(
        ["build", "--config", str(EXAMPLE_CONFIG), "--output", str(tmp_path)]
    )
    assert exit_code == 0
    assert (tmp_path / "index.html").exists()


def test_cli_build_reports_bad_config(tmp_path: Path) -> None:
    """A missing config file gives exit code 2 instead of a traceback."""
    exit_code = main(
        [
            "build",
            "--config",
            str(tmp_path / "missing.toml"),
            "--output",
            str(tmp_path / "out"),
        ]
    )
    assert exit_code == 2
