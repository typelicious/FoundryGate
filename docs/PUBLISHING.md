# FoundryGate Publishing

## Goal

Keep release publishing boring and repeatable.

FoundryGate currently ships through:

- Git tags and GitHub Releases
- Python distributions (`sdist` and `wheel`)
- a GHCR container image

PyPI remains opt-in and only publishes when trusted publishing is configured and `PYPI_PUBLISH=true` is set at the repository level.

## Dry-Run Path

Use the dry-run path whenever packaging, Docker, or release automation changes.

### GitHub

The repo includes [publish-dry-run](../.github/workflows/publish-dry-run.yml):

- builds the Python package
- runs `twine check dist/*`
- builds the container image through `docker/build-push-action`
- does not push to GHCR
- does not publish to PyPI

### Local

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
docker build -t foundrygate:dry-run .
```

## Real Release Path

The real publish flow stays tag-driven through [release-artifacts](../.github/workflows/release-artifacts.yml):

1. cut the release PR and merge it to `main`
2. tag the release from `main`
3. push the tag
4. let `release-artifacts` build Python distributions and the GHCR image
5. publish the GitHub Release
6. optionally allow PyPI publication through trusted publishing

## Trust Boundaries

- Dry-run workflows should never require production credentials.
- Real release publication should use GitHub environments and trusted publishing instead of long-lived secrets where possible.
- PyPI publication should remain opt-in until the package workflow is stable across several releases.

## Controlled Update Scheduling

Release publishing and deployment updates should stay separate concerns.

Publishing creates a tagged release. Applying that release on a host should remain a deliberate operator action or a tightly controlled scheduled helper.

If you want scheduled update application:

- keep `auto_update.enabled: true` explicit in `config.yaml`
- keep `update_check.release_channel` on `stable` unless you intentionally want preview releases in the check path
- keep `auto_update.rollout_ring` on `stable` or `early` for normal environments; use `canary` only for faster adopters
- keep `allow_major: false` unless you are ready to absorb breaking changes automatically
- keep `require_healthy_providers: true` unless you are intentionally allowing rollouts while the gateway is degraded
- set `min_release_age_hours` above `0` if you want scheduled rollouts to wait before applying newly published releases
- prefer the reviewed examples in [examples/foundrygate-auto-update.service](./examples/foundrygate-auto-update.service) and [examples/foundrygate-auto-update.timer](./examples/foundrygate-auto-update.timer)
- use the cron example in [examples/foundrygate-auto-update.cron](./examples/foundrygate-auto-update.cron) only when `systemd` timers are not practical

The helper still calls the normal update command. It does not bypass your service restart, health checks, or update guardrails.
