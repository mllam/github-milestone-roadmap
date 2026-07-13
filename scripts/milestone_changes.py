# /// script
# requires-python = ">=3.10"
# dependencies = ["httpx"]
# ///
"""List issues/PRs added to vX.Y.Z milestones in the last N hours.

Covers the three repos used by the mllam roadmap website.

Uses the GitHub GraphQL API: one query per repo fetches every SemVer
milestone (updated within the window) together with its issues, PRs, and
their timeline `MilestonedEvent`s. Only events created within the window
are reported.

Usage:
    uv run scripts/milestone_changes.py [--hours 24] [--token TOKEN]

Auth: set GITHUB_TOKEN in the environment (or pass --token). GraphQL
requires authentication.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import httpx

ORG = "mllam"
REPOS = ["neural-lam", "mllam-data-prep", "weather-model-graphs"]
VERSION_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
GRAPHQL_URL = "https://api.github.com/graphql"

# Fetch all milestones (open + closed), and for each their issues and PRs
# with their timeline milestoned events. Pagination is capped at first
# pages here for simplicity; we page milestones outer-loop, and inner
# connections use `first: 100` which covers all mllam milestones today.
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


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hours", type=float, default=24.0,
                   help="Look-back window in hours (default: 24).")
    p.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"),
                   help="GitHub token (default: $GITHUB_TOKEN).")
    return p.parse_args()


def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def trim_minute(ts: str) -> str:
    ts = ts.replace("+00:00", "Z")
    if len(ts) >= 17 and ts.endswith("Z"):
        return ts[:16] + "Z"
    return ts


def version_key(title: str) -> tuple[int, int, int]:
    m = VERSION_RE.match(title)
    assert m is not None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def gql(client: httpx.Client, variables: dict) -> dict:
    resp = client.post(GRAPHQL_URL, json={"query": QUERY, "variables": variables})
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


def collect(
    client: httpx.Client, repo: str, cutoff: datetime,
) -> dict[str, dict]:
    """Return {milestone_title: {"number": int, "items": {num: item}}}."""
    grouped: dict[str, dict] = {}
    cursor: str | None = None

    while True:
        data = gql(client, {"owner": ORG, "repo": repo, "cursor": cursor})
        milestones = data["repository"]["milestones"]
        stop = False

        for m in milestones["nodes"]:
            title = m["title"]
            if not VERSION_RE.match(title):
                continue
            # Milestones are ordered by updatedAt desc; once we hit one
            # older than cutoff we can stop paging.
            if parse_iso(m["updatedAt"]) < cutoff:
                stop = True
                continue

            number = m["number"]
            for coll_key in ("issues", "pullRequests"):
                for node in m[coll_key]["nodes"]:
                    # Prefilter: item's own updatedAt must be within window.
                    if parse_iso(node["updatedAt"]) < cutoff:
                        continue
                    matching = [
                        e for e in node["timelineItems"]["nodes"]
                        if e.get("__typename") == "MilestonedEvent"
                        and e.get("milestoneTitle") == title
                        and parse_iso(e["createdAt"]) >= cutoff
                    ]
                    if not matching:
                        continue
                    ev = max(matching, key=lambda e: e["createdAt"])
                    actor = ((ev.get("actor") or {}).get("login") or "unknown")
                    bucket = grouped.setdefault(
                        title, {"number": number, "items": {}},
                    )
                    bucket["items"][node["number"]] = {
                        "number": node["number"],
                        "title": (node.get("title") or "").strip(),
                        "url": node.get("url") or "",
                        "note": f"added by @{actor} at {trim_minute(ev['createdAt'])}",
                        "sort_key": ev["createdAt"],
                    }

        if stop or not milestones["pageInfo"]["hasNextPage"]:
            break
        cursor = milestones["pageInfo"]["endCursor"]

    return grouped


def format_item(item: dict) -> str:
    return f"[#{item['number']} {item['title']}]({item['url']})"


def render(
    repo_data: dict[str, dict[str, dict] | Exception], hours: float,
) -> str:
    lines: list[str] = [f"# Milestone additions in the last {hours:g}h", ""]
    total_items = 0
    repos_with_items = 0
    total_versions = 0
    empty_note = (
        "  - _no additions in the last 24h_"
        if hours == 24 else
        f"  - _no additions in the last {hours:g}h_"
    )

    for repo in REPOS:
        lines.append(f"- {repo}")
        result = repo_data.get(repo)
        if isinstance(result, Exception):
            lines.append(f"  - _error: {result}_")
            continue
        grouped = result or {}
        if not grouped:
            lines.append(empty_note)
            continue

        repos_with_items += 1
        total_versions += len(grouped)

        for title in sorted(grouped, key=version_key):
            bucket = grouped[title]
            mnum = bucket["number"]
            murl = f"https://github.com/{ORG}/{repo}/milestone/{mnum}"
            lines.append(f"  - [{title}]({murl})")
            items = sorted(bucket["items"].values(), key=lambda i: i["sort_key"])
            for item in items:
                lines.append(f"    - {format_item(item)}")
                total_items += 1

    lines.append("")
    lines.append(
        f"Summary: {total_items} items across "
        f"{repos_with_items} repos / {total_versions} versions "
        f"in the last {hours:g}h."
    )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()

    if not args.token:
        print(
            "error: GraphQL requires a token; set GITHUB_TOKEN or pass --token.",
            file=sys.stderr,
        )
        return 2

    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {args.token}",
        "User-Agent": "mllam-roadmap-milestone-changes",
    }

    repo_data: dict[str, dict[str, dict] | Exception] = {}
    had_error = False
    with httpx.Client(headers=headers, timeout=60.0) as client:
        for repo in REPOS:
            try:
                repo_data[repo] = collect(client, repo, cutoff)
            except Exception as exc:  # noqa: BLE001
                had_error = True
                repo_data[repo] = exc

    print(render(repo_data, args.hours))
    return 1 if had_error else 0


if __name__ == "__main__":
    sys.exit(main())
