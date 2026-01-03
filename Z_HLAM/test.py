# COPY/test_.py

from __future__ import annotations
from c_utils import Utils

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from MASTER.payload_ import MasterEvent

# ======================================================================
# TEST EXECUTOR — полный и стабильный вывод MasterEvent
# ======================================================================
async def execute_test(copy_id: int, mev: "MasterEvent"):
    payload = mev.payload or {}

    ts = payload.get("exec_ts")
    lat = payload.get("latency_ms")

    exec_time = (
        Utils.milliseconds_to_datetime(ts)
        if ts else "N/A"
    )
    latency = f"{lat} ms" if lat is not None else "N/A"

    # --------------------------------------------------
    # HEADER
    # --------------------------------------------------
    header = (
        f"[{mev.sig_type.upper():4}] "
        f"COPY[{copy_id}] "
        f"{mev.event.upper():8} "
        f"{mev.symbol:<12} "
        f"{mev.pos_side:<5} "
        f"{mev.method.upper():8}"
    )

    flags = []
    if mev.partially:
        flags.append("PARTIAL")
    if mev.sig_type == "log":
        flags.append("NO-COPY")

    flags_str = f" [{', '.join(flags)}]" if flags else ""

    # --------------------------------------------------
    # BASE INFO
    # --------------------------------------------------
    print(
        f"\n{'=' * 110}\n"
        f"{header}{flags_str}\n"
        f"{'-' * 110}\n"
        f"  exec_time : {exec_time}\n"
        f"  latency   : {latency}\n"
        f"  event     : {mev.event}\n"
        f"  method    : {mev.method}\n"
        f"  symbol    : {mev.symbol}\n"
        f"  side      : {mev.pos_side}\n"
        f"  sig_type  : {mev.sig_type}\n"
        f"  partially : {mev.partially}\n"
    )

    # --------------------------------------------------
    # PAYLOAD — структурированный вывод
    # --------------------------------------------------
    print("  payload   :")

    if not payload:
        print("    • <empty>")
    else:
        # 🔑 утверждённый порядок полей payload
        priority_keys = [
            # идентификация
            "order_id",

            # цена
            "price",
            "trigger_price",

            # количество
            "qty",
            "qty_delta",
            "qty_before",
            "qty_after",

            # attached OCO
            "tp_price",
            "sl_price",

            # исполнение
            "reduce_only",
            "trigger_exec",

            # параметры позиции
            "leverage",
            "open_type",

            # риск
            "used_margin",
        ]

        printed = set()

        for k in priority_keys:
            if k in payload:
                print(f"    • {k:<16}: {payload[k]}")
                printed.add(k)

        # всё остальное (на будущее, без потерь)
        for k, v in payload.items():
            if k not in printed:
                print(f"    • {k:<16}: {v}")

    # # --------------------------------------------------
    # # RAW EVENT (оригинал с биржи)
    # # --------------------------------------------------
    # if mev.raw:
    #     print("  raw_event :")
    #     print(f"    • event_type   : {mev.raw.event_type}")
    #     print(f"    • ts           : {mev.raw.ts}")
    #     print(f"    • raw_payload  :")
    #     for k, v in mev.raw.raw.items():
    #         print(f"        - {k}: {v}")

    print(f"{'=' * 110}")