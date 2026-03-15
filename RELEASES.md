# FoundryGate Releases

This repo does not require a heavy release process. Use lightweight tags plus GitHub Releases, with release automation building the Python package and container image from tags.

## Release Flow

1. Make sure `main` is green.
2. Update [CHANGELOG.md](./CHANGELOG.md):
   - Move the relevant notes from `Unreleased` into a versioned section.
   - Keep the notes focused on user-visible changes.
3. Create an annotated tag from `main`.
4. Push the tag to GitHub.
5. Let the release-artifacts workflow build Python distributions and the GHCR image.
6. Create a GitHub Release from that tag.
7. Use the changelog entry as the release notes, then add any short upgrade notes if needed.
8. Confirm that README plus the relevant docs pages still match the shipped runtime behavior.
9. If packaging or Docker changed shortly before the release, run the publish dry run first.
10. For hardening-heavy releases, keep the API functional tests green alongside unit and config coverage.

## Example

```bash
git checkout main
git pull --ff-only origin main
git tag -a v0.9.0 -m "FoundryGate v0.9.0"
git push origin v0.9.0
```

Then open GitHub Releases and publish a release for `v0.9.0`.

## Automation Baseline

Tagged releases now trigger [release-artifacts](./.github/workflows/release-artifacts.yml):

- always build `sdist` and `wheel`
- push the container image to GHCR
- publish to PyPI only when `PYPI_PUBLISH=true` is set and GitHub trusted publishing is configured for the `pypi` environment

The repo also includes [publish-dry-run](./.github/workflows/publish-dry-run.yml):

- build Python distributions without publishing them
- run `twine check`
- build the GHCR image without pushing it

## Versioning Guidance

- Use `x.y.z` version numbers and matching `vx.y.z` Git tags.
- Use a patch bump for fixes, documentation polish, and small compatibility updates.
- Use a minor bump for meaningful features, provider additions, routing behavior improvements, or operational changes.
- Use a major bump only for explicit breaking changes with a documented migration path.
- Avoid promising strict semantic versioning unless the project decides to enforce it consistently.

## Current Release Baseline

- `v0.3.0` is the first FoundryGate-branded release.
- `v0.4.0` establishes the hardened routing baseline: request hooks, multi-dimensional scoring, route introspection, and the refined operator dashboard.
- `v0.5.0` establishes the operator distribution baseline: image-provider contracts, Docker and GHCR packaging, PyPI workflow support, onboarding helpers, repo community standards, and cached release update checks.
- `v0.6.0` establishes the modality-expansion baseline: image route previews, provider capability coverage, shared image request validation, and image policy presets.
- `v0.7.0` establishes the operations-polish baseline: update alerts, operator events, rollout guardrails, scoped update checks, maintenance windows, and post-update verification hints.
- `v0.8.0` establishes the onboarding baseline: repeatable provider/client rollout helpers, starter templates, delegated-traffic examples, env validation, and shareable onboarding reports.
- `v0.9.0` is the pre-`v1.0` hardening baseline: conservative response headers, bounded request surfaces, stronger functional API coverage, and a full documentation pass over operator-facing behavior.

## Planned Publishing Path

- `v0.3.x`: GitHub Releases plus source checkout remain the default distribution path.
- `v0.5.0`: Docker and PyPI publishing baseline is introduced through the release workflow and repo docs.
- `v0.6.0`: modality-aware image routing becomes an explicit release line with provider inventory and image-policy guidance.
- `v0.7.0`: helper-driven update controls become a first-class release line with scoped rollout gates and verification hooks.
- `v0.8.0`: many-provider and many-client onboarding becomes copy/pasteable and validation-backed through reports, starters, and doctor checks.
- `v1.0.0`: keep GitHub Releases, Docker, and PyPI, and add a separate npm or TypeScript CLI package if the CLI surface is ready.

The npm or TypeScript package should stay separate from the Python gateway core. It is meant for CLI-facing integrations, not for rewriting the service runtime.

## Scheduled Deployment Examples

FoundryGate now includes a conservative helper-driven update path for controlled environments. The recommended examples live in:

- [docs/examples/foundrygate-auto-update.service](./docs/examples/foundrygate-auto-update.service)
- [docs/examples/foundrygate-auto-update.timer](./docs/examples/foundrygate-auto-update.timer)
- [docs/examples/foundrygate-auto-update.cron](./docs/examples/foundrygate-auto-update.cron)

Use these only after you have already validated the manual path:

```bash
./scripts/foundrygate-update-check
./scripts/foundrygate-auto-update
```

Keep `allow_major: false` unless you are intentionally allowing major-version rollouts through the scheduled helper.

## What Belongs In Release Notes

- New providers or routing behavior changes
- API surface changes
- Deployment or operational changes
- Breaking changes or migration notes
- Fixes that affect request behavior, fallbacks, or observability
