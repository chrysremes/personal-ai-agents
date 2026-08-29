# Triage labels

This document defines the label vocabulary used in the issue tracker.

## Label definitions

| Label | Meaning | Used by |
|-------|---------|---------|
| `needs-triage` | Issue has not been reviewed and prioritized yet | Triage skill, on new issues |
| `needs-info` | Issue is waiting for additional information before work can begin | Triage skill, when more context is needed |
| `ready-for-agent` | Issue is well-specified and ready for an agent to work on | Triage skill, after review |
| `ready-for-human` | Issue requires human review, decision, or manual work | Triage skill, when agent work is blocked |
| `wontfix` | Issue is acknowledged but will not be fixed | Triage skill, for deprioritized or out-of-scope work |

## Applying labels

Labels are applied in the YAML front matter of `.scratch/<feature>/issue.md`:

```yaml
---
title: Example issue
labels:
  - needs-triage
  - ready-for-agent
---
```

## Default label set

These five labels (and only these) are the canonical triage vocabulary:

- `needs-triage`
- `needs-info`
- `ready-for-agent`
- `ready-for-human`
- `wontfix`

## Custom labels

If you want to add additional domain-specific labels (e.g., `bug`, `feature-request`, `performance`), feel free to do so. The five canonical labels above are required; additional labels can coexist.
