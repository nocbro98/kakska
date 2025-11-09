#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
State Store
Persistencia ligera en SQLite con tablas para snapshots de posición,
registro de órdenes y metadatos de sesión

Características:
- Migraciones automáticas mínimas
- Integridad referencial
- Métodos atómicos para upsert
- Thread-safe con conexiones por thread
"""

import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any


class StateStore:
    """
    Almacén de estado persistente con SQLite

    Thread-safe: usa conexiones separadas por thread
    """

    def __init__(self, db_path: str = "data/state/trading_state.db"):
        """
        Args:
            db_path: Ruta a la base de datos SQLite
        """
        self.db_path = db_path
        self.logger = logging.getLogger("StateStore")

        # Thread-local storage para conexiones
        self._local = threading.local()

        # Asegurar que existe el directorio
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # Inicializar esquema
        self._initialize_schema()

        self.logger.info(f"StateStore initialized: {db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """Obtiene una conexión thread-local"""
        if not hasattr(self._local, 'conn'):
            self._local.conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=10.0
            )
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    @contextmanager
    def _transaction(self):
        """Context manager para transacciones"""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            self.logger.error(f"Transaction rollback: {e}")
            raise

    def _initialize_schema(self):
        """Crea las tablas si no existen"""
        with self._transaction() as conn:
            cursor = conn.cursor()

            # Tabla de sesiones
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    risk_profile TEXT,
                    initial_balance REAL,
                    final_balance REAL,
                    metadata TEXT
                )
            """)

            # Tabla de órdenes
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    client_order_id TEXT PRIMARY KEY,
                    order_id TEXT,
                    symbol TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    price REAL,
                    stop_price REAL,
                    status TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    ts_create TEXT NOT NULL,
                    ts_sent TEXT,
                    ts_ack TEXT,
                    ts_filled TEXT,
                    filled_qty REAL DEFAULT 0,
                    avg_fill_price REAL,
                    commission REAL DEFAULT 0,
                    entry_reason TEXT,
                    planned_sl REAL,
                    planned_tp REAL,
                    planned_rr REAL,
                    metadata TEXT,
                    UNIQUE(client_order_id)
                )
            """)

            # Índices para órdenes
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_symbol
                ON orders(symbol)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_status
                ON orders(status)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_strategy
                ON orders(strategy)
            """)

            # Tabla de posiciones
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    symbol TEXT PRIMARY KEY,
                    side TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    leverage INTEGER NOT NULL,
                    stop_loss REAL,
                    take_profit_1 REAL,
                    take_profit_2 REAL,
                    take_profit_3 REAL,
                    trailing_stop REAL,
                    ts_open TEXT NOT NULL,
                    entry_order_id TEXT,
                    strategy TEXT,
                    unrealized_pnl REAL DEFAULT 0,
                    realized_pnl REAL DEFAULT 0,
                    mae REAL DEFAULT 0,
                    mfe REAL DEFAULT 0,
                    commission_paid REAL DEFAULT 0,
                    funding_paid REAL DEFAULT 0
                )
            """)

            # Tabla de trades (journal estructurado)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    trade_id TEXT PRIMARY KEY,
                    ts_open TEXT NOT NULL,
                    ts_close TEXT,
                    symbol TEXT NOT NULL,
                    profile TEXT,
                    strategy_primary TEXT,
                    strategies_confluence TEXT,
                    regime_trend TEXT,
                    regime_volatility TEXT,
                    entry_type TEXT,
                    plan_rr REAL,
                    r_achieved REAL,
                    size_nominal REAL,
                    fees REAL DEFAULT 0,
                    funding REAL DEFAULT 0,
                    slippage_real REAL DEFAULT 0,
                    mae REAL DEFAULT 0,
                    mfe REAL DEFAULT 0,
                    reason_exit TEXT,
                    notes TEXT,
                    side TEXT,
                    entry_price REAL,
                    exit_price REAL,
                    quantity REAL
                )
            """)

            # Índices para trades
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_ts_open
                ON trades(ts_open)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_symbol
                ON trades(symbol)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_strategy
                ON trades(strategy_primary)
            """)

            # Tabla de métricas de estrategias (para IC weighting)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS strategy_metrics (
                    strategy TEXT NOT NULL,
                    date TEXT NOT NULL,
                    signal REAL,
                    forward_return REAL,
                    ic_score REAL,
                    weight REAL,
                    PRIMARY KEY (strategy, date)
                )
            """)

            # Tabla de régimen de mercado (memoria corta)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS regime_history (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    trend_type TEXT,
                    trend_strength REAL,
                    volatility_percentile REAL,
                    volatility_type TEXT,
                    is_squeeze INTEGER,
                    PRIMARY KEY (symbol, timeframe, timestamp)
                )
            """)

            # Tabla de datos históricos mínimos (para estrategias)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS historical_data_status (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    bars_available INTEGER DEFAULT 0,
                    bars_required INTEGER DEFAULT 0,
                    last_update TEXT,
                    PRIMARY KEY (symbol, timeframe, strategy)
                )
            """)

            self.logger.info("Database schema initialized")

    # =====================================================================
    # ORDERS
    # =====================================================================

    def save_order(self, order_dict: Dict[str, Any]) -> bool:
        """
        Guarda o actualiza una orden (upsert atómico)

        Args:
            order_dict: Diccionario con datos de la orden

        Returns:
            True si se guardó correctamente
        """
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT OR REPLACE INTO orders (
                        client_order_id, order_id, symbol, strategy, side, order_type,
                        quantity, price, stop_price, status, sequence,
                        ts_create, ts_sent, ts_ack, ts_filled,
                        filled_qty, avg_fill_price, commission,
                        entry_reason, planned_sl, planned_tp, planned_rr,
                        metadata
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                """, (
                    order_dict.get('client_order_id'),
                    order_dict.get('order_id'),
                    order_dict.get('symbol'),
                    order_dict.get('strategy'),
                    order_dict.get('side'),
                    order_dict.get('order_type'),
                    order_dict.get('quantity'),
                    order_dict.get('price'),
                    order_dict.get('stop_price'),
                    order_dict.get('status'),
                    order_dict.get('sequence', 0),
                    order_dict.get('ts_create'),
                    order_dict.get('ts_sent'),
                    order_dict.get('ts_ack'),
                    order_dict.get('ts_filled'),
                    order_dict.get('filled_qty', 0),
                    order_dict.get('avg_fill_price'),
                    order_dict.get('commission', 0),
                    order_dict.get('entry_reason'),
                    order_dict.get('planned_sl'),
                    order_dict.get('planned_tp'),
                    order_dict.get('planned_rr'),
                    str(order_dict.get('metadata', {}))
                ))

            return True

        except Exception as e:
            self.logger.error(f"Error saving order: {e}", exc_info=True)
            return False

    def get_order(self, client_order_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene una orden por su client_order_id"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM orders WHERE client_order_id = ?
        """, (client_order_id,))

        row = cursor.fetchone()
        return dict(row) if row else None

    def get_orders_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Obtiene todas las órdenes con un estado específico"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM orders WHERE status = ?
        """, (status,))

        return [dict(row) for row in cursor.fetchall()]

    def get_all_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Obtiene todas las órdenes, opcionalmente filtradas por símbolo"""
        conn = self._get_connection()
        cursor = conn.cursor()

        if symbol:
            cursor.execute("""
                SELECT * FROM orders WHERE symbol = ? ORDER BY ts_create DESC
            """, (symbol,))
        else:
            cursor.execute("""
                SELECT * FROM orders ORDER BY ts_create DESC
            """)

        return [dict(row) for row in cursor.fetchall()]

    # =====================================================================
    # POSITIONS
    # =====================================================================

    def save_position(self, position_dict: Dict[str, Any]) -> bool:
        """Guarda o actualiza una posición (upsert atómico)"""
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT OR REPLACE INTO positions (
                        symbol, side, entry_price, quantity, leverage,
                        stop_loss, take_profit_1, take_profit_2, take_profit_3, trailing_stop,
                        ts_open, entry_order_id, strategy,
                        unrealized_pnl, realized_pnl, mae, mfe,
                        commission_paid, funding_paid
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    position_dict.get('symbol'),
                    position_dict.get('side'),
                    position_dict.get('entry_price'),
                    position_dict.get('quantity'),
                    position_dict.get('leverage'),
                    position_dict.get('stop_loss'),
                    position_dict.get('take_profit_1'),
                    position_dict.get('take_profit_2'),
                    position_dict.get('take_profit_3'),
                    position_dict.get('trailing_stop'),
                    position_dict.get('ts_open'),
                    position_dict.get('entry_order_id'),
                    position_dict.get('strategy'),
                    position_dict.get('unrealized_pnl', 0),
                    position_dict.get('realized_pnl', 0),
                    position_dict.get('mae', 0),
                    position_dict.get('mfe', 0),
                    position_dict.get('commission_paid', 0),
                    position_dict.get('funding_paid', 0)
                ))

            return True

        except Exception as e:
            self.logger.error(f"Error saving position: {e}", exc_info=True)
            return False

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Obtiene una posición por símbolo"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM positions WHERE symbol = ?
        """, (symbol,))

        row = cursor.fetchone()
        return dict(row) if row else None

    def get_all_positions(self) -> List[Dict[str, Any]]:
        """Obtiene todas las posiciones abiertas"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM positions
        """)

        return [dict(row) for row in cursor.fetchall()]

    def delete_position(self, symbol: str) -> bool:
        """Elimina una posición"""
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))
            return True
        except Exception as e:
            self.logger.error(f"Error deleting position: {e}")
            return False

    # =====================================================================
    # TRADES
    # =====================================================================

    def save_trade(self, trade_dict: Dict[str, Any]) -> bool:
        """Guarda un trade completo en el journal"""
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT OR REPLACE INTO trades (
                        trade_id, ts_open, ts_close, symbol, profile,
                        strategy_primary, strategies_confluence,
                        regime_trend, regime_volatility, entry_type,
                        plan_rr, r_achieved, size_nominal,
                        fees, funding, slippage_real, mae, mfe,
                        reason_exit, notes, side, entry_price, exit_price, quantity
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    trade_dict.get('trade_id'),
                    trade_dict.get('ts_open'),
                    trade_dict.get('ts_close'),
                    trade_dict.get('symbol'),
                    trade_dict.get('profile'),
                    trade_dict.get('strategy_primary'),
                    trade_dict.get('strategies_confluence'),
                    trade_dict.get('regime_trend'),
                    trade_dict.get('regime_volatility'),
                    trade_dict.get('entry_type'),
                    trade_dict.get('plan_rr'),
                    trade_dict.get('r_achieved'),
                    trade_dict.get('size_nominal'),
                    trade_dict.get('fees', 0),
                    trade_dict.get('funding', 0),
                    trade_dict.get('slippage_real', 0),
                    trade_dict.get('mae', 0),
                    trade_dict.get('mfe', 0),
                    trade_dict.get('reason_exit'),
                    trade_dict.get('notes'),
                    trade_dict.get('side'),
                    trade_dict.get('entry_price'),
                    trade_dict.get('exit_price'),
                    trade_dict.get('quantity')
                ))

            return True

        except Exception as e:
            self.logger.error(f"Error saving trade: {e}", exc_info=True)
            return False

    def get_trades(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        symbol: Optional[str] = None,
        strategy: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Obtiene trades filtrados

        Args:
            start_date: Fecha inicio
            end_date: Fecha fin
            symbol: Símbolo
            strategy: Estrategia

        Returns:
            Lista de trades
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM trades WHERE 1=1"
        params = []

        if start_date:
            query += " AND ts_open >= ?"
            params.append(start_date.isoformat())

        if end_date:
            query += " AND ts_open <= ?"
            params.append(end_date.isoformat())

        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)

        if strategy:
            query += " AND strategy_primary = ?"
            params.append(strategy)

        query += " ORDER BY ts_open DESC"

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    # =====================================================================
    # REGIME
    # =====================================================================

    def save_regime(self, symbol: str, timeframe: str, regime_dict: Dict[str, Any]) -> bool:
        """Guarda snapshot de régimen"""
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT OR REPLACE INTO regime_history (
                        symbol, timeframe, timestamp,
                        trend_type, trend_strength, volatility_percentile,
                        volatility_type, is_squeeze
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    symbol,
                    timeframe,
                    regime_dict.get('timestamp', datetime.now().isoformat()),
                    regime_dict.get('trend_type'),
                    regime_dict.get('trend_strength'),
                    regime_dict.get('volatility_percentile'),
                    regime_dict.get('volatility_type'),
                    1 if regime_dict.get('is_squeeze') else 0
                ))

            return True

        except Exception as e:
            self.logger.error(f"Error saving regime: {e}")
            return False

    def get_latest_regime(self, symbol: str, timeframe: str) -> Optional[Dict[str, Any]]:
        """Obtiene el último régimen guardado"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM regime_history
            WHERE symbol = ? AND timeframe = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (symbol, timeframe))

        row = cursor.fetchone()
        return dict(row) if row else None

    # =====================================================================
    # HISTORICAL DATA STATUS
    # =====================================================================

    def update_data_status(
        self,
        symbol: str,
        timeframe: str,
        strategy: str,
        bars_available: int,
        bars_required: int
    ) -> bool:
        """Actualiza el estado de datos históricos disponibles"""
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT OR REPLACE INTO historical_data_status (
                        symbol, timeframe, strategy, bars_available, bars_required, last_update
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    symbol, timeframe, strategy, bars_available, bars_required,
                    datetime.now().isoformat()
                ))

            return True

        except Exception as e:
            self.logger.error(f"Error updating data status: {e}")
            return False

    def get_data_status(self, symbol: str, timeframe: str, strategy: str) -> Optional[Dict[str, Any]]:
        """Obtiene el estado de datos históricos"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM historical_data_status
            WHERE symbol = ? AND timeframe = ? AND strategy = ?
        """, (symbol, timeframe, strategy))

        row = cursor.fetchone()
        return dict(row) if row else None

    # =====================================================================
    # STRATEGY METRICS (IC Weighting)
    # =====================================================================

    def save_strategy_metric(self, strategy: str, date: str, metric_dict: Dict[str, Any]) -> bool:
        """Guarda métrica de estrategia para IC weighting"""
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT OR REPLACE INTO strategy_metrics (
                        strategy, date, signal, forward_return, ic_score, weight
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    strategy,
                    date,
                    metric_dict.get('signal'),
                    metric_dict.get('forward_return'),
                    metric_dict.get('ic_score'),
                    metric_dict.get('weight')
                ))

            return True

        except Exception as e:
            self.logger.error(f"Error saving strategy metric: {e}")
            return False

    def get_strategy_metrics(
        self,
        strategy: str,
        days_back: int = 30
    ) -> List[Dict[str, Any]]:
        """Obtiene métricas de una estrategia"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')

        cursor.execute("""
            SELECT * FROM strategy_metrics
            WHERE strategy = ? AND date >= ?
            ORDER BY date DESC
        """, (strategy, cutoff_date))

        return [dict(row) for row in cursor.fetchall()]

    # =====================================================================
    # CLEANUP
    # =====================================================================

    def cleanup_old_data(self, days_to_keep: int = 90):
        """Limpia datos antiguos para mantener la BD pequeña"""
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).isoformat()

                # Limpiar regime_history
                cursor.execute("""
                    DELETE FROM regime_history WHERE timestamp < ?
                """, (cutoff_date,))

                deleted_regime = cursor.rowcount

                # Limpiar strategy_metrics
                cutoff_date_str = (datetime.now() - timedelta(days=days_to_keep)).strftime('%Y-%m-%d')
                cursor.execute("""
                    DELETE FROM strategy_metrics WHERE date < ?
                """, (cutoff_date_str,))

                deleted_metrics = cursor.rowcount

                self.logger.info(
                    f"Cleanup: deleted {deleted_regime} regime records, "
                    f"{deleted_metrics} strategy metrics"
                )

            return True

        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
            return False

    def close(self):
        """Cierra conexiones"""
        if hasattr(self._local, 'conn'):
            self._local.conn.close()
            delattr(self._local, 'conn')
        self.logger.info("StateStore closed")
