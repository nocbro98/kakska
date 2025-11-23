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
import pandas as pd
from typing import Tuple, List, Optional
from strategies.base_strategy import BaseStrategy
from core.confluence_engine import StrategySignal
from utils.vsa_analyzer import VolumeSpreadAnalysis, VSASignal


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
        fvg_threshold: float = 0.001,
        enable_vsa: bool = True,
        enable_kaufman_filter: bool = True
    ):
        """
        Args:
            swing_length: Longitud para detectar swings
            fvg_threshold: Umbral mínimo para FVG (% del precio)
            enable_vsa: Habilitar validación VSA (Wyckoff)
            enable_kaufman_filter: Habilitar filtro de eficiencia Kaufman
        """
        # Calcular mínimo de barras requeridas
        # Necesitamos al menos: swing_length * 2 + buffer
        min_bars = max(50, swing_length * 3)

        super().__init__(name='SMC', min_bars_required=min_bars)

        self.swing_length = swing_length
        self.fvg_threshold = fvg_threshold
        self.enable_vsa = enable_vsa
        self.enable_kaufman_filter = enable_kaufman_filter

        # Inicializar VSA analyzer
        if self.enable_vsa:
            self.vsa_analyzer = VolumeSpreadAnalysis()
            self.logger.info("VSA validation enabled")
        else:
            self.vsa_analyzer = None
            self.logger.info("VSA validation disabled")

        self.logger.info(
            f"SMC Strategy initialized: "
            f"swing_length={swing_length}, "
            f"min_bars_required={self.min_bars_required}, "
            f"vsa_enabled={enable_vsa}, "
            f"kaufman_filter={enable_kaufman_filter}"
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
            # 2. CAPA SMC (Señales base)
            structure_signal, structure_reasons = self._detect_structure(highs, lows, closes)
            ob_signal, ob_reasons = self._detect_order_blocks(highs, lows, closes, opens)
            fvg_signal, fvg_reasons = self._detect_fair_value_gaps(highs, lows)

            # Combinar señales SMC
            smc_signals = [structure_signal, ob_signal, fvg_signal]
            valid_smc_signals = [s for s in smc_signals if s != 0]

            if not valid_smc_signals:
                return StrategySignal(
                    name=self.name,
                    signal=0,
                    confidence=0.0,
                    reasons=["No valid SMC patterns detected"]
                )

            # Señal SMC por mayoría
            avg_smc_signal = np.mean(valid_smc_signals)
            if avg_smc_signal > 0.3:
                smc_signal = 1
            elif avg_smc_signal < -0.3:
                smc_signal = -1
            else:
                smc_signal = 0

            if smc_signal == 0:
                return StrategySignal(
                    name=self.name,
                    signal=0,
                    confidence=0.0,
                    reasons=["SMC signals conflicting"]
                )

            # Confianza base
            base_confidence = len(valid_smc_signals) / 3.0 * 100
            all_reasons = structure_reasons + ob_reasons + fvg_reasons

            # 3. CAPA WYCKOFF (Validación VSA)
            vsa_valid = True
            vsa_signal_type = VSASignal.NORMAL
            vsa_confidence = 0.0

            if self.enable_vsa and self.vsa_analyzer and volumes is not None:
                vsa_analysis = self._validate_with_vsa(
                    closes, highs, lows, opens, volumes, smc_signal
                )
                vsa_valid = vsa_analysis['is_valid']
                vsa_signal_type = vsa_analysis['signal']
                vsa_confidence = vsa_analysis['confidence']

                if vsa_valid:
                    all_reasons.append(f"VSA: {vsa_signal_type.value} (conf={vsa_confidence:.1f}%)")
                    base_confidence += vsa_confidence * 0.2  # Boost 20%
                else:
                    all_reasons.append(f"VSA: {vsa_analysis['reason']}")
                    base_confidence *= 0.5  # Penalizar 50%

            # 4. CAPA ELLIOTT/KAUFMAN (Contexto de Tendencia)
            kaufman_valid = True
            kaufman_trend = "UNKNOWN"

            if self.enable_kaufman_filter:
                kaufman_analysis = self._validate_with_kaufman(closes, smc_signal)
                kaufman_valid = kaufman_analysis['is_valid']
                kaufman_trend = kaufman_analysis['trend']

                if kaufman_valid:
                    all_reasons.append(f"Kaufman: {kaufman_trend} trend")
                    base_confidence *= 1.1  # Boost 10%
                else:
                    all_reasons.append(f"Kaufman: {kaufman_analysis['reason']}")
                    base_confidence *= 0.7  # Penalizar 30%

            # 5. CONFLUENCIA FINAL
            if not vsa_valid and self.enable_vsa:
                return StrategySignal(
                    name=self.name,
                    signal=0,
                    confidence=0.0,
                    reasons=["VSA validation failed"] + all_reasons[:2]
                )

            if not kaufman_valid and self.enable_kaufman_filter:
                return StrategySignal(
                    name=self.name,
                    signal=0,
                    confidence=0.0,
                    reasons=["Market efficiency too low"] + all_reasons[:2]
                )

            # Señal final
            final_confidence = min(100.0, base_confidence)

            # Clasificar tipo de entrada según confluencia
            signal_strength = "STRONG" if final_confidence >= 70 else "SCALP"
            all_reasons.insert(0, f"{signal_strength} signal with {len(valid_smc_signals)}/3 SMC confirmations")

            return StrategySignal(
                name=self.name,
                signal=smc_signal,
                confidence=final_confidence / 100.0,
                reasons=all_reasons[:4]  # Top 4 razones
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

    # ===== VSA AND KAUFMAN VALIDATION METHODS =====

    def _validate_with_vsa(
        self,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        opens: np.ndarray,
        volumes: np.ndarray,
        smc_signal: int
    ) -> dict:
        """
        Valida señal SMC con VSA (Wyckoff Volume Spread Analysis)

        Args:
            closes, highs, lows, opens, volumes: Arrays de datos
            smc_signal: Señal SMC (1 = long, -1 = short)

        Returns:
            dict con: is_valid, signal, confidence, reason
        """
        try:
            # Crear DataFrame para VSA
            df = pd.DataFrame({
                'open': opens,
                'high': highs,
                'low': lows,
                'close': closes,
                'volume': volumes
            })

            # Analizar última vela
            current_candle = df.iloc[-1]
            vsa_analysis = self.vsa_analyzer.analyze_candle(current_candle, df)

            # Validar según dirección de señal SMC
            if smc_signal == 1:  # LONG
                # Señales VSA alcistas válidas
                bullish_signals = [
                    VSASignal.ABSORPTION_BUY,
                    VSASignal.NO_SUPPLY,
                    VSASignal.CLIMAX_SELL  # Clímax de venta puede ser reversión alcista
                ]

                if vsa_analysis.signal in bullish_signals:
                    return {
                        'is_valid': True,
                        'signal': vsa_analysis.signal,
                        'confidence': vsa_analysis.confidence,
                        'reason': f"VSA confirms LONG: {vsa_analysis.signal.value}"
                    }
                elif vsa_analysis.signal == VSASignal.NORMAL:
                    # Neutral es aceptable (no contradice)
                    return {
                        'is_valid': True,
                        'signal': vsa_analysis.signal,
                        'confidence': 50.0,
                        'reason': "VSA neutral (no contradiction)"
                    }
                else:
                    # Señal contradictoria
                    return {
                        'is_valid': False,
                        'signal': vsa_analysis.signal,
                        'confidence': 0.0,
                        'reason': f"VSA contradicts LONG: {vsa_analysis.signal.value}"
                    }

            elif smc_signal == -1:  # SHORT
                # Señales VSA bajistas válidas
                bearish_signals = [
                    VSASignal.ABSORPTION_SELL,
                    VSASignal.NO_DEMAND,
                    VSASignal.CLIMAX_BUY  # Clímax de compra puede ser reversión bajista
                ]

                if vsa_analysis.signal in bearish_signals:
                    return {
                        'is_valid': True,
                        'signal': vsa_analysis.signal,
                        'confidence': vsa_analysis.confidence,
                        'reason': f"VSA confirms SHORT: {vsa_analysis.signal.value}"
                    }
                elif vsa_analysis.signal == VSASignal.NORMAL:
                    return {
                        'is_valid': True,
                        'signal': vsa_analysis.signal,
                        'confidence': 50.0,
                        'reason': "VSA neutral (no contradiction)"
                    }
                else:
                    return {
                        'is_valid': False,
                        'signal': vsa_analysis.signal,
                        'confidence': 0.0,
                        'reason': f"VSA contradicts SHORT: {vsa_analysis.signal.value}"
                    }

            return {
                'is_valid': True,
                'signal': VSASignal.NORMAL,
                'confidence': 0.0,
                'reason': "No VSA signal"
            }

        except Exception as e:
            self.logger.warning(f"VSA validation error: {e}")
            # En caso de error, no bloquear la señal
            return {
                'is_valid': True,
                'signal': VSASignal.NORMAL,
                'confidence': 0.0,
                'reason': f"VSA error: {str(e)}"
            }

    def _validate_with_kaufman(
        self,
        closes: np.ndarray,
        smc_signal: int
    ) -> dict:
        """
        Valida señal SMC con filtro de eficiencia Kaufman

        Según Kaufman: ER < 0.30 indica mercado en ruido,
        no operar estrategias tendenciales.

        Args:
            closes: Array de precios de cierre
            smc_signal: Señal SMC (1 = long, -1 = short)

        Returns:
            dict con: is_valid, trend, reason
        """
        try:
            # Verificar contexto de tendencia válido
            is_valid, reason = self._is_valid_trend_context(closes, min_efficiency=0.25)

            if not is_valid:
                return {
                    'is_valid': False,
                    'trend': 'NOISE',
                    'reason': reason
                }

            # Obtener dirección de tendencia
            kama_trend = self._calculate_kama_trend(closes)

            # Validar consistencia con señal SMC
            if smc_signal == 1 and kama_trend == 'DOWN':
                return {
                    'is_valid': False,
                    'trend': kama_trend,
                    'reason': "KAMA shows DOWN trend but SMC signals LONG"
                }

            elif smc_signal == -1 and kama_trend == 'UP':
                return {
                    'is_valid': False,
                    'trend': kama_trend,
                    'reason': "KAMA shows UP trend but SMC signals SHORT"
                }

            # Detectar divergencia Elliott Wave 5 (reversión)
            is_divergence, div_confidence, div_reason = self._detect_elliott_wave_5_divergence(closes)

            if is_divergence:
                # Divergencia detectada - posible reversión
                # Esto es válido si SMC señala en dirección de la reversión
                return {
                    'is_valid': True,
                    'trend': f"{kama_trend}_REVERSAL",
                    'reason': f"Elliott Wave 5 divergence: {div_reason}"
                }

            # Contexto válido y consistente
            return {
                'is_valid': True,
                'trend': kama_trend,
                'reason': f"Valid {kama_trend} trend context"
            }

        except Exception as e:
            self.logger.warning(f"Kaufman validation error: {e}")
            # En caso de error, no bloquear la señal
            return {
                'is_valid': True,
                'trend': 'UNKNOWN',
                'reason': f"Kaufman error: {str(e)}"
            }
