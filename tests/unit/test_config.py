def test_config_defaults():
    from mcp_mikrotik.config import MikrotikConfig

    cfg = MikrotikConfig()
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 22
    assert cfg.username == "admin"
    assert cfg.mcp.transport == "stdio"
    assert cfg.mcp.host == "0.0.0.0"
    assert cfg.mcp.port == 8000


def test_allow_agent_defaults_false():
    from mcp_mikrotik.config import MikrotikConfig

    assert MikrotikConfig().allow_agent is False


def test_allow_agent_bare_cli_flag(monkeypatch):
    """`--allow-agent` must work as a bare flag (no explicit value)."""
    from mcp_mikrotik.config import MikrotikConfig

    monkeypatch.setattr("sys.argv", ["mcp-server-mikrotik", "--allow-agent"])
    cfg = MikrotikConfig(_cli_parse_args=True)
    assert cfg.allow_agent is True


def test_allow_agent_omitted_cli_flag(monkeypatch):
    from mcp_mikrotik.config import MikrotikConfig

    monkeypatch.setattr("sys.argv", ["mcp-server-mikrotik"])
    cfg = MikrotikConfig(_cli_parse_args=True)
    assert cfg.allow_agent is False


def test_allow_agent_env_override(monkeypatch):
    from mcp_mikrotik.config import MikrotikConfig

    monkeypatch.setenv("MIKROTIK_ALLOW_AGENT", "true")
    assert MikrotikConfig().allow_agent is True


def test_config_env_overrides(monkeypatch):
    from mcp_mikrotik.config import MikrotikConfig

    monkeypatch.setenv("MIKROTIK_HOST", "10.0.0.10")
    monkeypatch.setenv("MIKROTIK_PORT", "2222")
    monkeypatch.setenv("MIKROTIK_USERNAME", "u")
    monkeypatch.setenv("MIKROTIK_PASSWORD", "p")
    monkeypatch.setenv("MIKROTIK_MCP__TRANSPORT", "sse")
    monkeypatch.setenv("MIKROTIK_MCP__HOST", "127.0.0.1")
    monkeypatch.setenv("MIKROTIK_MCP__PORT", "9000")

    cfg = MikrotikConfig()
    assert cfg.host == "10.0.0.10"
    assert cfg.port == 2222
    assert cfg.username == "u"
    assert cfg.password == "p"
    assert cfg.mcp.transport == "sse"
    assert cfg.mcp.host == "127.0.0.1"
    assert cfg.mcp.port == 9000

