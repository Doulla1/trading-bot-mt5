"""Module de rapports journaliers: generation, analyse DeepSeek, envoi email."""

from src.reports.mailer import send_email
from src.reports.generator import generate_daily_report
from src.reports.analyzer import analyze_daily_results
from src.reports.daily_report import send_daily_report

__all__ = ["send_email", "generate_daily_report", "analyze_daily_results", "send_daily_report"]
