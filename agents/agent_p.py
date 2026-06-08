"""
Agent P - 持仓管理监控
职责：监控持仓，生成止盈止损信号
"""

import json
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from _paths import get_base_dir, get_pm_trader, get_pm_trader_env

_DEFAULT_STOP_LOSS = -0.10


def normalize_stop_loss(value, default=_DEFAULT_STOP_LOSS):
    """将 stop_loss 归一化为 float。

    兼容来源：
    - float / int：直接返回
    - dict：按优先级尝试 value / pct / percent / stop_loss /
            stop_loss_pct / threshold / max / min
    - None 或非法类型：返回 default 并打印 WARNING
    """
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ("value", "pct", "percent", "stop_loss",
                    "stop_loss_pct", "threshold", "max", "min"):
            candidate = value.get(key)
            if isinstance(candidate, (int, float)):
                return float(candidate)
        print(f"[Agent P] WARNING: stop_loss dict 无可用数值字段 {value!r}，"
              f"使用默认值 {default}")
        return default
    print(f"[Agent P] WARNING: stop_loss 类型非法 "
          f"({type(value).__name__}: {value!r})，使用默认值 {default}")
    return default


def valid_price(value):
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None
    return price


def normalize_outcome(value):
    outcome = str(value or "").strip().upper()
    if outcome in ("BUY_YES", "YES"):
        return "YES"
    if outcome in ("BUY_NO", "NO"):
        return "NO"
    return outcome


def _is_dry_run_mode() -> bool:
    return os.environ.get("EXECUTOR_DRY_RUN", "").lower() in ("1", "true", "yes")


def position_dedup_key(pos: dict):
    """合并去重键：(market_id 或 slug, outcome)。"""
    mid = str(pos.get("market_id") or "").strip()
    slug = str(
        pos.get("market_slug") or pos.get("slug") or pos.get("market") or ""
    ).strip()
    outcome = normalize_outcome(pos.get("outcome") or pos.get("direction"))
    ident = mid or slug
    if not ident or not outcome:
        return None
    return (ident, outcome)


def price_from_market(market, outcome):
    outcomes = market.get("outcomes") or []
    prices = market.get("outcome_prices") or []
    if isinstance(outcomes, str):
        try:
            outcomes = json.loads(outcomes)
        except Exception:
            outcomes = []
    if isinstance(prices, str):
        try:
            prices = json.loads(prices)
        except Exception:
            prices = []

    target = normalize_outcome(outcome)
    for index, candidate in enumerate(outcomes):
        if normalize_outcome(candidate) == target and index < len(prices):
            return valid_price(prices[index])
    return None


class AgentP:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.config_dir = self.base_dir / "config"
        self.data_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
    
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Agent P] {message}"
        print(log_msg)
        
        log_file = self.logs_dir / f"agent_p_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_msg + "\n")
    
    def load_config(self):
        """加载系统配置"""
        config_file = self.config_dir / "system_config.json"
        
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.log(f"⚠️  加载配置失败: {e}")
            return {}
    
    def get_pm_trader_portfolio(self) -> list:
        """从 pm-trader 拉取持仓（legacy / live 快照）。"""
        try:
            result = subprocess.run(
                [get_pm_trader(), "portfolio"],
                capture_output=True,
                text=True,
                timeout=30,
                env=get_pm_trader_env()
            )

            if result.returncode == 0:
                data = json.loads(result.stdout)
                if data.get("ok"):
                    return data.get("data", [])

            self.log(f"❌ 获取持仓失败: {result.stderr}")
            return []

        except Exception as e:
            self.log(f"❌ 获取持仓异常: {e}")
            return []

    def load_paper_open_positions(self) -> list[dict]:
        """读取 paper_portfolio.json 中未平仓的 paper 持仓。"""
        portfolio_file = self.data_dir / "paper_portfolio.json"
        if not portfolio_file.exists():
            return []
        try:
            with open(portfolio_file) as f:
                raw = json.load(f)
        except Exception as e:
            self.log(f"⚠️  加载 paper_portfolio 失败: {e}")
            return []

        open_positions = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            if item.get("closed_at"):
                continue
            if str(item.get("status", "")).lower() == "closed":
                continue
            open_positions.append(item)
        return open_positions

    def _resolve_current_price_no_fallback(self, pos, latest_data=None):
        """解析当前市价；无可靠价格时返回 None（不用 entry 价冒充现价）。"""
        for key in ("live_price", "current_price"):
            price = valid_price(pos.get(key))
            if price is not None:
                return price, "current_price"

        for key in ("mid", "bid", "ask"):
            price = valid_price(pos.get(key))
            if price is not None:
                return price, key

        latest_data = latest_data or {}
        markets = latest_data.get("polymarket_markets") or []
        market_id = str(pos.get("market_id") or "").strip()
        market_slug = str(pos.get("market_slug") or "").strip()
        market_question = str(
            pos.get("market_question") or pos.get("market_name") or ""
        ).strip()

        for market in markets:
            if not isinstance(market, dict):
                continue
            latest_ids = {
                str(market.get("id") or "").strip(),
                str(market.get("market_id") or "").strip(),
            }
            latest_slugs = {
                str(market.get("slug") or "").strip(),
                str(market.get("market_slug") or "").strip(),
            }
            latest_question = str(
                market.get("question") or market.get("market_question") or ""
            ).strip()
            matched = (
                bool(market_id and market_id in latest_ids)
                or bool(market_slug and market_slug in latest_slugs)
                or bool(market_question and market_question == latest_question)
            )
            if not matched:
                continue

            price = price_from_market(market, pos.get("outcome"))
            if price is not None:
                return price, "market_price"

        for key in ("last_known_price", "last_price", "previous_price", "mark_price"):
            price = valid_price(pos.get(key))
            if price is not None:
                return price, key

        return None, "missing"

    def normalize_paper_position(self, raw: dict, latest_data: dict | None = None) -> dict:
        """将 paper_portfolio 条目归一化为 Agent P analyze_positions 可识别格式。"""
        latest_data = latest_data or {}
        market_slug = str(
            raw.get("market_slug") or raw.get("slug") or raw.get("market") or ""
        )
        outcome = str(raw.get("direction") or raw.get("outcome") or "").lower()
        entry = valid_price(raw.get("entry_price") or raw.get("avg_entry_price")) or 0.0

        probe_pos = {
            "market_id": str(raw.get("market_id") or ""),
            "market_slug": market_slug,
            "outcome": outcome,
            "market_question": raw.get("market_name") or raw.get("question") or "",
        }
        current_price, _ = self._resolve_current_price_no_fallback(probe_pos, latest_data)
        percent_pnl = 0.0
        if current_price is not None and entry > 0:
            percent_pnl = (current_price - entry) / entry * 100.0

        shares = raw.get("shares")
        if shares is None:
            shares = raw.get("position_size")

        return {
            "market_id": str(raw.get("market_id") or ""),
            "market_slug": market_slug,
            "slug": market_slug,
            "market": str(raw.get("market") or market_slug),
            "outcome": outcome,
            "avg_entry_price": entry,
            "entry_price": entry,
            "shares": shares,
            "position_size": raw.get("position_size"),
            "opened_at": raw.get("opened_at", ""),
            "source": raw.get("source", ""),
            "grade": raw.get("grade", ""),
            "source_agent": raw.get("source_agent", ""),
            "signal_origin": raw.get("signal_origin", ""),
            "generated_cycle_id": raw.get("generated_cycle_id", ""),
            "probe": raw.get("probe", False),
            "live_price": current_price,
            "percent_pnl": percent_pnl,
            "status": "open",
            "portfolio_source": "paper_portfolio",
            "dry_run": True,
        }

    def merge_portfolios(
        self,
        pm_positions: list,
        paper_raw: list[dict],
        latest_data: dict | None = None,
    ) -> list:
        """pm-trader + paper 合并去重（pm-trader 优先）。"""
        latest_data = latest_data or self.load_latest_data()
        merged: list = []
        seen: set[tuple] = set()

        for pos in pm_positions:
            key = position_dedup_key(pos)
            if key:
                seen.add(key)
            merged.append(pos)

        for raw in paper_raw:
            norm = self.normalize_paper_position(raw, latest_data)
            key = position_dedup_key(norm)
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            merged.append(norm)

        return merged

    def get_portfolio(self):
        """获取当前持仓；dry-run 下合并 paper_portfolio open 仓。"""
        pm_positions = self.get_pm_trader_portfolio()

        if not _is_dry_run_mode():
            self.log(f"📊 当前持仓：{len(pm_positions)} 个")
            self.save_positions(pm_positions)
            return pm_positions

        paper_raw = self.load_paper_open_positions()
        latest_data = self.load_latest_data()
        merged = self.merge_portfolios(pm_positions, paper_raw, latest_data)
        self.log(
            f"📊 pm_trader_positions={len(pm_positions)} "
            f"paper_positions={len(paper_raw)} "
            f"merged_positions={len(merged)}"
        )
        self.save_positions(merged)
        return merged

    def save_positions(self, positions):
        """保存最新持仓快照，供策略和健康检查使用。

        写入时合并 closed_registry 状态：已在 registry 中的持仓标记
        status=closed，其余标记 status=open。这使 positions.json 始终
        反映真实的生命周期状态，同时不丢失 pm-trader 返回的原始数据。
        """
        registry = self.load_closed_registry()
        annotated = []
        for pos in positions:
            key = (
                str(pos.get("market_slug") or ""),
                str(pos.get("outcome") or ""),
            )
            if key in registry:
                record = registry[key]
                annotated.append({
                    **pos,
                    "status": "closed",
                    "closed_at": record.get("closed_at", ""),
                    "exit_price": record.get("exit_price"),
                    "close_reason": record.get("close_reason", ""),
                    "close_source": record.get("close_source", ""),
                })
            else:
                annotated.append({**pos, "status": "open"})

        # Phase 0 写入收敛：经 runtime.datastore 门面（json 输出不变：indent=2, ensure_ascii=False）
        from runtime import datastore as _ds
        _ds.set_positions(annotated, base_dir=self.base_dir)
        self.log(f"✅ 持仓快照已保存到 {self.data_dir / 'positions.json'}")
    
    def load_strategy_config(self):
        """加载动态策略配置"""
        config_file = self.data_dir / "strategy_config.json"
        
        if not config_file.exists():
            self.log("⚠️  无策略配置，使用默认参数")
            return None
        
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
            self.log("✅ 加载动态策略配置")
            return config
        except Exception as e:
            self.log(f"⚠️  加载策略配置失败: {e}")
            return None
    
    def load_learning_knowledge(self):
        """加载学习知识库"""
        kb_file = self.data_dir / "learning_knowledge_base.json"
        
        if not kb_file.exists():
            self.log("⚠️  无学习知识库")
            return None
        
        try:
            with open(kb_file, 'r') as f:
                kb = json.load(f)
            self.log("✅ 加载学习知识库")
            return kb
        except Exception as e:
            self.log(f"⚠️  加载学习知识库失败: {e}")
            return None

    # ------------------------------------------------------------------
    # positions 生命周期注册表
    # ------------------------------------------------------------------

    def load_closed_registry(self) -> dict:
        """从 positions_closed_registry.json 加载已关闭持仓注册表。

        返回 {(market_slug, outcome): record_dict} 字典，key 为 tuple。
        文件不存在或解析失败时返回空字典（安全降级）。
        """
        registry_file = self.data_dir / "positions_closed_registry.json"
        if not registry_file.exists():
            return {}
        try:
            with open(registry_file) as f:
                records = json.load(f)
            return {
                (str(r.get("market_slug", "")), str(r.get("outcome", ""))): r
                for r in records
                if r.get("market_slug") and r.get("outcome")
            }
        except Exception as e:
            self.log(f"⚠️  加载 closed registry 失败: {e}")
            return {}

    def update_closed_registry(self, sell_signals: list):
        """将 priority=urgent 的止损信号写入持仓关闭注册表，避免下轮重复生成。

        仅对 urgent 信号操作（止损、紧急止损），不影响止盈 / 中低优先级信号。
        幂等：同一 (market_slug, outcome) 已在注册表时不重复写入。
        """
        registry_file = self.data_dir / "positions_closed_registry.json"
        existing: list = []
        if registry_file.exists():
            try:
                with open(registry_file) as f:
                    existing = json.load(f)
            except Exception:
                existing = []

        existing_keys = {
            (str(r.get("market_slug", "")), str(r.get("outcome", "")))
            for r in existing
        }
        now = datetime.now().isoformat()
        added = 0
        for sig in sell_signals:
            if sig.get("priority") != "urgent":
                continue
            slug = str(sig.get("market_slug") or sig.get("market") or "")
            outcome = str(sig.get("outcome") or "")
            key = (slug, outcome)
            if not slug or key in existing_keys:
                continue
            existing.append({
                "market_slug": slug,
                "outcome": outcome,
                "closed_at": now,
                "exit_price": sig.get("price"),
                "close_reason": sig.get("reason", "stop_loss"),
                "close_source": "agent_p_stop_loss",
                "pnl": sig.get("pnl"),
            })
            existing_keys.add(key)
            added += 1

        if added:
            # Phase 0 写入收敛：经 runtime.datastore 门面（json 输出不变）
            from runtime import datastore as _ds
            _ds.upsert_closed_positions(existing, base_dir=self.base_dir)
            self.log(f"✅ closed registry 更新：新增 {added} 条，合计 {len(existing)} 条")

    def load_latest_data(self):
        data_file = self.data_dir / "latest_data.json"
        if not data_file.exists():
            return {}
        try:
            with open(data_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.log(f"⚠️  加载 latest_data 失败: {e}")
            return {}
    
    def get_market_category(self, market_slug):
        """识别市场类别"""
        market_lower = market_slug.lower()
        
        if any(sport in market_lower for sport in ['nhl', 'nba', 'nfl', 'mlb', 'soccer', 'football']):
            return 'sports'
        elif any(crypto in market_lower for crypto in ['btc', 'bitcoin', 'eth', 'ethereum', 'crypto']):
            return 'crypto'
        elif any(pol in market_lower for pol in ['trump', 'biden', 'election', 'president', 'democrat', 'republican']):
            return 'politics'
        elif any(ent in market_lower for ent in ['gta', 'movie', 'album', 'celebrity']):
            return 'entertainment'
        else:
            return 'default'

    def resolve_exit_price(self, pos, latest_data=None):
        for key in ("live_price", "current_price"):
            price = valid_price(pos.get(key))
            if price is not None:
                return price, "current_price"

        for key in ("mid", "bid", "ask"):
            price = valid_price(pos.get(key))
            if price is not None:
                return price, key

        latest_data = latest_data or {}
        markets = latest_data.get("polymarket_markets") or []
        market_id = str(pos.get("market_id") or "").strip()
        market_slug = str(pos.get("market_slug") or "").strip()
        market_question = str(pos.get("market_question") or pos.get("market_name") or "").strip()

        for market in markets:
            if not isinstance(market, dict):
                continue
            latest_ids = {
                str(market.get("id") or "").strip(),
                str(market.get("market_id") or "").strip(),
            }
            latest_slugs = {
                str(market.get("slug") or "").strip(),
                str(market.get("market_slug") or "").strip(),
            }
            latest_question = str(market.get("question") or market.get("market_question") or "").strip()
            matched = (
                bool(market_id and market_id in latest_ids)
                or bool(market_slug and market_slug in latest_slugs)
                or bool(market_question and market_question == latest_question)
            )
            if not matched:
                continue

            price = price_from_market(market, pos.get("outcome"))
            if price is not None:
                return price, "market_price"

        for key in ("last_known_price", "last_price", "previous_price", "mark_price"):
            price = valid_price(pos.get(key))
            if price is not None:
                return price, "last_known_price"

        for key in ("avg_entry_price", "entry_price"):
            price = valid_price(pos.get(key))
            if price is not None:
                return price, "entry_price_fallback"

        return None, "missing"

    def build_sell_signal(self, pos, reason, priority, pnl_percent, category, latest_data=None):
        market_slug = pos.get("market_slug")
        price, price_source = self.resolve_exit_price(pos, latest_data)
        signal_reason = reason
        warning = None
        if price is None:
            price_source = "missing"
            warning = "missing_exit_price"
            signal_reason = f"{reason} [missing_exit_price]"

        signal = {
            "market_id": pos.get("market_id"),
            "market": market_slug,
            "market_slug": market_slug,
            "outcome": pos.get("outcome"),
            "shares": pos.get("shares"),
            "price": price,
            "price_source": price_source,
            "reason": signal_reason,
            "priority": priority,
            "pnl": pnl_percent,
            "category": category
        }
        if warning:
            signal["warning"] = warning
        return signal
    
    def analyze_positions(self, positions):
        """分析持仓，生成卖出信号（使用动态策略）"""
        self.log("分析持仓...")

        # 加载已关闭持仓注册表，跳过已处理的持仓
        # status=closed 检查不依赖 registry 是否为空，两者独立生效。
        closed_registry = self.load_closed_registry()
        before = len(positions)
        positions = [
            p for p in positions
            if p.get("status") != "closed"
            and (str(p.get("market_slug") or ""), str(p.get("outcome") or ""))
            not in closed_registry
        ]
        skipped = before - len(positions)
        if skipped:
            self.log(
                f"⏭️  跳过 {skipped} 个已关闭持仓（来自 closed registry 或 status=closed）"
            )
        self.log(f"skipped_closed={skipped}")

        # 加载动态策略配置
        strategy_config = self.load_strategy_config()
        learning_kb = self.load_learning_knowledge()
        latest_data = self.load_latest_data()

        # 默认参数（如果没有动态配置）
        default_take_profit = 0.15
        default_stop_loss = -0.10
        trailing_trigger = 0.20
        trailing_percent = 0.05

        # Phase 3b：价格历史（波动退出）。slug→id 映射从 latest_data 取，按 id 查历史。
        # 读 data/market_price_history.json 事实源，不依赖旁路 DB；样本不足时 helper 自动不触发。
        try:
            from runtime import price_history as _ph
            price_hist = _ph.load_history(self.base_dir)
        except Exception:
            _ph, price_hist = None, {}
        slug2id = {}
        for m in (latest_data or {}).get("polymarket_markets", []) or []:
            if m.get("slug") and m.get("id"):
                slug2id[m["slug"]] = str(m["id"])
        vol_threshold = 0.08
        if strategy_config:
            vol_threshold = strategy_config.get("volatility_exit", {}).get("threshold", 0.08)

        sell_signals = []
        gta_vi_positions = []

        for pos in positions:
            market_slug = pos.get("market_slug", "")
            pnl_percent = pos.get("percent_pnl", 0) / 100
            category = self.get_market_category(market_slug)
            
            # 检查 GTA VI 相关性
            if "gta" in market_slug.lower() and "vi" in market_slug.lower():
                gta_vi_positions.append(pos)
            
            # 根据市场类别和策略配置，动态设置止盈止损
            if strategy_config:
                take_profit_range = strategy_config.get("take_profit", {}).get(category, strategy_config.get("take_profit", {}).get("default", {"min": 0.10, "max": 0.15}))
                take_profit = take_profit_range.get("max", default_take_profit)
                
                # 根据置信度设置止损（这里简化处理，使用中等置信度）
                raw_stop_loss = strategy_config.get("stop_loss", {}).get("medium_confidence", default_stop_loss)
                stop_loss = normalize_stop_loss(raw_stop_loss, default=default_stop_loss)
                
                # 获利回撤参数
                trailing_config = strategy_config.get("trailing_stop", {})
                trailing_trigger = trailing_config.get("trigger_profit", 0.20)
                trailing_percent = trailing_config.get("trailing_percent", 0.05)
            else:
                take_profit = default_take_profit
                stop_loss = default_stop_loss
            
            # 止盈
            if pnl_percent >= take_profit:
                sell_signals.append(self.build_sell_signal(
                    pos,
                    f"止盈 ({pnl_percent:.2%}, 目标 {take_profit:.0%})",
                    "high",
                    pnl_percent,
                    category,
                    latest_data,
                ))
            
            # 止损
            elif pnl_percent <= stop_loss:
                sell_signals.append(self.build_sell_signal(
                    pos,
                    f"止损 ({pnl_percent:.2%}, 阈值 {stop_loss:.0%})",
                    "urgent",
                    pnl_percent,
                    category,
                    latest_data,
                ))
            
            # 获利回撤止盈（当浮盈达到 trigger 后，从【真实历史最高点】回撤 trailing_percent 才卖）
            # Phase 3b 尾巴：用 price_history 的真实最高水位，替换原「假设当前=最高点」的简化实现。
            elif pnl_percent >= trailing_trigger:
                peak_pnl = self._peak_pnl_from_history(pos, market_slug, _ph, price_hist, slug2id)
                if peak_pnl is None:
                    # 无足够价格历史 → 回退保守旧行为（达 trigger 即止盈），不因缺数据而漏退出
                    sell_signals.append(self.build_sell_signal(
                        pos,
                        f"获利回撤止盈 ({pnl_percent:.2%}, 无峰值历史回退)",
                        "high",
                        pnl_percent,
                        category,
                        latest_data,
                    ))
                elif (peak_pnl - pnl_percent) >= trailing_percent:
                    # 从真实峰值回撤达阈值 → 卖出锁利
                    sell_signals.append(self.build_sell_signal(
                        pos,
                        f"获利回撤止盈 (峰值 {peak_pnl:.2%}→现 {pnl_percent:.2%}, "
                        f"回撤 {peak_pnl - pnl_percent:.2%} ≥ {trailing_percent:.0%})",
                        "high",
                        pnl_percent,
                        category,
                        latest_data,
                    ))
                # else: 仍在峰值附近（回撤不足）→ 持有，让利润奔跑（不生成卖出信号）
            
            # 小幅盈利但接近止损（保护利润）
            elif 0.02 <= pnl_percent < take_profit:
                # 检查是否有回撤风险
                if pos.get("live_price", 0) < pos.get("avg_entry_price", 0) * 0.98:
                    sell_signals.append(self.build_sell_signal(
                        pos,
                        f"保护利润 ({pnl_percent:.2%})",
                        "medium",
                        pnl_percent,
                        category,
                        latest_data,
                    ))

            # Phase 3b：波动退出 —— 未触发上述止盈/止损时，若该市场近窗口波动超阈值则退出，
            # 规避高波动制度下的来回打脸。样本不足（<MIN_SAMPLES）helper 自动返回 None 不触发。
            elif _ph is not None:
                mid = slug2id.get(market_slug)
                series = _ph.series_for(price_hist, mid) if mid else []
                vol = _ph.should_volatility_exit(series, threshold=vol_threshold) if series else None
                if vol is not None:
                    sell_signals.append(self.build_sell_signal(
                        pos,
                        f"波动退出 (近窗口波动 {vol:.3f} ≥ 阈值 {vol_threshold:.3f})",
                        "medium",
                        pnl_percent,
                        category,
                        latest_data,
                    ))
        
        # GTA VI 相关性风险检查
        if len(gta_vi_positions) >= 3:
            self.log(f"⚠️  GTA VI 相关性风险：{len(gta_vi_positions)} 个持仓")
            
            # 平仓表现最差的 GTA VI 持仓
            gta_vi_positions.sort(key=lambda x: x.get("percent_pnl", 0))
            
            for pos in gta_vi_positions[:2]:  # 平仓最差的 2 个
                if pos.get("market_slug") not in [s["market"] for s in sell_signals]:
                    sell_signals.append(self.build_sell_signal(
                        pos,
                        "降低 GTA VI 相关性风险",
                        "high",
                        pos.get("percent_pnl", 0) / 100,
                        category,
                        latest_data,
                    ))
        
        self.log(f"✅ 生成 {len(sell_signals)} 个卖出信号")
        
        return sell_signals
    
    def _peak_pnl_from_history(self, pos, market_slug, ph, price_hist, slug2id):
        """从价格历史算该持仓达到过的【真实最高浮盈%】（Phase 3b 尾巴：真实 trailing 最高水位）。

        按持有方向取该侧价格序列（YES→yes_price / NO→no_price）的 high_water 作为真实峰值价，
        与入场价算出峰值浮盈%。数据不足（<3 点）/无映射/无法计算 → 返回 None（调用方回退旧行为）。
        """
        if ph is None:
            return None
        mid = slug2id.get(market_slug)
        if not mid:
            return None
        outcome = normalize_outcome(pos.get("outcome") or pos.get("direction"))
        field = "no_price" if outcome == "NO" else "yes_price"
        series = ph.series_for(price_hist, mid, field=field)
        if not series or len(series) < 3:
            return None
        try:
            entry = float(pos.get("avg_entry_price") or pos.get("entry_price") or 0)
        except (TypeError, ValueError):
            return None
        if entry <= 0:
            return None
        peak = ph.high_water(series)
        if peak is None:
            return None
        return (peak - entry) / entry

    def run(self):
        """执行持仓管理"""
        self.log("开始持仓管理...")
        
        positions = self.get_portfolio()
        
        if not positions:
            self.log("ℹ️  无持仓")
            return
        
        sell_signals = self.analyze_positions(positions)

        # 保存卖出信号（即使为空也保存，方便调试）—— Phase 0 写入收敛，经 datastore 门面
        from runtime import datastore as _ds
        _ds.put_sell_signals("agent_p", sell_signals, base_dir=self.base_dir)

        # 将本轮紧急止损信号写入 closed registry，防止下一轮重复生成
        if sell_signals:
            self.update_closed_registry(sell_signals)

        self.log(f"✅ 生成 {len(sell_signals)} 个卖出信号")
        
        if sell_signals:
            # 按优先级分类
            urgent = [s for s in sell_signals if s["priority"] == "urgent"]
            high = [s for s in sell_signals if s["priority"] == "high"]
            medium = [s for s in sell_signals if s["priority"] == "medium"]
            
            if urgent:
                self.log(f"🚨 紧急止损：{len(urgent)} 个")
            if high:
                self.log(f"⚠️  高优先级：{len(high)} 个")
            if medium:
                self.log(f"ℹ️  中优先级：{len(medium)} 个")
        else:
            self.log("ℹ️  无卖出信号")

def main():
    agent = AgentP()
    agent.run()

if __name__ == "__main__":
    main()
