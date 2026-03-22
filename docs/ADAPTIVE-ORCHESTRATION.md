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

Guardrails:

- no breaking config migration
- keep old provider-only configs valid
- do not pretend full adaptive routing already exists once lane metadata ships

## `v1.9.0`: scoring and explainability

Primary goals:

- add lane-aware scoring to the router
- let scenarios influence the lane score threshold and degrade policy
- emit richer decision traces that explain *why* one lane won

Recommended minimal slices:

1. lane-aware candidate scoring in the router
2. scenario-aware lane preference weights
3. route-decision traces with chosen lane vs chosen route
4. operator-facing "why this lane?" detail in dashboard and API traces

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
