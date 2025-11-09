# Integración de GUI Moderna

Guía para integrar la GUI mejorada con binance_bot_2.py

## 🎯 Mejoras Implementadas

La nueva GUI (`gui/modern_trading_gui.py`) incluye:

✅ **Non-blocking API calls** - Operaciones en background threads
✅ **Configuración dinámica** - Cambiar symbol, timeframe, risk profile sin editar código
✅ **Messagebox para errores** - Notificaciones visuales de errores críticos
✅ **Layout responsivo** - Grid que se adapta al tamaño de ventana
✅ **Display de régimen** - Muestra estado del mercado en tiempo real
✅ **Kill switch mejorado** - Detención de emergencia con confirmación

---

## 📝 Integración en binance_bot_2.py

### Paso 1: Imports

```python
# Al inicio de binance_bot_2.py

from gui.modern_trading_gui import ModernTradingGUI, GUIState
```

### Paso 2: Crear Instancia de GUI

```python
def main():
    """Función principal con GUI moderna"""

    # Crear logger
    logger = TradingLogger()

    # Crear cliente Binance
    client = Client(Config.API_KEY, Config.SECRET_KEY, testnet=Config.USE_TESTNET)

    # Crear bot
    bot = TradingBot(logger, client)

    # ✨ NUEVO: Crear GUI moderna con callbacks
    gui = ModernTradingGUI(
        start_callback=bot.start,
        stop_callback=lambda: bot.stop(close_position=True),
        get_status_callback=bot.get_status,
        update_config_callback=bot.update_config  # Nueva función (ver Paso 3)
    )

    # Conectar bot con GUI para logs
    bot.set_gui_callback(gui.log_message)

    # Ejecutar GUI
    gui.run()
```

### Paso 3: Implementar update_config en TradingBot

```python
class TradingBot:
    """Trading bot con configuración dinámica"""

    def __init__(self, logger, client, gui_callback=None):
        # ... código existente ...

        # Configuración dinámica
        self.dynamic_config = {
            'symbol': Config.SYMBOL,
            'timeframe': Config.TIMEFRAME,
            'risk_profile': Config.DEFAULT_RISK_PROFILE,
            'testnet': Config.USE_TESTNET
        }

    def update_config(self, new_config: dict) -> bool:
        """
        Actualiza configuración sin reiniciar bot

        Args:
            new_config: Dict con nuevos valores

        Returns:
            True si se aplicó correctamente
        """
        try:
            # Validar configuración
            if 'symbol' in new_config:
                # Verificar que el símbolo existe
                if not self._validate_symbol(new_config['symbol']):
                    raise ValueError(f"Invalid symbol: {new_config['symbol']}")

            if 'timeframe' in new_config:
                valid_timeframes = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h']
                if new_config['timeframe'] not in valid_timeframes:
                    raise ValueError(f"Invalid timeframe: {new_config['timeframe']}")

            if 'risk_profile' in new_config:
                valid_profiles = ['conservador', 'normal', 'agresivo']
                if new_config['risk_profile'] not in valid_profiles:
                    raise ValueError(f"Invalid risk profile: {new_config['risk_profile']}")

            # Aplicar configuración
            self.dynamic_config.update(new_config)

            self.logger.log(f"Configuration updated: {new_config}", "INFO")

            return True

        except Exception as e:
            self.logger.log(f"Error updating config: {e}", "ERROR")
            return False

    def _validate_symbol(self, symbol: str) -> bool:
        """Valida que el símbolo existe en Binance"""
        try:
            self.client.futures_exchange_info()['symbols']
            # Buscar símbolo
            symbols = self.client.futures_exchange_info()['symbols']
            return any(s['symbol'] == symbol for s in symbols)
        except:
            return False

    def get_status(self) -> dict:
        """
        Obtiene estado completo del bot para GUI

        Returns:
            Dict con estado actual
        """
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
            # Balance
            if hasattr(self, 'order_manager'):
                status['balance'] = self.order_manager.balance

            # Position
            if hasattr(self, 'order_manager') and self.order_manager.has_position:
                status['position'] = self.order_manager.current_position_data

            # PnL (calcular desde trades CSV)
            if hasattr(self, 'trade_journal'):
                df = self.trade_journal.get_summary()
                if not df.empty:
                    status['pnl_usdt'] = df['pnl_usdt'].sum()
                    status['pnl_pct'] = (status['pnl_usdt'] / status['balance']) * 100
                    status['total_trades'] = len(df)
                    status['win_rate'] = (df['pnl_usdt'] > 0).sum() / len(df) * 100

            # Circuit Breaker
            if hasattr(self, 'modern_bridge') and self.modern_bridge.circuit_breaker:
                can_trade, reason = self.modern_bridge.can_trade()
                status['circuit_breaker'] = {
                    'paused': not can_trade,
                    'reason': reason
                }

            # Regime
            if hasattr(self, 'regime_filter'):
                regime_summary = self.regime_filter.get_regime_summary()
                status['regime'] = regime_summary

            # Uptime
            if hasattr(self, 'start_time'):
                from datetime import datetime
                uptime = (datetime.now() - self.start_time).total_seconds()
                status['uptime_seconds'] = int(uptime)

        except Exception as e:
            self.logger.log(f"Error getting status: {e}", "WARNING")

        return status

    def set_gui_callback(self, callback):
        """Configura callback para enviar logs a GUI"""
        self.gui_callback = callback

        # Actualizar logger para que envíe a GUI también
        if hasattr(self.logger, 'set_gui_callback'):
            self.logger.set_gui_callback(callback)
```

### Paso 4: Conectar Logs con GUI

```python
class TradingLogger:
    """Logger con soporte para GUI"""

    def __init__(self):
        # ... código existente ...

        self.gui_callback = None

    def set_gui_callback(self, callback):
        """Configura callback de GUI"""
        self.gui_callback = callback

    def log(self, message: str, level: str = "INFO", section: str = None):
        """Log con envío a GUI"""

        # ... código existente de logging a archivo/consola ...

        # Enviar a GUI si está configurado
        if self.gui_callback:
            try:
                self.gui_callback(message, level)
            except:
                pass  # Ignorar errores de GUI
```

---

## 🎨 Personalización de la GUI

### Cambiar Colores

```python
# En modern_trading_gui.py

# Configurar estilos
style = ttk.Style()

# Botón de éxito (verde)
style.configure("Success.TButton", foreground="green")

# Botón de peligro (rojo)
style.configure("Danger.TButton", foreground="red")
```

### Añadir Nuevos Widgets

```python
# En _create_status_section()

# Nuevo widget de ejemplo
ttk.Label(status_frame, text="Custom Metric:", font=("Arial", 10, "bold")).grid(
    row=5, column=0, sticky="w", pady=5
)
self.widgets['custom_metric_label'] = ttk.Label(
    status_frame,
    text="N/A",
    font=("Arial", 10)
)
self.widgets['custom_metric_label'].grid(row=5, column=1, sticky="w", padx=10, pady=5)
```

### Añadir Nuevas Acciones

```python
# Botón personalizado
self.widgets['custom_btn'] = ttk.Button(
    frame,
    text="Custom Action",
    command=self._custom_action
)
self.widgets['custom_btn'].grid(row=0, column=5, sticky="ew", padx=5)

def _custom_action(self):
    """Acción personalizada"""
    messagebox.showinfo("Custom", "Custom action executed")
```

---

## 🚀 Ejemplo Completo

Archivo `run_bot_with_gui.py`:

```python
#!/usr/bin/env python3
"""
Ejecutar Trading Bot con GUI Moderna
"""

import sys
from binance.client import Client
from gui.modern_trading_gui import ModernTradingGUI
from config_loader import load_config

# Importar clases del bot
# from binance_bot_2 import TradingBot, TradingLogger, Config


def main():
    """Función principal"""

    print("=" * 60)
    print("TRADING BOT - Modern Interface")
    print("=" * 60)

    # Cargar configuración
    config = load_config()
    print(config.get_summary())

    # Crear logger
    logger = TradingLogger()

    # Crear cliente Binance
    client = Client(
        config.api_key,
        config.api_secret,
        testnet=config.use_testnet
    )

    # Crear bot
    bot = TradingBot(logger, client)

    # Crear GUI con callbacks
    gui = ModernTradingGUI(
        start_callback=bot.start,
        stop_callback=lambda: bot.stop(close_position=True),
        get_status_callback=bot.get_status,
        update_config_callback=bot.update_config
    )

    # Conectar logger con GUI
    bot.set_gui_callback(gui.log_message)

    # Ejecutar
    gui.run()


if __name__ == "__main__":
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
```

Ejecutar:

```bash
python run_bot_with_gui.py
```

---

## 📊 Capturas de Funcionalidad

### Configuración Dinámica

1. Usuario cambia `Symbol` de BTCUSDT a ETHUSDT
2. Usuario cambia `Timeframe` de 5m a 15m
3. Usuario cambia `Risk Profile` de Normal a Agresivo
4. Usuario hace clic en "Aplicar Configuración"
5. GUI pregunta si quiere reiniciar el bot (si está corriendo)
6. Configuración se aplica exitosamente

### Background Operations

1. Usuario hace clic en "Iniciar Bot"
2. GUI muestra "🔄 Iniciando..." (botones deshabilitados)
3. Bot se inicia en background thread (GUI no se congela)
4. Al completar, GUI muestra "🟢 En ejecución"
5. Botones se actualizan (Start disabled, Stop/Kill enabled)

### Error Handling

1. Ocurre un error al iniciar el bot
2. Background thread captura el error
3. GUI muestra messagebox con el error
4. Estado cambia a "🔴 Error"
5. Log muestra detalles del error
6. Usuario puede intentar reiniciar

### Kill Switch

1. Usuario hace clic en "🚨 KILL SWITCH"
2. GUI muestra diálogo de confirmación crítico
3. Usuario confirma
4. Bot se detiene inmediatamente
5. Posiciones se cierran
6. Estado vuelve a "⚪ Detenido"

---

## ✅ Checklist de Integración

- [ ] Importar `ModernTradingGUI` en script principal
- [ ] Implementar `get_status()` en TradingBot
- [ ] Implementar `update_config()` en TradingBot
- [ ] Conectar `set_gui_callback()` en logger
- [ ] Añadir `regime_filter` para mostrar régimen
- [ ] Probar inicio/detención del bot
- [ ] Validar que la GUI no se congela durante operaciones
- [ ] Verificar que los errores se muestran en messagebox
- [ ] Probar cambio de configuración en caliente
- [ ] Validar kill switch con posiciones abiertas

---

## 🔧 Troubleshooting

### GUI se congela al iniciar bot

**Causa:** `start_callback()` se ejecuta en main thread

**Solución:** Ya implementado - todas las operaciones largas se ejecutan en background threads

### Messagebox no aparece

**Causa:** Error ocurre en thread background

**Solución:** Usar `update_queue` para enviar errores al main thread (ya implementado)

### Configuración no se aplica

**Causa:** `update_config_callback` es None o retorna False

**Solución:** Implementar `update_config()` en TradingBot correctamente

### Display de régimen vacío

**Causa:** Bot no tiene `regime_filter` inicializado

**Solución:** Inicializar `RegimeFilter` en TradingBot:

```python
from utils.regime_filter import RegimeFilter

self.regime_filter = RegimeFilter()
```

---

✅ **Con la GUI moderna, el bot tiene una interfaz profesional, responsive y con todas las operaciones non-blocking para mejor experiencia de usuario!**
