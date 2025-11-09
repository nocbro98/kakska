# Sistema de Trading Profesional - Arquitectura Completa

Sistema de trading automatizado para Binance Futures con arquitectura empresarial completa, implementando todas las mejores prácticas de trading algorítmico profesional.

## 🏗️ Arquitectura

### Componentes Core

#### 1. **Core de Ejecución y Microestructura**

##### 1.1 Reconciliación al Arranque + Idempotencia de Órdenes
- **ConnectionManager**: Gestiona conexiones con Binance y reconcilia estado al iniciar
- **OrderRegistry**: Registro de órdenes con clientOrderId determinístico
- **StateStore**: Persistencia local en SQLite
- **EventBus**: Sistema pub/sub para comunicación entre componentes

**Características:**
- clientOrderId determinístico: `SYM|STRAT|TS|SEQ|HASH`
- Prevención de órdenes duplicadas
- Regeneración con SEQ+1 tras cancel/reject
- Sincronización automática con exchange al arranque

##### 1.2 Slippage Budget + Selector de Tipo de Orden
- **SlippageEstimator**: Estima slippage y selecciona tipo de orden óptimo
- Budget configurable: max(spread_tolerado, pct_slippage, ticks)
- Selector inteligente:
  - `MARKET`: Rupturas urgentes en tendencia
  - `LIMIT/POST_ONLY`: Posicionamiento en rango
  - `STOP`: Breakouts planificados

##### 1.3 Límites Duros
- Validación de precisión (tickSize/stepSize)
- Bloqueo de órdenes < minNotional
- Rate limiting con backoff exponencial

#### 2. **Riesgo y Gobernanza**

##### 2.1 Circuit Breakers
**Umbrales configurables por perfil:**

| Perfil | Diario | Semanal | Mensual | Racha |
|--------|--------|---------|---------|-------|
| Conservador | -2.5% | -5% | -10% | 4 pérdidas |
| Normal | -3% | -6% | -10% | 4 pérdidas |
| Agresivo | -5% | -8% | -15% | 5 pérdidas |

**Estados:**
- `RUNNING`: Operando
- `PAUSED_DAILY/WEEKLY/MONTHLY`: Pausado por pérdidas
- `PAUSED_STREAK`: Pausado por racha
- `MANUAL_LOCK`: Pausado manualmente

##### 2.2 Exposure Caps
- Nominal total por símbolo
- Máximo de posiciones simultáneas
- Apalancamiento efectivo máximo

##### 2.3 Perfiles de Riesgo
```python
PROFILES = {
    'conservador': {
        'risk_per_trade': 0.75,
        'max_leverage': 3,
        'max_positions': 2
    },
    'normal': {
        'risk_per_trade': 1.5,
        'max_leverage': 5,
        'max_positions': 3
    },
    'agresivo': {
        'risk_per_trade': 2.5,
        'max_leverage': 10,
        'max_positions': 5
    }
}
```

#### 3. **Datos y Atribución**

##### 3.1 Journal Estructurado (SQLite)
Campos por trade:
- `ts_open`, `ts_close`, `symbol`, `profile`
- `strategy_primary`, `strategies_confluence`
- `regime_trend`, `regime_volatility`
- `entry_type`, `plan_rr`, `r_achieved`
- `size_nominal`, `fees`, `funding`, `slippage_real`
- `mae`, `mfe` (Maximum Adverse/Favorable Excursion)
- `reason_exit`, `notes`

##### 3.2 Atribución por Estrategia
- **AttributionSystem**: Calcula equity y KPIs por estrategia
- Métricas: Sharpe, Sortino, Profit Factor, Win Rate, MaxDD
- Curvas de equity separadas
- Matriz de confusión de señales

##### 3.3 Atribución por Régimen
KPIs separados por:
- Tendencia (trending_up/down/ranging)
- Volatilidad (high/low)
- Squeeze

##### 3.4 Reportes Semanales Autogenerados
Contenido:
- Número de trades, Sharpe/Sortino
- Profit Factor, MaxDD, Win Rate
- Comisiones y funding
- Top 3 estrategias
- 3 anomalías detectadas
- Cambios sugeridos de pesos

#### 4. **Portfolio de Señales**

##### 4.1 Pesos Dinámicos por IC (EWMA)
- **ICWeightingSystem**: Calcula Information Coefficient rolling
- IC = correlación Spearman entre señales y retornos futuros
- Normalización de pesos con caps:
  - Máximo: 50% por estrategia
  - Mínimo: 10% para no "apagar"
- Penalización temporal si IC < 0 consistentemente
- Rebalance cada 7 días

##### 4.2 Regímenes de Mercado
**RegimeDetector** detecta:

1. **Tendencia** (ADX + slope MA):
   - `TRENDING_UP/DOWN`: ADX > 20 + slope significativo
   - `RANGING`: ADX < 20

2. **Volatilidad** (ATR percentil):
   - `VOLATILE_HIGH`: ATR > percentil 80
   - `VOLATILE_LOW`: ATR < percentil 20

3. **Squeeze** (Bollinger Bandwidth):
   - `is_squeeze`: BB width < percentil 20

**Filtrado de estrategias:**
- Tendenciales (Elliott, Breakout) requieren TRENDING
- Reversión (Fibonacci, Wyckoff) requieren RANGING/SQUEEZE
- Alta volatilidad reduce tamaño automáticamente

## 📊 Estructura de Archivos

```
uwu/
├── core/
│   ├── event_bus.py              # Sistema pub/sub
│   ├── state_store.py            # Persistencia SQLite
│   ├── order_registry.py         # Registro idempotente de órdenes
│   ├── connection_manager.py     # Conexión y reconciliación
│   ├── circuit_breaker.py        # Circuit breakers
│   ├── regime_detector.py        # Detección de regímenes
│   ├── attribution_system.py     # Atribución por estrategia/régimen
│   └── ic_weighting.py           # Pesos dinámicos por IC
├── models/
│   ├── order_models.py           # Order, Position, Trade
│   ├── market_regime.py          # MarketRegime, RegimeType
│   └── risk_models.py            # RiskMetrics, CircuitBreakerState
├── utils/
│   ├── alert_manager.py          # Sistema de alertas
│   ├── report_generator.py       # Generador de reportes
│   └── slippage_estimator.py     # Estimación de slippage
├── data/
│   ├── state/                    # Estado persistido (SQLite)
│   ├── reports/                  # Reportes semanales
│   └── alerts.log                # Log de alertas
├── logs/                         # Logs del sistema
├── main_trading_system.py        # Sistema principal integrado
├── binance_bot_2.py              # Bot original (legacy)
└── README.md                     # Este archivo
```

## 🚀 Instalación y Configuración

### Paso 1: Instalar Dependencias

```bash
pip install -r requirements.txt
```

**Nota:** Si tienes problemas instalando TA-Lib, consulta la [guía oficial](https://github.com/mrjbq7/ta-lib#installation).

### Paso 2: Configurar Credenciales

1. **Copiar archivo de ejemplo:**
```bash
cp .env.example .env
```

2. **Editar `.env` con tus credenciales:**
```bash
# Obtén tus credenciales en:
# Testnet: https://testnet.binancefuture.com/
# Mainnet: https://www.binance.com/en/my/settings/api-management

BINANCE_API_KEY=tu_api_key_aqui
BINANCE_SECRET_KEY=tu_secret_key_aqui
TESTNET=true
RISK_PROFILE=normal
SYMBOL=BTCUSDT
```

**⚠️ IMPORTANTE:**
- **NUNCA** compartas tus API keys
- **NUNCA** subas el archivo `.env` a git (ya está en .gitignore)
- Usa **Testnet** para pruebas iniciales
- Configura permisos de API para Futures Trading solamente

### Paso 3: Primer Arranque en Testnet

```python
from main_trading_system import TradingSystem
import os

# Cargar credenciales desde .env
from dotenv import load_dotenv
load_dotenv()

# Crear sistema
system = TradingSystem(
    api_key=os.getenv("BINANCE_API_KEY"),
    api_secret=os.getenv("BINANCE_SECRET_KEY"),
    testnet=True,  # IMPORTANTE: Iniciar con Testnet
    risk_profile="normal",
    symbol="BTCUSDT"
)

# Inicializar (conecta y reconcilia)
if system.initialize():
    print("✅ Sistema inicializado correctamente")
    status = system.get_system_status()
    print(f"Balance: ${status['balance']:.2f}")
    print(f"Circuit Breaker: {status['circuit_breaker']['state']}")
else:
    print("❌ Error al inicializar")
```

### Testnet vs Mainnet

**Testnet (Recomendado para comenzar):**
```python
system = TradingSystem(testnet=True, ...)
```
- Base URL: `https://testnet.binancefuture.com`
- Fondos virtuales
- Sin riesgo real

**Mainnet (Producción):**
```python
system = TradingSystem(testnet=False, ...)
```
- Base URL: `https://fapi.binance.com`
- Fondos reales
- ⚠️ Solo usar tras validación exhaustiva en Testnet

## 🚀 Punto de Entrada: run_integrated_bot.py

**`run_integrated_bot.py` es el orquestador principal del sistema**, integrando todos los componentes modernos (arquitectura 3.0) con el bot legacy (`binance_bot_2.py`).

### Modos de Ejecución

#### 1. **Modo Headless (Sin GUI)**

Ejecuta el bot en modo servidor sin interfaz gráfica:

```bash
python run_integrated_bot.py
```

**Características:**
- Trading automático 24/7
- Logs en consola y archivos
- Ideal para VPS/servidores
- Detener con `Ctrl+C`

#### 2. **Modo GUI Moderna**

Ejecuta con la interfaz gráfica moderna (`ModernTradingGUI`):

```bash
python run_integrated_bot.py --gui
```

**Características:**
- Panel de control responsivo
- Configuración dinámica (symbol, timeframe, risk profile)
- Visualización de estado en tiempo real
- Display de régimen de mercado
- Logs integrados
- Botones Start/Stop/Kill-Switch

#### 3. **Modo GUI Legacy**

Ejecuta con la interfaz gráfica original de `binance_bot_2.py`:

```bash
python run_integrated_bot.py --legacy-gui
```

**Características:**
- GUI clásica de TradingBotGUI
- Compatible con versiones anteriores
- Para usuarios familiarizados con la interfaz original

### Flags Disponibles

| Flag | Descripción |
|------|-------------|
| `--gui` | Ejecuta con GUI moderna (ModernTradingGUI) |
| `--legacy-gui` | Ejecuta con GUI legacy (TradingBotGUI) |
| (sin flags) | Ejecuta en modo headless |

### Arquitectura de Integración

`run_integrated_bot.py` funciona como **wrapper** que:

1. **Inicializa bot legacy** (`binance_bot_2.py`)
2. **Inyecta componentes modernos**:
   - `ModernComponentsBridge` (EventBus, StateStore, OrderRegistry, ConnectionManager)
   - `RobustOrderExecutor` (reintentos con backoff exponencial)
   - `PyramidingManager` (gestión de piramidación)
   - `RegimeFilter` (filtrado por regímenes de mercado)
3. **Conecta componentes**: Event bus, alert manager, logger system
4. **Parchea trading loop**: Añade circuit breakers, regime updates, pyramiding checks
5. **Reconcilia estado** al arranque

### Ejemplo de Inicialización Completa

```python
from run_integrated_bot import IntegratedTradingBot

# Crear bot integrado
bot = IntegratedTradingBot(use_modern_gui=False)

# Inicializar todos los componentes
if bot.initialize():
    print("✅ Sistema inicializado")

    # Verificar estado
    status = bot.get_status()
    print(f"Balance: ${status['balance']:.2f}")
    print(f"Circuit Breaker: {status['circuit_breaker']}")
    print(f"Regime: {status['regime']}")

    # Iniciar trading
    bot.start()

    # ... mantener vivo ...

    # Detener
    bot.stop()
else:
    print("❌ Error al inicializar")
```

### Salida de Inicialización

Al ejecutar `run_integrated_bot.py`, verás:

```
======================================================================
TRADING BOT - Arquitectura 3.0 Integrada
======================================================================

[1/5] Inicializando bot legacy...
✓ python-binance validation passed (ThreadedWebsocketManager available)
  ✓ Bot legacy inicializado

[2/5] Inicializando ModernComponentsBridge...
  ✓ ModernComponentsBridge inicializado
  ✓ Reconciliación completada

[3/5] Inicializando RegimeFilter...
  ✓ RegimeFilter inicializado

[4/5] Inicializando Pyramiding Manager...
  ✓ PyramidingManager inicializado (max 2 adds)

[5/5] Integrando RobustOrderExecutor...
  ✓ RobustOrderExecutor integrado en OrderManager

======================================================================
✅ SISTEMA COMPLETAMENTE INTEGRADO
======================================================================
  Symbol: BTCUSDT
  Timeframe: 5m
  Mode: TESTNET
  Circuit Breakers: ON
  Regime Filter: ON
  Pyramiding: ON
  Alerts: Telegram, Discord, Email
======================================================================
```

### Validación de Dependencias

**IMPORTANTE**: `run_integrated_bot.py` depende de `binance_bot_2.py`, que valida automáticamente:

✅ **python-binance==1.0.19** está instalado
❌ **binance-connector** NO debe estar instalado (conflicto de namespace)
✅ **ThreadedWebsocketManager** está disponible

Si detecta conflictos, el bot aborta con:
```
======================================================================
ERROR: El módulo 'binance' instalado NO es python-binance.
======================================================================
Probablemente tienes binance-connector instalado, que expone un
módulo 'binance' incompatible que shadow las clases esperadas.

SOLUCIÓN:
  1. pip uninstall binance-connector binance
  2. pip install python-binance==1.0.19

CAUSA: binance-connector y python-binance no pueden coexistir
porque ambos exponen el namespace 'binance'.
======================================================================
```

**Ver `requirements.txt` para más detalles sobre dependencias.**

## 💻 Uso Avanzado (API Interna)

Si prefieres usar la API interna de `main_trading_system.py` directamente (sin el wrapper):

### Inicialización Básica

```python
from main_trading_system import TradingSystem

# Crear sistema
system = TradingSystem(
    api_key=api_key,
    api_secret=api_secret,
    testnet=True,
    risk_profile="normal"
)

# Inicializar (conecta, reconcilia, carga estado)
system.initialize()

# Obtener estado
status = system.get_system_status()
print(f"Balance: ${status['balance']:.2f}")
print(f"Circuit Breaker: {status['circuit_breaker']['state']}")
```

### Operaciones Principales

```python
# Verificar si se puede operar
can_trade, reason = system.circuit_breaker.can_trade()

# Verificar régimen de mercado
regime = system.regime_detector.get_current_regime()
allows_strategy = regime.allows_strategy('elliott')

# Obtener pesos de estrategias
weights = system.ic_weighting.get_all_weights()

# Generar reporte semanal
report_path = system.generate_weekly_report()

# Pausa manual
system.manual_pause("Maintenance")
system.manual_resume()
```

### Ejemplo de Flujo de Orden

```python
from models.order_models import Order, OrderSide, OrderType

# Crear orden
order = Order(
    symbol="BTCUSDT",
    strategy="elliott",
    side=OrderSide.BUY,
    order_type=OrderType.LIMIT,
    quantity=0.01,
    price=50000,
    planned_sl=49000,
    planned_tp=52000,
    planned_rr=2.0
)

# Registrar (verifica idempotencia)
if system.order_registry.register_order(order):
    # Orden nueva, se puede enviar
    # ... enviar a Binance ...
    pass
else:
    # Orden duplicada o ya existe
    print("Order already exists or cannot retry")
```

## 📈 Métricas y Reportes

### Dashboard de Atribución

```python
dashboard = system.attribution_system.get_dashboard_data()

# Equity total
print(f"Total Equity: ${dashboard['total_equity']:.2f}")

# Por estrategia
for strategy in dashboard['strategy_metrics']:
    print(f"{strategy['strategy']}: PnL=${strategy['total_pnl']:.2f}, Sharpe={strategy['sharpe_ratio']:.2f}")

# Por régimen
for regime, metrics in dashboard['regime_metrics'].items():
    print(f"{regime}: WR={metrics['win_rate']:.1f}%, Sharpe={metrics['sharpe_ratio']:.2f}")
```

### Reporte Semanal

Generado automáticamente cada semana:
- Archivo: `data/reports/weekly_report_YYYYMMDD_YYYYMMDD.txt`
- Alerta enviada con resumen
- Contiene: métricas, top estrategias, anomalías, sugerencias

## 🔒 Seguridad y Gobernanza

### Circuit Breakers Automáticos

El sistema SE PAUSA AUTOMÁTICAMENTE si:
- Pérdida diaria > umbral del perfil
- Pérdida semanal > umbral del perfil
- Pérdida mensual > umbral del perfil
- Racha de pérdidas consecutivas >= límite

**Acciones al activarse:**
1. Cerrar posiciones abiertas (opcional)
2. Pausar nuevas entradas
3. Emitir alerta crítica
4. Guardar estado y motivo
5. Programar reanudación automática (o manual)

### Reconciliación al Arranque

Al iniciar, el sistema:
1. Lee balance de cuenta
2. Lee posiciones abiertas en exchange
3. Lee órdenes abiertas en exchange
4. Compara con estado local (StateStore)
5. Sincroniza diferencias:
   - Posiciones "fantasma" → agregar a local
   - Posiciones locales inexistentes → eliminar
   - Órdenes inconsistentes → loguear o cancelar

**Resultado:** Cero órdenes duplicadas o fantasma.

## 🧪 Testing

### Test de Idempotencia

```python
# Simular corte de internet durante envío
order1 = Order(symbol="BTCUSDT", strategy="test", ...)
system.order_registry.register_order(order1)  # True (nueva)

# Reintentar misma orden
order2 = Order(symbol="BTCUSDT", strategy="test", ...)  # Mismo clientOrderId
system.order_registry.register_order(order2)  # False (duplicada)

# Tras cancel, regenerar con SEQ+1
new_order = order1.regenerate_with_next_seq()
system.order_registry.register_order(new_order)  # True (SEQ diferente)
```

### Test de Circuit Breaker

```python
# Simular pérdidas
for i in range(4):
    system.circuit_breaker.risk_metrics.add_trade_result(-100, is_win=False)

# Verificar estado
can_trade, reason = system.circuit_breaker.can_trade()
# can_trade = False, reason = "Racha de 4 pérdidas consecutivas"
```

## 📊 Casos de Uso

### 1. Entrada de Posición con Validación Completa

```python
# 1. Verificar circuit breaker
can_trade, reason = system.circuit_breaker.can_trade()
if not can_trade:
    print(f"Trading blocked: {reason}")
    return

# 2. Verificar régimen
regime = system.regime_detector.get_current_regime()
allows, reason = system.regime_detector.allows_strategy('elliott')
if not allows:
    print(f"Strategy blocked: {reason}")
    return

# 3. Ajustar tamaño por volatilidad
size_adjustment = regime.get_volatility_adjustment()
adjusted_size = base_size * size_adjustment

# 4. Estimar slippage
slippage, acceptable, reason = system.slippage_estimator.estimate_slippage(
    side='BUY',
    quantity=adjusted_size,
    bid=bid_price,
    ask=ask_price,
    bid_qty=bid_qty,
    ask_qty=ask_qty
)

if not acceptable:
    print(f"Slippage too high: {reason}")
    return

# 5. Crear y registrar orden
order = Order(...)
if system.order_registry.register_order(order):
    # Enviar a Binance
    pass
```

### 2. Cierre de Trade con Journal Completo

```python
from models.order_models import Trade

trade = Trade(
    trade_id=f"{symbol}_{datetime.now():%Y%m%d%H%M%S}",
    symbol=symbol,
    ts_open=entry_time,
    ts_close=datetime.now(),
    side=OrderSide.BUY,
    entry_price=entry_price,
    exit_price=exit_price,
    quantity=quantity,
    strategy_primary='elliott',
    strategies_confluence='elliott+fibonacci+smc',
    regime_trend=regime.trend_type.value,
    regime_volatility=regime.volatility_type.value,
    entry_type=OrderType.LIMIT,
    plan_rr=2.0,
    r_achieved=calculated_r,
    size_nominal=quantity * entry_price,
    fees=total_fees,
    funding=funding_paid,
    slippage_real=actual_slippage,
    mae=max_adverse_excursion,
    mfe=max_favorable_excursion,
    reason_exit='TP',
    profile=risk_profile
)

# Guardar en journal
system.state_store.save_trade(trade.to_dict())
```

## 🔧 Configuración Avanzada

### Personalizar Circuit Breakers

```python
system.circuit_breaker.risk_metrics.daily_loss_limit_pct = 5.0
system.circuit_breaker.risk_metrics.max_consecutive_losses = 5
```

### Personalizar IC Weighting

```python
system.ic_weighting.max_weight = 0.40  # 40% máximo por estrategia
system.ic_weighting.min_weight = 0.15  # 15% mínimo
system.ic_weighting.rebalance_days = 14  # Rebalancear cada 2 semanas
```

### Añadir Callback de Alertas

```python
def telegram_alert(message: str, level):
    # Enviar a Telegram
    pass

system.alert_manager.register_callback(telegram_alert)
```

## 📝 Logs y Debugging

### Archivos de Log

- `logs/trading_system_*.log`: Log principal del sistema
- `logs/errors.log`: Solo errores
- `logs/strategies_*.log`: Señales de estrategias
- `data/alerts.log`: Historial de alertas

### Nivel de Log

```python
import logging
logging.getLogger("TradingSystem").setLevel(logging.DEBUG)
logging.getLogger("CircuitBreaker").setLevel(logging.INFO)
```

## 🛠️ Resolución de Problemas

### Problema: "index 20 is out of bounds for axis 0 with size 20"

**Causa:**
Error en estrategia SMC al acceder a índices calculados sin validar longitud de datos.

**Síntoma:**
```
[12:40:12] Error en SMC: index 20 is out of bounds for axis 0 with size 20
```

**Solución Implementada:**
- Validación explícita de longitud ANTES de cualquier indexación
- Uso de `safe_index()` y `safe_slice()` para accesos seguros
- Early return con `signal=0` cuando datos insuficientes
- Protección con try/except para capturar excepciones inesperadas

**Código Correcto:**
```python
# ✅ CORRECTO: Validar antes de indexar
if len(data) < self.min_bars_required:
    return StrategySignal(signal=0, confidence=0.0, reasons=["Insufficient data"])

# ✅ CORRECTO: Uso seguro de índices
i = len(highs) - 1
if i - 2 < 0:
    return StrategySignal(signal=0, confidence=0.0, reasons=["Invalid index"])
```

**Test de Regresión:**
```bash
python tests/test_smc_index_error.py
```

### Problema: "Estrategias válidas: 0/4" tratado como error

**Causa:**
El motor de confluencia trataba señales con `signal=0` como errores en vez de "no-trade".

**Síntoma:**
```
[12:40:12] Estrategias válidas: 0/4
[12:40:12] Insuficientes estrategias (0 < 2)
[12:40:12] ❌ ERROR: No se puede operar
```

**Solución Implementada:**
- **signal=0 NO es un error**, es un estado normal de "no-trade"
- Solo cuentan como "válidas" las estrategias con `signal != 0` y `confidence > 0`
- Logging en nivel `INFO` en vez de `ERROR`
- El loop continúa sin degradar el circuit breaker

**Comportamiento Correcto:**
```
[12:40:12] Confluence evaluation: 0/4 valid strategies
[12:40:12] Insufficient valid strategies (0 < 2). No-trade decision.
[12:40:12] ℹ️ INFO: Esperando señales válidas...
```

### Problema: Órdenes duplicadas tras errores de red

**Causa:**
Reintentos sin idempotencia generaban múltiples órdenes.

**Solución Implementada:**
- `clientOrderId` determinístico: `SYM|STRAT|TS|SEQ|HASH`
- OrderRegistry previene duplicados
- Reconciliación al arranque detecta órdenes huérfanas
- Reintentos seguros con `execute_with_retry()`

### Problema: Estado desincronizado al arranque

**Causa:**
Órdenes/posiciones en Exchange pero no en local (o viceversa).

**Solución Implementada:**
- Reconciliación completa al arranque
- Adopta órdenes del exchange si no existen en local
- Marca como huérfanas órdenes locales no presentes en exchange
- Log detallado de sincronización

**Verificar Reconciliación:**
```python
result = system.connection_manager.reconcile_on_startup("BTCUSDT")
print(f"Órdenes adoptadas: {result['orders_adopted']}")
print(f"Órdenes huérfanas: {result['orders_orphaned']}")
```

## 🎯 Checklist de "Hecho-Hecho"

- [✅] T1: Reconciliación + idempotencia de órdenes
- [✅] T2: Circuit breakers con pausa y alerta
- [✅] T3: Atribución por estrategia + dashboard
- [✅] T4: Pesos dinámicos por IC (EWMA)
- [✅] T5: Regímenes de mercado como filtro
- [✅] T6: Journal ampliado (fees, funding, RR, slippage, MAE/MFE)
- [✅] T7: Reporte semanal autogenerado
- [⏳] T8: GUI mejorada (credenciales, perfil, kill-switch, countdown)

## 📚 Próximos Pasos

1. **GUI Completa** (T8):
   - Modal de credenciales con test de conexión
   - Toggle Testnet/Real con recolor
   - Selector de perfil de riesgo
   - Botón kill-switch prominente
   - Countdown de funding
   - Panel de atribución
   - Panel de circuit breakers

2. **Backtesting Robusto**:
   - Walk-forward optimization
   - Monte Carlo con permutación
   - PBO (Probability of Backtest Overfitting)
   - Stress tests

3. **Multi-Activo**:
   - ETHUSDT, SOLUSDT
   - Correlación rolling
   - Límites de exposición conjunta

## 🤝 Contribución

Este sistema implementa las mejores prácticas de trading algorítmico profesional. Para contribuir:

1. Mantener arquitectura modular
2. Usar Event-driven design
3. Persistir todo estado crítico
4. Emitir eventos para observabilidad
5. Logs exhaustivos con niveles apropiados
6. Tests de idempotencia y reconciliación

## 📄 Licencia

Uso interno - Sistema de trading profesional

---

**Autor**: Sistema Profesional de Trading Algorítmico
**Versión**: 3.0.0
**Fecha**: 2025-11-09
