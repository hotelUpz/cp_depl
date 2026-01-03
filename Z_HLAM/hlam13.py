# # MASTER/master_payload.py
# from __future__ import annotations

# import asyncio
# import time
# from dataclasses import dataclass, field
# from typing import Dict, Tuple, Optional, Literal, Any, List, Callable

# from MASTER.signal_cache import SignalCache, SignalEvent, PosVarSetup
# from c_utils import Utils, now
# from b_context import MainContext
# from c_log import ErrorHandler


# # =====================================================================
# # HL PROTOCOL
# # =====================================================================

# HL_EVENT = Literal["buy", "sell", "canceled", "filled"]
# METHOD = Literal["market", "limit", "trigger", "oco"]


# # =====================================================================
# # MASTER EVENT
# # =====================================================================

# @dataclass
# class MasterEvent:
#     event: HL_EVENT
#     method: METHOD
#     symbol: str
#     side: str
#     partially: bool
#     closed: bool
#     payload: Dict[str, Any]
#     sig_type: Literal["copy", "log"]

#     # NEW
#     pos_progress: Dict[str, Any]

#     ts: float = field(default_factory=time.time)

# # =====================================================================
# # MASTER PAYLOAD
# # =====================================================================

# class MasterPayload:
#     """
#     High-level агрегатор сигналов мастера.

#     ОСНОВНЫЕ ПРИНЦИПЫ:
#         • qty — ТОЛЬКО из position snapshot
#         • intent не моделируем
#         • trigger == limit по смыслу, но с trigger_price
#         • tp/sl — ТОЛЬКО attached OCO
#         • никаких эвристик и угадываний
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
#         self._last_deal: Dict[Tuple[str, str], Dict[str, Any]] = {}

#         self.out_queue = asyncio.Queue()

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

#         pv.setdefault("_last_exec_source", None)   # market | limit | trigger | None
#         pv.setdefault("attached_tp", None)
#         pv.setdefault("attached_sl", None)

#         return pv

#     # ==========================================================
#     def _fix_price(self, raw, symbol=None, side=None):
#         for k in ("dealAvgPrice", "avgPrice", "price", "openAvgPrice"):
#             if raw.get(k):
#                 return Utils.safe_float(raw[k])

#         return self._last_deal.get((symbol, side), {}).get("price")

#     # ==========================================================
#     def _is_stale_snapshot(self, key, raw) -> bool:
#         upd = raw.get("updateTime") or raw.get("timestamp") or 0
#         hold = raw.get("holdVol")

#         st = self._pos_state.get(key)
#         if not st:
#             self._pos_state[key] = {"upd": upd, "hold": hold}
#             return False

#         # закрытие позиции ВСЕГДА пропускаем
#         if hold == 0:
#             self._pos_state[key] = {"upd": upd, "hold": hold}
#             return False

#         if upd < st["upd"]:
#             return True
#         if upd == st["upd"] and hold == st["hold"]:
#             return True

#         self._pos_state[key] = {"upd": upd, "hold": hold}
#         return False

#     # ==========================================================
        
#     # ==========================================================
#     async def _route(self, ev: SignalEvent):
#         et = ev.event_type
#         symbol, side = ev.symbol, ev.side

#         # ------------------------------------------------------
#         # ATTACHED OCO — БЕЗ side
#         # ------------------------------------------------------
#         if et == "stop_attached":
#             root = self.mc.copy_configs.setdefault(0, {}).setdefault("runtime", {})
#             oco_buf = root.setdefault("_attached_oco", {})

#             oco_buf[symbol] = {
#                 "tp": Utils.safe_float(ev.raw.get("takeProfitPrice")),
#                 "sl": Utils.safe_float(ev.raw.get("stopLossPrice")),
#             }
#             return

#         if not side:
#             return

#         pv = self._ensure_pos_vars(symbol, side)

#         # ------------------------------------------------------
#         # LIMIT OPEN / CLOSE
#         # ------------------------------------------------------
#         if et in ("open_limit", "close_limit") and ev.raw.get("state") != 4:
#             pv["_last_exec_source"] = "limit"

#             await self._emit(
#                 event="buy" if et == "open_limit" else "sell",
#                 method="limit",
#                 symbol=symbol,
#                 side=side,
#                 partially=False,
#                 payload={
#                     "order_id": ev.raw.get("orderId"),
#                     "qty": Utils.safe_float(ev.raw.get("vol")),
#                     "price": Utils.safe_float(ev.raw.get("price")),

#                     "leverage": ev.raw.get("leverage"),
#                     "open_type": ev.raw.get("openType"),
#                     "reduce_only": bool(ev.raw.get("reduceOnly")),

#                     "used_margin": Utils.safe_float(ev.raw.get("usedMargin")),
#                 },
#                 sig_type="copy",
#                 ev_raw=ev,
#             )
#             return

#         # ------------------------------------------------------
#         # LIMIT CANCEL
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
#                 },
#                 sig_type="copy",
#                 ev_raw=ev,
#             )
#             return

#         # ------------------------------------------------------
#         # DEAL (price cache)
#         # ------------------------------------------------------
#         if et == "deal":
#             price = Utils.safe_float(ev.raw.get("price"))
#             if price:
#                 self._last_deal[(symbol, side)] = {"price": price, "ts": ev.ts}
#             return

#         # ------------------------------------------------------
#         # TRIGGER ORDERS (plan)
#         # ------------------------------------------------------
#         if et in ("plan_order", "plan_executed", "plan_cancelled"):
#             trigger_price = Utils.safe_float(
#                 ev.raw.get("triggerPrice") or ev.raw.get("price")
#             )
#             if not trigger_price:
#                 return

#             pv["_last_exec_source"] = "trigger"

#             if et == "plan_executed":
#                 event, sig = "filled", "log"
#             elif et == "plan_order":
#                 event, sig = "buy" if ev.raw.get("side") in (1, 3) else "sell", "copy"
#             else:
#                 event, sig = "canceled", "copy"

#             await self._emit(
#                 event=event,
#                 method="trigger",
#                 symbol=symbol,
#                 side=side,
#                 partially=False,
#                 payload={
#                     "order_id": ev.raw.get("orderId"),
#                     "qty": Utils.safe_float(ev.raw.get("vol")),
#                     "trigger_price": trigger_price,

#                     "leverage": ev.raw.get("leverage"),
#                     "open_type": ev.raw.get("openType"),
#                     "reduce_only": bool(ev.raw.get("reduceOnly")),

#                     "trigger_exec": (
#                         "market" if ev.raw.get("triggerType") == 2 else "limit"
#                     ),
#                 },
#                 sig_type=sig,
#                 ev_raw=ev,
#             )
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

#         qty_prev = pv["qty"]
#         qty_cur = Utils.safe_float(raw.get("holdVol"), 0.0)

#         if qty_prev == qty_cur:
#             return

#         price = Utils.to_human_digit(self._fix_price(raw, symbol, side))
#         last_src = pv["_last_exec_source"]

#         # --------------------------------------------------
#         # подтягиваем attached OCO
#         # --------------------------------------------------
#         root = self.mc.copy_configs.setdefault(0, {}).setdefault("runtime", {})
#         oco_buf = root.get("_attached_oco", {})

#         oco = oco_buf.pop(symbol, None)
#         if oco:
#             pv["attached_tp"] = oco.get("tp")
#             pv["attached_sl"] = oco.get("sl")

#         delta = abs(qty_cur - qty_prev)

#         # ================= BUY =================
#         if qty_cur > qty_prev:
#             pv["qty"] = qty_cur
#             pv["in_position"] = True

#             payload = {
#                 "qty": delta,
#                 "price": price,

#                 "leverage": raw.get("leverage"),
#                 "open_type": raw.get("openType"),
#                 "reduce_only": False,

#                 "qty_delta": delta,
#                 "qty_before": qty_prev,
#                 "qty_after": qty_cur,
#             }

#             if pv["attached_tp"]:
#                 payload["tp_price"] = pv["attached_tp"]
#             if pv["attached_sl"]:
#                 payload["sl_price"] = pv["attached_sl"]

#             sig_type = (
#                 "log"
#                 if last_src in ("limit", "trigger") and qty_prev == 0
#                 else "copy"
#             )

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
#             sig_type = (
#                 "log"
#                 if last_src in ("limit", "trigger") and is_full_close
#                 else "copy"
#             )

#             payload = {
#                 "qty": delta,
#                 "price": price,

#                 "leverage": raw.get("leverage"),
#                 "open_type": raw.get("openType"),
#                 "reduce_only": True,

#                 "qty_delta": delta,
#                 "qty_before": qty_prev,
#                 "qty_after": qty_cur,
#             }

#             await self._emit(
#                 event="sell",
#                 method="market",
#                 symbol=symbol,
#                 side=side,
#                 partially=qty_cur > 0,                
#                 payload=payload,
#                 sig_type=sig_type,
#                 ev_raw=ev,
#                 closed=is_full_close,
#             )

#             if qty_cur is not None and qty_cur == 0:
#                 try:
#                     self._pos_state.pop(key, None)
#                     self._last_deal.pop(key, None)
#                 except:
#                     pass

#         if qty_prev == 0 and qty_cur > 0:
#             pv["entry_price"] = price

#         pv["last_price"] = price
#         pv["qty_prev"] = qty_cur
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
#         closed: bool = False
#     ):
#         exec_ts = now()
#         raw_ts = ev_raw.ts if ev_raw else None

#         payload = dict(payload)
#         payload["exec_ts"] = exec_ts
#         payload["latency_ms"] = exec_ts - raw_ts if raw_ts else None

#         # --------------------------------------------------
#         # SNAPSHOT POS STATE
#         # --------------------------------------------------
#         pv = self._ensure_pos_vars(symbol, side)
#         pos_progress = {k: pv.get(k) for k in PosVarSetup.PUBLIC_PV_KEYS}

#         self._pending.append(
#             MasterEvent(
#                 event=event,
#                 method=method,
#                 symbol=symbol,
#                 side=side,
#                 partially=partially,
#                 closed=closed,
#                 payload=payload,
#                 sig_type=sig_type,
#                 pos_progress=pos_progress,
#                 ts=exec_ts,
#             )
#         )


# # MASTER/signal_fsm.py

# from __future__ import annotations
# import asyncio
# import hashlib
# import time
# from typing import *

# from b_context import MainContext
# from c_log import ErrorHandler

# from DESTRIBUTOR.copy_ import CopyDestrib

# from .signal_stream import MasterSignalStream
# from .master_payload import MasterPayload     # ← FIX
# from .signal_cache import SignalCache

# if TYPE_CHECKING:
#     from DESTRIBUTOR.helpers import Runtime


# def creds_hash(cfg: dict) -> str:
#     ex = cfg.get("exchange", {})
#     key = ex.get("api_key") or ""
#     sec = ex.get("api_secret") or ""
#     proxy = ex.get("proxy") or ""
#     return hashlib.md5(f"{key}:{sec}:{proxy}".encode()).hexdigest()


# class FSMLogger:
#     def __init__(self, prefix: str = "FSM"):
#         self.prefix = prefix

#     def enter(self, state: str):
#         ts = time.strftime("%H:%M:%S")
#         print(f"[{self.prefix}] {ts} → ENTER {state}")

#     def exit(self, state: str):
#         ts = time.strftime("%H:%M:%S")
#         print(f"[{self.prefix}] {ts} → EXIT {state}")


# class SignalFSM:
#     def __init__(
#         self,
#         mc: MainContext,
#         logger: ErrorHandler,
#         runtime: Runtime,
#         stop_flag: Callable,
#     ):
#         self.mc = mc
#         self.logger = logger        
#         self.runtime = runtime
#         self.stop_flag = stop_flag

#         # SIGNAL INFRA
#         self.signal_cache: SignalCache | None = None
#         self.signal_stream: MasterSignalStream | None = None
#         self.payload: MasterPayload | None = None      # ← FIX

#         # COPY LAYER
#         self.copy = CopyDestrib(
#             mc=self.mc,
#             logger=self.logger,
#             runtime=self.runtime,
#             stop_flag=self.stop_flag,
#         )

#         self.logfsm = FSMLogger(prefix="MASTER_FSM")
#         self.payload_task: asyncio.Task | None = None

#     def _reset_master_runtime(self):
#         rt = self.mc.copy_configs.setdefault(0, {}).setdefault("runtime", {})
#         try:
#             rt.pop("position_vars", None)
#             rt.pop("_attached_oco", None)
#         except:
#             pass

#     # =====================================================================
#     # MASTER SUPERVISOR
#     # =====================================================================
#     async def master_supervisor(self):
#         print("🚀 Master supervisor started")

#         last_hash = None
#         stream_task = None
#         copy_loop_task = None
#         self.logfsm.enter("DISABLED")

#         while not self.stop_flag():
#             await asyncio.sleep(0.05)

#             master_cfg = self.mc.copy_configs.get(0, {})
#             ex = master_cfg.get("exchange", {})
#             rt = master_cfg.get("runtime", {})

#             api_key = ex.get("api_key")
#             api_secret = ex.get("api_secret")
#             proxy = ex.get("proxy")

#             trading_enabled = rt.get("trading_enabled", False)
#             flagged_stop = rt.get("stop_flag", False)

#             # ------------------------------------------------------------
#             # MASTER DISABLED
#             # ------------------------------------------------------------
#             if not trading_enabled or flagged_stop:

#                 # stop WS
#                 if self.signal_stream:
#                     try: self.signal_stream.stop()
#                     except: pass
#                 self.signal_stream = None

#                 # cancel WS task
#                 if stream_task and not stream_task.done():
#                     stream_task.cancel()
#                     try: await stream_task
#                     except: pass
#                 stream_task = None

#                 # stop COPY loop
#                 if copy_loop_task and not copy_loop_task.done():
#                     self.copy.stop_signal_loop()
#                     copy_loop_task.cancel()
#                     try: await copy_loop_task
#                     except: pass
#                 copy_loop_task = None

#                 self._reset_master_runtime()

#                 last_hash = None
#                 await asyncio.sleep(0.3)
#                 continue

#             # ------------------------------------------------------------
#             # VERIFY CREDS
#             # ------------------------------------------------------------
#             if not (api_key and api_secret):
#                 await asyncio.sleep(0.3)
#                 continue

#             cur_hash = creds_hash(master_cfg)

#             # ------------------------------------------------------------
#             # SAME CREDS → RUNNING
#             # ------------------------------------------------------------
#             if cur_hash == last_hash and stream_task and not stream_task.done():
#                 await asyncio.sleep(0.2)
#                 continue

#             # ------------------------------------------------------------
#             # CREDS CHANGED → RELOAD EVERYTHING
#             # ------------------------------------------------------------
#             if self.signal_stream:
#                 self.logfsm.enter("RELOAD")

#             # stop old stream
#             if self.signal_stream:
#                 try: self.signal_stream.stop()
#                 except: pass

#             if stream_task and not stream_task.done():
#                 stream_task.cancel()
#                 try: await stream_task
#                 except: pass

#             self._reset_master_runtime()

#             # ---------------------------------------------------------
#             # START NEW WS STREAM
#             # ---------------------------------------------------------
#             self.signal_cache = SignalCache()

#             self.signal_stream = MasterSignalStream(
#                 api_key=api_key,
#                 api_secret=api_secret,
#                 signal_cache=self.signal_cache,
#                 logger=self.logger,
#                 stop_flag=self.stop_flag,
#                 proxy_url=proxy                
#             )
#             stream_task = asyncio.create_task(self.signal_stream.start())

#             while not self.stop_flag():
#                 await asyncio.sleep(0.05)
#                 if self.signal_stream.ready:
#                     break

#             print("✔ Master WS ready")

#             # ---------------------------------------------------------
#             # RECREATE MASTER-PAYLOAD
#             # ---------------------------------------------------------
#             if self.payload:
#                 try: self.payload.stop()         # ← FIX
#                 except: pass

#             if self.payload_task and not self.payload_task.done():
#                 self.payload_task.cancel()
#                 try:
#                     await self.payload_task
#                 except:
#                     pass
#             self.payload_task = None

#             self.payload = MasterPayload(
#                 cache=self.signal_cache,
#                 mc=self.mc,
#                 logger=self.logger,
#                 stop_flag=self.stop_flag
#             )
#             # ← ПОДКЛЮЧЕНИЕ ПЕЙЛОАДА К RAW STREAM
#             self.payload_task = asyncio.create_task(self.payload.run())
#             self.copy.attach_payload(self.payload)

#             # ---------------------------------------------------------
#             # STOP OLD COPY LOOP
#             # ---------------------------------------------------------
#             if copy_loop_task and not copy_loop_task.done():
#                 self.copy.stop_signal_loop()
#                 copy_loop_task.cancel()
#                 try: await copy_loop_task
#                 except: pass

#             # ---------------------------------------------------------
#             # START NEW COPY LOOP
#             # ---------------------------------------------------------
#             copy_loop_task = asyncio.create_task(self.copy.signal_loop())

#             last_hash = cur_hash
#             self.logfsm.enter("RUNNING")

#         self.logfsm.enter("DISABLED")




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
#     normalize_symbol,
#     side_from_order_side,
#     side_from_position_type,
# )

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
#         if IS_SHOW_SIGNAL: print(ev)
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
#         side = side_from_order_side(int(data.get("side", 0)))
#         await self._emit(symbol, side, "stop_attached", data)

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



# import asyncio
# import aiohttp
# import ssl
# from typing import *
# from a_config import PING_URL, PING_INTERVAL
# from c_log import ErrorHandler


# SSL_CTX = ssl.create_default_context()
# SSL_CTX.check_hostname = False
# SSL_CTX.verify_mode = ssl.CERT_NONE


# class NetworkManager:
#     def __init__(
#         self,
#         logger: ErrorHandler,
#         proxy_url: Optional[str],
#         stop_flag: Callable[[], bool],
#     ):        
#         self.session: Optional[aiohttp.ClientSession] = None
#         self.logger = logger
#         self._ping_task: asyncio.Task | None = None
#         if not proxy_url or proxy_url == "0" or proxy_url.strip() == "":
#             proxy_url = None
#         self.proxy_url = proxy_url
#         self.stop_flag = stop_flag
        
#         logger.wrap_foreign_methods(self)

#     async def initialize_session(self):
#         if not self.session or self.session.closed:

#             # Если есть прокси — отключаем SSL полностью
#             if self.proxy_url:
#                 connector = aiohttp.TCPConnector(ssl=False)
#                 self.session = aiohttp.ClientSession(connector=connector)

#             # Если нет прокси — используем SSL_CTX для всех запросов
#             else:
#                 # connector = aiohttp.TCPConnector(ssl=SSL_CTX)
#                 # self.session = aiohttp.ClientSession(connector=connector)
#                 self.session = aiohttp.ClientSession()

#     async def _ping_once(self) -> bool:
#         if not self.session or self.session.closed:
#             await self.initialize_session()
#         try:
#             timeout = aiohttp.ClientTimeout(total=5)
#             async with self.session.get(PING_URL, timeout=timeout) as resp:
#                 return resp.status == 200
#         except (aiohttp.ClientError, asyncio.TimeoutError):
#             return False

#     async def _ping_loop(self):
#         """Фоновый таск: держим сессию живой."""
#         attempt = 0
#         try:
#             while not self.stop_flag():
#                 attempt += 1
#                 alive = await self._ping_once()
#                 if not alive:
#                     self.logger.debug_info_notes(f"🔁 Пинг неудачен, пересоздаем сессию (попытка {attempt})")
#                     try:
#                         if self.session and not self.session.closed:
#                             await self.session.close()
#                     except Exception as e:
#                         self.logger.debug_error_notes(f"Ошибка при закрытии сессии: {e}")
#                     await self.initialize_session()
#                 await asyncio.sleep(PING_INTERVAL)

#         finally:
#             await self.shutdown_session()

#     def start_ping_loop(self):
#         """Запуск фонового пинга."""
#         if self._ping_task is None or self._ping_task.done():
#             self._ping_task = asyncio.create_task(self._ping_loop())

#     async def shutdown_session(self):
#         """Закрытие сессии и остановка фонового пинга."""
#         if self._ping_task and not self._ping_task.done():
#             self._ping_task.cancel()
#             try:
#                 await self._ping_task
#             except asyncio.CancelledError:
#                 pass
#         if self.session and not self.session.closed:
#             try:
#                 await self.session.close()
#             except Exception as e:
#                 self.logger.debug_error_notes(f"Ошибка при закрытии сессии: {e}")




# from __future__ import annotations

# import asyncio
# import random
# from typing import Callable, Iterable, Optional

# from aiogram import Bot
# from aiogram.exceptions import (
#     TelegramAPIError,
#     TelegramRetryAfter,
#     TelegramForbiddenError,
#     TelegramNetworkError,
# )

# from c_log import ErrorHandler


# class TelegramNotifier:
#     """
#     ДЕТЕРМИНИРОВАННЫЙ TG notifier

#     • никаких очередей
#     • никаких фоновых циклов
#     • один вызов = одно сообщение
#     • retry / rate-limit внутри
#     """

#     def __init__(
#         self,
#         bot: Bot,
#         logger: ErrorHandler,
#         stop_bot: Callable[[], bool],
#     ):
#         self.bot = bot
#         self.logger = logger
#         self.stop_bot = stop_bot
#         self.logger.wrap_foreign_methods(self)

#     # ==========================================================
#     # PUBLIC API
#     # ==========================================================

#     async def send(
#         self,
#         chat_id: int,
#         text: str,
#     ) -> Optional[int]:
#         """
#         Отправка одного сообщения.
#         Возвращает message_id или None.
#         """
#         return await self._send_message(chat_id, text)

#     async def send_block(
#         self,
#         chat_id: int,
#         texts: Iterable[str],
#         separator: str = "\n\n",
#     ) -> Optional[int]:
#         """
#         Отправка нескольких сообщений ОДНИМ блоком.
#         """
#         block = separator.join(t for t in texts if t)
#         if not block:
#             return None
#         return await self._send_message(chat_id, block)

#     # ==========================================================
#     # INTERNAL
#     # ==========================================================

#     async def _send_message(
#         self,
#         chat_id: int,
#         text: str,
#     ) -> Optional[int]:

#         while not self.stop_bot():
#             try:
#                 msg = await self.bot.send_message(
#                     chat_id=chat_id,
#                     text=text,
#                     parse_mode="HTML",
#                 )
#                 return msg.message_id

#             except TelegramRetryAfter as e:
#                 wait = int(getattr(e, "retry_after", 5))
#                 self.logger.debug_error_notes(
#                     f"[TG SEND][{chat_id}] rate limit → wait {wait}s",
#                     is_print=True,
#                 )
#                 await asyncio.sleep(wait)

#             except TelegramNetworkError as e:
#                 wait = random.uniform(1.0, 3.0)
#                 self.logger.debug_error_notes(
#                     f"[TG SEND][{chat_id}] network error → retry in {wait:.1f}s: {e}",
#                     is_print=True,
#                 )
#                 await asyncio.sleep(wait)

#             except TelegramForbiddenError:
#                 self.logger.debug_error_notes(
#                     f"[TG SEND][{chat_id}] bot blocked by user",
#                     is_print=True,
#                 )
#                 return None

#             except TelegramAPIError as e:
#                 self.logger.debug_error_notes(
#                     f"[TG SEND][{chat_id}] API error: {e}",
#                     is_print=True,
#                 )
#                 return None

#             except Exception as e:
#                 self.logger.debug_error_notes(
#                     f"[TG SEND][{chat_id}] unexpected error: {e}",
#                     is_print=True,
#                 )
#                 return None

#         return None



# # TG.tg_ui_copytrade.py
# from __future__ import annotations

# import asyncio
# from typing import *
# from aiogram import Bot, Dispatcher, types
# from aiogram.filters import Command

# from a_config import (
#     COPY_TEMPLATE,
#     COPY_NUMBER,
# )
# from c_log import ErrorHandler
# from c_utils import now
# from b_context import MainContext
# from DESTRIBUTOR.helpers import Runtime
# from .tg_helpers import parse_id_range, validate_master, validate_copy, format_status, can_push_cmd


# # =====================================================================
# #                          MAIN UI CLASS
# # =====================================================================

# class CopyTradeUI:
#     """
#     Полный Telegram UI для:
#     • Master (ID=0)
#     • Copies (1..COPY_NUMBER)

#     Всё залочено на self.admin_id — бот монопользовательский.
#     """

#     def __init__(
#             self,
#             bot: Bot,
#             dp: Dispatcher,
#             ctx: MainContext,
#             logger: ErrorHandler,
#             runtime: Runtime,
#             admin_id: int,
#             on_close: Callable[[List[int]], Awaitable[None]]
#         ):
#         self.bot = bot
#         self.dp = dp
#         self.ctx = ctx
#         self.log = logger
#         self.runtime = runtime
#         self.admin_id = admin_id
#         self.on_close = on_close

#         # runtime input state: chat → {...}
#         self.await_input: Dict[int, Optional[Dict[str, Any]]] = {}

#         # =====================================================================
#         #                   INIT MASTER + COPIES (генерируем master (0) + copies (1..N))
#         # =====================================================================
#         self.ctx.load_accounts()

#         # регистрируем handlers
#         self._register_handlers()

#         self.log.wrap_foreign_methods(self)

#     # =====================================================================
#     #                     MENU TEMPLATES
#     # =====================================================================

#     def menu_main(self):
#         kb = [
#             [types.KeyboardButton(text="▶️ START"), types.KeyboardButton(text="⏹ STOP")],
#             [types.KeyboardButton(text="🔒 CLOSE")],
#             [types.KeyboardButton(text="🧩 MASTER"), types.KeyboardButton(text="👥 COPIES")],
#         ]
#         return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

#     def menu_master(self):
#         kb = [
#             [types.KeyboardButton(text="⚙ MX Settings")],
#             [types.KeyboardButton(text="📑 Master Status")],
#             [types.KeyboardButton(text="🔄 Change Master")],
#             [types.KeyboardButton(text="⬅ Back")],
#         ]
#         return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

#     def menu_copies(self):
#         kb = [
#             [types.KeyboardButton(text="📋 List Copies")],
#             [types.KeyboardButton(text="📑 Copy Status")],   # ← НОВАЯ КНОПКА
#             [types.KeyboardButton(text="✏ Edit Copy")],
#             [types.KeyboardButton(text="➕ Add Copy"), types.KeyboardButton(text="🗑 Delete Copy")],
#             [types.KeyboardButton(text="⬅ Back")],
#         ]
#         return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

#     # =====================================================================
#     #                       INTERNAL HELPERS
#     # =====================================================================

#     def _check_admin(self, msg: types.Message) -> bool:
#         if msg.chat.id != self.admin_id:
#             asyncio.create_task(msg.answer("❗ Нет доступа"))
#             return False
#         return True

#     def _enter_input(self, chat_id: int, **kwargs):
#         self.await_input[chat_id] = kwargs

#     def _exit_input(self, chat_id: int):
#         self.await_input[chat_id] = None

#     # =====================================================================
#     #                     REGISTER HANDLERS
#     # =====================================================================

#     def _register_handlers(self):
#         dp = self.dp

#         dp.message.register(self.cmd_start, Command("start"))
#         dp.message.register(self.cmd_status, Command("status"))

#         # MAIN menu
#         dp.message.register(self.btn_start, lambda m: m.text == "▶️ START")
#         dp.message.register(self.btn_stop, lambda m: m.text == "⏹ STOP")
#         dp.message.register(self.btn_master, lambda m: m.text == "🧩 MASTER")
#         dp.message.register(self.btn_copies, lambda m: m.text == "👥 COPIES")
#         dp.message.register(self.btn_close, lambda m: m.text == "🔒 CLOSE")

#         # MASTER submenu
#         dp.message.register(self.btn_mx_settings, lambda m: m.text == "⚙ MX Settings")
#         dp.message.register(self.btn_mx_status, lambda m: m.text == "📑 Master Status")
#         dp.message.register(self.btn_mx_change, lambda m: m.text == "🔄 Change Master")
#         dp.message.register(self.btn_back, lambda m: m.text == "⬅ Back")

#         # COPIES submenu
#         dp.message.register(self.btn_copy_list, lambda m: m.text == "📋 List Copies")
#         dp.message.register(self.btn_copy_edit, lambda m: m.text == "✏ Edit Copy")
#         dp.message.register(self.btn_copy_add, lambda m: m.text == "➕ Add Copy")
#         dp.message.register(self.btn_copy_del, lambda m: m.text == "🗑 Delete Copy")
#         dp.message.register(self.btn_copy_status, lambda m: m.text == "📑 Copy Status")

#         # universal input handler
#         dp.message.register(self.handle_text_input)

#     # =====================================================================
#     #                          BASIC COMMANDS
#     # =====================================================================

#     async def cmd_start(self, msg: types.Message):
#         if not self._check_admin(msg):
#             return
#         await msg.answer("Добро пожаловать!", reply_markup=self.menu_main())

#     async def cmd_status(self, msg: types.Message):
#         if not self._check_admin(msg):
#             return
#         await self._ask_status_id(msg)

#     # =====================================================================
#     #                          MAIN BUTTONS
#     # =====================================================================

#     async def btn_start(self, msg: types.Message):
#         if not self._check_admin(msg):
#             return

#         cfg = self.ctx.copy_configs[0]
#         rt = cfg.setdefault("runtime", {})

#         # ❗ STOP ожидает подтверждения -> запрещаем START
#         if rt.get("stop_confirm"):
#             await msg.answer("❗ Остановка не завершена. Нажмите STOP ещё раз для подтверждения.")
#             return

#         # ❗ валидация
#         reason = validate_master(cfg)
#         if reason:
#             await msg.answer(f"❗ Мастер конфиг неполный:\n{reason}")
#             return

#         # 🔥 ПОЛНЫЙ RESET всех служебных флагов + старт
#         rt["stop_flag"] = False
#         rt["stop_confirm"] = False
#         rt["trading_enabled"] = True

#         await msg.answer("▶️ Мастер запущен", reply_markup=self.menu_main())

#     async def btn_stop(self, msg: types.Message):
#         if not self._check_admin(msg):
#             return

#         cfg = self.ctx.copy_configs[0]
#         rt = cfg.setdefault("runtime", {})

#         if not rt.get("trading_enabled"):
#             await msg.answer("⏹ Мастер уже остановлен.")
#             return

#         if not rt.get("stop_confirm"):
#             rt["stop_confirm"] = True
#             await msg.answer("❗ Нажмите STOP ещё раз для подтверждения.")
#             return

#         rt["trading_enabled"] = False
#         rt["stop_flag"] = True
#         rt["stop_confirm"] = False

#         await msg.answer("⏹ Остановка мастера активирована.")

#     async def btn_status(self, msg: types.Message):
#         if not self._check_admin(msg):
#             return
#         await self._ask_status_id(msg)

#     async def btn_master(self, msg: types.Message):
#         if not self._check_admin(msg):
#             return
#         await msg.answer("MASTER MENU:", reply_markup=self.menu_master())

#     async def btn_copies(self, msg: types.Message):
#         if not self._check_admin(msg):
#             return
#         await msg.answer("COPIES MENU:", reply_markup=self.menu_copies())

#     async def btn_close(self, msg: types.Message):
#         if not self._check_admin(msg):
#             return

#         self._enter_input(msg.chat.id, mode="close_ids")
#         await msg.answer(
#             "Введите ID или диапазон ID для закрытия позиций.\n"
#             "Пример: 1-3, 7, 9-5\n"
#             "Можно включать и 0 (мастер)."
#         )

#     async def btn_back(self, msg: types.Message):
#         if not self._check_admin(msg):
#             return
#         await msg.answer("Главное меню:", reply_markup=self.menu_main())

#     # =====================================================================
#     #                           STATUS BY ID
#     # =====================================================================

#     async def _ask_status_id(self, msg: types.Message):
#         cid = msg.chat.id
#         self._enter_input(cid, mode="status_id")
#         await msg.answer("Введите ID (0=master или 1..N):")

#     async def _send_status(self, msg: types.Message, acc_id: int, reply_kb=None):
#         cfg = self.ctx.copy_configs.get(acc_id)
#         if not cfg:
#             await msg.answer("❗ Нет такого аккаунта.")
#             return

#         if reply_kb is None:
#             await msg.answer(format_status(cfg))
#         else:
#             await msg.answer(format_status(cfg), reply_markup=reply_kb)

#     # =====================================================================
#     #                         MASTER SETTINGS
#     # =====================================================================

#     async def btn_mx_settings(self, msg: types.Message):
#         if not self._check_admin(msg):
#             return

#         text = (
#             "Настройки MASTER:\n"
#             "Выберите параметр для изменения:\n"
#             "1) api_key\n"
#             "2) api_secret\n"
#             "3) uid\n"
#             "4) proxy\n\n"
#             "Отправьте номер пункта."
#         )
#         self._enter_input(msg.chat.id, mode="master_edit")
#         await msg.answer(text)

#     async def btn_mx_status(self, msg: types.Message):
#         if not self._check_admin(msg):
#             return
#         await self._send_status(msg, 0)

#     async def btn_mx_change(self, msg: types.Message):
#         if not self._check_admin(msg):
#             return
#         self._enter_input(msg.chat.id, mode="change_master")
#         await msg.answer("Введите ID копи, с которым нужно поменяться ролями:")

#     # =====================================================================
#     #                          COPIES MENU
#     # =====================================================================

#     async def btn_copy_list(self, msg: types.Message):
#         if not self._check_admin(msg):
#             return

#         text = "Список копи-аккаунтов:\n\n"
#         for cid, cfg in self.ctx.copy_configs.items():
#             if cid == 0:
#                 continue
#             status = "🟢 ON" if cfg.get("enabled") else "⚪ OFF"
#             text += f"{cid}: {status}\n"

#         await msg.answer(text)

#     async def btn_copy_edit(self, msg: types.Message):
#         if not self._check_admin(msg):
#             return

#         self._enter_input(msg.chat.id, mode="copy_edit_select")
#         await msg.answer("Введите ID копи-аккаунта, который хотите изменить:")

#     async def btn_copy_add(self, msg: types.Message):
#         if not self._check_admin(msg):
#             return

#         self._enter_input(msg.chat.id, mode="copy_add")
#         await msg.answer("Введите ID копи-аккаунта, который хотите активировать:")

#     async def btn_copy_del(self, msg: types.Message):
#         if not self._check_admin(msg):
#             return

#         self._enter_input(msg.chat.id, mode="copy_del")
#         await msg.answer("Введите ID (или диапазон 5-10) копи-аккаунтов для удаления:")

#     async def btn_copy_status(self, msg: types.Message):
#         if not self._check_admin(msg):
#             return

#         self._enter_input(msg.chat.id, mode="copy_status_id")
#         await msg.answer("Введите ID копи-аккаунта (1..N):")

#     # =====================================================================
#     #                   UNIVERSAL TEXT INPUT HANDLER
#     # =====================================================================

#     async def handle_text_input(self, msg: types.Message):
#         chat_id = msg.chat.id
#         if chat_id != self.admin_id:
#             return

#         wait = self.await_input.get(chat_id)
#         if not wait:
#             return

#         raw = msg.text.strip()

#         # CANCEL
#         if raw.lower() in ("cancel", "отмена", "назад", ""):
#             self._exit_input(chat_id)
#             await msg.answer("❕ Ввод отменён.", reply_markup=self.menu_main())
#             return

#         mode = wait["mode"]

#         # ============================
#         #     CLOSE (id or range)
#         # ============================
#         if mode == "close_ids":
#             try:
#                 ids = parse_id_range(raw, allow_zero=True)

#                 if not ids:
#                     await msg.answer("❗ Не найдено допустимых ID.")
#                     return

#                 if not can_push_cmd(self.ctx):
#                     await msg.answer("⏳ Подождите секунду...")
#                     return

#                 asyncio.create_task(self.on_close(ids))

#                 self._exit_input(chat_id)
#                 await msg.answer(
#                     f"✔ Команда CLOSE отправлена для: {ids}",
#                     reply_markup=self.menu_main()
#                 )
#             except Exception as e:
#                 await msg.answer(f"❗ Ошибка формата: {e}")
#             return

#         # ============================
#         #     CHANGE MASTER
#         # ============================
#         if mode == "change_master":
#             try:
#                 cid = int(raw)
#                 if cid == 0 or cid not in self.ctx.copy_configs:
#                     await msg.answer("❗ Неверный ID.")
#                     return

#                 master = self.ctx.copy_configs[0]
#                 copy_acc = self.ctx.copy_configs[cid]

#                 # --- VALIDATE NEW MASTER CREDS ---
#                 ex = copy_acc.get("exchange", {})
#                 if not ex.get("api_key") or not ex.get("api_secret"):
#                     await msg.answer("❗ У этого копи нет необходимых кредов для роли MASTER.\n"
#                                     "Нужны api_key и api_secret.")
#                     return

#                 # swap exchange credentials
#                 master["exchange"], copy_acc["exchange"] = (
#                     copy_acc["exchange"],
#                     master["exchange"],
#                 )

#                 await self.ctx.save_users()
#                 self._exit_input(chat_id)
#                 await msg.answer("✔ Мастер успешно сменён!", reply_markup=self.menu_main())
#             except:
#                 await msg.answer("❗ Ошибка ID.")
#             return

#         # ============================
#         #     MASTER EDIT
#         # ============================
#         if mode == "master_edit":
#             if raw not in ("1", "2", "3", "4"):
#                 await msg.answer("❗ Неверный пункт.")
#                 return

#             field_map = {
#                 "1": "exchange.api_key",
#                 "2": "exchange.api_secret",
#                 "3": "exchange.uid",
#                 "4": "exchange.proxy",
#             }

#             field = field_map[raw]
#             self._enter_input(chat_id, mode="master_edit_final", field=field)
#             await msg.answer(f"Введите значение для {field}:")
#             return

#         if mode == "master_edit_final":
#             field = wait["field"]
#             cfg = self.ctx.copy_configs[0]

#             target = cfg
#             parts = field.split(".")
#             for p in parts[:-1]:
#                 target = target.setdefault(p, {})

#             last = parts[-1]
#             target[last] = raw

#             await self.ctx.save_users()
#             self._exit_input(chat_id)
#             await msg.answer("✔ Сохранено!", reply_markup=self.menu_master())
#             return

#         # ============================
#         #     COPY ADD
#         # ============================
#         if mode == "copy_add":
#             try:
#                 cid = int(raw)
#                 if cid == 0:
#                     await msg.answer("❗ ID=0 — это мастер. Для копи используйте 1..N.")
#                     return
#                 if cid < 1 or cid > COPY_NUMBER:
#                     await msg.answer("❗ Недопустимый ID.")
#                     return

#                 cfg = self.ctx.copy_configs[cid]

#                 # check creds
#                 missing = validate_copy(cfg)
#                 if missing:
#                     await msg.answer(f"❗ Нельзя активировать — конфиг неполный:\n{missing}")
#                     return

#                 cfg["enabled"] = True
#                 cfg["created_at"] = now()

#                 await self.ctx.save_users()

#                 await self.runtime.activate_copy(cid)
#                 self._exit_input(chat_id)
#                 await msg.answer("✔ Копи активирован!", reply_markup=self.menu_copies())
#             except:
#                 await msg.answer("❗ Ошибка ID.")
#             return

#         # ============================
#         #     COPY DELETE (range)
#         # ============================
#         if mode == "copy_del":
#             try:
#                 ids = parse_id_range(raw)
#                 for cid in ids:
#                     if cid == 0:
#                         await msg.answer("❗ ID=0 — это мастер. Для копи используйте 1..N.")
#                         return

#                     cfg = self.ctx.copy_configs[cid]
#                     # сбрасываем в дефолт:
#                     await self.runtime.deactivate_copy(cid)
#                     fresh = COPY_TEMPLATE.copy()
#                     fresh["id"] = cid
#                     fresh["enabled"] = False
#                     fresh["created_at"] = None
#                     self.ctx.copy_configs[cid] = fresh

#                 await self.ctx.save_users()
#                 self._exit_input(chat_id)
#                 await msg.answer("✔ Аккаунты сброшены!", reply_markup=self.menu_copies())
#             except:
#                 await msg.answer("❗ Ошибка формата.")
#             return
        
#         # ============================
#         #    COPY STATUS (ID)
#         # ============================
#         if mode == "copy_status_id":
#             try:
#                 cid = int(raw)
#                 if cid == 0 or cid not in self.ctx.copy_configs:
#                     await msg.answer("❗ Неверный ID.")
#                     return

#                 self._exit_input(chat_id)
#                 await self._send_status(msg, cid, reply_kb=self.menu_copies())
#             except:
#                 await msg.answer("❗ Ошибка ID.")
#             return

#         # ============================
#         #     COPY EDIT — choose ID
#         # ============================
#         if mode == "copy_edit_select":
#             try:
#                 cid = int(raw)
#                 if cid == 0:
#                     await msg.answer("❗ ID=0 — это мастер. Для копи используйте 1..N.")
#                     return

#                 if cid < 1 or cid > COPY_NUMBER:
#                     await msg.answer("❗ ID вне диапазона.")
#                     return

#                 self._enter_input(chat_id, mode="copy_edit_field", cid=cid)
#                 await msg.answer(
#                     "Выберите поле:\n"
#                     "1) api_key\n"
#                     "2) api_secret\n"
#                     "3) uid\n"
#                     "4) proxy\n"
#                     "5) coef\n"
#                     "6) leverage\n"
#                     "7) max_position_size\n"
#                     "8) random_size_pct\n"
#                     "9) delay_ms\n"
#                     "10) enabled (0/1)\n"
#                 )
#             except:
#                 await msg.answer("❗ Ошибка ID.")
#             return

#         # ============================
#         #     COPY EDIT — choose FIELD
#         # ============================
#         if mode == "copy_edit_field":
#             cid = wait["cid"]
#             if raw not in ("1","2","3","4","5","6","7","8","9","10"):
#                 await msg.answer("❗ Неверный пункт.")
#                 return

#             fields = {
#                 "1": "exchange.api_key",
#                 "2": "exchange.api_secret",
#                 "3": "exchange.uid",
#                 "4": "exchange.proxy",
#                 "5": "coef",
#                 "6": "leverage",
#                 "7": "max_position_size",
#                 "8": "random_size_pct",
#                 "9": "delay_ms",
#                 "10": "enabled",
#             }

#             field = fields[raw]
#             self._enter_input(chat_id, mode="copy_edit_final", cid=cid, field=field)
#             await msg.answer(f"Введите значение для {field}:")
#             return

#         # ============================
#         #     COPY EDIT — final write
#         # ============================
#         if mode == "copy_edit_final":
#             cid = wait["cid"]
#             field = wait["field"]
#             cfg = self.ctx.copy_configs[cid]

#             target = cfg
#             parts = field.split(".")
#             for p in parts[:-1]:
#                 target = target.setdefault(p, {})
#             last = parts[-1]

#             # convert type
#             if last in ("coef", "max_position_size", "delay_ms", "leverage"):
#                 try:
#                     target[last] = float(raw) if "." in raw else int(raw)
#                 except:
#                     await msg.answer("❗ Требуется число.")
#                     return

#             elif last == "random_size_pct":
#                 try:
#                     a,b = raw.replace(" ","").split(",")
#                     target[last] = (float(a), float(b))
#                 except:
#                     await msg.answer("❗ Формат: 0.9, 1.1")
#                     return

#             # elif last == "enabled":
#             #     if raw not in ("0","1"):
#             #         await msg.answer("❗ Введите 0 или 1.")
#             #         return
#             #     target[last] = raw == "1"

#             elif last == "enabled":
#                 if raw not in ("0","1"):
#                     await msg.answer("❗ Введите 0 или 1.")
#                     return
#                 enabled = raw == "1"
#                 target[last] = enabled

#                 await self.ctx.save_users()

#                 if enabled:
#                     await self.runtime.activate_copy(cid)
#                 else:
#                     await self.runtime.deactivate_copy(cid)

#                 self._exit_input(chat_id)
#                 await msg.answer("✔ Сохранено!", reply_markup=self.menu_copies())
#                 return

#             else:
#                 target[last] = raw

#             await self.ctx.save_users()
#             self._exit_input(chat_id)
#             await msg.answer("✔ Сохранено!", reply_markup=self.menu_copies())
#             return