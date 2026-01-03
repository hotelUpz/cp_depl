# MASTER/signal_stream.py
# from __future__ import annotations

# import asyncio
# import json
# import time
# import hmac
# import hashlib
# import random
# from typing import *

# import aiohttp

# from c_log import ErrorHandler
# from c_utils import now
# from .signal_cache import (
#     SignalCache, SignalEvent,
#     normalize_symbol,
#     side_from_order_side,
#     side_from_position_type,
# )


# class MasterSignalStream:
#     """
#     STREAM LEVEL ONLY.
#     НИКАКОЙ high-level логики.
#     """

#     def __init__(
#         self,
#         api_key: str,
#         api_secret: str,
#         signal_cache: SignalCache,
#         *,
#         logger: ErrorHandler,
#         stop_flag: Callable,
#         proxy_url: Optional[str] = None,
#         ws_url: str = "wss://contract.mexc.com/edge",
#         quote_asset: str = "USDT",
#     ):
#         self.api_key = api_key
#         self.api_secret = api_secret

#         self.cache = signal_cache
#         self.log = logger

#         self.proxy_url = None if not proxy_url or proxy_url == "0" else proxy_url
#         self.ws_url = ws_url
#         self.quote_asset = quote_asset.upper()

#         self.session: Optional[aiohttp.ClientSession] = None
#         self.websocket: Optional[aiohttp.ClientWebSocketResponse] = None

#         self.ready = False
#         self.is_connected = False
#         self.ping_interval = 12
#         self.stop_flag = stop_flag

#         self._external_stop = False
#         self._ping_task: Optional[asyncio.Task] = None

#     # --------------------------------------------------

#     def stop(self):
#         self._external_stop = True
#         self.ready = False
#         self.log.debug_info_notes("🛑 MasterSignalStream.stop()")

#     # --------------------------------------------------

#     def _signature(self, ts_ms: int) -> str:
#         return hmac.new(
#             self.api_secret.encode(),
#             f"{self.api_key}{ts_ms}".encode(),
#             hashlib.sha256,
#         ).hexdigest()

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
#             return True
#         except Exception as e:
#             self.log.debug_error_notes(f"WS connect failed: {e}")
#             return False

#     async def _login(self) -> bool:
#         try:
#             ts = int(time.time() * 1000)
#             await self.websocket.send_json({
#                 "method": "login",
#                 "param": {
#                     "apiKey": self.api_key,
#                     "reqTime": ts,
#                     "signature": self._signature(ts),
#                 }
#             })

#             msg = await asyncio.wait_for(self.websocket.receive(), timeout=10)
#             data = json.loads(msg.data)

#             return data.get("channel") == "rs.login" and data.get("data") == "success"
#         except Exception as e:
#             self.log.debug_error_notes(f"WS login exception: {e}")
#             return False

#     async def _ping_loop(self):
#         while not self._external_stop and self.is_connected and not self.stop_flag():
#             await asyncio.sleep(self.ping_interval)
#             try:
#                 await self.websocket.send_json({"method": "ping"})
#             except:
#                 return

#     async def _disconnect(self):
#         self.is_connected = False
#         self.ready = False

#         if self._ping_task and not self._ping_task.done():
#             self._ping_task.cancel()

#         if self.websocket:
#             await self.websocket.close()
#         if self.session:
#             await self.session.close()

#         self.websocket = None
#         self.session = None

#     # --------------------------------------------------
#     # RAW EVENT EMIT
#     # --------------------------------------------------

#     async def _emit(self, symbol, side, etype, raw):
#         ev = SignalEvent(
#             symbol=symbol,
#             side=side,
#             event_type=etype,
#             ts=now(),
#             raw=raw,
#         )
#         print(ev)
#         await self.cache.push_event(ev)   # ← ЕДИНСТВЕННЫЙ ВЫХОД

#     # --------------------------------------------------
#     # HANDLERS
#     # --------------------------------------------------

#     async def _handle_order(self, data):
#         symbol = normalize_symbol(data.get("symbol"), self.quote_asset)
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
#         symbol = normalize_symbol(data.get("symbol"), self.quote_asset)
#         side = side_from_order_side(int(data.get("side", 0)))
#         await self._emit(symbol, side, "deal", data)

#     async def _handle_position(self, data):
#         symbol = normalize_symbol(data.get("symbol"), self.quote_asset)
#         side = side_from_position_type(int(data.get("positionType", 0)))

#         hold_vol = float(data.get("holdVol", 0))
#         state = int(data.get("state", 0))

#         etype = "position_opened" if (state in (1, 2) and hold_vol > 0) else "position_closed"
#         await self._emit(symbol, side, etype, data)

#     async def _handle_plan_order(self, data):
#         symbol = normalize_symbol(data.get("symbol"), self.quote_asset)
#         side = side_from_order_side(int(data.get("side", 0)))
#         state = int(data.get("state", 0))

#         etype = "plan_order" if state == 1 else "plan_executed" if state == 3 else "plan_cancelled"
#         await self._emit(symbol, side, etype, data)

#     async def _handle_stop_order(self, data):
#         symbol = normalize_symbol(data.get("symbol"), self.quote_asset)
#         await self._emit(symbol, None, "raw", data)

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

# MASTER.master_payload.py

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

# # # меняем на:

# # HL_EVENT = Literal["buy", "sell", "canceled", "filled"]
# # METHOD = Literal["market", "limit", "trigger", "oco"]

# # =====================================================================
# # MASTER EVENT
# # =====================================================================

# @dataclass
# class MasterEvent:
#     """
#     Универсальное HL-событие.

#     payload может содержать:
#         • qty_delta / qty_before / qty_after
#         • price
#         • order_id
#         • tp_price / sl_price        ← attached OCO (одним ордером)
#         • exec_ts / latency_ms
#     """
#     event: HL_EVENT
#     method: METHOD
#     symbol: str
#     side: str
#     partially: bool
#     payload: Dict[str, Any]
#     sig_type: Literal["copy", "log"]
#     ts: float = field(default_factory=time.time)

# """
# Протокол вариаций:

# HL_EVENT  :  METHOD  :  sig_type
# buy | sell -- market -- copy. если идет вместе с осо (со стопом-тейком) то в payload заполненные поля tp_price, sl_price

# buy | sell -- limit | trigger | oco (если удастся отследить, если нет то нет) -- copy.
# Для limit | trigger в payload должно быть поле price (target_price) (чи как там оно сейчас -- можно переименовать).
# Для осо в payload должно быть поля tp_price, sl_price (чи как там оно сейчас). -- если удастя отследить его как отдельный ордер после существования основной позиции.


# canceled -- limit | trigger | oco (если удастся отследить, если нет то нет) -- copy
# filled -- limit | trigger | oco (если удастся отследить, если нет то нет)-- log

# на каждую сущность всегда и везде -- соответсвующий айдишник
# """

# class MasterPayload:
#     """
#     High-level агрегатор сигналов мастера.

#     Ключевые принципы:
#         • qty — ТОЛЬКО из snapshot
#         • intent не моделируем
#         • причина изменения qty — ТОЛЬКО исполнение
#         • attached TP/SL — атрибут BUY, не отдельный HL
#         • plan TP/SL — отдельные сущности
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
#         self._last_deal: Dict[Tuple[str, str], Dict[str, Any]] = {}

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

#         pv.setdefault("_last_exec_source", None)     # limit / tp / sl / None
#         pv.setdefault("attached_tp", None)           # биржевой OCO
#         pv.setdefault("attached_sl", None)

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

#         # ------------------------------------------------------
#         # ATTACHED TP/SL (OCO)
#         # ------------------------------------------------------
#         if et == "stop_attached":
#             pv["attached_tp"] = Utils.safe_float(ev.raw.get("takeProfitPrice"))
#             pv["attached_sl"] = Utils.safe_float(ev.raw.get("stopLossPrice"))
#             return

#         # ------------------------------------------------------
#         # LIMIT OPEN
#         # ------------------------------------------------------
#         if et == "open_limit":
#             if ev.raw.get("state") == 4:
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

#         # ------------------------------------------------------
#         # LIMIT CLOSE
#         # ------------------------------------------------------
#         if et == "close_limit":
#             if ev.raw.get("state") == 4:
#                 return

#             pv["_last_exec_source"] = "limit"

#             await self._emit(
#                 event="sell",
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

#         # ------------------------------------------------------
#         # LIMIT CANCEL / INVALID
#         # ------------------------------------------------------
#         if et in ("order_cancelled", "order_invalid"):
#             pv["_last_exec_source"] = None

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

#         # ------------------------------------------------------
#         # DEAL (price only)
#         # ------------------------------------------------------
#         if et == "deal":
#             price = Utils.safe_float(ev.raw.get("price"))
#             if price:
#                 self._last_deal[(symbol, side)] = {"price": price, "ts": ev.ts}
#             return

#         # ------------------------------------------------------
#         # PLAN TP / SL
#         # ------------------------------------------------------
#         if et in ("plan_order", "plan_executed", "plan_cancelled"):
#             await self._handle_plan(ev, pv)
#             return

#         # ------------------------------------------------------
#         # POSITION SNAPSHOT
#         # ------------------------------------------------------
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

#             payload = {
#                 "qty_delta": qty_cur - qty_prev,
#                 "qty_before": qty_prev,
#                 "qty_after": qty_cur,
#                 "price": price,
#             }

#             # attached OCO
#             if pv.get("attached_tp"):
#                 payload["tp_price"] = pv["attached_tp"]
#             if pv.get("attached_sl"):
#                 payload["sl_price"] = pv["attached_sl"]

#             sig_type = "log" if last_src in ("tp", "sl", "limit") else "copy"

#             await self._emit(
#                 event="buy",
#                 method="market",
#                 symbol=symbol,
#                 side=side,
#                 partially=qty_prev > 0,
#                 payload=payload,
#                 sig_type=sig_type,
#                 ev_raw=ev,
#             )

#             pv["attached_tp"] = None
#             pv["attached_sl"] = None

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
