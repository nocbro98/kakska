#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Attribution System
Sistema de atribución de performance por estrategia y régimen
"""

import logging
import numpy as np
from typing import Dict, List, Any
from collections import defaultdict

from core.state_store import StateStore
from core.event_bus import EventBus


class AttributionSystem:
    """
    Sistema de atribución de performance

    Calcula métricas por:
    - Estrategia
    - Régimen de mercado
    """

    def __init__(self, state_store: StateStore, event_bus: EventBus):
        self.state_store = state_store
        self.event_bus = event_bus
        self.logger = logging.getLogger("AttributionSystem")

    def get_strategy_metrics(self) -> List[Dict[str, Any]]:
        """Calcula métricas por estrategia"""
        trades = self.state_store.get_trades()

        # Agrupar por estrategia
        by_strategy = defaultdict(list)
        for trade in trades:
            strategy = trade.get('strategy_primary', 'unknown')
            by_strategy[strategy].append(trade)

        metrics = []
        for strategy, strategy_trades in by_strategy.items():
            metrics.append(self._calculate_metrics_for_group(strategy, strategy_trades))

        return metrics

    def get_regime_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Calcula métricas por régimen"""
        trades = self.state_store.get_trades()

        # Agrupar por régimen
        by_regime = defaultdict(list)
        for trade in trades:
            regime = trade.get('regime_trend', 'unknown')
            by_regime[regime].append(trade)

        metrics = {}
        for regime, regime_trades in by_regime.items():
            metrics[regime] = self._calculate_metrics_for_group(regime, regime_trades)

        return metrics

    def get_dashboard_data(self) -> Dict[str, Any]:
        """Retorna datos completos para dashboard"""
        strategy_metrics = self.get_strategy_metrics()
        regime_metrics = self.get_regime_metrics()

        # Calcular equity total
        trades = self.state_store.get_trades()
        total_pnl = sum(
            (t.get('exit_price', 0) - t.get('entry_price', 0)) * t.get('quantity', 0)
            for t in trades if t.get('exit_price')
        )

        # Matriz de confusión simplificada
        confusion_matrix = self._build_confusion_matrix(trades)

        return {
            'total_equity': total_pnl,
            'strategy_metrics': strategy_metrics,
            'regime_metrics': regime_metrics,
            'confusion_matrix': confusion_matrix
        }

    def _calculate_metrics_for_group(self, name: str, trades: List[Dict]) -> Dict[str, Any]:
        """Calcula métricas para un grupo de trades"""
        if not trades:
            return {
                'strategy': name,
                'total_trades': 0,
                'total_pnl': 0,
                'win_rate': 0,
                'profit_factor': 0,
                'sharpe_ratio': 0,
                'max_dd': 0
            }

        # PnL
        pnls = [
            (t.get('exit_price', 0) - t.get('entry_price', 0)) * t.get('quantity', 0)
            for t in trades if t.get('exit_price')
        ]

        total_pnl = sum(pnls)

        # Win rate
        winners = [p for p in pnls if p > 0]
        losers = [p for p in pnls if p < 0]
        win_rate = len(winners) / len(pnls) * 100 if pnls else 0

        # Profit Factor
        gross_profit = sum(winners) if winners else 0
        gross_loss = abs(sum(losers)) if losers else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        # Sharpe (simplificado)
        if len(pnls) > 1:
            mean_pnl = np.mean(pnls)
            std_pnl = np.std(pnls)
            sharpe = mean_pnl / std_pnl * np.sqrt(252) if std_pnl > 0 else 0
        else:
            sharpe = 0

        # MaxDD (simplificado)
        equity_curve = np.cumsum(pnls)
        peak = np.maximum.accumulate(equity_curve)
        drawdown = peak - equity_curve
        max_dd = np.max(drawdown) if len(drawdown) > 0 else 0

        return {
            'strategy': name,
            'total_trades': len(trades),
            'total_pnl': total_pnl,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'sharpe_ratio': sharpe,
            'max_dd': max_dd
        }

    def _build_confusion_matrix(self, trades: List[Dict]) -> Dict[str, Dict[str, int]]:
        """Construye matriz de confusión simplificada"""
        matrix = {
            'long': {'positive': 0, 'negative': 0},
            'short': {'positive': 0, 'negative': 0}
        }

        for trade in trades:
            if not trade.get('exit_price'):
                continue

            pnl = (trade.get('exit_price', 0) - trade.get('entry_price', 0)) * trade.get('quantity', 0)
            side = trade.get('side', 'BUY')

            signal_type = 'long' if side == 'BUY' else 'short'
            outcome = 'positive' if pnl > 0 else 'negative'

            matrix[signal_type][outcome] += 1

        return matrix
