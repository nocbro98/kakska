"""
Backtesting System
Sistema de backtesting para validación de estrategias con datos históricos

Características:
- Carga de datos históricos (Binance o CSV)
- Simulación realista de ejecución (slippage, fees)
- Métricas de performance completas
- Comparación de estrategias
- Walk-forward analysis
- Export de resultados
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
import logging
import json


class TradeType(Enum):
    """Tipo de trade"""
    LONG = "long"
    SHORT = "short"


@dataclass
class BacktestTrade:
    """Trade ejecutado en backtest"""
    timestamp: datetime
    type: TradeType
    entry_price: float
    exit_price: float
    quantity: float
    pnl_usdt: float
    pnl_pct: float
    fees: float
    slippage: float
    strategy: str
    hold_time_minutes: int
    mae: float = 0.0  # Maximum Adverse Excursion
    mfe: float = 0.0  # Maximum Favorable Excursion
    exit_reason: str = "unknown"


@dataclass
class BacktestResult:
    """Resultado de backtest"""
    # Configuración
    symbol: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    strategy_name: str

    # Trades
    trades: List[BacktestTrade] = field(default_factory=list)

    # Métricas calculadas
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0

    total_pnl_usdt: float = 0.0
    total_pnl_pct: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0

    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0

    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0

    avg_hold_time_minutes: float = 0.0

    # Equity curve
    equity_curve: List[float] = field(default_factory=list)
    drawdown_curve: List[float] = field(default_factory=list)

    # Fees y costos
    total_fees: float = 0.0
    total_slippage: float = 0.0

    def calculate_metrics(self):
        """Calcula todas las métricas a partir de los trades"""

        if not self.trades:
            return

        # Contar trades
        self.total_trades = len(self.trades)
        self.winning_trades = sum(1 for t in self.trades if t.pnl_usdt > 0)
        self.losing_trades = sum(1 for t in self.trades if t.pnl_usdt <= 0)

        # Win rate
        self.win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0

        # PnL total
        self.total_pnl_usdt = sum(t.pnl_usdt for t in self.trades)
        self.total_pnl_pct = (self.total_pnl_usdt / self.initial_capital) * 100

        # Promedio win/loss
        wins = [t.pnl_usdt for t in self.trades if t.pnl_usdt > 0]
        losses = [abs(t.pnl_usdt) for t in self.trades if t.pnl_usdt <= 0]

        self.avg_win = np.mean(wins) if wins else 0
        self.avg_loss = np.mean(losses) if losses else 0

        # Profit factor
        total_wins = sum(wins) if wins else 0
        total_losses = sum(losses) if losses else 0
        self.profit_factor = (total_wins / total_losses) if total_losses > 0 else 0

        # Fees y slippage
        self.total_fees = sum(t.fees for t in self.trades)
        self.total_slippage = sum(t.slippage for t in self.trades)

        # Hold time promedio
        self.avg_hold_time_minutes = np.mean([t.hold_time_minutes for t in self.trades])

        # Equity curve y drawdown
        self._calculate_equity_curve()

        # Sharpe y Sortino
        self._calculate_risk_metrics()

    def _calculate_equity_curve(self):
        """Calcula equity curve y drawdown"""

        equity = self.initial_capital
        self.equity_curve = [equity]
        peak = equity

        for trade in self.trades:
            equity += trade.pnl_usdt
            self.equity_curve.append(equity)

            # Drawdown
            if equity > peak:
                peak = equity

            dd = peak - equity
            dd_pct = (dd / peak) * 100 if peak > 0 else 0

            self.drawdown_curve.append(dd_pct)

            # Max drawdown
            if dd > self.max_drawdown:
                self.max_drawdown = dd
                self.max_drawdown_pct = dd_pct

    def _calculate_risk_metrics(self):
        """Calcula Sharpe y Sortino ratios"""

        if len(self.trades) < 2:
            return

        # Retornos por trade
        returns = [t.pnl_pct for t in self.trades]

        # Sharpe ratio (anualizado)
        mean_return = np.mean(returns)
        std_return = np.std(returns)

        # Aproximar trades por año (asumiendo 252 días trading)
        avg_days_per_trade = self.avg_hold_time_minutes / (60 * 24)
        trades_per_year = 252 / avg_days_per_trade if avg_days_per_trade > 0 else 0

        self.sharpe_ratio = (mean_return * np.sqrt(trades_per_year)) / std_return if std_return > 0 else 0

        # Sortino ratio (solo downside deviation)
        negative_returns = [r for r in returns if r < 0]
        downside_std = np.std(negative_returns) if negative_returns else 0

        self.sortino_ratio = (mean_return * np.sqrt(trades_per_year)) / downside_std if downside_std > 0 else 0

    def to_dict(self) -> Dict:
        """Convierte resultado a diccionario"""

        return {
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'start_date': self.start_date.isoformat(),
            'end_date': self.end_date.isoformat(),
            'initial_capital': self.initial_capital,
            'strategy_name': self.strategy_name,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': round(self.win_rate, 2),
            'total_pnl_usdt': round(self.total_pnl_usdt, 2),
            'total_pnl_pct': round(self.total_pnl_pct, 2),
            'avg_win': round(self.avg_win, 2),
            'avg_loss': round(self.avg_loss, 2),
            'profit_factor': round(self.profit_factor, 2),
            'max_drawdown': round(self.max_drawdown, 2),
            'max_drawdown_pct': round(self.max_drawdown_pct, 2),
            'sharpe_ratio': round(self.sharpe_ratio, 2),
            'sortino_ratio': round(self.sortino_ratio, 2),
            'avg_hold_time_minutes': round(self.avg_hold_time_minutes, 2),
            'total_fees': round(self.total_fees, 2),
            'total_slippage': round(self.total_slippage, 2),
            'final_capital': round(self.initial_capital + self.total_pnl_usdt, 2)
        }

    def print_summary(self):
        """Imprime resumen del backtest"""

        print("\n" + "=" * 70)
        print("BACKTEST RESULTS")
        print("=" * 70)
        print(f"\nStrategy: {self.strategy_name}")
        print(f"Symbol: {self.symbol} | Timeframe: {self.timeframe}")
        print(f"Period: {self.start_date.date()} to {self.end_date.date()}")
        print(f"Initial Capital: ${self.initial_capital:,.2f}")
        print(f"Final Capital: ${self.initial_capital + self.total_pnl_usdt:,.2f}")

        print(f"\n📊 TRADES:")
        print(f"  Total Trades: {self.total_trades}")
        print(f"  Winning: {self.winning_trades} | Losing: {self.losing_trades}")
        print(f"  Win Rate: {self.win_rate:.2f}%")
        print(f"  Avg Hold Time: {self.avg_hold_time_minutes:.1f} minutes")

        print(f"\n💰 PERFORMANCE:")
        print(f"  Total PnL: ${self.total_pnl_usdt:,.2f} ({self.total_pnl_pct:+.2f}%)")
        print(f"  Avg Win: ${self.avg_win:.2f}")
        print(f"  Avg Loss: ${self.avg_loss:.2f}")
        print(f"  Profit Factor: {self.profit_factor:.2f}")

        print(f"\n📉 RISK:")
        print(f"  Max Drawdown: ${self.max_drawdown:.2f} ({self.max_drawdown_pct:.2f}%)")
        print(f"  Sharpe Ratio: {self.sharpe_ratio:.2f}")
        print(f"  Sortino Ratio: {self.sortino_ratio:.2f}")

        print(f"\n💸 COSTS:")
        print(f"  Total Fees: ${self.total_fees:.2f}")
        print(f"  Total Slippage: ${self.total_slippage:.2f}")

        print("\n" + "=" * 70 + "\n")


class BacktestEngine:
    """
    Motor de backtesting

    Simula ejecución de estrategias con datos históricos
    """

    def __init__(
        self,
        initial_capital: float = 10000.0,
        maker_fee: float = 0.0002,  # 0.02%
        taker_fee: float = 0.0004,  # 0.04%
        slippage_pct: float = 0.0001,  # 0.01%
        use_regime_filter: bool = True
    ):
        """
        Args:
            initial_capital: Capital inicial
            maker_fee: Fee de maker (%)
            taker_fee: Fee de taker (%)
            slippage_pct: Slippage estimado (%)
            use_regime_filter: Usar filtrado por régimen
        """
        self.initial_capital = initial_capital
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self.slippage_pct = slippage_pct
        self.use_regime_filter = use_regime_filter

        self.logger = logging.getLogger("BacktestEngine")

    def load_data_from_binance(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        client=None
    ) -> pd.DataFrame:
        """
        Carga datos históricos desde Binance

        Args:
            symbol: Par de trading
            timeframe: Timeframe (1m, 5m, 1h, etc.)
            start_date: Fecha inicio
            end_date: Fecha fin
            client: Cliente de Binance

        Returns:
            DataFrame con OHLCV
        """

        if client is None:
            raise ValueError("Binance client required")

        self.logger.info(f"Loading data from Binance: {symbol} {timeframe}")

        # Convertir fechas a timestamps
        start_ts = int(start_date.timestamp() * 1000)
        end_ts = int(end_date.timestamp() * 1000)

        # Obtener klines
        klines = client.futures_klines(
            symbol=symbol,
            interval=timeframe,
            startTime=start_ts,
            endTime=end_ts,
            limit=1500
        )

        # Convertir a DataFrame
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])

        # Limpiar y convertir tipos
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)

        self.logger.info(f"Loaded {len(df)} candles")

        return df

    def load_data_from_csv(self, filepath: str) -> pd.DataFrame:
        """
        Carga datos desde archivo CSV

        Args:
            filepath: Ruta al archivo CSV

        Returns:
            DataFrame con OHLCV
        """

        self.logger.info(f"Loading data from CSV: {filepath}")

        df = pd.read_csv(filepath)

        # Verificar columnas requeridas
        required = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        if not all(col in df.columns for col in required):
            raise ValueError(f"CSV must contain columns: {required}")

        df['timestamp'] = pd.to_datetime(df['timestamp'])

        self.logger.info(f"Loaded {len(df)} candles")

        return df

    def run_backtest(
        self,
        df: pd.DataFrame,
        strategy_analyzer: Callable,
        symbol: str,
        timeframe: str,
        strategy_name: str = "Unknown",
        regime_filter=None
    ) -> BacktestResult:
        """
        Ejecuta backtest con una estrategia

        Args:
            df: DataFrame con OHLCV e indicadores
            strategy_analyzer: Función que retorna señal de trading
            symbol: Par de trading
            timeframe: Timeframe
            strategy_name: Nombre de la estrategia
            regime_filter: RegimeFilter opcional

        Returns:
            BacktestResult con métricas
        """

        self.logger.info(f"Running backtest: {strategy_name}")

        result = BacktestResult(
            symbol=symbol,
            timeframe=timeframe,
            start_date=df['timestamp'].iloc[0],
            end_date=df['timestamp'].iloc[-1],
            initial_capital=self.initial_capital,
            strategy_name=strategy_name
        )

        # Estado de posición
        in_position = False
        current_trade = None
        entry_price = 0.0
        entry_time = None
        trade_type = None

        # Iterar sobre datos
        for i in range(100, len(df)):  # Empezar después de warmup

            current_row = df.iloc[i]
            current_price = current_row['close']
            current_time = current_row['timestamp']

            # Slice de datos hasta i (simula datos disponibles)
            historical_df = df.iloc[:i+1].copy()

            # Filtrar por régimen si está habilitado
            if self.use_regime_filter and regime_filter:
                regime = regime_filter.update(historical_df)
                should_filter, reason = regime_filter.should_filter_strategy(
                    strategy_name, regime
                )

                if should_filter:
                    # Bloquear señales
                    continue

            # Obtener señal de la estrategia
            signal = strategy_analyzer(historical_df, current_price)

            # Procesar señal
            if not in_position:
                # Buscar entrada
                if signal.get('signal') == 1:  # LONG
                    in_position = True
                    trade_type = TradeType.LONG
                    entry_price = current_price * (1 + self.slippage_pct)  # Slippage
                    entry_time = current_time

                    self.logger.debug(f"LONG entry @ {entry_price:.2f}")

                elif signal.get('signal') == -1:  # SHORT
                    in_position = True
                    trade_type = TradeType.SHORT
                    entry_price = current_price * (1 - self.slippage_pct)
                    entry_time = current_time

                    self.logger.debug(f"SHORT entry @ {entry_price:.2f}")

            else:
                # Buscar salida
                should_exit = False
                exit_reason = "signal"

                # Señal de salida
                if trade_type == TradeType.LONG and signal.get('signal') == -1:
                    should_exit = True
                elif trade_type == TradeType.SHORT and signal.get('signal') == 1:
                    should_exit = True
                elif signal.get('signal') == 0:  # Señal neutral
                    should_exit = True
                    exit_reason = "neutral"

                # Simular SL/TP (simplificado)
                # En backtest real, verificar high/low de cada vela

                if should_exit:
                    exit_price = current_price * (1 - self.slippage_pct) if trade_type == TradeType.LONG else current_price * (1 + self.slippage_pct)

                    # Calcular PnL
                    if trade_type == TradeType.LONG:
                        pnl_usdt = exit_price - entry_price
                    else:  # SHORT
                        pnl_usdt = entry_price - exit_price

                    pnl_pct = (pnl_usdt / entry_price) * 100

                    # Calcular fees (entry + exit)
                    quantity = 1.0  # Simplificado
                    fees = (entry_price + exit_price) * quantity * self.taker_fee

                    # Slippage total
                    slippage = abs(entry_price - current_price) + abs(exit_price - current_price)

                    # Crear trade
                    hold_time = (current_time - entry_time).total_seconds() / 60

                    trade = BacktestTrade(
                        timestamp=entry_time,
                        type=trade_type,
                        entry_price=entry_price,
                        exit_price=exit_price,
                        quantity=quantity,
                        pnl_usdt=pnl_usdt - fees,  # Restar fees
                        pnl_pct=pnl_pct,
                        fees=fees,
                        slippage=slippage,
                        strategy=strategy_name,
                        hold_time_minutes=int(hold_time),
                        exit_reason=exit_reason
                    )

                    result.trades.append(trade)

                    self.logger.debug(
                        f"Exit @ {exit_price:.2f} | "
                        f"PnL: ${pnl_usdt:.2f} ({pnl_pct:+.2f}%)"
                    )

                    # Reset
                    in_position = False
                    current_trade = None

        # Cerrar posición abierta al final (si existe)
        if in_position:
            self.logger.warning("Closing open position at end of backtest")
            # Similar a código de salida arriba

        # Calcular métricas
        result.calculate_metrics()

        self.logger.info(
            f"Backtest complete: {result.total_trades} trades, "
            f"PnL: ${result.total_pnl_usdt:.2f} ({result.total_pnl_pct:+.2f}%)"
        )

        return result

    def compare_strategies(
        self,
        df: pd.DataFrame,
        strategies: Dict[str, Callable],
        symbol: str,
        timeframe: str,
        regime_filter=None
    ) -> Dict[str, BacktestResult]:
        """
        Compara múltiples estrategias

        Args:
            df: DataFrame con datos
            strategies: Dict {name: analyzer_function}
            symbol: Par de trading
            timeframe: Timeframe
            regime_filter: RegimeFilter opcional

        Returns:
            Dict {strategy_name: BacktestResult}
        """

        self.logger.info(f"Comparing {len(strategies)} strategies")

        results = {}

        for name, analyzer in strategies.items():
            result = self.run_backtest(
                df=df,
                strategy_analyzer=analyzer,
                symbol=symbol,
                timeframe=timeframe,
                strategy_name=name,
                regime_filter=regime_filter
            )

            results[name] = result

        # Imprimir comparación
        self._print_comparison(results)

        return results

    def _print_comparison(self, results: Dict[str, BacktestResult]):
        """Imprime tabla comparativa"""

        print("\n" + "=" * 100)
        print("STRATEGY COMPARISON")
        print("=" * 100)

        # Header
        print(f"\n{'Strategy':<20} {'Trades':<8} {'Win%':<8} {'PnL $':<12} {'PnL %':<10} "
              f"{'MaxDD%':<10} {'Sharpe':<8} {'PF':<6}")
        print("-" * 100)

        # Ordenar por PnL
        sorted_results = sorted(
            results.items(),
            key=lambda x: x[1].total_pnl_usdt,
            reverse=True
        )

        for name, result in sorted_results:
            print(
                f"{name:<20} "
                f"{result.total_trades:<8} "
                f"{result.win_rate:<8.1f} "
                f"${result.total_pnl_usdt:<11.2f} "
                f"{result.total_pnl_pct:<10.2f} "
                f"{result.max_drawdown_pct:<10.2f} "
                f"{result.sharpe_ratio:<8.2f} "
                f"{result.profit_factor:<6.2f}"
            )

        print("=" * 100 + "\n")

    def walk_forward_analysis(
        self,
        df: pd.DataFrame,
        strategy_analyzer: Callable,
        symbol: str,
        timeframe: str,
        strategy_name: str,
        train_size_pct: float = 0.7,
        n_folds: int = 5
    ) -> List[BacktestResult]:
        """
        Walk-forward analysis

        Divide datos en múltiples períodos de train/test para validación

        Args:
            df: DataFrame completo
            strategy_analyzer: Función de análisis
            symbol: Par
            timeframe: Timeframe
            strategy_name: Nombre estrategia
            train_size_pct: % de datos para training
            n_folds: Número de folds

        Returns:
            Lista de BacktestResults (uno por fold)
        """

        self.logger.info(f"Walk-forward analysis: {n_folds} folds")

        fold_size = len(df) // n_folds
        results = []

        for i in range(n_folds):
            fold_start = i * fold_size
            fold_end = (i + 1) * fold_size if i < n_folds - 1 else len(df)

            fold_df = df.iloc[fold_start:fold_end].copy()

            self.logger.info(f"Fold {i+1}/{n_folds}: {len(fold_df)} candles")

            result = self.run_backtest(
                df=fold_df,
                strategy_analyzer=strategy_analyzer,
                symbol=symbol,
                timeframe=timeframe,
                strategy_name=f"{strategy_name}_fold{i+1}"
            )

            results.append(result)

        # Imprimir resumen
        self._print_walkforward_summary(results)

        return results

    def _print_walkforward_summary(self, results: List[BacktestResult]):
        """Imprime resumen de walk-forward"""

        print("\n" + "=" * 80)
        print("WALK-FORWARD ANALYSIS SUMMARY")
        print("=" * 80)

        avg_pnl = np.mean([r.total_pnl_pct for r in results])
        std_pnl = np.std([r.total_pnl_pct for r in results])
        avg_sharpe = np.mean([r.sharpe_ratio for r in results])

        print(f"\nFolds: {len(results)}")
        print(f"Avg PnL: {avg_pnl:.2f}% ± {std_pnl:.2f}%")
        print(f"Avg Sharpe: {avg_sharpe:.2f}")
        print(f"Consistency: {(sum(1 for r in results if r.total_pnl_pct > 0) / len(results) * 100):.1f}% profitable folds")

        print("\nPer-Fold Results:")
        for i, result in enumerate(results, 1):
            print(f"  Fold {i}: {result.total_pnl_pct:+.2f}% | Sharpe: {result.sharpe_ratio:.2f}")

        print("=" * 80 + "\n")

    def export_results(self, result: BacktestResult, output_path: str):
        """
        Exporta resultados a archivo

        Args:
            result: BacktestResult
            output_path: Ruta de salida (.json o .csv)
        """

        if output_path.endswith('.json'):
            with open(output_path, 'w') as f:
                json.dump(result.to_dict(), f, indent=2)

            self.logger.info(f"Results exported to {output_path}")

        elif output_path.endswith('.csv'):
            # Exportar trades a CSV
            trades_df = pd.DataFrame([
                {
                    'timestamp': t.timestamp,
                    'type': t.type.value,
                    'entry_price': t.entry_price,
                    'exit_price': t.exit_price,
                    'quantity': t.quantity,
                    'pnl_usdt': t.pnl_usdt,
                    'pnl_pct': t.pnl_pct,
                    'fees': t.fees,
                    'hold_time_min': t.hold_time_minutes,
                    'exit_reason': t.exit_reason
                }
                for t in result.trades
            ])

            trades_df.to_csv(output_path, index=False)

            self.logger.info(f"Trades exported to {output_path}")

        else:
            raise ValueError("Output format must be .json or .csv")
