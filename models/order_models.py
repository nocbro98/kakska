"""
Order Models
Modelos de datos para órdenes, posiciones y trades
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
import hashlib


class OrderStatus(Enum):
    """Estados de una orden"""
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    PENDING_CANCEL = "PENDING_CANCEL"


class OrderSide(Enum):
    """Lado de la orden"""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """Tipo de orden"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"
    STOP_LIMIT = "STOP_LIMIT"
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"
    POST_ONLY = "POST_ONLY"


@dataclass
class Order:
    """
    Representa una orden con idempotencia
    clientOrderId = SYM|STRAT|TS|SEQ|HASH
    """
    symbol: str
    strategy: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None

    # Identificación idempotente
    client_order_id: Optional[str] = None
    sequence: int = 0

    # Estado
    status: OrderStatus = OrderStatus.NEW
    order_id: Optional[str] = None  # ID de Binance

    # Timestamps
    ts_create: datetime = field(default_factory=datetime.now)
    ts_sent: Optional[datetime] = None
    ts_ack: Optional[datetime] = None
    ts_filled: Optional[datetime] = None

    # Ejecución
    filled_qty: float = 0.0
    avg_fill_price: Optional[float] = None
    commission: float = 0.0
    commission_asset: str = "USDT"

    # Contexto de trading
    entry_reason: Optional[str] = None
    planned_sl: Optional[float] = None
    planned_tp: Optional[float] = None
    planned_rr: Optional[float] = None

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Generar clientOrderId si no existe"""
        if self.client_order_id is None:
            self.client_order_id = self.generate_client_order_id()

    def generate_client_order_id(self) -> str:
        """
        Genera un clientOrderId determinístico e idempotente
        Formato: SYM|STRAT|TS|SEQ|HASH
        """
        ts_str = self.ts_create.strftime("%Y%m%d%H%M%S%f")

        # Hash de entrada para garantizar unicidad
        entry_data = f"{self.symbol}{self.strategy}{self.side.value}{self.quantity}{self.price}{self.stop_price}"
        entry_hash = hashlib.md5(entry_data.encode()).hexdigest()[:8]

        return f"{self.symbol}|{self.strategy}|{ts_str}|{self.sequence}|{entry_hash}"

    def regenerate_with_next_seq(self) -> 'Order':
        """Genera una nueva orden con SEQ+1 (para reintentos tras cancel/reject)"""
        new_order = Order(
            symbol=self.symbol,
            strategy=self.strategy,
            side=self.side,
            order_type=self.order_type,
            quantity=self.quantity,
            price=self.price,
            stop_price=self.stop_price,
            sequence=self.sequence + 1,
            ts_create=datetime.now(),
            entry_reason=self.entry_reason,
            planned_sl=self.planned_sl,
            planned_tp=self.planned_tp,
            planned_rr=self.planned_rr,
            metadata=self.metadata.copy()
        )
        return new_order

    def can_retry(self) -> bool:
        """Determina si la orden puede reintentarse"""
        return self.status in [
            OrderStatus.CANCELED,
            OrderStatus.EXPIRED,
            OrderStatus.REJECTED
        ]

    def is_active(self) -> bool:
        """Determina si la orden está activa"""
        return self.status in [
            OrderStatus.NEW,
            OrderStatus.PARTIALLY_FILLED
        ]

    def is_terminal(self) -> bool:
        """Determina si la orden está en estado terminal"""
        return self.status in [
            OrderStatus.FILLED,
            OrderStatus.CANCELED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED
        ]

    def to_dict(self) -> Dict[str, Any]:
        """Convierte la orden a diccionario"""
        return {
            'symbol': self.symbol,
            'strategy': self.strategy,
            'side': self.side.value,
            'order_type': self.order_type.value,
            'quantity': self.quantity,
            'price': self.price,
            'stop_price': self.stop_price,
            'client_order_id': self.client_order_id,
            'sequence': self.sequence,
            'status': self.status.value,
            'order_id': self.order_id,
            'ts_create': self.ts_create.isoformat(),
            'ts_sent': self.ts_sent.isoformat() if self.ts_sent else None,
            'ts_ack': self.ts_ack.isoformat() if self.ts_ack else None,
            'ts_filled': self.ts_filled.isoformat() if self.ts_filled else None,
            'filled_qty': self.filled_qty,
            'avg_fill_price': self.avg_fill_price,
            'commission': self.commission,
            'entry_reason': self.entry_reason,
            'planned_sl': self.planned_sl,
            'planned_tp': self.planned_tp,
            'planned_rr': self.planned_rr,
            'metadata': self.metadata
        }


@dataclass
class Position:
    """Representa una posición abierta"""
    symbol: str
    side: OrderSide
    entry_price: float
    quantity: float
    leverage: int

    # Gestión de riesgo
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    trailing_stop: Optional[float] = None

    # Tracking
    ts_open: datetime = field(default_factory=datetime.now)
    entry_order_id: Optional[str] = None
    strategy: Optional[str] = None

    # PnL tracking
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    mae: float = 0.0  # Maximum Adverse Excursion
    mfe: float = 0.0  # Maximum Favorable Excursion

    # Costos
    commission_paid: float = 0.0
    funding_paid: float = 0.0

    def update_pnl(self, current_price: float):
        """Actualiza PnL no realizado y MAE/MFE"""
        multiplier = 1 if self.side == OrderSide.BUY else -1
        pnl_pct = multiplier * (current_price - self.entry_price) / self.entry_price * 100
        self.unrealized_pnl = pnl_pct * self.quantity * self.entry_price / 100

        # Actualizar MAE/MFE
        if pnl_pct < 0:
            self.mae = min(self.mae, pnl_pct)
        else:
            self.mfe = max(self.mfe, pnl_pct)

    def to_dict(self) -> Dict[str, Any]:
        """Convierte la posición a diccionario"""
        return {
            'symbol': self.symbol,
            'side': self.side.value,
            'entry_price': self.entry_price,
            'quantity': self.quantity,
            'leverage': self.leverage,
            'stop_loss': self.stop_loss,
            'take_profit_1': self.take_profit_1,
            'take_profit_2': self.take_profit_2,
            'take_profit_3': self.take_profit_3,
            'trailing_stop': self.trailing_stop,
            'ts_open': self.ts_open.isoformat(),
            'entry_order_id': self.entry_order_id,
            'strategy': self.strategy,
            'unrealized_pnl': self.unrealized_pnl,
            'realized_pnl': self.realized_pnl,
            'mae': self.mae,
            'mfe': self.mfe,
            'commission_paid': self.commission_paid,
            'funding_paid': self.funding_paid
        }


@dataclass
class Trade:
    """
    Representa un trade completo (ciclo de vida completo)
    Para el journal estructurado
    """
    # Identificación
    trade_id: str
    symbol: str

    # Timing
    ts_open: datetime
    ts_close: Optional[datetime] = None

    # Ejecución
    side: OrderSide = OrderSide.BUY
    entry_price: float = 0.0
    exit_price: Optional[float] = None
    quantity: float = 0.0

    # Estrategia y confluencia
    strategy_primary: Optional[str] = None
    strategies_confluence: Optional[str] = None  # "Elliott+Fibonacci+SMC"

    # Régimen de mercado
    regime_trend: Optional[str] = None  # "trend"/"range"
    regime_volatility: Optional[str] = None  # "high"/"low"

    # Tipo de entrada
    entry_type: OrderType = OrderType.MARKET

    # Plan vs Realidad
    plan_rr: Optional[float] = None
    r_achieved: Optional[float] = None

    # Tamaño
    size_nominal: float = 0.0

    # Costos
    fees: float = 0.0
    funding: float = 0.0
    slippage_real: float = 0.0

    # Excursiones
    mae: float = 0.0  # Maximum Adverse Excursion (%)
    mfe: float = 0.0  # Maximum Favorable Excursion (%)

    # Salida
    reason_exit: Optional[str] = None  # "TP"/"SL"/"TS"/"timeout"/"manual"

    # Metadata
    notes: Optional[str] = None
    profile: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convierte el trade a diccionario para CSV/SQLite"""
        return {
            'trade_id': self.trade_id,
            'ts_open': self.ts_open.isoformat(),
            'ts_close': self.ts_close.isoformat() if self.ts_close else None,
            'symbol': self.symbol,
            'profile': self.profile,
            'strategy_primary': self.strategy_primary,
            'strategies_confluence': self.strategies_confluence,
            'regime_trend': self.regime_trend,
            'regime_volatility': self.regime_volatility,
            'entry_type': self.entry_type.value if isinstance(self.entry_type, OrderType) else self.entry_type,
            'plan_rr': self.plan_rr,
            'r_achieved': self.r_achieved,
            'size_nominal': self.size_nominal,
            'fees': self.fees,
            'funding': self.funding,
            'slippage_real': self.slippage_real,
            'mae': self.mae,
            'mfe': self.mfe,
            'reason_exit': self.reason_exit,
            'notes': self.notes,
            'side': self.side.value if isinstance(self.side, OrderSide) else self.side,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'quantity': self.quantity
        }
