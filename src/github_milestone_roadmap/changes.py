"""List issues/PRs added to vX.Y.Z milestones in the last N hours.

Uses the GitHub GraphQL API: one query per repo fetches every SemVer
milestone (updated within the window) together with its issues, PRs, and
their timeline ``MilestonedEvent``s. Only events created within the window
are reported. The output is Markdown with nested lists, suitable for pasting
into Slack.

GraphQL requires authentication, so a GitHub token is needed.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from .config import RepoConfig

VERSION_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
GRAPHQL_URL = "https://api.github.com/graphql"

# Fetch all milestones (open + closed), and for each their issues and PRs
# with their timeline milestoned events. Pagination is capped at first
# pages here for simplicity; we page milestones outer-loop, and inner
# connections use `first: 50`.
QUERY = """
query($owner: String!, $repo: String!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    milestones(first: 10, after: $cursor, states: [OPEN, CLOSED],
               orderBy: {field: UPDATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        title
        updatedAt
        url
        issues(first: 50, states: [OPEN, CLOSED]) {
          nodes {
            number
            title
            url
            updatedAt
            timelineItems(first: 20, itemTypes: [MILESTONED_EVENT]) {
              nodes {
                __typename
                ... on MilestonedEvent {
                  createdAt
                  milestoneTitle
                  actor { login }
                }
              }
            }
          }
        }
        pullRequests(first: 50, states: [OPEN, CLOSED, MERGED]) {
          nodes {
            number
            title
            url
            updatedAt
            timelineItems(first: 20, itemTypes: [MILESTONED_EVENT]) {
              nodes {
                __typename
                ... on MilestonedEvent {
                  createdAt
                  milestoneTitle
                  actor { login }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

# {milestone_title: {"number": int, "items": {item_number: item}}}
MilestoneAdditions = dict[str, dict[str, Any]]


def parse_iso(ts: str) -> datetime:
    """Parse a GitHub ISO-8601 timestamp.

    Parameters
    ----------
    ts : str
        Timestamp such as ``2026-01-02T03:04:05Z``.

    Returns
    -------
    datetime
        Timezone-aware datetime.
    """
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def trim_to_minute(ts: str) -> str:
    """Drop the seconds from a UTC ISO-8601 timestamp.

    Parameters
    ----------
    ts : str
        Timestamp ending in ``Z`` or ``+00:00``.

    Returns
    -------
    str
        Timestamp like ``2026-01-02T03:04Z``; other formats are returned as-is.
    """
    ts = ts.replace("+00:00", "Z")
    if len(ts) >= 17 and ts.endswith("Z"):
        return ts[:16] + "Z"
    return ts


def compute_version_key(title: str) -> tuple[int, int, int]:
    """Build a sort key from a ``vX.Y.Z`` milestone title.

    Parameters
    ----------
    title : str
        Milestone title matching ``VERSION_RE``.

    Returns
    -------
    tuple of int
        ``(major, minor, patch)``.

    Raises
    ------
    ValueError
        If the title is not a ``vX.Y.Z`` version.
    """
    match = VERSION_RE.match(title)
    if match is None:
        raise ValueError(f"not a vX.Y.Z version: {title!r}")
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def run_graphql_query(client: httpx.Client, variables: dict[str, Any]) -> dict:
    """Run ``QUERY`` against the GitHub GraphQL API.

    Parameters
    ----------
    client : httpx.Client
        Authenticated HTTP client.
    variables : dict
        Query variables (``owner``, ``repo``, ``cursor``).

    Returns
    -------
    dict
        The ``data`` part of the response.

    Raises
    ------
    httpx.HTTPStatusError
        On a non-2xx response.
    RuntimeError
        If the response contains GraphQL errors.
    """
    resp = client.post(GRAPHQL_URL, json={"query": QUERY, "variables": variables})
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


def collect_milestone_additions(
    client: httpx.Client, repo: RepoConfig, cutoff: datetime
) -> MilestoneAdditions:
    """Find issues/PRs added to ``vX.Y.Z`` milestones of a repo since ``cutoff``.

    Parameters
    ----------
    client : httpx.Client
        Authenticated HTTP client.
    repo : RepoConfig
        Repository to query.
    cutoff : datetime
        Only milestone events at or after this time are reported.

    Returns
    -------
    MilestoneAdditions
        ``{milestone_title: {"number": int, "items": {num: item}}}``.
    """
    grouped: MilestoneAdditions = {}
    cursor: str | None = None

    while True:
        data = run_graphql_query(
            client, {"owner": repo.owner, "repo": repo.name, "cursor": cursor}
        )
        milestones = data["repository"]["milestones"]
        stop = False

        for milestone in milestones["nodes"]:
            title = milestone["title"]
            if not VERSION_RE.match(title):
                continue
            # Milestones are ordered by updatedAt desc; once we hit one
            # older than cutoff we can stop paging.
            if parse_iso(milestone["updatedAt"]) < cutoff:
                stop = True
                continue

            for coll_key in ("issues", "pullRequests"):
                for node in milestone[coll_key]["nodes"]:
                    # Prefilter: item's own updatedAt must be within window.
                    if parse_iso(node["updatedAt"]) < cutoff:
                        continue
                    matching = [
                        event
                        for event in node["timelineItems"]["nodes"]
                        if event.get("__typename") == "MilestonedEvent"
                        and event.get("milestoneTitle") == title
                        and parse_iso(event["createdAt"]) >= cutoff
                    ]
                    if not matching:
                        continue
                    event = max(matching, key=lambda e: e["createdAt"])
                    actor = (event.get("actor") or {}).get("login") or "unknown"
                    bucket = grouped.setdefault(
                        title, {"number": milestone["number"], "items": {}}
                    )
                    bucket["items"][node["number"]] = {
                        "number": node["number"],
                        "title": (node.get("title") or "").strip(),
                        "url": node.get("url") or "",
                        "note": (
                            f"added by @{actor} at {trim_to_minute(event['createdAt'])}"
                        ),
                        "sort_key": event["createdAt"],
                    }

        if stop or not milestones["pageInfo"]["hasNextPage"]:
            break
        cursor = milestones["pageInfo"]["endCursor"]

    return grouped


def format_item_link(item: dict[str, Any]) -> str:
    """Format an issue/PR as a Markdown link.

    Parameters
    ----------
    item : dict
        Item with ``number``, ``title`` and ``url``.

    Returns
    -------
    str
        ``[#N title](url)``.
    """
    return f"[#{item['number']} {item['title']}]({item['url']})"


def render_changes_report(
    repos: tuple[RepoConfig, ...],
    repo_data: dict[str, MilestoneAdditions | Exception],
    hours: float,
) -> str:
    """Render the Markdown report of milestone additions.

    Parameters
    ----------
    repos : tuple of RepoConfig
        Repositories in report order.
    repo_data : dict
        Result of ``collect_milestone_additions`` per repo name, or the
        exception raised while collecting it.
    hours : float
        Look-back window, used in headings.

    Returns
    -------
    str
        Markdown report.
    """
    lines: list[str] = [f"# Milestone additions in the last {hours:g}h", ""]
    total_items = 0
    repos_with_items = 0
    total_versions = 0

    for repo in repos:
        lines.append(f"- {repo.name}")
        result = repo_data.get(repo.name)
        if isinstance(result, Exception):
            lines.append(f"  - _error: {result}_")
            continue
        grouped = result or {}
        if not grouped:
            lines.append(f"  - _no additions in the last {hours:g}h_")
            continue

        repos_with_items += 1
        total_versions += len(grouped)

        for title in sorted(grouped, key=compute_version_key):
            bucket = grouped[title]
            milestone_url = (
                f"https://github.com/{repo.owner}/{repo.name}"
                f"/milestone/{bucket['number']}"
            )
            lines.append(f"  - [{title}]({milestone_url})")
            items = sorted(bucket["items"].values(), key=lambda i: i["sort_key"])
            for item in items:
                lines.append(f"    - {format_item_link(item)}")
                total_items += 1

    lines.append("")
    lines.append(
        f"Summary: {total_items} items across "
        f"{repos_with_items} repos / {total_versions} versions "
        f"in the last {hours:g}h."
    )
    return "\n".join(lines)


def create_github_client(token: str) -> httpx.Client:
    """Create an HTTP client authenticated against the GitHub API.

    Parameters
    ----------
    token : str
        GitHub token.

    Returns
    -------
    httpx.Client
        The client; the caller is responsible for closing it.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "github-milestone-roadmap",
    }
    return httpx.Client(headers=headers, timeout=60.0)


def report_milestone_changes(
    client: httpx.Client, repos: tuple[RepoConfig, ...], hours: float
) -> tuple[str, bool]:
    """Collect milestone additions for all repos and render the report.

    Parameters
    ----------
    client : httpx.Client
        Authenticated HTTP client.
    repos : tuple of RepoConfig
        Repositories to report on.
    hours : float
        Look-back window in hours.

    Returns
    -------
    tuple of (str, bool)
        The Markdown report, and whether any repo failed.
    """
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    repo_data: dict[str, MilestoneAdditions | Exception] = {}
    had_error = False
    for repo in repos:
        try:
            repo_data[repo.name] = collect_milestone_additions(client, repo, cutoff)
        except Exception as exc:  # noqa: BLE001
            had_error = True
            repo_data[repo.name] = exc
    return render_changes_report(repos, repo_data, hours), had_error
