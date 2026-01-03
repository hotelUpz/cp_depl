# # main.py
# from __future__ import annotations

# import asyncio
# # import aiohttp
# import hashlib
# from aiogram import Bot, Dispatcher

# from a_config import TG_BOT_TOKEN, ADMIN_CHAT_ID
# from b_context import *
# from c_log import ErrorHandler, log_time
# from b_network import NetworkManager

# # telegram UI (оставляем)
# from TG.tg_ui_copytrade import CopyTradeUI
# from TG.tg_notifier import TelegramNotifier

# # master stream
# from MASTER.signal_cache import SignalCache
# from MASTER.signal_stream import MasterSignalStream
# from DESTRIBUTOR.cmd_ import CmdDestrib
# from DESTRIBUTOR.copy_ import CopyDestrib
# from DESTRIBUTOR.helpers import Runtime
# # from API.MX.client import MexcClient
# from API.MX.public import MXPublic
# from MASTER.signal_tracker import MasterOrderTracker



# def creds_hash(cfg: dict) -> str:
#     ex = cfg.get("exchange", {})
#     key = ex.get("api_key") or ""
#     sec = ex.get("api_secret") or ""
#     proxy = ex.get("proxy") or ""
#     s = f"{key}:{sec}:{proxy}"
#     return hashlib.md5(s.encode()).hexdigest()


# class CoreApp:
#     def __init__(self):
#         self.mc = MainContext()
#         self.logger = ErrorHandler()

#         self.bot = Bot(TG_BOT_TOKEN, parse_mode=None)
#         self.dp = Dispatcher()

#         self._stop_flag = False

#         # === MASTER SIGNALLING SYSTEM ===
#         self.signal_cache = SignalCache()
#         self.signal_stream: MasterSignalStream | None = None
#         self.tracker = MasterOrderTracker(self.signal_cache, logger=self.logger)
        
#         self.ready: bool = False

#         self.runtime = Runtime(
#             mc=self.mc,
#             logger=self.logger,            
#             stop_flag=lambda: self._stop_flag,
#         )

#         self.copy = CopyDestrib(
#             mc=self.mc,
#             logger=self.logger,
#             runtime=self.runtime,            
#             signal_cache=self.signal_cache,
#             stop_flag=lambda: self._stop_flag,
#             ready=lambda: self.ready
#         )
#         self.copy.attach_tracker(self.tracker)

#         self.cmd = CmdDestrib(
#             mc=self.mc,
#             logger=self.logger,     
#             runtime=self.runtime,       
#             stop_flag=lambda: self._stop_flag,
#         )

#     # ============================================================
#     # Telegram infra (оставлено, просто закомментировано)
#     # ============================================================
#     async def init_telegram(self):
#         # User UI
#         self.ui_copytrade = CopyTradeUI(
#             bot=self.bot,
#             dp=self.dp,
#             ctx=self.mc,
#             logger=self.logger,
#             runtime=self.runtime,
#             admin_id=ADMIN_CHAT_ID
#         )

#         # Notifier
#         self.notifier = TelegramNotifier(
#             bot=self.bot,
#             queues_msg=self.mc.queues_msg,
#             logger=self.logger,
#             stop_bot=lambda: self._stop_flag
#         )

#     # ------------------------------------------------------------------------
#     # DATA LOAD (UNIFIED)
#     # ------------------------------------------------------------------------
#     async def load_spec_data(self) -> None:
#         try:
#             proxy = MASTER_TEMPLATE.get("exchange", {}).get("proxy")
#             self.public_connector = NetworkManager(
#                 logger=self.logger,
#                 proxy_url=proxy,
#                 stop_flag=lambda: self._stop_flag
#             )
#             self.public_connector.start_ping_loop()
#             if not await self.runtime.wait_for_session(id=0, connector=self.public_connector):
#                 print(f"Failed get instruments_data in stady init session")
#                 return
#             for _ in range(10):
#                 if self._stop_flag:
#                     return
#                 try:
#                     data = await MXPublic.get_instruments(session=self.public_connector.session)
#                     if data:
#                         self.mc.instruments_data = data
#                         break
#                 except Exception as e:
#                     print(f"Failed get instruments_data: {e}")
#                 await asyncio.sleep(0.8)

#         finally:
#             await self.public_connector.shutdown_session()

#     # ============================================================
#     # MASTER WS START
#     # ============================================================        
#     async def start_master_signal_stream(self):
#         print("🚀 Master WS supervisor started")

#         last_hash = None
#         stream_task = None
#         signal_task = None

#         while not self._stop_flag:

#             await asyncio.sleep(0)  # критично для responsiveness

#             master_cfg = self.mc.copy_configs.get(0, {})
#             ex = master_cfg.get("exchange", {})
#             # print(ex)

#             api_key = ex.get("api_key")
#             api_secret = ex.get("api_secret")
#             proxy = ex.get("proxy")
#             enabled = master_cfg.get("enabled", False)

#             ready = (api_key and api_secret and enabled)

#             if not ready:
#                 await asyncio.sleep(0.5)
#                 continue

#             cur_hash = creds_hash(master_cfg)

#             if cur_hash != last_hash:

#                 print("🔄 Restarting master stream")

#                 if self.signal_stream:
#                     try: self.signal_stream.stop()
#                     except: pass

#                 if stream_task and not stream_task.done():
#                     stream_task.cancel()
#                     try: await stream_task
#                     except: pass

#                 self.signal_stream = MasterSignalStream(
#                     api_key=api_key,
#                     api_secret=api_secret,
#                     signal_cache=self.signal_cache,
#                     logger=self.logger,
#                     proxy_url=proxy,
#                 )

#                 stream_task = asyncio.create_task(self.signal_stream.start())

#                 while not self._stop_flag:
#                     await asyncio.sleep(0)
#                     if self.signal_stream.ready:
#                         break

#                 self.copy.attach_tracker(self.tracker) # -- здесь ему место

#                 self.ready = True # -- этот товарищ и вовсе больше не нужен. это -- хрен на голову одевать. все линейно, прозрачно
#                 last_hash = cur_hash

#                 print("🚀 Stream ready")
#                 if signal_task is not None:
#                     pass
#                     # signal_task.done() # -- как-то надо остановить и задачу и внутреннюю лупу. возможно внутрь self.copy добавить соответствующий метод остановки.


#                 signal_task = asyncio.create_task(self.copy.signal_loop()) # -- сюда хорошего!!
#                 print("✔ Copy loop started")

#     # ============================================================
#     # RUN
#     # ============================================================
#     async def run(self):
#         print(f"Время старта: {log_time()}")

#         # 1. Telegram UI
#         await self.init_telegram()
#         tg_task = asyncio.create_task(self.dp.start_polling(
#             self.bot,
#             skip_updates=True,
#             polling_timeout=60,
#             handle_as_tasks=True
#         ))
#         print("✔ Telegram started")

#         # 2. Загрузка данных для MEXC (инструменты)
#         await self.load_spec_data()
#         print("✔ Instruments loaded")

#         # 3. Старт supervisor WS (но он сам поднимет ready)
#         master_task = asyncio.create_task(self.start_master_signal_stream())
#         print("✔ Master supervisor started")

#         # # 4. COPY loop (он сам ждёт ready())
#         # signal_task = asyncio.create_task(self.copy.signal_loop()) -- к такой бабушке!!
#         # print("✔ Copy loop started")

#         # 5. Cmd loop (независим)
#         cmd_task = asyncio.create_task(self.cmd.cmd_loop())
#         print("✔ Cmd loop started")

#         try:
#             await asyncio.gather(
#                 tg_task,
#                 master_task,
#                 # signal_task,
#                 cmd_task
#             )
#         except asyncio.CancelledError:
#             pass
#         finally:
#             await self.bot.session.close()


# async def main():
#     app = CoreApp()
#     try:
#         await app.run()
#     except KeyboardInterrupt:
#         print("💥 Exit: Ctrl+C pressed")


# if __name__ == "__main__":
#     asyncio.run(main())



# # DESTRIBUTOR/copy_destrib.py
# from __future__ import annotations

# import asyncio
# from typing import Callable, TYPE_CHECKING

# from b_context import MainContext
# from c_log import ErrorHandler

# from MASTER.signal_cache import SignalCache
# from MASTER.master_payload import MasterEvent, MasterPayloadBuilder


# # from pos.pos_vars_setup import PosVarSetup
# from .copy_executor import CopyExecutor


# if TYPE_CHECKING:
#     from .helpers import Runtime
#     from API.MX.client import MexcClient



# # @dataclass
# # class MasterEvent:
# #     event: Literal[
# #         "order_created",
# #         "order_triggered",
# #         "opened",
# #         "closed",
# #         "partial_closed",
# #         "deal"
# #     ]
# #     symbol: str
# #     side: Optional[str]  # LONG/SHORT
# #     payload: Dict[str, Any]
# #     ts: float

# class CopyDestrib:
#     """
#     CopyDestrib — принимает HIGH-LEVEL MasterEvent,
#     раздаёт их копи-аккаунтам.

#     Теперь поддерживает корректный перезапуск loop при смене мастер ключей:
#         ✔ stop_signal_loop()
#         ✔ stop_tracker()
#         ✔ graceful shutdown async generator
#     """

#     def __init__(
#         self,
#         mc: MainContext,
#         logger: ErrorHandler,
#         runtime: Runtime,
#         signal_cache: SignalCache,
#         stop_flag: Callable,
#     ):
#         self.mc = mc
#         self.logger = logger
#         self.stop_flag = stop_flag
#         self.runtime = runtime
#         self.signal_cache = signal_cache

#         self.payload: MasterPayloadBuilder | None = None
#         self.executor = CopyExecutor(runtime=self.runtime)

#         # внутренние флаги остановки
#         self._stop_signal_loop = True
#         self._stop_tracker = True

#     # ----------------------------------------------------------------------
#     #  Внешний supervisor вызывает это после рестарта master-stream
#     # ----------------------------------------------------------------------
#     def attach_payload(self, payload: MasterPayloadBuilder):
#         self.payload = payload

#     # ----------------------------------------------------------------------
#     # STOP API — вызывается supervisor'ом перед рестартом copy-loop
#     # ----------------------------------------------------------------------

#     def stop_signal_loop(self):
#         """
#         Остановить рабочий цикл CopyDestrib (signal_loop).
#         """
#         print("🛑 CopyDestrib: stop_signal_loop() called")
#         self._stop_signal_loop = True

#     def stop_tracker(self):
#         print("🛑 CopyDestrib: stop_tracker() called")
#         self._stop_tracker = True
#         if self.payload:
#             self.payload.external_stop()

#     # ======================================================================
#     # EXECUTOR — пока заглушка (просто печатает события)
#     # ======================================================================

#     async def execute_copy_order(self, copy_id: int, mev: MasterEvent):
#         await self.executor.execute(copy_id, mev)
#         print(
#             f"⚙ EXEC [{copy_id}] → HL({mev.event}) "
#             f"{mev.symbol} {mev.side} payload={mev.payload}"
#         )

#     # ======================================================================
#     # BROADCAST
#     # ======================================================================

#     async def _broadcast_to_copies(self, mev: MasterEvent):
#         """
#         Рассылаем событие всем активным копи-аккаунтам.
#         """
#         for cid, cfg in self.mc.copy_configs.items():
#             if cid == 0:
#                 continue
#             if not cfg.get("enabled"):
#                 continue

#             print(f"   → COPY[{cid}] handling HL → {mev.event}")

#             try:
#                 asyncio.create_task(self.execute_copy_order(cid, mev))
#             except Exception as e:
#                 print(f"❗ ERROR exec copy[{cid}]: {e}")

#     # ======================================================================
#     # MAIN REACTIVE LOOP
#     # ======================================================================

#     async def signal_loop(self):
#         """
#         Главный high-level поток.

#         ВАЖНО:
#             — может быть остановлен supervisor'ом
#             — корректно завершает tracker.run()
#             — запускается заново при смене ключей мастера
#         """

#         if not self.payload:
#             print("❗ ERROR: tracker is not attached!")
#             return

#         print("✔ CopyDestrib: signal_loop STARTED")

#         # разрешаем работу
#         self._stop_signal_loop = False
#         self._stop_tracker = False

#         # ждём включения мастера (proxy, master_cfg.enable, runtime)
#         while not self.stop_flag() and not self._stop_signal_loop:
#             master_rt = self.mc.copy_configs.get(0, {}).get("runtime", {})
#             if master_rt.get("trading_enabled") and not master_rt.get("stop_flag"):
#                 break
#             await asyncio.sleep(0.1)

#         if self._stop_signal_loop:
#             print("🛑 CopyDestrib: signal_loop aborted before start")
#             return

#         print("✔ CopyDestrib: READY for high-level master events")

#         # запускаем high-level поток
#         async for mev in self.payload.run():

#             # если supervisor сказал "стоп" — выходим
#             if self._stop_signal_loop or self._stop_tracker or self.stop_flag():
#                 print("🛑 CopyDestrib: exit from HL loop")
#                 break

#             print(f"⚡ HL EVENT → {mev.event}: {mev.symbol} {mev.side}  {mev.payload}")

#             await self._broadcast_to_copies(mev)

#         print("🛑 CopyDestrib: signal_loop FINISHED")
