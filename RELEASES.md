# fusionAIze Gate Releases

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
11. If the Homebrew formula changed, bump [`Formula/faigate.rb`](./Formula/faigate.rb) to the new release tag and update its `sha256`.

## Example

```bash
git checkout main
git pull --ff-only origin main
git tag -a v1.4.5 -m "fusionAIze Gate v1.4.5"
git push origin v1.4.5
```

Then open GitHub Releases and publish a release for `v1.4.5`.

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

- `v0.3.0` is the first fusionAIze Gate-branded release.
- `v0.4.0` establishes the hardened routing baseline: request hooks, multi-dimensional scoring, route introspection, and the refined operator dashboard.
- `v0.5.0` establishes the operator distribution baseline: image-provider contracts, Docker and GHCR packaging, PyPI workflow support, onboarding helpers, repo community standards, and cached release update checks.
- `v0.6.0` establishes the modality-expansion baseline: image route previews, provider capability coverage, shared image request validation, and image policy presets.
- `v0.7.0` establishes the operations-polish baseline: update alerts, operator events, rollout guardrails, scoped update checks, maintenance windows, and post-update verification hints.
- `v0.8.0` establishes the onboarding baseline: repeatable provider/client rollout helpers, starter templates, delegated-traffic examples, env validation, and shareable onboarding reports.
- `v0.9.0` is the pre-`v1.0` hardening baseline: conservative response headers, bounded request surfaces, stronger functional API coverage, and a full documentation pass over operator-facing behavior.
- `v1.0.0` establishes the stable baseline: trust-boundary validation for upstream base URLs, sanitized provider-error responses, a documented security review, and the separate `@faigate/cli` npm package for CLI-facing workflows.
- `v1.1.0` deepens post-1.0 adoption: wider AI-native starter coverage, tighter policy semantics, richer client highlights in stats/dashboard, and cleaner onboarding guidance for popular agent frameworks.
- `v1.2.0` establishes the workstation and packaging baseline: Linux/macOS/Windows workstation guidance, macOS-aware runtime helpers, Windows startup examples, explicit config-path support for packaged installs, and a project-owned Homebrew formula path.
- `v1.2.1` is the first packaging follow-up on top of that baseline: the Homebrew formula now prefers `python@3.12` for a cleaner macOS install path and the docs now explicitly cover unqualified `brew install faigate` after tapping the project-owned tap.
- `v1.2.2` hardens the macOS packaging path further: the Homebrew formula now builds `pydantic-core` from source with explicit header padding, validates the wrapped binary in its formula test, and documents how virtualenvs can shadow the Brew-installed CLI.
- `v1.2.3` finishes the immediate Brew runtime stabilization pass: the Brew-managed wrapper now invokes the correct Python module entrypoint and the formula also builds `watchfiles` from source to avoid the next macOS linkage fixup failure.
- `v1.3.0` establishes the guided setup and catalog-assisted discovery baseline: routing modes and shortcuts are first-class, the config wizard can suggest, diff, apply, and back up multi-provider changes, provider-catalog drift alerts are richer, and discovery views stay explicitly performance-led and link-neutral.
- `v1.4.0` establishes the rebrand baseline: the product name is now `fusionAIze Gate`, the technical slug is `faigate`, and package, script, service, documentation, and repository references align with the new identity.
- `v1.4.5` establishes the first Gate-native shell control-center baseline: operators now get one consistent menu for status, configure, clients, validation, control, and update flows, with client quickstarts, structured configure paths, and stronger service-control helpers.

## Planned Publishing Path

- `v0.3.x`: GitHub Releases plus source checkout remain the default distribution path.
- `v0.5.0`: Docker and PyPI publishing baseline is introduced through the release workflow and repo docs.
- `v0.6.0`: modality-aware image routing becomes an explicit release line with provider inventory and image-policy guidance.
- `v0.7.0`: helper-driven update controls become a first-class release line with scoped rollout gates and verification hooks.
- `v0.8.0`: many-provider and many-client onboarding becomes copy/pasteable and validation-backed through reports, starters, and doctor checks.
- `v1.0.0`: keep GitHub Releases, Docker, and PyPI, and add the separate npm CLI package under `packages/faigate-cli`.
- `v1.2.0`: add the project-owned Homebrew packaging path for macOS workstations while keeping Docker, GitHub Releases, Python artifacts, and the separate npm CLI package.
- `v1.2.1`: harden the Homebrew path with a more stable Python baseline and clearer tap/install guidance for macOS users.
- `v1.2.2`: finish the first macOS packaging hardening pass by targeting the `pydantic-core` linkage warning directly and tightening the wrapper-level install checks.
- `v1.2.3`: complete the immediate Brew-runtime stabilization work by fixing the packaged entrypoint path and broadening the native-wheel source-build policy on macOS.
- `v1.3.0`: deepen guided onboarding and catalog-assisted operations with purpose-aware routing modes, config-wizard update flows, provider-catalog drift checks, and compact provider-discovery surfaces.
- `v1.4.0`: ship the first fully rebranded release under `fusionAIze/faigate` so operators can adopt the new naming without mixed package, script, or documentation surfaces.
- `v1.4.5`: ship the first cohesive shell UX line for standalone Gate operation, then follow with the actual Homebrew formula bump once the release tag exists.

The npm package stays separate from the Python gateway core. It is meant for CLI-facing integrations, not for rewriting the service runtime.

`v1.2.0` started the project-owned Homebrew path through [`Formula/faigate.rb`](./Formula/faigate.rb), intended for a dedicated tap or direct tap-by-URL workflow on macOS.

## Scheduled Deployment Examples

fusionAIze Gate now includes a conservative helper-driven update path for controlled environments. The recommended examples live in:

- [docs/examples/faigate-auto-update.service](./docs/examples/faigate-auto-update.service)
- [docs/examples/faigate-auto-update.timer](./docs/examples/faigate-auto-update.timer)
- [docs/examples/faigate-auto-update.cron](./docs/examples/faigate-auto-update.cron)

Use these only after you have already validated the manual path:

```bash
./scripts/faigate-update-check
./scripts/faigate-auto-update
```

Keep `allow_major: false` unless you are intentionally allowing major-version rollouts through the scheduled helper.

## What Belongs In Release Notes

- New providers or routing behavior changes
- API surface changes
- Deployment or operational changes
- Breaking changes or migration notes
- Fixes that affect request behavior, fallbacks, or observability
