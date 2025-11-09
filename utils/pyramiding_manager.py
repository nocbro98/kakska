"""
Pyramiding Manager
Gestor de piramidación para añadir a posiciones ganadoras

Implementa la funcionalidad allow_pyramiding del perfil Agresivo:
- Añade a posiciones cuando están en profit
- Controla número máximo de añadidos (pyramid_max_adds)
- Ajusta stop loss global
- Reduce tamaño en cada añadido (gestión de riesgo)
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime


class PyramidingManager:
    """
    Gestor de piramidación para posiciones ganadoras

    Características:
    - Solo añade si posición está en profit mínimo
    - Máximo de añadidos configurables
    - Reduce tamaño en cada añadido (50% del original)
    - Actualiza stop loss a breakeven o mejor
    - Registra todos los añadidos
    """

    def __init__(
        self,
        logger,
        max_adds: int = 2,
        min_profit_pct: float = 1.0,  # Mínimo 1% de profit para añadir
        size_reduction_factor: float = 0.5  # Cada añadido es 50% del tamaño original
    ):
        self.logger = logger
        self.max_adds = max_adds
        self.min_profit_pct = min_profit_pct
        self.size_reduction_factor = size_reduction_factor

        # Estado de piramidación por posición
        self.pyramid_state: Dict[str, Dict[str, Any]] = {}

    def initialize_position(
        self,
        symbol: str,
        entry_price: float,
        quantity: float,
        side: str
    ):
        """
        Inicializa tracking de piramidación para una posición

        Args:
            symbol: Símbolo de la posición
            entry_price: Precio de entrada original
            quantity: Cantidad original
            side: 'BUY' o 'SELL'
        """
        self.pyramid_state[symbol] = {
            'original_entry': entry_price,
            'original_quantity': quantity,
            'side': side,
            'num_adds': 0,
            'total_quantity': quantity,
            'weighted_avg_entry': entry_price,
            'add_history': [],
            'last_add_price': entry_price
        }

        self.logger.info(
            f"[PYRAMID] Initialized tracking for {symbol}: "
            f"{side} {quantity} @ {entry_price}"
        )

    def can_add_to_position(
        self,
        symbol: str,
        current_price: float
    ) -> tuple[bool, Optional[str]]:
        """
        Verifica si se puede añadir a la posición

        Args:
            symbol: Símbolo
            current_price: Precio actual del mercado

        Returns:
            (can_add: bool, reason: str if cannot)
        """
        if symbol not in self.pyramid_state:
            return False, "Position not initialized for pyramiding"

        state = self.pyramid_state[symbol]

        # Verificar número máximo de añadidos
        if state['num_adds'] >= self.max_adds:
            return False, f"Max adds reached ({self.max_adds})"

        # Calcular profit actual
        side = state['side']
        avg_entry = state['weighted_avg_entry']

        if side == 'BUY':
            profit_pct = ((current_price - avg_entry) / avg_entry) * 100
        else:  # SELL
            profit_pct = ((avg_entry - current_price) / avg_entry) * 100

        # Verificar profit mínimo
        if profit_pct < self.min_profit_pct:
            return False, f"Insufficient profit: {profit_pct:.2f}% < {self.min_profit_pct}%"

        # Verificar que el precio ha avanzado suficiente desde el último añadido
        last_add_price = state['last_add_price']

        if side == 'BUY':
            price_advance_pct = ((current_price - last_add_price) / last_add_price) * 100
        else:
            price_advance_pct = ((last_add_price - current_price) / last_add_price) * 100

        if price_advance_pct < self.min_profit_pct:
            return False, f"Price hasn't advanced enough since last add: {price_advance_pct:.2f}%"

        return True, None

    def calculate_add_size(self, symbol: str) -> float:
        """
        Calcula el tamaño del próximo añadido

        Args:
            symbol: Símbolo

        Returns:
            Cantidad a añadir
        """
        if symbol not in self.pyramid_state:
            return 0.0

        state = self.pyramid_state[symbol]
        original_qty = state['original_quantity']

        # Cada añadido es más pequeño que el anterior
        add_size = original_qty * (self.size_reduction_factor ** (state['num_adds'] + 1))

        self.logger.info(
            f"[PYRAMID] Calculated add size for {symbol}: {add_size:.8f} "
            f"(add #{state['num_adds'] + 1})"
        )

        return add_size

    def record_add(
        self,
        symbol: str,
        add_price: float,
        add_quantity: float
    ) -> Dict[str, Any]:
        """
        Registra un añadido a la posición

        Args:
            symbol: Símbolo
            add_price: Precio del añadido
            add_quantity: Cantidad añadida

        Returns:
            Estado actualizado de la posición piramidada
        """
        if symbol not in self.pyramid_state:
            self.logger.error(f"[PYRAMID] Cannot record add: {symbol} not initialized")
            return {}

        state = self.pyramid_state[symbol]

        # Calcular nuevo precio promedio ponderado
        old_total_value = state['weighted_avg_entry'] * state['total_quantity']
        add_value = add_price * add_quantity
        new_total_quantity = state['total_quantity'] + add_quantity
        new_avg_entry = (old_total_value + add_value) / new_total_quantity

        # Actualizar estado
        state['num_adds'] += 1
        state['total_quantity'] = new_total_quantity
        state['weighted_avg_entry'] = new_avg_entry
        state['last_add_price'] = add_price

        # Registrar en historial
        add_record = {
            'add_num': state['num_adds'],
            'timestamp': datetime.now().isoformat(),
            'price': add_price,
            'quantity': add_quantity,
            'new_avg_entry': new_avg_entry,
            'new_total_qty': new_total_quantity
        }

        state['add_history'].append(add_record)

        self.logger.info(
            f"[PYRAMID] Recorded add #{state['num_adds']} for {symbol}:\n"
            f"  Add: {add_quantity} @ {add_price}\n"
            f"  New Total: {new_total_quantity}\n"
            f"  New Avg Entry: {new_avg_entry:.2f}\n"
            f"  Old Avg: {old_total_value / (new_total_quantity - add_quantity):.2f}"
        )

        return state

    def calculate_new_stop_loss(
        self,
        symbol: str,
        current_price: float,
        atr: float
    ) -> Optional[float]:
        """
        Calcula nuevo stop loss tras añadir a posición

        Estrategia:
        - Mover SL a breakeven (avg entry)
        - O mejor: avg entry + pequeño profit lock

        Args:
            symbol: Símbolo
            current_price: Precio actual
            atr: ATR actual

        Returns:
            Nuevo precio de stop loss
        """
        if symbol not in self.pyramid_state:
            return None

        state = self.pyramid_state[symbol]
        avg_entry = state['weighted_avg_entry']
        side = state['side']

        # Estrategia: SL en breakeven + pequeño margen (0.5 ATR)
        if side == 'BUY':
            new_sl = avg_entry + (atr * 0.5)  # Breakeven + buffer
        else:  # SELL
            new_sl = avg_entry - (atr * 0.5)

        self.logger.info(
            f"[PYRAMID] Calculated new SL for {symbol}:\n"
            f"  Avg Entry: {avg_entry:.2f}\n"
            f"  New SL: {new_sl:.2f}\n"
            f"  Buffer: {atr * 0.5:.2f}"
        )

        return new_sl

    def get_position_state(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Obtiene estado de piramidación de una posición"""
        return self.pyramid_state.get(symbol)

    def close_position(self, symbol: str) -> Dict[str, Any]:
        """
        Cierra tracking de piramidación y retorna resumen

        Args:
            symbol: Símbolo

        Returns:
            Resumen de la posición piramidada
        """
        if symbol not in self.pyramid_state:
            return {}

        state = self.pyramid_state[symbol]

        summary = {
            'symbol': symbol,
            'original_entry': state['original_entry'],
            'original_quantity': state['original_quantity'],
            'final_avg_entry': state['weighted_avg_entry'],
            'final_quantity': state['total_quantity'],
            'num_adds': state['num_adds'],
            'add_history': state['add_history'],
            'avg_entry_improvement': (
                state['weighted_avg_entry'] - state['original_entry']
            ) if state['side'] == 'BUY' else (
                state['original_entry'] - state['weighted_avg_entry']
            )
        }

        self.logger.info(
            f"[PYRAMID] Position {symbol} closed:\n"
            f"  Original: {state['original_quantity']} @ {state['original_entry']:.2f}\n"
            f"  Final: {state['total_quantity']} @ {state['weighted_avg_entry']:.2f}\n"
            f"  Adds: {state['num_adds']}"
        )

        # Limpiar estado
        del self.pyramid_state[symbol]

        return summary

    def should_pyramid_on_signal(
        self,
        symbol: str,
        signal_side: str,
        current_price: float,
        signal_confidence: float,
        min_confidence: float = 75.0
    ) -> tuple[bool, Optional[str]]:
        """
        Verifica si se debe piramitar en base a una nueva señal

        Args:
            symbol: Símbolo
            signal_side: Lado de la señal ('BUY' o 'SELL')
            current_price: Precio actual
            signal_confidence: Confianza de la señal (0-100)
            min_confidence: Confianza mínima requerida

        Returns:
            (should_pyramid: bool, reason: str)
        """
        if symbol not in self.pyramid_state:
            return False, "No position to pyramid"

        state = self.pyramid_state[symbol]

        # Verificar que la señal va en la misma dirección
        if signal_side != state['side']:
            return False, f"Signal direction ({signal_side}) != position ({state['side']})"

        # Verificar confianza de la señal
        if signal_confidence < min_confidence:
            return False, f"Signal confidence too low: {signal_confidence:.1f}% < {min_confidence}%"

        # Verificar que se puede añadir
        can_add, reason = self.can_add_to_position(symbol, current_price)

        if not can_add:
            return False, reason

        return True, None

    def get_summary(self) -> Dict[str, Any]:
        """Retorna resumen de todas las posiciones piramidadas activas"""
        return {
            'active_pyramids': len(self.pyramid_state),
            'positions': {
                symbol: {
                    'num_adds': state['num_adds'],
                    'total_quantity': state['total_quantity'],
                    'avg_entry': state['weighted_avg_entry']
                }
                for symbol, state in self.pyramid_state.items()
            }
        }
