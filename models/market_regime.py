"""
Market Regime Models
Modelos para detección y clasificación de regímenes de mercado
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class RegimeType(Enum):
    """Tipos de régimen de mercado"""
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    SQUEEZE = "squeeze"
    VOLATILE_HIGH = "volatile_high"
    VOLATILE_LOW = "volatile_low"
    UNKNOWN = "unknown"


@dataclass
class MarketRegime:
    """Estado actual del régimen de mercado"""
    # Tendencia
    trend_type: RegimeType = RegimeType.UNKNOWN
    trend_strength: float = 0.0  # ADX
    trend_slope: float = 0.0  # Pendiente de MA

    # Volatilidad
    volatility_percentile: float = 50.0  # Percentil de ATR/Close
    volatility_type: RegimeType = RegimeType.UNKNOWN

    # Rango/Squeeze
    bb_width_percentile: float = 50.0  # Percentil de Bollinger Bandwidth
    is_squeeze: bool = False

    # Timestamp
    ts_updated: datetime = None

    def __post_init__(self):
        if self.ts_updated is None:
            self.ts_updated = datetime.now()

    def allows_strategy(self, strategy_type: str) -> bool:
        """
        Determina si el régimen permite una estrategia específica

        Reglas:
        - Estrategias tendenciales requieren TRENDING
        - Estrategias de reversión requieren RANGING o SQUEEZE
        - Alta volatilidad puede bloquear según slippage budget
        """
        if strategy_type in ['elliott', 'breakout', 'smc_trend']:
            # Estrategias tendenciales
            return self.trend_type in [
                RegimeType.TRENDING_UP,
                RegimeType.TRENDING_DOWN
            ] and self.trend_strength > 20

        elif strategy_type in ['fibonacci_retracement', 'wyckoff_accumulation', 'mean_reversion']:
            # Estrategias de reversión/rango
            return self.trend_type == RegimeType.RANGING or self.is_squeeze

        return True  # Por defecto, permitir

    def get_volatility_adjustment(self) -> float:
        """
        Retorna factor de ajuste de tamaño según volatilidad
        1.0 = normal
        < 1.0 = reducir tamaño
        > 1.0 = aumentar tamaño
        """
        if self.volatility_percentile > 80:
            return 0.5  # Reducir 50% en alta volatilidad
        elif self.volatility_percentile > 60:
            return 0.75
        elif self.volatility_percentile < 20:
            return 1.25  # Aumentar 25% en baja volatilidad
        return 1.0

    def to_dict(self):
        """Convierte el régimen a diccionario"""
        return {
            'trend_type': self.trend_type.value,
            'trend_strength': self.trend_strength,
            'trend_slope': self.trend_slope,
            'volatility_percentile': self.volatility_percentile,
            'volatility_type': self.volatility_type.value,
            'bb_width_percentile': self.bb_width_percentile,
            'is_squeeze': self.is_squeeze,
            'ts_updated': self.ts_updated.isoformat()
        }
