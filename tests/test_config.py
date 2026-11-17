"""Tests for loading and validating the roadmap configuration."""

from pathlib import Path

import pytest

from github_milestone_roadmap.config import (
    DEFAULT_HEADING,
    ConfigError,
    load_config,
    parse_config_data,
)

EXAMPLE_CONFIG = Path(__file__).parent.parent / "examples" / "roadmap.toml"


def test_load_example_config() -> None:
    """The shipped example config loads with all fields set."""
    config = load_config(EXAMPLE_CONFIG)
    assert config.title == "MLLAM Roadmap"
    assert config.cache_key == "mllam-roadmap"
    assert config.home.text == "MLLAM"
    assert [repo.name for repo in config.repos] == [
        "neural-lam",
        "mllam-data-prep",
        "weather-model-graphs",
    ]
    assert all(repo.owner == "mllam" for repo in config.repos)


def test_defaults_for_minimal_config() -> None:
    """Optional fields fall back to documented defaults."""
    config = parse_config_data(
        {"title": "My Project Roadmap", "repos": [{"owner": "o", "name": "r"}]}
    )
    assert config.heading == DEFAULT_HEADING
    assert config.subtitle == ""
    assert config.description == "My Project Roadmap"
    assert config.source_url == ""
    assert config.cache_key == "my-project-roadmap"
    assert config.home.text == "My Project Roadmap"
    assert config.home.url == "/"
    assert config.repos[0].description == ""


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"repos": [{"owner": "o", "name": "r"}]}, "missing required key 'title'"),
        ({"title": "t"}, "at least one [[repos]]"),
        ({"title": "t", "repos": []}, "at least one [[repos]]"),
        ({"title": "t", "repos": [{"name": "r"}]}, "missing required key 'owner'"),
        (
            {"title": "t", "repos": [{"owner": "o", "name": "r", "extra": 1}]},
            "unknown key(s) extra",
        ),
        (
            {"title": "t", "tittle": "x", "repos": [{"owner": "o", "name": "r"}]},
            "unknown key(s) tittle",
        ),
        (
            {"title": "t", "repos": [{"owner": "o", "name": "bad name"}]},
            "not a valid GitHub name",
        ),
        (
            {
                "title": "t",
                "repos": [{"owner": "a", "name": "r"}, {"owner": "b", "name": "r"}],
            },
            "used twice",
        ),
        ({"title": 3, "repos": [{"owner": "o", "name": "r"}]}, "must be a string"),
    ],
)
def test_invalid_config_raises(data: dict, message: str) -> None:
    """Invalid configurations raise ConfigError with a helpful message."""
    with pytest.raises(ConfigError) as excinfo:
        parse_config_data(data)
    assert message in str(excinfo.value)


def test_invalid_toml_raises(tmp_path: Path) -> None:
    """A file that is not valid TOML raises ConfigError naming the file."""
    path = tmp_path / "roadmap.toml"
    path.write_text("title = \n", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid TOML"):
        load_config(path)
