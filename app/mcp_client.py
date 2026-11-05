"""MCP client: one long-lived session to the Ekyam Dev MCP server, shared by every request.

The MCP library's connection objects must be opened and closed in the same asyncio task,
so a background task owns the connection and request handlers only call session methods.
If the connection drops, the next call reconnects once and retries.
"""
import asyncio
import json
import logging
from datetime import timedelta

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from . import config
from .auth import AuthError, ServiceAuth

log = logging.getLogger("minted.mcp")


class ToolUnavailable(Exception):
    """The MCP server could not be reached or refused us (network, auth, timeout)."""


def _root_cause(e: BaseException) -> BaseException:
    while isinstance(e, BaseExceptionGroup) and e.exceptions:
        e = e.exceptions[0]
    return e


def describe(e: BaseException) -> str:
    e = _root_cause(e)
    return f"{type(e).__name__}: {e}"


class MCPConnection:
    def __init__(self) -> None:
        self.session: ClientSession | None = None
        self._task: asyncio.Task | None = None
        self._ready: asyncio.Event | None = None
        self._stop: asyncio.Event | None = None
        self._lock = asyncio.Lock()
        self._auth: ServiceAuth | None = None
        self.server_info: dict = {}
        self._broken: asyncio.Event | None = None

    async def _runner(self) -> None:
        try:
            async with streamablehttp_client(config.MCP_URL, auth=self._auth,
                                             timeout=30, sse_read_timeout=config.MCP_TIMEOUT) as (read, write, _):
                async with ClientSession(read, write, message_handler=self._on_message) as session:
                    init = await session.initialize()
                    self.server_info = {"name": init.serverInfo.name, "version": init.serverInfo.version}
                    self.session = session
                    log.info("MCP connected: %s (%s)", config.MCP_URL, self.server_info.get("name"))
                    self._ready.set()
                    await self._stop.wait()
        finally:
            self.session = None
            self._ready.set()  # wake anyone waiting, even on failure

    async def _on_message(self, message) -> None:
        # The transport reports HTTP failures (e.g. a 401 mid-session) as exceptions here and
        # would otherwise leave the waiting call hanging until its timeout: mark the session broken.
        if isinstance(message, Exception):
            log.warning("MCP transport error: %s", describe(message))
            if self._broken:
                self._broken.set()

    async def _connect(self) -> None:
        if self._auth is None:
            try:
                self._auth = ServiceAuth()
            except AuthError as e:
                raise ToolUnavailable(f"sign-in settings: {e}")
        try:
            await self._auth._token()  # sign in first, so a bad client id/secret gives a clear message
        except AuthError as e:
            raise ToolUnavailable(f"sign-in failed: {e}")
        except httpx.HTTPError as e:
            raise ToolUnavailable(f"sign-in failed: {describe(e)}")
        self._ready, self._stop, self._broken = asyncio.Event(), asyncio.Event(), asyncio.Event()
        self._task = asyncio.create_task(self._runner(), name="mcp-connection")
        await self._ready.wait()
        if self.session is None:  # the runner ended before connecting: surface its error
            err = self._task.exception() if self._task.done() else None
            self._task = None
            raise ToolUnavailable(describe(err) if err else "could not connect to the MCP server")

    async def _ensure(self) -> ClientSession:
        async with self._lock:
            if (self.session is None or self._task is None or self._task.done()
                    or (self._broken is not None and self._broken.is_set())):
                await self._disconnect()
                await self._connect()
            return self.session

    async def _disconnect(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        if self._stop:
            self._stop.set()
        try:
            await asyncio.wait_for(task, timeout=5)
        except BaseException:  # already failed or slow to close: cancel it
            task.cancel()
        self.session = None

    async def reset(self) -> None:
        async with self._lock:
            await self._disconnect()

    async def close(self) -> None:
        await self.reset()
        if self._auth:
            await self._auth.close()

    async def call(self, tool: str, args: dict):
        """Run a tool; returns the MCP CallToolResult. Raises ToolUnavailable if unreachable."""
        last: BaseException | None = None
        for attempt in (1, 2):
            try:
                session = await self._ensure()
                return await self._unless_broken(session.call_tool(
                    tool, args, read_timeout_seconds=timedelta(seconds=config.MCP_TIMEOUT)))
            except ToolUnavailable as e:
                last = e
            except Exception as e:  # dropped session, expired session id, timeout...
                last = e
                log.warning("MCP call %s failed (attempt %d): %s", tool, attempt, describe(e))
            await self.reset()
        raise ToolUnavailable(describe(last) if last else "unknown error")

    async def _unless_broken(self, coro):
        """Await coro, but give up at once if the connection breaks (instead of waiting for the timeout)."""
        broken, runner = self._broken, self._task
        call = asyncio.ensure_future(coro)
        watch = asyncio.ensure_future(broken.wait())
        # also stop waiting if the connection task itself ends (the transport crashed, e.g. on a 401)
        try:
            done, _ = await asyncio.wait({call, watch, runner}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            watch.cancel()
        if call in done:
            return call.result()
        if runner in done and not runner.cancelled() and runner.exception():
            call.cancel()
            raise ToolUnavailable(describe(runner.exception()))
        call.cancel()
        raise ToolUnavailable("the MCP connection broke during the call")

    async def list_tools(self) -> list[str]:
        for attempt in (1, 2):
            try:
                session = await self._ensure()
                return [t.name for t in (await self._unless_broken(session.list_tools())).tools]
            except ToolUnavailable:
                if attempt == 2:
                    raise
            except Exception:
                if attempt == 2:
                    raise
            await self.reset()


mcp = MCPConnection()


def parse_result(result) -> dict:
    """Turn an MCP CallToolResult into the tool's own JSON (what the pages expect)."""
    text = "".join(getattr(c, "text", "") or "" for c in (result.content or []))
    if result.isError:
        return {"success": False, "error": text or "The tool reported an error."}
    sc = result.structuredContent
    if isinstance(sc, dict) and sc:
        return sc["result"] if set(sc) == {"result"} and isinstance(sc["result"], dict) else sc
    try:
        data = json.loads(text)
    except ValueError:
        return {"success": False, "error": "The tool's answer was not JSON.", "raw": text[:2000]}
    return data if isinstance(data, dict) else {"success": True, "result": data}


def payload(data: dict) -> dict:
    """Some tool runners wrap the answer as {"payload": {...}}; Excel and warm-up want the inside."""
    return data["payload"] if isinstance(data, dict) and isinstance(data.get("payload"), dict) else data


async def tool_json(tool: str, args: dict | None = None) -> dict:
    if tool not in config.ALLOWED_TOOLS:
        raise ValueError(f"Tool {tool} is not allowed")
    return parse_result(await mcp.call(tool, args or {}))
