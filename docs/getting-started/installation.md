# Installation

## MCP Registry (Recommended)

MikroTik MCP is listed on the [MCP Registry](https://registry.modelcontextprotocol.io) — a community-driven catalog of MCP servers. Registry-aware clients (Claude Desktop, VS Code, Cursor) can install it in one command without manual config file editing.

```bash
claude mcp add io.github.jeff-nasseri/mikrotik-mcp
```

The client fetches the server metadata from the registry, installs `mcp-server-mikrotik` from PyPI, and prompts you for the required environment variables (`MIKROTIK_HOST`, `MIKROTIK_USERNAME`, `MIKROTIK_PASSWORD`).

> **PyPI install only:** If your client does not support registry-based install, use one of the manual methods below.

---

## Prerequisites
- Python 3.8+
- MikroTik RouterOS device with API access enabled
- Python dependencies (routeros-api or similar)

## Manual Installation

```bash
# Clone the repository
git clone https://github.com/jeff-nasseri/mikrotik-mcp.git
cd mikrotik-mcp

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .

# Run the server (stdio, default)
mcp-server-mikrotik

# Run with SSE transport
mcp-server-mikrotik --mcp.transport sse

# Run with streamable HTTP transport
mcp-server-mikrotik --mcp.transport streamable-http
```

### CLI Options

| Flag | Description | Default |
|------|-------------|---------|
| `--host` | MikroTik device IP/hostname | from config |
| `--username` | SSH username | from config |
| `--password` | SSH password | from config |
| `--key-filename` | SSH key filename | from config |
| `--allow-agent` | Authenticate with keys loaded in the local SSH agent (`ssh-agent` / Pageant). Bare flag — no value needed. | `false` |
| `--agent-key-fingerprint` | Hint selecting which agent key to offer, as a fingerprint (`SHA256:…` from `ssh-add -l`, or an MD5 `aa:bb:…`). Only used with `--allow-agent`. | _(none)_ |
| `--port` | SSH port | `22` |
| `--mcp.transport` | Transport type: `stdio`, `sse`, `streamable-http` | `stdio` |
| `--mcp.host` | HTTP server listen address | `0.0.0.0` |
| `--mcp.port` | HTTP server listen port | `8000` |

HTTP-based transports (`sse`, `streamable-http`) expose a `GET /health` endpoint for health checks. This endpoint is **not available** in `stdio` mode.

#### SSH agent authentication (`--allow-agent`)

Pass `--allow-agent` (or set `MIKROTIK_ALLOW_AGENT=true`) to have the server
authenticate using the private keys held by your SSH agent instead of a
password or an on-disk key file. The public part of a loaded key must be
installed on the RouterOS user (`/user ssh-keys import`).

For this to work the agent must be reachable **by the server process**:

- The `SSH_AUTH_SOCK` environment variable must be present in the server's
  environment. When the server is launched by an MCP client or run inside a
  container, that variable is often not inherited — forward it explicitly.
- The agent must actually hold a key — run `ssh-add -l` to check, and
  `ssh-add` to load one.

If `--allow-agent` is set but no key can be used, the server logs a warning
identifying which of these two conditions is unmet.

RouterOS aborts an SSH session after only a few rejected public keys, so the
server offers agent identities **one per connection** and stops at the first
key the device accepts (rather than presenting the whole agent at once, which
makes RouterOS disconnect with `code 2` when the agent holds many keys). If
every agent key is rejected, it falls back to key-file / password
authentication when those are configured.

**Selecting the right key.** If your agent holds many keys, trying them one by
one means the device logs several rejected logins before the accepted key is
reached. There are two ways to offer only the correct key (checked in this
order):

1. **Fingerprint hint** — pass `--agent-key-fingerprint` with the fingerprint
   shown by `ssh-add -l` (or `ssh-keygen -lf key.pub`):

   ```
   mcp-server-mikrotik --allow-agent --agent-key-fingerprint SHA256:AbC…
   ```

   Both the modern `SHA256:…` (base64) and legacy MD5 `aa:bb:…` (hex) forms are
   accepted, with or without the `SHA256:`/`MD5:` prefix.

2. **`~/.ssh/config` `IdentityFile`** — add an entry for the device (the file
   must be readable by the server process):

   ```
   Host 192.168.88.1
       IdentityFile ~/.ssh/id_mikrotik
   ```

   The server matches the configured identity's public key
   (`~/.ssh/id_mikrotik.pub`) against the keys in the agent and offers just
   that one. The private key never has to be readable; only the public key and
   the agent are used.

Either way it becomes a single authentication attempt. With neither set, all
agent keys are tried one per connection.

**`~/.ssh/config` connection settings.** When the configured host matches a
stanza in `~/.ssh/config`, its `HostName`, `User` and `Port` also fill any
connection parameter left at its default — so you can point `MIKROTIK_HOST` at
an alias:

```
Host myrouter
    HostName 192.168.88.1
    User admin
    Port 2200
    IdentityFile ~/.ssh/id_mikrotik
```

An explicitly-set `MIKROTIK_USERNAME` / `MIKROTIK_PORT` (any non-default value)
always takes precedence over the config file.

## Docker Installation

The easiest way to run the MCP MikroTik server is using Docker.

### Official prebuilt image (GitHub Container Registry)

A multi-arch image (`linux/amd64` + `linux/arm64`) is published to GHCR, so you
can pull it directly instead of building from source:

```bash
# Latest release
docker pull ghcr.io/jeff-nasseri/mikrotik-mcp:latest

# A specific version (matches the PyPI / git tag version)
docker pull ghcr.io/jeff-nasseri/mikrotik-mcp:0.10.1
```

| Tag | Points to |
|-----|-----------|
| `latest` | The most recent release |
| `X.Y.Z` | A specific released version (e.g. `0.10.1`), aligned with the PyPI release |
| `X.Y` | The latest patch of a minor line (e.g. `0.10`) |
| `sha-<short>` | A specific commit |

In the examples below, substitute `ghcr.io/jeff-nasseri/mikrotik-mcp:latest` for
`mikrotik-mcp` to use the prebuilt image instead of a locally built one.

### Build from source

1. **Clone the repository:**
   ```bash
   git clone https://github.com/jeff-nasseri/mikrotik-mcp.git
   cd mikrotik-mcp
   ```

2. **Build the Docker image:**
   ```bash
   docker build -t mikrotik-mcp .
   ```

3. **Run with stdio (default, for IDE integration):**

   Add this to your `~/.cursor/mcp.json`:
   ```json
   {
     "mcpServers": {
       "mikrotik-mcp-server": {
         "command": "docker",
         "args": [
           "run",
           "--rm",
           "-i",
           "-e", "MIKROTIK_HOST=192.168.88.1",
           "-e", "MIKROTIK_USERNAME=sshuser",
           "-e", "MIKROTIK_PASSWORD=your_password",
           "-e", "MIKROTIK_PORT=22",
           "mikrotik-mcp"
         ]
       }
     }
   }
   ```

4. **Run with SSE or streamable HTTP transport:**

   ```bash
   docker run --rm -p 8000:8000 \
     -e MIKROTIK_HOST=192.168.88.1 \
     -e MIKROTIK_USERNAME=sshuser \
     -e MIKROTIK_PASSWORD=your_password \
     -e MIKROTIK_MCP__TRANSPORT=sse \
     mikrotik-mcp
   ```

   The server will be available at `http://localhost:8000/sse` (SSE) or `http://localhost:8000/mcp` (streamable HTTP).

   **Environment Variables:**

   | Variable | Description | Default |
   |----------|-------------|---------|
   | `MIKROTIK_HOST` | MikroTik device IP/hostname | `192.168.88.1` |
   | `MIKROTIK_USERNAME` | SSH username | `admin` |
   | `MIKROTIK_PASSWORD` | SSH password | _(empty)_ |
   | `MIKROTIK_ALLOW_AGENT` | Authenticate with keys from the SSH agent (see [SSH agent authentication](#ssh-agent-authentication---allow-agent)). Requires `SSH_AUTH_SOCK` to be forwarded into the container. | `false` |
   | `MIKROTIK_AGENT_KEY_FINGERPRINT` | Fingerprint hint selecting which agent key to offer (`SHA256:…` or MD5 `aa:bb:…`). | _(none)_ |
   | `MIKROTIK_PORT` | SSH port | `22` |
   | `MIKROTIK_MCP__TRANSPORT` | Transport type: `stdio`, `sse`, `streamable-http` | `stdio` |
   | `MIKROTIK_MCP__HOST` | HTTP server listen address | `0.0.0.0` |
   | `MIKROTIK_MCP__PORT` | HTTP server listen port | `8000` |
   | `MIKROTIK_MCP__ALLOWED_HOSTS` | Comma-separated `Host` header allowlist for the HTTP transports (DNS-rebinding protection). Set to your domain behind a reverse proxy; `*` disables the check. | _(empty)_ |
   | `MIKROTIK_MCP__ALLOWED_ORIGINS` | Comma-separated `Origin` header allowlist for the HTTP transports. | _(empty)_ |

### Docker Compose

For a long-running, self-hosted setup, use an HTTP-based transport
(`sse` or `streamable-http`) so MCP clients can connect over the network. The
`stdio` transport is meant for direct IDE integration where the client attaches
to the process's stdin/stdout, not for a standalone background service.

```yaml
services:
  mikrotik-mcp:
    image: ghcr.io/jeff-nasseri/mikrotik-mcp:latest
    container_name: mikrotik-mcp
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      MIKROTIK_HOST: "192.168.88.1"
      MIKROTIK_USERNAME: "admin"
      MIKROTIK_PASSWORD: "change-me"
      MIKROTIK_PORT: "22"                      # SSH port of the RouterOS device
      MIKROTIK_MCP__TRANSPORT: "streamable-http"
      MIKROTIK_MCP__HOST: "0.0.0.0"
      MIKROTIK_MCP__PORT: "8000"
```

```bash
docker compose up -d
```

The server is then reachable at `http://localhost:8000/mcp` (streamable HTTP)
or `http://localhost:8000/sse` (if you set `MIKROTIK_MCP__TRANSPORT: sse`), and
`GET http://localhost:8000/health` returns `OK`.

#### Behind a reverse proxy (or any non-localhost access)

The HTTP transports (`sse` / `streamable-http`) apply DNS-rebinding protection,
which validates the request's `Host` header. When the server is reached on a
custom domain or a non-localhost IP — e.g. through a reverse proxy — you must
allowlist that host, otherwise requests to `/mcp` are rejected with **HTTP 421
"Invalid Host header"** (while `/health` still works, since it is exempt):

```yaml
    environment:
      MIKROTIK_MCP__TRANSPORT: "streamable-http"
      MIKROTIK_MCP__HOST: "0.0.0.0"
      # Allowlist the Host header(s) clients use to reach the server:
      MIKROTIK_MCP__ALLOWED_HOSTS: "mcp.example.com"
      # Allowlist the Origin header(s) for browser-based clients:
      MIKROTIK_MCP__ALLOWED_ORIGINS: "https://app.example.com"
```

Both accept a **comma-separated** list, e.g.:

```yaml
      MIKROTIK_MCP__ALLOWED_HOSTS: "mcp.example.com, mcp.example.com:*, 192.168.1.50:8000"
      MIKROTIK_MCP__ALLOWED_ORIGINS: "https://app.example.com, https://admin.example.com"
```

- Append `:*` to a host (e.g. `mcp.example.com:*`) to allow it on any port.
- Set `MIKROTIK_MCP__ALLOWED_HOSTS: "*"` to disable the host check entirely.
- If you leave it unset on a non-localhost bind, the check is auto-disabled (a
  warning is logged) so the server still works out of the box.

> ⚠️ Passing `MIKROTIK_PASSWORD` as an environment variable makes it visible via
> `docker inspect`. See [SECURITY.md](../../SECURITY.md) for safer alternatives.
