# FoundryGate Releases

This repo does not require a heavy release process. Use lightweight tags plus GitHub Releases.

## Release Flow

1. Make sure `main` is green.
2. Update [CHANGELOG.md](./CHANGELOG.md):
   - Move the relevant notes from `Unreleased` into a versioned section.
   - Keep the notes focused on user-visible changes.
3. Create an annotated tag from `main`.
4. Push the tag to GitHub.
5. Create a GitHub Release from that tag.
6. Use the changelog entry as the release notes, then add any short upgrade notes if needed.

## Example

```bash
git checkout main
git pull --ff-only origin main
git tag -a v0.3.0 -m "FoundryGate v0.3.0"
git push origin v0.3.0
```

Then open GitHub Releases and publish a release for `v0.3.0`.

## Versioning Guidance

- Use `x.y.z` version numbers and matching `vx.y.z` Git tags.
- Use a patch bump for fixes, documentation polish, and small compatibility updates.
- Use a minor bump for meaningful features, provider additions, routing behavior improvements, or operational changes.
- Use a major bump only for explicit breaking changes with a documented migration path.
- Avoid promising strict semantic versioning unless the project decides to enforce it consistently.

## Current Release Baseline

- `v0.3.0` is the current target for the first FoundryGate-branded release.
- This release line is the baseline for the full FoundryGate technical naming adoption.

## What Belongs In Release Notes

- New providers or routing behavior changes
- API surface changes
- Deployment or operational changes
- Breaking changes or migration notes
- Fixes that affect request behavior, fallbacks, or observability
