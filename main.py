"""Mean-reversion BTC bot for make.fun btc-race-24h-20261117-0603 (v2).

Regime-aware: the dev window is range-bound, but out-of-sample BTC days in
Nov 2026 include -3% to -6% downtrends where blind dip-buying loses $25-75.
v2 adds:
  - a regime filter (price vs 360-bar mean + mean slope): in a downtrend it
    only takes small bounce trades (deep dip + 1-bar uptick + tight stops);
  - a bounce confirmation on normal buys (close above the previous close);
  - a lockout after a stop-loss exit (no re-buy until the price is back
    above the reference or the lockout expires), so it cannot catch the
    same falling knife repeatedly.

Long only, at most one position, deterministic (no clock, no randomness).
Standard library only; the makefun_bars shim is vendored.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"

# ---- tunable parameters ----
W_REF = 360        # reference window (bars) for the mean
W_FAST = 60        # fast trend window (bars)
BUY1 = 0.005       # normal-regime first dip level vs reference: buy 50% of cash
BUY2 = 0.009       # normal-regime second dip level: buy the rest
SELL_REF = 0.003   # sell when close >= reference * (1 + SELL_REF)
TP = 0.008         # take profit vs average entry price
SL = 0.010         # stop loss vs average entry price
BREAK = 0.020      # emergency exit when close <= reference * (1 - BREAK)
COOLDOWN = 15      # bars to wait after a normal sell before buying again
TREND_GUARD = -0.03   # skip buys when the 60-bar return is below this
REGIME_DIP = 0.005    # downtrend if close < ref*(1-REGIME_DIP) and ref falling
REGIME_ON = True
EQUITY_STOP = 0.02    # halt new buys once equity falls this far below $1000
DOWN_BUY = 0.012
DOWN_SIZE = 0.15
DOWN_TP = 0.005       # downtrend take profit
DOWN_SL = 0.005       # downtrend stop loss
LOCKOUT = 60          # bars of no-buy after a stop-loss exit
BOUNCE = False         # require close > previous close to buy (too strict: kills entries)
FAST_CAP = True        # normal buys also require close <= 60-bar mean (blocks buying
                       # a "dip" vs the slow mean that is actually near the recent highs)
MAX_SLIP_BPS = 100    # cap vs latest close

_closes = []
_last_sell_seq = -10**9
_lockout_until = -10**9
_downtrade = False    # current open position is a downtrend bounce trade


def _sma(xs, n):
    return sum(xs[-n:]) / n


def _entry_price(state):
    h = state.positions.get(SYMBOL)
    if not h or not h.qty:
        return None
    return h.cost * 10 ** (8 + 5) // (h.qty * 10 ** 6)


def on_batch(state, batch):
    global _last_sell_seq, _lockout_until, _downtrade
    if state.warming_up:
        return []
    bars = [b for b in batch.get("bars", []) if b.get("symbol") == SYMBOL]
    if not bars:
        return []
    close = state.close(SYMBOL)
    if close is None:
        return []
    prev_close = _closes[-1] if _closes else close
    _closes.append(close)
    if len(_closes) < W_REF:
        return []

    ref = _sma(_closes, W_REF)
    fast = _sma(_closes, W_FAST)
    # reference slope: needs W_REF + W_FAST closes; neutral until then
    if len(_closes) >= W_REF + W_FAST:
        ref_ago = _sma(_closes[:-W_FAST], W_REF)
        ref_falling = ref < ref_ago
    else:
        ref_falling = False
    ret60 = close / _closes[-W_FAST - 1] - 1.0
    downtrend = REGIME_ON and close < ref * (1.0 - REGIME_DIP) and ref_falling
    bounced = (not BOUNCE) or close > prev_close

    held = state.positions.get(SYMBOL)
    qty = held.qty if held else 0
    equity = state.equity
    pos_value = state.value(SYMBOL, qty) if qty else 0
    pos_frac = pos_value / equity if equity > 0 else 0.0

    if qty:
        entry = _entry_price(state)
        tp = DOWN_TP if _downtrade else TP
        sl = DOWN_SL if _downtrade else SL
        if (
            close >= ref * (1.0 + SELL_REF)
            or (entry is not None and close >= entry * (1.0 + tp))
            or (entry is not None and close <= entry * (1.0 - sl))
            or close <= ref * (1.0 - BREAK)
        ):
            hit_sl = entry is not None and close <= entry * (1.0 - sl)
            orders = [{"side": "sell", "symbol": SYMBOL, "qty": qty,
                       "max_slippage_bps": MAX_SLIP_BPS}]
            _last_sell_seq = state.seq
            if hit_sl:
                _lockout_until = state.seq + LOCKOUT
            _downtrade = False
            return orders
        # scale in deeper on a further dip (normal regime only, once)
        if (not _downtrade and pos_frac < 0.99 and close <= ref * (1.0 - BUY2)
                and ret60 >= TREND_GUARD and bounced
                and (not FAST_CAP or close <= fast)):
            room = state.cash
            if room >= 1_000_000:
                return [{"side": "buy", "symbol": SYMBOL,
                         "notional_quote_units": room,
                         "max_slippage_bps": MAX_SLIP_BPS}]
        return []

    # flat: look for a buy
    if state.seq - _last_sell_seq < COOLDOWN:
        return []
    if state.equity <= 1_000_000_000 * (1.0 - EQUITY_STOP):
        return []  # equity stop: stop opening new trades for the rest of the run
    if state.seq < _lockout_until and close < ref:
        return []
    if ret60 < TREND_GUARD:
        return []
    if not bounced:
        return []
    if downtrend:
        if close <= ref * (1.0 - DOWN_BUY):
            spend = int(state.cash * DOWN_SIZE)
            if spend >= 1_000_000:
                _downtrade = True
                return [{"side": "buy", "symbol": SYMBOL,
                         "notional_quote_units": spend,
                         "max_slippage_bps": MAX_SLIP_BPS}]
        return []
    if close <= ref * (1.0 - BUY1) and (not FAST_CAP or close <= fast):
        spend = state.cash // 2
        if spend >= 1_000_000:
            return [{"side": "buy", "symbol": SYMBOL,
                     "notional_quote_units": spend,
                     "max_slippage_bps": MAX_SLIP_BPS}]
    return []


makefun_bars.run(on_batch)
