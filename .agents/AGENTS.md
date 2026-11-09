# AI Rules & Context

This file serves as the primary entry point for AI agents to understand The Terminal project context, rules, and workflow.

## Project State
- **Project Name**: The Terminal — Macro Research & Top-Down Analytics Platform
- **Phase**: Initial Development (Phase 1 — Infrastructure)
- **Current Focus**: Building the distributed data platform foundation (Docker environment, PostgreSQL, Redpanda, Dagster, observability stack)

## User Preferences
- **Communication**: Concise, Technical, Formal
- **Language**: English
- **Role Definition**: "AI generates code and suggestions, but humans own commits and architecture decisions. AI should not introduce new frameworks, services, or patterns without an explicit request."
- **Communication**: "For any non-trivial change, AI must restate the problem, propose an approach, and wait for confirmation before editing files."
- **Validation**: "At the end of each step, AI summarizes the files changed, the behavior modified, and any follow-up TODOs before we move on."
- **Priorities**: "When DRY, SOLID, KISS, and YAGNI conflict, prioritize YAGNI > KISS > SOLID > DRY. Apply DRY only after 3+ stable repetitions, and favor simple, well-factored code over perfect abstraction."

## Execution Environment
- **Platform**: WSL (Ubuntu) on Windows
- **Project Path**: `/mnt/d/10-26-2024/Projects/Personal/The-Terminal`
- **Mandate**: All project execution (Docker, Compose, scripts, tests) must be performed through WSL
- **Scope**: Docker, Docker Compose, and shell execution inside containers. Git and file management remain on Windows.

## Core Documentation
- **Constitution**: [CONSTITUTION.md](docs/CONSTITUTION.md)
- **Project Standards**: [STANDARDS.md](docs/STANDARDS.md)
- **Collaboration Rules**: [WORKING_TOGETHER.md](docs/WORKING_TOGETHER.md)
- **Coding Standards**: [CODING_STANDARDS.md](docs/CODING_STANDARDS.md)
- **Architecture**: [ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **Test Patterns**: [TEST_PATTERNS.md](docs/TEST_PATTERNS.md)
- **API Design System**: [DESIGN_SYSTEM.md](docs/DESIGN_SYSTEM.md)

## Tech Stack
- **Language**: Python 3.9+
- **Orchestration**: Dagster
- **Event Streaming**: Redpanda (Kafka-compatible)
- **Storage**: ClickHouse (time-series), PostgreSQL (metadata)
- **API Layer**: FastAPI
- **Observability**: Grafana, Prometheus, Loki, OpenTelemetry
- **Containerization**: Docker, Docker Compose
- **Dev Environment**: WSL Ubuntu

## Core Principles from README.md
- **Observability First**: Every service, adapter, and pipeline must expose logs, metrics, tracing, health checks, lineage, and telemetry
- **Event-Driven Architecture**: Services communicate through streaming infrastructure
- **Data Lineage**: Every transformation must be reproducible, traceable, versioned, and auditable
- **AI-Native Infrastructure**: Platform must be machine-readable, self-documenting, schema-driven, and introspectable
- **Loose Coupling**: External frameworks remain replaceable modules

## Thinking Process
1. **Context First**: Before suggesting code, check README.md, chatgpt-research.md, and docs/* to understand where the change fits
2. **Step-by-Step**: Break down complex tasks into smaller definitions
3. **No Hallucinations**: Verify file paths and names before citing them
