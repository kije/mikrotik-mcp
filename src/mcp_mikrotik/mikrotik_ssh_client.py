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

    def _log_agent_status(self) -> None:
        """Probe the SSH agent and log its status (diagnostics only).

        paramiko performs the real agent-based authentication itself when
        ``allow_agent=True`` is passed to ``SSHClient.connect`` — it connects
        to the agent via ``paramiko.agent.get_agent_connection`` (the
        ``SSH_AUTH_SOCK`` unix socket on POSIX, or Pageant / OpenSSH agent on
        Windows). This helper does not authenticate; it simply surfaces the
        two failure modes that otherwise look identical to "no key found":

          1. ``SSH_AUTH_SOCK`` is not present in the server process's
             environment (common when the MCP server is spawned by a client
             or run inside a container that does not forward the agent socket).
          2. The agent is reachable but holds no identities (``ssh-add`` was
             never run, or the keys have expired).

        Any error here is swallowed: it must never prevent the real
        connection attempt below.
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
            return

        try:
            agent = paramiko.Agent()
            try:
                keys = agent.get_keys()
            finally:
                agent.close()
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Could not query the SSH agent: {e}")
            return

        if not keys:
            logger.warning(
                "allow_agent is enabled and the SSH agent is reachable, but "
                "it exposes no keys. Load a key with 'ssh-add' before "
                "connecting."
            )
        else:
            logger.info(f"SSH agent exposes {len(keys)} key(s) for authentication")

    def connect(self):
        """Establish SSH connection to MikroTik device."""
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            if self.allow_agent:
                self._log_agent_status()
            self.client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                key_filename=self.key_filename,
                look_for_keys=False,
                allow_agent=self.allow_agent,
                timeout=10
            )
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MikroTik: {e}")
            return False

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
