# b_network.py

from __future__ import annotations

import asyncio
import aiohttp
import ssl
from typing import Callable, Optional, TYPE_CHECKING

from a_config import PING_URL, PING_INTERVAL

if TYPE_CHECKING:
    from c_log import UnifiedLogger


# ============================================================
# SSL
# ============================================================

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


# ============================================================
# NETWORK MANAGER
# ============================================================

class NetworkManager:
    """
    Infrastructure-level network/session manager.

    Responsibilities:
        • maintain aiohttp session
        • periodic ping
        • auto-recreate session on failure
        • clean shutdown
    """

    def __init__(
        self,
        logger: "UnifiedLogger",
        proxy_url: Optional[str],
        stop_flag: Callable[[], bool],
    ):
        self.logger = logger
        self.stop_flag = stop_flag

        self.session: Optional[aiohttp.ClientSession] = None
        self._ping_task: Optional[asyncio.Task] = None

        if not proxy_url or proxy_url.strip() == "0":
            proxy_url = None
        self.proxy_url = proxy_url

    # --------------------------------------------------
    # SESSION
    # --------------------------------------------------
    async def initialize_session(self):
        if self.session and not self.session.closed:
            return

        try:
            if self.proxy_url:
                connector = aiohttp.TCPConnector(ssl=False)
                self.session = aiohttp.ClientSession(connector=connector)
                self.logger.info("NetworkManager: session created (proxy, ssl disabled)")
            else:
                # при желании можно вернуть SSL_CTX
                self.session = aiohttp.ClientSession()
                self.logger.info("NetworkManager: session created (direct)")
        except Exception as e:
            self.logger.exception("NetworkManager: session init failed", e)
            raise

    # --------------------------------------------------
    # PING
    # --------------------------------------------------
    async def _ping_once(self) -> bool:
        if not self.session or self.session.closed:
            await self.initialize_session()

        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with self.session.get(PING_URL, timeout=timeout) as resp:
                return resp.status == 200

        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False

        except Exception as e:
            self.logger.exception("NetworkManager: ping exception", e)
            return False
        
    async def _ping_loop(self):
        """
        Background task: keeps session alive.
        Reactive, non-blocking, monotonic-based.
        """
        self.logger.info("NetworkManager: ping loop started")

        next_ping_ts = asyncio.get_event_loop().time()

        try:
            while not self.stop_flag():
                now = asyncio.get_event_loop().time()

                if now >= next_ping_ts:
                    alive = await self._ping_once()

                    if not alive:
                        self.logger.warning(
                            "NetworkManager: ping failed, recreating session"
                        )
                        await self._recreate_session()

                    # планируем следующий ping
                    next_ping_ts = now + PING_INTERVAL

                # короткий yield, высокая отзывчивость
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            pass

        except Exception as e:
            self.logger.exception("NetworkManager: ping loop crashed", e)

        finally:
            self.logger.info("NetworkManager: ping loop stopped")

    # async def _ping_loop(self):
    #     """
    #     Background task: keeps session alive.
    #     """
    #     attempt = 0
    #     self.logger.info("NetworkManager: ping loop started")

    #     try:
    #         while not self.stop_flag():
    #             attempt += 1

    #             alive = await self._ping_once()
    #             if not alive:
    #                 self.logger.warning(
    #                     f"NetworkManager: ping failed, recreating session (attempt {attempt})"
    #                 )
    #                 await self._recreate_session()

    #             await asyncio.sleep(PING_INTERVAL)

    #     except asyncio.CancelledError:
    #         pass

    #     except Exception as e:
    #         self.logger.exception("NetworkManager: ping loop crashed", e)

    #     finally:
    #         # await self.shutdown_session()
    #         self.logger.info("NetworkManager: ping loop stopped")

    async def _recreate_session(self):
        try:
            if self.session and not self.session.closed:
                await self.session.close()
        except Exception as e:
            self.logger.exception("NetworkManager: error closing session", e)

        self.session = None
        await self.initialize_session()

    # --------------------------------------------------
    # PUBLIC API
    # --------------------------------------------------
    def start_ping_loop(self):
        if self._ping_task is None or self._ping_task.done():
            self._ping_task = asyncio.create_task(self._ping_loop())

    async def shutdown_session(self):
        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass

        if self.session and not self.session.closed:
            try:
                await self.session.close()
                self.logger.info("NetworkManager: session closed")
            except Exception as e:
                self.logger.exception("NetworkManager: error closing session", e)

        self.session = None
