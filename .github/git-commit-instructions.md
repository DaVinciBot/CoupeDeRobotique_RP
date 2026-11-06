Write commit messages in English, following Conventional Commits (see CONTRIBUTING.md):

type(scope): description

- type: one of feat, fix, perf, test, refactor, docs, build, ci, chore.
- scope: optional, the part of the code concerned (e.g. nav, lidar, safety).
- description: short, imperative mood, lowercase, no trailing period.

Examples:
feat(nav): add visibility graph planner
fix(safety): stop motors when lidar goes silent
docs: add commit message format
