# COPY.copy_.py

from __future__ import annotations

import asyncio
from typing import *
# import random

from a_config import TG_LOG_TTL_MS, IS_REPORT
from c_log import UnifiedLogger
from c_utils import now

from .pv_fsm_ import PosMonitorFSM, PreparePnlReport
from .state_ import CopyOrderIntentFactory
from .exequter_ import CopyExequter
from TG.notifier_ import FormatUILogs
from MASTER.payload_ import MasterEvent

if TYPE_CHECKING:
    from .state_ import CopyState
    from b_context import MainContext
    from MASTER.payload_ import MasterPayload


# ==================================================
# SNAPSHOT HASH (STATE CONVERGENCE)
# ==================================================
def snapshot_hash(position_vars: Dict[str, Dict[str, dict]]) -> int:
    h = 0
    for symbol, sides in position_vars.items():
        for pos_side, pv in sides.items():
            qty = pv.get("qty")
            if qty:
                # symbol + side → стабильный сид
                h ^= hash(symbol)
                h ^= hash(pos_side)
                h ^= int(qty * 1e8)  # фиксируем float
    return h


# ==================================================
# SAFE REFRESH
# ==================================================
async def safe_refresh(m: PosMonitorFSM, timeout: float) -> bool:
    try:
        await asyncio.wait_for(m.refresh(), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        return False
    except Exception:
        return False


# ==================================================
# REFRESH WITH CONVERGENCE
# ==================================================
async def refresh_with_retry(
    monitors: Dict[int, PosMonitorFSM],
    *,
    interval: float = 0.1,
    timeout: float = 5.0,
    attempts: int = 50,
) -> None:

    if not monitors:
        return

    # 🔑 базовый снапшот ДО любых refresh
    prev_hash = 0
    for m in monitors.values():
        prev_hash ^= snapshot_hash(m.position_vars)

    for _ in range(attempts):
        tasks = [
            asyncio.create_task(safe_refresh(m, timeout))
            for m in monitors.values()
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

        # 🔍 снапшот ПОСЛЕ refresh
        cur_hash = 0
        for m in monitors.values():
            cur_hash ^= snapshot_hash(m.position_vars)

        # ✅ ИЗМЕНЕНИЕ ЗАФИКСИРОВАНО — ВЫХОДИМ
        if cur_hash != prev_hash:
            return

        await asyncio.sleep(interval)
        

# ==================================================
# COPY DISTRIBUTOR
# ==================================================
class CopyDestrib:
    """
    CopyDestrib — неблокирующий intake + сериализованный executor.
    """

    def __init__(
        self,
        mc: "MainContext",
        logger: UnifiedLogger,
        copy_state: CopyState,
        stop_flag: Callable[[], bool],
    ):
        self.mc = mc
        self.logger = logger
        self.copy_state = copy_state
        self.stop_flag = stop_flag

        self.payload: "MasterPayload" | None = None

        self._stop_signal_loop = True
        self._stop_tracker = True
        self._last_log_flush_ts: int = 0
        self._pnl_results: List = []

        self.intent_factory = CopyOrderIntentFactory(self.mc)
        self.reset_pv_state = PreparePnlReport(self.mc, self.logger)
        self._exequter = CopyExequter(self.mc, self.logger)

        # 🔒 строгая сериализация исполнения сигналов
        self._exec_sem = asyncio.Semaphore(1)

    # ==================================================
    # PAYLOAD
    # ==================================================

    def attach_payload(self, payload: "MasterPayload"):
        self.payload = payload
        self.logger.info("CopyDestrib: payload attached")

    # ==================================================
    # STOP API
    # ==================================================

    def stop_signal_loop(self):
        self.logger.info("CopyDestrib: stop_signal_loop()")
        self._stop_signal_loop = True

    # ==================================================
    # UI LOG FLUSH WITH TTL
    # ==================================================

    async def _flush_notify_with_ttl(self) -> None:
        """
        Flushes accumulated UI logs with TTL.
        Non-blocking for main pipeline.
        """
        if not self.mc.log_events:
            return

        now_ts = now()

        if (
            self._last_log_flush_ts == 0
            or now_ts - self._last_log_flush_ts >= TG_LOG_TTL_MS
        ):
            texts = FormatUILogs.flush_log_events(self.mc.log_events)

            if texts or self._pnl_results:
                self._last_log_flush_ts = now_ts

            if texts:
                await self.mc.tg_notifier.send_block(texts)

            if IS_REPORT:
                # 🔒 финальный отчёт
                if self._pnl_results:
                    texts: list[str] = []
                    texts.extend(FormatUILogs.format_general_report(self._pnl_results))
                    texts.append(FormatUILogs.format_general_summary(self._pnl_results))
                    self._pnl_results.clear()
                    await self.mc.tg_notifier.send_block(texts)

    # ==================================================
    # MANUAL CLOSE EXPANDER
    # ==================================================

    async def _expand_manual_close(
        self,
        mev: MasterEvent,
    ) -> List[MasterEvent]:
        """
        Expands manual CLOSE intent into atomic close events.
        """
        events: List[MasterEvent] = []

        for cid in self.mc.cmd_ids:
            rt = self.copy_state.ensure_copy_state(cid)
            if not rt:
                continue

            position_vars = rt.get("position_vars") or {}

            for symbol, sides in position_vars.items():
                for pos_side, pv in sides.items():
                    if not pv.get("in_position"):
                        continue

                    qty = pv.get("qty")
                    if not qty or qty <= 0:
                        continue

                    sub = MasterEvent(
                        event="sell",
                        method="market",
                        symbol=symbol,
                        pos_side=pos_side,
                        partially=False,
                        closed=True,
                        sig_type="manual",
                        payload={
                            "qty": qty,
                            "reduce_only": True,
                            "leverage": pv.get("leverage"),
                            "open_type": pv.get("margin_mode"),
                        },
                        ts=mev.ts,
                    )

                    # 🔒 жёсткая привязка к конкретному copy-id
                    sub._cid = cid
                    events.append(sub)

        return events

    # ==================================================
    # INTERNAL: FAN-OUT (COPY / LOG ONLY)
    # ==================================================

    async def _broadcast_to_copies(
        self,
        mev: "MasterEvent",
        monitors: Dict[int, PosMonitorFSM],
    ):
        if mev.sig_type not in ("copy", "log"):
            return

        # UI лог мастера
        self.mc.log_events.append((0, mev))

        tasks: list[asyncio.Task] = []

        for cid, cfg in self.mc.copy_configs.items():

            if cid == 0 or not cfg or not cfg.get("enabled"):
                continue

            rt = self.copy_state.ensure_copy_state(cid)
            if not rt:
                continue

            tasks.append(
                asyncio.create_task(
                    self._exequter.handle_copy_event(cid, cfg, rt, mev, monitors)
                )
            )

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=False)

    # ==================================================
    # EXECUTOR (SERIALIZED)
    # ==================================================

    async def _execute_signal(self, mev: "MasterEvent"):
        async with self._exec_sem:

            local_monitors: Dict[int, PosMonitorFSM] = {}
            results: list[dict] = []

            try:
                if mev.sig_type == "manual":
                    # ⚠️ manual-event — уже атомарный
                    cid = getattr(mev, "_cid", None)
                    if cid is None:
                        return

                    cfg = self.mc.copy_configs.get(cid)
                    rt = self.copy_state.ensure_copy_state(cid)
                    if not cfg or not rt:
                        return

                    await self._exequter.handle_copy_event(
                        cid, cfg, rt, mev, local_monitors
                    )

                else:
                    # print("_broadcast_to_copies")
                    await self._broadcast_to_copies(mev, local_monitors)

                ids = list(local_monitors.keys())

                if mev.method.upper() == "MARKET" and local_monitors:
                    await refresh_with_retry(local_monitors)

            except Exception:
                self.logger.exception(
                    "[CopyDestrib] execute_signal failed",
                )

            finally:
                if IS_REPORT:
                    results = await self.reset_pv_state.assum_positions(ids)
                    if results:
                        self._pnl_results.extend(results)

                # 🕒 TTL logs
                await self._flush_notify_with_ttl()

    async def _execute_and_ack(self, mev: "MasterEvent"):
        try:
            await self._execute_signal(mev)
        except Exception:
            self.logger.exception("[CopyDestrib] execute_and_ack failed")
        finally:
            # ✅ ACK ТОЛЬКО ПОСЛЕ ОБРАБОТКИ
            self.payload.out_queue.task_done()

    # ==================================================
    # SIGNAL LOOP (INTAKE)
    # ==================================================

    async def signal_loop(self):
        if not self.payload:
            self.logger.error("CopyDestrib: payload not attached")
            return

        self.logger.info("CopyDestrib: signal_loop STARTED")

        self._stop_signal_loop = False
        self._stop_tracker = False

        # ожидание разрешения торговли
        while not self.stop_flag() and not self._stop_signal_loop:
            master_rt = self.mc.copy_configs.get(0, {}).get("cmd_state", {})
            if master_rt.get("trading_enabled") and not master_rt.get("stop_flag"):
                break
            await asyncio.sleep(0.1)

        if self._stop_signal_loop:
            return

        self.logger.info("CopyDestrib: READY")

        while not self.stop_flag() and not self._stop_signal_loop:
            try:
                # ======================================================
                # 1️⃣ берём ОДНО master-событие
                # ======================================================
                mev: "MasterEvent" = await self.payload.out_queue.get()
                # self.payload.out_queue.task_done()

                print(
                    "\n=== MASTER EVENT ===",
                    f"\n ts={mev.ts}",
                    f"\n event={mev.event}",
                    f"\n method={mev.method}",
                    f"\n symbol={mev.symbol}",
                    f"\n side={mev.pos_side}",
                    f"\n partially={mev.partially}",
                    f"\n closed={mev.closed}",
                    f"\n sig_type={mev.sig_type}",
                    f"\n payload={mev.payload}",
                    "\n====================\n",
                )

                if self._stop_tracker:
                    break

                if mev.sig_type == "manual":
                    expanded = await self._expand_manual_close(mev)

                    for sub_mev in expanded:
                        task = asyncio.create_task(self._execute_signal(sub_mev))
                        self.mc.background_tasks.add(task)
                        task.add_done_callback(self.mc.background_tasks.discard)

                    # ✅ ACK ровно ОДИН — за исходный manual intent
                    self.payload.out_queue.task_done()
                    self.mc.cmd_ids.clear()

                else:
                    task = asyncio.create_task(self._execute_and_ack(mev))
                    self.mc.background_tasks.add(task)
                    task.add_done_callback(self.mc.background_tasks.discard)

            except asyncio.CancelledError:
                break

        self.logger.info("CopyDestrib: signal_loop FINISHED")

    #     # # TEST MODE: изоляция от саморепликации
    #     # if TEST_MODE:
    #     #     mev = copy.deepcopy(mev)
    #     #     mev.symbol = "FET_USDT"
