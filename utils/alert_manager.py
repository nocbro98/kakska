"""
Alert Manager
Sistema de alertas multi-canal (Telegram, Email, etc.)
"""
import logging
from typing import Optional, Callable, List
from datetime import datetime
from enum import Enum


class AlertLevel(Enum):
    """Niveles de alerta"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertManager:
    """
    Gestor de alertas multi-canal

    Soporta:
    - Logging
    - Callbacks personalizados (para Telegram, Discord, Email, etc.)
    - Archivo de alertas
    """

    def __init__(self, alerts_file: str = "data/alerts.log"):
        self.alerts_file = alerts_file
        self.logger = logging.getLogger("AlertManager")

        # Callbacks por nivel
        self.callbacks: List[Callable[[str, AlertLevel], None]] = []

        # Crear archivo de alertas
        try:
            with open(self.alerts_file, 'a') as f:
                f.write(f"\n{'='*60}\n")
                f.write(f"Alert Manager started at {datetime.now()}\n")
                f.write(f"{'='*60}\n")
        except Exception as e:
            self.logger.error(f"Error creating alerts file: {e}")

    def register_callback(self, callback: Callable[[str, AlertLevel], None]):
        """
        Registra un callback para recibir alertas

        El callback debe aceptar (message: str, level: AlertLevel)
        """
        self.callbacks.append(callback)
        self.logger.info(f"Registered alert callback: {callback.__name__}")

    def send_alert(self, message: str, level: AlertLevel = AlertLevel.INFO):
        """
        Envía una alerta a todos los canales registrados

        Args:
            message: Mensaje de la alerta
            level: Nivel de severidad
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_message = f"[{timestamp}] [{level.value.upper()}] {message}"

        # Log
        if level == AlertLevel.CRITICAL:
            self.logger.critical(message)
        elif level == AlertLevel.WARNING:
            self.logger.warning(message)
        else:
            self.logger.info(message)

        # Escribir a archivo
        try:
            with open(self.alerts_file, 'a') as f:
                f.write(formatted_message + '\n')
        except Exception as e:
            self.logger.error(f"Error writing to alerts file: {e}")

        # Llamar callbacks
        for callback in self.callbacks:
            try:
                callback(message, level)
            except Exception as e:
                self.logger.error(f"Error in alert callback {callback.__name__}: {e}")

    def alert_info(self, message: str):
        """Envía una alerta de nivel INFO"""
        self.send_alert(message, AlertLevel.INFO)

    def alert_warning(self, message: str):
        """Envía una alerta de nivel WARNING"""
        self.send_alert(message, AlertLevel.WARNING)

    def alert_critical(self, message: str):
        """Envía una alerta de nivel CRITICAL"""
        self.send_alert(message, AlertLevel.CRITICAL)

    def get_recent_alerts(self, n: int = 10) -> List[str]:
        """Obtiene las últimas N alertas"""
        try:
            with open(self.alerts_file, 'r') as f:
                lines = f.readlines()
                return lines[-n:]
        except Exception as e:
            self.logger.error(f"Error reading alerts file: {e}")
            return []
