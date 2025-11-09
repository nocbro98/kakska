#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Connection Manager
Gestiona conexiones con Binance y reconcilia estado al arranque

Características:
- Reconexión y reintento con política exponencial acotada
- Reconciliación al arranque: lee órdenes abiertas y posiciones
- Alinea con OrderRegistry y StateStore
- Rate limiting con backoff
- Clasificación de errores por dominio
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException

from core.event_bus import EventBus, EventType
from core.state_store import StateStore
from core.order_registry import OrderRegistry
from models.order_models import Order, OrderSide, OrderType, OrderStatus


class ErrorCategory(Enum):
    """Categorías de errores"""
    NETWORK = "network"           # Errores de red o timeout
    RATE_LIMIT = "rate_limit"     # Límite de tasa
    EXCHANGE = "exchange"         # Errores del exchange (códigos específicos)
    VALIDATION = "validation"     # Errores de validación
    UNKNOWN = "unknown"


class ConnectionManager:
    """
    Gestor de conexiones con Binance

    Responsabilidades:
    - Conectar con Binance (Testnet o Mainnet)
    - Reconciliar estado al arranque
    - Reintentar con backoff exponencial
    - Clasificar errores por categoría
    - Emitir eventos para circuit breaker
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool,
        state_store: StateStore,
        event_bus: EventBus,
        order_registry: OrderRegistry,
        max_retries: int = 4
    ):
        """
        Args:
            api_key: API key de Binance
            api_secret: API secret de Binance
            testnet: Si True, usa Binance Testnet
            state_store: Almacén de estado
            event_bus: Bus de eventos
            order_registry: Registro de órdenes
            max_retries: Máximo número de reintentos
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.state_store = state_store
        self.event_bus = event_bus
        self.order_registry = order_registry
        self.max_retries = max_retries

        self.logger = logging.getLogger("ConnectionManager")

        # Cliente de Binance
        self.client: Optional[Client] = None

        # Estado de conexión
        self.connected = False

        # Contadores de errores por categoría (para circuit breaker)
        self.error_counts = {
            ErrorCategory.NETWORK: 0,
            ErrorCategory.RATE_LIMIT: 0,
            ErrorCategory.EXCHANGE: 0,
            ErrorCategory.VALIDATION: 0,
            ErrorCategory.UNKNOWN: 0
        }

        self.logger.info(f"ConnectionManager initialized (testnet={testnet})")

    def connect(self) -> bool:
        """
        Conecta con Binance

        Returns:
            True si la conexión fue exitosa
        """
        try:
            if self.testnet:
                # Binance Futures Testnet
                self.client = Client(
                    self.api_key,
                    self.api_secret,
                    testnet=True
                )
                # Configurar base URL para Futures Testnet
                self.client.API_URL = 'https://testnet.binancefuture.com/fapi'
            else:
                # Binance Futures Mainnet
                self.client = Client(self.api_key, self.api_secret)

            # Probar conexión obteniendo server time
            server_time = self.client.futures_time()
            self.logger.info(f"Connected to Binance (server time: {server_time['serverTime']})")

            self.connected = True

            # Emitir evento
            self.event_bus.publish(
                EventType.SYSTEM_STARTUP,
                {'component': 'ConnectionManager', 'testnet': self.testnet},
                source='ConnectionManager'
            )

            return True

        except Exception as e:
            self.logger.error(f"Failed to connect to Binance: {e}", exc_info=True)
            self.connected = False
            return False

    def disconnect(self):
        """Desconecta de Binance"""
        self.client = None
        self.connected = False
        self.logger.info("Disconnected from Binance")

    def reconcile_on_startup(self, symbol: str) -> Dict[str, Any]:
        """
        Reconcilia el estado al arranque

        Pasos:
        1. Lee órdenes abiertas en Binance
        2. Lee posiciones abiertas en Binance
        3. Compara con estado local (StateStore / OrderRegistry)
        4. Sincroniza diferencias:
           - Órdenes en exchange pero no en local → adoptar
           - Órdenes en local pero no en exchange → marcar como huérfanas
           - Posiciones en exchange pero no en local → adoptar
           - Posiciones en local pero no en exchange → eliminar

        Args:
            symbol: Símbolo a reconciliar

        Returns:
            Diccionario con resultado de la reconciliación
        """
        if not self.connected:
            return {'success': False, 'error': 'Not connected'}

        self.logger.info(f"Starting reconciliation for {symbol}...")

        try:
            # 1. Obtener órdenes abiertas en exchange
            exchange_orders = self._get_open_orders_from_exchange(symbol)
            self.logger.info(f"Found {len(exchange_orders)} open orders in exchange")

            # 2. Obtener posiciones abiertas en exchange
            exchange_positions = self._get_positions_from_exchange(symbol)
            self.logger.info(f"Found {len(exchange_positions)} open positions in exchange")

            # 3. Obtener estado local
            local_orders = self.order_registry.get_active_orders(symbol)
            local_positions = self.state_store.get_all_positions()

            self.logger.info(f"Found {len(local_orders)} active orders in local registry")
            self.logger.info(f"Found {len(local_positions)} positions in local state")

            # 4. Reconciliar órdenes
            orders_adopted = 0
            orders_orphaned = 0

            # Mapear órdenes del exchange por order_id
            exchange_orders_map = {o['orderId']: o for o in exchange_orders}

            # Verificar órdenes locales
            for local_order in local_orders:
                if local_order.order_id:
                    if local_order.order_id not in exchange_orders_map:
                        # Orden local no está en exchange → huérfana
                        self.logger.warning(
                            f"Orphaned order detected: {local_order.client_order_id} "
                            f"(order_id: {local_order.order_id})"
                        )
                        # Marcar como cancelada
                        self.order_registry.update_order_status(
                            local_order.client_order_id,
                            OrderStatus.CANCELED
                        )
                        orders_orphaned += 1

            # Verificar órdenes del exchange
            for exchange_order in exchange_orders:
                order_id = str(exchange_order['orderId'])
                client_order_id = exchange_order.get('clientOrderId')

                # Verificar si existe en local
                local_order = None
                if client_order_id:
                    local_order = self.order_registry.get_order(client_order_id)

                if not local_order:
                    # Orden en exchange no está en local → adoptar
                    self.logger.info(f"Adopting order from exchange: {order_id}")
                    self._adopt_exchange_order(exchange_order)
                    orders_adopted += 1

            # 5. Reconciliar posiciones
            positions_adopted = 0
            positions_removed = 0

            # Mapear posiciones del exchange por symbol
            exchange_positions_map = {p['symbol']: p for p in exchange_positions}

            # Verificar posiciones locales
            for local_position in local_positions:
                pos_symbol = local_position['symbol']
                if pos_symbol not in exchange_positions_map:
                    # Posición local no está en exchange → eliminar
                    self.logger.warning(f"Removing stale local position: {pos_symbol}")
                    self.state_store.delete_position(pos_symbol)
                    positions_removed += 1

            # Verificar posiciones del exchange
            for exchange_position in exchange_positions:
                pos_symbol = exchange_position['symbol']
                local_position = self.state_store.get_position(pos_symbol)

                if not local_position:
                    # Posición en exchange no está en local → adoptar
                    self.logger.info(f"Adopting position from exchange: {pos_symbol}")
                    self._adopt_exchange_position(exchange_position)
                    positions_adopted += 1

            self.logger.info(
                f"Reconciliation complete: "
                f"orders adopted={orders_adopted}, orphaned={orders_orphaned}, "
                f"positions adopted={positions_adopted}, removed={positions_removed}"
            )

            return {
                'success': True,
                'orders_adopted': orders_adopted,
                'orders_orphaned': orders_orphaned,
                'positions_adopted': positions_adopted,
                'positions_removed': positions_removed,
                'open_orders': len(exchange_orders),
                'open_positions': len(exchange_positions)
            }

        except Exception as e:
            self.logger.error(f"Error during reconciliation: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def _get_open_orders_from_exchange(self, symbol: str) -> List[Dict[str, Any]]:
        """Obtiene órdenes abiertas del exchange"""
        try:
            orders = self.client.futures_get_open_orders(symbol=symbol)
            return orders
        except Exception as e:
            self.logger.error(f"Error getting open orders: {e}")
            return []

    def _get_positions_from_exchange(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Obtiene posiciones abiertas del exchange"""
        try:
            positions = self.client.futures_position_information(symbol=symbol)
            # Filtrar solo posiciones con cantidad > 0
            open_positions = [
                p for p in positions
                if float(p.get('positionAmt', 0)) != 0
            ]
            return open_positions
        except Exception as e:
            self.logger.error(f"Error getting positions: {e}")
            return []

    def _adopt_exchange_order(self, exchange_order: Dict[str, Any]):
        """Adopta una orden del exchange al estado local"""
        try:
            # Crear Order desde datos del exchange
            order = Order(
                symbol=exchange_order['symbol'],
                strategy='unknown',  # No conocemos la estrategia
                side=OrderSide.BUY if exchange_order['side'] == 'BUY' else OrderSide.SELL,
                order_type=OrderType[exchange_order['type']],
                quantity=float(exchange_order['origQty']),
                price=float(exchange_order['price']) if exchange_order.get('price') else None,
                client_order_id=exchange_order.get('clientOrderId', f"adopted_{exchange_order['orderId']}"),
                order_id=str(exchange_order['orderId']),
                status=OrderStatus[exchange_order['status']]
            )

            # Registrar
            self.order_registry.register_order(order)

        except Exception as e:
            self.logger.error(f"Error adopting exchange order: {e}", exc_info=True)

    def _adopt_exchange_position(self, exchange_position: Dict[str, Any]):
        """Adopta una posición del exchange al estado local"""
        try:
            from models.order_models import Position

            position_amt = float(exchange_position['positionAmt'])
            entry_price = float(exchange_position['entryPrice'])

            position = Position(
                symbol=exchange_position['symbol'],
                side=OrderSide.BUY if position_amt > 0 else OrderSide.SELL,
                entry_price=entry_price,
                quantity=abs(position_amt),
                leverage=int(exchange_position.get('leverage', 1)),
                unrealized_pnl=float(exchange_position.get('unRealizedProfit', 0))
            )

            # Guardar
            self.state_store.save_position(position.to_dict())

        except Exception as e:
            self.logger.error(f"Error adopting exchange position: {e}", exc_info=True)

    def get_account_balance(self) -> float:
        """
        Obtiene el balance de la cuenta (USDT disponible)

        Returns:
            Balance en USDT
        """
        if not self.connected:
            return 0.0

        try:
            account = self.client.futures_account()

            for asset in account.get('assets', []):
                if asset['asset'] == 'USDT':
                    return float(asset['availableBalance'])

            return 0.0

        except Exception as e:
            self.logger.error(f"Error getting account balance: {e}")
            return 0.0

    def execute_with_retry(
        self,
        func,
        *args,
        **kwargs
    ) -> Tuple[Optional[Any], Optional[ErrorCategory]]:
        """
        Ejecuta una función con reintento exponencial

        Args:
            func: Función a ejecutar
            *args: Argumentos posicionales
            **kwargs: Argumentos keyword

        Returns:
            (result, error_category)
        """
        for attempt in range(self.max_retries + 1):
            try:
                result = func(*args, **kwargs)
                return result, None

            except BinanceAPIException as e:
                error_category = self._classify_binance_error(e)
                self.error_counts[error_category] += 1

                if error_category == ErrorCategory.RATE_LIMIT:
                    # Rate limit: esperar más tiempo
                    backoff = min(2 ** attempt, 16)  # Máximo 16s
                    self.logger.warning(
                        f"Rate limit hit (attempt {attempt+1}/{self.max_retries+1}), "
                        f"waiting {backoff}s"
                    )
                    time.sleep(backoff)

                elif error_category == ErrorCategory.NETWORK:
                    # Error de red: reintentar con backoff
                    backoff = min(2 ** attempt, 16)
                    self.logger.warning(
                        f"Network error (attempt {attempt+1}/{self.max_retries+1}), "
                        f"waiting {backoff}s: {e}"
                    )
                    time.sleep(backoff)

                elif error_category == ErrorCategory.EXCHANGE:
                    # Error del exchange: no reintentar
                    self.logger.error(f"Exchange error: {e}")
                    return None, error_category

                elif error_category == ErrorCategory.VALIDATION:
                    # Error de validación: no reintentar
                    self.logger.error(f"Validation error: {e}")
                    return None, error_category

                else:
                    # Error desconocido: reintentar una vez
                    if attempt < 1:
                        time.sleep(2)
                    else:
                        return None, error_category

            except BinanceRequestException as e:
                # Error de request (red, timeout)
                self.error_counts[ErrorCategory.NETWORK] += 1

                backoff = min(2 ** attempt, 16)
                self.logger.warning(
                    f"Request error (attempt {attempt+1}/{self.max_retries+1}), "
                    f"waiting {backoff}s: {e}"
                )
                time.sleep(backoff)

            except Exception as e:
                # Error desconocido
                self.error_counts[ErrorCategory.UNKNOWN] += 1
                self.logger.error(f"Unknown error: {e}", exc_info=True)
                return None, ErrorCategory.UNKNOWN

        # Agotó reintentos
        self.logger.error(f"Max retries exceeded for {func.__name__}")
        return None, ErrorCategory.NETWORK

    def _classify_binance_error(self, e: BinanceAPIException) -> ErrorCategory:
        """
        Clasifica un error de Binance por categoría

        Args:
            e: Excepción de Binance

        Returns:
            Categoría del error
        """
        code = e.code

        # Rate limiting
        if code == -1003:  # TOO_MANY_REQUESTS
            return ErrorCategory.RATE_LIMIT

        # Errores del exchange (no reintentar)
        if code in [-2019, -1013, -1021, -4000]:
            # -2019: Margin insufficient
            # -1013: Invalid quantity
            # -1021: Timestamp outside recv window
            # -4000: Invalid price
            return ErrorCategory.EXCHANGE

        # Errores de red / timeout
        if code in [-1001, -1007]:
            # -1001: Disconnected
            # -1007: Timeout
            return ErrorCategory.NETWORK

        # Por defecto, considerarlo de exchange
        return ErrorCategory.EXCHANGE

    def get_error_stats(self) -> Dict[str, int]:
        """Retorna estadísticas de errores"""
        return {cat.value: count for cat, count in self.error_counts.items()}

    def reset_error_counts(self):
        """Resetea contadores de errores"""
        for cat in self.error_counts:
            self.error_counts[cat] = 0
