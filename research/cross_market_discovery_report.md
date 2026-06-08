# Cross-Market Discovery Report (Phase 2 Observation)

**Generated:** 2026-06-07T05:26:08.522442+00:00  
**Type:** Read-only statistical research — no signals, no strategy/risk changes**  
**Principle:** Observation ≠ Experience

## Scope

Pairs studied: BTC↔ETH, BTC↔Funding, BTC↔PM Crypto, QQQ↔BTC, TQQQ↔BTC, SOXL↔BTC, DXY↔BTC, Gold↔BTC

## Summary Table

| Pair | n | Pearson (lag=0) | Spearman | Best lag | |r| lag | Confidence |
|------|---|-----------------|----------|----------|---------|------------|
| BTC ↔ ETH | 1617 | 0.84108102078568 | 0.8268263839198935 | 0 | 0.84108102078568 | high |
| BTC ↔ Funding | 93 | -0.16923747292488472 | -0.18119423472889498 | 2 | -0.19168214375843629 | low |
| BTC ↔ PM Crypto (live tape) | 2 | None | None | 0 | None | low |
| QQQ ↔ BTC | 1109 | 0.4338643010645598 | 0.391441976656809 | 0 | 0.4338643010645598 | high |
| TQQQ ↔ BTC | 1109 | 0.43275216025522667 | 0.39072053566817444 | 0 | 0.43275216025522667 | high |
| SOXL ↔ BTC | 1109 | 0.36576557045501634 | 0.36559798088023016 | 0 | 0.36576557045501634 | high |
| Gold ↔ BTC | 50 | 0.2194435328983689 | 0.26626650660264106 | -4 | 0.35756625161627775 | low |
| DXY ↔ BTC | 0 | None | None | None | None | insufficient_data |

## Pair Details

### BTC ↔ ETH

- Sample size: **1617**
- Pearson (lag=0): **0.84108102078568**
- Spearman (lag=0): **0.8268263839198935**
- Best lag: **0** (Pearson=0.84108102078568, n=1617)
- Vol ratio (A/B daily): **0.7388761478027218**

### BTC ↔ Funding

- Sample size: **93**
- Pearson (lag=0): **-0.16923747292488472**
- Spearman (lag=0): **-0.18119423472889498**
- Best lag: **2** (Pearson=-0.19168214375843629, n=91)
- Vol ratio (A/B daily): **596.060043247073**
- Note: lag>0 => A leads B

### BTC ↔ PM Crypto (live tape)

- Sample size: **2**
- Pearson (lag=0): **None**
- Spearman (lag=0): **None**
- Best lag: **0** (Pearson=None, n=0)
- Vol ratio (A/B daily): **None**

### QQQ ↔ BTC

- Sample size: **1109**
- Pearson (lag=0): **0.4338643010645598**
- Spearman (lag=0): **0.391441976656809**
- Best lag: **0** (Pearson=0.4338643010645598, n=1109)
- Vol ratio (A/B daily): **0.48581649122904624**

### TQQQ ↔ BTC

- Sample size: **1109**
- Pearson (lag=0): **0.43275216025522667**
- Spearman (lag=0): **0.39072053566817444**
- Best lag: **0** (Pearson=0.43275216025522667, n=1109)
- Vol ratio (A/B daily): **1.445833070556269**

### SOXL ↔ BTC

- Sample size: **1109**
- Pearson (lag=0): **0.36576557045501634**
- Spearman (lag=0): **0.36559798088023016**
- Best lag: **0** (Pearson=0.36576557045501634, n=1109)
- Vol ratio (A/B daily): **2.3395286295928184**

### Gold ↔ BTC

- Sample size: **50**
- Pearson (lag=0): **0.2194435328983689**
- Spearman (lag=0): **0.26626650660264106**
- Best lag: **-4** (Pearson=0.35756625161627775, n=46)
- Vol ratio (A/B daily): **0.6128391159443732**
- Note: lag>0 => A leads B

### DXY ↔ BTC

- Sample size: **0**
- Pearson (lag=0): **None**
- Spearman (lag=0): **None**
- Best lag: **None** (Pearson=None, n=0)
- Note: dxy_daily.jsonl missing; see research/dxy_manual_input_spec.md

## Data Sources

- `shared_intelligence/history/markets/{BTC,ETH,QQQ,TQQQ,SOXL}.json`
- `data/historical/okx_BTC_USDT_SWAP_funding_rate_*.json`
- `data/historical/commodities_march_april_2026.json` (gold hourly → daily)
- `shared_intelligence/history/replay_dataset.jsonl` (PM crypto proxy)

## Prohibited

This report does NOT generate trading signals or modify agents/strategy/risk.
