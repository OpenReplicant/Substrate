# mcp-router

Substrate's MCP router (S-203: modules run on their own and meet over MCP; S-205: the router's rules live in Postgres,
its edge and connectors are processes outside it). One static binary, two modes. The rules (gates, the record, who
decides) are the `env.mcp_*` functions in `environment/sql/010_mcp.sql`; the binary holds none of them.

## `mcp-router serve`: the edge

- `/mcp`: an MCP server over streamable HTTP (stateless: each request builds the server from the tools registered
  at that moment, for the caller in its token). Tools are named `<server>_<tool>`, plus `router_outcome {action}`.
  A call goes through `env.mcp_call`; the router waits (LISTEN `env_action`, one listener for all waits) up to
  `WAIT_SECONDS` for it to end, else answers that it waits for approval.
- `/api/login`, `/api/tools`, `/api/calls`, `/api/decide`: the JSON API of the desktop page. Sign-in opens a Postgres
  connection as `person_<name>` with the password and, if it works, mints an 8-hour token. Only `person_` roles decide.
- `/`: the page (embedded; no inline script or style, no CDN). `/healthz`: `ok`.
- Every request to `/mcp` and `/api` (but login) needs `Authorization: Bearer <HS256 JWT>` made as the Knowledge
  Kernel makes them (`repos/kernel/kk/cli.py mint`): claims `role`, `iat`, `exp`.

| env | |
| --- | --- |
| `DATABASE_URL` | the router's login (`env_router`) |
| `KK_JWT_SECRET` | the token secret, at least 32 characters |
| `LISTEN` | default `:8090` |
| `WAIT_SECONDS` | default `15` |
| `FRAME_ANCESTORS` | default `http://127.0.0.1:8080 http://localhost:8080` (the desktop that frames the page) |

## `mcp-router connect`: one backend

    mcp-router connect --name NAME --stdio "command arg ..."     # or repeat --arg
    mcp-router connect --name NAME --url http://host:port/mcp [--list-role ROLE]

`DATABASE_URL` is the connector's login (`env_connector`). It lists the backend's tools, registers them with
`env.mcp_register` (again every 60 s and after a reconnect), reads the tools' queues and applies each call, reporting
with `env.done`. With `--url` and `KK_JWT_SECRET`, each call carries a 5-minute token for the caller's role (one
session per role), so identity passes through. A line per call goes to stderr (action, tool, caller, argument
*keys*, ok, ms). The image is based on Python so stdio servers written in Python run under it.

## Build and test (containers only)

    podman build -t localhost/substrate-mcp-router:dev -f mcp-router/Containerfile mcp-router
    podman run --rm -v "$PWD/mcp-router:/src:Z" -w /src docker.io/library/golang:1.25.14 \
      sh -c 'gofmt -l . && go vet ./... && go test ./...'
