#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot de Trading Automatizado para Binance Futures USDT Perpetual
VERSIÓN INTEGRADA COMPLETA 2.0 - Fusión de todas las funcionalidades

Implementa todas las mejoras del checklist:
- Perfiles de Riesgo (Conservador/Normal/Agresivo)
- Estrategias mejoradas (Elliott, Fibonacci, Wyckoff, SMC)
- WebSocket avanzado con reconexión inteligente
- Risk Controller con kill-switch
- Position Manager con salidas parciales
- Order Precision Manager
- Sistema de Confluencia con IC
- GUI completa

Autor: Sistema Profesional de Trading Algorítmico
Versión: 2.0.0
"""

import os
import math
import sys
import json
import time
import logging
import threading
import queue
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import warnings
warnings.filterwarnings('ignore')

# Importaciones de terceros
import numpy as np
import pandas as pd
import talib
# Imports personalizados (binance_fixes para WebSocket mejorado)
try:
    from binance_fixes import ImprovedBinanceClient, AlternativeWebSocketManager, PollingDataManager
    BINANCE_FIXES_AVAILABLE = True
except ImportError:
    BINANCE_FIXES_AVAILABLE = False
    print("WARNING: binance_fixes not available, using standard Binance client")

from scipy import signal
from scipy.stats import spearmanr

# ==========================================
# VALIDACIÓN DE DEPENDENCIA: python-binance
# ==========================================
# Este bot requiere python-binance==1.0.19 (no binance-connector)
# binance-connector expone un módulo 'binance' incompatible que shadow
# las clases Client y ThreadedWebsocketManager esperadas por este código.

try:
    import binance
    # Verificar que el módulo tiene las clases esperadas
    if not hasattr(binance, 'Client') and not hasattr(binance, 'client'):
        raise ImportError(
            "\n" + "="*70 + "\n"
            "ERROR: El módulo 'binance' instalado NO es python-binance.\n"
            "="*70 + "\n"
            "Probablemente tienes binance-connector instalado, que expone un\n"
            "módulo 'binance' incompatible que shadow las clases esperadas.\n\n"
            "SOLUCIÓN:\n"
            "  1. pip uninstall binance-connector binance\n"
            "  2. pip install python-binance==1.0.19\n\n"
            "CAUSA: binance-connector y python-binance no pueden coexistir\n"
            "porque ambos exponen el namespace 'binance'.\n"
            "="*70
        )

    # Intentar importar ThreadedWebsocketManager como prueba adicional
    try:
        from binance import ThreadedWebsocketManager
        _twsm_test = ThreadedWebsocketManager  # Verificar que no es None
    except (ImportError, AttributeError) as e:
        raise ImportError(
            "\n" + "="*70 + "\n"
            f"ERROR: No se pudo importar ThreadedWebsocketManager: {e}\n"
            "="*70 + "\n"
            "Esto indica que el módulo 'binance' instalado NO es python-binance==1.0.19.\n\n"
            "SOLUCIÓN:\n"
            "  1. pip uninstall binance-connector binance\n"
            "  2. pip install python-binance==1.0.19\n"
            "="*70
        )

except ImportError as e:
    if "No module named 'binance'" in str(e) or "No module named" in str(e):
        raise ImportError(
            "\n" + "="*70 + "\n"
            "ERROR: python-binance no está instalado.\n"
            "="*70 + "\n"
            "SOLUCIÓN:\n"
            "  pip install python-binance==1.0.19\n"
            "="*70
        )
    else:
        raise  # Re-raise si es otro tipo de ImportError ya formateado

# Si llegamos aquí, la validación pasó
print("✓ python-binance validation passed (ThreadedWebsocketManager available)")

from binance.client import Client
from binance.exceptions import BinanceAPIException
from enum import Enum
from collections import deque
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog

# ==========================================
# ENUMERACIONES Y DATACLASSES (del archivo complete)
# ==========================================

class RiskProfile(Enum):
    """Perfiles de riesgo disponibles"""
    CONSERVATIVE = "conservador"
    NORMAL = "normal"
    AGGRESSIVE = "agresivo"

class LogLevel(Enum):
    """Niveles de severidad de logs"""
    DEBUG = 0
    INFO = 1
    SUCCESS = 2
    WARNING = 3
    ERROR = 4
    CRITICAL = 5

class ConnectionMode(Enum):
    """Modos de conexión de datos"""
    WEBSOCKET = "WebSocket"
    POLLING = "Polling"

class AccountTier(Enum):
    """Niveles de cuenta según balance"""
    MICRO = "micro"      # < $1,000
    SMALL = "small"      # $1,000 - $10,000
    STANDARD = "standard" # $10,000 - $100,000
    LARGE = "large"      # > $100,000


# ==========================================
# CONFIGURACIÓN DE PERFILES DE RIESGO (del archivo complete)
# ==========================================

class RiskProfileConfig:
    """Configuración completa de perfiles de riesgo"""
    
    PROFILES = {
        RiskProfile.CONSERVATIVE: {
            'name': 'Conservador',
            'risk_per_trade': 0.75,  # % del capital
            'max_daily_loss': 2.0,   # % pérdida máxima diaria
            'min_confluence': 75,     # % confluencia mínima
            'confidence_threshold': 70,  # % confianza mínima
            'min_rr_ratio': 2.0,     # Ratio riesgo-recompensa mínimo
            'max_leverage': 3,       # Apalancamiento máximo
            'max_positions': 2,      # Posiciones simultáneas máximas
            'cooldown_after_loss': 120,  # Minutos después de SL
            'cooldown_after_win': 30,    # Minutos después de TP3
            'max_trades_per_hour': 2,
            'funding_filter_minutes': 15,  # Minutos antes/después funding
            # Salidas conservadoras: 80-100% en TP1, breakeven, sin trailing
            'tp1_percentage': 80,
            'tp2_percentage': 20,
            'tp3_percentage': 0,
            'use_trailing': False,
            'breakeven_at_tp1': True,
        },
        RiskProfile.NORMAL: {
            'name': 'Normal',
            'risk_per_trade': 1.5,
            'max_daily_loss': 5.0,
            'min_confluence': 65,
            'confidence_threshold': 60,
            'min_rr_ratio': 1.5,
            'max_leverage': 5,
            'max_positions': 3,
            'cooldown_after_loss': 60,
            'cooldown_after_win': 15,
            'max_trades_per_hour': 4,
            'funding_filter_minutes': 10,
            # Salidas normales: 50% TP1→BE, 30% TP2, 20% trailing
            'tp1_percentage': 50,
            'tp2_percentage': 30,
            'tp3_percentage': 20,
            'use_trailing': True,
            'breakeven_at_tp1': True,
        },
        RiskProfile.AGGRESSIVE: {
            'name': 'Agresivo',
            'risk_per_trade': 2.5,
            'max_daily_loss': 10.0,
            'min_confluence': 55,
            'confidence_threshold': 50,
            'min_rr_ratio': 1.2,
            'max_leverage': 10,
            'max_positions': 5,
            'cooldown_after_loss': 30,
            'cooldown_after_win': 5,
            'max_trades_per_hour': 8,
            'funding_filter_minutes': 5,
            # Salidas agresivas: 30% TP1→BE, 30% TP2, 40% trailing
            'tp1_percentage': 30,
            'tp2_percentage': 30,
            'tp3_percentage': 40,
            'use_trailing': True,
            'breakeven_at_tp1': True,
            'allow_pyramiding': True,  # Permite añadir a posiciones ganadoras
            'pyramid_max_adds': 2,
        }
    }
    
    @staticmethod
    def get_config(profile: RiskProfile) -> Dict:
        """Obtener configuración de un perfil"""
        return RiskProfileConfig.PROFILES[profile].copy()
    
    @staticmethod
    def get_account_tier(balance: float) -> AccountTier:
        """Determinar nivel de cuenta según balance"""
        if balance < 1000:
            return AccountTier.MICRO
        elif balance < 10000:
            return AccountTier.SMALL
        elif balance < 100000:
            return AccountTier.STANDARD
        else:
            return AccountTier.LARGE
    
    @staticmethod
    def adjust_for_account_tier(config: Dict, tier: AccountTier, balance: float) -> Dict:
        """Ajustar configuración según nivel de cuenta"""
        adjusted = config.copy()
        
        # Límites absolutos de riesgo por trade según tier
        max_risk_usdt = {
            AccountTier.MICRO: min(balance * 0.02, 20),
            AccountTier.SMALL: min(balance * 0.02, 200),
            AccountTier.STANDARD: min(balance * 0.015, 1500),
            AccountTier.LARGE: min(balance * 0.01, 10000),
        }
        
        adjusted['max_risk_usdt'] = max_risk_usdt[tier]
        
        # Reducir apalancamiento en cuentas grandes para preservar capital
        if tier == AccountTier.LARGE:
            adjusted['max_leverage'] = min(adjusted['max_leverage'], 5)
        
        return adjusted


# ==========================================
# CONFIGURACIÓN PRINCIPAL
# ==========================================

class Config:
    """Configuración centralizada del bot"""

    # Credenciales API - LEER DE VARIABLES DE ENTORNO
    # IMPORTANTE: Configura estas variables de entorno antes de ejecutar:
    #   export BINANCE_API_KEY="tu_api_key_aqui"
    #   export BINANCE_SECRET_KEY="tu_secret_key_aqui"
    API_KEY = os.getenv("BINANCE_API_KEY", "")
    SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "")
    
    # Parámetros de Trading
    SYMBOL = "BTCUSDT"
    TIMEFRAME = "5m"
    
        
    # Gestión de Riesgo por defecto (sobrescritos por perfil activo)
    RISK_PER_TRADE = 1.5  # % del capital por operación
    MAX_DAILY_LOSS = 5.0  # % pérdida máxima diaria
    LEVERAGE = 5  # Apalancamiento por defecto
    MIN_RR_RATIO = 1.5  # Ratio riesgo-recompensa mínimo
    
# Perfil de riesgo por defecto
    DEFAULT_RISK_PROFILE = RiskProfile.NORMAL
    
    # Tamaños de posición
    MIN_POSITION_USDT = 20
    MAX_POSITION_USDT = 10000
    
    # Indicadores técnicos
    ATR_PERIOD = 14
    ATR_MULTIPLIER = 2.0
    ATR_MULTIPLIER_TRAILING = 2.5
    RSI_PERIOD = 14
    
    # WebSocket y Conectividad
    WS_QUEUE_SIZE = 5000
    WS_PROCESSED_QUEUE_SIZE = 1000
    WS_RECONNECT_BASE_DELAY = 1.0
    WS_RECONNECT_MAX_DELAY = 60.0
    WS_RECONNECT_MAX_ATTEMPTS = 5
    WS_HEARTBEAT_INTERVAL = 30  # segundos
    WS_LATENCY_WARNING_MS = 100
    WS_LATENCY_CRITICAL_MS = 500
    PROACTIVE_RECONNECT_HOURS = 12
    
    # Polling fallback
    POLLING_INTERVAL = 60  # segundos (1 minuto por vela cerrada)

    # Funding rate
    FUNDING_INTERVAL_HOURS = 8
    FUNDING_TIMES_UTC = [0, 8, 16]  # Horas UTC del cobro de funding

    # Límites de tiempo en posición
    MAX_TIME_IN_TRADE_MINUTES = 240  # 4 horas
    MAX_POSITION_HOLD_MINUTES = 240  # Alias para claridad
    
    # Sistema de ponderación de estrategias
    IC_CALCULATION_WINDOW = 60  # días
    IC_UPDATE_FREQUENCY_DAYS = 7
    EWMA_LAMBDA = 0.94  # Factor de decaimiento exponencial
    
    # Control del bot
    USE_TESTNET = True
    LOG_LEVEL = logging.INFO
    LOG_DIR = "logs"
    
    # Archivo CSV de trades
    TRADES_CSV_FILENAME = "trading_bot_trades.csv"
    
    # GUI Update intervals
    GUI_UPDATE_INTERVAL_MS = 1000  # 1 segundo
    STATS_UPDATE_INTERVAL_MS = 5000  # 5 segundos




# ==========================================
# FUNCIONES DE UTILIDAD PARA INDICADORES
# ==========================================

def validate_indicator(value, name="indicator"):
    """Validar que un indicador no sea NaN o inválido"""
    if value is None:
        return False, f"{name} is None"
    if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
        return False, f"{name} is NaN or Inf"
    return True, "OK"

def safe_atr(df, period=14, default=None):
    """Calcular ATR de manera segura con validación"""
    if len(df) < period:
        return default if default is not None else df['close'].iloc[-1] * 0.01
    
    atr = talib.ATR(df['high'].values, df['low'].values, df['close'].values, timeperiod=period)
    
    if len(atr) == 0 or np.isnan(atr[-1]):
        return default if default is not None else df['close'].iloc[-1] * 0.01
    
    return atr[-1]

def safe_rsi(df, period=14, default=50.0):
    """Calcular RSI de manera segura con validación"""
    if len(df) < period:
        return default
    
    rsi = talib.RSI(df['close'].values, timeperiod=period)
    
    if len(rsi) == 0 or np.isnan(rsi[-1]):
        return default
    
    return rsi[-1]

# ==========================================
# SISTEMA DE LOGGING MEJORADO
# ==========================================

class ColoredFormatter(logging.Formatter):
    """Formateador con colores para consola"""
    
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[37m',       # White
        'SUCCESS': '\033[32m',    # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m'
    }
    
    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        record.levelname = f"{log_color}{record.levelname:8}{self.COLORS['RESET']}"
        return super().format(record)

class TradingLogger:
    """Sistema de logging profesional con múltiples salidas y filtros"""
    
    def __init__(self, log_dir="logs"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        
        # Añadir nivel SUCCESS personalizado
        logging.SUCCESS = 25
        logging.addLevelName(logging.SUCCESS, 'SUCCESS')
        
        # Configurar formato de logs
        self.formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        self.colored_formatter = ColoredFormatter(
            '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Logger principal
        self.logger = logging.getLogger("TradingBot")
        self.logger.setLevel(Config.LOG_LEVEL)
        self.logger.handlers.clear()
        
        # Handler para archivo
        log_file = os.path.join(log_dir, f"trading_{datetime.now():%Y%m%d_%H%M%S}.log")
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(self.formatter)
        self.logger.addHandler(file_handler)
        
        # Handler para consola con colores
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(self.colored_formatter)
        self.logger.addHandler(console_handler)
        
        # Logs especializados
        self.trade_logger = self._setup_trade_logger()
        self.error_logger = self._setup_error_logger()
        self.strategy_logger = self._setup_strategy_logger()
        
        # Cola para GUI
        self.gui_queue = None
        
    def _setup_trade_logger(self):
        """
        Logger específico para operaciones con formato CSV

        El archivo se guarda en: logs/trading_bot_trades.csv
        NOTA PARA GUI: Leer desde esta ruta, no desde el directorio raíz.
        """
        logger = logging.getLogger("Trades")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()

        # Ruta completa del CSV: logs/trading_bot_trades.csv
        self.trades_csv_path = os.path.join(self.log_dir, Config.TRADES_CSV_FILENAME)
        handler = logging.FileHandler(self.trades_csv_path)
        handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(handler)

        # Escribir encabezado CSV si el archivo no existe o está vacío
        # Columnas: timestamp,symbol,side,entry_price,exit_price,quantity,pnl_usdt,pnl_pct,
        #          strategy,confidence,risk_profile,mode,risk_usdt,risk_pct,rr_ratio,
        #          duration_minutes,max_drawdown_pct,funding_paid,
        #          elliott_signal,elliott_conf,fibonacci_signal,fibonacci_conf,
        #          wyckoff_signal,wyckoff_conf,smc_signal,smc_conf
        if not os.path.exists(self.trades_csv_path) or os.path.getsize(self.trades_csv_path) == 0:
            logger.info("timestamp,symbol,side,entry_price,exit_price,quantity,pnl_usdt,pnl_pct,strategy,confidence,risk_profile,mode,risk_usdt,risk_pct,rr_ratio,duration_minutes,max_drawdown_pct,funding_paid,elliott_signal,elliott_conf,fibonacci_signal,fibonacci_conf,wyckoff_signal,wyckoff_conf,smc_signal,smc_conf")

        return logger

    def get_trades_csv_path(self):
        """Obtener ruta completa del archivo CSV de trades (para la GUI)"""
        return getattr(self, 'trades_csv_path', os.path.join(self.log_dir, Config.TRADES_CSV_FILENAME))
    
    def _setup_error_logger(self):
        """Logger específico para errores"""
        logger = logging.getLogger("Errors")
        logger.setLevel(logging.ERROR)
        logger.handlers.clear()
        
        handler = logging.FileHandler(
            os.path.join(self.log_dir, "errors.log")
        )
        handler.setFormatter(self.formatter)
        logger.addHandler(handler)
        return logger
    
    def _setup_strategy_logger(self):
        """Logger específico para señales de estrategias"""
        logger = logging.getLogger("Strategies")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        
        handler = logging.FileHandler(
            os.path.join(self.log_dir, f"strategies_{datetime.now():%Y%m%d}.log")
        )
        handler.setFormatter(self.formatter)
        logger.addHandler(handler)
        return logger
    
    def set_gui_queue(self, gui_queue):
        """Configurar cola para enviar logs a GUI"""
        self.gui_queue = gui_queue
    
    def log(self, message: str, level: str = 'INFO', component: str = None):
        """Log con envío a GUI"""
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'SUCCESS': logging.SUCCESS,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        
        log_level = level_map.get(level.upper(), logging.INFO)
        
        if component:
            logger = logging.getLogger(f"TradingBot.{component}")
        else:
            logger = self.logger
        
        logger.log(log_level, message)
        
        # Enviar a GUI si está configurado
        if self.gui_queue:
            try:
                self.gui_queue.put_nowait(('log', {
                    'message': message,
                    'level': level,
                    'timestamp': datetime.now()
                }))
            except queue.Full:
                pass
    
    def log_trade(self, trade_data: Dict):
        """Registrar operación en CSV y enviar a GUI"""
        csv_line = (f"{trade_data['timestamp']},{trade_data['symbol']},"
                   f"{trade_data['side']},{trade_data.get('entry_price', '')},"
                   f"{trade_data.get('exit_price', '')},{trade_data.get('quantity', '')},"
                   f"{trade_data.get('pnl_usdt', '')},{trade_data.get('pnl_pct', '')},"
                   f"{trade_data['strategy']},{trade_data['confidence']},"
                   f"{trade_data.get('risk_profile', '')},{trade_data.get('mode', '')},"
                   f"{trade_data.get('risk_usdt', '')},{trade_data.get('risk_pct', '')},"
                   f"{trade_data.get('rr_ratio', '')},{trade_data.get('duration_minutes', '')},"
                   f"{trade_data.get('max_drawdown_pct', '')},{trade_data.get('funding_paid', '')}")
        
        self.trade_logger.info(csv_line)
        
        # Enviar a GUI
        if self.gui_queue:
            try:
                self.gui_queue.put_nowait(('trade', trade_data))
            except queue.Full:
                pass
    
    def log_strategy_signal(self, strategy: str, signal: Dict):
        """Registrar señal de estrategia con detalles (usa signal numérico: -1/0/1)"""
        # Convertir signal numérico a texto para logging
        signal_value = signal.get('signal', 0)
        signal_text = 'BUY' if signal_value == 1 else ('SELL' if signal_value == -1 else 'NONE')

        msg = (f"Estrategia: {strategy} | Señal: {signal_text} | "
               f"Confianza: {signal.get('confidence', 0):.1f}% | "
               f"Detalles: {json.dumps(signal.get('details', {}))}")
        self.strategy_logger.info(msg)

    def success(self, message: str, component: str = None):
        """Log de éxito"""
        self.log(message, 'SUCCESS', component)

    def info(self, message: str, component: str = None):
        """Log de información"""
        self.log(message, 'INFO', component)

    def debug(self, message: str, component: str = None):
        """Log de debug"""
        self.log(message, 'DEBUG', component)

    def warning(self, message: str, component: str = None):
        """Log de advertencia"""
        self.log(message, 'WARNING', component)

    def error(self, message: str, component: str = None):
        """Log de error"""
        self.log(message, 'ERROR', component)

    def critical(self, message: str, component: str = None):
        """Log crítico"""
        self.log(message, 'CRITICAL', component)

# ==========================================
# PRECISIÓN DE ÓRDENES Y FILTROS
# ==========================================

class OrderPrecisionManager:
    """Gestor de precisión de órdenes según filtros de Binance"""
    
    def __init__(self, client, symbol, logger):
        self.client = client
        self.symbol = symbol
        self.logger = logger
        
        # Información de símbolo
        self.symbol_info = None
        self.tick_size = None
        self.step_size = None
        self.min_notional = None
        self.price_precision = None
        self.quantity_precision = None
        
        self._load_symbol_info()
    
    def _load_symbol_info(self):
        """Cargar información del símbolo desde Binance"""
        try:
            exchange_info = self.client.futures_exchange_info()
            
            for symbol_data in exchange_info['symbols']:
                if symbol_data['symbol'] == self.symbol:
                    self.symbol_info = symbol_data
                    
                    # Extraer filtros
                    for filter_data in symbol_data['filters']:
                        if filter_data['filterType'] == 'PRICE_FILTER':
                            self.tick_size = float(filter_data['tickSize'])
                        elif filter_data['filterType'] == 'LOT_SIZE':
                            self.step_size = float(filter_data['stepSize'])
                        elif filter_data['filterType'] == 'MIN_NOTIONAL':
                            self.min_notional = float(filter_data['notional'])
                    
                    # Calcular precisiones
                    self.price_precision = int(round(-np.log10(self.tick_size), 0))
                    self.quantity_precision = int(round(-np.log10(self.step_size), 0))
                    
                    self.logger.success(
                        f"Precisión cargada - Precio: {self.price_precision} decimales, "
                        f"Cantidad: {self.quantity_precision} decimales, "
                        f"Min Notional: ${self.min_notional}",
                        "OrderPrecision"
                    )
                    return
            
            raise ValueError(f"Símbolo {self.symbol} no encontrado")
            
        except Exception as e:
            self.logger.log(f"Error cargando información de símbolo: {e}", "ERROR", "OrderPrecision")
            # Valores por defecto para BTCUSDT
            self.tick_size = 0.01
            self.step_size = 0.001
            self.min_notional = 10.0
            self.price_precision = 2
            self.quantity_precision = 3
    
    def round_price(self, price: float, side: str = None, order_type: str = 'LIMIT') -> float:
        """
        Redondear precio con direccionalidad según side y tipo de orden
        Usa redondeo decimal para evitar flotantes "sucios" (0.01000000002)

        Args:
            price: Precio a redondear
            side: 'BUY' o 'SELL' (None = floor por defecto)
            order_type: 'LIMIT', 'STOP_LOSS', 'TAKE_PROFIT'

        Reglas:
            - LIMIT BUY: redondear hacia abajo (mejor precio para compra)
            - LIMIT SELL: redondear hacia arriba (mejor precio para venta)
            - STOP/TP BUY: redondear hacia arriba (trigger más seguro)
            - STOP/TP SELL: redondear hacia abajo (trigger más seguro)
        """
        from decimal import Decimal, ROUND_DOWN, ROUND_UP

        # Convertir a Decimal para precisión exacta
        price_dec = Decimal(str(price))
        tick_dec = Decimal(str(self.tick_size))

        # Determinar dirección de redondeo
        if side is None:
            # Por defecto, floor
            rounding = ROUND_DOWN
        elif order_type == 'LIMIT':
            rounding = ROUND_DOWN if side == 'BUY' else ROUND_UP
        else:  # STOP_LOSS, TAKE_PROFIT
            rounding = ROUND_UP if side == 'BUY' else ROUND_DOWN

        # Redondear al múltiplo de tick_size
        rounded = (price_dec / tick_dec).quantize(Decimal('1'), rounding=rounding) * tick_dec

        # Retornar como float, pero el valor ya está limpio
        return float(rounded)

    def round_quantity(self, quantity: float) -> float:
        """
        Redondear cantidad al múltiplo inferior exacto de stepSize
        Usa redondeo decimal para evitar flotantes "sucios" (0.00100000000001)
        """
        from decimal import Decimal, ROUND_DOWN

        # Convertir a Decimal para precisión exacta
        quantity_dec = Decimal(str(quantity))
        step_dec = Decimal(str(self.step_size))

        # Redondear hacia abajo al múltiplo de step_size
        rounded = (quantity_dec / step_dec).quantize(Decimal('1'), rounding=ROUND_DOWN) * step_dec

        # Retornar como float, pero el valor ya está limpio
        return float(rounded)
    
    def validate_order(self, price: float, quantity: float, allow_adjust=True) -> Tuple[bool, str, float, float]:
        """
        Validar y ajustar orden según filtros de Binance

        Args:
            price: Precio de la orden
            quantity: Cantidad a operar
            allow_adjust: Si True, intenta ajustar cantidad para cumplir mínimos

        Returns:
            (is_valid, error_message, adjusted_price, adjusted_quantity)
        """
        # Ajustar precisión al piso del múltiplo
        adj_price = self.round_price(price)
        adj_quantity = self.round_quantity(quantity)

        # Validar cantidad mínima
        if adj_quantity < self.step_size:
            if allow_adjust:
                adj_quantity = self.step_size
            else:
                return False, f"Cantidad {adj_quantity} < mínima {self.step_size}", adj_price, adj_quantity

        # Validar notional mínimo
        notional = adj_price * adj_quantity
        if notional < self.min_notional:
            if allow_adjust:
                # Intentar aumentar cantidad al mínimo necesario usando ceil
                # Esto asegura que siempre alcancemos el notional mínimo sin pasarnos ni quedarnos cortos
                min_quantity_needed = self.min_notional / adj_price
                # Usar math.ceil para redondear hacia arriba al siguiente múltiplo de step_size
                adj_quantity = math.ceil(min_quantity_needed / self.step_size) * self.step_size
                notional = adj_price * adj_quantity

                # Verificar si ahora cumple
                if notional < self.min_notional:
                    return False, f"Notional ${notional:.2f} < mínimo ${self.min_notional} (no ajustable)", adj_price, adj_quantity

                self.logger.info(
                    f"Cantidad ajustada de {quantity:.6f} a {adj_quantity:.6f} "
                    f"para cumplir notional mínimo (${notional:.2f})",
                    "OrderPrecision"
                )
            else:
                return False, f"Notional ${notional:.2f} < mínimo ${self.min_notional}", adj_price, adj_quantity

        return True, "OK", adj_price, adj_quantity
    
    def calculate_position_size(self, entry_price: float, stop_loss: float, 
                               risk_usdt: float) -> Tuple[float, float]:
        """
        Calcular tamaño de posición basado en riesgo
        
        Returns:
            (quantity, notional_usdt)
        """
        # Distancia del stop loss
        stop_distance = abs(entry_price - stop_loss)
        
        if stop_distance == 0:
            return 0, 0
        
        # Cantidad basada en riesgo
        quantity = risk_usdt / stop_distance
        
        # Ajustar según precisión
        quantity = self.round_quantity(quantity)
        
        # Validar
        is_valid, error, adj_price, adj_quantity = self.validate_order(entry_price, quantity)
        
        if not is_valid:
            self.logger.log(f"Tamaño de posición inválido: {error}", "WARNING", "OrderPrecision")
            return 0, 0
        
        notional = adj_quantity * adj_price
        return adj_quantity, notional

# ==========================================
# DETECCIÓN MEJORADA DE ELLIOTT WAVE
# ==========================================

# ==========================================
# ESTRATEGIAS DE TRADING MEJORADAS
# ==========================================

class ElliottWaveDetector:
    """Detector mejorado de patrones de Elliott Wave - Ampliado para impulsos bajistas"""
    
    def __init__(self, logger):
        self.logger = logger
        self.min_wave_size = 10
        # Umbral de confianza reducido para aportar más frecuentemente
        self.confidence_threshold = 50  # Reducido de 60%
        
    def find_pivots(self, highs: np.ndarray, lows: np.ndarray, order: int = 5) -> Tuple[np.ndarray, np.ndarray]:
        """
        Identificar puntos pivote con ordenamiento temporal

        Returns:
            high_pivots: Índices de pivotes altos ordenados temporalmente
            low_pivots: Índices de pivotes bajos ordenados temporalmente
        """
        high_pivots = signal.argrelextrema(highs, np.greater, order=order)[0]
        low_pivots = signal.argrelextrema(lows, np.less, order=order)[0]

        # Ya están ordenados por índice (tiempo), pero asegurar
        high_pivots = np.sort(high_pivots)
        low_pivots = np.sort(low_pivots)

        return high_pivots, low_pivots

    def _validate_temporal_sequence(self, indices: List[int]) -> bool:
        """
        Validar que los índices están en orden temporal estricto

        Args:
            indices: Lista de índices de pivotes en el orden de las ondas

        Returns:
            True si están en orden temporal correcto (ascendente)
        """
        for i in range(len(indices) - 1):
            if indices[i] >= indices[i + 1]:
                return False
        return True
    
    def detect_pattern(self, df: pd.DataFrame, atr: float) -> Dict:
        """
        Detectar patrones Elliott Wave - Ahora incluye impulsos alcistas Y bajistas
        
        Returns:
            Dict con dirección, confianza y detalles
        """
        try:
            if len(df) < 100:
                return {'signal': 0, 'confidence': 0, 'details': {}}
            
            highs = df['high'].values
            lows = df['low'].values
            closes = df['close'].values
            
            # Buscar patrones alcistas (originales)
            bullish_signal = self._detect_bullish_impulse(highs, lows, closes, atr)
            
            # Buscar patrones bajistas (NUEVO)
            bearish_signal = self._detect_bearish_impulse(highs, lows, closes, atr)
            
            # Retornar la señal con mayor confianza
            if bullish_signal['confidence'] > bearish_signal['confidence']:
                if bullish_signal['confidence'] >= self.confidence_threshold:
                    return bullish_signal
            else:
                if bearish_signal['confidence'] >= self.confidence_threshold:
                    return bearish_signal
            
            return {'signal': 0, 'confidence': 0, 'details': {}}
            
        except Exception as e:
            self.logger.log(f"Error en Elliott Wave: {e}", "ERROR", "ElliottWave")
            return {'signal': 0, 'confidence': 0, 'details': {}}
    
    def _detect_bullish_impulse(self, highs, lows, closes, atr):
        """Detectar impulso alcista (5 ondas al alza) con validación temporal"""
        high_pivots, low_pivots = self.find_pivots(highs, lows)

        if len(high_pivots) < 3 or len(low_pivots) < 3:
            return {'signal': 0, 'confidence': 0, 'details': {}}

        # Combinar pivots con tipo y ordenar por índice temporal
        all_pivots = []
        for idx in high_pivots:
            all_pivots.append({'index': idx, 'type': 'high', 'value': highs[idx]})
        for idx in low_pivots:
            all_pivots.append({'index': idx, 'type': 'low', 'value': lows[idx]})

        # Ordenar por índice temporal
        all_pivots.sort(key=lambda x: x['index'])

        # Buscar secuencia: low -> high -> low -> high -> low -> high
        # (inicio onda 1 -> fin onda 1 -> fin onda 2 -> fin onda 3 -> fin onda 4 -> fin onda 5)
        for i in range(len(all_pivots) - 5):
            if (all_pivots[i]['type'] == 'low' and
                all_pivots[i+1]['type'] == 'high' and
                all_pivots[i+2]['type'] == 'low' and
                all_pivots[i+3]['type'] == 'high' and
                all_pivots[i+4]['type'] == 'low' and
                all_pivots[i+5]['type'] == 'high'):

                # Extraer valores de ondas
                waves = [
                    all_pivots[i]['value'],    # Wave 1 start
                    all_pivots[i+1]['value'],  # Wave 1 end
                    all_pivots[i+2]['value'],  # Wave 2 end
                    all_pivots[i+3]['value'],  # Wave 3 end
                    all_pivots[i+4]['value'],  # Wave 4 end
                    all_pivots[i+5]['value'],  # Wave 5 end
                ]

                # Extraer índices temporales
                wave_indices = [
                    all_pivots[i]['index'],
                    all_pivots[i+1]['index'],
                    all_pivots[i+2]['index'],
                    all_pivots[i+3]['index'],
                    all_pivots[i+4]['index'],
                    all_pivots[i+5]['index'],
                ]

                # Validar secuencia temporal (ya debería estar, pero verificar)
                if not self._validate_temporal_sequence(wave_indices):
                    continue

                # Validar reglas de Elliott
                if self._validate_elliott_rules(waves):
                    fib_score = self._calculate_fibonacci_score(waves)

                    # Señal de venta en onda 5
                    if fib_score > 50:
                        return {
                            'signal': -1,  # Vender en tope de onda 5
                            'confidence': fib_score,
                            'details': {
                                'pattern': 'bullish_impulse_wave5',
                                'wave_5_high': waves[5],
                                'fib_conformity': fib_score,
                                'wave_indices': wave_indices
                            }
                        }

        return {'signal': 0, 'confidence': 0, 'details': {}}
    
    def _detect_bearish_impulse(self, highs, lows, closes, atr):
        """Detectar impulso bajista (5 ondas a la baja) con validación temporal"""
        high_pivots, low_pivots = self.find_pivots(highs, lows)

        if len(high_pivots) < 3 or len(low_pivots) < 3:
            return {'signal': 0, 'confidence': 0, 'details': {}}

        # Combinar pivots con tipo y ordenar por índice temporal
        all_pivots = []
        for idx in high_pivots:
            all_pivots.append({'index': idx, 'type': 'high', 'value': highs[idx]})
        for idx in low_pivots:
            all_pivots.append({'index': idx, 'type': 'low', 'value': lows[idx]})

        # Ordenar por índice temporal
        all_pivots.sort(key=lambda x: x['index'])

        # Buscar secuencia: high -> low -> high -> low -> high -> low
        # (inicio onda 1 -> fin onda 1 -> fin onda 2 -> fin onda 3 -> fin onda 4 -> fin onda 5)
        for i in range(len(all_pivots) - 5):
            if (all_pivots[i]['type'] == 'high' and
                all_pivots[i+1]['type'] == 'low' and
                all_pivots[i+2]['type'] == 'high' and
                all_pivots[i+3]['type'] == 'low' and
                all_pivots[i+4]['type'] == 'high' and
                all_pivots[i+5]['type'] == 'low'):

                # Extraer valores de ondas
                waves = [
                    all_pivots[i]['value'],    # Wave 1 start (alto)
                    all_pivots[i+1]['value'],  # Wave 1 end (bajo)
                    all_pivots[i+2]['value'],  # Wave 2 end (rebote)
                    all_pivots[i+3]['value'],  # Wave 3 end (bajo más bajo)
                    all_pivots[i+4]['value'],  # Wave 4 end (rebote)
                    all_pivots[i+5]['value'],  # Wave 5 end (bajo final)
                ]

                # Extraer índices temporales
                wave_indices = [
                    all_pivots[i]['index'],
                    all_pivots[i+1]['index'],
                    all_pivots[i+2]['index'],
                    all_pivots[i+3]['index'],
                    all_pivots[i+4]['index'],
                    all_pivots[i+5]['index'],
                ]

                # Validar secuencia temporal
                if not self._validate_temporal_sequence(wave_indices):
                    continue

                # Validar reglas de Elliott bajista
                if self._validate_bearish_elliott_rules(waves):
                    fib_score = self._calculate_fibonacci_score_bearish(waves)

                    # Señal de compra en onda 5 bajista
                    if fib_score > 50:
                        return {
                            'signal': 1,  # Comprar en fondo de onda 5 bajista
                            'confidence': fib_score,
                            'details': {
                                'pattern': 'bearish_impulse_wave5',
                                'wave_5_low': waves[5],
                                'fib_conformity': fib_score,
                                'wave_indices': wave_indices
                            }
                        }

        return {'signal': 0, 'confidence': 0, 'details': {}}
    
    def _validate_elliott_rules(self, waves: List[float]) -> bool:
        """Validar reglas de Elliott Wave alcista"""
        if len(waves) != 6:
            return False
        
        w1_start, w1_end, w2_end, w3_end, w4_end, w5_end = waves
        
        # Regla 1: Wave 2 no retrocede más del 100%
        if w2_end <= w1_start:
            return False
        
        # Regla 2: Wave 3 no puede ser la más corta
        w1_len = abs(w1_end - w1_start)
        w3_len = abs(w3_end - w2_end)
        w5_len = abs(w5_end - w4_end)
        
        if w3_len < w1_len or w3_len < w5_len:
            return False
        
        # Regla 3: Wave 4 no solapa con Wave 1
        if w4_end <= w1_end:
            return False
        
        return True
    
    def _validate_bearish_elliott_rules(self, waves: List[float]) -> bool:
        """Validar reglas de Elliott Wave bajista"""
        if len(waves) != 6:
            return False
        
        w1_start, w1_end, w2_end, w3_end, w4_end, w5_end = waves
        
        # Regla 1: Wave 2 no retrocede más del 100%
        if w2_end >= w1_start:
            return False
        
        # Regla 2: Wave 3 no puede ser la más corta
        w1_len = abs(w1_start - w1_end)
        w3_len = abs(w2_end - w3_end)
        w5_len = abs(w4_end - w5_end)
        
        if w3_len < w1_len or w3_len < w5_len:
            return False
        
        # Regla 3: Wave 4 no solapa con Wave 1
        if w4_end >= w1_end:
            return False
        
        return True
    
    def _calculate_fibonacci_score(self, waves: List[float]) -> float:
        """Calcular puntuación Fibonacci para patrón alcista"""
        w1_start, w1_end, w2_end, w3_end, w4_end, w5_end = waves
        score = 0.0
        
        # Wave 2: retroceso 38.2-61.8%
        w1_range = w1_end - w1_start
        if w1_range != 0:
            w2_retrace = (w1_end - w2_end) / w1_range
            if 0.382 <= w2_retrace <= 0.618:
                score += 25
        
        # Wave 3: extensión 138.2-161.8%
        if w1_range != 0:
            w3_extension = (w3_end - w2_end) / w1_range
            if 1.382 <= w3_extension <= 1.618:
                score += 25
        
        # Wave 4: retroceso 23.6-38.2%
        w3_range = w3_end - w2_end
        if w3_range != 0:
            w4_retrace = (w3_end - w4_end) / w3_range
            if 0.236 <= w4_retrace <= 0.382:
                score += 25
        
        # Wave 5: relación con Wave 1
        w5_len = w5_end - w4_end
        if w1_range != 0 and 0.618 <= (w5_len / w1_range) <= 1.618:
            score += 25
        
        return score
    
    def _calculate_fibonacci_score_bearish(self, waves: List[float]) -> float:
        """Calcular puntuación Fibonacci para patrón bajista"""
        w1_start, w1_end, w2_end, w3_end, w4_end, w5_end = waves
        score = 0.0
        
        # Wave 2: retroceso 38.2-61.8%
        w1_range = w1_start - w1_end
        if w1_range != 0:
            w2_retrace = (w2_end - w1_end) / w1_range
            if 0.382 <= w2_retrace <= 0.618:
                score += 25
        
        # Wave 3: extensión 138.2-161.8%
        if w1_range != 0:
            w3_extension = (w2_end - w3_end) / w1_range
            if 1.382 <= w3_extension <= 1.618:
                score += 25
        
        # Wave 4: retroceso 23.6-38.2%
        w3_range = w2_end - w3_end
        if w3_range != 0:
            w4_retrace = (w4_end - w3_end) / w3_range
            if 0.236 <= w4_retrace <= 0.382:
                score += 25
        
        # Wave 5: relación con Wave 1
        w5_len = w4_end - w5_end
        if w1_range != 0 and 0.618 <= (w5_len / w1_range) <= 1.618:
            score += 25
        
        return score

    def analyze(self, df: pd.DataFrame) -> Dict:
        """
        Análisis de Elliott Wave (wrapper para compatibilidad)
        Retorna formato estándar para MultiStrategyTrader
        """
        # Calcular ATR antes de llamar a detect_pattern
        atr = safe_atr(df, Config.ATR_PERIOD)

        # Llamar al método existente con ATR
        if hasattr(self, 'detect_pattern'):
            result = self.detect_pattern(df, atr)
        else:
            result = {
                'pattern_found': False,
                'confidence': 0.0,
                'signal': 0
            }

        # Convertir al formato estándar si es necesario
        return {
            'signal': result.get('signal', 0),
            'confidence': result.get('confidence', 0.0),
            'details': result
        }


# ==========================================
# FIBONACCI MEJORADO CON TOLERANCIAS ATR
# ==========================================
class FibonacciAnalyzer:
    """Analizador de Fibonacci con tolerancias basadas en ATR"""
    
    def __init__(self, logger):
        self.logger = logger
        # Niveles de Fibonacci clave
        self.fib_levels = [0.236, 0.382, 0.5, 0.618, 0.786]
        self.golden_zone = (0.618, 0.786)
        
    def analyze(self, df: pd.DataFrame, atr: float) -> Dict:
        """
        Analizar niveles de Fibonacci con tolerancia ATR
        
        Args:
            df: DataFrame con datos OHLCV
            atr: Average True Range actual
            
        Returns:
            Dict con señal y detalles
        """
        try:
            if len(df) < 50:
                return {'signal': 0, 'confidence': 0, 'details': {}}
            
            # Encontrar swing high/low recientes
            highs = df['high'].values[-50:]
            lows = df['low'].values[-50:]
            closes = df['close'].values
            current_price = closes[-1]
            
            swing_high = np.max(highs)
            swing_low = np.min(lows)
            price_range = swing_high - swing_low
            
            if price_range == 0:
                return {'signal': 0, 'confidence': 0, 'details': {}}
            
            # Calcular retroceso actual
            current_retracement = (swing_high - current_price) / price_range
            
            # Tolerancia relativa al ATR (no % fijo)
            tolerance = (atr / price_range) * 0.5  # 50% del ATR como tolerancia
            
            signal = {'signal': 0, 'confidence': 0, 'details': {}}
            
            # Golden Zone (0.618-0.786): zona de alta probabilidad
            if self._in_zone(current_retracement, self.golden_zone, tolerance):
                # Precio en golden zone + confirmación de momentum
                if self._check_bullish_momentum(df):
                    signal = {
                        'signal': 1,
                        'confidence': 75,
                        'details': {
                            'pattern': 'golden_zone_bounce',
                            'retracement': current_retracement,
                            'swing_high': swing_high,
                            'swing_low': swing_low,
                            'target': swing_high
                        }
                    }
            
            # Nivel 0.5 (50% de retroceso)
            elif self._near_level(current_retracement, 0.5, tolerance):
                if self._check_bullish_momentum(df):
                    signal = {
                        'signal': 1,
                        'confidence': 65,
                        'details': {
                            'pattern': 'fibonacci_50_bounce',
                            'retracement': current_retracement,
                            'level': 0.5
                        }
                    }
            
            # Extensiones (precio por encima del swing high)
            elif current_price > swing_high:
                extension = (current_price - swing_high) / price_range
                # Extensión 1.618 - posible toma de ganancias
                if self._near_level(extension, 0.618, tolerance):
                    signal = {
                        'signal': -1,
                        'confidence': 70,
                        'details': {
                            'pattern': 'fibonacci_extension_1618',
                            'extension': 1 + extension
                        }
                    }
            
            return signal
            
        except Exception as e:
            self.logger.log(f"Error en Fibonacci: {e}", "ERROR", "Fibonacci")
            return {'signal': 0, 'confidence': 0, 'details': {}}
    
    def _in_zone(self, value: float, zone: Tuple[float, float], tolerance: float) -> bool:
        """Verificar si valor está en zona con tolerancia"""
        return (zone[0] - tolerance) <= value <= (zone[1] + tolerance)
    
    def _near_level(self, value: float, level: float, tolerance: float) -> bool:
        """Verificar si valor está cerca de nivel con tolerancia"""
        return abs(value - level) <= tolerance
    
    def _check_bullish_momentum(self, df: pd.DataFrame) -> bool:
        """Verificar momentum alcista"""
        if len(df) < 10:
            return False
        
        closes = df['close'].values[-10:]
        # Precio actual mayor que hace 3 velas
        return closes[-1] > closes[-4]

# ==========================================
# WYCKOFF VSA MEJORADO
# ==========================================
class WyckoffVSADetector:
    """Detector Wyckoff con criterios corregidos de no demand/no supply"""
    
    def __init__(self, logger):
        self.logger = logger
        self.lookback = 20
        
    def detect(self, df: pd.DataFrame, atr: float) -> Dict:
        """
        Detectar eventos Wyckoff/VSA
        
        Criterios corregidos:
        - No demand: bajo volumen + rango estrecho (no solo volumen bajo)
        - No supply: bajo volumen + rango estrecho (no solo volumen bajo)
        """
        try:
            if len(df) < self.lookback + 5:
                return {'signal': 0, 'confidence': 0, 'details': {}}
            
            recent_df = df.tail(self.lookback + 5).copy()
            volumes = recent_df['volume'].values
            closes = recent_df['close'].values
            opens = recent_df['open'].values
            highs = recent_df['high'].values
            lows = recent_df['low'].values
            
            # Promedios
            avg_volume = np.mean(volumes[:-1])
            avg_range = np.mean(highs[:-1] - lows[:-1])
            
            # Vela actual
            current_volume = volumes[-1]
            current_range = highs[-1] - lows[-1]
            current_close = closes[-1]
            current_open = opens[-1]
            
            # No Demand (CORREGIDO): bajo volumen + rango estrecho en subida
            if (current_close > current_open and  # Vela alcista
                current_volume < avg_volume * 0.6 and  # Volumen bajo
                current_range < avg_range * 0.7):  # Rango estrecho
                return {
                    'signal': -1,
                    'confidence': 70,
                    'details': {
                        'pattern': 'no_demand',
                        'volume_ratio': current_volume / avg_volume,
                        'range_ratio': current_range / avg_range
                    }
                }
            
            # No Supply (CORREGIDO): bajo volumen + rango estrecho en bajada
            if (current_close < current_open and  # Vela bajista
                current_volume < avg_volume * 0.6 and  # Volumen bajo
                current_range < avg_range * 0.7):  # Rango estrecho
                return {
                    'signal': 1,
                    'confidence': 70,
                    'details': {
                        'pattern': 'no_supply',
                        'volume_ratio': current_volume / avg_volume,
                        'range_ratio': current_range / avg_range
                    }
                }
            
            # Climax de Compras: volumen muy alto en subida
            if (current_volume > avg_volume * 2.0 and
                current_close > current_open and
                current_range > avg_range * 1.5):
                return {
                    'signal': -1,
                    'confidence': 65,
                    'details': {
                        'pattern': 'buying_climax',
                        'volume_ratio': current_volume / avg_volume
                    }
                }
            
            # Climax de Ventas: volumen muy alto en bajada
            if (current_volume > avg_volume * 2.0 and
                current_close < current_open and
                current_range > avg_range * 1.5):
                return {
                    'signal': 1,
                    'confidence': 65,
                    'details': {
                        'pattern': 'selling_climax',
                        'volume_ratio': current_volume / avg_volume
                    }
                }
            
            # Spring (trampa bajista)
            spring = self._detect_spring(lows, volumes, avg_volume)
            if spring:
                return {
                    'signal': 1,
                    'confidence': 75,
                    'details': {'pattern': 'spring'}
                }
            
            return {'signal': 0, 'confidence': 0, 'details': {}}
            
        except Exception as e:
            self.logger.log(f"Error en Wyckoff: {e}", "ERROR", "Wyckoff")
            return {'signal': 0, 'confidence': 0, 'details': {}}
    
    def _detect_spring(self, lows: np.ndarray, volumes: np.ndarray, avg_volume: float) -> bool:
        """
        Detectar spring (trampa bajista) - CORREGIDO
        
        El mínimo debe ser el actual o muy reciente, no de hace 20 velas
        """
        if len(lows) < 5:
            return False
        
        # Buscar mínimo en últimas 5 velas (no 20)
        recent_lows = lows[-5:]
        min_idx_recent = np.argmin(recent_lows)
        
        # El mínimo debe ser hace máximo 2 velas
        if min_idx_recent < 3:
            # Verificar rebote con volumen
            current_volume = volumes[-1]
            if current_volume > avg_volume * 1.2:
                return True

        return False

    def analyze(self, df: pd.DataFrame, atr: float = None) -> Dict:
        """
        Wrapper para compatibilidad con MultiStrategyTrader
        Llama a detect() calculando ATR si es necesario
        """
        if atr is None:
            atr = safe_atr(df, Config.ATR_PERIOD)
        return self.detect(df, atr)

# ==========================================
# SMART MONEY CONCEPTS (SMC)
# ==========================================
class SmartMoneyDetector:
    """Detector de conceptos Smart Money (Order Blocks, FVG, etc.)"""
    
    def __init__(self, logger):
        self.logger = logger
        
    def detect(self, df: pd.DataFrame, atr: float) -> Dict:
        """Detectar estructuras Smart Money"""
        try:
            if len(df) < 50:
                return {'signal': 0, 'confidence': 0, 'details': {}}

            # Order Blocks
            ob_signal = self._detect_order_blocks(df)
            if ob_signal['signal'] != 0:
                return ob_signal

            # Fair Value Gaps (FVG)
            fvg_signal = self._detect_fvg(df, atr)
            if fvg_signal['signal'] != 0:
                return fvg_signal

            # Break of Structure (BOS)
            bos_signal = self._detect_bos(df)
            if bos_signal['signal'] != 0:
                return bos_signal

            return {'signal': 0, 'confidence': 0, 'details': {}}

        except Exception as e:
            self.logger.log(f"Error en SMC: {e}", "ERROR", "SMC")
            return {'signal': 0, 'confidence': 0, 'details': {}}
    
    def _detect_order_blocks(self, df: pd.DataFrame) -> Dict:
        """Detectar Order Blocks (zonas de institucionales)"""
        highs = df['high'].values[-20:]
        lows = df['low'].values[-20:]
        closes = df['close'].values[-20:]
        opens = df['open'].values[-20:]
        current_price = closes[-1]

        # Bullish Order Block: vela bajista seguida de fuerte movimiento alcista
        # FIX: Cambiar range para evitar índice fuera de límites
        # Con len(closes)=20: range(17, 18) itera solo i=17, evitando acceso a closes[20]
        for i in range(len(closes) - 3, len(closes) - 2):
            if closes[i] < opens[i]:  # Vela bajista
                # Verificar movimiento alcista después
                if closes[i+1] > closes[i] and closes[i+2] > closes[i+1]:
                    ob_low = lows[i]
                    ob_high = opens[i]

                    # Precio retestea el order block
                    if ob_low <= current_price <= ob_high:
                        return {
                            'signal': 1,
                            'confidence': 70,
                            'details': {
                                'pattern': 'bullish_order_block',
                                'ob_zone': (ob_low, ob_high)
                            }
                        }

        # Bearish Order Block
        # FIX: Mismo ajuste para evitar índice fuera de límites
        for i in range(len(closes) - 3, len(closes) - 2):
            if closes[i] > opens[i]:  # Vela alcista
                # Verificar movimiento bajista después
                if closes[i+1] < closes[i] and closes[i+2] < closes[i+1]:
                    ob_high = highs[i]
                    ob_low = closes[i]

                    # Precio retestea el order block
                    if ob_low <= current_price <= ob_high:
                        return {
                            'signal': -1,
                            'confidence': 70,
                            'details': {
                                'pattern': 'bearish_order_block',
                                'ob_zone': (ob_low, ob_high)
                            }
                        }

        return {'signal': 0, 'confidence': 0, 'details': {}}
    
    def _detect_fvg(self, df: pd.DataFrame, atr: float) -> Dict:
        """Detectar Fair Value Gaps (gaps de ineficiencia)"""
        highs = df['high'].values[-10:]
        lows = df['low'].values[-10:]
        current_price = df['close'].values[-1]
        
        # Bullish FVG: gap entre el high de hace 2 velas y el low actual
        for i in range(len(highs) - 2):
            gap_bottom = highs[i]
            gap_top = lows[i+2]
            
            if gap_top > gap_bottom:  # Hay gap
                gap_size = gap_top - gap_bottom
                
                # Gap significativo (> 50% ATR)
                if gap_size > atr * 0.5:
                    # Precio en el gap
                    if gap_bottom <= current_price <= gap_top:
                        return {
                            'signal': 1,
                            'confidence': 65,
                            'details': {
                                'pattern': 'bullish_fvg',
                                'gap_zone': (gap_bottom, gap_top)
                            }
                        }
        
        # Bearish FVG
        for i in range(len(lows) - 2):
            gap_top = lows[i]
            gap_bottom = highs[i+2]
            
            if gap_top > gap_bottom:  # Hay gap
                gap_size = gap_top - gap_bottom
                
                if gap_size > atr * 0.5:
                    if gap_bottom <= current_price <= gap_top:
                        return {
                            'signal': -1,
                            'confidence': 65,
                            'details': {
                                'pattern': 'bearish_fvg',
                                'gap_zone': (gap_bottom, gap_top)
                            }
                        }
        
        return {'signal': 0, 'confidence': 0, 'details': {}}
    
    def _detect_bos(self, df: pd.DataFrame) -> Dict:
        """Detectar Break of Structure"""
        highs = df['high'].values[-30:]
        lows = df['low'].values[-30:]
        closes = df['close'].values[-30:]
        
        # Bullish BOS: ruptura de máximo significativo
        recent_high = np.max(highs[:-3])
        current_close = closes[-1]
        
        if current_close > recent_high:
            return {
                'signal': 1,
                'confidence': 60,
                'details': {
                    'pattern': 'bullish_bos',
                    'broken_level': recent_high
                }
            }
        
        # Bearish BOS: ruptura de mínimo significativo
        recent_low = np.min(lows[:-3])
        
        if current_close < recent_low:
            return {
                'signal': -1,
                'confidence': 60,
                'details': {
                    'pattern': 'bearish_bos',
                    'broken_level': recent_low
                }
            }
        
        return {'signal': 0, 'confidence': 0, 'details': {}}

    def analyze(self, df: pd.DataFrame, atr: float = None) -> Dict:
        """
        Wrapper para compatibilidad con MultiStrategyTrader
        Llama a detect() calculando ATR si es necesario
        """
        if atr is None:
            atr = safe_atr(df, Config.ATR_PERIOD)
        return self.detect(df, atr)

# ==========================================
# SISTEMA DE CONFLUENCIA CON IC
# ==========================================
#
# NOTA: Esta clase NO está siendo usada actualmente.
# MultiStrategyTrader tiene su propio sistema de confluencia integrado.
# Esta clase está aquí para referencia futura si se desea una implementación
# más avanzada con Information Coefficient (IC).
# ==========================================

class ConfluenceSystem:
    """Sistema de confluencia multi-estrategia con Information Coefficient"""
    
    def __init__(self, logger):
        self.logger = logger
        
        # Estrategias disponibles
        self.strategies = {
            'elliott': {'weight': 0.25, 'ic_history': deque(maxlen=60), 'enabled': True},
            'fibonacci': {'weight': 0.25, 'ic_history': deque(maxlen=60), 'enabled': True},
            'wyckoff': {'weight': 0.25, 'ic_history': deque(maxlen=60), 'enabled': True},
            'smc': {'weight': 0.25, 'ic_history': deque(maxlen=60), 'enabled': True}
        }
        
        # Histórico de señales y retornos para IC
        self.signal_history = deque(maxlen=Config.IC_CALCULATION_WINDOW)
        self.return_history = deque(maxlen=Config.IC_CALCULATION_WINDOW)
        
        # Última actualización de pesos
        self.last_weight_update = datetime.now()
        
    def calculate_confluence(self, signals: Dict[str, Dict], min_confluence: float = 65) -> Dict:
        """Calcular confluencia ponderada de señales (usa signal numérico: -1/0/1)"""
        try:
            weighted_signal = 0
            total_weight = 0
            total_confidence = 0
            active_strategies = []
            strategy_details = {}

            for strategy_name, signal_data in signals.items():
                if strategy_name not in self.strategies:
                    continue

                strategy = self.strategies[strategy_name]

                if not strategy['enabled']:
                    continue

                signal_value = signal_data.get('signal', 0)  # -1, 0, 1
                confidence = signal_data.get('confidence', 0)
                weight = strategy['weight']

                if signal_value != 0 and confidence > 0:
                    contribution = signal_value * weight * (confidence / 100)
                    weighted_signal += contribution
                    total_weight += weight
                    total_confidence += confidence * weight

                    active_strategies.append(strategy_name)
                    strategy_details[strategy_name] = {
                        'signal': signal_value,
                        'confidence': confidence,
                        'weight': weight,
                        'contribution': contribution
                    }

                    self.logger.log_strategy_signal(strategy_name, signal_data)

            if total_weight == 0:
                return {
                    'signal': 0,
                    'confidence': 0,
                    'confluence_score': 0,
                    'details': {}
                }

            confluence_score = abs(weighted_signal) * 100
            avg_confidence = total_confidence / total_weight

            if abs(weighted_signal) < (min_confluence / 100):
                final_signal = 0
            else:
                final_signal = 1 if weighted_signal > 0 else -1

            dominant_strategy = max(strategy_details.items(),
                                   key=lambda x: abs(x[1]['contribution']))[0] if strategy_details else 'N/A'

            result = {
                'signal': final_signal,
                'confidence': avg_confidence,
                'confluence_score': confluence_score,
                'dominant_strategy': dominant_strategy,
                'active_strategies': active_strategies,
                'strategy_details': strategy_details,
                'weights': {k: v['weight'] for k, v in self.strategies.items()}
            }

            # Convertir signal numérico a texto para el log
            signal_text = 'BUY' if final_signal == 1 else ('SELL' if final_signal == -1 else 'NONE')
            strategies_str = ', '.join([f'{s}({strategy_details[s]["confidence"]:.0f}%)' for s in active_strategies])
            self.logger.log(
                f"Confluencia: {signal_text} | Score: {confluence_score:.1f}% | "
                f"Confianza: {avg_confidence:.1f}% | "
                f"Estrategias: {strategies_str}",
                "INFO",
                "Confluence"
            )

            return result

        except Exception as e:
            self.logger.log(f"Error en cálculo de confluencia: {e}", "ERROR", "Confluence")
            return {'signal': 0, 'confidence': 0, 'confluence_score': 0, 'details': {}}

# Due to file length, I'll now create a complete integrated bot file and move it to outputs

# ==========================================
# RISK MANAGER Y GESTIÓN (del archivo base)
# ==========================================

class RiskManager:
    """Sistema completo de gestión de riesgo"""
    
    def __init__(self, client, logger):
        self.client = client
        self.logger = logger
        self.daily_loss = 0.0
        self.daily_trades = 0
        self.consecutive_losses = 0
        self.last_reset = datetime.now().date()

        # Kill-switch con cooldown
        self.kill_switch_active = False
        self.cooldown_until = None
        self.last_trade_result = None  # 'win' o 'loss'

        # Tracking de trades por hora
        self.trades_timestamps = []  # Lista de timestamps de trades
        
    def reset_daily_stats(self):
        """Reiniciar estadísticas diarias"""
        current_date = datetime.now().date()
        if current_date > self.last_reset:
            self.daily_loss = 0.0
            self.daily_trades = 0
            self.consecutive_losses = 0
            self.last_reset = current_date
            self.logger.info("Estadísticas diarias reiniciadas")
            
    def calculate_position_size(self, balance: float, entry: float, 
                               stop_loss: float, risk_pct: float = None) -> float:
        """Calcular tamaño de posición basado en riesgo"""
        if risk_pct is None:
            risk_pct = Config.RISK_PER_TRADE
            
        risk_amount = balance * (risk_pct / 100)
        stop_distance = abs(entry - stop_loss)
        
        if stop_distance == 0:
            return 0
            
        position_value = risk_amount / (stop_distance / entry)
        position_size = position_value / entry
        
        # Aplicar límites
        position_value = max(Config.MIN_POSITION_USDT, 
                            min(Config.MAX_POSITION_USDT, position_value))
        
        return round(position_value / entry, 3)
    
    def calculate_stops(self, df: pd.DataFrame, entry: float,
                       side: str) -> Tuple[float, List[float]]:
        """
        Calcular stop loss y take profits dinámicos

        Niveles de TP fijos en 1.5R, 2.5R, 4.0R (conservadores y probados).
        Los porcentajes del perfil (tp1_percentage, tp2_percentage, tp3_percentage)
        determinan QUÉ PORCENTAJE de la posición cerrar en cada TP, NO los niveles.

        Para implementar salidas parciales por perfil, ver PositionManager (futuro).
        """
        # Calcular ATR
        atr = talib.ATR(df['high'], df['low'], df['close'],
                       timeperiod=Config.ATR_PERIOD).iloc[-1]

        stop_distance = atr * Config.ATR_MULTIPLIER

        if side == 'BUY':
            stop_loss = entry - stop_distance
            take_profits = [
                entry + (stop_distance * 1.5),  # TP1: 1.5R
                entry + (stop_distance * 2.5),  # TP2: 2.5R
                entry + (stop_distance * 4.0)   # TP3: 4R
            ]
        else:  # SELL
            stop_loss = entry + stop_distance
            take_profits = [
                entry - (stop_distance * 1.5),  # TP1: 1.5R
                entry - (stop_distance * 2.5),  # TP2: 2.5R
                entry - (stop_distance * 4.0)   # TP3: 4R
            ]

        return round(stop_loss, 2), [round(tp, 2) for tp in take_profits]
    
    def check_risk_limits(self, potential_loss_pct: float) -> bool:
        """
        Verificar si se puede tomar más riesgo

        Args:
            potential_loss_pct: Pérdida potencial en PORCENTAJE del balance (no USDT)
                              Por ejemplo: 1.5 significa 1.5% del balance

        Returns:
            True si se puede operar, False si se exceden los límites
        """
        self.reset_daily_stats()

        # Usar límite del perfil activo (no Config fijo)
        risk_config = RiskProfileConfig.get_config(Config.DEFAULT_RISK_PROFILE)
        max_daily_loss = risk_config.get('max_daily_loss', 5.0)

        # Verificar pérdida diaria (ambos en porcentaje)
        if (self.daily_loss + potential_loss_pct) > max_daily_loss:
            self.logger.warning(
                f"Límite de pérdida diaria alcanzado: {self.daily_loss:.2f}% + "
                f"{potential_loss_pct:.2f}% > {max_daily_loss}% (perfil {Config.DEFAULT_RISK_PROFILE.value})"
            )
            return False

        # Verificar racha de pérdidas
        if self.consecutive_losses >= 3:
            self.logger.warning("Racha de pérdidas detectada - pausar trading")
            return False

        return True

    def activate_kill_switch(self, reason: str, cooldown_minutes: int):
        """Activar kill-switch con cooldown"""
        self.kill_switch_active = True
        self.cooldown_until = datetime.now() + timedelta(minutes=cooldown_minutes)
        self.logger.warning(f"[KILL-SWITCH] Activado por: {reason}. Cooldown hasta: {self.cooldown_until.strftime('%H:%M:%S')}")

    def check_kill_switch(self) -> Tuple[bool, str]:
        """Verificar si kill-switch está activo"""
        if not self.kill_switch_active:
            return False, ""

        # Verificar si ya pasó el cooldown
        if datetime.now() >= self.cooldown_until:
            self.kill_switch_active = False
            self.logger.success("[KILL-SWITCH] Cooldown completado. Sistema reactivado.")
            return False, ""

        remaining = (self.cooldown_until - datetime.now()).total_seconds() / 60
        return True, f"Kill-switch activo. Quedan {remaining:.1f} minutos de cooldown"

    def check_hourly_limit(self) -> Tuple[bool, str]:
        """Verificar límite de trades por hora según perfil"""
        risk_config = RiskProfileConfig.get_config(Config.DEFAULT_RISK_PROFILE)
        max_trades_per_hour = risk_config.get('max_trades_per_hour', 4)

        # Limpiar trades antiguos (más de 1 hora)
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)
        self.trades_timestamps = [ts for ts in self.trades_timestamps if ts > one_hour_ago]

        # Verificar límite
        trades_last_hour = len(self.trades_timestamps)
        if trades_last_hour >= max_trades_per_hour:
            return False, f"Límite de trades por hora alcanzado ({trades_last_hour}/{max_trades_per_hour} en perfil {Config.DEFAULT_RISK_PROFILE.value})"

        return True, ""

    def register_trade(self):
        """Registrar nuevo trade para tracking horario"""
        self.trades_timestamps.append(datetime.now())

    def update_stats(self, pnl_pct: float):
        """
        Actualizar estadísticas de riesgo y activar kill-switch si es necesario

        Args:
            pnl_pct: PnL en PORCENTAJE del balance (no USDT)
                    Valores positivos = ganancia, negativos = pérdida
        """
        self.daily_trades += 1
        risk_config = RiskProfileConfig.get_config(Config.DEFAULT_RISK_PROFILE)

        if pnl_pct < 0:
            self.daily_loss += abs(pnl_pct)
            self.consecutive_losses += 1
            self.last_trade_result = 'loss'

            # Activar kill-switch si se alcanza pérdida diaria máxima
            if self.daily_loss >= risk_config.get('max_daily_loss', 5.0):
                cooldown = risk_config.get('cooldown_after_loss', 60)
                self.activate_kill_switch(f"Pérdida diaria alcanzada ({self.daily_loss:.2f}%)", cooldown)
        else:
            self.consecutive_losses = 0
            self.last_trade_result = 'win'

        self.logger.info(
            f"Stats actualizadas - Pérdida diaria: {self.daily_loss:.2f}%, "
            f"Trades: {self.daily_trades}, Pérdidas consecutivas: {self.consecutive_losses}"
        )

# ==========================================
# SISTEMA DE TRADING MULTI-ESTRATEGIA
# ==========================================


# ==========================================
# POSITION MANAGER
# ==========================================

class PositionManager:
    """Gestor de posiciones con salidas parciales"""
    
    def __init__(self, client, logger, precision_manager, risk_config):
        self.client = client
        self.logger = logger
        self.precision_manager = precision_manager
        self.risk_config = risk_config
        self.current_position = None
    
    def has_position(self):
        return self.current_position is not None


# ORDER MANAGER
# ==========================================

class OrderManager:
    """Gestión de órdenes y posiciones en Binance Futures"""
    
    def __init__(self, client, logger):
        self.client = client
        self.logger = logger
        self.current_position = None
        self.pending_orders = []

        # Tracking de posición para breakeven y trailing
        self.current_position_data = None  # Almacena entry_price, side, stop_loss, take_profits, quantity
        self.tp1_hit = False  # Flag para saber si TP1 fue alcanzado
        
    def get_account_balance(self) -> float:
        """Obtener balance de la cuenta"""
        try:
            if hasattr(self, 'improved_client'):
                return self.improved_client.get_futures_balance()
            else:
                account = self.client.futures_account()
                return float(account['totalWalletBalance'])
        except Exception as e:
            self.logger.error(f"Error obteniendo balance: {e}")
            return 0
    
    def get_position_info(self) -> Dict:
        """Obtener información de posición actual"""
        try:
            positions = self.client.futures_position_information(symbol=Config.SYMBOL)
            position = positions[0] if positions else None
            
            if position and float(position['positionAmt']) != 0:
                return {
                    'symbol': position['symbol'],
                    'amount': float(position['positionAmt']),
                    'entry_price': float(position['entryPrice']),
                    'unrealized_pnl': float(position['unRealizedProfit']),
                    'side': 'BUY' if float(position['positionAmt']) > 0 else 'SELL'
                }
            return None
            
        except Exception as e:
            self.logger.error(f"Error obteniendo posición: {e}")
            return None
    
    def place_order(self, side: str, quantity: float, order_type: str = 'MARKET',
                   price: float = None, stop_price: float = None, reduce_only: bool = False) -> Dict:
        """Colocar orden en Binance Futures"""
        try:
            # Validar y ajustar precisión si existe precision_manager
            if hasattr(self, 'precision_manager') and self.precision_manager:
                # Ajustar cantidad
                quantity = self.precision_manager.round_quantity(quantity)

                # Validar precio con redondeo direccional según side y tipo de orden
                order_price = price if price else stop_price
                if order_price:
                    # Redondeo direccional: LIMIT vs STOP/TP, BUY vs SELL
                    if order_type in ['STOP_LOSS', 'TAKE_PROFIT', 'STOP_MARKET', 'TAKE_PROFIT_MARKET']:
                        order_price = self.precision_manager.round_price(order_price, side, 'STOP_LOSS')
                    else:
                        order_price = self.precision_manager.round_price(order_price, side, 'LIMIT')

                    # Para órdenes reduce-only (SL/TP), NO validar notional mínimo ni ajustar cantidad
                    # Solo respetar precisión
                    if reduce_only or order_type in ['STOP_MARKET', 'TAKE_PROFIT_MARKET']:
                        # Solo redondear, no validar notional
                        quantity = self.precision_manager.round_quantity(quantity)
                        if price:
                            price = order_price
                        if stop_price:
                            stop_price = order_price
                    else:
                        # Para órdenes de apertura, validar con allow_adjust=True
                        is_valid, error_msg, adj_price, adj_quantity = self.precision_manager.validate_order(
                            order_price, quantity, allow_adjust=True
                        )

                        if not is_valid:
                            self.logger.error(f"Orden inválida: {error_msg}")
                            return None

                        quantity = adj_quantity
                        if price:
                            price = adj_price
                        if stop_price:
                            stop_price = adj_price

            params = {
                'symbol': Config.SYMBOL,
                'side': side,
                'type': order_type,
                'quantity': quantity
            }

            if order_type == 'LIMIT' and price:
                params['price'] = price
                params['timeInForce'] = 'GTC'

            elif order_type in ['STOP_MARKET', 'TAKE_PROFIT_MARKET'] and stop_price:
                params['stopPrice'] = stop_price
                params['workingType'] = 'MARK_PRICE'
                # Agregar reduceOnly para órdenes de SL/TP
                params['reduceOnly'] = True

            # Agregar reduceOnly si se especifica explícitamente
            if reduce_only:
                params['reduceOnly'] = True

            order = self.client.futures_create_order(**params)
            
            self.logger.info(
                f"Orden colocada: {side} {quantity} {Config.SYMBOL} "
                f"tipo {order_type} - ID: {order['orderId']}"
            )
            
            return order
            
        except BinanceAPIException as e:
            self.logger.error(f"Error API Binance: {e.message}")
            return None
        except Exception as e:
            self.logger.error(f"Error colocando orden: {e}")
            return None
    
    def open_position(self, signal: Dict, df: pd.DataFrame) -> bool:
        """Abrir nueva posición con gestión de riesgo"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("[TRADING] >>> INTENTANDO ABRIR POSICION")
            self.logger.info("=" * 60)
            
            # Verificar que no hay posición abierta
            if self.get_position_info():
                self.logger.warning("[ERROR] Ya existe una posicion abierta")
                return False
            
            balance = self.get_account_balance()
            self.logger.info(f"[BALANCE] Balance disponible: ${balance:.2f}")
            
            if balance <= 0:
                self.logger.error("[ERROR] Balance insuficiente")
                return False
            
            # Determinar dirección
            side = 'BUY' if signal['confluence']['action'] > 0 else 'SELL'
            entry_price = signal['current_price']
            self.logger.info(f"[SETUP] Lado: {side} | Precio entrada: ${entry_price:.2f}")
            
            # Calcular stops
            stop_loss, take_profits = self.risk_manager.calculate_stops(df, entry_price, side)
            self.logger.info(f"[SETUP] Stop Loss: ${stop_loss:.2f}")
            self.logger.info(f"[SETUP] Take Profits: {[f'${tp:.2f}' for tp in take_profits]}")

            # Validar RR mínimo según perfil de riesgo
            risk_config = RiskProfileConfig.get_config(Config.DEFAULT_RISK_PROFILE)
            min_rr_ratio = risk_config.get('min_rr_ratio', 1.5)

            # Calcular RR actual (TP1 como referencia conservadora para validación)
            risk = abs(entry_price - stop_loss)
            reward = abs(take_profits[0] - entry_price) if take_profits else 0  # Usar TP1 como referencia
            actual_rr_ratio = (reward / risk) if risk > 0 else 0

            self.logger.info(f"[RR] Ratio TP1: {actual_rr_ratio:.2f} | Mínimo requerido: {min_rr_ratio:.2f}")

            if actual_rr_ratio < min_rr_ratio:
                self.logger.warning(f"[ERROR] RR insuficiente ({actual_rr_ratio:.2f} < {min_rr_ratio:.2f} requerido por perfil {Config.DEFAULT_RISK_PROFILE.value})")
                return False

            # Calcular RR efectivo ponderado por los porcentajes de TP del perfil
            # Esto da una métrica más realista del riesgo/recompensa esperado
            tp1_pct = risk_config.get('tp1_percentage', 50) / 100.0
            tp2_pct = risk_config.get('tp2_percentage', 30) / 100.0
            tp3_pct = risk_config.get('tp3_percentage', 20) / 100.0

            weighted_rr = 0
            if len(take_profits) >= 1 and tp1_pct > 0:
                rr1 = abs(take_profits[0] - entry_price) / risk
                weighted_rr += rr1 * tp1_pct
            if len(take_profits) >= 2 and tp2_pct > 0:
                rr2 = abs(take_profits[1] - entry_price) / risk
                weighted_rr += rr2 * tp2_pct
            if len(take_profits) >= 3 and tp3_pct > 0:
                rr3 = abs(take_profits[2] - entry_price) / risk
                weighted_rr += rr3 * tp3_pct

            self.logger.info(
                f"[RR EFECTIVO] Ponderado por TPs: {weighted_rr:.2f}x "
                f"({tp1_pct*100:.0f}%@{actual_rr_ratio:.2f}R + "
                f"{tp2_pct*100:.0f}%@{abs(take_profits[1]-entry_price)/risk if len(take_profits)>1 else 0:.2f}R + "
                f"{tp3_pct*100:.0f}%@{abs(take_profits[2]-entry_price)/risk if len(take_profits)>2 else 0:.2f}R)"
            )

            # Calcular tamaño de posición
            position_size = self.risk_manager.calculate_position_size(
                balance, entry_price, stop_loss
            )
            self.logger.info(f"[SETUP] Tamano de posicion: {position_size:.4f} BTC")
            
            if position_size <= 0:
                self.logger.error("[ERROR] Tamano de posicion invalido")
                return False
            
            # Verificar límites de riesgo (CORREGIDO: calcular en USDT y %)
            loss_usdt = abs(entry_price - stop_loss) * position_size
            loss_pct = (loss_usdt / balance) * 100

            self.logger.info(f"[RISK] Perdida potencial: ${loss_usdt:.2f} ({loss_pct:.2f}%)")

            # Validar max_risk_usdt del perfil (límite absoluto en dólares)
            account_tier = RiskProfileConfig.get_account_tier(balance)
            adjusted_risk_config = RiskProfileConfig.adjust_for_account_tier(risk_config, account_tier, balance)
            max_risk_usdt = adjusted_risk_config.get('max_risk_usdt')

            if max_risk_usdt and loss_usdt > max_risk_usdt:
                self.logger.warning(
                    f"[ERROR] Riesgo en USDT excede límite: ${loss_usdt:.2f} > ${max_risk_usdt:.2f} "
                    f"(tier {account_tier.value})"
                )
                return False

            if not self.risk_manager.check_risk_limits(loss_pct):
                self.logger.warning("[ERROR] Limites de riesgo excedidos")
                return False

            self.logger.info("[TRADING] >> Verificaciones pasadas, colocando orden...")

            # Colocar orden principal
            entry_order = self.place_order(side, position_size, 'MARKET')

            if not entry_order:
                self.logger.error("[ERROR] Fallo orden de entrada")
                return False

            self.logger.info(f"[SUCCESS] Orden de entrada ejecutada: {entry_order['orderId']}")

            # VALIDACIÓN CRÍTICA: Verificar si el ajuste por notional mínimo aumentó el riesgo descontroladamente
            # Obtener la posición real para ver la cantidad ejecutada
            actual_position = self.get_position_info()
            if actual_position:
                actual_quantity = abs(actual_position['amount'])
                actual_loss_usdt = abs(entry_price - stop_loss) * actual_quantity
                actual_loss_pct = (actual_loss_usdt / balance) * 100

                # Verificar si el riesgo real excede el planificado más allá de la tolerancia (2%)
                risk_increase_pct = ((actual_loss_pct - loss_pct) / loss_pct) * 100 if loss_pct > 0 else 0

                if risk_increase_pct > 2.0:  # Tolerancia del 2%
                    self.logger.error(
                        f"[CRITICAL] Ajuste por notional mínimo aumentó riesgo en {risk_increase_pct:.1f}%: "
                        f"${loss_usdt:.2f} ({loss_pct:.2f}%) → ${actual_loss_usdt:.2f} ({actual_loss_pct:.2f}%). "
                        f"CANCELANDO posición..."
                    )
                    # Cerrar posición inmediatamente
                    self.close_position("Riesgo excedido por ajuste de notional")
                    return False

                # Verificar también max_risk_usdt con la cantidad real
                if max_risk_usdt and actual_loss_usdt > max_risk_usdt:
                    self.logger.error(
                        f"[CRITICAL] Riesgo real excede max_risk_usdt: ${actual_loss_usdt:.2f} > ${max_risk_usdt:.2f}. "
                        f"CANCELANDO posición..."
                    )
                    self.close_position("Riesgo real excede max_risk_usdt")
                    return False

                # Actualizar valores con los reales
                position_size = actual_quantity
                loss_usdt = actual_loss_usdt
                loss_pct = actual_loss_pct
                self.logger.info(
                    f"[RISK FINAL] Riesgo real: ${loss_usdt:.2f} ({loss_pct:.2f}%) - Dentro de límites permitidos"
                )
            
            # Colocar stop loss
            sl_side = 'SELL' if side == 'BUY' else 'BUY'
            sl_order = self.place_order(
                sl_side, position_size, 'STOP_MARKET', 
                stop_price=stop_loss
            )
            
            if sl_order:
                self.logger.info(f"[SUCCESS] Stop Loss colocado: {sl_order['orderId']}")
            
            # Colocar take profits parciales según perfil
            risk_config = RiskProfileConfig.get_config(Config.DEFAULT_RISK_PROFILE)
            tp1_pct = risk_config.get('tp1_percentage', 50) / 100.0
            tp2_pct = risk_config.get('tp2_percentage', 30) / 100.0
            tp3_pct = risk_config.get('tp3_percentage', 20) / 100.0

            tp_sizes = [
                position_size * tp1_pct,
                position_size * tp2_pct,
                position_size * tp3_pct
            ]

            self.logger.info(
                f"[TP CONFIG] Salidas parciales según perfil {Config.DEFAULT_RISK_PROFILE.value}: "
                f"TP1={tp1_pct*100:.0f}%, TP2={tp2_pct*100:.0f}%, TP3={tp3_pct*100:.0f}%"
            )

            for i, (tp_price, tp_size) in enumerate(zip(take_profits, tp_sizes)):
                if tp_size > 0:  # Solo colocar si el porcentaje es > 0
                    tp_order = self.place_order(
                        sl_side, round(tp_size, 3), 'TAKE_PROFIT_MARKET',
                        stop_price=tp_price
                    )
                    if tp_order:
                        self.logger.info(f"[SUCCESS] Take Profit {i+1} colocado: {tp_order['orderId']} ({tp_size:.4f} = {tp1_pct*100 if i==0 else (tp2_pct*100 if i==1 else tp3_pct*100):.0f}%)")
                
            # Registrar trade (incluyendo métricas de riesgo, RR efectivo y señales individuales)
            # Extraer señales individuales para IC más preciso
            signals_data = signal.get('signals', {})
            trade_data = {
                'timestamp': datetime.now().isoformat(),
                'symbol': Config.SYMBOL,
                'side': side,
                'entry_price': entry_price,
                'quantity': position_size,
                'strategy': signal['confluence']['dominant_strategy'],
                'confidence': signal['confluence']['confidence'],
                'risk_profile': Config.DEFAULT_RISK_PROFILE.value,
                'risk_usdt': round(loss_usdt, 2),
                'risk_pct': round(loss_pct, 2),
                'rr_ratio': round(weighted_rr, 2),  # RR efectivo ponderado
                # Señales individuales para cálculo de IC
                'elliott_signal': signals_data.get('elliott', {}).get('signal', 0),
                'elliott_conf': round(signals_data.get('elliott', {}).get('confidence', 0), 1),
                'fibonacci_signal': signals_data.get('fibonacci', {}).get('signal', 0),
                'fibonacci_conf': round(signals_data.get('fibonacci', {}).get('confidence', 0), 1),
                'wyckoff_signal': signals_data.get('wyckoff', {}).get('signal', 0),
                'wyckoff_conf': round(signals_data.get('wyckoff', {}).get('confidence', 0), 1),
                'smc_signal': signals_data.get('smc', {}).get('signal', 0),
                'smc_conf': round(signals_data.get('smc', {}).get('confidence', 0), 1)
            }
            
            # Registrar trade en CSV (el logger ya maneja el envío a GUI)
            self.logger.log_trade(trade_data)
            
            self.logger.info("=" * 60)
            self.logger.info(
                f"[SUCCESS] >>> POSICION ABIERTA: {side} {position_size:.4f} @ ${entry_price:.2f}"
            )
            self.logger.info(f"         SL: ${stop_loss:.2f} | TPs: {[f'${tp:.2f}' for tp in take_profits]}")
            self.logger.info("=" * 60)

            # Almacenar datos de posición para breakeven/trailing (almacenar en OrderManager)
            self.current_position_data = {
                'entry_price': entry_price,
                'side': side,
                'stop_loss': stop_loss,
                'take_profits': take_profits,
                'quantity': position_size,
                'sl_order_id': sl_order['orderId'] if sl_order else None
            }

            return True
            
        except Exception as e:
            self.logger.error(f"[ERROR] Error abriendo posicion: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def close_position(self, reason: str = "Signal", entry_price: float = None,
                      entry_time: datetime = None, strategy: str = None,
                      confidence: float = None) -> bool:
        """
        Cerrar posición actual y registrar PnL en CSV

        Args:
            reason: Motivo del cierre
            entry_price: Precio de entrada (opcional, para calcular PnL preciso)
            entry_time: Hora de entrada (para calcular duración)
            strategy: Estrategia que generó la señal
            confidence: Confianza de la estrategia
        """
        try:
            position = self.get_position_info()
            if not position:
                return False

            side = 'SELL' if position['side'] == 'BUY' else 'BUY'
            quantity = abs(position['amount'])

            # Obtener precio actual para exit_price
            current_price = float(self.client.futures_symbol_ticker(symbol=Config.SYMBOL)['price'])

            # Cerrar posición
            close_order = self.place_order(side, quantity, 'MARKET')

            if close_order:
                # Cancelar órdenes pendientes
                self.cancel_all_orders()

                # Calcular PnL
                pnl_usdt = position['unrealized_pnl']
                balance = self.get_account_balance()
                pnl_pct = (pnl_usdt / balance) * 100

                # Actualizar estadísticas
                self.risk_manager.update_stats(pnl_pct)

                # Calcular duración si se proporcionó entry_time
                duration_minutes = None
                if entry_time:
                    duration_minutes = (datetime.now() - entry_time).total_seconds() / 60

                # Registrar cierre en CSV
                close_data = {
                    'timestamp': datetime.now().isoformat(),
                    'symbol': Config.SYMBOL,
                    'side': position['side'],
                    'entry_price': entry_price if entry_price else position['entry_price'],
                    'exit_price': current_price,
                    'quantity': quantity,
                    'pnl_usdt': round(pnl_usdt, 2),
                    'pnl_pct': round(pnl_pct, 4),
                    'strategy': strategy if strategy else 'N/A',
                    'confidence': confidence if confidence else 0,
                    'risk_profile': '',
                    'mode': reason,
                    'risk_usdt': '',
                    'risk_pct': '',
                    'rr_ratio': '',
                    'duration_minutes': round(duration_minutes, 2) if duration_minutes else '',
                    'max_drawdown_pct': '',
                    'funding_paid': '',
                    # Señales individuales (vacías en cierre)
                    'elliott_signal': '',
                    'elliott_conf': '',
                    'fibonacci_signal': '',
                    'fibonacci_conf': '',
                    'wyckoff_signal': '',
                    'wyckoff_conf': '',
                    'smc_signal': '',
                    'smc_conf': ''
                }

                self.logger.log_trade(close_data)

                self.logger.info(
                    f"POSICIÓN CERRADA: {reason} - PnL: ${pnl_usdt:.2f} ({pnl_pct:.2f}%)"
                )

                # Limpiar tracking de posición para breakeven/trailing
                self.current_position_data = None
                self.tp1_hit = False

                return True

        except Exception as e:
            self.logger.error(f"Error cerrando posición: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def cancel_all_orders(self):
        """Cancelar todas las órdenes abiertas"""
        try:
            self.client.futures_cancel_all_open_orders(symbol=Config.SYMBOL)
            self.logger.info("Todas las órdenes canceladas")
        except Exception as e:
            self.logger.error(f"Error cancelando órdenes: {e}")

# ==========================================
# BOT PRINCIPAL
# ==========================================


# ==========================================

# ==========================================
# MULTI-STRATEGY TRADER
# ==========================================

class MultiStrategyTrader:
    """Coordinador de múltiples estrategias con gestión de confluencia"""
    
    def __init__(self, client, logger):
        self.client = client
        self.logger = logger
        
        # Inicializar estrategias
        self.elliott = ElliottWaveDetector(logger)
        self.fibonacci = FibonacciAnalyzer(logger)
        self.wyckoff = WyckoffVSADetector(logger)
        self.smc = SmartMoneyDetector(logger)
        self.risk_manager = RiskManager(client, logger)
        
        # Pesos dinámicos de estrategias
        self.strategy_weights = {
            'elliott': {'weight': 0.25, 'ic_window': []},
            'fibonacci': {'weight': 0.25, 'ic_window': []},
            'wyckoff': {'weight': 0.25, 'ic_window': []},
            'smc': {'weight': 0.25, 'ic_window': []}
        }

        self.ic_lookback = 20
        self.min_confluence = 2  # Mínimo de estrategias de acuerdo (cambiado de 3 a 2 para ser más flexible)

        # Timestamp para actualización periódica de IC weights
        self.last_ic_update = datetime.now()
        self.ic_update_interval_days = 7  # Actualizar cada 7 días
        

    def is_near_funding_time(self, minutes_window=10):
        """
        Verificar si estamos cerca del cobro de funding

        Returns:
            tuple: (is_near: bool, next_funding_utc: str, next_funding_local: str)
        """
        from datetime import datetime, timedelta
        import pytz

        now = datetime.utcnow()
        current_hour = now.hour
        current_minute = now.minute

        # Horarios de funding: 00:00, 08:00, 16:00 UTC
        funding_hours = [0, 8, 16]

        # Encontrar próximo funding
        next_funding_hour = None
        for funding_hour in funding_hours:
            if current_hour < funding_hour or (current_hour == funding_hour and current_minute < 0):
                next_funding_hour = funding_hour
                break

        if next_funding_hour is None:
            # Próximo funding es mañana a las 00:00
            next_funding_hour = funding_hours[0]
            next_funding = datetime(now.year, now.month, now.day, next_funding_hour, 0, 0, tzinfo=pytz.UTC) + timedelta(days=1)
        else:
            next_funding = datetime(now.year, now.month, now.day, next_funding_hour, 0, 0, tzinfo=pytz.UTC)

        # Convertir a hora local de Santiago (America/Santiago)
        santiago_tz = pytz.timezone('America/Santiago')
        next_funding_santiago = next_funding.astimezone(santiago_tz)

        # Verificar si estamos en ventana
        is_near = False
        for funding_hour in funding_hours:
            # Calcular minutos hasta el funding
            if current_hour == funding_hour:
                if current_minute < minutes_window or current_minute > (60 - minutes_window):
                    is_near = True
                    break
            elif current_hour == (funding_hour - 1) % 24:
                if current_minute > (60 - minutes_window):
                    is_near = True
                    break
            elif current_hour == (funding_hour + 1) % 24:
                if current_minute < minutes_window:
                    is_near = True
                    break

        return is_near, next_funding.strftime('%H:%M UTC'), next_funding_santiago.strftime('%H:%M CLT')

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcular todos los indicadores técnicos necesarios"""
        # RSI
        df['rsi'] = talib.RSI(df['close'], timeperiod=Config.RSI_PERIOD)
        
        # MACD
        macd, signal, hist = talib.MACD(df['close'])
        df['macd'] = macd
        df['macd_signal'] = signal
        df['macd_hist'] = hist
        
        # ATR
        df['atr'] = talib.ATR(df['high'], df['low'], df['close'], 
                             timeperiod=Config.ATR_PERIOD)
        
        # Medias móviles
        df['sma_20'] = talib.SMA(df['close'], timeperiod=20)
        df['sma_50'] = talib.SMA(df['close'], timeperiod=50)
        df['ema_12'] = talib.EMA(df['close'], timeperiod=12)
        df['ema_26'] = talib.EMA(df['close'], timeperiod=26)
        
        # Bollinger Bands
        upper, middle, lower = talib.BBANDS(df['close'])
        df['bb_upper'] = upper
        df['bb_middle'] = middle
        df['bb_lower'] = lower
        
        return df
    
    def update_ic_weights(self, predictions: Dict, actual_return: float):
        """Actualizar pesos basados en Information Coefficient"""
        for strategy_name, pred in predictions.items():
            if strategy_name not in self.strategy_weights:
                continue

            # Calcular correlación entre predicción y retorno real
            ic = 1.0 if (pred > 0 and actual_return > 0) or \
                       (pred < 0 and actual_return < 0) else -1.0

            self.strategy_weights[strategy_name]['ic_window'].append(ic)

            # Mantener ventana de tamaño fijo
            if len(self.strategy_weights[strategy_name]['ic_window']) > self.ic_lookback:
                self.strategy_weights[strategy_name]['ic_window'].pop(0)

        # Normalizar pesos basados en IC promedio
        ic_values = []
        for strategy_data in self.strategy_weights.values():
            if strategy_data['ic_window']:
                ic_values.append(np.mean(strategy_data['ic_window']))
            else:
                ic_values.append(0)

        # Solo usar ICs positivos
        ic_positive = [max(ic, 0) for ic in ic_values]
        total_ic = sum(ic_positive)

        if total_ic > 0:
            for i, (name, data) in enumerate(self.strategy_weights.items()):
                data['weight'] = ic_positive[i] / total_ic

        self.logger.info(f"Pesos actualizados: {self.strategy_weights}")

    def check_and_recalibrate_ic_weights(self):
        """
        Verificar si han pasado 7 días y recalibrar IC weights basándose en rendimiento histórico

        Esta función se ejecuta periódicamente para rebalancear los pesos de las estrategias
        basándose en el rendimiento de los últimos trades registrados en el CSV.
        """
        now = datetime.now()
        days_since_update = (now - self.last_ic_update).total_seconds() / (24 * 3600)

        if days_since_update >= self.ic_update_interval_days:
            self.logger.info(f"[IC-WEIGHTS] Han pasado {days_since_update:.1f} días. Recalibrando pesos...")

            try:
                # Usar la ruta correcta del CSV (logs/trading_bot_trades.csv)
                trades_csv_path = self.logger.get_trades_csv_path()

                # Leer últimos trades del CSV
                if os.path.exists(trades_csv_path):
                    df_trades = pd.read_csv(trades_csv_path)

                    # Filtrar solo trades de los últimos 30 días con estrategia definida
                    if len(df_trades) > 0 and 'timestamp' in df_trades.columns and 'strategy' in df_trades.columns:
                        df_trades['timestamp'] = pd.to_datetime(df_trades['timestamp'])
                        thirty_days_ago = now - timedelta(days=30)
                        recent_trades = df_trades[
                            (df_trades['timestamp'] > thirty_days_ago) &
                            (df_trades['strategy'].notna()) &
                            (df_trades['strategy'] != 'N/A') &
                            (df_trades['pnl_pct'].notna())
                        ]

                        if len(recent_trades) > 0:
                            # Calcular win rate y PnL promedio por estrategia
                            strategy_performance = {}

                            for strategy in ['elliott', 'fibonacci', 'wyckoff', 'smc']:
                                strat_trades = recent_trades[recent_trades['strategy'].str.lower() == strategy]

                                if len(strat_trades) > 0:
                                    win_rate = len(strat_trades[strat_trades['pnl_pct'] > 0]) / len(strat_trades)
                                    avg_pnl = strat_trades['pnl_pct'].mean()

                                    # Combinar win rate y avg_pnl para score
                                    # Peso: 60% win rate, 40% avg pnl normalizado
                                    score = (win_rate * 0.6) + (min(max(avg_pnl / 5.0, -1), 1) * 0.4)
                                    strategy_performance[strategy] = max(score, 0)  # No negativos
                                else:
                                    strategy_performance[strategy] = 0.25  # Peso neutral si no hay datos

                            # Normalizar scores a pesos
                            total_score = sum(strategy_performance.values())
                            if total_score > 0:
                                for strategy, score in strategy_performance.items():
                                    new_weight = score / total_score
                                    old_weight = self.strategy_weights[strategy]['weight']
                                    self.strategy_weights[strategy]['weight'] = new_weight
                                    self.logger.info(
                                        f"[IC-WEIGHTS] {strategy}: {old_weight:.2%} → {new_weight:.2%}"
                                    )

                                self.last_ic_update = now
                                self.logger.info(
                                    f"[IC-WEIGHTS] Recalibración completada basada en {len(recent_trades)} trades recientes"
                                )
                            else:
                                # Resetear a pesos iguales si no hay datos suficientes
                                for strategy in self.strategy_weights:
                                    self.strategy_weights[strategy]['weight'] = 0.25
                                self.last_ic_update = now
                                self.logger.info("[IC-WEIGHTS] Pesos reseteados a valores por defecto (0.25)")
                        else:
                            self.logger.info("[IC-WEIGHTS] No hay trades recientes suficientes para recalibrar")
                    else:
                        self.logger.info("[IC-WEIGHTS] CSV de trades no tiene formato esperado")
                else:
                    self.logger.info(f"[IC-WEIGHTS] Archivo {trades_csv_path} no existe aún")

            except Exception as e:
                self.logger.error(f"[IC-WEIGHTS] Error recalibrando pesos: {e}")
                import traceback
                self.logger.error(traceback.format_exc())
    
    def check_confluence(self, signals: Dict) -> Dict:
        """Verificar confluencia entre estrategias"""
        result = {
            'action': 0,
            'confidence': 0.0,
            'strategies_agree': 0,
            'dominant_strategy': None
        }
        
        # Extraer señales y confianzas
        strategy_signals = []
        for strategy, analysis in signals.items():
            self.logger.debug(f"[DEBUG] {strategy}: signal={analysis['signal']}, confidence={analysis['confidence']}")
            
            if analysis['signal'] != 0 and analysis['confidence'] >= 60:  # CAMBIO: >= en lugar de >
                strategy_signals.append({
                    'name': strategy,
                    'signal': analysis['signal'],
                    'confidence': analysis['confidence'],
                    'weight': self.strategy_weights[strategy]['weight']
                })
                self.logger.debug(f"[DEBUG] {strategy} INCLUIDA en confluencia")
            else:
                self.logger.debug(f"[DEBUG] {strategy} EXCLUIDA (signal={analysis['signal']}, conf={analysis['confidence']})")
        
        self.logger.info(f"[CONFLUENCE] Estrategias validas: {len(strategy_signals)}/{len(signals)}")
        
        if len(strategy_signals) < self.min_confluence:
            self.logger.info(f"[CONFLUENCE] Insuficientes estrategias ({len(strategy_signals)} < {self.min_confluence})")
            return result
        
        # Verificar acuerdo en dirección
        buy_signals = [s for s in strategy_signals if s['signal'] > 0]
        sell_signals = [s for s in strategy_signals if s['signal'] < 0]
        
        self.logger.info(f"[CONFLUENCE] Buy signals: {len(buy_signals)}, Sell signals: {len(sell_signals)}")
        
        if len(buy_signals) >= self.min_confluence:
            result['action'] = 1
            result['strategies_agree'] = len(buy_signals)
            
            # Calcular confianza ponderada normalizada
            # Redistribuir pesos entre estrategias activas
            total_weight = sum(s['weight'] for s in buy_signals)
            if total_weight > 0:
                # Normalizar pesos para que sumen 1.0
                normalized_signals = [
                    {**s, 'normalized_weight': s['weight'] / total_weight} 
                    for s in buy_signals
                ]
                weighted_conf = sum(s['confidence'] * s['normalized_weight'] for s in normalized_signals)
            else:
                weighted_conf = sum(s['confidence'] for s in buy_signals) / len(buy_signals)
            
            result['confidence'] = weighted_conf
            
            # Estrategia dominante
            result['dominant_strategy'] = max(buy_signals, 
                                             key=lambda x: x['confidence'])['name']
            
            self.logger.info(f"[CONFLUENCE] >>> SENAL DE COMPRA detectada (conf={weighted_conf:.1f}%)")
            
        elif len(sell_signals) >= self.min_confluence:
            result['action'] = -1
            result['strategies_agree'] = len(sell_signals)
            
            # Calcular confianza ponderada normalizada
            # Redistribuir pesos entre estrategias activas
            total_weight = sum(s['weight'] for s in sell_signals)
            if total_weight > 0:
                # Normalizar pesos para que sumen 1.0
                normalized_signals = [
                    {**s, 'normalized_weight': s['weight'] / total_weight} 
                    for s in sell_signals
                ]
                weighted_conf = sum(s['confidence'] * s['normalized_weight'] for s in normalized_signals)
            else:
                weighted_conf = sum(s['confidence'] for s in sell_signals) / len(sell_signals)
            
            result['confidence'] = weighted_conf
            
            # Estrategia dominante
            result['dominant_strategy'] = max(sell_signals, 
                                             key=lambda x: x['confidence'])['name']
            
            self.logger.info(f"[CONFLUENCE] >>> SENAL DE VENTA detectada (conf={weighted_conf:.1f}%)")
        
        return result
    
    def analyze_market(self, df: pd.DataFrame) -> Dict:
        """Análisis completo del mercado con todas las estrategias"""
        # Calcular indicadores
        df = self.calculate_indicators(df)

        # Verificar y recalibrar IC weights cada 7 días
        self.check_and_recalibrate_ic_weights()

        # Ejecutar cada estrategia
        signals = {
            'elliott': self.elliott.analyze(df),
            'fibonacci': self.fibonacci.analyze(df),
            'wyckoff': self.wyckoff.analyze(df),
            'smc': self.smc.analyze(df)
        }

        # Verificar confluencia
        confluence = self.check_confluence(signals)

        # Usar umbrales del perfil activo
        risk_config = RiskProfileConfig.get_config(Config.DEFAULT_RISK_PROFILE)
        min_confidence_threshold = risk_config.get('confidence_threshold', 60)

        # Compilar resultado final
        result = {
            'timestamp': datetime.now(),
            'signals': signals,
            'confluence': confluence,
            'should_trade': confluence['confidence'] >= min_confidence_threshold,  # Usar umbral del perfil
            'current_price': df['close'].iloc[-1]
        }

        if result['should_trade']:
            self.logger.info(
                f"SEÑAL DE TRADING: {confluence['action']} con confianza "
                f"{confluence['confidence']:.1f}% (umbral: {min_confidence_threshold}%) - "
                f"{confluence['strategies_agree']} estrategias de acuerdo"
            )

        return result

# ==========================================
# GESTOR DE ÓRDENES
# ==========================================

# TRADING BOT PRINCIPAL
# ==========================================

class TradingBot:
    """Bot principal que coordina todos los componentes"""
    
    def __init__(self, message_queue=None):
        # CRÍTICO: Fix para Windows - configurar event loop policy LO MÁS TEMPRANO POSIBLE
        # DEBE estar ANTES de cualquier operación async, cliente Binance, o WebSocket Manager
        # Esto previene errores de aiodns: "aiodns needs a SelectorEventLoop on Windows"
        if sys.platform == 'win32':
            try:
                import asyncio
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            except Exception as e:
                print(f"Warning: No se pudo configurar event loop policy: {e}")

        # Inicializar logger
        self.logger_system = TradingLogger()
        self.logger = self.logger_system  # Usar el wrapper completo

        # Message queue para GUI (opcional) - conectar inmediatamente
        self.message_queue = message_queue
        if message_queue:
            self.logger_system.set_gui_queue(message_queue)

        # Inicializar cliente Binance
        self.client = self._init_client()

        # Inicializar OrderPrecisionManager (pasar logger_system completo)
        self.precision_manager = OrderPrecisionManager(self.client, Config.SYMBOL, self.logger_system)

        # Componentes del sistema (pasar logger_system completo a todos)
        self.trader = MultiStrategyTrader(self.client, self.logger_system)
        self.order_manager = OrderManager(self.client, self.logger_system)
        self.order_manager.risk_manager = self.trader.risk_manager
        self.order_manager.precision_manager = self.precision_manager  # Agregar precision manager
        
        # Control de ejecución
        self.is_running = False
        self.stop_event = threading.Event()
        self.trading_thread = None
        self.ws_manager = None
        self.polling_thread = None  # Thread para modo polling
        self.ws_retry_thread = None  # Thread para reintentos de WebSocket
        self.ws_retry_count = 0
        self.last_ws_retry = None
        self.using_polling = False  # Flag para saber si estamos en modo polling

        # Datos de mercado con protección contra condiciones de carrera
        self.market_data = pd.DataFrame()
        self.market_data_lock = threading.Lock()  # Mutex para evitar race conditions
        self.last_signal = None

        # Tracking de posición para cierre por tiempo
        self.position_entry_time = None

        # NOTA: current_position_data y tp1_hit están solo en OrderManager (no duplicar aquí)
        # para evitar inconsistencias. Acceder vía self.order_manager.current_position_data

        # Control de frecuencia de logs (reducir ruido)
        self.last_log_time = datetime.now()
        self.log_interval_minutes = 5  # Loguear estado cada 5 minutos
        self.last_logged_state = None  # Para detectar cambios de estado
        
    def _init_client(self) -> Client:
        """Inicializar cliente de Binance"""
        try:
            if Config.USE_TESTNET and BINANCE_FIXES_AVAILABLE:
                self.improved_client = ImprovedBinanceClient(
                    Config.API_KEY,
                    Config.SECRET_KEY,
                    testnet=Config.USE_TESTNET
                )
                client = self.improved_client.client
                self.logger.info("Cliente inicializado en TESTNET (con ImprovedBinanceClient)")
            else:
                client = Client(Config.API_KEY, Config.SECRET_KEY, testnet=Config.USE_TESTNET)
                if Config.USE_TESTNET:
                    self.logger.info("Cliente inicializado en TESTNET (cliente estándar)")
                else:
                    self.logger.info("Cliente inicializado en PRODUCCIÓN")
            
            # Sincronizar tiempo con servidor de Binance
            try:
                server_time = client.get_server_time()
                local_time = int(time.time() * 1000)
                time_offset = server_time['serverTime'] - local_time
                self.logger.info(f"Diferencia de tiempo con servidor: {time_offset}ms")
                
                # Si la diferencia es mayor a 1000ms, advertir al usuario
                if abs(time_offset) > 1000:
                    self.logger.warning(
                        f"[WARNING] Tu reloj local esta {abs(time_offset)}ms "
                        f"{'adelantado' if time_offset < 0 else 'atrasado'}. "
                        f"Esto puede causar errores. Considera sincronizar tu reloj."
                    )
            except Exception as e:
                self.logger.warning(f"No se pudo verificar sincronización de tiempo: {e}")
            
            # Configurar apalancamiento dinámico según perfil y tier
            try:
                # Obtener balance para determinar tier
                account_info = client.futures_account()
                balance = float(account_info['totalWalletBalance'])

                # Determinar tier y ajustar configuración
                account_tier = RiskProfileConfig.get_account_tier(balance)
                risk_config = RiskProfileConfig.get_config(Config.DEFAULT_RISK_PROFILE)
                risk_config = RiskProfileConfig.adjust_for_account_tier(risk_config, account_tier, balance)

                # Obtener apalancamiento máximo del perfil
                max_leverage = risk_config.get('max_leverage', Config.LEVERAGE)

                # Aplicar apalancamiento
                client.futures_change_leverage(
                    symbol=Config.SYMBOL,
                    leverage=max_leverage
                )
                client.futures_change_margin_type(
                    symbol=Config.SYMBOL,
                    marginType='ISOLATED'
                )
                self.logger.info(
                    f"Apalancamiento configurado: {max_leverage}x ISOLATED "
                    f"(Perfil: {Config.DEFAULT_RISK_PROFILE.value}, Tier: {account_tier.value}, Balance: ${balance:.2f})"
                )
            except Exception as e:
                self.logger.warning(f"No se pudo configurar apalancamiento: {e}")
                
            return client
            
        except Exception as e:
            self.logger.error(f"Error inicializando cliente: {e}")
            raise
    
    def load_historical_data(self, limit: int = 200):
        """Cargar datos históricos para análisis inicial"""
        try:
            klines = self.client.futures_klines(
                symbol=Config.SYMBOL,
                interval=Config.TIMEFRAME,
                limit=limit
            )
            
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_volume',
                'taker_buy_quote_volume', 'ignore'
            ])
            
            # Convertir a tipos numéricos
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            self.market_data = df
            self.logger.info(f"Datos históricos cargados: {len(df)} velas")
            
        except Exception as e:
            self.logger.error(f"Error cargando datos históricos: {e}")
    
    def on_kline_message(self, msg):
        """Procesar mensaje de WebSocket con nueva vela"""
        try:
            # Detectar errores críticos del WebSocket
            if msg.get('e') == 'error':
                error_type = msg.get('type', '')
                error_msg = msg.get('m', '')
                
                self.logger.error(f"Error WebSocket: {msg}")
                
                # Si el WebSocket se cerró, cambiar a polling
                if 'ReadLoopClosed' in error_type or 'closed' in error_msg.lower():
                    self.logger.warning("[WEBSOCKET] WebSocket cerrado inesperadamente")
                    self.logger.info("[WEBSOCKET] Cambiando automaticamente a modo POLLING...")
                    
                    # Detener WebSocket
                    self.stop_websocket()
                    
                    # Activar polling si no está activo ya
                    if not self.polling_thread or not self.polling_thread.is_alive():
                        self.start_polling_mode()
                
                return
            
            kline = msg.get('k')
            if not kline:
                return
            
            # Solo procesar velas cerradas
            if not kline['x']:
                return
            
            # Actualizar DataFrame con protección contra race conditions
            new_candle = pd.DataFrame([{
                'open': float(kline['o']),
                'high': float(kline['h']),
                'low': float(kline['l']),
                'close': float(kline['c']),
                'volume': float(kline['v'])
            }], index=[pd.to_datetime(kline['t'], unit='ms')])

            with self.market_data_lock:
                self.market_data = pd.concat([self.market_data, new_candle])
                self.market_data = self.market_data.tail(500)  # Mantener últimas 500 velas

            self.logger.info(f"Nueva vela: Close={kline['c']}, Volume={kline['v']}")

            # Analizar mercado
            self.analyze_and_trade()
            
        except Exception as e:
            self.logger.error(f"Error procesando mensaje WebSocket: {e}")
            # En caso de error grave, cambiar a polling
            if "closed" in str(e).lower() or "connection" in str(e).lower():
                self.logger.info("[WEBSOCKET] Error de conexion detectado, cambiando a POLLING...")
                if not self.polling_thread or not self.polling_thread.is_alive():
                    self.start_polling_mode()
    
    def analyze_and_trade(self):
        """Ejecutar análisis y tomar decisiones de trading"""
        try:
            # Crear copia estable de market_data dentro del lock para evitar race conditions
            with self.market_data_lock:
                if len(self.market_data) < 100:
                    self.logger.debug(f"Datos insuficientes: {len(self.market_data)} velas (mínimo 100)")
                    return
                # Copiar datos dentro del lock y liberar inmediatamente
                market_data_snapshot = self.market_data.copy()

            # Analizar mercado con la copia estable (fuera del lock)
            signal = self.trader.analyze_market(market_data_snapshot)

            # Verificar posición actual
            position = self.order_manager.get_position_info()

            # Control de frecuencia de logs (reducir ruido)
            # Solo loguear si:
            # 1. Han pasado más de log_interval_minutes desde el último log
            # 2. El estado ha cambiado (should_trade, posición abierta/cerrada)
            now = datetime.now()
            time_since_last_log = (now - self.last_log_time).total_seconds() / 60

            current_state = {
                'should_trade': signal['should_trade'],
                'has_position': position is not None,
                'action': signal['confluence']['action'],
                'confidence': round(signal['confluence']['confidence'], 0)
            }

            state_changed = (self.last_logged_state != current_state)
            time_to_log = (time_since_last_log >= self.log_interval_minutes)

            if state_changed or time_to_log or signal['should_trade']:
                # Log detallado de la señal
                self.logger.info(f"[ANALISIS] Analisis completado:")
                self.logger.info(f"   - Should trade: {signal['should_trade']}")
                self.logger.info(f"   - Confluence action: {signal['confluence']['action']}")
                self.logger.info(f"   - Confidence: {signal['confluence']['confidence']:.1f}%")
                self.logger.info(f"   - Strategies agree: {signal['confluence']['strategies_agree']}")

                if position:
                    self.logger.info(f"[POSICION] Posicion actual: {position['side']} {position['amount']}")
                else:
                    self.logger.info("[POSICION] Sin posicion abierta")

                self.last_log_time = now
                self.last_logged_state = current_state
            
            # Lógica de trading
            if signal['should_trade'] and not position:
                self.logger.info("[TRADING] >>> Intentando abrir nueva posicion...")

                # 1. Verificar kill-switch
                kill_active, kill_msg = self.trader.risk_manager.check_kill_switch()
                if kill_active:
                    self.logger.warning(f"[KILL-SWITCH] {kill_msg}")
                    return

                # 2. Verificar límite de trades por hora
                hourly_ok, hourly_msg = self.trader.risk_manager.check_hourly_limit()
                if not hourly_ok:
                    self.logger.warning(f"[HOURLY-LIMIT] {hourly_msg}")
                    return

                # 3. Verificar ventana de funding según perfil de riesgo activo
                risk_config = RiskProfileConfig.get_config(Config.DEFAULT_RISK_PROFILE)
                funding_window = risk_config.get('funding_filter_minutes', 10)
                is_near_funding, next_utc, next_local = self.trader.is_near_funding_time(funding_window)
                if is_near_funding:
                    self.logger.warning(
                        f"[FUNDING] Dentro de ventana de funding (±{funding_window}min por perfil {Config.DEFAULT_RISK_PROFILE.value}). "
                        f"Próximo funding: {next_utc} ({next_local}). Operación bloqueada."
                    )
                else:
                    # Abrir nueva posición (usar snapshot estable)
                    success = self.order_manager.open_position(signal, market_data_snapshot)
                    if success:
                        self.last_signal = signal
                        self.position_entry_time = datetime.now()  # Guardar tiempo de entrada
                        self.trader.risk_manager.register_trade()  # Registrar para límite horario
                        self.logger.info("[SUCCESS] Posicion abierta exitosamente")
                    else:
                        self.logger.warning("[WARNING] No se pudo abrir posicion")
                    
            elif position:
                # Gestionar posición existente
                # 1. Verificar cierre por tiempo máximo
                if self.position_entry_time:
                    time_in_position = (datetime.now() - self.position_entry_time).total_seconds() / 60  # minutos
                    max_time = Config.MAX_POSITION_HOLD_MINUTES if hasattr(Config, 'MAX_POSITION_HOLD_MINUTES') else 240
                    if time_in_position >= max_time:
                        self.logger.warning(f"[TIMEOUT] Posición lleva {time_in_position:.1f} minutos (máximo {max_time}). Cerrando por tiempo...")
                        self.order_manager.close_position("Tiempo máximo excedido")
                        self.position_entry_time = None
                        return

                # 2. Gestionar breakeven y trailing stop
                if self.order_manager.current_position_data:
                    risk_config = RiskProfileConfig.get_config(Config.DEFAULT_RISK_PROFILE)
                    current_price = float(market_data_snapshot['close'].iloc[-1])
                    pos_data = self.order_manager.current_position_data
                    entry_price = pos_data['entry_price']
                    side = pos_data['side']
                    take_profits = pos_data['take_profits']

                    # 2a. Breakeven automático al alcanzar TP1
                    if not self.order_manager.tp1_hit and risk_config.get('breakeven_at_tp1', False):
                        tp1_price = take_profits[0] if take_profits else None
                        tp1_reached = False

                        if tp1_price:
                            if side == 'BUY' and current_price >= tp1_price:
                                tp1_reached = True
                            elif side == 'SELL' and current_price <= tp1_price:
                                tp1_reached = True

                        if tp1_reached:
                            self.logger.info(f"[BREAKEVEN] TP1 alcanzado (${current_price:.2f}), moviendo SL a breakeven (${entry_price:.2f})")
                            # Cancelar SL actual
                            if pos_data.get('sl_order_id'):
                                try:
                                    self.order_manager.client.futures_cancel_order(
                                        symbol=Config.SYMBOL,
                                        orderId=pos_data['sl_order_id']
                                    )
                                    self.logger.info(f"[BREAKEVEN] SL anterior cancelado: {pos_data['sl_order_id']}")
                                except Exception as e:
                                    self.logger.warning(f"[BREAKEVEN] No se pudo cancelar SL anterior: {e}")

                            # Colocar nuevo SL en breakeven
                            sl_side = 'SELL' if side == 'BUY' else 'BUY'
                            quantity = pos_data['quantity']
                            new_sl = self.order_manager.place_order(
                                sl_side, quantity, 'STOP_MARKET',
                                stop_price=entry_price
                            )
                            if new_sl:
                                self.logger.info(f"[BREAKEVEN] Nuevo SL en breakeven: {new_sl['orderId']}")
                                pos_data['sl_order_id'] = new_sl['orderId']
                                pos_data['stop_loss'] = entry_price
                                self.order_manager.tp1_hit = True

                    # 2b. Trailing stop (solo después de TP1 o si está configurado)
                    if self.order_manager.tp1_hit and risk_config.get('use_trailing', False):
                        # Calcular ATR para trailing stop
                        if 'atr' in market_data_snapshot.columns and len(market_data_snapshot) > 0:
                            atr = float(market_data_snapshot['atr'].iloc[-1])
                            # Usar multiplicador configurable para trailing (por defecto 2.5x ATR)
                            trailing_multiplier = Config.ATR_MULTIPLIER_TRAILING if hasattr(Config, 'ATR_MULTIPLIER_TRAILING') else 2.5
                            trailing_distance = atr * trailing_multiplier

                            current_sl = pos_data['stop_loss']

                            # Calcular nuevo SL trailing
                            if side == 'BUY':
                                # Para LONG: SL sube con el precio, nunca baja
                                new_trailing_sl = current_price - trailing_distance
                                if new_trailing_sl > current_sl:
                                    self.logger.info(f"[TRAILING] Ajustando SL: ${current_sl:.2f} → ${new_trailing_sl:.2f} (precio actual: ${current_price:.2f})")

                                    # Cancelar SL actual
                                    if pos_data.get('sl_order_id'):
                                        try:
                                            self.order_manager.client.futures_cancel_order(
                                                symbol=Config.SYMBOL,
                                                orderId=pos_data['sl_order_id']
                                            )
                                        except Exception as e:
                                            self.logger.warning(f"[TRAILING] No se pudo cancelar SL: {e}")

                                    # Colocar nuevo SL trailing
                                    new_sl = self.order_manager.place_order(
                                        'SELL', pos_data['quantity'], 'STOP_MARKET',
                                        stop_price=new_trailing_sl
                                    )
                                    if new_sl:
                                        pos_data['sl_order_id'] = new_sl['orderId']
                                        pos_data['stop_loss'] = new_trailing_sl
                                        self.logger.info(f"[TRAILING] SL actualizado: {new_sl['orderId']}")

                            else:  # SELL
                                # Para SHORT: SL baja con el precio, nunca sube
                                new_trailing_sl = current_price + trailing_distance
                                if new_trailing_sl < current_sl:
                                    self.logger.info(f"[TRAILING] Ajustando SL: ${current_sl:.2f} → ${new_trailing_sl:.2f} (precio actual: ${current_price:.2f})")

                                    # Cancelar SL actual
                                    if pos_data.get('sl_order_id'):
                                        try:
                                            self.order_manager.client.futures_cancel_order(
                                                symbol=Config.SYMBOL,
                                                orderId=pos_data['sl_order_id']
                                            )
                                        except Exception as e:
                                            self.logger.warning(f"[TRAILING] No se pudo cancelar SL: {e}")

                                    # Colocar nuevo SL trailing
                                    new_sl = self.order_manager.place_order(
                                        'BUY', pos_data['quantity'], 'STOP_MARKET',
                                        stop_price=new_trailing_sl
                                    )
                                    if new_sl:
                                        pos_data['sl_order_id'] = new_sl['orderId']
                                        pos_data['stop_loss'] = new_trailing_sl
                                        self.logger.info(f"[TRAILING] SL actualizado: {new_sl['orderId']}")

                # 3. Cerrar si hay señal contraria fuerte
                if signal['should_trade']:
                    position_side = 1 if position['side'] == 'BUY' else -1
                    signal_side = signal['confluence']['action']

                    if position_side != signal_side and signal['confluence']['confidence'] > 80:
                        self.logger.info("[TRADING] Senal contraria detectada, cerrando posicion...")
                        self.order_manager.close_position("Señal contraria")
                        self.position_entry_time = None
            elif signal['should_trade']:
                self.logger.info("[WARNING] Senal de trading pero no se cumplieron las condiciones")
                        
        except Exception as e:
            self.logger.error(f"Error en análisis y trading: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    def start_websocket(self):
        """Iniciar WebSocket para datos en tiempo real"""
        try:
            # Event loop policy ya configurado en __init__ para Windows

            # Intentar usar AlternativeWebSocketManager o PollingDataManager
            use_polling = False
            
            try:
                # Primero intentar con ThreadedWebsocketManager
                self.ws_manager = ThreadedWebsocketManager(
                    api_key=Config.API_KEY,
                    api_secret=Config.SECRET_KEY,
                    testnet=Config.USE_TESTNET
                )
                
                # Timeout de 5 segundos para verificar inicio
                import threading
                init_event = threading.Event()
                
                def start_ws():
                    try:
                        self.ws_manager.start()
                        init_event.set()
                    except Exception as e:
                        self.logger.error(f"Error iniciando WebSocket en thread: {e}")
                
                ws_thread = threading.Thread(target=start_ws, daemon=True)
                ws_thread.start()
                
                # Esperar máximo 5 segundos
                if init_event.wait(timeout=5):
                    # Suscribirse a klines
                    subscription_key = self.ws_manager.start_kline_futures_socket(
                        callback=self.on_kline_message,
                        symbol=Config.SYMBOL,
                        interval=Config.TIMEFRAME
                    )
                    self.logger.success(f"WebSocket iniciado exitosamente")
                    self.logger.info(f"Suscripción activa - Key: {subscription_key}")
                    self.logger.info(f"Canal: {Config.SYMBOL} klines {Config.TIMEFRAME}")
                else:
                    raise Exception("Binance Socket Manager failed to initialize after 5 seconds")

            except Exception as e:
                self.logger.warning(f"WebSocket no disponible: {e}")
                self.logger.info(">>> Activando MODO POLLING como alternativa...")
                use_polling = True
            
            # Si WebSocket falla, usar polling y programar reintentos
            if use_polling:
                self.start_polling_mode()
                self.start_ws_retry_mechanism()
            
        except Exception as e:
            self.logger.error(f"Error iniciando WebSocket: {e}")
            self.logger.info("Iniciando modo de polling...")
            self.start_polling_mode()
    
    def start_ws_retry_mechanism(self):
        """Iniciar mecanismo de reintento automático de WebSocket"""
        if self.ws_retry_thread and self.ws_retry_thread.is_alive():
            return

        def ws_retry_loop():
            """Loop que intenta reconectar WebSocket con backoff exponencial"""
            retry_delays = [60, 120, 300, 600, 900]  # 1min, 2min, 5min, 10min, 15min
            retry_index = 0

            while not self.stop_event.is_set() and self.using_polling:
                # Calcular delay según número de intentos
                delay = retry_delays[min(retry_index, len(retry_delays) - 1)]

                self.logger.info(f"[WS-RETRY] Próximo intento de reconexión WebSocket en {delay}s")

                # Esperar antes del reintento
                if self.stop_event.wait(timeout=delay):
                    break  # stop_event fue activado

                if not self.using_polling:
                    break  # Ya reconectamos exitosamente

                # Intentar reconectar
                self.logger.info(f"[WS-RETRY] Intento #{retry_index + 1} de reconexión WebSocket...")
                try:
                    # Detener polling actual
                    if self.polling_thread and self.polling_thread.is_alive():
                        # No detener stop_event, solo esperar a que termine naturalmente
                        pass

                    # Intentar iniciar WebSocket
                    self.ws_manager = ThreadedWebsocketManager(
                        api_key=Config.API_KEY,
                        api_secret=Config.SECRET_KEY,
                        testnet=Config.USE_TESTNET
                    )

                    import threading
                    init_event = threading.Event()

                    def start_ws():
                        try:
                            self.ws_manager.start()
                            init_event.set()
                        except Exception as e:
                            self.logger.debug(f"Error en start WebSocket: {e}")

                    ws_thread = threading.Thread(target=start_ws, daemon=True)
                    ws_thread.start()

                    if init_event.wait(timeout=5):
                        # WebSocket iniciado exitosamente
                        subscription_key = self.ws_manager.start_kline_futures_socket(
                            callback=self.on_kline_message,
                            symbol=Config.SYMBOL,
                            interval=Config.TIMEFRAME
                        )
                        self.logger.success(f"[WS-RETRY] WebSocket reconectado exitosamente!")
                        self.using_polling = False
                        # El polling thread se detendrá naturalmente en la próxima iteración
                        break  # Salir del loop de reintentos
                    else:
                        raise Exception("Timeout iniciando WebSocket")

                except Exception as e:
                    self.logger.debug(f"[WS-RETRY] Fallo intento #{retry_index + 1}: {e}")
                    retry_index += 1

        self.using_polling = True
        self.ws_retry_thread = threading.Thread(target=ws_retry_loop, daemon=True, name="WS-Retry")
        self.ws_retry_thread.start()
        self.logger.info("[WS-RETRY] Mecanismo de reintento automático activado")

    def start_polling_mode(self):
        """Modo alternativo: obtener datos mediante polling cada minuto"""
        # Verificar si ya hay un thread de polling activo
        if self.polling_thread and self.polling_thread.is_alive():
            self.logger.info("Modo polling ya está activo")
            return

        self.using_polling = True
        self.logger.info("=== MODO POLLING ACTIVADO ===")
        self.logger.info("Los datos se actualizarán cada 60 segundos")
        
        def polling_loop():
            while not self.stop_event.is_set():
                try:
                    # Obtener última vela cerrada
                    klines = self.client.futures_klines(
                        symbol=Config.SYMBOL,
                        interval=Config.TIMEFRAME,
                        limit=2  # Última vela cerrada
                    )
                    
                    if klines:
                        kline = klines[-2]  # Penúltima es la última cerrada
                        
                        # Actualizar DataFrame con protección contra race conditions
                        new_candle = pd.DataFrame([{
                            'open': float(kline[1]),
                            'high': float(kline[2]),
                            'low': float(kline[3]),
                            'close': float(kline[4]),
                            'volume': float(kline[5])
                        }], index=[pd.to_datetime(kline[0], unit='ms')])

                        # Evitar duplicados (verificar con lock)
                        should_analyze = False
                        with self.market_data_lock:
                            if new_candle.index[0] not in self.market_data.index:
                                self.market_data = pd.concat([self.market_data, new_candle])
                                self.market_data = self.market_data.tail(500)
                                should_analyze = True

                        if should_analyze:
                            self.logger.info(f"[POLLING] Nueva vela: Close={kline[4]}")
                            # Analizar mercado
                            self.analyze_and_trade()
                    
                except Exception as e:
                    self.logger.error(f"Error en polling: {e}")
                
                # Esperar intervalo configurado en Config
                time.sleep(Config.POLLING_INTERVAL if hasattr(Config, 'POLLING_INTERVAL') and Config.POLLING_INTERVAL >= 1 else 60)
        
        # Iniciar thread de polling
        self.polling_thread = threading.Thread(target=polling_loop, daemon=True)
        self.polling_thread.start()
        self.logger.info("[OK] Thread de polling iniciado")
    
    def stop_websocket(self):
        """Detener WebSocket"""
        try:
            if self.ws_manager:
                try:
                    self.ws_manager.stop()
                    self.logger.info("WebSocket detenido")
                except Exception as e:
                    self.logger.warning(f"Error al detener WebSocket (puede estar ya cerrado): {e}")
                finally:
                    self.ws_manager = None  # Limpiar referencia
        except Exception as e:
            self.logger.error(f"Error deteniendo WebSocket: {e}")
    
    def trading_loop(self):
        """Bucle principal de trading"""
        self.logger.info("=== INICIANDO BOT DE TRADING ===")
        
        try:
            # Cargar datos históricos
            self.load_historical_data()
            
            # Iniciar WebSocket
            self.start_websocket()
            
            # Mantener el bot ejecutándose
            while not self.stop_event.is_set():
                time.sleep(1)
                
                # Verificar salud del sistema cada minuto
                if int(time.time()) % 60 == 0:
                    self.health_check()
                    
        except Exception as e:
            self.logger.error(f"Error en bucle de trading: {e}")
            
        finally:
            self.cleanup()
    
    def health_check(self):
        """Verificar salud del sistema"""
        try:
            # Verificar conexión (con fallback si futures_ping no existe)
            try:
                self.client.futures_ping()
            except AttributeError:
                # Fallback a ping() o get_server_time()
                try:
                    self.client.ping()
                except AttributeError:
                    self.client.get_server_time()
            
            # Verificar balance
            balance = self.order_manager.get_account_balance()
            
            # Verificar posición
            position = self.order_manager.get_position_info()
            
            status = f"Balance: ${balance:.2f}"
            if position:
                status += f" | Posición: {position['side']} {position['amount']}"
                
            self.logger.info(f"Health Check OK - {status}")
            
        except Exception as e:
            self.logger.error(f"Health Check falló: {e}")
    
    def start(self):
        """Iniciar bot"""
        if self.is_running:
            self.logger.warning("Bot ya está en ejecución")
            return
            
        self.is_running = True
        self.stop_event.clear()
        
        self.trading_thread = threading.Thread(target=self.trading_loop, daemon=True)
        self.trading_thread.start()
        
        self.logger.info("Bot iniciado exitosamente")
    
    def stop(self):
        """Detener bot"""
        if not self.is_running:
            return
            
        self.logger.info("Deteniendo bot...")
        
        # Cerrar posiciones abiertas
        position = self.order_manager.get_position_info()
        if position:
            self.order_manager.close_position("Bot detenido")
            self.position_entry_time = None  # Limpiar tracking de tiempo

        # Cancelar órdenes pendientes
        self.order_manager.cancel_all_orders()
        
        # Señalar detención
        self.stop_event.set()
        self.is_running = False
        
        # Detener WebSocket
        self.stop_websocket()
        
        self.logger.info("Bot detenido")
    
    def cleanup(self):
        """Limpieza de recursos"""
        try:
            self.stop_websocket()
            
            # Detener polling thread si está activo
            if self.polling_thread and self.polling_thread.is_alive():
                self.logger.info("Deteniendo polling thread...")
                # El thread se detendrá cuando stop_event sea True
                self.polling_thread.join(timeout=2)
            
            self.logger.info("Limpieza completada")
        except Exception as e:
            self.logger.error(f"Error en limpieza: {e}")

# ==========================================
# INTERFAZ GRÁFICA
# ==========================================


# ==========================================
# INTERFAZ GRÁFICA COMPLETA
# ==========================================

class TradingBotGUI:
    """Interfaz gráfica profesional para el bot de trading"""

    def __init__(self, root, bot=None):
        """
        Args:
            root: tk.Tk() root window
            bot: (Opcional) TradingBot instance. Si None, crea uno nuevo.
        """
        self.root = root
        self.root.title("Bot de Trading Algorítmico - Binance Futures")
        self.root.geometry("1200x800")

        # Queue para comunicación entre threads
        self.message_queue = queue.Queue()

        # Bot instance con queue
        if bot is not None:
            # Usar bot provisto (ej. desde IntegratedTradingBot)
            self.bot = bot
            # Conectar message_queue si el bot no tiene uno
            if not hasattr(self.bot, 'message_queue') or self.bot.message_queue is None:
                self.bot.message_queue = self.message_queue
        else:
            # Crear bot nuevo (comportamiento legacy)
            self.bot = TradingBot(message_queue=self.message_queue)

        self.setup_gui()
        self.check_queue()
        
    def setup_gui(self):
        """Configurar interfaz gráfica completa"""
        # Estilo
        style = ttk.Style()
        style.theme_use('clam')
        
        # Frame principal
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # ===== Panel de Control =====
        control_frame = ttk.LabelFrame(main_frame, text="Panel de Control", padding="10")
        control_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        # Botones de control
        self.start_button = ttk.Button(
            control_frame, text="▶ INICIAR BOT", 
            command=self.start_bot, width=20
        )
        self.start_button.grid(row=0, column=0, padx=5)
        
        self.stop_button = ttk.Button(
            control_frame, text="■ DETENER BOT", 
            command=self.stop_bot, width=20, state='disabled'
        )
        self.stop_button.grid(row=0, column=1, padx=5)
        
        # Indicadores de estado
        self.status_label = ttk.Label(
            control_frame, text="Estado: DETENIDO", 
            font=('Arial', 10, 'bold')
        )
        self.status_label.grid(row=0, column=2, padx=20)
        
        # Progreso
        self.progress = ttk.Progressbar(
            control_frame, mode='indeterminate', 
            length=200
        )
        self.progress.grid(row=0, column=3, padx=5)
        
        # ===== Información de Cuenta =====
        account_frame = ttk.LabelFrame(main_frame, text="Información de Cuenta", padding="10")
        account_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N), pady=5)
        
        # Labels de información
        self.balance_label = ttk.Label(account_frame, text="Balance: $0.00")
        self.balance_label.grid(row=0, column=0, sticky=tk.W)
        
        self.pnl_label = ttk.Label(account_frame, text="PnL Diario: $0.00")
        self.pnl_label.grid(row=1, column=0, sticky=tk.W)
        
        self.position_label = ttk.Label(account_frame, text="Posición: Ninguna")
        self.position_label.grid(row=2, column=0, sticky=tk.W)
        
        # ===== Log de Trading =====
        log_frame = ttk.LabelFrame(main_frame, text="Log de Actividad", padding="10")
        log_frame.grid(row=1, column=1, rowspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=15, width=60, 
            state='disabled', wrap='word'
        )
        self.log_text.pack(fill='both', expand=True)
        
        # Configurar tags de color
        self.log_text.tag_config('INFO', foreground='black')
        self.log_text.tag_config('SUCCESS', foreground='green', font=('Arial', 9, 'bold'))
        self.log_text.tag_config('WARNING', foreground='orange')
        self.log_text.tag_config('ERROR', foreground='red', font=('Arial', 9, 'bold'))
        
        # ===== Tabla de Operaciones =====
        trades_frame = ttk.LabelFrame(main_frame, text="Operaciones Recientes", padding="10")
        trades_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        # Treeview para operaciones
        columns = ('Tiempo', 'Tipo', 'Precio', 'Cantidad', 'PnL', 'Estrategia')
        self.trades_tree = ttk.Treeview(
            trades_frame, columns=columns, 
            show='headings', height=8
        )
        
        for col in columns:
            self.trades_tree.heading(col, text=col)
            width = 100 if col != 'Tiempo' else 150
            self.trades_tree.column(col, width=width)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(trades_frame, orient='vertical', command=self.trades_tree.yview)
        self.trades_tree.configure(yscrollcommand=scrollbar.set)
        
        self.trades_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # ===== Estadísticas =====
        stats_frame = ttk.LabelFrame(main_frame, text="Estadísticas", padding="10")
        stats_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        # Grid de estadísticas
        self.stats_labels = {}
        stats = [
            ('Total Trades:', '0'),
            ('Win Rate:', '0%'),
            ('Profit Factor:', '0.00'),
            ('Max Drawdown:', '0%'),
            ('Sharpe Ratio:', '0.00'),
            ('Avg Win:', '$0.00'),
            ('Avg Loss:', '$0.00'),
            ('Consecutive Losses:', '0')
        ]
        
        for i, (label, value) in enumerate(stats):
            ttk.Label(stats_frame, text=label).grid(row=i//4, column=(i%4)*2, sticky=tk.W, padx=5)
            self.stats_labels[label] = ttk.Label(stats_frame, text=value, font=('Arial', 9, 'bold'))
            self.stats_labels[label].grid(row=i//4, column=(i%4)*2+1, sticky=tk.W, padx=5)
        
        # Configurar pesos de grid
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
    def start_bot(self):
        """Iniciar el bot de trading"""
        self.bot.start()
        
        # Actualizar UI
        self.start_button.config(state='disabled')
        self.stop_button.config(state='normal')
        self.status_label.config(text="Estado: ACTIVO", foreground='green')
        self.progress.start()
        
        self.add_log("Bot de trading iniciado", 'SUCCESS')
        self.load_historical_trades()
        self.update_account_info()
        self.update_stats()
        
        # Iniciar actualización periódica
        self.schedule_updates()
    
    def load_historical_trades(self):
        """Cargar trades históricos del CSV"""
        try:
            csv_file = 'trading_bot_trades.csv'
            if not os.path.exists(csv_file):
                return
            
            import pandas as pd
            df = pd.read_csv(csv_file)
            
            # Limpiar tabla actual
            for item in self.trades_tree.get_children():
                self.trades_tree.delete(item)
            
            # Cargar últimas 50 operaciones
            for _, row in df.tail(50).iterrows():
                trade_data = {
                    'timestamp': row.get('timestamp', 'N/A'),
                    'side': row.get('side', 'N/A'),
                    'price': row.get('price', 0),
                    'quantity': row.get('quantity', 0),
                    'pnl': row.get('pnl', 0) if 'pnl' in row else 0,
                    'strategy': row.get('strategy', 'N/A')
                }
                self.add_trade(trade_data)
            
            self.add_log(f"Cargadas {min(50, len(df))} operaciones históricas", 'INFO')
            
        except Exception as e:
            self.add_log(f"Error cargando trades históricos: {e}", 'WARNING')
        
    def stop_bot(self):
        """Detener el bot de trading"""
        # Confirmación
        if not messagebox.askyesno("Confirmar", "¿Desea detener el bot? Se cerrarán todas las posiciones abiertas."):
            return
            
        self.bot.stop()
        
        # Actualizar UI
        self.start_button.config(state='normal')
        self.stop_button.config(state='disabled')
        self.status_label.config(text="Estado: DETENIDO", foreground='red')
        self.progress.stop()
        
        self.add_log("Bot de trading detenido", 'WARNING')
        
    def add_log(self, message: str, tag: str = 'INFO'):
        """Agregar mensaje al log"""
        self.log_text.config(state='normal')
        
        timestamp = datetime.now().strftime('%H:%M:%S')
        full_message = f"[{timestamp}] {message}\n"
        
        self.log_text.insert('end', full_message, tag)
        self.log_text.see('end')
        
        # Limitar a 1000 líneas
        lines = int(self.log_text.index('end-1c').split('.')[0])
        if lines > 1000:
            self.log_text.delete('1.0', '2.0')
        
        self.log_text.config(state='disabled')
        
    def update_account_info(self):
        """Actualizar información de cuenta"""
        try:
            # Balance
            balance = self.bot.order_manager.get_account_balance()
            self.balance_label.config(text=f"Balance: ${balance:.2f}")
            
            # Posición
            position = self.bot.order_manager.get_position_info()
            if position:
                # Calcular tiempo abierto
                if hasattr(self.bot, 'last_signal') and self.bot.last_signal:
                    entry_time = self.bot.last_signal.get('timestamp', datetime.now())
                    time_open = datetime.now() - entry_time
                    hours = int(time_open.total_seconds() // 3600)
                    minutes = int((time_open.total_seconds() % 3600) // 60)
                    time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
                else:
                    time_str = "N/A"
                
                # Información detallada de posición
                pos_text = f"Posición: {position['side']} {position['amount']:.4f} @ ${position['entry_price']:.2f} (Abierta: {time_str})"
                self.position_label.config(text=pos_text)
                
                # PnL con color
                pnl = position.get('unrealized_pnl', 0)
                pnl_color = 'green' if pnl > 0 else 'red' if pnl < 0 else 'black'
                pnl_symbol = "+" if pnl > 0 else ""
                self.pnl_label.config(
                    text=f"PnL No Realizado: {pnl_symbol}${pnl:.2f}",
                    foreground=pnl_color
                )
                
                # Log de estrategia (si disponible)
                if hasattr(self.bot, 'last_signal') and self.bot.last_signal:
                    strategy = self.bot.last_signal.get('confluence', {}).get('dominant_strategy', 'N/A')
                    confidence = self.bot.last_signal.get('confluence', {}).get('confidence', 0)
                    self.add_log(f"Estrategia activa: {strategy} (conf: {confidence:.1f}%)", 'INFO')
            else:
                self.position_label.config(text="Posición: Ninguna")
                self.pnl_label.config(text="PnL No Realizado: $0.00", foreground='black')
                
        except Exception as e:
            self.add_log(f"Error actualizando información: {e}", 'ERROR')
            
    def add_trade(self, trade_data: Dict):
        """Agregar operación a la tabla"""
        try:
            # Formatear timestamp
            timestamp_raw = trade_data.get('timestamp', '')
            if 'T' in timestamp_raw or '-' in timestamp_raw:  # ISO format
                try:
                    dt = datetime.fromisoformat(timestamp_raw.replace('Z', '+00:00'))
                    timestamp = dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    timestamp = timestamp_raw
            else:
                timestamp = timestamp_raw
            
            # Preparar valores
            side = trade_data.get('side', 'N/A')
            price = trade_data.get('price', 0)
            quantity = trade_data.get('quantity', 0)
            pnl = trade_data.get('pnl', 0)
            strategy = trade_data.get('strategy', 'N/A')
            
            values = (
                timestamp,
                side,
                f"${price:.2f}",
                f"{quantity:.4f}",
                f"${pnl:.2f}" if pnl != 0 else "Abierta",
                strategy
            )
            
            self.trades_tree.insert('', 0, values=values)
            
            # Colorear según PnL
            if pnl > 0:
                self.trades_tree.item(self.trades_tree.get_children()[0], tags=('profit',))
                self.trades_tree.tag_configure('profit', foreground='green')
            elif pnl < 0:
                self.trades_tree.item(self.trades_tree.get_children()[0], tags=('loss',))
                self.trades_tree.tag_configure('loss', foreground='red')
            
            # Limitar a últimas 50 operaciones
            children = self.trades_tree.get_children()
            if len(children) > 50:
                self.trades_tree.delete(children[-1])
                
        except Exception as e:
            self.add_log(f"Error agregando trade: {e}", 'ERROR')
            
    def update_stats(self):
        """Actualizar estadísticas de trading"""
        try:
            # Leer trades del CSV si existe
            csv_file = 'trading_bot_trades.csv'
            if not os.path.exists(csv_file):
                return
            
            import pandas as pd
            df = pd.read_csv(csv_file)
            
            if len(df) == 0:
                return
            
            # Calcular estadísticas
            total_trades = len(df)
            winning_trades = len(df[df['pnl'] > 0]) if 'pnl' in df.columns else 0
            losing_trades = len(df[df['pnl'] < 0]) if 'pnl' in df.columns else 0
            
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            if 'pnl' in df.columns:
                avg_win = df[df['pnl'] > 0]['pnl'].mean() if winning_trades > 0 else 0
                avg_loss = abs(df[df['pnl'] < 0]['pnl'].mean()) if losing_trades > 0 else 0
                total_pnl = df['pnl'].sum()
                
                # Profit factor
                gross_profit = df[df['pnl'] > 0]['pnl'].sum() if winning_trades > 0 else 0
                gross_loss = abs(df[df['pnl'] < 0]['pnl'].sum()) if losing_trades > 0 else 1
                profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
                
                # Max drawdown (simplificado)
                cumulative = df['pnl'].cumsum()
                running_max = cumulative.cummax()
                drawdown = (cumulative - running_max) / running_max * 100
                max_drawdown = abs(drawdown.min()) if len(drawdown) > 0 else 0
                
                # Consecutive losses
                consecutive_losses = 0
                current_streak = 0
                for pnl in df['pnl']:
                    if pnl < 0:
                        current_streak += 1
                        consecutive_losses = max(consecutive_losses, current_streak)
                    else:
                        current_streak = 0
            else:
                avg_win = 0
                avg_loss = 0
                profit_factor = 0
                max_drawdown = 0
                consecutive_losses = 0
            
            # Actualizar labels
            self.stats_labels['Total Trades:'].config(text=str(total_trades))
            self.stats_labels['Win Rate:'].config(text=f"{win_rate:.1f}%")
            self.stats_labels['Profit Factor:'].config(text=f"{profit_factor:.2f}")
            self.stats_labels['Max Drawdown:'].config(text=f"{max_drawdown:.1f}%")
            self.stats_labels['Sharpe Ratio:'].config(text="N/A")  # Requiere más cálculo
            self.stats_labels['Avg Win:'].config(text=f"${avg_win:.2f}")
            self.stats_labels['Avg Loss:'].config(text=f"${avg_loss:.2f}")
            self.stats_labels['Consecutive Losses:'].config(text=str(consecutive_losses))
            
        except Exception as e:
            self.add_log(f"Error calculando estadísticas: {e}", 'ERROR')
        
    def schedule_updates(self):
        """Programar actualizaciones periódicas"""
        if self.bot.is_running:
            self.update_account_info()
            self.update_stats()
            self.root.after(5000, self.schedule_updates)  # Actualizar cada 5 segundos
            
    def check_queue(self):
        """Procesar mensajes de la cola"""
        try:
            while True:
                msg_type, data = self.message_queue.get_nowait()
                
                if msg_type == 'log':
                    self.add_log(data['message'], data.get('level', 'INFO'))
                elif msg_type == 'trade':
                    self.add_trade(data)
                elif msg_type == 'update_stats':
                    self.update_stats()
                    
        except queue.Empty:
            pass
            
        self.root.after(100, self.check_queue)
        
    def on_closing(self):
        """Manejar cierre de ventana"""
        if self.bot.is_running:
            if messagebox.askyesno("Confirmar", "El bot está activo. ¿Desea detenerlo y salir?"):
                self.bot.stop()
                self.root.destroy()
        else:
            self.root.destroy()

# ==========================================
# FUNCIÓN PRINCIPAL
# ==========================================

def main():
    """Función principal para ejecutar el bot"""
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║     BOT DE TRADING ALGORÍTMICO - BINANCE FUTURES        ║
    ║     Versión 2.0.0 - Multi-Estrategia Profesional        ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    # Advertencia de seguridad
    print("*** ADVERTENCIA: Este bot opera con dinero real.")
    print("*** Use bajo su propio riesgo. Comience con cantidades pequeñas.")
    print("*** Se recomienda probar primero en TESTNET.\n")
    
    # Crear ventana principal
    root = tk.Tk()
    app = TradingBotGUI(root)
    
    # Configurar cierre
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    # Ejecutar aplicación
    root.mainloop()

if __name__ == "__main__":
    main()