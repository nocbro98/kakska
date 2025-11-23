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
import queue
from datetime import datetime
import threading
from typing import Dict, Any

# Importar bot existente
from binance_bot_2 import TradingBot, TradingBotGUI, Config, RiskProfile

# Importar sistema de monkey patching
from integration_patches import create_bot_patches, apply_patches_to_bot_instance


class LoggerQueueAdapter:
    """
    Adapter para convertir entre el formato de TradingLogger y ModernTradingGUI.

    TradingLogger pone: ('log', {'message': msg, 'level': lvl, ...})
    ModernTradingGUI espera: ('log', (msg, lvl))

    No hereda de Queue, solo actúa como proxy transparente.
    """

    def __init__(self, target_queue: queue.Queue):
        self.target_queue = target_queue

    def put(self, item, block=True, timeout=None):
        """Override put para adaptar formato"""
        try:
            if isinstance(item, tuple) and len(item) == 2:
                msg_type, data = item

                if msg_type == 'log' and isinstance(data, dict):
                    # Convertir de dict a tuple
                    message = data.get('message', '')
                    level = data.get('level', 'INFO')
                    self.target_queue.put(('log', (message, level)), block=block, timeout=timeout)
                else:
                    # Pasar otros mensajes sin modificar
                    self.target_queue.put(item, block=block, timeout=timeout)
            else:
                # Pasar mensajes no reconocidos sin modificar
                self.target_queue.put(item, block=block, timeout=timeout)
        except Exception as e:
            # Silently ignore queue errors to avoid blocking logging
            pass

    def put_nowait(self, item):
        """Override put_nowait para adaptar formato"""
        return self.put(item, block=False)

    def empty(self):
        """Proxy to target queue"""
        return self.target_queue.empty()

    def qsize(self):
        """Proxy to target queue"""
        return self.target_queue.qsize()

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

        # ===== VALIDACIÓN TEMPRANA DE CREDENCIALES =====
        print("\n[0/5] Validando credenciales...")

        if not Config.API_KEY or Config.API_KEY.strip() == '':
            print("\n" + "="*70)
            print("❌ ERROR: BINANCE_API_KEY no está configurada")
            print("="*70)
            print("\nSOLUCIÓN:")
            print("  1. Crea un archivo .env en el directorio raíz")
            print("  2. Añade: BINANCE_API_KEY=tu_api_key_aqui")
            print("  3. Añade: BINANCE_SECRET_KEY=tu_secret_key_aqui")
            print("\nPara obtener credenciales:")
            print("  Testnet: https://testnet.binancefuture.com/")
            print("  Mainnet: https://www.binance.com/en/my/settings/api-management")
            print("="*70 + "\n")
            return False

        if not Config.SECRET_KEY or Config.SECRET_KEY.strip() == '':
            print("\n" + "="*70)
            print("❌ ERROR: BINANCE_SECRET_KEY no está configurada")
            print("="*70)
            print("\nSOLUCIÓN:")
            print("  1. Crea un archivo .env en el directorio raíz")
            print("  2. Añade: BINANCE_API_KEY=tu_api_key_aqui")
            print("  3. Añade: BINANCE_SECRET_KEY=tu_secret_key_aqui")
            print("\nPara obtener credenciales:")
            print("  Testnet: https://testnet.binancefuture.com/")
            print("  Mainnet: https://www.binance.com/en/my/settings/api-management")
            print("="*70 + "\n")
            return False

        print("  ✓ Credenciales validadas (API_KEY y SECRET_KEY presentes)")

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
        """Patch el analyze_and_trade del bot para agregar funcionalidad moderna"""

        # Guardar referencia al método original
        original_analyze_and_trade = self.legacy_bot.analyze_and_trade

        # Inicializar timestamp para regime update
        self._last_regime_update = time.time()

        def patched_analyze_and_trade():
            """analyze_and_trade con componentes modernos integrados"""

            try:
                # ===== CIRCUIT BREAKER CHECK =====
                if self.modern_bridge:
                    can_trade, reason = self.modern_bridge.can_trade()
                    if not can_trade:
                        self.legacy_bot.logger.warning(f"⛔ Trading pausado por circuit breaker: {reason}")
                        return  # No analizar si circuit breaker está activo

                # ===== RÉGIMEN UPDATE (cada 5 minutos) =====
                if self.regime_filter:
                    if (time.time() - self._last_regime_update) > 300:
                        try:
                            with self.legacy_bot.market_data_lock:
                                if len(self.legacy_bot.market_data) > 0:
                                    regime = self.regime_filter.update(
                                        self.legacy_bot.market_data.copy()
                                    )
                                    self.regime_filter.log_regime_status(regime)
                            self._last_regime_update = time.time()
                        except Exception as e:
                            self.legacy_bot.logger.warning(f"Error updating regime: {e}")

                # ===== EJECUTAR ANÁLISIS ORIGINAL =====
                # Esto ejecuta el análisis completo de las 4 estrategias del bot legacy
                original_analyze_and_trade()

                # ===== PYRAMIDING CHECK (después del análisis) =====
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

            except Exception as e:
                self.legacy_bot.logger.error(f"Error in patched analyze_and_trade: {e}", exc_info=True)

        # Reemplazar solo el método analyze_and_trade, NO el trading_loop completo
        self.legacy_bot.analyze_and_trade = patched_analyze_and_trade

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
        """Obtener estado del bot con información completa"""

        status = {
            'balance': 0.0,
            'position': None,
            'pnl_usdt': 0.0,
            'pnl_pct': 0.0,
            'circuit_breaker': {'paused': False, 'reason': None},
            'regime': None,
            'total_trades': 0,
            'win_rate': 0.0,
            'uptime_seconds': 0,
            'open_orders': [],
            'is_running': False
        }

        try:
            # Estado de ejecución
            if self.legacy_bot:
                status['is_running'] = self.legacy_bot.is_running

            # Balance
            if self.legacy_bot and hasattr(self.legacy_bot, 'client'):
                try:
                    account_info = self.legacy_bot.client.futures_account()
                    status['balance'] = float(account_info.get('totalWalletBalance', 0.0))
                except Exception as e:
                    # Si falla, intentar balance simple
                    if hasattr(self.legacy_bot, 'balance'):
                        status['balance'] = float(self.legacy_bot.balance)

            # Circuit breaker
            if self.modern_bridge:
                can_trade, reason = self.modern_bridge.can_trade()
                status['circuit_breaker'] = {
                    'paused': not can_trade,
                    'reason': reason if not can_trade else None
                }

            # Régimen
            if self.regime_filter:
                regime_summary = self.regime_filter.get_regime_summary()
                status['regime'] = regime_summary

            # Posición y PnL
            if self.legacy_bot and self.legacy_bot.order_manager:
                if self.legacy_bot.order_manager.current_position_data:
                    position = self.legacy_bot.order_manager.current_position_data
                    status['position'] = position

                    # Calcular PnL si hay posición
                    try:
                        entry_price = float(position.get('entry_price', 0))
                        quantity = float(position.get('quantity', 0))
                        side = position.get('side', 'BUY')

                        # Obtener precio actual
                        current_price = 0.0
                        if hasattr(self.legacy_bot, 'client'):
                            ticker = self.legacy_bot.client.futures_symbol_ticker(symbol=Config.SYMBOL)
                            current_price = float(ticker.get('price', 0))

                        if current_price > 0 and entry_price > 0 and quantity > 0:
                            # Calcular PnL
                            if side == 'BUY':
                                pnl_usdt = (current_price - entry_price) * quantity
                            else:  # SELL
                                pnl_usdt = (entry_price - current_price) * quantity

                            status['pnl_usdt'] = pnl_usdt
                            status['pnl_pct'] = (pnl_usdt / (entry_price * quantity)) * 100

                    except Exception as e:
                        pass  # PnL no disponible

                # Órdenes abiertas
                try:
                    if hasattr(self.legacy_bot, 'client'):
                        open_orders = self.legacy_bot.client.futures_get_open_orders(symbol=Config.SYMBOL)
                        status['open_orders'] = [
                            {
                                'orderId': order.get('orderId'),
                                'type': order.get('type'),
                                'side': order.get('side'),
                                'price': float(order.get('price', 0)),
                                'quantity': float(order.get('origQty', 0)),
                                'status': order.get('status')
                            }
                            for order in open_orders
                        ]
                except Exception as e:
                    pass  # Órdenes no disponibles

            # Estadísticas de trading
            if self.legacy_bot and hasattr(self.legacy_bot, 'trade_history'):
                trades = self.legacy_bot.trade_history
                status['total_trades'] = len(trades)

                if trades:
                    winning_trades = sum(1 for t in trades if t.get('pnl', 0) > 0)
                    status['win_rate'] = (winning_trades / len(trades)) * 100

            # Uptime
            if self.legacy_bot and hasattr(self.legacy_bot, 'start_time'):
                import time
                status['uptime_seconds'] = int(time.time() - self.legacy_bot.start_time)

        except Exception as e:
            print(f"Error getting status: {e}")
            import traceback
            traceback.print_exc()

        return status

    def update_config(self, config: Dict[str, Any]) -> bool:
        """
        Actualizar configuración dinámica del bot.

        Args:
            config: Dict con keys: symbol, timeframe, risk_profile, testnet

        Returns:
            True si la actualización fue exitosa, False en caso contrario
        """
        try:
            # Validar que el bot esté detenido antes de actualizar
            if self.legacy_bot and self.legacy_bot.is_running:
                print("⚠️ Cannot update config while bot is running. Stop first.")
                return False

            # Actualizar Config global
            if 'symbol' in config:
                Config.SYMBOL = config['symbol']

            if 'timeframe' in config:
                Config.TIMEFRAME = config['timeframe']

            if 'risk_profile' in config:
                # Mapear string a RiskProfile
                profile_map = {
                    'Conservador': RiskProfile.CONSERVATIVE,
                    'Normal': RiskProfile.NORMAL,
                    'Agresivo': RiskProfile.AGGRESSIVE
                }
                if config['risk_profile'] in profile_map:
                    Config.RISK_PROFILE = profile_map[config['risk_profile']]

            if 'testnet' in config:
                Config.USE_TESTNET = config['testnet']

            print(f"✅ Configuration updated: {config}")
            return True

        except Exception as e:
            print(f"❌ Error updating config: {e}")
            return False

    def run_with_gui(self):
        """Ejecutar con GUI moderna con telemetría en tiempo real"""

        # ===== 1. CREAR GUI PRIMERO (para obtener ui_queue) =====
        gui = ModernTradingGUI(
            start_callback=self.start,
            stop_callback=self.stop,
            get_status_callback=self.get_status,
            update_config_callback=self.update_config
        )

        # ===== 2. APLICAR MONKEY PATCHING A LA CLASE TradingBot =====
        # CRÍTICO: Aplicar ANTES de crear la instancia del bot
        print("\n[DEBUG] Aplicando monkey patches a TradingBot...")
        TradingBotPatched = create_bot_patches(TradingBot, ui_queue=gui.update_queue)

        # Reemplazar la clase global temporalmente para que initialize() use la versión parcheada
        import binance_bot_2
        binance_bot_2.TradingBot = TradingBotPatched

        # ===== 3. INICIALIZAR COMPONENTES (ahora con bot parcheado) =====
        if not self.initialize():
            print("Failed to initialize")
            return

        # ===== 4. CONECTAR LOGGER CON ADAPTER DE FORMATO =====
        if self.legacy_bot and hasattr(self.legacy_bot, 'logger_system'):
            adapter_queue = LoggerQueueAdapter(gui.update_queue)
            self.legacy_bot.logger_system.set_gui_queue(adapter_queue)

        # ===== 5. EJECUTAR GUI =====
        # El health_check del bot ahora enviará eventos automáticamente a gui.update_queue
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

        # Crear root de Tkinter y GUI legacy con bot integrado
        root = tk.Tk()
        gui = TradingBotGUI(root, bot=bot.legacy_bot)

        # Configurar cierre limpio
        def on_closing():
            if hasattr(gui, 'on_closing'):
                gui.on_closing()
            else:
                bot.stop()
                root.destroy()

        root.protocol("WM_DELETE_WINDOW", on_closing)

        # Ejecutar mainloop
        root.mainloop()

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
