#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Base Strategy
Clase base para todas las estrategias con validaciones robustas

Includes:
- Data validation helpers
- Elliott/Kaufman analysis helpers
- Safe array access methods
"""

import logging
import numpy as np
from abc import ABC, abstractmethod
from typing import Tuple, List, Optional
from core.confluence_engine import StrategySignal
from utils.indicators import (
    calculate_kama,
    calculate_ewo,
    calculate_efficiency_ratio,
    validate_trend_with_kaufman,
    detect_elliott_wave_3,
    detect_elliott_divergence_wave_5,
    classify_market_state_kaufman
)


class BaseStrategy(ABC):
    """
    Clase base para estrategias

    Características:
    - Validación de longitud de datos ANTES de cualquier operación
    - Early returns con signal=0 cuando no hay datos suficientes
    - Logging claro de por qué no se genera señal
    - Sin excepciones no controladas
    """

    def __init__(self, name: str, min_bars_required: int):
        """
        Args:
            name: Nombre de la estrategia
            min_bars_required: Mínimo de barras requeridas
        """
        self.name = name
        self.min_bars_required = min_bars_required
        self.logger = logging.getLogger(f"Strategy.{name}")

    @abstractmethod
    def analyze(
        self,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        opens: np.ndarray,
        volumes: Optional[np.ndarray] = None
    ) -> StrategySignal:
        """
        Analiza datos y genera una señal

        IMPORTANTE:
        - SIEMPRE validar longitud ANTES de indexar
        - Retornar StrategySignal(signal=0, confidence=0.0) si datos insuficientes
        - Usar np.clip() para índices calculados
        - Validar que i-k >= 0 antes de acceder

        Args:
            closes: Precios de cierre
            highs: Precios máximos
            lows: Precios mínimos
            opens: Precios de apertura
            volumes: Volúmenes (opcional)

        Returns:
            StrategySignal
        """
        pass

    def validate_data(
        self,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        opens: np.ndarray
    ) -> Tuple[bool, str]:
        """
        Valida que los datos sean suficientes

        Returns:
            (válido, razón)
        """
        if len(closes) < self.min_bars_required:
            reason = f"Insufficient data: {len(closes)} < {self.min_bars_required}"
            self.logger.debug(reason)
            return False, reason

        if len(highs) != len(closes) or len(lows) != len(closes) or len(opens) != len(closes):
            reason = "Array length mismatch"
            self.logger.warning(reason)
            return False, reason

        # Verificar NaN
        if np.any(np.isnan(closes)) or np.any(np.isnan(highs)) or np.any(np.isnan(lows)):
            reason = "NaN values detected"
            self.logger.warning(reason)
            return False, reason

        return True, ""

    def safe_index(self, array: np.ndarray, index: int) -> float:
        """
        Acceso seguro a un índice de array

        Args:
            array: Array
            index: Índice

        Returns:
            Valor o NaN si fuera de rango
        """
        if index < 0 or index >= len(array):
            return np.nan

        return array[index]

    def safe_slice(self, array: np.ndarray, start: int, end: Optional[int] = None) -> np.ndarray:
        """
        Slice seguro de array

        Args:
            array: Array
            start: Inicio
            end: Fin (None = hasta el final)

        Returns:
            Slice o array vacío si índices inválidos
        """
        # Ajustar índices negativos
        length = len(array)

        if start < 0:
            start = max(0, length + start)

        if end is not None and end < 0:
            end = max(0, length + end)

        # Validar rangos
        if start >= length:
            return np.array([])

        if end is not None and end > length:
            end = length

        return array[start:end]

    # ===== ELLIOTT/KAUFMAN HELPERS =====

    def _calculate_ewo(self, closes: np.ndarray) -> Optional[float]:
        """
        Calcula Elliott Wave Oscillator actual

        Args:
            closes: Array de precios de cierre

        Returns:
            Valor actual de EWO o None si insuficientes datos
        """
        ewo = calculate_ewo(closes)

        if len(ewo) == 0 or np.isnan(ewo[-1]):
            return None

        return ewo[-1]

    def _calculate_kama_trend(self, closes: np.ndarray) -> str:
        """
        Determina la tendencia usando KAMA

        Args:
            closes: Array de precios de cierre

        Returns:
            'UP', 'DOWN', 'NEUTRAL', 'NOISE', o 'UNKNOWN'
        """
        is_valid, direction, er = validate_trend_with_kaufman(closes)

        if not is_valid:
            return direction  # 'NOISE', 'UNKNOWN', o 'CONFLICTING'

        return direction  # 'UP' o 'DOWN'

    def _get_market_efficiency(self, closes: np.ndarray, period: int = 10) -> float:
        """
        Calcula Efficiency Ratio actual

        Args:
            closes: Array de precios
            period: Período de cálculo

        Returns:
            Efficiency Ratio (0.0 - 1.0)
        """
        er = calculate_efficiency_ratio(closes, period)

        if len(er) == 0 or np.isnan(er[-1]):
            return 0.0

        return er[-1]

    def _is_valid_trend_context(
        self,
        closes: np.ndarray,
        min_efficiency: float = 0.30
    ) -> Tuple[bool, str]:
        """
        Valida si el contexto es apropiado para estrategias tendenciales

        Según Kaufman: ER < 0.30 indica ruido, no operar estrategias de tendencia.

        Args:
            closes: Array de precios
            min_efficiency: Eficiencia mínima requerida

        Returns:
            (is_valid, reason)
        """
        er = self._get_market_efficiency(closes)
        market_state = classify_market_state_kaufman(er)

        if market_state == "NOISE":
            return False, f"Market in NOISE state (ER={er:.2f} < {min_efficiency})"

        if market_state == "UNKNOWN":
            return False, "Insufficient data for efficiency calculation"

        return True, f"Valid trend context (ER={er:.2f}, state={market_state})"

    def _detect_elliott_wave_5_divergence(
        self,
        closes: np.ndarray,
        lookback: int = 50
    ) -> Tuple[bool, float, str]:
        """
        Detecta divergencia de Onda 5 (posible reversión)

        Args:
            closes: Array de precios
            lookback: Ventana de búsqueda para Onda 3

        Returns:
            (is_divergence, confidence, reason)
        """
        # Calcular EWO
        ewo = calculate_ewo(closes)

        if len(ewo) < lookback:
            return False, 0.0, "Insufficient data for Elliott analysis"

        # Detectar Onda 3
        wave_3_idx, wave_3_ewo = detect_elliott_wave_3(ewo, lookback)

        if wave_3_idx is None:
            return False, 0.0, "No Wave 3 detected"

        # Detectar divergencia Wave 5
        is_div, confidence = detect_elliott_divergence_wave_5(
            closes,
            ewo,
            wave_3_idx
        )

        if is_div:
            reason = f"Wave 5 divergence detected (confidence={confidence:.1f}%)"
            return True, confidence, reason
        else:
            return False, 0.0, "No Wave 5 divergence"

    def _should_filter_by_efficiency(
        self,
        closes: np.ndarray,
        strategy_type: str = 'elliott'
    ) -> Tuple[bool, str]:
        """
        Determina si la señal debe filtrarse por baja eficiencia

        Args:
            closes: Array de precios
            strategy_type: Tipo de estrategia ('elliott', 'breakout', etc.)

        Returns:
            (should_filter, reason)
        """
        # Estrategias que requieren eficiencia alta
        trend_strategies = ['elliott', 'breakout', 'momentum', 'trend_following']

        if strategy_type.lower() not in trend_strategies:
            return False, "Strategy does not require efficiency filter"

        er = self._get_market_efficiency(closes)
        market_state = classify_market_state_kaufman(er)

        if market_state == "NOISE":
            return True, f"Market in NOISE (ER={er:.2f}), filtering {strategy_type} signals"

        return False, f"Market efficiency acceptable (ER={er:.2f}, state={market_state})"
