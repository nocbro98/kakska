#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regime Detector
Detector de régimen de mercado con umbrales explícitos

Criterios:
- Tendencia: ADX + slope MA
- Volatilidad: ATR percentil
- Squeeze: Bollinger Bandwidth percentil
"""

import logging
import numpy as np
from typing import Optional, Tuple
from datetime import datetime

from core.event_bus import EventBus, EventType
from models.market_regime import MarketRegime, RegimeType


class RegimeDetector:
    """
    Detector de régimen de mercado

    Detecta:
    - Tendencia (ADX + slope)
    - Volatilidad (ATR percentil)
    - Squeeze (BB width percentil)
    """

    def __init__(
        self,
        event_bus: EventBus,
        adx_threshold: float = 20.0,
        volatility_high_percentile: float = 80.0,
        volatility_low_percentile: float = 20.0,
        squeeze_percentile: float = 20.0
    ):
        """
        Args:
            event_bus: Bus de eventos
            adx_threshold: Umbral de ADX para tendencia
            volatility_high_percentile: Percentil para volatilidad alta
            volatility_low_percentile: Percentil para volatilidad baja
            squeeze_percentile: Percentil para squeeze
        """
        self.event_bus = event_bus
        self.adx_threshold = adx_threshold
        self.volatility_high_percentile = volatility_high_percentile
        self.volatility_low_percentile = volatility_low_percentile
        self.squeeze_percentile = squeeze_percentile
        self.logger = logging.getLogger("RegimeDetector")

        self.current_regime: Optional[MarketRegime] = None

    def detect_regime(
        self,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        lookback: int = 100
    ) -> MarketRegime:
        """
        Detecta el régimen actual

        Args:
            closes: Precios de cierre
            highs: Precios máximos
            lows: Precios mínimos
            lookback: Período para cálculos

        Returns:
            MarketRegime detectado
        """
        if len(closes) < lookback:
            self.logger.warning(f"Insufficient data for regime detection: {len(closes)} < {lookback}")
            return MarketRegime(trend_type=RegimeType.UNKNOWN, volatility_type=RegimeType.UNKNOWN)

        # Calcular ADX
        adx = self._calculate_adx(highs, lows, closes, period=14)

        # Calcular slope de MA
        ma = self._calculate_sma(closes, period=20)
        slope = self._calculate_slope(ma, period=10)

        # Determinar tendencia
        if adx > self.adx_threshold:
            if slope > 0:
                trend_type = RegimeType.TRENDING_UP
            else:
                trend_type = RegimeType.TRENDING_DOWN
        else:
            trend_type = RegimeType.RANGING

        # Calcular ATR y su percentil
        atr = self._calculate_atr(highs, lows, closes, period=14)
        atr_normalized = atr / closes[-1] * 100  # ATR como % del precio
        atr_percentile = self._calculate_percentile(atr_normalized, lookback)

        # Determinar volatilidad
        if atr_percentile > self.volatility_high_percentile:
            volatility_type = RegimeType.VOLATILE_HIGH
        elif atr_percentile < self.volatility_low_percentile:
            volatility_type = RegimeType.VOLATILE_LOW
        else:
            volatility_type = RegimeType.UNKNOWN

        # Calcular Bollinger Bandwidth y su percentil
        bb_width = self._calculate_bb_width(closes, period=20, std_dev=2)
        bb_percentile = self._calculate_percentile(bb_width, lookback)

        is_squeeze = bb_percentile < self.squeeze_percentile

        # Crear régimen
        regime = MarketRegime(
            trend_type=trend_type,
            trend_strength=adx,
            trend_slope=slope,
            volatility_percentile=atr_percentile,
            volatility_type=volatility_type,
            bb_width_percentile=bb_percentile,
            is_squeeze=is_squeeze,
            ts_updated=datetime.now()
        )

        # Verificar cambio de régimen
        if self.current_regime and regime.trend_type != self.current_regime.trend_type:
            self.logger.info(f"Regime changed: {self.current_regime.trend_type.value} → {regime.trend_type.value}")

            self.event_bus.publish(
                EventType.REGIME_CHANGED,
                regime.to_dict(),
                source='RegimeDetector'
            )

        self.current_regime = regime
        return regime

    def get_current_regime(self) -> Optional[MarketRegime]:
        """Retorna el régimen actual"""
        return self.current_regime

    def allows_strategy(self, strategy_type: str) -> Tuple[bool, str]:
        """
        Verifica si el régimen permite una estrategia

        Args:
            strategy_type: Tipo de estrategia

        Returns:
            (permite, razón)
        """
        if not self.current_regime:
            return False, "No regime detected yet"

        if self.current_regime.allows_strategy(strategy_type):
            return True, "Strategy allowed in current regime"
        else:
            return False, f"Strategy '{strategy_type}' not suitable for {self.current_regime.trend_type.value}"

    def get_stats(self) -> dict:
        """Retorna estadísticas del detector"""
        if not self.current_regime:
            return {'regime': None}

        regime_dict = self.current_regime.to_dict()

        # Agregar info sobre estrategias permitidas
        allows_trending = self.current_regime.trend_type in [RegimeType.TRENDING_UP, RegimeType.TRENDING_DOWN]
        allows_mean_reversion = self.current_regime.trend_type == RegimeType.RANGING or self.current_regime.is_squeeze

        return {
            'regime': regime_dict,
            'allows_trending': allows_trending,
            'allows_mean_reversion': allows_mean_reversion,
            'size_adjustment': self.current_regime.get_volatility_adjustment()
        }

    # Indicadores técnicos

    def _calculate_sma(self, data: np.ndarray, period: int) -> np.ndarray:
        """Calcula Simple Moving Average"""
        if len(data) < period:
            return np.full(len(data), np.nan)
        return np.convolve(data, np.ones(period)/period, mode='same')

    def _calculate_slope(self, data: np.ndarray, period: int) -> float:
        """Calcula la pendiente de los últimos N puntos"""
        if len(data) < period:
            return 0.0

        recent = data[-period:]
        x = np.arange(len(recent))
        slope = np.polyfit(x, recent, 1)[0]
        return slope

    def _calculate_atr(self, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int) -> float:
        """Calcula Average True Range"""
        if len(closes) < period + 1:
            return 0.0

        tr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(
                np.abs(highs[1:] - closes[:-1]),
                np.abs(lows[1:] - closes[:-1])
            )
        )

        atr = np.mean(tr[-period:])
        return atr

    def _calculate_adx(self, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
        """Calcula Average Directional Index (simplificado)"""
        if len(closes) < period + 1:
            return 0.0

        # Calcular +DM y -DM
        high_diff = np.diff(highs)
        low_diff = -np.diff(lows)

        plus_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0)
        minus_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0)

        # Calcular TR
        tr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(
                np.abs(highs[1:] - closes[:-1]),
                np.abs(lows[1:] - closes[:-1])
            )
        )

        # Suavizar
        atr = np.mean(tr[-period:])
        plus_di = np.mean(plus_dm[-period:]) / atr * 100 if atr > 0 else 0
        minus_di = np.mean(minus_dm[-period:]) / atr * 100 if atr > 0 else 0

        # Calcular ADX (simplificado)
        dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) > 0 else 0

        return dx

    def _calculate_bb_width(self, closes: np.ndarray, period: int, std_dev: float) -> float:
        """Calcula Bollinger Bandwidth"""
        if len(closes) < period:
            return 0.0

        recent = closes[-period:]
        ma = np.mean(recent)
        std = np.std(recent)

        upper = ma + std_dev * std
        lower = ma - std_dev * std

        width = (upper - lower) / ma * 100 if ma > 0 else 0
        return width

    def _calculate_percentile(self, value: float, lookback: int) -> float:
        """Calcula el percentil de un valor (simplificado)"""
        # En una implementación completa, mantendría un buffer histórico
        # Por ahora, retornamos un valor razonable
        return 50.0
