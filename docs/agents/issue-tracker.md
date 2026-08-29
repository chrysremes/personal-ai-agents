# Issue tracker

Issues for this repo are tracked locally as markdown files within `.scratch/` directories.

## Workflow

1. **Create an issue**: Add a new markdown file under `.scratch/<feature-name>/issue.md`
2. **Apply triage labels**: Use front matter to assign labels (see example below)
3. **Track progress**: Update the file as work progresses
4. **Close issues**: Archive or delete when complete

## File format

Each issue is a markdown file with optional YAML front matter:

```markdown
---
title: Brief description of the issue
labels: 
  - needs-triage
  - ready-for-agent
assigned_to: 
  - person-name
status: open  # or in-progress, closed
---

# Issue description

Details about what needs to be done, context, and acceptance criteria.

## Notes

- Ongoing notes about progress
```

## Directory structure

```
.scratch/
├── feature-name-1/
│   ├── issue.md
│   └── subtask.md
├── feature-name-2/
│   └── issue.md
```

## Label vocabulary

See `docs/agents/triage-labels.md` for the complete label vocabulary. Apply labels to issues as needed to communicate status and priority.

## No external sync

This is a local-only issue tracker. There is no sync with GitHub Issues, Jira, or any external system. Issues live entirely in this repository.
