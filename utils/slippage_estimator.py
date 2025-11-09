"""
Slippage Estimator
Estimación de slippage y selector de tipo de orden
"""
import logging
from typing import Dict, Optional, Tuple
from enum import Enum

from models.order_models import OrderType


class SlippageEstimator:
    """
    Estimador de slippage y selector de tipo de orden

    Política:
    - Definir budget: max(spread_tolerado, pct_slippage, ticks)
    - Si la mejor ejecución esperada supera el budget → cancelar o post-only
    - Selector:
      * market para rupturas con urgencia (régimen tendencial + liquidez alta)
      * limit/post-only para entradas de posicionamiento (rango/squeeze)
      * trigger (stop) para breakouts planeados
    """

    def __init__(
        self,
        max_slippage_pct: float = 0.1,  # 0.1% máximo
        max_spread_pct: float = 0.05,   # 0.05% spread máximo
        min_liquidity_usdt: float = 10000  # $10k mínimo en orderbook
    ):
        self.max_slippage_pct = max_slippage_pct
        self.max_spread_pct = max_spread_pct
        self.min_liquidity_usdt = min_liquidity_usdt
        self.logger = logging.getLogger("SlippageEstimator")

    def estimate_slippage(
        self,
        side: str,
        quantity: float,
        bid: float,
        ask: float,
        bid_qty: float,
        ask_qty: float
    ) -> Tuple[float, bool, str]:
        """
        Estima el slippage esperado

        Args:
            side: 'BUY' o 'SELL'
            quantity: Cantidad a operar
            bid: Mejor bid
            ask: Mejor ask
            bid_qty: Cantidad en mejor bid
            ask_qty: Cantidad en mejor ask

        Returns:
            (slippage_pct, acceptable, reason)
        """
        # Calcular spread
        mid_price = (bid + ask) / 2
        spread_pct = (ask - bid) / mid_price * 100

        # Si spread > límite, rechazar
        if spread_pct > self.max_spread_pct:
            return spread_pct, False, f"Spread too wide: {spread_pct:.3f}% > {self.max_spread_pct}%"

        # Estimar slippage según liquidez
        if side == 'BUY':
            available_liquidity = ask * ask_qty
            slippage_pct = spread_pct / 2  # Aproximación: mitad del spread
        else:
            available_liquidity = bid * bid_qty
            slippage_pct = spread_pct / 2

        # Si liquidez insuficiente, aumentar slippage estimado
        required_liquidity = quantity * mid_price
        if available_liquidity < required_liquidity:
            liquidity_ratio = required_liquidity / available_liquidity
            slippage_pct *= liquidity_ratio
            self.logger.warning(
                f"Insufficient liquidity: required ${required_liquidity:.0f}, "
                f"available ${available_liquidity:.0f}"
            )

        # Verificar si slippage es aceptable
        acceptable = slippage_pct <= self.max_slippage_pct

        if not acceptable:
            reason = f"Slippage too high: {slippage_pct:.3f}% > {self.max_slippage_pct}%"
        else:
            reason = f"Slippage acceptable: {slippage_pct:.3f}%"

        return slippage_pct, acceptable, reason

    def select_order_type(
        self,
        strategy_type: str,
        regime_trend: str,
        is_urgent: bool,
        slippage_pct: float
    ) -> Tuple[OrderType, str]:
        """
        Selecciona el tipo de orden óptimo

        Args:
            strategy_type: Tipo de estrategia
            regime_trend: Régimen de tendencia
            is_urgent: Si requiere ejecución urgente
            slippage_pct: Slippage estimado

        Returns:
            (order_type, reason)
        """
        # Market para rupturas urgentes en tendencia
        if is_urgent and regime_trend in ['trending_up', 'trending_down']:
            if slippage_pct <= self.max_slippage_pct:
                return OrderType.MARKET, "Urgent breakout in trending market"
            else:
                # Slippage muy alto, usar limit
                return OrderType.LIMIT, "High slippage, using limit order"

        # Post-only para rangos/squeeze
        if regime_trend in ['ranging', 'squeeze']:
            return OrderType.POST_ONLY, "Range/squeeze regime, using post-only"

        # Limit por defecto
        return OrderType.LIMIT, "Default limit order"

    def calculate_limit_price(
        self,
        side: str,
        mid_price: float,
        slippage_budget_pct: float = 0.05
    ) -> float:
        """
        Calcula precio límite con budget de slippage

        Args:
            side: 'BUY' o 'SELL'
            mid_price: Precio mid actual
            slippage_budget_pct: Budget de slippage (%)

        Returns:
            Precio límite
        """
        if side == 'BUY':
            # Para compra: mid + slippage
            limit_price = mid_price * (1 + slippage_budget_pct / 100)
        else:
            # Para venta: mid - slippage
            limit_price = mid_price * (1 - slippage_budget_pct / 100)

        return limit_price

    def log_execution_analysis(
        self,
        symbol: str,
        side: str,
        bid: float,
        ask: float,
        slippage_estimated: float,
        order_type: OrderType,
        reason: str
    ):
        """Log análisis de ejecución"""
        spread = ask - bid
        spread_pct = (ask - bid) / ((bid + ask) / 2) * 100

        self.logger.info(
            f"Execution Analysis for {symbol} {side}:\n"
            f"  Bid/Ask: {bid:.2f} / {ask:.2f} (spread: {spread_pct:.3f}%)\n"
            f"  Estimated slippage: {slippage_estimated:.3f}%\n"
            f"  Order type selected: {order_type.value}\n"
            f"  Reason: {reason}"
        )
