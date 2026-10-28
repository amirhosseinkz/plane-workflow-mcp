# Plane Workflow MCP and the official Plane MCP server

[Back to the README](../README.md)

**Short version:** use the official server for broad access to Plane resources or a
hosted OAuth connection. Use Plane Workflow MCP when you want your agent to plan,
start, and complete work under your team's rules, with previews and a factual
completion record. They can be installed side by side.

## Feature comparison

Choose this server when you want configurable planning requirements, a structured
completion record, and project-specific workflows. Choose the official server
when you want broad Plane resource coverage or a hosted OAuth connection.

| Need | Plane Workflow MCP | Official Plane MCP |
| --- | --- | --- |
| Team planning rules | Advisory or strict profiles for required planning fields | General resource operations; no equivalent profile policy documented in the reviewed README |
| Review changes | Explicit `dry_run=true` previews for supported writes | Review/confirmation depends on the client; no equivalent preview workflow documented in the reviewed README |
| Completion | Dedicated operation requires a started item, summary, and verification | Work-item updates, comments, and worklogs available as operations |
| Reporting | Project attention briefings and DOCX/PDF exports | Work-item queries, counts, and grouping through PQL |
| Connection | Local stdio, API key, guided setup | Local stdio or hosted HTTP with OAuth/API token |

Comparison checked against the [official README at a pinned revision](https://github.com/makeplane/plane-mcp-server/blob/beee888f24fc65229a41bc4e0ede20cf4bc59444/README.md)
on September 27, 2026. “Not documented” does not mean impossible or unsupported.

**Review is a client workflow, not a server-enforced approval gate.** Ask your
agent to preview first and wait for your approval. Some write tools default to
`dry_run=false`; the server does not prove a human approved a call. Configured
planning requirements and lifecycle checks are enforced by the server. Tasks are
updated when the agent calls tools; there is no background code-to-task sync.
