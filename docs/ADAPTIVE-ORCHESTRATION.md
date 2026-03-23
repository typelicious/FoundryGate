# Adaptive Model Orchestration

## Why This Track Exists

fusionAIze Gate should not stop at "many providers behind one URL".

The real product value is higher:

- take model-choice work away from the operator and end user
- route to the strongest acceptable lane for the current task
- protect premium direct quotas when cheaper or equivalent paths are good enough
- keep quality-first scenarios on the same canonical lane for as long as possible
- degrade gracefully and explainably when quota, latency, or reliability pressure appears

This document describes the target architecture from the first `v1.8.0` lane foundation through the adaptive lines planned for `v1.9.0`, `v1.10.x`, and `v1.11.x`.

## Core Concepts

### 1. Canonical model lane

Gate should reason about the *capability lane* first, not the transport path first.

Examples:

- `anthropic/opus-4.6`
- `anthropic/sonnet-4.6`
- `anthropic/haiku-4.5`
- `google/gemini-pro-high`
- `google/gemini-pro-low`
- `google/gemini-flash`
- `openai/gpt-4o`
- `openai/gpt-4o-mini`
- `deepseek/reasoner`
- `deepseek/chat`

A canonical lane describes what the operator is really buying:

- quality profile
- reasoning depth
- speed posture
- context posture
- tool posture
- benchmark cluster

### 2. Execution route

One canonical lane may be available through several execution paths.

Examples for a future `anthropic/opus-4.6` lane:

- direct Anthropic route
- aggregator route through OpenRouter
- aggregator route through Kilo
- aggregator route through BLACKBOX

That means Gate should be able to answer two separate questions:

1. Which canonical lane is the right lane for this task?
2. Which execution route is the best current way to reach that lane?

### 3. Scenario policy

Scenarios such as `quality`, `balanced`, `eco`, and `free` should influence:

- the minimum lane quality acceptable for a task
- how expensive a same-lane route may be before a cheaper sibling lane is preferred
- how aggressively Gate should protect direct premium quotas
- how quickly Gate should degrade to a cheaper cluster

### 4. Lane cluster

Canonical lanes should be grouped into clusters for graceful degradation and substitution.

Examples:

- `elite-reasoning`
- `quality-workhorse`
- `balanced-workhorse`
- `fast-workhorse`
- `budget-general`
- `image-quality`

The cluster is what lets Gate choose a sensible second-best answer instead of a random fallback.

## Aggregator Strategy

Aggregators such as OpenRouter, Kilo, and BLACKBOX should not only be treated as "cheap/fallback providers".

They are also *alternate routes* to some canonical lanes.

### Desired behavior

For a `quality` scenario and a task that genuinely wants `anthropic/opus-4.6`:

1. choose canonical lane `anthropic/opus-4.6`
2. try the preferred route order for that lane
3. if the direct Anthropic route is quota-limited or unavailable, try a same-lane aggregator route
4. only degrade to `anthropic/sonnet-4.6` or another cluster substitute when the whole canonical lane is not viable

For a `balanced` scenario:

- the threshold for choosing `anthropic/opus-4.6` should be higher
- Gate should prefer workhorse lanes such as `anthropic/sonnet-4.6`, `openai/gpt-4o`, or `google/gemini-pro-low` more often
- same-lane aggregator routes can still be used, but the cost/latency tradeoff should be stricter

For an `eco` or `free` scenario:

- premium canonical lanes should be chosen sparingly
- workhorse, budget, and free clusters should dominate by default
- same-lane premium aggregator routes should only win when the task demands them strongly enough

## Benchmark And Cost Layer

Adaptive routing is only credible if Gate carries a real benchmark-and-cost view.

### What has to be modeled

Per canonical lane:

- quality posture
- reasoning posture
- speed posture
- context posture
- tool posture
- benchmark cluster
- benchmark freshness

Per execution route:

- route type (`direct`, `aggregator`, `wallet-router`, `local`)
- current cost class
- volatility
- quota class
- current health and recent failures
- route-specific latency pressure

### What should be kept current

The benchmark layer does not need to become a large benchmark lab immediately, but it must be curated and refreshable.

Recommended inputs:

- official provider model documentation
- internal operator observations from Gate metrics
- curated benchmark snapshots reviewed on a release cadence
- explicit freshness tracking so stale benchmark assumptions are visible

## Runtime Adaptation

The adaptive line should not only choose a lane at request start. It should also react to real pressure.

### Signals to collect

- rate-limit errors
- quota exhausted errors
- model unavailable errors
- timeout spikes
- p95 latency inflation
- fallback pressure
- repeated route retries
- spend pressure by lane, family, and scenario

### Reactions to allow

- lower one route's score temporarily
- hold a route in cooldown
- switch to another route for the same canonical lane
- switch to another canonical lane in the same cluster
- finally degrade to a lower cluster if required by the active scenario policy

### Explainability requirement

Every meaningful adaptive choice should be explainable:

- chosen canonical lane
- chosen execution route
- why the direct path was skipped or demoted
- whether this was a same-lane fallback or a cluster downgrade

## Release Roadmap

## `v1.8.0`: lane foundation

Primary goals:

- introduce canonical lane vocabulary to the runtime and docs
- add provider lane metadata to config, wizard output, and catalog surfaces
- start distinguishing canonical lanes from execution routes
- prepare scenarios and dashboards to reason in lane terms instead of only provider-tier terms

Recommended minimal slices:

1. canonical lane registry and provider-route bindings
2. optional `provider.lane` config block with validation
3. wizard/catalog exposure of canonical lane and route metadata
4. roadmap, architecture, and config docs that describe the new model clearly

Current branch status:

- done: canonical lane registry and provider-route bindings
- done: `provider.lane` config metadata with validation and normalization
- done: wizard and provider-catalog exposure of canonical lane metadata
- in progress: lane-aware scoring, same-lane-route fallback, and first dashboard/provider-detail explainability

Guardrails:

- no breaking config migration
- keep old provider-only configs valid
- do not pretend full adaptive routing already exists once lane metadata ships

### Observed `v1.8.0` smoke findings

The first live operator smoke on `v1.8.0` validated the lane vocabulary and route-preview
surfaces, but it also exposed a second track of work that must land before adaptive routing
can be trusted operationally.

What worked:

- route previews now surface `canonical_model`, `route_type`, `lane_cluster`,
  `known_routes`, and `degrade_to`
- complex coding prompts can already escalate into stronger reasoning lanes
- `/api/providers` and the shell dashboard expose live lane metadata

What did not hold up strongly enough in live execution:

- env and key handling still left room for unresolved or invalid auth values to make it
  into real provider attempts
- provider-specific path assumptions were still too generic for some aggregators
- metrics and traces still favored the *initial chosen lane* over the *actual attempted route*
- `/health` still answered the question "is the service up?" better than
  "is this gateway request-ready against real upstreams?"

That means the next line must prioritize runtime trust and observability before pushing live
adaptation harder.

## `v1.8.1`: runtime request-readiness hardening

Primary goals:

- ensure live requests fail early and clearly when env, auth, or endpoint assumptions are wrong
- move provider health closer to real request-readiness rather than basic process liveness
- reduce avoidable runtime surprises before any aggressive adaptive behavior is layered on top

Required slices:

1. env and key resolution hardening
2. provider-specific endpoint normalization
3. shallow auth and request-readiness probes
4. clearer health separation between service state and upstream readiness

### 1. Env and key resolution hardening

Gate currently expands env placeholders in config, but live smoke showed that request paths can
still encounter effectively unusable auth state.

The runtime needs stricter handling for:

- unresolved placeholder-shaped values such as `${OPENAI_API_KEY}`
- self-referential or accidentally re-saved placeholder values in `faigate.env`
- empty-but-present auth values
- provider keys that are present syntactically but clearly invalid for the target provider

Implementation expectations:

- normalize auth-related config values into one explicit runtime form before provider backends are built
- detect unresolved placeholder-shaped values as invalid runtime secrets, not usable API keys
- surface those invalid states in doctor, provider probe, and request-readiness views
- keep operator messaging concrete:
  - missing key
  - unresolved placeholder
  - key shape invalid for provider family

Relevant code surfaces:

- `faigate/config.py`
- `faigate/providers.py`
- `faigate/main.py`
- `scripts/faigate-doctor`
- `scripts/faigate-provider-probe`

### 2. Provider-specific endpoint normalization

The current `openai-compat` path assumes one generic shape:

- `GET /models`
- `POST /chat/completions`

That is too coarse for aggregators and gateway-style providers.

We need route-specific transport metadata so that a provider route can declare:

- models path
- chat-completions path
- image-generation path
- whether a `/v1` prefix is already included in `base_url`
- whether extra headers are required
- whether a probe should use `GET /models`, a lightweight `POST`, or provider-specific auth validation

The route registry should stop being capability-only metadata and start owning transport-level
differences too.

Implementation expectations:

- extend provider or route metadata with per-route path overrides
- remove provider-specific URL heuristics from scattered conditional branches
- make OpenRouter, Kilo, BLACKBOX, and similar aggregators first-class route shapes instead of
  "generic OpenAI-compatible providers with a different base URL"

Relevant code surfaces:

- `faigate/providers.py`
- `faigate/lane_registry.py`
- `faigate/wizard.py`
- `faigate/provider_catalog.py`

### 3. Shallow auth and request-readiness probes

The current health path and provider probe are still too close to "config present + service up".

We need one cheap readiness layer that can answer:

- can this provider be reached?
- does auth look accepted?
- is the configured endpoint shape plausible?
- is the configured model likely available?

This should not become a full completion request for every check, but it must be stronger than
basic `/models` reachability alone.

Recommended readiness states:

- `ready`
- `missing-key`
- `placeholder-key`
- `invalid-auth`
- `endpoint-mismatch`
- `model-unavailable`
- `quota-limited`
- `rate-limited`
- `transport-error`

Implementation expectations:

- add one request-readiness snapshot per provider or route
- expose it in `/health`, `/api/providers`, provider probe, and dashboard drilldowns
- keep the probe lightweight enough for regular operator use

Relevant code surfaces:

- `faigate/providers.py`
- `faigate/main.py`
- `faigate/dashboard.py`
- `scripts/faigate-provider-probe`

### 4. Health separation

The live smoke showed that "service healthy" is not the same as "request-ready".

Gate should surface at least four layers clearly:

- `service`: process and service manager state
- `runtime`: API reachable and config loaded
- `provider`: provider object and last known provider-health state
- `request_ready`: current live confidence that real routed requests can succeed

Operator-facing outputs should stop collapsing these into one binary health line.

Implementation expectations:

- keep `/health` compact, but add explicit readiness buckets
- update the shell dashboard and menu summary to distinguish:
  - service healthy
  - runtime healthy
  - providers healthy
  - providers request-ready

Relevant code surfaces:

- `faigate/main.py`
- `faigate/dashboard.py`
- `scripts/faigate-menu`
- `scripts/faigate-health`

## `v1.8.2`: trace and metrics hardening

Primary goals:

- make routing traces reflect the route that actually ran, not only the lane that originally won
- record same-lane fallback and cluster downgrade behavior explicitly
- make stats trustworthy enough for operator decisions and later adaptation work

### Current gap

The `v1.8.0` smoke showed that trace payloads already carry rich decision metadata, but the
persisted runtime picture is still incomplete:

- `selection_path` is not consistently recorded for real attempts
- traces lean toward the initial decision context even when later attempts differ
- stats cannot yet cleanly answer:
  - which route actually ran?
  - was this a same-lane fallback?
  - was this a cluster downgrade?
  - how many attempts did one request actually need?

### Required slices

1. persist the *actual attempted route* per attempt
2. distinguish chosen lane from executed route in traces and stats
3. record fallback semantics explicitly
4. expose that model cleanly in dashboard and API responses

### Target trace fields

Per request or per attempt, Gate should preserve:

- chosen canonical lane
- chosen execution route
- attempted routes in order
- final route
- final outcome
- `selection_path`
- `same_lane_fallback_used`
- `cluster_degrade_used`
- route penalty at decision time
- rejected or skipped route reasons where practical

Relevant code surfaces:

- `faigate/main.py`
- `faigate/metrics.py`
- `faigate/router.py`
- `faigate/dashboard.py`

## `v1.9.0`: complexity scoring and explainable lane choice

Primary goals:

- improve how Gate reads prompt complexity, especially for coding-heavy clients
- make `opencode` and similar coding clients escalate out of cheap lanes earlier and more reliably
- turn route preview from "plausible" into "operator-trustworthy"

### Current gap

`v1.8.0` can already choose better lanes for obviously complex coding prompts, but it still
misclassifies some architecture- or tradeoff-heavy requests as simple enough for cheap lanes.

This means complexity scoring still overweights:

- message brevity
- generic short-message heuristics

and underweights:

- architecture signals
- refactor and migration signals
- rollback and failure-mode reasoning
- design-tradeoff language
- code review and implementation planning language

### Required slices

1. improve request-dimension extraction before heuristic routing
2. add stronger client-aware coding complexity cues for `opencode`
3. make short-but-complex coding prompts escalate earlier
4. explain not only which lane won, but why cheaper lanes lost

Implementation expectations:

- expand heuristic dimensions beyond raw length
- use coding-specific complexity vocabularies and signal clusters
- let client and scenario posture influence the threshold for premium or reasoning lanes
- retain explainability in route preview and traces

Relevant code surfaces:

- `faigate/router.py`
- `faigate/main.py`
- `tests/test_routing.py`
- `tests/test_routing_dimensions.py`

## `v1.9.x`: health-aware operator trust surfaces

Primary goals:

- make health and routing confidence understandable to operators at a glance
- prevent a "green service" from hiding a "red request path"

Recommended slices:

1. request-readiness summary cards in dashboard
2. route-pressure and degraded-lane visibility
3. provider-family and lane-family readiness summaries
4. explicit operator hints when auth, path, or model issues dominate failures

## Why live adaptation waits

Live adaptation should become a first-class routing force only after:

- env and endpoint handling are hardened
- request-readiness is visible and trustworthy
- traces and stats describe *actual* route behavior cleanly
- complexity scoring is strong enough to pick the right canonical lane more often

Otherwise Gate risks adapting on top of noisy, misleading, or transport-layer failure causes.

## `v1.10.0`: live adaptation

Primary goals:

- move from static scoring to dynamic lane/route adaptation
- use recent failures, latency pressure, quota signals, and fallback pressure to steer live traffic

Recommended minimal slices:

1. adaptive route cooldowns
2. same-lane route fallback before cluster downgrade
3. quota and rate-limit pressure signals in runtime state
4. dashboard panels for degraded lanes and live route pressure

## `v1.10.x`: benchmark and cost hardening

Primary goals:

- keep benchmark and cost assumptions reviewable and fresh
- tighten cluster-based degradation and same-lane route substitution

Recommended minimal slices:

1. benchmark freshness metadata and review reminders
2. lane-cluster substitution rules
3. cost-pressure and budget-pressure operator hints
4. route-specific benchmark and spend snapshots in dashboard views

## `v1.11.x`: operator trust and controlled automation

Primary goals:

- make adaptive routing trustworthy enough for heavier operator reliance
- add stronger operator controls, guardrails, and long-lived budget policies

Recommended minimal slices:

1. family- or lane-level budget rails
2. operator policies for protecting premium direct quotas
3. controlled adaptive-routing feature flags and ring rollout
4. richer route simulation and dry-run tooling

## Data Model Summary

The target layered model is:

1. canonical lane
2. execution route
3. scenario policy
4. live pressure state
5. explainability trace

This is the path that turns Gate from "a configurable router" into "an adaptive, performance-led orchestration plane".
