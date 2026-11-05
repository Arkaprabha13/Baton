---
name: baton-adapters
description: Guidelines for writing the Maps Scraper and Gmail MCP adapters for Baton. Use this when writing adapters/scraper.py or adapters/email.py.
---
# Baton Adapters
## Maps Scraper
- Repo cloned at `vendor/maps-scraper`. Runs via Docker Compose on `localhost:8080`.
- Start with: `cd vendor/maps-scraper && docker compose up -d`.
- API: POST `localhost:8080/api/v1/jobs`, poll for completion, download CSV.

## Gmail MCP
- Repo cloned at `vendor/gmail-mcp`. Requires Node.js 18+.
- Setup: `cd vendor/gmail-mcp && npm install && npm run build && npm start`.
- Runs on `http://localhost:3100`. Use `langchain-mcp-adapters` via SSE (`http://localhost:3100/sse`).
- Tools exposed: `send_email`, `search_emails`.