"""Configuration centralisee du trading bot."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Parametres charges depuis .env avec fallbacks."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    deepseek_api_key: str = ""
    mt5_login: int = 0
    mt5_password: str = ""
    mt5_server: str = "FusionMarkets-Demo"
    mt5_magic_number: int = 123456
    trading_symbol: str = "EURUSD"
    trading_timeframe: str = "M15"
    max_risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 3.0
    max_open_positions: int = 1
    min_confidence_threshold: int = 70
    analysis_interval_minutes: int = 15
    database_path: str = "data/trading.db"
    log_level: str = "INFO"
    log_file: str = "logs/trading-bot.log"

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parent.parent

    @property
    def _symbol_dir(self) -> str:
        """Sous-dossier par symbole pour isoler les instances paralleles."""
        return self.trading_symbol.lower()

    @property
    def db_path(self) -> Path:
        p = Path(self.database_path)
        if not p.is_absolute():
            p = self.project_root / "data" / self._symbol_dir / "trading.db"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def log_path(self) -> Path:
        p = Path(self.log_file)
        if not p.is_absolute():
            p = self.project_root / "logs" / self._symbol_dir / "trading-bot.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def screenshots_dir(self) -> Path:
        p = self.project_root / "data" / self._symbol_dir / "screenshots"
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
