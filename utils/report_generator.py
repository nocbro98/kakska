"""
Weekly Report Generator
Generador automático de reportes semanales
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import numpy as np

from core.state_store import StateStore
from core.attribution_system import AttributionSystem
from utils.alert_manager import AlertManager, AlertLevel


class WeeklyReportGenerator:
    """
    Generador de reportes semanales automáticos

    Contenido:
    - Semana calendario
    - Número de trades
    - Sharpe/Sortino deflactados
    - Profit Factor
    - MaxDD
    - Hitrate
    - Comisiones y funding
    - Top 3 estrategias
    - 3 anomalías detectadas
    - Cambios sugeridos de pesos
    """

    def __init__(
        self,
        state_store: StateStore,
        attribution_system: AttributionSystem,
        alert_manager: AlertManager,
        reports_dir: str = "data/reports"
    ):
        self.state_store = state_store
        self.attribution_system = attribution_system
        self.alert_manager = alert_manager
        self.reports_dir = reports_dir
        self.logger = logging.getLogger("WeeklyReport")

        # Crear directorio de reportes
        import os
        os.makedirs(reports_dir, exist_ok=True)

    def generate_weekly_report(self) -> str:
        """
        Genera reporte semanal completo

        Returns:
            Ruta del archivo generado
        """
        now = datetime.now()
        week_start = now - timedelta(days=7)
        week_end = now

        self.logger.info(f"Generating weekly report: {week_start.date()} to {week_end.date()}")

        # Obtener trades de la semana
        trades = self.state_store.get_trades(start_date=week_start, end_date=week_end)

        if not trades:
            self.logger.warning("No trades this week, skipping report")
            return None

        # Calcular métricas
        metrics = self._calculate_metrics(trades)

        # Obtener atribución por estrategia
        strategy_metrics = self.attribution_system.get_strategy_metrics()
        top_strategies = self._get_top_strategies(strategy_metrics, n=3)

        # Detectar anomalías
        anomalies = self._detect_anomalies(trades, metrics)

        # Sugerir cambios de pesos
        weight_suggestions = self._suggest_weight_changes(strategy_metrics)

        # Generar reporte
        report_content = self._format_report(
            week_start,
            week_end,
            trades,
            metrics,
            top_strategies,
            anomalies,
            weight_suggestions
        )

        # Guardar reporte
        report_filename = f"weekly_report_{week_start.strftime('%Y%m%d')}_{week_end.strftime('%Y%m%d')}.txt"
        report_path = f"{self.reports_dir}/{report_filename}"

        try:
            with open(report_path, 'w') as f:
                f.write(report_content)
            self.logger.info(f"Weekly report saved: {report_path}")
        except Exception as e:
            self.logger.error(f"Error saving report: {e}")
            return None

        # Enviar resumen por alerta
        summary = self._create_summary(metrics)
        self.alert_manager.alert_info(f"📊 Weekly Report Generated\n{summary}")

        return report_path

    def _calculate_metrics(self, trades: List[Dict]) -> Dict[str, Any]:
        """Calcula métricas de la semana"""
        if not trades:
            return {}

        # PnL
        total_pnl = sum(t.get('exit_price', 0) - t.get('entry_price', 0) for t in trades if t.get('exit_price'))
        returns = [(t.get('exit_price', 0) - t.get('entry_price', 0)) / t.get('entry_price', 1) * 100
                   for t in trades if t.get('exit_price') and t.get('entry_price')]

        # Win rate
        winners = [r for r in returns if r > 0]
        losers = [r for r in returns if r < 0]
        win_rate = len(winners) / len(returns) * 100 if returns else 0

        # Profit Factor
        gross_profit = sum(winners) if winners else 0
        gross_loss = abs(sum(losers)) if losers else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        # Sharpe & Sortino
        if len(returns) > 1:
            mean_return = np.mean(returns)
            std_return = np.std(returns)
            sharpe = (mean_return / std_return * np.sqrt(252)) if std_return > 0 else 0

            downside_returns = [r for r in returns if r < 0]
            if downside_returns:
                downside_std = np.std(downside_returns)
                sortino = (mean_return / downside_std * np.sqrt(252)) if downside_std > 0 else 0
            else:
                sortino = 0
        else:
            sharpe = 0
            sortino = 0

        # MaxDD
        equity_curve = np.cumsum(returns)
        peak = np.maximum.accumulate(equity_curve)
        drawdown = (peak - equity_curve) / peak * 100
        max_dd = np.max(drawdown) if len(drawdown) > 0 else 0

        # Comisiones y funding
        total_fees = sum(t.get('fees', 0) for t in trades)
        total_funding = sum(t.get('funding', 0) for t in trades)

        return {
            'num_trades': len(trades),
            'total_pnl': total_pnl,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'sharpe_ratio': sharpe,
            'sortino_ratio': sortino,
            'max_dd': max_dd,
            'total_fees': total_fees,
            'total_funding': total_funding,
            'avg_return': np.mean(returns) if returns else 0,
            'avg_win': np.mean(winners) if winners else 0,
            'avg_loss': np.mean(losers) if losers else 0
        }

    def _get_top_strategies(self, strategy_metrics: List[Dict], n: int = 3) -> List[Dict]:
        """Obtiene las top N estrategias por PnL"""
        sorted_strategies = sorted(
            strategy_metrics,
            key=lambda x: x.get('total_pnl', 0),
            reverse=True
        )
        return sorted_strategies[:n]

    def _detect_anomalies(self, trades: List[Dict], metrics: Dict) -> List[str]:
        """Detecta anomalías en el trading de la semana"""
        anomalies = []

        # 1. Win rate muy bajo
        if metrics.get('win_rate', 0) < 30:
            anomalies.append(
                f"⚠️ Win rate muy bajo: {metrics['win_rate']:.1f}% (esperado >40%)"
            )

        # 2. Profit Factor < 1
        if metrics.get('profit_factor', 0) < 1:
            anomalies.append(
                f"⚠️ Profit Factor negativo: {metrics['profit_factor']:.2f} (esperado >1.5)"
            )

        # 3. Drawdown alto
        if metrics.get('max_dd', 0) > 10:
            anomalies.append(
                f"⚠️ Drawdown alto: {metrics['max_dd']:.2f}% (esperado <10%)"
            )

        # 4. Comisiones excesivas
        avg_fee_per_trade = metrics.get('total_fees', 0) / metrics.get('num_trades', 1)
        if avg_fee_per_trade > 5:  # $5 por trade es alto
            anomalies.append(
                f"⚠️ Comisiones altas: ${avg_fee_per_trade:.2f} promedio por trade"
            )

        # 5. Pocos trades
        if metrics.get('num_trades', 0) < 5:
            anomalies.append(
                f"ℹ️ Baja actividad: solo {metrics['num_trades']} trades esta semana"
            )

        # Si no hay anomalías, agregar mensaje positivo
        if not anomalies:
            anomalies.append("✅ No se detectaron anomalías significativas")

        return anomalies[:3]  # Máximo 3

    def _suggest_weight_changes(self, strategy_metrics: List[Dict]) -> List[str]:
        """Sugiere cambios en los pesos de estrategias"""
        suggestions = []

        for strategy in strategy_metrics:
            name = strategy.get('strategy', 'unknown')
            pnl = strategy.get('total_pnl', 0)
            win_rate = strategy.get('win_rate', 0)
            sharpe = strategy.get('sharpe_ratio', 0)

            # Sugerir aumentar peso si performance es buena
            if pnl > 0 and win_rate > 60 and sharpe > 1.5:
                suggestions.append(
                    f"↗️ Aumentar peso de '{name}': PnL={pnl:.2f}, WR={win_rate:.1f}%, Sharpe={sharpe:.2f}"
                )

            # Sugerir reducir peso si performance es mala
            elif pnl < 0 and win_rate < 40:
                suggestions.append(
                    f"↘️ Reducir peso de '{name}': PnL={pnl:.2f}, WR={win_rate:.1f}%"
                )

        if not suggestions:
            suggestions.append("➡️ Mantener pesos actuales")

        return suggestions[:3]  # Máximo 3

    def _format_report(
        self,
        week_start: datetime,
        week_end: datetime,
        trades: List[Dict],
        metrics: Dict,
        top_strategies: List[Dict],
        anomalies: List[str],
        suggestions: List[str]
    ) -> str:
        """Formatea el reporte completo"""
        lines = []
        lines.append("=" * 80)
        lines.append("REPORTE SEMANAL DE TRADING")
        lines.append("=" * 80)
        lines.append(f"\nSemana: {week_start.strftime('%Y-%m-%d')} a {week_end.strftime('%Y-%m-%d')}")
        lines.append(f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        # Resumen general
        lines.append("\n--- RESUMEN GENERAL ---")
        lines.append(f"Número de trades: {metrics.get('num_trades', 0)}")
        lines.append(f"PnL total: ${metrics.get('total_pnl', 0):.2f}")
        lines.append(f"Win Rate: {metrics.get('win_rate', 0):.1f}%")
        lines.append(f"Profit Factor: {metrics.get('profit_factor', 0):.2f}")
        lines.append(f"Retorno promedio: {metrics.get('avg_return', 0):.2f}%")
        lines.append(f"Ganancia promedio: {metrics.get('avg_win', 0):.2f}%")
        lines.append(f"Pérdida promedio: {metrics.get('avg_loss', 0):.2f}%")

        # Métricas de riesgo
        lines.append("\n--- MÉTRICAS DE RIESGO ---")
        lines.append(f"Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}")
        lines.append(f"Sortino Ratio: {metrics.get('sortino_ratio', 0):.2f}")
        lines.append(f"Max Drawdown: {metrics.get('max_dd', 0):.2f}%")

        # Costos
        lines.append("\n--- COSTOS ---")
        lines.append(f"Comisiones totales: ${metrics.get('total_fees', 0):.2f}")
        lines.append(f"Funding total: ${metrics.get('total_funding', 0):.2f}")
        lines.append(f"Costos totales: ${metrics.get('total_fees', 0) + metrics.get('total_funding', 0):.2f}")

        # Top estrategias
        lines.append("\n--- TOP 3 ESTRATEGIAS ---")
        for i, strategy in enumerate(top_strategies, 1):
            lines.append(
                f"{i}. {strategy.get('strategy', 'unknown')}: "
                f"PnL=${strategy.get('total_pnl', 0):.2f}, "
                f"WR={strategy.get('win_rate', 0):.1f}%, "
                f"PF={strategy.get('profit_factor', 0):.2f}"
            )

        # Anomalías
        lines.append("\n--- ANOMALÍAS DETECTADAS ---")
        for anomaly in anomalies:
            lines.append(anomaly)

        # Sugerencias
        lines.append("\n--- CAMBIOS SUGERIDOS DE PESOS ---")
        for suggestion in suggestions:
            lines.append(suggestion)

        lines.append("\n" + "=" * 80)
        lines.append("FIN DEL REPORTE")
        lines.append("=" * 80)

        return "\n".join(lines)

    def _create_summary(self, metrics: Dict) -> str:
        """Crea un resumen corto para alertas"""
        return (
            f"Trades: {metrics.get('num_trades', 0)} | "
            f"WR: {metrics.get('win_rate', 0):.1f}% | "
            f"PF: {metrics.get('profit_factor', 0):.2f} | "
            f"Sharpe: {metrics.get('sharpe_ratio', 0):.2f} | "
            f"MaxDD: {metrics.get('max_dd', 0):.2f}%"
        )

    def schedule_weekly_generation(self):
        """
        Programa generación automática cada semana

        Nota: Esto requiere un scheduler como APScheduler o similar
        Por ahora, el caller debe llamar a generate_weekly_report() manualmente
        """
        # TODO: Implementar con APScheduler si se requiere
        pass
