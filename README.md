# github-milestone-roadmap

Build a live roadmap website from GitHub release milestones across several
repositories.

The generated site is a single static page. It reads milestones, issues and
pull requests from the public GitHub API in the visitor's browser, so the
roadmap is always current without rebuilding the site. It is used for the
[mllam community roadmap](https://mllam.github.io/roadmap).

## The milestone convention

Milestone names decide where an item appears:

- `vX.Y.Z`: the item is **on the roadmap** for that release.
- `vX.Y.Z (proposed)`: the item is **proposed** for that release.

For each release the page shows three lanes: open issues/PRs on the roadmap,
open proposed issues/PRs, and pull requests already merged into the `vX.Y.Z`
milestone. Open pull requests also show their review status. Milestones with
other names are ignored.

## Usage

Write a `roadmap.toml` describing your roadmap (see
[`examples/roadmap.toml`](examples/roadmap.toml) for every option):

```toml
title = "My Community Roadmap"
subtitle = "Upcoming work across our packages"
source_url = "https://github.com/my-org"

[home]
text = "My Community"
url = "/"

[[repos]]
owner = "my-org"
name = "my-package"
description = "What this package does."
```

Then build the site:

```sh
uvx github-milestone-roadmap build --config roadmap.toml --output _site/roadmap
```

This writes `index.html`, `app.js`, `styles.css` and `config.json` to the
output directory. The page only uses relative paths, so it can be served from
any subpath.

### In a GitHub Pages workflow

Pin the version so that roadmap tool updates reach your site only when you bump
it:

```yaml
      - uses: astral-sh/setup-uv@v6
      - name: Build roadmap
        run: uvx github-milestone-roadmap==0.1.0 build --config roadmap.toml --output _site/roadmap
      - uses: actions/upload-pages-artifact@v3
        with:
          path: _site
```

See the [mllam.github.io deploy workflow](https://github.com/mllam/mllam.github.io/blob/main/.github/workflows/pages.yml)
for a complete example.

### API usage and caching

Without authentication, the GitHub API allows 60 requests per hour per
visitor. The page makes three requests per repository (open milestones, open
issues/PRs, recently closed PRs) plus one per displayed open pull request for
its review status. Responses are cached in the browser's `localStorage` for 15
minutes under the config's `cache_key`, and stale cached data is shown if the
rate limit is reached.

## Milestone changes report

`changes` prints the issues and pull requests added to a `vX.Y.Z` milestone in
the last 24 hours across the configured repositories, grouped per repository
and version. The output is Markdown with nested lists, suitable for pasting
into Slack.

It uses the GraphQL API, so a GitHub token is required. With the
[`gh`](https://cli.github.com/) CLI logged in:

```sh
uvx github-milestone-roadmap changes --config roadmap.toml --token "$(gh auth token)"
```

or set `GITHUB_TOKEN` in the environment. Use `--hours N` to change the
look-back window.

## Development

```sh
uv run pytest
uv run pre-commit install   # ruff lint and format on commit
```

To preview the page locally:

```sh
uv run github-milestone-roadmap build --config examples/roadmap.toml --output _site
python3 -m http.server --directory _site 8080
```

Then visit http://localhost:8080. The page needs `config.json` from the build,
so opening `index.html` directly from disk will not work.

## Releasing

Versions come from git tags (hatch-vcs). To release, update `CHANGELOG.md`,
merge to `main`, then tag `vX.Y.Z` on `main` and push the tag. The `release`
workflow publishes to PyPI with trusted publishing.
