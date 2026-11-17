# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Package the mllam roadmap page as the reusable `github-milestone-roadmap`
  tool: `github-milestone-roadmap build` writes the static site for any set of
  repositories described in a TOML config, and `github-milestone-roadmap changes`
  (formerly `scripts/milestone_changes.py`) prints recent milestone additions
  for the same repositories. Repositories can come from several owners.
  [\#2](https://github.com/mllam/github-milestone-roadmap/pull/2), @leifdenby

### Changed

- The site is no longer deployed from this repository. Sites that use the tool
  build it in their own deploy workflow (mllam's roadmap is served at
  https://mllam.github.io/roadmap from the `mllam/mllam.github.io` repository).
  [\#2](https://github.com/mllam/github-milestone-roadmap/pull/2), @leifdenby
