#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main Trading System - Entrypoint Único
Sistema de Trading Profesional con Arquitectura Completa

ENTRYPOINT ÚNICO del sistema de trading.
Todos los demás scripts deben invocar a esta API pública.

Características:
- Reconciliación al arranque con idempotencia de órdenes
- Circuit breakers automáticos
- Atribución por estrategia y régimen
- Pesos dinámicos por IC (EWMA)
- Detección de regímenes de mercado
- Journal completo con MAE/MFE
- Reportes semanales automáticos
- Sistema de alertas multi-canal
- Confluence engine para multi-estrategia
"""

import os
import sys
import logging
import time
import argparse
import numpy as np
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

# Cargar variables de entorno desde .env
from dotenv import load_dotenv

# Componentes core
from core.event_bus import EventBus
from core.state_store import StateStore
from core.order_registry import OrderRegistry
from core.connection_manager import ConnectionManager
from core.circuit_breaker import CircuitBreakerManager
from core.regime_detector import RegimeDetector
from core.attribution_system import AttributionSystem
from core.ic_weighting import ICWeightingSystem
from core.confluence_engine import ConfluenceEngine, StrategySignal

# Utilidades
from utils.alert_manager import AlertManager
from utils.report_generator import WeeklyReportGenerator
from utils.slippage_estimator import SlippageEstimator

# Estrategias
from strategies.smc_strategy import SMCStrategy


class TradingSystem:
    """
    Sistema de Trading Completo - API Pública

    Entrypoint único para inicialización, ejecución y control del bot.

    Métodos públicos:
    - initialize(): Conecta, reconcilia y prepara componentes
    - run(): Loop principal de trading
    - pause(): Pausa temporalmente
    - resume(): Reanuda tras pausa
    - shutdown(): Cierre limpio
    - get_system_status(): Estado completo del sistema
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = True,
        risk_profile: str = "normal",
        symbol: str = "BTCUSDT",
        leverage: int = 5,
        loop_interval: int = 60
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.risk_profile = risk_profile
        self.symbol = symbol
        self.leverage = leverage
        self.loop_interval = loop_interval  # Segundos entre evaluaciones

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
        self.confluence_engine = None

        # Estrategias
        self.strategies = {}

        # Utilidades
        self.alert_manager = None
        self.report_generator = None
        self.slippage_estimator = None

        # Estado
        self.running = False
        self.paused = False

    def _setup_logging(self):
        """Configura el sistema de logging"""
        os.makedirs("logs", exist_ok=True)

        log_level = os.getenv("LOG_LEVEL", "INFO").upper()

        logging.basicConfig(
            level=getattr(logging, log_level, logging.INFO),
            format='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
            handlers=[
                logging.FileHandler(f"logs/trading_system_{datetime.now():%Y%m%d_%H%M%S}.log"),
                logging.StreamHandler()
            ]
        )

        return logging.getLogger("TradingSystem")

    def initialize(self):
        """
        Inicializa todos los componentes del sistema de forma idempotente

        Orden de inicialización:
        1. Event Bus
        2. State Store (SQLite local)
        3. Alert Manager
        4. Order Registry
        5. Connection Manager + reconciliación
        6. Circuit Breaker
        7. Regime Detector
        8. Attribution System
        9. IC Weighting
        10. Confluence Engine
        11. Estrategias
        12. Slippage Estimator
        13. Report Generator

        Returns:
            bool: True si inicialización exitosa, False en caso contrario
        """
        self.logger.info("=" * 80)
        self.logger.info("INITIALIZING TRADING SYSTEM")
        self.logger.info("=" * 80)
        self.logger.info(f"Profile: {self.risk_profile}")
        self.logger.info(f"Symbol: {self.symbol}")
        self.logger.info(f"Testnet: {self.testnet}")
        self.logger.info(f"Leverage: {self.leverage}")

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
            self.logger.info("Connecting to Binance...")
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
            strategy_names = ['smc']  # Por ahora solo SMC implementada
            self.ic_weighting = ICWeightingSystem(
                self.state_store,
                self.event_bus,
                strategy_names
            )

            # 10. Confluence Engine
            self.logger.info("Initializing Confluence Engine...")
            min_strategies = int(os.getenv("MIN_STRATEGIES_FOR_CONFLUENCE", "1"))
            min_confidence = float(os.getenv("MIN_CONFIDENCE_FOR_ENTRY", "0.5"))

            self.confluence_engine = ConfluenceEngine(
                min_strategies=min_strategies,
                min_confidence=min_confidence,
                weights=self.ic_weighting.get_all_weights()
            )

            # 11. Estrategias
            self.logger.info("Initializing Strategies...")
            self.strategies['smc'] = SMCStrategy(swing_length=10, fvg_threshold=0.001)
            self.logger.info(f"Loaded {len(self.strategies)} strategies")

            # 12. Slippage Estimator
            self.logger.info("Initializing Slippage Estimator...")
            self.slippage_estimator = SlippageEstimator()

            # 13. Report Generator
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
                f"Trading System Started\n"
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

    def run(self, max_iterations: Optional[int] = None):
        """
        Loop principal de trading

        Ejecuta el ciclo de decisiones de forma determinística:
        1. Verificar circuit breaker
        2. Obtener datos de mercado
        3. Detectar régimen
        4. Evaluar estrategias
        5. Agregar señales con confluence
        6. Tomar decisiones de trading
        7. Esperar próxima iteración

        Args:
            max_iterations: Máximo de iteraciones (None = infinito, para testing usar valor finito)
        """
        if not self.running:
            self.logger.error("System not initialized. Call initialize() first.")
            return

        self.logger.info("=" * 80)
        self.logger.info("STARTING TRADING LOOP")
        self.logger.info("=" * 80)
        self.logger.info(f"Loop interval: {self.loop_interval}s")
        self.logger.info(f"Max iterations: {max_iterations if max_iterations else 'unlimited'}")

        iteration = 0

        try:
            while self.running:
                if max_iterations and iteration >= max_iterations:
                    self.logger.info(f"Reached max iterations ({max_iterations}). Exiting loop.")
                    break

                iteration += 1
                self.logger.info(f"\n--- Iteration {iteration} ---")

                # Verificar si está pausado
                if self.paused:
                    self.logger.info("System is paused. Waiting...")
                    time.sleep(5)
                    continue

                # 1. Verificar circuit breaker
                can_trade, reason = self.circuit_breaker.can_trade()
                if not can_trade:
                    self.logger.warning(f"Trading blocked by circuit breaker: {reason}")
                    time.sleep(self.loop_interval)
                    continue

                # 2. Obtener datos de mercado
                market_data = self._get_market_data()
                if not market_data:
                    self.logger.warning("Failed to get market data. Skipping iteration.")
                    time.sleep(self.loop_interval)
                    continue

                # 3. Detectar régimen
                regime = self._detect_regime(market_data)
                if regime:
                    self.logger.info(
                        f"Regime: {regime.trend_type.value}, "
                        f"ADX: {regime.trend_strength:.1f}, "
                        f"Volatility: {regime.volatility_percentile:.0f}%ile"
                    )

                # 4. Evaluar estrategias
                signals = self._evaluate_strategies(market_data)

                # 5. Agregar señales con confluence
                decision = self.confluence_engine.evaluate(signals)

                self.logger.info(
                    f"Confluence Decision: {decision.signal.name} "
                    f"(confidence: {decision.confidence:.2%}, "
                    f"valid strategies: {decision.num_strategies_valid}/{decision.num_strategies_total})"
                )

                for reason in decision.reasons:
                    self.logger.info(f"  - {reason}")

                # 6. Tomar decisión de trading
                if decision.should_trade():
                    self.logger.info(f"Signal detected: {decision.signal.name}")
                    # TODO: Implementar lógica de ejecución de órdenes
                    # Por ahora solo log
                else:
                    self.logger.info("No trade signal. Waiting for next iteration.")

                # 7. Esperar próxima iteración
                time.sleep(self.loop_interval)

        except KeyboardInterrupt:
            self.logger.info("KeyboardInterrupt received. Shutting down...")
        except Exception as e:
            self.logger.error(f"Error in trading loop: {e}", exc_info=True)
        finally:
            self.logger.info("Trading loop ended")

    def _get_market_data(self) -> Optional[Dict[str, Any]]:
        """
        Obtiene datos de mercado del exchange

        Returns:
            Dict con closes, highs, lows, opens, volumes
        """
        try:
            # Obtener klines recientes (última 100 velas de 1h)
            klines = self.connection_manager.client.futures_klines(
                symbol=self.symbol,
                interval='1h',
                limit=100
            )

            if not klines:
                return None

            # Convertir a numpy arrays
            closes = np.array([float(k[4]) for k in klines])
            highs = np.array([float(k[2]) for k in klines])
            lows = np.array([float(k[3]) for k in klines])
            opens = np.array([float(k[1]) for k in klines])
            volumes = np.array([float(k[5]) for k in klines])

            return {
                'closes': closes,
                'highs': highs,
                'lows': lows,
                'opens': opens,
                'volumes': volumes,
                'timestamp': datetime.now()
            }

        except Exception as e:
            self.logger.error(f"Error getting market data: {e}")
            return None

    def _detect_regime(self, market_data: Dict[str, Any]):
        """Detecta el régimen de mercado"""
        try:
            regime = self.regime_detector.detect_regime(
                closes=market_data['closes'],
                highs=market_data['highs'],
                lows=market_data['lows'],
                lookback=100
            )
            return regime
        except Exception as e:
            self.logger.error(f"Error detecting regime: {e}", exc_info=True)
            return None

    def _evaluate_strategies(self, market_data: Dict[str, Any]) -> List[StrategySignal]:
        """
        Evalúa todas las estrategias con los datos de mercado

        Returns:
            Lista de StrategySignal
        """
        signals = []

        for name, strategy in self.strategies.items():
            try:
                signal = strategy.analyze(
                    closes=market_data['closes'],
                    highs=market_data['highs'],
                    lows=market_data['lows'],
                    opens=market_data['opens'],
                    volumes=market_data.get('volumes')
                )
                signals.append(signal)

                self.logger.debug(
                    f"Strategy '{name}': signal={signal.signal}, "
                    f"confidence={signal.confidence:.2%}, "
                    f"reasons={signal.reasons[:2]}"
                )

            except Exception as e:
                self.logger.error(f"Error evaluating strategy '{name}': {e}", exc_info=True)
                # En caso de error, añadir señal neutra
                signals.append(StrategySignal(
                    name=name,
                    signal=0,
                    confidence=0.0,
                    reasons=[f"Error: {str(e)}"]
                ))

        return signals

    def pause(self):
        """Pausa el sistema temporalmente (idempotente)"""
        if not self.paused:
            self.paused = True
            self.logger.warning("System paused")
            self.alert_manager.alert_warning("System paused")

    def resume(self):
        """Reanuda el sistema tras pausa (idempotente)"""
        if self.paused:
            self.paused = False
            self.logger.info("System resumed")
            self.alert_manager.alert_info("System resumed")

    def shutdown(self):
        """
        Cierra el sistema limpiamente

        Pasos:
        1. Marcar como no running
        2. Drenar event bus
        3. Cerrar conexiones
        4. Guardar snapshot de estado
        5. Emitir reporte final
        """
        self.logger.info("=" * 80)
        self.logger.info("SHUTTING DOWN TRADING SYSTEM")
        self.logger.info("=" * 80)

        self.running = False

        try:
            # Drenar event bus
            if self.event_bus:
                self.logger.info("Stopping Event Bus...")
                self.event_bus.stop()

            # Cerrar conexiones
            if self.connection_manager:
                self.logger.info("Disconnecting from Binance...")
                self.connection_manager.disconnect()

            # Guardar snapshot de estado
            if self.state_store:
                self.logger.info("Saving state snapshot...")
                # StateStore se cierra automáticamente con el contexto

            # Emitir alerta de cierre
            if self.alert_manager:
                self.alert_manager.alert_info("Trading System Shutdown Complete")

            self.logger.info("=" * 80)
            self.logger.info("SHUTDOWN COMPLETE")
            self.logger.info("=" * 80)

        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}", exc_info=True)

    def get_system_status(self) -> Dict[str, Any]:
        """
        Retorna estado completo del sistema

        Returns:
            Dict con status, balance, circuit_breaker, regime, ic_weighting, orders, attribution
        """
        if not self.running:
            return {'status': 'stopped'}

        try:
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
                'status': 'running' if not self.paused else 'paused',
                'balance': balance,
                'circuit_breaker': cb_status,
                'regime': regime_stats,
                'ic_weighting': ic_stats,
                'orders': order_stats,
                'attribution': dashboard_data,
                'event_bus_stats': self.event_bus.get_stats()
            }

        except Exception as e:
            self.logger.error(f"Error getting system status: {e}", exc_info=True)
            return {'status': 'error', 'error': str(e)}

    def generate_weekly_report(self):
        """Genera reporte semanal"""
        if self.report_generator:
            return self.report_generator.generate_weekly_report()
        return None

    def manual_pause(self, reason: str = "Manual pause"):
        """Pausa manual del sistema con circuit breaker"""
        if self.circuit_breaker:
            self.circuit_breaker.manual_pause(reason)
            self.logger.warning(f"System manually paused: {reason}")

    def manual_resume(self):
        """Reanudación manual del sistema"""
        if self.circuit_breaker:
            self.circuit_breaker.manual_resume()
            self.logger.info("System manually resumed")


def load_config_from_env() -> Dict[str, Any]:
    """
    Carga configuración desde variables de entorno

    Prioridad: CLI args > env vars > .env > defaults

    Returns:
        Dict con configuración
    """
    # Cargar .env si existe
    env_path = Path('.env')
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✓ Loaded configuration from {env_path}")
    else:
        print(f"⚠ Warning: {env_path} not found. Using environment variables and defaults.")

    config = {
        'api_key': os.getenv('BINANCE_API_KEY', ''),
        'api_secret': os.getenv('BINANCE_SECRET_KEY', ''),
        'testnet': os.getenv('TESTNET', 'true').lower() == 'true',
        'risk_profile': os.getenv('RISK_PROFILE', 'normal'),
        'symbol': os.getenv('SYMBOL', 'BTCUSDT'),
        'leverage': int(os.getenv('LEVERAGE', '5')),
        'loop_interval': int(os.getenv('LOOP_INTERVAL', '60'))
    }

    # Validar credenciales
    if not config['api_key'] or not config['api_secret']:
        print("\n" + "=" * 80)
        print("❌ ERROR: Binance API credentials not found")
        print("=" * 80)
        print("\nPlease set the following environment variables:")
        print("  - BINANCE_API_KEY")
        print("  - BINANCE_SECRET_KEY")
        print("\nOr create a .env file from .env.example:")
        print("  cp .env.example .env")
        print("  # Edit .env with your credentials")
        print("=" * 80)
        sys.exit(1)

    return config


def main():
    """
    Función principal - CLI entrypoint

    Soporta argumentos de línea de comandos que sobrescriben .env
    """
    parser = argparse.ArgumentParser(
        description='Binance Futures Trading Bot',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--testnet', action='store_true', help='Use Binance Testnet')
    parser.add_argument('--mainnet', action='store_true', help='Use Binance Mainnet')
    parser.add_argument('--symbol', type=str, help='Trading symbol (e.g., BTCUSDT)')
    parser.add_argument('--profile', type=str, choices=['conservador', 'normal', 'agresivo'],
                        help='Risk profile')
    parser.add_argument('--iterations', type=int, help='Max iterations (for testing)')

    args = parser.parse_args()

    # Cargar configuración base desde .env
    config = load_config_from_env()

    # Sobrescribir con argumentos CLI si se proporcionan
    if args.testnet:
        config['testnet'] = True
    if args.mainnet:
        config['testnet'] = False
    if args.symbol:
        config['symbol'] = args.symbol
    if args.profile:
        config['risk_profile'] = args.profile

    # Mostrar configuración
    print("\n" + "=" * 80)
    print("TRADING BOT CONFIGURATION")
    print("=" * 80)
    print(f"Testnet: {config['testnet']}")
    print(f"Symbol: {config['symbol']}")
    print(f"Risk Profile: {config['risk_profile']}")
    print(f"Leverage: {config['leverage']}x")
    print(f"Loop Interval: {config['loop_interval']}s")
    print("=" * 80 + "\n")

    # Crear sistema
    system = TradingSystem(
        api_key=config['api_key'],
        api_secret=config['api_secret'],
        testnet=config['testnet'],
        risk_profile=config['risk_profile'],
        symbol=config['symbol'],
        leverage=config['leverage'],
        loop_interval=config['loop_interval']
    )

    # Inicializar
    if not system.initialize():
        print("❌ Failed to initialize system")
        sys.exit(1)

    # Mostrar estado inicial
    status = system.get_system_status()
    print("\n" + "=" * 80)
    print("SYSTEM STATUS")
    print("=" * 80)
    print(f"Status: {status['status']}")
    print(f"Balance: ${status['balance']:.2f}")
    print(f"Circuit Breaker: {status['circuit_breaker']['state']}")
    print(f"Open Orders: {status['orders']['active_orders']}")
    print("=" * 80 + "\n")

    # Ejecutar loop de trading
    try:
        system.run(max_iterations=args.iterations)
    except KeyboardInterrupt:
        print("\n⚠ KeyboardInterrupt received")
    finally:
        print("\n🛑 Shutting down...")
        system.shutdown()
        print("✓ Shutdown complete\n")


if __name__ == "__main__":
    main()
