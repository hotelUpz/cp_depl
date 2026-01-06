# # # MASTER.payload_.py

# # from __future__ import annotations

# # import asyncio
# # from dataclasses import dataclass, field
# # from typing import *

# # from MASTER.state_ import PosVarSetup
# # from c_utils import Utils, now

# # if TYPE_CHECKING:
# #     from MASTER.state_ import SignalCache, SignalEvent
# #     from b_context import MainContext
# #     from c_log import UnifiedLogger


# # # =====================================================================
# # # HL PROTOCOL
# # # =====================================================================

# # HL_EVENT = Literal["buy", "sell", "canceled", "filled"]
# # METHOD = Literal["market", "limit", "trigger", "oco"]


# # # =====================================================================
# # # MASTER EVENT
# # # =====================================================================

# # @dataclass
# # class MasterEvent:
# #     # MasterEvent may contain _cid for manual routing
# #     event: HL_EVENT
# #     method: METHOD
# #     symbol: str
# #     pos_side: str
# #     partially: bool
# #     closed: bool
# #     payload: Dict[str, Any]
# #     sig_type: Literal["copy", "log", "manual"]
# #     ts: int = field(default_factory=now)

# # # =====================================================================
# # # MASTER PAYLOAD
# # # =====================================================================

# # class MasterPayload:
# #     """
# #     High-level агрегатор сигналов мастера.
# #     """

# #     def __init__(
# #         self,
# #         cache: "SignalCache",
# #         mc: "MainContext",
# #         logger: "UnifiedLogger",
# #         stop_flag: Callable,
# #     ):
# #         self.cache = cache
# #         self.mc = mc
# #         self.logger = logger
# #         self.stop_flag = stop_flag

# #         self._pending: List[MasterEvent] = []
# #         self._stop = False

# #         self._pos_state: Dict[Tuple[str, str], Dict[str, Any]] = {}
# #         self._last_deal: Dict[Tuple[str, str], Dict[str, Any]] = {}
# #         self._attached_oco: Dict[str, dict] = {}

# #         self.out_queue = asyncio.Queue(maxsize=1000)

# #     # ==========================================================
# #     def stop(self):
# #         self._stop = True
# #         self.mc.pos_vars_root.clear()
# #         self.logger.info("MasterPayload: stop requested")

# #     # ==========================================================
# #     async def run(self):
# #         self.logger.info("MasterPayload READY")

# #         while not self._stop and not self.stop_flag():
# #             await self.cache._event_notify.wait()
# #             raw_events = await self.cache.pop_events()

# #             for ev in raw_events:
# #                 await self._route(ev)

# #             out = self._pending[:]
# #             self._pending.clear()

# #             for mev in out:
# #                 await self.out_queue.put(mev)

# #         self.logger.info("MasterPayload STOPPED")

# #     # ==========================================================
# #     def _ensure_pos_vars(self, symbol: str, pos_side: str) -> dict:
# #         PosVarSetup.set_pos_defaults(
# #             self.mc.pos_vars_root,
# #             symbol,
# #             pos_side,
# #             instruments_data=self.mc.instruments_data,
# #         )

# #         return self.mc.pos_vars_root.get(symbol, {}).get(pos_side, {})

# #     # ==========================================================
# #     def _fix_price(self, raw, symbol=None, side=None):
# #         for k in ("dealAvgPrice", "avgPrice", "price", "openAvgPrice"):
# #             if raw.get(k):
# #                 return Utils.safe_float(raw[k])
# #         return self._last_deal.get((symbol, side), {}).get("price")

# #     # ==========================================================
# #     def _is_stale_snapshot(self, key, raw) -> bool:
# #         upd = raw.get("updateTime") or raw.get("timestamp") or 0
# #         hold = raw.get("holdVol")

# #         st = self._pos_state.get(key)
# #         if not st:
# #             self._pos_state[key] = {"upd": upd, "hold": hold}
# #             return False

# #         if hold == 0:
# #             self._pos_state[key] = {"upd": upd, "hold": hold}
# #             return False

# #         if upd < st["upd"]:
# #             return True
# #         if upd == st["upd"] and hold == st["hold"]:
# #             return True

# #         self._pos_state[key] = {"upd": upd, "hold": hold}
# #         return False

# #     # ==========================================================
# #     async def _route(self, ev: "SignalEvent"):
# #         et = ev.event_type
# #         symbol, pos_side = ev.symbol, ev.pos_side

# #         # ---------------- ATTACHED OCO ----------------
# #         if et == "stop_attached":
# #             self._attached_oco[symbol] = {
# #                 "tp": Utils.safe_float(ev.raw.get("takeProfitPrice")),
# #                 "sl": Utils.safe_float(ev.raw.get("stopLossPrice")),
# #             }
# #             return

# #         if not pos_side:
# #             return

# #         pv = self._ensure_pos_vars(symbol, pos_side)

# #         # ---------------- LIMIT OPEN / CLOSE ----------------
# #         if et in ("open_limit", "close_limit") and ev.raw.get("state") == 2:
# #             pv["_last_exec_source"] = "limit"

# #             await self._emit(
# #                 event="buy" if et == "open_limit" else "sell",
# #                 method="limit",
# #                 symbol=symbol,
# #                 pos_side=pos_side,
# #                 partially=False,
# #                 payload={
# #                     "order_id": ev.raw.get("orderId"),
# #                     "qty": Utils.safe_float(ev.raw.get("vol")),
# #                     "price": Utils.safe_float(ev.raw.get("price")),
# #                     "leverage": ev.raw.get("leverage"),
# #                     "open_type": ev.raw.get("openType"),
# #                     "reduce_only": bool(ev.raw.get("reduceOnly")),
# #                     "used_margin": Utils.safe_float(ev.raw.get("usedMargin")),
# #                 },
# #                 sig_type="copy",
# #                 ev_raw=ev,
# #             )
# #             return

# #         # ---------------- LIMIT CANCEL ----------------
# #         if et in ("order_cancelled", "order_invalid"):
# #             pv["_last_exec_source"] = None

# #             await self._emit(
# #                 event="canceled",
# #                 method="limit",
# #                 symbol=symbol,
# #                 pos_side=pos_side,
# #                 partially=False,
# #                 payload={"order_id": ev.raw.get("orderId")},
# #                 sig_type="copy",
# #                 ev_raw=ev,
# #             )
# #             return

# #         # ---------------- DEAL ----------------
# #         if et == "deal":
# #             price = Utils.safe_float(ev.raw.get("price"))
# #             if price:
# #                 self._last_deal[(symbol, pos_side)] = {"price": price, "ts": ev.ts}
# #             return

# #         # ---------------- TRIGGER ----------------
# #         if et in ("plan_order", "plan_executed", "plan_cancelled"):
# #             trigger_price = Utils.safe_float(
# #                 ev.raw.get("triggerPrice") or ev.raw.get("price")
# #             )
# #             if not trigger_price:
# #                 return

# #             pv["_last_exec_source"] = "trigger"

# #             if et == "plan_executed":
# #                 event, sig = "filled", "log"
# #             elif et == "plan_order":
# #                 event, sig = "buy" if ev.raw.get("side") in (1, 3) else "sell", "copy"
# #             else:
# #                 event, sig = "canceled", "copy"

# #             await self._emit(
# #                 event=event,
# #                 method="trigger",
# #                 symbol=symbol,
# #                 pos_side=pos_side,
# #                 partially=False,
# #                 payload={
# #                     "order_id": ev.raw.get("orderId"),
# #                     "qty": Utils.safe_float(ev.raw.get("vol")),
# #                     "trigger_price": trigger_price,
# #                     "leverage": ev.raw.get("leverage"),
# #                     "open_type": ev.raw.get("openType"),
# #                     "reduce_only": bool(ev.raw.get("reduceOnly")),
# #                     "trigger_exec": ev.raw.get("triggerType"),
# #                 },
# #                 sig_type=sig,
# #                 ev_raw=ev,
# #             )
# #             return

# #         # ---------------- POSITION SNAPSHOT ----------------
# #         if et in ("position_opened", "position_closed"):
# #             await self._on_position_snapshot(ev, pv)

# #     # ==========================================================
# #     async def _on_position_snapshot(self, ev: "SignalEvent", pv: dict):
# #         raw = ev.raw
# #         symbol, pos_side = ev.symbol, ev.pos_side
# #         key = (symbol, pos_side)

# #         if self._is_stale_snapshot(key, raw):
# #             return

# #         qty_prev = pv["qty"]
# #         qty_cur = Utils.safe_float(raw.get("holdVol"), 0.0)

# #         if qty_prev == qty_cur:
# #             return

# #         price = Utils.to_human_digit(self._fix_price(raw, symbol, pos_side))
# #         last_src = pv["_last_exec_source"]

# #         oco = self._attached_oco.pop(symbol, None)

# #         if oco:
# #             pv["_attached_tp"] = oco.get("tp")
# #             pv["_attached_sl"] = oco.get("sl")

# #         delta = abs(qty_cur - qty_prev)

# #         # ================= BUY =================
# #         if qty_cur > qty_prev:
# #             pv["qty"] = qty_cur
# #             pv["in_position"] = True

# #             payload = {
# #                 "qty": delta,
# #                 "price": price,
# #                 "leverage": raw.get("leverage"),
# #                 "open_type": raw.get("openType"),
# #                 "reduce_only": False,
# #                 "qty_delta": delta,
# #                 "qty_before": qty_prev,
# #                 "qty_after": qty_cur,
# #             }

# #             if pv.get("_attached_tp") is not None:
# #                 payload["tp_price"] = pv["_attached_tp"]
# #             if pv.get("_attached_sl") is not None:
# #                 payload["sl_price"] = pv["_attached_sl"]

# #             # sig_type = (
# #             #     "log"
# #             #     if last_src in ("limit", "trigger") and qty_prev == 0
# #             #     else "copy"
# #             # )
# #             sig_type = "log" if last_src in ("limit", "trigger") else "copy"

# #             await self._emit(
# #                 event="buy",
# #                 method="market",
# #                 symbol=symbol,
# #                 pos_side=pos_side,
# #                 partially=qty_prev > 0,
# #                 payload=payload,
# #                 sig_type=sig_type,
# #                 ev_raw=ev,
# #             )

# #             pv["_attached_tp"] = None
# #             pv["_attached_sl"] = None

# #         # ================= SELL =================
# #         elif qty_cur < qty_prev:
# #             pv["qty"] = qty_cur
# #             pv["in_position"] = qty_cur > 0

# #             is_full_close = qty_cur == 0
# #             sig_type = (
# #                 "log"
# #                 if last_src in ("limit", "trigger") and is_full_close
# #                 else "copy"
# #             )

# #             payload = {
# #                 "qty": delta,
# #                 "price": price,
# #                 "leverage": raw.get("leverage"),
# #                 "open_type": raw.get("openType"),
# #                 "reduce_only": True,
# #                 "qty_delta": delta,
# #                 "qty_before": qty_prev,
# #                 "qty_after": qty_cur,
# #             }

# #             await self._emit(
# #                 event="sell",
# #                 method="market",
# #                 symbol=symbol,
# #                 pos_side=pos_side,
# #                 partially=qty_cur > 0,
# #                 payload=payload,
# #                 sig_type=sig_type,
# #                 ev_raw=ev,
# #                 closed=is_full_close,
# #             )

# #             if is_full_close:
# #                 self._pos_state.pop(key, None)
# #                 self._last_deal.pop(key, None)

# #         if qty_prev == 0 and qty_cur > 0:
# #             pv["entry_price"] = price

# #         pv["avg_price"] = price
# #         pv["_last_exec_source"] = None

# #     # ==========================================================
# #     async def _emit(
# #         self,
# #         *,
# #         event: HL_EVENT,
# #         method: METHOD,
# #         symbol: str,
# #         pos_side: str,
# #         partially: bool,
# #         payload: Dict[str, Any],
# #         sig_type: Literal["copy", "log"],
# #         ev_raw: Optional["SignalEvent"],
# #         closed: bool = False,
# #     ):
# #         exec_ts = now()
# #         raw_ts = ev_raw.ts if ev_raw else None

# #         payload = dict(payload)
# #         payload["exec_ts"] = exec_ts
# #         payload["latency_ms"] = exec_ts - raw_ts if raw_ts else None

# #         self._pending.append(
# #             MasterEvent(
# #                 event=event,
# #                 method=method,
# #                 symbol=symbol,
# #                 pos_side=pos_side,
# #                 partially=partially,
# #                 closed=closed,
# #                 payload=payload,
# #                 sig_type=sig_type,
# #                 ts=exec_ts,
# #             )
# #         )




# # COPY.copy_.py

# from __future__ import annotations

# import asyncio
# from typing import *
# # import random

# from a_config import TG_LOG_TTL_MS, IS_REPORT
# from c_log import UnifiedLogger
# from c_utils import now

# from .pv_fsm_ import PosMonitorFSM, PreparePnlReport
# from .state_ import CopyOrderIntentFactory
# from .exequter_ import CopyExequter
# from TG.notifier_ import FormatUILogs
# from MASTER.payload_ import MasterEvent

# if TYPE_CHECKING:
#     from .state_ import CopyState
#     from b_context import MainContext
#     from MASTER.payload_ import MasterPayload


# # ==================================================
# # SNAPSHOT HASH (STATE CONVERGENCE)
# # ==================================================
# def snapshot_hash(position_vars: Dict[str, Dict[str, dict]]) -> int:
#     h = 0
#     for symbol, sides in position_vars.items():
#         for pos_side, pv in sides.items():
#             qty = pv.get("qty")
#             if qty:
#                 # symbol + side → стабильный сид
#                 h ^= hash(symbol)
#                 h ^= hash(pos_side)
#                 h ^= int(qty * 1e8)  # фиксируем float
#     return h

# # ==================================================
# # SAFE REFRESH
# # ==================================================
# async def safe_refresh(m: PosMonitorFSM, timeout: float) -> bool:
#     try:
#         await asyncio.wait_for(m.refresh(), timeout=timeout)
#         return True
#     except asyncio.TimeoutError:
#         return False
#     except Exception:
#         return False

# # ==================================================
# # REFRESH WITH CONVERGENCE (RATE-SAFE)
# # ==================================================
# async def refresh_with_retry(
#     monitors: Dict[int, PosMonitorFSM],
#     *,
#     base_interval: float = 0.05,   # минимальный интервал
#     max_interval: float = 0.5,     # верхний предел backoff
#     timeout: float = 4.0,         # абсолютный дедлайн
#     max_iters: int = 20,           # 🔒 <= 50 refresh за окно
#     backoff: float = 1.25,         # мягкий рост
# ) -> None:

#     if not monitors:
#         return

#     start_ts = asyncio.get_event_loop().time()

#     # 🔑 базовый снапшот ДО refresh
#     prev_hash = 0
#     for m in monitors.values():
#         prev_hash ^= snapshot_hash(m.position_vars)

#     interval = base_interval

#     for _ in range(max_iters):

#         # ⏱️ hard timeout guard
#         if asyncio.get_event_loop().time() - start_ts >= timeout:
#             return

#         tasks = [
#             asyncio.create_task(safe_refresh(m, timeout))
#             for m in monitors.values()
#         ]
#         await asyncio.gather(*tasks, return_exceptions=True)

#         # 🔍 снапшот ПОСЛЕ refresh
#         cur_hash = 0
#         for m in monitors.values():
#             cur_hash ^= snapshot_hash(m.position_vars)

#         # ✅ convergence зафиксирован
#         if cur_hash != prev_hash:
#             return

#         # 📈 динамический backoff
#         await asyncio.sleep(interval)
#         interval = min(interval * backoff, max_interval)

# # async def refresh_with_retry(
# #     monitors: Dict[int, PosMonitorFSM],
# #     *,
# #     interval: float = 0.05,
# #     timeout: float = 10.0,
# #     attempts: int = 200,
# # ) -> None:

# #     if not monitors:
# #         return

# #     # 🔑 базовый снапшот ДО любых refresh
# #     prev_hash = 0
# #     for m in monitors.values():
# #         prev_hash ^= snapshot_hash(m.position_vars)

# #     for _ in range(attempts):
# #         tasks = [
# #             asyncio.create_task(safe_refresh(m, timeout))
# #             for m in monitors.values()
# #         ]
# #         await asyncio.gather(*tasks, return_exceptions=True)

# #         # 🔍 снапшот ПОСЛЕ refresh
# #         cur_hash = 0
# #         for m in monitors.values():
# #             cur_hash ^= snapshot_hash(m.position_vars)

# #         # ✅ ИЗМЕНЕНИЕ ЗАФИКСИРОВАНО — ВЫХОДИМ
# #         if cur_hash != prev_hash:
# #             return

# #         await asyncio.sleep(interval)
        

# # ==================================================
# # COPY DISTRIBUTOR
# # ==================================================
# class CopyDestrib:
#     """
#     CopyDestrib — неблокирующий intake + сериализованный executor.
#     """

#     def __init__(
#         self,
#         mc: "MainContext",
#         logger: UnifiedLogger,
#         copy_state: CopyState,
#         stop_flag: Callable[[], bool],
#     ):
#         self.mc = mc
#         self.logger = logger
#         self.copy_state = copy_state
#         self.stop_flag = stop_flag

#         self.payload: Optional["MasterPayload"] = None

#         self._stop_signal_loop = True
#         self._stop_tracker = True
#         self._last_log_flush_ts: int = 0
#         self._pnl_results: List = []

#         self.intent_factory = CopyOrderIntentFactory(self.mc)
#         self.reset_pv_state = PreparePnlReport(self.mc, self.logger)
#         self._exequter = CopyExequter(self.mc, self.logger)

#         # 🔒 строгая сериализация исполнения сигналов
#         self._exec_sem = asyncio.Semaphore(1)

#     # ==================================================
#     # PAYLOAD
#     # ==================================================

#     def attach_payload(self, payload: "MasterPayload"):
#         self.payload = payload
#         self.logger.info("CopyDestrib: payload attached")

#     # ==================================================
#     # STOP API
#     # ==================================================

#     def stop_signal_loop(self):
#         self.logger.info("CopyDestrib: stop_signal_loop()")
#         self._stop_signal_loop = True

#     # ==================================================
#     # UI LOG FLUSH WITH TTL
#     # ==================================================

#     async def _flush_notify_with_ttl(self) -> None:
#         """
#         Flushes accumulated UI logs with TTL.
#         Non-blocking for main pipeline.
#         """
#         if not self.mc.log_events:
#             return

#         now_ts = now()

#         if (
#             self._last_log_flush_ts == 0
#             or now_ts - self._last_log_flush_ts >= TG_LOG_TTL_MS
#         ):
#             texts = FormatUILogs.flush_log_events(self.mc.log_events)

#             if texts or self._pnl_results:
#                 self._last_log_flush_ts = now_ts

#             if texts:
#                 await self.mc.tg_notifier.send_block(texts)

#             if IS_REPORT:
#                 # 🔒 финальный отчёт
#                 if self._pnl_results:
#                     texts: list[str] = []
#                     texts.extend(FormatUILogs.format_general_report(self._pnl_results))
#                     texts.append(FormatUILogs.format_general_summary(self._pnl_results))
#                     self._pnl_results.clear()
#                     await self.mc.tg_notifier.send_block(texts)

#     # ==================================================
#     # MANUAL CLOSE EXPANDER
#     # ==================================================

#     async def _expand_manual_close(
#         self,
#         mev: MasterEvent,
#     ) -> List[MasterEvent]:
#         """
#         Expands manual CLOSE intent into atomic close events.
#         """
#         events: List[MasterEvent] = []

#         for cid in self.mc.cmd_ids:
#             rt = self.copy_state.ensure_copy_state(cid)
#             if not rt:
#                 continue

#             position_vars = rt.get("position_vars") or {}

#             for symbol, sides in position_vars.items():
#                 for pos_side, pv in sides.items():
#                     if not pv.get("in_position"):
#                         continue

#                     qty = pv.get("qty")
#                     if not qty or qty <= 0:
#                         continue

#                     sub = MasterEvent(
#                         event="sell",
#                         method="market",
#                         symbol=symbol,
#                         pos_side=pos_side,
#                         partially=False,
#                         closed=True,
#                         sig_type="manual",
#                         payload={
#                             "qty": qty,
#                             "reduce_only": True,
#                             "leverage": pv.get("leverage"),
#                             "open_type": pv.get("margin_mode"),
#                         },
#                         ts=mev.ts,
#                     )

#                     # 🔒 жёсткая привязка к конкретному copy-id
#                     sub._cid = cid
#                     events.append(sub)

#         return events

#     # ==================================================
#     # INTERNAL: FAN-OUT (COPY / LOG ONLY)
#     # ==================================================

#     async def _broadcast_to_copies(
#         self,
#         mev: "MasterEvent",
#         monitors: Dict[int, PosMonitorFSM],
#     ):
#         if mev.sig_type not in ("copy", "log"):
#             return

#         # UI лог мастера
#         self.mc.log_events.append((0, mev))

#         tasks: list[asyncio.Task] = []

#         for cid, cfg in self.mc.copy_configs.items():

#             if cid == 0 or not cfg or not cfg.get("enabled"):
#                 continue

#             rt = self.copy_state.ensure_copy_state(cid)
#             if not rt:
#                 continue

#             tasks.append(
#                 asyncio.create_task(
#                     self._exequter.handle_copy_event(cid, cfg, rt, mev, monitors)
#                 )
#             )

#         if tasks:
#             await asyncio.gather(*tasks, return_exceptions=False)

#     # ==================================================
#     # EXECUTOR (SERIALIZED)
#     # ==================================================

#     async def _execute_signal(self, mev: "MasterEvent"):
#         async with self._exec_sem:

#             local_monitors: Dict[int, PosMonitorFSM] = {}
#             results: list[dict] = []

#             try:
#                 if mev.sig_type == "manual":
#                     # ⚠️ manual-event — уже атомарный
#                     cid = getattr(mev, "_cid", None)
#                     if cid is None:
#                         return

#                     cfg = self.mc.copy_configs.get(cid)
#                     rt = self.copy_state.ensure_copy_state(cid)
#                     if not cfg or not rt:
#                         return

#                     await self._exequter.handle_copy_event(
#                         cid, cfg, rt, mev, local_monitors
#                     )

#                 else:
#                     # print("_broadcast_to_copies")
#                     await self._broadcast_to_copies(mev, local_monitors)

#                 ids = list(local_monitors.keys())

#                 if mev.method.upper() == "MARKET" and local_monitors:
#                     await refresh_with_retry(local_monitors)

#             except Exception:
#                 self.logger.exception(
#                     "[CopyDestrib] execute_signal failed",
#                 )

#             finally:
#                 if IS_REPORT:
#                     results = await self.reset_pv_state.assum_positions(ids)
#                     if results:
#                         self._pnl_results.extend(results)

#                 # 🕒 TTL logs
#                 await self._flush_notify_with_ttl()

#     async def _execute_and_ack(self, mev: "MasterEvent"):
#         try:
#             await self._execute_signal(mev)
#         except Exception:
#             self.logger.exception("[CopyDestrib] execute_and_ack failed")
#         finally:
#             # ✅ ACK ТОЛЬКО ПОСЛЕ ОБРАБОТКИ
#             self.payload.out_queue.task_done()

#     # ==================================================
#     # SIGNAL LOOP (INTAKE)
#     # ==================================================

#     async def signal_loop(self):
#         if not self.payload:
#             self.logger.error("CopyDestrib: payload not attached")
#             return

#         self.logger.info("CopyDestrib: signal_loop STARTED")

#         self._stop_signal_loop = False
#         self._stop_tracker = False

#         # ожидание разрешения торговли
#         while not self.stop_flag() and not self._stop_signal_loop:
#             master_rt = self.mc.copy_configs.get(0, {}).get("cmd_state", {})
#             if master_rt.get("trading_enabled") and not master_rt.get("stop_flag"):
#                 break
#             await asyncio.sleep(0.1)

#         if self._stop_signal_loop:
#             return

#         self.logger.info("CopyDestrib: READY")

#         while not self.stop_flag() and not self._stop_signal_loop:
#             try:
#                 # ======================================================
#                 # 1️⃣ берём ОДНО master-событие
#                 # ======================================================
#                 mev: "MasterEvent" = await self.payload.out_queue.get()
#                 # self.payload.out_queue.task_done()

#                 print(
#                     "\n=== MASTER EVENT ===",
#                     f"\n ts={mev.ts}",
#                     f"\n event={mev.event}",
#                     f"\n method={mev.method}",
#                     f"\n symbol={mev.symbol}",
#                     f"\n side={mev.pos_side}",
#                     f"\n partially={mev.partially}",
#                     f"\n closed={mev.closed}",
#                     f"\n sig_type={mev.sig_type}",
#                     f"\n payload={mev.payload}",
#                     "\n====================\n",
#                 )

#                 if self._stop_tracker:
#                     break

#                 if mev.sig_type == "manual":
#                     expanded = await self._expand_manual_close(mev)

#                     for sub_mev in expanded:
#                         task = asyncio.create_task(self._execute_signal(sub_mev))
#                         self.mc.background_tasks.add(task)
#                         task.add_done_callback(self.mc.background_tasks.discard)

#                     # ✅ ACK ровно ОДИН — за исходный manual intent
#                     self.payload.out_queue.task_done()
#                     self.mc.cmd_ids.clear()

#                 else:
#                     # task = asyncio.create_task(self._execute_and_ack(mev))
#                     # self.mc.background_tasks.add(task)
#                     # task.add_done_callback(self.mc.background_tasks.discard)
#                     pass

#             except asyncio.CancelledError:
#                 break

#         self.logger.info("CopyDestrib: signal_loop FINISHED")

#     #     # # TEST MODE: изоляция от саморепликации
#     #     # if TEST_MODE:
#     #     #     mev = copy.deepcopy(mev)
#     #     #     mev.symbol = "FET_USDT"

# # COPY.exequter_.py

# from __future__ import annotations

# import asyncio
# from typing import *

# from b_context import PosVarTemplate
# from c_utils import now
# from .pv_fsm_ import PosMonitorFSM
# from .state_ import CopyOrderIntentFactory

# if TYPE_CHECKING:
#     from c_log import UnifiedLogger
#     from .state_ import CopyOrderIntent
#     from b_context import MainContext
#     from MASTER.payload_ import MasterEvent, MasterPayload
#     from API.MX.client import MexcClient


# # ======================================================================
# # POSITION ACCESS
# # ======================================================================
# def get_copy_pos(rt: dict, symbol: str, side: str) -> dict:
#     pv_root = rt.setdefault("position_vars", {})
#     sym = pv_root.setdefault(symbol, {})
#     if side not in sym:
#         sym[side] = PosVarTemplate.base_template()
#     return sym[side]


# # ==================================================
# # LATENCY (DEBUG PRINT ONLY)
# # ==================================================
# def _record_latency(
#     cid: int,
#     mev: "MasterEvent",
#     res: Optional[dict],
# ) -> None:
#     """
#     Debug-only latency print.
#     No storage, no side effects.
#     """

#     if not res or not isinstance(res, dict):
#         return

#     master_ts = getattr(mev, "ts", None)
#     if not master_ts:
#         return

#     copy_ts = res.get("ts")
#     if not copy_ts:
#         return

#     latency = copy_ts - master_ts

#     print(
#         f"[LATENCY]"
#         f" cid={cid}"
#         f" {mev.symbol}"
#         f" {mev.pos_side}"
#         f" latency={latency}ms"
#         # f" master_ts={master_ts}"
#         # f" copy_ts={copy_ts}"
#     )  


# class CopyExequter:
#     def __init__(
#         self,
#         mc: "MainContext",
#         logger: UnifiedLogger
#     ):
#         self.mc = mc
#         self.logger = logger

#         self.payload: Optional["MasterPayload"] = None
#         self.intent_factory = CopyOrderIntentFactory(self.mc)

#     # ==================================================
#     # INTERNAL: COPY EVENT
#     # ==================================================
#     async def handle_copy_event(
#         self,
#         cid: int,
#         cfg: dict,
#         rt: dict,
#         mev: MasterEvent,
#         monitors: Dict[int, PosMonitorFSM],
#     ):

#         # --------------------------------------------------
#         # CLIENT
#         # --------------------------------------------------
#         client: "MexcClient" = self.mc.copy_runtime_states.get(cid, {}).get("mc_client", None)
#         if not client:
#             return
        
#         # --------------------------------------------------
#         # orders_vars
#         # --------------------------------------------------
#         ov_root = rt.setdefault("orders_vars", {})
#         sym_root = ov_root.setdefault(mev.symbol, {})
#         side_root = sym_root.setdefault(mev.pos_side, {})
        
#         # --------------------------------------------------
#         # CANCEL (НЕ ЧЕРЕЗ INTENT)
#         # --------------------------------------------------
#         if mev.event == "canceled":
#             master_oid = mev.payload.get("order_id")
#             if not master_oid:
#                 self.mc.log_events.append(
#                     (cid, f"{mev.symbol} {mev.pos_side} :: CANCEL SKIP (no master order_id)")
#                 )
#                 return

#             # ---------- LIMIT ----------
#             if mev.method == "limit":
#                 limit_root = side_root.get("limit", {})
#                 rec = limit_root.pop(master_oid, None)
#                 if not rec:
#                     self.mc.log_events.append(
#                         (cid, f"{mev.symbol} {mev.pos_side} :: LIMIT CANCEL MISS master_oid={master_oid}")
#                     )
#                     return

#                 copy_oid = rec.get("copy_order_id")
#                 if not copy_oid:
#                     return

#                 res = await client.cancel_limit_orders([copy_oid])
#                 if not res or not res.get("success"):
#                     self.mc.log_events.append(
#                         (cid, f"{mev.symbol} {mev.pos_side} :: LIMIT CANCEL FAILED copy_oid={copy_oid}")
#                     )
#                 else:
#                     self.mc.log_events.append(
#                         (cid, f"{mev.symbol} {mev.pos_side} :: LIMIT CANCELED copy_oid={copy_oid}")
#                     )
                
#                 _record_latency(
#                     cid=cid,
#                     mev=mev,
#                     res=res
#                 )
#                 return

#             # ---------- TRIGGER ----------
#             if mev.method == "trigger":
#                 trigger_root = side_root.get("trigger", {})
#                 rec = trigger_root.pop(master_oid, None)
#                 if not rec:
#                     self.mc.log_events.append(
#                         (cid, f"{mev.symbol} {mev.pos_side} :: TRIGGER CANCEL MISS master_oid={master_oid}")
#                     )
#                     return

#                 copy_oid = rec.get("copy_order_id")
#                 if not copy_oid:
#                     return

#                 res = await client.cancel_trigger_order(
#                     [copy_oid],
#                     symbol=mev.symbol,
#                 )
#                 if not res or not res.get("success"):
#                     self.mc.log_events.append(
#                         (cid, f"{mev.symbol} {mev.pos_side} :: TRIGGER CANCEL FAILED copy_oid={copy_oid}")
#                     )
#                 else:
#                     self.mc.log_events.append(
#                         (cid, f"{mev.symbol} {mev.pos_side} :: TRIGGER CANCELED copy_oid={copy_oid}")
#                     )
                    
#                 _record_latency(
#                     cid=cid,
#                     mev=mev,
#                     res=res
#                 )

#                 return

#             return

#         # --------------------------------------------------
#         # POSITION SNAPSHOT (FSM)
#         # --------------------------------------------------
#         if cid not in monitors:
#             monitors[cid] = PosMonitorFSM(
#                 rt["position_vars"],
#                 client.fetch_positions,
#             )

#         if mev.sig_type == "log":
#             return

#         # --------------------------------------------------
#         # BUILD INTENT
#         # --------------------------------------------------
#         copy_pv = get_copy_pos(rt, mev.symbol, mev.pos_side)

#         spec = (
#             self.mc.pos_vars_root
#             .get("position_vars", {})
#             .get(mev.symbol, {})
#             .get("spec", {})
#         )

#         intent: Optional[CopyOrderIntent] = self.intent_factory.build(
#             cfg=cfg,
#             mev=mev,
#             copy_pv=copy_pv,
#             spec=spec,
#         )

#         if not intent:
#             print("not intent")
#             return
        
#         # if TEST_MODE: await asyncio.sleep(5.0 + random.uniform(0.15, 0.6))
#         if intent.delay_ms: await asyncio.sleep(intent.delay_ms / 1000)

#         anchor = f"{intent.symbol} {intent.position_side}"

#         # --------------------------------------------------
#         # FORCE CLOSE
#         # --------------------------------------------------
#         if mev.closed:
#             res = await client.make_order(
#                 symbol=intent.symbol,
#                 contract=intent.contracts,
#                 side=intent.side,
#                 position_side=intent.position_side,
#                 leverage=intent.leverage,
#                 open_type=intent.open_type,
#                 market_type="MARKET",
#                 debug=True,
#             )

#             _record_latency(
#                 cid=cid,
#                 mev=mev,
#                 res=res
#             )

#             if not res or not res.get("success"):
#                 rt["last_error"] = res.get("reason") if res else "UNKNOWN"
#                 rt["last_error_ts"] = now()
#                 self.mc.log_events.append(
#                     (cid, f"{anchor} :: CLOSE FAILED: {rt['last_error']}")
#                 )
#                 return
            
#             if mev.sig_type == "manual":
#                 limit_ids = [
#                     v.get("copy_order_id")
#                     for v in side_root.get("limit", {}).values()
#                     if v.get("copy_order_id")
#                 ]
#                 trigger_ids = [
#                     v.get("copy_order_id")
#                     for v in side_root.get("trigger", {}).values()
#                     if v.get("copy_order_id")
#                 ]

#                 if limit_ids or trigger_ids:
#                     cancel_res = await client.cancel_orders_bulk(
#                         limit_order_ids=limit_ids,
#                         trigger_order_ids=trigger_ids,
#                         symbol=intent.symbol,
#                     )

#                     if cancel_res and cancel_res.get("success"):
#                         side_root.get("limit", {}).clear()
#                         side_root.get("trigger", {}).clear()
#                     else:
#                         reason = cancel_res.get("reason") if cancel_res else "UNKNOWN"
#                         self.mc.log_events.append(
#                             (cid, f"{intent.symbol} {intent.position_side} :: CANCEL FAILED: {reason}")
#                         )

#             return
        
#         # --------------------------------------------------
#         # ORDERS CACHE INIT
#         # --------------------------------------------------
#         limit_root = side_root.setdefault("limit", {})
#         trigger_root = side_root.setdefault("trigger", {})
#         master_oid = mev.payload.get("order_id")

#         # --------------------------------------------------
#         # MARKET / LIMIT
#         # --------------------------------------------------
#         if intent.method in ("MARKET", "LIMIT"):
#             res = await client.make_order(
#                 symbol=intent.symbol,
#                 contract=intent.contracts,
#                 side=intent.side,
#                 position_side=intent.position_side,
#                 leverage=intent.leverage,
#                 open_type=intent.open_type,
#                 price=intent.price if intent.method == "LIMIT" else None,
#                 stopLossPrice=intent.sl_price,
#                 takeProfitPrice=intent.tp_price,
#                 market_type=intent.method,
#                 debug=True,
#             )

#             _record_latency(
#                 cid=cid,
#                 mev=mev,
#                 res=res
#             )

#             if not res or not res.get("success"):
#                 rt["last_error"] = res.get("reason") if res else "UNKNOWN"
#                 rt["last_error_ts"] = now()
#                 self.mc.log_events.append(
#                     (cid, f"{anchor} :: {intent.method} FAILED: {rt['last_error']}")
#                 )
#                 return

#             if intent.method == "LIMIT" and master_oid:
#                 limit_root[master_oid] = {
#                     "copy_order_id": res.get("order_id"),
#                     "price": intent.price,
#                     "qty": intent.contracts,
#                     "status": "OPEN",
#                 }

#             return

#         # --------------------------------------------------
#         # TRIGGER
#         # --------------------------------------------------
#         if intent.method == "TRIGGER":
#             res = await client.make_trigger_order(
#                 symbol=intent.symbol,
#                 side=intent.side,
#                 position_side=intent.position_side,
#                 contract=intent.contracts,
#                 trigger_price=intent.trigger_price,
#                 leverage=intent.leverage,
#                 open_type=intent.open_type,
#                 order_type=mev.payload.get("trigger_exec", 2),
#                 debug=True,
#             )

#             _record_latency(
#                 cid=cid,
#                 mev=mev,
#                 res=res
#             )

#             if not res or not res.get("success"):
#                 rt["last_error"] = res.get("reason") if res else "UNKNOWN"
#                 rt["last_error_ts"] = now()
#                 self.mc.log_events.append(
#                     (cid, f"{anchor} :: TRIGGER FAILED: {rt['last_error']}")
#                 )
#                 return

#             if master_oid:
#                 trigger_root[master_oid] = {
#                     "copy_order_id": res.get("order_id"),
#                     "trigger_price": intent.trigger_price,
#                     "qty": intent.contracts,
#                     "status": "OPEN",
#                 }

#             return

# (клиент):

# ...
#     # POST
#     async def make_order(
#         self,
#         symbol: str,
#         contract: float,
#         side: str,
#         position_side: str,
#         leverage: int,
#         open_type: int,
#         price: Optional[str] = None,
#         stopLossPrice: Optional[str] = None,
#         takeProfitPrice: Optional[str] = None,
#         market_type: str = "MARKET",
#         debug: bool = True,
#     ) -> dict:

#         # -------- market type
#         if market_type == "MARKET":
#             order_type = OrderType.MarketOrder
#         elif market_type == "LIMIT":
#             order_type = OrderType.PriceLimited
#         else:
#             return OrderValidator.validate_and_log(
#                 None, "MAKE_ORDER", debug
#             )

#         # -------- side
#         if position_side.upper() == "LONG":
#             order_side = OrderSide.OpenLong if side.upper() == "BUY" else OrderSide.CloseLong
#         elif position_side.upper() == "SHORT":
#             order_side = OrderSide.OpenShort if side.upper() == "BUY" else OrderSide.CloseShort
#         else:
#             return OrderValidator.validate_and_log(
#                 None, "MAKE_ORDER", debug
#             )

#         # -------- open type
#         if open_type == 1:
#             openType = OpenType.Isolated
#         elif open_type == 2:
#             openType = OpenType.Cross
#         else:
#             return OrderValidator.validate_and_log(
#                 None, "MAKE_ORDER", debug
#             )

#         if openType == OpenType.Isolated and not leverage:
#             return OrderValidator.validate_and_log(
#                 None, "MAKE_ORDER", debug
#             )

#         # -------- API call
#         result = await self.api.create_order(
#             order_request=CreateOrderRequest(
#                 symbol=symbol,
#                 side=order_side,
#                 vol=contract,
#                 leverage=leverage,
#                 openType=openType,
#                 type=order_type,
#                 price=price,
#                 stopLossPrice=stopLossPrice,
#                 takeProfitPrice=takeProfitPrice,
#             ),
#             session=self.session,
#         )

#         return OrderValidator.validate_and_log(
#             result=result,
#             debug_label="MAKE_ORDER",
#             debug=debug,
#         )
        
#     async def make_trigger_order(
#         self,
#         *,
#         symbol: str,
#         side: Literal["BUY", "SELL"],          # торговая сторона
#         position_side: Literal["LONG", "SHORT"],
#         contract: float,
#         trigger_price: str,
#         leverage: int,
#         open_type: int,
#         order_type: int = 2,                   # 1=LIMIT, 2=MARKET
#         debug: bool = False,
#     ) -> dict:
#         """
#         Универсальный trigger-ордер (open / close).

#         BUY  -> trigger on price <= trigger_price
#         SELL -> trigger on price >= trigger_price
#         """

#         # --------------------------------------------------
#         # ORDER SIDE (open / close)
#         # --------------------------------------------------
#         if position_side == "LONG":
#             order_side = (
#                 OrderSide.OpenLong if side == "BUY"
#                 else OrderSide.CloseLong
#             )
#         elif position_side == "SHORT":
#             order_side = (
#                 OrderSide.OpenShort if side == "BUY"
#                 else OrderSide.CloseShort
#             )
#         else:
#             return OrderValidator.validate_and_log(
#                 None, "TRIGGER_ORDER", debug
#             )

#         # --------------------------------------------------
#         # TRIGGER TYPE (ключевая часть)
#         # --------------------------------------------------
#         trigger_type = (
#             TriggerType.LessThanOrEqual
#             # if (side == "BUY" and position_side == "LONG") or (side == "SELL" and position_side == "SHORT")
#             if order_side in (OrderSide.OpenLong, OrderSide.CloseShort)
#             else TriggerType.GreaterThanOrEqual
#         )

#         # --------------------------------------------------
#         # OPEN TYPE
#         # --------------------------------------------------
#         if open_type == 1:
#             openType = OpenType.Isolated
#         elif open_type == 2:
#             openType = OpenType.Cross
#         else:
#             return OrderValidator.validate_and_log(
#                 None, "TRIGGER_ORDER", debug
#             )

#         if openType == OpenType.Isolated and not leverage:
#             return OrderValidator.validate_and_log(
#                 None, "TRIGGER_ORDER", debug
#             )

#         # --------------------------------------------------
#         # EXEC ORDER TYPE
#         # --------------------------------------------------
#         exec_order_type = (
#             OrderType.PriceLimited
#             if order_type == 1
#             else OrderType.MarketOrder
#         )

#         # --------------------------------------------------
#         # API CALL
#         # --------------------------------------------------
#         trigger_request = TriggerOrderRequest(
#             symbol=symbol,
#             side=order_side,
#             vol=contract,
#             leverage=leverage,
#             openType=openType,
#             orderType=exec_order_type,
#             executeCycle=ExecuteCycle.UntilCanceled,
#             trend=TriggerPriceType.LatestPrice,
#             triggerPrice=trigger_price,
#             triggerType=trigger_type,
#         )

#         result = await self.api.create_trigger_order(
#             trigger_order_request=trigger_request,
#             session=self.session,
#         )

#         return OrderValidator.validate_and_log(
#             result=result,
#             debug_label="TRIGGER_ORDER",
#             debug=debug,
#         )
    
#     # DELETE
#     async def cancel_trigger_order(
#         self,
#         order_id_list: List[str],
#         symbol: str,
#         debug: bool = True,
#     ) -> dict:
#         """
#         Отмена trigger / plan ордеров
#         """

#         if not order_id_list:
#             return OrderValidator.validate_and_log(
#                 None, "CANCEL_TRIGGER", debug
#             )

#         order_list = [{"orderId": oid, "symbol": symbol} for oid in order_id_list]

#         result = await self.api.cancel_trigger_orders(
#             orders=order_list,
#             session=self.session,
#         )

#         return OrderValidator.validate_and_log(
#             result=result,
#             debug_label="CANCEL_TRIGGER",
#             debug=debug,
#         )
    
#     async def cancel_limit_orders(
#         self,
#         order_id_list: List[str],
#         debug: bool = True,
#     ) -> dict:
#         """
#         Отмена обычных (не trigger) лимитных ордеров по orderId.
#         """
#         if not order_id_list:
#             return {
#                 "success": False,
#                 "order_ids": [],
#                 "reason": "order_id_list is empty",
#                 "raw": None,
#                 "ts": int(time.time() * 1000),
#             }

#         result = await self.api.cancel_orders(
#             order_ids=order_id_list,
#             session=self.session
#         )

#         return OrderValidator.validate_and_log(
#             result=result,
#             debug_label="CANCEL_LIMIT",
#             debug=debug
#         )
    
#     async def cancel_all_orders(
#         self,
#         symbol: str,
#         debug: bool = True
#     ) -> dict:
#         """
#         Отмена ВСЕХ ордеров (limit + trigger) по символу.
#         """
#         result = await self.api.cancel_all_orders(
#             symbol=symbol,
#             session=self.session
#         )

#         return OrderValidator.validate_and_log(
#             result=result,
#             debug_label="CANCEL_ALL",
#             debug=debug
#         )
        
#     async def cancel_orders_bulk(
#         self,
#         *,
#         limit_order_ids: Optional[List[str]] = None,
#         trigger_order_ids: Optional[List[str]] = None,
#         symbol: Optional[str] = None,
#         debug: bool = True,
#     ) -> dict:
#         """
#         Универсальная массовая отмена ордеров по спискам ID.

#         • limit_order_ids  → обычные лимитные ордера
#         • trigger_order_ids → trigger / plan ордера (TP / SL)
#         • symbol обязателен, если есть trigger_order_ids
#         """

#         results = {
#             "limit": None,
#             "trigger": None,
#             "errors": [],
#         }

#         # --------------------------------------------------
#         # LIMIT ORDERS
#         # --------------------------------------------------
#         if limit_order_ids:
#             try:
#                 res = await self.cancel_limit_orders(
#                     order_id_list=limit_order_ids,
#                     debug=debug,
#                 )
#                 results["limit"] = res
#                 if not res.get("success"):
#                     results["errors"].append(("limit", res.get("reason")))
#             except Exception as e:
#                 results["errors"].append(("limit", str(e)))

#         # --------------------------------------------------
#         # TRIGGER ORDERS
#         # --------------------------------------------------
#         if trigger_order_ids:
#             if not symbol:
#                 results["errors"].append(
#                     ("trigger", "symbol is required for trigger order cancel")
#                 )
#             else:
#                 try:
#                     res = await self.cancel_trigger_order(
#                         order_id_list=trigger_order_ids,
#                         symbol=symbol,
#                         debug=debug,
#                     )
#                     results["trigger"] = res
#                     if not res.get("success"):
#                         results["errors"].append(("trigger", res.get("reason")))
#                 except Exception as e:
#                     results["errors"].append(("trigger", str(e)))

#         success = not results["errors"]

#         return {
#             "success": success,
#             "details": results,
#         }


# @dataclass
# class CopyOrderIntent:
#     # --- required ---
#     symbol: str
#     side: str                 # BUY / SELL
#     position_side: str        # LONG / SHORT
#     contracts: float
#     method: Literal["MARKET", "LIMIT", "TRIGGER"]

#     # --- optional ---
#     leverage: Optional[int] = None
#     open_type: Optional[int] = None

#     price: Optional[str] = None
#     trigger_price: Optional[str] = None
#     sl_price: Optional[str] = None
#     tp_price: Optional[str] = None
#     changing_qty_flag: bool = False

#     delay_ms: int = 0


# class CopyOrderIntentFactory:
#     """
#     Единственная точка кастомизации ИНИЦИИРУЮЩИХ ордеров.
#     CLOSE здесь не существует.
#     """

#     def __init__(self, mc: "MainContext"):
#         self.mc = mc

#     # --------------------------------------------------
#     def build(
#         self,
#         cfg: Dict,
#         mev: "MasterEvent",
#         copy_pv: Dict,
#         spec: Dict
#     ) -> Optional[CopyOrderIntent]:

#         payload = mev.payload or {}
#         cid = cfg.get("cid", "?")

#         # --------------------------------------------------
#         # 3️⃣ LEVERAGE
#         # --------------------------------------------------
#         if not mev.closed:
#             leverage = (
#                 cfg.get("leverage")
#                 or payload.get("leverage")
#                 or copy_pv.get("leverage")
#                 or FALLBACK_LEVERAGE
#             )
#         else:
#             leverage = copy_pv.get("leverage")

#         max_lev = spec.get("max_leverage")
#         if max_lev:
#             leverage = min(int(leverage), int(max_lev))
#         try:
#             leverage = int(leverage)
#         except ValueError:
#             pass

#         # --------------------------------------------------
#         # 4️⃣ OPEN TYPE
#         # --------------------------------------------------
#         if not mev.closed:
#             open_type = (
#                 cfg.get("margin_mode")
#                 or payload.get("open_type")
#                 or copy_pv.get("margin_mode")
#                 or FALLBACK_MARGIN_MODE
#             )
#         else:
#             open_type = copy_pv.get("margin_mode")
        
#         try:
#             open_type = int(open_type)
#         except ValueError:
#             pass

#         sl_price = tp_price = price = trigger_price = None

#         max_margin = Utils.safe_float(cfg.get("max_position_size"))

#         coef = Utils.safe_float(cfg.get("coef", 1.0)) or 1.0
#         lo, hi = Utils.safe_float(cfg.get("random_size_pct", [0.0, 0.0])[0]), Utils.safe_float(cfg.get("random_size_pct", [0.0, 0.0])[1])
#         rnd = 100
#         if lo or hi and hi > lo:
#             rnd = random.uniform(lo, hi)

#         qty = None
#         payload_qty = Utils.safe_float(payload.get("qty"))
#         copy_pv_qty = Utils.safe_float(copy_pv.get("qty"))
#         changing_qty_flag = (coef not in (0, 1, None)) or lo or hi or max_margin

#         # --------------------------------------------------
#         # 6️⃣ DELAY
#         # --------------------------------------------------        
#         delay_ms = 0

#         if mev.sig_type != "manual":
#             delay_cfg = cfg.get("delay_ms", [0, 0])

#             if isinstance(delay_cfg, (list, tuple)) and len(delay_cfg) == 2:
#                 lo, hi = Utils.safe_float(delay_cfg[0]), Utils.safe_float(delay_cfg[1])
#                 lo, hi = abs(lo), abs(hi)
#                 if hi > lo:
#                     delay_ms = int(random.uniform(lo, hi))
#             elif isinstance(delay_cfg, (int, float)):
#                 delay_ms = int(delay_cfg)

#         # --------------------------------------------------
#         # 6️⃣ PROCE
#         # --------------------------------------------------
#         price_precision = spec.get("price_precision") if spec else None
#         price = self._fmt_price(payload.get("price"), price_precision)

#         # ==================================================
#         # CLOSE
#         # ==================================================
#         if mev.closed:
#             qty = payload_qty if not changing_qty_flag else copy_pv_qty
#             if not qty or qty <= 0:
#                 self._log_drop(cid, mev, "CLOSE_QTY_INVALID", qty=qty)
#                 return None

#         # ==================================================
#         # OPEN / MODIFY
#         # ==================================================
#         else:    
#             qty = payload_qty        
#             if not qty or qty <= 0:
#                 self._log_drop(cid, mev, "QTY_PAYLOAD_INVALID", qty=qty, payload=payload)
#                 return None

#             # --------------------------------------------------
#             # CLAMP (если БЫЛИ изменения)
#             # --------------------------------------------------
#             if changing_qty_flag:
#                 raw_price = payload.get("price") or copy_pv.get("entry_price")
#                 price_f = Utils.safe_float(raw_price)

#                 qty = self._clamp_by_max_margin(
#                     contracts=qty,
#                     max_margin=max_margin,
#                     price=price_f,
#                     leverage=leverage,
#                     coef=coef,
#                     rnd=rnd,
#                     spec=spec,
#                 )

#                 if not qty or qty <= 0:
#                     self._log_drop(
#                         cid, mev,
#                         "QTY_AFTER_CLAMP_INVALID",
#                         qty=qty,
#                         price=price_f,
#                         max_margin=cfg.get("max_position_size"),
#                         vol_unit=spec.get("vol_unit"),
#                     )
#                     return None

#             # --------------------------------------------------
#             # PRICES
#             # --------------------------------------------------
#             trigger_price = self._fmt_price(payload.get("trigger_price"), price_precision)
#             sl_price = self._fmt_price(payload.get("sl_price"), price_precision)
#             tp_price = self._fmt_price(payload.get("tp_price"), price_precision)

#         return CopyOrderIntent(
#             symbol=mev.symbol,
#             side="BUY" if mev.event == "buy" else "SELL",
#             position_side=mev.pos_side,
#             contracts=qty,
#             method=mev.method.upper(),
#             price=price,
#             trigger_price=trigger_price,
#             leverage=leverage,
#             open_type=open_type,
#             sl_price=sl_price,
#             tp_price=tp_price,
#             changing_qty_flag=changing_qty_flag,
#             delay_ms=delay_ms,
#         )

#     # --------------------------------------------------
#     def _fmt_price(self, value, precision):
#         if value is None:
#             return None
#         raw = Utils.safe_float(value)
#         if raw is None:
#             return None
#         if precision is not None:
#             raw = round(raw, precision)
#         return Utils.to_human_digit(raw)

#     # --------------------------------------------------
#     def _log_drop(self, cid, mev, reason: str, **extra):
#         parts = [
#             f"{mev.symbol} {mev.pos_side}",
#             f"INTENT DROP",
#             f"reason={reason}",
#             f"event={mev.event}",
#             f"method={mev.method}",
#         ]

#         if extra:
#             extras = ", ".join(f"{k}={v}" for k, v in extra.items())
#             parts.append(extras)

#         self.mc.log_events.append(
#             (cid, " :: ".join(parts))
#             # (cid, " :: ".join(parts), now())
#         )

#     # --------------------------------------------------
#     def _clamp_by_max_margin(
#         self,
#         *,
#         contracts: float,
#         max_margin: float,
#         price: Optional[float],
#         leverage: int,
#         coef: float,
#         rnd: float,
#         spec: dict,
#     ) -> float:

#         if not isinstance(contracts, (int, float)) or not math.isfinite(contracts):
#             return 0.0
#         if not price or price <= 0 or not leverage or leverage <= 0:
#             return contracts
        
#         if not spec:
#             return contracts
        
#         contract_size = spec.get("contract_size")
#         vol_unit = spec.get("vol_unit")
#         precision = spec.get("contract_precision")

#         if not contract_size or not vol_unit or precision is None:
#             return contracts

#         margin = (contracts * contract_size * price) / leverage

#         # --------------------------------------------------
#         # 1️⃣ COEF
#         # --------------------------------------------------            
#         if coef and coef not in (0, 1):
#             margin *= abs(coef)

#         # --------------------------------------------------
#         # 2️⃣ RANDOM SIZE
#         # --------------------------------------------------
        
#         if rnd and rnd not in (0, 100):
#             margin *= abs(rnd / 100)

#         if margin and max_margin and margin >= max_margin:
#             margin = abs(float(max_margin))

#         elif not margin:
#             return 0.0 

#         # считаем объём в базовой валюте
#         base_qty = (margin * leverage) / price
#         # переводим в контракты
#         contracts = base_qty / contract_size

#         # contracts = round(contracts / vol_unit) * vol_unit
#         contracts = math.floor(contracts / vol_unit) * vol_unit
#         contracts = round(contracts, precision)


#         if not math.isfinite(contracts) or contracts <= 0:
#             return 0.0

#         return contracts

# это копи слой.

# вот мастер слой:

# # MASTER.stream_.py

# from __future__ import annotations

# import asyncio
# import aiohttp
# import json
# import time
# import hmac
# import hashlib
# import random
# from typing import *

# from a_config import BLACK_SYMBOLS

# from c_utils import now
# from .state_ import (
#     SignalEvent,
#     normalize_symbol,
#     side_from_order_side,
#     side_from_position_type,
# )

# if TYPE_CHECKING:
#     from c_log import UnifiedLogger
#     from .state_ import SignalCache


# IS_SHOW_SIGNAL = False


# class MasterSignalStream:
#     """
#     STREAM LEVEL ONLY.
#     НИКАКОЙ high-level логики.
#     """

#     def __init__(
#         self,
#         api_key: str,
#         api_secret: str,
#         signal_cache: "SignalCache",
#         *,
#         logger: "UnifiedLogger",
#         stop_flag: Callable,
#         proxy_url: Optional[str] = None,
#         ws_url: str = "wss://contract.mexc.com/edge",
#         # ws_url: str = "wss://contract.mexc.com/ws",
#         quota_asset: str = "USDT",
#     ):
#         self.api_key = api_key
#         self.api_secret = api_secret

#         self.cache = signal_cache
#         self.logger = logger

#         self.proxy_url = None if not proxy_url or proxy_url == "0" else proxy_url
#         self.ws_url = ws_url
#         self.quota_asset = quota_asset.upper()

#         self.session: Optional[aiohttp.ClientSession] = None
#         self.websocket: Optional[aiohttp.ClientWebSocketResponse] = None

#         self.ready = False
#         self.is_connected = False
#         self.ping_interval = 12
#         self.stop_flag = stop_flag

#         self._external_stop = False
#         self._ping_task: Optional[asyncio.Task] = None

#         self.black_symbols = {x.upper() for x in BLACK_SYMBOLS if x and x.strip()}

#     # --------------------------------------------------
#     # LIFECYCLE
#     # --------------------------------------------------

#     def stop(self):
#         self._external_stop = True
#         self.ready = False
#         self.logger.info("MasterSignalStream: stop requested")

#     # --------------------------------------------------
#     def _signature(self, ts_ms: int) -> str:
#         payload = f"{self.api_key}{ts_ms}"
#         return hmac.new(
#             self.api_secret.encode("utf-8"),
#             payload.encode("utf-8"),
#             hashlib.sha256
#         ).hexdigest()

#     # def _signature(self, ts_ms: int) -> str:
#     #     return hmac.new(
#     #         self.api_secret.encode(),
#     #         f"{self.api_key}{ts_ms}".encode(),
#     #         hashlib.sha256,
#     #     ).hexdigest()

#     # --------------------------------------------------
#     # CONNECTION
#     # --------------------------------------------------

#     async def _connect(self) -> bool:
#         try:
#             if not self.session or self.session.closed:
#                 self.session = aiohttp.ClientSession()

#             self.websocket = await self.session.ws_connect(
#                 self.ws_url,
#                 proxy=self.proxy_url,
#                 autoping=False,
#             )

#             self.is_connected = True
#             self.logger.info("MasterSignalStream: WS connected")
#             return True

#         except Exception as e:
#             self.logger.warning(f"WS connect failed: {e}")
#             return False
            
#     async def _login(self) -> bool:
#         ts = int(time.time() * 1000) - 1000  # 🔥 важно
#         await self.websocket.send_json({
#             "method": "login",
#             "param": {
#                 "apiKey": self.api_key,
#                 "reqTime": ts,
#                 "signature": self._signature(ts),
#             }
#         })

#         msg = await asyncio.wait_for(self.websocket.receive(), timeout=10)
#         data = json.loads(msg.data)

#         if data.get("channel") == "rs.login" and data.get("data") == "success":
#             self.logger.info("MasterSignalStream: WS login success")
#             return True

#         self.logger.error(f"WS login failed: {data}")
#         return False


#     # async def _login(self) -> bool:
#     #     try:
#     #         ts = int(time.time() * 1000)
#     #         await self.websocket.send_json({
#     #             "method": "login",
#     #             "param": {
#     #                 "apiKey": self.api_key,
#     #                 "reqTime": ts,
#     #                 "signature": self._signature(ts),
#     #             }
#     #         })

#     #         msg = await asyncio.wait_for(self.websocket.receive(), timeout=10)
#     #         data = json.loads(msg.data)

#     #         ok = data.get("channel") == "rs.login" and data.get("data") == "success"
#     #         if ok:
#     #             self.logger.info("MasterSignalStream: WS login success")
#     #         else:
#     #             self.logger.warning(f"WS login failed: {data}")

#     #         return ok

#     #     except Exception as e:
#     #         self.logger.warning(f"WS login exception: {e}")
#     #         return False

#     async def _ping_loop(self):
#         while not self._external_stop and self.is_connected and not self.stop_flag():
#             await asyncio.sleep(self.ping_interval)
#             try:
#                 await self.websocket.send_json({"method": "ping"})
#             except Exception:
#                 return

#     async def _disconnect(self):
#         self.is_connected = False
#         self.ready = False

#         if self._ping_task and not self._ping_task.done():
#             self._ping_task.cancel()

#         try:
#             if self.websocket:
#                 await self.websocket.close()
#             if self.session:
#                 await self.session.close()
#         except Exception:
#             pass

#         self.websocket = None
#         self.session = None
#         self.logger.info("MasterSignalStream: WS disconnected")

#     # --------------------------------------------------
#     # RAW EVENT EMIT
#     # --------------------------------------------------

#     async def _emit(self, symbol, pos_side, etype, raw):
#         if symbol and symbol.upper() in self.black_symbols:
#             return
        
#         ev = SignalEvent(
#             symbol=symbol,
#             pos_side=pos_side,
#             event_type=etype,
#             ts=now(),
#             raw=raw,
#         )
#         if IS_SHOW_SIGNAL:
#             self.logger.debug(f"RAW SIGNAL: {ev}")
#         await self.cache.push_event(ev)

#     # --------------------------------------------------
#     # HANDLERS
#     # --------------------------------------------------

#     async def _handle_order(self, data):
#         symbol = normalize_symbol(data.get("symbol"), self.quota_asset)
#         side_code = int(data.get("side", 0))
#         side = side_from_order_side(side_code)

#         state = int(data.get("state", 0))
#         order_type = int(data.get("orderType", 0))

#         if order_type == 5:
#             etype = "open_market" if side_code in (1, 3) else "close_market"
#         elif order_type == 1:
#             etype = "open_limit" if side_code in (1, 3) else "close_limit"
#         else:
#             etype = "trigger_order"

#         await self._emit(symbol, side, etype, data)

#         if state in (1, 2):
#             await self._emit(
#                 symbol, side,
#                 "open_pending" if side_code in (1, 3) else "close_pending",
#                 data,
#             )

#         if state == 4:
#             await self._emit(symbol, side, "order_cancelled", data)
#         elif state == 5:
#             await self._emit(symbol, side, "order_invalid", data)

#     async def _handle_order_deal(self, data):
#         symbol = normalize_symbol(data.get("symbol"), self.quota_asset)
#         side = side_from_order_side(int(data.get("side", 0)))
#         await self._emit(symbol, side, "deal", data)

#     async def _handle_position(self, data):
#         symbol = normalize_symbol(data.get("symbol"), self.quota_asset)
#         side = side_from_position_type(int(data.get("positionType", 0)))

#         hold_vol = float(data.get("holdVol", 0))
#         state = int(data.get("state", 0))

#         etype = (
#             "position_opened"
#             if (state in (1, 2) and hold_vol > 0)
#             else "position_closed"
#         )
#         await self._emit(symbol, side, etype, data)

#     async def _handle_plan_order(self, data):
#         symbol = normalize_symbol(data.get("symbol"), self.quota_asset)
#         side = side_from_order_side(int(data.get("side", 0)))
#         state = int(data.get("state", 0))

#         etype = (
#             "plan_order"
#             if state == 1
#             else "plan_executed"
#             if state == 3
#             else "plan_cancelled"
#         )
#         await self._emit(symbol, side, etype, data)

#     async def _handle_stop_order(self, data):
#         symbol = normalize_symbol(data.get("symbol"), self.quota_asset)
#         side = side_from_order_side(int(data.get("side", 0)))
#         await self._emit(symbol, side, "stop_attached", data)

#     # --------------------------------------------------
#     # MESSAGE LOOP
#     # --------------------------------------------------

#     async def _handle_messages(self):
#         while not self._external_stop and not self.stop_flag():
#             try:
#                 msg = await asyncio.wait_for(self.websocket.receive(), timeout=1.0)
#             except asyncio.TimeoutError:
#                 continue

#             if msg.type != aiohttp.WSMsgType.TEXT:
#                 continue

#             data = json.loads(msg.data)
#             channel = data.get("channel")
#             payload = data.get("data", {})

#             if channel == "push.personal.order":
#                 await self._handle_order(payload)
#             elif channel == "push.personal.order.deal":
#                 await self._handle_order_deal(payload)
#             elif channel == "push.personal.position":
#                 await self._handle_position(payload)
#             elif channel == "push.personal.plan.order":
#                 await self._handle_plan_order(payload)
#             elif channel == "push.personal.stop.order":
#                 await self._handle_stop_order(payload)

#     # --------------------------------------------------
#     # MAIN LOOP
#     # --------------------------------------------------

#     async def start(self):
#         self._external_stop = False

#         while not self._external_stop and not self.stop_flag():
#             if not await self._connect():
#                 await asyncio.sleep(1)
#                 continue

#             if not await self._login():
#                 await self._disconnect()
#                 await asyncio.sleep(1)
#                 continue

#             self.ready = True
#             self._ping_task = asyncio.create_task(self._ping_loop())

#             await self._handle_messages()
#             await self._disconnect()

#             if not self._external_stop:
#                 await asyncio.sleep(random.uniform(0.8, 1.5))

# между этими двумя слоями есть важная сущность # MASTER.payload_.py

# в нынешнем виде она полностью бесполезна:

# # MASTER.payload_.py

# from __future__ import annotations

# import asyncio
# from dataclasses import dataclass, field
# from typing import *

# from MASTER.state_ import PosVarSetup
# from c_utils import Utils, now

# if TYPE_CHECKING:
#     from MASTER.state_ import SignalCache, SignalEvent
#     from b_context import MainContext
#     from c_log import UnifiedLogger


# # ======================================================
# # PROTOCOL
# # ======================================================

# HL_EVENT = Literal["buy", "sell"]
# METHOD = Literal["market"]


# # ======================================================
# # MASTER EVENT
# # ======================================================

# @dataclass
# class MasterEvent:
#     event: HL_EVENT                # buy / sell
#     method: METHOD                 # always market
#     symbol: str
#     pos_side: str                  # LONG / SHORT
#     payload: Dict[str, Any]
#     sig_type: Literal["copy", "manual"]
#     ts: int = field(default_factory=now)


# # ======================================================
# # MASTER PAYLOAD
# # ======================================================

# class MasterPayload:
#     """
#     SNAPSHOT-DRIVEN payload (ONE-WAY)

#     ИНВАРИАНТЫ:
#     • BUY  — qty: 0 -> >0
#     • SELL — qty: >0 -> 0
#     • НИКАКИХ сигналов из deal / intent
#     • SHORT и LONG работают одинаково
#     """

#     def __init__(
#         self,
#         cache: "SignalCache",
#         mc: "MainContext",
#         logger: "UnifiedLogger",
#         stop_flag: Callable[[], bool],
#     ):
#         self.cache = cache
#         self.mc = mc
#         self.logger = logger
#         self.stop_flag = stop_flag

#         self._pending: list[MasterEvent] = []
#         self._stop = False

#         # (symbol, pos_side) -> last qty
#         self._last_qty: Dict[Tuple[str, str], float] = {}

#         self.out_queue = asyncio.Queue(maxsize=1000)

#     # ==================================================
#     def stop(self):
#         self._stop = True
#         self._last_qty.clear()
#         self.mc.pos_vars_root.clear()
#         self.logger.info("MasterPayload: stop requested")

#     # ==================================================
#     async def run(self):
#         self.logger.info("MasterPayload READY")

#         while not self._stop and not self.stop_flag():
#             await self.cache._event_notify.wait()
#             events = await self.cache.pop_events()

#             for ev in events:
#                 await self._route(ev)

#             for mev in self._pending:
#                 await self.out_queue.put(mev)

#             self._pending.clear()

#         self.logger.info("MasterPayload STOPPED")

#     # ==================================================
#     def _ensure_pv(self, symbol: str, pos_side: str) -> dict:
#         PosVarSetup.set_pos_defaults(
#             self.mc.pos_vars_root,
#             symbol,
#             pos_side,
#             instruments_data=self.mc.instruments_data,
#         )
#         return self.mc.pos_vars_root[symbol][pos_side]

#     # ==================================================
#     async def _route(self, ev: "SignalEvent"):
#         """
#         Единственная логика:
#         реагируем ТОЛЬКО на position snapshot.
#         """
#         if ev.event_type not in ("position_opened", "position_closed"):
#             return

#         symbol, pos_side = ev.symbol, ev.pos_side
#         if not symbol or not pos_side:
#             return

#         pv = self._ensure_pv(symbol, pos_side)

#         qty_cur = Utils.safe_float(ev.raw.get("holdVol"), 0.0)
#         qty_prev = self._last_qty.get((symbol, pos_side), 0.0)

#         price = Utils.safe_float(
#             ev.raw.get("avgPrice")
#             or ev.raw.get("openAvgPrice")
#             or ev.raw.get("price")
#         )

#         # обновляем pv
#         pv["qty"] = qty_cur
#         pv["in_position"] = qty_cur > 0
#         pv["avg_price"] = price

#         self._last_qty[(symbol, pos_side)] = qty_cur

#         # ================= OPEN =================
#         if qty_prev == 0 and qty_cur > 0:
#             self._emit(
#                 event="buy",
#                 symbol=symbol,
#                 pos_side=pos_side,
#                 payload={
#                     "qty": qty_cur,
#                     "price": price,
#                     "reduce_only": False,
#                 },
#                 ev_raw=ev,
#             )
#             return

#         # ================= CLOSE =================
#         if qty_prev > 0 and qty_cur == 0:
#             self._emit(
#                 event="sell",
#                 symbol=symbol,
#                 pos_side=pos_side,
#                 payload={
#                     "qty": qty_prev,
#                     "price": price,
#                     "reduce_only": True,
#                 },
#                 ev_raw=ev,
#             )
#             self._last_qty.pop((symbol, pos_side), None)
#             return

#     # ==================================================
#     def _emit(
#         self,
#         *,
#         event: HL_EVENT,
#         symbol: str,
#         pos_side: str,
#         payload: Dict[str, Any],
#         ev_raw: Optional["SignalEvent"],
#     ):
#         ts = now()

#         payload = dict(payload)
#         payload["exec_ts"] = ts
#         payload["latency_ms"] = ts - ev_raw.ts if ev_raw else None

#         self._pending.append(
#             MasterEvent(
#                 event=event,
#                 method="market",
#                 symbol=symbol,
#                 pos_side=pos_side,
#                 payload=payload,
#                 sig_type="copy",
#                 ts=ts,
#             )
#         )

# раньше почти работала:

# # # MASTER.payload_.py

# # from __future__ import annotations

# # import asyncio
# # from dataclasses import dataclass, field
# # from typing import *

# # from MASTER.state_ import PosVarSetup
# # from c_utils import Utils, now

# # if TYPE_CHECKING:
# #     from MASTER.state_ import SignalCache, SignalEvent
# #     from b_context import MainContext
# #     from c_log import UnifiedLogger


# # # =====================================================================
# # # HL PROTOCOL
# # # =====================================================================

# # HL_EVENT = Literal["buy", "sell", "canceled", "filled"]
# # METHOD = Literal["market", "limit", "trigger", "oco"]


# # # =====================================================================
# # # MASTER EVENT
# # # =====================================================================

# # @dataclass
# # class MasterEvent:
# #     # MasterEvent may contain _cid for manual routing
# #     event: HL_EVENT
# #     method: METHOD
# #     symbol: str
# #     pos_side: str
# #     partially: bool
# #     closed: bool
# #     payload: Dict[str, Any]
# #     sig_type: Literal["copy", "log", "manual"]
# #     ts: int = field(default_factory=now)

# # # =====================================================================
# # # MASTER PAYLOAD
# # # =====================================================================

# # class MasterPayload:
# #     """
# #     High-level агрегатор сигналов мастера.
# #     """

# #     def __init__(
# #         self,
# #         cache: "SignalCache",
# #         mc: "MainContext",
# #         logger: "UnifiedLogger",
# #         stop_flag: Callable,
# #     ):
# #         self.cache = cache
# #         self.mc = mc
# #         self.logger = logger
# #         self.stop_flag = stop_flag

# #         self._pending: List[MasterEvent] = []
# #         self._stop = False

# #         self._pos_state: Dict[Tuple[str, str], Dict[str, Any]] = {}
# #         self._last_deal: Dict[Tuple[str, str], Dict[str, Any]] = {}
# #         self._attached_oco: Dict[str, dict] = {}

# #         self.out_queue = asyncio.Queue(maxsize=1000)

# #     # ==========================================================
# #     def stop(self):
# #         self._stop = True
# #         self.mc.pos_vars_root.clear()
# #         self.logger.info("MasterPayload: stop requested")

# #     # ==========================================================
# #     async def run(self):
# #         self.logger.info("MasterPayload READY")

# #         while not self._stop and not self.stop_flag():
# #             await self.cache._event_notify.wait()
# #             raw_events = await self.cache.pop_events()

# #             for ev in raw_events:
# #                 await self._route(ev)

# #             out = self._pending[:]
# #             self._pending.clear()

# #             for mev in out:
# #                 await self.out_queue.put(mev)

# #         self.logger.info("MasterPayload STOPPED")

# #     # ==========================================================
# #     def _ensure_pos_vars(self, symbol: str, pos_side: str) -> dict:
# #         PosVarSetup.set_pos_defaults(
# #             self.mc.pos_vars_root,
# #             symbol,
# #             pos_side,
# #             instruments_data=self.mc.instruments_data,
# #         )

# #         return self.mc.pos_vars_root.get(symbol, {}).get(pos_side, {})

# #     # ==========================================================
# #     def _fix_price(self, raw, symbol=None, side=None):
# #         for k in ("dealAvgPrice", "avgPrice", "price", "openAvgPrice"):
# #             if raw.get(k):
# #                 return Utils.safe_float(raw[k])
# #         return self._last_deal.get((symbol, side), {}).get("price")

# #     # ==========================================================
# #     def _is_stale_snapshot(self, key, raw) -> bool:
# #         upd = raw.get("updateTime") or raw.get("timestamp") or 0
# #         hold = raw.get("holdVol")

# #         st = self._pos_state.get(key)
# #         if not st:
# #             self._pos_state[key] = {"upd": upd, "hold": hold}
# #             return False

# #         if hold == 0:
# #             self._pos_state[key] = {"upd": upd, "hold": hold}
# #             return False

# #         if upd < st["upd"]:
# #             return True
# #         if upd == st["upd"] and hold == st["hold"]:
# #             return True

# #         self._pos_state[key] = {"upd": upd, "hold": hold}
# #         return False

# #     # ==========================================================
# #     async def _route(self, ev: "SignalEvent"):
# #         et = ev.event_type
# #         symbol, pos_side = ev.symbol, ev.pos_side

# #         # ---------------- ATTACHED OCO ----------------
# #         if et == "stop_attached":
# #             self._attached_oco[symbol] = {
# #                 "tp": Utils.safe_float(ev.raw.get("takeProfitPrice")),
# #                 "sl": Utils.safe_float(ev.raw.get("stopLossPrice")),
# #             }
# #             return

# #         if not pos_side:
# #             return

# #         pv = self._ensure_pos_vars(symbol, pos_side)

# #         # ---------------- LIMIT OPEN / CLOSE ----------------
# #         if et in ("open_limit", "close_limit") and ev.raw.get("state") == 2:
# #             pv["_last_exec_source"] = "limit"

# #             await self._emit(
# #                 event="buy" if et == "open_limit" else "sell",
# #                 method="limit",
# #                 symbol=symbol,
# #                 pos_side=pos_side,
# #                 partially=False,
# #                 payload={
# #                     "order_id": ev.raw.get("orderId"),
# #                     "qty": Utils.safe_float(ev.raw.get("vol")),
# #                     "price": Utils.safe_float(ev.raw.get("price")),
# #                     "leverage": ev.raw.get("leverage"),
# #                     "open_type": ev.raw.get("openType"),
# #                     "reduce_only": bool(ev.raw.get("reduceOnly")),
# #                     "used_margin": Utils.safe_float(ev.raw.get("usedMargin")),
# #                 },
# #                 sig_type="copy",
# #                 ev_raw=ev,
# #             )
# #             return

# #         # ---------------- LIMIT CANCEL ----------------
# #         if et in ("order_cancelled", "order_invalid"):
# #             pv["_last_exec_source"] = None

# #             await self._emit(
# #                 event="canceled",
# #                 method="limit",
# #                 symbol=symbol,
# #                 pos_side=pos_side,
# #                 partially=False,
# #                 payload={"order_id": ev.raw.get("orderId")},
# #                 sig_type="copy",
# #                 ev_raw=ev,
# #             )
# #             return

# #         # ---------------- DEAL ----------------
# #         if et == "deal":
# #             price = Utils.safe_float(ev.raw.get("price"))
# #             if price:
# #                 self._last_deal[(symbol, pos_side)] = {"price": price, "ts": ev.ts}
# #             return

# #         # ---------------- TRIGGER ----------------
# #         if et in ("plan_order", "plan_executed", "plan_cancelled"):
# #             trigger_price = Utils.safe_float(
# #                 ev.raw.get("triggerPrice") or ev.raw.get("price")
# #             )
# #             if not trigger_price:
# #                 return

# #             pv["_last_exec_source"] = "trigger"

# #             if et == "plan_executed":
# #                 event, sig = "filled", "log"
# #             elif et == "plan_order":
# #                 event, sig = "buy" if ev.raw.get("side") in (1, 3) else "sell", "copy"
# #             else:
# #                 event, sig = "canceled", "copy"

# #             await self._emit(
# #                 event=event,
# #                 method="trigger",
# #                 symbol=symbol,
# #                 pos_side=pos_side,
# #                 partially=False,
# #                 payload={
# #                     "order_id": ev.raw.get("orderId"),
# #                     "qty": Utils.safe_float(ev.raw.get("vol")),
# #                     "trigger_price": trigger_price,
# #                     "leverage": ev.raw.get("leverage"),
# #                     "open_type": ev.raw.get("openType"),
# #                     "reduce_only": bool(ev.raw.get("reduceOnly")),
# #                     "trigger_exec": ev.raw.get("triggerType"),
# #                 },
# #                 sig_type=sig,
# #                 ev_raw=ev,
# #             )
# #             return

# #         # ---------------- POSITION SNAPSHOT ----------------
# #         if et in ("position_opened", "position_closed"):
# #             await self._on_position_snapshot(ev, pv)

# #     # ==========================================================
# #     async def _on_position_snapshot(self, ev: "SignalEvent", pv: dict):
# #         raw = ev.raw
# #         symbol, pos_side = ev.symbol, ev.pos_side
# #         key = (symbol, pos_side)

# #         if self._is_stale_snapshot(key, raw):
# #             return

# #         qty_prev = pv["qty"]
# #         qty_cur = Utils.safe_float(raw.get("holdVol"), 0.0)

# #         if qty_prev == qty_cur:
# #             return

# #         price = Utils.to_human_digit(self._fix_price(raw, symbol, pos_side))
# #         last_src = pv["_last_exec_source"]

# #         oco = self._attached_oco.pop(symbol, None)

# #         if oco:
# #             pv["_attached_tp"] = oco.get("tp")
# #             pv["_attached_sl"] = oco.get("sl")

# #         delta = abs(qty_cur - qty_prev)

# #         # ================= BUY =================
# #         if qty_cur > qty_prev:
# #             pv["qty"] = qty_cur
# #             pv["in_position"] = True

# #             payload = {
# #                 "qty": delta,
# #                 "price": price,
# #                 "leverage": raw.get("leverage"),
# #                 "open_type": raw.get("openType"),
# #                 "reduce_only": False,
# #                 "qty_delta": delta,
# #                 "qty_before": qty_prev,
# #                 "qty_after": qty_cur,
# #             }

# #             if pv.get("_attached_tp") is not None:
# #                 payload["tp_price"] = pv["_attached_tp"]
# #             if pv.get("_attached_sl") is not None:
# #                 payload["sl_price"] = pv["_attached_sl"]

# #             # sig_type = (
# #             #     "log"
# #             #     if last_src in ("limit", "trigger") and qty_prev == 0
# #             #     else "copy"
# #             # )
# #             sig_type = "log" if last_src in ("limit", "trigger") else "copy"

# #             await self._emit(
# #                 event="buy",
# #                 method="market",
# #                 symbol=symbol,
# #                 pos_side=pos_side,
# #                 partially=qty_prev > 0,
# #                 payload=payload,
# #                 sig_type=sig_type,
# #                 ev_raw=ev,
# #             )

# #             pv["_attached_tp"] = None
# #             pv["_attached_sl"] = None

# #         # ================= SELL =================
# #         elif qty_cur < qty_prev:
# #             pv["qty"] = qty_cur
# #             pv["in_position"] = qty_cur > 0

# #             is_full_close = qty_cur == 0
# #             sig_type = (
# #                 "log"
# #                 if last_src in ("limit", "trigger") and is_full_close
# #                 else "copy"
# #             )

# #             payload = {
# #                 "qty": delta,
# #                 "price": price,
# #                 "leverage": raw.get("leverage"),
# #                 "open_type": raw.get("openType"),
# #                 "reduce_only": True,
# #                 "qty_delta": delta,
# #                 "qty_before": qty_prev,
# #                 "qty_after": qty_cur,
# #             }

# #             await self._emit(
# #                 event="sell",
# #                 method="market",
# #                 symbol=symbol,
# #                 pos_side=pos_side,
# #                 partially=qty_cur > 0,
# #                 payload=payload,
# #                 sig_type=sig_type,
# #                 ev_raw=ev,
# #                 closed=is_full_close,
# #             )

# #             if is_full_close:
# #                 self._pos_state.pop(key, None)
# #                 self._last_deal.pop(key, None)

# #         if qty_prev == 0 and qty_cur > 0:
# #             pv["entry_price"] = price

# #         pv["avg_price"] = price
# #         pv["_last_exec_source"] = None

# #     # ==========================================================
# #     async def _emit(
# #         self,
# #         *,
# #         event: HL_EVENT,
# #         method: METHOD,
# #         symbol: str,
# #         pos_side: str,
# #         partially: bool,
# #         payload: Dict[str, Any],
# #         sig_type: Literal["copy", "log"],
# #         ev_raw: Optional["SignalEvent"],
# #         closed: bool = False,
# #     ):
# #         exec_ts = now()
# #         raw_ts = ev_raw.ts if ev_raw else None

# #         payload = dict(payload)
# #         payload["exec_ts"] = exec_ts
# #         payload["latency_ms"] = exec_ts - raw_ts if raw_ts else None

# #         self._pending.append(
# #             MasterEvent(
# #                 event=event,
# #                 method=method,
# #                 symbol=symbol,
# #                 pos_side=pos_side,
# #                 partially=partially,
# #                 closed=closed,
# #                 payload=payload,
# #                 sig_type=sig_type,
# #                 ts=exec_ts,
# #             )
# #         )

# 1. тип сигнала log -- удалить к ебаной матери. это мусор.
# 2. должно нормально копировать лимитки, отмены лимиток. новые лимитки.
# 3. есть четкий флаг на стороне копи closed -- partially и reduceOnly на стороне копи -- туда же куда и пункт 1.
# 4. при исполнении лимиток не должно событие исполнения ордера интерпретировать как новый сигнал по рынку. В противном случае будет двойной вход.
# 5. Тригерные ордера -- само собой. Должны работать по такому же принципу как и лимитные
# 6. Лимитные ордера будь то по маркету, если имеют параметры стоп лосс и тейк профит цены должны копироваться. еще. когда будешь переписывать, не вооди никакие новые имена полей (например тектов и стопов)
# 7. Основная проблема последнего закоментированного кода была в том что он событие исполнение лимитки иногда (не всегда) интерпретировал как вход по рынку и кидал сигнал (смотри пункт 4). 
# Итак жду от тебя новый MASTER.payload_.py





    # # --------------------------------------------------
    # # HANDLERS
    # # --------------------------------------------------

    # async def _handle_order(self, data):
    #     symbol = normalize_symbol(data.get("symbol"), self.quota_asset)
    #     side_code = int(data.get("side", 0))
    #     side = side_from_order_side(side_code)

    #     state = int(data.get("state", 0))
    #     order_type = int(data.get("orderType", 0))

        # if order_type == 5:
        #     etype = "open_market" if side_code in (1, 3) else "close_market"
        # elif order_type == 1:
        #     etype = "open_limit" if side_code in (1, 3) else "close_limit"
        # else:
        #     etype = "trigger_order"


    #     await self._emit(symbol, side, etype, data)

    #     if state in (1, 2):
    #         await self._emit(
    #             symbol, side,
    #             "open_pending" if side_code in (1, 3) else "close_pending",
    #             data,
    #         )

    #     if state == 4:
    #         await self._emit(symbol, side, "order_cancelled", data)
    #     elif state == 5:
    #         await self._emit(symbol, side, "order_invalid", data)




from __future__ import annotations

# import asyncio
# from dataclasses import dataclass, field
# from typing import *

# from MASTER.state_ import PosVarSetup
# from c_utils import Utils, now

# if TYPE_CHECKING:
#     from MASTER.state_ import SignalCache, SignalEvent
#     from b_context import MainContext
#     from c_log import UnifiedLogger


# # =====================================================================
# # HL PROTOCOL
# # =====================================================================

# HL_EVENT = Literal["buy", "sell", "canceled"]
# METHOD = Literal["market", "limit", "trigger"]


# # =====================================================================
# # MASTER EVENT
# # =====================================================================

# @dataclass
# class MasterEvent:
#     event: HL_EVENT
#     method: METHOD
#     symbol: str
#     pos_side: str
#     closed: bool                     # ← СВЯТОЙ ФЛАГ
#     payload: Dict[str, Any]
#     sig_type: Literal["copy", "manual"]
#     ts: int = field(default_factory=now)


# # =====================================================================
# # MASTER PAYLOAD (EXECUTION-ONLY)
# # =====================================================================

# class MasterPayload:
#     """
#     EXECUTION-ONLY PAYLOAD

#     ИСТИНЫ:
#     • Источник сигналов — ТОЛЬКО execution reports
#     • Snapshot НИКОГДА не генерит market / limit сигналы
#     • closed — единственный управляющий флаг
#     """

#     def __init__(
#         self,
#         cache: "SignalCache",
#         mc: "MainContext",
#         logger: "UnifiedLogger",
#         stop_flag: Callable[[], bool],
#     ):
#         self.cache = cache
#         self.mc = mc
#         self.logger = logger
#         self.stop_flag = stop_flag

#         self._pending: list[MasterEvent] = []
#         self._stop = False

#         self.out_queue = asyncio.Queue(maxsize=1000)

#     # ==================================================
#     def stop(self):
#         self._stop = True
#         self.mc.pos_vars_root.clear()
#         self.logger.info("MasterPayload: stop requested")

#     # ==================================================
#     async def run(self):
#         self.logger.info("MasterPayload READY")

#         while not self._stop and not self.stop_flag():
#             await self.cache._event_notify.wait()
#             events = await self.cache.pop_events()

#             for ev in events:
#                 self._route(ev)

#             for mev in self._pending:
#                 await self.out_queue.put(mev)

#             self._pending.clear()

#         self.logger.info("MasterPayload STOPPED")

#     # ==================================================
#     def _ensure_pv(self, symbol: str, pos_side: str) -> dict:
#         PosVarSetup.set_pos_defaults(
#             self.mc.pos_vars_root,
#             symbol,
#             pos_side,
#             instruments_data=self.mc.instruments_data,
#         )
#         return self.mc.pos_vars_root[symbol][pos_side]

#     # ==================================================
#     def _route(self, ev: "SignalEvent"):
#         et = ev.event_type
#         symbol, pos_side = ev.symbol, ev.pos_side
#         if not symbol or not pos_side:
#             return

#         pv = self._ensure_pv(symbol, pos_side)

#         # ==================================================
#         # MARKET EXECUTION
#         # ==================================================
#         if et in ("open_market", "close_market"):
#             reduce_only = bool(ev.raw.get("reduceOnly"))
#             is_close = (et == "close_market") or reduce_only

#             if is_close: pos_side = {"LONG": "SHORT", "SHORT": "LONG"}.get(pos_side.upper())

#             self._emit(
#                 event="sell" if is_close else "buy",
#                 method="market",
#                 symbol=symbol,
#                 pos_side=pos_side,
#                 closed=is_close,
#                 payload={
#                     "order_id": ev.raw.get("orderId"),
#                     "qty": Utils.safe_float(ev.raw.get("vol")),
#                     "price": Utils.safe_float(
#                         ev.raw.get("price")
#                         or ev.raw.get("dealAvgPrice")
#                         or ev.raw.get("avgPrice")
#                     ),
#                     "leverage": ev.raw.get("leverage"),
#                     "open_type": ev.raw.get("openType"),
#                     "reduce_only": reduce_only,
#                 },
#                 ev_raw=ev,
#             )
#             return

#         # ==================================================
#         # LIMIT EXECUTION
#         # ==================================================
#         if et in ("open_limit", "close_limit"):
#             reduce_only = bool(ev.raw.get("reduceOnly"))
#             is_close = (et == "close_limit") or reduce_only

#             self._emit(
#                 event="sell" if is_close else "buy",
#                 method="limit",
#                 symbol=symbol,
#                 pos_side=pos_side,
#                 closed=is_close,
#                 payload={
#                     "order_id": ev.raw.get("orderId"),
#                     "qty": Utils.safe_float(ev.raw.get("vol")),
#                     "price": Utils.safe_float(ev.raw.get("price")),
#                     "leverage": ev.raw.get("leverage"),
#                     "open_type": ev.raw.get("openType"),
#                     "reduce_only": reduce_only,
#                 },
#                 ev_raw=ev,
#             )
#             return

#         # ==================================================
#         # LIMIT / MARKET CANCEL
#         # ==================================================
#         if et in ("order_cancelled", "order_invalid"):
#             self._emit(
#                 event="canceled",
#                 method="limit",
#                 symbol=symbol,
#                 pos_side=pos_side,
#                 closed=False,
#                 payload={
#                     "order_id": ev.raw.get("orderId"),
#                 },
#                 ev_raw=ev,
#             )
#             return

#         # ==================================================
#         # TRIGGER EXECUTION
#         # ==================================================
#         if et == "plan_executed":
#             reduce_only = bool(ev.raw.get("reduceOnly"))
#             is_sell = ev.raw.get("side") not in (1, 3)

#             self._emit(
#                 event="sell" if is_sell else "buy",
#                 method="trigger",
#                 symbol=symbol,
#                 pos_side=pos_side,
#                 closed=reduce_only,
#                 payload={
#                     "order_id": ev.raw.get("orderId"),
#                     "qty": Utils.safe_float(ev.raw.get("vol")),
#                     "trigger_price": Utils.safe_float(ev.raw.get("triggerPrice")),
#                     "leverage": ev.raw.get("leverage"),
#                     "open_type": ev.raw.get("openType"),
#                     "reduce_only": reduce_only,
#                     "trigger_exec": ev.raw.get("triggerType"),
#                 },
#                 ev_raw=ev,
#             )
#             return

#         # --------------------------------------------------
#         # TRIGGER CANCEL
#         # --------------------------------------------------
#         if et == "plan_cancelled":
#             self._emit(
#                 event="canceled",
#                 method="trigger",
#                 symbol=symbol,
#                 pos_side=pos_side,
#                 closed=False,
#                 payload={
#                     "order_id": ev.raw.get("orderId"),
#                 },
#                 ev_raw=ev,
#             )
#             return

#         # ==================================================
#         # POSITION SNAPSHOT (STATE ONLY, NO SIGNALS)
#         # ==================================================
#         if et in ("position_opened", "position_closed"):
#             pv["qty"] = Utils.safe_float(ev.raw.get("holdVol"), 0.0)
#             pv["in_position"] = pv["qty"] > 0
#             pv["avg_price"] = Utils.safe_float(
#                 ev.raw.get("avgPrice")
#                 or ev.raw.get("openAvgPrice")
#                 or ev.raw.get("price")
#             )
#             return

#     # ==================================================
#     @staticmethod
#     def _extract_exchange_ts(ev_raw: "SignalEvent") -> Optional[int]:
#         if not ev_raw:
#             return None

#         raw = ev_raw.raw or {}

#         for key in ("updateTime", "createTime", "timestamp", "time", "ts"):
#             val = raw.get(key)
#             if isinstance(val, (int, float)) and val > 0:
#                 val = int(val)
#                 if val < 10_000_000_000:  # sec → ms
#                     val *= 1000
#                 return val

#         return None

#     # ==================================================
#     def _emit(
#         self,
#         *,
#         event: HL_EVENT,
#         method: METHOD,
#         symbol: str,
#         pos_side: str,
#         payload: Dict[str, Any],
#         ev_raw: Optional["SignalEvent"],
#         closed: bool = False,
#         sig_type: Literal["copy", "manual"] = "copy",
#     ):
#         exec_ts = ev_raw.ts if ev_raw and ev_raw.ts else now()
#         exch_ts = self._extract_exchange_ts(ev_raw)

#         payload = dict(payload)
#         payload["exec_ts"] = exec_ts
        
#         payload["latency_ms"] = (
#             exec_ts - exch_ts if exch_ts else None
#         )

#         self._pending.append(
#             MasterEvent(
#                 event=event,
#                 method=method,
#                 symbol=symbol,
#                 pos_side=pos_side,
#                 closed=closed,
#                 payload=payload,
#                 sig_type=sig_type,
#                 ts=exec_ts,
#             )
#         )




# from __future__ import annotations

# import asyncio
# from dataclasses import dataclass, field
# from typing import *

# from c_utils import Utils, now
# from MASTER.state_ import PosVarSetup

# if TYPE_CHECKING:
#     from MASTER.state_ import SignalCache, SignalEvent
#     from b_context import MainContext
#     from c_log import UnifiedLogger


# # =====================================================================
# # HL PROTOCOL
# # =====================================================================

# HL_EVENT = Literal["buy", "sell", "canceled"]
# METHOD = Literal["market", "limit", "trigger"]


# # =====================================================================
# # MASTER EVENT
# # =====================================================================

# @dataclass
# class MasterEvent:
#     event: HL_EVENT
#     method: METHOD
#     symbol: str
#     pos_side: str
#     closed: bool
#     payload: Dict[str, Any]
#     sig_type: Literal["copy", "manual"]
#     ts: int = field(default_factory=now)


# # =====================================================================
# # MASTER PAYLOAD (EXECUTION-ONLY)
# # =====================================================================

# class MasterPayload:
#     """
#     EXECUTION-ONLY PAYLOAD

#     ИСТИНЫ:
#     • Источник сигналов — ТОЛЬКО execution reports
#     • LIMIT placed = intent
#     • LIMIT filled = market-effect
#     • reduceOnly НЕ используется для LIMIT
#     """

#     def __init__(
#         self,
#         cache: "SignalCache",
#         mc: "MainContext",
#         logger: "UnifiedLogger",
#         stop_flag: Callable[[], bool],
#     ):
#         self.cache = cache
#         self.mc = mc
#         self.logger = logger
#         self.stop_flag = stop_flag

#         self._pending: list[MasterEvent] = []
#         self._stop = False

#         self.out_queue = asyncio.Queue(maxsize=1000)
#         self._limit_intents: set[str] = set()

#     # ==================================================
#     def stop(self):
#         self._stop = True
#         self.mc.pos_vars_root.clear()
#         self.logger.info("MasterPayload: stop requested")

#     # ==================================================
#     async def run(self):
#         self.logger.info("MasterPayload READY")

#         while not self._stop and not self.stop_flag():
#             await self.cache._event_notify.wait()
#             events = await self.cache.pop_events()

#             for ev in events:
#                 self._route(ev)

#             for mev in self._pending:
#                 await self.out_queue.put(mev)

#             self._pending.clear()

#         self.logger.info("MasterPayload STOPPED")

#     # ==================================================
#     def _ensure_pv(self, symbol: str, pos_side: str) -> dict:
#         PosVarSetup.set_pos_defaults(
#             self.mc.pos_vars_root,
#             symbol,
#             pos_side,
#             instruments_data=self.mc.instruments_data,
#         )
#         return self.mc.pos_vars_root[symbol][pos_side]

#     # ==================================================
#     def _route(self, ev: "SignalEvent"):
#         et = ev.event_type
#         symbol, pos_side = ev.symbol, ev.pos_side
#         if not symbol or not pos_side:
#             return

#         raw = ev.raw or {}

#         # ==================================================
#         # MARKET FILLED
#         # ==================================================
#         if et == "market_filled":
#             raw = ev.raw or {}

#             reduce_only = bool(raw.get("reduceOnly"))
#             is_close = reduce_only

#             emit_side = pos_side
#             if is_close:
#                 emit_side = {"LONG": "SHORT", "SHORT": "LONG"}[pos_side]

#             self._emit(
#                 event="sell" if is_close else "buy",
#                 method="market",
#                 symbol=symbol,
#                 pos_side=emit_side,
#                 closed=is_close,
#                 payload=self._base_payload(raw),
#                 ev_raw=ev,
#             )
#             return

#         # ==================================================
#         # LIMIT FILLED (execution)
#         # ==================================================
#         if et == "limit_filled":
#             raw = ev.raw or {}
#             oid = raw.get("orderId")

#             # если это intent → НИКАКОГО сигнала
#             if oid in self._limit_intents:
#                 self._limit_intents.discard(oid)
#                 return

#             # иначе — это ручная лимитка (hotkey OPEN)
#             self._emit(
#                 event="buy",
#                 method="limit",
#                 symbol=symbol,
#                 pos_side=pos_side,
#                 closed=False,
#                 payload=self._base_payload(raw),
#                 ev_raw=ev,
#             )
#             return


#         # ==================================================
#         # LIMIT PLACED (INTENT)
#         # ==================================================
#         if et == "limit_placed":
#             oid = raw.get("orderId")
#             if oid:
#                 self._limit_intents.add(oid)

#             self._emit(
#                 event="buy",
#                 method="limit",
#                 symbol=symbol,
#                 pos_side=pos_side,
#                 closed=False,
#                 payload=self._base_payload(raw),
#                 ev_raw=ev,
#             )
#             return

#         # ==================================================
#         # TRIGGER FILLED
#         # ==================================================
#         if et == "trigger_filled":
#             reduce_only = bool(raw.get("reduceOnly"))
#             is_sell = raw.get("side") not in (1, 3)

#             emit_side = pos_side
#             if reduce_only:
#                 emit_side = {"LONG": "SHORT", "SHORT": "LONG"}[pos_side]

#             self._emit(
#                 event="sell" if is_sell else "buy",
#                 method="trigger",
#                 symbol=symbol,
#                 pos_side=emit_side,
#                 closed=reduce_only,
#                 payload=self._base_payload(raw),
#                 ev_raw=ev,
#             )
#             return

#         # ==================================================
#         # CANCEL
#         # ==================================================
#         if et in ("order_cancelled", "order_invalid"):
#             oid = raw.get("orderId")
#             if oid:
#                 self._limit_intents.discard(oid)

#             self._emit(
#                 event="canceled",
#                 method="limit",
#                 symbol=symbol,
#                 pos_side=pos_side,
#                 closed=False,
#                 payload={"order_id": raw.get("orderId")},
#                 ev_raw=ev,
#             )
#             return

#     # ==================================================
#     @staticmethod
#     def _base_payload(raw: dict) -> dict:
#         return {
#             "order_id": raw.get("orderId"),
#             "qty": Utils.safe_float(raw.get("vol")),
#             "price": Utils.safe_float(
#                 raw.get("price")
#                 or raw.get("dealAvgPrice")
#                 or raw.get("avgPrice")
#             ),
#             "leverage": raw.get("leverage"),
#             "open_type": raw.get("openType"),
#             "reduce_only": bool(raw.get("reduceOnly")),
#         }

#     # ==================================================
#     @staticmethod
#     def _extract_exchange_ts(ev_raw: "SignalEvent") -> Optional[int]:
#         if not ev_raw:
#             return None
#         raw = ev_raw.raw or {}
#         for key in ("updateTime", "createTime", "timestamp", "time", "ts"):
#             val = raw.get(key)
#             if isinstance(val, (int, float)) and val > 0:
#                 if val < 10_000_000_000:
#                     val *= 1000
#                 return int(val)
#         return None

#     # ==================================================
#     def _emit(
#         self,
#         *,
#         event: HL_EVENT,
#         method: METHOD,
#         symbol: str,
#         pos_side: str,
#         payload: Dict[str, Any],
#         ev_raw: Optional["SignalEvent"],
#         closed: bool = False,
#         sig_type: Literal["copy", "manual"] = "copy",
#     ):
#         exec_ts = ev_raw.ts if ev_raw else now()
#         exch_ts = self._extract_exchange_ts(ev_raw)

#         payload = dict(payload)
#         payload["exec_ts"] = exec_ts
#         payload["latency_ms"] = exec_ts - exch_ts if exch_ts else None

#         self._pending.append(
#             MasterEvent(
#                 event=event,
#                 method=method,
#                 symbol=symbol,
#                 pos_side=pos_side,
#                 closed=closed,
#                 payload=payload,
#                 sig_type=sig_type,
#                 ts=exec_ts,
#             )
#         )



# # COPY.copy_.py

# from __future__ import annotations

# import asyncio
# from typing import *
# # import random
# import time

# from a_config import TG_LOG_TTL_MS, IS_REPORT
# from c_log import UnifiedLogger
# from c_utils import now

# from .pv_fsm_ import PosMonitorFSM, PreparePnlReport
# from .state_ import CopyOrderIntentFactory
# from .exequter_ import CopyExequter
# from TG.notifier_ import FormatUILogs
# from MASTER.payload_ import MasterEvent

# if TYPE_CHECKING:
#     from .state_ import CopyState
#     from b_context import MainContext
#     from MASTER.payload_ import MasterPayload


# # ==================================================
# # SNAPSHOT HASH (STATE CONVERGENCE)
# # ==================================================
# def snapshot_hash(position_vars: Dict[str, Dict[str, dict]]) -> int:
#     items = []

#     for symbol in sorted(position_vars):
#         for side in sorted(position_vars[symbol]):
#             pv = position_vars[symbol][side]
#             items.append((
#                 symbol,
#                 side,
#                 pv.get("in_position", False),
#                 pv.get("qty", 0),
#                 pv.get("_state"),        # 🔥 КЛЮЧ
#                 pv.get("_entry_ts"),     # 🔒 защищает от двойного close
#             ))

#     return hash(tuple(items))


# # ==================================================
# # SAFE REFRESH
# # ==================================================
# async def safe_refresh(m: PosMonitorFSM, timeout: float=2) -> bool:
#     try:
#         await asyncio.wait_for(m.refresh(), timeout=timeout)
#         return True
#     except asyncio.TimeoutError:
#         return False
#     except Exception:
#         return False
    

# async def refresh_with_retry(
#     monitors: Dict[int, PosMonitorFSM],
#     *,
#     start_delay: float = 0.05,      # 50 ms
#     backoff: float = 1.25,
#     max_delay: float = 0.5,
#     max_attempts: int = 10,
#     timeout: float = 10.0,
# ) -> None:
#     if not monitors:
#         return

#     delay = start_delay

#     start_time = time.monotonic()

#     for _ in range(max_attempts):
#         if time.monotonic() - start_time >= timeout:
#             return
        
#         await asyncio.gather(
#             *[safe_refresh(m) for m in monitors.values()],
#             return_exceptions=True,
#         )

#         cur_hash = tuple(
#             snapshot_hash(m.position_vars)
#             for m in monitors.values()
#         )

#         if cur_hash == prev_hash:
#             return

#         prev_hash = cur_hash

#         await asyncio.sleep(delay)
#         delay = min(delay * backoff, max_delay)


# # ==================================================
# # COPY DISTRIBUTOR
# # ==================================================
# class CopyDestrib:
#     """
#     CopyDestrib — неблокирующий intake + сериализованный executor.
#     """

#     def __init__(
#         self,
#         mc: "MainContext",
#         logger: UnifiedLogger,
#         copy_state: CopyState,
#         stop_flag: Callable[[], bool],
#     ):
#         self.mc = mc
#         self.logger = logger
#         self.copy_state = copy_state
#         self.stop_flag = stop_flag

#         self.payload: Optional["MasterPayload"] = None

#         self._stop_signal_loop = True
#         self._stop_tracker = True
#         self._last_log_flush_ts: int = 0
#         self._pnl_results: List = []

#         self.intent_factory = CopyOrderIntentFactory(self.mc)
#         self.reset_pv_state = PreparePnlReport(self.mc, self.logger)
#         self._exequter = CopyExequter(self.mc, self.logger)

#         # 🔒 строгая сериализация исполнения сигналов
#         self._exec_sem = asyncio.Semaphore(1)

#     # ==================================================
#     # PAYLOAD
#     # ==================================================

#     def attach_payload(self, payload: "MasterPayload"):
#         self.payload = payload
#         self.logger.info("CopyDestrib: payload attached")

#     # ==================================================
#     # STOP API
#     # ==================================================

#     def stop_signal_loop(self):
#         self.logger.info("CopyDestrib: stop_signal_loop()")
#         self._stop_signal_loop = True

#     # ==================================================
#     # UI LOG FLUSH WITH TTL
#     # ==================================================

#     async def _flush_notify_with_ttl(self) -> None:
#         """
#         Flushes accumulated UI logs with TTL.
#         Non-blocking for main pipeline.
#         """
#         if not self.mc.log_events:
#             return

#         now_ts = now()

#         if (
#             self._last_log_flush_ts == 0
#             or now_ts - self._last_log_flush_ts >= TG_LOG_TTL_MS
#         ):
#             texts = FormatUILogs.flush_log_events(self.mc.log_events)

#             if texts or self._pnl_results:
#                 self._last_log_flush_ts = now_ts

#             if texts:
#                 await self.mc.tg_notifier.send_block(texts)

#             if IS_REPORT:
#                 # 🔒 финальный отчёт
#                 if self._pnl_results:
#                     texts: list[str] = []
#                     texts.extend(FormatUILogs.format_general_report(self._pnl_results))
#                     texts.append(FormatUILogs.format_general_summary(self._pnl_results))
#                     self._pnl_results.clear()
#                     await self.mc.tg_notifier.send_block(texts)

#     # ==================================================
#     # MANUAL CLOSE EXPANDER
#     # ==================================================

#     async def _expand_manual_close(
#         self,
#         mev: MasterEvent,
#     ) -> List[MasterEvent]:
#         """
#         Expands manual CLOSE intent into atomic close events.
#         """
#         events: List[MasterEvent] = []

#         for cid in self.mc.cmd_ids:
#             rt = self.copy_state.ensure_copy_state(cid)
#             if not rt:
#                 continue

#             position_vars = rt.get("position_vars") or {}

#             for symbol, sides in position_vars.items():
#                 for pos_side, pv in sides.items():
#                     if not pv.get("in_position"):
#                         continue

#                     qty = pv.get("qty")
#                     if not qty or qty <= 0:
#                         continue

#                     sub = MasterEvent(
#                         event="sell",
#                         method="market",
#                         symbol=symbol,
#                         pos_side=pos_side,
#                         closed=True,
#                         sig_type="manual",
#                         payload={
#                             "qty": qty,
#                             "reduce_only": True,
#                             "leverage": pv.get("leverage"),
#                             "open_type": pv.get("margin_mode"),
#                         },
#                         ts=mev.ts,
#                     )

#                     # 🔒 жёсткая привязка к конкретному copy-id
#                     sub._cid = cid
#                     events.append(sub)

#         return events

#     # ==================================================
#     # INTERNAL: FAN-OUT (COPY / LOG ONLY)
#     # ==================================================

#     async def _broadcast_to_copies(
#         self,
#         mev: "MasterEvent",
#         monitors: Dict[int, PosMonitorFSM],
#     ):
#         if mev.sig_type not in ("copy"):
#             return

#         # UI лог мастера
#         self.mc.log_events.append((0, mev))

#         tasks: list[asyncio.Task] = []

#         for cid, cfg in self.mc.copy_configs.items():

#             if cid == 0 or not cfg or not cfg.get("enabled"):
#                 continue

#             rt = self.copy_state.ensure_copy_state(cid)
#             if not rt:
#                 continue

#             tasks.append(
#                 asyncio.create_task(
#                     self._exequter.handle_copy_event(cid, cfg, rt, mev, monitors)
#                 )
#             )

#         if tasks:
#             await asyncio.gather(*tasks, return_exceptions=False)

#     # ==================================================
#     # EXECUTOR (SERIALIZED)
#     # ==================================================

#     async def _execute_signal(self, mev: "MasterEvent"):        

#         local_monitors: Dict[int, PosMonitorFSM] = {}
#         results: list[dict] = []
#         ids = 0

#         try:
#             if mev.sig_type == "manual":
#                 # ⚠️ manual-event — уже атомарный
#                 cid = getattr(mev, "_cid", None)
#                 if cid is None:
#                     return

#                 cfg = self.mc.copy_configs.get(cid)
#                 rt = self.copy_state.ensure_copy_state(cid)
#                 if not cfg or not rt:
#                     return

#                 await self._exequter.handle_copy_event(
#                     cid, cfg, rt, mev, local_monitors
#                 )

#             else:
#                 async with self._exec_sem:
#                     # print("_broadcast_to_copies")
#                     await self._broadcast_to_copies(mev, local_monitors)

#             ids = list(local_monitors.keys())

#             # if mev.method.upper() == "MARKET" and local_monitors:
#             if local_monitors:
#                 await refresh_with_retry(local_monitors)

#         except Exception:
#             self.logger.exception(
#                 "[CopyDestrib] execute_signal failed",
#             )

#         finally:
#             # if IS_REPORT and ids:
#             #     results = await self.reset_pv_state.assum_positions(ids)
#             #     if results:
#             #         self._pnl_results.extend(results)

#             await self._flush_notify_with_ttl()


#     async def _execute_and_ack(self, mev: "MasterEvent"):
#         try:
#             await self._execute_signal(mev)
#         except Exception:
#             self.logger.exception("[CopyDestrib] execute_and_ack failed")
#         finally:
#             # ✅ ACK ТОЛЬКО ПОСЛЕ ОБРАБОТКИ
#             self.payload.out_queue.task_done()
#             # pass

#     # ==================================================
#     # SIGNAL LOOP (INTAKE)
#     # ==================================================

#     async def signal_loop(self):
#         if not self.payload:
#             self.logger.error("CopyDestrib: payload not attached")
#             return

#         self.logger.info("CopyDestrib: signal_loop STARTED")

#         self._stop_signal_loop = False
#         self._stop_tracker = False

#         # ожидание разрешения торговли
#         while not self.stop_flag() and not self._stop_signal_loop:
#             master_rt = self.mc.copy_configs.get(0, {}).get("cmd_state", {})
#             if master_rt.get("trading_enabled") and not master_rt.get("stop_flag"):
#                 break
#             await asyncio.sleep(0.1)

#         if self._stop_signal_loop:
#             return

#         self.logger.info("CopyDestrib: READY")

#         while not self.stop_flag() and not self._stop_signal_loop:
#             try:
#                 # ======================================================
#                 # 1️⃣ берём ОДНО master-событие
#                 # ======================================================
#                 mev: "MasterEvent" = await self.payload.out_queue.get()
#                 # print(mev)
#                 # self.payload.out_queue.task_done()

#                 print(
#                     "\n=== MASTER EVENT ===",
#                     f"\n ts={mev.ts}",
#                     f"\n event={mev.event}",
#                     f"\n method={mev.method}",
#                     f"\n symbol={mev.symbol}",
#                     f"\n side={mev.pos_side}",
#                     f"\n closed={mev.closed}",
#                     f"\n sig_type={mev.sig_type}",
#                     f"\n payload={mev.payload}",
#                     "\n====================\n",
#                 )

#                 if self._stop_tracker:
#                     break

#                 if mev.sig_type == "manual":
#                     expanded = await self._expand_manual_close(mev)

#                     for sub_mev in expanded:
#                         task = asyncio.create_task(self._execute_signal(sub_mev))
#                         self.mc.background_tasks.add(task)
#                         task.add_done_callback(self.mc.background_tasks.discard)

#                     # ✅ ACK ровно ОДИН — за исходный manual intent
#                     self.payload.out_queue.task_done()
#                     self.mc.cmd_ids.clear()

#                 else:
#                     task = asyncio.create_task(self._execute_and_ack(mev))
#                     self.mc.background_tasks.add(task)
#                     task.add_done_callback(self.mc.background_tasks.discard)
#                     pass

#             except asyncio.CancelledError:
#                 break

#         self.logger.info("CopyDestrib: signal_loop FINISHED")

#     #     # # TEST MODE: изоляция от саморепликации
#     #     # if TEST_MODE:
#     #     #     mev = copy.deepcopy(mev)
#     #     #     mev.symbol = "FET_USDT"