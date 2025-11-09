#!/usr/bin/env python3
"""
Run Integrated Bot
Script para ejecutar el bot con TODOS los componentes modernos integrados

Este wrapper envuelve binance_bot_2.py existente e inyecta todos los
componentes de la arquitectura 3.0 sin modificar el código original.

Usage:
    python run_integrated_bot.py
    python run_integrated_bot.py --gui
    python run_integrated_bot.py --config aggressive
"""

import sys
import os
import argparse
import logging
import time
from datetime import datetime
import threading

# Importar bot existente
from binance_bot_2 import TradingBot, TradingBotGUI, Config

# Importar componentes modernos
from integration_bridge import ModernComponentsBridge
from utils.robust_order_executor import RobustOrderExecutor
from utils.pyramiding_manager import PyramidingManager
from utils.regime_filter import RegimeFilter
from gui.modern_trading_gui import ModernTradingGUI
from config_loader import load_config


class IntegratedTradingBot:
    """
    Wrapper que integra todos los componentes modernos con el bot existente
    """

    def __init__(self, use_modern_gui=False):
        """
        Args:
            use_modern_gui: Usar GUI moderna en lugar de legacy
        """
        self.use_modern_gui = use_modern_gui
        self.legacy_bot = None
        self.modern_bridge = None
        self.regime_filter = None
        self.pyramiding_manager = None

        print("=" * 70)
        print("TRADING BOT - Arquitectura 3.0 Integrada")
        print("=" * 70)

    def initialize(self):
        """Inicializar todos los componentes"""

        print("\n[1/5] Inicializando bot legacy...")

        # Crear bot legacy
        self.legacy_bot = TradingBot()

        print("[2/5] Inicializando ModernComponentsBridge...")

        # Modern Components Bridge
        try:
            self.modern_bridge = ModernComponentsBridge(
                api_key=Config.API_KEY,
                api_secret=Config.SECRET_KEY,
                testnet=Config.USE_TESTNET,
                risk_profile='normal',
                symbol=Config.SYMBOL
            )

            if self.modern_bridge.initialize():
                print("  ✓ ModernComponentsBridge inicializado")
                print(f"  ✓ Reconciliación completada")

                # Conectar alert manager con logger
                if hasattr(self.legacy_bot, 'logger_system') and self.modern_bridge.alert_manager:
                    self.legacy_bot.logger_system.alert_manager = self.modern_bridge.alert_manager

            else:
                print("  ⚠️ ModernComponentsBridge falló")
                self.modern_bridge = None

        except Exception as e:
            print(f"  ❌ Error: {e}")
            self.modern_bridge = None

        print("[3/5] Inicializando RegimeFilter...")

        # Regime Filter
        try:
            self.regime_filter = RegimeFilter()
            print("  ✓ RegimeFilter inicializado")

            # Conectar con trader
            if hasattr(self.legacy_bot, 'trader'):
                self.legacy_bot.trader.regime_filter = self.regime_filter

        except Exception as e:
            print(f"  ❌ Error: {e}")
            self.regime_filter = None

        print("[4/5] Inicializando Pyramiding Manager...")

        # Pyramiding Manager
        if hasattr(Config, 'ALLOW_PYRAMIDING') and Config.ALLOW_PYRAMIDING:
            try:
                self.pyramiding_manager = PyramidingManager(
                    max_adds=getattr(Config, 'PYRAMID_MAX_ADDS', 2),
                    min_profit_pct=getattr(Config, 'PYRAMID_MIN_PROFIT_PCT', 1.0),
                    size_reduction_factor=getattr(Config, 'PYRAMID_SIZE_REDUCTION', 0.5)
                )
                print(f"  ✓ PyramidingManager inicializado (max {self.pyramiding_manager.max_adds} adds)")

            except Exception as e:
                print(f"  ❌ Error: {e}")
                self.pyramiding_manager = None
        else:
            print("  ⊘ Pyramiding deshabilitado (ALLOW_PYRAMIDING=False)")

        print("[5/5] Integrando RobustOrderExecutor...")

        # RobustOrderExecutor
        try:
            self.legacy_bot.order_manager.robust_executor = RobustOrderExecutor(
                client=self.legacy_bot.client,
                symbol=Config.SYMBOL,
                logger=self.legacy_bot.logger_system
            )
            print("  ✓ RobustOrderExecutor integrado en OrderManager")

        except Exception as e:
            print(f"  ❌ Error: {e}")

        # Conectar componentes
        self.legacy_bot.modern_bridge = self.modern_bridge
        self.legacy_bot.regime_filter = self.regime_filter
        self.legacy_bot.pyramiding_manager = self.pyramiding_manager

        # Patch trading loop
        self._patch_trading_loop()

        print("\n" + "=" * 70)
        print("✅ SISTEMA COMPLETAMENTE INTEGRADO")
        print("=" * 70)
        print(f"  Symbol: {Config.SYMBOL}")
        print(f"  Timeframe: {Config.TIMEFRAME}")
        print(f"  Mode: {'TESTNET' if Config.USE_TESTNET else 'PRODUCCIÓN'}")
        print(f"  Circuit Breakers: {'ON' if self.modern_bridge else 'OFF'}")
        print(f"  Regime Filter: {'ON' if self.regime_filter else 'OFF'}")
        print(f"  Pyramiding: {'ON' if self.pyramiding_manager else 'OFF'}")
        print(f"  Alerts: {self._get_alert_status()}")
        print("=" * 70 + "\n")

        return True

    def _get_alert_status(self):
        """Obtener status de alertas"""
        if not self.modern_bridge or not self.modern_bridge.alert_manager:
            return "OFF"

        status = self.modern_bridge.alert_manager.get_status()
        channels = []
        if status.get('telegram'):
            channels.append("Telegram")
        if status.get('discord'):
            channels.append("Discord")
        if status.get('email'):
            channels.append("Email")

        return ", ".join(channels) if channels else "Configured but no channels"

    def _patch_trading_loop(self):
        """Patch el trading loop del bot para agregar funcionalidad moderna"""

        # Guardar referencia al loop original
        original_trading_loop = self.legacy_bot.trading_loop

        def patched_trading_loop():
            """Trading loop con componentes modernos integrados"""

            self.legacy_bot.logger.info("Starting trading loop (patched with modern components)...")

            while not self.legacy_bot.stop_event.is_set():
                try:
                    # ===== CIRCUIT BREAKER CHECK =====
                    if self.modern_bridge:
                        can_trade, reason = self.modern_bridge.can_trade()
                        if not can_trade:
                            self.legacy_bot.logger.warning(f"⛔ Trading pausado: {reason}")
                            time.sleep(60)
                            continue

                    # ===== RÉGIMEN UPDATE (cada 5 minutos) =====
                    if self.regime_filter and hasattr(self, '_last_regime_update'):
                        if (time.time() - self._last_regime_update) > 300:
                            try:
                                with self.legacy_bot.market_data_lock:
                                    if len(self.legacy_bot.market_data) > 0:
                                        regime = self.regime_filter.update(
                                            self.legacy_bot.market_data.copy()
                                        )
                                        self.regime_filter.log_regime_status(regime)
                                self._last_regime_update = time.time()
                            except:
                                pass
                    elif self.regime_filter:
                        self._last_regime_update = time.time()

                    # ===== PYRAMIDING CHECK =====
                    if (self.pyramiding_manager and
                        self.legacy_bot.order_manager.current_position_data and
                        hasattr(Config, 'ALLOW_PYRAMIDING') and Config.ALLOW_PYRAMIDING):

                        try:
                            with self.legacy_bot.market_data_lock:
                                if len(self.legacy_bot.market_data) > 0:
                                    current_price = float(self.legacy_bot.market_data['close'].iloc[-1])
                                    df_copy = self.legacy_bot.market_data.copy()

                            # Verificar si se puede piramidear
                            can_add, _ = self.pyramiding_manager.can_add_to_position(
                                Config.SYMBOL, current_price
                            )

                            if can_add and len(df_copy) >= 100:
                                # Analizar señal
                                signals = self.legacy_bot.trader.analyze_market(df_copy, current_price)

                                position_side = self.legacy_bot.order_manager.current_position_data['side']

                                should_add = False
                                if position_side == 'BUY' and signals and signals.get('signal') == 1:
                                    if signals.get('confidence', 0) >= 60:
                                        should_add = True
                                elif position_side == 'SELL' and signals and signals.get('signal') == -1:
                                    if signals.get('confidence', 0) >= 60:
                                        should_add = True

                                if should_add:
                                    self._execute_pyramiding(current_price)

                        except Exception as e:
                            self.legacy_bot.logger.error(f"Error en pyramiding: {e}")

                    # Delay entre iteraciones
                    time.sleep(1)

                except Exception as e:
                    self.legacy_bot.logger.error(f"Error in trading loop: {e}", exc_info=True)
                    time.sleep(5)

            self.legacy_bot.logger.info("Trading loop terminated")

        # Reemplazar el loop
        self.legacy_bot.trading_loop = patched_trading_loop

    def _execute_pyramiding(self, current_price: float):
        """Ejecutar piramidación"""

        try:
            symbol = Config.SYMBOL
            position_side = self.legacy_bot.order_manager.current_position_data['side']

            # Calcular tamaño
            add_size = self.pyramiding_manager.calculate_add_size(symbol)

            # Ajustar precisión
            if self.legacy_bot.precision_manager:
                add_size = self.legacy_bot.precision_manager.round_quantity(add_size)

            self.legacy_bot.logger.info(f"[PYRAMID] Adding {add_size} @ {current_price}")

            # Ejecutar orden
            add_order = self.legacy_bot.client.futures_create_order(
                symbol=symbol,
                side=position_side,
                type='MARKET',
                quantity=add_size
            )

            # Registrar
            self.pyramiding_manager.record_add(symbol, current_price, add_size)

            # Calcular nuevo SL (breakeven)
            with self.legacy_bot.market_data_lock:
                if 'atr' in self.legacy_bot.market_data.columns:
                    atr = self.legacy_bot.market_data['atr'].iloc[-1]
                else:
                    atr = current_price * 0.01

            new_sl = self.pyramiding_manager.calculate_new_stop_loss(
                symbol, current_price, atr
            )

            # Actualizar SL
            if hasattr(self.legacy_bot.order_manager, 'robust_executor'):
                current_qty = self.legacy_bot.order_manager.current_position_data['quantity']
                success = self.legacy_bot.order_manager.robust_executor.update_stop_loss(
                    side=position_side,
                    quantity=current_qty + add_size,
                    new_stop_price=new_sl,
                    old_sl_order_id=self.legacy_bot.order_manager.current_position_data.get('sl_order_id')
                )

                if success:
                    self.legacy_bot.order_manager.current_position_data['stop_loss'] = new_sl
                    self.legacy_bot.order_manager.current_position_data['quantity'] += add_size

            # Alerta
            if self.modern_bridge and self.modern_bridge.alert_manager:
                state = self.pyramiding_manager.get_position_state(symbol)
                self.modern_bridge.alert_manager.alert_info(
                    f"🔺 Pyramiding Add #{state['num_adds']}\n"
                    f"Symbol: {symbol}\n"
                    f"Add Size: {add_size}\n"
                    f"Price: ${current_price:.2f}\n"
                    f"New SL: ${new_sl:.2f}"
                )

            self.legacy_bot.logger.info(f"✅ Pyramiding add executed")

        except Exception as e:
            self.legacy_bot.logger.error(f"Error in pyramiding: {e}", exc_info=True)

    def start(self):
        """Iniciar el bot"""
        if not self.legacy_bot:
            raise RuntimeError("Bot not initialized. Call initialize() first")

        self.legacy_bot.start()

    def stop(self):
        """Detener el bot"""
        if self.legacy_bot:
            self.legacy_bot.stop()

    def get_status(self) -> dict:
        """Obtener estado del bot"""

        status = {
            'balance': 0.0,
            'position': None,
            'pnl_usdt': 0.0,
            'pnl_pct': 0.0,
            'circuit_breaker': {'paused': False},
            'regime': None,
            'total_trades': 0,
            'win_rate': 0.0,
            'uptime_seconds': 0
        }

        try:
            # Circuit breaker
            if self.modern_bridge:
                can_trade, reason = self.modern_bridge.can_trade()
                status['circuit_breaker'] = {
                    'paused': not can_trade,
                    'reason': reason
                }

            # Régimen
            if self.regime_filter:
                regime_summary = self.regime_filter.get_regime_summary()
                status['regime'] = regime_summary

            # Posición
            if self.legacy_bot and self.legacy_bot.order_manager:
                if self.legacy_bot.order_manager.current_position_data:
                    status['position'] = self.legacy_bot.order_manager.current_position_data

        except Exception as e:
            print(f"Error getting status: {e}")

        return status

    def run_with_gui(self):
        """Ejecutar con GUI moderna"""

        # Inicializar componentes
        if not self.initialize():
            print("Failed to initialize")
            return

        # Crear GUI
        gui = ModernTradingGUI(
            start_callback=self.start,
            stop_callback=self.stop,
            get_status_callback=self.get_status
        )

        # Conectar logger
        if self.legacy_bot:
            self.legacy_bot.logger_system.set_gui_callback(gui.log_message)

        # Ejecutar
        gui.run()

    def run_headless(self):
        """Ejecutar sin GUI"""

        if not self.initialize():
            print("Failed to initialize")
            return

        # Iniciar
        self.start()

        # Mantener vivo
        try:
            while self.legacy_bot.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping bot...")
            self.stop()


def main():
    parser = argparse.ArgumentParser(description='Trading Bot con Arquitectura 3.0 Integrada')

    parser.add_argument(
        '--gui',
        action='store_true',
        help='Ejecutar con GUI moderna'
    )

    parser.add_argument(
        '--legacy-gui',
        action='store_true',
        help='Ejecutar con GUI legacy de binance_bot_2.py'
    )

    args = parser.parse_args()

    # Configurar logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Crear bot integrado
    bot = IntegratedTradingBot(use_modern_gui=args.gui)

    # Ejecutar
    if args.gui:
        # GUI moderna
        bot.run_with_gui()

    elif args.legacy_gui:
        # GUI legacy
        if not bot.initialize():
            print("Failed to initialize")
            return

        # Usar GUI legacy
        gui = TradingBotGUI(bot.legacy_bot)
        gui.run()

    else:
        # Headless
        bot.run_headless()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
