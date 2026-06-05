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

    # --- Configuration IA (v4.0: multi-provider) ---
    # Cle API principale pour les decisions de trading
    ai_api_key: str = ""
    # Modele utilise pour la decision principale
    ai_model: str = "deepseek-v4-pro"
    # Modele utilise pour les cycles de confirmation (plus rapide/leger)
    ai_fast_model: str = "deepseek-v4-flash"
    # URL de base de l'API (change selon le fournisseur)
    ai_base_url: str = "https://api.deepseek.com/v1"
    # Nom du fournisseur (cosmetique, pour les logs)
    ai_provider: str = "deepseek"
    # --- Retrocompatibilite (deprecated, migrer vers ai_api_key) ---
    openai_api_key: str = ""
    deepseek_api_key: str = ""
    # Activer ou non la generation d'images et l'OCR via Vision
    # DESACTIVE PAR DEFAUT CAR: 
    # 1. Les Points Pivots mathematiques (S1, S2, R1...) sont plus precis que la lecture visuelle (sans hallucinations).
    # 2. Gain enorme en vitesse d'execution (2s au lieu de 15s).
    # 3. Evite les conflits entre l'ADX mathematique et l'estimation visuelle de la tendance par l'IA.
    use_vision_ocr: bool = False
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

    # Rapport journalier par email
    mailer_api_secret: str = ""
    mailer_api_url: str = "https://mailing.weltaare-tech.com/api/v1/emails"
    report_recipient_email: str = "dialloabdoul99c@gmail.com"
    report_recipient_name: str = ""
    report_sender_name: str = "Trading Bot MT5"
    report_send_hour_utc: int = 23
    report_send_minute_utc: int = 0

    @property
    def ai_api_key_resolved(self) -> str:
        """Resout la cle API : ai_api_key d'abord, puis fallback deepseek_api_key (retrocompatibilite)."""
        return self.ai_api_key or self.deepseek_api_key

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
