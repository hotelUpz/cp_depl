

# class SignalsHandler:
#     @staticmethod
#     async def _copy_open(mc_client: MexcClient, rt: Dict, event: SignalEvent, pos: Dict):
#         """
#         Мастер открыл позицию → делаем то же самое.
#         """

#         symbol = event.symbol
#         side = event.side
#         vol = event.vol
#         leverage = rt["leverage"] if "leverage" in rt else 10

#         # 1) Конвертация объёма мастера в контракты копии
#         contracts = vol
#         pos["contracts"] = contracts
#         pos["pending_open"] = True

#         # 2) MARKET / LIMIT
#         is_market = event.event_type == "open_market"

#         if is_market:
#             resp = await mc_client.make_order(
#                 symbol=symbol,
#                 contract=contracts,
#                 side="BUY",
#                 position_side=side,
#                 leverage=leverage,
#                 open_type=2,                # CROSS по умолчанию
#                 price=None,
#                 market_type="MARKET",
#                 debug=True
#             )
#         else:
#             resp = await mc_client.make_order(
#                 symbol=symbol,
#                 contract=contracts,
#                 side="BUY",
#                 position_side=side,
#                 leverage=leverage,
#                 open_type=2,
#                 price=event.price,
#                 market_type="LIMIT",
#                 debug=True
#             )

#         result = OrderValidator.validate_and_log(resp, "open")

#         if result["success"]:
#             pos["pending_open"] = False
#             pos["in_position"] = True
#             pos["entry_price"] = event.price
#             pos["order_id"] = [result["order_id"]]
#             print(f"OPEN OK → {symbol} {side}")
#         else:
#             print(f"OPEN FAIL → {symbol} {side}: {result['reason']}")

#     @staticmethod
#     async def _copy_close(mc_client: MexcClient, rt: Dict, event: SignalEvent, pos: Dict):
#         symbol = event.symbol
#         side = event.side
#         contracts = pos.get("contracts")
#         leverage = rt["leverage"]

#         if not contracts:
#             print(f"⚠ no contracts to close {symbol} {side}")
#             return

#         resp = await mc_client.make_order(
#             symbol=symbol,
#             contract=contracts,
#             side="SELL",
#             position_side=side,
#             leverage=leverage,
#             open_type=2,
#             price=None,
#             market_type="MARKET",
#             debug=True
#         )

#         result = OrderValidator.validate_and_log(resp, "close")

#         if result["success"]:
#             pos["in_position"] = False
#             pos["contracts"] = None
#             pos["entry_price"] = None
#             print(f"CLOSE OK → {symbol} {side}")
#         else:
#             print(f"CLOSE FAIL → {symbol} {side}: {result['reason']}")

#     @staticmethod
#     async def _copy_cancel(mc_client: MexcClient, rt: Dict, event: SignalEvent, pos: Dict):
#         symbol = event.symbol

#         oid = pos.get("order_id")
#         if not oid:
#             return

#         await mc_client.cancel_order(
#             order_id_list=oid,
#             symbol=symbol
#         )

#         pos["order_id"] = None
#         print(f"✔ CANCEL COPY LIMIT → {symbol}")

#     @staticmethod
#     async def _copy_tp_sl_create(mc_client: MexcClient, rt: Dict, event: SignalEvent, pos: Dict):
#         symbol = event.symbol
#         side = event.side
#         contracts = pos.get("contracts")
#         leverage = rt["leverage"]

#         if not contracts:
#             return

#         price = event.price
#         close_order_type = "tp" if event.raw.get("isTp") else "sl"

#         resp = await mc_client.create_stop_loss_take_profit(
#             symbol=symbol,
#             position_side=side,
#             contract=contracts,
#             price=price,
#             leverage=leverage,
#             open_type=2,
#             close_order_type=close_order_type,
#             order_type=1,         # MARKET ON TRIGGER
#         )

#         ok = OrderValidator.validate_and_log(resp, "tp/sl")

#         if ok["success"]:
#             key = "tp_id" if close_order_type == "tp" else "sl_id"
#             pos[key] = [ok["order_id"]]

#         print(f"TP/SL SET → {symbol} {side}")

#     @staticmethod
#     async def _copy_tp_sl_cancel(mc_client: MexcClient, rt: Dict, event: SignalEvent, pos: Dict):
#         symbol = event.symbol

#         await mc_client.cancel_order_template(
#             symbol=symbol,
#             pos_data=pos,
#             key_list=["tp", "sl"]
#         )

#         print(f"TP/SL CANCEL → {symbol}")

#     @staticmethod
#     async def _on_deal(rt: Dict, event: SignalEvent, pos: Dict):
#         if not pos.get("in_position"):
#             return

#         if event.deal_vol and event.price:
#             pos["entry_price"] = event.price

#     @staticmethod
#     async def _on_position_opened(rt: Dict, event: SignalEvent, pos: Dict):
#         pos["in_position"] = True
#         pos["pending_open"] = False
#         print(f"POS OPENED → {event.symbol} {event.side}")

#     @staticmethod
#     async def _on_position_closed(rt: Dict, event: SignalEvent, pos: Dict):
#         pos["in_position"] = False
#         pos["contracts"] = None
#         pos["entry_price"] = None
#         pos["tp_id"] = None
#         pos["sl_id"] = None
#         print(f"POS CLOSED → {event.symbol} {event.side}")





# class MasterPayload:
#     """
#     MASTERPAYLOAD v3.3 — MXC-safe HL aggregator.

#     ОСНОВНОЕ:
#         • qty меняется ТОЛЬКО по position snapshot
#         • deal / order — источники контекста, НЕ qty
#         • лимитки → pending_open
#         • никаких фантомных объёмов
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

#         # snapshot dedupe
#         self._pos_state: Dict[Tuple[str, str], Dict[str, Any]] = {}
#         self._missing_spec_printed = set()

#     # -----------------------------------------------------------------
#     def stop(self):
#         self._stop = True

#     # -----------------------------------------------------------------
#     async def run(self):
#         print("✔ MasterPayload v3.3 READY")

#         while not self._stop and not self.stop_flag():
#             await self.cache._event_notify.wait()
#             raw_events = await self.cache.pop_events()

#             for ev in raw_events:
#                 await self._route(ev)

#             out = self._pending[:]
#             self._pending.clear()

#             for e in out:
#                 yield e

#         print("🛑 MasterPayload STOPPED")

#     # -----------------------------------------------------------------
#     # POS VARS
#     # -----------------------------------------------------------------

#     def _ensure_pos_vars(self, symbol: str, side: str) -> dict:
#         if self._pos_vars_root is None:
#             root = self.mc.copy_configs.get(0, {}).get("runtime", {})
#             self.mc.copy_configs[0]["runtime"] = root
#             root.setdefault("position_vars", {})
#             self._pos_vars_root = root["position_vars"]

#         pv = self._pos_vars_root
#         PosVarSetup.set_pos_defaults(
#             position_vars=pv,
#             symbol=symbol,
#             pos_side=side,
#             instruments_data=self.mc.instruments_data,
#         )
#         return pv[symbol][side]

#     # -----------------------------------------------------------------
#     def _safe_spec(self, pv: dict, symbol: str, side: str) -> Optional[dict]:
#         spec = pv.get("spec")
#         if not spec:
#             key = (symbol, side)
#             if key not in self._missing_spec_printed:
#                 print(f"⚠️ SPEC missing for {symbol} {side}")
#                 self._missing_spec_printed.add(key)
#             return None
#         return spec

#     # -----------------------------------------------------------------
#     def _fix_price(self, raw: dict):
#         for k in (
#             "avgPrice", "price",
#             "holdAvgPrice", "openAvgPrice",
#             "newOpenAvgPrice", "closeAvgPrice",
#             "newCloseAvgPrice", "dealAvgPrice",
#         ):
#             v = raw.get(k)
#             if v:
#                 return v
#         return None

#     # -----------------------------------------------------------------
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

#     # -----------------------------------------------------------------
#     async def _route(self, ev: SignalEvent):
#         et = ev.event_type
#         symbol, side = ev.symbol, ev.side
#         if not side:
#             return

#         pv = self._ensure_pos_vars(symbol, side)

#         # ---------------- OPEN ORDERS ----------------
#         if et in ("open_market", "open_limit", "trigger_order"):
#             pv["pending_open"] = True
#             pv["pending_method"] = (
#                 "market" if "market" in et else
#                 "limit" if "limit" in et else
#                 "trigger"
#             )
#             pv["pending_price"] = self._fix_price(ev.raw)
#             pv["last_order_ts"] = ev.ts

#         # ---------------- POSITION SNAPSHOT ----------------
#         elif et in ("position_opened", "position_closed"):
#             await self._on_position_snapshot(ev, pv)

#         # deal / pending / plan — не трогаем qty

#     # -----------------------------------------------------------------
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

#             pv["qty"] = qty_cur
#             pv["in_position"] = True
#             pv["pending_open"] = False

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

#         # ================= SELL =================
#         elif qty_cur < qty_prev:
#             partially = qty_cur > 0

#             pv["qty"] = qty_cur
#             pv["in_position"] = qty_cur > 0

#             await self._emit(
#                 event="sell",
#                 method="market",
#                 symbol=symbol,
#                 side=side,
#                 partially=partially,
#                 payload={
#                     "qty_delta": qty_prev - qty_cur,
#                     "qty_before": qty_prev,
#                     "qty_after": qty_cur,
#                     "price": price,
#                 },
#                 ev_raw=ev,
#             )

#     # -----------------------------------------------------------------
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

#     # -----------------------------------------------------------------
#     async def on_raw(self, ev: SignalEvent):
#         pass



# # MASTER/signal_cache.py
# from __future__ import annotations
# import asyncio
# from dataclasses import dataclass, field
# from typing import Any, Dict, Deque, Tuple, Optional, Literal
# from collections import deque


# Side = Literal["LONG", "SHORT"]


# # -----------------------------
# # NORMALIZATION HELPERS
# # -----------------------------

# def normalize_symbol(raw_symbol: str, quote_asset: str = "USDT") -> str:
#     """BTCUSDT → BTC_USDT, btc-usdt → BTC_USDT"""
#     if not raw_symbol:
#         return ""
#     qa = quote_asset.upper()
#     s = raw_symbol.upper().replace("-", "").replace("_", "").replace(" ", "")
#     return s.replace(qa, f"_{qa}")


# def side_from_order_side(code: int) -> Optional[Side]:
#     """
#     MXC:
#         1=open long, 2=close short,
#         3=open short, 4=close long
#     """
#     return (
#         "LONG" if code in (1, 4)
#         else "SHORT" if code in (2, 3)
#         else None
#     )


# def side_from_position_type(code: int) -> Optional[Side]:
#     return (
#         "LONG" if code == 1
#         else "SHORT" if code == 2
#         else None
#     )


# # -----------------------------
# # RAW SIGNAL EVENT STRUCT
# # -----------------------------

# SignalEventType = Literal[
#     "open_market",
#     "open_limit",
#     "close_market",
#     "close_limit",
#     "open_pending",
#     "close_pending",
#     "plan_order",
#     "plan_executed",
#     "plan_cancelled",
#     "position_opened",
#     "position_closed",
#     "order_cancelled",
#     "order_invalid",
#     "deal",
#     "trigger_order",
#     "raw"
# ]


# @dataclass
# class SignalEvent:
#     symbol: str
#     side: Optional[Side]
#     event_type: SignalEventType
#     ts: int
#     raw: Dict[str, Any] = field(default_factory=dict)


# # -----------------------------
# # ULTRA FAST CACHE (NO LOGIC)
# # -----------------------------

# class SignalCache:
#     """
#     Простой быстрый кеш RAW событий.
#     Никакой логики супрессии / bucket / флагов.
#     """

#     def __init__(self):
#         self._events: Deque[SignalEvent] = deque()
#         self._last_raw: Dict[Tuple[str, Side], Dict[str, Any]] = {}

#         self._lock = asyncio.Lock()
#         self._event_notify = asyncio.Event()

#     # -----------------------------------------------------
#     async def push_event(self, ev: SignalEvent):
#         async with self._lock:
#             self._events.append(ev)
#             if ev.side:
#                 self._last_raw[(ev.symbol, ev.side)] = ev.raw
#             self._event_notify.set()

#     # -----------------------------------------------------
#     async def pop_events(self) -> list[SignalEvent]:
#         async with self._lock:
#             out = list(self._events)
#             self._events.clear()
#             self._event_notify.clear()
#             return out

#     # -----------------------------------------------------
#     def get_last_raw(self, symbol: str, side: Side) -> Optional[Dict[str, Any]]:
#         return self._last_raw.get((symbol, side))


# # MASTER/signal_stream.py
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
#     normalize_symbol, side_from_order_side, side_from_position_type
# )


# class MasterSignalStream:
#     """
#     ЧИСТЫЙ STREAM-LEVEL:
#         • ws-connect / reconnect
#         • подписка
#         • парсинг mx events
#         • нормализация orderType
#         • пуш в SignalCache → RAW ONLY

#     High-level logic (precision / smoothing / TTL / partial-close)
#     выполняет MasterPayload (компостер), НЕ здесь.
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
#         self._wake_event = asyncio.Event()

#         self._ping_task: Optional[asyncio.Task] = None

#         # временный хук вместо MasterPayload
#         self._raw_listener = self._print_stub

#     # ======================================================
#     # PUBLIC API
#     # ======================================================

#     def stop(self):
#         self._external_stop = True
#         self._wake_event.set()
#         self.ready = False
#         self.log.debug_info_notes("🛑 MasterSignalStream.stop()")

#     def attach_raw_listener(self, cb):
#         """Подцепляем MasterPayload."""
#         self._raw_listener = cb

#     async def _on_raw_event(self, ev: SignalEvent):
#         """hook → потом заменится на MasterPayload.run()"""
#         await self._raw_listener(ev)

#     async def _print_stub(self, ev: SignalEvent):
#         print(f"RAW[{ev.event_type}] {ev.symbol} {ev.side} → {ev.raw}")

#     # ======================================================
#     # INTERNALS — CONNECT / LOGIN
#     # ======================================================

#     def _signature(self, ts_ms: int) -> str:
#         return hmac.new(
#             self.api_secret.encode(),
#             f"{self.api_key}{ts_ms}".encode(),
#             hashlib.sha256,
#         ).hexdigest()

#     async def _connect(self) -> bool:
#         if self._external_stop:
#             return False

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
#         if self._external_stop:
#             return False

#         try:
#             ts = int(time.time() * 1000)
#             await self.websocket.send_json({
#                 "method": "login",
#                 "param": {
#                     "apiKey": self.api_key,
#                     "reqTime": ts,
#                     "signature": self._signature(ts)
#                 }
#             })

#             msg = await asyncio.wait_for(self.websocket.receive(), timeout=10)
#             data = json.loads(msg.data)

#             if data.get("channel") == "rs.login" and data.get("data") == "success":
#                 return True

#             self.log.debug_error_notes(f"WS login rejected: {data}")
#             return False

#         except Exception as e:
#             self.log.debug_error_notes(f"WS login exception: {e}")
#             return False

#     # ======================================================
#     # PING LOOP
#     # ======================================================

#     async def _ping_loop(self):
#         while not self._external_stop and self.is_connected and not self.stop_flag():
#             await asyncio.sleep(self.ping_interval)
#             try:
#                 await self.websocket.send_json({"method": "ping"})
#             except:
#                 return

#     # ======================================================
#     # DISCONNECT
#     # ======================================================

#     async def _disconnect(self):
#         self.is_connected = False
#         self.ready = False

#         if self._ping_task and not self._ping_task.done():
#             self._ping_task.cancel()

#         try:
#             if self.websocket:
#                 await self.websocket.close()
#         except:
#             pass

#         try:
#             if self.session:
#                 await self.session.close()
#         except:
#             pass

#         self.websocket = None
#         self.session = None

#     # ======================================================
#     # MESSAGE LOOP
#     # ======================================================

#     async def _handle_messages(self):
#         """Базовый консумер — парсит MX события → SignalCache"""
#         while not self._external_stop and not self.stop_flag():
#             try:
#                 msg = await asyncio.wait_for(self.websocket.receive(), timeout=1.0)
#             except asyncio.TimeoutError:
#                 continue
#             except:
#                 return

#             if msg.type != aiohttp.WSMsgType.TEXT:
#                 continue

#             try:
#                 data = json.loads(msg.data)
#             except:
#                 continue

#             if data.get("method") == "ping":
#                 await self.websocket.send_json({"method": "pong"})
#                 continue

#             channel = data.get("channel")
#             payload = data.get("data", {})

#             # ROUTER TO HANDLERS
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

#     # ======================================================
#     # EVENT PROCESSORS — RAW NORMALIZED SIGNALS
#     # ======================================================

#     async def _emit(self, symbol, side, etype, raw):
#         ev = SignalEvent(
#             symbol=symbol,
#             side=side,
#             event_type=etype,
#             ts=now(),
#             raw=raw
#         )
#         await self.cache.push_event(ev)
#         await self._on_raw_event(ev)

#     # ------------------------------------------------------

#     async def _handle_order(self, data):
#         symbol = normalize_symbol(data.get("symbol"), self.quote_asset)
#         if not symbol:
#             return

#         side_code = int(data.get("side", 0))
#         side = side_from_order_side(side_code)

#         state = int(data.get("state", 0))
#         order_type = int(data.get("orderType", 0))

#         # MXC orderType normalization
#         if order_type == 5:
#             etype = "open_market" if side_code in (1, 3) else "close_market"
#         elif order_type == 1:
#             etype = "open_limit" if side_code in (1, 3) else "close_limit"
#         else:
#             etype = "trigger_order"

#         await self._emit(symbol, side, etype, data)

#         if state in (1, 2):
#             pending = "open_pending" if side_code in (1, 3) else "close_pending"
#             await self._emit(symbol, side, pending, data)

#         if state == 4:
#             await self._emit(symbol, side, "order_cancelled", data)
#         elif state == 5:
#             await self._emit(symbol, side, "order_invalid", data)

#     # ------------------------------------------------------

#     async def _handle_order_deal(self, data):
#         symbol = normalize_symbol(data.get("symbol"), self.quote_asset)
#         side = side_from_order_side(int(data.get("side", 0)))
#         await self._emit(symbol, side, "deal", data)

#     # ------------------------------------------------------

#     async def _handle_position(self, data):
#         symbol = normalize_symbol(data.get("symbol"), self.quote_asset)
#         side = side_from_position_type(int(data.get("positionType", 0)))

#         hold_vol = float(data.get("holdVol", 0))
#         state = int(data.get("state", 0))

#         etype = "position_opened" if (state in (1, 2) and hold_vol > 0) else "position_closed"
#         await self._emit(symbol, side, etype, data)

#     # ------------------------------------------------------

#     async def _handle_plan_order(self, data):
#         symbol = normalize_symbol(data.get("symbol"), self.quote_asset)
#         side = side_from_order_side(int(data.get("side", 0)))
#         state = int(data.get("state", 0))

#         if state == 1:
#             etype = "plan_order"
#         elif state == 3:
#             etype = "plan_executed"
#         else:
#             etype = "plan_cancelled"

#         await self._emit(symbol, side, etype, data)

#     # ------------------------------------------------------

#     async def _handle_stop_order(self, data):
#         symbol = normalize_symbol(data.get("symbol"), self.quote_asset)
#         await self._emit(symbol, None, "raw", data)

#     # ======================================================
#     # PUBLIC START LOOP
#     # ======================================================

#     async def start(self):
#         self._external_stop = False
#         self._wake_event.clear()

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

#         await self._disconnect()


