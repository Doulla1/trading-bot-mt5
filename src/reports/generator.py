"""Generateur de rapport quotidien: statistiques, HTML, consolidation multi-symboles.

Interroge toutes les bases de donnees par symbole pour produire un rapport
complet de la journee de trading.
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from loguru import logger

from src.config import settings


def _discover_symbol_dbs() -> list[tuple[str, Path]]:
    """Decouvre toutes les bases de donnees par symbole dans data/.

    Returns:
        Liste de tuples (symbol, db_path).
    """
    data_dir = settings.project_root / "data"
    if not data_dir.exists():
        return []

    dbs = []
    for folder in sorted(data_dir.iterdir()):
        if folder.is_dir() and not folder.name.startswith("."):
            db_path = folder / "trading.db"
            if db_path.exists():
                dbs.append((folder.name.upper(), db_path))
    return dbs


def generate_daily_report(date: datetime | None = None) -> dict:
    """Genere un rapport quotidien complet.

    Args:
        date: Date du rapport (defaut: aujourd'hui UTC).

    Returns:
        Dictionnaire avec:
          - stats: dict de stats globales
          - trades: liste de tous les trades du jour
          - symbols: dict par symbole avec stats+trades
          - html: str du rapport HTML complet
          - has_trades: bool
    """
    if date is None:
        date = datetime.now(timezone.utc)

    date_str = date.strftime("%Y-%m-%d")
    date_display = date.strftime("%d/%m/%Y")

    symbol_dbs = _discover_symbol_dbs()
    logger.info(f"Generation rapport pour {date_str} | {len(symbol_dbs)} symbole(s) trouve(s)")

    all_trades: list[dict] = []
    symbols_data: dict = {}

    for sym, db_path in symbol_dbs:
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row

            # Trades ouverts aujourd'hui (peu importe leur statut)
            rows = conn.execute(
                "SELECT * FROM trades WHERE date(opened_at) = ? ORDER BY opened_at ASC",
                [date_str],
            ).fetchall()

            # Nombre d'analyses aujourd'hui (pour contexte)
            analysis_count = conn.execute(
                "SELECT COUNT(*) FROM analysis_logs WHERE date(timestamp) = ? AND symbol = ?",
                [date_str, sym],
            ).fetchone()[0]

            trades = [dict(r) for r in rows]
            stats = _compute_symbol_stats(trades)
            stats["analysis_count"] = analysis_count
            symbols_data[sym] = {"stats": stats, "trades": trades}
            all_trades.extend(trades)

            if rows:
                logger.info(f"  {sym}: {len(trades)} trade(s) | P&L: {stats['total_profit']:+.2f}")
            elif analysis_count > 0:
                logger.info(f"  {sym}: 0 trade | {analysis_count} analyse(s)")

            conn.close()
        except Exception as e:
            logger.warning(f"Erreur lecture DB {sym}: {e}")

    global_stats = _compute_global_stats(all_trades, symbols_data)
    html = _render_html(date_display, global_stats, symbols_data, all_trades)

    return {
        "stats": global_stats,
        "trades": all_trades,
        "symbols": symbols_data,
        "html": html,
        "has_trades": len(all_trades) > 0,
    }


def _compute_symbol_stats(trades: list[dict]) -> dict:
    """Calcule les statistiques pour un symbole."""
    closed = [t for t in trades if t.get("profit") is not None]
    profits = [t["profit"] for t in closed]
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p < 0]
    breakeven = [p for p in profits if p == 0]
    unreconciled = [t for t in closed if t.get("close_price", 1) == 0.0 and t.get("profit", 0) == 0.0]

    confidences = [t.get("confidence", 0) for t in trades if t.get("confidence")]

    durations = []
    for t in closed:
        if t.get("opened_at") and t.get("closed_at"):
            try:
                opened = datetime.fromisoformat(t["opened_at"])
                closed_at = datetime.fromisoformat(t["closed_at"])
                durations.append((closed_at - opened).total_seconds() / 60)
            except (ValueError, TypeError):
                pass

    return {
        "total_trades": len(trades),
        "closed": len(closed),
        "open": len(trades) - len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(breakeven),
        "unreconciled": len(unreconciled),
        "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else 0,
        "total_profit": round(sum(profits), 2),
        "best_trade": round(max(profits), 2) if profits else 0,
        "worst_trade": round(min(profits), 2) if profits else 0,
        "avg_profit": round(sum(profits) / len(profits), 2) if profits else 0,
        "avg_confidence": round(sum(confidences) / len(confidences), 1) if confidences else 0,
        "avg_duration_min": round(sum(durations) / len(durations), 1) if durations else 0,
    }


def _compute_global_stats(all_trades: list[dict], symbols_data: dict) -> dict:
    """Calcule les statistiques globales."""
    closed = [t for t in all_trades if t.get("profit") is not None]
    profits = [t["profit"] for t in closed]
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p < 0]
    breakeven = [p for p in profits if p == 0]
    unreconciled = [t for t in closed if t.get("close_price", 1) == 0.0 and t.get("profit", 0) == 0.0]

    confidences = [t.get("confidence", 0) for t in all_trades if t.get("confidence")]

    durations = []
    for t in closed:
        if t.get("opened_at") and t.get("closed_at"):
            try:
                opened = datetime.fromisoformat(t["opened_at"])
                closed_at = datetime.fromisoformat(t["closed_at"])
                durations.append((closed_at - opened).total_seconds() / 60)
            except (ValueError, TypeError):
                pass

    return {
        "total_trades": len(all_trades),
        "closed": len(closed),
        "open": len(all_trades) - len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(breakeven),
        "unreconciled": len(unreconciled),
        "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else 0,
        "total_profit": round(sum(profits), 2),
        "best_trade": round(max(profits), 2) if profits else 0,
        "worst_trade": round(min(profits), 2) if profits else 0,
        "avg_profit": round(sum(profits) / len(profits), 2) if profits else 0,
        "avg_confidence": round(sum(confidences) / len(confidences), 1) if confidences else 0,
        "avg_duration": f"{round(sum(durations) / len(durations), 1)} min" if durations else "N/A",
        "symbols_count": len(symbols_data),
    }


def _render_html(
    date_display: str,
    stats: dict,
    symbols_data: dict,
    _all_trades: list[dict] | None = None,
) -> str:
    """Genere le rapport HTML complet avec design responsive."""

    total = stats["total_trades"]
    pnl_color = "#22c55e" if stats["total_profit"] >= 0 else "#ef4444"
    pnl_sign = "+" if stats["total_profit"] >= 0 else ""

    # Section resume global - table layout pour compatibilite Gmail
    breakeven_count = stats.get("breakeven", 0)
    unreconciled_count = stats.get("unreconciled", 0)
    summary_html = f"""
    <div style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border-radius: 12px; padding: 20px 24px; margin-bottom: 24px; color: #e2e8f0;">
        <h2 style="margin: 0 0 14px 0; font-size: 20px; color: #f1f5f9;">Resume Global</h2>
        <table cellpadding="0" cellspacing="0" border="0" style="width:100%;">
            <tr>
                <td style="padding:6px 14px 6px 0; width:20%;"><span style="color:#94a3b8; font-size:12px; text-transform:uppercase;">Trades</span><br><span style="font-size:22px; font-weight:700; color:#f1f5f9;">{total}</span></td>
                <td style="padding:6px 14px; width:20%;"><span style="color:#94a3b8; font-size:12px; text-transform:uppercase;">Gagnants</span><br><span style="font-size:22px; font-weight:700; color:#22c55e;">{stats['wins']}</span></td>
                <td style="padding:6px 14px; width:20%;"><span style="color:#94a3b8; font-size:12px; text-transform:uppercase;">Perdants</span><br><span style="font-size:22px; font-weight:700; color:#ef4444;">{stats['losses']}</span></td>
                <td style="padding:6px 14px; width:20%;"><span style="color:#94a3b8; font-size:12px; text-transform:uppercase;">Win Rate</span><br><span style="font-size:22px; font-weight:700; color:#f1f5f9;">{stats['win_rate']}%</span></td>
                <td style="padding:6px 0 6px 14px; width:20%;"><span style="color:#94a3b8; font-size:12px; text-transform:uppercase;">P&amp;L Total</span><br><span style="font-size:22px; font-weight:700; color:{pnl_color};">{pnl_sign}{stats['total_profit']:.2f} $</span></td>
            </tr>"""

    if breakeven_count or unreconciled_count:
        summary_html += '<tr style="font-size:12px; color:#94a3b8;">'
        if breakeven_count:
            summary_html += f'<td style="padding:2px 14px 2px 0;">Breakeven: <b style="color:#94a3b8;">{breakeven_count}</b></td>'
        else:
            summary_html += '<td style="padding:2px 14px 2px 0;"></td>'
        if unreconciled_count:
            summary_html += f'<td style="padding:2px 14px;" colspan="2">Non reconcilies: <b style="color:#f59e0b;">{unreconciled_count}</b></td>'
        else:
            summary_html += '<td style="padding:2px 14px;" colspan="2"></td>'
        summary_html += '<td style="padding:2px 14px;" colspan="2"></td></tr>'

    summary_html += f"""</table>
        <div style="margin-top: 10px; font-size:13px; color:#94a3b8;">
            Meilleur: <span style="color:#22c55e;font-weight:600;">{stats['best_trade']:+.2f} $</span>
            &nbsp;&nbsp;Pire: <span style="color:#ef4444;font-weight:600;">{stats['worst_trade']:+.2f} $</span>
            &nbsp;&nbsp;Moyen: <span style="color:#f1f5f9;font-weight:600;">{stats['avg_profit']:+.2f} $</span>
            &nbsp;&nbsp;Duree moy: <span style="color:#f1f5f9;font-weight:600;">{stats['avg_duration']}</span>
            &nbsp;&nbsp;Confiance moy: <span style="color:#f1f5f9;font-weight:600;">{stats['avg_confidence']}%</span>
        </div>
    </div>"""

    # Section par symbole
    symbols_html = ""
    for sym, data in symbols_data.items():
        s = data["stats"]
        s_pnl_color = "#22c55e" if s["total_profit"] >= 0 else "#ef4444"
        s_pnl_sign = "+" if s["total_profit"] >= 0 else ""
        be_count = s.get("breakeven", 0)
        be_str = f'/<b style="color:#94a3b8;">{be_count}</b>' if be_count else ""

        trades_rows = ""
        for t in data["trades"]:
            t_pnl = t.get("profit")
            t_close = t.get("close_price", 1)
            if t_pnl is not None:
                # Unreconciled: close_price=0.0 et profit=0.0
                if t_close == 0.0 and t_pnl == 0.0:
                    t_pnl_color = "#f59e0b"
                    t_pnl_str = "N/R"
                elif t_pnl > 0:
                    t_pnl_color = "#22c55e"
                elif t_pnl < 0:
                    t_pnl_color = "#ef4444"
                else:
                    t_pnl_color = "#94a3b8"
                t_pnl_str = f"{t_pnl:+.2f} $"
            else:
                t_pnl_color = "#f59e0b"
                t_pnl_str = "En cours"

            opened = t.get("opened_at", "?")[:16] if t.get("opened_at") else "?"
            trades_rows += f"""
                <tr>
                    <td style="padding: 8px 12px; border-bottom: 1px solid #1e293b;">{opened}</td>
                    <td style="padding: 8px 12px; border-bottom: 1px solid #1e293b;">
                        <span style="color: {'#22c55e' if t.get('direction') == 'BUY' else '#ef4444'};">{t.get('direction', '?')}</span>
                    </td>
                    <td style="padding: 8px 12px; border-bottom: 1px solid #1e293b;">{t.get('volume', '?')}</td>
                    <td style="padding: 8px 12px; border-bottom: 1px solid #1e293b;">{t.get('open_price', '?')}</td>
                    <td style="padding: 8px 12px; border-bottom: 1px solid #1e293b; color: {t_pnl_color}; font-weight: 600;">{t_pnl_str}</td>
                </tr>"""

        symbols_html += f"""
        <div style="background: #0f172a; border-radius: 10px; padding: 20px; margin-bottom: 16px; border-left: 3px solid {'#22c55e' if s['total_profit'] >= 0 else '#ef4444'};">
            <h3 style="margin: 0 0 12px 0; font-size: 17px; color: #f1f5f9;">{sym}</h3>
            <div style="display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; font-size: 13px; color: #94a3b8;">
                <span>Trades: <b style="color: #e2e8f0;">{s['total_trades']}</b></span>
                <span>G/P: <b style="color: #22c55e;">{s['wins']}</b>/<b style="color: #ef4444;">{s['losses']}</b>{be_str}</span>
                <span>WR: <b style="color: #e2e8f0;">{s['win_rate']}%</b></span>
                <span>P&L: <b style="color: {s_pnl_color};">{s_pnl_sign}{s['total_profit']:.2f} $</b></span>
                <span>Moy: <b style="color: #e2e8f0;">{s['avg_profit']:+.2f} $</b></span>
                <span>Duree: <b style="color: #e2e8f0;">{s['avg_duration_min']} min</b></span>
            </div>
            <table style="width: 100%; border-collapse: collapse; font-size: 13px; color: #cbd5e1;">
                <thead>
                    <tr style="background: #1e293b;">
                        <th style="padding: 8px 12px; text-align: left; border-bottom: 2px solid #334155;">Ouverture</th>
                        <th style="padding: 8px 12px; text-align: left; border-bottom: 2px solid #334155;">Dir.</th>
                        <th style="padding: 8px 12px; text-align: left; border-bottom: 2px solid #334155;">Volume</th>
                        <th style="padding: 8px 12px; text-align: left; border-bottom: 2px solid #334155;">Prix</th>
                        <th style="padding: 8px 12px; text-align: left; border-bottom: 2px solid #334155;">P&L</th>
                    </tr>
                </thead>
                <tbody>{trades_rows}</tbody>
            </table>
        </div>"""

    # Template complet
    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Rapport Trading - {date_display}</title>
</head>
<body style="margin: 0; padding: 0; background: #020617; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
    <div style="max-width: 680px; margin: 0 auto; padding: 24px 16px;">

        <!-- En-tete -->
        <div style="text-align: center; margin-bottom: 28px;">
            <h1 style="margin: 0; font-size: 26px; font-weight: 800; color: #f1f5f9; letter-spacing: -0.5px;">
                Rapport de Trading
            </h1>
            <p style="margin: 6px 0 0 0; font-size: 14px; color: #64748b;">
                {date_display} | Genere automatiquement par Trading Bot MT5
            </p>
        </div>

        {summary_html}

        <!-- Section par symbole -->
        <h2 style="color: #e2e8f0; font-size: 18px; margin: 24px 0 12px 0;">Details par Paire</h2>
        {symbols_html if symbols_html else '<p style="color: #64748b; font-style: italic;">Aucun trade aujourd\'hui.</p>'}

        <!-- Placeholder pour l\'analyse DeepSeek (sera remplace) -->
        <div id="deepseek-analysis" style="background: #0f172a; border-radius: 10px; padding: 20px; margin-top: 24px; border: 1px solid #1e293b;">
            <h2 style="margin: 0 0 12px 0; font-size: 18px; color: #f1f5f9;">Analyse DeepSeek V4 Pro</h2>
            <p style="color: #64748b; font-style: italic;">##ANALYSIS_PLACEHOLDER##</p>
        </div>

        <!-- Pied de page -->
        <div style="text-align: center; margin-top: 32px; padding-top: 16px; border-top: 1px solid #1e293b;">
            <p style="font-size: 11px; color: #475569;">
                Trading Bot MT5 | Rapport automatique | {stats['symbols_count']} paire(s) surveillee(s)
            </p>
        </div>

    </div>
</body>
</html>"""

    return html


def get_symbols_detail_text(symbols_data: dict) -> str:
    """Genere un texte formaté avec les details par symbole pour le prompt DeepSeek."""
    lines = []
    for sym, data in symbols_data.items():
        s = data["stats"]
        lines.append(
            f"- {sym}: {s['total_trades']} trades, {s['wins']}W/{s['losses']}L "
            f"(WR: {s['win_rate']}%), P&L: {s['total_profit']:+.2f} $, "
            f"moy/trade: {s['avg_profit']:+.2f} $"
        )
    return "\n".join(lines) if lines else "Aucun trade aujourd'hui."
