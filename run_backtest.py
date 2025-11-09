#!/usr/bin/env python3
"""
Run Backtest
Script para ejecutar backtests de estrategias de trading

Usage:
    python run_backtest.py --symbol BTCUSDT --days 30 --strategy ma_cross
"""

import sys
import argparse
import logging
from datetime import datetime, timedelta
from binance.client import Client

from utils.backtester import BacktestEngine
from utils.regime_filter import RegimeFilter
from config_loader import load_config


def simple_ma_strategy(df, current_price, fast=20, slow=50):
    """Estrategia de cruce de medias móviles"""

    df['ma_fast'] = df['close'].rolling(fast).mean()
    df['ma_slow'] = df['close'].rolling(slow).mean()

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Cruce alcista
    if prev['ma_fast'] <= prev['ma_slow'] and last['ma_fast'] > last['ma_slow']:
        return {'signal': 1, 'confidence': 70}

    # Cruce bajista
    elif prev['ma_fast'] >= prev['ma_slow'] and last['ma_fast'] < last['ma_slow']:
        return {'signal': -1, 'confidence': 70}

    return {'signal': 0, 'confidence': 0}


def rsi_strategy(df, current_price, period=14, oversold=30, overbought=70):
    """Estrategia RSI simple"""

    # Calcular RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    last_rsi = df['rsi'].iloc[-1]

    # Sobrevendido
    if last_rsi < oversold:
        return {'signal': 1, 'confidence': 65}

    # Sobrecomprado
    elif last_rsi > overbought:
        return {'signal': -1, 'confidence': 65}

    return {'signal': 0, 'confidence': 0}


def bollinger_strategy(df, current_price, period=20, std_dev=2):
    """Estrategia de Bollinger Bands"""

    df['bb_middle'] = df['close'].rolling(period).mean()
    df['bb_std'] = df['close'].rolling(period).std()
    df['bb_upper'] = df['bb_middle'] + (df['bb_std'] * std_dev)
    df['bb_lower'] = df['bb_middle'] - (df['bb_std'] * std_dev)

    last_close = df['close'].iloc[-1]
    last_upper = df['bb_upper'].iloc[-1]
    last_lower = df['bb_lower'].iloc[-1]

    # Precio toca banda inferior (sobreventa)
    if last_close <= last_lower:
        return {'signal': 1, 'confidence': 60}

    # Precio toca banda superior (sobrecompra)
    elif last_close >= last_upper:
        return {'signal': -1, 'confidence': 60}

    return {'signal': 0, 'confidence': 0}


STRATEGIES = {
    'ma_cross': lambda df, p: simple_ma_strategy(df, p, 20, 50),
    'ma_cross_fast': lambda df, p: simple_ma_strategy(df, p, 10, 30),
    'ma_cross_slow': lambda df, p: simple_ma_strategy(df, p, 50, 100),
    'rsi': rsi_strategy,
    'bollinger': bollinger_strategy
}


def main():
    parser = argparse.ArgumentParser(description='Backtest Trading Strategies')

    parser.add_argument(
        '--symbol',
        type=str,
        default='BTCUSDT',
        help='Trading pair (default: BTCUSDT)'
    )

    parser.add_argument(
        '--timeframe',
        type=str,
        default='5m',
        choices=['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h'],
        help='Timeframe (default: 5m)'
    )

    parser.add_argument(
        '--days',
        type=int,
        default=30,
        help='Number of days to backtest (default: 30)'
    )

    parser.add_argument(
        '--strategy',
        type=str,
        default='ma_cross',
        choices=list(STRATEGIES.keys()),
        help=f'Strategy to backtest (default: ma_cross)'
    )

    parser.add_argument(
        '--capital',
        type=float,
        default=10000.0,
        help='Initial capital (default: 10000)'
    )

    parser.add_argument(
        '--compare-all',
        action='store_true',
        help='Compare all strategies'
    )

    parser.add_argument(
        '--walk-forward',
        action='store_true',
        help='Run walk-forward analysis'
    )

    parser.add_argument(
        '--use-regime-filter',
        action='store_true',
        help='Use regime filter'
    )

    parser.add_argument(
        '--export',
        type=str,
        help='Export results to file (.json or .csv)'
    )

    parser.add_argument(
        '--from-csv',
        type=str,
        help='Load data from CSV file instead of Binance'
    )

    args = parser.parse_args()

    # Configurar logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    logger = logging.getLogger(__name__)

    print("=" * 70)
    print("BACKTESTING SYSTEM")
    print("=" * 70)
    print(f"\nSymbol: {args.symbol}")
    print(f"Timeframe: {args.timeframe}")
    print(f"Period: Last {args.days} days")
    print(f"Initial Capital: ${args.capital:,.2f}")
    print(f"Strategy: {args.strategy}")
    print(f"Regime Filter: {'ON' if args.use_regime_filter else 'OFF'}")
    print()

    # Crear engine
    engine = BacktestEngine(
        initial_capital=args.capital,
        maker_fee=0.0002,
        taker_fee=0.0004,
        slippage_pct=0.0001,
        use_regime_filter=args.use_regime_filter
    )

    # Cargar datos
    if args.from_csv:
        logger.info(f"Loading data from CSV: {args.from_csv}")
        df = engine.load_data_from_csv(args.from_csv)

    else:
        # Cargar desde Binance
        config = load_config()

        client = Client(
            config.api_key,
            config.api_secret,
            testnet=config.use_testnet
        )

        start_date = datetime.now() - timedelta(days=args.days)
        end_date = datetime.now()

        logger.info("Loading data from Binance...")

        df = engine.load_data_from_binance(
            symbol=args.symbol,
            timeframe=args.timeframe,
            start_date=start_date,
            end_date=end_date,
            client=client
        )

    logger.info(f"Loaded {len(df)} candles")

    # Regime filter
    regime_filter = None
    if args.use_regime_filter:
        logger.info("Initializing regime filter...")
        regime_filter = RegimeFilter()

    # Comparar todas las estrategias
    if args.compare_all:
        logger.info("Comparing all strategies...")

        results = engine.compare_strategies(
            df=df,
            strategies=STRATEGIES,
            symbol=args.symbol,
            timeframe=args.timeframe,
            regime_filter=regime_filter
        )

        # Mostrar ganador
        best = max(results.items(), key=lambda x: x[1].total_pnl_usdt)
        print(f"\n🏆 WINNER: {best[0]}")
        print(f"   PnL: ${best[1].total_pnl_usdt:.2f} ({best[1].total_pnl_pct:+.2f}%)")
        print(f"   Sharpe: {best[1].sharpe_ratio:.2f}")

        # Exportar ganador si se especifica
        if args.export:
            logger.info(f"Exporting best strategy to {args.export}")
            engine.export_results(best[1], args.export)

        return

    # Estrategia individual
    strategy_fn = STRATEGIES[args.strategy]

    # Walk-forward analysis
    if args.walk_forward:
        logger.info("Running walk-forward analysis...")

        results = engine.walk_forward_analysis(
            df=df,
            strategy_analyzer=strategy_fn,
            symbol=args.symbol,
            timeframe=args.timeframe,
            strategy_name=args.strategy,
            n_folds=5
        )

        # Promedio de resultados
        avg_pnl = sum(r.total_pnl_pct for r in results) / len(results)
        print(f"\n📊 Average PnL across folds: {avg_pnl:+.2f}%")

        return

    # Backtest simple
    logger.info(f"Running backtest: {args.strategy}")

    result = engine.run_backtest(
        df=df,
        strategy_analyzer=strategy_fn,
        symbol=args.symbol,
        timeframe=args.timeframe,
        strategy_name=args.strategy,
        regime_filter=regime_filter
    )

    # Mostrar resultados
    result.print_summary()

    # Exportar si se especifica
    if args.export:
        logger.info(f"Exporting results to {args.export}")
        engine.export_results(result, args.export)
        print(f"\n✅ Results exported to {args.export}")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
