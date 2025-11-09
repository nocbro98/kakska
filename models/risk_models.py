"""
Risk Models
Modelos para gestión de riesgo y circuit breakers
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, List


class CircuitBreakerState(Enum):
    """Estados del circuit breaker"""
    RUNNING = "RUNNING"
    PAUSED_DAILY = "PAUSED_DAILY"
    PAUSED_WEEKLY = "PAUSED_WEEKLY"
    PAUSED_MONTHLY = "PAUSED_MONTHLY"
    PAUSED_STREAK = "PAUSED_STREAK"
    MANUAL_LOCK = "MANUAL_LOCK"


@dataclass
class RiskMetrics:
    """Métricas de riesgo en tiempo real"""
    # Balance
    balance: float = 0.0
    initial_balance: float = 0.0

    # Drawdown
    peak_balance: float = 0.0
    current_dd_pct: float = 0.0
    max_dd_pct: float = 0.0

    # Pérdidas/Ganancias por período
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    monthly_pnl: float = 0.0

    # Límites de pérdidas (en % del balance inicial del período)
    daily_loss_limit_pct: float = 3.0
    weekly_loss_limit_pct: float = 6.0
    monthly_loss_limit_pct: float = 10.0

    # Racha de pérdidas
    consecutive_losses: int = 0
    max_consecutive_losses: int = 4

    # Exposición
    total_exposure_usdt: float = 0.0
    num_open_positions: int = 0
    max_positions: int = 2

    # Circuit breaker
    cb_state: CircuitBreakerState = CircuitBreakerState.RUNNING
    cb_reason: Optional[str] = None
    cb_triggered_at: Optional[datetime] = None
    cb_resume_at: Optional[datetime] = None

    # Timestamps de inicio de períodos
    period_start_daily: datetime = field(default_factory=datetime.now)
    period_start_weekly: datetime = field(default_factory=datetime.now)
    period_start_monthly: datetime = field(default_factory=datetime.now)

    def update_balance(self, new_balance: float):
        """Actualiza balance y calcula drawdown"""
        self.balance = new_balance

        # Actualizar peak
        if new_balance > self.peak_balance:
            self.peak_balance = new_balance

        # Calcular DD actual
        if self.peak_balance > 0:
            self.current_dd_pct = (self.peak_balance - new_balance) / self.peak_balance * 100
            self.max_dd_pct = max(self.max_dd_pct, self.current_dd_pct)

    def add_trade_result(self, pnl: float, is_win: bool):
        """Registra resultado de un trade"""
        self.daily_pnl += pnl
        self.weekly_pnl += pnl
        self.monthly_pnl += pnl

        if is_win:
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1

    def check_circuit_breakers(self) -> tuple[bool, Optional[str]]:
        """
        Verifica si se debe activar algún circuit breaker

        Returns:
            (should_trigger: bool, reason: str)
        """
        if self.cb_state != CircuitBreakerState.RUNNING:
            return True, self.cb_reason

        # Verificar pérdida diaria
        daily_loss_pct = (self.daily_pnl / self.initial_balance) * 100
        if daily_loss_pct <= -self.daily_loss_limit_pct:
            self.trigger_circuit_breaker(
                CircuitBreakerState.PAUSED_DAILY,
                f"Pérdida diaria: {daily_loss_pct:.2f}% (límite: {self.daily_loss_limit_pct}%)",
                hours=24
            )
            return True, self.cb_reason

        # Verificar pérdida semanal
        weekly_loss_pct = (self.weekly_pnl / self.initial_balance) * 100
        if weekly_loss_pct <= -self.weekly_loss_limit_pct:
            self.trigger_circuit_breaker(
                CircuitBreakerState.PAUSED_WEEKLY,
                f"Pérdida semanal: {weekly_loss_pct:.2f}% (límite: {self.weekly_loss_limit_pct}%)",
                hours=48
            )
            return True, self.cb_reason

        # Verificar pérdida mensual
        monthly_loss_pct = (self.monthly_pnl / self.initial_balance) * 100
        if monthly_loss_pct <= -self.monthly_loss_limit_pct:
            self.trigger_circuit_breaker(
                CircuitBreakerState.PAUSED_MONTHLY,
                f"Pérdida mensual: {monthly_loss_pct:.2f}% (límite: {self.monthly_loss_limit_pct}%)",
                hours=None  # Requiere revisión manual
            )
            return True, self.cb_reason

        # Verificar racha de pérdidas
        if self.consecutive_losses >= self.max_consecutive_losses:
            self.trigger_circuit_breaker(
                CircuitBreakerState.PAUSED_STREAK,
                f"Racha de {self.consecutive_losses} pérdidas consecutivas",
                hours=12
            )
            return True, self.cb_reason

        return False, None

    def trigger_circuit_breaker(self, state: CircuitBreakerState, reason: str, hours: Optional[int]):
        """Activa un circuit breaker"""
        self.cb_state = state
        self.cb_reason = reason
        self.cb_triggered_at = datetime.now()

        if hours is not None:
            self.cb_resume_at = self.cb_triggered_at + timedelta(hours=hours)
        else:
            self.cb_resume_at = None  # Requiere intervención manual

    def can_resume_trading(self) -> bool:
        """Verifica si se puede reanudar el trading"""
        if self.cb_state == CircuitBreakerState.RUNNING:
            return True

        if self.cb_state == CircuitBreakerState.MANUAL_LOCK:
            return False

        if self.cb_resume_at is None:
            return False  # Requiere intervención manual

        return datetime.now() >= self.cb_resume_at

    def resume_trading(self):
        """Reanuda el trading tras circuit breaker"""
        self.cb_state = CircuitBreakerState.RUNNING
        self.cb_reason = None
        self.cb_triggered_at = None
        self.cb_resume_at = None

    def reset_period(self, period: str):
        """Resetea métricas de un período específico"""
        now = datetime.now()
        if period == 'daily':
            self.daily_pnl = 0.0
            self.period_start_daily = now
        elif period == 'weekly':
            self.weekly_pnl = 0.0
            self.period_start_weekly = now
        elif period == 'monthly':
            self.monthly_pnl = 0.0
            self.period_start_monthly = now

    def to_dict(self):
        """Convierte las métricas a diccionario"""
        return {
            'balance': self.balance,
            'peak_balance': self.peak_balance,
            'current_dd_pct': self.current_dd_pct,
            'max_dd_pct': self.max_dd_pct,
            'daily_pnl': self.daily_pnl,
            'weekly_pnl': self.weekly_pnl,
            'monthly_pnl': self.monthly_pnl,
            'consecutive_losses': self.consecutive_losses,
            'total_exposure_usdt': self.total_exposure_usdt,
            'num_open_positions': self.num_open_positions,
            'cb_state': self.cb_state.value,
            'cb_reason': self.cb_reason,
            'cb_triggered_at': self.cb_triggered_at.isoformat() if self.cb_triggered_at else None,
            'cb_resume_at': self.cb_resume_at.isoformat() if self.cb_resume_at else None
        }
