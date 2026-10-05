# GitHub silent references

Apply only when the user asks for silent references.

Goal: link or track a repository not owned by the user while leaving its timeline unchanged.

- Write issue/PR links as `redirect.github.com` URLs, e.g. `https://redirect.github.com/owner/repo/issues/123`, so GitHub creates no cross-reference event.
- Skip native relationships (dependencies, parent/sub-issues) to that repository.
