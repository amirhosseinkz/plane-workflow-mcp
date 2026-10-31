# Runs the stdio MCP server. Used by MCP directories such as Glama to inspect the
# tools; for everyday use, install with `uv tool install plane-workflow-mcp`.
FROM python:3.12-slim

WORKDIR /app
COPY plugins/plane-workflow /app
RUN pip install --no-cache-dir .

ENTRYPOINT ["plane-workflow", "mcp"]
