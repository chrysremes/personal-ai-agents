# Domain docs

This document describes how domain knowledge and architecture decisions are documented and consumed by agent skills.

## Layout: Single-context

This repo uses a **single-context** layout, meaning all domain documentation lives at the repo root:

```
/
├── CONTEXT.md           # Single context document
├── docs/adr/            # Architecture decision records (ADRs)
│   ├── 0001-*.md
│   ├── 0002-*.md
│   └── ...
└── ...
```

### When to use single-context

- Single monolithic codebase
- One domain context (everything belongs to the same mental model)
- All engineers and agents share the same understanding of the project

### When to use multi-context (not this repo)

Multi-context layout uses a `CONTEXT-MAP.md` at the repo root, then one `CONTEXT.md` per subdomain:

```
/
├── CONTEXT-MAP.md         # Index of all contexts
├── auth/
│   └── CONTEXT.md         # Auth domain context
├── api/
│   └── CONTEXT.md         # API domain context
└── ...
```

Multi-context is for large monorepos where different packages or services have separate domains.

## Consumer rules

### For agents and humans reading this repo

1. **Start with CONTEXT.md** at the repo root — it defines terminology, domain concepts, and key abstractions
2. **Read ADRs in docs/adr/** to understand past decisions and their rationale
3. **For disagreements**, check the ADR for the last decision on that topic; if none exists, that's a candidate for a new ADR
4. **When proposing changes**, consider whether a new ADR should document the decision

### For agents writing code

- Respect the terminology and abstractions defined in `CONTEXT.md`
- Check `docs/adr/` before introducing new patterns or significant structural changes
- When proposing a new approach that breaks with past decisions, raise it as a new ADR

## ADR format

Architecture Decision Records (ADRs) follow the Nygard template:

```markdown
# ADR-NNNN: Brief title

**Date**: YYYY-MM-DD
**Status**: Accepted | Pending | Rejected | Superseded
**Deciders**: List of people involved

## Context

What is the issue that we're seeing?

## Decision

What is the change that we're proposing or have agreed to do?

## Consequences

What becomes easier or more difficult to do and any risks introduced by this change?

## Alternatives considered

What alternatives did we reject and why?
```

## How to create CONTEXT.md

1. List the key domain concepts and how they relate
2. Define terminology unique to this codebase
3. Explain the high-level architecture and flow
4. Document constraints and invariants
5. Link to relevant ADRs

Start small; expand as the domain grows.
