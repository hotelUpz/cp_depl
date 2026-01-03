    # @staticmethod    
    # def has_open_positions(position_vars) -> bool:
    #     """
    #     Проверка, есть ли хотя бы одна открытая позиция по данным position_vars.
    #     Ожидается структура:
    #     position_vars[symbol][side]["in_position"] == True
    #     """
    #     for symbol_data in position_vars.values():
    #         for side, pos in symbol_data.items():
    #             if side == "spec":
    #                 continue
    #             if isinstance(pos, dict) and pos.get("in_position"):
    #                 return True
    #     return False


    
    # @staticmethod
    # def format_duration(ms: int) -> str:
    #     """
    #     Конвертирует миллисекундную разницу в формат "Xh Ym" или "Xm" или "Xs".
    #     :param ms: длительность в миллисекундах
    #     """
    #     if ms is None:
    #         return ""
        
    #     total_seconds = ms // 1000
    #     hours = total_seconds // 3600
    #     minutes = (total_seconds % 3600) // 60
    #     seconds = total_seconds % 60

    #     if hours > 0 and minutes > 0:
    #         return f"{hours}h {minutes}m"
    #     elif minutes > 0 and seconds > 0:
    #         return f"{minutes}m {seconds}s"
    #     elif minutes > 0:
    #         return f"{minutes}m"
    #     else:
    #         return f"{seconds}s"




    # @staticmethod
    # def parse_precision(data: List[Dict[str, Any]], symbol: str) -> Optional[Dict[str, Any]]:
    #     """
    #     Возвращает параметры для торговли конкретным фьючерсом (Gate.io):
    #     - ctVal: стоимость контракта (quanto_multiplier)
    #     - lotSz: минимальный шаг размера позиции (order_size_min)
    #     - contract_precision: количество знаков после точки для лота
    #     - price_precision: количество знаков после точки для цены
    #     - max_leverage: максимальное плечо
    #     """
    #     if not data:
    #         return None

    #     for info in data:
    #         if info.get("name") == symbol:
    #             # вспомогательная функция для подсчёта знаков после точки
    #             def count_precision(value_str: str) -> int:
    #                 if not value_str:
    #                     return 0
    #                 parts = str(value_str).split(".")
    #                 return len(parts[1]) if len(parts) > 1 else 0

    #             try:
    #                 ctVal_str = str(info.get("quanto_multiplier") or "1")
    #                 lot_sz_str = str(info.get("order_size_min") or "1")
    #                 tick_sz_str = str(info.get("order_price_round") or "0.01")
    #                 max_leverage = (
    #                     info.get("leverage_max")
    #                     or info.get("max_leverage")
    #                     or info.get("leverUp")
    #                     or None
    #                 )

    #                 return {
    #                     "ctVal": float(ctVal_str),
    #                     "lotSz": float(lot_sz_str),
    #                     "contract_precision": count_precision(lot_sz_str),
    #                     "price_precision": count_precision(tick_sz_str),
    #                     "max_leverage": int(float(max_leverage)) if max_leverage else None,
    #                 }

    #             except Exception as e:
    #                 print(f"[parse_precision][{symbol}] Ошибка при парсинге: {e}")
    #                 return None

    #     print(f"[parse_precision] Нет данных для символа {symbol}")
    #     return None    
    
    # @staticmethod
    # def contract_calc(
    #     margin_size: float,
    #     entry_price: float,
    #     leverage: float,
    #     ctVal: float,
    #     lotSz: float,
    #     contract_precision: int,
    #     volume_rate: float = 100.0,
    #     debug_label: str = None
    # ) -> Optional[float]:
    #     """
    #     Рассчитывает количество контрактов на основе входных параметров.
    #     """
    #     log_prefix = f"{debug_label}: " if debug_label else ""
    #     print(f"{log_prefix}Starting contract_calc with inputs: margin_size={margin_size}, entry_price={entry_price}, leverage={leverage}, ctVal={ctVal}, lotSz={lotSz}, contract_precision={contract_precision}, volume_rate={volume_rate}")

    #     if any(x is None or not isinstance(x, (int, float)) or x <= 0 for x in [margin_size, entry_price, leverage, ctVal, lotSz]):
    #         print(f"{log_prefix}Invalid input parameters in contract_calc: margin_size={margin_size}, entry_price={entry_price}, leverage={leverage}, ctVal={ctVal}, lotSz={lotSz}")
    #         return None

    #     try:
    #         deal_amount = margin_size * (volume_rate / 100.0)
    #         print(f"{log_prefix}Calculated deal_amount = {deal_amount}")

    #         base_qty = (deal_amount * leverage) / entry_price
    #         print(f"{log_prefix}Calculated base_qty = {base_qty}")

    #         raw_contracts = base_qty / ctVal
    #         print(f"{log_prefix}Calculated raw_contracts = {raw_contracts}")

    #         rounded_steps = round(raw_contracts / lotSz) * lotSz
    #         print(f"{log_prefix}Calculated rounded_steps = {rounded_steps}")

    #         contracts = round(rounded_steps, contract_precision)
    #         print(f"{log_prefix}Calculated contracts = {contracts}")

    #         if contracts <= 0:
    #             print(f"{log_prefix}Calculated contracts <= 0: {contracts}")
    #             return None
    #         return contracts
    #     except Exception as e:
    #         print(f"{log_prefix}Error in contract_calc: {str(e)}")
    #         return None