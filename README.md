# MLLAM Roadmap

Static GitHub Pages site for the MLLAM community roadmap.

The page queries the public GitHub API directly from the browser and shows open issues and pull requests assigned to open roadmap milestones in these repositories:

- `mllam/neural-lam`
- `mllam/mllam-data-prep`
- `mllam/weather-model-graphs`

Milestone naming controls how items are grouped:

- `vX.Y.Z` means the item is on the roadmap for that release.
- `vX.Y.Z (proposed)` means the item is proposed for that release.

Only open issues and open pull requests are displayed.

To reduce GitHub API usage, the page makes three base requests per repository: one for open milestones, one for open issues/pull requests, and one for recently closed pull requests so merged PRs can be shown. Displayed open pull requests also fetch their cached review status. Responses are cached in the browser's `localStorage` for 15 minutes, and stale cached data is used if GitHub's unauthenticated API rate limit is reached.

## Development

Open `index.html` in a browser, or serve the directory with any static file server.

For example:

```sh
python3 -m http.server 8080
```

Then visit `http://localhost:8080`.

## Deployment

The GitHub Actions workflow in `.github/workflows/pages.yml` deploys the site to GitHub Pages on pushes to `main` and can also be run manually.
