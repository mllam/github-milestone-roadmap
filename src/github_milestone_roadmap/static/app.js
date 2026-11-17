const API_ROOT = "https://api.github.com";
const CACHE_TTL_MS = 15 * 60 * 1000;

// Filled from config.json, which `github-milestone-roadmap build` writes next to this file.
let CACHE_PREFIX = "roadmap:";
let REPOS = [];

const roadmapEl = document.querySelector("#roadmap");

if ("scrollRestoration" in history) {
  history.scrollRestoration = "manual";
}

loadRoadmap();

async function loadRoadmap() {
  try {
    const config = await loadConfig();
    CACHE_PREFIX = `${config.cache_key}:`;
    REPOS = config.repos;
  } catch (error) {
    const message = document.createElement("p");
    message.className = "empty";
    message.textContent = `Could not load the roadmap configuration (config.json): ${apiErrorMessage(error)}`;
    roadmapEl.replaceChildren(message);
    return;
  }

  renderRoadmap(REPOS.map((repo) => ({ ...repo, loading: true, releases: [] })));
  REPOS.forEach((repo) => refreshPackage(repo.name));

  if (!location.hash) {
    window.scrollTo({ top: 0, left: 0 });
  }
}

async function loadConfig() {
  const response = await fetch("config.json", { cache: "no-cache" });
  if (!response.ok) {
    throw new Error(`request failed with ${response.status} ${response.statusText}`);
  }
  return response.json();
}

function repoUrl(repo) {
  return `https://github.com/${repo.owner}/${repo.name}`;
}

async function refreshPackage(repoName, options = {}) {
  const repo = REPOS.find((item) => item.name === repoName);
  if (!repo) return;

  replacePackageCard({ ...repo, loading: true, releases: [] });
  const pkg = await loadPackageRoadmap(repo, options);
  replacePackageCard(pkg);
}

async function loadPackageRoadmap(repo, options = {}) {
  try {
    const [milestones, items, closedPulls] = await Promise.all([
      githubJson(`/repos/${repo.owner}/${repo.name}/milestones?state=open&per_page=100`, options),
      githubJson(`/repos/${repo.owner}/${repo.name}/issues?state=open&per_page=100`, options),
      githubJson(`/repos/${repo.owner}/${repo.name}/pulls?state=closed&sort=updated&direction=desc&per_page=100`, options),
    ]);
    const releases = groupMilestonesByRelease(milestones);
    const itemsByMilestone = groupItemsByMilestone(items);
    const mergedPullsByMilestone = groupMergedPullsByMilestone(closedPulls);

    for (const release of releases) {
      release.roadmap = itemsForMilestone(itemsByMilestone, release.roadmapMilestone);
      release.proposed = itemsForMilestone(itemsByMilestone, release.proposedMilestone);
      release.merged = mergedPullsForMilestone(mergedPullsByMilestone, release.roadmapMilestone);
    }

    await addReviewStatuses(repo, releases, options);

    return {
      ...repo,
      url: repoUrl(repo),
      releases: releases.filter((release) => release.roadmap.length > 0 || release.proposed.length > 0 || release.merged.length > 0),
    };
  } catch (error) {
    return {
      ...repo,
      url: repoUrl(repo),
      error: apiErrorMessage(error),
      releases: [],
    };
  }
}

function groupMilestonesByRelease(milestones) {
  const byVersion = new Map();

  for (const milestone of milestones) {
    const match = milestone.title.trim().match(/^(v?\d+\.\d+\.\d+)(?:\s*\(proposed\))?$/i);
    if (!match) continue;

    const version = normalizeVersion(match[1]);
    const proposed = /\(proposed\)$/i.test(milestone.title.trim());

    if (!byVersion.has(version)) {
      byVersion.set(version, {
        version,
        roadmapMilestone: null,
        proposedMilestone: null,
        roadmap: [],
        proposed: [],
        merged: [],
      });
    }

    const release = byVersion.get(version);
    if (proposed) {
      release.proposedMilestone = milestone;
    } else {
      release.roadmapMilestone = milestone;
    }
  }

  return [...byVersion.values()].sort((a, b) => compareVersions(a.version, b.version));
}

function groupItemsByMilestone(items) {
  const byMilestone = new Map();

  for (const item of items) {
    if (!item.milestone) continue;
    const existing = byMilestone.get(item.milestone.number) || [];
    existing.push(item);
    byMilestone.set(item.milestone.number, existing);
  }

  return byMilestone;
}

function groupMergedPullsByMilestone(pulls) {
  const byMilestone = new Map();

  for (const pull of pulls) {
    if (!pull.merged_at || !pull.milestone) continue;
    const existing = byMilestone.get(pull.milestone.number) || [];
    existing.push(pull);
    byMilestone.set(pull.milestone.number, existing);
  }

  return byMilestone;
}

function itemsForMilestone(itemsByMilestone, milestone) {
  if (!milestone) return [];

  return (itemsByMilestone.get(milestone.number) || [])
    .map((item) => ({
      title: item.title,
      number: item.number,
      url: item.html_url,
      type: item.pull_request ? "pr" : "issue",
      reviewStatus: null,
      labels: item.labels.map((label) => label.name),
      author: item.user?.login || null,
      assignees: item.assignees.map((assignee) => assignee.login),
      updatedAt: item.updated_at,
    }))
    .sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt));
}

function mergedPullsForMilestone(pullsByMilestone, milestone) {
  if (!milestone) return [];

  return (pullsByMilestone.get(milestone.number) || [])
    .map((pull) => ({
      title: pull.title,
      number: pull.number,
      url: pull.html_url,
      type: "pr",
      reviewStatus: null,
      labels: (pull.labels || []).map((label) => label.name),
      author: pull.user?.login || null,
      assignees: (pull.assignees || []).map((assignee) => assignee.login),
      updatedAt: pull.updated_at,
      mergedAt: pull.merged_at,
    }))
    .sort((a, b) => new Date(b.mergedAt) - new Date(a.mergedAt));
}

async function addReviewStatuses(repo, releases, options = {}) {
  const pullRequests = releases.flatMap((release) => [
    ...release.roadmap.filter((item) => item.type === "pr"),
    ...release.proposed.filter((item) => item.type === "pr"),
  ]);

  await Promise.all(pullRequests.map(async (item) => {
    try {
      const reviews = await githubJson(`/repos/${repo.owner}/${repo.name}/pulls/${item.number}/reviews?per_page=100`, options);
      item.reviewStatus = reviewStatusFromReviews(reviews);
    } catch {
      item.reviewStatus = null;
    }
  }));
}

function reviewStatusFromReviews(reviews) {
  const latestByReviewer = new Map();

  for (const review of reviews) {
    if (!review.user?.login || !review.submitted_at) continue;
    latestByReviewer.set(review.user.login, review.state);
  }

  const states = [...latestByReviewer.values()];
  if (states.includes("CHANGES_REQUESTED")) {
    return { type: "changes", text: "🔴 Changes requested" };
  }

  if (states.includes("APPROVED")) {
    return { type: "approved", text: "🟢 Approved" };
  }

  return { type: "review", text: "🟡 Review required" };
}

async function githubJson(path, options = {}) {
  const cached = readCache(path);
  if (!options.forceRefresh && cached && Date.now() - cached.savedAt < CACHE_TTL_MS) {
    return cached.data;
  }

  const response = await fetch(`${API_ROOT}${path}`, {
    headers: {
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
  });

  if (!response.ok) {
    const remaining = response.headers.get("x-ratelimit-remaining");
    const reset = response.headers.get("x-ratelimit-reset");
    if (response.status === 403 && remaining === "0" && cached) {
      return cached.data;
    }

    const message = response.status === 403 && remaining === "0"
      ? `GitHub API rate limit reached. Try again after ${formatResetTime(reset)}.`
      : `GitHub API request failed with ${response.status} ${response.statusText}.`;
    throw new Error(message);
  }

  const data = await response.json();
  writeCache(path, data);
  return data;
}

function readCache(path) {
  try {
    const value = localStorage.getItem(`${CACHE_PREFIX}${path}`);
    return value ? JSON.parse(value) : null;
  } catch {
    return null;
  }
}

function writeCache(path, data) {
  try {
    localStorage.setItem(`${CACHE_PREFIX}${path}`, JSON.stringify({ savedAt: Date.now(), data }));
  } catch {
    // Ignore full or unavailable storage; the live API response is still usable.
  }
}

function renderRoadmap(packages) {
  const fragment = document.createDocumentFragment();

  for (const pkg of packages) {
    fragment.appendChild(renderPackage(pkg));
  }

  roadmapEl.replaceChildren(fragment);
}

function replacePackageCard(pkg) {
  const current = roadmapEl.querySelector(`[data-repo="${pkg.name}"]`);
  const next = renderPackage(pkg);

  if (current) {
    current.replaceWith(next);
  } else {
    roadmapEl.appendChild(next);
  }
}

function renderPackage(pkg) {
  const article = document.createElement("article");
  article.className = `package-card${pkg.error ? " error" : ""}`;
  article.dataset.repo = pkg.name;
  article.id = pkg.name;

  const header = document.createElement("header");
  header.className = "package-header";

  const headingGroup = document.createElement("div");
  const heading = document.createElement("h2");
  heading.textContent = pkg.name;
  const description = document.createElement("p");
  description.textContent = packageStatusText(pkg);
  headingGroup.append(heading, description);

  const actions = document.createElement("div");
  actions.className = "package-actions";

  const link = document.createElement("a");
  link.className = "repo-link";
  link.href = pkg.url || repoUrl(pkg);
  link.rel = "noreferrer";
  link.textContent = "View repo";

  const reload = document.createElement("button");
  reload.className = "reload-button";
  reload.type = "button";
  reload.setAttribute("aria-label", pkg.loading ? `Reloading ${pkg.name}` : `Reload ${pkg.name}`);
  reload.disabled = Boolean(pkg.loading);
  reload.addEventListener("click", () => refreshPackage(pkg.name, { forceRefresh: true }));

  const reloadIcon = document.createElement("span");
  reloadIcon.className = "reload-icon";
  reloadIcon.setAttribute("aria-hidden", "true");
  reloadIcon.textContent = "↻";

  const reloadText = document.createElement("span");
  reloadText.textContent = pkg.loading ? "Loading" : "Reload";
  reload.append(reloadIcon, reloadText);

  actions.append(link, reload);

  header.append(headingGroup, actions);
  article.appendChild(header);

  const releaseList = document.createElement("div");
  releaseList.className = "release-list";

  if (pkg.loading) {
    const loading = document.createElement("p");
    loading.className = "empty";
    loading.textContent = "Fetching open milestones, issues, and pull requests from GitHub.";
    releaseList.appendChild(loading);
  } else if (pkg.releases.length === 0 && !pkg.error) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "No open roadmap items found.";
    releaseList.appendChild(empty);
  }

  if (!pkg.loading && pkg.releases.length > 0) {
    releaseList.appendChild(renderReleaseNav(pkg));
  }

  for (const release of pkg.releases) {
    releaseList.appendChild(renderRelease(pkg.name, release));
  }

  article.appendChild(releaseList);
  return article;
}

function packageStatusText(pkg) {
  if (pkg.loading) return "Loading open roadmap items from GitHub.";
  if (pkg.error) return pkg.error;
  return pkg.description;
}

function renderReleaseNav(pkg) {
  const nav = document.createElement("nav");
  nav.className = "release-nav";
  nav.setAttribute("aria-label", `${pkg.name} planned releases`);

  const label = document.createElement("span");
  label.textContent = "Jump to release";
  nav.appendChild(label);

  for (const release of pkg.releases) {
    const link = document.createElement("a");
    link.href = `#${releaseId(pkg.name, release.version)}`;
    link.textContent = release.version;
    nav.appendChild(link);
  }

  return nav;
}

function renderRelease(repoName, release) {
  const section = document.createElement("section");
  section.className = "release-row";
  const id = releaseId(repoName, release.version);
  section.id = id;

  const heading = document.createElement("div");
  heading.className = "release-label";

  const title = document.createElement("h3");
  title.textContent = release.version;

  const counts = document.createElement("div");
  counts.className = "release-counts";
  counts.append(
    renderReleaseCount(`🗺️ ${release.roadmap.length} on roadmap`, `${id}-roadmap`),
    renderReleaseCount(`💡 ${release.proposed.length} proposed`, `${id}-proposed`),
    renderReleaseCount(`✅ ${release.merged.length} merged`, `${id}-merged`),
  );

  heading.append(title, counts);

  const grid = document.createElement("div");
  grid.className = "release-grid";
  grid.append(
    renderLane("🗺️ On roadmap", release.roadmap, release.roadmapMilestone, "No open items.", `${id}-roadmap`),
    renderLane("💡 Proposed", release.proposed, release.proposedMilestone, "No open items.", `${id}-proposed`),
    renderLane("✅ Merged", release.merged, release.roadmapMilestone, "No merged PRs.", `${id}-merged`),
  );

  section.append(heading, grid);
  return section;
}

function renderReleaseCount(text, targetId) {
  const count = document.createElement("a");
  count.className = "release-count";
  count.href = `#${targetId}`;
  count.textContent = text;

  return count;
}

function releaseId(repoName, version) {
  return `${repoName}-${version}`.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function renderLane(title, items, milestone, emptyText, id) {
  const lane = document.createElement("section");
  lane.className = "lane";
  lane.id = id;

  const heading = document.createElement("h4");
  const label = milestone?.html_url ? document.createElement("a") : document.createElement("span");
  label.textContent = title;
  if (milestone?.html_url) {
    label.className = "milestone-link";
    label.href = milestone.html_url;
    label.rel = "noreferrer";
  }
  const count = document.createElement("span");
  count.className = "count";
  count.textContent = items.length;
  heading.append(label, count);
  lane.appendChild(heading);

  if (items.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = emptyText;
    lane.appendChild(empty);
    return lane;
  }

  const list = document.createElement("ul");
  list.className = "item-list";
  for (const item of items) {
    list.appendChild(renderItem(item));
  }
  lane.appendChild(list);
  return lane;
}

function renderItem(item) {
  const row = document.createElement("li");
  row.className = "item";

  const titleRow = document.createElement("div");
  titleRow.className = "item-title-row";

  const link = document.createElement("a");
  link.className = "item-title";
  link.href = item.url;
  link.rel = "noreferrer";
  link.textContent = item.title;

  const number = document.createElement("a");
  number.className = "item-number";
  number.href = item.url;
  number.rel = "noreferrer";
  number.textContent = `#${item.number}`;

  const itemActions = document.createElement("div");
  itemActions.className = "item-actions";

  if (item.reviewStatus) {
    const status = document.createElement("span");
    status.className = `review-status ${item.reviewStatus.type}`;
    status.textContent = item.reviewStatus.text;
    itemActions.appendChild(status);
  }

  itemActions.appendChild(number);
  titleRow.append(link, itemActions);
  row.appendChild(titleRow);

  const footer = document.createElement("div");
  footer.className = "item-footer";

  const labels = document.createElement("div");
  labels.className = "labels";
  if (item.labels.length > 0) {
    for (const labelText of item.labels) {
      const label = document.createElement("span");
      label.className = "pill";
      label.textContent = labelText;
      labels.appendChild(label);
    }
  }

  const people = document.createElement("div");
  people.className = "people";
  for (const personInfo of itemPeople(item)) {
    const person = document.createElement("span");
    person.className = `person ${personInfo.type}`;
    person.textContent = personInfo.text;
    people.appendChild(person);
  }

  if (labels.children.length > 0 || people.children.length > 0) {
    footer.append(labels, people);
    row.appendChild(footer);
  }

  return row;
}

function itemPeople(item) {
  const people = [];

  if (item.type === "pr" && item.author) {
    people.push({ type: "owner", text: `👤 Owner @${item.author}` });
  }

  for (const assignee of item.assignees) {
    people.push({ type: "assignee", text: `🛠️ Assignee @${assignee}` });
  }

  return people;
}

function normalizeVersion(version) {
  return version.startsWith("v") ? version : `v${version}`;
}

function compareVersions(a, b) {
  const left = a.replace(/^v/i, "").split(".").map(Number);
  const right = b.replace(/^v/i, "").split(".").map(Number);

  for (let index = 0; index < Math.max(left.length, right.length); index += 1) {
    const diff = (left[index] || 0) - (right[index] || 0);
    if (diff !== 0) return diff;
  }

  return 0;
}

function apiErrorMessage(error) {
  return error instanceof Error ? error.message : "An unknown error occurred.";
}

function formatResetTime(resetSeconds) {
  if (!resetSeconds) return "the rate limit resets";
  return new Date(Number(resetSeconds) * 1000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}
