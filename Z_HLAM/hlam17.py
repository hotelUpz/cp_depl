# # # SIGNAL.signal_fsm.py

# # from __future__ import annotations

# # import asyncio
# # import hashlib
# # from typing import *

# # from DESTRIBUTOR.copy_ import CopyDestrib
# # from .signal_stream import MasterSignalStream
# # from .master_payload import MasterPayload
# # from .signal_state import SignalCache

# # if TYPE_CHECKING:
# #     from DESTRIBUTOR.state_ import CopyState
# #     from b_context import MainContext
# #     from c_log import UnifiedLogger


# # # ======================================================================
# # # HELPERS
# # # ======================================================================

# # def creds_hash(cfg: dict) -> str:
# #     ex = cfg.get("exchange", {})
# #     key = ex.get("api_key") or ""
# #     sec = ex.get("api_secret") or ""
# #     proxy = ex.get("proxy") or ""
# #     return hashlib.md5(f"{key}:{sec}:{proxy}".encode()).hexdigest()


# # # ======================================================================
# # # SIGNAL FSM
# # # ======================================================================

# # class SignalFSM:
# #     def __init__(
# #         self,
# #         mc: "MainContext",
# #         logger: "UnifiedLogger",
# #         copy_state: CopyState,
# #         stop_flag: Callable,
# #     ):
# #         self.mc = mc
# #         self.logger = logger
# #         self.copy_state = copy_state
# #         self.stop_flag = stop_flag

# #         # SIGNAL INFRA
# #         self.signal_cache: SignalCache | None = None
# #         self.signal_stream: MasterSignalStream | None = None
# #         self.payload: MasterPayload | None = None

# #         # COPY LAYER
# #         self.copy = CopyDestrib(
# #             mc=self.mc,
# #             logger=self.logger,
# #             copy_state=self.copy_state,
# #             stop_flag=self.stop_flag,
# #         )

# #         self.payload_task: asyncio.Task | None = None

# #     # ------------------------------------------------------------------
# #     def _reset_master_state(self):
# #         self.mc.pos_vars_root.clear()

# #     # ==================================================================
# #     # MASTER SUPERVISOR
# #     # ==================================================================
# #     async def master_supervisor(self):
# #         self.logger.info("[FSM] Master supervisor started")
# #         self.logger.info("[FSM] ENTER DISABLED")

# #         last_hash = None
# #         stream_task: asyncio.Task | None = None
# #         copy_loop_task: asyncio.Task | None = None

# #         while not self.stop_flag():
# #             await asyncio.sleep(0.05)

# #             master_cfg = self.mc.copy_configs.get(0, {})
# #             ex = master_cfg.get("exchange", {})
# #             cmd_state = master_cfg.get("cmd_state", {})

# #             api_key = ex.get("api_key")
# #             api_secret = ex.get("api_secret")
# #             proxy = ex.get("proxy")

# #             trading_enabled = cmd_state.get("trading_enabled", False)
# #             flagged_stop = cmd_state.get("stop_flag", False)

# #             # ------------------------------------------------------------
# #             # MASTER DISABLED
# #             # ------------------------------------------------------------
# #             if not trading_enabled or flagged_stop:

# #                 # stop WS
# #                 if self.signal_stream:
# #                     try:
# #                         self.signal_stream.stop()
# #                     except Exception:
# #                         pass
# #                 self.signal_stream = None

# #                 # cancel WS task
# #                 if stream_task and not stream_task.done():
# #                     stream_task.cancel()
# #                     with asyncio.CancelledError:
# #                         pass
# #                 stream_task = None

# #                 # stop COPY loop
# #                 if copy_loop_task and not copy_loop_task.done():
# #                     self.copy.stop_signal_loop()
# #                     copy_loop_task.cancel()
# #                     with asyncio.CancelledError:
# #                         pass
# #                 copy_loop_task = None

# #                 self._reset_master_state()
# #                 last_hash = None

# #                 await asyncio.sleep(0.3)
# #                 continue

# #             # ------------------------------------------------------------
# #             # VERIFY CREDS
# #             # ------------------------------------------------------------
# #             if not (api_key and api_secret):
# #                 await asyncio.sleep(0.3)
# #                 continue

# #             cur_hash = creds_hash(master_cfg)

# #             # ------------------------------------------------------------
# #             # SAME CREDS → RUNNING
# #             # ------------------------------------------------------------
# #             if cur_hash == last_hash and stream_task and not stream_task.done():
# #                 await asyncio.sleep(0.2)
# #                 continue

# #             # ------------------------------------------------------------
# #             # CREDS CHANGED → RELOAD
# #             # ------------------------------------------------------------
# #             if self.signal_stream:
# #                 self.logger.info("[FSM] ENTER RELOAD")

# #             # stop old stream
# #             if self.signal_stream:
# #                 try:
# #                     self.signal_stream.stop()
# #                 except Exception:
# #                     pass

# #             if stream_task and not stream_task.done():
# #                 stream_task.cancel()
# #                 with asyncio.CancelledError:
# #                     pass

# #             self._reset_master_state()

# #             # ---------------------------------------------------------
# #             # START NEW WS STREAM
# #             # ---------------------------------------------------------
# #             self.signal_cache = SignalCache()

# #             self.signal_stream = MasterSignalStream(
# #                 api_key=api_key,
# #                 api_secret=api_secret,
# #                 signal_cache=self.signal_cache,
# #                 logger=self.logger,
# #                 stop_flag=self.stop_flag,
# #                 proxy_url=proxy,
# #             )
# #             stream_task = asyncio.create_task(self.signal_stream.start())

# #             while not self.stop_flag():
# #                 await asyncio.sleep(0.05)
# #                 if self.signal_stream.ready:
# #                     break

# #             self.logger.info("[FSM] Master WS ready")

# #             # ---------------------------------------------------------
# #             # RECREATE MASTER PAYLOAD
# #             # ---------------------------------------------------------
# #             if self.payload:
# #                 try:
# #                     self.payload.stop()
# #                 except Exception:
# #                     pass

# #             if self.payload_task and not self.payload_task.done():
# #                 self.payload_task.cancel()
# #                 with asyncio.CancelledError:
# #                     pass
# #             self.payload_task = None

# #             self.payload = MasterPayload(
# #                 cache=self.signal_cache,
# #                 mc=self.mc,
# #                 logger=self.logger,
# #                 stop_flag=self.stop_flag,
# #             )
# #             self.payload_task = asyncio.create_task(self.payload.run())
# #             self.copy.attach_payload(self.payload)

# #             # ---------------------------------------------------------
# #             # STOP OLD COPY LOOP
# #             # ---------------------------------------------------------
# #             if copy_loop_task and not copy_loop_task.done():
# #                 self.copy.stop_signal_loop()
# #                 copy_loop_task.cancel()
# #                 with asyncio.CancelledError:
# #                     pass

# #             # ---------------------------------------------------------
# #             # START NEW COPY LOOP
# #             # ---------------------------------------------------------
# #             copy_loop_task = asyncio.create_task(self.copy.signal_loop())

# #             last_hash = cur_hash
# #             self.logger.info("[FSM] ENTER RUNNING")

# #         self.logger.info("[FSM] ENTER DISABLED")



# # SIGNAL.signal_fsm.py

# from __future__ import annotations

# import asyncio
# import hashlib
# from typing import *

# from COPY.copy_ import CopyDestrib
# from .signal_stream import MasterSignalStream
# from .master_payload import MasterPayload
# from .signal_state import SignalCache

# if TYPE_CHECKING:
#     from COPY.state_ import CopyState
#     from b_context import MainContext
#     from c_log import UnifiedLogger


# def creds_hash(cfg: dict) -> str:
#     ex = cfg.get("exchange", {})
#     key = ex.get("api_key") or ""
#     sec = ex.get("api_secret") or ""
#     proxy = ex.get("proxy") or ""
#     return hashlib.md5(f"{key}:{sec}:{proxy}".encode()).hexdigest()


# class SignalFSM:
#     def __init__(
#         self,
#         mc: "MainContext",
#         logger: "UnifiedLogger",
#         copy_state: CopyState,
#         stop_flag: Callable,
#     ):
#         self.mc = mc
#         self.logger = logger
#         self.copy_state = copy_state
#         self.stop_flag = stop_flag

#         self.signal_cache: SignalCache | None = None
#         self.signal_stream: MasterSignalStream | None = None
#         self.payload: MasterPayload | None = None

#         self.copy = CopyDestrib(
#             mc=self.mc,
#             logger=self.logger,
#             copy_state=self.copy_state,
#             stop_flag=self.stop_flag,
#         )
#         self.logger.wrap_object_methods(self.copy)

#         self.payload_task: asyncio.Task | None = None
#         self.copy_loop_task: asyncio.Task | None = None

#     # --------------------------------------------------
#     def _reset_master_state(self):
#         self.mc.pos_vars_root.clear()

#     # ==================================================
#     async def master_supervisor(self):
#         self.logger.info("[FSM] Master supervisor started")

#         last_hash: str | None = None
#         stream_task: asyncio.Task | None = None

#         while not self.stop_flag():
#             await asyncio.sleep(0.05)

#             master_cfg = self.mc.copy_configs.get(0, {})
#             ex = master_cfg.get("exchange", {})
#             cmd_state = master_cfg.get("cmd_state", {})

#             trading_enabled = cmd_state.get("trading_enabled", False)
#             flagged_stop = cmd_state.get("stop_flag", False)

#             api_key = ex.get("api_key")
#             api_secret = ex.get("api_secret")
#             proxy = ex.get("proxy")

#             # ==================================================
#             # HARD STOP ONLY
#             # ==================================================
#             if flagged_stop:
#                 self.logger.info("[FSM] HARD STOP")

#                 if self.signal_stream:
#                     self.signal_stream.stop()
#                 self.signal_stream = None

#                 if stream_task and not stream_task.done():
#                     stream_task.cancel()
#                 stream_task = None

#                 if self.payload:
#                     self.payload.stop()
#                 if self.payload_task and not self.payload_task.done():
#                     self.payload_task.cancel()
#                 self.payload = None
#                 self.payload_task = None

#                 if self.copy_loop_task and not self.copy_loop_task.done():
#                     self.copy.stop_signal_loop()
#                     self.copy_loop_task.cancel()
#                 self.copy_loop_task = None

#                 self._reset_master_state()
#                 await asyncio.sleep(0.3)
#                 continue

#             # ==================================================
#             # DISABLED → PAUSE ONLY (NO RESET)
#             # ==================================================
#             if not trading_enabled:
#                 await asyncio.sleep(0.2)
#                 continue

#             # ==================================================
#             # CREDS CHECK
#             # ==================================================
#             if not (api_key and api_secret):
#                 await asyncio.sleep(0.3)
#                 continue

#             cur_hash = creds_hash(master_cfg)

#             # ==================================================
#             # RUNNING & SAME CREDS
#             # ==================================================
#             if cur_hash == last_hash and stream_task and not stream_task.done():
#                 await asyncio.sleep(0.2)
#                 continue

#             # ==================================================
#             # RELOAD (CREDS CHANGED OR FIRST START)
#             # ==================================================
#             self.logger.info("[FSM] RELOAD MASTER STREAM")

#             if self.signal_stream:
#                 self.signal_stream.stop()

#             if stream_task and not stream_task.done():
#                 stream_task.cancel()

#             self._reset_master_state()

#             # ---------- NEW CACHE ----------
#             self.signal_cache = SignalCache()

#             self.signal_stream = MasterSignalStream(
#                 api_key=api_key,
#                 api_secret=api_secret,
#                 signal_cache=self.signal_cache,
#                 logger=self.logger,
#                 stop_flag=self.stop_flag,
#                 proxy_url=proxy,
#             )
#             self.logger.wrap_object_methods(self.signal_stream)
#             stream_task = asyncio.create_task(self.signal_stream.start())

#             while not self.stop_flag():
#                 await asyncio.sleep(0.05)
#                 if self.signal_stream.ready:
#                     break

#             self.logger.info("[FSM] Master WS ready")

#             # ---------- PAYLOAD ----------
#             if self.payload:
#                 self.payload.stop()
#             if self.payload_task and not self.payload_task.done():
#                 self.payload_task.cancel()

#             self.payload = MasterPayload(
#                 cache=self.signal_cache,
#                 mc=self.mc,
#                 logger=self.logger,
#                 stop_flag=self.stop_flag,
#             )
#             self.logger.wrap_object_methods(self.signal_stream)
#             self.payload_task = asyncio.create_task(self.payload.run())
#             self.copy.attach_payload(self.payload)

#             # ---------- COPY LOOP ----------
#             if not self.copy_loop_task or self.copy_loop_task.done():
#                 self.copy_loop_task = asyncio.create_task(
#                     self.copy.signal_loop()
#                 )

#             last_hash = cur_hash
#             self.logger.info("[FSM] ENTER RUNNING")

#         self.logger.info("[FSM] EXIT")



    # async def _execute_signal(self, mev: "MasterEvent"):
    #     async with self._exec_sem:

    #         local_monitors: Dict[int, PosMonitorFSM] = {}

    #         await self._broadcast_to_copies(mev, local_monitors)

    #         results: list[dict] = []
    #         ids = list(local_monitors.keys())

    #         if mev.method.upper() == "MARKET" and local_monitors:
    #             await asyncio.gather(
    #                 *[m.refresh() for m in local_monitors.values()],
    #                 return_exceptions=False,
    #             )

    #             results = await self.reset_pv_state.finalize_positions(ids)

    #         await flush_ui_logs_if_any(self.mc)

    #         if results:
    #             texts: list[str] = []
    #             texts.extend(FormatUILogs.format_general_report(results))
    #             texts.append(FormatUILogs.format_general_summary(results))
    #             await self.mc.tg_notifier.send_block(texts)







    # async def init_telegram(self):
    #     self.ui_copytrade = UIMenu(
    #         bot=self.bot,
    #         dp=self.dp,
    #         ctx=self.mc,
    #         logger=self.logger,
    #         copy_state=self.copy_state,
    #         admin_id=ADMIN_CHAT_ID,
    #         on_close=self.cmd.on_close,   # ← ВАЖНО
    #     )

    #     self.mc.tg_notifier = TelegramNotifier(
    #         bot=self.bot,
    #         logger=self.logger,
    #         chat_id=ADMIN_CHAT_ID,
    #         stop_bot=lambda: self._stop_flag,
    #     )

    #     self.logger.wrap_object_methods(self.ui_copytrade)
    #     self.logger.wrap_object_methods(self.mc.tg_notifier)