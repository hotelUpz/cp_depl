# # main.py
# from __future__ import annotations

# import asyncio
# import multiprocessing as mp
# import signal
# import time
# import traceback
# from typing import Any

# # ============================================================
# # CORE PROCESS
# # ============================================================

# def core_process(cmd_q: mp.Queue):
#     """
#     Трейдинг-процесс.
#     НИКАКОГО aiogram здесь.
#     """
#     async def core_main():
#         print("[CORE] started")

#         # ====== здесь твой реальный CoreApp ======
#         from b_context import MainContext
#         from c_log import UnifiedLogger
#         from COPY.state_ import CopyState
#         from MASTER.signal_fsm_ import SignalFSM

#         mc = MainContext()
#         mc.load_accounts()

#         logger = UnifiedLogger(name="core", context="CORE")
#         stop_flag = False

#         copy_state = CopyState(mc=mc, logger=logger, stop_flag=lambda: stop_flag)

#         signal_fsm = SignalFSM(
#             mc=mc,
#             logger=logger,
#             copy_state=copy_state,
#             stop_flag=lambda: stop_flag,
#         )

#         fsm_task = asyncio.create_task(signal_fsm.master_supervisor())

#         # ====== command loop ======
#         try:
#             while True:
#                 await asyncio.sleep(0.05)

#                 while not cmd_q.empty():
#                     cmd: dict[str, Any] = cmd_q.get_nowait()
#                     c = cmd.get("cmd")

#                     if c == "ACTIVATE_COPY":
#                         cid = cmd["cid"]
#                         print(f"[CORE] activate copy {cid}")
#                         await copy_state.activate_copy(cid)

#                     elif c == "DEACTIVATE_COPY":
#                         cid = cmd["cid"]
#                         print(f"[CORE] deactivate copy {cid}")
#                         await copy_state.deactivate_copy(cid)

#                     elif c == "STOP_ALL":
#                         print("[CORE] STOP_ALL received")
#                         raise KeyboardInterrupt

#         except KeyboardInterrupt:
#             print("[CORE] stopping")

#         finally:
#             fsm_task.cancel()
#             with contextlib.suppress(asyncio.CancelledError):
#                 await fsm_task

#             for cid in list(mc.copy_runtime_states.keys()):
#                 await copy_state.shutdown_runtime(cid)

#             print("[CORE] stopped cleanly")

#     import contextlib
#     try:
#         asyncio.run(core_main())
#     except Exception:
#         traceback.print_exc()


# # ============================================================
# # TELEGRAM PROCESS
# # ============================================================

# def tg_process(cmd_q: mp.Queue):
#     """
#     Telegram-процесс.
#     НИКАКОГО трейдинга здесь.
#     """
#     async def tg_main():
#         print("[TG] started")

#         from aiogram import Bot, Dispatcher
#         from aiogram.filters import Command
#         from aiogram.types import Message
#         from a_config import TG_BOT_TOKEN, ADMIN_CHAT_ID

#         bot = Bot(TG_BOT_TOKEN)
#         dp = Dispatcher()

#         @dp.message(Command("copy_on"))
#         async def copy_on(msg: Message):
#             cid = int(msg.text.split()[1])
#             cmd_q.put({"cmd": "ACTIVATE_COPY", "cid": cid})
#             await msg.answer(f"Copy {cid} activating")

#         @dp.message(Command("copy_off"))
#         async def copy_off(msg: Message):
#             cid = int(msg.text.split()[1])
#             cmd_q.put({"cmd": "DEACTIVATE_COPY", "cid": cid})
#             await msg.answer(f"Copy {cid} deactivated")

#         @dp.message(Command("stop"))
#         async def stop_all(msg: Message):
#             if msg.from_user.id == ADMIN_CHAT_ID:
#                 cmd_q.put({"cmd": "STOP_ALL"})
#                 await msg.answer("Stopping system")

#         await dp.start_polling(bot)

#     try:
#         asyncio.run(tg_main())
#     except KeyboardInterrupt:
#         print("[TG] stopped")
#     except Exception:
#         traceback.print_exc()


# # ============================================================
# # ENTRYPOINT
# # ============================================================

# if __name__ == "__main__":
#     mp.set_start_method("spawn", force=True)

#     cmd_q = mp.Queue()

#     core = mp.Process(target=core_process, args=(cmd_q,), name="CORE")
#     tg = mp.Process(target=tg_process, args=(cmd_q,), name="TG")

#     core.start()
#     tg.start()

#     try:
#         while core.is_alive() and tg.is_alive():
#             time.sleep(0.5)

#     except KeyboardInterrupt:
#         print("[MAIN] Ctrl+C")

#     finally:
#         cmd_q.put({"cmd": "STOP_ALL"})
#         core.join(timeout=5)
#         tg.terminate()
#         tg.join(timeout=2)

#         print("[MAIN] exit")




    # async def _handle_copy_event(
    #     self,
    #     cid: int,
    #     cfg: dict,
    #     rt: dict,
    #     mev: "MasterEvent",
    #     monitors: Dict[int, PosMonitorFSM],
    # ):
    #     try:
    #         client: "MexcClient" = await FetchState.get_mx_client(self.copy_state, cid)
    #         if not client:
    #             return
    #     except Exception:
    #         traceback.print_exc()
    #         return

    #     # FSM (локальный, per-event)
    #     if cid not in monitors:
    #         monitors[cid] = PosMonitorFSM(
    #             rt["position_vars"],
    #             client.fetch_positions,
    #         )

    #     copy_pv = FetchState.get_copy_pos(rt, mev.symbol, mev.pos_side)

    #     spec = (
    #         self.mc.pos_vars_root
    #         .get(mev.symbol, {})
    #         .get("spec", {})
    #     )

    #     intent: CopyOrderIntent | None = self.intent_factory.build(
    #         cfg=cfg,
    #         mev=mev,
    #         copy_pv=copy_pv,
    #         spec=spec,
    #     )

    #     if not intent:
    #         print("not intent")
    #         return

    #     # if TEST_MODE:
    #     #     self.logger.debug(f"[TEST] intent={asdict(intent)}")
    #     #     return
        
    #     if TEST_MODE: await asyncio.sleep(5.0 + random.uniform(0.15, 0.6))

    #     # LOG-ONLY
    #     if mev.sig_type == "log":
    #         return

    #     if intent.delay_ms:
    #         await asyncio.sleep(intent.delay_ms / 1000)

    #     anchor = f"{intent.symbol} {intent.position_side}"

    #     # ---------------- CLOSE ----------------
    #     if mev.closed:
    #         if rt.get("cmd_closing"):
    #             return
            
    #         if not intent.contracts:
    #             self.mc.log_events.append(
    #                 (cid, f"{mev.symbol} {mev.pos_side} :: INTENT DROPPED (qty<=0 after coef/clamp)")
    #             )

    #         res = await client.make_order(
    #             symbol=intent.symbol,
    #             contract=intent.contracts,
    #             side=intent.side,
    #             position_side=intent.position_side,
    #             leverage=intent.leverage,
    #             open_type=intent.open_type,
    #             market_type="MARKET",
    #             debug=True,
    #         )

    #         if not res or not res.get("success"):
    #             reason = res.get("reason") if res else "UNKNOWN"
    #             self.mc.log_events.append(
    #                 (cid, f"{anchor} :: CLOSE FAILED: {reason}")
    #             )
    #         return

    #     # ---------------- MARKET / LIMIT ----------------
    #     if intent.method in ("MARKET", "LIMIT"):
    #         res = await client.make_order(
    #             symbol=intent.symbol,
    #             contract=intent.contracts,
    #             side=intent.side,
    #             position_side=intent.position_side,
    #             leverage=intent.leverage,
    #             open_type=intent.open_type,
    #             price=intent.price if intent.method == "LIMIT" else None,
    #             stopLossPrice=intent.sl_price,
    #             takeProfitPrice=intent.tp_price,
    #             market_type=intent.method,
    #             debug=True,
    #         )

    #         if not res or not res.get("success"):
    #             reason = res.get("reason") if res else "UNKNOWN"
    #             self.mc.log_events.append(
    #                 (cid, f"{anchor} :: {intent.method} FAILED: {reason}")
    #             )






# @dataclass
# class CopyOrderIntent:
#     # --- required ---
#     symbol: str
#     side: str                 # BUY / SELL
#     position_side: str        # LONG / SHORT
#     contracts: float
#     method: Literal["MARKET", "LIMIT", "TRIGGER"]

#     # --- optional ---
#     leverage: int | None = None
#     open_type: Optional[int] = None

#     price: Optional[str] = None
#     trigger_price: Optional[str] = None
#     sl_price: Optional[str] = None
#     tp_price: Optional[str] = None

#     delay_ms: int = 0


# class CopyOrderIntentFactory:
#     """
#     Единственная точка кастомизации ИНИЦИИРУЮЩИХ ордеров.
#     CLOSE здесь не существует.
#     """

#     def build(
#         self,
#         cfg: Dict,
#         mev: "MasterEvent",
#         copy_pv: Dict,
#         spec: Dict
#     ) -> Optional[CopyOrderIntent]:

#         payload = mev.payload or {}

#         # --------------------------------------------------
#         # 3️⃣ LEVERAGE
#         # --------------------------------------------------
#         leverage = (
#             cfg.get("leverage")
#             or payload.get("leverage")
#             or copy_pv.get("leverage")
#             or FALLBACK_LEVERAGE
#         )

#         max_lev = spec.get("max_leverage")
#         if max_lev:
#             leverage = min(int(leverage), int(max_lev))
#         leverage = int(leverage)

#         # --------------------------------------------------
#         # 4️⃣ OPEN TYPE
#         # --------------------------------------------------
#         open_type = (
#             cfg.get("margin_mode")
#             or payload.get("open_type")
#             or copy_pv.get("margin_mode")
#             or FALLBACK_MARGIN_MODE
#         )
#         open_type = int(open_type)

#         sl_price = None
#         tp_price = None
#         price = None
#         trigger_price = None
#         delay_ms = 0

#         if mev.closed:
#             qty = copy_pv.get("qty")  # нужно так. того тербует новая архитектура. прими за истину

#         else:
#             qty = float(payload.get("qty", 0.0))
#             if qty <= 0:
#                 print(
#                     "[INTENT SKIP] qty<=0",
#                     "event=", mev.event,
#                     "method=", mev.method,
#                     "symbol=", mev.symbol,
#                     "pos_side=", mev.pos_side,
#                     "payload=", payload,
#                 )
#                 return None
            
#             old_qty = qty

#             # --------------------------------------------------
#             # 1️⃣ COEF
#             # --------------------------------------------------
#             coef = float(cfg.get("coef", 1.0))
#             if coef and coef != 1:
#                 qty *= coef

#             # --------------------------------------------------
#             # 2️⃣ RANDOM SIZE
#             # --------------------------------------------------
#             lo, hi = cfg.get("random_size_pct", (0.0, 0.0))
#             if lo or hi:
#                 rnd = random.uniform(lo, hi)
#                 qty *= 1 + rnd / 100

#             if qty != old_qty:
#                 qty = self._clamp_by_max_margin(
#                     contracts=qty,
#                     cfg=cfg,
#                     price=payload.get("price") or copy_pv.get("entry_price"),
#                     leverage=leverage,
#                     spec=spec,
#                 )
#                 if qty <= 0:
#                     return None

#             # --------------------------------------------------
#             # 6️⃣ DELAY
#             # --------------------------------------------------
#             delay_ms = int(cfg.get("delay_ms", 0))
#             if delay_ms > 0:
#                 delay_ms = int(random.uniform(0, delay_ms))

#             price_precision = None
#             if spec and spec.get("price_precision"): price_precision = spec.get("price_precision")

#             if payload.get("price"):
#                 raw = Utils.safe_float(payload.get("price"))
#                 if price_precision is not None:
#                     raw = round(raw, price_precision)
#                 price = Utils.to_human_digit(raw)

#             if payload.get("trigger_price"):
#                 raw = Utils.safe_float(payload.get("trigger_price"))
#                 if price_precision is not None:
#                     raw = round(raw, price_precision)
#                 trigger_price = Utils.to_human_digit(raw)

#             if payload.get("sl_price"):
#                 raw = Utils.safe_float(payload.get("sl_price"))
#                 if price_precision is not None:
#                     raw = round(raw, price_precision)
#                 sl_price = Utils.to_human_digit(raw)

#             if payload.get("tp_price"):
#                 raw = Utils.safe_float(payload.get("tp_price"))
#                 if price_precision is not None:
#                     raw = round(raw, price_precision)
#                 tp_price = Utils.to_human_digit(raw)                  

#         return CopyOrderIntent(
#             symbol=mev.symbol,
#             side="BUY" if mev.event == "buy" else "SELL",
#             position_side=mev.pos_side,
#             contracts=qty,
#             method=mev.method.upper(),
#             price=price,
#             trigger_price=trigger_price,
#             leverage=leverage,
#             open_type=open_type,
#             sl_price=sl_price,
#             tp_price=tp_price,
#             delay_ms=delay_ms,
#         )

#     # --------------------------------------------------
#     def _clamp_by_max_margin(
#         self,
#         *,
#         contracts: float,
#         cfg: dict,
#         price: Optional[float],
#         leverage: int,
#         spec: dict,
#     ) -> float:

#         max_margin = cfg.get("max_position_size")
#         if not max_margin or not price or leverage <= 0:
#             return contracts

#         contract_size = spec.get("contract_size", 1)
#         vol_unit = spec.get("vol_unit", 1)
#         precision = spec.get("contract_precision", 3)

#         margin = (contracts * contract_size * price) / leverage
#         if margin <= max_margin:
#             return contracts

#         coef = max_margin / margin
#         contracts *= coef
#         contracts = (contracts // vol_unit) * vol_unit
#         return round(contracts, precision)




            # # ======================================================
            # # 3️⃣ TEST MODE: ждём, пока:
            # #    • ордер исполнится
            # #    • снапшоты пройдут
            # #    • master может нагенерить вторичные события
            # # ======================================================
            # if TEST_MODE:
            #     await asyncio.sleep(30)

            #     # ==================================================
            #     # 4️⃣ жёстко вычищаем всё, что успело самонагенериться
            #     # ==================================================
            #     flushed = 0
            #     try:
            #         while True:
            #             self.payload.out_queue.get_nowait()
            #             self.payload.out_queue.task_done()
            #             flushed += 1
            #     except asyncio.QueueEmpty:
            #         pass

            #     if flushed:
            #         self.logger.warning(
            #             f"[TEST] flushed {flushed} replicated MasterEvent(s)"
            #         )