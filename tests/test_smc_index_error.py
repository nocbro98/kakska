#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test SMC Index Error Fix
Reproduce el error original y valida la solución

ERROR ORIGINAL: "index 20 is out of bounds for axis 0 with size 20"
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import logging
from strategies.smc_strategy import SMCStrategy

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s'
)

logger = logging.getLogger("TestSMC")


def test_smc_with_exactly_20_bars():
    """
    Test que reproduce el error original con exactamente 20 elementos

    ANTES: IndexError: index 20 is out of bounds for axis 0 with size 20
    DESPUÉS: Retorna StrategySignal con signal=0 (insufficient data)
    """
    logger.info("=" * 80)
    logger.info("TEST: SMC con exactamente 20 barras (caso crítico)")
    logger.info("=" * 80)

    # Crear datos sintéticos con exactamente 20 elementos
    np.random.seed(42)
    n_bars = 20

    closes = np.random.uniform(40000, 41000, n_bars)
    highs = closes + np.random.uniform(50, 200, n_bars)
    lows = closes - np.random.uniform(50, 200, n_bars)
    opens = closes + np.random.uniform(-100, 100, n_bars)

    logger.info(f"Datos: {n_bars} barras")
    logger.info(f"Closes shape: {closes.shape}")

    # Crear estrategia SMC
    strategy = SMCStrategy(swing_length=10)

    # ESTO CAUSABA IndexError en la versión anterior
    # AHORA debe retornar signal=0 sin excepciones
    try:
        signal = strategy.analyze(closes, highs, lows, opens)

        logger.info(f"✅ Análisis completado sin excepciones")
        logger.info(f"Signal: {signal.signal}")
        logger.info(f"Confidence: {signal.confidence:.2%}")
        logger.info(f"Reasons: {signal.reasons}")

        # Validar que no lanza excepción
        assert signal is not None, "Signal should not be None"

        # Con 20 barras y swing_length=10, deberíamos tener datos insuficientes
        # porque min_bars_required = max(50, 10*3) = 50
        assert signal.signal == 0, "Signal should be 0 (insufficient data)"
        assert signal.confidence == 0.0, "Confidence should be 0.0"

        logger.info("✅ TEST PASSED: No IndexError con 20 barras")
        return True

    except IndexError as e:
        logger.error(f"❌ TEST FAILED: IndexError aún presente: {e}")
        raise

    except Exception as e:
        logger.error(f"❌ TEST FAILED: Unexpected error: {e}")
        raise


def test_smc_with_various_lengths():
    """
    Test con diferentes tamaños de datos (fuzz testing)
    """
    logger.info("\n" + "=" * 80)
    logger.info("TEST: SMC con diferentes longitudes (5-200 barras)")
    logger.info("=" * 80)

    strategy = SMCStrategy(swing_length=10)

    test_lengths = [5, 10, 15, 20, 25, 30, 50, 100, 200]

    for length in test_lengths:
        logger.info(f"\nProbando con {length} barras...")

        # Generar datos sintéticos
        np.random.seed(length)
        closes = np.random.uniform(40000, 41000, length)
        highs = closes + np.random.uniform(50, 200, length)
        lows = closes - np.random.uniform(50, 200, length)
        opens = closes + np.random.uniform(-100, 100, length)

        try:
            signal = strategy.analyze(closes, highs, lows, opens)

            logger.info(
                f"  Length={length}: signal={signal.signal}, "
                f"confidence={signal.confidence:.2f}, "
                f"reason={signal.reasons[0] if signal.reasons else 'none'}"
            )

        except IndexError as e:
            logger.error(f"  ❌ IndexError con {length} barras: {e}")
            raise

        except Exception as e:
            logger.error(f"  ❌ Error con {length} barras: {e}")
            raise

    logger.info("\n✅ TEST PASSED: No IndexError con ningún tamaño")
    return True


def test_confluence_with_zero_signals():
    """
    Test que verifica que el confluence engine maneja correctamente
    el caso de 0/4 estrategias válidas
    """
    logger.info("\n" + "=" * 80)
    logger.info("TEST: Confluence con 0 estrategias válidas")
    logger.info("=" * 80)

    from core.confluence_engine import ConfluenceEngine, StrategySignal

    engine = ConfluenceEngine(min_strategies=2, min_confidence=0.5)

    # Todas las estrategias con signal=0 (datos insuficientes)
    signals = [
        StrategySignal(name='elliott', signal=0, confidence=0.0, reasons=['insufficient data']),
        StrategySignal(name='fibonacci', signal=0, confidence=0.0, reasons=['insufficient data']),
        StrategySignal(name='wyckoff', signal=0, confidence=0.0, reasons=['insufficient data']),
        StrategySignal(name='smc', signal=0, confidence=0.0, reasons=['insufficient data'])
    ]

    # ESTO NO DEBE SER UN ERROR, es un no-trade válido
    decision = engine.evaluate(signals)

    logger.info(f"Decision: {decision.signal.name}")
    logger.info(f"Confidence: {decision.confidence:.2%}")
    logger.info(f"Valid strategies: {decision.num_strategies_valid}/{decision.num_strategies_total}")
    logger.info(f"Reasons: {decision.reasons}")

    # Validar
    assert decision.signal.name == 'NEUTRAL', "Decision should be NEUTRAL"
    assert decision.num_strategies_valid == 0, "Should have 0 valid strategies"
    assert not decision.should_trade(), "Should not trade"

    logger.info("✅ TEST PASSED: Confluence maneja correctamente 0/4 estrategias")
    return True


def main():
    """Ejecuta todos los tests"""
    logger.info("\n" + "=" * 80)
    logger.info("TESTS CRÍTICOS: SMC IndexError y Confluence")
    logger.info("=" * 80)

    try:
        # Test 1: Caso crítico con 20 barras
        test_smc_with_exactly_20_bars()

        # Test 2: Fuzz testing con diferentes longitudes
        test_smc_with_various_lengths()

        # Test 3: Confluence con 0 señales válidas
        test_confluence_with_zero_signals()

        logger.info("\n" + "=" * 80)
        logger.info("✅ TODOS LOS TESTS PASARON EXITOSAMENTE")
        logger.info("=" * 80)

        return True

    except Exception as e:
        logger.error("\n" + "=" * 80)
        logger.error(f"❌ TESTS FALLARON: {e}")
        logger.error("=" * 80)
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
