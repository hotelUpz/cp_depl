# # ============================================================
# # RUNTIME MANAGER
# # ============================================================
# from __future__ import annotations
# import copy
# from typing import Dict, Callable, Any

# from b_main_context import MainContext
# from c_log import ErrorHandler
# from b_network import NetworkManager
# from pos.pos_vars_setup import PosVarSetup

# # COPY_RUNTIME_STATE импортируется из a_config
# from a_config import COPY_RUNTIME_STATE, COPY_NUMBER


# class Runtime:
#     """
#     Управляет жизненным циклом runtime-состояний для всех копи-аккаунтов.
#     Создаёт runtime по требованию, закрывает, следит за сетевыми соединениями.
#     """

#     def __init__(
#             self,
#             mc: MainContext,
#             logger: ErrorHandler,
#             stop_flag: Callable
#         ):
#         self.mc = mc
#         self.logger = logger
#         self.stop_flag = stop_flag

#     # ------------------------------------------------------------
#     # PUBLIC API
#     # ------------------------------------------------------------
#     async def activate_copy(self, id: int):
#         """Активирует рантайм + регистрирует ID как активный."""
#         self.mc.active_copy_ids.add(id)
#         await self.ensure_runtime(id)

#     async def deactivate_copy(self, id: int):
#         """Отключает рантайм и чистит всё сетевое состояние."""
#         if id in self.mc.active_copy_ids:
#             self.mc.active_copy_ids.remove(id)
#             await self.shutdown_runtime(id)

#     # ------------------------------------------------------------
#     # INTERNAL RUNTIME CREATION
#     # ------------------------------------------------------------
#     async def ensure_runtime(self, id: int) -> Dict[str, Any]:
#         """
#         Создаёт runtime-состояние если его нет.
#         Инициализирует:
#         - closing=False
#         - position_vars по шаблону PosVarSetup
#         - NetworkManager + ping loop
#         """

#         # Уже есть — возвращаем
#         if id in self.mc.copy_runtime_states:
#             return self.mc.copy_runtime_states[id]

#         # === 1) создаём копию шаблона runtime ===
#         rt = copy.deepcopy(COPY_RUNTIME_STATE)
#         rt["id"] = id
#         rt["closing"] = False  # всегда явно ставим

#         # === 2) создаём сетевой Connector ===
#         proxy = self.mc.copy_configs[id]["exchange"].get("proxy")

#         rt["connector"] = NetworkManager(
#             logger=self.logger,
#             proxy_url=proxy,
#             stop_flag=self.stop_flag,
#         )
#         rt["connector"].start_ping_loop()

#         # === 3) Готовим позиционную структуру ===
#         #     instruments_data должен быть в MainContext
#         instruments = getattr(self.mc, "instruments_data", None)

#         # позиционное дерево:
#         # symbol → {LONG: {...}, SHORT: {...}}
#         position_vars = {}
#         rt["position_vars"] = position_vars

#         # Если instruments есть — подготовим по всем торгуемым парам MEXC.
#         # Реальный список symbols ты позже вставишь в MainContext.
#         if instruments:
#             for symbol in instruments:
#                 PosVarSetup.set_pos_defaults(
#                     position_vars=position_vars,
#                     symbol=symbol,
#                     instruments_data=instruments,
#                     reset_flag=True
#                 )
#         else:
#             # fallback: пустая структура, заполним позже когда появится сигнал
#             rt["position_vars"] = {}

#         # === 4) Регистрируем runtime ===
#         self.mc.copy_runtime_states[id] = rt
#         return rt

#     # ------------------------------------------------------------
#     # INTERNAL SHUTDOWN
#     # ------------------------------------------------------------
#     async def shutdown_runtime(self, id: int):
#         """Корректное завершение runtime-слоя."""
#         rt = self.mc.copy_runtime_states.get(id)
#         if not rt:
#             return

#         conn: NetworkManager = rt.get("connector")
#         if conn:
#             await conn.shutdown_session()

#         del self.mc.copy_runtime_states[id]




        # # ============================
        # #     STATUS(ID)
        # # ============================
        # if mode == "status_id":
        #     try:
        #         acc_id = int(raw)
        #         self._exit_input(chat_id)
        #         await self._send_status(msg, acc_id, reply_kb=self.menu_main())
        #     except:
        #         await msg.answer("❗ Неверный ID.")
        #     return






    # async def _handle_position(self, data: Dict[str, Any]) -> None:
    #     """
    #     push.personal.position
    #     """
    #     symbol = normalize_symbol(data.get("symbol", ""), self.quote_asset)
    #     if not symbol:
    #         return

    #     position_type = int(data.get("positionType", 0))  # 1 long, 2 short
    #     side = side_from_position_type(position_type)
    #     if side is None:
    #         return

    #     state = int(data.get("state", 0))  # 1 holding, 2 system holding, 3 closed
    #     hold_vol = float(data.get("holdVol", 0.0))

    #     if state in (1, 2) and hold_vol > 0:
    #         flag = "position_opened"
    #     elif state == 3 or hold_vol == 0:
    #         flag = "position_closed"
    #     else:
    #         flag = "raw"

    #     if flag != "raw":
    #         await self.cache.set_flag(symbol, side, flag, raw=data)
    #         await self._push_event(symbol, side, flag, data)



    # async def _handle_master_signal(self, event: SignalEvent):
    #     print(f"📡 SIGNAL: {event.event_type}  {event.symbol} {event.side}")
    #     print(f"    vol={event.vol}  price={event.price}  order_id={event.order_id}")

    #     # Покатим на копи-аккаунты:
    #     for idx, (cid, cfg) in enumerate(self.mc.copy_configs.items(), start=1):
    #         if not cfg.get("enabled"):
    #             continue

    #         asyncio.create_task(self.safe_exec(cid, event))




# # DESTRIBUTOR.copy_destrib.py
# from __future__ import annotations
# from b_context import *
# from c_log import ErrorHandler

# # master stream
# from MASTER.signal_cache import SignalCache, SignalEvent
# from .helpers import Runtime, SignalsHandler

# if TYPE_CHECKING:
#     from API.MX.client import MexcClient

# from pos.pos_vars_setup import PosVarSetup
# from MASTER.signal_tracker import MasterEvent
# from MASTER.signal_tracker import MasterOrderTracker


# class CopyDestrib:
#     def __init__(
#             self,
#             mc: MainContext,
#             logger: ErrorHandler,    
#             runtime: Runtime,      
#             signal_cache: SignalCache,
#             stop_flag: Callable,
#             ready: Callable
#         ):
#         self.mc = mc
#         self.logger = logger
#         self.stop_flag = stop_flag
#         self.runtime = runtime
#         self.signal_cache = signal_cache
#         self.ready = ready
#         self.tracker = None     

#     def attach_tracker(self, tracker: MasterOrderTracker):
#         self.tracker = tracker

#     # ============================================================
#     # ВРЕМЕННЫЙ EXECUTOR
#     # ============================================================
#     async def execute_copy_order(self, copy_id: int, event: SignalEvent):
#         """
#         Главный исполнитель зеркальных событий.
#         Здесь мы ничего не решаем вручную — только зеркалим мастера.
#         """

#         rt = await self.runtime.ensure_runtime(copy_id)
#         mc_client: MexcClient = rt["mc_client"]

#         # -----------------------------
#         # 1) ИНИЦИАЛИЗАЦИЯ position_vars
#         # -----------------------------
#         if "position_vars" not in rt:
#             rt["position_vars"] = {}

#         # безопасно создаём под-структуру -- в свете новой архитектуры сведем к минимуму либо полностью уберем. но лучше какой-то слепок оставить
#         PosVarSetup.set_pos_defaults(
#             position_vars=rt["position_vars"],
#             symbol=event.symbol,
#             pos_side=event.side,
#             instruments_data=self.mc.instruments_data,
#         )

#         pos = rt["position_vars"][event.symbol][event.side]

#         # ----------------------------------------
#         # 2) ROUTER — вызываем нужный обработчик
#         # ----------------------------------------
#         et = event.event_type
        
#         # -- тут все старое...
#         # if et in ("open_market", "open_limit"):
#         #     await SignalsHandler._copy_open(mc_client, rt, event, pos)
#         # elif et in ("close_market", "close_limit"):
#         #     await SignalsHandler._copy_close(mc_client, rt, event, pos)
#         # elif et in ("order_cancelled", "order_invalid"):
#         #     await SignalsHandler._copy_cancel(mc_client, rt, event, pos)
#         # elif et == "plan_order":
#         #     await SignalsHandler._copy_tp_sl_create(mc_client, rt, event, pos)
#         # elif et in ("plan_cancelled", "plan_executed"):
#         #     await SignalsHandler._copy_tp_sl_cancel(mc_client, rt, event, pos)
#         # elif et == "deal":
#         #     await SignalsHandler._on_deal(rt, event, pos)
#         # elif et == "position_opened":
#         #     await SignalsHandler._on_position_opened(rt, event, pos)
#         # elif et == "position_closed":
#         #     await SignalsHandler._on_position_closed(rt, event, pos)

#         print(
#             f"⚙ EXEC [{copy_id}] → {event.event_type} {event.symbol} {event.side} "
#             f"vol={event.vol} price={event.price}"
#         )

#     # ============================================================
#     # ОБРАБОТКА ОДНОГО СОБЫТИЯ
#     # ============================================================
#     async def _broadcast_to_copies(self, mev: MasterEvent):
#         """
#         Рассылаем HIGH-LEVEL события всем копи-аккаунтам.
#         Пока просто print, позже будет copy-executor.
#         """
#         for cid, cfg in self.mc.copy_configs.items():
#             if cid == 0:
#                 continue
#             if not cfg.get("enabled"):
#                 continue

#             # пока: печать
#             print(f"   → COPY[{cid}] handling {mev.event}")
#             try:
#                 asyncio.create_task(self.execute_copy_order(cid, mev.event))
#             except Exception as e:
#                 print(f"❗ ERROR exec copy[{cid}]: {e}")

#     # ============================================================
#     # РЕАКТИВНЫЙ ЛУП БЕЗ SLEEP(), БЕЗ ЗАДЕРЖЕК
#     # ============================================================

#     async def signal_loop(self):

#         # 1. Ждём включения мастера
#         while not self.stop_flag():
#             master_rt = self.mc.copy_configs.get(0, {}).get("runtime", {})
#             if master_rt.get("trading_enabled") and not master_rt.get("stop_flag"):
#                 break
#             await asyncio.sleep(0.1)

#         # 2. Ждём готовности websocket мастера
#         while not self.stop_flag():
#             if self.ready():
#                 break
#             await asyncio.sleep(0.1)

#         print("✔ CopyDestrib: READY for HIGH-LEVEL master events")

#         # 3. Слушаем HIGH-LEVEL поток
#         async for mev in self.tracker.run():
#             if self.stop_flag():
#                 break

#             print(f"⚡ HL EVENT → {mev.event}: {mev.symbol} {mev.side}  {mev.payload}")

#             # --- отправляем на копи-аккаунты ---
#             asyncio.create_task(self._broadcast_to_copies(mev))

