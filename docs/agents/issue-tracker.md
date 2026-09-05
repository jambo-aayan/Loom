# Issue tracker: GitHub

Issues and specs for this repo live as GitHub issues on `jambo-aayan/Loom` (renamed from `trader_bot_t212`).

## Conventions

Two equivalent toolsets depending on what's available in the session — use whichever is present:

**Via the `gh` CLI** (if available):
- Create: `gh issue create --title "..." --body "..."`
- Read: `gh issue view <number> --comments`
- List: `gh issue list --state open --json number,title,body,labels,comments`
- Comment: `gh issue comment <number> --body "..."`
- Label: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- Close: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v`; `gh` does this automatically when run inside a clone.

**Via the GitHub MCP tools** (this environment's default — no `gh` CLI here):
- Create: `mcp__github__issue_write` (mode: create)
- Read: `mcp__github__issue_read`
- List: `mcp__github__list_issues` (broad) or `mcp__github__search_issues` (targeted)
- Comment: `mcp__github__add_issue_comment`
- Label: `mcp__github__issue_write` (mode: update, with labels)
- Close: `mcp__github__issue_write` (mode: update, state: closed, with a `state_reason`)

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Only relevant if `/triage` is later installed — leave off unless external PRs should be treated as feature requests.)_

## When a skill says "publish to the issue tracker"

Create a GitHub issue on `jambo-aayan/Loom`.

## When a skill says "fetch the relevant ticket"

Read the GitHub issue by number (MCP `issue_read`, or `gh issue view <number> --comments`).
