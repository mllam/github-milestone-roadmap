"""Load and validate the roadmap configuration file (TOML)."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_HEADING = "Community Roadmap"

_TOP_LEVEL_KEYS = {
    "title",
    "heading",
    "subtitle",
    "description",
    "source_url",
    "cache_key",
    "home",
    "repos",
}
_HOME_KEYS = {"text", "url"}
_REPO_KEYS = {"owner", "name", "description"}
_REPO_PART_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class ConfigError(ValueError):
    """Raised when the roadmap configuration is invalid."""


@dataclass(frozen=True)
class RepoConfig:
    """A GitHub repository shown on the roadmap.

    Attributes
    ----------
    owner : str
        GitHub user or organisation owning the repository.
    name : str
        Repository name. Also used as the page anchor, so it must be unique.
    description : str
        Short description shown under the repository heading.
    """

    owner: str
    name: str
    description: str = ""


@dataclass(frozen=True)
class HomeLink:
    """The brand link in the top-left corner of the page.

    Attributes
    ----------
    text : str
        Link text.
    url : str
        Link target.
    """

    text: str
    url: str


@dataclass(frozen=True)
class RoadmapConfig:
    """Configuration of one roadmap site.

    Attributes
    ----------
    title : str
        Browser tab title.
    heading : str
        Main page heading.
    subtitle : str
        Line shown under the heading.
    description : str
        Content of the ``<meta name="description">`` tag.
    source_url : str
        URL of the GitHub link in the top-right corner; empty hides the link.
    cache_key : str
        Prefix for the browser ``localStorage`` cache of GitHub API responses.
    home : HomeLink
        Brand link in the top-left corner.
    repos : tuple of RepoConfig
        Repositories shown on the roadmap, in display order.
    """

    title: str
    heading: str
    subtitle: str
    description: str
    source_url: str
    cache_key: str
    home: HomeLink
    repos: tuple[RepoConfig, ...]


def slugify_text(text: str) -> str:
    """Turn free text into a lowercase, hyphen-separated slug.

    Parameters
    ----------
    text : str
        Text to convert.

    Returns
    -------
    str
        Slug containing only ``a-z``, ``0-9`` and ``-``.
    """
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def read_string_field(
    table: dict[str, Any], key: str, where: str, default: str | None = None
) -> str:
    """Read a string value from a TOML table.

    Parameters
    ----------
    table : dict
        Parsed TOML table.
    key : str
        Key to read.
    where : str
        Location of the table, used in error messages.
    default : str or None
        Value used when the key is missing; ``None`` makes the key required.

    Returns
    -------
    str
        The value.

    Raises
    ------
    ConfigError
        If the key is required and missing, or the value is not a string.
    """
    if key not in table:
        if default is None:
            raise ConfigError(f"{where}: missing required key '{key}'")
        return default
    value = table[key]
    if not isinstance(value, str):
        raise ConfigError(f"{where}: '{key}' must be a string, got {value!r}")
    return value


def check_unknown_keys(table: dict[str, Any], allowed: set[str], where: str) -> None:
    """Fail on keys that the configuration format does not know.

    Parameters
    ----------
    table : dict
        Parsed TOML table.
    allowed : set of str
        Keys allowed in this table.
    where : str
        Location of the table, used in error messages.

    Raises
    ------
    ConfigError
        If the table contains keys outside ``allowed``.
    """
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise ConfigError(
            f"{where}: unknown key(s) {', '.join(unknown)}; "
            f"allowed: {', '.join(sorted(allowed))}"
        )


def parse_repo_entry(entry: Any, index: int) -> RepoConfig:
    """Validate one ``[[repos]]`` entry.

    Parameters
    ----------
    entry : Any
        Parsed TOML value of the entry.
    index : int
        Position of the entry, used in error messages.

    Returns
    -------
    RepoConfig
        The validated repository.

    Raises
    ------
    ConfigError
        If the entry is malformed.
    """
    where = f"repos[{index}]"
    if not isinstance(entry, dict):
        raise ConfigError(f"{where}: must be a table with 'owner' and 'name'")
    check_unknown_keys(entry, _REPO_KEYS, where)
    owner = read_string_field(entry, "owner", where)
    name = read_string_field(entry, "name", where)
    for key, value in (("owner", owner), ("name", name)):
        if not _REPO_PART_RE.match(value):
            raise ConfigError(f"{where}: '{key}' is not a valid GitHub name: {value!r}")
    description = read_string_field(entry, "description", where, default="")
    return RepoConfig(owner=owner, name=name, description=description)


def parse_config_data(data: dict[str, Any]) -> RoadmapConfig:
    """Validate parsed TOML data and fill in defaults.

    Parameters
    ----------
    data : dict
        Parsed TOML document.

    Returns
    -------
    RoadmapConfig
        The validated configuration.

    Raises
    ------
    ConfigError
        If the data does not describe a valid roadmap.
    """
    check_unknown_keys(data, _TOP_LEVEL_KEYS, "config")
    title = read_string_field(data, "title", "config")
    heading = read_string_field(data, "heading", "config", default=DEFAULT_HEADING)
    subtitle = read_string_field(data, "subtitle", "config", default="")
    description = read_string_field(
        data, "description", "config", default=subtitle or title
    )
    source_url = read_string_field(data, "source_url", "config", default="")
    cache_key = read_string_field(
        data, "cache_key", "config", default=slugify_text(title) or "roadmap"
    )

    home_data = data.get("home", {})
    if not isinstance(home_data, dict):
        raise ConfigError("home: must be a table with 'text' and 'url'")
    check_unknown_keys(home_data, _HOME_KEYS, "home")
    home = HomeLink(
        text=read_string_field(home_data, "text", "home", default=title),
        url=read_string_field(home_data, "url", "home", default="/"),
    )

    repos_data = data.get("repos")
    if not isinstance(repos_data, list) or not repos_data:
        raise ConfigError("config: at least one [[repos]] entry is required")
    repos = tuple(parse_repo_entry(entry, i) for i, entry in enumerate(repos_data))

    seen: set[str] = set()
    for repo in repos:
        if repo.name in seen:
            raise ConfigError(
                f"repos: repository name '{repo.name}' is used twice; "
                "names must be unique because they are used as page anchors"
            )
        seen.add(repo.name)

    return RoadmapConfig(
        title=title,
        heading=heading,
        subtitle=subtitle,
        description=description,
        source_url=source_url,
        cache_key=cache_key,
        home=home,
        repos=repos,
    )


def load_config(path: Path) -> RoadmapConfig:
    """Read and validate a roadmap configuration file.

    Parameters
    ----------
    path : Path
        Path to the TOML configuration file.

    Returns
    -------
    RoadmapConfig
        The validated configuration.

    Raises
    ------
    ConfigError
        If the file is not valid TOML or not a valid roadmap configuration.
    FileNotFoundError
        If the file does not exist.
    """
    with path.open("rb") as file:
        try:
            data = tomllib.load(file)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"{path}: invalid TOML: {exc}") from exc
    try:
        return parse_config_data(data)
    except ConfigError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
