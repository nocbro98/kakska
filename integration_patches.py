"""
Integración Completa - Parches para binance_bot_2.py

Este archivo contiene las modificaciones necesarias para integrar
todos los componentes modernos en binance_bot_2.py

Para aplicar la integración:
1. Hacer backup de binance_bot_2.py
2. Aplicar estos cambios manualmente O
3. Usar el script run_integrated_bot.py que wrapper el bot existente
"""

# ============================================================================
# PATCH 1: Imports adicionales al inicio del archivo
# Agregar después de los imports existentes
# ============================================================================

ADDITIONAL_IMPORTS = """
# ===== COMPONENTES MODERNOS (Arquitectura 3.0) =====
from integration_bridge import ModernComponentsBridge
from utils.robust_order_executor import RobustOrderExecutor
from utils.pyramiding_manager import PyramidingManager
from utils.regime_filter import RegimeFilter
from config_loader import load_config
"""

# ============================================================================
# PATCH 2: Modificar TradingBot.__init__
# Agregar después de la inicialización de componentes existentes
# ============================================================================

TRADINGBOT_INIT_ADDITIONS = """
        # ===== COMPONENTES MODERNOS =====
        self.logger.info("Inicializando componentes modernos (Arquitectura 3.0)...")

        # Modern Components Bridge
        try:
            self.modern_bridge = ModernComponentsBridge(
                api_key=Config.API_KEY,
                api_secret=Config.SECRET_KEY,
                testnet=Config.USE_TESTNET,
                risk_profile='normal',  # Tomar del Config
                symbol=Config.SYMBOL
            )

            # Inicializar bridge (con reconciliación)
            if self.modern_bridge.initialize():
                self.logger.info("✓ ModernComponentsBridge inicializado")

                # Conectar logger del bridge con el sistema
                if hasattr(self.modern_bridge, 'alert_manager'):
                    self.logger_system.alert_manager = self.modern_bridge.alert_manager
            else:
                self.logger.warning("⚠️ ModernComponentsBridge falló al inicializar")
                self.modern_bridge = None

        except Exception as e:
            self.logger.error(f"Error inicializando ModernComponentsBridge: {e}")
            self.modern_bridge = None

        # Regime Filter
        try:
            self.regime_filter = RegimeFilter()
            self.logger.info("✓ RegimeFilter inicializado")
        except Exception as e:
            self.logger.error(f"Error inicializando RegimeFilter: {e}")
            self.regime_filter = None

        # Pyramiding Manager (solo si perfil agresivo)
        self.pyramiding_manager = None
        if Config.ALLOW_PYRAMIDING:
            try:
                self.pyramiding_manager = PyramidingManager(
                    max_adds=Config.PYRAMID_MAX_ADDS,
                    min_profit_pct=Config.PYRAMID_MIN_PROFIT_PCT,
                    size_reduction_factor=Config.PYRAMID_SIZE_REDUCTION
                )
                self.logger.info(f"✓ PyramidingManager inicializado (max {Config.PYRAMID_MAX_ADDS} adds)")
            except Exception as e:
                self.logger.error(f"Error inicializando PyramidingManager: {e}")

        # RobustOrderExecutor para OrderManager
        try:
            self.order_manager.robust_executor = RobustOrderExecutor(
                client=self.client,
                symbol=Config.SYMBOL,
                logger=self.logger_system
            )
            self.logger.info("✓ RobustOrderExecutor integrado en OrderManager")
        except Exception as e:
            self.logger.error(f"Error inicializando RobustOrderExecutor: {e}")

        # Conectar componentes entre sí
        if self.regime_filter and self.trader:
            self.trader.regime_filter = self.regime_filter

        if self.pyramiding_manager and self.order_manager:
            self.order_manager.pyramiding_manager = self.pyramiding_manager
"""

# ============================================================================
# PATCH 3: Modificar Config para incluir parámetros de piramidación
# Agregar en la clase Config
# ============================================================================

CONFIG_ADDITIONS = """
    # ===== PIRAMIDACIÓN =====
    ALLOW_PYRAMIDING = os.getenv("ALLOW_PYRAMIDING", "False").lower() == "true"
    PYRAMID_MAX_ADDS = int(os.getenv("PYRAMID_MAX_ADDS", "2"))
    PYRAMID_MIN_PROFIT_PCT = float(os.getenv("PYRAMID_MIN_PROFIT_PCT", "1.0"))
    PYRAMID_SIZE_REDUCTION = float(os.getenv("PYRAMID_SIZE_REDUCTION", "0.5"))
"""

# ============================================================================
# PATCH 4: Modificar OrderManager.open_position para usar RobustOrderExecutor
# Reemplazar el método completo
# ============================================================================

ORDERMANAGER_OPEN_POSITION = '''
    def open_position(self, side: str, entry_price: float, stop_loss: float,
                      take_profits: List[Tuple[float, float]], strategy: str,
                      quantity: float = None, modern_bridge=None):
        """
        Abrir posición con ejecución robusta

        Args:
            side: 'BUY' o 'SELL'
            entry_price: Precio de entrada (usado para cálculo, orden es MARKET)
            stop_loss: Precio de stop loss
            take_profits: Lista de (precio, porcentaje)
            strategy: Nombre de la estrategia
            quantity: Cantidad a operar (calculada si es None)
            modern_bridge: ModernComponentsBridge opcional
        """

        try:
            # Calcular cantidad si no se especificó
            if quantity is None:
                quantity = self.risk_manager.calculate_position_size(entry_price, stop_loss)

            # Ajustar cantidad por precisión
            if self.precision_manager:
                quantity = self.precision_manager.round_quantity(quantity)

            self.logger.info(f"[ENTRY] Abriendo posición {side}: {quantity} @ SL={stop_loss}")

            # ===== NUEVO: Usar RobustOrderExecutor si está disponible =====
            if hasattr(self, 'robust_executor') and self.robust_executor:
                result = self.robust_executor.execute_entry_with_protection(
                    side=side,
                    quantity=quantity,
                    stop_loss=stop_loss,
                    take_profits=take_profits,
                    order_type='MARKET',
                    price=None,
                    max_retries=3
                )

                if not result['success']:
                    error_msg = f"Failed to open position: {', '.join(result['errors'])}"
                    self.logger.error(f"⚠️ {error_msg}")

                    # Alerta de error
                    if modern_bridge and modern_bridge.alert_manager:
                        modern_bridge.alert_manager.alert_error(
                            "Position Entry Failed",
                            error_msg
                        )

                    return False

                # Actualizar estado de posición
                entry_price_actual = float(result['entry_order']['avgPrice'])

                self.current_position_data = {
                    'side': side,
                    'quantity': quantity,
                    'entry_price': entry_price_actual,
                    'entry_time': datetime.now().isoformat(),
                    'stop_loss': stop_loss,
                    'take_profits': take_profits,
                    'strategy': strategy,
                    'entry_order_id': result['entry_order']['orderId'],
                    'sl_order_id': result['sl_order']['orderId'],
                    'tp_order_ids': [tp['orderId'] for tp in result['tp_orders']],
                    'tp1_hit': False
                }

                self.logger.info(
                    f"✅ Position opened with VERIFIED protection\\n"
                    f"  Entry: {result['entry_order']['orderId']} @ {entry_price_actual}\\n"
                    f"  SL: {result['sl_order']['orderId']} @ {stop_loss}\\n"
                    f"  TPs: {len(result['tp_orders'])} orders"
                )

                # Alerta de posición abierta
                if modern_bridge and modern_bridge.alert_manager:
                    modern_bridge.alert_manager.alert_position_opened(
                        symbol=Config.SYMBOL,
                        side=side,
                        quantity=quantity,
                        price=entry_price_actual
                    )

                return True

            else:
                # Fallback: Ejecución legacy (sin verificación robusta)
                self.logger.warning("RobustOrderExecutor no disponible, usando ejecución legacy")
                # ... código legacy existente ...

        except Exception as e:
            self.logger.error(f"Error abriendo posición: {e}", exc_info=True)
            return False
'''

# ============================================================================
# PATCH 5: Modificar MultiStrategyTrader.analyze_market para usar RegimeFilter
# Agregar al inicio del método
# ============================================================================

MULTISTRATEGTRADER_ANALYZE_ADDITIONS = """
        # ===== FILTRADO POR RÉGIMEN =====
        if hasattr(self, 'regime_filter') and self.regime_filter:
            try:
                # Actualizar régimen
                regime = self.regime_filter.update(df)

                # Log del régimen cada cierto tiempo
                if hasattr(self, '_last_regime_log'):
                    if (datetime.now() - self._last_regime_log).total_seconds() > 300:  # 5 min
                        self.regime_filter.log_regime_status(regime)
                        self._last_regime_log = datetime.now()
                else:
                    self._last_regime_log = datetime.now()
                    self.regime_filter.log_regime_status(regime)

            except Exception as e:
                self.logger.warning(f"Error actualizando régimen: {e}")
"""

# ============================================================================
# PATCH 6: Modificar TradingBot.trading_loop para verificar circuit breakers
# Agregar al inicio del loop
# ============================================================================

TRADINGLOOP_ADDITIONS = """
            # ===== VERIFICAR CIRCUIT BREAKERS =====
            if self.modern_bridge:
                can_trade, reason = self.modern_bridge.can_trade()
                if not can_trade:
                    self.logger.warning(f"⛔ Trading pausado: {reason}")
                    time.sleep(60)  # Esperar 1 minuto
                    continue
"""

# ============================================================================
# PATCH 7: Modificar TradingBot.trading_loop para piramidación
# Agregar después de verificar señales
# ============================================================================

PYRAMIDING_CHECK = """
            # ===== VERIFICAR PIRAMIDACIÓN =====
            if (self.order_manager.current_position_data and
                self.pyramiding_manager and
                Config.ALLOW_PYRAMIDING):

                try:
                    with self.market_data_lock:
                        if len(self.market_data) > 0:
                            current_price = float(self.market_data['close'].iloc[-1])

                    # Verificar si se puede piramidear
                    can_add, reason = self.pyramiding_manager.can_add_to_position(
                        Config.SYMBOL, current_price
                    )

                    if can_add:
                        # Verificar señal de confluencia en la misma dirección
                        position_side = self.order_manager.current_position_data['side']

                        # Analizar mercado
                        with self.market_data_lock:
                            df_copy = self.market_data.copy()

                        if len(df_copy) >= 100:
                            signals = self.trader.analyze_market(df_copy, current_price)

                            # Verificar dirección
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
                    self.logger.error(f"Error en verificación de piramidación: {e}")
"""

# ============================================================================
# PATCH 8: Agregar método _execute_pyramiding a TradingBot
# Nuevo método
# ============================================================================

EXECUTE_PYRAMIDING_METHOD = '''
    def _execute_pyramiding(self, current_price: float):
        """Ejecutar adición a posición (piramidación)"""

        try:
            symbol = Config.SYMBOL
            position_side = self.order_manager.current_position_data['side']

            # Calcular tamaño de la adición
            add_size = self.pyramiding_manager.calculate_add_size(symbol)

            # Ajustar por precisión
            if self.precision_manager:
                add_size = self.precision_manager.round_quantity(add_size)

            self.logger.info(f"[PYRAMID] Agregando {add_size} a posición @ {current_price}")

            # Ejecutar orden de adición
            add_order = self.client.futures_create_order(
                symbol=symbol,
                side=position_side,
                type='MARKET',
                quantity=add_size
            )

            # Registrar adición
            self.pyramiding_manager.record_add(symbol, current_price, add_size)

            # Calcular nuevo SL (breakeven)
            with self.market_data_lock:
                if 'atr' in self.market_data.columns:
                    atr = self.market_data['atr'].iloc[-1]
                else:
                    atr = current_price * 0.01  # 1% como fallback

            new_sl = self.pyramiding_manager.calculate_new_stop_loss(
                symbol, current_price, atr
            )

            # Actualizar SL
            if hasattr(self.order_manager, 'robust_executor'):
                success = self.order_manager.robust_executor.update_stop_loss(
                    side=position_side,
                    quantity=self.order_manager.current_position_data['quantity'] + add_size,
                    new_stop_price=new_sl,
                    old_sl_order_id=self.order_manager.current_position_data.get('sl_order_id')
                )

                if success:
                    self.order_manager.current_position_data['stop_loss'] = new_sl
                    self.order_manager.current_position_data['quantity'] += add_size

            # Alerta
            if self.modern_bridge and self.modern_bridge.alert_manager:
                state = self.pyramiding_manager.get_position_state(symbol)
                self.modern_bridge.alert_manager.alert_info(
                    f"🔺 Pyramiding Add #{state['num_adds']}\\n"
                    f"Symbol: {symbol}\\n"
                    f"Add Size: {add_size}\\n"
                    f"Price: ${current_price:.2f}\\n"
                    f"New Avg Entry: ${state['weighted_avg_entry']:.2f}\\n"
                    f"New SL: ${new_sl:.2f} (breakeven+)"
                )

            self.logger.info(
                f"✅ Pyramiding add executed\\n"
                f"  Total quantity: {self.order_manager.current_position_data['quantity']}\\n"
                f"  New SL: ${new_sl:.2f}"
            )

        except Exception as e:
            self.logger.error(f"Error ejecutando piramidación: {e}", exc_info=True)
'''

# ============================================================================
# Instrucciones de aplicación
# ============================================================================

INSTRUCTIONS = """
INSTRUCCIONES PARA APLICAR LA INTEGRACIÓN:

Opción 1: Aplicar manualmente
------------------------------
1. Hacer backup: cp binance_bot_2.py binance_bot_2.py.backup
2. Abrir binance_bot_2.py
3. Aplicar cada PATCH en el orden indicado
4. Guardar cambios

Opción 2: Usar wrapper (más seguro)
------------------------------------
1. No modificar binance_bot_2.py
2. Usar run_integrated_bot.py que wrappea el bot existente
3. Todas las integraciones se manejan externamente

La opción 2 es más segura y permite rollback inmediato.
"""

if __name__ == "__main__":
    print("=" * 70)
    print("PATCHES DE INTEGRACIÓN - Arquitectura 3.0")
    print("=" * 70)
    print(INSTRUCTIONS)
    print("\nPATCHES DISPONIBLES:")
    print("  1. ADDITIONAL_IMPORTS")
    print("  2. TRADINGBOT_INIT_ADDITIONS")
    print("  3. CONFIG_ADDITIONS")
    print("  4. ORDERMANAGER_OPEN_POSITION")
    print("  5. MULTISTRATEGTRADER_ANALYZE_ADDITIONS")
    print("  6. TRADINGLOOP_ADDITIONS")
    print("  7. PYRAMIDING_CHECK")
    print("  8. EXECUTE_PYRAMIDING_METHOD")
    print("\nTotal: 8 patches para integración completa")
    print("=" * 70)
