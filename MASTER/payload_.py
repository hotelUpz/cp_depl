# MASTER.payload_.py

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import *

from MASTER.state_ import PosVarSetup
from c_utils import Utils, now

if TYPE_CHECKING:
    from MASTER.state_ import SignalCache, SignalEvent
    from b_context import MainContext
    from c_log import UnifiedLogger


# =====================================================================
# HL PROTOCOL
# =====================================================================

HL_EVENT = Literal["buy", "sell", "canceled", "filled"]
METHOD = Literal["market", "limit", "trigger", "oco"]


# =====================================================================
# MASTER EVENT
# =====================================================================

@dataclass
class MasterEvent:
    # MasterEvent may contain _cid for manual routing
    event: HL_EVENT
    method: METHOD
    symbol: str
    pos_side: str
    partially: bool
    closed: bool
    payload: Dict[str, Any]
    sig_type: Literal["copy", "log", "manual"]
    ts: int = field(default_factory=now)

# =====================================================================
# MASTER PAYLOAD
# =====================================================================

class MasterPayload:
    """
    High-level агрегатор сигналов мастера.
    """

    def __init__(
        self,
        cache: "SignalCache",
        mc: "MainContext",
        logger: "UnifiedLogger",
        stop_flag: Callable,
    ):
        self.cache = cache
        self.mc = mc
        self.logger = logger
        self.stop_flag = stop_flag

        self._pending: List[MasterEvent] = []
        self._stop = False

        self._pos_state: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._last_deal: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._attached_oco: Dict[str, dict] = {}

        self.out_queue = asyncio.Queue(maxsize=1000)

    # ==========================================================
    def stop(self):
        self._stop = True
        self.mc.pos_vars_root.clear()
        self.logger.info("MasterPayload: stop requested")

    # ==========================================================
    async def run(self):
        self.logger.info("MasterPayload READY")

        while not self._stop and not self.stop_flag():
            await self.cache._event_notify.wait()
            raw_events = await self.cache.pop_events()

            for ev in raw_events:
                await self._route(ev)

            out = self._pending[:]
            self._pending.clear()

            for mev in out:
                await self.out_queue.put(mev)

        self.logger.info("MasterPayload STOPPED")

    # ==========================================================
    def _ensure_pos_vars(self, symbol: str, pos_side: str) -> dict:
        PosVarSetup.set_pos_defaults(
            self.mc.pos_vars_root,
            symbol,
            pos_side,
            instruments_data=self.mc.instruments_data,
        )

        return self.mc.pos_vars_root.get(symbol, {}).get(pos_side, {})

    # ==========================================================
    def _fix_price(self, raw, symbol=None, side=None):
        for k in ("dealAvgPrice", "avgPrice", "price", "openAvgPrice"):
            if raw.get(k):
                return Utils.safe_float(raw[k])
        return self._last_deal.get((symbol, side), {}).get("price")

    # ==========================================================
    def _is_stale_snapshot(self, key, raw) -> bool:
        upd = raw.get("updateTime") or raw.get("timestamp") or 0
        hold = raw.get("holdVol")

        st = self._pos_state.get(key)
        if not st:
            self._pos_state[key] = {"upd": upd, "hold": hold}
            return False

        if hold == 0:
            self._pos_state[key] = {"upd": upd, "hold": hold}
            return False

        if upd < st["upd"]:
            return True
        if upd == st["upd"] and hold == st["hold"]:
            return True

        self._pos_state[key] = {"upd": upd, "hold": hold}
        return False

    # ==========================================================
    async def _route(self, ev: "SignalEvent"):
        et = ev.event_type
        symbol, pos_side = ev.symbol, ev.pos_side

        # ---------------- ATTACHED OCO ----------------
        if et == "stop_attached":
            self._attached_oco[symbol] = {
                "tp": Utils.safe_float(ev.raw.get("takeProfitPrice")),
                "sl": Utils.safe_float(ev.raw.get("stopLossPrice")),
            }
            return

        if not pos_side:
            return

        pv = self._ensure_pos_vars(symbol, pos_side)

        # ---------------- LIMIT OPEN / CLOSE ----------------
        if et in ("open_limit", "close_limit") and ev.raw.get("state") != 4:
            pv["_last_exec_source"] = "limit"

            await self._emit(
                event="buy" if et == "open_limit" else "sell",
                method="limit",
                symbol=symbol,
                pos_side=pos_side,
                partially=False,
                payload={
                    "order_id": ev.raw.get("orderId"),
                    "qty": Utils.safe_float(ev.raw.get("vol")),
                    "price": Utils.safe_float(ev.raw.get("price")),
                    "leverage": ev.raw.get("leverage"),
                    "open_type": ev.raw.get("openType"),
                    "reduce_only": bool(ev.raw.get("reduceOnly")),
                    "used_margin": Utils.safe_float(ev.raw.get("usedMargin")),
                },
                sig_type="copy",
                ev_raw=ev,
            )
            return

        # ---------------- LIMIT CANCEL ----------------
        if et in ("order_cancelled", "order_invalid"):
            pv["_last_exec_source"] = None

            await self._emit(
                event="canceled",
                method="limit",
                symbol=symbol,
                pos_side=pos_side,
                partially=False,
                payload={"order_id": ev.raw.get("orderId")},
                sig_type="copy",
                ev_raw=ev,
            )
            return

        # ---------------- DEAL ----------------
        if et == "deal":
            price = Utils.safe_float(ev.raw.get("price"))
            if price:
                self._last_deal[(symbol, pos_side)] = {"price": price, "ts": ev.ts}
            return

        # ---------------- TRIGGER ----------------
        if et in ("plan_order", "plan_executed", "plan_cancelled"):
            trigger_price = Utils.safe_float(
                ev.raw.get("triggerPrice") or ev.raw.get("price")
            )
            if not trigger_price:
                return

            pv["_last_exec_source"] = "trigger"

            if et == "plan_executed":
                event, sig = "filled", "log"
            elif et == "plan_order":
                event, sig = "buy" if ev.raw.get("side") in (1, 3) else "sell", "copy"
            else:
                event, sig = "canceled", "copy"

            await self._emit(
                event=event,
                method="trigger",
                symbol=symbol,
                pos_side=pos_side,
                partially=False,
                payload={
                    "order_id": ev.raw.get("orderId"),
                    "qty": Utils.safe_float(ev.raw.get("vol")),
                    "trigger_price": trigger_price,
                    "leverage": ev.raw.get("leverage"),
                    "open_type": ev.raw.get("openType"),
                    "reduce_only": bool(ev.raw.get("reduceOnly")),
                    "trigger_exec": ev.raw.get("triggerType"),
                },
                sig_type=sig,
                ev_raw=ev,
            )
            return

        # ---------------- POSITION SNAPSHOT ----------------
        if et in ("position_opened", "position_closed"):
            await self._on_position_snapshot(ev, pv)

    # ==========================================================
    async def _on_position_snapshot(self, ev: "SignalEvent", pv: dict):
        raw = ev.raw
        symbol, pos_side = ev.symbol, ev.pos_side
        key = (symbol, pos_side)

        if self._is_stale_snapshot(key, raw):
            return

        qty_prev = pv["qty"]
        qty_cur = Utils.safe_float(raw.get("holdVol"), 0.0)

        if qty_prev == qty_cur:
            return

        price = Utils.to_human_digit(self._fix_price(raw, symbol, pos_side))
        last_src = pv["_last_exec_source"]

        oco = self._attached_oco.pop(symbol, None)

        if oco:
            pv["_attached_tp"] = oco.get("tp")
            pv["_attached_sl"] = oco.get("sl")

        delta = abs(qty_cur - qty_prev)

        # ================= BUY =================
        if qty_cur > qty_prev:
            pv["qty"] = qty_cur
            pv["in_position"] = True

            payload = {
                "qty": delta,
                "price": price,
                "leverage": raw.get("leverage"),
                "open_type": raw.get("openType"),
                "reduce_only": False,
                "qty_delta": delta,
                "qty_before": qty_prev,
                "qty_after": qty_cur,
            }

            if pv.get("_attached_tp") is not None:
                payload["tp_price"] = pv["_attached_tp"]
            if pv.get("_attached_sl") is not None:
                payload["sl_price"] = pv["_attached_sl"]

            sig_type = (
                "log"
                if last_src in ("limit", "trigger") and qty_prev == 0
                else "copy"
            )

            await self._emit(
                event="buy",
                method="market",
                symbol=symbol,
                pos_side=pos_side,
                partially=qty_prev > 0,
                payload=payload,
                sig_type=sig_type,
                ev_raw=ev,
            )

            pv["_attached_tp"] = None
            pv["_attached_sl"] = None

        # ================= SELL =================
        elif qty_cur < qty_prev:
            pv["qty"] = qty_cur
            pv["in_position"] = qty_cur > 0

            is_full_close = qty_cur == 0
            sig_type = (
                "log"
                if last_src in ("limit", "trigger") and is_full_close
                else "copy"
            )

            payload = {
                "qty": delta,
                "price": price,
                "leverage": raw.get("leverage"),
                "open_type": raw.get("openType"),
                "reduce_only": True,
                "qty_delta": delta,
                "qty_before": qty_prev,
                "qty_after": qty_cur,
            }

            await self._emit(
                event="sell",
                method="market",
                symbol=symbol,
                pos_side=pos_side,
                partially=qty_cur > 0,
                payload=payload,
                sig_type=sig_type,
                ev_raw=ev,
                closed=is_full_close,
            )

            if is_full_close:
                self._pos_state.pop(key, None)
                self._last_deal.pop(key, None)

        if qty_prev == 0 and qty_cur > 0:
            pv["entry_price"] = price

        pv["avg_price"] = price
        pv["_last_exec_source"] = None

    # ==========================================================
    async def _emit(
        self,
        *,
        event: HL_EVENT,
        method: METHOD,
        symbol: str,
        pos_side: str,
        partially: bool,
        payload: Dict[str, Any],
        sig_type: Literal["copy", "log"],
        ev_raw: Optional["SignalEvent"],
        closed: bool = False,
    ):
        exec_ts = now()
        raw_ts = ev_raw.ts if ev_raw else None

        payload = dict(payload)
        payload["exec_ts"] = exec_ts
        payload["latency_ms"] = exec_ts - raw_ts if raw_ts else None

        self._pending.append(
            MasterEvent(
                event=event,
                method=method,
                symbol=symbol,
                pos_side=pos_side,
                partially=partially,
                closed=closed,
                payload=payload,
                sig_type=sig_type,
                ts=exec_ts,
            )
        )
