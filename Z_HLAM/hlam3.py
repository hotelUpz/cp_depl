# from __future__ import annotations

# import asyncio
# import time
# from typing import *

# from a_config import (
#     POSITIONS_LOOP_FREQUENCY,
#     COMMAND_LOOP_FREQUENCY,
#     SIGNAL_LOOP_FREQUENCY,
# )
# from b_network import NetworkManager
# from API.GATE.client import GateFuturesClient  # type: ignore[import]
# from c_log import ErrorHandler
# from c_utils import Utils
# from c_templates import OrderTemplates

# from .pos.pos_vars_setup import PosVarSetup
# from .pos.pos_monitor import PosMonitor
# from .pos.cleanup_fsm import PositionCleanupFSM
# from .loops.signal_loop import signal_loop
# from .loops.command_loop import command_loop
# from .loops.pos_monitoring_loop import pos_monitoring_loop

# # worker/worker.py


# NotifyCallable = Callable[[Dict[str, Any]], Awaitable[None]]


# def _now() -> float:
#     return time.time()


# def make_default_record(
#     symbol: str,
#     pos_side: str,
#     leverage: Optional[int],
#     entry_price: Optional[float],
#     order_type: str,
# ) -> Dict[str, Any]:
#     """
#     Локальный аналог default_record, без привязки к BotContext.
#     То, что отправляем в notifier как body.
#     """
#     return {
#         "symbol": symbol,
#         "pos_side": pos_side,
#         "leverage": leverage,
#         "order_type": order_type,
#         "entry_price": entry_price,
#         "entry_status": "waiting",

#         "tp1": None,
#         "tp1_status": "none",

#         "tp2": None,
#         "tp2_status": "none",

#         "sl": None,
#         "sl_status": "none",

#         "pnl_text": "PNL: сделка не завершена",
#     }


# async def notify_update(
#     notify: NotifyCallable,
#     user_id: int,
#     symbol: str,
#     pos_side: str,
#     record: Dict[str, Any],
# ) -> None:
#     """
#     Обновление якоря позиции.
#     """
#     report: Dict[str, Any] = {
#         "type": "worker_report",
#         "user_id": user_id,
#         "event": "update_position",
#         "symbol": symbol,
#         "pos_side": pos_side,
#         "body": record,
#     }
#     await notify(report)


# async def notify_event(
#     notify: NotifyCallable,
#     user_id: int,
#     event: str,
#     payload: Dict[str, Any],
# ) -> None:
#     """
#     Произвольное событие от worker'а.
#     """
#     data: Dict[str, Any] = {
#         "type": "worker_report",
#         "user_id": user_id,
#         "event": event,
#     }
#     data.update(payload)
#     await notify(data)


# class Worker:
#     """
#     Worker = чистый торговый процесс на одного пользователя.

#     ВАЖНО:
#     - trading_enabled: включает/выключает торговлю (при False сигналы игнорим).
#     - stop_flag: мягкий стоп (лупы завершаются, DI гасится).
#       УСТАНАВЛИВАЕТСЯ ТОЛЬКО ЧЕРЕЗ set_stop_flag(True) С ПРОВЕРКОЙ ПОЗИЦИЙ (UI).
#     """

#     def __init__(
#         self,
#         user_id: int,
#         user_config: Dict[str, Any],
#         user_position_vars: Dict[str, Any],
#         prices: Dict[str, float],
#         instruments_data: List[Dict[str, Any]],
#         signal_bus: "asyncio.Queue[dict]",
#         command_bus: "asyncio.Queue[dict]",
#         notify: NotifyCallable,
#         info_logger: ErrorHandler,
#     ):
#         self.user_id = user_id

#         # Единый источник настроек для КОНКРЕТНОГО юзера
#         self.user_config: Dict[str, Any] = user_config or {}

#         # ⚠️ ВАЖНО:
#         # В многопроцессной схеме Ray это локальный стейт актера.
#         # UI/Notifier получают правду о позициях через worker_report'ы.
#         self.user_position_vars: Dict[str, Any] = user_position_vars

#         self.instruments_data = instruments_data
#         self.prices = prices

#         self._refresh_user_cfg()

#         self.signal_bus = signal_bus
#         self.command_bus = command_bus
#         self.notify = notify

#         # состояние
#         self.trading_enabled: bool = False
#         self.stop_flag: bool = False

#         # DI-объекты
#         self.gate_client: Optional[GateFuturesClient] = None
#         self.templates: Optional[OrderTemplates] = None

#         # служебные таски
#         self._tasks: list[asyncio.Task] = []
#         self.info_logger = info_logger

#         # составные части (инициализируются в run)
#         self.pos_vars_setup: Optional[PosVarSetup] = None
#         self.connector: Optional[NetworkManager] = None
#         self.pos_monitor: Optional[PosMonitor] = None
#         self.cleanup_fsm: Optional[PositionCleanupFSM] = None

#     # ========================================================
#     #  CONFIG / FIN_SETTINGS HELPERS (без матрёшек)
#     # ========================================================

#     def _refresh_user_cfg(self) -> None:
#         """
#         Обновляем кеш fin_settings_root и gate_cfg из user_config
#         (единый источник истины для этого юзера).
#         """
#         cfg = self.user_config or {}

#         root = cfg.get("config", {}).get("fin_settings", {})
#         self.fin_settings_root = root if isinstance(root, dict) else {}

#         gate_cfg = cfg.get("config", {}).get("GATE", {}) or {}
#         self.gate_cfg = gate_cfg
#         self.api_key = gate_cfg.get("api_key")
#         self.api_secret = gate_cfg.get("api_secret")
#         self.proxy_url = gate_cfg.get("proxy_url")

#     def _get_fin_settings(self, settings_tag: str) -> Dict[str, Any]:
#         """
#         Берём настройки строго из fin_settings_root, который живёт в user_config.
#         """
#         if not isinstance(self.fin_settings_root, dict):
#             return {}
#         return self.fin_settings_root.get(settings_tag, {}) or {}

#     # ========================================================
#     #  ПУБЛИЧНЫЕ МЕТОДЫ ДЛЯ ORCHESTRATOR / WorkerActor
#     # ========================================================

#     async def set_trading_enabled(self, value: bool) -> None:
#         """
#         Включение/выключение торговли.
#         При False:
#         - сигнальные лупы продолжают жить, но новые сигналы просто игнорируются.
#         """
#         self.trading_enabled = value
#         self.info_logger.debug_info_notes(
#             f"[Worker {self.user_id}] trading_enabled = {value}",
#             is_print=True,
#         )

#     async def set_stop_flag(self, value: bool) -> None:
#         """
#         Мягкий стоп, вызванный снаружи (из UI через Orchestrator.set_stop_flag).

#         НОВАЯ ЛОГИКА:
#         - НИКАКИХ дополнительных проверок позиций здесь нет.
#           TG UI уже проверил, можно ли останавливать бота, до выставления флага.
#         - Если value == False:
#             - просто снимаем стоп-флаг (теоретически, для будущих рестартов).
#         - Если value == True:
#             - ставим stop_flag = True и trading_enabled = False;
#             - все внутренние лупы видят stop_flag и аккуратно завершаются;
#             - после завершения run() отработает _cleanup_after_run()
#               и отправит worker_report "worker_stopped".
#         """
#         self.stop_flag = bool(value)

#         if not value:
#             self.info_logger.debug_info_notes(
#                 f"[Worker {self.user_id}] stop_flag RESET (False)",
#                 is_print=True,
#             )
#             return

#         self.trading_enabled = False
#         self.info_logger.debug_info_notes(
#             f"[Worker {self.user_id}] soft stop requested "
#             f"(stop_flag=True, trading_disabled)",
#             is_print=True,
#         )

#     # ========================================================
#     #  ЖИЗНЕННЫЙ ЦИКЛ
#     # ========================================================

#     async def run(self) -> None:
#         """
#         Главный жизненный цикл воркера.

#         Сценарий:
#         - ждём, пока trading_enabled не станет True (или нас не убьют stop_flag'ом);
#         - инициализируем DI;
#         - запускаем лупы;
#         - ждём их завершения;
#         - чистим ресурсы, шлём worker_stopped.
#         """
#         self.info_logger.debug_info_notes(
#             f"[Worker {self.user_id}] run() waiting for trading_enabled...",
#             is_print=True,
#         )
#         while not self.trading_enabled and not self.stop_flag:
#             await asyncio.sleep(0.1)

#         if self.stop_flag:
#             self.info_logger.debug_info_notes(
#                 f"[Worker {self.user_id}] run() aborted before start (stop_flag=True)",
#                 is_print=True,
#             )
#             return

#         # перед запуском DI обновляем кеш конфигов (GATE + fin_settings)
#         self._refresh_user_cfg()

#         self.info_logger.debug_info_notes(
#             f"[Worker {self.user_id}] run() start",
#             is_print=True,
#         )

#         # создаём DI только здесь
#         self.pos_vars_setup = PosVarSetup()

#         self.connector = NetworkManager(
#             info_logger=self.info_logger,
#             proxy_url=self.proxy_url,
#             stop_flag=lambda: self.stop_flag,
#         )

#         self.gate_client = GateFuturesClient(
#             api_key=self.api_key,
#             api_secret=self.api_secret,
#             proxy_url=self.proxy_url,
#             session=self.connector.session,
#             stop_flag=lambda: self.stop_flag,
#             info_logger=self.info_logger,
#         )

#         self.templates = OrderTemplates(
#             info_logger=self.info_logger,
#             gate_client=self.gate_client,
#         )

#         self.pos_monitor = PosMonitor(
#             user_position_vars=self.user_position_vars,
#             fetch_positions=self.gate_client.fetch_positions,
#         )

#         self.cleanup_fsm = PositionCleanupFSM(
#             user_id=self.user_id,
#             user_position_vars=self.user_position_vars,
#             gate_client=self.gate_client,
#             notify=self.notify,
#             info_logger=self.info_logger,
#         )

#         self._tasks = [
#             asyncio.create_task(signal_loop(self), name=f"signal_loop_{self.user_id}"),
#             asyncio.create_task(command_loop(self), name=f"command_loop_{self.user_id}"),
#             asyncio.create_task(
#                 pos_monitoring_loop(self),
#                 name=f"pos_monitoring_loop_{self.user_id}",
#             ),
#         ]

#         try:
#             await asyncio.gather(*self._tasks, return_exceptions=True)
#         finally:
#             await self._cleanup_after_run()

#         self.info_logger.debug_info_notes(
#             f"[Worker {self.user_id}] run() finished",
#             is_print=True,
#         )

#     # ========================================================
#     #  ВНУТРЕННИЕ ХЕЛПЕРЫ
#     # ========================================================

#     async def _cleanup_after_run(self) -> None:
#         """
#         Завершение работы воркера:
#         - закрываем DI-объекты (по возможности),
#         - чистим кеши,
#         - шлём событие worker_stopped.
#         """
#         try:
#             if self.cleanup_fsm is not None:
#                 close = getattr(self.cleanup_fsm, "close", None)
#                 if callable(close):
#                     res = close()
#                     if asyncio.iscoroutine(res):
#                         await res
#         except Exception as e:  # noqa: BLE001
#             self.info_logger.debug_error_notes(
#                 f"[Worker {self.user_id}] error closing cleanup_fsm: {e}",
#                 is_print=True,
#             )

#         try:
#             if self.pos_monitor is not None:
#                 close = getattr(self.pos_monitor, "close", None)
#                 if callable(close):
#                     res = close()
#                     if asyncio.iscoroutine(res):
#                         await res
#         except Exception as e:  # noqa: BLE001
#             self.info_logger.debug_error_notes(
#                 f"[Worker {self.user_id}] error closing pos_monitor: {e}",
#                 is_print=True,
#             )

#         try:
#             if self.gate_client is not None:
#                 close = getattr(self.gate_client, "close", None)
#                 if callable(close):
#                     res = close()
#                     if asyncio.iscoroutine(res):
#                         await res
#         except Exception as e:  # noqa: BLE001
#             self.info_logger.debug_error_notes(
#                 f"[Worker {self.user_id}] error closing gate_client: {e}",
#                 is_print=True,
#             )

#         try:
#             if self.connector is not None:
#                 close = getattr(self.connector, "close", None)
#                 if callable(close):
#                     res = close()
#                     if asyncio.iscoroutine(res):
#                         await res
#         except Exception as e:  # noqa: BLE001
#             self.info_logger.debug_error_notes(
#                 f"[Worker {self.user_id}] error closing connector: {e}",
#                 is_print=True,
#             )

#         # чистим кеш позиций (локальный в акторе)
#         self.user_position_vars.clear()

#         try:
#             await self._notify_event(
#                 "worker_stopped",
#                 {"reason": "graceful_stop" if self.stop_flag else "loop_ended"},
#             )
#         except Exception as e:  # noqa: BLE001
#             self.info_logger.debug_error_notes(
#                 f"[Worker {self.user_id}] error sending worker_stopped: {e}",
#                 is_print=True,
#             )

#     # ========================================================
#     #  ОБРАБОТКА СИГНАЛОВ
#     # ========================================================

#     async def _handle_signal_message(self, msg: Dict[str, Any]) -> None:
#         """
#         Обработчик одного сигнала.

#         Ожидаемый формат msg:
#         {
#           "type": "signal",
#           "matched_tag": "soft" / "trading pair",
#           "parsed": {...},      # parsed_msg
#           "timestamp": 1739999999000
#         }
#         """
#         if self.stop_flag:
#             return

#         # дополнительный гард — чтобы никакой сигнал не прошёл при trading_enabled=False
#         if not self.trading_enabled:
#             return

#         parsed_msg = msg.get("parsed") or {}
#         settings_tag = (msg.get("matched_tag") or "").strip()
#         ts_ms = msg.get("timestamp") or int(_now() * 1000)

#         symbol = parsed_msg.get("symbol")
#         pos_side = (parsed_msg.get("pos_side") or "").upper()

#         if not symbol or pos_side not in {"LONG", "SHORT"}:
#             await self._notify_event(
#                 "signal_rejected",
#                 {"reason": "missing symbol/pos_side", "raw": msg},
#             )
#             return

#         # fin_settings только из user_config
#         fin_settings = self._get_fin_settings(settings_tag)

#         if not fin_settings:
#             await self._notify_event(
#                 "signal_rejected",
#                 {
#                     "reason": f"fin_settings not found for tag='{settings_tag}'",
#                     "raw": msg,
#                 },
#             )
#             return

#         order_timeout = fin_settings.get("order_timeout", 60)
#         diff_sec = _now() - (ts_ms / 1000.0)
#         if diff_sec > order_timeout:
#             await self._notify_event(
#                 "signal_rejected",
#                 {
#                     "reason": f"signal too old ({diff_sec:.1f}s > {order_timeout}s)",
#                     "raw": msg,
#                 },
#             )
#             return

#         # инициализация pos_vars in-place
#         assert self.pos_vars_setup is not None
#         ok = self.pos_vars_setup.set_pos_defaults(
#             user_position_vars=self.user_position_vars,
#             symbol=symbol,
#             pos_side=pos_side,
#             instruments_data=self.instruments_data,
#             reset_flag=False,
#         )
#         if not ok:
#             await self._notify_event(
#                 "signal_rejected",
#                 {"reason": "pos_vars_setup failed (no instruments/specs)", "raw": msg},
#             )
#             return

#         symbol_data = self.user_position_vars[symbol]
#         pos_data = symbol_data[pos_side]

#         if pos_data.get("in_position") or pos_data.get("pending_open"):
#             self.info_logger.debug_info_notes(
#                 f"[Worker {self.user_id}] Skip: already in_position or pending {symbol} {pos_side}",
#                 is_print=True,
#             )
#             return

#         pos_data["settings_tag"] = settings_tag

#         max_leverage = symbol_data.get("spec", {}).get("max_leverage", 20)
#         leverage = (
#             fin_settings.get("leverage")
#             or parsed_msg.get("leverage")
#             or max_leverage
#         )
#         leverage = min(leverage, max_leverage)
#         pos_data["leverage"] = leverage
#         pos_data["margin_vol"] = fin_settings.get("margin_size", 0.0)

#         cur_price = self.prices.get(symbol)
#         if cur_price is None:
#             await self._notify_event(
#                 "signal_rejected",
#                 {
#                     "reason": "no current price for symbol",
#                     "symbol": symbol,
#                     "raw": msg,
#                 },
#             )
#             return

#         fix_price_scale = Utils.fix_price_scale
#         for key in (
#             "entry_price",
#             "take_profit1",
#             "take_profit2",
#             "stop_loss",
#             "take_profit",
#         ):
#             if key in parsed_msg:
#                 parsed_msg[key] = fix_price_scale(parsed_msg.get(key), cur_price)

#         print("await self._complete_signal_task")
#         await self._complete_signal_task(
#             parsed_msg=parsed_msg,
#             fin_settings=fin_settings,
#             symbol_data=symbol_data,
#             pos_data=pos_data,
#             last_timestamp=ts_ms,
#             cur_price=cur_price,
#         )

#     async def _complete_signal_task(
#         self,
#         parsed_msg: Dict[str, Any],
#         fin_settings: Dict[str, Any],
#         symbol_data: Dict[str, Any],
#         pos_data: Dict[str, Any],
#         last_timestamp: int,
#         cur_price: float,
#     ) -> None:
#         """
#         Логика открытия позиции (без Telegram-зависимостей).
#         """
#         if self.stop_flag:
#             return

#         symbol = parsed_msg.get("symbol")
#         pos_side = parsed_msg.get("pos_side")
#         pos_side_u = (pos_side or "").upper()

#         pos_data["pending_open"] = True

#         leverage = pos_data.get("leverage")
#         entry_price = parsed_msg.get("entry_price")
#         stop_loss = parsed_msg.get("stop_loss")

#         spec = symbol_data.get("spec", {})
#         price_precision = spec.get("price_precision", 4)

#         order_type_cfg = fin_settings.get("order_type")
#         force_limit: bool = bool(parsed_msg.get("force_limit"))
#         half_margin: bool = bool(parsed_msg.get("half_margin"))

#         settings_order_type = "limit" if order_type_cfg == 1 else "market"
#         order_type = "limit" if force_limit else settings_order_type

#         try:
#             record = make_default_record(
#                 symbol=symbol,
#                 pos_side=pos_side_u,
#                 leverage=leverage,
#                 entry_price=round(float(entry_price), price_precision)
#                 if entry_price
#                 else None,
#                 order_type=order_type,
#             )

#             take_profits = Utils.build_take_profits(
#                 parsed_msg=parsed_msg,
#                 dop_tp=fin_settings.get("dop_tp"),
#                 price_precision=price_precision,
#                 pos_side=pos_side_u,
#                 entry_price=entry_price,
#             )

#             if not take_profits:
#                 record["tp1_status"] = "Invalid data"
#                 record["tp2_status"] = "Invalid data"
#             else:
#                 risk_sl_ok_status = Utils.validate_risk_order(
#                     pos_side=pos_side_u,
#                     cur_price=cur_price,
#                     sl=stop_loss,
#                     tp=None,
#                     epsilon_pct=0.05,
#                 )
#                 if risk_sl_ok_status != "ok":
#                     record["entry_status"] = risk_sl_ok_status

#                 for tp_val, _vol in take_profits:
#                     risk_tp_ok_status = Utils.validate_risk_order(
#                         pos_side=pos_side_u,
#                         cur_price=cur_price,
#                         sl=None,
#                         tp=tp_val,
#                         epsilon_pct=0.05,
#                     )
#                     if risk_tp_ok_status != "ok":
#                         record["entry_status"] = risk_tp_ok_status
#                         break

#             if record["entry_status"] != "waiting" or record.get("tp1_status") == "Invalid data":
#                 await self._notify_update(symbol, pos_side_u, record)
#                 return

#             assert self.templates is not None
#             order_template_response = await self.templates.initial_order_template(
#                 record=record,
#                 fin_settings=fin_settings,
#                 symbol=symbol,
#                 leverage=leverage,
#                 entry_price=entry_price,
#                 pos_side=pos_side_u,
#                 symbol_data=symbol_data,
#                 pos_data=pos_data,
#                 stop_loss=stop_loss,
#                 take_profits=take_profits,
#                 order_type=order_type,
#                 half_margin=half_margin,
#             )

#             await self._notify_update(symbol, pos_side_u, record)

#             if order_type == "limit" and order_template_response:
#                 asyncio.create_task(
#                     self._complete_until_cancel(
#                         fin_settings=fin_settings,
#                         symbol=symbol,
#                         pos_side=pos_side_u,
#                         pos_data=pos_data,
#                         record=record,
#                         last_timestamp=last_timestamp,
#                     )
#                 )
#         finally:
#             pos_data["pending_open"] = False

#     async def _complete_until_cancel(
#         self,
#         fin_settings: Dict[str, Any],
#         symbol: str,
#         pos_side: str,
#         pos_data: Dict[str, Any],
#         record: Dict[str, Any],
#         last_timestamp: int,  # noqa: ARG002
#     ) -> bool:
#         """
#         Ожидание открытия лимитного ордера до таймаута.
#         Если не открылся — отмена (через gate_client).
#         """
#         debug_label = f"[complete_until_cancel_{symbol}_{pos_side}]"
#         self.info_logger.debug_info_notes(
#             f"{debug_label} Waiting for position to open",
#             is_print=True,
#         )

#         start_time = _now()
#         timeout = fin_settings.get("order_timeout", 30)

#         try:
#             while (_now() - start_time) < timeout and not self.stop_flag:
#                 if pos_data.get("in_position"):
#                     self.info_logger.debug_info_notes(
#                         f"{debug_label} Position opened successfully",
#                         is_print=True,
#                     )
#                     record["entry_status"] = "filled"
#                     await self._notify_update(symbol, pos_side, record)
#                     return True
#                 await asyncio.sleep(0.1)

#             if self.stop_flag:
#                 self.info_logger.debug_info_notes(
#                     f"{debug_label} interrupted by stop_flag",
#                     is_print=True,
#                 )
#                 return False

#             self.info_logger.debug_info_notes(
#                 f"{debug_label} Timeout: Position not opened within {timeout} seconds",
#                 is_print=True,
#             )
#             record["entry_status"] = "failed. Reason: TIME-OUT"

#             try:
#                 assert self.gate_client is not None
#                 cancel_result = await self.gate_client.cancel_all_orders_by_symbol_and_side(
#                     instId=symbol,
#                     pos_side=pos_side,
#                 )

#                 if cancel_result is None:
#                     self.info_logger.debug_info_notes(
#                         f"{debug_label} cancel_all_orders_by_symbol_and_side not implemented",
#                         is_print=True,
#                     )
#                     return False

#                 main_cancelled = cancel_result.get("main_cancelled_count", 0)
#                 price_cancelled = cancel_result.get("price_cancelled_count", 0)

#                 if main_cancelled > 0 or price_cancelled > 0:
#                     self.info_logger.debug_info_notes(
#                         f"{debug_label} Cancelled {main_cancelled} main orders and {price_cancelled} trigger orders",
#                         is_print=True,
#                     )
#                     record.update(
#                         {
#                             "tp1_status": "cancelled",
#                             "tp2_status": "cancelled",
#                             "sl_status": "cancelled",
#                         }
#                     )

#                 return main_cancelled > 0 or price_cancelled > 0

#             except Exception as e:  # noqa: BLE001
#                 self.info_logger.debug_error_notes(
#                     f"{debug_label} Cancellation error: {str(e)}",
#                     is_print=True,
#                 )
#                 pos_data["order_id"] = None
#                 return False
#         finally:
#             await self._notify_update(symbol, pos_side, record)

#     # ========================================================
#     #  КОМАНДЫ: MODIFY SL / TP / FORCE CLOSE
#     # ========================================================

#     async def _handle_trading_command(self, cmd: Dict[str, Any]) -> None:
#         if self.stop_flag:
#             return

#         ctype = cmd.get("type")
#         symbol = cmd.get("symbol")
#         pos_side = (cmd.get("pos_side") or "").upper()

#         if not symbol or pos_side not in {"LONG", "SHORT"}:
#             self.info_logger.debug_error_notes(
#                 f"[Worker {self.user_id}] invalid trading command: {cmd}",
#                 is_print=True,
#             )
#             return

#         symbol_data = self.user_position_vars.get(symbol) or {}
#         pos_data = symbol_data.get(pos_side, {})

#         if ctype == "modify_sl":
#             await self._cmd_modify_sl(symbol, pos_side, pos_data, cmd.get("new_sl"))
#         elif ctype == "modify_tp":
#             tp_index = int(cmd.get("tp_index") or 1)
#             await self._cmd_modify_tp(
#                 symbol,
#                 pos_side,
#                 pos_data,
#                 tp_index,
#                 cmd.get("price"),
#                 cmd.get("percent"),
#             )
#         elif ctype == "force_close":
#             await self._cmd_force_close(
#                 symbol,
#                 pos_side,
#                 pos_data,
#                 cmd.get("close_type") or "market",
#             )

#     async def _cmd_modify_sl(
#         self,
#         symbol: str,
#         pos_side: str,
#         pos_data: Dict[str, Any],
#         new_sl: Optional[float],
#     ) -> None:
#         """
#         Обработка команды modify_sl (от кнопки).
#         """
#         if not pos_data.get("in_position"):
#             await self._notify_event(
#                 "command_rejected",
#                 {
#                     "symbol": symbol,
#                     "pos_side": pos_side,
#                     "reason": "position not active",
#                     "command": "modify_sl",
#                 },
#             )
#             return

#         spec = self.user_position_vars[symbol].get("spec", {})
#         price_precision = spec.get("price_precision", 4)

#         record = make_default_record(
#             symbol=symbol,
#             pos_side=pos_side,
#             leverage=pos_data.get("leverage"),
#             entry_price=pos_data.get("entry_price"),
#             order_type="market",
#         )
#         record["sl"] = round(float(new_sl), price_precision) if new_sl is not None else None

#         settings_tag = pos_data.get("settings_tag") or "soft"
#         fin_settings = self._get_fin_settings(settings_tag)

#         assert self.templates is not None
#         ok = await self.templates.modify_risk_orders(
#             record=record,
#             symbol=symbol,
#             pos_side=pos_side,
#             fin_settings=fin_settings,
#             symbol_data=self.user_position_vars[symbol],
#             pos_data=pos_data,
#             modify_sl=True,
#             new_sl=new_sl,
#             modify_tp=False,
#             new_tp=None,
#             tp_index=None,
#         )

#         if ok:
#             await self._notify_update(symbol, pos_side, record)
#         else:
#             await self._notify_event(
#                 "command_failed",
#                 {
#                     "symbol": symbol,
#                     "pos_side": pos_side,
#                     "command": "modify_sl",
#                 },
#             )

#     async def _cmd_modify_tp(
#         self,
#         symbol: str,
#         pos_side: str,
#         pos_data: Dict[str, Any],
#         tp_index: int,
#         price: Optional[float],
#         percent: Optional[float],
#     ) -> None:
#         if not pos_data.get("in_position"):
#             await self._notify_event(
#                 "command_rejected",
#                 {
#                     "symbol": symbol,
#                     "pos_side": pos_side,
#                     "reason": "position not active",
#                     "command": "modify_tp",
#                 },
#             )
#             return

#         spec = self.user_position_vars[symbol].get("spec", {})
#         price_precision = spec.get("price_precision", 4)

#         record = make_default_record(
#             symbol=symbol,
#             pos_side=pos_side,
#             leverage=pos_data.get("leverage"),
#             entry_price=pos_data.get("entry_price"),
#             order_type="market",
#         )
#         if price is not None and percent is not None:
#             record[f"tp{tp_index}"] = (
#                 round(float(price), price_precision),
#                 float(percent),
#             )

#         settings_tag = pos_data.get("settings_tag") or "soft"
#         fin_settings = self._get_fin_settings(settings_tag)

#         assert self.templates is not None
#         ok = await self.templates.modify_risk_orders(
#             record=record,
#             symbol=symbol,
#             pos_side=pos_side,
#             fin_settings=fin_settings,
#             symbol_data=self.user_position_vars[symbol],
#             pos_data=pos_data,
#             modify_sl=False,
#             new_sl=None,
#             modify_tp=True,
#             new_tp=(price, percent),
#             tp_index=tp_index,
#         )

#         if ok:
#             await self._notify_update(symbol, pos_side, record)
#         else:
#             await self._notify_event(
#                 "command_failed",
#                 {
#                     "symbol": symbol,
#                     "pos_side": pos_side,
#                     "command": "modify_tp",
#                 },
#             )

#     async def _cmd_force_close(
#         self,
#         symbol: str,
#         pos_side: str,
#         pos_data: Dict[str, Any],
#         close_type: str,
#     ) -> None:
#         if not pos_data.get("in_position"):
#             await self._notify_event(
#                 "command_rejected",
#                 {
#                     "symbol": symbol,
#                     "pos_side": pos_side,
#                     "reason": "position not active",
#                     "command": "force_close",
#                 },
#             )
#             return

#         record = make_default_record(
#             symbol=symbol,
#             pos_side=pos_side,
#             leverage=pos_data.get("leverage"),
#             entry_price=pos_data.get("entry_price"),
#             order_type="market",
#         )

#         settings_tag = pos_data.get("settings_tag") or "soft"
#         fin_settings = self._get_fin_settings(settings_tag)

#         assert self.templates is not None
#         ok = await self.templates.force_position_close(
#             symbol=symbol,
#             pos_side=pos_side,
#             fin_settings=fin_settings,
#             pos_data=pos_data,
#             record=record,
#             close_type=close_type,
#         )

#         if ok:
#             await self._notify_update(symbol, pos_side, record)
#         else:
#             await self._notify_event(
#                 "command_failed",
#                 {
#                     "symbol": symbol,
#                     "pos_side": pos_side,
#                     "command": "force_close",
#                 },
#             )

#     # ========================================================
#     #  NOTIFY HELPERS
#     # ========================================================

#     async def _notify_update(
#         self,
#         symbol: str,
#         pos_side: str,
#         record: Dict[str, Any],
#     ) -> None:
#         await notify_update(self.notify, self.user_id, symbol, pos_side, record)

#     async def _notify_event(
#         self,
#         event: str,
#         payload: Dict[str, Any],
#     ) -> None:
#         await notify_event(self.notify, self.user_id, event, payload)






# if now() - details.get("created_at") >= CONFIG_TTL:




# def parse_id_range(raw: str) -> List[int]:
#     """
#     Пример вводов:
#     "5" → [5]
#     "3-8" → [3,4,5,6,7,8]
#     "1, 4, 6-8"
#     """
#     result = []
#     parts = raw.replace(" ", "").split(",")

#     for part in parts:
#         if "-" in part:
#             a,b = part.split("-")
#             a = int(a); b = int(b)
#             result.extend(range(a, b+1))
#         else:
#             result.append(int(part))

#     # фильтруем недопустимые
#     return [cid for cid in result if 1 <= cid <= COPY_NUMBER]




# # ============================================================
# # RUNTIME MANAGER
# # ============================================================
# class Runtime:
#     def __init__(
#             self,
#             mc: MainContext,
#             logger: ErrorHandler,
#             stop_flag: Callable
#         ):
#         self.mc = mc
#         self.logger = logger
#         self.stop_flag = stop_flag

#     async def activate_copy(self, id: int):
#         self.mc.active_copy_ids.add(id)
#         await self.ensure_runtime(id)

#     async def deactivate_copy(self, id: int):
#         if id in self.mc.active_copy_ids:
#             self.mc.active_copy_ids.remove(id)
#             await self.shutdown_runtime(id)

#     async def ensure_runtime(self, id: int) -> Dict[str, Any]:

#         if id in self.mc.copy_runtime_states:
#             return self.mc.copy_runtime_states[id]
        
#         rt = copy.deepcopy(COPY_RUNTIME_STATE)
#         rt["id"] = id

#         proxy = self.mc.copy_configs[id]["exchange"].get("proxy")

#         rt["connector"] = NetworkManager(
#             logger=self.logger,
#             proxy_url=proxy,
#             stop_flag=self.stop_flag
#         )
#         rt["connector"].start_ping_loop()

#         self.mc.copy_runtime_states[id] = rt
#         return rt


#     async def shutdown_runtime(self, id: int):
#         rt = self.mc.copy_runtime_states.get(id)
#         if not rt:
#             return

#         conn: NetworkManager = rt.get("connector")
#         if conn:
#             await conn.shutdown_session()

#         del self.mc.copy_runtime_states[id]


# class CopyDestrib:
#     def __init__(
#             self,
#             mc: MainContext,
#             logger: ErrorHandler,            
#             signal_cache: SignalCache,
#             stop_flag: Callable,
#         ):
#         self.mc = mc
#         self.logger = logger
#         self.stop_flag = stop_flag
#         self.signal_cache = signal_cache

#     # ============================================================
#     # ВРЕМЕННЫЙ EXECUTOR
#     # ============================================================
#     async def execute_copy_order(self, copy_id: int, event: SignalEvent):
#         print(
#             f"⚙ EXEC [{copy_id}] → {event.event_type} {event.symbol} {event.side} "
#             f"vol={event.vol} price={event.price}"
#         )

#     # ============================================================
#     # ОБРАБОТКА ОДНОГО СОБЫТИЯ
#     # ============================================================
#     async def _handle_master_signal(self, event: SignalEvent):
#         print(f"📡 SIGNAL: {event.event_type}  {event.symbol} {event.side}")
#         print(f"    vol={event.vol}  price={event.price}  order_id={event.order_id}")

#         # Покатим на копи-аккаунты:
#         for idx, (cid, cfg) in enumerate(self.mc.copy_configs.items(), start=1):
#             # if not cfg.get("enabled"):
#             #     continue

#             await self.execute_copy_order(cid, event)

#     # ============================================================
#     # РЕАКТИВНЫЙ ЛУП БЕЗ SLEEP(), БЕЗ ЗАДЕРЖЕК
#     # ============================================================
#     async def signal_loop(self):
#         cache = self.signal_cache

#         while not self.stop_flag():

#             # 🔥 ждём, пока WS-стрим добавит событие
#             await cache._event_notify.wait()

#             if self.stop_flag():
#                 break

#             # # # торговля включена?
#             # master_rt = self.mc.copy_configs.get(0, {}).get("runtime", {})
#             # if not master_rt.get("trading_enabled") or master_rt.get("stop_flag"):
#             #     await cache.pop_events()
#             #     continue

#             # получаем пачку событий
#             events = await cache.pop_events()
#             if not events:
#                 continue

#             for ev in events:
#                 try:
#                     await self._handle_master_signal(ev)
#                 except Exception as e:
#                     print(f"❗ error in signal handler: {e}")