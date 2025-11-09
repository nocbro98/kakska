# Ejemplo Completo de Integración: binance_bot_2.py con Arquitectura 3.0

Este documento muestra un ejemplo completo de cómo integrar **todos** los componentes modernos en el bot existente.

## 📁 Estructura de Archivos Modificados

```
uwu/
├── binance_bot_2.py           # ✏️ MODIFICAR (ejemplo completo abajo)
├── config_loader.py            # ✅ YA CREADO
├── integration_bridge.py       # ✅ YA CREADO (actualizado con ActiveAlertManager)
├── .env                        # ✏️ CREAR/ACTUALIZAR
├── core/                       # ✅ YA CREADO
│   ├── event_bus.py
│   ├── state_store.py
│   ├── connection_manager.py
│   ├── circuit_breaker.py
│   ├── regime_detector.py
│   ├── attribution_system.py
│   └── ic_weighting.py
└── utils/                      # ✅ YA CREADO
    ├── active_alerts.py        # ✅ NUEVO (alertas reales)
    ├── robust_order_executor.py # ✅ NUEVO (verificación SL)
    └── pyramiding_manager.py   # ✅ NUEVO (piramidación)
```

---

## 🔧 Paso 1: Actualizar .env

```bash
# ========================================
# Credenciales Binance
# ========================================
BINANCE_API_KEY=your_api_key_here
BINANCE_SECRET_KEY=your_secret_key_here

# ========================================
# Trading
# ========================================
SYMBOL=BTCUSDT
TIMEFRAME=5m
USE_TESTNET=True
RISK_PROFILE=normal  # conservador, normal, agresivo

# ========================================
# Sistema
# ========================================
LOG_LEVEL=INFO
DATA_DIR=data
LOGS_DIR=logs
ENVIRONMENT=development  # development, staging, production

# ========================================
# Alertas - Telegram (opcional)
# ========================================
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=-1001234567890

# ========================================
# Alertas - Discord (opcional)
# ========================================
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# ========================================
# Alertas - Email (opcional)
# ========================================
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_FROM=bot@example.com
EMAIL_TO=alerts@example.com
EMAIL_PASSWORD=app_password_here

# ========================================
# Piramidación (solo perfil agresivo)
# ========================================
ALLOW_PYRAMIDING=True
PYRAMID_MAX_ADDS=2
PYRAMID_MIN_PROFIT_PCT=1.0
PYRAMID_SIZE_REDUCTION=0.5
```

---

## 📝 Paso 2: Modificar binance_bot_2.py

### 2.1 Imports al inicio del archivo

```python
# ========================================
# Imports existentes (mantener)
# ========================================
import os
import sys
import time
import pandas as pd
import numpy as np
from binance.client import Client
from binance.exceptions import BinanceAPIException
# ... resto de imports existentes ...

# ========================================
# NUEVOS IMPORTS - Arquitectura 3.0
# ========================================
from config_loader import load_config
from integration_bridge import ModernComponentsBridge
from utils.robust_order_executor import RobustOrderExecutor
from utils.pyramiding_manager import PyramidingManager

# Cargar configuración desde .env
config = load_config()
print(config.get_summary())  # Mostrar resumen al arrancar
```

### 2.2 Actualizar clase Config

```python
class Config:
    """Configuración del bot - ahora carga desde .env"""

    # ========================================
    # Credenciales (desde .env)
    # ========================================
    API_KEY = config.api_key
    SECRET_KEY = config.api_secret

    # ========================================
    # Trading (desde .env)
    # ========================================
    SYMBOL = config.symbol
    TIMEFRAME = config.timeframe
    USE_TESTNET = config.use_testnet

    # ========================================
    # Perfil de Riesgo (desde .env)
    # ========================================
    DEFAULT_RISK_PROFILE = RiskProfile[config.risk_profile.upper()]

    # ========================================
    # Piramidación (desde .env)
    # ========================================
    ALLOW_PYRAMIDING = os.getenv("ALLOW_PYRAMIDING", "False").lower() == "true"
    PYRAMID_MAX_ADDS = int(os.getenv("PYRAMID_MAX_ADDS", "2"))
    PYRAMID_MIN_PROFIT_PCT = float(os.getenv("PYRAMID_MIN_PROFIT_PCT", "1.0"))
    PYRAMID_SIZE_REDUCTION = float(os.getenv("PYRAMID_SIZE_REDUCTION", "0.5"))

    # ========================================
    # Directorios (desde .env)
    # ========================================
    LOG_DIR = config.logs_dir
    DATA_DIR = config.data_dir

    # ========================================
    # Resto de configuración (mantener como está)
    # ========================================
    # ... parámetros de estrategias, GUI, etc. ...
```

### 2.3 Actualizar clase OrderManager

```python
class OrderManager:
    """Gestión de órdenes con ejecución robusta"""

    def __init__(self, client, symbol, logger, balance):
        self.client = client
        self.symbol = symbol
        self.logger = logger
        self.balance = balance

        # Estado de posición actual
        self.has_position = False
        self.current_position_data = None

        # Perfil de riesgo
        self.risk_profile = Config.DEFAULT_RISK_PROFILE
        self.risk_pct = self.risk_profile.value['risk_per_trade']

        # ✨ NUEVO: Ejecutor robusto con verificación de SL
        self.robust_executor = RobustOrderExecutor(
            client=self.client,
            symbol=self.symbol,
            logger=self.logger
        )

    def open_position(
        self,
        side: str,
        quantity: float,
        stop_loss: float,
        take_profits: List[Tuple[float, float]],
        strategy: str,
        modern_bridge=None  # ✨ NUEVO: pasar bridge para alertas
    ):
        """Abrir posición con ejecución robusta verificada"""

        self.logger.log(
            f"[ENTRY] Opening {side} position: {quantity} @ SL={stop_loss}",
            "INFO"
        )

        # ✨ NUEVO: Usar RobustOrderExecutor
        result = self.robust_executor.execute_entry_with_protection(
            side=side,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profits=take_profits,
            order_type='MARKET',
            price=None,
            max_retries=3
        )

        # Verificar resultado
        if not result['success']:
            error_msg = f"Failed to open position: {', '.join(result['errors'])}"
            self.logger.log(f"⚠️ {error_msg}", "ERROR")

            # ✨ NUEVO: Alerta de error crítico
            if modern_bridge and modern_bridge.alert_manager:
                modern_bridge.alert_manager.alert_error(
                    "Position Entry Failed",
                    error_msg
                )

            return None

        # Log de éxito
        entry_price = float(result['entry_order']['avgPrice'])
        self.logger.log(
            f"✅ Position opened with VERIFIED protection\n"
            f"  Entry: {result['entry_order']['orderId']} @ {entry_price}\n"
            f"  SL: {result['sl_order']['orderId']} @ {stop_loss}\n"
            f"  TPs: {len(result['tp_orders'])} orders",
            "SUCCESS"
        )

        # Actualizar estado
        self.has_position = True
        self.current_position_data = {
            'side': side,
            'quantity': quantity,
            'entry_price': entry_price,
            'entry_time': datetime.now().isoformat(),
            'stop_loss': stop_loss,
            'take_profits': take_profits,
            'strategy': strategy,
            'entry_order_id': result['entry_order']['orderId'],
            'sl_order_id': result['sl_order']['orderId'],
            'tp_order_ids': [tp['orderId'] for tp in result['tp_orders']]
        }

        # ✨ NUEVO: Enviar alerta de posición abierta
        if modern_bridge and modern_bridge.alert_manager:
            modern_bridge.alert_manager.alert_position_opened(
                symbol=self.symbol,
                side=side,
                quantity=quantity,
                price=entry_price
            )

        return self.current_position_data

    def update_stop_loss(self, new_stop_loss: float):
        """Actualizar SL con verificación (trailing stop, breakeven)"""

        if not self.has_position:
            return False

        # ✨ NUEVO: Usar método verificado
        success = self.robust_executor.update_stop_loss(
            side=self.current_position_data['side'],
            quantity=self.current_position_data['quantity'],
            new_stop_price=new_stop_loss,
            old_sl_order_id=self.current_position_data.get('sl_order_id')
        )

        if success:
            self.current_position_data['stop_loss'] = new_stop_loss
            self.logger.log(f"✅ Stop loss updated to {new_stop_loss}", "INFO")
        else:
            self.logger.log(f"⚠️ Failed to update stop loss", "WARNING")

        return success

    def close_position(self, reason: str = "manual", modern_bridge=None):
        """Cerrar posición con notificación"""

        if not self.has_position:
            return

        # ... código existente para cerrar posición ...

        # Calcular PnL
        entry_price = self.current_position_data['entry_price']
        # ... cálculo de pnl_usdt, pnl_pct ...

        # ✨ NUEVO: Notificar cierre al sistema moderno
        if modern_bridge:
            trade_data = {
                'timestamp': datetime.now().isoformat(),
                'symbol': self.symbol,
                'side': self.current_position_data['side'],
                'entry_price': entry_price,
                'exit_price': exit_price,
                'quantity': self.current_position_data['quantity'],
                'pnl_usdt': pnl_usdt,
                'pnl_pct': pnl_pct,
                'strategy': self.current_position_data.get('strategy', 'unknown'),
                'reason_exit': reason
            }

            # Actualizar métricas y verificar circuit breakers
            modern_bridge.on_trade_completed(trade_data)

            # Enviar alerta
            if modern_bridge.alert_manager:
                modern_bridge.alert_manager.alert_position_closed(
                    symbol=self.symbol,
                    pnl_usdt=pnl_usdt,
                    pnl_pct=pnl_pct,
                    reason=reason
                )

        # Reset estado
        self.has_position = False
        self.current_position_data = None
```

### 2.4 Actualizar clase TradingBot

```python
class TradingBot:
    """Bot principal con arquitectura 3.0"""

    def __init__(self, logger, client, gui_callback=None):
        self.logger = logger
        self.client = client
        self.gui_callback = gui_callback

        # ... código existente ...

        # ✨ NUEVO: Componentes modernos
        self.modern_bridge = None
        self.pyramiding_manager = None

        # Flags
        self.is_running = False
        self.stop_event = threading.Event()

    def start(self):
        """Iniciar bot con reconciliación"""

        if self.is_running:
            self.logger.log("Bot already running", "WARNING")
            return

        self.logger.log("=" * 60, "INFO")
        self.logger.log("STARTING TRADING BOT WITH ARCHITECTURE 3.0", "INFO")
        self.logger.log("=" * 60, "INFO")

        # ✨ NUEVO: Inicializar componentes modernos
        self.modern_bridge = ModernComponentsBridge(
            api_key=Config.API_KEY,
            api_secret=Config.SECRET_KEY,
            testnet=Config.USE_TESTNET,
            risk_profile=Config.DEFAULT_RISK_PROFILE.value['name'],
            symbol=Config.SYMBOL
        )

        if not self.modern_bridge.initialize():
            self.logger.log("❌ Failed to initialize modern components", "ERROR")
            return

        self.logger.log("✓ Modern components initialized", "SUCCESS")

        # ✨ NUEVO: Inicializar PyramidingManager si está habilitado
        if Config.ALLOW_PYRAMIDING:
            self.pyramiding_manager = PyramidingManager(
                max_adds=Config.PYRAMID_MAX_ADDS,
                min_profit_pct=Config.PYRAMID_MIN_PROFIT_PCT,
                size_reduction_factor=Config.PYRAMID_SIZE_REDUCTION
            )
            self.logger.log(
                f"✓ Pyramiding enabled (max {Config.PYRAMID_MAX_ADDS} adds)",
                "INFO"
            )

        # Verificar circuit breakers antes de empezar
        can_trade, reason = self.modern_bridge.can_trade()
        if not can_trade:
            self.logger.log(f"⛔ Trading blocked: {reason}", "WARNING")
            return

        # Continuar con inicio normal
        self.is_running = True
        self.stop_event.clear()

        # Iniciar threads
        self.websocket_thread = threading.Thread(target=self.start_websocket, daemon=True)
        self.trading_thread = threading.Thread(target=self.trading_loop, daemon=True)

        self.websocket_thread.start()
        self.trading_thread.start()

        self.logger.log("✅ Bot started successfully", "SUCCESS")

    def trading_loop(self):
        """Loop principal con circuit breakers, régimen y piramidación"""

        last_regime_update = time.time()
        last_ic_rebalance = time.time()

        while not self.stop_event.is_set():
            try:
                # ✨ NUEVO: Verificar circuit breakers
                can_trade, reason = self.modern_bridge.can_trade()
                if not can_trade:
                    self.logger.log(f"⛔ Trading paused: {reason}", "WARNING")
                    time.sleep(60)  # Esperar 1 minuto
                    continue

                # Procesar velas de la cola
                if len(self.klines_queue) > 0:
                    kline = self.klines_queue.popleft()
                    self.process_kline(kline)

                # ✨ NUEVO: Actualizar régimen de mercado cada 5 minutos
                if time.time() - last_regime_update > 300:
                    self.modern_bridge.update_regime(self.df)
                    last_regime_update = time.time()

                # ✨ NUEVO: Rebalancear pesos IC cada 24 horas
                if time.time() - last_ic_rebalance > 86400:
                    self.logger.log("Rebalancing IC weights...", "INFO")
                    new_weights = self.modern_bridge.rebalance_ic_weights()
                    self.logger.log(f"New IC weights: {new_weights}", "INFO")
                    last_ic_rebalance = time.time()

                # ✨ NUEVO: Verificar piramidación si hay posición
                if (self.order_manager.has_position and
                    self.pyramiding_manager and
                    Config.ALLOW_PYRAMIDING):

                    current_price = float(self.df['close'].iloc[-1])
                    should_add, signal_strength = self._check_pyramiding_signal(current_price)

                    if should_add:
                        self._execute_pyramiding(current_price, signal_strength)

                time.sleep(1)

            except Exception as e:
                self.logger.log(f"Error in trading loop: {e}", "ERROR")
                time.sleep(5)

    def process_kline(self, kline):
        """Procesar vela con detección de régimen"""

        # ... código existente para actualizar df ...

        # ✨ NUEVO: Actualizar régimen en cada vela
        if self.modern_bridge:
            self.modern_bridge.update_regime(self.df)

        # Continuar con análisis normal
        self.analyze_and_trade()

    def analyze_and_trade(self):
        """Analizar mercado con filtrado por régimen"""

        if len(self.df) < 100:
            return

        current_price = float(self.df['close'].iloc[-1])

        # Analizar con todas las estrategias
        signals = self.multi_strategy_trader.analyze_market(
            self.df,
            current_price,
            modern_bridge=self.modern_bridge  # ✨ NUEVO: pasar bridge
        )

        if not signals:
            return

        # Ejecutar señal
        if signals['signal'] == 1:  # BUY
            # ... código existente ...
            self.order_manager.open_position(
                side='BUY',
                quantity=quantity,
                stop_loss=stop_loss,
                take_profits=take_profits,
                strategy=signals['dominant_strategy'],
                modern_bridge=self.modern_bridge  # ✨ NUEVO
            )

        elif signals['signal'] == -1:  # SELL
            # ... similar ...
            pass

    def _check_pyramiding_signal(self, current_price: float) -> tuple[bool, float]:
        """Verificar si se debe agregar a la posición"""

        symbol = Config.SYMBOL

        # 1. Verificar si se puede piramidear
        can_add, reason = self.pyramiding_manager.can_add_to_position(
            symbol, current_price
        )

        if not can_add:
            self.logger.log(f"[PYRAMID] Cannot add: {reason}", "DEBUG")
            return False, 0.0

        # 2. Verificar señal de confluencia en la misma dirección
        position_side = self.order_manager.current_position_data['side']

        signals = self.multi_strategy_trader.analyze_market(
            self.df,
            current_price,
            modern_bridge=self.modern_bridge
        )

        if not signals:
            return False, 0.0

        # Verificar dirección y fuerza
        if position_side == 'BUY' and signals['signal'] == 1:
            signal_strength = signals['confidence']
            if signal_strength >= 60:
                self.logger.log(
                    f"[PYRAMID] Signal detected: {signal_strength}%",
                    "INFO"
                )
                return True, signal_strength

        elif position_side == 'SELL' and signals['signal'] == -1:
            signal_strength = signals['confidence']
            if signal_strength >= 60:
                self.logger.log(
                    f"[PYRAMID] Signal detected: {signal_strength}%",
                    "INFO"
                )
                return True, signal_strength

        return False, 0.0

    def _execute_pyramiding(self, current_price: float, signal_strength: float):
        """Ejecutar adición a posición"""

        symbol = Config.SYMBOL
        position_side = self.order_manager.current_position_data['side']

        # 1. Calcular tamaño
        add_size = self.pyramiding_manager.calculate_add_size(symbol)

        self.logger.log(
            f"[PYRAMID] Adding {add_size} to position at {current_price}",
            "INFO"
        )

        # 2. Ejecutar orden
        try:
            add_order = self.client.futures_create_order(
                symbol=symbol,
                side=position_side,
                type='MARKET',
                quantity=add_size
            )

            # 3. Registrar adición
            self.pyramiding_manager.record_add(symbol, current_price, add_size)

            # 4. Calcular nuevo SL (breakeven)
            atr = self.df['atr'].iloc[-1]
            new_sl = self.pyramiding_manager.calculate_new_stop_loss(
                symbol, current_price, atr
            )

            # 5. Actualizar SL con verificación
            self.order_manager.update_stop_loss(new_sl)

            # 6. Alerta
            state = self.pyramiding_manager.get_position_state(symbol)
            if self.modern_bridge and self.modern_bridge.alert_manager:
                self.modern_bridge.alert_manager.alert_info(
                    f"🔺 Pyramiding Add #{state['num_adds']}\n"
                    f"Symbol: {symbol}\n"
                    f"Add Size: {add_size}\n"
                    f"Price: ${current_price:.2f}\n"
                    f"New Avg Entry: ${state['weighted_avg_entry']:.2f}\n"
                    f"New SL: ${new_sl:.2f} (breakeven+)"
                )

            self.logger.log(
                f"✅ Pyramiding add #{state['num_adds']} executed\n"
                f"  Total quantity: {state['total_quantity']}\n"
                f"  Weighted avg entry: ${state['weighted_avg_entry']:.2f}\n"
                f"  New SL: ${new_sl:.2f}",
                "SUCCESS"
            )

        except Exception as e:
            self.logger.log(f"❌ Error in pyramiding: {e}", "ERROR")

    def stop(self, close_position=True):
        """Detener bot con cleanup"""

        if not self.is_running:
            return

        self.logger.log("Stopping bot...", "INFO")

        # Cerrar posición si existe
        if close_position and self.order_manager.has_position:
            self.order_manager.close_position(
                reason="bot_stopped",
                modern_bridge=self.modern_bridge
            )

        # ✨ NUEVO: Shutdown de componentes modernos
        if self.modern_bridge:
            self.modern_bridge.shutdown()

        # Cleanup threads
        self.is_running = False
        self.stop_event.set()

        # ... resto del código de cleanup ...

        self.logger.log("✅ Bot stopped successfully", "INFO")
```

### 2.5 Actualizar clase MultiStrategyTrader

```python
class MultiStrategyTrader:
    """Análisis multi-estrategia con filtrado por régimen"""

    def analyze_market(
        self,
        df: pd.DataFrame,
        current_price: float,
        modern_bridge=None  # ✨ NUEVO
    ):
        """Analizar mercado con pesos dinámicos y filtrado por régimen"""

        # ... código existente para generar señales ...

        # ✨ NUEVO: Obtener pesos dinámicos por IC
        if modern_bridge:
            ic_weights = modern_bridge.get_ic_weights()
            self.logger.log(f"[IC] Dynamic weights: {ic_weights}", "DEBUG", "Confluence")

            # Actualizar pesos
            for strategy_name, weight in ic_weights.items():
                if strategy_name in self.strategy_weights:
                    self.strategy_weights[strategy_name] = weight

        # Generar señales de cada estrategia
        signals = []
        for strategy_name, strategy in self.strategies.items():
            signal = strategy.analyze(df)

            # ✨ NUEVO: Filtrar por régimen de mercado
            if modern_bridge:
                should_filter, reason = modern_bridge.should_filter_signal_by_regime(
                    strategy_name
                )

                if should_filter:
                    self.logger.log(
                        f"[REGIME] {strategy_name} blocked: {reason}",
                        "WARNING",
                        "Confluence"
                    )
                    # Anular señal
                    signal['signal'] = 0
                    signal['confidence'] = 0

            signals.append(signal)

        # ✨ NUEVO: Ajustar tamaño por volatilidad
        size_adjustment = 1.0
        if modern_bridge:
            size_adjustment = modern_bridge.get_regime_size_adjustment()
            if size_adjustment != 1.0:
                self.logger.log(
                    f"[REGIME] Size adjustment: {size_adjustment:.2%}",
                    "INFO",
                    "Confluence"
                )

        # Continuar con análisis de confluencia normal
        # ... código existente ...

        # Agregar ajuste de tamaño al resultado
        if final_signal:
            final_signal['size_adjustment'] = size_adjustment

        return final_signal
```

---

## 🎯 Paso 3: Flujo de Ejecución Completo

### Al Arrancar:

1. ✅ ConfigLoader lee variables de `.env`
2. ✅ ModernComponentsBridge inicializa todos los componentes
3. ✅ ConnectionManager reconcilia estado (detecta posiciones/órdenes fantasma)
4. ✅ CircuitBreakerManager carga balance inicial
5. ✅ ActiveAlertManager configura Telegram/Discord/Email
6. ✅ PyramidingManager se inicializa si está habilitado

### En Cada Vela:

1. ✅ RegimeDetector actualiza clasificación del mercado
2. ✅ MultiStrategyTrader obtiene pesos dinámicos (IC)
3. ✅ Señales se filtran por régimen
4. ✅ Tamaño de posición se ajusta por volatilidad

### Al Abrir Posición:

1. ✅ RobustOrderExecutor ejecuta entrada
2. ✅ Verifica que SL se colocó realmente
3. ✅ Reintenta hasta 3 veces con backoff
4. ✅ Cierre de emergencia si falla
5. ✅ ActiveAlertManager envía notificación

### Durante Posición Abierta:

1. ✅ CircuitBreaker verifica umbrales cada trade
2. ✅ PyramidingManager verifica si se puede agregar
3. ✅ Trailing stop se actualiza con verificación

### Al Cerrar Posición:

1. ✅ AttributionSystem registra PnL por estrategia
2. ✅ CircuitBreaker actualiza métricas de riesgo
3. ✅ ActiveAlertManager envía notificación con resultado
4. ✅ ICWeighting actualiza correlaciones

### Cada 24 Horas:

1. ✅ ICWeighting rebalancea pesos
2. ✅ CircuitBreaker resetea períodos diarios
3. ✅ AttributionSystem genera métricas

---

## ✅ Checklist de Verificación

Antes de ejecutar el bot en producción, verificar:

- [ ] `.env` configurado con credenciales válidas
- [ ] `USE_TESTNET=True` si es para pruebas
- [ ] Al menos un canal de alertas configurado (Telegram/Discord/Email)
- [ ] Logs muestran "✓ Modern components bridge initialized successfully"
- [ ] Logs muestran reconciliación completa (X positions, Y orders)
- [ ] Circuit breakers configurados según perfil de riesgo
- [ ] Piramidación habilitada solo si `RISK_PROFILE=agresivo`
- [ ] Balance inicial detectado correctamente

---

## 🚨 Problemas Comunes y Soluciones

### Error: "Configuration validation failed"
**Causa:** Faltan credenciales en `.env`

**Solución:**
```bash
# Verificar que existan:
BINANCE_API_KEY=...
BINANCE_SECRET_KEY=...
```

### Error: "Failed to connect to Binance"
**Causa:** Credenciales inválidas o firewall

**Solución:**
- Verificar credenciales en Binance
- Si testnet: verificar `USE_TESTNET=True`
- Verificar conexión a internet

### Warning: "No alert channels configured"
**Causa:** No hay tokens de Telegram/Discord/Email en `.env`

**Solución:** Normal si no quieres alertas. Para habilitar:
```bash
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

### Error: "Emergency close position - SL failed"
**Causa:** Stop loss no se pudo colocar después de 3 reintentos

**Solución:**
- Verificar límites de la cuenta
- Verificar precio de SL válido
- Verificar saldo suficiente
- El sistema cierra automáticamente para proteger

### Circuit Breaker activado constantemente
**Causa:** Balance inicial muy bajo o pérdidas consecutivas

**Solución:**
- Verificar balance en exchange
- Ajustar umbrales en perfil de riesgo
- Resetear manualmente si es necesario

---

## 📊 Logs Esperados (ejemplo exitoso)

```
[10:00:00] ============================================================
[10:00:00] STARTING TRADING BOT WITH ARCHITECTURE 3.0
[10:00:00] ============================================================
[10:00:01] Initializing modern components bridge...
[10:00:01] ✓ EventBus started
[10:00:01] ✓ StateStore initialized
[10:00:02] ✓ ActiveAlertManager initialized: {'telegram': True, 'discord': False, 'email': False, 'num_callbacks': 0}
[10:00:02] ✓ OrderRegistry initialized
[10:00:03] ✓ ConnectionManager connected
[10:00:04] ✓ Reconciliation complete: 0 positions, 0 orders
[10:00:04] ✓ CircuitBreaker initialized (balance: $1000.00)
[10:00:04] ✓ RegimeDetector initialized
[10:00:04] ✓ AttributionSystem initialized
[10:00:04] ✓ ICWeighting initialized
[10:00:04] ============================================================
[10:00:04] ✅ Modern components bridge initialized successfully
[10:00:04] ============================================================
[10:00:05] ✓ Pyramiding enabled (max 2 adds)
[10:00:05] ✅ Bot started successfully
[10:00:10] [IC] Dynamic weights: {'elliott': 0.25, 'fibonacci': 0.25, 'wyckoff': 0.25, 'smc': 0.25}
[10:05:32] [REGIME] Market regime: TRENDING_UP (strength: 45.2, volatility: NORMAL)
[10:15:45] [ENTRY] Opening BUY position: 0.01 @ SL=43500.0
[10:15:46] ✅ Position opened with VERIFIED protection
[10:15:46]   Entry: 123456789 @ 44000.0
[10:15:46]   SL: 123456790 @ 43500.0
[10:15:46]   TPs: 2 orders
```

---

## 🎓 Siguientes Pasos

Una vez que el bot esté funcionando con la arquitectura 3.0:

1. **Monitorear logs** durante 24-48 horas en testnet
2. **Validar alertas** en Telegram/Discord/Email
3. **Verificar circuit breakers** con trades simulados
4. **Probar piramidación** en tendencias fuertes
5. **Analizar reportes** generados por AttributionSystem
6. **Ajustar umbrales** según comportamiento observado
7. **Migrar a producción** incrementalmente

---

✅ **¡Sistema completo integrado y listo para operar con máxima robustez!**
