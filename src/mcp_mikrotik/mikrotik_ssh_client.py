import base64
import io
import logging
import os
import sys
from typing import Optional

import paramiko

logger = logging.getLogger(__name__)

class MikroTikSSHClient:
    """SSH client for MikroTik devices."""

    def __init__(self, host: str, username: str, password: str, key_filename: Optional[str], port: int = 22, allow_agent: bool = False):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.client = None
        self.channel = None
        self.key_filename = key_filename
        self.allow_agent = allow_agent
        self._agent = None

    @staticmethod
    def _decode_output(data: bytes) -> str:
        """Decode raw SSH output bytes with a multi-encoding fallback chain.

        RouterOS devices may return output encoded in UTF-8, CP1252 (Windows
        Western European), or ISO 8859-1 (Latin-1) depending on the locale
        configured on the device.  Strict UTF-8 decoding raises
        UnicodeDecodeError for characters such as Swedish å/ä/ö (issue #58).

        Fallback order:
          1. UTF-8       — covers ASCII and most modern configurations
          2. CP1252      — covers Windows Western European characters (å ä ö …)
          3. Latin-1     — always succeeds; covers all single-byte code points
        """
        if not data:
            return ""
        for encoding in ("utf-8", "cp1252", "latin-1"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        # Unreachable in practice (latin-1 never raises), but kept as a
        # safety net: replace unrecognised bytes rather than crashing.
        return data.decode("utf-8", errors="replace")

    def _get_agent_keys(self):
        """Return the identities held by the local SSH agent.

        The agent is reached via ``paramiko.agent.get_agent_connection`` (the
        ``SSH_AUTH_SOCK`` unix socket on POSIX, or Pageant / OpenSSH agent on
        Windows). Two failure modes otherwise look identical to "no key found",
        so each is called out with a targeted warning:

          1. ``SSH_AUTH_SOCK`` is not present in the server process's
             environment (common when the server is spawned by an MCP client
             or run inside a container that does not forward the agent socket).
          2. The agent is reachable but holds no identities (``ssh-add`` was
             never run, or the keys have expired).

        The returned ``AgentKey`` objects sign through the live agent
        connection, so ``self._agent`` is kept open until :meth:`connect`
        finishes and closes it via :meth:`_close_agent`.
        """
        sock = os.environ.get("SSH_AUTH_SOCK")
        if not sock and sys.platform != "win32":
            logger.warning(
                "allow_agent is enabled but SSH_AUTH_SOCK is not set in the "
                "server process's environment, so the SSH agent cannot be "
                "reached. Ensure the agent socket is forwarded to the MCP "
                "server process (e.g. inherit SSH_AUTH_SOCK from the shell "
                "that started it)."
            )
            return []

        try:
            self._agent = paramiko.Agent()
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Could not connect to the SSH agent: {e}")
            return []

        keys = list(self._agent.get_keys())
        if not keys:
            logger.warning(
                "allow_agent is enabled and the SSH agent is reachable, but "
                "it exposes no keys. Load a key with 'ssh-add' before "
                "connecting."
            )
        return keys

    @staticmethod
    def _pubkey_blob_from_file(path: str) -> Optional[bytes]:
        """Return the wire-format public-key blob stored in an OpenSSH ``.pub``
        file, or ``None`` if it cannot be read.

        An OpenSSH public-key file is ``<type> <base64-blob> [comment]``; the
        decoded middle field is exactly what ``paramiko.PKey.asbytes`` returns
        for the corresponding key, so the two can be compared directly.
        """
        try:
            with open(os.path.expanduser(path)) as f:
                fields = f.read().split()
        except OSError:
            return None
        if len(fields) < 2:
            return None
        try:
            return base64.b64decode(fields[1])
        except (ValueError, IndexError):
            return None

    def _ssh_config_identity_blobs(self) -> set:
        """Public-key blobs of the ``IdentityFile``(s) configured for this host
        in ``~/.ssh/config``.

        This lets an agent full of unrelated keys be narrowed to just the
        identity the user already associates with the device — the same
        selection ``ssh`` itself performs — so we present one key instead of
        offering (and getting rejected for) every key in turn.
        """
        config_path = os.path.expanduser("~/.ssh/config")
        if not os.path.exists(config_path):
            return set()
        try:
            ssh_config = paramiko.SSHConfig()
            with open(config_path) as f:
                ssh_config.parse(f)
            host_conf = ssh_config.lookup(self.host)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug(f"Could not parse ~/.ssh/config: {e}")
            return set()

        blobs = set()
        for identity_file in host_conf.get("identityfile") or []:
            # IdentityFile normally names the private key; the blob lives in the
            # sibling ".pub". Accept either being given directly.
            for candidate in (f"{identity_file}.pub", identity_file):
                blob = self._pubkey_blob_from_file(candidate)
                if blob:
                    blobs.add(blob)
                    break
        return blobs

    def _select_agent_keys(self, agent_keys: list) -> list:
        """Narrow the agent keys to those matching the host's configured
        ``IdentityFile`` when ``~/.ssh/config`` names one.

        Falls back to the full list when the config selects nothing (no entry
        for the host, or the named identity is not loaded in the agent), so
        agent auth still works without any SSH config.
        """
        wanted = self._ssh_config_identity_blobs()
        if not wanted:
            return agent_keys
        matched = [k for k in agent_keys if k.asbytes() in wanted]
        if matched:
            logger.info(
                f"Selected {len(matched)} agent key(s) matching the "
                f"IdentityFile for host '{self.host}' in ~/.ssh/config"
            )
            return matched
        logger.debug(
            "~/.ssh/config names an IdentityFile for host '%s' but no matching "
            "key is loaded in the agent; offering all agent keys",
            self.host,
        )
        return agent_keys

    def _close_agent(self) -> None:
        if self._agent is not None:
            try:
                self._agent.close()
            except Exception:  # pragma: no cover - defensive
                pass
            self._agent = None

    def _open(self, pkey=None, allow_agent: bool = False, use_password: bool = True, quiet: bool = False) -> bool:
        """Open a single SSH connection attempt and store the client on success.

        A failed attempt returns ``False`` rather than raising so the caller
        can move on to the next candidate key. ``quiet`` keeps per-key
        rejections at debug level to avoid flooding the log during the agent
        key sweep.
        """
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password if use_password else None,
                key_filename=self.key_filename,
                pkey=pkey,
                look_for_keys=False,
                allow_agent=allow_agent,
                timeout=10,
            )
            self.client = client
            return True
        except Exception as e:
            if quiet:
                logger.debug(f"SSH authentication attempt failed: {e}")
            else:
                logger.error(f"Failed to connect to MikroTik: {e}")
            return False

    def connect(self):
        """Establish SSH connection to MikroTik device.

        With ``allow_agent`` enabled, agent identities are tried one per
        connection instead of all at once. RouterOS aborts a session after
        only a few rejected public keys, so offering a whole agent's worth of
        keys on one connection (paramiko's default ``allow_agent`` behaviour)
        makes the device disconnect before the accepted key is reached — a
        loaded agent with many keys otherwise fails with "Disconnect (code 2)".
        Trying each key on its own connection keeps every attempt within
        RouterOS's per-session limit and stops at the first accepted key.
        """
        try:
            if not self.allow_agent:
                return self._open(allow_agent=False)

            agent_keys = self._get_agent_keys()
            if agent_keys:
                agent_keys = self._select_agent_keys(agent_keys)
                if len(agent_keys) > 3:
                    logger.warning(
                        "%d agent keys will be tried one per connection, so the "
                        "device will log that many rejected logins before the "
                        "accepted key is found. Add an 'IdentityFile' for host "
                        "'%s' to ~/.ssh/config (or load fewer keys into the "
                        "agent) to offer only the correct key.",
                        len(agent_keys),
                        self.host,
                    )
                logger.info(f"Trying {len(agent_keys)} SSH agent key(s) for authentication")
                for index, key in enumerate(agent_keys, start=1):
                    if self._open(pkey=key, use_password=False, quiet=True):
                        logger.info(f"Authenticated with SSH agent key {index}/{len(agent_keys)}")
                        return True
                logger.info(
                    f"All {len(agent_keys)} SSH agent key(s) were rejected by the device"
                )

            # No agent keys, or every agent key was rejected: fall back to
            # key-file / password authentication when configured.
            if self.key_filename or self.password or not agent_keys:
                return self._open(allow_agent=False)

            logger.error(
                "Authentication failed: all SSH agent key(s) were rejected and "
                "no key file or password is configured"
            )
            return False
        finally:
            self._close_agent()

    def execute_command(self, command: str) -> str:
        """Execute a command on MikroTik device using exec_command."""
        if not self.client:
            raise Exception("Not connected to MikroTik device")

        try:
            stdin, stdout, stderr = self.client.exec_command(command)

            output = self._decode_output(stdout.read())
            error = self._decode_output(stderr.read())

            if error and not output:
                return error

            return output
        except Exception as e:
            logger.error(f"Error executing command: {e}")
            raise

    def download_file(self, remote_filename: str) -> bytes:
        """Download a file from the device over SFTP and return its raw bytes.

        RouterOS exposes its file store over the SSH/SFTP subsystem, so binary
        backups and text exports alike can be transferred without mangling.
        """
        if not self.client:
            raise Exception("Not connected to MikroTik device")

        sftp = self.client.open_sftp()
        try:
            buffer = io.BytesIO()
            sftp.getfo(remote_filename, buffer)
            return buffer.getvalue()
        finally:
            sftp.close()

    def upload_file(self, remote_filename: str, data: bytes) -> None:
        """Upload raw bytes to a file on the device over SFTP."""
        if not self.client:
            raise Exception("Not connected to MikroTik device")

        sftp = self.client.open_sftp()
        try:
            sftp.putfo(io.BytesIO(data), remote_filename)
        finally:
            sftp.close()

    def disconnect(self):
        """Close SSH connection."""
        if self.client:
            self.client.close()
