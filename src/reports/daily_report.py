"""Orchestrateur du rapport journalier: generation + analyse + envoi email.

Point d'entree principal pour la generation et l'envoi du rapport quotidien.
Appele par le scheduler a 23h UTC et par le script standalone send_report.py.
"""

from datetime import datetime, timezone
from loguru import logger

from src.config import settings
from src.reports.mailer import send_email
from src.reports.generator import generate_daily_report, get_symbols_detail_text
from src.reports.analyzer import analyze_daily_results


def send_daily_report(date: datetime | None = None) -> bool:
    """Genere et envoie le rapport journalier complet par email.

    Args:
        date: Date du rapport (defaut: aujourd'hui UTC).

    Returns:
        True si l'email a ete envoye avec succes.
    """
    if date is None:
        date = datetime.now(timezone.utc)

    date_display = date.strftime("%d/%m/%Y")
    logger.info(f"=== GENERATION RAPPORT JOURNALIER {date_display} ===")

    # 1. Generer le rapport
    report = generate_daily_report(date)
    stats = report["stats"]
    trades = report["trades"]
    symbols_data = report["symbols"]
    html = report["html"]

    # 2. Analyse DeepSeek V4 Pro
    symbols_detail = get_symbols_detail_text(symbols_data)
    analysis_text = analyze_daily_results(stats, trades, symbols_detail)

    # 3. Formater l'analyse en HTML (paragraphes, gras, etc.)
    analysis_html = _format_analysis_html(analysis_text)
    html = html.replace("##ANALYSIS_PLACEHOLDER##", analysis_html)

    # 4. Sujet de l'email
    pnl_sign = "+" if stats["total_profit"] >= 0 else ""
    subject = (
        f"Rapport Trading {date_display} | "
        f"{stats['total_trades']} trades | "
        f"P&L: {pnl_sign}{stats['total_profit']:.2f} $ | "
        f"WR: {stats['win_rate']}%"
    )

    # 5. Envoyer
    recipient = settings.report_recipient_email
    if not recipient:
        logger.error("Aucun destinataire configure pour le rapport")
        return False

    success = send_email(
        recipient_email=recipient,
        subject=subject,
        body_html=html,
        recipient_name=settings.report_recipient_name or "",
    )

    if success:
        logger.info(f"Rapport journalier envoye a {recipient}")
    else:
        logger.error(f"Echec de l'envoi du rapport a {recipient}")

    return success


def _format_analysis_html(text: str) -> str:
    """Convertit le texte d'analyse en HTML avec mise en forme."""
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    close_ul = "</ul>"

    html_lines: list[str] = []
    in_list = False

    def _close_list():
        nonlocal in_list
        if in_list:
            html_lines.append(close_ul)
            in_list = False

    for line in escaped.split("\n"):
        stripped = line.strip()
        if not stripped:
            _close_list()
            html_lines.append("<br>")
            continue

        # Titres de section (markdown: **Texte**)
        if stripped.startswith("**") and stripped.endswith("**"):
            _close_list()
            title = stripped.strip("*")
            html_lines.append(
                f'<h3 style="color: #f1f5f9; font-size: 15px; margin: 16px 0 8px 0;">{title}</h3>'
            )
        elif stripped.startswith(("- ", "* ")):
            if not in_list:
                html_lines.append(
                    '<ul style="margin: 4px 0; padding-left: 20px; color: #cbd5e1;">'
                )
                in_list = True
            item = _bold_format(stripped[2:])
            html_lines.append(f"<li>{item}</li>")
        else:
            _close_list()
            formatted = _bold_format(stripped)
            html_lines.append(
                f'<p style="color: #cbd5e1; font-size: 14px; line-height: 1.6; margin: 4px 0;">{formatted}</p>'
            )

    _close_list()
    return "\n".join(html_lines)


def _bold_format(text: str) -> str:
    """Convertit **texte** en <strong>texte</strong>."""
    import re
    return re.sub(r"\*\*(.+?)\*\*", r"<strong style='color: #f1f5f9;'>\1</strong>", text)
