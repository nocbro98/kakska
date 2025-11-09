# Changelog

## [3.0.0] - 2025-11-09

### Added - Core de Ejecución
- **ConnectionManager** con reconciliación automática al arranque
- **OrderRegistry** con sistema de idempotencia de órdenes
- **StateStore** para persistencia en SQLite
- **EventBus** sistema pub/sub para comunicación entre componentes
- clientOrderId determinístico: `SYM|STRAT|TS|SEQ|HASH`
- Regeneración de órdenes con SEQ+1 tras cancel/reject
- SlippageEstimator con selector de tipo de orden
- Validación de límites duros (tickSize, stepSize, minNotional)

### Added - Riesgo y Gobernanza
- **CircuitBreakerManager** con umbrales configurables
- Circuit breakers por período: diario, semanal, mensual
- Circuit breaker por racha de pérdidas
- Estados: RUNNING, PAUSED_DAILY/WEEKLY/MONTHLY/STREAK, MANUAL_LOCK
- Exposure caps configurables
- Perfiles de riesgo: conservador, normal, agresivo

### Added - Atribución y Métricas
- **AttributionSystem** para tracking por estrategia y régimen
- Journal estructurado en SQLite con todos los campos requeridos
- Campos: ts_open, ts_close, strategy_primary, strategies_confluence
- Campos: regime_trend, regime_volatility, entry_type
- Campos: plan_rr, r_achieved, fees, funding, slippage_real
- Campos: mae, mfe, reason_exit, notes
- Equity curves por estrategia
- KPIs por régimen de mercado
- Matriz de confusión de señales

### Added - Portfolio de Señales
- **ICWeightingSystem** con pesos dinámicos basados en IC
- Information Coefficient (IC) con EWMA (λ=0.94)
- Caps: máximo 50%, mínimo 10% por estrategia
- Penalización temporal para IC < 0
- Rebalance automático cada 7 días

### Added - Regímenes de Mercado
- **RegimeDetector** para filtrado de señales
- Detección de tendencia: ADX + slope MA
- Detección de volatilidad: ATR percentil
- Detección de squeeze: Bollinger Bandwidth percentil
- Bloqueo/liberación de estrategias según régimen
- Ajuste automático de tamaño por volatilidad

### Added - Reportes y Alertas
- **WeeklyReportGenerator** para reportes automáticos
- Contenido: trades, Sharpe/Sortino, PF, MaxDD, hitrate
- Top 3 estrategias por performance
- Detección de 3 anomalías
- Sugerencias de cambios de pesos
- **AlertManager** multi-canal
- Sistema de alertas por nivel (INFO, WARNING, CRITICAL)

### Added - Sistema Integrado
- **TradingSystem** clase principal que integra todos los componentes
- Inicialización automática de todos los subsistemas
- Reconciliación al startup
- API unificada para operaciones
- Shutdown limpio con persistencia de estado

### Changed
- Arquitectura completamente modular
- Event-driven design para desacoplamiento
- Persistencia completa en SQLite
- Logging exhaustivo con niveles apropiados

### Technical Debt
- GUI completa (T8) - pendiente
- Backtesting robusto con walk-forward
- Multi-activo con gestión de correlación
- Tests unitarios automatizados
- Integración con Telegram/Discord

## [2.0.0] - Anterior

### Features anteriores del binance_bot_2.py
- Perfiles de riesgo básicos
- Estrategias: Elliott, Fibonacci, Wyckoff, SMC
- WebSocket avanzado con reconexión
- Risk Controller básico
- Position Manager con salidas parciales
- Sistema de confluencia básico
- GUI básica

---

**Nota**: Este changelog documenta la evolución hacia una arquitectura profesional completa con todos los componentes críticos de un sistema de trading institucional.
