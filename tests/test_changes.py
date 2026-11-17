"""Tests for the milestone changes report (no network access)."""

from datetime import UTC, datetime

import httpx
import pytest

from github_milestone_roadmap.changes import (
    collect_milestone_additions,
    compute_version_key,
    render_changes_report,
    trim_to_minute,
)
from github_milestone_roadmap.config import RepoConfig

REPOS = (RepoConfig("org", "alpha"), RepoConfig("org", "beta"))
CUTOFF = datetime(2026, 1, 1, tzinfo=UTC)


def build_item_node(
    number: int, updated_at: str, events: list[dict], title: str = "Item"
) -> dict:
    """Build a fake GraphQL issue/PR node.

    Parameters
    ----------
    number : int
        Issue/PR number.
    updated_at : str
        ``updatedAt`` timestamp.
    events : list of dict
        Timeline events.
    title : str
        Issue/PR title.

    Returns
    -------
    dict
        The node.
    """
    return {
        "number": number,
        "title": f" {title} ",
        "url": f"https://github.com/org/alpha/issues/{number}",
        "updatedAt": updated_at,
        "timelineItems": {"nodes": events},
    }


def build_milestoned_event(title: str, created_at: str, actor: str = "bob") -> dict:
    """Build a fake ``MilestonedEvent``.

    Parameters
    ----------
    title : str
        Milestone title.
    created_at : str
        Event timestamp.
    actor : str
        Login of the user who set the milestone.

    Returns
    -------
    dict
        The event.
    """
    return {
        "__typename": "MilestonedEvent",
        "createdAt": created_at,
        "milestoneTitle": title,
        "actor": {"login": actor},
    }


def build_graphql_response() -> dict:
    """Build a fake GraphQL response with one recent and one old milestone.

    Returns
    -------
    dict
        Response body.
    """
    recent = "2026-01-02T10:00:00Z"
    old = "2025-12-01T10:00:00Z"
    return {
        "data": {
            "repository": {
                "milestones": {
                    "pageInfo": {"hasNextPage": True, "endCursor": "c1"},
                    "nodes": [
                        {
                            "number": 3,
                            "title": "v1.0.0",
                            "updatedAt": recent,
                            "url": "",
                            "issues": {
                                "nodes": [
                                    build_item_node(
                                        1,
                                        recent,
                                        [build_milestoned_event("v1.0.0", recent)],
                                    ),
                                    # Milestoned before the cutoff: ignored.
                                    build_item_node(
                                        2,
                                        recent,
                                        [build_milestoned_event("v1.0.0", old)],
                                    ),
                                ]
                            },
                            "pullRequests": {
                                "nodes": [
                                    build_item_node(
                                        5,
                                        recent,
                                        [build_milestoned_event("v1.0.0", recent)],
                                        title="PR",
                                    )
                                ]
                            },
                        },
                        {
                            "number": 9,
                            "title": "v1.0.0 (proposed)",
                            "updatedAt": recent,
                            "url": "",
                            "issues": {"nodes": []},
                            "pullRequests": {"nodes": []},
                        },
                        {
                            "number": 1,
                            "title": "v0.9.0",
                            "updatedAt": old,
                            "url": "",
                            "issues": {"nodes": []},
                            "pullRequests": {"nodes": []},
                        },
                    ],
                }
            }
        }
    }


def test_collect_milestone_additions() -> None:
    """Only recent additions to vX.Y.Z milestones are collected; paging stops."""
    requests: list[httpx.Request] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=build_graphql_response())

    client = httpx.Client(transport=httpx.MockTransport(handle_request))
    grouped = collect_milestone_additions(client, REPOS[0], CUTOFF)

    assert len(requests) == 1  # the old milestone stops paging
    assert list(grouped) == ["v1.0.0"]
    assert grouped["v1.0.0"]["number"] == 3
    items = grouped["v1.0.0"]["items"]
    assert sorted(items) == [1, 5]
    assert items[1]["title"] == "Item"
    assert items[1]["note"] == "added by @bob at 2026-01-02T10:00Z"


def test_render_changes_report() -> None:
    """The report lists versions in SemVer order, errors and empty repos."""
    item = {"number": 1, "title": "Fix", "url": "https://x/1", "sort_key": "a"}
    repo_data = {
        "alpha": {
            "v1.10.0": {"number": 4, "items": {1: item}},
            "v1.2.0": {"number": 2, "items": {1: item}},
        },
        "beta": RuntimeError("boom"),
    }
    report = render_changes_report(REPOS, repo_data, 24)
    assert report.splitlines() == [
        "# Milestone additions in the last 24h",
        "",
        "- alpha",
        "  - [v1.2.0](https://github.com/org/alpha/milestone/2)",
        "    - [#1 Fix](https://x/1)",
        "  - [v1.10.0](https://github.com/org/alpha/milestone/4)",
        "    - [#1 Fix](https://x/1)",
        "- beta",
        "  - _error: boom_",
        "",
        "Summary: 2 items across 1 repos / 2 versions in the last 24h.",
    ]


def test_render_changes_report_empty() -> None:
    """Repos without additions get a placeholder line using the window length."""
    report = render_changes_report(REPOS[:1], {"alpha": {}}, 6)
    assert "  - _no additions in the last 6h_" in report


def test_compute_version_key() -> None:
    """Version keys sort numerically and reject non-versions."""
    assert compute_version_key("v1.10.2") == (1, 10, 2)
    with pytest.raises(ValueError):
        compute_version_key("v1.0.0 (proposed)")


def test_trim_to_minute() -> None:
    """Seconds are dropped from UTC timestamps."""
    assert trim_to_minute("2026-01-02T03:04:05Z") == "2026-01-02T03:04Z"
    assert trim_to_minute("2026-01-02T03:04:05+00:00") == "2026-01-02T03:04Z"
