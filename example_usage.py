#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Example Usage of Trading System
Ejemplos de uso del sistema de trading completo
"""

import os
from datetime import datetime
from main_trading_system import TradingSystem
from models.order_models import Order, OrderSide, OrderType


def example_1_basic_initialization():
    """
    Ejemplo 1: Inicialización básica del sistema
    """
    print("\n" + "=" * 80)
    print("EJEMPLO 1: Inicialización Básica")
    print("=" * 80)

    # Credenciales (leer de variables de entorno)
    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_SECRET_KEY", "")

    if not api_key or not api_secret:
        print("⚠️  Set BINANCE_API_KEY and BINANCE_SECRET_KEY environment variables")
        return None

    # Crear sistema
    system = TradingSystem(
        api_key=api_key,
        api_secret=api_secret,
        testnet=True,
        risk_profile="normal",
        symbol="BTCUSDT"
    )

    # Inicializar
    if system.initialize():
        print("✅ Sistema inicializado correctamente")

        # Mostrar estado
        status = system.get_system_status()
        print(f"\n📊 Estado del Sistema:")
        print(f"   Balance: ${status['balance']:.2f}")
        print(f"   Circuit Breaker: {status['circuit_breaker']['state']}")
        print(f"   Órdenes activas: {status['orders']['active_orders']}")

        return system
    else:
        print("❌ Error al inicializar sistema")
        return None


def example_2_circuit_breaker_check(system):
    """
    Ejemplo 2: Verificación de Circuit Breaker
    """
    print("\n" + "=" * 80)
    print("EJEMPLO 2: Verificación de Circuit Breaker")
    print("=" * 80)

    if not system:
        print("Sistema no disponible")
        return

    # Verificar si se puede operar
    can_trade, reason = system.circuit_breaker.can_trade()

    if can_trade:
        print("✅ Trading permitido")
    else:
        print(f"⛔ Trading bloqueado: {reason}")

    # Mostrar métricas de riesgo
    status = system.circuit_breaker.get_status()
    print(f"\n📈 Métricas de Riesgo:")
    print(f"   Balance: ${status['balance']:.2f}")
    print(f"   Peak Balance: ${status['peak_balance']:.2f}")
    print(f"   Drawdown Actual: {status['current_dd_pct']:.2f}%")
    print(f"   Max Drawdown: {status['max_dd_pct']:.2f}%")
    print(f"   PnL Diario: ${status['daily_pnl']:.2f}")
    print(f"   PnL Semanal: ${status['weekly_pnl']:.2f}")
    print(f"   Racha de pérdidas: {status['consecutive_losses']}")


def example_3_regime_detection(system):
    """
    Ejemplo 3: Detección de Régimen de Mercado
    """
    print("\n" + "=" * 80)
    print("EJEMPLO 3: Detección de Régimen de Mercado")
    print("=" * 80)

    if not system:
        print("Sistema no disponible")
        return

    # Obtener régimen actual
    regime_stats = system.regime_detector.get_stats()

    if regime_stats.get('regime'):
        regime = regime_stats['regime']
        print(f"\n🌊 Régimen Actual:")
        print(f"   Tendencia: {regime['trend_type']}")
        print(f"   Fuerza (ADX): {regime['trend_strength']:.1f}")
        print(f"   Volatilidad: {regime['volatility_type']} ({regime['volatility_percentile']:.0f}%ile)")
        print(f"   Squeeze: {'Sí' if regime['is_squeeze'] else 'No'}")

        # Verificar qué estrategias permite
        print(f"\n📋 Estrategias Permitidas:")
        print(f"   Tendenciales (Elliott): {'✅' if regime_stats['allows_trending'] else '❌'}")
        print(f"   Reversión (Fibonacci): {'✅' if regime_stats['allows_mean_reversion'] else '❌'}")

        # Ajuste de tamaño
        size_adj = regime_stats['size_adjustment']
        print(f"\n📏 Ajuste de Tamaño por Volatilidad: {size_adj:.0%}")
    else:
        print("⚠️  Régimen no detectado aún (faltan datos)")


def example_4_ic_weights(system):
    """
    Ejemplo 4: Pesos de Estrategias por IC
    """
    print("\n" + "=" * 80)
    print("EJEMPLO 4: Pesos de Estrategias por IC")
    print("=" * 80)

    if not system:
        print("Sistema no disponible")
        return

    # Obtener pesos actuales
    weights = system.ic_weighting.get_all_weights()
    stats = system.ic_weighting.get_stats()

    print(f"\n⚖️  Pesos Actuales de Estrategias:")
    for strategy, weight in weights.items():
        ic_score = stats['ic_scores'].get(strategy, 0)
        print(f"   {strategy:15s}: {weight:6.2%} (IC: {ic_score:6.3f})")

    print(f"\n📅 Última Rebalance: {stats['last_rebalance']}")
    print(f"   Max Weight: {stats['config']['max_weight']:.0%}")
    print(f"   Min Weight: {stats['config']['min_weight']:.0%}")
    print(f"   Rebalance cada: {stats['config']['rebalance_days']} días")


def example_5_attribution(system):
    """
    Ejemplo 5: Sistema de Atribución
    """
    print("\n" + "=" * 80)
    print("EJEMPLO 5: Sistema de Atribución")
    print("=" * 80)

    if not system:
        print("Sistema no disponible")
        return

    # Obtener datos de atribución
    dashboard = system.attribution_system.get_dashboard_data()

    print(f"\n💰 Equity Total: ${dashboard['total_equity']:.2f}")

    # Métricas por estrategia
    print(f"\n📊 Performance por Estrategia:")
    for strategy in dashboard['strategy_metrics']:
        print(f"\n   {strategy['strategy'].upper()}:")
        print(f"      PnL: ${strategy['total_pnl']:.2f}")
        print(f"      Trades: {strategy['total_trades']}")
        print(f"      Win Rate: {strategy['win_rate']:.1f}%")
        print(f"      Profit Factor: {strategy['profit_factor']:.2f}")
        print(f"      Sharpe: {strategy['sharpe_ratio']:.2f}")
        print(f"      Max DD: {strategy['max_dd']:.2f}%")

    # Métricas por régimen
    print(f"\n🌐 Performance por Régimen:")
    for regime, metrics in dashboard['regime_metrics'].items():
        print(f"\n   {regime.upper()}:")
        print(f"      PnL: ${metrics['total_pnl']:.2f}")
        print(f"      Trades: {metrics['total_trades']}")
        print(f"      Win Rate: {metrics['win_rate']:.1f}%")
        print(f"      Sharpe: {metrics['sharpe_ratio']:.2f}")

    # Matriz de confusión
    print(f"\n🎯 Matriz de Confusión de Señales:")
    for signal, outcomes in dashboard['confusion_matrix'].items():
        total = sum(outcomes.values())
        if total > 0:
            accuracy = (outcomes['positive'] / total * 100)
            print(f"   {signal:5s}: {accuracy:5.1f}% accuracy ({total} señales)")


def example_6_order_idempotency(system):
    """
    Ejemplo 6: Idempotencia de Órdenes
    """
    print("\n" + "=" * 80)
    print("EJEMPLO 6: Idempotencia de Órdenes")
    print("=" * 80)

    if not system:
        print("Sistema no disponible")
        return

    # Crear orden de ejemplo
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

    print(f"\n📝 Orden Creada:")
    print(f"   Client Order ID: {order.client_order_id}")
    print(f"   Symbol: {order.symbol}")
    print(f"   Side: {order.side.value}")
    print(f"   Quantity: {order.quantity}")
    print(f"   Price: ${order.price:.2f}")
    print(f"   Sequence: {order.sequence}")

    # Intentar registrar
    if system.order_registry.register_order(order):
        print("\n✅ Orden registrada correctamente (nueva)")
    else:
        print("\n⚠️  Orden duplicada o no se puede reintentar")

    # Intentar registrar de nuevo (debería fallar)
    print("\n🔄 Reintentando misma orden...")
    if system.order_registry.register_order(order):
        print("✅ Orden registrada (nueva)")
    else:
        print("⛔ Orden rechazada (duplicada) - ¡Idempotencia funcionando!")

    # Regenerar con SEQ+1
    print("\n♻️  Regenerando con SEQ+1...")
    new_order = order.regenerate_with_next_seq()
    print(f"   Nuevo Client Order ID: {new_order.client_order_id}")
    print(f"   Nueva Sequence: {new_order.sequence}")


def example_7_weekly_report(system):
    """
    Ejemplo 7: Generación de Reporte Semanal
    """
    print("\n" + "=" * 80)
    print("EJEMPLO 7: Generación de Reporte Semanal")
    print("=" * 80)

    if not system:
        print("Sistema no disponible")
        return

    print("\n📄 Generando reporte semanal...")
    report_path = system.generate_weekly_report()

    if report_path:
        print(f"✅ Reporte generado: {report_path}")

        # Leer y mostrar primeras líneas
        try:
            with open(report_path, 'r') as f:
                lines = f.readlines()[:30]
                print("\n📋 Primeras líneas del reporte:")
                print("".join(lines))
        except Exception as e:
            print(f"⚠️  Error leyendo reporte: {e}")
    else:
        print("⚠️  No se generó reporte (probablemente no hay trades esta semana)")


def main():
    """Ejecuta todos los ejemplos"""
    print("\n" + "=" * 80)
    print("EJEMPLOS DE USO DEL SISTEMA DE TRADING")
    print("=" * 80)

    # Ejemplo 1: Inicialización
    system = example_1_basic_initialization()

    if not system:
        print("\n❌ No se pudo inicializar el sistema. Verifica las credenciales.")
        return

    # Ejemplo 2: Circuit Breaker
    example_2_circuit_breaker_check(system)

    # Ejemplo 3: Régimen de Mercado
    example_3_regime_detection(system)

    # Ejemplo 4: Pesos IC
    example_4_ic_weights(system)

    # Ejemplo 5: Atribución
    example_5_attribution(system)

    # Ejemplo 6: Idempotencia
    example_6_order_idempotency(system)

    # Ejemplo 7: Reporte Semanal
    example_7_weekly_report(system)

    # Shutdown
    print("\n" + "=" * 80)
    print("FINALIZANDO SISTEMA")
    print("=" * 80)
    system.shutdown()
    print("✅ Sistema finalizado correctamente")


if __name__ == "__main__":
    main()
