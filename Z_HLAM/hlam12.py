
    # async def _route(self, ev: SignalEvent):
    #     et = ev.event_type
    #     symbol, side = ev.symbol, ev.side

    #     # ------------------------------------------------------
    #     # ATTACHED OCO — БЕЗ side
    #     # ------------------------------------------------------
    #     if et == "stop_attached":
    #         root = self.mc.copy_configs.setdefault(0, {}).setdefault("runtime", {})
    #         oco_buf = root.setdefault("_attached_oco", {})

    #         oco_buf[symbol] = {
    #             "tp": Utils.safe_float(ev.raw.get("takeProfitPrice")),
    #             "sl": Utils.safe_float(ev.raw.get("stopLossPrice")),
    #         }
    #         return

    #     if not side:
    #         return

    #     pv = self._ensure_pos_vars(symbol, side)

    #     # ------------------------------------------------------
    #     # LIMIT OPEN / CLOSE
    #     # ------------------------------------------------------
    #     if et in ("open_limit", "close_limit") and ev.raw.get("state") != 4:
    #         pv["_last_exec_source"] = "limit"

    #         await self._emit(
    #             event="buy" if et == "open_limit" else "sell",
    #             method="limit",
    #             symbol=symbol,
    #             side=side,
    #             partially=False,
    #             payload={
    #                 # базовое
    #                 "order_id": ev.raw.get("orderId"),
    #                 "price": Utils.safe_float(ev.raw.get("price")),
    #                 "qty": Utils.safe_float(ev.raw.get("vol")),

    #                 # торговая семантика
    #                 "reduce_only": bool(ev.raw.get("reduceOnly")),
    #                 "open_type": ev.raw.get("openType"),          # 1 isolated / 2 cross
    #                 "order_type": ev.raw.get("orderType"),        # 1 limit
    #                 "position_mode": ev.raw.get("positionMode"),  # hedge / one-way

    #                 # риск / маржа
    #                 "leverage": ev.raw.get("leverage"),
    #                 "used_margin": Utils.safe_float(ev.raw.get("usedMargin")),
    #             },
    #             sig_type="copy",
    #             ev_raw=ev,
    #         )
    #         return

    #     # ------------------------------------------------------
    #     # LIMIT CANCEL
    #     # ------------------------------------------------------
    #     if et in ("order_cancelled", "order_invalid"):
    #         pv["_last_exec_source"] = None

    #         await self._emit(
    #             event="canceled",
    #             method="limit",
    #             symbol=symbol,
    #             side=side,
    #             partially=False,
    #             payload={
    #                 "order_id": ev.raw.get("orderId"),
    #             },
    #             sig_type="copy",
    #             ev_raw=ev,
    #         )
    #         return

    #     # ------------------------------------------------------
    #     # DEAL (price cache)
    #     # ------------------------------------------------------
    #     if et == "deal":
    #         price = Utils.safe_float(ev.raw.get("price"))
    #         if price:
    #             self._last_deal[(symbol, side)] = {"price": price, "ts": ev.ts}
    #         return

    #     # ------------------------------------------------------
    #     # TRIGGER ORDERS (plan)
    #     # ------------------------------------------------------
    #     if et in ("plan_order", "plan_executed", "plan_cancelled"):
    #         trigger_price = Utils.safe_float(
    #             ev.raw.get("triggerPrice") or ev.raw.get("price")
    #         )
    #         if not trigger_price:
    #             return

    #         pv["_last_exec_source"] = "trigger"

    #         if et == "plan_executed":
    #             event, sig = "filled", "log"
    #         elif et == "plan_order":
    #             event, sig = "buy" if ev.raw.get("side") in (1, 3) else "sell", "copy"
    #         else:
    #             event, sig = "canceled", "copy"

    #         await self._emit(
    #             event=event,
    #             method="trigger",
    #             symbol=symbol,
    #             side=side,
    #             partially=False,
    #             payload={
    #                 "order_id": ev.raw.get("orderId"),
    #                 "trigger_price": trigger_price,

    #                 "reduce_only": bool(ev.raw.get("reduceOnly")),

    #                 # как исполняется триггер
    #                 "trigger_exec": (
    #                     "market" if ev.raw.get("triggerType") == 2 else "limit"
    #                 ),

    #                 # параметры позиции
    #                 "open_type": ev.raw.get("openType"),
    #                 "order_type": ev.raw.get("orderType"),
    #                 "position_mode": ev.raw.get("positionMode"),
    #                 "leverage": ev.raw.get("leverage"),

    #                 # объём
    #                 "qty": Utils.safe_float(ev.raw.get("vol")),
    #             },
    #             sig_type=sig,
    #             ev_raw=ev,
    #         )
    #         return

    #     # ------------------------------------------------------
    #     # POSITION SNAPSHOT
    #     # ------------------------------------------------------
    #     if et in ("position_opened", "position_closed"):
    #         await self._on_position_snapshot(ev, pv)

    # ==========================================================
    # async def _on_position_snapshot(self, ev: SignalEvent, pv: dict):
    #     raw = ev.raw
    #     symbol, side = ev.symbol, ev.side
    #     key = (symbol, side)

    #     if self._is_stale_snapshot(key, raw):
    #         return

    #     await asyncio.sleep(OPEN_TTL)

    #     qty_prev = pv["qty"]
    #     qty_cur = Utils.safe_float(raw.get("holdVol"), 0.0)

    #     if qty_prev == qty_cur:
    #         return

    #     price = Utils.to_human_digit(self._fix_price(raw, symbol, side))
    #     last_src = pv["_last_exec_source"]

    #     # --------------------------------------------------
    #     # подтягиваем attached OCO по symbol (если было)
    #     # --------------------------------------------------
    #     root = self.mc.copy_configs.setdefault(0, {}).setdefault("runtime", {})
    #     oco_buf = root.get("_attached_oco", {})

    #     oco = oco_buf.pop(symbol, None)
    #     if oco:
    #         pv["attached_tp"] = oco.get("tp")
    #         pv["attached_sl"] = oco.get("sl")

    #     # ================= BUY =================
    #     if qty_cur > qty_prev:
    #         pv["qty"] = qty_cur
    #         pv["in_position"] = True
    #         delta = abs(qty_cur - qty_prev)

    #         payload = {
    #             # количественная часть
    #             "qty_delta": delta,
    #             "qty_before": qty_prev,
    #             "qty_after": qty_cur,

    #             # цена факта
    #             "price": price,

    #             # ===== ДЛЯ make_order =====
    #             "contract": delta,
    #             "position_side": side,              # LONG / SHORT
    #             "side": "BUY",                      # т.к. qty растёт
    #             "market_type": "MARKET",

    #             # параметры позиции
    #             "leverage": raw.get("leverage"),
    #             "open_type": raw.get("openType"),
    #         }

    #         if pv["attached_tp"]:
    #             payload["tp_price"] = pv["attached_tp"]
    #         if pv["attached_sl"]:
    #             payload["sl_price"] = pv["attached_sl"]

    #         sig_type = (
    #             "log"
    #             if last_src in ("limit", "trigger") and qty_prev == 0
    #             else "copy"
    #         )

    #         await self._emit(
    #             event="buy",
    #             method="market",
    #             symbol=symbol,
    #             side=side,
    #             partially=qty_prev > 0,
    #             payload=payload,
    #             sig_type=sig_type,
    #             ev_raw=ev,
    #         )

    #         pv["attached_tp"] = None
    #         pv["attached_sl"] = None

    #     # ================= SELL =================
    #     elif qty_cur < qty_prev:
    #         pv["qty"] = qty_cur
    #         pv["in_position"] = qty_cur > 0

    #         is_full_close = qty_cur == 0
    #         sig_type = (
    #            "log"
    #             if last_src in ("limit", "trigger") and is_full_close
    #             else "copy"
    #         )
    #         delta = abs(qty_cur - qty_prev)

    #         await self._emit(
    #             event="sell",
    #             method="market",
    #             symbol=symbol,
    #             side=side,
    #             partially=qty_cur > 0,                
    #             payload = {
    #                 # количественная часть
    #                 "qty_delta": delta,
    #                 "qty_before": qty_prev,
    #                 "qty_after": qty_cur,

    #                 # цена факта
    #                 "price": price,

    #                 # ===== ДЛЯ make_order =====
    #                 "contract": delta,
    #                 "position_side": side,              # LONG / SHORT
    #                 "side": "SELL",
    #                 "market_type": "MARKET",

    #                 # параметры позиции
    #                 "leverage": raw.get("leverage"),
    #                 "open_type": raw.get("openType"),
    #             },
    #             sig_type=sig_type,
    #             ev_raw=ev,
    #         )

    #     pv["_last_exec_source"] = None



    # async def _emit(
    #     self,
    #     *,
    #     event: HL_EVENT,
    #     method: METHOD,
    #     symbol: str,
    #     side: str,
    #     partially: bool,
    #     payload: Dict[str, Any],
    #     sig_type: Literal["copy", "log"],
    #     ev_raw: Optional[SignalEvent],
    # ):
    #     exec_ts = int(time.time() * 1000)
    #     raw_ts = ev_raw.ts if ev_raw else None

    #     payload = dict(payload)
    #     payload["exec_ts"] = exec_ts
    #     payload["latency_ms"] = exec_ts - raw_ts if raw_ts else None

    #     self._pending.append(
    #         MasterEvent(
    #             event=event,
    #             method=method,
    #             symbol=symbol,
    #             side=side,
    #             partially=partially,
    #             payload=payload,
    #             sig_type=sig_type,
    #             # raw=ev_raw,
    #             ts=exec_ts,
    #         )
    #     )



# OPEN_TTL = 0.010     # 20ms — стабилизация открытия позиции
# DEAL_TTL = 0.040     # 40ms — стабилизация partial 


    # def _remember_order(
    #     self,
    #     st: Dict[str, Any],
    #     master_id: Optional[str],
    #     copy_id: Optional[str]
    # ):
    #     if not master_id or not copy_id:
    #         return
    #     st["orders"][master_id] = copy_id

    # def _remember_plan(
    #     self,
    #     st: Dict[str, Any],
    #     master_plan_id: Optional[str],
    #     copy_plan_id: Optional[str]
    # ):
    #     if not master_plan_id or not copy_plan_id:
    #         return
    #     st["plans"][master_plan_id] = copy_plan_id



        # # отменяем на копи
        # await cli.cancel_order_by_id(copy_oid)

        # # очищаем маппинг
        # st["orders"].pop(master_oid, None)



# COPY_RUNTIME_STATE = {
#     "id": None,

#     # ===== NETWORK =====
#     "connector": None,          # NetworkManager instance
#     "mc_client": None,
#     "network_ready": False,

#     # ===== ERRORS =====
#     "last_error": None,
#     "last_error_ts": None,

#     # ===== ORDERS / POSITIONS =====
#     "position_vars": {},       # symbol → {side, size, price}
#     "closing": False,          # 

#     # ===== MASTER MIRROR FLAG =====
#     "last_master_flag": {},     # (symbol, side) → {flag, ts, raw}

#     # ===== ACTIVITY =====
#     "last_action_ts": None,
# }




    

# class PosVarSetup:

#     PUBLIC_PV_KEYS = (
#         "in_position", "qty", "qty_prev",
#         "entry_price", "last_price",
#         "last_update", "leverage",
#         "exec_state", "attached_tp", "attached_sl"
#     )

#     @staticmethod
#     def pos_vars_root_template() -> Dict[str, Any]:
#         return {
#             # ==================================================
#             # POSITION STATE (FACTUAL)
#             # ==================================================
#             "in_position": False,

#             # quantities
#             "qty": 0.0,              # текущий holdVol
#             "qty_prev": 0.0,         # предыдущее значение (опционально)

#             # prices
#             "entry_price": None,
#             "last_price": None,

#             # timestamps
#             "last_update": 0,

#             # meta
#             "leverage": None,

#             # ==================================================
#             # EXECUTION STATE (ACTIVE ENTITIES)
#             # ==================================================
#             "exec_state": {
#                 "limit_open": False,
#                 "limit_close": False,
#                 "tp": False,
#                 "sl": False,
#             },

#             # ==================================================
#             # MASTER PAYLOAD INTERNAL STATE
#             # ==================================================
#             "_last_exec_source": None,    # market | limit | trigger | None

#             # attached OCO (from stop_attached)
#             "attached_tp": None,
#             "attached_sl": None,
#         }


# # DESTRIBUTOR.helpers.py

# from __future__ import annotations
# import asyncio
# import copy
# import hashlib
# from typing import *

# from a_config import SESSION_TTL, DEDUP_TTL_MS, ADMIN_CHAT_ID
# from b_context import MainContext, COPY_RUNTIME_STATE
# from c_log import ErrorHandler
# from c_utils import now, Utils
# from b_network import NetworkManager

# from API.MX.client import MexcClient
# from MASTER.master_payload import MasterEvent
# from pos.pos_temp import PosVarTemplate


# # ============================================================
# # POSITION ACCESS
# # ============================================================

# def get_master_pos(mev: MasterEvent) -> dict:
#     return mev.pos_progress or {}


# def get_copy_pos(rt: dict, symbol: str, side: str) -> dict:
#     pv_root = rt.setdefault("position_vars", {})
#     sym = pv_root.setdefault(symbol, {})

#     if side not in sym:
#         sym[side] = PosVarTemplate.base_template()

#     return sym[side]

# # ============================================================
# # ORDER RESULT HANDLING
# # ============================================================

# # def notify_result(cid: int, res: dict):
# #     print(f"[COPY {cid}] RESULT → {res}")


# def format_master_log_event(cid: int, mev: MasterEvent) -> str:
#     """
#     Форматирует sig_type=log (информационные события от мастера)
#     """

#     p = mev.payload or {}

#     lines = [
#         f"🧾 <b>COPY #{cid}</b>",
#         f"• {mev.symbol} {mev.side}",
#         f"• event: <b>{mev.event.upper()}</b>",
#         f"• method: {mev.method}",
#     ]

#     if mev.partially:
#         lines.append("• partial execution")

#     if mev.closed:
#         lines.append("• position <b>CLOSED</b>")

#     if "price" in p:
#         lines.append(f"• price: {Utils.to_human_digit(p.get('price'))}")

#     if "qty" in p:
#         lines.append(f"• qty: {Utils.to_human_digit(p.get('qty'))}")

#     if "latency_ms" in p:
#         lines.append(f"• latency: {p.get('latency_ms')} ms")

#     return "\n".join(lines)

# def format_order_result(cid: int, res: dict) -> str:
#     if res.get("success"):
#         return (
#             f"✅ <b>COPY #{cid}</b>\n"
#             f"Order executed successfully\n"
#             f"Order ID: {res.get('order_id') or res.get('order_ids')}"
#         )

#     return (
#         f"❌ <b>COPY #{cid}</b>\n"
#         f"Order failed\n"
#         f"Reason: {res.get('reason') or 'unknown'}"
#     )

# async def notify_result(mc: MainContext, cid: int, res: dict):
#     text = format_order_result(cid, res)
#     await notify_copy_event(mc, cid, text)

#     if mc.debug:
#         print(f"[COPY {cid}] RESULT → {res}")


# # ============================================================
# # NOTIFICATION PIPE
# # ============================================================

# async def notify_copy_event(
#     mc: MainContext,
#     cid: int,
#     text: str,
# ):
#     chat_id = mc.copy_configs.get(cid, {}).get("tg_chat_id")
#     if not chat_id:
#         return

#     notifier = mc.tg_notifier
#     await notifier.send(chat_id, text)

# # ==== 

# async def on_order_result(
#     mc: MainContext,
#     cid: int,
#     res: dict,
#     symbol: str | None = None,
#     side: str | None = None,
#     delta_qty: float | None = None,
# ):
#     rt = mc.copy_runtime_states.get(cid)
#     if not rt:
#         return

#     rt["last_action_ts"] = now()

#     if res.get("success"):
#         if symbol and side and delta_qty is not None:
#             pv = get_copy_pos(rt, symbol, side)
#             pv["qty"] = max(0.0, (pv.get("qty") or 0.0) + delta_qty)
#             pv["in_position"] = pv["qty"] > 0

#             if delta_qty > 0 and not pv.get("entry_ts"):
#                 pv["entry_ts"] = now()

#     else:
#         rt["last_error"] = res.get("reason")
#         rt["last_error_ts"] = now()

#     await notify_result(mc, cid, res)


# async def force_close_copy(
#     mc: MainContext,
#     runtime: "Runtime",
#     cid: int,
# ):
#     rt = await runtime.ensure_runtime(cid)

#     if rt.get("cmd_closing"):
#         return

#     client: MexcClient = rt.get("mc_client")
#     if not client:
#         return

#     try:
#         rt["cmd_closing"] = True
#         now_ts = now()

#         summaries: list[str] = []

#         # ======================================================
#         # 1️⃣ Закрываем все позиции
#         # ======================================================
#         for symbol, sides in rt.get("position_vars", {}).items():
#             for side, pv in sides.items():
#                 if not pv.get("in_position"):
#                     continue

#                 qty = pv.get("qty")
#                 if not qty:
#                     continue

#                 entry_ts = pv.get("entry_ts")
#                 entry_price = pv.get("entry_price")
#                 exit_ts = now_ts

#                 # ---- MARKET CLOSE ----
#                 res = await client.make_order(
#                     symbol=symbol,
#                     contract=qty,
#                     side="SELL",
#                     position_side=side,
#                     market_type="MARKET",
#                     reduce_only=True,
#                     debug=True,
#                 )

#                 await on_order_result(
#                     mc=mc,
#                     cid=cid,
#                     res=res,
#                     symbol=symbol,
#                     side=side,
#                     delta_qty=-qty,
#                 )

#                 # ---- PnL FROM EXCHANGE ----
#                 pnl = await client.get_realized_pnl(
#                     symbol=symbol,
#                     start_time=entry_ts,
#                     end_time=exit_ts,
#                     direction=1 if side == "LONG" else 2,
#                 )

#                 duration_sec = (
#                     (exit_ts - entry_ts) // 1000 if entry_ts else 0
#                 )

#                 summary = format_close_summary(
#                     cid=cid,
#                     symbol=symbol,
#                     side=side,
#                     entry_price=entry_price,
#                     exit_price = pv.get("last_price") or entry_price,
#                     duration_sec=duration_sec,
#                     pnl_usdt=pnl.get("pnl_usdt"),
#                     pnl_pct=pnl.get("pnl_pct"),
#                 )

#                 summaries.append(summary)

#                 # ---- CLEANUP PV ----
#                 pv["entry_ts"] = None
#                 pv["entry_price"] = None
#                 pv["last_price"] = None
#                 pv["qty"] = 0.0
#                 pv["in_position"] = False

#         # ======================================================
#         # 2️⃣ Отменяем все ордера
#         # ======================================================
#         for symbol in rt.get("position_vars", {}).keys():
#             try:
#                 await client.cancel_all_orders(symbol=symbol)
#             except Exception as e:
#                 if mc.debug:
#                     print(f"[FORCE_CLOSE:{cid}] cancel error {symbol}: {e}")

#         # ======================================================
#         # 3️⃣ ОТПРАВКА SUMMARY В TG (BATCH READY)
#         # ======================================================
#         await mc.tg_notifier.send_block(
#             chat_id=ADMIN_CHAT_ID,
#             texts=summaries,
#         )


#     finally:
#         rt["cmd_closing"] = False

# # ============================================================
# # DEDUP
# # ============================================================

# def event_fingerprint(mev: MasterEvent) -> str:
#     p = mev.payload or {}

#     key = (
#         mev.symbol,
#         mev.side,
#         mev.event,
#         mev.method,
#         p.get("order_id"),
#         p.get("qty_delta"),
#         p.get("qty_after"),
#         p.get("trigger_price"),
#         p.get("price"),
#     )

#     return hashlib.sha1(repr(key).encode()).hexdigest()


# def cleanup_dedup(rt: dict, ttl_ms: int = DEDUP_TTL_MS):
#     now_ts = now()
#     dedup = rt.get("dedup", {})

#     for k, ts in list(dedup.items()):
#         if now_ts - ts > ttl_ms * 2:
#             dedup.pop(k, None)


# def is_duplicate_event(rt: dict, mev: MasterEvent) -> bool:
#     fp = event_fingerprint(mev)
#     now_ts = now()

#     dedup = rt.setdefault("dedup", {})

#     last_ts = dedup.get(fp)
#     if last_ts and now_ts - last_ts < DEDUP_TTL_MS:
#         return True

#     dedup[fp] = now_ts

#     # мягкая чистка
#     if len(dedup) > 100:
#         cleanup_dedup(rt)

#     return False


# # ============================================================
# # CLIENT ACCESS
# # ============================================================

# async def get_mx_client(runtime: "Runtime", copy_id: int) -> Optional[MexcClient]:
#     rt = await runtime.ensure_runtime(copy_id)
#     if rt.get("closing"):
#         return None
#     return rt.get("mc_client")


# # ============================================================
# # SUMMARY HELPERS
# # ============================================================

# def _format_duration(sec: int) -> str:
#     if sec < 60:
#         return f"{sec}s"
#     if sec < 3600:
#         m, s = divmod(sec, 60)
#         return f"{m}m {s}s"
#     h, rem = divmod(sec, 3600)
#     m, _ = divmod(rem, 60)
#     return f"{h}h {m}m"


# def format_close_summary(
#     cid: int,
#     symbol: str,
#     side: str,
#     entry_price: float | None,
#     exit_price: float | None,
#     duration_sec: int,
#     pnl_usdt: float | None,
#     pnl_pct: float | None,
# ) -> str:
#     sign = "+" if pnl_usdt and pnl_usdt > 0 else ""
#     pnl_line = (
#         f"<b>{sign}{Utils.to_human_digit(pnl_usdt)}$</b>"
#         if pnl_usdt is not None
#         else "N/A"
#     )

#     pct_line = (
#         f"({sign}{Utils.to_human_digit(pnl_pct)}%)"
#         if pnl_pct is not None
#         else ""
#     )

#     return (
#         f"📊 <b>COPY #{cid} — POSITION CLOSED</b>\n\n"
#         f"{symbol} — {side}\n"
#         f"Вход: {Utils.to_human_digit(entry_price)}\n"
#         f"Выход: {Utils.to_human_digit(exit_price)}\n\n"
#         f"PNL: {pnl_line} {pct_line}\n"
#         f"Длительность: {_format_duration(duration_sec)}"
#     )

# # ============================================================
# # POSITION ACCESS
# # ============================================================

# def get_copy_pos(rt: dict, symbol: str, side: str) -> dict:
#     pv_root = rt.setdefault("position_vars", {})
#     sym = pv_root.setdefault(symbol, {})
#     if side not in sym:
#         sym[side] = PosVarTemplate.base_template()
#     return sym[side]


# # ============================================================
# # FORCE CLOSE (RETURNS DATA)
# # ============================================================

# async def force_close_copy(
#     mc: MainContext,
#     runtime: "Runtime",
#     cid: int,
# ) -> list[dict]:
#     """
#     Закрывает ВСЕ позиции копи-аккаунта.
#     Возвращает список результатов для GENERAL summary.
#     """
#     rt = await runtime.ensure_runtime(cid)
#     if rt.get("cmd_closing"):
#         return []

#     client: MexcClient = rt.get("mc_client")
#     if not client:
#         return []

#     results: list[dict] = []
#     now_ts = now()

#     try:
#         rt["cmd_closing"] = True

#         for symbol, sides in rt.get("position_vars", {}).items():
#             for side, pv in sides.items():
#                 if not pv.get("in_position"):
#                     continue

#                 qty = pv.get("qty") or 0.0
#                 if qty <= 0:
#                     continue

#                 entry_ts = pv.get("entry_ts")
#                 entry_price = pv.get("entry_price")

#                 # ---- MARKET CLOSE ----
#                 res = await client.make_order(
#                     symbol=symbol,
#                     contract=qty,
#                     side="SELL",
#                     position_side=side,
#                     market_type="MARKET",
#                     reduce_only=True,
#                     debug=True,
#                 )

#                 # ---- PNL ----
#                 pnl = await client.get_realized_pnl(
#                     symbol=symbol,
#                     start_time=entry_ts,
#                     end_time=now_ts,
#                     direction=1 if side == "LONG" else 2,
#                 )

#                 duration_sec = (
#                     (now_ts - entry_ts) // 1000 if entry_ts else 0
#                 )

#                 results.append({
#                     "cid": cid,
#                     "symbol": symbol,
#                     "side": side,
#                     "pnl_usdt": pnl.get("pnl_usdt"),
#                     "pnl_pct": pnl.get("pnl_pct"),
#                     "duration_sec": duration_sec,
#                 })

#                 # ---- CLEANUP ----
#                 pv.update({
#                     "qty": 0.0,
#                     "in_position": False,
#                     "entry_ts": None,
#                     "entry_price": None,
#                     "last_price": None,
#                 })

#         # ---- CANCEL ORDERS ----
#         for symbol in rt.get("position_vars", {}).keys():
#             try:
#                 await client.cancel_all_orders(symbol=symbol)
#             except Exception:
#                 pass

#         return results

#     finally:
#         rt["cmd_closing"] = False


# # ============================================================
# # GENERAL SUMMARY FORMAT
# # ============================================================

# def format_general_summary(rows: list[dict]) -> str:
#     total_usdt = 0.0
#     total_pct = 0.0
#     count = 0

#     for r in rows:
#         if r["pnl_usdt"] is None:
#             continue
#         total_usdt += r["pnl_usdt"]
#         total_pct += r["pnl_pct"] or 0.0
#         count += 1

#     sign = "+" if total_usdt > 0 else ""

#     return (
#         f"📊 <b>GENERAL SUMMARY</b>\n\n"
#         f"Закрыто позиций: {count}\n"
#         f"PNL: <b>{sign}{Utils.to_human_digit(total_usdt)}$</b>\n"
#         f"PNL %: {sign}{Utils.to_human_digit(total_pct)}%"
#     )
