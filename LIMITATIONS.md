# Limitations

This project is currently frozen as a dry-run-first runtime. The correct positioning is:

**AI Native Multi-Agent Market Runtime**

It must not be presented as an automatic profit system, AI crypto trading system, high-frequency arbitrage system, or quant fund platform.

## Dry-Run Only

Current validation is dry-run only. The system has not completed real trading validation and should not be treated as live-ready.

## No Institutional Quant Stack

The repository does not contain an institutional quant stack. It does not provide:

- portfolio optimization
- execution quality analytics
- market impact modeling
- formal backtesting with clean train/test separation
- production-grade order management
- independent risk systems
- audit-grade reconciliation

## Lightweight Risk Engine

`risk/risk_engine.py` provides a lightweight risk snapshot for runtime context. It is not a full VaR, stress testing, margin, exposure, or portfolio construction framework.

## Heuristic Fallback

Agent G fallback learning is deterministic and useful for keeping learning files fresh during dry-run. It is heuristic:

- no model weights are updated
- no embedding memory is trained
- no causal inference is performed
- no production trading edge is proven

## LLM And API Fragility

Many agents depend on LLM and external API availability. Dry-run logs have shown rate limits and connection/import failures. Current behavior is designed to fail closed or degrade, not to guarantee production uptime.

## Non-Production System

This is a research/runtime prototype. It has useful orchestration and dry-run safety properties, but it is not a production trading system.

## No Real Trading Validation

There is no validated real-money execution track record. Dry-run `success=0` confirms safety during observation, not profitability or live readiness.

## Frozen Stage

At this stage, the project should be sealed, stabilized, and documented. Further work should not add Agents, models, dashboards, databases, APIs, quant frameworks, or orchestrator rewrites unless a new stage is explicitly opened.
