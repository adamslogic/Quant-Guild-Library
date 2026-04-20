"""
Wheel strategy desk: Interactive Brokers + Tkinter.

Uses ib_insync (same TWS/Gateway protocol as the official ibapi Python package)
with a small worker thread so the GUI stays responsive.

Wheel rules (per symbol):
- Long stock >= 100 shares: sell covered calls targeting call_delta, only if
  strike >= average cost basis (maps the common "above cost basis" intent).
- Otherwise: sell cash-secured puts targeting put_delta.

Dry-run is ON by default; disable it only when you intend to send live orders.
This is educational software, not financial advice.
"""

from __future__ import annotations

import asyncio
import json
import math
import queue
import threading
import tkinter as tk
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Optional

try:
    from ib_insync import IB, LimitOrder, Option, PortfolioItem, Stock, util
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency. Install with:\n"
        "  pip install -r wheel_requirements.txt\n"
    ) from exc

# IB event loop in a background thread (safe with Tkinter main thread).
util.patchAsyncio()


STATE_PATH = Path(__file__).with_suffix(".state.json")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7497  # TWS live; paper TWS often 7497 on paper login; Gateway 4001/4002


@dataclass
class WheelRow:
    symbol: str
    put_delta: float = -0.25
    call_delta: float = 0.30
    dte_max: int = 45
    enabled: bool = True
    cost_basis_override: Optional[float] = None  # if None, use IB avg cost
    notes: str = ""

    def normalized_symbol(self) -> str:
        return self.symbol.strip().upper()


@dataclass
class AppState:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    client_id: int = 7
    dry_run: bool = True
    rows: list[WheelRow] = field(default_factory=list)


def load_state(path: Path = STATE_PATH) -> AppState:
    if not path.exists():
        return AppState(rows=[WheelRow(symbol="SPY")])
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = [WheelRow(**r) for r in data.get("rows", [])]
    return AppState(
        host=data.get("host", DEFAULT_HOST),
        port=int(data.get("port", DEFAULT_PORT)),
        client_id=int(data.get("client_id", 7)),
        dry_run=bool(data.get("dry_run", True)),
        rows=rows,
    )


def save_state(state: AppState, path: Path = STATE_PATH) -> None:
    payload: dict[str, Any] = {
        "host": state.host,
        "port": state.port,
        "client_id": state.client_id,
        "dry_run": state.dry_run,
        "rows": [asdict(r) for r in state.rows],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class IBWorker(threading.Thread):
    """Runs ib_insync on a dedicated thread."""

    def __init__(self, inbound: queue.Queue, outbound: queue.Queue) -> None:
        super().__init__(daemon=True)
        self.inbound = inbound
        self.outbound = outbound
        self.ib = IB()
        self._stop = threading.Event()

    def run(self) -> None:
        self.ib.run(self._loop())

    async def _loop(self) -> None:
        try:
            while not self._stop.is_set():
                msg = await self._next_inbound()
                if msg is None:
                    continue
                kind = msg.get("type")
                try:
                    if kind == "connect":
                        await self._connect(msg["host"], int(msg["port"]), int(msg["client_id"]))
                    elif kind == "disconnect":
                        if self.ib.isConnected():
                            self.ib.disconnect()
                        self._emit("status", connected=False, text="Disconnected")
                    elif kind == "shutdown":
                        if self.ib.isConnected():
                            self.ib.disconnect()
                        break
                    elif kind == "portfolio_refresh":
                        await self._portfolio_refresh()
                    elif kind == "wheel_tick":
                        await self._wheel_tick(msg["rows"], bool(msg.get("dry_run", True)))
                    else:
                        self._emit("log", text=f"Unknown command: {kind}")
                except Exception as exc:  # noqa: BLE001
                    self._emit("log", text=f"IB error: {exc!r}")
        finally:
            if self.ib.isConnected():
                self.ib.disconnect()

    async def _next_inbound(self) -> Optional[dict[str, Any]]:
        while not self._stop.is_set():
            try:
                return self.inbound.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.05)
        return None

    def stop(self) -> None:
        try:
            self.inbound.put_nowait({"type": "shutdown"})
        except queue.Full:
            self.inbound.put({"type": "shutdown"})
        self._stop.set()

    def _emit(self, kind: str, **kwargs: Any) -> None:
        self.outbound.put({"type": kind, **kwargs})

    async def _connect(self, host: str, port: int, client_id: int) -> None:
        if self.ib.isConnected():
            self.ib.disconnect()
        await self.ib.connectAsync(host, port, clientId=client_id, readonly=False, timeout=12)
        self._emit("status", connected=True, text=f"Connected {host}:{port} (clientId={client_id})")
        self._emit("log", text="Connection established.")

    async def _portfolio_refresh(self) -> None:
        if not self.ib.isConnected():
            self._emit("log", text="Not connected.")
            return
        portfolio = self.ib.portfolio()
        rows: list[dict[str, Any]] = []
        for p in portfolio:
            rows.append(portfolio_row_dict(p))
        self._emit("portfolio", rows=rows)

    async def _wheel_tick(self, rows: list[dict[str, Any]], dry_run: bool) -> None:
        if not self.ib.isConnected():
            self._emit("log", text="Wheel tick skipped: not connected.")
            return

        portfolio = self.ib.portfolio()
        for rd in rows:
            if not rd.get("enabled", True):
                continue
            sym = str(rd.get("symbol", "")).strip().upper()
            if not sym:
                continue
            try:
                await self._process_symbol(rd, portfolio, dry_run)
            except Exception as exc:  # noqa: BLE001
                self._emit("log", text=f"{sym}: {exc!r}")

    async def _process_symbol(self, rd: dict[str, Any], portfolio: list[Any], dry_run: bool) -> None:
        sym = str(rd["symbol"]).strip().upper()
        put_target = float(rd.get("put_delta", -0.25))
        call_target = float(rd.get("call_delta", 0.30))
        dte_max = int(rd.get("dte_max", 45))
        basis_override = rd.get("cost_basis_override")
        basis_override_f = float(basis_override) if basis_override not in (None, "", "None") else None

        stock_qty, stock_basis = stock_position_from_portfolio(portfolio, sym, basis_override_f)
        if stock_qty < 0:
            self._emit("log", text=f"{sym}: short stock — wheel automation skipped.")
            return
        has_short_call = has_short_option(portfolio, sym, right="C")
        has_short_put = has_short_option(portfolio, sym, right="P")

        u = Stock(sym, "SMART", "USD")
        await self.ib.qualifyContractsAsync(u)
        price = await self._underlying_px(u)
        if price is None or math.isnan(price):
            self._emit("log", text=f"{sym}: no underlying price; skipping.")
            return

        if stock_qty >= 100:
            if has_short_call:
                self._emit("log", text=f"{sym}: already short calls; no action.")
                return
            basis = stock_basis if stock_basis is not None else price
            exp = await pick_expiry(self.ib, u, dte_max)
            if not exp:
                self._emit("log", text=f"{sym}: no option expiries; skipping.")
                return
            opt = await best_call_by_delta(
                self.ib, u, exp, call_target, min_strike=basis, underlying_px=price
            )
            if opt is None:
                self._emit("log", text=f"{sym}: no suitable call (delta {call_target}, strike>={basis:.2f}).")
                return
            qty = max(1, int(stock_qty // 100))
            await self._sell_single_leg(opt, qty, dry_run, label=f"CC {sym} x{qty}")
        else:
            if has_short_put:
                self._emit("log", text=f"{sym}: already short puts; no action.")
                return
            exp = await pick_expiry(self.ib, u, dte_max)
            if not exp:
                self._emit("log", text=f"{sym}: no option expiries; skipping.")
                return
            opt = await best_put_by_delta(self.ib, u, exp, put_target, underlying_px=price)
            if opt is None:
                self._emit("log", text=f"{sym}: no suitable put (delta {put_target}).")
                return
            await self._sell_single_leg(opt, 1, dry_run, label=f"CSP {sym}")

    async def _underlying_px(self, u: Stock) -> Optional[float]:
        t = self.ib.reqMktData(u, "", True)
        try:
            for _ in range(40):
                await self.ib.sleepAsync(0.25)
                last = t.last
                close = t.close
                bid, ask = t.bid, t.ask
                if last and not math.isnan(last):
                    return float(last)
                if close and not math.isnan(close):
                    return float(close)
                if bid and ask and bid > 0 and ask > 0:
                    return (float(bid) + float(ask)) / 2
            return None
        finally:
            self.ib.cancelMktData(u)

    async def _sell_single_leg(self, opt: Option, qty: int, dry_run: bool, label: str) -> None:
        await self.ib.qualifyContractsAsync(opt)
        t = self.ib.reqMktData(opt, "", True)
        try:
            for _ in range(50):
                await self.ib.sleepAsync(0.2)
                bid = t.bid
                ask = t.ask
                if bid and ask and bid > 0 and ask > 0:
                    break
            bid = t.bid or 0.0
            ask = t.ask or 0.0
            mid = (bid + ask) / 2 if bid and ask else (bid or ask or 0.0)
            limit = round(max(mid * 0.95, bid * 0.98, 0.01), 2) if mid else None
        finally:
            self.ib.cancelMktData(opt)

        if limit is None:
            self._emit("log", text=f"{label}: no quote; not sending.")
            return

        if dry_run:
            self._emit(
                "log",
                text=f"[DRY RUN] SELL {qty} {opt.localSymbol} @ LMT {limit:.2f} ({label})",
            )
            return

        order = LimitOrder("SELL", float(qty), float(limit))
        trade = self.ib.placeOrder(opt, order)
        self._emit("log", text=f"Order sent: {trade} ({label})")


def portfolio_row_dict(p: PortfolioItem) -> dict[str, Any]:
    c = p.contract
    sym = getattr(c, "symbol", "") or ""
    return {
        "symbol": sym,
        "secType": getattr(c, "secType", ""),
        "right": getattr(c, "right", ""),
        "strike": float(getattr(c, "strike", 0) or 0),
        "expiry": getattr(c, "lastTradeDateOrContractMonth", ""),
        "position": float(p.position),
        "avgCost": float(p.averageCost),
        "marketPrice": float(p.marketPrice) if p.marketPrice is not None else None,
        "marketValue": float(p.marketValue) if p.marketValue is not None else None,
        "account": p.account,
    }


def stock_position_from_portfolio(
    portfolio: list[Any], symbol: str, basis_override: Optional[float]
) -> tuple[float, Optional[float]]:
    qty = 0.0
    basis: Optional[float] = basis_override
    for p in portfolio:
        c = p.contract
        if getattr(c, "symbol", "") != symbol:
            continue
        if getattr(c, "secType", "") != "STK":
            continue
        qty += float(p.position)
        if basis is None and float(p.position) != 0:
            # averageCost from IB is per-share for stock in many accounts
            basis = float(p.averageCost)
    return qty, basis


def has_short_option(portfolio: list[Any], symbol: str, right: str) -> bool:
    for p in portfolio:
        c = p.contract
        if getattr(c, "symbol", "") != symbol:
            continue
        if getattr(c, "secType", "") != "OPT":
            continue
        if getattr(c, "right", "") != right:
            continue
        if float(p.position) < 0:
            return True
    return False


async def pick_expiry(ib: IB, u: Stock, dte_max: int) -> Optional[str]:
    params = await ib.reqSecDefOptParamsAsync(u.symbol, "", u.secType, u.conId)
    if not params:
        return None
    p = params[0]
    today = date.today()
    target = min(30, max(7, dte_max // 2))
    scored: list[tuple[int, int, str]] = []
    for exp in p.expirations:
        try:
            y, m, d = int(exp[:4]), int(exp[4:6]), int(exp[6:8])
            dt = date(y, m, d)
        except Exception:  # noqa: BLE001
            continue
        dte = (dt - today).days
        if dte < 1 or dte > dte_max:
            continue
        scored.append((abs(dte - target), dte, exp))
    if not scored:
        return None
    scored.sort(key=lambda t: (t[0], t[1]))
    return scored[0][2]


async def best_call_by_delta(
    ib: IB,
    u: Stock,
    expiry: str,
    target_delta: float,
    min_strike: float,
    underlying_px: float,
) -> Optional[Option]:
    params = await ib.reqSecDefOptParamsAsync(u.symbol, "", u.secType, u.conId)
    if not params:
        return None
    p0 = params[0]
    tclass = getattr(p0, "tradingClass", "") or u.symbol
    strikes = sorted(float(s) for s in p0.strikes)
    strikes = [s for s in strikes if s >= min_strike and s >= underlying_px * 0.85]
    strikes = strikes[:24]  # cap IB pacing / latency
    if not strikes:
        return None

    best: Optional[tuple[float, Option]] = None
    for strike in strikes:
        opt = Option(
            u.symbol,
            expiry,
            strike,
            "C",
            "SMART",
            currency="USD",
            tradingClass=tclass,
        )
        g = await snapshot_delta(ib, opt)
        if g is None:
            continue
        err = abs(g - target_delta)
        if best is None or err < best[0]:
            best = (err, opt)
    return best[1] if best else None


async def best_put_by_delta(
    ib: IB, u: Stock, expiry: str, target_delta: float, underlying_px: float
) -> Optional[Option]:
    params = await ib.reqSecDefOptParamsAsync(u.symbol, "", u.secType, u.conId)
    if not params:
        return None
    p0 = params[0]
    tclass = getattr(p0, "tradingClass", "") or u.symbol
    strikes = sorted((float(s) for s in p0.strikes), reverse=True)
    strikes = [s for s in strikes if s <= underlying_px * 1.15]
    strikes = strikes[:24]
    if not strikes:
        return None

    best: Optional[tuple[float, Option]] = None
    for strike in strikes:
        opt = Option(
            u.symbol,
            expiry,
            strike,
            "P",
            "SMART",
            currency="USD",
            tradingClass=tclass,
        )
        g = await snapshot_delta(ib, opt)
        if g is None:
            continue
        err = abs(g - target_delta)
        if best is None or err < best[0]:
            best = (err, opt)
    return best[1] if best else None


async def snapshot_delta(ib: IB, opt: Option) -> Optional[float]:
    ok = await ib.qualifyContractsAsync(opt)
    if not ok:
        return None
    for glist in ("106", ""):
        t = ib.reqMktData(opt, glist, True)
        try:
            for _ in range(35):
                await ib.sleepAsync(0.12)
                mg = t.modelGreeks
                if mg and mg.delta is not None and not math.isnan(mg.delta):
                    return float(mg.delta)
        finally:
            ib.cancelMktData(opt)
    return None


class WheelApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Wheel desk (IB)")
        self.geometry("1100x720")

        self.state = load_state()
        self.inbound: queue.Queue = queue.Queue()
        self.outbound: queue.Queue = queue.Queue()
        self.worker = IBWorker(self.inbound, self.outbound)
        self.worker.start()

        self._build_ui()
        self.after(120, self._poll_outbound)

    def _build_ui(self) -> None:
        top = ttk.Frame(self, padding=8)
        top.pack(fill=tk.X)

        ttk.Label(top, text="Host").grid(row=0, column=0, sticky="w")
        self.host_var = tk.StringVar(value=self.state.host)
        ttk.Entry(top, textvariable=self.host_var, width=14).grid(row=0, column=1, padx=4)

        ttk.Label(top, text="Port").grid(row=0, column=2, sticky="w")
        self.port_var = tk.StringVar(value=str(self.state.port))
        ttk.Entry(top, textvariable=self.port_var, width=8).grid(row=0, column=3, padx=4)

        ttk.Label(top, text="Client ID").grid(row=0, column=4, sticky="w")
        self.client_var = tk.StringVar(value=str(self.state.client_id))
        ttk.Entry(top, textvariable=self.client_var, width=6).grid(row=0, column=5, padx=4)

        self.dry_run_var = tk.BooleanVar(value=self.state.dry_run)
        ttk.Checkbutton(top, text="Dry run (no orders)", variable=self.dry_run_var).grid(
            row=0, column=6, padx=8
        )

        ttk.Button(top, text="Connect", command=self._connect).grid(row=0, column=7, padx=4)
        ttk.Button(top, text="Disconnect", command=self._disconnect).grid(row=0, column=8, padx=4)

        ttk.Button(top, text="Refresh portfolio", command=self._refresh_portfolio).grid(
            row=0, column=9, padx=4
        )
        ttk.Button(top, text="Run wheel rules once", command=lambda: self._wheel_once(confirm_live=True)).grid(
            row=0, column=10, padx=4
        )

        self.auto_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Auto every 60s", variable=self.auto_var, command=self._toggle_auto).grid(
            row=0, column=11, padx=8
        )

        mid = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        mid.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        left = ttk.Frame(mid, padding=4)
        right = ttk.Frame(mid, padding=4)
        mid.add(left, weight=3)
        mid.add(right, weight=2)

        cols = ("symbol", "put_delta", "call_delta", "dte_max", "basis", "enabled", "notes")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
        headers = {
            "symbol": "Underlying",
            "put_delta": "Put Δ target",
            "call_delta": "Call Δ target",
            "dte_max": "Max DTE",
            "basis": "Basis override",
            "enabled": "On",
            "notes": "Notes",
        }
        widths = {
            "symbol": 90,
            "put_delta": 90,
            "call_delta": 90,
            "dte_max": 70,
            "basis": 110,
            "enabled": 50,
            "notes": 220,
        }
        for c in cols:
            self.tree.heading(c, text=headers[c])
            self.tree.column(c, width=widths[c], anchor="center" if c != "notes" else "w")

        vsb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        btns = ttk.Frame(left)
        btns.pack(fill=tk.X, pady=6)
        ttk.Button(btns, text="Add row", command=self._add_row).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="Delete row", command=self._del_row).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="Save state", command=self._save_state).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="Reload state", command=self._reload_state).pack(side=tk.LEFT, padx=2)

        ttk.Label(
            left,
            text=(
                "Rules: ≥100 shares → short covered calls at call Δ, strike ≥ cost basis. "
                "Otherwise → short puts at put Δ. Existing short same leg skips."
            ),
            wraplength=640,
        ).pack(anchor="w", pady=4)

        ttk.Label(right, text="Portfolio (from IB)").pack(anchor="w")
        pcols = ("symbol", "secType", "right", "strike", "expiry", "position", "avgCost")
        self.ptree = ttk.Treeview(right, columns=pcols, show="headings", height=14)
        for c in pcols:
            self.ptree.heading(c, text=c)
            self.ptree.column(c, width=88, anchor="center")
        self.ptree.pack(fill=tk.BOTH, expand=True)

        ttk.Label(right, text="Log").pack(anchor="w", pady=(8, 0))
        self.log = tk.Text(right, height=12, wrap="word")
        self.log.pack(fill=tk.BOTH, expand=True)

        self._load_rows_into_tree()

    def _log(self, text: str) -> None:
        self.log.insert("end", f"{datetime.now():%H:%M:%S}  {text}\n")
        self.log.see("end")

    def _poll_outbound(self) -> None:
        try:
            while True:
                msg = self.outbound.get_nowait()
                kind = msg.get("type")
                if kind == "log":
                    self._log(str(msg.get("text", "")))
                elif kind == "status":
                    # Could add a status bar; keep log for now
                    self._log(str(msg.get("text", "")))
                elif kind == "portfolio":
                    self._render_portfolio(msg.get("rows", []))
                else:
                    self._log(f"Event: {msg}")
        except queue.Empty:
            pass
        self.after(120, self._poll_outbound)

    def _render_portfolio(self, rows: list[dict[str, Any]]) -> None:
        for i in self.ptree.get_children():
            self.ptree.delete(i)
        for r in rows:
            self.ptree.insert(
                "",
                "end",
                values=(
                    r.get("symbol", ""),
                    r.get("secType", ""),
                    r.get("right", ""),
                    f'{r.get("strike", 0):g}',
                    r.get("expiry", ""),
                    f'{r.get("position", 0):g}',
                    f'{r.get("avgCost", 0):.4f}',
                ),
            )

    def _rows_from_tree(self) -> list[WheelRow]:
        rows: list[WheelRow] = []
        for iid in self.tree.get_children():
            v = self.tree.item(iid, "values")
            basis_raw = str(v[4]).strip()
            basis: Optional[float] = None
            if basis_raw and basis_raw.lower() not in ("none", "auto", "-"):
                try:
                    basis = float(basis_raw)
                except ValueError:
                    basis = None
            rows.append(
                WheelRow(
                    symbol=str(v[0]),
                    put_delta=float(v[1]),
                    call_delta=float(v[2]),
                    dte_max=int(float(v[3])),
                    cost_basis_override=basis,
                    enabled=str(v[5]).lower() in ("1", "true", "yes", "on", "y"),
                    notes=str(v[6]),
                )
            )
        return rows

    def _load_rows_into_tree(self) -> None:
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for r in self.state.rows:
            self.tree.insert(
                "",
                "end",
                values=(
                    r.symbol,
                    f"{r.put_delta:g}",
                    f"{r.call_delta:g}",
                    str(r.dte_max),
                    "" if r.cost_basis_override is None else f"{r.cost_basis_override:g}",
                    "yes" if r.enabled else "no",
                    r.notes,
                ),
            )

    def _add_row(self) -> None:
        self.tree.insert("", "end", values=("TICKER", "-0.25", "0.30", "45", "", "yes", ""))

    def _del_row(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        self.tree.delete(sel[0])

    def _save_state(self) -> None:
        self.state.host = self.host_var.get().strip() or DEFAULT_HOST
        self.state.port = int(self.port_var.get().strip() or str(DEFAULT_PORT))
        self.state.client_id = int(self.client_var.get().strip() or "7")
        self.state.dry_run = bool(self.dry_run_var.get())
        self.state.rows = self._rows_from_tree()
        save_state(self.state)
        self._log(f"State saved to {STATE_PATH}")

    def _reload_state(self) -> None:
        self.state = load_state()
        self.host_var.set(self.state.host)
        self.port_var.set(str(self.state.port))
        self.client_var.set(str(self.state.client_id))
        self.dry_run_var.set(self.state.dry_run)
        self._load_rows_into_tree()
        self._log("State reloaded.")

    def _connect(self) -> None:
        self._save_state()
        self.inbound.put(
            {
                "type": "connect",
                "host": self.host_var.get().strip() or DEFAULT_HOST,
                "port": int(self.port_var.get().strip() or str(DEFAULT_PORT)),
                "client_id": int(self.client_var.get().strip() or "7"),
            }
        )

    def _disconnect(self) -> None:
        self.inbound.put({"type": "disconnect"})

    def _refresh_portfolio(self) -> None:
        self.inbound.put({"type": "portfolio_refresh"})

    def _wheel_once(self, confirm_live: bool = True) -> None:
        if confirm_live and not self.dry_run_var.get():
            ok = messagebox.askyesno(
                "Confirm live trading",
                "Dry run is off. This step may submit real orders to Interactive Brokers. Continue?",
                icon="warning",
            )
            if not ok:
                return
        rows = [asdict(r) for r in self._rows_from_tree()]
        self.inbound.put({"type": "wheel_tick", "rows": rows, "dry_run": bool(self.dry_run_var.get())})

    def _toggle_auto(self) -> None:
        if self.auto_var.get():
            if not self.dry_run_var.get():
                self._log("Auto is on with dry run off: orders may be sent every 60s without further prompts.")
            self._schedule_auto()
        else:
            self._log("Auto wheel disabled.")

    def _schedule_auto(self) -> None:
        if not self.auto_var.get():
            return
        self._wheel_once(confirm_live=False)
        self._refresh_portfolio()
        self.after(60_000, self._schedule_auto)

    def destroy(self) -> None:
        try:
            self.worker.stop()
        finally:
            super().destroy()


def main() -> None:
    app = WheelApp()
    app.mainloop()


if __name__ == "__main__":
    main()
