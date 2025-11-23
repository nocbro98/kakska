"""
Integration Patches
Sistema de Monkey Patching para inyectar telemetría del bot legacy hacia la GUI moderna.

Implementa el patrón Proxy para interceptar métodos clave del TradingBot y
despachar eventos de estado a través de una cola thread-safe.
"""

import time
from queue import Queue
from typing import Optional


def create_bot_patches(original_class, ui_queue: Optional[Queue] = None):
    """
    Aplica Monkey Patching a la clase TradingBot para inyectar
    telemetría hacia la GUI moderna.

    Args:
        original_class: La clase TradingBot a parchear
        ui_queue: Cola compartida para enviar eventos a la GUI (Thread-safe FIFO)

    Returns:
        La clase parcheada con telemetría inyectada
    """

    # ===== 1. CAPTURA DE REFERENCIAS (Method Preservation) =====
    # Guardamos punteros a los métodos originales para no romper la lógica base
    _original_health_check = original_class.health_check
    _original_init = original_class.__init__

    # ===== 2. INYECCIÓN DE DEPENDENCIAS EN EL CONSTRUCTOR =====
    def patched_init(self, *args, **kwargs):
        """
        Constructor parcheado que inyecta la cola UI en la instancia del bot.

        Dependency Injection Pattern: El bot original no conoce la GUI.
        Al modificar __init__, le pasamos la referencia de memoria de ui_queue.
        Esto permite que el backend tenga un canal de escritura hacia el frontend.
        """
        # Ejecutar inicialización original
        _original_init(self, *args, **kwargs)

        # Inyectar cola UI
        self.ui_queue = ui_queue

        # Debug logging
        if ui_queue is not None:
            print(f"✓ UI Queue inyectada en TradingBot (qsize: {ui_queue.qsize()})")
        else:
            print("⚠ UI Queue no proporcionada - telemetría deshabilitada")

    # ===== 3. IMPLEMENTACIÓN DEL WRAPPER (Interceptor) PARA HEALTH_CHECK =====
    def patched_health_check(self):
        """
        Wrapper de health_check que agrega despacho de estado a la GUI.

        Proxy Pattern: No reescribimos la lógica de Binance (eso sería peligroso).
        En su lugar, "envolvemos" la función:

        1. _original_health_check(self): Hace la llamada API a Binance,
           actualiza self.balance y verifica conectividad.

        2. Post-execution hook: Una vez que el estado interno está fresco,
           leemos ese valor y lo enviamos a la GUI.
        """

        # A. EJECUCIÓN DE LA LÓGICA BASE (Critical Path)
        # Esto asegura que el bot siga calculando su balance y conexión con Binance
        _original_health_check(self)

        # B. DISPATCH DE EVENTOS A LA GUI (Side Effect seguro)
        if hasattr(self, 'ui_queue') and self.ui_queue is not None:
            try:
                # ===== EXTRACCIÓN DE ESTADO (State Harvesting) =====
                # Usamos getattr con fallbacks para evitar AttributeErrors

                # Balance
                current_balance = getattr(self, 'balance', 0.0)
                if not current_balance and hasattr(self, 'order_manager'):
                    try:
                        current_balance = self.order_manager.get_account_balance()
                    except:
                        current_balance = 0.0

                # Posición actual
                current_position = None
                unrealized_pnl = 0.0
                if hasattr(self, 'order_manager') and self.order_manager.current_position_data:
                    current_position = self.order_manager.current_position_data
                    unrealized_pnl = current_position.get('unrealized_pnl', 0.0)

                # Estado de conexión
                is_connected = getattr(self, 'is_running', False)

                # ===== CONSTRUCCIÓN DEL PAYLOAD (DTO - Data Transfer Object) =====

                # Payload 1: Estado de conexión
                status_payload = {
                    'type': 'status',
                    'data': 'running' if is_connected else 'stopped'
                }

                # Payload 2: Balance y PnL
                balance_payload = {
                    'type': 'balance',
                    'data': {
                        'available_balance': float(current_balance),
                        'total_wallet_balance': float(current_balance),
                        'unrealized_pnl': float(unrealized_pnl)
                    }
                }

                # Payload 3: Posición (si existe)
                if current_position:
                    position_payload = {
                        'type': 'position',
                        'data': {
                            'symbol': current_position.get('symbol', 'N/A'),
                            'side': current_position.get('side', 'N/A'),
                            'quantity': float(current_position.get('quantity', 0)),
                            'entry_price': float(current_position.get('entry_price', 0)),
                            'unrealized_pnl': float(unrealized_pnl)
                        }
                    }
                    self.ui_queue.put(position_payload)

                # ===== ENCOLADO (Producing) - Non-blocking put =====
                self.ui_queue.put(status_payload)
                self.ui_queue.put(balance_payload)

            except Exception as e:
                # Silent Catch: No queremos que un error de UI detenga el hilo de Trading
                print(f"WARNING: Fallo en serialización de estado a GUI: {str(e)}")

    # ===== 4. APLICACIÓN DEL PARCHE (Runtime Binding) =====
    original_class.__init__ = patched_init
    original_class.health_check = patched_health_check

    return original_class


def apply_patches_to_bot_instance(bot_instance, ui_queue: Queue):
    """
    Aplica patches a una instancia ya creada del bot (alternativa al patching de clase).

    Útil si el bot ya fue instanciado antes de poder parchear la clase.

    Args:
        bot_instance: Instancia del TradingBot
        ui_queue: Cola para despachar eventos
    """
    # Inyectar cola
    bot_instance.ui_queue = ui_queue

    # Capturar método original
    _original_health_check = bot_instance.health_check

    # Crear wrapper
    def patched_health_check():
        _original_health_check()

        if hasattr(bot_instance, 'ui_queue') and bot_instance.ui_queue is not None:
            try:
                current_balance = getattr(bot_instance, 'balance', 0.0)
                if not current_balance and hasattr(bot_instance, 'order_manager'):
                    try:
                        current_balance = bot_instance.order_manager.get_account_balance()
                    except:
                        current_balance = 0.0

                is_connected = getattr(bot_instance, 'is_running', False)

                status_payload = {
                    'type': 'status',
                    'data': 'running' if is_connected else 'stopped'
                }

                balance_payload = {
                    'type': 'balance',
                    'data': {
                        'available_balance': float(current_balance),
                        'total_wallet_balance': float(current_balance),
                        'unrealized_pnl': 0.0
                    }
                }

                bot_instance.ui_queue.put(status_payload)
                bot_instance.ui_queue.put(balance_payload)

            except Exception as e:
                print(f"WARNING: Fallo en serialización de estado a GUI: {str(e)}")

    # Reemplazar método
    bot_instance.health_check = patched_health_check

    print("✓ Patches aplicados a instancia del bot")
