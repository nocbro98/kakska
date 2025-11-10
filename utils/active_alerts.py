"""
Active Alerts System
Sistema de alertas activo con integración real de Telegram, Discord y Email

Implementa notificaciones reales (no solo logging) para eventos críticos:
- Circuit breakers
- Stop loss/Take profit
- Errores críticos
- Posiciones abiertas/cerradas
"""

import logging
import os
from typing import Optional, Callable, List, Dict, Any
from datetime import datetime
from enum import Enum


class AlertLevel(Enum):
    """Niveles de alerta"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class TelegramAlert:
    """Envío de alertas via Telegram"""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.logger = logging.getLogger("TelegramAlert")

        try:
            import requests
            self.requests = requests
            self.enabled = True

            # Verificar conexión
            self._test_connection()

        except ImportError:
            self.logger.warning("requests not installed, Telegram alerts disabled")
            self.enabled = False

    def _test_connection(self):
        """Verifica que el bot funcione"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/getMe"
            response = self.requests.get(url, timeout=5)

            if response.status_code == 200:
                bot_info = response.json()
                self.logger.info(
                    f"Telegram bot connected: @{bot_info['result']['username']}"
                )
            else:
                self.logger.error(f"Telegram bot test failed: {response.status_code}")
                self.enabled = False

        except Exception as e:
            self.logger.error(f"Telegram connection test failed: {e}")
            self.enabled = False

    def send(self, message: str, level: AlertLevel = AlertLevel.INFO):
        """Envía mensaje via Telegram"""
        if not self.enabled:
            return

        try:
            # Añadir emoji según nivel
            emoji_map = {
                AlertLevel.INFO: "ℹ️",
                AlertLevel.WARNING: "⚠️",
                AlertLevel.CRITICAL: "🚨"
            }

            emoji = emoji_map.get(level, "📢")
            formatted_message = f"{emoji} {message}"

            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': formatted_message,
                'parse_mode': 'HTML'
            }

            response = self.requests.post(url, json=payload, timeout=10)

            if response.status_code != 200:
                self.logger.error(f"Telegram send failed: {response.status_code}")

        except Exception as e:
            self.logger.error(f"Error sending Telegram alert: {e}")


class DiscordAlert:
    """Envío de alertas via Discord Webhook"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self.logger = logging.getLogger("DiscordAlert")

        try:
            import requests
            self.requests = requests
            self.enabled = True

            # Verificar webhook
            self._test_connection()

        except ImportError:
            self.logger.warning("requests not installed, Discord alerts disabled")
            self.enabled = False

    def _test_connection(self):
        """Verifica que el webhook funcione"""
        try:
            # Discord permite GET para verificar webhook
            response = self.requests.get(self.webhook_url, timeout=5)

            if response.status_code == 200:
                self.logger.info("Discord webhook connected")
            else:
                self.logger.warning(f"Discord webhook may not work: {response.status_code}")

        except Exception as e:
            self.logger.error(f"Discord connection test failed: {e}")
            self.enabled = False

    def send(self, message: str, level: AlertLevel = AlertLevel.INFO):
        """Envía mensaje via Discord"""
        if not self.enabled:
            return

        try:
            # Color según nivel
            color_map = {
                AlertLevel.INFO: 0x3498db,      # Azul
                AlertLevel.WARNING: 0xf39c12,   # Naranja
                AlertLevel.CRITICAL: 0xe74c3c   # Rojo
            }

            color = color_map.get(level, 0x95a5a6)

            payload = {
                'embeds': [{
                    'title': f"{level.value.upper()} Alert",
                    'description': message,
                    'color': color,
                    'timestamp': datetime.utcnow().isoformat()
                }]
            }

            response = self.requests.post(self.webhook_url, json=payload, timeout=10)

            if response.status_code != 204:
                self.logger.error(f"Discord send failed: {response.status_code}")

        except Exception as e:
            self.logger.error(f"Error sending Discord alert: {e}")


class EmailAlert:
    """Envío de alertas via Email (SMTP)"""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        from_email: str,
        to_email: str,
        password: str
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.from_email = from_email
        self.to_email = to_email
        self.password = password
        self.logger = logging.getLogger("EmailAlert")

        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            self.smtplib = smtplib
            self.MIMEText = MIMEText
            self.MIMEMultipart = MIMEMultipart
            self.enabled = True

            # Verificar conexión
            self._test_connection()

        except ImportError:
            self.logger.warning("email libraries not available, Email alerts disabled")
            self.enabled = False

    def _test_connection(self):
        """Verifica conexión SMTP"""
        try:
            server = self.smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10)
            server.starttls()
            server.login(self.from_email, self.password)
            server.quit()

            self.logger.info(f"Email SMTP connected: {self.smtp_host}:{self.smtp_port}")

        except Exception as e:
            self.logger.error(f"Email connection test failed: {e}")
            self.enabled = False

    def send(self, message: str, level: AlertLevel = AlertLevel.INFO):
        """Envía email"""
        if not self.enabled:
            return

        try:
            msg = self.MIMEMultipart()
            msg['From'] = self.from_email
            msg['To'] = self.to_email
            msg['Subject'] = f"Trading Bot Alert - {level.value.upper()}"

            body = f"""
Trading Bot Alert

Level: {level.value.upper()}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Message:
{message}

---
Automated alert from Trading Bot
            """

            msg.attach(self.MIMEText(body, 'plain'))

            server = self.smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10)
            server.starttls()
            server.login(self.from_email, self.password)
            server.send_message(msg)
            server.quit()

        except Exception as e:
            self.logger.error(f"Error sending email alert: {e}")


class ActiveAlertManager:
    """
    Gestor de alertas activas con múltiples canales

    Auto-configura canales desde variables de entorno:
    - TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    - DISCORD_WEBHOOK_URL
    - EMAIL_SMTP_HOST, EMAIL_FROM, EMAIL_TO, EMAIL_PASSWORD
    """

    def __init__(self):
        self.logger = logging.getLogger("ActiveAlertManager")

        # Canales
        self.telegram: Optional[TelegramAlert] = None
        self.discord: Optional[DiscordAlert] = None
        self.email: Optional[EmailAlert] = None

        # Callbacks adicionales
        self.callbacks: List[Callable] = []

        # Auto-configurar desde env
        self._auto_configure()

    def _auto_configure(self):
        """Configura canales automáticamente desde variables de entorno"""

        # Telegram
        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        telegram_chat = os.getenv("TELEGRAM_CHAT_ID")

        if telegram_token and telegram_chat:
            self.logger.info("Configuring Telegram alerts...")
            self.telegram = TelegramAlert(telegram_token, telegram_chat)
        else:
            self.logger.debug("Telegram not configured (missing token or chat_id)")

        # Discord
        discord_webhook = os.getenv("DISCORD_WEBHOOK_URL")

        if discord_webhook:
            self.logger.info("Configuring Discord alerts...")
            self.discord = DiscordAlert(discord_webhook)
        else:
            self.logger.debug("Discord not configured (missing webhook)")

        # Email
        email_host = os.getenv("EMAIL_SMTP_HOST")
        email_from = os.getenv("EMAIL_FROM")
        email_to = os.getenv("EMAIL_TO")
        email_password = os.getenv("EMAIL_PASSWORD")

        if all([email_host, email_from, email_to, email_password]):
            email_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
            self.logger.info("Configuring Email alerts...")
            self.email = EmailAlert(
                email_host, email_port, email_from, email_to, email_password
            )
        else:
            self.logger.debug("Email not configured (missing credentials)")

        # Resumen
        active_channels = []
        if self.telegram and self.telegram.enabled:
            active_channels.append("Telegram")
        if self.discord and self.discord.enabled:
            active_channels.append("Discord")
        if self.email and self.email.enabled:
            active_channels.append("Email")

        if active_channels:
            self.logger.info(f"✓ Active alert channels: {', '.join(active_channels)}")
        else:
            self.logger.warning("⚠️ No alert channels configured!")

    def add_callback(self, callback: Callable[[str, AlertLevel], None]):
        """Añade callback personalizado"""
        self.callbacks.append(callback)
        self.logger.info(f"Added alert callback: {callback.__name__}")

    def send_alert(self, message: str, level: AlertLevel = AlertLevel.INFO):
        """Envía alerta a todos los canales activos"""

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] [{level.value.upper()}] {message}"

        # Log
        if level == AlertLevel.CRITICAL:
            self.logger.critical(message)
        elif level == AlertLevel.WARNING:
            self.logger.warning(message)
        else:
            self.logger.info(message)

        # Telegram
        if self.telegram and self.telegram.enabled:
            try:
                self.telegram.send(message, level)
            except Exception as e:
                self.logger.error(f"Error sending Telegram alert: {e}")

        # Discord
        if self.discord and self.discord.enabled:
            try:
                self.discord.send(message, level)
            except Exception as e:
                self.logger.error(f"Error sending Discord alert: {e}")

        # Email (solo WARNING y CRITICAL para evitar spam)
        if self.email and self.email.enabled and level in [AlertLevel.WARNING, AlertLevel.CRITICAL]:
            try:
                self.email.send(message, level)
            except Exception as e:
                self.logger.error(f"Error sending Email alert: {e}")

        # Callbacks personalizados
        for callback in self.callbacks:
            try:
                callback(message, level)
            except Exception as e:
                self.logger.error(f"Error in alert callback: {e}")

    def alert_info(self, message: str):
        """Envía alerta INFO"""
        self.send_alert(message, AlertLevel.INFO)

    def alert_warning(self, message: str):
        """Envía alerta WARNING"""
        self.send_alert(message, AlertLevel.WARNING)

    def alert_critical(self, message: str):
        """Envía alerta CRITICAL"""
        self.send_alert(message, AlertLevel.CRITICAL)

    # Helpers para eventos comunes

    def alert_position_opened(self, symbol: str, side: str, quantity: float, price: float):
        """Alerta de posición abierta"""
        message = (
            f"📈 Position Opened\n"
            f"Symbol: {symbol}\n"
            f"Side: {side}\n"
            f"Quantity: {quantity}\n"
            f"Price: ${price:.2f}"
        )
        self.alert_info(message)

    def alert_position_closed(
        self,
        symbol: str,
        pnl_usdt: float,
        pnl_pct: float,
        reason: str
    ):
        """Alerta de posición cerrada"""
        emoji = "✅" if pnl_usdt > 0 else "❌"
        level = AlertLevel.INFO if pnl_usdt > 0 else AlertLevel.WARNING

        message = (
            f"{emoji} Position Closed\n"
            f"Symbol: {symbol}\n"
            f"PnL: ${pnl_usdt:.2f} ({pnl_pct:+.2f}%)\n"
            f"Reason: {reason}"
        )

        self.send_alert(message, level)

    def alert_circuit_breaker(self, state: str, reason: str):
        """Alerta de circuit breaker activado"""
        message = (
            f"🚨 CIRCUIT BREAKER ACTIVATED\n"
            f"State: {state}\n"
            f"Reason: {reason}\n"
            f"Trading paused!"
        )
        self.alert_critical(message)

    def alert_error(self, error_type: str, details: str):
        """Alerta de error crítico"""
        message = (
            f"⚠️ Critical Error\n"
            f"Type: {error_type}\n"
            f"Details: {details}"
        )
        self.alert_critical(message)

    def get_status(self) -> Dict[str, bool]:
        """Retorna estado de canales"""
        return {
            'telegram': self.telegram.enabled if self.telegram else False,
            'discord': self.discord.enabled if self.discord else False,
            'email': self.email.enabled if self.email else False,
            'num_callbacks': len(self.callbacks)
        }
