"""
Regime Filter Helper
Helper para filtrado de señales basado en régimen de mercado

Simplifica el uso de RegimeDetector en la lógica de trading, proporcionando
métodos directos para verificar compatibilidad de estrategias con el régimen actual.
"""

import logging
from typing import Dict, Tuple, Optional
import pandas as pd
from core.regime_detector import RegimeDetector, MarketRegime, RegimeType


class RegimeFilter:
    """
    Helper para filtrado de señales por régimen de mercado

    Proporciona una interfaz simplificada para:
    - Detectar régimen actual
    - Filtrar estrategias incompatibles
    - Ajustar tamaño de posición por volatilidad
    - Recomendar estrategias según régimen
    """

    def __init__(self, event_bus=None):
        """
        Args:
            event_bus: EventBus opcional para eventos
        """
        self.detector = RegimeDetector(event_bus)
        self.logger = logging.getLogger("RegimeFilter")

        # Mapeo de estrategias a regímenes compatibles
        self.strategy_regime_map = {
            # Estrategias tendenciales (requieren tendencia fuerte)
            'elliott': {
                'compatible': [RegimeType.TRENDING_UP, RegimeType.TRENDING_DOWN],
                'min_strength': 25,
                'description': 'Elliott Wave funciona mejor en tendencias claras'
            },

            # Estrategias de retroceso (funcionan en rango o tendencia débil)
            'fibonacci': {
                'compatible': [RegimeType.RANGING, RegimeType.TRENDING_UP, RegimeType.TRENDING_DOWN],
                'min_strength': 0,  # Funciona en cualquier fuerza
                'description': 'Fibonacci retrocesos funcionan en cualquier condición'
            },

            # Wyckoff acumulación/distribución (mejor en rango)
            'wyckoff': {
                'compatible': [RegimeType.RANGING],
                'min_strength': 0,
                'description': 'Wyckoff acumulación mejor en mercados laterales'
            },

            # SMC (Smart Money Concepts) - mejor en tendencia
            'smc': {
                'compatible': [RegimeType.TRENDING_UP, RegimeType.TRENDING_DOWN],
                'min_strength': 20,
                'description': 'SMC Order Blocks mejor en tendencias'
            },

            # Breakouts (mejor en squeeze con baja volatilidad)
            'breakout': {
                'compatible': [RegimeType.RANGING],
                'requires_squeeze': True,
                'description': 'Breakouts mejor después de consolidación'
            }
        }

    def update(self, df: pd.DataFrame) -> MarketRegime:
        """
        Actualiza detección de régimen con nuevos datos

        Args:
            df: DataFrame con OHLCV y indicadores (ADX, ATR, BBands)

        Returns:
            MarketRegime detectado
        """
        # Extraer arrays de precios del dataframe
        closes = df['close'].to_numpy()
        highs = df['high'].to_numpy()
        lows = df['low'].to_numpy()

        # Detectar régimen con los arrays separados
        regime = self.detector.detect_regime(closes, highs, lows)

        self.logger.debug(
            f"[REGIME] {regime.trend_type.value} "
            f"(strength: {regime.trend_strength:.1f}, "
            f"vol: {regime.volatility_type.value})"
        )

        return regime

    def should_filter_strategy(
        self,
        strategy_name: str,
        regime: Optional[MarketRegime] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Verifica si una estrategia debe ser filtrada según el régimen

        Args:
            strategy_name: Nombre de la estrategia
            regime: Régimen actual (usa el último detectado si es None)

        Returns:
            (should_filter, reason) - True si debe bloquearse
        """
        # Usar régimen actual si no se especifica
        if regime is None:
            regime = self.detector.current_regime

        if regime is None:
            return False, None  # Sin régimen detectado, no filtrar

        # Verificar si la estrategia está mapeada
        if strategy_name not in self.strategy_regime_map:
            self.logger.warning(f"Strategy '{strategy_name}' not in regime map")
            return False, None  # No filtrar estrategias desconocidas

        strategy_config = self.strategy_regime_map[strategy_name]

        # Verificar compatibilidad de tipo de régimen
        if regime.trend_type not in strategy_config['compatible']:
            reason = (
                f"{strategy_name} incompatible with {regime.trend_type.value} "
                f"(requires {[r.value for r in strategy_config['compatible']]})"
            )
            return True, reason

        # Verificar fuerza mínima de tendencia
        min_strength = strategy_config.get('min_strength', 0)
        if regime.trend_strength < min_strength:
            reason = (
                f"{strategy_name} requires trend strength >= {min_strength} "
                f"(current: {regime.trend_strength:.1f})"
            )
            return True, reason

        # Verificar squeeze si es requerido
        if strategy_config.get('requires_squeeze', False):
            if not regime.is_squeeze:
                reason = f"{strategy_name} requires market squeeze (consolidation)"
                return True, reason

        # Estrategia compatible con régimen actual
        return False, None

    def get_compatible_strategies(
        self,
        strategies: list,
        regime: Optional[MarketRegime] = None
    ) -> Dict[str, bool]:
        """
        Obtiene lista de estrategias compatibles con el régimen

        Args:
            strategies: Lista de nombres de estrategias
            regime: Régimen actual (usa el último detectado si es None)

        Returns:
            Dict {strategy_name: is_compatible}
        """
        if regime is None:
            regime = self.detector.current_regime

        if regime is None:
            # Sin régimen, todas compatibles
            return {s: True for s in strategies}

        compatibility = {}
        for strategy in strategies:
            should_filter, _ = self.should_filter_strategy(strategy, regime)
            compatibility[strategy] = not should_filter

        return compatibility

    def get_recommended_strategies(
        self,
        regime: Optional[MarketRegime] = None
    ) -> list:
        """
        Obtiene lista de estrategias recomendadas para el régimen actual

        Args:
            regime: Régimen actual (usa el último detectado si es None)

        Returns:
            Lista de nombres de estrategias recomendadas
        """
        if regime is None:
            regime = self.detector.current_regime

        if regime is None:
            return []

        recommended = []

        for strategy_name, config in self.strategy_regime_map.items():
            # Verificar compatibilidad
            should_filter, _ = self.should_filter_strategy(strategy_name, regime)

            if not should_filter:
                recommended.append(strategy_name)

        return recommended

    def get_position_size_multiplier(
        self,
        regime: Optional[MarketRegime] = None,
        base_multiplier: float = 1.0
    ) -> float:
        """
        Calcula multiplicador de tamaño según volatilidad del régimen

        Args:
            regime: Régimen actual (usa el último detectado si es None)
            base_multiplier: Multiplicador base (default: 1.0)

        Returns:
            Multiplicador ajustado (0.5 - 1.25)
        """
        if regime is None:
            regime = self.detector.current_regime

        if regime is None:
            return base_multiplier

        # Ajustar según percentil de volatilidad
        vol_percentile = regime.volatility_percentile

        if vol_percentile < 20:
            # Volatilidad muy baja - aumentar tamaño
            multiplier = 1.25
        elif vol_percentile < 40:
            # Volatilidad baja - tamaño normal+
            multiplier = 1.1
        elif vol_percentile < 60:
            # Volatilidad normal
            multiplier = 1.0
        elif vol_percentile < 80:
            # Volatilidad alta - reducir tamaño
            multiplier = 0.75
        else:
            # Volatilidad muy alta - reducir significativamente
            multiplier = 0.5

        adjusted = base_multiplier * multiplier

        self.logger.debug(
            f"[REGIME] Size multiplier: {adjusted:.2f} "
            f"(vol percentile: {vol_percentile:.1f})"
        )

        return adjusted

    def get_regime_summary(
        self,
        regime: Optional[MarketRegime] = None
    ) -> Dict:
        """
        Obtiene resumen del régimen actual

        Args:
            regime: Régimen actual (usa el último detectado si es None)

        Returns:
            Dict con información del régimen
        """
        if regime is None:
            regime = self.detector.current_regime

        if regime is None:
            return {
                'detected': False,
                'message': 'No regime detected yet'
            }

        # Obtener estrategias recomendadas
        recommended = self.get_recommended_strategies(regime)

        # Calcular multiplicador de tamaño
        size_mult = self.get_position_size_multiplier(regime)

        summary = {
            'detected': True,
            'trend_type': regime.trend_type.value,
            'trend_strength': regime.trend_strength,
            'trend_slope': regime.trend_slope,
            'volatility_type': regime.volatility_type.value,
            'volatility_percentile': regime.volatility_percentile,
            'is_squeeze': regime.is_squeeze,
            'bb_width_percentile': regime.bb_width_percentile,
            'recommended_strategies': recommended,
            'position_size_multiplier': size_mult,
            'timestamp': regime.ts_updated
        }

        return summary

    def log_regime_status(self, regime: Optional[MarketRegime] = None):
        """
        Registra estado del régimen en logs

        Args:
            regime: Régimen actual (usa el último detectado si es None)
        """
        summary = self.get_regime_summary(regime)

        if not summary['detected']:
            self.logger.info("[REGIME] No regime detected")
            return

        self.logger.info(
            f"[REGIME] Market Status:\n"
            f"  Trend: {summary['trend_type']} "
            f"(strength: {summary['trend_strength']:.1f}, "
            f"slope: {summary['trend_slope']:.3f})\n"
            f"  Volatility: {summary['volatility_type']} "
            f"(percentile: {summary['volatility_percentile']:.1f})\n"
            f"  Squeeze: {'YES' if summary['is_squeeze'] else 'NO'} "
            f"(BB width: {summary['bb_width_percentile']:.1f})\n"
            f"  Recommended strategies: {', '.join(summary['recommended_strategies'])}\n"
            f"  Position size multiplier: {summary['position_size_multiplier']:.2f}x"
        )


def filter_signals_by_regime(
    signals: Dict,
    strategy_weights: Dict,
    regime_filter: RegimeFilter,
    df: pd.DataFrame,
    logger=None
) -> Dict:
    """
    Función helper para filtrar señales según régimen de mercado

    Args:
        signals: Dict con señales de cada estrategia
        strategy_weights: Dict con pesos de cada estrategia
        regime_filter: Instancia de RegimeFilter
        df: DataFrame con datos de mercado
        logger: Logger opcional

    Returns:
        Dict con señales filtradas y ajustadas
    """
    if logger is None:
        logger = logging.getLogger("filter_signals_by_regime")

    # Actualizar régimen
    regime = regime_filter.update(df)

    # Filtrar cada señal
    filtered_signals = {}
    blocked_count = 0

    for strategy_name, signal_data in signals.items():
        # Verificar si debe filtrarse
        should_filter, reason = regime_filter.should_filter_strategy(
            strategy_name, regime
        )

        if should_filter:
            # Bloquear señal
            logger.warning(f"[REGIME] {strategy_name} BLOCKED: {reason}")
            filtered_signals[strategy_name] = {
                'signal': 0,
                'confidence': 0,
                'blocked_by_regime': True,
                'reason': reason
            }
            blocked_count += 1
        else:
            # Permitir señal
            filtered_signals[strategy_name] = signal_data.copy()
            filtered_signals[strategy_name]['blocked_by_regime'] = False

    # Ajustar tamaño de posición por volatilidad
    size_multiplier = regime_filter.get_position_size_multiplier(regime)

    logger.info(
        f"[REGIME] Filtering complete: "
        f"{blocked_count}/{len(signals)} strategies blocked, "
        f"size multiplier: {size_multiplier:.2f}x"
    )

    return {
        'filtered_signals': filtered_signals,
        'regime': regime,
        'size_multiplier': size_multiplier,
        'blocked_count': blocked_count
    }
