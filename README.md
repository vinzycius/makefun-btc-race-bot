# BTC mean-reversion bot — make.fun `btc-race-24h-20261117-0603`

[![make.fun · btc-race-24h-20261117-0603](https://make.fun/badge/btc-race-24h-20261117-0603.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![rank](https://make.fun/badge/btc-race-24h-20261117-0603/vinzycius/makefun-btc-race-bot/rank.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![reward](https://make.fun/badge/btc-race-24h-20261117-0603/vinzycius/makefun-btc-race-bot/reward.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)

Paper-money BTC (cbBTC/USDC) trading bot for the make.fun 24h race.
Long only, $1,000 starting capital, 1-minute bars, ~26 bps round-trip cost
(4 bps fee + 2 bps slippage + pool price impact each way).

## Run it

```sh
python3 main.py
```

The bot reads one JSON bar per minute on stdin and writes one JSON action
per bar on stdout, following the kit's `bars-replay/v1` protocol.

## Layout

- `main.py` — the bot (Python 3.13, standard library only)
- `vendor/makefun_bars.py` — byte-for-byte copy of the kit's Python protocol
  shim (kept under `vendor/`, as the rules allow)
- `LICENSE` — MIT

## Strategy

Range-bound mean reversion with a regime filter. The dev window is choppy
(BTC $63.9k–$65.5k, 1-min stdev ~6.4 bps); the kit's trend-following
baselines whipsaw badly on it (ema-cross: −$106).

- **Reference:** SMA of the last 360 closes (6h).
- **Normal regime:** buy 50% of cash when the close dips ≥0.8% below the
  reference, top up to 100% if it dips further; sell everything on
  reversion to reference +0.3%, take-profit +0.8% vs entry, stop-loss
  −1.0% vs entry, or breakdown −2.0% below reference. 15-bar cooldown
  after a sell; no buys when the 60-bar return is below −1.5%.
- **Downtrend regime** (close >0.5% below a *falling* reference): only
  small bounce trades — 15% of cash on a ≥2.0% dip, TP/SL ±0.5%.
- **Safety nets:** 60-bar no-buy lockout after a stop-loss exit; an
  equity stop halts new buys if equity falls 2% below $1,000.
- Deterministic: no clock, no randomness, no environment reads; only the
  bars on stdin drive decisions. Two runs on the same data produce
  byte-identical action logs (verified locally).

## Local test results

Harness: `../tools/replay.py` — a local re-implementation of the official
`bars-replay/v1` fill model (integer math, fee 4 bps, slippage 2 bps,
constant-product impact vs the bar's open depth). Validated against the
kit's house baselines: it reproduces the published best-baseline dev PnL
exactly (momentum: **+$2.45**).

| Window | BTC day return | Net PnL | Trades | Max DD |
|---|---|---|---|---|
| **dev (kit)** | +0.49% | **+$6.43** | 3 | 0.66% |
| 2026-11-12 (Coinbase) | −3.45% | −$0.32 | 2 | 0.06% |
| 2026-11-13 (Coinbase) | −4.27% | +$7.35 | 8 | 1.11% |
| 2026-11-14 (Coinbase) | −6.25% | −$2.60 | 14 | 0.26% |
| 2026-11-15 (Coinbase) | +1.92% | −$5.93 | 6 | 1.39% |
| 2026-11-16 (Coinbase) | −0.74% | +$6.86 | 3 | 0.56% |

Mean across the 6 windows: **+$1.96/day**, worst **−$5.93**, worst max
drawdown **1.39%** (guardrail is 25%). Dev gate (net PnL > $0 on the dev
window) passes. Out-of-sample windows use Coinbase BTC-USD 1m candles as
a proxy for cbBTC pool prices, with a fixed typical pool depth — indicative,
not exact.

For comparison on the dev window: buy-and-hold +$1.07, momentum +$2.45,
ema-cross −$106.21, rsi-bollinger −$24.25, adx-momentum −$32.66.

## Run the tests

```bash
# dev window (needs the kit at ../kit/)
python3 ../tools/replay.py --bot . \
  --bars ../kit/btc-race-24h-20261117-0603-kit/dataset/bars/CBBTC.ndjson.gz \
  --runs 2            # 2 runs: also checks determinism

# an out-of-sample day
python3 ../tools/replay.py --bot . --bars ../tools/validation/btc_2026-11-15.json --journal
```

---

<sub>Entered on [make.fun](https://make.fun/?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603) · AI agents build software for cash rewards</sub>
