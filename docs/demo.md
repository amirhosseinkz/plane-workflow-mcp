# Demo: a bug report becomes a planned task

## Reproduce the offline preview

From the repository root:

```bash
uv run --locked --project plugins/plane-workflow python scripts/demo_preview.py
```

This executes the actual creation-preview code using the existing lifecycle test
fixture. Network access is blocked for the example, stored credentials are not
used, and no Plane work item is created. The date and IDs are synthetic. It shows
strict planning defaults, acceptance criteria, and a preview with no writes.

[See the generated sample output](demo-output.json). The sample uses a Friday
start and Monday target to demonstrate the fixture's two-business-day mapping.
It is a code demonstration, not a live integration test or a client recording.

## Record a 45-second live walkthrough

Use a disposable Plane project and the first prompt in [examples](examples.md).
Configure the workflow beforehand; use advisory planning for a minimal recording,
or configure real strict planning defaults before demonstrating those fields.
Keep the resulting title and identifiers from your actual run.

| Time | Screen/action | Narration |
| --- | --- | --- |
| 0–7s | Show the bug prompt in the coding client | “A checkout retry can create two orders. Let's turn that into a task.” |
| 7–20s | Show the actual preview | “The agent checks for similar work and builds the task using this project's workflow.” |
| 20–28s | Review the proposed fields and approve | “I review the description and planning fields before applying the change.” |
| 28–40s | Show the created item in Plane | “Here is the task that was actually created, including the acceptance criteria.” |
| 40–45s | Show the quick-start link | “Try a read-only project briefing first, then preview your own task.” |

If calls take longer, record the whole interaction and label any cuts. Do not show
an approval animation or successful Plane result that did not happen. Keep API
keys and unrelated workspace data out of the frame. Review the recording before
publishing it, then replace the README's illustrative walkthrough link with the
actual recording. A live recording has not yet been produced.
