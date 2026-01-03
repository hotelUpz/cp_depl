# c_utils.py

from __future__ import annotations
from typing import *
from datetime import datetime
from a_config import PRECISION, QUOTA_ASSET
from c_log import TZ
from decimal import Decimal, getcontext
import time


getcontext().prec = PRECISION  # точность Decimal


def now() -> int:
    """Return current timestamp in milliseconds."""
    return int(time.time() * 1000)


class Utils:    
    @staticmethod
    def to_human_digit(value):
        if value is None:
            # return "N/A"
            return None
        getcontext().prec = PRECISION
        dec_value = Decimal(str(value)).normalize()
        if dec_value == dec_value.to_integral():
            return format(dec_value, 'f')
        else:
            return format(dec_value, 'f').rstrip('0').rstrip('.')  
        
    def format_duration(ms: int) -> str:
        """
        Конвертирует миллисекундную разницу в формат "Xh Ym" или "Xm" или "Xs".
        :param ms: длительность в миллисекундах
        """
        if ms is None:
            return ""
        
        total_seconds = ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if hours > 0 and minutes > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0 and seconds > 0:
            return f"{minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m"
        else:
            return f"{seconds}s"
        
    @staticmethod
    def safe_float(value: Any, default: float = 0.0) -> float:
        """Преобразует значение в float, если не удалось — возвращает default"""
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
        
    @staticmethod
    def safe_int(value: Any, default: int = 0) -> int:
        """Преобразует значение в int, если не удалось — возвращает default"""
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
        
    @staticmethod
    def safe_round(value: Any, ndigits: int = 2, default: float = 0.0) -> float:
        """Безопасный round для None или нечисловых значений"""
        try:
            return round(float(value), ndigits)
        except (TypeError, ValueError):
            return default        

    @staticmethod
    def parse_precision(symbols_info: list[dict], symbol: str) -> dict:
        """
        Возвращает настройки для qty, price и макс. плеча в виде словаря:
        {
            "contract_precision": int,
            "price_precision": int,
            "contract_size": float,
            "price_unit": float,
            "vol_unit": float,
            "max_leverage": int | None
        }
        Если символ не найден или данные пустые → None.
        """
        symbol_data = next((item for item in symbols_info if item.get("symbol") == symbol or item.get("baseCoinName") + f"_{QUOTA_ASSET}" == symbol), None)
        if not symbol_data:
            return None

        # обработка maxLeverage
        raw_leverage = symbol_data.get("maxLeverage")
        try:
            max_leverage = int(float(raw_leverage)) if raw_leverage is not None else None
        except (ValueError, TypeError):
            max_leverage = None

        return {
            "contract_precision": symbol_data.get("volScale", 3),
            "price_precision": symbol_data.get("priceScale", 2),
            "contract_size": float(symbol_data.get("contractSize", 1)),
            "price_unit": float(symbol_data.get("priceUnit", 0.01)),
            "vol_unit": float(symbol_data.get("volUnit", 1)),
            "max_leverage": max_leverage
        }
        
    def contract_calc(
        self,
        spec: dict,
        margin_size: float,
        entry_price: float,
        leverage: float,
        volume_rate: float,
        debug_label: str = None
    ) -> Optional[float]:
        """
        Рассчитывает количество контрактов (vol), которое надо передать в API MEXC.
        """
        contract_size = spec.get("contract_size")
        vol_unit = spec.get("vol_unit")
        contract_precision = spec.get("contract_precision")

        # проверка на валидность
        if any(not isinstance(x, (int, float)) for x in [margin_size, entry_price, leverage, contract_size]):
            print(f"{debug_label}: Invalid input parameters in contract_calc")
            return None

        try:
            # сколько денег реально задействуем
            deal_amount = margin_size * volume_rate / 100

            # считаем объём в базовой валюте
            base_qty = (deal_amount * leverage) / entry_price

            # переводим в контракты
            raw_contracts = base_qty / contract_size

            # округляем по vol_unit
            contracts = round(raw_contracts / vol_unit) * vol_unit

            # окончательно ограничиваем precision
            contracts = round(contracts, contract_precision)

            return contracts
        except Exception as e:
            print(f"{debug_label}: Error in contract_calc: {e}")
            return None

    @staticmethod
    def milliseconds_to_datetime(milliseconds):
        if milliseconds is None:
            return "N/A"
        try:
            ms = int(milliseconds)   # <-- приведение к int
            if milliseconds < 0: return "N/A"
        except (ValueError, TypeError):
            return "N/A"

        if ms > 1e10:  # похоже на миллисекунды
            seconds = ms / 1000
        else:
            seconds = ms

        dt = datetime.fromtimestamp(seconds, TZ)
        return dt.strftime("%Y-%m-%d %H:%M:%S")