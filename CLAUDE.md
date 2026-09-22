# CLAUDE.md

## Agent skills

### Issue tracker

Issues and specs live as GitHub issues on `jambo-aayan/trader_bot_t212`. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Working agreement

### Never write production code without a spec and a ticket

The order is **spec → ticket → implement**, in that order, every time. Do not skip to
implementation because a change looks small, obvious, or already agreed in conversation.

Agreement on *what to do next* is not authorisation to build it. When the user approves a
recommendation, that approves the next planning step — writing the spec — not the code. If a
decision has been made but no spec and ticket exist for it, the next move is `/to-spec`, not an
editor.

What this does **not** cover, and which needs no ticket:

- Writing and editing docs: ADRs, `CONTEXT.md`, `BACKLOG.md`, analysis notes.
- Throwaway analysis in the scratchpad directory — simulations, measurements, one-off scripts
  used to answer a design question. These inform the spec; they are not the product.

If you are unsure which side of the line something falls on, ask before writing it.
