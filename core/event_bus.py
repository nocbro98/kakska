#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Event Bus
Sistema pub/sub thread-safe para comunicación entre componentes

Características:
- Thread-safe con locks
- Colas internas con backpressure
- Método no bloqueante para publicar desde hilos de datos
- Enumeraciones de eventos operativos
"""

import logging
import threading
from datetime import datetime
from enum import Enum
from queue import Queue, Full
from typing import Callable, Dict, List, Any, Optional
from dataclasses import dataclass


class EventType(Enum):
    """Tipos de eventos del sistema"""
    # Market Data
    MARKET_TICK = "market_tick"
    MARKET_ORDERBOOK_UPDATE = "market_orderbook_update"

    # Estrategias
    SIGNAL_GENERATED = "signal_generated"
    SIGNAL_CONFLUENCE = "signal_confluence"

    # Órdenes
    ORDER_CREATED = "order_created"
    ORDER_SENT = "order_sent"
    ORDER_ACCEPTED = "order_accepted"
    ORDER_REJECTED = "order_rejected"
    ORDER_PARTIAL_FILL = "order_partial_fill"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELED = "order_canceled"

    # Posiciones
    POSITION_OPENED = "position_opened"
    POSITION_UPDATED = "position_updated"
    POSITION_CLOSED = "position_closed"

    # Régimen
    REGIME_CHANGED = "regime_changed"

    # Risk & Circuit Breakers
    RISK_LIMIT_WARNING = "risk_limit_warning"
    CIRCUIT_BREAKER_OPENED = "circuit_breaker_opened"
    CIRCUIT_BREAKER_CLOSED = "circuit_breaker_closed"
    CIRCUIT_BREAKER_HALF_OPEN = "circuit_breaker_half_open"

    # System
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"
    SYSTEM_ERROR = "system_error"
    HEARTBEAT = "heartbeat"


@dataclass
class Event:
    """Representa un evento del sistema"""
    event_type: EventType
    data: Dict[str, Any]
    timestamp: datetime
    source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'event_type': self.event_type.value,
            'data': self.data,
            'timestamp': self.timestamp.isoformat(),
            'source': self.source
        }


class EventBus:
    """
    Bus de eventos pub/sub thread-safe

    Características:
    - Thread-safe con locks
    - Suscripciones por tipo de evento
    - Cola interna para evitar bloqueos
    - Backpressure si la cola se llena
    """

    def __init__(self, max_queue_size: int = 10000):
        """
        Args:
            max_queue_size: Tamaño máximo de la cola interna
        """
        self.max_queue_size = max_queue_size
        self.logger = logging.getLogger("EventBus")

        # Suscriptores por tipo de evento
        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._lock = threading.RLock()

        # Cola interna para procesamiento asíncrono
        self._event_queue: Queue = Queue(maxsize=max_queue_size)

        # Worker thread
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False

        # Estadísticas
        self._stats = {
            'events_published': 0,
            'events_processed': 0,
            'events_dropped': 0,
            'queue_full_count': 0
        }
        self._stats_lock = threading.Lock()

    def start(self):
        """Inicia el worker thread del bus"""
        if self._running:
            self.logger.warning("EventBus already running")
            return

        self._running = True
        self._worker_thread = threading.Thread(target=self._process_events, daemon=True)
        self._worker_thread.start()
        self.logger.info("EventBus started")

    def stop(self):
        """Detiene el worker thread del bus"""
        if not self._running:
            return

        self.logger.info("Stopping EventBus...")
        self._running = False

        if self._worker_thread:
            self._worker_thread.join(timeout=5)

        self.logger.info("EventBus stopped")

    def subscribe(self, event_type: EventType, callback: Callable[[Event], None]):
        """
        Suscribe un callback a un tipo de evento

        Args:
            event_type: Tipo de evento
            callback: Función callback que recibe el evento
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []

            if callback not in self._subscribers[event_type]:
                self._subscribers[event_type].append(callback)
                self.logger.debug(f"Subscribed {callback.__name__} to {event_type.value}")

    def unsubscribe(self, event_type: EventType, callback: Callable[[Event], None]):
        """
        Desuscribe un callback de un tipo de evento

        Args:
            event_type: Tipo de evento
            callback: Función callback a eliminar
        """
        with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(callback)
                    self.logger.debug(f"Unsubscribed {callback.__name__} from {event_type.value}")
                except ValueError:
                    pass

    def publish(
        self,
        event_type: EventType,
        data: Dict[str, Any],
        source: Optional[str] = None,
        blocking: bool = False
    ) -> bool:
        """
        Publica un evento (no bloqueante por defecto)

        Args:
            event_type: Tipo de evento
            data: Datos del evento
            source: Fuente del evento
            blocking: Si True, bloquea hasta que el evento se encole

        Returns:
            True si el evento se encoló, False si se descartó por cola llena
        """
        event = Event(
            event_type=event_type,
            data=data,
            timestamp=datetime.now(),
            source=source
        )

        try:
            if blocking:
                self._event_queue.put(event, block=True)
            else:
                self._event_queue.put(event, block=False)

            with self._stats_lock:
                self._stats['events_published'] += 1

            return True

        except Full:
            # Cola llena - aplicar backpressure
            with self._stats_lock:
                self._stats['events_dropped'] += 1
                self._stats['queue_full_count'] += 1

            self.logger.warning(
                f"Event queue full ({self.max_queue_size}), "
                f"dropping event: {event_type.value}"
            )
            return False

    def publish_sync(self, event_type: EventType, data: Dict[str, Any], source: Optional[str] = None):
        """
        Publica un evento de forma síncrona (entrega inmediata a suscriptores)

        Args:
            event_type: Tipo de evento
            data: Datos del evento
            source: Fuente del evento
        """
        event = Event(
            event_type=event_type,
            data=data,
            timestamp=datetime.now(),
            source=source
        )

        self._dispatch_event(event)

        with self._stats_lock:
            self._stats['events_published'] += 1
            self._stats['events_processed'] += 1

    def _process_events(self):
        """Worker thread que procesa eventos de la cola"""
        self.logger.info("EventBus worker thread started")

        while self._running:
            try:
                # Timeout para poder chequear _running periódicamente
                event = self._event_queue.get(timeout=0.1)
                self._dispatch_event(event)

                with self._stats_lock:
                    self._stats['events_processed'] += 1

            except Exception as e:
                if self._running:  # Solo loguear si no es shutdown
                    self.logger.error(f"Error processing event: {e}", exc_info=True)

        # Procesar eventos restantes en la cola
        while not self._event_queue.empty():
            try:
                event = self._event_queue.get_nowait()
                self._dispatch_event(event)
            except Exception:
                break

        self.logger.info("EventBus worker thread stopped")

    def _dispatch_event(self, event: Event):
        """
        Despacha un evento a todos los suscriptores

        Args:
            event: Evento a despachar
        """
        with self._lock:
            subscribers = self._subscribers.get(event.event_type, []).copy()

        for callback in subscribers:
            try:
                callback(event)
            except Exception as e:
                self.logger.error(
                    f"Error in subscriber {callback.__name__} for {event.event_type.value}: {e}",
                    exc_info=True
                )

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas del bus"""
        with self._stats_lock:
            return {
                **self._stats,
                'queue_size': self._event_queue.qsize(),
                'queue_capacity': self.max_queue_size,
                'num_subscribers': sum(len(subs) for subs in self._subscribers.values()),
                'running': self._running
            }

    def clear_stats(self):
        """Limpia las estadísticas"""
        with self._stats_lock:
            self._stats = {
                'events_published': 0,
                'events_processed': 0,
                'events_dropped': 0,
                'queue_full_count': 0
            }
