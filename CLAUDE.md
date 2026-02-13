# Megregore — Project Rules

## Workflow
- **Plan mode** for any non-trivial task (3+ steps or architectural decisions). If something goes sideways, STOP and re-plan.
- **Verify before done** — never mark a task complete without proving it works. Run tests, check logs, demonstrate correctness.
- **Simplicity first** — make every change as simple as possible. No premature abstractions. If 100 lines suffice, don't write 1000.
- **Minimal impact** — touch only what's necessary. No unsolicited cleanup or refactoring.
- **Autonomous bug fixing** — when given a bug, just fix it. Point at logs/errors, then resolve. Zero hand-holding needed.

## Before implementing
- Surface assumptions explicitly before non-trivial work. Don't silently fill in ambiguous requirements.
- When confused or seeing inconsistencies, STOP and ask. Don't guess and hope.
- Push back on bad ideas directly. Sycophancy is a failure mode.

## Task tracking
- Plan to `tasks/todo.md` with checkable items. Track progress as you go.
- After any user correction, update `tasks/lessons.md` with a rule to prevent repeating it.

## Code standards
- Find root causes, no temporary fixes. Senior developer standards.
- Correctness first, performance second. Naive-then-optimize for algorithmic work.
- Don't remove code you don't understand. Don't "clean up" code outside the task scope.
- After refactoring, identify dead code and ask before removing.
