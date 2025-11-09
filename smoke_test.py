#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smoke Test - Verificación básica de integración

Valida que el sistema pueda:
1. Cargar configuración
2. Inicializar componentes sin errores
3. Conectarse a Binance Testnet (requiere credenciales válidas)
4. Ejecutar un ciclo de decisión
5. Cerrar limpiamente

NO ejecuta órdenes reales.
"""

import sys
import os
from pathlib import Path

# Agregar directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent))

# Cargar .env
from dotenv import load_dotenv
load_dotenv()

from main_trading_system import TradingSystem, load_config_from_env


def smoke_test():
    """
    Smoke test básico

    Returns:
        bool: True si pasa, False si falla
    """
    print("=" * 80)
    print("SMOKE TEST - INTEGRATION VALIDATION")
    print("=" * 80)

    try:
        # 1. Cargar configuración
        print("\n[1/5] Loading configuration...")
        config = load_config_from_env()
        print(f"  ✓ Configuration loaded")
        print(f"    - Testnet: {config['testnet']}")
        print(f"    - Symbol: {config['symbol']}")
        print(f"    - Profile: {config['risk_profile']}")

        # 2. Crear sistema
        print("\n[2/5] Creating TradingSystem...")
        system = TradingSystem(
            api_key=config['api_key'],
            api_secret=config['api_secret'],
            testnet=config['testnet'],
            risk_profile=config['risk_profile'],
            symbol=config['symbol'],
            leverage=config['leverage'],
            loop_interval=config['loop_interval']
        )
        print("  ✓ TradingSystem created")

        # 3. Inicializar
        print("\n[3/5] Initializing system...")
        if not system.initialize():
            print("  ✗ Initialization failed")
            return False
        print("  ✓ System initialized successfully")

        # 4. Ejecutar 1 iteración del loop
        print("\n[4/5] Running one trading loop iteration...")
        system.run(max_iterations=1)
        print("  ✓ Trading loop executed")

        # 5. Cerrar limpiamente
        print("\n[5/5] Shutting down...")
        system.shutdown()
        print("  ✓ System shutdown complete")

        print("\n" + "=" * 80)
        print("✅ SMOKE TEST PASSED")
        print("=" * 80)
        return True

    except Exception as e:
        print(f"\n❌ SMOKE TEST FAILED")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        print("=" * 80)
        return False


if __name__ == "__main__":
    success = smoke_test()
    sys.exit(0 if success else 1)
