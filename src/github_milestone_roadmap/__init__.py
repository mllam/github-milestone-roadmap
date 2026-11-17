"""Build a live roadmap website from GitHub release milestones."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("github-milestone-roadmap")
except PackageNotFoundError:  # pragma: no cover - only when not installed
    __version__ = "unknown"
