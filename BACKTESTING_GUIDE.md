# Guía de Backtesting

Sistema completo de backtesting para validación de estrategias con datos históricos.

---

## 📋 Tabla de Contenidos

1. [¿Qué es Backtesting?](#qué-es-backtesting)
2. [BacktestEngine](#backtestengine)
3. [Uso Básico](#uso-básico)
4. [Integración con Estrategias](#integración-con-estrategias)
5. [Walk-Forward Analysis](#walk-forward-analysis)
6. [Comparación de Estrategias](#comparación-de-estrategias)
7. [Métricas Explicadas](#métricas-explicadas)
8. [Best Practices](#best-practices)

---

## 🎯 ¿Qué es Backtesting?

**Backtesting** es el proceso de validar una estrategia de trading ejecutándola sobre datos históricos para evaluar su desempeño.

### ¿Por qué es importante?

✅ **Validación:** Confirma que la estrategia funciona antes de arriesgar capital real
✅ **Optimización:** Permite ajustar parámetros para mejor performance
✅ **Confianza:** Genera confianza en la estrategia al ver resultados históricos
✅ **Comparación:** Permite comparar múltiples estrategias objetivamente

### ⚠️ Limitaciones del Backtesting

❌ **Overfitting:** Optimizar demasiado para datos pasados puede fallar en el futuro
❌ **Look-ahead bias:** Usar información que no estaría disponible en tiempo real
❌ **Slippage:** Difícil simular exactamente el slippage real
❌ **Market conditions:** El mercado cambia, pasado ≠ futuro

---

## 🔧 BacktestEngine

### Características

El `BacktestEngine` incluye:

✅ **Carga de datos** desde Binance o CSV
✅ **Simulación realista** con fees y slippage
✅ **Métricas completas**: Sharpe, Sortino, MaxDD, Win Rate, Profit Factor
✅ **Equity curve** y drawdown tracking
✅ **Trade log detallado** con MAE/MFE
✅ **Comparación de estrategias**
✅ **Walk-forward analysis**
✅ **Export a CSV/JSON**

### Parámetros de Configuración

```python
BacktestEngine(
    initial_capital=10000.0,    # Capital inicial
    maker_fee=0.0002,           # 0.02% (maker)
    taker_fee=0.0004,           # 0.04% (taker)
    slippage_pct=0.0001,        # 0.01% slippage estimado
    use_regime_filter=True      # Usar filtrado por régimen
)
```

---

## 🚀 Uso Básico

### Ejemplo 1: Backtest Simple

```python
from utils.backtester import BacktestEngine
from binance.client import Client
from datetime import datetime, timedelta

# Crear engine
engine = BacktestEngine(
    initial_capital=10000.0,
    maker_fee=0.0002,
    taker_fee=0.0004
)

# Cargar datos desde Binance
client = Client(api_key, api_secret)

start_date = datetime.now() - timedelta(days=30)
end_date = datetime.now()

df = engine.load_data_from_binance(
    symbol='BTCUSDT',
    timeframe='5m',
    start_date=start_date,
    end_date=end_date,
    client=client
)

print(f"Loaded {len(df)} candles")
```

### Ejemplo 2: Crear Estrategia Simple

```python
def simple_ma_strategy(df, current_price):
    """
    Estrategia de cruce de medias móviles

    Args:
        df: DataFrame con datos históricos
        current_price: Precio actual

    Returns:
        Dict con señal: 1 (LONG), -1 (SHORT), 0 (NEUTRAL)
    """

    # Calcular MAs
    df['ma_fast'] = df['close'].rolling(20).mean()
    df['ma_slow'] = df['close'].rolling(50).mean()

    # Última fila
    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Cruce alcista
    if prev['ma_fast'] <= prev['ma_slow'] and last['ma_fast'] > last['ma_slow']:
        return {'signal': 1, 'confidence': 70}

    # Cruce bajista
    elif prev['ma_fast'] >= prev['ma_slow'] and last['ma_fast'] < last['ma_slow']:
        return {'signal': -1, 'confidence': 70}

    # Sin señal
    else:
        return {'signal': 0, 'confidence': 0}
```

### Ejemplo 3: Ejecutar Backtest

```python
# Agregar indicadores al DataFrame
df['ma_fast'] = df['close'].rolling(20).mean()
df['ma_slow'] = df['close'].rolling(50).mean()

# Ejecutar backtest
result = engine.run_backtest(
    df=df,
    strategy_analyzer=simple_ma_strategy,
    symbol='BTCUSDT',
    timeframe='5m',
    strategy_name='MA Cross 20/50'
)

# Imprimir resumen
result.print_summary()
```

**Output esperado:**

```
======================================================================
BACKTEST RESULTS
======================================================================

Strategy: MA Cross 20/50
Symbol: BTCUSDT | Timeframe: 5m
Period: 2024-12-10 to 2025-01-09
Initial Capital: $10,000.00
Final Capital: $10,450.00

📊 TRADES:
  Total Trades: 45
  Winning: 28 | Losing: 17
  Win Rate: 62.22%
  Avg Hold Time: 245.3 minutes

💰 PERFORMANCE:
  Total PnL: $450.00 (+4.50%)
  Avg Win: $35.50
  Avg Loss: $18.20
  Profit Factor: 1.95

📉 RISK:
  Max Drawdown: $125.00 (1.25%)
  Sharpe Ratio: 1.85
  Sortino Ratio: 2.45

💸 COSTS:
  Total Fees: $45.20
  Total Slippage: $12.30

======================================================================
```

---

## 🔗 Integración con Estrategias Existentes

### Adaptar Estrategias de binance_bot_2.py

```python
# Estrategia existente de Elliott Wave
from binance_bot_2 import ElliotWaveDetector

# Wrapper para backtesting
def elliott_strategy_wrapper(df, current_price):
    """Adapta ElliotWaveDetector para backtesting"""

    # Crear instancia
    detector = ElliotWaveDetector()

    # Analizar
    result = detector.analyze(df)

    # Convertir a formato de backtest
    return {
        'signal': result.get('signal', 0),
        'confidence': result.get('confidence', 0)
    }

# Ejecutar backtest
result = engine.run_backtest(
    df=df,
    strategy_analyzer=elliott_strategy_wrapper,
    symbol='BTCUSDT',
    timeframe='5m',
    strategy_name='Elliott Wave'
)
```

### Con Filtrado por Régimen

```python
from utils.regime_filter import RegimeFilter

# Crear filtro
regime_filter = RegimeFilter()

# Backtest con filtrado
result = engine.run_backtest(
    df=df,
    strategy_analyzer=elliott_strategy_wrapper,
    symbol='BTCUSDT',
    timeframe='5m',
    strategy_name='Elliott Wave + Regime Filter',
    regime_filter=regime_filter  # ✨ NUEVO
)

# Las señales incompatibles con el régimen serán bloqueadas
```

---

## 📊 Walk-Forward Analysis

**Walk-Forward Analysis** divide los datos en múltiples períodos de entrenamiento y prueba para validar consistencia.

### ¿Por qué es importante?

✅ Evita overfitting validando en datos fuera de muestra
✅ Muestra consistencia de la estrategia en diferentes períodos
✅ Más realista que un solo backtest

### Ejemplo:

```python
# Walk-forward con 5 folds
results = engine.walk_forward_analysis(
    df=df,
    strategy_analyzer=simple_ma_strategy,
    symbol='BTCUSDT',
    timeframe='5m',
    strategy_name='MA Cross',
    train_size_pct=0.7,  # 70% training, 30% testing
    n_folds=5
)

# El engine imprime automáticamente el resumen
```

**Output esperado:**

```
================================================================================
WALK-FORWARD ANALYSIS SUMMARY
================================================================================

Folds: 5
Avg PnL: 3.25% ± 1.85%
Avg Sharpe: 1.65
Consistency: 80.0% profitable folds

Per-Fold Results:
  Fold 1: +4.50% | Sharpe: 2.10
  Fold 2: +2.80% | Sharpe: 1.45
  Fold 3: -0.50% | Sharpe: -0.25
  Fold 4: +5.20% | Sharpe: 2.35
  Fold 5: +4.25% | Sharpe: 1.95
================================================================================
```

**Interpretación:**
- **Avg PnL positivo:** La estrategia es rentable en promedio
- **Baja desviación estándar:** Resultados consistentes
- **80% profitable folds:** Funciona bien en la mayoría de condiciones

---

## 🏆 Comparación de Estrategias

Compara múltiples estrategias para encontrar la mejor.

### Ejemplo:

```python
# Definir estrategias
strategies = {
    'MA Cross 20/50': simple_ma_strategy,
    'Elliott Wave': elliott_strategy_wrapper,
    'Fibonacci': fibonacci_strategy_wrapper,
    'Wyckoff': wyckoff_strategy_wrapper,
    'SMC': smc_strategy_wrapper
}

# Comparar
results = engine.compare_strategies(
    df=df,
    strategies=strategies,
    symbol='BTCUSDT',
    timeframe='5m',
    regime_filter=regime_filter  # Opcional
)
```

**Output esperado:**

```
====================================================================================================
STRATEGY COMPARISON
====================================================================================================

Strategy             Trades   Win%     PnL $        PnL %      MaxDD%     Sharpe   PF
----------------------------------------------------------------------------------------------------
Fibonacci            52       65.4     $625.30      6.25       1.85       2.15     2.25
Elliott Wave         45       62.2     $450.00      4.50       1.25       1.85     1.95
MA Cross 20/50       38       58.0     $385.50      3.86       2.10       1.55     1.75
SMC                  41       55.0     $320.80      3.21       2.50       1.35     1.60
Wyckoff              35       52.0     $245.00      2.45       3.15       1.10     1.45
====================================================================================================
```

**Interpretación:**
- **Fibonacci** tiene mejor PnL y Sharpe ratio
- **Elliott Wave** buen balance de performance y drawdown
- **Wyckoff** menor performance en este período

---

## 📈 Métricas Explicadas

### Métricas de Performance

**Total Trades:** Número de trades ejecutados
- Más trades = más datos, pero también más fees

**Win Rate:** % de trades ganadores
- >50% es bueno, pero no es lo único importante
- Un sistema con 40% win rate puede ser rentable si avg_win >> avg_loss

**Total PnL:** Ganancia/pérdida total
- En USD y %
- Métrica principal de rentabilidad

**Avg Win / Avg Loss:** Promedio de ganancias vs pérdidas
- Ratio importante: si avg_win/avg_loss > 2, puedes ganar con win rate < 50%

**Profit Factor:** Total ganancias / Total pérdidas
- >1.0 = rentable
- >1.5 = bueno
- >2.0 = excelente

### Métricas de Riesgo

**Max Drawdown:** Máxima caída desde un peak
- En USD y %
- Indica el peor escenario que has enfrentado
- Importante para sizing y gestión de riesgo

**Sharpe Ratio:** (Retorno - Risk-free rate) / Desviación estándar
- Mide retorno ajustado por riesgo
- >1.0 = bueno
- >2.0 = muy bueno
- >3.0 = excelente

**Sortino Ratio:** Similar a Sharpe, pero solo considera downside volatility
- Generalmente mayor que Sharpe
- Mejor métrica si te preocupa más la downside

### Métricas de Costos

**Total Fees:** Fees de trading acumulados
- Importante considerar en estrategias high-frequency
- Puede convertir una estrategia rentable en perdedora

**Total Slippage:** Diferencia entre precio esperado y ejecutado
- En mercados ilíquidos puede ser significativo

### Métricas de Tiempo

**Avg Hold Time:** Tiempo promedio de cada trade
- Importante para calcular oportunity cost
- Estrategias con hold time menor aprovechan más el capital

---

## ✅ Best Practices

### 1. Usa Suficientes Datos

❌ **Malo:** 1 semana de datos
✅ **Bueno:** 3-6 meses de datos
✅✅ **Mejor:** 1+ año de datos

Más datos = más representativo de diferentes condiciones de mercado

### 2. Considera Múltiples Timeframes

Prueba tu estrategia en diferentes timeframes:
- 5m, 15m, 1h, 4h

Una buena estrategia debería funcionar en múltiples timeframes (con ajustes).

### 3. Divide In-Sample y Out-of-Sample

✅ **Train:** 70% de datos (optimizar parámetros)
✅ **Test:** 30% de datos (validar, NUNCA tocar para optimizar)

Si optimizas en test data = overfitting

### 4. Walk-Forward Analysis

Siempre haz walk-forward para verificar consistencia.

### 5. Considera Transaction Costs

Incluye siempre:
- Fees de maker/taker
- Slippage estimado
- Funding rates (en futuros)

Ignorar costos puede hacer que una estrategia perdedora parezca ganadora.

### 6. Evita Overfitting

⚠️ Señales de overfitting:
- Performance perfecta en backtest
- Performance terrible en live trading
- Demasiados parámetros ajustables
- Estrategia muy compleja

✅ Para evitar:
- Mantén la estrategia simple
- Usa walk-forward
- Valida en out-of-sample
- No optimices cada parámetro

### 7. Simula Realismo

Tu backtest debe simular condiciones reales:
- No uses información futura (look-ahead bias)
- Incluye latencia
- Simula órdenes que no se llenan
- Considera market impact en órdenes grandes

### 8. Documenta Todo

Registra:
- Parámetros usados
- Resultados
- Fecha del backtest
- Versión de la estrategia

Esto permite reproducir y comparar resultados.

---

## 🧪 Ejemplo Completo de Flujo

```python
#!/usr/bin/env python3
"""
Script completo de backtesting
"""

from utils.backtester import BacktestEngine
from binance.client import Client
from datetime import datetime, timedelta
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)

def main():
    # 1. Crear engine
    engine = BacktestEngine(
        initial_capital=10000.0,
        maker_fee=0.0002,
        taker_fee=0.0004,
        slippage_pct=0.0001
    )

    # 2. Cargar datos
    client = Client(api_key, api_secret)

    df = engine.load_data_from_binance(
        symbol='BTCUSDT',
        timeframe='5m',
        start_date=datetime.now() - timedelta(days=60),
        end_date=datetime.now(),
        client=client
    )

    # 3. Agregar indicadores
    df['ma_fast'] = df['close'].rolling(20).mean()
    df['ma_slow'] = df['close'].rolling(50).mean()

    # 4. Backtest simple
    print("\n=== SIMPLE BACKTEST ===")
    result = engine.run_backtest(
        df=df,
        strategy_analyzer=simple_ma_strategy,
        symbol='BTCUSDT',
        timeframe='5m',
        strategy_name='MA Cross'
    )
    result.print_summary()

    # 5. Walk-forward analysis
    print("\n=== WALK-FORWARD ANALYSIS ===")
    wf_results = engine.walk_forward_analysis(
        df=df,
        strategy_analyzer=simple_ma_strategy,
        symbol='BTCUSDT',
        timeframe='5m',
        strategy_name='MA Cross',
        n_folds=5
    )

    # 6. Comparar estrategias
    print("\n=== STRATEGY COMPARISON ===")
    strategies = {
        'MA Cross 20/50': simple_ma_strategy,
        'MA Cross 10/30': lambda df, p: ma_strategy(df, p, 10, 30),
        'MA Cross 50/100': lambda df, p: ma_strategy(df, p, 50, 100)
    }

    comparison = engine.compare_strategies(
        df=df,
        strategies=strategies,
        symbol='BTCUSDT',
        timeframe='5m'
    )

    # 7. Exportar mejor resultado
    best_strategy = max(comparison.items(), key=lambda x: x[1].total_pnl_usdt)
    engine.export_results(best_strategy[1], 'backtest_results.json')

    print(f"\n✅ Best strategy: {best_strategy[0]}")
    print(f"PnL: ${best_strategy[1].total_pnl_usdt:.2f}")


if __name__ == '__main__':
    main()
```

---

## 📊 Interpretar Resultados

### Escenario 1: Estrategia Buena

```
Total PnL: +$850.00 (+8.50%)
Win Rate: 58%
Profit Factor: 2.1
Max Drawdown: 3.2%
Sharpe: 2.3
```

✅ **Veredicto:** Buena estrategia
- PnL positivo consistente
- Profit factor >2
- Sharpe >2
- Drawdown controlado

### Escenario 2: Overfitting

```
Total PnL: +$1,500.00 (+15.00%)
Win Rate: 92%
Profit Factor: 8.5
Max Drawdown: 0.5%
Sharpe: 5.2
```

⚠️ **Veredicto:** Posible overfitting
- Resultados demasiado buenos
- Probablemente no se replicará en live
- Validar con walk-forward y out-of-sample

### Escenario 3: Estrategia Inconsistente

```
Walk-forward folds:
  Fold 1: +15.2%
  Fold 2: -8.5%
  Fold 3: +12.1%
  Fold 4: -5.2%
  Fold 5: +3.5%
```

❌ **Veredicto:** Inconsistente
- Alta varianza entre folds
- No confiable para live trading
- Necesita mejoras o descartarse

---

## 🎓 Próximos Pasos

Después de backtesting exitoso:

1. **Paper Trading:** Probar en tiempo real sin dinero real
2. **Small Live Test:** Empezar con capital pequeño
3. **Monitoreo Activo:** Comparar live results vs backtest
4. **Iteración:** Ajustar según performance real

---

✅ **El backtesting es una herramienta poderosa, pero recuerda: pasado ≠ futuro. Úsalo como guía, no como garantía.**
