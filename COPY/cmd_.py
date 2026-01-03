# COPY.cmd_.py

from __future__ import annotations

import asyncio
from typing import *

from c_utils import now
from MASTER.payload_ import MasterEvent

if TYPE_CHECKING:
    from b_context import MainContext
    from c_log import UnifiedLogger
    from MASTER.payload_ import MasterPayload


class CmdDestrib:
    """
    Manual CLOSE orchestrator.

    Архитектурные инварианты:
    • CmdDestrib НЕ вызывает API биржи
    • CmdDestrib НЕ мутирует position_vars
    • Любое закрытие = synthetic MasterEvent(sig_type="manual")
    • Вся логика исполнения → CopyDestrib / CopyExequter
    """

    def __init__(
        self,
        mc: "MainContext",
        logger: "UnifiedLogger",
        stop_flag: Callable[[], bool],
    ):
        self.mc = mc
        self.logger = logger
        self.stop_flag = stop_flag

        # 🔒 строгая сериализация UI-кнопки
        self._close_lock = asyncio.Lock()

    # ==================================================
    # ENTRY POINT (TG BUTTON)
    # ==================================================
    async def on_close(self, ids: List[int]) -> None:
        """
        Единственная точка manual close через UI.
        """

        if self.stop_flag():
            return

        async with self._close_lock:
            ids = [cid for cid in ids if cid != 0]
            if not ids:
                return

            # ---- UI INTENT LOG ----
            self.mc.log_events.append(
                (0, f"🔴 CLOSE INTENT: manual button → copies [{', '.join(map(str, ids))}]")
            )
            self.mc.cmd_ids = ids
            mev = MasterEvent(
                event="sell",
                method="market",
                symbol="ALL OPENED SYMBOLS",
                pos_side=None,
                partially=False,
                closed=True,
                payload=None,
                sig_type="manual",
                ts=now(),
            )
            payload = self.mc.master_payload
            if not payload:
                self.logger.warning("Manual close ignored: payload not ready")
                return

            await payload.out_queue.put(mev)
