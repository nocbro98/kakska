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

## 🚀 Instalación

### Requisitos
```bash
pip install binance-connector pandas numpy talib scipy
```

### Configuración

1. **Variables de Entorno:**
```bash
export BINANCE_API_KEY="tu_api_key"
export BINANCE_SECRET_KEY="tu_secret_key"
```

2. **Testnet vs Mainnet:**
```python
system = TradingSystem(
    api_key=api_key,
    api_secret=api_secret,
    testnet=True,  # False para mainnet
    risk_profile="normal",
    symbol="BTCUSDT"
)
```

## 💻 Uso

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
