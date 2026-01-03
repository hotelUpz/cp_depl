# COPY.exequter_.py

from __future__ import annotations

import asyncio
from typing import *

from b_context import PosVarTemplate
from c_utils import now
from .pv_fsm_ import PosMonitorFSM
from .state_ import CopyOrderIntentFactory

if TYPE_CHECKING:
    from c_log import UnifiedLogger
    from .state_ import CopyOrderIntent
    from b_context import MainContext
    from MASTER.payload_ import MasterEvent, MasterPayload
    from API.MX.client import MexcClient


# ======================================================================
# POSITION ACCESS
# ======================================================================
@staticmethod
def get_copy_pos(rt: dict, symbol: str, side: str) -> dict:
    pv_root = rt.setdefault("position_vars", {})
    sym = pv_root.setdefault(symbol, {})
    if side not in sym:
        sym[side] = PosVarTemplate.base_template()
    return sym[side]


# ==================================================
# LATENCY (DEBUG PRINT ONLY)
# ==================================================
def _record_latency(
    cid: int,
    mev: "MasterEvent",
    res: Optional[dict],
) -> None:
    """
    Debug-only latency print.
    No storage, no side effects.
    """

    if not res or not isinstance(res, dict):
        return

    master_ts = getattr(mev, "ts", None)
    if not master_ts:
        return

    copy_ts = res.get("ts")
    if not copy_ts:
        return

    latency = copy_ts - master_ts

    print(
        f"[LATENCY]"
        f" cid={cid}"
        f" {mev.symbol}"
        f" {mev.pos_side}"
        f" latency={latency}ms"
        # f" master_ts={master_ts}"
        # f" copy_ts={copy_ts}"
    )  


class CopyExequter:
    def __init__(
        self,
        mc: "MainContext",
        logger: UnifiedLogger
    ):
        self.mc = mc
        self.logger = logger

        self.payload: "MasterPayload" | None = None
        self.intent_factory = CopyOrderIntentFactory(self.mc)

    # ==================================================
    # INTERNAL: COPY EVENT
    # ==================================================
    async def handle_copy_event(
        self,
        cid: int,
        cfg: dict,
        rt: dict,
        mev: MasterEvent,
        monitors: Dict[int, PosMonitorFSM],
    ):

        # --------------------------------------------------
        # CLIENT
        # --------------------------------------------------
        client: "MexcClient" = self.mc.copy_runtime_states.get(cid, {}).get("mc_client", None)
        if not client:
            return
        
        # --------------------------------------------------
        # orders_vars
        # --------------------------------------------------
        ov_root = rt.setdefault("orders_vars", {})
        sym_root = ov_root.setdefault(mev.symbol, {})
        side_root = sym_root.setdefault(mev.pos_side, {})
        
        # --------------------------------------------------
        # CANCEL (НЕ ЧЕРЕЗ INTENT)
        # --------------------------------------------------
        if mev.event == "canceled":
            master_oid = mev.payload.get("order_id")
            if not master_oid:
                self.mc.log_events.append(
                    (cid, f"{mev.symbol} {mev.pos_side} :: CANCEL SKIP (no master order_id)")
                )
                return

            # ---------- LIMIT ----------
            if mev.method == "limit":
                limit_root = side_root.get("limit", {})
                rec = limit_root.pop(master_oid, None)
                if not rec:
                    self.mc.log_events.append(
                        (cid, f"{mev.symbol} {mev.pos_side} :: LIMIT CANCEL MISS master_oid={master_oid}")
                    )
                    return

                copy_oid = rec.get("copy_order_id")
                if not copy_oid:
                    return

                res = await client.cancel_limit_orders([copy_oid])
                if not res or not res.get("success"):
                    self.mc.log_events.append(
                        (cid, f"{mev.symbol} {mev.pos_side} :: LIMIT CANCEL FAILED copy_oid={copy_oid}")
                    )
                else:
                    self.mc.log_events.append(
                        (cid, f"{mev.symbol} {mev.pos_side} :: LIMIT CANCELED copy_oid={copy_oid}")
                    )
                return

            # ---------- TRIGGER ----------
            if mev.method == "trigger":
                trigger_root = side_root.get("trigger", {})
                rec = trigger_root.pop(master_oid, None)
                if not rec:
                    self.mc.log_events.append(
                        (cid, f"{mev.symbol} {mev.pos_side} :: TRIGGER CANCEL MISS master_oid={master_oid}")
                    )
                    return

                copy_oid = rec.get("copy_order_id")
                if not copy_oid:
                    return

                res = await client.cancel_trigger_order(
                    [copy_oid],
                    symbol=mev.symbol,
                )
                if not res or not res.get("success"):
                    self.mc.log_events.append(
                        (cid, f"{mev.symbol} {mev.pos_side} :: TRIGGER CANCEL FAILED copy_oid={copy_oid}")
                    )
                else:
                    self.mc.log_events.append(
                        (cid, f"{mev.symbol} {mev.pos_side} :: TRIGGER CANCELED copy_oid={copy_oid}")
                    )
                return

            return

        # --------------------------------------------------
        # POSITION SNAPSHOT (FSM)
        # --------------------------------------------------
        if cid not in monitors:
            monitors[cid] = PosMonitorFSM(
                rt["position_vars"],
                client.fetch_positions,
            )

        if mev.sig_type == "log":
            return

        # --------------------------------------------------
        # BUILD INTENT
        # --------------------------------------------------
        copy_pv = get_copy_pos(rt, mev.symbol, mev.pos_side)

        spec = (
            self.mc.pos_vars_root
            .get("position_vars", {})
            .get(mev.symbol, {})
            .get("spec", {})
        )

        intent: CopyOrderIntent | None = self.intent_factory.build(
            cfg=cfg,
            mev=mev,
            copy_pv=copy_pv,
            spec=spec,
        )

        if not intent:
            print("not intent")
            return
        
        # if TEST_MODE: await asyncio.sleep(5.0 + random.uniform(0.15, 0.6))
        if intent.delay_ms: await asyncio.sleep(intent.delay_ms / 1000)

        anchor = f"{intent.symbol} {intent.position_side}"

        # --------------------------------------------------
        # FORCE CLOSE
        # --------------------------------------------------
        if mev.closed:
            res = await client.make_order(
                symbol=intent.symbol,
                contract=intent.contracts,
                side=intent.side,
                position_side=intent.position_side,
                leverage=intent.leverage,
                open_type=intent.open_type,
                market_type="MARKET",
                debug=True,
            )

            _record_latency(
                cid=cid,
                mev=mev,
                res=res
            )

            if not res or not res.get("success"):
                rt["last_error"] = res.get("reason") if res else "UNKNOWN"
                rt["last_error_ts"] = now()
                self.mc.log_events.append(
                    (cid, f"{anchor} :: CLOSE FAILED: {rt['last_error']}")
                )
                return
            
            if mev.sig_type == "manual":
                limit_ids = [
                    v.get("copy_order_id")
                    for v in side_root.get("limit", {}).values()
                    if v.get("copy_order_id")
                ]
                trigger_ids = [
                    v.get("copy_order_id")
                    for v in side_root.get("trigger", {}).values()
                    if v.get("copy_order_id")
                ]

                if limit_ids or trigger_ids:
                    cancel_res = await client.cancel_orders_bulk(
                        limit_order_ids=limit_ids,
                        trigger_order_ids=trigger_ids,
                        symbol=intent.symbol,
                    )

                    if cancel_res and cancel_res.get("success"):
                        side_root.get("limit", {}).clear()
                        side_root.get("trigger", {}).clear()
                    else:
                        reason = cancel_res.get("reason") if cancel_res else "UNKNOWN"
                        self.mc.log_events.append(
                            (cid, f"{intent.symbol} {intent.position_side} :: CANCEL FAILED: {reason}")
                        )

            return
        
        # --------------------------------------------------
        # ORDERS CACHE INIT
        # --------------------------------------------------
        limit_root = side_root.setdefault("limit", {})
        trigger_root = side_root.setdefault("trigger", {})
        master_oid = mev.payload.get("order_id")

        # --------------------------------------------------
        # MARKET / LIMIT
        # --------------------------------------------------
        if intent.method in ("MARKET", "LIMIT"):
            res = await client.make_order(
                symbol=intent.symbol,
                contract=intent.contracts,
                side=intent.side,
                position_side=intent.position_side,
                leverage=intent.leverage,
                open_type=intent.open_type,
                price=intent.price if intent.method == "LIMIT" else None,
                stopLossPrice=intent.sl_price,
                takeProfitPrice=intent.tp_price,
                market_type=intent.method,
                debug=True,
            )

            _record_latency(
                cid=cid,
                mev=mev,
                res=res
            )

            if not res or not res.get("success"):
                rt["last_error"] = res.get("reason") if res else "UNKNOWN"
                rt["last_error_ts"] = now()
                self.mc.log_events.append(
                    (cid, f"{anchor} :: {intent.method} FAILED: {rt['last_error']}")
                )
                return

            if intent.method == "LIMIT" and master_oid:
                limit_root[master_oid] = {
                    "copy_order_id": res.get("order_id"),
                    "price": intent.price,
                    "qty": intent.contracts,
                    "status": "OPEN",
                }

            return

        # --------------------------------------------------
        # TRIGGER
        # --------------------------------------------------
        if intent.method == "TRIGGER":
            res = await client.make_trigger_order(
                symbol=intent.symbol,
                side=intent.side,
                position_side=intent.position_side,
                contract=intent.contracts,
                trigger_price=intent.trigger_price,
                leverage=intent.leverage,
                open_type=intent.open_type,
                order_type=mev.payload.get("trigger_exec", 2),
                debug=True,
            )

            if not res or not res.get("success"):
                rt["last_error"] = res.get("reason") if res else "UNKNOWN"
                rt["last_error_ts"] = now()
                self.mc.log_events.append(
                    (cid, f"{anchor} :: TRIGGER FAILED: {rt['last_error']}")
                )
                return

            if master_oid:
                trigger_root[master_oid] = {
                    "copy_order_id": res.get("order_id"),
                    "trigger_price": intent.trigger_price,
                    "qty": intent.contracts,
                    "status": "OPEN",
                }

            return