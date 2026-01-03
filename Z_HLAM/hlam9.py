# # MASTER.master_payload.py

# from __future__ import annotations

# import asyncio
# import time
# from dataclasses import dataclass, field
# from typing import Dict, Tuple, Optional, Literal, Any, List, Callable

# from MASTER.signal_cache import SignalCache, SignalEvent, PosVarSetup
# from c_utils import Utils
# from a_config import OPEN_TTL
# from b_context import MainContext
# from c_log import ErrorHandler


# # =====================================================================
# # HL PROTOCOL
# # =====================================================================

# HL_EVENT = Literal["buy", "sell", "canceled", "filled"]
# METHOD = Literal["market", "limit", "tp", "sl"]


# @dataclass
# class MasterEvent:
#     event: HL_EVENT
#     method: METHOD
#     symbol: str
#     side: str
#     partially: bool
#     payload: Dict[str, Any]
#     sig_type: Literal["copy", "log"]
#     ts: float = field(default_factory=time.time)


# # =====================================================================
# # MASTER PAYLOAD
# # =====================================================================

# class MasterPayload:
#     """
#     MasterPayload — high-level агрегатор и интерпретатор сигналов мастера.

#     Назначение:
#         • принимает RAW события из SignalCache
#         • определяет причинно-следственную связь между ордерами и snapshot-ами позиции
#         • преобразует события в HL-протокол (MasterEvent)
#         • решает, является ли событие копируемым (sig_type="copy")
#           или служебным/логируемым (sig_type="log")

#     Внутренняя схема работы:

#         WS / Stream
#              │
#              ▼
#         SignalCache
#              │  (RAW SignalEvent)
#              ▼
#         MasterPayload._route(ev)
#              │
#              ├─ plan_order / plan_executed / plan_cancelled
#              │     → _handle_plan()
#              │     → фиксируется _last_exec_source (tp / sl)
#              │     → генерируется HL-событие (sell / filled / canceled)
#              │
#              ├─ deal
#              │     → обновляется последняя цена (_last_deal)
#              │
#              └─ position_opened / position_closed
#                    → _on_position_snapshot()
#                    → сравнение qty_prev vs qty_cur
#                    → определение BUY / SELL
#                    → классификация sig_type:
#                         • log  — если snapshot подтверждает ранее зафиксированное
#                                  исполнение (tp / sl / limit)
#                         • copy — если изменение qty произошло без зафиксированной
#                                  причины (ручной маркет, внешний бот, и т.п.)
#                    → сброс _last_exec_source

#         MasterEvent
#              │
#              ▼
#         out_queue → CopyDestrib → CopyExecutor

#     Ключевые принципы:
#         • Snapshot позиции — единственный источник истины по qty
#         • Наличие активных ордеров НЕ используется как причина изменения qty
#         • Причина изменения фиксируется только фактом исполнения (plan / limit fill)
#         • Каждое исполнение влияет ровно на один snapshot (одноразовый маркер)

#     Результат:
#         • корректное различение copy / log
#         • отсутствие ложных подавлений сигналов
#         • устойчивость к ручным действиям и внешним ботам
#     """

#     def __init__(
#         self,
#         cache: SignalCache,
#         mc: MainContext,
#         logger: ErrorHandler,
#         stop_flag: Callable,
#     ):
#         self.cache = cache
#         self.mc = mc
#         self.log = logger
#         self.stop_flag = stop_flag

#         self._pos_vars_root = None
#         self._pending: List[MasterEvent] = []
#         self._stop = False

#         self._pos_state: Dict[Tuple[str, str], Dict[str, Any]] = {}
#         self.out_queue = asyncio.Queue()
#         self._last_deal = {}

#     # ==========================================================
#     def stop(self):
#         self._stop = True

#     # ==========================================================
#     async def run(self):
#         print("✔ MasterPayload READY")

#         while not self._stop and not self.stop_flag():
#             await self.cache._event_notify.wait()
#             raw_events = await self.cache.pop_events()

#             for ev in raw_events:
#                 await self._route(ev)

#             out = self._pending[:]
#             self._pending.clear()

#             for mev in out:
#                 await self.out_queue.put(mev)

#         print("🛑 MasterPayload STOPPED")

#     # ==========================================================
#     def _ensure_pos_vars(self, symbol: str, side: str) -> dict:
#         if self._pos_vars_root is None:
#             root = self.mc.copy_configs.setdefault(0, {}).setdefault("runtime", {})
#             root.setdefault("position_vars", {})
#             self._pos_vars_root = root["position_vars"]

#         PosVarSetup.set_pos_defaults(
#             self._pos_vars_root,
#             symbol,
#             side,
#             instruments_data=self.mc.instruments_data,
#         )

#         pv = self._pos_vars_root[symbol][side]
#         pv.setdefault("_last_exec_source", None)  # tp / sl / limit / None
#         return pv

#     # ==========================================================
#     def _fix_price(self, raw, symbol=None, side=None):
#         for k in ("dealAvgPrice", "avgPrice", "price", "openAvgPrice"):
#             if raw.get(k):
#                 return Utils.safe_float(raw[k])

#         key = (symbol, side)
#         if key in self._last_deal:
#             return self._last_deal[key]["price"]

#         return None

#     # ==========================================================
#     def _detect_risk_method(self, raw) -> Optional[Literal["tp", "sl"]]:
#         pt = raw.get("planType")
#         if pt == 1:
#             return "tp"
#         if pt == 2:
#             return "sl"

#         trigger = Utils.safe_float(raw.get("triggerPrice"))
#         price = self._fix_price(raw)
#         if trigger and price:
#             return "tp" if trigger > price else "sl"
#         return None

#     # ==========================================================
#     def _is_stale_snapshot(self, key, raw) -> bool:
#         upd = raw.get("updateTime") or raw.get("timestamp") or 0
#         hold = raw.get("holdVol")

#         st = self._pos_state.get(key)
#         if not st:
#             self._pos_state[key] = {"upd": upd, "hold": hold}
#             return False

#         if upd < st["upd"]:
#             return True
#         if upd == st["upd"] and hold == st["hold"]:
#             return True

#         self._pos_state[key] = {"upd": upd, "hold": hold}
#         return False

#     # ==========================================================
#     async def _handle_plan(self, ev: SignalEvent, pv: dict):
#         raw = ev.raw
#         symbol, side = ev.symbol, ev.side

#         method = self._detect_risk_method(raw)
#         if not method:
#             return

#         pv["_last_exec_source"] = method

#         if ev.event_type == "plan_executed":
#             event, sig = "filled", "log"
#         elif ev.event_type == "plan_order":
#             event, sig = "sell", "copy"
#         else:
#             event, sig = "canceled", "copy"

#         await self._emit(
#             event=event,
#             method=method,
#             symbol=symbol,
#             side=side,
#             partially=False,
#             payload={
#                 "order_id": raw.get("orderId"),
#                 "price": Utils.safe_float(raw.get("triggerPrice") or raw.get("price")),
#             },
#             sig_type=sig,
#             ev_raw=ev,
#         )

#     # ==========================================================
#     async def _route(self, ev: SignalEvent):
#         et = ev.event_type
#         symbol, side = ev.symbol, ev.side
#         if not side:
#             return

#         pv = self._ensure_pos_vars(symbol, side)

#         # ======================================================
#         # LIMIT ORDER CREATED
#         # ======================================================
#         if et == "open_limit":
#             state = ev.raw.get("state")

#             # state=4 → это финал / отмена, BUY тут НЕЛЬЗЯ
#             if state == 4:
#                 return
            
#             pv["_last_exec_source"] = "limit"

#             await self._emit(
#                 event="buy",
#                 method="limit",
#                 symbol=symbol,
#                 side=side,
#                 partially=False,
#                 payload={
#                     "order_id": ev.raw.get("orderId"),
#                     "qty": Utils.safe_float(ev.raw.get("vol")),
#                     "price": Utils.safe_float(ev.raw.get("price")),
#                 },
#                 sig_type="copy",
#                 ev_raw=ev,
#             )
#             return

#         # ======================================================
#         # LIMIT ORDER CANCELLED / INVALID
#         # ======================================================
#         if et in ("order_cancelled", "order_invalid"):
#             pv["_last_exec_source"] = None  # важно!

#             await self._emit(
#                 event="canceled",
#                 method="limit",
#                 symbol=symbol,
#                 side=side,
#                 partially=False,
#                 payload={
#                     "order_id": ev.raw.get("orderId"),
#                     "price": Utils.safe_float(ev.raw.get("price")),
#                 },
#                 sig_type="copy",
#                 ev_raw=ev,
#             )
#             return

#         # ======================================================
#         # DEAL (price only)
#         # ======================================================
#         if et == "deal":
#             price = Utils.safe_float(ev.raw.get("price"))
#             if price:
#                 self._last_deal[(symbol, side)] = {"price": price, "ts": ev.ts}
#             return

#         # ======================================================
#         # PLAN ORDERS
#         # ======================================================
#         if et in ("plan_order", "plan_executed", "plan_cancelled"):
#             await self._handle_plan(ev, pv)
#             return

#         # ======================================================
#         # POSITION SNAPSHOT
#         # ======================================================
#         if et in ("position_opened", "position_closed"):
#             await self._on_position_snapshot(ev, pv)


#     # ==========================================================
#     async def _on_position_snapshot(self, ev: SignalEvent, pv: dict):
#         raw = ev.raw
#         symbol, side = ev.symbol, ev.side
#         key = (symbol, side)

#         if self._is_stale_snapshot(key, raw):
#             return

#         await asyncio.sleep(OPEN_TTL)

#         qty_prev = pv["qty"]
#         qty_cur = Utils.safe_float(raw.get("holdVol"), 0.0)

#         if qty_prev == qty_cur:
#             return

#         price = Utils.to_human_digit(self._fix_price(raw, symbol, side))
#         last_src = pv.get("_last_exec_source")

#         # ================= BUY =================
#         if qty_cur > qty_prev:
#             pv["qty"] = qty_cur
#             pv["in_position"] = True

#             sig_type = "log" if last_src in ("tp", "sl", "limit") else "copy"

#             await self._emit(
#                 event="buy",
#                 method="market",
#                 symbol=symbol,
#                 side=side,
#                 partially=qty_prev > 0,
#                 payload={
#                     "qty_delta": qty_cur - qty_prev,
#                     "qty_before": qty_prev,
#                     "qty_after": qty_cur,
#                     "price": price,
#                 },
#                 sig_type=sig_type,
#                 ev_raw=ev,
#             )

#         # ================= SELL =================
#         elif qty_cur < qty_prev:
#             pv["qty"] = qty_cur
#             pv["in_position"] = qty_cur > 0

#             is_full_close = qty_cur == 0
#             sig_type = "copy" if is_full_close else (
#                 "log" if last_src in ("tp", "sl", "limit") else "copy"
#             )

#             await self._emit(
#                 event="sell",
#                 method="market",
#                 symbol=symbol,
#                 side=side,
#                 partially=qty_cur > 0,
#                 payload={
#                     "qty_delta": qty_prev - qty_cur,
#                     "qty_before": qty_prev,
#                     "qty_after": qty_cur,
#                     "price": price,
#                 },
#                 sig_type=sig_type,
#                 ev_raw=ev,
#             )

#         # consume source marker
#         pv["_last_exec_source"] = None

#     # ==========================================================
#     async def _emit(
#         self,
#         *,
#         event: HL_EVENT,
#         method: METHOD,
#         symbol: str,
#         side: str,
#         partially: bool,
#         payload: Dict[str, Any],
#         sig_type: Literal["copy", "log"],
#         ev_raw: Optional[SignalEvent],
#     ):
#         exec_ts = int(time.time() * 1000)
#         raw_ts = ev_raw.ts if ev_raw else None

#         payload = dict(payload)
#         payload["exec_ts"] = exec_ts
#         payload["latency_ms"] = exec_ts - raw_ts if raw_ts else None

#         self._pending.append(
#             MasterEvent(
#                 event=event,
#                 method=method,
#                 symbol=symbol,
#                 side=side,
#                 partially=partially,
#                 payload=payload,
#                 sig_type=sig_type,
#                 ts=exec_ts,
#             )
#         )
