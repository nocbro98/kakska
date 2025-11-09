"""
Integration Bridge
Puente de integración entre binance_bot_2.py (legacy) y la arquitectura modular 3.0

Este módulo permite usar los componentes modernos (ConnectionManager, CircuitBreaker,
RegimeDetector, etc.) desde el bot existente sin romper la compatibilidad.
"""

import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime

# Componentes modulares 3.0
from core.event_bus import EventBus, EventType
from core.state_store import StateStore
from core.connection_manager import ConnectionManager
from core.order_registry import OrderRegistry
from core.circuit_breaker import CircuitBreakerManager
from core.regime_detector import RegimeDetector
from core.attribution_system import AttributionSystem
from core.ic_weighting import ICWeightingSystem

# Utilidades
from utils.active_alerts import ActiveAlertManager, AlertLevel


class ModernComponentsBridge:
    """
    Puente que inyecta componentes modernos en el bot legacy

    Permite usar:
    - ConnectionManager para reconciliación
    - CircuitBreakerManager para pausas inteligentes
    - RegimeDetector para filtrado de señales
    - AlertManager para notificaciones
    - AttributionSystem para métricas avanzadas
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = True,
        risk_profile: str = "normal",
        symbol: str = "BTCUSDT"
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.risk_profile = risk_profile
        self.symbol = symbol

        self.logger = logging.getLogger("ModernBridge")

        # Componentes core
        self.event_bus: Optional[EventBus] = None
        self.state_store: Optional[StateStore] = None
        self.order_registry: Optional[OrderRegistry] = None
        self.connection_manager: Optional[ConnectionManager] = None
        self.circuit_breaker: Optional[CircuitBreakerManager] = None
        self.regime_detector: Optional[RegimeDetector] = None
        self.attribution_system: Optional[AttributionSystem] = None
        self.ic_weighting: Optional[ICWeightingSystem] = None
        self.alert_manager: Optional[ActiveAlertManager] = None

        self.initialized = False

    def initialize(self) -> bool:
        """
        Inicializa todos los componentes modernos

        Returns:
            True si la inicialización fue exitosa
        """
        try:
            self.logger.info("Initializing modern components bridge...")

            # 1. Event Bus
            self.event_bus = EventBus()
            self.event_bus.start()
            self.logger.info("✓ EventBus started")

            # 2. State Store
            self.state_store = StateStore()
            self.logger.info("✓ StateStore initialized")

            # 3. Active Alert Manager (with Telegram/Discord/Email)
            self.alert_manager = ActiveAlertManager()
            # ActiveAlertManager auto-configures from environment variables
            alert_status = self.alert_manager.get_status()
            self.logger.info(f"✓ ActiveAlertManager initialized: {alert_status}")

            # 4. Order Registry
            self.order_registry = OrderRegistry(self.state_store, self.event_bus)
            self.logger.info("✓ OrderRegistry initialized")

            # 5. Connection Manager
            self.connection_manager = ConnectionManager(
                self.api_key,
                self.api_secret,
                self.testnet,
                self.state_store,
                self.event_bus,
                self.order_registry
            )

            # Conectar y reconciliar
            if not self.connection_manager.connect():
                raise Exception("Failed to connect to Binance")

            self.logger.info("✓ ConnectionManager connected")

            # Reconciliar estado al arranque
            reconciliation = self.connection_manager.reconcile_on_startup(self.symbol)
            if reconciliation.get('success'):
                self.logger.info(
                    f"✓ Reconciliation complete: {reconciliation['open_positions']} positions, "
                    f"{reconciliation['open_orders']} orders"
                )
            else:
                self.logger.warning(f"Reconciliation warning: {reconciliation.get('error')}")

            # 6. Circuit Breaker
            self.circuit_breaker = CircuitBreakerManager(
                self.state_store,
                self.event_bus,
                self.risk_profile,
                alert_callback=self.alert_manager.alert_critical
            )

            # Actualizar balance inicial
            balance = self.connection_manager.get_account_balance()
            self.circuit_breaker.update_balance(balance)
            self.logger.info(f"✓ CircuitBreaker initialized (balance: ${balance:.2f})")

            # 7. Regime Detector
            self.regime_detector = RegimeDetector(self.event_bus)
            self.logger.info("✓ RegimeDetector initialized")

            # 8. Attribution System
            self.attribution_system = AttributionSystem(self.state_store, self.event_bus)
            self.logger.info("✓ AttributionSystem initialized")

            # 9. IC Weighting
            strategies = ['elliott', 'fibonacci', 'wyckoff', 'smc']
            self.ic_weighting = ICWeightingSystem(
                self.state_store,
                self.event_bus,
                strategies
            )
            self.logger.info("✓ ICWeighting initialized")

            self.initialized = True
            self.logger.info("=" * 60)
            self.logger.info("✅ Modern components bridge initialized successfully")
            self.logger.info("=" * 60)

            # Enviar alerta de inicio
            self.alert_manager.alert_info(
                f"🚀 Modern Components Initialized\n"
                f"Profile: {self.risk_profile}\n"
                f"Symbol: {self.symbol}\n"
                f"Balance: ${balance:.2f}"
            )

            return True

        except Exception as e:
            self.logger.error(f"Error initializing modern components: {e}", exc_info=True)
            self.shutdown()
            return False


    def can_trade(self) -> tuple[bool, Optional[str]]:
        """
        Verifica si se puede operar (circuit breakers)

        Returns:
            (can_trade, reason_if_blocked)
        """
        if not self.initialized or not self.circuit_breaker:
            return True, None

        return self.circuit_breaker.can_trade()

    def should_filter_signal_by_regime(self, strategy_type: str) -> tuple[bool, Optional[str]]:
        """
        Verifica si una señal debe ser filtrada por régimen de mercado

        Args:
            strategy_type: Tipo de estrategia (elliott, fibonacci, wyckoff, smc)

        Returns:
            (should_filter, reason_if_filtered)
        """
        if not self.initialized or not self.regime_detector:
            return False, None

        if not self.regime_detector.current_regime:
            return False, None  # Sin régimen detectado, permitir

        # Verificar si el régimen permite esta estrategia
        allowed, reason = self.regime_detector.allows_strategy(strategy_type)

        return not allowed, reason  # Invertir: True si debe filtrar

    def get_regime_size_adjustment(self) -> float:
        """
        Obtiene factor de ajuste de tamaño según volatilidad

        Returns:
            Factor multiplicador (0.5-1.25)
        """
        if not self.initialized or not self.regime_detector:
            return 1.0

        return self.regime_detector.get_size_adjustment()

    def update_regime(self, df):
        """Actualiza detección de régimen con nuevos datos"""
        if self.initialized and self.regime_detector:
            self.regime_detector.detect_regime(df)

    def get_ic_weights(self) -> Dict[str, float]:
        """Obtiene pesos actuales de estrategias por IC"""
        if not self.initialized or not self.ic_weighting:
            # Pesos iguales por defecto
            return {
                'elliott': 0.25,
                'fibonacci': 0.25,
                'wyckoff': 0.25,
                'smc': 0.25
            }

        return self.ic_weighting.get_all_weights()

    def rebalance_ic_weights(self) -> Dict[str, float]:
        """Rebalancea pesos por IC si es necesario"""
        if self.initialized and self.ic_weighting:
            if self.ic_weighting.should_rebalance():
                return self.ic_weighting.rebalance_weights(force=True)

        return self.get_ic_weights()

    def on_trade_completed(self, trade_data: Dict[str, Any]):
        """
        Callback cuando se completa un trade

        Args:
            trade_data: Datos del trade completado
        """
        if not self.initialized:
            return

        # Emitir evento
        self.event_bus.publish(
            EventType.TRADE_COMPLETED,
            data=trade_data,
            source="LegacyBot"
        )

        # Actualizar circuit breaker
        pnl = trade_data.get('pnl_usdt', 0)
        is_win = pnl > 0
        self.circuit_breaker.risk_metrics.add_trade_result(pnl, is_win)

        # Verificar si se activa circuit breaker
        should_trigger, reason = self.circuit_breaker.risk_metrics.check_circuit_breakers()
        if should_trigger and self.circuit_breaker.risk_metrics.cb_state.value != "RUNNING":
            self.logger.critical(f"🚨 CIRCUIT BREAKER TRIGGERED: {reason}")
            self.alert_manager.alert_critical(
                f"⚠️ CIRCUIT BREAKER ACTIVADO\n{reason}"
            )

    def get_status(self) -> Dict[str, Any]:
        """Obtiene estado de todos los componentes"""
        if not self.initialized:
            return {'initialized': False}

        return {
            'initialized': True,
            'circuit_breaker': self.circuit_breaker.get_status() if self.circuit_breaker else {},
            'regime': self.regime_detector.get_stats() if self.regime_detector else {},
            'ic_weights': self.get_ic_weights(),
            'balance': self.connection_manager.get_account_balance() if self.connection_manager else 0
        }

    def shutdown(self):
        """Cierra todos los componentes"""
        self.logger.info("Shutting down modern components bridge...")

        if self.event_bus:
            self.event_bus.stop()

        if self.connection_manager:
            self.connection_manager.disconnect()

        self.initialized = False
        self.logger.info("Modern components bridge shut down")


# Función helper para crear el bridge desde Config
def create_bridge_from_config(config_class) -> ModernComponentsBridge:
    """
    Crea un ModernComponentsBridge desde una clase Config legacy

    Args:
        config_class: Clase Config de binance_bot_2.py

    Returns:
        ModernComponentsBridge inicializado
    """
    bridge = ModernComponentsBridge(
        api_key=config_class.API_KEY,
        api_secret=config_class.SECRET_KEY,
        testnet=config_class.USE_TESTNET,
        risk_profile=config_class.DEFAULT_RISK_PROFILE.value,
        symbol=config_class.SYMBOL
    )

    return bridge
