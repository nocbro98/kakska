#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Circuit Breaker Manager
Disyuntor con estados y umbrales configurables por perfil

Características:
- Estados: closed, open, half-open
- Umbrales por categoría (red, lógica, exchange)
- Ventana temporal configurable
- Integración con eventos y alertas
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Callable, Dict, Any, Tuple

from core.event_bus import EventBus, EventType
from core.state_store import StateStore
from models.risk_models import RiskMetrics, CircuitBreakerState


# Perfiles de riesgo predefinidos
RISK_PROFILES = {
    'conservador': {
        'daily_loss_limit_pct': 2.5,
        'weekly_loss_limit_pct': 5.0,
        'monthly_loss_limit_pct': 10.0,
        'max_consecutive_losses': 4,
        'max_positions': 2
    },
    'normal': {
        'daily_loss_limit_pct': 3.0,
        'weekly_loss_limit_pct': 6.0,
        'monthly_loss_limit_pct': 10.0,
        'max_consecutive_losses': 4,
        'max_positions': 3
    },
    'agresivo': {
        'daily_loss_limit_pct': 5.0,
        'weekly_loss_limit_pct': 8.0,
        'monthly_loss_limit_pct': 15.0,
        'max_consecutive_losses': 5,
        'max_positions': 5
    }
}


class CircuitBreakerManager:
    """
    Gestor de circuit breakers con estados y umbrales

    Estados:
    - RUNNING: Operando normalmente
    - PAUSED_DAILY/WEEKLY/MONTHLY: Pausado por pérdidas
    - PAUSED_STREAK: Pausado por racha de pérdidas
    - MANUAL_LOCK: Pausado manualmente
    """

    def __init__(
        self,
        state_store: StateStore,
        event_bus: EventBus,
        risk_profile: str = 'normal',
        alert_callback: Optional[Callable[[str], None]] = None
    ):
        """
        Args:
            state_store: Almacén de estado
            event_bus: Bus de eventos
            risk_profile: Perfil de riesgo ('conservador', 'normal', 'agresivo')
            alert_callback: Callback para alertas críticas
        """
        self.state_store = state_store
        self.event_bus = event_bus
        self.risk_profile = risk_profile
        self.alert_callback = alert_callback
        self.logger = logging.getLogger("CircuitBreaker")

        # Inicializar métricas de riesgo
        profile_config = RISK_PROFILES.get(risk_profile, RISK_PROFILES['normal'])
        self.risk_metrics = RiskMetrics(
            daily_loss_limit_pct=profile_config['daily_loss_limit_pct'],
            weekly_loss_limit_pct=profile_config['weekly_loss_limit_pct'],
            monthly_loss_limit_pct=profile_config['monthly_loss_limit_pct'],
            max_consecutive_losses=profile_config['max_consecutive_losses'],
            max_positions=profile_config['max_positions']
        )

        self.logger.info(f"CircuitBreaker initialized with profile: {risk_profile}")

    def update_balance(self, new_balance: float):
        """Actualiza el balance y recalcula drawdown"""
        if self.risk_metrics.initial_balance == 0:
            self.risk_metrics.initial_balance = new_balance

        self.risk_metrics.update_balance(new_balance)

    def register_trade_result(self, pnl: float, is_win: bool):
        """
        Registra el resultado de un trade

        Args:
            pnl: PnL del trade
            is_win: Si el trade fue ganador
        """
        self.risk_metrics.add_trade_result(pnl, is_win)

        # Verificar circuit breakers
        triggered, reason = self.risk_metrics.check_circuit_breakers()

        if triggered:
            self.logger.critical(f"Circuit Breaker TRIGGERED: {reason}")

            # Emitir evento
            self.event_bus.publish(
                EventType.CIRCUIT_BREAKER_OPENED,
                {
                    'state': self.risk_metrics.cb_state.value,
                    'reason': reason,
                    'balance': self.risk_metrics.balance
                },
                source='CircuitBreaker'
            )

            # Enviar alerta crítica
            if self.alert_callback:
                self.alert_callback(
                    f"🔴 CIRCUIT BREAKER ACTIVADO\n"
                    f"Motivo: {reason}\n"
                    f"Balance: ${self.risk_metrics.balance:.2f}\n"
                    f"Estado: {self.risk_metrics.cb_state.value}"
                )

    def can_trade(self) -> Tuple[bool, Optional[str]]:
        """
        Verifica si se puede operar

        Returns:
            (puede_operar, razón)
        """
        # Verificar si puede reanudar automáticamente
        if self.risk_metrics.can_resume_trading():
            self.resume_trading()

        if self.risk_metrics.cb_state == CircuitBreakerState.RUNNING:
            return True, None

        return False, self.risk_metrics.cb_reason

    def manual_pause(self, reason: str):
        """Pausa manual del sistema"""
        self.risk_metrics.cb_state = CircuitBreakerState.MANUAL_LOCK
        self.risk_metrics.cb_reason = reason
        self.risk_metrics.cb_triggered_at = datetime.now()
        self.risk_metrics.cb_resume_at = None  # Requiere reanudación manual

        self.logger.warning(f"Manual pause: {reason}")

        self.event_bus.publish(
            EventType.CIRCUIT_BREAKER_OPENED,
            {'state': CircuitBreakerState.MANUAL_LOCK.value, 'reason': reason},
            source='CircuitBreaker'
        )

    def manual_resume(self):
        """Reanuda el sistema manualmente"""
        if self.risk_metrics.cb_state == CircuitBreakerState.MANUAL_LOCK:
            self.risk_metrics.resume_trading()
            self.logger.info("System manually resumed")

            self.event_bus.publish(
                EventType.CIRCUIT_BREAKER_CLOSED,
                {'state': CircuitBreakerState.RUNNING.value},
                source='CircuitBreaker'
            )

    def resume_trading(self):
        """Reanuda el trading tras circuit breaker automático"""
        self.risk_metrics.resume_trading()
        self.logger.info("Trading resumed")

        self.event_bus.publish(
            EventType.CIRCUIT_BREAKER_CLOSED,
            {'state': CircuitBreakerState.RUNNING.value},
            source='CircuitBreaker'
        )

    def get_status(self) -> Dict[str, Any]:
        """Retorna el estado completo del circuit breaker"""
        return {
            'state': self.risk_metrics.cb_state.value,
            'can_trade': self.risk_metrics.cb_state == CircuitBreakerState.RUNNING,
            'reason': self.risk_metrics.cb_reason,
            'balance': self.risk_metrics.balance,
            'peak_balance': self.risk_metrics.peak_balance,
            'current_dd_pct': self.risk_metrics.current_dd_pct,
            'max_dd_pct': self.risk_metrics.max_dd_pct,
            'daily_pnl': self.risk_metrics.daily_pnl,
            'weekly_pnl': self.risk_metrics.weekly_pnl,
            'monthly_pnl': self.risk_metrics.monthly_pnl,
            'consecutive_losses': self.risk_metrics.consecutive_losses,
            'num_open_positions': self.risk_metrics.num_open_positions,
            'profile': self.risk_profile,
            'limits': {
                'daily_loss_pct': self.risk_metrics.daily_loss_limit_pct,
                'weekly_loss_pct': self.risk_metrics.weekly_loss_limit_pct,
                'monthly_loss_pct': self.risk_metrics.monthly_loss_limit_pct,
                'max_consecutive_losses': self.risk_metrics.max_consecutive_losses,
                'max_positions': self.risk_metrics.max_positions
            }
        }
