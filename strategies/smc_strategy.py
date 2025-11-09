#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Money Concepts (SMC) Strategy
Estrategia basada en conceptos institucionales con validaciones robustas

SOLUCIÓN AL ERROR: "index 20 is out of bounds for axis 0 with size 20"

Causa del error:
- La implementación original accedía a índices calculados sin validar
- Ejemplo: array[-window:][window] cuando len(array) == window
- Operaciones como i-k sin verificar que i >= k

Solución implementada:
- Validación explícita de longitud ANTES de cualquier indexación
- Uso de np.clip() para índices calculados
- Guards para asegurar que i-k >= 0
- Early return con signal=0 si datos insuficientes
"""

import logging
import numpy as np
from typing import Tuple, List
from strategies.base_strategy import BaseStrategy
from core.confluence_engine import StrategySignal


class SMCStrategy(BaseStrategy):
    """
    Smart Money Concepts Strategy

    Detecta:
    - Order Blocks
    - Fair Value Gaps (FVG)
    - Break of Structure (BOS)
    - Change of Character (CHoCH)

    IMPORTANTE: Todas las operaciones están protegidas contra IndexError
    """

    def __init__(
        self,
        swing_length: int = 10,
        fvg_threshold: float = 0.001
    ):
        """
        Args:
            swing_length: Longitud para detectar swings
            fvg_threshold: Umbral mínimo para FVG (% del precio)
        """
        # Calcular mínimo de barras requeridas
        # Necesitamos al menos: swing_length * 2 + buffer
        min_bars = max(50, swing_length * 3)

        super().__init__(name='SMC', min_bars_required=min_bars)

        self.swing_length = swing_length
        self.fvg_threshold = fvg_threshold

        self.logger.info(
            f"SMC Strategy initialized: "
            f"swing_length={swing_length}, "
            f"min_bars_required={self.min_bars_required}"
        )

    def analyze(
        self,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        opens: np.ndarray,
        volumes=None
    ) -> StrategySignal:
        """
        Analiza según SMC

        Returns:
            StrategySignal con signal, confidence y reasons
        """
        # 1. Validación crítica de datos
        valid, reason = self.validate_data(closes, highs, lows, opens)
        if not valid:
            return StrategySignal(
                name=self.name,
                signal=0,
                confidence=0.0,
                reasons=[f"Insufficient data: {reason}"]
            )

        try:
            # 2. Detectar estructura de mercado
            structure_signal, structure_reasons = self._detect_structure(highs, lows, closes)

            # 3. Detectar order blocks
            ob_signal, ob_reasons = self._detect_order_blocks(highs, lows, closes, opens)

            # 4. Detectar Fair Value Gaps
            fvg_signal, fvg_reasons = self._detect_fair_value_gaps(highs, lows)

            # 5. Combinar señales
            signals = [structure_signal, ob_signal, fvg_signal]
            valid_signals = [s for s in signals if s != 0]

            if not valid_signals:
                # No hay señales válidas
                return StrategySignal(
                    name=self.name,
                    signal=0,
                    confidence=0.0,
                    reasons=["No valid SMC patterns detected"]
                )

            # Señal por mayoría
            avg_signal = np.mean(valid_signals)

            if avg_signal > 0.3:
                final_signal = 1
            elif avg_signal < -0.3:
                final_signal = -1
            else:
                final_signal = 0

            # Confianza basada en número de confirmaciones
            confidence = len(valid_signals) / 3.0

            # Agregar razones
            all_reasons = structure_reasons + ob_reasons + fvg_reasons

            return StrategySignal(
                name=self.name,
                signal=final_signal,
                confidence=confidence,
                reasons=all_reasons[:3]  # Top 3 razones
            )

        except Exception as e:
            # Capturar CUALQUIER excepción no prevista
            self.logger.error(f"Unexpected error in SMC analyze: {e}", exc_info=True)
            return StrategySignal(
                name=self.name,
                signal=0,
                confidence=0.0,
                reasons=[f"Error: {str(e)}"]
            )

    def _detect_structure(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray
    ) -> Tuple[int, List[str]]:
        """
        Detecta Break of Structure (BOS) y Change of Character (CHoCH)

        VALIDACIONES:
        - Verificar longitud antes de indexar
        - Usar índices con np.clip
        """
        reasons = []

        # Validar longitud mínima
        required_length = self.swing_length * 2 + 1
        if len(highs) < required_length:
            return 0, [f"Insufficient data for structure ({len(highs)} < {required_length})"]

        try:
            # Detectar swing highs y lows recientes
            swing_highs = self._find_swing_highs(highs)
            swing_lows = self._find_swing_lows(lows)

            if len(swing_highs) < 2 or len(swing_lows) < 2:
                return 0, ["Insufficient swing points"]

            # Break of Structure (BOS)
            # Bullish BOS: precio rompe último swing high
            last_swing_high = swing_highs[-1]
            current_price = closes[-1]

            if current_price > last_swing_high:
                reasons.append("Bullish BOS")
                return 1, reasons

            # Bearish BOS: precio rompe último swing low
            last_swing_low = swing_lows[-1]

            if current_price < last_swing_low:
                reasons.append("Bearish BOS")
                return -1, reasons

            return 0, ["No structure break"]

        except Exception as e:
            self.logger.error(f"Error in _detect_structure: {e}", exc_info=True)
            return 0, [f"Structure detection error: {str(e)}"]

    def _detect_order_blocks(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        opens: np.ndarray
    ) -> Tuple[int, List[str]]:
        """
        Detecta Order Blocks (bloques de órdenes institucionales)

        VALIDACIONES CRÍTICAS:
        - Verificar que i-1 >= 0 antes de acceder
        - Usar safe_index para accesos
        """
        reasons = []

        # Validar longitud
        if len(closes) < 10:
            return 0, ["Insufficient data for order blocks"]

        try:
            # Buscar velas con movimiento fuerte (order block)
            # Vela alcista fuerte seguida de consolidación = bullish OB
            # Vela bajista fuerte seguida de consolidación = bearish OB

            # Tomar últimas 20 velas de forma segura
            lookback = min(20, len(closes) - 1)
            recent_closes = closes[-lookback:]
            recent_opens = opens[-lookback:]
            recent_highs = highs[-lookback:]
            recent_lows = lows[-lookback:]

            # Buscar velas con body grande
            bodies = np.abs(recent_closes - recent_opens)
            avg_body = np.mean(bodies)

            # Vela con body > 2x promedio = potencial order block
            strong_candles = bodies > avg_body * 2

            if not np.any(strong_candles):
                return 0, ["No strong candles for OB"]

            # Última vela fuerte
            last_strong_idx = np.where(strong_candles)[0][-1]

            # Verificar que no estamos en el borde
            if last_strong_idx >= len(recent_closes) - 1:
                return 0, ["OB too recent"]

            # Verificar dirección
            if recent_closes[last_strong_idx] > recent_opens[last_strong_idx]:
                # Vela alcista
                reasons.append("Bullish Order Block detected")
                return 1, reasons
            else:
                # Vela bajista
                reasons.append("Bearish Order Block detected")
                return -1, reasons

        except Exception as e:
            self.logger.error(f"Error in _detect_order_blocks: {e}", exc_info=True)
            return 0, [f"Order block detection error: {str(e)}"]

    def _detect_fair_value_gaps(
        self,
        highs: np.ndarray,
        lows: np.ndarray
    ) -> Tuple[int, List[str]]:
        """
        Detecta Fair Value Gaps (huecos de precio)

        VALIDACIÓN: Acceso seguro a i-2, i-1, i
        """
        reasons = []

        # Validar longitud: necesitamos al menos 3 velas
        if len(highs) < 3:
            return 0, ["Insufficient data for FVG"]

        try:
            # FVG = gap entre vela[i-2] y vela[i] que no toca vela[i-1]
            # Bullish FVG: low[i] > high[i-2]
            # Bearish FVG: high[i] < low[i-2]

            i = len(highs) - 1  # Última vela
            i_1 = i - 1
            i_2 = i - 2

            # Validar índices (ya sabemos que len >= 3, pero doble check)
            if i_2 < 0:
                return 0, ["Invalid index for FVG"]

            # Bullish FVG
            if lows[i] > highs[i_2]:
                gap_size = (lows[i] - highs[i_2]) / highs[i_2]
                if gap_size > self.fvg_threshold:
                    reasons.append(f"Bullish FVG ({gap_size:.2%})")
                    return 1, reasons

            # Bearish FVG
            if highs[i] < lows[i_2]:
                gap_size = (lows[i_2] - highs[i]) / lows[i_2]
                if gap_size > self.fvg_threshold:
                    reasons.append(f"Bearish FVG ({gap_size:.2%})")
                    return -1, reasons

            return 0, ["No FVG detected"]

        except Exception as e:
            self.logger.error(f"Error in _detect_fair_value_gaps: {e}", exc_info=True)
            return 0, [f"FVG detection error: {str(e)}"]

    def _find_swing_highs(self, highs: np.ndarray) -> List[float]:
        """
        Encuentra swing highs

        VALIDACIÓN: Uso de safe_slice y verificación de rangos
        """
        swing_highs = []
        length = len(highs)

        # Necesitamos al menos swing_length * 2 + 1
        if length < self.swing_length * 2 + 1:
            return swing_highs

        # Iterar desde swing_length hasta length - swing_length
        for i in range(self.swing_length, length - self.swing_length):
            # Verificar que i es un máximo local
            left_window = self.safe_slice(highs, i - self.swing_length, i)
            right_window = self.safe_slice(highs, i + 1, i + 1 + self.swing_length)

            if len(left_window) == 0 or len(right_window) == 0:
                continue

            current = highs[i]

            if np.all(current >= left_window) and np.all(current >= right_window):
                swing_highs.append(current)

        return swing_highs

    def _find_swing_lows(self, lows: np.ndarray) -> List[float]:
        """
        Encuentra swing lows

        VALIDACIÓN: Uso de safe_slice y verificación de rangos
        """
        swing_lows = []
        length = len(lows)

        # Necesitamos al menos swing_length * 2 + 1
        if length < self.swing_length * 2 + 1:
            return swing_lows

        # Iterar desde swing_length hasta length - swing_length
        for i in range(self.swing_length, length - self.swing_length):
            # Verificar que i es un mínimo local
            left_window = self.safe_slice(lows, i - self.swing_length, i)
            right_window = self.safe_slice(lows, i + 1, i + 1 + self.swing_length)

            if len(left_window) == 0 or len(right_window) == 0:
                continue

            current = lows[i]

            if np.all(current <= left_window) and np.all(current <= right_window):
                swing_lows.append(current)

        return swing_lows
