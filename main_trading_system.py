#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main Trading System
Sistema de Trading Profesional con Arquitectura Completa

Características:
- Reconciliación al arranque con idempotencia de órdenes
- Circuit breakers automáticos
- Atribución por estrategia y régimen
- Pesos dinámicos por IC (EWMA)
- Detección de regímenes de mercado
- Journal completo con MAE/MFE
- Reportes semanales automáticos
- Sistema de alertas multi-canal
"""

import os
import sys
import logging
from datetime import datetime
from typing import Optional

# Componentes core
from core.event_bus import EventBus
from core.state_store import StateStore
from core.order_registry import OrderRegistry
from core.connection_manager import ConnectionManager
from core.circuit_breaker import CircuitBreakerManager
from core.regime_detector import RegimeDetector
from core.attribution_system import AttributionSystem
from core.ic_weighting import ICWeightingSystem

# Utilidades
from utils.alert_manager import AlertManager
from utils.report_generator import WeeklyReportGenerator
from utils.slippage_estimator import SlippageEstimator


class TradingSystem:
    """
    Sistema de Trading Completo

    Integra todos los componentes en un sistema cohesivo
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

        # Logger
        self.logger = self._setup_logging()

        # Componentes core
        self.event_bus = None
        self.state_store = None
        self.order_registry = None
        self.connection_manager = None
        self.circuit_breaker = None
        self.regime_detector = None
        self.attribution_system = None
        self.ic_weighting = None

        # Utilidades
        self.alert_manager = None
        self.report_generator = None
        self.slippage_estimator = None

        # Estado
        self.running = False

    def _setup_logging(self):
        """Configura el sistema de logging"""
        os.makedirs("logs", exist_ok=True)

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
            handlers=[
                logging.FileHandler(f"logs/trading_system_{datetime.now():%Y%m%d_%H%M%S}.log"),
                logging.StreamHandler()
            ]
        )

        return logging.getLogger("TradingSystem")

    def initialize(self):
        """Inicializa todos los componentes del sistema"""
        self.logger.info("=" * 80)
        self.logger.info("INITIALIZING TRADING SYSTEM")
        self.logger.info("=" * 80)
        self.logger.info(f"Profile: {self.risk_profile}")
        self.logger.info(f"Symbol: {self.symbol}")
        self.logger.info(f"Testnet: {self.testnet}")

        try:
            # 1. Event Bus
            self.logger.info("Starting Event Bus...")
            self.event_bus = EventBus()
            self.event_bus.start()

            # 2. State Store
            self.logger.info("Initializing State Store...")
            self.state_store = StateStore()

            # 3. Alert Manager
            self.logger.info("Initializing Alert Manager...")
            self.alert_manager = AlertManager()

            # 4. Order Registry
            self.logger.info("Initializing Order Registry...")
            self.order_registry = OrderRegistry(self.state_store, self.event_bus)

            # 5. Connection Manager
            self.logger.info("Initializing Connection Manager...")
            self.connection_manager = ConnectionManager(
                self.api_key,
                self.api_secret,
                self.testnet,
                self.state_store,
                self.event_bus,
                self.order_registry
            )

            # Conectar con Binance
            if not self.connection_manager.connect():
                raise Exception("Failed to connect to Binance")

            # Reconciliar estado al arranque
            self.logger.info("Performing startup reconciliation...")
            reconciliation_result = self.connection_manager.reconcile_on_startup(self.symbol)
            if not reconciliation_result.get('success'):
                self.logger.warning(f"Reconciliation warning: {reconciliation_result.get('error')}")
            else:
                self.logger.info(
                    f"Reconciliation complete: {reconciliation_result['open_positions']} positions, "
                    f"{reconciliation_result['open_orders']} orders"
                )

            # 6. Circuit Breaker
            self.logger.info("Initializing Circuit Breaker...")
            self.circuit_breaker = CircuitBreakerManager(
                self.state_store,
                self.event_bus,
                self.risk_profile,
                alert_callback=self.alert_manager.alert_critical
            )

            # Actualizar balance inicial
            balance = self.connection_manager.get_account_balance()
            self.circuit_breaker.update_balance(balance)
            self.logger.info(f"Account balance: ${balance:.2f}")

            # 7. Regime Detector
            self.logger.info("Initializing Regime Detector...")
            self.regime_detector = RegimeDetector(self.event_bus)

            # 8. Attribution System
            self.logger.info("Initializing Attribution System...")
            self.attribution_system = AttributionSystem(self.state_store, self.event_bus)

            # 9. IC Weighting System
            self.logger.info("Initializing IC Weighting System...")
            # Definir estrategias disponibles
            strategies = ['elliott', 'fibonacci', 'wyckoff', 'smc']
            self.ic_weighting = ICWeightingSystem(
                self.state_store,
                self.event_bus,
                strategies
            )

            # 10. Slippage Estimator
            self.logger.info("Initializing Slippage Estimator...")
            self.slippage_estimator = SlippageEstimator()

            # 11. Report Generator
            self.logger.info("Initializing Report Generator...")
            self.report_generator = WeeklyReportGenerator(
                self.state_store,
                self.attribution_system,
                self.alert_manager
            )

            self.running = True

            self.logger.info("=" * 80)
            self.logger.info("SYSTEM INITIALIZATION COMPLETE")
            self.logger.info("=" * 80)

            # Enviar alerta de inicio
            self.alert_manager.alert_info(
                f"🚀 Trading System Started\n"
                f"Profile: {self.risk_profile}\n"
                f"Symbol: {self.symbol}\n"
                f"Balance: ${balance:.2f}\n"
                f"Testnet: {self.testnet}"
            )

            return True

        except Exception as e:
            self.logger.error(f"Error during initialization: {e}", exc_info=True)
            self.shutdown()
            return False

    def shutdown(self):
        """Cierra el sistema limpiamente"""
        self.logger.info("Shutting down trading system...")

        self.running = False

        if self.event_bus:
            self.event_bus.stop()

        if self.connection_manager:
            self.connection_manager.disconnect()

        self.logger.info("System shutdown complete")

    def get_system_status(self) -> dict:
        """Retorna estado completo del sistema"""
        if not self.running:
            return {'status': 'stopped'}

        # Balance
        balance = self.connection_manager.get_account_balance()

        # Circuit breaker
        cb_status = self.circuit_breaker.get_status()

        # Regime
        regime_stats = self.regime_detector.get_stats() if self.regime_detector.current_regime else {}

        # IC weights
        ic_stats = self.ic_weighting.get_stats()

        # Order registry
        order_stats = self.order_registry.get_stats()

        # Attribution
        dashboard_data = self.attribution_system.get_dashboard_data()

        return {
            'status': 'running',
            'balance': balance,
            'circuit_breaker': cb_status,
            'regime': regime_stats,
            'ic_weighting': ic_stats,
            'orders': order_stats,
            'attribution': dashboard_data
        }

    def generate_weekly_report(self):
        """Genera reporte semanal"""
        if self.report_generator:
            return self.report_generator.generate_weekly_report()
        return None

    def manual_pause(self, reason: str = "Manual pause"):
        """Pausa manual del sistema"""
        if self.circuit_breaker:
            self.circuit_breaker.manual_pause(reason)
            self.logger.warning(f"System manually paused: {reason}")

    def manual_resume(self):
        """Reanudación manual del sistema"""
        if self.circuit_breaker:
            self.circuit_breaker.manual_resume()
            self.logger.info("System manually resumed")


def main():
    """Función principal para testing"""
    # Leer credenciales de variables de entorno
    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_SECRET_KEY", "")

    if not api_key or not api_secret:
        print("ERROR: Please set BINANCE_API_KEY and BINANCE_SECRET_KEY environment variables")
        sys.exit(1)

    # Crear sistema
    system = TradingSystem(
        api_key=api_key,
        api_secret=api_secret,
        testnet=True,
        risk_profile="normal",
        symbol="BTCUSDT"
    )

    # Inicializar
    if not system.initialize():
        print("Failed to initialize system")
        sys.exit(1)

    # Mostrar estado
    status = system.get_system_status()
    print("\n" + "=" * 80)
    print("SYSTEM STATUS")
    print("=" * 80)
    print(f"Status: {status['status']}")
    print(f"Balance: ${status['balance']:.2f}")
    print(f"Circuit Breaker: {status['circuit_breaker']['state']}")
    print(f"Open Orders: {status['orders']['active_orders']}")
    print("=" * 80)

    # El sistema está listo para operar
    # En producción, aquí comenzaría el loop principal de trading

    try:
        input("\nPress Enter to shutdown...\n")
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        system.shutdown()


if __name__ == "__main__":
    main()
