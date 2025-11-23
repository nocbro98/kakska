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

    # Wyckoff Accumulation Phases
    ACCUMULATION_PHASE_A = "accumulation_phase_a"  # Preliminary Support (PS) y Selling Climax (SC)
    ACCUMULATION_PHASE_B = "accumulation_phase_b"  # Automatic Rally (AR) y Secondary Test (ST)
    ACCUMULATION_PHASE_C = "accumulation_phase_c"  # Spring y Test
    ACCUMULATION_PHASE_D = "accumulation_phase_d"  # Sign of Strength (SOS) y Last Point of Support (LPS)
    ACCUMULATION_PHASE_E = "accumulation_phase_e"  # Markup (Breakout definitivo)

    # Wyckoff Distribution Phases
    DISTRIBUTION_PHASE_A = "distribution_phase_a"  # Preliminary Supply (PSY) y Buying Climax (BC)
    DISTRIBUTION_PHASE_B = "distribution_phase_b"  # Automatic Reaction (AR) y Secondary Test (ST)
    DISTRIBUTION_PHASE_C = "distribution_phase_c"  # Upthrust (UT) y Test
    DISTRIBUTION_PHASE_D = "distribution_phase_d"  # Sign of Weakness (SOW) y Last Point of Supply (LPSY)
    DISTRIBUTION_PHASE_E = "distribution_phase_e"  # Markdown (Breakdown definitivo)


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

    # Wyckoff Phase Detection
    wyckoff_phase: Optional[RegimeType] = None
    wyckoff_confidence: float = 0.0  # Confianza en la fase detectada (0-100)
    wyckoff_support_level: Optional[float] = None  # Nivel de soporte clave para Accumulation
    wyckoff_resistance_level: Optional[float] = None  # Nivel de resistencia clave para Distribution

    # Timestamp
    ts_updated: datetime = None

    def __post_init__(self):
        if self.ts_updated is None:
            self.ts_updated = datetime.now()

    def allows_strategy(self, strategy_type: str) -> bool:
        """
        Determina si el régimen permite una estrategia específica

        Reglas:
        - Estrategias tendenciales requieren TRENDING o Wyckoff Phase E
        - Estrategias de reversión requieren RANGING o SQUEEZE
        - Wyckoff Phase C (Spring) es ideal para entradas
        - Alta volatilidad puede bloquear según slippage budget
        """
        # Estrategias tendenciales
        if strategy_type in ['elliott', 'breakout', 'smc_trend']:
            # Permitir en tendencias claras
            if self.trend_type in [RegimeType.TRENDING_UP, RegimeType.TRENDING_DOWN]:
                return self.trend_strength > 20

            # O en fase de markup/markdown de Wyckoff
            if self.wyckoff_phase in [
                RegimeType.ACCUMULATION_PHASE_E,
                RegimeType.DISTRIBUTION_PHASE_E
            ]:
                return self.wyckoff_confidence > 60

            return False

        # Estrategias de reversión/rango
        elif strategy_type in ['fibonacci_retracement', 'wyckoff_accumulation', 'mean_reversion']:
            # Permitir en ranging o squeeze
            if self.trend_type == RegimeType.RANGING or self.is_squeeze:
                return True

            # Spring de Wyckoff es setup de alta probabilidad
            if self.wyckoff_phase == RegimeType.ACCUMULATION_PHASE_C:
                return self.wyckoff_confidence > 70

            # Upthrust de Distribution también
            if self.wyckoff_phase == RegimeType.DISTRIBUTION_PHASE_C:
                return self.wyckoff_confidence > 70

            return False

        # Estrategias específicas de Wyckoff
        elif strategy_type == 'wyckoff_spring':
            return self.wyckoff_phase == RegimeType.ACCUMULATION_PHASE_C

        elif strategy_type == 'wyckoff_upthrust':
            return self.wyckoff_phase == RegimeType.DISTRIBUTION_PHASE_C

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
            'wyckoff_phase': self.wyckoff_phase.value if self.wyckoff_phase else None,
            'wyckoff_confidence': self.wyckoff_confidence,
            'wyckoff_support_level': self.wyckoff_support_level,
            'wyckoff_resistance_level': self.wyckoff_resistance_level,
            'ts_updated': self.ts_updated.isoformat()
        }
