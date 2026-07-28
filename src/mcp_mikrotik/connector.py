import asyncio
import logging
from typing import Optional

from mcp.server.mcpserver import Context

from .inventory import DeviceNotFoundError, get_inventory

logger = logging.getLogger(__name__)


def _execute_sync(command: str, device: Optional[str] = None) -> str:
    """Execute a MikroTik command over a fresh SSH connection (blocking).

    Each call opens its own connection and closes it again, so concurrent
    sessions never share a client.
    """
    inventory = get_inventory()
    target = inventory.resolve(device)
    logger.info(f"Executing MikroTik command on '{target.title}': {command}")

    with inventory.session(target.title) as client:
        result = client.execute_command(command)

    logger.info(f"Command result: {repr(result)}")
    return result


def download_file_sync(filename: str, device: Optional[str] = None) -> bytes:
    """Download a file from the target device over SFTP and return its bytes."""
    inventory = get_inventory()
    target = inventory.resolve(device)
    logger.info(f"Downloading file from '{target.title}': {filename}")

    with inventory.session(target.title) as client:
        return client.download_file(filename)


def upload_file_sync(filename: str, data: bytes, device: Optional[str] = None) -> None:
    """Upload bytes to a file on the target device over SFTP."""
    inventory = get_inventory()
    target = inventory.resolve(device)
    logger.info(f"Uploading file to '{target.title}': {filename} ({len(data)} bytes)")

    with inventory.session(target.title) as client:
        client.upload_file(filename, data)


async def execute_mikrotik_command(
    command: str, ctx: Optional[Context] = None, device: Optional[str] = None
) -> str:
    """Execute a MikroTik command on the selected device and return the output.

    ``device`` is the inventory title of the target. It may be omitted when the
    inventory holds exactly one device.

    When Safe Mode is active *for that device* the command is routed through
    that device's persistent interactive shell so it runs inside the safe-mode
    context.

    ``ctx`` is optional so this can also back MCP *resource* handlers, which
    (unlike tools) are not given a per-request :class:`Context`. When ``ctx``
    is ``None`` progress is logged only to the module logger.
    """
    from .safe_mode import get_safe_mode_manager

    async def _notify(level: str, message: str) -> None:
        if ctx is None:
            return
        await getattr(ctx, level)(message)

    # Resolve the target first so a bad/missing device is reported clearly and
    # never silently executed somewhere else.
    try:
        target = get_inventory().resolve(device)
    except DeviceNotFoundError as exc:
        msg = f"Error: {exc}"
        await _notify("error", msg)
        return msg

    safe_mgr = get_safe_mode_manager(target.title)
    if safe_mgr.is_active:
        await _notify("info", f"Executing on '{target.title}' (safe mode): {command}")
        try:
            result = await asyncio.to_thread(safe_mgr.execute, command)
        except Exception as e:
            result = f"Error executing command in safe mode session: {str(e)}"
    else:
        await _notify("info", f"Executing on '{target.title}': {command}")
        try:
            result = await asyncio.to_thread(_execute_sync, command, target.title)
        except ConnectionError as e:
            result = f"Error: {str(e)}"
        except Exception as e:
            result = f"Error executing command: {str(e)}"

    logger.info(f"Command result: {repr(result)}")
    if result.startswith("Error"):
        await _notify("error", result)
    return result
