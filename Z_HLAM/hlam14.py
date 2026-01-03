

# class CopyOrderBuilder:
#     def __init__(
#         self,
#         # *,
#         cfg: dict,
#         mev: MasterEvent,
#         # pv: dict,
#         # logger: UnifiedLogger | None = None,
#     ):
#         self.cfg = cfg
#         self.mev = mev
#         self.pv = self.mev.pos_progress
#         self.spec = mev.spec
#         # self.log = logger
#         # self.log.wrap_object_methods(self)

#     def _base_contracts(self) -> float:
#         return float(self.mev.payload.get("qty", 0.0))

#     def _apply_coef(self, contracts: float) -> float:
#         coef = self.cfg.get("coef", 1.0)
#         return contracts * coef if coef else contracts

#     def _apply_random_size(self, contracts: float) -> float:
#         lo, hi = self.cfg.get("random_size_pct", (0.0, 0.0))
#         if lo == hi == 0:
#             return contracts

#         pct = random.uniform(lo, hi)
#         return contracts * (1 + pct / 100)

#     def _clamp_by_max_margin(self, contracts: float) -> float:
#         max_margin = self.cfg.get("max_position_size")
#         if not max_margin:
#             return contracts

#         price = (
#             self.mev.payload.get("price")
#             or self.pv.get("entry_price")
#         )
#         leverage = self.mev.payload.get("leverage", 1)

#         if not price or leverage <= 0:
#             return contracts

#         contract_size = self.spec.get("contract_size", 1)
#         vol_unit = self.spec.get("vol_unit", 1)
#         precision = self.spec.get("contract_precision", 3)

#         margin = (contracts * contract_size * price) / leverage
#         if margin <= max_margin:
#             return contracts

#         coef = max_margin / margin
#         new_contracts = contracts * coef

#         # строго вниз
#         new_contracts = (new_contracts // vol_unit) * vol_unit
#         return round(new_contracts, precision)

#     def _resolve_leverage(self) -> int:
#         lev = self.cfg.get("leverage") or self.mev.payload.get("leverage") or DEFAULT_LEVERAGE
#         max_lev = self.spec.get("max_leverage")

#         if max_lev:
#             lev = min(int(lev), int(max_lev))

#         return int(lev)

#     def _resolve_margin_mode(self) -> Optional[str]:
#         return (
#             self.cfg.get("margin_mode")
#             or self.mev.payload.get("margin_mode")
#             or DEFAULT_MARGIN_MODE
#         )

#     def _resolve_delay(self) -> int:
#         base = int(self.cfg.get("delay_ms", 0))
#         if base <= 0:
#             return 0
#         return int(random.uniform(0, base))
        
#     def build(self) -> Optional[CopyOrderIntent]:

#         contracts = self._base_contracts()
#         if contracts <= 0:
#             return None

#         contracts = self._apply_coef(contracts)
#         contracts = self._apply_random_size(contracts)
#         contracts = self._clamp_by_max_margin(contracts)

#         if contracts <= 0:
#             return None

#         return CopyOrderIntent(
#             symbol=self.mev.symbol,
#             side="BUY" if self.mev.event == "buy" else "SELL",
#             position_side=self.mev.side,
#             contracts=contracts,

#             method=self.mev.method.upper(),
#             price=self.mev.payload.get("price"),
#             trigger_price=self.mev.payload.get("trigger_price"),

#             leverage=self._resolve_leverage(),
#             margin_mode=self._resolve_margin_mode(),
#             open_type=self.mev.payload.get("open_type"),
#             reduce_only=bool(self.mev.payload.get("reduce_only")),

#             delay_ms=self._resolve_delay(),
#         )



# # ======================================================================
# # ACCOUNTE RISK
# # ======================================================================

# class Risk:
#     @staticmethod
#     def clamp_contracts_by_max_margin(
#         *,
#         contracts: float,
#         entry_price: float,
#         leverage: float,
#         spec: dict,
#         max_margin: float,
#     ) -> float:
#         """
#         Ограничивает количество контрактов так,
#         чтобы маржинальное обеспечение не превышало max_margin (USDT).
#         Формулы соответствуют MEXC USDT futures.
#         """

#         if not all([contracts, entry_price, leverage, max_margin]):
#             return contracts

#         contract_size = spec.get("contract_size", 1)
#         precision = spec.get("contract_precision", 3)
#         vol_unit = spec.get("vol_unit", 1)

#         # текущая маржа мастера
#         master_margin = (
#             contracts * contract_size * entry_price
#         ) / leverage

#         if master_margin <= max_margin:
#             return contracts

#         # коэффициент сжатия
#         coef = max_margin / master_margin

#         new_contracts = contracts * coef

#         # обязательное округление ВНИЗ
#         new_contracts = (new_contracts // vol_unit) * vol_unit
#         new_contracts = round(new_contracts, precision)

#         return max(new_contracts, 0.0)




        # # --------------------------------------------------
        # # CANCEL
        # # --------------------------------------------------
        # if mev.event == "canceled":

        #     order_id = mev.payload.get("order_id")
        #     if not order_id:
        #         return

        #     self.logger.info(
        #         f"COPY[{cid}] CANCEL {mev.method.upper()} order_id={order_id}"
        #     )

        #     if mev.method == "limit":
        #         res = await client.cancel_limit_orders([order_id])
        #     elif mev.method == "trigger":
        #         res = await client.cancel_trigger_order(
        #             [order_id],
        #             symbol=mev.symbol,
        #         )
        #     else:
        #         return

        #     await on_order_result(
        #         mc=self.mc,
        #         cid=cid,
        #         res=res,
        #     )

    # async def _broadcast_to_copies(self, mev: MasterEvent):
    #     for cid, cfg in self.mc.copy_configs.items():

    #         if cid == 0 or not cfg.get("enabled"):
    #             continue

    #         try:
    #             if TEST_MODE:
    #                 asyncio.create_task(execute_test(cid, mev))
    #             else:
    #                 asyncio.create_task(
    #                     self._handle_copy_event(cid, cfg, mev)
    #                 )
    #         except Exception as e:
    #             self.logger.exception(
    #                 f"COPY[{cid}] broadcast error", e
    #             )


        # if self._pos_vars_root is None:
        #     root = self.mc.copy_configs.setdefault(0, {}).setdefault("runtime", {})
        #     root.setdefault("position_vars", {})
        #     self._pos_vars_root = root["position_vars"]


            # root = self.mc.copy_configs.setdefault(0, {}).setdefault("runtime", {})
            # oco_buf = root.setdefault("_attached_oco", {})


        # root = self.mc.copy_configs.setdefault(0, {}).setdefault("runtime", {})
        # oco = root.get("_attached_oco", {}).pop(symbol, None)


# def now(format="ms"):
#     if format == "ms":
#         return int(time.time() * 1000)
    
#     return int(time.time())


    
    # # 🔒 SAFE SYNC FOR MASTER ONLY
    # if cid == 0:
    #     await PosMonitorMX(rt["position_vars"], client.fetch_positions).refresh()


            # elif last == "enabled":
            #     if raw not in ("0","1"):
            #         await msg.answer("❗ Введите 0 или 1.")
            #         return
            #     enabled = raw == "1"
            #     target[last] = enabled

            #     await self.ctx.save_users()

            #     if enabled:
            #         await self.copy_state.activate_copy(cid)
            #     else:
            #         await self.copy_state.deactivate_copy(cid)

            #     self._exit_input(chat_id)
            #     await msg.answer("✔ Сохранено!", reply_markup=self.menu_copies())
            #     return


# def validate_master(cfg: dict) -> Optional[str]:
#     ex = cfg.get("exchange", {})
#     if not ex.get("api_key"):
#         return "API Key не заполнен"
#     if not ex.get("api_secret"):
#         return "Secret Key не заполнен"
#     if not ex.get("uid"):
#         return "UID не заполнен"
#     return None


# def validate_copy(cfg: dict) -> Optional[str]:
#     ex = cfg.get("exchange", {})
#     if not ex.get("api_key"):
#         return "API Key не заполнен"
#     if not ex.get("api_secret"):
#         return "Secret Key не заполнен"
#     if not ex.get("uid"):
#         return "UID не заполнен"

#     rnd = cfg.get("random_size_pct")
#     if not isinstance(rnd, (tuple, list)) or len(rnd) != 2:
#         return "random_size_pct должен быть формата (min, max)"
#     return None



            # "exec_state": {
            #     "limit_open": False,
            #     "limit_close": False,
            #     "tp": False,
            #     "sl": False,
            # },



    # PUBLIC_KEYS = (
    #     "in_position",
    #     "qty", "qty_prev",
    #     "entry_price", "avg_price",
    #     "leverage", "margin_mode",
    #     "entry_ts", "exit_ts"
    # )


                    # # --------------------------------------------------
                    # pv.update({
                    #     "in_position": False,
                    #     "qty": 0.0,
                    #     "qty_prev": 0.0,

                    #     "entry_price": None,
                    #     "avg_price": None,

                    #     "entry_ts": None,
                    #     "exit_ts": now_ts,
                    # })



                # except Exception as e:
                #     logger.warning(
                #         f"[FORCE_CLOSE:{cid}] cancel_all_orders failed "
                #         f"{symbol}: {e}"
                #     )