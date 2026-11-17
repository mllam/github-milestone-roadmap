"""Write the static roadmap site for a configuration."""

from __future__ import annotations

import json
from html import escape
from importlib.resources import files
from pathlib import Path
from string import Template

from . import __version__
from .config import RoadmapConfig

STATIC_ASSETS = ("app.js", "styles.css")

GITHUB_ICON_PATH = (
    "M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 "
    "0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13"
    "-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07"
    "-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08"
    "-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82A7.65 7.65 0 0 1 8 3.86c.68 0 1.36"
    ".09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27"
    ".82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93"
    "-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z"
)


def read_static_text(name: str) -> str:
    """Read a file shipped in the package's ``static`` folder.

    Parameters
    ----------
    name : str
        File name inside ``static``.

    Returns
    -------
    str
        File contents.
    """
    return (
        files("github_milestone_roadmap")
        .joinpath("static", name)
        .read_text(encoding="utf-8")
    )


def render_source_link(source_url: str) -> str:
    """Render the GitHub link shown in the top-right corner.

    Parameters
    ----------
    source_url : str
        Link target; empty means no link.

    Returns
    -------
    str
        HTML for the link, or an empty string.
    """
    if not source_url:
        return ""
    return (
        f'        <a class="github-link" href="{escape(source_url)}" '
        'rel="noreferrer">\n'
        '          <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">\n'
        f'            <path d="{GITHUB_ICON_PATH}" />\n'
        "          </svg>\n"
        "          <span>GitHub</span>\n"
        "        </a>"
    )


def render_index_html(config: RoadmapConfig) -> str:
    """Fill the ``index.html`` template from a configuration.

    All configuration values are HTML-escaped.

    Parameters
    ----------
    config : RoadmapConfig
        The roadmap configuration.

    Returns
    -------
    str
        The rendered page.
    """
    repo_links = "\n".join(
        f'          <a href="#{escape(repo.name)}">{escape(repo.name)}</a>'
        for repo in config.repos
    )
    subtitle_paragraph = (
        f'        <p class="subtitle">{escape(config.subtitle)}</p>'
        if config.subtitle
        else ""
    )
    template = Template(read_static_text("index.html"))
    return template.substitute(
        title=escape(config.title),
        heading=escape(config.heading),
        description=escape(config.description),
        home_url=escape(config.home.url),
        home_text=escape(config.home.text),
        source_link=render_source_link(config.source_url),
        subtitle_paragraph=subtitle_paragraph,
        repo_links=repo_links,
        version=escape(__version__),
    )


def build_runtime_config(config: RoadmapConfig) -> dict[str, object]:
    """Build the ``config.json`` content that ``app.js`` reads in the browser.

    Parameters
    ----------
    config : RoadmapConfig
        The roadmap configuration.

    Returns
    -------
    dict
        JSON-serialisable runtime configuration.
    """
    return {
        "cache_key": config.cache_key,
        "repos": [
            {"owner": repo.owner, "name": repo.name, "description": repo.description}
            for repo in config.repos
        ],
    }


def build_site(config: RoadmapConfig, output_dir: Path) -> list[Path]:
    """Write the roadmap site into a directory.

    Existing files with the same names are overwritten; other files in
    ``output_dir`` are left untouched.

    Parameters
    ----------
    config : RoadmapConfig
        The roadmap configuration.
    output_dir : Path
        Directory to write into; created if missing.

    Returns
    -------
    list of Path
        The files written.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    index_path = output_dir / "index.html"
    index_path.write_text(render_index_html(config), encoding="utf-8")
    written.append(index_path)

    for name in STATIC_ASSETS:
        path = output_dir / name
        path.write_text(read_static_text(name), encoding="utf-8")
        written.append(path)

    config_path = output_dir / "config.json"
    config_path.write_text(
        json.dumps(build_runtime_config(config), indent=2) + "\n", encoding="utf-8"
    )
    written.append(config_path)
    return written
