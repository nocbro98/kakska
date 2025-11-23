#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Volume Spread Analysis (VSA) Module
Implementación de la "Ley de Esfuerzo vs. Resultado" según Valdecantos/Villahermosa

Conceptos Clave:
- Esfuerzo: Volumen (cantidad de transacciones)
- Resultado: Spread (rango de precio H-L)
- Anomalías: Situaciones donde el esfuerzo no corresponde con el resultado

Referencias:
- José Luis Valdecantos: "VSA: Volume Spread Analysis"
- Tom Williams: "Master the Markets"
"""

import logging
import numpy as np
import pandas as pd
from enum import Enum
from typing import Dict, Optional, Tuple
from dataclasses import dataclass


class VSASignal(Enum):
    """Tipos de señales VSA"""
    NORMAL = "normal"
    ABSORPTION_BUY = "absorption_buy"  # Absorción de ventas (alcista)
    ABSORPTION_SELL = "absorption_sell"  # Absorción de compras (bajista)
    NO_SUPPLY = "no_supply"  # Sin oferta (alcista)
    NO_DEMAND = "no_demand"  # Sin demanda (bajista)
    EFFORT_NO_RESULT_BULLISH = "effort_no_result_bullish"  # Esfuerzo sin resultado alcista
    EFFORT_NO_RESULT_BEARISH = "effort_no_result_bearish"  # Esfuerzo sin resultado bajista
    CLIMAX_BUY = "climax_buy"  # Clímax de compra (potencial top)
    CLIMAX_SELL = "climax_sell"  # Clímax de venta (potencial bottom)


@dataclass
class VSAAnalysis:
    """Resultado del análisis VSA de una vela"""
    signal: VSASignal
    relative_volume: float
    relative_spread: float
    confidence: float  # 0-100
    reasons: list


class VolumeSpreadAnalysis:
    """
    Analizador de Volumen y Spread según metodología VSA

    Implementa:
    - Detección de anomalías de volumen/spread
    - Identificación de absorción institucional
    - Detección de clímax de compra/venta
    - Validación de rupturas con volumen

    Uso:
        vsa = VolumeSpreadAnalysis()
        signal = vsa.analyze_candle(df.iloc[-1], df)
    """

    def __init__(
        self,
        volume_period: int = 20,
        spread_period: int = 20,
        high_volume_threshold: float = 2.0,
        low_volume_threshold: float = 0.6,
        narrow_spread_threshold: float = 0.8,
        wide_spread_threshold: float = 1.5
    ):
        """
        Args:
            volume_period: Período para calcular media de volumen
            spread_period: Período para calcular media de spread
            high_volume_threshold: Multiplicador para volumen alto
            low_volume_threshold: Multiplicador para volumen bajo
            narrow_spread_threshold: Multiplicador para spread estrecho
            wide_spread_threshold: Multiplicador para spread amplio
        """
        self.volume_period = volume_period
        self.spread_period = spread_period
        self.high_vol_threshold = high_volume_threshold
        self.low_vol_threshold = low_volume_threshold
        self.narrow_spread_threshold = narrow_spread_threshold
        self.wide_spread_threshold = wide_spread_threshold

        self.logger = logging.getLogger("VSA")

        self.logger.info(
            f"VSA initialized: vol_period={volume_period}, "
            f"spread_period={spread_period}"
        )

    def calculate_relative_metrics(
        self,
        current_candle: pd.Series,
        historical_data: pd.DataFrame
    ) -> Tuple[float, float]:
        """
        Calcula métricas relativas de volumen y spread

        Args:
            current_candle: Vela actual
            historical_data: DataFrame con histórico (debe incluir current_candle)

        Returns:
            (relative_volume, relative_spread)
        """
        try:
            # Validar que tenemos suficientes datos
            if len(historical_data) < max(self.volume_period, self.spread_period):
                return 1.0, 1.0  # Valores neutros

            # Calcular spread actual
            current_spread = current_candle['high'] - current_candle['low']

            # Evitar división por cero
            if current_spread <= 0:
                current_spread = current_candle['close'] * 0.0001  # 0.01% mínimo

            # Spread relativo
            historical_spreads = historical_data['high'] - historical_data['low']
            avg_spread = historical_spreads.rolling(self.spread_period).mean().iloc[-1]

            if avg_spread > 0:
                relative_spread = current_spread / avg_spread
            else:
                relative_spread = 1.0

            # Volumen relativo (si está disponible)
            if 'volume' in current_candle and current_candle['volume'] is not None:
                current_volume = current_candle['volume']

                if 'volume' in historical_data.columns:
                    avg_volume = historical_data['volume'].rolling(self.volume_period).mean().iloc[-1]

                    if avg_volume > 0:
                        relative_volume = current_volume / avg_volume
                    else:
                        relative_volume = 1.0
                else:
                    relative_volume = 1.0
            else:
                # Si no hay volumen, retornar neutro
                relative_volume = 1.0

            return relative_volume, relative_spread

        except Exception as e:
            self.logger.warning(f"Error calculating relative metrics: {e}")
            return 1.0, 1.0  # Valores neutros en caso de error

    def analyze_candle(
        self,
        current_candle: pd.Series,
        historical_data: Optional[pd.DataFrame] = None
    ) -> VSAAnalysis:
        """
        Analiza una vela individual según VSA

        Args:
            current_candle: Vela a analizar (debe tener: open, high, low, close, volume)
            historical_data: DataFrame con histórico para calcular medias

        Returns:
            VSAAnalysis con señal detectada
        """
        # Si no hay datos históricos, retornar NORMAL
        if historical_data is None or len(historical_data) < 20:
            return VSAAnalysis(
                signal=VSASignal.NORMAL,
                relative_volume=1.0,
                relative_spread=1.0,
                confidence=0.0,
                reasons=["Insufficient historical data"]
            )

        # Calcular métricas relativas
        rel_vol, rel_spread = self.calculate_relative_metrics(current_candle, historical_data)

        # Determinar tipo de vela
        is_bullish = current_candle['close'] > current_candle['open']
        is_bearish = current_candle['close'] < current_candle['open']

        # Variables para el análisis
        signal = VSASignal.NORMAL
        confidence = 0.0
        reasons = []

        # ===== DETECCIÓN DE ANOMALÍAS VSA =====

        # 1. ESFUERZO SIN RESULTADO ALCISTA (Absorción de Ventas)
        # Condición: Alto volumen + spread estrecho + vela bajista
        if (rel_vol > self.high_vol_threshold and
            rel_spread < self.narrow_spread_threshold and
            is_bearish):
            signal = VSASignal.ABSORPTION_BUY
            confidence = min(90.0, 50.0 + (rel_vol * 10))
            reasons.append(
                f"High volume ({rel_vol:.2f}x) with narrow spread ({rel_spread:.2f}x) "
                "on down bar suggests professional absorption"
            )

        # 2. ESFUERZO SIN RESULTADO BAJISTA (Absorción de Compras)
        # Condición: Alto volumen + spread estrecho + vela alcista
        elif (rel_vol > self.high_vol_threshold and
              rel_spread < self.narrow_spread_threshold and
              is_bullish):
            signal = VSASignal.ABSORPTION_SELL
            confidence = min(90.0, 50.0 + (rel_vol * 10))
            reasons.append(
                f"High volume ({rel_vol:.2f}x) with narrow spread ({rel_spread:.2f}x) "
                "on up bar suggests distribution"
            )

        # 3. SIN OFERTA (No Supply)
        # Condición: Bajo volumen + spread estrecho + vela alcista
        elif (rel_vol < self.low_vol_threshold and
              rel_spread < self.narrow_spread_threshold and
              is_bullish):
            signal = VSASignal.NO_SUPPLY
            confidence = 65.0
            reasons.append(
                f"Low volume ({rel_vol:.2f}x) on up bar suggests no supply - bullish"
            )

        # 4. SIN DEMANDA (No Demand)
        # Condición: Bajo volumen + spread estrecho + vela bajista
        elif (rel_vol < self.low_vol_threshold and
              rel_spread < self.narrow_spread_threshold and
              is_bearish):
            signal = VSASignal.NO_DEMAND
            confidence = 65.0
            reasons.append(
                f"Low volume ({rel_vol:.2f}x) on down bar suggests no demand - bearish"
            )

        # 5. CLÍMAX DE COMPRA (Buying Climax)
        # Condición: Volumen extremadamente alto + spread amplio + vela alcista
        elif (rel_vol > self.high_vol_threshold * 1.5 and
              rel_spread > self.wide_spread_threshold and
              is_bullish):
            signal = VSASignal.CLIMAX_BUY
            confidence = 75.0
            reasons.append(
                f"Extreme volume ({rel_vol:.2f}x) with wide spread - "
                "possible buying climax (reversal)"
            )

        # 6. CLÍMAX DE VENTA (Selling Climax)
        # Condición: Volumen extremadamente alto + spread amplio + vela bajista
        elif (rel_vol > self.high_vol_threshold * 1.5 and
              rel_spread > self.wide_spread_threshold and
              is_bearish):
            signal = VSASignal.CLIMAX_SELL
            confidence = 75.0
            reasons.append(
                f"Extreme volume ({rel_vol:.2f}x) with wide spread - "
                "possible selling climax (reversal)"
            )

        # 7. Condiciones normales
        else:
            signal = VSASignal.NORMAL
            confidence = 0.0
            reasons.append("No VSA anomaly detected")

        return VSAAnalysis(
            signal=signal,
            relative_volume=rel_vol,
            relative_spread=rel_spread,
            confidence=confidence,
            reasons=reasons
        )

    def validate_breakout(
        self,
        breakout_candle: pd.Series,
        historical_data: pd.DataFrame,
        breakout_direction: str = 'up'
    ) -> Tuple[bool, float, str]:
        """
        Valida una ruptura usando VSA

        Una ruptura válida debe tener:
        - Volumen por encima del promedio
        - Spread amplio (momentum)
        - Dirección consistente

        Args:
            breakout_candle: Vela de ruptura
            historical_data: Histórico
            breakout_direction: 'up' o 'down'

        Returns:
            (is_valid, confidence, reason)
        """
        rel_vol, rel_spread = self.calculate_relative_metrics(breakout_candle, historical_data)

        # Criterios para ruptura válida
        valid_volume = rel_vol > 1.2  # Al menos 20% más de volumen
        valid_spread = rel_spread > 0.8  # Spread no demasiado estrecho

        is_bullish = breakout_candle['close'] > breakout_candle['open']
        is_bearish = breakout_candle['close'] < breakout_candle['open']

        # Verificar dirección consistente
        if breakout_direction == 'up':
            direction_ok = is_bullish
        else:
            direction_ok = is_bearish

        # Calcular confianza
        if valid_volume and valid_spread and direction_ok:
            confidence = min(90.0, 50.0 + (rel_vol * 20))
            reason = f"Valid breakout: volume={rel_vol:.2f}x, spread={rel_spread:.2f}x"
            return True, confidence, reason
        else:
            confidence = 30.0
            issues = []
            if not valid_volume:
                issues.append(f"low volume ({rel_vol:.2f}x)")
            if not valid_spread:
                issues.append(f"narrow spread ({rel_spread:.2f}x)")
            if not direction_ok:
                issues.append("wrong direction")

            reason = f"Weak breakout: {', '.join(issues)}"
            return False, confidence, reason

    def detect_spring(
        self,
        historical_data: pd.DataFrame,
        support_level: float,
        lookback: int = 5
    ) -> Tuple[bool, float]:
        """
        Detecta un "Spring" de Wyckoff

        Spring: Ruptura falsa por debajo del soporte con bajo volumen,
        seguida de recuperación rápida.

        Args:
            historical_data: DataFrame con datos recientes
            support_level: Nivel de soporte a testear
            lookback: Velas a revisar

        Returns:
            (is_spring, confidence)
        """
        if len(historical_data) < lookback:
            return False, 0.0

        recent_data = historical_data.iloc[-lookback:]

        # Buscar vela que rompió soporte
        broke_support = recent_data[recent_data['low'] < support_level]

        if len(broke_support) == 0:
            return False, 0.0

        # Obtener la última vela que rompió
        spring_candle = broke_support.iloc[-1]
        spring_idx = historical_data.index.get_loc(spring_candle.name)

        # Analizar volumen de la ruptura
        rel_vol, _ = self.calculate_relative_metrics(spring_candle, historical_data)

        # Spring válido: bajo volumen + precio recupera por encima del soporte
        current_close = historical_data.iloc[-1]['close']
        recovered = current_close > support_level
        low_volume = rel_vol < 1.0

        if recovered and low_volume:
            confidence = 70.0 + (1.0 - rel_vol) * 20  # Más confianza si volumen muy bajo
            return True, min(90.0, confidence)

        return False, 0.0
