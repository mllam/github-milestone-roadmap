"""Command-line interface: ``github-milestone-roadmap build|changes``."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .build import build_site
from .changes import create_github_client, report_milestone_changes
from .config import ConfigError, load_config


def build_arg_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the CLI.

    Returns
    -------
    argparse.ArgumentParser
        Parser with the ``build`` and ``changes`` subcommands.
    """
    parser = argparse.ArgumentParser(
        prog="github-milestone-roadmap",
        description="Build a live roadmap website from GitHub release milestones.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser(
        "build", help="Write the static roadmap site to a directory."
    )
    build.add_argument(
        "--config",
        type=Path,
        default=Path("roadmap.toml"),
        help="Roadmap config file (default: roadmap.toml).",
    )
    build.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Directory to write the site to (created if missing).",
    )

    changes = subparsers.add_parser(
        "changes",
        help="Print a Markdown list of issues/PRs recently added to vX.Y.Z milestones.",
    )
    changes.add_argument(
        "--config",
        type=Path,
        default=Path("roadmap.toml"),
        help="Roadmap config file (default: roadmap.toml).",
    )
    changes.add_argument(
        "--hours",
        type=float,
        default=24.0,
        help="Look-back window in hours (default: 24).",
    )
    changes.add_argument(
        "--token",
        default=os.environ.get("GITHUB_TOKEN"),
        help="GitHub token (default: $GITHUB_TOKEN).",
    )
    return parser


def run_build_command(args: argparse.Namespace) -> int:
    """Run the ``build`` subcommand.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed arguments.

    Returns
    -------
    int
        Exit code.
    """
    config = load_config(args.config)
    written = build_site(config, args.output)
    print(
        f"github-milestone-roadmap {__version__}: wrote {len(written)} files "
        f"to {args.output}",
        file=sys.stderr,
    )
    return 0


def run_changes_command(args: argparse.Namespace) -> int:
    """Run the ``changes`` subcommand.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed arguments.

    Returns
    -------
    int
        Exit code: 0 on success, 1 if any repo failed, 2 without a token.
    """
    if not args.token:
        print(
            "error: GraphQL requires a token; set GITHUB_TOKEN or pass --token.",
            file=sys.stderr,
        )
        return 2
    config = load_config(args.config)
    with create_github_client(args.token) as client:
        report, had_error = report_milestone_changes(client, config.repos, args.hours)
    print(report)
    return 1 if had_error else 0


def main(argv: list[str] | None = None) -> int:
    """Run the CLI.

    Parameters
    ----------
    argv : list of str or None
        Arguments without the program name; ``None`` uses ``sys.argv``.

    Returns
    -------
    int
        Exit code.
    """
    args = build_arg_parser().parse_args(argv)
    try:
        if args.command == "build":
            return run_build_command(args)
        return run_changes_command(args)
    except (ConfigError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
