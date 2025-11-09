"""
Config Loader
Sistema de configuración mejorado que lee desde variables de entorno

Mejoras sobre Config original:
- Lee todos los parámetros desde .env
- Soporta múltiples entornos (dev, staging, prod)
- Validación de configuración
- Valores por defecto seguros
"""

import os
import logging
from typing import Optional
from enum import Enum


class Environment(Enum):
    """Entornos de ejecución"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class ConfigLoader:
    """
    Cargador de configuración desde variables de entorno

    Uso:
        config = ConfigLoader.load()
        api_key = config.api_key
        symbol = config.symbol
    """

    def __init__(self):
        self.logger = logging.getLogger("ConfigLoader")

        # === Credenciales ===
        self.api_key: str = ""
        self.api_secret: str = ""

        # === Trading ===
        self.symbol: str = "BTCUSDT"
        self.timeframe: str = "5m"
        self.use_testnet: bool = True

        # === Perfiles de Riesgo ===
        self.risk_profile: str = "normal"  # conservador, normal, agresivo

        # === Sistema ===
        self.log_level: str = "INFO"
        self.data_dir: str = "data"
        self.logs_dir: str = "logs"

        # === Alertas (Telegram) ===
        self.telegram_bot_token: Optional[str] = None
        self.telegram_chat_id: Optional[str] = None

        # === Alertas (Discord) ===
        self.discord_webhook_url: Optional[str] = None

        # === Alertas (Email) ===
        self.email_smtp_host: Optional[str] = None
        self.email_smtp_port: int = 587
        self.email_from: Optional[str] = None
        self.email_to: Optional[str] = None
        self.email_password: Optional[str] = None

        # === Entorno ===
        self.environment: Environment = Environment.DEVELOPMENT

        # === Flags internos ===
        self.loaded: bool = False
        self.validated: bool = False

    @classmethod
    def load(cls, env_file: Optional[str] = None) -> 'ConfigLoader':
        """
        Carga configuración desde variables de entorno

        Args:
            env_file: Ruta al archivo .env (opcional)

        Returns:
            ConfigLoader con valores cargados
        """
        config = cls()

        # Intentar cargar .env si existe
        if env_file and os.path.exists(env_file):
            config._load_env_file(env_file)

        # Cargar desde variables de entorno
        config._load_from_env()

        config.loaded = True

        # Validar configuración
        config.validate()

        return config

    def _load_env_file(self, env_file: str):
        """Carga variables desde archivo .env"""
        try:
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()

                    # Ignorar comentarios y líneas vacías
                    if not line or line.startswith('#'):
                        continue

                    # Parsear KEY=VALUE
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()

                        # Remover comillas si existen
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        elif value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]

                        # Setear en entorno si no existe
                        if key not in os.environ:
                            os.environ[key] = value

            self.logger.info(f"Loaded configuration from {env_file}")

        except Exception as e:
            self.logger.warning(f"Could not load {env_file}: {e}")

    def _load_from_env(self):
        """Carga configuración desde variables de entorno"""

        # === Credenciales (OBLIGATORIAS) ===
        self.api_key = os.getenv("BINANCE_API_KEY", "")
        self.api_secret = os.getenv("BINANCE_SECRET_KEY", "")

        # === Trading ===
        self.symbol = os.getenv("SYMBOL", "BTCUSDT")
        self.timeframe = os.getenv("TIMEFRAME", "5m")
        self.use_testnet = self._parse_bool(os.getenv("USE_TESTNET", "True"))

        # === Perfil de Riesgo ===
        self.risk_profile = os.getenv("RISK_PROFILE", "normal").lower()
        if self.risk_profile not in ['conservador', 'normal', 'agresivo']:
            self.logger.warning(f"Invalid risk_profile '{self.risk_profile}', defaulting to 'normal'")
            self.risk_profile = "normal"

        # === Sistema ===
        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        self.data_dir = os.getenv("DATA_DIR", "data")
        self.logs_dir = os.getenv("LOGS_DIR", "logs")

        # === Alertas - Telegram ===
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

        # === Alertas - Discord ===
        self.discord_webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

        # === Alertas - Email ===
        self.email_smtp_host = os.getenv("EMAIL_SMTP_HOST")
        self.email_smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
        self.email_from = os.getenv("EMAIL_FROM")
        self.email_to = os.getenv("EMAIL_TO")
        self.email_password = os.getenv("EMAIL_PASSWORD")

        # === Entorno ===
        env_str = os.getenv("ENVIRONMENT", "development").lower()
        if env_str == "production":
            self.environment = Environment.PRODUCTION
        elif env_str == "staging":
            self.environment = Environment.STAGING
        else:
            self.environment = Environment.DEVELOPMENT

    def _parse_bool(self, value: str) -> bool:
        """Parsea string a booleano"""
        return value.lower() in ['true', '1', 'yes', 'on']

    def validate(self) -> bool:
        """
        Valida que la configuración sea correcta

        Returns:
            True si es válida

        Raises:
            ValueError si hay errores críticos
        """
        errors = []

        # Validar credenciales
        if not self.api_key:
            errors.append("BINANCE_API_KEY is required")

        if not self.api_secret:
            errors.append("BINANCE_SECRET_KEY is required")

        # Validar símbolo
        if not self.symbol or len(self.symbol) < 3:
            errors.append(f"Invalid SYMBOL: '{self.symbol}'")

        # Validar timeframe
        valid_timeframes = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d']
        if self.timeframe not in valid_timeframes:
            errors.append(f"Invalid TIMEFRAME: '{self.timeframe}' (valid: {valid_timeframes})")

        # Warnings (no críticos)
        if not self.telegram_bot_token and not self.discord_webhook_url and not self.email_smtp_host:
            self.logger.warning("⚠️  No alert channels configured (Telegram, Discord, Email)")

        if self.environment == Environment.PRODUCTION and self.use_testnet:
            self.logger.warning("⚠️  PRODUCTION environment with USE_TESTNET=True (unusual)")

        # Si hay errores críticos, fallar
        if errors:
            error_msg = "\n".join(f"  - {e}" for e in errors)
            raise ValueError(f"Configuration validation failed:\n{error_msg}")

        self.validated = True
        self.logger.info("✓ Configuration validated successfully")

        return True

    def get_summary(self) -> str:
        """Retorna resumen de configuración (sin secrets)"""
        lines = []
        lines.append("=" * 60)
        lines.append("CONFIGURATION SUMMARY")
        lines.append("=" * 60)

        lines.append(f"\n🔧 Environment: {self.environment.value}")
        lines.append(f"📊 Trading:")
        lines.append(f"   Symbol: {self.symbol}")
        lines.append(f"   Timeframe: {self.timeframe}")
        lines.append(f"   Testnet: {self.use_testnet}")
        lines.append(f"   Risk Profile: {self.risk_profile}")

        lines.append(f"\n📁 Directories:")
        lines.append(f"   Data: {self.data_dir}")
        lines.append(f"   Logs: {self.logs_dir}")

        lines.append(f"\n🔔 Alerts:")
        lines.append(f"   Telegram: {'✓ Configured' if self.telegram_bot_token else '✗ Not configured'}")
        lines.append(f"   Discord: {'✓ Configured' if self.discord_webhook_url else '✗ Not configured'}")
        lines.append(f"   Email: {'✓ Configured' if self.email_smtp_host else '✗ Not configured'}")

        lines.append(f"\n🔐 Credentials:")
        lines.append(f"   API Key: {'✓ Set' if self.api_key else '✗ Missing'}")
        lines.append(f"   API Secret: {'✓ Set' if self.api_secret else '✗ Missing'}")

        lines.append("\n" + "=" * 60)

        return "\n".join(lines)

    def to_legacy_config_dict(self) -> dict:
        """
        Convierte a diccionario compatible con Config legacy

        Returns:
            Dict con valores para Config de binance_bot_2.py
        """
        return {
            'API_KEY': self.api_key,
            'SECRET_KEY': self.api_secret,
            'SYMBOL': self.symbol,
            'TIMEFRAME': self.timeframe,
            'USE_TESTNET': self.use_testnet,
            'RISK_PROFILE': self.risk_profile,
            'LOG_LEVEL': self.log_level,
            'LOG_DIR': self.logs_dir,
            'DATA_DIR': self.data_dir
        }


# Función helper para cargar configuración
def load_config(env_file: Optional[str] = ".env") -> ConfigLoader:
    """
    Carga configuración de manera simple

    Args:
        env_file: Ruta al archivo .env

    Returns:
        ConfigLoader con valores cargados y validados

    Example:
        config = load_config()
        print(config.get_summary())
    """
    # Si no existe .env, intentar cargar solo desde entorno
    if not os.path.exists(env_file):
        env_file = None

    return ConfigLoader.load(env_file)


# Clase singleton para acceso global
class Config:
    """
    Singleton de configuración

    Uso:
        from config_loader import Config
        print(Config.SYMBOL)
    """
    _instance: Optional[ConfigLoader] = None

    @classmethod
    def load(cls, env_file: str = ".env") -> ConfigLoader:
        """Carga y cachea configuración"""
        if cls._instance is None:
            cls._instance = load_config(env_file)
        return cls._instance

    @classmethod
    def get(cls) -> ConfigLoader:
        """Obtiene configuración cacheada"""
        if cls._instance is None:
            cls._instance = load_config()
        return cls._instance

    # Propiedades de acceso directo (compatibilidad con código legacy)
    @classmethod
    @property
    def API_KEY(cls) -> str:
        return cls.get().api_key

    @classmethod
    @property
    def SECRET_KEY(cls) -> str:
        return cls.get().api_secret

    @classmethod
    @property
    def SYMBOL(cls) -> str:
        return cls.get().symbol

    @classmethod
    @property
    def TIMEFRAME(cls) -> str:
        return cls.get().timeframe

    @classmethod
    @property
    def USE_TESTNET(cls) -> bool:
        return cls.get().use_testnet


if __name__ == "__main__":
    # Test de carga de configuración
    logging.basicConfig(level=logging.INFO)

    print("\n" + "=" * 60)
    print("CONFIG LOADER TEST")
    print("=" * 60)

    try:
        config = load_config()
        print(config.get_summary())

        print("\n✅ Configuration loaded successfully!")

    except ValueError as e:
        print(f"\n❌ Configuration error:\n{e}")

    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
