#!/usr/bin/env python3
"""
Moteur de Backtest Commun pour les Stratégies de Trading.
Gère la simulation bar-par-bar, la gestion de portefeuille (SL/TP, Breakeven, Trailing),
les coûts de commission et slippage, et le calcul des statistiques de performance.
"""

import os
import pandas as pd
import numpy as np
from pathlib import Path
from loguru import logger

class BacktestEngine:
    """
    Moteur de backtest pour simuler l'exécution de stratégies sur des données historiques.
    """
    def __init__(
        self,
        symbol: str,
        timeframe: str,
        initial_balance: float = 1000.0,
        data_dir: str = "data/historical",
        slippage_pips: float = 1.0,
        commission_per_lot: float = 7.0  # 7$ par lot standard round-turn
    ):
        self.symbol = symbol.upper()
        self.timeframe = timeframe.upper()
        self.initial_balance = initial_balance
        self.data_dir = Path(data_dir)
        self.slippage_pips = slippage_pips
        self.commission_per_lot = commission_per_lot
        
        # Configuration spécifique à l'actif
        self.is_gold = self.symbol == "XAUUSD"
        self.point = 0.01 if self.is_gold else 0.00001
        self.pip_factor = self.point if self.is_gold else 10 * self.point
        self.contract_size = 100 if self.is_gold else 100000
        
        self.df = None
        self.trades = []
        self.balance = initial_balance
        self.equity_curve = []
        
    def load_data(self) -> pd.DataFrame:
        """
        Charge les données historiques CSV locales.
        """
        filename = f"{self.symbol.lower()}_{self.timeframe.lower()}_1y.csv"
        csv_path = self.data_dir / filename
        
        if not csv_path.exists():
            raise FileNotFoundError(f"Fichier historique introuvable : {csv_path}")
            
        logger.info(f"[{self.symbol}] Chargement des données depuis {csv_path}...")
        df = pd.read_csv(csv_path)
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.sort_values("datetime").reset_index(drop=True)
        return df

    def run(
        self,
        df_with_signals: pd.DataFrame,
        risk_pct: float = 1.0,
        sl_atr_mult: float = 1.5,
        tp_ratio: float = 2.0,
        use_breakeven: bool = True,
        use_trailing: bool = True,
        trailing_atr_mult: float = 1.5,
        time_exit_bars: int = 48
    ) -> tuple[pd.DataFrame, dict]:
        """
        Simule l'exécution sur le dataframe de signaux bar-par-bar.
        """
        balance = self.initial_balance
        active_trade = None
        closed_trades = []
        equity_curve = []
        
        df = df_with_signals.copy()
        
        for idx, row in df.iterrows():
            close_val = float(row["close"])
            high_val = float(row["high"])
            low_val = float(row["low"])
            dt = row["datetime"]
            atr_val = float(row["atr"]) if "atr" in row else 0.0
            
            # Mettre à jour l'equity
            open_profit = 0.0
            if active_trade is not None:
                volume = active_trade["volume"]
                open_price = active_trade["open_price"]
                direction = active_trade["direction"]
                if direction == "BUY":
                    open_profit = (close_val - open_price) * volume * self.contract_size
                else:
                    open_profit = (open_price - close_val) * volume * self.contract_size
                
            equity = balance + open_profit
            equity_curve.append((dt, equity))
            
            if active_trade is not None:
                # Vérifier les sorties
                direction = active_trade["direction"]
                volume = active_trade["volume"]
                open_price = active_trade["open_price"]
                stop_loss = active_trade["stop_loss"]
                take_profit = active_trade["take_profit"]
                open_idx = active_trade["open_idx"]
                initial_sl_dist = active_trade["initial_sl_dist"]
                is_breakeven = active_trade["is_breakeven"]
                
                closed = False
                exit_price = 0.0
                exit_reason = ""
                
                if direction == "BUY":
                    if low_val <= stop_loss:
                        closed = True
                        exit_price = stop_loss
                        exit_reason = "SL"
                    elif high_val >= take_profit:
                        closed = True
                        exit_price = take_profit
                        exit_reason = "TP"
                    elif idx - open_idx >= time_exit_bars:
                        closed = True
                        exit_price = close_val
                        exit_reason = "TIME"
                else:  # SELL
                    if high_val >= stop_loss:
                        closed = True
                        exit_price = stop_loss
                        exit_reason = "SL"
                    elif low_val <= take_profit:
                        closed = True
                        exit_price = take_profit
                        exit_reason = "TP"
                    elif idx - open_idx >= time_exit_bars:
                        closed = True
                        exit_price = close_val
                        exit_reason = "TIME"
                        
                if closed:
                    # Calculer le profit/perte net
                    if direction == "BUY":
                        gross_profit = (exit_price - open_price) * volume * self.contract_size
                    else:
                        gross_profit = (open_price - exit_price) * volume * self.contract_size
                        
                    comm = volume * self.commission_per_lot
                    spread_cost = volume * (self.slippage_pips * self.pip_factor) * self.contract_size
                    net_profit = gross_profit - comm - spread_cost
                    balance += net_profit
                    equity = balance
                    
                    closed_trades.append({
                        "ticket": len(closed_trades) + 1,
                        "symbol": self.symbol,
                        "direction": direction,
                        "volume": volume,
                        "open_price": open_price,
                        "close_price": exit_price,
                        "open_time": active_trade["open_time"],
                        "close_time": dt,
                        "profit": net_profit,
                        "exit_reason": exit_reason,
                        "stop_loss": stop_loss,
                        "take_profit": take_profit
                    })
                    active_trade = None
                else:
                    # Gérer le Breakeven et le Trailing Stop
                    if direction == "BUY":
                        if use_breakeven and not is_breakeven:
                            if close_val - open_price >= initial_sl_dist:
                                active_trade["stop_loss"] = open_price
                                active_trade["is_breakeven"] = True
                        if use_trailing:
                            new_sl = close_val - trailing_atr_mult * atr_val
                            if new_sl > active_trade["stop_loss"]:
                                active_trade["stop_loss"] = new_sl
                    else:  # SELL
                        if use_breakeven and not is_breakeven:
                            if open_price - close_val >= initial_sl_dist:
                                active_trade["stop_loss"] = open_price
                                active_trade["is_breakeven"] = True
                        if use_trailing:
                            new_sl = close_val + trailing_atr_mult * atr_val
                            if new_sl < active_trade["stop_loss"]:
                                active_trade["stop_loss"] = new_sl
            
            # Gérer les entrées
            if active_trade is None:
                buy_sig = bool(row["buy_signal"]) if "buy_signal" in row else False
                sell_sig = bool(row["sell_signal"]) if "sell_signal" in row else False
                
                if (buy_sig or sell_sig) and atr_val > 0:
                    risk_amount = balance * (risk_pct / 100.0)
                    sl_dist = sl_atr_mult * atr_val
                    
                    volume = risk_amount / (sl_dist * self.contract_size)
                    volume = max(0.01, round(volume, 2))
                    
                    if buy_sig:
                        active_trade = {
                            "direction": "BUY",
                            "open_price": close_val,
                            "open_time": dt,
                            "open_idx": idx,
                            "volume": volume,
                            "stop_loss": close_val - sl_dist,
                            "take_profit": close_val + tp_ratio * sl_dist,
                            "initial_sl_dist": sl_dist,
                            "is_breakeven": False
                        }
                    elif sell_sig:
                        active_trade = {
                            "direction": "SELL",
                            "open_price": close_val,
                            "open_time": dt,
                            "open_idx": idx,
                            "volume": volume,
                            "stop_loss": close_val + sl_dist,
                            "take_profit": close_val - tp_ratio * sl_dist,
                            "initial_sl_dist": sl_dist,
                            "is_breakeven": False
                        }
                        
        # Fermer la dernière position si elle est encore ouverte
        if active_trade is not None:
            row = df.iloc[-1]
            close_val = float(row["close"])
            dt = row["datetime"]
            volume = active_trade["volume"]
            open_price = active_trade["open_price"]
            direction = active_trade["direction"]
            
            if direction == "BUY":
                gross_profit = (close_val - open_price) * volume * self.contract_size
            else:
                gross_profit = (open_price - close_val) * volume * self.contract_size
                
            comm = volume * self.commission_per_lot
            spread_cost = volume * (self.slippage_pips * self.pip_factor) * self.contract_size
            net_profit = gross_profit - comm - spread_cost
            balance += net_profit
            
            closed_trades.append({
                "ticket": len(closed_trades) + 1,
                "symbol": self.symbol,
                "direction": direction,
                "volume": volume,
                "open_price": open_price,
                "close_price": close_val,
                "open_time": active_trade["open_time"],
                "close_time": dt,
                "profit": net_profit,
                "exit_reason": "FORCE_CLOSE",
                "stop_loss": active_trade["stop_loss"],
                "take_profit": active_trade["take_profit"]
            })
            
        # Calculer les métriques globales
        df_trades = pd.DataFrame(closed_trades)
        total_trades = len(closed_trades)
        
        if total_trades > 0:
            wins = sum(1 for t in closed_trades if t["profit"] > 0)
            losses = sum(1 for t in closed_trades if t["profit"] <= 0)
            win_rate = round((wins / total_trades) * 100.0, 1)
            
            gross_profits = sum(t["profit"] for t in closed_trades if t["profit"] > 0)
            gross_losses = sum(t["profit"] for t in closed_trades if t["profit"] <= 0)
            
            if gross_losses != 0:
                profit_factor = round(gross_profits / abs(gross_losses), 2)
            else:
                profit_factor = 99.9 if gross_profits > 0 else 0.0
                
            net_profit = round(balance - self.initial_balance, 2)
            net_return = round((net_profit / self.initial_balance) * 100.0, 2)
            
            wins_list = [t["profit"] for t in closed_trades if t["profit"] > 0]
            losses_list = [t["profit"] for t in closed_trades if t["profit"] <= 0]
            avg_win = round(np.mean(wins_list), 2) if wins_list else 0.0
            avg_loss = round(np.mean(losses_list), 2) if losses_list else 0.0
            
            expectancy = round(net_profit / total_trades, 2)
            
            exit_breakdown = {}
            for t in closed_trades:
                reason = t["exit_reason"]
                exit_breakdown[reason] = exit_breakdown.get(reason, 0) + 1
        else:
            win_rate = 0.0
            profit_factor = 0.0
            net_profit = 0.0
            net_return = 0.0
            avg_win = 0.0
            avg_loss = 0.0
            expectancy = 0.0
            exit_breakdown = {}
            
        max_dd = 0.0
        sharpe = 0.0
        
        if equity_curve:
            peak = -float("inf")
            drawdowns = []
            for dt, eq in equity_curve:
                if eq > peak:
                    peak = eq
                dd = ((peak - eq) / peak) * 100.0 if peak > 0 else 0.0
                drawdowns.append(dd)
            max_dd = round(max(drawdowns), 2) if drawdowns else 0.0
            
            eq_df = pd.DataFrame(equity_curve, columns=["datetime", "equity"])
            eq_df["datetime"] = pd.to_datetime(eq_df["datetime"])
            eq_df = eq_df.set_index("datetime").sort_index()
            daily = eq_df["equity"].resample("D").last().dropna()
            
            if len(daily) >= 2:
                daily_returns = daily.pct_change().dropna()
                mean_ret = daily_returns.mean()
                std_ret = daily_returns.std()
                if std_ret > 0:
                    sharpe = round((mean_ret / std_ret) * np.sqrt(252), 2)
                    
        metrics = {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "initial_balance": self.initial_balance,
            "final_balance": round(balance, 2),
            "net_profit": net_profit,
            "net_return_pct": net_return,
            "total_trades": total_trades,
            "wins": sum(1 for t in closed_trades if t["profit"] > 0) if total_trades > 0 else 0,
            "losses": sum(1 for t in closed_trades if t["profit"] <= 0) if total_trades > 0 else 0,
            "win_rate_pct": win_rate,
            "profit_factor": profit_factor,
            "sharpe_ratio": sharpe,
            "max_drawdown_pct": max_dd,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "expectancy": expectancy,
            "exit_breakdown": exit_breakdown
        }
        
        return df_trades, metrics