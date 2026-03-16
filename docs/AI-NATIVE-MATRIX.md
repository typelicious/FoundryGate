# FoundryGate AI-Native Client Matrix

This page tracks the post-`v1.0` client-expansion line for FoundryGate.

The goal is not to add endless one-off integrations. The goal is to identify which AI-native clients and agent frameworks are worth first-class starter templates, which ones only need a compatibility note, and which ones should wait until there is a real operator need.

All star and recency figures below were checked against the public GitHub repos on **2026-03-15**.

## Selection Rules

We prioritize frameworks that are:

- actively maintained
- already popular enough to matter externally
- able to use OpenAI-compatible APIs or configurable base URLs cleanly
- likely to benefit from local-worker routing, policy routing, fallback, and operator visibility

We de-prioritize frameworks that:

- require deep custom runtime embedding instead of a clean HTTP integration
- are closer to full app platforms than reusable client frameworks
- would force FoundryGate into plugin/API surface commitments too early

## Priority Matrix

| Project | Stars | Last push | Fit for FoundryGate | Initial action |
| --- | ---: | --- | --- | --- |
| [langchain-ai/langchain](https://github.com/langchain-ai/langchain) | 129,607 | 2026-03-15 | Very high | Template |
| [microsoft/autogen](https://github.com/microsoft/autogen) | 55,647 | 2026-03-14 | Very high | Template |
| [run-llama/llama_index](https://github.com/run-llama/llama_index) | 47,689 | 2026-03-15 | Very high | Template |
| [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | 46,136 | 2026-03-15 | Very high | Template |
| [agno-agi/agno](https://github.com/agno-agi/agno) | 38,706 | 2026-03-15 | High | Template |
| [microsoft/semantic-kernel](https://github.com/microsoft/semantic-kernel) | 27,463 | 2026-03-14 | High | Template |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | 26,455 | 2026-03-15 | Very high | Template |
| [deepset-ai/haystack](https://github.com/deepset-ai/haystack) | 24,512 | 2026-03-15 | High | Template |
| [paperclipai/paperclip](https://github.com/paperclipai/paperclip) | 24,080 | 2026-03-15 | High | Requested template |
| [mastra-ai/mastra](https://github.com/mastra-ai/mastra) | 22,021 | 2026-03-15 | High | Template |
| [google/adk-python](https://github.com/google/adk-python) | 18,380 | 2026-03-15 | High | Template |
| [pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai) | 15,480 | 2026-03-13 | High | Matrix now, template next |
| [camel-ai/camel](https://github.com/camel-ai/camel) | 16,354 | 2026-03-15 | Medium-high | Matrix now, template next |
| [Agent-Field/SWE-AF](https://github.com/Agent-Field/SWE-AF) | 436 | 2026-03-15 | High | Requested template |
| [Heyvhuang/ship-faster](https://github.com/Heyvhuang/ship-faster) | 320 | 2026-03-15 | Medium | Requested template |

## Matrix-Only For Now

These projects are important signals, but they are not the best first template targets for `v1.1.0`.

| Project | Stars | Why not first-wave |
| --- | ---: | --- |
| [langgenius/dify](https://github.com/langgenius/dify) | 132,912 | More platform/application surface than client-template surface |
| [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) | 69,161 | Strong dev-agent platform, but less “generic starter template” friendly for the first FoundryGate slice |
| [BlockRunAI/ClawRouter](https://github.com/BlockRunAI/ClawRouter) | 5,522 | Best treated as competitive/reference input, not as a target integration |

## First-Wave Template Set For `v1.1.0`

This is the recommended minimum useful template wave:

1. `SWE-AF`
2. `paperclip`
3. `ship-faster`
4. `LangChain`
5. `LangGraph`
6. `AutoGen`
7. `LlamaIndex`
8. `CrewAI`

That set gives FoundryGate:

- the three user-requested integrations
- strong coverage of the most recognizable agent ecosystems
- both Python-heavy and orchestration-heavy client shapes
- a good external-discovery story without documenting ten nearly identical setups at once

## Second-Wave Template Set

This wave is now covered in the repo:

- `Agno`
- `Semantic Kernel`
- `Haystack`
- `Mastra`
- `Google ADK`

## Third-Wave Template Set

The next clean bundle after the second wave is:

- `AutoGen`
- `LlamaIndex`
- `CrewAI`
- `PydanticAI`
- `CAMEL`

## ClawRouter Watch List

ClawRouter remains a useful reference point for product direction and operator ergonomics.

We should keep watching for:

- modality expansion patterns
- clearer comparison/positioning language
- routing-signal ideas worth formalizing better in FoundryGate
- operator-experience improvements that fit the no-build dashboard

We should not blindly copy:

- product claims we cannot verify
- hosted-account assumptions that do not fit FoundryGate's local-first shape
- features that would bloat the gateway core instead of strengthening it
