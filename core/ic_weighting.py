#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IC Weighting System
Sistema de pesos dinámicos por Information Coefficient (EWMA)
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List

from core.state_store import StateStore
from core.event_bus import EventBus


class ICWeightingSystem:
    """
    Sistema de pesos dinámicos basado en IC

    Calcula Information Coefficient (correlación entre señal y retorno futuro)
    y ajusta pesos con EWMA
    """

    def __init__(
        self,
        state_store: StateStore,
        event_bus: EventBus,
        strategies: List[str],
        max_weight: float = 0.5,
        min_weight: float = 0.1,
        rebalance_days: int = 7
    ):
        """
        Args:
            state_store: Almacén de estado
            event_bus: Bus de eventos
            strategies: Lista de estrategias
            max_weight: Peso máximo por estrategia
            min_weight: Peso mínimo por estrategia
            rebalance_days: Días entre rebalances
        """
        self.state_store = state_store
        self.event_bus = event_bus
        self.strategies = strategies
        self.max_weight = max_weight
        self.min_weight = min_weight
        self.rebalance_days = rebalance_days
        self.logger = logging.getLogger("ICWeighting")

        # Pesos actuales (inicialmente iguales)
        self.weights = {s: 1.0 / len(strategies) for s in strategies}
        self.last_rebalance = datetime.now()

        self.logger.info(f"ICWeighting initialized with {len(strategies)} strategies")

    def get_weight(self, strategy: str) -> float:
        """Obtiene el peso actual de una estrategia"""
        return self.weights.get(strategy, 0.0)

    def get_all_weights(self) -> Dict[str, float]:
        """Obtiene todos los pesos"""
        return self.weights.copy()

    def rebalance_if_needed(self):
        """Rebalancea pesos si es necesario"""
        days_since_rebalance = (datetime.now() - self.last_rebalance).days

        if days_since_rebalance >= self.rebalance_days:
            self.rebalance()

    def rebalance(self):
        """Rebalancea los pesos según IC reciente"""
        self.logger.info("Rebalancing strategy weights...")

        # Calcular IC scores para cada estrategia
        ic_scores = {}
        for strategy in self.strategies:
            ic = self._calculate_ic(strategy)
            ic_scores[strategy] = ic

        # Normalizar IC a pesos
        # IC score puede ser entre -1 y 1
        # Convertir a pesos positivos: (IC + 1) / 2
        raw_weights = {}
        for strategy, ic in ic_scores.items():
            raw_weights[strategy] = max(0, (ic + 1) / 2)

        # Normalizar a suma = 1
        total = sum(raw_weights.values())
        if total > 0:
            normalized_weights = {s: w / total for s, w in raw_weights.items()}
        else:
            # Si no hay IC válido, pesos iguales
            normalized_weights = {s: 1.0 / len(self.strategies) for s in self.strategies}

        # Aplicar caps de max_weight y min_weight
        for strategy in self.strategies:
            weight = normalized_weights[strategy]
            weight = max(self.min_weight, min(self.max_weight, weight))
            self.weights[strategy] = weight

        # Renormalizar tras aplicar caps
        total = sum(self.weights.values())
        if total > 0:
            self.weights = {s: w / total for s, w in self.weights.items()}

        self.last_rebalance = datetime.now()

        self.logger.info(f"Rebalance complete: {self.weights}")

    def _calculate_ic(self, strategy: str, days_back: int = 30) -> float:
        """
        Calcula IC (Information Coefficient) para una estrategia

        IC = correlación entre señal y retorno futuro

        Args:
            strategy: Nombre de la estrategia
            days_back: Días atrás para cálculo

        Returns:
            IC score (entre -1 y 1)
        """
        # Obtener métricas guardadas
        metrics = self.state_store.get_strategy_metrics(strategy, days_back)

        if not metrics or len(metrics) < 5:
            return 0.0  # Insuficientes datos

        # Calcular correlación simple
        signals = [m['signal'] for m in metrics if m.get('signal') is not None]
        returns = [m['forward_return'] for m in metrics if m.get('forward_return') is not None]

        if len(signals) < 5 or len(returns) < 5:
            return 0.0

        # Correlación de Spearman (simplificada)
        try:
            from scipy.stats import spearmanr
            ic, _ = spearmanr(signals[:len(returns)], returns[:len(signals)])
            return ic if not np.isnan(ic) else 0.0
        except:
            # Fallback: correlación simple
            import numpy as np
            if len(signals) == len(returns):
                corr = np.corrcoef(signals, returns)[0, 1]
                return corr if not np.isnan(corr) else 0.0
            return 0.0

    def get_stats(self) -> Dict:
        """Retorna estadísticas del sistema de weighting"""
        ic_scores = {s: self._calculate_ic(s) for s in self.strategies}

        return {
            'weights': self.weights,
            'ic_scores': ic_scores,
            'last_rebalance': self.last_rebalance.isoformat(),
            'config': {
                'max_weight': self.max_weight,
                'min_weight': self.min_weight,
                'rebalance_days': self.rebalance_days
            }
        }
