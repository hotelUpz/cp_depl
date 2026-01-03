
                    # if not res or not res.get("success"):
                    #     self.logger.warning(
                    #         f"[FORCE_CLOSE:{cid}] close FAILED {symbol} {pos_side}: "
                    #         f"{res.get('reason') if res else 'no response'}"
                    #     )
                    #     continue








# def format_status(cfg: dict) -> str:
#     """
#     Полный красивый форматтер статуса для MASTER и COPY.
#     Показывает:
#     - role
#     - exchange.*
#     - runtime.*
#     - риск-параметры и копи-настройки
#     - coef, leverage, delay_ms, random_size_pct
#     - enabled / created_at
#     - id
#     """
#     lines = []

#     # ========================
#     # ROLE + ID
#     # ========================
#     role = cfg.get("role", "copy").upper()
#     acc_id = cfg.get("id")
#     enabled = cfg.get("enabled", False)

#     status_icon = "🟢" if enabled else "⚪"
#     lines.append(f"{status_icon} Role: {role} (ID={acc_id})")

#     # ========================
#     # EXCHANGE BLOCK
#     # ========================
#     ex = cfg.get("exchange", {})
#     lines.append("\n<b>Exchange</b>:")
#     lines.append(f"  • api_key: {ex.get('api_key') or '—'}")
#     lines.append(f"  • api_secret: {ex.get('api_secret') or '—'}")
#     lines.append(f"  • uid: {ex.get('uid') or '—'}")
#     proxy = ex.get("proxy")
#     lines.append(f"  • proxy: {proxy if proxy not in (None, '', '0') else '—'}")

#     # ========================
#     # RUNTIME BLOCK
#     # ========================
#     rt = cfg.get("cmd_state") or {}
#     if rt:
#         lines.append("\n<b>Runtime</b>:")
#         for k, v in rt.items():
#             lines.append(f"  • {k}: {v}")

#     # ========================
#     # COPY SETTINGS BLOCK
#     # (общие параметры)
#     # ========================
#     copy_fields = (
#         "coef",
#         "leverage",
#         "margin_mode",
#         "max_position_size",
#         "random_size_pct",
#         "delay_ms",
#     )

#     show_copy_block = any(k in cfg for k in copy_fields)

#     if show_copy_block:
#         lines.append("\n<b>Copy Settings</b>:")

#         coef = cfg.get("coef")
#         if coef is not None:
#             lines.append(f"  • coef: {coef}")

#         lev = cfg.get("leverage")
#         if lev is not None:
#             lines.append(f"  • leverage: {lev}")

#         margin_mode = cfg.get("margin_mode")
#         if margin_mode is not None:
#             lines.append(f"  • margin_mode: {margin_mode}")

#         mps = cfg.get("max_position_size")
#         if mps is not None:
#             lines.append(f"  • max_position_size: {mps}")

#         rnd = cfg.get("random_size_pct")
#         if rnd:
#             try:
#                 lines.append(f"  • random_size_pct: ({rnd[0]}, {rnd[1]})")
#             except:
#                 lines.append(f"  • random_size_pct: {rnd}")

#         dms = cfg.get("delay_ms")
#         if dms is not None:
#             lines.append(f"  • delay_ms: {dms} ms")

#     # ========================
#     # CREATED AT
#     # ========================
#     ts = cfg.get("created_at")
#     if ts:
#         assert isinstance(ts, int) and ts > 1e10
#         lines.append(f"\nCreated at: {Utils.milliseconds_to_datetime(ts)}")

#     return "\n".join(lines)



# graceful_shutdown.py

# from __future__ import annotations
# import signal
# import asyncio

# from typing import TYPE_CHECKING

# if TYPE_CHECKING:
#     from main import CoreApp


# def setup_graceful_shutdown(app: "CoreApp"):
#     loop = asyncio.get_event_loop()

#     def _handler():
#         print("🛑 Graceful shutdown initiated")
#         app._stop_flag = True

#     try:
#         loop.add_signal_handler(signal.SIGTERM, _handler)
#         loop.add_signal_handler(signal.SIGINT, _handler)
#     except NotImplementedError:
#         # --- Windows fallback ---
#         import threading

#         def win_handler(*args):
#             _handler()

#         # Python на Win вызывает handler через KeyboardInterrupt
#         threading.excepthook = lambda args: win_handler()



        # =====================================================================
        #                   INIT MASTER + COPIES (генерируем master (0) + copies (1..N))
        # =====================================================================
        # self.ctx.load_accounts()




    # # ======================================================
    # # LEVELS
    # # ======================================================

    # def debug(self, msg: str):
    #     if LOG_DEBUG:
    #         self._logger.debug(msg)

    # def info(self, msg: str):
    #     if LOG_INFO:
    #         self._logger.info(msg)

    # def warning(self, msg: str):
    #     if LOG_WARNING:
    #         self._logger.warning(msg)

    # def error(self, msg: str):
    #     if LOG_ERROR:
    #         self._logger.error(msg)

    # def exception(self, msg: str, exc: Exception | None = None):
    #     if LOG_ERROR:
    #         if exc:
    #             self._logger.exception(f"{msg}: {exc}")
    #         else:
    #             self._logger.exception(msg)



    # # ==========================================================================
    # # SHUTDOWN
    # # ==========================================================================
    # async def shutdown(self):
    #     self._stop_flag = True

    #     if self.spec_task:
    #         self.spec_task.cancel()
    #         with contextlib.suppress(asyncio.CancelledError):
    #             await self.spec_task

    #     if self.public_connector:
    #         await self.public_connector.shutdown_session()

    #     await self.bot.session.close()

    #     self.logger.info("CoreApp stopped")




    # # --------------------------------------------------
    # async def _broadcast_to_copies(self, mev: "MasterEvent"):
    #     if mev.sig_type not in ("copy", "log"):
    #         return
    #     self.logger.debug(
    #         f"[BROADCAST] enter | event={mev.event} "
    #         f"symbol={mev.symbol} side={mev.pos_side} closed={mev.closed}"
    #     )

    #     tasks = []

    #     for idx, (cid, cfg) in enumerate(self.mc.copy_configs.items(), start=1):
    #         self.logger.debug(
    #             f"[BROADCAST] inspect cid={cid} enabled={cfg.get('enabled')}"
    #         )

    #         # print(cfg)
    #         if not cfg.get("enabled"):
    #             continue
            
    #         # print("ncvnjkcvdkjvcdkjcdkj")
    #         rt = await self.copy_state.ensure_copy_state(cid)
    #         if not rt or rt.get("cmd_closing"):
    #             continue

    #         tasks.append(
    #             asyncio.create_task(
    #                 self._handle_copy_event(cid, cfg, rt, mev)
    #             )
    #         )

    #     self.logger.debug(f"[BROADCAST] tasks_created={len(tasks)}")

    #     if not tasks:
    #         self.logger.info(
    #             f"[BROADCAST] no active copies for {mev.event} {mev.symbol}"
    #         )
    #         return

    #     await asyncio.gather(*tasks, return_exceptions=False)

    #     if mev.method.upper() == "MARKET" and self.pos_monitors:
    #         ids = list(self.pos_monitors.keys())
    #         await asyncio.gather(
    #             *[m.refresh() for m in self.pos_monitors.values()],
    #             return_exceptions=False,
    #         )
    #         self.pos_monitors.clear()
    #         await self.reset_pv_state.finalize_positions(ids)




            # if self.mc.log_events:
            #     texts = FormatUILogs.flush_log_events(self.mc.log_events)
            #     if texts:
            #         await self.mc.tg_notifier.send_block(texts)


            # for r in all_finish_results:
            #     cid = r.get("cid")
            #     self.mc.log_events.append((cid, r))

            # self.mc.log_events.append((0, "📊 Positions finalized"))

            # texts: List[str] = []

            # texts.extend(
            #     FormatUILogs.format_general_report(all_finish_results)
            # )
            # texts.append(
            #     FormatUILogs.format_general_summary(all_finish_results)
            # )
            
            # texts.append("📊 Positions finalized")
            # await self.mc.tg_notifier.send_block(texts)





# class CopyState:
#     """
#     Управляет ЖИЗНЕННЫМ ЦИКЛОМ copy-runtime.
#     Никакой ленивой инициализации в бою.
#     """

#     def __init__(
#         self,
#         mc: "MainContext",
#         logger: "UnifiedLogger",
#         stop_flag: Callable[[], bool],
#     ):
#         self.mc = mc
#         self.logger = logger
#         self.stop_flag = stop_flag

#     # ==================================================
#     # LOW-LEVEL WAIT
#     # ==================================================

#     async def wait_for_session(
#         self,
#         connector: NetworkManager,
#         timeout_ms: int = SESSION_TTL,
#     ) -> bool:
#         t0 = now()
#         while not self.stop_flag():
#             if connector.session:
#                 return True
#             if now() - t0 > timeout_ms:
#                 return False
#             await asyncio.sleep(0.01)
#         return False

#     # ==================================================
#     # PUBLIC API
#     # ==================================================

#     async def activate_copy(self, cid: int) -> bool:
#         """
#         Полная подготовка copy-аккаунта.
#         Вызывается ТОЛЬКО из UI / команды.
#         """
#         self.logger.info(f"[CopyState:{cid}] activate_copy")

#         self.mc.active_copy_ids.add(cid)

#         rt = await self._init_copy_runtime(cid)
#         if not rt:
#             self.logger.error(f"[CopyState:{cid}] activation failed")
#             self.mc.active_copy_ids.discard(cid)
#             return False

#         self.logger.info(f"[CopyState:{cid}] READY")
#         return True

#     async def deactivate_copy(self, cid: int):
#         """
#         Полное выключение copy-аккаунта.
#         """
#         self.logger.info(f"[CopyState:{cid}] deactivate_copy")
#         self.mc.active_copy_ids.discard(cid)
#         await self.shutdown_runtime(cid)

#     async def ensure_copy_state(self, cid: int) -> Optional[Dict[str, Any]]:
#         """
#         БОЕВОЙ МЕТОД.
#         НИЧЕГО НЕ СОЗДАЁТ.
#         НИЧЕГО НЕ ЧИНИТ.
#         """
#         rt = self.mc.copy_runtime_states.get(cid)
#         if not rt:
#             return None

#         if not rt.get("network_ready"):
#             return None

#         return rt

#     # ==================================================
#     # INTERNAL INIT
#     # ==================================================

#     async def _init_copy_runtime(self, cid: int) -> Optional[Dict[str, Any]]:
#         """
#         Вся тяжёлая инициализация здесь.
#         """

#         cfg = self.mc.copy_configs.get(cid)
#         if not cfg:
#             self.logger.error(f"[CopyState:{cid}] no config")
#             return None

#         if not cfg.get("enabled"):
#             self.logger.warning(f"[CopyState:{cid}] not enabled")
#             return None

#         # если уже существует — считаем валидным
#         rt = self.mc.copy_runtime_states.get(cid)
#         if rt and rt.get("network_ready"):
#             return rt

#         # ---- CREATE RUNTIME ----
#         rt = copy.deepcopy(COPY_RUNTIME_STATE)
#         rt["id"] = cid
#         self.mc.copy_runtime_states[cid] = rt

#         ex = cfg.get("exchange", {})
#         api_key = ex.get("api_key")
#         api_secret = ex.get("api_secret")
#         uid = ex.get("uid")
#         proxy = ex.get("proxy")

#         # ---- NETWORK ----
#         connector = NetworkManager(
#             logger=self.logger,
#             proxy_url=proxy,
#             stop_flag=self.stop_flag,
#         )
#         self.logger.wrap_object_methods(connector)
#         connector.start_ping_loop()

#         rt["connector"] = connector

#         ok = await self.wait_for_session(connector)
#         if not ok:
#             self.logger.error(f"[CopyState:{cid}] session timeout")
#             await self.shutdown_runtime(cid)
#             return None

#         # ---- CLIENT ----
#         mc_client = MexcClient(
#             connector=connector,
#             logger=self.logger,
#             api_key=api_key,
#             api_secret=api_secret,
#             token=uid,
#         )
#         self.logger.wrap_object_methods(mc_client)

#         rt["mc_client"] = mc_client
#         rt["network_ready"] = True

#         return rt

#     # ==================================================
#     # SHUTDOWN
#     # ==================================================

#     async def shutdown_runtime(self, cid: int):
#         rt = self.mc.copy_runtime_states.pop(cid, None)
#         if not rt:
#             return

#         conn = rt.get("connector")
#         if conn:
#             try:
#                 await conn.shutdown_session()
#             except Exception:
#                 pass

#         self.logger.info(f"[CopyState:{cid}] runtime destroyed")

