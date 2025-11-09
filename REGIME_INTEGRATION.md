# Integración del Detector de Régimen de Mercado

Guía práctica para usar el RegimeDetector y RegimeFilter en binance_bot_2.py

## 📋 Tabla de Contenidos

1. [¿Qué es el Régimen de Mercado?](#qué-es-el-régimen-de-mercado)
2. [RegimeFilter Helper](#regimefilter-helper)
3. [Integración en TradingBot](#integración-en-tradingbot)
4. [Ejemplos Prácticos](#ejemplos-prácticos)
5. [Estrategias por Régimen](#estrategias-por-régimen)

---

## 🎯 ¿Qué es el Régimen de Mercado?

El **régimen de mercado** es la caracterización del comportamiento actual del precio en términos de:

- **Tendencia**: UP, DOWN, o RANGING
- **Fuerza de tendencia**: 0-100 (basado en ADX)
- **Volatilidad**: LOW, NORMAL, HIGH, EXTREME
- **Squeeze**: ¿Está el mercado consolidando? (Bollinger Bands estrechas)

**¿Por qué es importante?**

Diferentes estrategias funcionan mejor en diferentes regímenes:
- **Elliott Wave** necesita tendencias fuertes
- **Fibonacci** funciona en retrocesos de tendencia
- **Wyckoff** detecta acumulación en rangos
- **SMC** encuentra order blocks en tendencias
- **Breakouts** aprovechan salidas de consolidación

Filtrar estrategias por régimen **aumenta la precisión** y **reduce señales falsas**.

---

## 🔧 RegimeFilter Helper

El `RegimeFilter` es un helper que simplifica el uso del RegimeDetector.

### Inicialización

```python
from utils.regime_filter import RegimeFilter

class TradingBot:
    def __init__(self, ...):
        # ... código existente ...

        # ✨ NUEVO: RegimeFilter
        self.regime_filter = RegimeFilter(event_bus=None)
        self.logger.log("✓ RegimeFilter initialized", "INFO")
```

### Métodos Principales

#### 1. Actualizar Régimen

```python
def process_kline(self, kline):
    """Procesar vela y actualizar régimen"""

    # ... actualizar df ...

    # ✨ Actualizar régimen con cada vela
    regime = self.regime_filter.update(self.df)

    # Log del régimen (opcional)
    self.regime_filter.log_regime_status(regime)
```

#### 2. Filtrar Estrategia Individual

```python
# Verificar si Elliott Wave debe filtrarse
should_filter, reason = self.regime_filter.should_filter_strategy('elliott')

if should_filter:
    print(f"Elliott bloqueado: {reason}")
    # No ejecutar señal de Elliott
else:
    # Elliott compatible con régimen actual
    pass
```

#### 3. Obtener Estrategias Compatibles

```python
# Lista de todas las estrategias
all_strategies = ['elliott', 'fibonacci', 'wyckoff', 'smc']

# Verificar compatibilidad
compatibility = self.regime_filter.get_compatible_strategies(all_strategies)

# Resultado: {'elliott': False, 'fibonacci': True, 'wyckoff': True, 'smc': False}
```

#### 4. Ajustar Tamaño por Volatilidad

```python
# Obtener multiplicador de tamaño (0.5 - 1.25)
size_mult = self.regime_filter.get_position_size_multiplier()

# Calcular tamaño con ajuste
base_quantity = 0.1
adjusted_quantity = base_quantity * size_mult

print(f"Tamaño ajustado: {adjusted_quantity} (mult: {size_mult:.2f}x)")
```

---

## 🚀 Integración en TradingBot

### Opción 1: Integración Básica (Manual)

```python
class TradingBot:
    def __init__(self, ...):
        # ... código existente ...

        # Inicializar RegimeFilter
        self.regime_filter = RegimeFilter()

    def analyze_and_trade(self):
        """Analizar mercado con filtrado por régimen"""

        if len(self.df) < 100:
            return

        current_price = float(self.df['close'].iloc[-1])

        # 1. Actualizar régimen
        regime = self.regime_filter.update(self.df)

        # 2. Analizar con todas las estrategias
        all_signals = self.multi_strategy_trader.analyze_market(
            self.df,
            current_price
        )

        # 3. Filtrar señales por régimen
        filtered_signals = {}

        for strategy_name, signal_data in all_signals.items():
            should_filter, reason = self.regime_filter.should_filter_strategy(
                strategy_name, regime
            )

            if should_filter:
                self.logger.log(
                    f"[REGIME] {strategy_name} bloqueado: {reason}",
                    "WARNING"
                )
                # Anular señal
                filtered_signals[strategy_name] = {
                    'signal': 0,
                    'confidence': 0
                }
            else:
                # Mantener señal original
                filtered_signals[strategy_name] = signal_data

        # 4. Calcular confluencia con señales filtradas
        # ... código de confluencia existente ...

        # 5. Ajustar tamaño por volatilidad
        if final_signal:
            size_mult = self.regime_filter.get_position_size_multiplier(regime)
            quantity = self._calculate_position_size(entry, stop_loss)
            quantity *= size_mult  # Ajuste por volatilidad

            self.logger.log(
                f"Position size adjusted by {size_mult:.2f}x (volatility)",
                "INFO"
            )
```

### Opción 2: Integración Automática (con Helper)

```python
from utils.regime_filter import filter_signals_by_regime

class TradingBot:
    def __init__(self, ...):
        # ... código existente ...

        # Inicializar RegimeFilter
        self.regime_filter = RegimeFilter()

    def analyze_and_trade(self):
        """Analizar mercado con filtrado automático por régimen"""

        if len(self.df) < 100:
            return

        current_price = float(self.df['close'].iloc[-1])

        # Analizar con todas las estrategias
        all_signals = self.multi_strategy_trader.analyze_market(
            self.df,
            current_price
        )

        # ✨ Filtrar automáticamente con helper
        result = filter_signals_by_regime(
            signals=all_signals,
            strategy_weights=self.multi_strategy_trader.strategy_weights,
            regime_filter=self.regime_filter,
            df=self.df,
            logger=self.logger
        )

        filtered_signals = result['filtered_signals']
        regime = result['regime']
        size_multiplier = result['size_multiplier']

        # Log del filtrado
        self.logger.log(
            f"[REGIME] {result['blocked_count']}/{len(all_signals)} strategies blocked, "
            f"size mult: {size_multiplier:.2f}x",
            "INFO"
        )

        # Continuar con confluencia usando señales filtradas
        # ... código de confluencia ...
```

### Opción 3: Integración con ModernComponentsBridge

```python
class TradingBot:
    def __init__(self, ...):
        # ... código existente ...

        # Usar ModernComponentsBridge (ya incluye RegimeDetector)
        # NO necesitas crear RegimeFilter por separado
        pass

    def analyze_and_trade(self):
        """Usar régimen desde ModernComponentsBridge"""

        # El bridge ya tiene RegimeDetector integrado

        # Actualizar régimen (ya se hace automáticamente en process_kline)
        # self.modern_bridge.update_regime(self.df)

        # Analizar señales
        signals = self.multi_strategy_trader.analyze_market(
            self.df,
            current_price,
            modern_bridge=self.modern_bridge  # Pasa el bridge
        )

        # El MultiStrategyTrader usa modern_bridge.should_filter_signal_by_regime()
        # para filtrar automáticamente
```

---

## 📊 Ejemplos Prácticos

### Ejemplo 1: Log de Estado del Régimen

```python
def trading_loop(self):
    """Loop con logging de régimen cada 5 minutos"""

    last_regime_log = time.time()

    while not self.stop_event.is_set():
        # ... código existente ...

        # Log del régimen cada 5 minutos
        if time.time() - last_regime_log > 300:
            self.regime_filter.log_regime_status()
            last_regime_log = time.time()
```

**Output esperado:**

```
[10:15:30] [REGIME] Market Status:
  Trend: TRENDING_UP (strength: 45.2, slope: 0.023)
  Volatility: NORMAL (percentile: 52.3)
  Squeeze: NO (BB width: 78.5)
  Recommended strategies: elliott, fibonacci, smc
  Position size multiplier: 1.00x
```

### Ejemplo 2: Mostrar Régimen en GUI

```python
def update_gui_status(self):
    """Actualizar GUI con información del régimen"""

    summary = self.regime_filter.get_regime_summary()

    if summary['detected']:
        regime_text = (
            f"Régimen: {summary['trend_type']} "
            f"({summary['trend_strength']:.0f}% strength)\n"
            f"Volatilidad: {summary['volatility_type']}\n"
            f"Estrategias: {', '.join(summary['recommended_strategies'])}"
        )

        # Actualizar label en GUI
        if self.gui_callback:
            self.gui_callback('regime_status', regime_text)
```

### Ejemplo 3: Decisión de Trading Basada en Régimen

```python
def should_take_trade(self, signal, strategy_name):
    """Verificar si se debe tomar un trade considerando el régimen"""

    # 1. Verificar señal básica
    if signal['signal'] == 0:
        return False, "No signal"

    # 2. Verificar compatibilidad con régimen
    should_filter, reason = self.regime_filter.should_filter_strategy(strategy_name)

    if should_filter:
        return False, f"Blocked by regime: {reason}"

    # 3. Verificar confianza mínima
    if signal['confidence'] < 60:
        return False, f"Low confidence: {signal['confidence']}%"

    # 4. Trade aprobado
    return True, "OK"


# Uso:
can_trade, reason = self.should_take_trade(elliott_signal, 'elliott')

if can_trade:
    self.order_manager.open_position(...)
else:
    self.logger.log(f"Trade rejected: {reason}", "INFO")
```

---

## 📈 Estrategias por Régimen

### Tabla de Compatibilidad

| Estrategia | Regímenes Compatibles | Fuerza Mínima | Squeeze | Descripción |
|------------|----------------------|---------------|---------|-------------|
| **Elliott** | TRENDING_UP, TRENDING_DOWN | 25 | No | Ondas en tendencias claras |
| **Fibonacci** | Cualquiera | 0 | No | Retrocesos en cualquier condición |
| **Wyckoff** | RANGING | 0 | No | Acumulación en laterales |
| **SMC** | TRENDING_UP, TRENDING_DOWN | 20 | No | Order Blocks en tendencias |
| **Breakout** | RANGING | 0 | Sí | Rupturas tras consolidación |

### Escenarios Típicos

#### Escenario 1: Tendencia Alcista Fuerte

```
Régimen detectado:
- Trend: TRENDING_UP
- Strength: 52
- Volatility: NORMAL

Estrategias recomendadas:
✅ Elliott (ondas alcistas)
✅ Fibonacci (retrocesos para comprar)
✅ SMC (order blocks alcistas)
❌ Wyckoff (requiere rango)
❌ Breakout (requiere squeeze)
```

#### Escenario 2: Mercado Lateral

```
Régimen detectado:
- Trend: RANGING
- Strength: 12
- Volatility: LOW
- Squeeze: YES

Estrategias recomendadas:
✅ Wyckoff (acumulación/distribución)
✅ Fibonacci (rebotes en soportes)
✅ Breakout (preparación para ruptura)
❌ Elliott (requiere tendencia)
❌ SMC (requiere tendencia)
```

#### Escenario 3: Alta Volatilidad

```
Régimen detectado:
- Trend: TRENDING_DOWN
- Strength: 38
- Volatility: HIGH (percentile: 85)

Acción:
- Reducir tamaño de posición a 0.75x
- Usar solo estrategias tendenciales con alta confianza
- Ampliar stop loss por volatilidad
```

---

## 🔧 Configuración Avanzada

### Personalizar Mapeo de Estrategias

```python
# Modificar regime_filter.py para agregar nuevas estrategias

self.strategy_regime_map = {
    # ... mapeo existente ...

    # Nueva estrategia personalizada
    'mi_estrategia': {
        'compatible': [RegimeType.TRENDING_UP],
        'min_strength': 30,
        'requires_squeeze': False,
        'description': 'Mi estrategia solo en tendencias alcistas fuertes'
    }
}
```

### Ajustar Multiplicadores de Tamaño

```python
# En regime_filter.py, método get_position_size_multiplier()

if vol_percentile < 20:
    multiplier = 1.5  # Aumentar más en baja volatilidad
elif vol_percentile > 80:
    multiplier = 0.3  # Reducir más en alta volatilidad
```

---

## ✅ Checklist de Integración

- [ ] Crear instancia de RegimeFilter en TradingBot.__init__()
- [ ] Actualizar régimen en process_kline() o cada N minutos
- [ ] Filtrar señales antes de calcular confluencia
- [ ] Ajustar tamaño de posición por multiplicador de volatilidad
- [ ] Loguear estado del régimen periódicamente
- [ ] Mostrar régimen en GUI (opcional)
- [ ] Probar con diferentes condiciones de mercado
- [ ] Validar que estrategias se bloquean correctamente
- [ ] Verificar que tamaño se ajusta según volatilidad

---

## 🧪 Testing

### Test 1: Verificar Filtrado

```python
# Crear régimen de prueba
from models.market_regime import MarketRegime, RegimeType

test_regime = MarketRegime(
    trend_type=RegimeType.RANGING,
    trend_strength=15,
    volatility_percentile=50
)

# Verificar filtrado
regime_filter = RegimeFilter()

# Elliott debería bloquearse (requiere tendencia)
should_filter, reason = regime_filter.should_filter_strategy('elliott', test_regime)
assert should_filter == True

# Wyckoff debería permitirse (funciona en rango)
should_filter, reason = regime_filter.should_filter_strategy('wyckoff', test_regime)
assert should_filter == False

print("✅ Filtrado funciona correctamente")
```

### Test 2: Verificar Multiplicador

```python
# Alta volatilidad → reducir tamaño
high_vol_regime = MarketRegime(
    trend_type=RegimeType.TRENDING_UP,
    volatility_percentile=90  # Alta
)

mult = regime_filter.get_position_size_multiplier(high_vol_regime)
assert mult <= 0.75  # Debe reducir

# Baja volatilidad → aumentar tamaño
low_vol_regime = MarketRegime(
    trend_type=RegimeType.TRENDING_UP,
    volatility_percentile=15  # Baja
)

mult = regime_filter.get_position_size_multiplier(low_vol_regime)
assert mult >= 1.1  # Debe aumentar

print("✅ Multiplicador funciona correctamente")
```

---

## 📚 Referencias

- **core/regime_detector.py**: Detector principal de régimen
- **utils/regime_filter.py**: Helper para filtrado
- **models/market_regime.py**: Modelos de datos
- **INTEGRATION_GUIDE.md**: Guía general de integración

---

✅ **Con el RegimeFilter, el bot solo operará estrategias compatibles con las condiciones actuales del mercado, mejorando la precisión y reduciendo señales falsas.**
