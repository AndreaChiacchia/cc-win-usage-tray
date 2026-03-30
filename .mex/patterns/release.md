---
name: release
description: Build and release a new version — version bump, exe build, git tagging, and GitHub release. Follows the merge procedure in the global CLAUDE.md.
triggers:
  - "release"
  - "bump version"
  - "build exe"
  - "publish"
  - "tag"
  - "merge to main"
edges:
  - target: context/setup.md
    condition: for build commands and prerequisites
last_updated: 2026-03-30
---

# Release

## Context

Version is tracked in `src/version.py` (`__version__ = "X.Y.Z"`). The README badge must be kept in sync. The exe is built with PyInstaller using `ClaudeUsageTray.spec`. Branch strategy: `staging` is the working branch; `main` is release-only.

## Steps

Follow the merge procedure from the global CLAUDE.md exactly:

1. **Determine SemVer level** from commits since last version bump (feat → minor, fix → patch, breaking → major). Higher level wins if mixed.
2. **Bump `src/version.py`** on `staging`.
3. **Update README badge** — `![version](https://img.shields.io/badge/version-vX.Y.Z-blue)`. Check if any other README content needs updating (new features, changed behavior).
4. Commit both changes on `staging` with a `chore: bump version to X.Y.Z` message.
5. **Push `staging`** to remote.
6. **Switch to `main`**, merge `staging`: `git checkout main && git merge staging`
7. **Push `main`**.
8. **Fast-forward `staging` from `main`**: `git checkout staging && git merge main && git push origin staging`
9. **Compile changelog** from commits since the last tag. Format:
   ```
   feat: concise summary (abc1234)
   fix: concise summary (def5678)
   ```
   List features first, then fixes, then other. Include full GitHub commit URLs where possible.
10. **Annotated tag on `main`**: `git tag -a vX.Y.Z -m "$(changelog)"` then `git push origin vX.Y.Z`
11. **Build the exe**: `cd src && pyinstaller ../ClaudeUsageTray.spec` → `dist/ClaudeUsageTray.exe`
12. **Create GitHub release**: attach `dist/ClaudeUsageTray.exe`, paste changelog as release notes.

## Gotchas

- **The spec file is `ClaudeUsageTray.spec` in the repo root** — run PyInstaller from `src/`, pointing at `../ClaudeUsageTray.spec`.
- **Python 3.10+ is required to build.** The exe bundles the Python runtime so end users don't need Python.
- **`src/version.py` is the single source of truth.** The README badge is secondary. Don't bump one without the other.
- **Tag on `main` after the merge**, not on `staging`. The tag represents the released state.

## Verify

- [ ] `src/version.py` matches the new version string
- [ ] README badge matches the new version
- [ ] Tag is on `main`, not `staging`
- [ ] `dist/ClaudeUsageTray.exe` launches without a console window
- [ ] Startup notification toast appears on first run of the new exe

## Update Scaffold

- [ ] Update `.mex/ROUTER.md` "Current Project State" with the new version
- [ ] Update any `.mex/context/` files if release process changed
