#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Order Registry
Registro de órdenes con idempotencia basada en clientOrderId determinístico

Características:
- clientOrderId determinístico: SYM|STRAT|TS|SEQ|HASH
- Prevención de órdenes duplicadas
- Regeneración con SEQ+1 tras cancel/reject
- Integración con StateStore y EventBus
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from core.event_bus import EventBus, EventType
from core.state_store import StateStore
from models.order_models import Order, OrderStatus


class OrderRegistry:
    """
    Registro centralizado de órdenes con garantía de idempotencia

    El registro garantiza que:
    - No se envíen órdenes duplicadas
    - Los reintentos tras errores de red no creen duplicados
    - Las órdenes se persisten antes de enviar
    - Se emiten eventos para observabilidad
    """

    def __init__(self, state_store: StateStore, event_bus: EventBus):
        """
        Args:
            state_store: Almacén de estado persistente
            event_bus: Bus de eventos
        """
        self.state_store = state_store
        self.event_bus = event_bus
        self.logger = logging.getLogger("OrderRegistry")

        # Cache en memoria de órdenes activas (por performance)
        self._active_orders: Dict[str, Order] = {}

        # Cargar órdenes activas desde state_store
        self._load_active_orders()

        self.logger.info("OrderRegistry initialized")

    def _load_active_orders(self):
        """Carga órdenes activas desde el StateStore"""
        try:
            # Cargar órdenes en estado activo (NEW, PARTIALLY_FILLED)
            active_statuses = [OrderStatus.NEW.value, OrderStatus.PARTIALLY_FILLED.value]

            for status in active_statuses:
                orders = self.state_store.get_orders_by_status(status)
                for order_dict in orders:
                    client_order_id = order_dict.get('client_order_id')
                    if client_order_id:
                        # Reconstruir Order desde dict
                        order = self._dict_to_order(order_dict)
                        self._active_orders[client_order_id] = order

            self.logger.info(f"Loaded {len(self._active_orders)} active orders from StateStore")

        except Exception as e:
            self.logger.error(f"Error loading active orders: {e}", exc_info=True)

    def register_order(self, order: Order) -> bool:
        """
        Registra una orden nueva

        Verificaciones:
        - Si el clientOrderId ya existe → rechazar (duplicada)
        - Si la orden tiene estado terminal → permitir solo si can_retry()

        Args:
            order: Orden a registrar

        Returns:
            True si la orden se registró (es nueva o se puede reintentar)
            False si la orden está duplicada o no se puede registrar
        """
        client_order_id = order.client_order_id

        # Verificar si ya existe
        existing_order = self._active_orders.get(client_order_id)

        if existing_order:
            # Orden ya registrada
            if existing_order.is_active():
                self.logger.warning(
                    f"Order {client_order_id} already registered and active (status: {existing_order.status.value})"
                )
                return False

            elif existing_order.is_terminal():
                # Orden en estado terminal
                if not existing_order.can_retry():
                    self.logger.warning(
                        f"Order {client_order_id} is in terminal state {existing_order.status.value} "
                        f"and cannot be retried"
                    )
                    return False

                # Orden terminal pero puede reintentarse
                # (usuario debe usar regenerate_with_next_seq() para nuevo clientOrderId)
                self.logger.warning(
                    f"Order {client_order_id} is in terminal state {existing_order.status.value}. "
                    f"Use regenerate_with_next_seq() for retry."
                )
                return False

        # Orden nueva o puede reintentarse
        try:
            # Persistir en StateStore
            order_dict = order.to_dict()
            if not self.state_store.save_order(order_dict):
                self.logger.error(f"Failed to save order {client_order_id} to StateStore")
                return False

            # Agregar a cache
            self._active_orders[client_order_id] = order

            # Emitir evento
            self.event_bus.publish(
                EventType.ORDER_CREATED,
                {
                    'client_order_id': client_order_id,
                    'symbol': order.symbol,
                    'strategy': order.strategy,
                    'side': order.side.value,
                    'quantity': order.quantity,
                    'price': order.price,
                    'order_type': order.order_type.value
                },
                source='OrderRegistry'
            )

            self.logger.info(
                f"Order registered: {order.symbol} {order.side.value} {order.quantity} @ {order.price} "
                f"(strategy: {order.strategy}, client_order_id: {client_order_id})"
            )

            return True

        except Exception as e:
            self.logger.error(f"Error registering order: {e}", exc_info=True)
            return False

    def update_order_status(
        self,
        client_order_id: str,
        new_status: OrderStatus,
        order_id: Optional[str] = None,
        filled_qty: Optional[float] = None,
        avg_fill_price: Optional[float] = None,
        commission: Optional[float] = None
    ) -> bool:
        """
        Actualiza el estado de una orden

        Args:
            client_order_id: ID de cliente de la orden
            new_status: Nuevo estado
            order_id: ID de Binance (si está disponible)
            filled_qty: Cantidad llenada
            avg_fill_price: Precio promedio de llenado
            commission: Comisión pagada

        Returns:
            True si se actualizó correctamente
        """
        order = self._active_orders.get(client_order_id)

        if not order:
            # Buscar en StateStore
            order_dict = self.state_store.get_order(client_order_id)
            if not order_dict:
                self.logger.warning(f"Order {client_order_id} not found in registry")
                return False

            order = self._dict_to_order(order_dict)

        # Actualizar campos
        order.status = new_status

        if order_id:
            order.order_id = order_id

        if filled_qty is not None:
            order.filled_qty = filled_qty

        if avg_fill_price is not None:
            order.avg_fill_price = avg_fill_price

        if commission is not None:
            order.commission = commission

        # Actualizar timestamps según estado
        now = datetime.now()
        if new_status == OrderStatus.NEW and not order.ts_sent:
            order.ts_sent = now
        elif new_status in [OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED] and not order.ts_ack:
            order.ts_ack = now
        elif new_status == OrderStatus.FILLED:
            order.ts_filled = now

        # Persistir
        try:
            order_dict = order.to_dict()
            if not self.state_store.save_order(order_dict):
                self.logger.error(f"Failed to save order update for {client_order_id}")
                return False

            # Actualizar cache
            if order.is_active():
                self._active_orders[client_order_id] = order
            else:
                # Orden terminal, remover de cache
                self._active_orders.pop(client_order_id, None)

            # Emitir evento correspondiente
            event_type = self._get_event_type_for_status(new_status)
            if event_type:
                self.event_bus.publish(
                    event_type,
                    {
                        'client_order_id': client_order_id,
                        'order_id': order_id,
                        'status': new_status.value,
                        'symbol': order.symbol,
                        'filled_qty': filled_qty,
                        'avg_fill_price': avg_fill_price
                    },
                    source='OrderRegistry'
                )

            self.logger.info(
                f"Order {client_order_id} updated: {new_status.value} "
                f"(filled: {filled_qty}/{order.quantity})"
            )

            return True

        except Exception as e:
            self.logger.error(f"Error updating order status: {e}", exc_info=True)
            return False

    def get_order(self, client_order_id: str) -> Optional[Order]:
        """Obtiene una orden por su clientOrderId"""
        # Buscar en cache
        order = self._active_orders.get(client_order_id)
        if order:
            return order

        # Buscar en StateStore
        order_dict = self.state_store.get_order(client_order_id)
        if order_dict:
            return self._dict_to_order(order_dict)

        return None

    def get_active_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        Obtiene todas las órdenes activas

        Args:
            symbol: Filtrar por símbolo (opcional)

        Returns:
            Lista de órdenes activas
        """
        orders = list(self._active_orders.values())

        if symbol:
            orders = [o for o in orders if o.symbol == symbol]

        return orders

    def get_all_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        Obtiene todas las órdenes (activas e históricas)

        Args:
            symbol: Filtrar por símbolo (opcional)

        Returns:
            Lista de todas las órdenes
        """
        order_dicts = self.state_store.get_all_orders(symbol)
        return [self._dict_to_order(od) for od in order_dicts]

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas del registro"""
        active_orders = len(self._active_orders)

        # Contar por estrategia
        by_strategy = {}
        for order in self._active_orders.values():
            by_strategy[order.strategy] = by_strategy.get(order.strategy, 0) + 1

        # Contar por símbolo
        by_symbol = {}
        for order in self._active_orders.values():
            by_symbol[order.symbol] = by_symbol.get(order.symbol, 0) + 1

        return {
            'active_orders': active_orders,
            'by_strategy': by_strategy,
            'by_symbol': by_symbol
        }

    def _get_event_type_for_status(self, status: OrderStatus) -> Optional[EventType]:
        """Mapea OrderStatus a EventType"""
        mapping = {
            OrderStatus.NEW: EventType.ORDER_ACCEPTED,
            OrderStatus.PARTIALLY_FILLED: EventType.ORDER_PARTIAL_FILL,
            OrderStatus.FILLED: EventType.ORDER_FILLED,
            OrderStatus.CANCELED: EventType.ORDER_CANCELED,
            OrderStatus.REJECTED: EventType.ORDER_REJECTED
        }
        return mapping.get(status)

    def _dict_to_order(self, order_dict: Dict[str, Any]) -> Order:
        """Reconstruye un objeto Order desde un diccionario"""
        from models.order_models import OrderSide, OrderType

        return Order(
            symbol=order_dict['symbol'],
            strategy=order_dict['strategy'],
            side=OrderSide[order_dict['side']],
            order_type=OrderType[order_dict['order_type']],
            quantity=order_dict['quantity'],
            price=order_dict.get('price'),
            stop_price=order_dict.get('stop_price'),
            client_order_id=order_dict['client_order_id'],
            sequence=order_dict['sequence'],
            status=OrderStatus[order_dict['status']],
            order_id=order_dict.get('order_id'),
            ts_create=datetime.fromisoformat(order_dict['ts_create']),
            ts_sent=datetime.fromisoformat(order_dict['ts_sent']) if order_dict.get('ts_sent') else None,
            ts_ack=datetime.fromisoformat(order_dict['ts_ack']) if order_dict.get('ts_ack') else None,
            ts_filled=datetime.fromisoformat(order_dict['ts_filled']) if order_dict.get('ts_filled') else None,
            filled_qty=order_dict.get('filled_qty', 0),
            avg_fill_price=order_dict.get('avg_fill_price'),
            commission=order_dict.get('commission', 0),
            entry_reason=order_dict.get('entry_reason'),
            planned_sl=order_dict.get('planned_sl'),
            planned_tp=order_dict.get('planned_tp'),
            planned_rr=order_dict.get('planned_rr')
        )
