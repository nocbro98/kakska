#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Base Strategy
Clase base para todas las estrategias con validaciones robustas
"""

import logging
import numpy as np
from abc import ABC, abstractmethod
from typing import Tuple, List, Optional
from core.confluence_engine import StrategySignal


class BaseStrategy(ABC):
    """
    Clase base para estrategias

    Características:
    - Validación de longitud de datos ANTES de cualquier operación
    - Early returns con signal=0 cuando no hay datos suficientes
    - Logging claro de por qué no se genera señal
    - Sin excepciones no controladas
    """

    def __init__(self, name: str, min_bars_required: int):
        """
        Args:
            name: Nombre de la estrategia
            min_bars_required: Mínimo de barras requeridas
        """
        self.name = name
        self.min_bars_required = min_bars_required
        self.logger = logging.getLogger(f"Strategy.{name}")

    @abstractmethod
    def analyze(
        self,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        opens: np.ndarray,
        volumes: Optional[np.ndarray] = None
    ) -> StrategySignal:
        """
        Analiza datos y genera una señal

        IMPORTANTE:
        - SIEMPRE validar longitud ANTES de indexar
        - Retornar StrategySignal(signal=0, confidence=0.0) si datos insuficientes
        - Usar np.clip() para índices calculados
        - Validar que i-k >= 0 antes de acceder

        Args:
            closes: Precios de cierre
            highs: Precios máximos
            lows: Precios mínimos
            opens: Precios de apertura
            volumes: Volúmenes (opcional)

        Returns:
            StrategySignal
        """
        pass

    def validate_data(
        self,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        opens: np.ndarray
    ) -> Tuple[bool, str]:
        """
        Valida que los datos sean suficientes

        Returns:
            (válido, razón)
        """
        if len(closes) < self.min_bars_required:
            reason = f"Insufficient data: {len(closes)} < {self.min_bars_required}"
            self.logger.debug(reason)
            return False, reason

        if len(highs) != len(closes) or len(lows) != len(closes) or len(opens) != len(closes):
            reason = "Array length mismatch"
            self.logger.warning(reason)
            return False, reason

        # Verificar NaN
        if np.any(np.isnan(closes)) or np.any(np.isnan(highs)) or np.any(np.isnan(lows)):
            reason = "NaN values detected"
            self.logger.warning(reason)
            return False, reason

        return True, ""

    def safe_index(self, array: np.ndarray, index: int) -> float:
        """
        Acceso seguro a un índice de array

        Args:
            array: Array
            index: Índice

        Returns:
            Valor o NaN si fuera de rango
        """
        if index < 0 or index >= len(array):
            return np.nan

        return array[index]

    def safe_slice(self, array: np.ndarray, start: int, end: Optional[int] = None) -> np.ndarray:
        """
        Slice seguro de array

        Args:
            array: Array
            start: Inicio
            end: Fin (None = hasta el final)

        Returns:
            Slice o array vacío si índices inválidos
        """
        # Ajustar índices negativos
        length = len(array)

        if start < 0:
            start = max(0, length + start)

        if end is not None and end < 0:
            end = max(0, length + end)

        # Validar rangos
        if start >= length:
            return np.array([])

        if end is not None and end > length:
            end = length

        return array[start:end]
