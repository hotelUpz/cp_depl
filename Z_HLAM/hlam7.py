# from __future__ import annotations

# import asyncio
# import time
# from dataclasses import dataclass, field
# from typing import Dict, Tuple, Optional, Literal, Any, List, Callable

# from MASTER.signal_cache import SignalCache, SignalEvent
# from pos.pos_vars_setup import PosVarSetup
# from c_utils import Utils
# from a_config import OPEN_TTL
# from b_context import MainContext
# from c_log import ErrorHandler


# # =====================================================================
# # HL PROTOCOL
# # =====================================================================

# HL_EVENT = Literal[
#     "buy",
#     "sell",
#     "canceled",
#     "filled",   # ← НОВОЕ
# ]


# METHOD = Literal["market", "limit", "trigger"]


# @dataclass
# class MasterEvent:
#     event: HL_EVENT
#     method: METHOD
#     symbol: str
#     side: str                  # LONG / SHORT
#     partially: bool
#     payload: Dict[str, Any]
#     ts: float = field(default_factory=time.time)


# # =====================================================================
# # MASTER PAYLOAD v3.4
# # =====================================================================

# class MasterPayload:
#     """
#     MASTERPAYLOAD v3.4 — MXC-correct HL aggregator.

#     ПРИНЦИПЫ:
#         • qty ТОЛЬКО из position snapshot
#         • order = намерение
#         • limit/trigger копируются как limit/trigger
#         • filled — служебный (НЕ copy)
#         • маркет-логика не тронута
#     """

#     def __init__(self, cache: SignalCache, mc: MainContext, logger: ErrorHandler, stop_flag: Callable):
#         self.cache = cache
#         self.mc = mc
#         self.log = logger
#         self.stop_flag = stop_flag

#         self._pos_vars_root = None
#         self._pending: List[MasterEvent] = []
#         self._stop = False

#         self._pos_state: Dict[Tuple[str, str], Dict[str, Any]] = {}
#         self._missing_spec_printed = set()
#         self.out_queue = asyncio.Queue()

#     # ==========================================================
#     def stop(self):
#         self._stop = True

#     # ==========================================================
#     async def run(self):
#         print("✔ MasterPayload v3.4 READY")

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
#         return self._pos_vars_root[symbol][side]

#     # ==========================================================
#     def _fix_price(self, raw: dict):
#         for k in (
#             "avgPrice", "price",
#             "holdAvgPrice", "openAvgPrice",
#             "newOpenAvgPrice", "closeAvgPrice",
#             "newCloseAvgPrice", "dealAvgPrice",
#         ):
#             if raw.get(k):
#                 return raw[k]
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
#     async def _route(self, ev: SignalEvent):
#         et = ev.event_type
#         symbol, side = ev.symbol, ev.side
#         if not side:
#             return

#         pv = self._ensure_pos_vars(symbol, side)

#         # ---------- ORDER INTENT ----------
#         if et in ("open_market", "open_limit", "trigger_order"):
#             pv["pending_open"] = True
#             pv["pending_method"] = (
#                 "market" if "market" in et else
#                 "limit" if "limit" in et else
#                 "trigger"
#             )
#             pv["pending_price"] = self._fix_price(ev.raw)
#             pv["pending_order_id"] = ev.raw.get("orderId")
#             pv["last_order_ts"] = ev.ts
#             return

#         # ---------- POSITION SNAPSHOT ----------
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

#         qty_prev = pv.get("qty", 0.0)
#         qty_cur = Utils.safe_float(raw.get("holdVol"), 0.0)

#         if qty_prev == qty_cur:
#             return

#         price = Utils.to_human_digit(self._fix_price(raw))

#         # ================= BUY =================
#         if qty_cur > qty_prev:
#             partially = qty_prev > 0
#             method = pv.get("pending_method", "market")

#             # ---- FILLED (служебный) ----
#             if pv.get("pending_open") and method != "market":
#                 await self._emit(
#                     event="filled",
#                     method=method,
#                     symbol=symbol,
#                     side=side,
#                     partially=False,
#                     payload={
#                         "order_id": pv.get("pending_order_id"),
#                         "qty": qty_cur - qty_prev,
#                         "price": price,
#                     },
#                     ev_raw=ev,
#                 )

#             pv["qty"] = qty_cur
#             pv["in_position"] = True

#             # ---- BUY (copy) ----
#             await self._emit(
#                 event="buy",
#                 method=method,
#                 symbol=symbol,
#                 side=side,
#                 partially=partially,
#                 payload={
#                     "qty_delta": qty_cur - qty_prev,
#                     "qty_before": qty_prev,
#                     "qty_after": qty_cur,
#                     "price": price,
#                 },
#                 ev_raw=ev,
#             )

#             # ---- CLEAR PENDING ----
#             pv.pop("pending_open", None)
#             pv.pop("pending_method", None)
#             pv.pop("pending_price", None)
#             pv.pop("pending_order_id", None)

#         # ================= SELL =================
#         elif qty_cur < qty_prev:
#             pv["qty"] = qty_cur
#             pv["in_position"] = qty_cur > 0

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
#                 ev_raw=ev,
#             )

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
#                 ts=exec_ts,
#             )
#         )


# from __future__ import annotations

# import asyncio
# import time
# from dataclasses import dataclass, field
# from typing import Dict, Tuple, Optional, Literal, Any, List, Callable

# from MASTER.signal_cache import SignalCache, SignalEvent
# from pos.pos_vars_setup import PosVarSetup
# from c_utils import Utils
# from a_config import OPEN_TTL
# from b_context import MainContext
# from c_log import ErrorHandler


# # =====================================================================
# # HL PROTOCOL
# # =====================================================================

# HL_EVENT = Literal[
#     "buy",
#     "sell",
#     "canceled",
#     "filled",
# ]


# METHOD = Literal["market", "limit", "tp", "sl"]

# # Единый протокол вариаций. Прямая и ясная как двери:

# """
# HL_EVENT  :  METHOD  :  sig_type
# buy -- market (тут тоже айдишники никто не отменял) -- copy
# sell -- market (тут тоже айдишники никто не отменял) -- copy

# buy -- limit (тут тоже айдишники никто не отменял) -- copy
# sell -- limit (тут тоже айдишники никто не отменял) -- copy

# canceled -- limit -- (будет айдишник) -- copy

# filled -- limit -- (будет айдишник) -- log

# sell (всегда для риск ордеров) -- tp (тут тоже айдишники никто не отменял) -- copy
# sell (всегда для риск ордеров) -- sl (тут тоже айдишники никто не отменял) -- copy

# canceled (всегда для риск ордеров) -- tp (тут тоже айдишники никто не отменял) -- copy  -- все кристально ясно
# canceled (всегда для риск ордеров) -- sl (тут тоже айдишники никто не отменял) -- copy  -- все кристально ясно

# filled (всегда для риск ордеров) -- tp (тут тоже айдишники никто не отменял) -- log  -- все кристально ясно. понятно и козе (и даже козлу)
# filled (всегда для риск ордеров) -- sl (тут тоже айдишники никто не отменял) -- log  -- все кристально ясно. понятно и ослу (и даже носорогу)

# """

# # а пока что мы тут: и нужно сделать хирургический рефакторинг, добавить обработку всех инвариаций, без слома того как ныне работает
# # парс маркет ордеров и лимитных ордеров. имею в виду качество, не имена


# @dataclass
# class MasterEvent:
#     event: HL_EVENT
#     method: METHOD
#     symbol: str
#     side: str                         # LONG / SHORT
#     partially: bool
#     payload: Dict[str, Any]
#     sig_type: Literal["copy", "log"]  # copy -- копируем как сигнал, log -- чисто логируем.
#     # (Добавил только что. Можно дать более удачные имена)
#     ts: float = field(default_factory=time.time)


# # =====================================================================
# # MASTER PAYLOAD v3.4
# # =====================================================================

# class MasterPayload:
#     """
#     MASTERPAYLOAD v3.4 — MXC-correct HL aggregator.

#     ПРИНЦИПЫ:
#         • qty ТОЛЬКО из position snapshot
#         • order = намерение
#         • limit/trigger копируются как limit/trigger
#         • filled — служебный (НЕ copy)
#         • маркет-логика не тронута
#     """

#     def __init__(self, cache: SignalCache, mc: MainContext, logger: ErrorHandler, stop_flag: Callable):
#         self.cache = cache
#         self.mc = mc
#         self.log = logger
#         self.stop_flag = stop_flag

#         self._pos_vars_root = None
#         self._pending: List[MasterEvent] = []
#         self._stop = False

#         self._pos_state: Dict[Tuple[str, str], Dict[str, Any]] = {}
#         self._missing_spec_printed = set()
#         self.out_queue = asyncio.Queue()
#         self._last_deal = {}   # (symbol, side) → {"price": float, "ts": int}

#     # ==========================================================
#     def stop(self):
#         self._stop = True

#     # ==========================================================
#     async def run(self):
#         print("✔ MasterPayload v3.4 READY")

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
#         return self._pos_vars_root[symbol][side]

#     # ==========================================================
#     def _fix_price(self, raw, symbol=None, side=None):
#         # raw prices
#         for k in ("dealAvgPrice", "avgPrice", "price", "openAvgPrice"):
#             if raw.get(k):
#                 return Utils.safe_float(raw[k])

#         # pending limit price
#         if symbol and side:
#             pv = self._ensure_pos_vars(symbol, side)
#             if pv.get("pending_price"):
#                 return pv["pending_price"]

#         # last deal
#         key = (symbol, side)
#         if key in self._last_deal:
#             return self._last_deal[key]["price"]

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
#     async def _route(self, ev: SignalEvent):
#         et = ev.event_type
#         symbol, side = ev.symbol, ev.side
#         if not side:
#             return

#         pv = self._ensure_pos_vars(symbol, side)

#         # ======================================================
#         # 0) ORDER CANCEL / INVALID (высший приоритет)
#         # ======================================================
#         if et in ("order_cancelled", "order_invalid"):
#             await self._emit(
#                 event="canceled",
#                 method=pv.get("pending_method", "limit"),
#                 symbol=symbol,
#                 side=side,
#                 partially=False,
#                 payload={
#                     "order_id": pv.get("pending_order_id"),
#                     "price": pv.get("pending_price"),
#                 },
#                 ev_raw=ev,
#             )

#             # сбрасываем pending
#             pv.pop("pending_open", None)
#             pv.pop("pending_method", None)
#             pv.pop("pending_price", None)
#             pv.pop("pending_order_id", None)
#             return

#         # ======================================================
#         # 1) LIMIT ORDER CREATED (Intent)
#         # ======================================================
#         if et == "open_limit":
#             pv["pending_open"] = True
#             pv["pending_method"] = "limit"
#             pv["pending_price"] = self._fix_price(ev.raw)
#             pv["pending_order_id"] = ev.raw.get("orderId")
#             pv["last_order_ts"] = ev.ts

#             await self._emit(
#                 event="buy",
#                 method="limit",
#                 symbol=symbol,
#                 side=side,
#                 partially=False,
#                 payload={
#                     "qty_delta": Utils.safe_float(ev.raw.get("vol", 0)),
#                     "price": Utils.safe_float(ev.raw.get("price", 0)),
#                     "order_id": ev.raw.get("orderId"),
#                 },
#                 ev_raw=ev,
#             )
#             # НЕ return! Даем DEAL и position_snapshot проходить далее.

#         # ======================================================
#         # 2) MARKET ORDER INTENT
#         # ======================================================
#         if et == "open_market":
#             pv["pending_open"] = True
#             pv["pending_method"] = "market"
#             pv["pending_price"] = self._fix_price(ev.raw)
#             pv["pending_order_id"] = ev.raw.get("orderId")
#             pv["last_order_ts"] = ev.ts
#             # тут не шлем HL — маркет BUY придёт через snapshot/deal
#             # return НЕ нужен

#         # ======================================================
#         # 3) TRIGGER ORDER INTENT
#         # ======================================================
#         if et == "trigger_order":
#             pv["pending_open"] = True
#             pv["pending_method"] = "trigger"
#             pv["pending_price"] = self._fix_price(ev.raw)
#             pv["pending_order_id"] = ev.raw.get("orderId")
#             pv["last_order_ts"] = ev.ts
#             # return не нужен

#         # ======================================================
#         # 4) DEAL (фиксация цены и возможное частичное исполнение)
#         # ======================================================
#         if et == "deal":
#             price = Utils.safe_float(ev.raw.get("price"))
#             if price:
#                 self._last_deal[(symbol, side)] = {
#                     "price": price,
#                     "ts": ev.ts,
#                 }
#             return

#         # ======================================================
#         # 5) POSITION SNAPSHOT (самый важный!)
#         # ======================================================
#         if et in ("position_opened", "position_closed"):
#             await self._on_position_snapshot(ev, pv)
#             return

#         # ======================================================
#         # 6) PLAN ORDERS (TP/SL)
#         # ======================================================
#         if et in ("plan_order", "plan_executed", "plan_cancelled"):
#             # Пока не участвуют в HL протоколе
#             return


#     # ==========================================================
#     async def _on_position_snapshot(self, ev: SignalEvent, pv: dict):
#         raw = ev.raw
#         symbol, side = ev.symbol, ev.side
#         key = (symbol, side)

#         if self._is_stale_snapshot(key, raw):
#             return

#         await asyncio.sleep(OPEN_TTL)

#         qty_prev = pv.get("qty", 0.0)
#         qty_cur = Utils.safe_float(raw.get("holdVol"), 0.0)

#         if qty_prev == qty_cur:
#             return

#         price = Utils.to_human_digit(
#             self._fix_price(raw, symbol, side)
#         )

#         # ================= BUY =================
#         if qty_cur > qty_prev:
#             partially = qty_prev > 0
#             method = pv.get("pending_method", "market")

#             # ---- FILLED (служебный) ----
#             if pv.get("pending_open") and method != "market":
#                 await self._emit(
#                     event="filled",
#                     method=method,
#                     symbol=symbol,
#                     side=side,
#                     partially=False,
#                     payload={
#                         "order_id": pv.get("pending_order_id"),
#                         "qty": qty_cur - qty_prev,
#                         "price": price,
#                     },
#                     ev_raw=ev,
#                 )

#             pv["qty"] = qty_cur
#             pv["in_position"] = True

#             # ---- BUY (copy) ----
#             await self._emit(
#                 event="buy",
#                 method=method,
#                 symbol=symbol,
#                 side=side,
#                 partially=partially,
#                 payload={
#                     "qty_delta": qty_cur - qty_prev,
#                     "qty_before": qty_prev,
#                     "qty_after": qty_cur,
#                     "price": price,
#                 },
#                 ev_raw=ev,
#             )

#             # ---- CLEAR PENDING ----
#             pv.pop("pending_open", None)
#             pv.pop("pending_method", None)
#             pv.pop("pending_price", None)
#             pv.pop("pending_order_id", None)

#         # ================= SELL =================
#         elif qty_cur < qty_prev:
#             pv["qty"] = qty_cur
#             pv["in_position"] = qty_cur > 0

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
#                 ev_raw=ev,
#             )

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
#                 ts=exec_ts,
#             )
#         )
