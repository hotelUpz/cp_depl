   

    

    # async def cancel_order_template(
    #         self,
    #         symbol: str,
    #         pos_data: Dict,
    #         key_list: List
    #     ) -> None:
    #     """
    #     Отменяет текущий алгоритмический ордер, если он существует (order_id).
    #     После попытки отмены сбрасывает pos_data['order_id'] в None.
    #     """
    #     order_id_list = []
    #     for order_label in key_list:      # order_label in ["tp", "sl"]
    #         order_id = pos_data.get(f"{order_label}_id", None)
    #         if order_id:
    #             # print(f"if order_id: {order_id[0]}")
    #             order_id_list.append(order_id[0])

    #     try:
    #         if order_id_list:
    #             cancel_resp = await self.cancel_order(
    #                 order_id_list=order_id_list,
    #                 symbol=symbol
    #             )
    #             self.logger.debug_info_notes(
    #                 f"[INFO] Order {order_id_list} cancelled for {symbol}: {cancel_resp}", is_print=True
    #             )
    #     except Exception as e:
    #         self.logger.debug_error_notes(
    #             f"[ERROR] Failed to cancel order {order_id_list} for {symbol}: {e}", is_print=True
    #         )
    #     finally:
    #         for order_label in key_list:
    #             try:
    #                 # async with self.bloc_async:
    #                 pos_data[f"{order_label}_id"] = None
    #             except Exception:
    #                 pass
     
    # async def cancel_all_orders(
    #     self,
    #     symbol: str,
    #     debug: bool = True
    # ) -> ApiResponse[int]:
    #     """
    #     Отмена триггерных ордеров по их orderId.
    #     :param order_id_list: список ID ордеров
    #     :param symbol:        символ ордера (обязательно)
    #     :param debug:         печатать отладочную информацию
    #     """
    #     # if debug:
    #     #     print(
    #     #         f"--- INFO: cancel_all_order ---\n"
    #     #         f"symbol:     {symbol}\n"
    #     #         f"----------------------------\n"
    #     #     )

    #     # формируем список словарей для API
    #     return await self.api.cancel_all_orders(symbol=symbol, session=self.session)


    # ########################## BYPASS WAY ###############################         
    # async def set_hedge_mode(
    #         self,
    #         pos_mode: int = 1
    #     ):
    #     # Hedge = 1
    #     # OneWay = 2       
    #     await self.api.change_position_mode(position_mode=PositionMode(pos_mode), session=self.session)



# class OrderValidator:
#     @staticmethod
#     def validate_and_log(
#         result: ApiResponse,
#         debug_label: str,
#         debug: bool =True       
#     ) -> dict:
#         """
#         Проверяет результат ответа биржи при создании ордера.

#         Возвращает словарь:
#         {
#             "success": bool,
#             "order_id": str | None,
#             "ts": int,
#             "reason": str | None,   # текст ошибки если есть
#             "msg": str              # строка для логов
#         }
#         """
#         ts = int(time.time() * 1000)
#         order_id, reason = None, None
#         # print(result)

#         if result and result.success and result.code == 0:
#             order_id = getattr(result.data, "orderId", None) or result.data
#             ts = getattr(result.data, "ts", ts)
#             # if debug:
#             #     msg = f"[{debug_label}] ✅ Ордер создан: orderId={order_id}, ts={ts}"
#                 # print(msg)
#             return {
#                 "success": True,
#                 "order_id": order_id,
#                 "ts": ts,
#                 "reason": None
#             }

#         # если что-то пошло не так
#         reason = getattr(result, "message", None) or "Неизвестная ошибка"
#         code = getattr(result, "code", None) or "N/A"
#         # if debug:
#         #     msg = f"[{debug_label}] ❌ Ошибка при создании ордера: code={code}, reason={reason}"
#         #     print(msg)

#         return {
#             "success": False,
#             "order_id": None,
#             "ts": ts,
#             "reason": reason,
#         }




# # ----------------------------
# class MexcClient:
#     def __init__(
#             self,
#             connector: NetworkManager,
#             logger: ErrorHandler,
#             api_key: str = None,
#             api_secret: str = None,
#             token: str = None,
            
#         ):      
#         self.session: Optional[aiohttp.ClientSession] = connector.session
#         self.logger = logger

#         self.api_key = api_key
#         self.api_secret = api_secret        

#         self.api = MexcFuturesAPI(token, testnet=False)
#         logger.wrap_foreign_methods(self)  

#     # POST  

#     async def make_order(
#         self,
#         symbol: str,
#         contract: float,
#         side: str,
#         position_side: str,
#         leverage: int,
#         open_type: str,
#         debug_price: float = None,
#         price: Optional[float] = None,
#         stopLossPrice: Optional[float] = None,
#         takeProfitPrice: Optional[float] = None,
#         market_type: str = "MARKET",        
#         debug: bool = True   # флаг дебага
#     ) -> ApiResponse[int]:

#         if market_type == "MARKET":
#             market_type = OrderType.MarketOrder 
#         elif market_type == "LIMIT":
#             market_type = OrderType.PriceLimited
#         else:
#             print(f"Параметр market_type должен быть MARKET или LIMIT")
#             return
        
#         if position_side.upper() == "LONG":
#             side = OrderSide.OpenLong if side.upper() == "BUY" else OrderSide.CloseLong
#         elif position_side.upper() == "SHORT":
#             side = OrderSide.OpenShort if side.upper() == "BUY" else OrderSide.CloseShort  
#         else:
#             print(f"Параметр position_side not in [LONG, SHORT]")
#             return

#         if open_type == 1:
#             open_type = OpenType.Isolated
#         elif open_type == 2:
#             open_type = OpenType.Cross
#         else:
#             print(f"Параметр open_type not in [1, 2]")
#             return
        
#         if open_type == OpenType.Isolated and not leverage:
#             print(f"Параметр leverage обязателен при ISOLATED open_type")
#             return
        
#         # if debug:
#         #     print(
#         #         f"--- INFO: make_order ---\n"
#         #         f"symbol:        {symbol}\n"
#         #         f"approximate price:  {debug_price}\n"
#         #         f"contract:      {contract}\n"
#         #         f"side:          {side}\n"
#         #         f"position_side: {position_side}\n"
#         #         f"leverage:      {leverage}\n"
#         #         f"open_type:     {open_type}\n"
#         #         f"market_type:   {market_type}\n"
#         #         f"-------------------------\n"
#         #     )

#         return await self.api.create_order(
#             order_request=CreateOrderRequest(
#                 symbol=symbol,
#                 side=side,
#                 vol=contract,
#                 leverage=leverage,
#                 openType=open_type,
#                 type=market_type,
#                 price=price,
#                 stopLossPrice=stopLossPrice,
#                 takeProfitPrice=takeProfitPrice
#             ),
#             session=self.session
#         )

#     async def make_trigger_order(
#         self,
#         symbol: str,
#         position_side: str,
#         contract: float,
#         price: float,
#         leverage: int,
#         open_type: int,
#         close_order_type: str, # "tp" | "sl"
#         order_type: int = 1,      # 1 -- по маркету, 2 -- лимиткой
#         debug: bool = False
#     ) -> ApiResponse[int]:
        
#         """
#         Универсальный выход (SL/TP) по рынку.
#         - is_take_profit=False -> стоп-лосс
#         - is_take_profit=True  -> тейк-профит

#         Логика условий:
#         CloseLong:
#             SL -> price <= trigger  (LessThanOrEqual)
#             TP -> price >= trigger  (GreaterThanOrEqual)
#         CloseShort:
#             SL -> price >= trigger  (GreaterThanOrEqual)
#             TP -> price <= trigger  (LessThanOrEqual)
#         """

#         if position_side.upper() == "LONG":
#             side = OrderSide.CloseLong
#         elif position_side.upper() == "SHORT":
#             side = OrderSide.CloseShort
#         else:
#             print(f"Параметр position_side not in [LONG, SHORT]")
#             return
        
#         if close_order_type not in ("tp", "sl"):
#             print("close_order_type must be 'tp' or 'sl' for exit order")
#             return

#         if close_order_type == "tp":
#             trigger_type = (
#                 TriggerType.GreaterThanOrEqual if side == OrderSide.CloseLong
#                 else TriggerType.LessThanOrEqual
#             )
#         else:
#             trigger_type = (
#                 TriggerType.LessThanOrEqual if side == OrderSide.CloseLong
#                 else TriggerType.GreaterThanOrEqual
#             )

#         if open_type == 1:
#             open_type = OpenType.Isolated
#         elif open_type == 2:
#             open_type = OpenType.Cross
#         else:
#             print(f"Параметр open_type not in [1, 2]")
#             return
        
#         if open_type == OpenType.Isolated and not leverage:
#             print(f"Параметр leverage обязателен при ISOLATED open_type")
#             return
        
#         if order_type == 1:
#             orderType = OrderType.MarketOrder
#         else:
#             print(f"Параметр order_type != 1 (create_stop_loss_take_profit).")
#             return

#         # if debug:
#         #     print(
#         #         f"--- INFO: create_stop_loss_take_profit ---\n"
#         #         f"symbol:          {symbol}\n"
#         #         f"position_side:   {position_side}\n"
#         #         f"close_order_type:{close_order_type}\n"
#         #         f"side:            {side}\n"
#         #         f"contract:        {contract}\n"
#         #         f"price:           {price}\n"
#         #         f"trigger_type:    {trigger_type}\n"
#         #         f"open_type:       {open_type}\n"
#         #         f"leverage:        {leverage}\n"
#         #         f"------------------------------------------\n"
#         #     )

#         trigger_request = TriggerOrderRequest(
#             symbol=symbol,
#             side=side,
#             vol=contract,                      # количество (в контрактах)
#             leverage=leverage,
#             openType=open_type,
#             orderType=orderType,
#             executeCycle=ExecuteCycle.UntilCanceled,
#             trend=TriggerPriceType.LatestPrice,
#             triggerPrice=price,
#             triggerType=trigger_type,
#         )
#         return await self.api.create_trigger_order(trigger_order_request=trigger_request, session=self.session)  
    
#     # DELETE
     
#     async def cancel_order(
#         self,
#         order_id_list: List[str],
#         symbol: str,
#         debug: bool = True
#     ) -> ApiResponse[int]:
#         """
#         Отмена триггерных ордеров по их orderId.
#         :param order_id_list: список ID ордеров
#         :param symbol:        символ ордера (обязательно)
#         :param debug:         печатать отладочную информацию
#         """
#         # if debug:
#         #     print(
#         #         f"--- INFO: cancel_order ---\n"
#         #         f"symbol:     {symbol}\n"
#         #         f"order_ids:  {order_id_list}\n"
#         #         f"----------------------------\n"
#         #     )

#         # формируем список словарей для API
#         order_list = [{"orderId": oid, "symbol": symbol} for oid in order_id_list]
#         return await self.api.cancel_trigger_orders(orders=order_list, session=self.session)



    # async def _broadcast_to_copies(self, mev: MasterEvent):
    #     for cid, cfg in self.mc.copy_configs.items():

    #         # 0 = мастер → пропускаем
    #         if cid == 0:
    #             continue

    #         if not cfg.get("enabled"):
    #             continue

    #         print(f" → COPY[{cid}] received HL signal")

    #         try:
    #             asyncio.create_task(self._execute_test(cid, mev))
    #         except Exception as e:
    #             print(f"❗ ERROR executing event for copy[{cid}]: {e}")





# class PosVarSetup:
#     @staticmethod
#     def pos_vars_root_template() -> Dict[str, Any]:
#         return {
#             # ==================================================
#             # POSITION STATE (FACTUAL)
#             # ==================================================
#             "in_position": False,

#             # quantities
#             "qty": 0.0,          # текущий holdVol (контракты)
#             "qty_prev": 0.0,     # предыдущее значение

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
#                 # лимитные ордера
#                 "limit_open": False,     # лимит на вход / добор
#                 "limit_close": False,    # лимит на закрытие

#                 # риск-ордера
#                 "tp": False,
#                 "sl": False,
#             },
#         }
