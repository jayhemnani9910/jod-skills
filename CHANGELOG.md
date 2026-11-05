# Changelog

All notable changes to this project are written down here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The plugin manifests are at version 0.1.0. No release is tagged yet.

## [Unreleased]

### Added

- Offline tests for the manifests, audit setup, the Hacker News tagger, the
  GitHub trending parser and oss-status (with a fake `gh`).
- CI: ruff, shellcheck, the tests, a bundle sync check and
  `claude plugin validate`.
- `.env.example` listing every optional setting.
- Demo GIF, CONTRIBUTING.md, issue and PR templates.

### Changed

- The audit skill's `package.json` now says MIT, matching the repo.

### Removed

- An unused variable in `oss-status/fetch.sh`.

## 2026-10-07

### Fixed

- audit: pack pages are cut the same way on every page, so no chunk is skipped.
- audit: files graphify cannot parse now go into a module.
- audit: resume is keyed by the files read, not the community id.
- audit: the static server in `browse.js` stays inside the project folder.
- oss-status: every open item shows; the date window only limits closed ones.
- oss-status: commit statuses no longer print `null=null`.
- oss-status: age in days works with BSD `date`.
- hn-daily: one bad item no longer kills the fallback list.
- github-daily: `--file` paths are quoted.

## 2026-09-12

### Added

- The jod-skills marketplace with four skills: audit, hn-daily, github-daily
  and oss-status, each as its own plugin and all four as one bundle.
