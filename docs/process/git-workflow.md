# Git Workflow

## Default model

FoundryGate uses a protected `main` branch and short-lived working branches.

The default flow is:

- `main` is stable and releaseable
- `feature/<topic>-<date>` is used for implementation
- `review/<topic>-<date>` is optional and used for focused review, test-hardening, or merge-preparation work
- `hotfix/<topic>-<date>` is reserved for urgent fixes that should land quickly on top of current `main`

There is no long-lived `develop` branch by default.

## Why

This repository is still small enough that a long-lived integration branch would add more coordination cost than value.

The current priorities are:

- keep `main` clean,
- keep review cycles visible,
- keep releases simple,
- avoid hidden drift between "stable" and "development" branches.

If parallel feature pressure grows substantially later, a dedicated integration branch can be introduced deliberately.

## Branch naming

Use predictable names:

- `feature/provider-capabilities-2026-03-11`
- `feature/local-worker-provider-2026-03-11`
- `review/provider-capabilities-2026-03-11`
- `hotfix/health-endpoint-regression-2026-03-11`

## Standard flow

1. Start from current `main`.
2. Create a `feature/...` branch.
3. Keep commits small and coherent.
4. Run local checks before pushing.
5. Open a PR from the feature branch into `main`.
6. Merge only when CI is green and review concerns are addressed.

## Review cadence

Every 4 or 5 merged PRs, run a broader maintenance pass in addition to normal feature reviews.

That pass should include:

- unit test review
- integration test review
- functional test review against current user workflows
- documentation review across README, roadmap, process docs, troubleshooting docs, and integration guides
- community-health and security review across code of conduct, security policy, issue templates, PR template, and GitHub security automation
- cleanup of stale assumptions, outdated examples, or renamed surfaces

This keeps the project understandable from the outside and prevents documentation drift after several fast feature PRs.

## Optional review branch flow

Use a `review/...` branch only when a second focused pass is useful.

Recommended pattern:

1. Create `review/...` from the active `feature/...` branch.
2. Use it for review-only fixes, experiments, or hardening work.
3. Cherry-pick or otherwise move the accepted fixes back onto the source feature branch.
4. Merge the reviewed feature branch into `main`.

The feature branch remains the source of truth for the PR.

## Main branch rules

- do not commit directly to `main`
- keep `main` protected
- require CI to pass before merge
- prefer linear history
- tag releases from `main`

## Release flow

Release from `main` only.

Typical sequence:

1. fast-forward local `main`
2. update `CHANGELOG.md`
3. create an annotated tag such as `v0.3.0`
4. push the tag
5. publish a GitHub Release

See [RELEASES.md](../../RELEASES.md) for release details.

## Worktree note

If you use multiple Git worktrees, remember that:

- only one worktree can own a checked-out local branch at a time
- deleting merged branches may fail until the branch is no longer checked out anywhere
- `origin/main` may advance before every worktree has been fast-forwarded locally

Keep branch cleanup explicit when multiple tools or agents share the same repository.
