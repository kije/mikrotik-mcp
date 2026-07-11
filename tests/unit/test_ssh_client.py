import io

import pytest


# ---------------------------------------------------------------------------
# _decode_output: encoding fallback (issue #58)
# ---------------------------------------------------------------------------

class TestDecodeOutput:
    """Unit tests for MikroTikSSHClient._decode_output."""

    def setup_method(self):
        from mcp_mikrotik.mikrotik_ssh_client import MikroTikSSHClient
        self.decode = MikroTikSSHClient._decode_output

    def test_empty_bytes_returns_empty_string(self):
        assert self.decode(b"") == ""

    def test_pure_ascii_decoded_correctly(self):
        assert self.decode(b"hello world") == "hello world"

    def test_valid_utf8_decoded_correctly(self):
        # UTF-8 encoded euro sign and em-dash
        data = "€—".encode("utf-8")
        assert self.decode(data) == "€—"

    def test_cp1252_swedish_chars_decoded_correctly(self):
        # Swedish å ä ö — encoded as CP1252 / Latin-1 overlapping bytes
        # CP1252: å=0xE5, ä=0xE4, ö=0xF6
        data = "från Gör om ö".encode("cp1252")
        result = self.decode(data)
        assert "å" in result or "\xe5" in result  # å
        assert "ö" in result or "\xf6" in result  # ö

    def test_latin1_only_bytes_decoded_without_error(self):
        # Bytes that are valid latin-1 but not valid UTF-8 or CP1252
        # 0x9D is undefined in CP1252 but valid latin-1
        data = bytes([0x48, 0x65, 0x6C, 0x6C, 0x6F, 0x9D])
        result = self.decode(data)
        assert isinstance(result, str)
        assert result.startswith("Hello")

    def test_cp1252_nat_rule_comment_does_not_raise(self):
        # Simulated RouterOS NAT print output with a Swedish comment
        # b"\xf6" = ö in cp1252
        raw = b"chain=srcnat action=masquerade comment=\"\xf6ppet n\xe4t\""
        result = self.decode(raw)
        assert isinstance(result, str)
        assert "ppet" in result  # partial match regardless of exact char

    def test_swedish_bytes_reported_in_issue_do_not_raise(self):
        # Exact bytes mentioned in the issue: 0xf6 (ö) and 0xe5 (å)
        raw = bytes([0xF6, 0x20, 0xE5])
        result = self.decode(raw)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# execute_command with non-ASCII stdout/stderr
# ---------------------------------------------------------------------------

def test_execute_command_handles_cp1252_stdout(monkeypatch):
    from mcp_mikrotik.mikrotik_ssh_client import MikroTikSSHClient
    import mcp_mikrotik.mikrotik_ssh_client as mod

    # Simulate RouterOS returning CP1252-encoded bytes on stdout
    cp1252_bytes = "comment=\"från\"".encode("cp1252")

    class DummySSH:
        def set_missing_host_key_policy(self, _): pass
        def connect(self, **kwargs): pass
        def exec_command(self, command):
            return (None, io.BytesIO(cp1252_bytes), io.BytesIO(b""))
        def close(self): pass

    monkeypatch.setattr(mod.paramiko, "SSHClient", lambda: DummySSH())

    client = MikroTikSSHClient(host="h", username="u", password="p", key_filename=None)
    assert client.connect() is True
    result = client.execute_command("/ip firewall nat print")
    assert isinstance(result, str)
    assert "comment=" in result


def test_execute_command_handles_cp1252_stderr(monkeypatch):
    from mcp_mikrotik.mikrotik_ssh_client import MikroTikSSHClient
    import mcp_mikrotik.mikrotik_ssh_client as mod

    # Non-ASCII bytes on stderr, empty stdout → should return decoded stderr
    cp1252_err = "failure: ej till\xe5ten".encode("cp1252")

    class DummySSH:
        def set_missing_host_key_policy(self, _): pass
        def connect(self, **kwargs): pass
        def exec_command(self, command):
            return (None, io.BytesIO(b""), io.BytesIO(cp1252_err))
        def close(self): pass

    monkeypatch.setattr(mod.paramiko, "SSHClient", lambda: DummySSH())

    client = MikroTikSSHClient(host="h", username="u", password="p", key_filename=None)
    assert client.connect() is True
    result = client.execute_command("/ip firewall nat print")
    assert isinstance(result, str)
    assert "failure" in result


def test_ssh_client_requires_connect_for_execute():
    from mcp_mikrotik.mikrotik_ssh_client import MikroTikSSHClient

    client = MikroTikSSHClient(host="h", username="u", password="p", key_filename=None, port=22)
    with pytest.raises(Exception, match="Not connected"):
        client.execute_command("/system identity print")


def test_ssh_client_connect_and_execute(monkeypatch):
    from mcp_mikrotik.mikrotik_ssh_client import MikroTikSSHClient
    import mcp_mikrotik.mikrotik_ssh_client as mod

    state = {"connect_kwargs": None, "closed": 0}

    class DummySSH:
        def set_missing_host_key_policy(self, _policy):
            pass

        def connect(self, **kwargs):
            state["connect_kwargs"] = kwargs

        def exec_command(self, command: str):
            assert command == "/system identity print"
            return (None, io.BytesIO(b"out"), io.BytesIO(b""))

        def close(self):
            state["closed"] += 1

    monkeypatch.setattr(mod.paramiko, "SSHClient", lambda: DummySSH())

    client = MikroTikSSHClient(host="h", username="u", password="p", key_filename="k", port=2222)
    assert client.connect() is True
    assert state["connect_kwargs"]["hostname"] == "h"
    assert state["connect_kwargs"]["port"] == 2222
    assert state["connect_kwargs"]["username"] == "u"
    assert state["connect_kwargs"]["password"] == "p"
    assert state["connect_kwargs"]["key_filename"] == "k"

    assert client.execute_command("/system identity print") == "out"
    client.disconnect()
    assert state["closed"] == 1


# ---------------------------------------------------------------------------
# SSH agent authentication (--allow-agent)
# ---------------------------------------------------------------------------

def _install_dummy_ssh(monkeypatch, accept=None):
    """Patch paramiko.SSHClient with a fake that records every connect attempt.

    ``accept`` is a predicate over the connect kwargs deciding whether an
    attempt authenticates; when it returns False the fake raises, mirroring a
    rejected key. Defaults to accepting every attempt. Returns a state dict
    with ``attempts`` (all kwargs) and ``connect_kwargs`` (the accepted one).
    """
    import paramiko
    import mcp_mikrotik.mikrotik_ssh_client as mod

    if accept is None:
        accept = lambda kwargs: True

    state = {"attempts": [], "connect_kwargs": None}

    class DummySSH:
        def set_missing_host_key_policy(self, _policy):
            pass

        def connect(self, **kwargs):
            state["attempts"].append(kwargs)
            if not accept(kwargs):
                raise paramiko.ssh_exception.AuthenticationException("rejected")
            state["connect_kwargs"] = kwargs

        def close(self):
            pass

    monkeypatch.setattr(mod.paramiko, "SSHClient", lambda: DummySSH())
    return state


def _install_dummy_agent(monkeypatch, keys):
    import mcp_mikrotik.mikrotik_ssh_client as mod

    class DummyAgent:
        def get_keys(self):
            return tuple(keys)

        def close(self):
            pass

    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/agent.sock")
    monkeypatch.setattr(mod.paramiko, "Agent", lambda: DummyAgent())


def test_allow_agent_defaults_off_uses_plain_connect(monkeypatch):
    from mcp_mikrotik.mikrotik_ssh_client import MikroTikSSHClient

    state = _install_dummy_ssh(monkeypatch)

    client = MikroTikSSHClient(host="h", username="u", password="p", key_filename=None)
    assert client.allow_agent is False
    assert client.connect() is True
    assert state["connect_kwargs"]["allow_agent"] is False
    assert state["connect_kwargs"]["pkey"] is None
    assert state["connect_kwargs"]["password"] == "p"


def test_allow_agent_offers_each_key_on_its_own_connection(monkeypatch):
    """Agent keys are offered one per connection (not all via allow_agent)."""
    from mcp_mikrotik.mikrotik_ssh_client import MikroTikSSHClient

    # Only "good" authenticates; "bad1"/"bad2" are rejected.
    state = _install_dummy_ssh(monkeypatch, accept=lambda kw: kw.get("pkey") == "good")
    _install_dummy_agent(monkeypatch, ["bad1", "bad2", "good"])

    client = MikroTikSSHClient(host="h", username="u", password="", key_filename=None, allow_agent=True)
    assert client.connect() is True

    # Each attempt offered exactly one agent key, never the whole set at once.
    offered = [a["pkey"] for a in state["attempts"]]
    assert offered == ["bad1", "bad2", "good"]
    assert all(a["allow_agent"] is False for a in state["attempts"])
    # Agent attempts must not also fire off a password auth.
    assert all(a["password"] is None for a in state["attempts"])
    assert state["connect_kwargs"]["pkey"] == "good"


def test_allow_agent_stops_at_first_accepted_key(monkeypatch):
    from mcp_mikrotik.mikrotik_ssh_client import MikroTikSSHClient

    state = _install_dummy_ssh(monkeypatch, accept=lambda kw: kw.get("pkey") == "first")
    _install_dummy_agent(monkeypatch, ["first", "second"])

    client = MikroTikSSHClient(host="h", username="u", password="", key_filename=None, allow_agent=True)
    assert client.connect() is True
    # "second" must never be tried once "first" is accepted.
    assert [a["pkey"] for a in state["attempts"]] == ["first"]


def test_allow_agent_falls_back_to_password_when_all_keys_rejected(monkeypatch):
    from mcp_mikrotik.mikrotik_ssh_client import MikroTikSSHClient

    # Keys (pkey set) are rejected; the password fallback (pkey is None) works.
    state = _install_dummy_ssh(monkeypatch, accept=lambda kw: kw.get("pkey") is None)
    _install_dummy_agent(monkeypatch, ["bad1", "bad2"])

    client = MikroTikSSHClient(host="h", username="u", password="pw", key_filename=None, allow_agent=True)
    assert client.connect() is True
    # Last attempt is the password fallback: no pkey, password sent.
    assert state["connect_kwargs"]["pkey"] is None
    assert state["connect_kwargs"]["password"] == "pw"


def test_allow_agent_fails_when_all_keys_rejected_and_no_password(monkeypatch):
    from mcp_mikrotik.mikrotik_ssh_client import MikroTikSSHClient

    state = _install_dummy_ssh(monkeypatch, accept=lambda kw: False)
    _install_dummy_agent(monkeypatch, ["bad1"])

    client = MikroTikSSHClient(host="h", username="u", password="", key_filename=None, allow_agent=True)
    assert client.connect() is False
    # Only the single agent key was tried; no spurious password fallback.
    assert [a["pkey"] for a in state["attempts"]] == ["bad1"]


def test_allow_agent_warns_when_sock_missing(monkeypatch, caplog):
    from mcp_mikrotik.mikrotik_ssh_client import MikroTikSSHClient
    import mcp_mikrotik.mikrotik_ssh_client as mod

    state = _install_dummy_ssh(monkeypatch)
    monkeypatch.setattr(mod.sys, "platform", "linux")
    monkeypatch.delenv("SSH_AUTH_SOCK", raising=False)

    # Agent must not even be constructed when the socket is absent.
    def _boom():
        raise AssertionError("paramiko.Agent should not be created without SSH_AUTH_SOCK")

    monkeypatch.setattr(mod.paramiko, "Agent", _boom)

    client = MikroTikSSHClient(host="h", username="u", password="", key_filename=None, allow_agent=True)
    with caplog.at_level("WARNING"):
        assert client.connect() is True  # falls back to plain connect
    assert any("SSH_AUTH_SOCK" in r.message for r in caplog.records)


def test_allow_agent_warns_when_agent_has_no_keys(monkeypatch, caplog):
    from mcp_mikrotik.mikrotik_ssh_client import MikroTikSSHClient

    _install_dummy_ssh(monkeypatch)
    _install_dummy_agent(monkeypatch, [])

    client = MikroTikSSHClient(host="h", username="u", password="", key_filename=None, allow_agent=True)
    with caplog.at_level("WARNING"):
        assert client.connect() is True
    assert any("no keys" in r.message for r in caplog.records)


def test_agent_probe_failure_does_not_block_connect(monkeypatch):
    from mcp_mikrotik.mikrotik_ssh_client import MikroTikSSHClient
    import mcp_mikrotik.mikrotik_ssh_client as mod

    _install_dummy_ssh(monkeypatch)
    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/agent.sock")

    def _raise():
        raise RuntimeError("agent exploded")

    monkeypatch.setattr(mod.paramiko, "Agent", _raise)

    client = MikroTikSSHClient(host="h", username="u", password="", key_filename=None, allow_agent=True)
    # A broken agent probe must never prevent the fallback connection attempt.
    assert client.connect() is True


# ---------------------------------------------------------------------------
# Agent key selection via ~/.ssh/config IdentityFile
# ---------------------------------------------------------------------------

def _make_agent_key(seed: bytes):
    """A fake AgentKey whose asbytes() blob matches its .pub line on disk.

    Returns ``(key, pub_line)`` where ``key.asbytes()`` equals the wire blob
    encoded in ``pub_line`` — mirroring the real paramiko relationship the
    selection logic relies on.
    """
    import base64
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    priv = Ed25519PrivateKey.from_private_bytes(seed)
    pub_line = priv.public_key().public_bytes(
        serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH
    ).decode()
    wire_blob = base64.b64decode(pub_line.split()[1])

    class FakeAgentKey:
        def asbytes(self):
            return wire_blob

    return FakeAgentKey(), pub_line


def _write_ssh_config(home, host, identity_path):
    ssh_dir = home / ".ssh"
    ssh_dir.mkdir(parents=True, exist_ok=True)
    (ssh_dir / "config").write_text(
        f"Host {host}\n  IdentityFile {identity_path}\n  IdentitiesOnly yes\n"
    )


def test_ssh_config_identityfile_narrows_agent_keys(monkeypatch, tmp_path):
    """Only the agent key matching the host's IdentityFile is offered."""
    from mcp_mikrotik.mikrotik_ssh_client import MikroTikSSHClient

    key_a, pub_a = _make_agent_key(b"\x01" * 32)
    key_b, pub_b = _make_agent_key(b"\x02" * 32)

    # Write key_b's public key as the configured identity.
    id_path = tmp_path / "id_router"
    (tmp_path / "id_router.pub").write_text(pub_b)
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_ssh_config(tmp_path, "10.0.0.1", str(id_path))

    state = _install_dummy_ssh(monkeypatch, accept=lambda kw: kw.get("pkey") is key_b)
    _install_dummy_agent(monkeypatch, [key_a, key_b])

    client = MikroTikSSHClient(host="10.0.0.1", username="u", password="", key_filename=None, allow_agent=True)
    assert client.connect() is True

    # key_a (not the configured identity) must never be offered.
    offered = [a["pkey"] for a in state["attempts"]]
    assert offered == [key_b]


def test_ssh_config_no_match_offers_all_agent_keys(monkeypatch, tmp_path):
    from mcp_mikrotik.mikrotik_ssh_client import MikroTikSSHClient

    key_a, _ = _make_agent_key(b"\x03" * 32)
    key_b, _ = _make_agent_key(b"\x04" * 32)
    # Config references an identity that is NOT loaded in the agent.
    _, pub_other = _make_agent_key(b"\x05" * 32)
    (tmp_path / "id_other.pub").write_text(pub_other)
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_ssh_config(tmp_path, "10.0.0.2", str(tmp_path / "id_other"))

    state = _install_dummy_ssh(monkeypatch, accept=lambda kw: kw.get("pkey") is key_b)
    _install_dummy_agent(monkeypatch, [key_a, key_b])

    client = MikroTikSSHClient(host="10.0.0.2", username="u", password="", key_filename=None, allow_agent=True)
    assert client.connect() is True
    # No narrowing possible -> both keys tried in order.
    assert [a["pkey"] for a in state["attempts"]] == [key_a, key_b]


def test_no_ssh_config_offers_all_agent_keys(monkeypatch, tmp_path):
    from mcp_mikrotik.mikrotik_ssh_client import MikroTikSSHClient

    key_a, _ = _make_agent_key(b"\x06" * 32)
    key_b, _ = _make_agent_key(b"\x07" * 32)
    monkeypatch.setenv("HOME", str(tmp_path))  # no ~/.ssh/config present

    state = _install_dummy_ssh(monkeypatch, accept=lambda kw: kw.get("pkey") is key_b)
    _install_dummy_agent(monkeypatch, [key_a, key_b])

    client = MikroTikSSHClient(host="10.0.0.3", username="u", password="", key_filename=None, allow_agent=True)
    assert client.connect() is True
    assert [a["pkey"] for a in state["attempts"]] == [key_a, key_b]


def test_ssh_client_returns_stderr_when_no_stdout(monkeypatch):
    from mcp_mikrotik.mikrotik_ssh_client import MikroTikSSHClient
    import mcp_mikrotik.mikrotik_ssh_client as mod

    class DummySSH:
        def set_missing_host_key_policy(self, _policy):
            pass

        def connect(self, **kwargs):
            pass

        def exec_command(self, command: str):
            return (None, io.BytesIO(b""), io.BytesIO(b"failure: nope"))

        def close(self):
            pass

    monkeypatch.setattr(mod.paramiko, "SSHClient", lambda: DummySSH())

    client = MikroTikSSHClient(host="h", username="u", password="p", key_filename=None, port=22)
    assert client.connect() is True
    assert client.execute_command("/x") == "failure: nope"


# ---------------------------------------------------------------------------
# SFTP file transfer: download_file / upload_file
# ---------------------------------------------------------------------------

def _connect_client_with_sftp(monkeypatch, sftp):
    from mcp_mikrotik.mikrotik_ssh_client import MikroTikSSHClient
    import mcp_mikrotik.mikrotik_ssh_client as mod

    class DummySSH:
        def set_missing_host_key_policy(self, _policy):
            pass

        def connect(self, **kwargs):
            pass

        def open_sftp(self):
            return sftp

        def close(self):
            pass

    monkeypatch.setattr(mod.paramiko, "SSHClient", lambda: DummySSH())
    client = MikroTikSSHClient(host="h", username="u", password="p", key_filename=None)
    assert client.connect() is True
    return client


def test_ssh_client_download_file_via_sftp(monkeypatch):
    class DummySFTP:
        def __init__(self, payload):
            self.payload = payload
            self.closed = False
            self.requested = None

        def getfo(self, remotepath, fileobj):
            self.requested = remotepath
            fileobj.write(self.payload)

        def close(self):
            self.closed = True

    # Binary payload that is NOT valid UTF-8 — proves raw bytes survive intact.
    sftp = DummySFTP(b"\x00\x01\x02backup\xff")
    client = _connect_client_with_sftp(monkeypatch, sftp)

    data = client.download_file("backup_123.backup")
    assert data == b"\x00\x01\x02backup\xff"
    assert sftp.requested == "backup_123.backup"
    assert sftp.closed is True


def test_ssh_client_upload_file_via_sftp(monkeypatch):
    captured = {}

    class DummySFTP:
        def __init__(self):
            self.closed = False

        def putfo(self, fileobj, remotepath):
            captured["remotepath"] = remotepath
            captured["data"] = fileobj.read()

        def close(self):
            self.closed = True

    sftp = DummySFTP()
    client = _connect_client_with_sftp(monkeypatch, sftp)

    client.upload_file("restore.rsc", b"/system identity\n")
    assert captured["remotepath"] == "restore.rsc"
    assert captured["data"] == b"/system identity\n"
    assert sftp.closed is True


def test_ssh_client_download_requires_connect():
    from mcp_mikrotik.mikrotik_ssh_client import MikroTikSSHClient

    client = MikroTikSSHClient(host="h", username="u", password="p", key_filename=None, port=22)
    with pytest.raises(Exception, match="Not connected"):
        client.download_file("x.backup")


def test_ssh_client_upload_requires_connect():
    from mcp_mikrotik.mikrotik_ssh_client import MikroTikSSHClient

    client = MikroTikSSHClient(host="h", username="u", password="p", key_filename=None, port=22)
    with pytest.raises(Exception, match="Not connected"):
        client.upload_file("x.rsc", b"data")

