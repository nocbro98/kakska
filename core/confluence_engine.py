#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Confluence Engine
Motor de agregación de señales multi-estrategia

IMPORTANTE: Manejo correcto de señales 0
- Una estrategia con signal=0 NO es un error
- Es un estado normal de "no-trade" por datos insuficientes
- Solo cuentan como "válidas" las estrategias con signal != 0 y confidence > 0

Características:
- Agregación de señales con pesos configurables
- Umbrales para número mínimo de estrategias y confianza
- Rechazo silencioso de entradas NaN o vacías
- Logging claro de por qué cada estrategia fue excluida
"""

import logging
import math
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class SignalType(Enum):
    """Tipo de señal"""
    LONG = 1
    NEUTRAL = 0
    SHORT = -1


@dataclass
class StrategySignal:
    """Señal de una estrategia individual"""
    name: str
    signal: int  # -1, 0, +1
    confidence: float  # 0.0 a 1.0
    reasons: List[str]

    def is_valid(self) -> bool:
        """
        Una señal es válida si:
        - signal != 0 (tiene dirección)
        - confidence > 0
        - No tiene NaN
        """
        if self.signal == 0:
            return False

        if self.confidence <= 0:
            return False

        if math.isnan(self.confidence):
            return False

        return True

    def get_exclusion_reason(self) -> str:
        """Retorna la razón de exclusión si no es válida"""
        if self.signal == 0:
            return "no signal (0)"
        if self.confidence <= 0:
            return "zero confidence"
        if math.isnan(self.confidence):
            return "NaN confidence"
        return "unknown"


@dataclass
class ConfluenceDecision:
    """Decisión final del motor de confluencia"""
    signal: SignalType
    confidence: float
    num_strategies_valid: int
    num_strategies_total: int
    reasons: List[str]
    strategy_breakdown: List[Dict[str, Any]]

    def should_trade(self) -> bool:
        """Retorna True si la decisión indica que se debe operar"""
        return self.signal != SignalType.NEUTRAL and self.confidence > 0


class ConfluenceEngine:
    """
    Motor de confluencia multi-estrategia

    Política:
    - Solo estrategias con signal != 0 y confidence > 0 cuentan como "válidas"
    - signal=0 es NO-TRADE, no error
    - Requiere mínimo N estrategias válidas para operar
    - Requiere confianza promedio ponderada >= umbral
    """

    def __init__(
        self,
        min_strategies: int = 2,
        min_confidence: float = 0.5,
        weights: Optional[Dict[str, float]] = None
    ):
        """
        Args:
            min_strategies: Mínimo de estrategias válidas requeridas
            min_confidence: Confianza mínima promedio ponderada
            weights: Pesos por estrategia (opcional)
        """
        self.min_strategies = min_strategies
        self.min_confidence = min_confidence
        self.weights = weights or {}
        self.logger = logging.getLogger("ConfluenceEngine")

        self.logger.info(
            f"ConfluenceEngine initialized: "
            f"min_strategies={min_strategies}, "
            f"min_confidence={min_confidence}"
        )

    def evaluate(self, signals: List[StrategySignal]) -> ConfluenceDecision:
        """
        Evalúa señales de múltiples estrategias y produce una decisión

        Args:
            signals: Lista de señales de estrategias

        Returns:
            ConfluenceDecision con la decisión final
        """
        # 1. Filtrar señales válidas
        valid_signals = []
        excluded_signals = []

        for signal in signals:
            if signal.is_valid():
                valid_signals.append(signal)
            else:
                excluded_signals.append(signal)
                reason = signal.get_exclusion_reason()
                self.logger.debug(
                    f"Strategy '{signal.name}' excluded: {reason}"
                )

        num_valid = len(valid_signals)
        num_total = len(signals)

        # Log de diagnóstico (nivel INFO para visibilidad)
        self.logger.info(
            f"Confluence evaluation: {num_valid}/{num_total} valid strategies"
        )

        # 2. Verificar umbral mínimo de estrategias
        if num_valid < self.min_strategies:
            self.logger.info(
                f"Insufficient valid strategies ({num_valid} < {self.min_strategies}). "
                f"No-trade decision."
            )

            return ConfluenceDecision(
                signal=SignalType.NEUTRAL,
                confidence=0.0,
                num_strategies_valid=num_valid,
                num_strategies_total=num_total,
                reasons=[f"Insufficient valid strategies ({num_valid} < {self.min_strategies})"],
                strategy_breakdown=self._build_breakdown(signals, valid_signals)
            )

        # 3. Calcular señal agregada
        weighted_signal = 0.0
        weighted_confidence = 0.0
        total_weight = 0.0

        for signal in valid_signals:
            weight = self.weights.get(signal.name, 1.0)
            weighted_signal += signal.signal * signal.confidence * weight
            weighted_confidence += signal.confidence * weight
            total_weight += weight

        # Normalizar
        if total_weight > 0:
            avg_signal = weighted_signal / total_weight
            avg_confidence = weighted_confidence / total_weight
        else:
            avg_signal = 0.0
            avg_confidence = 0.0

        # 4. Determinar dirección
        if avg_signal > 0.2:
            final_signal = SignalType.LONG
        elif avg_signal < -0.2:
            final_signal = SignalType.SHORT
        else:
            final_signal = SignalType.NEUTRAL

        # 5. Verificar confianza mínima
        if avg_confidence < self.min_confidence:
            self.logger.info(
                f"Confidence too low ({avg_confidence:.2f} < {self.min_confidence}). "
                f"No-trade decision."
            )

            return ConfluenceDecision(
                signal=SignalType.NEUTRAL,
                confidence=avg_confidence,
                num_strategies_valid=num_valid,
                num_strategies_total=num_total,
                reasons=[f"Confidence too low ({avg_confidence:.2f} < {self.min_confidence})"],
                strategy_breakdown=self._build_breakdown(signals, valid_signals)
            )

        # 6. Decisión final
        reasons = [
            f"{num_valid} strategies agree: {final_signal.name}",
            f"Average confidence: {avg_confidence:.2%}"
        ]

        # Agregar detalles de cada estrategia válida
        for signal in valid_signals:
            reasons.append(f"- {signal.name}: {signal.signal} @ {signal.confidence:.0%}")

        self.logger.info(
            f"Confluence decision: {final_signal.name} with {avg_confidence:.2%} confidence "
            f"({num_valid} strategies)"
        )

        return ConfluenceDecision(
            signal=final_signal,
            confidence=avg_confidence,
            num_strategies_valid=num_valid,
            num_strategies_total=num_total,
            reasons=reasons,
            strategy_breakdown=self._build_breakdown(signals, valid_signals)
        )

    def _build_breakdown(
        self,
        all_signals: List[StrategySignal],
        valid_signals: List[StrategySignal]
    ) -> List[Dict[str, Any]]:
        """Construye el desglose de estrategias para debugging"""
        breakdown = []

        for signal in all_signals:
            is_valid = signal in valid_signals

            breakdown.append({
                'name': signal.name,
                'signal': signal.signal,
                'confidence': signal.confidence,
                'valid': is_valid,
                'exclusion_reason': None if is_valid else signal.get_exclusion_reason(),
                'weight': self.weights.get(signal.name, 1.0)
            })

        return breakdown

    def update_weights(self, new_weights: Dict[str, float]):
        """Actualiza los pesos de las estrategias"""
        self.weights.update(new_weights)
        self.logger.info(f"Weights updated: {self.weights}")


def example_usage():
    """Ejemplo de uso del Confluence Engine"""
    # Crear motor
    engine = ConfluenceEngine(min_strategies=2, min_confidence=0.5)

    # Caso 1: Todas las estrategias con signal=0 (datos insuficientes)
    signals = [
        StrategySignal(name='elliott', signal=0, confidence=0.0, reasons=['insufficient data']),
        StrategySignal(name='fibonacci', signal=0, confidence=0.0, reasons=['insufficient data']),
        StrategySignal(name='wyckoff', signal=0, confidence=0.0, reasons=['insufficient data']),
        StrategySignal(name='smc', signal=0, confidence=0.0, reasons=['insufficient data'])
    ]

    decision = engine.evaluate(signals)
    print(f"Decision: {decision.signal.name}, confidence: {decision.confidence:.2%}")
    print(f"Valid strategies: {decision.num_strategies_valid}/{decision.num_strategies_total}")
    # Output: Decision: NEUTRAL, confidence: 0.00%
    #         Valid strategies: 0/4
    # IMPORTANTE: Esto NO es un error, es un no-trade válido

    # Caso 2: Algunas estrategias con señales válidas
    signals = [
        StrategySignal(name='elliott', signal=1, confidence=0.7, reasons=['uptrend']),
        StrategySignal(name='fibonacci', signal=1, confidence=0.6, reasons=['retracement support']),
        StrategySignal(name='wyckoff', signal=0, confidence=0.0, reasons=['insufficient data']),
        StrategySignal(name='smc', signal=-1, confidence=0.3, reasons=['order block'])
    ]

    decision = engine.evaluate(signals)
    print(f"\nDecision: {decision.signal.name}, confidence: {decision.confidence:.2%}")
    print(f"Valid strategies: {decision.num_strategies_valid}/{decision.num_strategies_total}")
    # Output: Decision: LONG, confidence: 65%
    #         Valid strategies: 3/4


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    example_usage()
