"""
Robust Order Execution Manager
Sistema robusto de ejecución de órdenes con verificación y reintentos

Mejoras sobre OrderManager básico:
- Verificación de SL/TP colocados correctamente
- Reintentos automáticos con backoff exponencial
- Protección contra posiciones sin stop-loss
- Logging detallado de cada paso
"""

import logging
import time
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from binance.client import Client
from binance.exceptions import BinanceAPIException


class RobustOrderExecutor:
    """
    Ejecutor robusto de órdenes con verificación y reintentos

    Características:
    - Verifica que SL/TP se coloquen correctamente
    - Reintenta automáticamente si falla
    - Cierra posición si no puede colocar SL
    - Registra todo en logs detallados
    """

    def __init__(
        self,
        client: Client,
        symbol: str,
        logger,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        self.client = client
        self.symbol = symbol
        self.logger = logger
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def execute_entry_with_protection(
        self,
        side: str,
        quantity: float,
        stop_loss: float,
        take_profits: List[Tuple[float, float]],  # [(price, qty), ...]
        entry_type: str = "MARKET",
        entry_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Ejecuta entrada completa con protección garantizada

        Args:
            side: 'BUY' o 'SELL'
            quantity: Cantidad total
            stop_loss: Precio de stop loss
            take_profits: Lista de (precio, cantidad) para TPs
            entry_type: 'MARKET' o 'LIMIT'
            entry_price: Precio límite si entry_type='LIMIT'

        Returns:
            Dict con resultado:
                {
                    'success': bool,
                    'entry_order': dict,
                    'sl_order': dict,
                    'tp_orders': list,
                    'errors': list
                }
        """
        result = {
            'success': False,
            'entry_order': None,
            'sl_order': None,
            'tp_orders': [],
            'errors': []
        }

        try:
            # PASO 1: Ejecutar orden de entrada
            self.logger.info(f"[ROBUST] Step 1: Executing {entry_type} {side} order")

            entry_order = self._execute_entry_order(
                side=side,
                quantity=quantity,
                order_type=entry_type,
                price=entry_price
            )

            if not entry_order:
                result['errors'].append("Failed to execute entry order")
                return result

            result['entry_order'] = entry_order
            self.logger.info(f"[ROBUST] ✓ Entry order executed: {entry_order['orderId']}")

            # PASO 2: Colocar Stop Loss (CRÍTICO)
            self.logger.info(f"[ROBUST] Step 2: Placing CRITICAL stop loss at {stop_loss}")

            sl_order = self._place_stop_loss_with_verification(
                side=side,
                quantity=quantity,
                stop_price=stop_loss
            )

            if not sl_order:
                # CRÍTICO: No pudimos colocar SL, cerrar posición inmediatamente
                self.logger.critical(
                    "[ROBUST] ⚠️ CRITICAL: Failed to place stop loss! "
                    "Closing position immediately for safety."
                )

                # Intentar cerrar posición
                self._emergency_close_position(side, quantity)

                result['errors'].append("Failed to place stop loss - position closed")
                return result

            result['sl_order'] = sl_order
            self.logger.info(f"[ROBUST] ✓ Stop loss placed: {sl_order['orderId']}")

            # PASO 3: Colocar Take Profits (opcional pero importante)
            self.logger.info(f"[ROBUST] Step 3: Placing {len(take_profits)} take profit orders")

            for i, (tp_price, tp_qty) in enumerate(take_profits, 1):
                tp_order = self._place_take_profit_with_retry(
                    side=side,
                    quantity=tp_qty,
                    price=tp_price,
                    label=f"TP{i}"
                )

                if tp_order:
                    result['tp_orders'].append(tp_order)
                    self.logger.info(f"[ROBUST] ✓ TP{i} placed: {tp_order['orderId']}")
                else:
                    self.logger.warning(f"[ROBUST] ⚠️ Failed to place TP{i}")
                    result['errors'].append(f"Failed to place TP{i}")

            # Verificar cobertura total
            total_tp_qty = sum(qty for _, qty in take_profits)
            placed_tp_qty = sum(float(tp['origQty']) for tp in result['tp_orders'])

            if abs(placed_tp_qty - total_tp_qty) > 0.001:
                self.logger.warning(
                    f"[ROBUST] ⚠️ TP coverage incomplete: "
                    f"planned={total_tp_qty}, placed={placed_tp_qty}"
                )

            # TODO: Aquí podríamos reajustar TPs si falta cobertura

            result['success'] = True
            self.logger.info(
                f"[ROBUST] ✅ Order execution complete: "
                f"Entry + SL + {len(result['tp_orders'])}/{len(take_profits)} TPs"
            )

            return result

        except Exception as e:
            self.logger.error(f"[ROBUST] Fatal error during order execution: {e}", exc_info=True)
            result['errors'].append(f"Fatal error: {str(e)}")
            return result

    def _execute_entry_order(
        self,
        side: str,
        quantity: float,
        order_type: str,
        price: Optional[float] = None
    ) -> Optional[Dict]:
        """Ejecuta orden de entrada con reintentos"""

        for attempt in range(1, self.max_retries + 1):
            try:
                if order_type == "MARKET":
                    order = self.client.futures_create_order(
                        symbol=self.symbol,
                        side=side,
                        type='MARKET',
                        quantity=quantity
                    )
                else:  # LIMIT
                    order = self.client.futures_create_order(
                        symbol=self.symbol,
                        side=side,
                        type='LIMIT',
                        timeInForce='GTC',
                        quantity=quantity,
                        price=price
                    )

                return order

            except BinanceAPIException as e:
                self.logger.warning(
                    f"[ROBUST] Entry order attempt {attempt}/{self.max_retries} failed: {e}"
                )

                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** (attempt - 1))  # Backoff exponencial
                    time.sleep(delay)
                else:
                    self.logger.error(f"[ROBUST] Entry order failed after {self.max_retries} attempts")
                    return None

            except Exception as e:
                self.logger.error(f"[ROBUST] Unexpected error in entry order: {e}")
                return None

        return None

    def _place_stop_loss_with_verification(
        self,
        side: str,
        quantity: float,
        stop_price: float
    ) -> Optional[Dict]:
        """
        Coloca stop loss con verificación obligatoria

        Si falla todos los reintentos, retorna None
        """
        opposite_side = 'SELL' if side == 'BUY' else 'BUY'

        for attempt in range(1, self.max_retries + 1):
            try:
                # Colocar SL
                sl_order = self.client.futures_create_order(
                    symbol=self.symbol,
                    side=opposite_side,
                    type='STOP_MARKET',
                    stopPrice=stop_price,
                    quantity=quantity,
                    closePosition=False
                )

                # VERIFICAR que se colocó
                time.sleep(0.5)  # Pequeña pausa para que se registre

                # Buscar en órdenes abiertas
                open_orders = self.client.futures_get_open_orders(symbol=self.symbol)
                sl_found = any(
                    o['orderId'] == sl_order['orderId']
                    for o in open_orders
                )

                if sl_found:
                    self.logger.info(f"[ROBUST] Stop loss verified in open orders")
                    return sl_order
                else:
                    self.logger.warning(
                        f"[ROBUST] Stop loss placed but not found in open orders (attempt {attempt})"
                    )

                    if attempt < self.max_retries:
                        time.sleep(self.retry_delay * attempt)
                    else:
                        return None

            except BinanceAPIException as e:
                self.logger.warning(
                    f"[ROBUST] SL placement attempt {attempt}/{self.max_retries} failed: {e}"
                )

                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** (attempt - 1))
                    time.sleep(delay)
                else:
                    return None

            except Exception as e:
                self.logger.error(f"[ROBUST] Unexpected error placing SL: {e}")
                return None

        return None

    def _place_take_profit_with_retry(
        self,
        side: str,
        quantity: float,
        price: float,
        label: str = "TP"
    ) -> Optional[Dict]:
        """Coloca take profit con reintentos"""
        opposite_side = 'SELL' if side == 'BUY' else 'BUY'

        for attempt in range(1, self.max_retries + 1):
            try:
                tp_order = self.client.futures_create_order(
                    symbol=self.symbol,
                    side=opposite_side,
                    type='LIMIT',
                    timeInForce='GTC',
                    quantity=quantity,
                    price=price
                )

                return tp_order

            except BinanceAPIException as e:
                self.logger.warning(
                    f"[ROBUST] {label} placement attempt {attempt}/{self.max_retries} failed: {e}"
                )

                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * attempt)
                else:
                    return None

            except Exception as e:
                self.logger.error(f"[ROBUST] Unexpected error placing {label}: {e}")
                return None

        return None

    def _emergency_close_position(self, side: str, quantity: float):
        """Cierra posición de emergencia si no se pudo colocar SL"""
        opposite_side = 'SELL' if side == 'BUY' else 'BUY'

        try:
            self.logger.critical("[ROBUST] Executing EMERGENCY close position")

            close_order = self.client.futures_create_order(
                symbol=self.symbol,
                side=opposite_side,
                type='MARKET',
                quantity=quantity
            )

            self.logger.critical(
                f"[ROBUST] Emergency close executed: {close_order['orderId']}"
            )

            return close_order

        except Exception as e:
            self.logger.critical(
                f"[ROBUST] ⚠️⚠️⚠️ CRITICAL: Emergency close FAILED: {e}\n"
                f"MANUAL INTERVENTION REQUIRED!\n"
                f"Position: {side} {quantity} {self.symbol} WITHOUT STOP LOSS"
            )
            return None

    def update_stop_loss(
        self,
        current_sl_order_id: int,
        new_stop_price: float,
        side: str,
        quantity: float
    ) -> Optional[Dict]:
        """
        Actualiza stop loss cancelando el anterior y colocando uno nuevo

        Args:
            current_sl_order_id: ID de la orden SL actual
            new_stop_price: Nuevo precio de stop
            side: Lado de la posición original ('BUY' o 'SELL')
            quantity: Cantidad

        Returns:
            Nueva orden SL o None si falla
        """
        try:
            # Cancelar SL anterior
            self.logger.info(f"[ROBUST] Canceling old SL: {current_sl_order_id}")

            self.client.futures_cancel_order(
                symbol=self.symbol,
                orderId=current_sl_order_id
            )

            # Colocar nuevo SL con verificación
            self.logger.info(f"[ROBUST] Placing new SL at {new_stop_price}")

            new_sl = self._place_stop_loss_with_verification(
                side=side,
                quantity=quantity,
                stop_price=new_stop_price
            )

            if new_sl:
                self.logger.info(f"[ROBUST] ✓ SL updated successfully")
                return new_sl
            else:
                self.logger.critical(
                    "[ROBUST] ⚠️ CRITICAL: Failed to place new SL after canceling old one!\n"
                    "Position is now UNPROTECTED"
                )
                return None

        except Exception as e:
            self.logger.error(f"[ROBUST] Error updating SL: {e}", exc_info=True)
            return None

    def verify_all_orders(self, expected_order_ids: List[int]) -> Dict[str, Any]:
        """
        Verifica que todas las órdenes esperadas estén activas

        Returns:
            {
                'all_present': bool,
                'missing': list,
                'present': list
            }
        """
        try:
            open_orders = self.client.futures_get_open_orders(symbol=self.symbol)
            open_order_ids = [o['orderId'] for o in open_orders]

            present = [oid for oid in expected_order_ids if oid in open_order_ids]
            missing = [oid for oid in expected_order_ids if oid not in open_order_ids]

            return {
                'all_present': len(missing) == 0,
                'missing': missing,
                'present': present
            }

        except Exception as e:
            self.logger.error(f"[ROBUST] Error verifying orders: {e}")
            return {
                'all_present': False,
                'missing': expected_order_ids,
                'present': []
            }
