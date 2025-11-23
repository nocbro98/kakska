#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Technical Indicators Module
Indicadores técnicos avanzados para análisis de mercado

Incluye:
- KAMA (Kaufman Adaptive Moving Average)
- EWO (Elliott Wave Oscillator)
- Efficiency Ratio
- Otros indicadores adaptativos

Referencias:
- Perry Kaufman: "Trading Systems and Methods" (2013)
- Robert Elliott: "The Wave Principle"
"""

import numpy as np
import pandas as pd
from typing import Tuple, Optional
import logging


logger = logging.getLogger("Indicators")


def calculate_efficiency_ratio(
    prices: np.ndarray,
    period: int = 10
) -> np.ndarray:
    """
    Calcula el Efficiency Ratio (ER) de Kaufman

    El ER mide qué tan eficiente es el movimiento del precio:
    - ER cercano a 1.0: Movimiento direccional fuerte (tendencia)
    - ER cercano a 0.0: Movimiento errático (ruido/rango)

    Formula:
        Change = Abs(Price[t] - Price[t-n])
        Volatility = Sum(Abs(Price[i] - Price[i-1])) for i in [t-n, t]
        ER = Change / Volatility

    Args:
        prices: Array de precios
        period: Período de cálculo

    Returns:
        Array de Efficiency Ratios
    """
    if len(prices) < period:
        return np.full(len(prices), np.nan)

    er = np.full(len(prices), np.nan)

    for i in range(period, len(prices)):
        # Cambio neto (dirección)
        change = abs(prices[i] - prices[i - period])

        # Volatilidad (suma de movimientos)
        volatility = np.sum(np.abs(np.diff(prices[i - period:i + 1])))

        # Efficiency Ratio
        if volatility > 0:
            er[i] = change / volatility
        else:
            er[i] = 0.0

    return er


def calculate_kama(
    prices: np.ndarray,
    er_period: int = 10,
    fast_ema_period: int = 2,
    slow_ema_period: int = 30
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calcula KAMA (Kaufman Adaptive Moving Average)

    KAMA es una media móvil que se adapta a la volatilidad del mercado:
    - En tendencias fuertes (ER alto): Se comporta como EMA rápida
    - En mercados laterales (ER bajo): Se comporta como EMA lenta

    Esto reduce el ruido en rangos y responde rápido en tendencias.

    Formula:
        SC = (ER * (fast_sc - slow_sc) + slow_sc)^2
        KAMA[t] = KAMA[t-1] + SC * (Price - KAMA[t-1])

    Donde:
        fast_sc = 2 / (fast_ema_period + 1)
        slow_sc = 2 / (slow_ema_period + 1)

    Args:
        prices: Array de precios
        er_period: Período para Efficiency Ratio
        fast_ema_period: Período de EMA rápida
        slow_ema_period: Período de EMA lenta

    Returns:
        (kama, efficiency_ratio)
    """
    if len(prices) < er_period + 1:
        return np.full(len(prices), np.nan), np.full(len(prices), np.nan)

    # Calcular Efficiency Ratio
    er = calculate_efficiency_ratio(prices, er_period)

    # Smoothing constants
    fast_sc = 2.0 / (fast_ema_period + 1)
    slow_sc = 2.0 / (slow_ema_period + 1)

    # Inicializar KAMA
    kama = np.full(len(prices), np.nan)
    kama[er_period] = prices[er_period]  # Seed inicial

    # Calcular KAMA recursivamente
    for i in range(er_period + 1, len(prices)):
        if np.isnan(er[i]):
            continue

        # Smoothing constant adaptativo
        sc = (er[i] * (fast_sc - slow_sc) + slow_sc) ** 2

        # KAMA adaptativo
        kama[i] = kama[i - 1] + sc * (prices[i] - kama[i - 1])

    return kama, er


def classify_market_state_kaufman(
    efficiency_ratio: float,
    noise_threshold: float = 0.30,
    trend_threshold: float = 0.50
) -> str:
    """
    Clasifica el estado del mercado según Kaufman

    Categorías:
    - NOISE: ER < 0.30 (mercado lateral, no operar Elliott)
    - WEAK_TREND: 0.30 <= ER < 0.50
    - STRONG_TREND: ER >= 0.50 (ideal para Elliott)

    Args:
        efficiency_ratio: Valor actual del ER
        noise_threshold: Umbral de ruido
        trend_threshold: Umbral de tendencia fuerte

    Returns:
        Estado del mercado
    """
    if np.isnan(efficiency_ratio):
        return "UNKNOWN"

    if efficiency_ratio < noise_threshold:
        return "NOISE"
    elif efficiency_ratio < trend_threshold:
        return "WEAK_TREND"
    else:
        return "STRONG_TREND"


def calculate_ewo(
    prices: np.ndarray,
    fast_period: int = 5,
    slow_period: int = 35
) -> np.ndarray:
    """
    Calcula EWO (Elliott Wave Oscillator)

    El EWO es un oscilador de momentum usado para objetivar el conteo de ondas
    de Elliott. Ayuda a identificar:
    - Onda 3: Máximo absoluto del EWO
    - Onda 5: Divergencia (precio nuevo high, pero EWO más bajo)

    Formula:
        EWO = SMA(close, fast_period) - SMA(close, slow_period)

    Args:
        prices: Array de precios de cierre
        fast_period: Período de SMA rápida (default: 5)
        slow_period: Período de SMA lenta (default: 35)

    Returns:
        Array de valores EWO
    """
    if len(prices) < slow_period:
        return np.full(len(prices), np.nan)

    # Calcular SMAs
    sma_fast = pd.Series(prices).rolling(window=fast_period).mean().values
    sma_slow = pd.Series(prices).rolling(window=slow_period).mean().values

    # EWO = Diferencia
    ewo = sma_fast - sma_slow

    return ewo


def detect_elliott_wave_3(
    ewo: np.ndarray,
    lookback: int = 50
) -> Tuple[Optional[int], float]:
    """
    Detecta Onda 3 de Elliott usando EWO

    La Onda 3 típicamente muestra el valor absoluto máximo del EWO,
    indicando el mayor momentum de la tendencia.

    Args:
        ewo: Array de Elliott Wave Oscillator
        lookback: Ventana de búsqueda hacia atrás

    Returns:
        (índice_onda_3, valor_ewo) o (None, 0.0)
    """
    if len(ewo) < lookback:
        lookback = len(ewo)

    # Obtener ventana reciente
    recent_ewo = ewo[-lookback:]

    # Filtrar NaN
    valid_indices = ~np.isnan(recent_ewo)
    if not np.any(valid_indices):
        return None, 0.0

    valid_ewo = recent_ewo[valid_indices]

    # Buscar valor absoluto máximo
    abs_ewo = np.abs(valid_ewo)
    max_idx = np.argmax(abs_ewo)

    # Convertir a índice global
    valid_positions = np.where(valid_indices)[0]
    global_idx = len(ewo) - lookback + valid_positions[max_idx]

    return global_idx, valid_ewo[max_idx]


def detect_elliott_divergence_wave_5(
    prices: np.ndarray,
    ewo: np.ndarray,
    wave_3_idx: Optional[int] = None,
    min_bars_since_wave_3: int = 10
) -> Tuple[bool, float]:
    """
    Detecta divergencia de Onda 5 (posible final de impulso)

    Criterios para Onda 5:
    1. Precio actual > Precio en pico EWO (nuevo high/low)
    2. EWO actual < EWO en pico (divergencia bajista)
    3. Han pasado suficientes barras desde Onda 3

    Args:
        prices: Array de precios
        ewo: Array de EWO
        wave_3_idx: Índice de la Onda 3 (peak EWO)
        min_bars_since_wave_3: Mínimo de barras entre Onda 3 y 5

    Returns:
        (is_divergence, confidence)
    """
    if wave_3_idx is None:
        # Auto-detectar Onda 3
        wave_3_idx, _ = detect_elliott_wave_3(ewo)

    if wave_3_idx is None or wave_3_idx >= len(prices) - 1:
        return False, 0.0

    # Verificar distancia mínima
    bars_since_wave_3 = len(prices) - 1 - wave_3_idx
    if bars_since_wave_3 < min_bars_since_wave_3:
        return False, 0.0

    # Valores de referencia (Onda 3)
    price_at_wave_3 = prices[wave_3_idx]
    ewo_at_wave_3 = ewo[wave_3_idx]

    # Valores actuales (posible Onda 5)
    current_price = prices[-1]
    current_ewo = ewo[-1]

    if np.isnan(current_ewo) or np.isnan(ewo_at_wave_3):
        return False, 0.0

    # Detectar divergencia alcista (bull market)
    if ewo_at_wave_3 > 0:
        price_new_high = current_price > price_at_wave_3
        ewo_lower = current_ewo < ewo_at_wave_3

        if price_new_high and ewo_lower:
            # Calcular confianza basada en magnitud de divergencia
            price_change = (current_price - price_at_wave_3) / price_at_wave_3
            ewo_decline = (ewo_at_wave_3 - current_ewo) / abs(ewo_at_wave_3)

            confidence = min(90.0, 50.0 + ewo_decline * 100)
            return True, confidence

    # Detectar divergencia bajista (bear market)
    elif ewo_at_wave_3 < 0:
        price_new_low = current_price < price_at_wave_3
        ewo_higher = current_ewo > ewo_at_wave_3  # Menos negativo

        if price_new_low and ewo_higher:
            price_change = (price_at_wave_3 - current_price) / price_at_wave_3
            ewo_improvement = (current_ewo - ewo_at_wave_3) / abs(ewo_at_wave_3)

            confidence = min(90.0, 50.0 + ewo_improvement * 100)
            return True, confidence

    return False, 0.0


def calculate_adaptive_atr(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    period: int = 14,
    efficiency_ratio: Optional[np.ndarray] = None
) -> np.ndarray:
    """
    Calcula ATR adaptativo usando Efficiency Ratio

    En mercados con baja eficiencia (ruido), el ATR se suaviza más.
    En mercados con alta eficiencia (tendencia), el ATR es más reactivo.

    Args:
        highs: Precios máximos
        lows: Precios mínimos
        closes: Precios de cierre
        period: Período base de ATR
        efficiency_ratio: ER pre-calculado (opcional)

    Returns:
        Array de ATR adaptativo
    """
    if len(closes) < period:
        return np.full(len(closes), np.nan)

    # Calcular True Range
    tr1 = highs - lows
    tr2 = np.abs(highs - np.roll(closes, 1))
    tr3 = np.abs(lows - np.roll(closes, 1))

    tr = np.maximum(tr1, np.maximum(tr2, tr3))
    tr[0] = np.nan  # Primer valor no tiene previous close

    # ATR estándar
    atr = pd.Series(tr).rolling(window=period).mean().values

    # Si no hay ER, retornar ATR estándar
    if efficiency_ratio is None:
        return atr

    # Aplicar adaptación con ER
    # ER alto -> menor suavizado (más reactivo)
    # ER bajo -> mayor suavizado (menos ruido)
    adaptive_atr = np.copy(atr)

    for i in range(period, len(atr)):
        if not np.isnan(efficiency_ratio[i]) and not np.isnan(atr[i]):
            # Factor de adaptación (0.5 a 2.0)
            adaptation = 0.5 + efficiency_ratio[i] * 1.5

            # Ajustar ATR
            if i > period:
                adaptive_atr[i] = adaptive_atr[i - 1] + adaptation * (tr[i] - adaptive_atr[i - 1])

    return adaptive_atr


def validate_trend_with_kaufman(
    prices: np.ndarray,
    kama_period: int = 10,
    min_efficiency: float = 0.30
) -> Tuple[bool, str, float]:
    """
    Valida si existe una tendencia válida según Kaufman

    Útil para filtrar señales de estrategias tendenciales (Elliott, breakouts).

    Args:
        prices: Array de precios
        kama_period: Período para KAMA
        min_efficiency: Eficiencia mínima requerida

    Returns:
        (is_valid_trend, trend_direction, efficiency_ratio)
    """
    if len(prices) < kama_period + 10:
        return False, "UNKNOWN", 0.0

    # Calcular KAMA y ER
    kama, er = calculate_kama(prices, er_period=kama_period)

    # Obtener valores actuales
    current_er = er[-1]
    current_price = prices[-1]
    current_kama = kama[-1]

    if np.isnan(current_er) or np.isnan(current_kama):
        return False, "UNKNOWN", 0.0

    # Verificar eficiencia mínima
    if current_er < min_efficiency:
        return False, "NOISE", current_er

    # Determinar dirección
    if current_price > current_kama:
        trend_direction = "UP"
    elif current_price < current_kama:
        trend_direction = "DOWN"
    else:
        trend_direction = "NEUTRAL"

    # Validar consistencia de tendencia
    # Verificar que KAMA tenga pendiente consistente
    if len(kama) >= 5:
        kama_slope = (kama[-1] - kama[-5]) / kama[-5]

        if trend_direction == "UP" and kama_slope < -0.001:
            return False, "CONFLICTING", current_er
        elif trend_direction == "DOWN" and kama_slope > 0.001:
            return False, "CONFLICTING", current_er

    return True, trend_direction, current_er
