"""
Modern Trading GUI
Interfaz gráfica mejorada con responsividad y configuración dinámica

Mejoras sobre GUI legacy:
- API calls en background threads (non-blocking)
- Configuración dinámica (risk profile, symbol, timeframe)
- Messagebox para errores críticos
- Layout responsivo con grid
- Display de régimen de mercado
- Kill-switch mejorado
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import queue
from typing import Optional, Callable, Dict, Any
from datetime import datetime
from enum import Enum


class GUIState(Enum):
    """Estados de la GUI"""
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class ModernTradingGUI:
    """
    Interfaz gráfica mejorada para trading bot

    Características:
    - Non-blocking API calls
    - Dynamic configuration
    - Real-time status updates
    - Error handling with messageboxes
    - Market regime display
    - Responsive layout
    """

    def __init__(
        self,
        start_callback: Callable[[], None],
        stop_callback: Callable[[], None],
        get_status_callback: Callable[[], Dict[str, Any]],
        update_config_callback: Optional[Callable[[Dict], bool]] = None
    ):
        """
        Args:
            start_callback: Función para iniciar el bot
            stop_callback: Función para detener el bot
            get_status_callback: Función para obtener estado del bot
            update_config_callback: Función para actualizar configuración
        """
        self.start_callback = start_callback
        self.stop_callback = stop_callback
        self.get_status_callback = get_status_callback
        self.update_config_callback = update_config_callback

        # Estado
        self.state = GUIState.IDLE
        self.root = None

        # Widgets principales
        self.widgets = {}

        # Queue para actualizaciones desde threads
        self.update_queue = queue.Queue()

        # Último error
        self.last_error = None

    def create_window(self):
        """Crea la ventana principal"""

        self.root = tk.Tk()
        self.root.title("Trading Bot - Modern Interface")
        self.root.geometry("1000x700")
        self.root.resizable(True, True)

        # Configurar grid para responsividad
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # Crear secciones
        self._create_config_section()
        self._create_status_section()
        self._create_controls_section()
        self._create_log_section()

        # Iniciar actualizador periódico
        self._start_periodic_update()

        # Cerrar ventana correctamente
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _create_config_section(self):
        """Crea sección de configuración dinámica"""

        frame = ttk.LabelFrame(self.root, text="⚙️ Configuración", padding=10)
        frame.grid(row=0, column=0, sticky="ew", padx=10, pady=5)

        # Grid responsivo
        for i in range(4):
            frame.grid_columnconfigure(i, weight=1)

        # Symbol
        ttk.Label(frame, text="Symbol:").grid(row=0, column=0, sticky="w")
        self.widgets['symbol_var'] = tk.StringVar(value="BTCUSDT")
        self.widgets['symbol_entry'] = ttk.Entry(
            frame,
            textvariable=self.widgets['symbol_var'],
            width=12
        )
        self.widgets['symbol_entry'].grid(row=0, column=1, sticky="ew", padx=5)

        # Timeframe
        ttk.Label(frame, text="Timeframe:").grid(row=0, column=2, sticky="w", padx=(20, 0))
        self.widgets['timeframe_var'] = tk.StringVar(value="5m")
        self.widgets['timeframe_combo'] = ttk.Combobox(
            frame,
            textvariable=self.widgets['timeframe_var'],
            values=["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h"],
            width=8,
            state="readonly"
        )
        self.widgets['timeframe_combo'].grid(row=0, column=3, sticky="ew", padx=5)

        # Risk Profile
        ttk.Label(frame, text="Risk Profile:").grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.widgets['risk_profile_var'] = tk.StringVar(value="Normal")
        self.widgets['risk_profile_combo'] = ttk.Combobox(
            frame,
            textvariable=self.widgets['risk_profile_var'],
            values=["Conservador", "Normal", "Agresivo"],
            width=12,
            state="readonly"
        )
        self.widgets['risk_profile_combo'].grid(row=1, column=1, sticky="ew", padx=5, pady=(10, 0))

        # Testnet
        self.widgets['testnet_var'] = tk.BooleanVar(value=True)
        self.widgets['testnet_check'] = ttk.Checkbutton(
            frame,
            text="Testnet Mode",
            variable=self.widgets['testnet_var']
        )
        self.widgets['testnet_check'].grid(row=1, column=2, columnspan=2, sticky="w", padx=(20, 0), pady=(10, 0))

        # Botón para aplicar configuración
        self.widgets['apply_config_btn'] = ttk.Button(
            frame,
            text="Aplicar Configuración",
            command=self._apply_configuration
        )
        self.widgets['apply_config_btn'].grid(row=2, column=0, columnspan=4, pady=(15, 5))

    def _create_status_section(self):
        """Crea sección de estado"""

        frame = ttk.LabelFrame(self.root, text="📊 Estado", padding=10)
        frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)

        # Grid responsivo
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)

        # Estado general (izquierda)
        status_frame = ttk.Frame(frame)
        status_frame.grid(row=0, column=0, sticky="nsew", padx=5)

        # Bot status
        ttk.Label(status_frame, text="Bot Status:", font=("Arial", 10, "bold")).grid(
            row=0, column=0, sticky="w", pady=5
        )
        self.widgets['bot_status_label'] = ttk.Label(
            status_frame,
            text="⚪ Detenido",
            font=("Arial", 10)
        )
        self.widgets['bot_status_label'].grid(row=0, column=1, sticky="w", padx=10, pady=5)

        # Balance
        ttk.Label(status_frame, text="Balance:", font=("Arial", 10, "bold")).grid(
            row=1, column=0, sticky="w", pady=5
        )
        self.widgets['balance_label'] = ttk.Label(
            status_frame,
            text="$0.00",
            font=("Arial", 10)
        )
        self.widgets['balance_label'].grid(row=1, column=1, sticky="w", padx=10, pady=5)

        # Position
        ttk.Label(status_frame, text="Position:", font=("Arial", 10, "bold")).grid(
            row=2, column=0, sticky="w", pady=5
        )
        self.widgets['position_label'] = ttk.Label(
            status_frame,
            text="None",
            font=("Arial", 10)
        )
        self.widgets['position_label'].grid(row=2, column=1, sticky="w", padx=10, pady=5)

        # PnL
        ttk.Label(status_frame, text="Total PnL:", font=("Arial", 10, "bold")).grid(
            row=3, column=0, sticky="w", pady=5
        )
        self.widgets['pnl_label'] = ttk.Label(
            status_frame,
            text="$0.00 (0.00%)",
            font=("Arial", 10)
        )
        self.widgets['pnl_label'].grid(row=3, column=1, sticky="w", padx=10, pady=5)

        # Circuit Breaker Status
        ttk.Label(status_frame, text="Circuit Breaker:", font=("Arial", 10, "bold")).grid(
            row=4, column=0, sticky="w", pady=5
        )
        self.widgets['cb_status_label'] = ttk.Label(
            status_frame,
            text="✅ OK",
            font=("Arial", 10),
            foreground="green"
        )
        self.widgets['cb_status_label'].grid(row=4, column=1, sticky="w", padx=10, pady=5)

        # Market Regime (derecha)
        regime_frame = ttk.LabelFrame(frame, text="🌍 Régimen de Mercado", padding=10)
        regime_frame.grid(row=0, column=1, sticky="nsew", padx=5)

        self.widgets['regime_text'] = tk.Text(
            regime_frame,
            height=10,
            width=40,
            font=("Courier", 9),
            state='disabled',
            bg="#f0f0f0"
        )
        self.widgets['regime_text'].pack(fill=tk.BOTH, expand=True)

        # Métricas rápidas (fila inferior)
        metrics_frame = ttk.Frame(frame)
        metrics_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        ttk.Label(metrics_frame, text="Trades:", font=("Arial", 9)).grid(row=0, column=0, sticky="w")
        self.widgets['trades_label'] = ttk.Label(metrics_frame, text="0", font=("Arial", 9))
        self.widgets['trades_label'].grid(row=0, column=1, sticky="w", padx=5)

        ttk.Label(metrics_frame, text="Win Rate:", font=("Arial", 9)).grid(row=0, column=2, sticky="w", padx=(20, 0))
        self.widgets['winrate_label'] = ttk.Label(metrics_frame, text="0%", font=("Arial", 9))
        self.widgets['winrate_label'].grid(row=0, column=3, sticky="w", padx=5)

        ttk.Label(metrics_frame, text="Uptime:", font=("Arial", 9)).grid(row=0, column=4, sticky="w", padx=(20, 0))
        self.widgets['uptime_label'] = ttk.Label(metrics_frame, text="0h 0m", font=("Arial", 9))
        self.widgets['uptime_label'].grid(row=0, column=5, sticky="w", padx=5)

    def _create_controls_section(self):
        """Crea sección de controles"""

        frame = ttk.Frame(self.root, padding=10)
        frame.grid(row=2, column=0, sticky="ew", padx=10, pady=5)

        # Grid responsivo
        for i in range(5):
            frame.grid_columnconfigure(i, weight=1)

        # Start button
        self.widgets['start_btn'] = ttk.Button(
            frame,
            text="▶️ Iniciar Bot",
            command=self._start_bot,
            style="Success.TButton"
        )
        self.widgets['start_btn'].grid(row=0, column=0, sticky="ew", padx=5)

        # Stop button
        self.widgets['stop_btn'] = ttk.Button(
            frame,
            text="⏹️ Detener Bot",
            command=self._stop_bot,
            state="disabled",
            style="Danger.TButton"
        )
        self.widgets['stop_btn'].grid(row=0, column=1, sticky="ew", padx=5)

        # Kill Switch (emergency stop)
        self.widgets['kill_btn'] = ttk.Button(
            frame,
            text="🚨 KILL SWITCH",
            command=self._emergency_stop,
            state="disabled"
        )
        self.widgets['kill_btn'].grid(row=0, column=2, sticky="ew", padx=5)

        # Clear Logs
        self.widgets['clear_logs_btn'] = ttk.Button(
            frame,
            text="🗑️ Limpiar Logs",
            command=self._clear_logs
        )
        self.widgets['clear_logs_btn'].grid(row=0, column=3, sticky="ew", padx=5)

        # Refresh Status
        self.widgets['refresh_btn'] = ttk.Button(
            frame,
            text="🔄 Actualizar",
            command=self._refresh_status
        )
        self.widgets['refresh_btn'].grid(row=0, column=4, sticky="ew", padx=5)

    def _create_log_section(self):
        """Crea sección de logs"""

        frame = ttk.LabelFrame(self.root, text="📋 Logs", padding=10)
        frame.grid(row=3, column=0, sticky="nsew", padx=10, pady=5)

        # Grid responsivo
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        # Text widget con scroll
        self.widgets['log_text'] = scrolledtext.ScrolledText(
            frame,
            height=15,
            font=("Courier", 9),
            state='disabled'
        )
        self.widgets['log_text'].grid(row=0, column=0, sticky="nsew")

        # Configurar tags de colores
        self.widgets['log_text'].tag_config("INFO", foreground="black")
        self.widgets['log_text'].tag_config("SUCCESS", foreground="green", font=("Courier", 9, "bold"))
        self.widgets['log_text'].tag_config("WARNING", foreground="orange", font=("Courier", 9, "bold"))
        self.widgets['log_text'].tag_config("ERROR", foreground="red", font=("Courier", 9, "bold"))
        self.widgets['log_text'].tag_config("CRITICAL", foreground="darkred", font=("Courier", 9, "bold"))

    def _apply_configuration(self):
        """Aplica configuración actualizada (sin reiniciar bot)"""

        if self.state == GUIState.RUNNING:
            response = messagebox.askyesno(
                "Bot en ejecución",
                "El bot está en ejecución. ¿Desea detenerlo, aplicar la configuración y reiniciarlo?"
            )

            if not response:
                return

            # Detener, aplicar, reiniciar
            self._stop_bot()
            self.root.after(2000, self._apply_and_restart)
        else:
            # Aplicar directamente
            self._do_apply_configuration()

    def _apply_and_restart(self):
        """Aplica configuración y reinicia bot"""
        if self._do_apply_configuration():
            self.root.after(1000, self._start_bot)

    def _do_apply_configuration(self) -> bool:
        """Aplica configuración actual"""

        if not self.update_config_callback:
            messagebox.showwarning(
                "No disponible",
                "Actualización de configuración no disponible en esta versión"
            )
            return False

        config = {
            'symbol': self.widgets['symbol_var'].get(),
            'timeframe': self.widgets['timeframe_var'].get(),
            'risk_profile': self.widgets['risk_profile_var'].get().lower(),
            'testnet': self.widgets['testnet_var'].get()
        }

        try:
            success = self.update_config_callback(config)

            if success:
                messagebox.showinfo(
                    "Configuración actualizada",
                    "La configuración se aplicó correctamente"
                )
                self.log_message("✅ Configuration updated", "SUCCESS")
                return True
            else:
                raise Exception("Update returned False")

        except Exception as e:
            messagebox.showerror(
                "Error de configuración",
                f"No se pudo aplicar la configuración:\n{str(e)}"
            )
            self.log_message(f"❌ Config error: {e}", "ERROR")
            return False

    def _start_bot(self):
        """Inicia el bot en background thread"""

        if self.state == GUIState.RUNNING:
            messagebox.showwarning("Bot en ejecución", "El bot ya está en ejecución")
            return

        # Confirmar inicio
        symbol = self.widgets['symbol_var'].get()
        timeframe = self.widgets['timeframe_var'].get()
        testnet = self.widgets['testnet_var'].get()

        response = messagebox.askyesno(
            "Iniciar Bot",
            f"¿Iniciar trading bot?\n\n"
            f"Symbol: {symbol}\n"
            f"Timeframe: {timeframe}\n"
            f"Mode: {'Testnet' if testnet else 'PRODUCCIÓN'}"
        )

        if not response:
            return

        # Cambiar estado
        self.state = GUIState.STARTING
        self._update_button_states()

        # Log
        self.log_message("🚀 Iniciando bot...", "INFO")

        # Ejecutar en background thread
        threading.Thread(
            target=self._background_start,
            daemon=True
        ).start()

    def _background_start(self):
        """Inicia bot en background (non-blocking)"""

        try:
            self.start_callback()

            # Actualizar estado en main thread
            self.update_queue.put(('state', GUIState.RUNNING))
            self.update_queue.put(('log', ('✅ Bot iniciado correctamente', 'SUCCESS')))

        except Exception as e:
            self.last_error = str(e)
            self.update_queue.put(('state', GUIState.ERROR))
            self.update_queue.put(('log', (f'❌ Error al iniciar: {e}', 'ERROR')))
            self.update_queue.put(('error', f'Error al iniciar el bot:\n{e}'))

    def _stop_bot(self):
        """Detiene el bot"""

        if self.state != GUIState.RUNNING:
            return

        # Confirmar detención
        response = messagebox.askyesno(
            "Detener Bot",
            "¿Detener el bot?\n\n"
            "Las posiciones abiertas se cerrarán."
        )

        if not response:
            return

        # Cambiar estado
        self.state = GUIState.STOPPING
        self._update_button_states()

        # Log
        self.log_message("⏹️ Deteniendo bot...", "INFO")

        # Ejecutar en background
        threading.Thread(
            target=self._background_stop,
            daemon=True
        ).start()

    def _background_stop(self):
        """Detiene bot en background"""

        try:
            self.stop_callback()

            # Actualizar estado
            self.update_queue.put(('state', GUIState.IDLE))
            self.update_queue.put(('log', ('✅ Bot detenido', 'SUCCESS')))

        except Exception as e:
            self.update_queue.put(('log', (f'❌ Error al detener: {e}', 'ERROR')))
            self.update_queue.put(('error', f'Error al detener el bot:\n{e}'))

    def _emergency_stop(self):
        """Detención de emergencia (kill switch)"""

        response = messagebox.askokcancel(
            "🚨 KILL SWITCH",
            "DETENCIÓN DE EMERGENCIA\n\n"
            "Esto detendrá el bot inmediatamente y cerrará\n"
            "todas las posiciones abiertas.\n\n"
            "¿Continuar?",
            icon='warning'
        )

        if not response:
            return

        self.log_message("🚨 KILL SWITCH ACTIVATED", "CRITICAL")

        # Forzar detención inmediata
        try:
            self.stop_callback()
            self.state = GUIState.IDLE
            self._update_button_states()
            self.log_message("✅ Emergency stop completed", "SUCCESS")

        except Exception as e:
            messagebox.showerror(
                "Error crítico",
                f"Error durante detención de emergencia:\n{e}"
            )

    def _refresh_status(self):
        """Actualiza estado del bot (en background)"""

        threading.Thread(
            target=self._background_refresh,
            daemon=True
        ).start()

    def _background_refresh(self):
        """Actualiza estado en background"""

        try:
            status = self.get_status_callback()
            self.update_queue.put(('status', status))

        except Exception as e:
            self.update_queue.put(('log', (f'Error al actualizar: {e}', 'WARNING')))

    def _clear_logs(self):
        """Limpia el área de logs"""

        self.widgets['log_text'].config(state='normal')
        self.widgets['log_text'].delete(1.0, tk.END)
        self.widgets['log_text'].config(state='disabled')

    def _update_button_states(self):
        """Actualiza estado de botones según estado actual"""

        if self.state == GUIState.IDLE:
            self.widgets['start_btn'].config(state='normal')
            self.widgets['stop_btn'].config(state='disabled')
            self.widgets['kill_btn'].config(state='disabled')
            self.widgets['bot_status_label'].config(text="⚪ Detenido", foreground="gray")

        elif self.state == GUIState.STARTING:
            self.widgets['start_btn'].config(state='disabled')
            self.widgets['stop_btn'].config(state='disabled')
            self.widgets['kill_btn'].config(state='disabled')
            self.widgets['bot_status_label'].config(text="🔄 Iniciando...", foreground="blue")

        elif self.state == GUIState.RUNNING:
            self.widgets['start_btn'].config(state='disabled')
            self.widgets['stop_btn'].config(state='normal')
            self.widgets['kill_btn'].config(state='normal')
            self.widgets['bot_status_label'].config(text="🟢 En ejecución", foreground="green")

        elif self.state == GUIState.STOPPING:
            self.widgets['start_btn'].config(state='disabled')
            self.widgets['stop_btn'].config(state='disabled')
            self.widgets['kill_btn'].config(state='disabled')
            self.widgets['bot_status_label'].config(text="🔄 Deteniendo...", foreground="orange")

        elif self.state == GUIState.ERROR:
            self.widgets['start_btn'].config(state='normal')
            self.widgets['stop_btn'].config(state='disabled')
            self.widgets['kill_btn'].config(state='disabled')
            self.widgets['bot_status_label'].config(text="🔴 Error", foreground="red")

    def _start_periodic_update(self):
        """Inicia actualizador periódico"""

        # Procesar queue de actualizaciones
        self._process_update_queue()

        # Actualizar cada 100ms para mayor responsividad
        self.root.after(100, self._start_periodic_update)

    def _process_update_queue(self):
        """Procesa queue de actualizaciones desde threads (soporta formato tuple y dict)"""

        while not self.update_queue.empty():
            try:
                item = self.update_queue.get_nowait()

                # Manejar formato antiguo (tuple) y nuevo (dict del monkey patching)
                if isinstance(item, dict):
                    # Nuevo formato del monkey patching: {'type': 'status', 'data': ...}
                    update_type = item.get('type')
                    data = item.get('data')

                    if update_type == 'status':
                        # Actualizar indicador de conexión
                        if data == 'running':
                            self.widgets['bot_status_label'].config(text="🟢 Running", foreground="green")
                        else:
                            self.widgets['bot_status_label'].config(text="🔴 Stopped", foreground="red")

                    elif update_type == 'balance':
                        # Actualizar balance y PnL
                        if isinstance(data, dict):
                            balance = data.get('available_balance', 0.0)
                            self.widgets['balance_label'].config(text=f"${balance:.2f}")

                            unrealized_pnl = data.get('unrealized_pnl', 0.0)
                            if unrealized_pnl != 0:
                                color = "green" if unrealized_pnl > 0 else "red"
                                self.widgets['pnl_label'].config(
                                    text=f"${unrealized_pnl:.2f}",
                                    foreground=color
                                )

                    elif update_type == 'position':
                        # Actualizar información de posición
                        if isinstance(data, dict):
                            side = data.get('side', 'N/A')
                            quantity = data.get('quantity', 0)
                            entry_price = data.get('entry_price', 0)

                            position_text = f"{side} {quantity:.3f} @ ${entry_price:.2f}"
                            if 'position_label' in self.widgets:
                                self.widgets['position_label'].config(text=position_text)

                elif isinstance(item, tuple):
                    # Formato antiguo: ('state', data) o ('log', (msg, level))
                    update_type, data = item

                    if update_type == 'state':
                        self.state = data
                        self._update_button_states()

                    elif update_type == 'log':
                        message, level = data
                        self.log_message(message, level)

                    elif update_type == 'status':
                        self._update_status_display(data)

                    elif update_type == 'error':
                        messagebox.showerror("Error", data)

            except queue.Empty:
                break
            except Exception as e:
                # Silent error handling para no romper el loop de UI
                import traceback
                traceback.print_exc()

    def _update_status_display(self, status: Dict):
        """Actualiza display de estado"""

        # Balance
        if 'balance' in status:
            self.widgets['balance_label'].config(text=f"${status['balance']:.2f}")

        # Position
        if 'position' in status:
            pos = status['position']
            if pos:
                self.widgets['position_label'].config(
                    text=f"{pos['side']} {pos['quantity']} @ ${pos['entry_price']:.2f}"
                )
            else:
                self.widgets['position_label'].config(text="None")

        # PnL
        if 'pnl_usdt' in status and 'pnl_pct' in status:
            pnl_text = f"${status['pnl_usdt']:.2f} ({status['pnl_pct']:+.2f}%)"
            color = "green" if status['pnl_usdt'] >= 0 else "red"
            self.widgets['pnl_label'].config(text=pnl_text, foreground=color)

        # Circuit Breaker
        if 'circuit_breaker' in status:
            cb = status['circuit_breaker']
            if cb.get('paused', False):
                self.widgets['cb_status_label'].config(
                    text=f"⛔ PAUSED: {cb.get('reason', 'Unknown')}",
                    foreground="red"
                )
            else:
                self.widgets['cb_status_label'].config(text="✅ OK", foreground="green")

        # Market Regime
        if 'regime' in status:
            self._update_regime_display(status['regime'])

        # Metrics
        if 'total_trades' in status:
            self.widgets['trades_label'].config(text=str(status['total_trades']))

        if 'win_rate' in status:
            self.widgets['winrate_label'].config(text=f"{status['win_rate']:.1f}%")

        if 'uptime_seconds' in status:
            hours = status['uptime_seconds'] // 3600
            minutes = (status['uptime_seconds'] % 3600) // 60
            self.widgets['uptime_label'].config(text=f"{hours}h {minutes}m")

    def _update_regime_display(self, regime: Dict):
        """Actualiza display de régimen de mercado"""

        if not regime or not regime.get('detected', False):
            regime_text = "No regime detected"
        else:
            regime_text = (
                f"Trend: {regime['trend_type']}\n"
                f"Strength: {regime['trend_strength']:.1f}\n"
                f"Slope: {regime['trend_slope']:.4f}\n"
                f"\n"
                f"Volatility: {regime['volatility_type']}\n"
                f"Percentile: {regime['volatility_percentile']:.1f}\n"
                f"\n"
                f"Squeeze: {'YES' if regime.get('is_squeeze') else 'NO'}\n"
                f"BB Width %ile: {regime.get('bb_width_percentile', 0):.1f}\n"
                f"\n"
                f"Recommended:\n"
            )

            for strat in regime.get('recommended_strategies', []):
                regime_text += f"  • {strat}\n"

            regime_text += f"\nSize Mult: {regime.get('position_size_multiplier', 1.0):.2f}x"

        # Actualizar text widget
        self.widgets['regime_text'].config(state='normal')
        self.widgets['regime_text'].delete(1.0, tk.END)
        self.widgets['regime_text'].insert(1.0, regime_text)
        self.widgets['regime_text'].config(state='disabled')

    def log_message(self, message: str, level: str = "INFO"):
        """Agrega mensaje al log"""

        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}\n"

        self.widgets['log_text'].config(state='normal')
        self.widgets['log_text'].insert(tk.END, formatted, level)
        self.widgets['log_text'].see(tk.END)
        self.widgets['log_text'].config(state='disabled')

    def _on_close(self):
        """Maneja cierre de ventana"""

        if self.state == GUIState.RUNNING:
            response = messagebox.askyesnocancel(
                "Cerrar aplicación",
                "El bot está en ejecución.\n\n"
                "¿Desea detenerlo antes de cerrar?\n\n"
                "Sí: Detener y cerrar\n"
                "No: Cerrar sin detener (bot continúa)\n"
                "Cancelar: No cerrar"
            )

            if response is None:  # Cancel
                return

            if response:  # Yes - stop and close
                self.stop_callback()

        self.root.destroy()

    def run(self):
        """Inicia el loop de la GUI"""

        if self.root is None:
            self.create_window()

        self.root.mainloop()
