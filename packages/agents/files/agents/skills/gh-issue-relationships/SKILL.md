---
name: gh-issue-relationships
description: Use for creating GitHub sub-issue and blocked-by relationships.
---

# GitHub Issue Relationships

```bash
gh issue create -R OWNER/REPO --parent "$PARENT" ...
gh issue edit "$CHILD" -R OWNER/REPO --parent "$PARENT"
gh issue edit "$PARENT" -R OWNER/REPO --add-sub-issue "$CHILDREN"
gh issue edit "$BLOCKED" -R OWNER/REPO --add-blocked-by "$BLOCKERS"
gh issue edit "$BLOCKER" -R OWNER/REPO --add-blocking "$BLOCKED_ISSUES"
```

Plural values are comma-separated issue numbers or URLs.
