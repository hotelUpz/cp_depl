
# def _order_side_match(order_side: OrderSide, pos_side: str) -> bool:
#     if pos_side == "LONG":
#         return order_side in (OrderSide.OpenLong, OrderSide.CloseLong)
#     if pos_side == "SHORT":
#         return order_side in (OrderSide.OpenShort, OrderSide.CloseShort)
#     return False


    # async def cancel_all_orders_by_side(
    #     self,
    #     symbol: str,
    #     pos_side: Literal["LONG", "SHORT"],
    #     debug: bool = True,
    # ) -> dict:
    #     """
    #     Универсальная отмена ВСЕХ ордеров по symbol + стороне (hedge-safe).

    #     Отменяет:
    #     • обычные лимитные ордера
    #     • trigger orders (TP / SL)
    #     • stop-limit orders

    #     Работает корректно в hedge mode.
    #     """

    #     results = {
    #         "symbol": symbol,
    #         "side": pos_side,
    #         "limit_orders": [],
    #         "trigger_orders": [],
    #         "stop_limit_orders": [],
    #         "errors": [],
    #     }

    #     # --------------------------------------------------
    #     # 1️⃣ LIMIT / MARKET ORDERS
    #     # --------------------------------------------------
    #     try:
    #         resp = await self.api.get_current_pending_orders(symbol=symbol, session=self.session)
    #         if resp.success and resp.data:
    #             limit_ids = [
    #                 o.orderId for o in resp.data
    #                 if _order_side_match(o.side, pos_side)
    #             ]

    #             if limit_ids:
    #                 r = await self.api.cancel_orders(limit_ids, session=self.session)
    #                 results["limit_orders"] = limit_ids
    #                 if not r.success:
    #                     results["errors"].append(("limit", r.message))
    #     except Exception as e:
    #         results["errors"].append(("limit", str(e)))

    #     # --------------------------------------------------
    #     # 2️⃣ TRIGGER ORDERS (planorder)
    #     # --------------------------------------------------
    #     try:
    #         resp = await self.api.get_trigger_orders(symbol=symbol, session=self.session)
    #         if resp.success and resp.data:
    #             trigger_payload = [
    #                 {"id": o.id}
    #                 for o in resp.data
    #                 if _order_side_match(o.side, pos_side)
    #             ]

    #             if trigger_payload:
    #                 r = await self.api.cancel_trigger_orders(trigger_payload, session=self.session)
    #                 results["trigger_orders"] = [o["id"] for o in trigger_payload]
    #                 if not r.success:
    #                     results["errors"].append(("trigger", r.message))
    #     except Exception as e:
    #         results["errors"].append(("trigger", str(e)))

    #     # --------------------------------------------------
    #     # 3️⃣ STOP-LIMIT ORDERS
    #     # --------------------------------------------------
    #     try:
    #         resp = await self.api.get_stop_limit_orders(symbol=symbol, session=self.session)
    #         if resp.success and resp.data:
    #             stop_ids = [
    #                 o.id for o in resp.data
    #                 if (
    #                     (pos_side == "LONG" and o.positionType == PositionType.Long) or
    #                     (pos_side == "SHORT" and o.positionType == PositionType.Short)
    #                 )
    #             ]

    #             for stop_id in stop_ids:
    #                 r = await self.api.cancel_stop_limit_order(stop_id, session=self.session)
    #                 results["stop_limit_orders"].append(stop_id)
    #                 if not r.success:
    #                     results["errors"].append(("stop_limit", r.message))
    #     except Exception as e:
    #         results["errors"].append(("stop_limit", str(e)))

    #     # --------------------------------------------------
    #     # FINAL
    #     # --------------------------------------------------
    #     success = not results["errors"]

    #     return {
    #         "success": success,
    #         "symbol": symbol,
    #         "side": pos_side,
    #         "details": results,
    #     }



# ======================================================================
# ORDER RESULT STATE UPDATE (DOMAIN, NO TG)
# ======================================================================

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

#     if res.get("success"):
#         if symbol and side and delta_qty is not None:
#             pv = FetchState.get_copy_pos(rt, symbol, side)
#             pv["qty"] = max(0.0, (pv.get("qty") or 0.0) + delta_qty)
#             pv["in_position"] = pv["qty"] > 0

#             if delta_qty > 0 and not pv.get("entry_ts"):
#                 pv["entry_ts"] = now()
#     else:
#         rt["last_error"] = res.get("reason")
#         rt["last_error_ts"] = now()





    # async def make_trigger_order(
    #     self,
    #     symbol: str,
    #     position_side: str,
    #     contract: float,
    #     price: Optional[str],
    #     leverage: int,
    #     open_type: int,
    #     close_order_type: str,  # "tp" | "sl"
    #     order_type: int = 2,
    #     debug: bool = False,
    # ) -> dict:

    #     # -------- side
    #     if position_side.upper() == "LONG":
    #         side = OrderSide.CloseLong
    #     elif position_side.upper() == "SHORT":
    #         side = OrderSide.CloseShort
    #     else:
    #         return OrderValidator.validate_and_log(None, "TRIGGER_ORDER", debug)

    #     # -------- trigger type
    #     if close_order_type == "tp":
    #         trigger_type = (
    #             TriggerType.GreaterThanOrEqual
    #             if side == OrderSide.CloseLong
    #             else TriggerType.LessThanOrEqual
    #         )
    #     elif close_order_type == "sl":
    #         trigger_type = (
    #             TriggerType.LessThanOrEqual
    #             if side == OrderSide.CloseLong
    #             else TriggerType.GreaterThanOrEqual
    #         )
    #     else:
    #         return OrderValidator.validate_and_log(None, "TRIGGER_ORDER", debug)

    #     # -------- open type
    #     if open_type == 1:
    #         openType = OpenType.Isolated
    #     elif open_type == 2:
    #         openType = OpenType.Cross
    #     else:
    #         return OrderValidator.validate_and_log(None, "TRIGGER_ORDER", debug)

    #     if openType == OpenType.Isolated and not leverage:
    #         return OrderValidator.validate_and_log(None, "TRIGGER_ORDER", debug)

    #     if order_type == 1:
    #         order_type = OrderType.PriceLimited
    #     else:
    #         order_type = OrderType.MarketOrder

    #     # -------- API call
    #     trigger_request = TriggerOrderRequest(
    #         symbol=symbol,
    #         side=side,
    #         vol=contract,
    #         leverage=leverage,
    #         openType=openType,
    #         orderType=order_type,
    #         executeCycle=ExecuteCycle.UntilCanceled,
    #         trend=TriggerPriceType.LatestPrice,
    #         triggerPrice=price,
    #         triggerType=trigger_type,
    #     )

    #     result = await self.api.create_trigger_order(
    #         trigger_order_request=trigger_request,
    #         session=self.session,
    #     )

    #     return OrderValidator.validate_and_log(
    #         result=result,
    #         debug_label="TRIGGER_ORDER",
    #         debug=debug,
    #     )


# # DESTRIBUTOR/copy_.py

# from __future__ import annotations

# import asyncio
# from typing import *

# from b_context import MainContext
# from c_log import UnifiedLogger
# from c_utils import now

# from MASTER.master_payload import MasterEvent, MasterPayload

# from .helpers import DedupUtils, FetchState
# from .pv_fsm import PosMonitorFSM
# from .state_ import CopyOrderIntentFactory, ResetPVState

# if TYPE_CHECKING:
#     from .state_ import CopyState, CopyOrderIntent

# from TG.tg_notifier import FormatUILogs


# class CopyDestrib:
#     """
#     CopyDestrib — принимает HIGH-LEVEL MasterEvent и
#     рассылает их всем активным copy-аккаунтам.
#     """

#     def __init__(
#         self,
#         mc: MainContext,
#         logger: UnifiedLogger,
#         copy_state: CopyState,
#         stop_flag: Callable[[], bool],
#     ):
#         self.mc = mc
#         self.logger = logger
#         self.copy_state = copy_state
#         self.stop_flag = stop_flag

#         self.payload: MasterPayload | None = None

#         self._stop_signal_loop = True
#         self._stop_tracker = True

#         self.intent_factory = CopyOrderIntentFactory()
#         self.reset_pv_state = ResetPVState(self.mc, self.logger)

#         # локальные FSM-мониторы (НЕ в mc)
#         self.pos_monitors: Dict[int, PosMonitorFSM] = {}

#     # ------------------------------------------------------------------
#     # PAYLOAD
#     # ------------------------------------------------------------------

#     def attach_payload(self, payload: MasterPayload):
#         self.payload = payload
#         self.logger.info("CopyDestrib: payload attached")

#     # ------------------------------------------------------------------
#     # STOP API
#     # ------------------------------------------------------------------

#     def stop_signal_loop(self):
#         self.logger.info("CopyDestrib: stop_signal_loop() called")
#         self._stop_signal_loop = True

#     def stop_tracker(self):
#         self.logger.info("CopyDestrib: stop_tracker() called")
#         self._stop_tracker = True
#         if self.payload:
#             self.payload.stop()

#         # финальный сброс логов
#         if self.mc.log_events:
#             self.mc.log_events.clear()

#     # ------------------------------------------------------------------
#     # COPY EVENT HANDLER
#     # ------------------------------------------------------------------

#     async def _handle_copy_event(
#         self,
#         cid: int,
#         cfg: dict,
#         rt: Dict,
#         mev: MasterEvent,
#     ) -> None:

#         if mev.sig_type not in ("copy", "log"):
#             return

#         # ---------------- CLIENT ----------------
#         client = await FetchState.get_mx_client(self.copy_state, cid)
#         if not client:
#             self.logger.warning(f"COPY[{cid}] no client")
#             return

#         # ---------------- FSM ----------------
#         if cid not in self.pos_monitors:
#             self.pos_monitors[cid] = PosMonitorFSM(
#                 rt["position_vars"],
#                 client.fetch_positions,
#             )

#         # ---------------- LOG ONLY ----------------
#         if mev.sig_type == "log":
#             self.mc.log_events.append((cid, mev))
#             return

#         # ---------------- DEDUP ----------------
#         if not mev.closed and DedupUtils.is_duplicate_event(rt, mev):
#             return

#         # ---------------- CANCEL (TODO: IDs) ----------------
#         if mev.event == "canceled":
#             # TODO: корректная отмена по сохранённым order_id
#             return

#         # ---------------- BUILD INTENT ----------------
#         copy_pv = FetchState.get_copy_pos(rt, mev.symbol, mev.pos_side)

#         master_root = self.mc.pos_vars_root.get("position_vars", {})
#         symbol_spec = master_root.get(mev.symbol, {}).get("spec", {})

#         intent: CopyOrderIntent | None = self.intent_factory.build(
#             cfg=cfg,
#             mev=mev,
#             copy_pv=copy_pv,
#             spec=symbol_spec,
#         )
#         if not intent:
#             return

#         if intent.delay_ms > 0:
#             await asyncio.sleep(intent.delay_ms / 1000)

#         # ---------------- CLOSED (SIGNAL) ----------------
#         if mev.closed:
#             if rt.get("cmd_closing"):
#                 return

#             self.logger.info(f"COPY[{cid}] SIGNAL CLOSE {intent.symbol} {intent.position_side}")

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

#             if not res or not res.get("success"):
#                 rt["last_error"] = res.get("reason") if res else "UNKNOWN ERROR"
#                 rt["last_error_ts"] = now()

#             return

#         # ---------------- EXECUTE ----------------
#         if intent.method in ("MARKET", "LIMIT"):

#             if intent.method == "MARKET" and rt.get("cmd_closing"):
#                 return

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

#             if not res or not res.get("success"):
#                 rt["last_error"] = res.get("reason") if res else "UNKNOWN ERROR"
#                 rt["last_error_ts"] = now()

#             # TODO: сохранить order_id в orders_vars
#             return

#         if intent.method == "TRIGGER":
#             close_type = "tp" if intent.side == "BUY" else "sl"

#             res = await client.make_trigger_order(
#                 symbol=intent.symbol,
#                 position_side=intent.position_side,
#                 contract=intent.contracts,
#                 price=intent.trigger_price,
#                 leverage=intent.leverage,
#                 open_type=intent.open_type,
#                 close_order_type=close_type,
#                 order_type=mev.payload.get("trigger_exec", 2),
#                 debug=True,
#             )

#             if not res or not res.get("success"):
#                 rt["last_error"] = res.get("reason") if res else "UNKNOWN ERROR"
#                 rt["last_error_ts"] = now()

#             # TODO: сохранить trigger order_id
#             return

#     # ------------------------------------------------------------------
#     # BROADCAST
#     # ------------------------------------------------------------------

#     async def _broadcast_to_copies(self, mev: MasterEvent) -> None:

#         tasks: List[asyncio.Task] = []

#         for cid, cfg in self.mc.copy_configs.items():
#             if cid == 0 or not cfg.get("enabled"):
#                 continue

#             rt = await self.copy_state.ensure_copy_state(cid)
#             if not rt or rt.get("cmd_closing"):
#                 continue

#             tasks.append(
#                 asyncio.create_task(
#                     self._handle_copy_event(cid, cfg, rt, mev)
#                 )
#             )

#         if tasks:
#             await asyncio.gather(*tasks, return_exceptions=True)

#         # -------- FSM SYNC --------
#         if not self.pos_monitors:
#             return

#         refresh_tasks: List[asyncio.Task] = []
#         ids: List[int] = []

#         for cid, monitor in self.pos_monitors.items():
#             refresh_tasks.append(asyncio.create_task(monitor.refresh()))
#             ids.append(cid)

#         if refresh_tasks:
#             await asyncio.gather(*refresh_tasks, return_exceptions=True)

#         self.pos_monitors.clear()

#         await self.reset_pv_state.finalize_positions(ids=ids)

#     # ------------------------------------------------------------------
#     # MAIN LOOP
#     # ------------------------------------------------------------------

#     async def signal_loop(self):

#         if not self.payload:
#             self.logger.error("CopyDestrib: payload not attached")
#             return

#         self.logger.info("CopyDestrib: signal_loop STARTED")

#         self._stop_signal_loop = False
#         self._stop_tracker = False

#         # ожидание старта мастера
#         while not self.stop_flag() and not self._stop_signal_loop:
#             master_rt = self.mc.copy_configs.get(0, {}).get("cmd_state", {})
#             if master_rt.get("trading_enabled") and not master_rt.get("stop_flag"):
#                 break
#             await asyncio.sleep(0.1)

#         if self._stop_signal_loop:
#             self.logger.warning("CopyDestrib: aborted before start")
#             return

#         self.logger.info("CopyDestrib: READY for HL events")

#         while not self.stop_flag() and not self._stop_signal_loop:
#             try:
#                 mev: MasterEvent = await self.payload.out_queue.get()
#             except asyncio.CancelledError:
#                 break

#             if self._stop_signal_loop or self._stop_tracker or self.stop_flag():
#                 break

#             await self._broadcast_to_copies(mev)

#             if self.mc.log_events:
#                 texts = FormatUILogs.flush_log_events(self.mc.log_events)
#                 if texts:
#                     await self.mc.tg_notifier.send_block(texts)

#         self.logger.info("CopyDestrib: signal_loop FINISHED")










# # DESTRIBUTOR/copy_.py

# from __future__ import annotations

# import asyncio
# from typing import *

# from b_context import MainContext
# from c_log import UnifiedLogger
# from c_utils import now

# from MASTER.master_payload import MasterEvent, MasterPayload
# from .helpers import DedupUtils, FetchState
# from .pv_fsm import PosMonitorFSM
# from .state_ import CopyOrderIntentFactory, ResetPVState

# from TG.tg_notifier import FormatUILogs

# if TYPE_CHECKING:
#     from .state_ import CopyState, CopyOrderIntent


# class CopyDestrib:
#     """
#     CopyDestrib — принимает HIGH-LEVEL MasterEvent и
#     рассылает их всем активным copy-аккаунтам.
#     """

#     def __init__(
#         self,
#         mc: MainContext,
#         logger: UnifiedLogger,
#         copy_state: CopyState,
#         stop_flag: Callable[[], bool],
#     ):
#         self.mc = mc
#         self.logger = logger
#         self.copy_state = copy_state
#         self.stop_flag = stop_flag

#         self.payload: MasterPayload | None = None

#         self._stop_signal_loop = True
#         self._stop_tracker = True

#         self.intent_factory = CopyOrderIntentFactory()
#         self.reset_pv_state = ResetPVState(self.mc, self.logger)

#         # локальные FSM-мониторы (НЕ в mc)
#         self.pos_monitors: Dict[int, PosMonitorFSM] = {}

#     # --------------------------------------------------
#     def attach_payload(self, payload: MasterPayload):
#         self.payload = payload
#         self.logger.info("CopyDestrib: payload attached")

#     # ------------------------------------------------------------------
#     # STOP API
#     # ------------------------------------------------------------------

#     def stop_signal_loop(self):
#         self.logger.info("CopyDestrib: stop_signal_loop() called")
#         self._stop_signal_loop = True

#     def stop_tracker(self):
#         self.logger.info("CopyDestrib: stop_tracker() called")
#         self._stop_tracker = True
#         if self.payload:
#             self.payload.stop()

#         # финальный сброс логов
#         if self.mc.log_events:
#             self.mc.log_events.clear()

#     # --------------------------------------------------
#     async def _handle_copy_event(
#         self,
#         cid: int,
#         cfg: dict,
#         rt: dict,
#         mev: MasterEvent,
#     ):
#         # --------------------------------------------------
#         if mev.sig_type not in ("copy", "log"):
#             return

#         client = await FetchState.get_mx_client(self.copy_state, cid)
#         if not client:
#             return

#         # --------------------------------------------------
#         # LOG ONLY
#         # --------------------------------------------------
#         if mev.sig_type == "log":
#             self.mc.log_events.append((cid, mev))
#             return

#         # --------------------------------------------------
#         # DEDUP (НЕ для закрытий)
#         # --------------------------------------------------
#         if not mev.closed and DedupUtils.is_duplicate_event(rt, mev):
#             return

#         # --------------------------------------------------
#         # POSITION SNAPSHOT
#         # --------------------------------------------------
#         if cid not in self.pos_monitors:
#             self.pos_monitors[cid] = PosMonitorFSM(
#                 rt["position_vars"],
#                 client.fetch_positions,
#             )
#         await self.pos_monitors[cid].refresh()

#         # --------------------------------------------------
#         # BUILD INTENT
#         # --------------------------------------------------
#         copy_pv = FetchState.get_copy_pos(rt, mev.symbol, mev.pos_side)

#         spec = (
#             self.mc.pos_vars_root
#             .get("position_vars", {})
#             .get(mev.symbol, {})
#             .get("spec", {})
#         )

#         intent: CopyOrderIntent | None = self.intent_factory.build(
#             cfg=cfg,
#             mev=mev,
#             copy_pv=copy_pv,
#             spec=spec,
#         )
#         if not intent:
#             return

#         if intent.delay_ms:
#             await asyncio.sleep(intent.delay_ms / 1000)

#         # --------------------------------------------------
#         # ORDERS CACHE INIT
#         # --------------------------------------------------
#         ov_root = rt.setdefault("orders_vars", {})
#         sym_root = ov_root.setdefault(intent.symbol, {})
#         side_root = sym_root.setdefault(intent.position_side, {})
#         limit_root = side_root.setdefault("limit", {})
#         trigger_root = side_root.setdefault("trigger", {})

#         master_oid = mev.payload.get("order_id")

#         # --------------------------------------------------
#         # FORCE CLOSE (CLOSED FLAG)
#         # --------------------------------------------------
#         if mev.closed:
#             if rt.get("cmd_closing"):
#                 return

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

#             if not res or not res.get("success"):
#                 rt["last_error"] = res.get("reason") if res else "UNKNOWN"
#                 rt["last_error_ts"] = now()

#             return

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

#             if not res or not res.get("success"):
#                 rt["last_error"] = res.get("reason") if res else "UNKNOWN"
#                 rt["last_error_ts"] = now()
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

#             if not res or not res.get("success"):
#                 rt["last_error"] = res.get("reason") if res else "UNKNOWN"
#                 rt["last_error_ts"] = now()
#                 return

#             if master_oid:
#                 trigger_root[master_oid] = {
#                     "copy_order_id": res.get("order_id"),
#                     "trigger_price": intent.trigger_price,
#                     "qty": intent.contracts,
#                     "status": "OPEN",
#                 }

#             return

#     # --------------------------------------------------
#     async def _broadcast_to_copies(self, mev: MasterEvent):
#         tasks = []

#         for cid, cfg in self.mc.copy_configs.items():
#             if cid == 0 or not cfg.get("enabled"):
#                 continue

#             rt = await self.copy_state.ensure_copy_state(cid)
#             if not rt or rt.get("cmd_closing"):
#                 continue

#             tasks.append(
#                 asyncio.create_task(
#                     self._handle_copy_event(cid, cfg, rt, mev)
#                 )
#             )

#         if tasks:
#             await asyncio.gather(*tasks, return_exceptions=True)

#             if self.pos_monitors:
#                 ids = list(self.pos_monitors.keys())
#                 await asyncio.gather(
#                     *[m.refresh() for m in self.pos_monitors.values()],
#                     return_exceptions=True,
#                 )
#                 self.pos_monitors.clear()
#                 await self.reset_pv_state.finalize_positions(ids)

#     # ------------------------------------------------------------------
#     # MAIN LOOP
#     # ------------------------------------------------------------------

#     async def signal_loop(self):

#         if not self.payload:
#             self.logger.error("CopyDestrib: payload not attached")
#             return

#         self.logger.info("CopyDestrib: signal_loop STARTED")

#         self._stop_signal_loop = False
#         self._stop_tracker = False

#         # ожидание старта мастера
#         while not self.stop_flag() and not self._stop_signal_loop:
#             master_rt = self.mc.copy_configs.get(0, {}).get("cmd_state", {})
#             if master_rt.get("trading_enabled") and not master_rt.get("stop_flag"):
#                 break
#             await asyncio.sleep(0.1)

#         if self._stop_signal_loop:
#             self.logger.warning("CopyDestrib: aborted before start")
#             return

#         self.logger.info("CopyDestrib: READY for HL events")

#         while not self.stop_flag() and not self._stop_signal_loop:
#             try:
#                 mev: MasterEvent = await self.payload.out_queue.get()
#             except asyncio.CancelledError:
#                 break

#             if self._stop_signal_loop or self._stop_tracker or self.stop_flag():
#                 break

#             await self._broadcast_to_copies(mev)

#             if self.mc.log_events:
#                 texts = FormatUILogs.flush_log_events(self.mc.log_events)
#                 if texts:
#                     await self.mc.tg_notifier.send_block(texts)

#         self.logger.info("CopyDestrib: signal_loop FINISHED")




    # @staticmethod
    # def flush_log_events(log_events: Iterable) -> List[str]:
    #     """
    #     Форматирует и очищает накопленные лог-события.
    #     """
    #     if not log_events:
    #         return []

    #     try:
    #         return [
    #             FormatUILogs.format_master_log_event(cid, mev)
    #             for cid, mev in log_events
    #         ]
    #     finally:
    #         log_events.clear()





