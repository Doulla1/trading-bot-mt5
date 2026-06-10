"""Moteur de strategie : combine IA, indicateurs et gestion des risques.

v4.0: SL/TP bases sur l'ATR, TIME EXIT corrige (20-bar break),
      cooldown post TIME EXIT, configuration par symbole."""

import MetaTrader5 as mt5
from loguru import logger
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone

from src.config import settings
from src.mt5.bridge import get_account_info, get_symbol_info, is_market_open
from src.mt5.executor import (
    open_position, close_position, calculate_position_size,
    get_open_positions, count_open_positions, TradeResult,
)
from src.data.database import get_db, log_trade_close
from src.ai.prompts import SL_LIMITS_CONFIG

# ============================================================
# Configuration SL/TP par symbole basee sur l'ATR (v4.0)
# atr_mult : multiplicateur de l'ATR (en pips) pour le SL
# min_sl   : SL minimum absolu en pips
# min_tp   : TP minimum absolu en pips
# tp_ratio : ratio TP/SL (TP = SL * tp_ratio)
# ============================================================
_ATR_SL_CONFIG: dict[str, dict] = {
    "XAUUSD": {"atr_mult": 0.5, "min_sl": 150, "min_tp": 300, "tp_ratio": 2.0},
    "EURUSD": {"atr_mult": 1.5, "min_sl": 15,  "min_tp": 30,  "tp_ratio": 2.0},
    "GBPUSD": {"atr_mult": 1.8, "min_sl": 25,  "min_tp": 50,  "tp_ratio": 2.0},
    "AUDUSD": {"atr_mult": 1.5, "min_sl": 15,  "min_tp": 30,  "tp_ratio": 2.0},
    "USDJPY": {"atr_mult": 1.8, "min_sl": 30,  "min_tp": 60,  "tp_ratio": 2.0},
    "USDCHF": {"atr_mult": 1.5, "min_sl": 15,  "min_tp": 30,  "tp_ratio": 2.0},
    "EURGBP": {"atr_mult": 1.5, "min_sl": 15,  "min_tp": 30,  "tp_ratio": 2.0},
    "EURJPY": {"atr_mult": 1.8, "min_sl": 25,  "min_tp": 50,  "tp_ratio": 2.0},
    "GBPJPY": {"atr_mult": 2.0, "min_sl": 35,  "min_tp": 70,  "tp_ratio": 2.0},
}

# Duree du cooldown apres un TIME EXIT (en minutes)
_COOLDOWN_MINUTES: int = 30

# v4.1: Symboles temporairement desactives (pertes recurrentes, modele inadapte)
_DISABLED_SYMBOLS: set[str] = set()

# v4.1: Seuil ADX anti-range et nombre de periodes consecutives
_RANGING_ADX_THRESHOLD: float = 25.0
_RANGING_CONSECUTIVE_BARS: int = 3
# Stocke les derniers ADX par symbole pour detecter le range
_ranging_state: dict[str, int] = {}  # sym -> compteur de periodes ADX < seuil


def _atr_to_pips(atr_value: float, point: float) -> float:
    """Convertit la valeur ATR brute (unites de prix) en pips.

    Ex: EURUSD ATR=0.00105, point=0.00001 -> 10.5 pips
        XAUUSD ATR=45.0, point=0.01 -> 450 pips"""
    if atr_value is None or point == 0:
        return 0.0
    return atr_value / (10.0 * point)


def _get_atr_based_sl_tp(symbol: str, indicators: dict, deepseek_sl: int, deepseek_tp: int) -> tuple[int, int]:
    """Calcule le SL et TP bases sur l'ATR, en respectant les minimums par symbole.

    Retourne (sl_pips, tp_pips).
    Si le TP propose par DeepSeek respecte le ratio de securite de 1.5 * SL,
    on le conserve pour respecter les obstacles techniques (ex: Pivot R3/S3),
    plutot que de forcer le ratio cible rigide de 2.0."""
    cfg = _ATR_SL_CONFIG.get(symbol, _ATR_SL_CONFIG["EURUSD"])
    atr_value = indicators.get("atr_14") if indicators else None
    sym_info = mt5.symbol_info(symbol)
    point = sym_info.point if sym_info else 0.00001

    atr_pips = _atr_to_pips(atr_value, point) if atr_value else 0.0
    atr_based_sl = max(cfg["min_sl"], int(atr_pips * cfg["atr_mult"])) if atr_pips > 0 else cfg["min_sl"]

    # SL final: le plus large entre DeepSeek et ATR
    sl_final = max(deepseek_sl, atr_based_sl)

    # TP final:
    # 1) Calculer le TP minimum absolu base sur le ratio de securite minimum (1.5R)
    min_tp_absolute = int(sl_final * 1.5)

    # 2) Si le TP de DeepSeek est >= 1.5R, on le conserve pour preserver les niveaux techniques,
    # sinon on applique le ratio cible de la config (ex: 2.0) ou au moins le min_tp.
    if deepseek_tp >= min_tp_absolute:
        tp_final = deepseek_tp
    else:
        tp_target = max(cfg["min_tp"], int(sl_final * cfg["tp_ratio"]))
        tp_final = max(deepseek_tp, tp_target)

    if sl_final != deepseek_sl or tp_final != deepseek_tp:
        logger.info(
            f"SL/TP limites ATR pour {symbol}: DeepSeek SL={deepseek_sl}/TP={deepseek_tp} -> "
            f"ATR SL={sl_final}/TP={tp_final} (ATR={atr_pips:.0f} pips, min_sl={cfg['min_sl']})"
        )

    return sl_final, tp_final


def _set_cooldown_after_exit(symbol: str, direction: str) -> None:
    """Active un cooldown de _COOLDOWN_MINUTES minutes apres un TIME EXIT.
    Empeche de re-entrer dans la meme direction trop rapidement."""
    try:
        db = get_db()
        from datetime import datetime, timedelta
        until = (datetime.now() + timedelta(minutes=_COOLDOWN_MINUTES)).isoformat()
        key = f"cooldown_{symbol}_{direction}"
        db.execute("INSERT OR REPLACE INTO bot_state (key, value) VALUES (?, ?)", [key, until])
        db.commit()
        logger.info(f"COOLDOWN actif pour {symbol} {direction} jusqu'a {until[:16]}")
    except Exception:
        pass


def _is_cooldown_active(symbol: str, direction: str) -> bool:
    """Verifie si un cooldown est actif pour ce symbole et cette direction."""
    try:
        db = get_db()
        key = f"cooldown_{symbol}_{direction}"
        row = db.execute("SELECT value FROM bot_state WHERE key = ?", [key]).fetchone()
        if row is None:
            return False
        from datetime import datetime
        until = datetime.fromisoformat(row[0])
        return datetime.now() < until
    except Exception:
        return False


@dataclass
class StrategyResult:
    """Resultat d'un cycle de strategie."""
    decision: dict | None
    trade_result: Optional[TradeResult] = None
    closed_positions: list = field(default_factory=list)


def execute_decision(decision: dict) -> StrategyResult:
    """Execute la decision de l'IA avec les regles de risk management.

    v4.1: Applique le Hard SL Floor (le SL ne peut JAMAIS etre < min_sl du symbole)
    et le filtre anti-range (ADX < 25 pendant 3+ periodes bloque BUY/SELL)."""
    result = StrategyResult(decision=decision)
    action = decision["action"]

    guard_result = _check_pre_trade_guards(action)
    if guard_result is not None:
        return guard_result

    account = get_account_info()
    symbol_info = get_symbol_info()
    balance = account.get("balance", 0)

    # CLOSE
    if action == "CLOSE":
        for pos in get_open_positions():
            close_res = close_position(pos["ticket"])
            result.closed_positions.append(close_res)
        return result

    # BUY / SELL
    if action in ("BUY", "SELL"):
        sym = settings.trading_symbol
        open_positions = get_open_positions(sym)

        # Si position deja ouverte dans la direction opposee
        if open_positions:
            existing_pos = open_positions[0]
            existing_dir = "BUY" if existing_pos.get("type") == mt5.POSITION_TYPE_BUY else "SELL"
            if existing_dir != action:
                # Signaux opposes: fermer la position, NE PAS inverser immediatement
                # Le prochain cycle decidera si une nouvelle position est justifiee
                logger.info(f"Fermeture {existing_dir} (signaux opposes), pas de reversal immediat")
                close_res = close_position(existing_pos["ticket"])
                result.closed_positions.append(close_res)
                # On ne logue plus la fermeture ici (evite la race condition avec MT5 history)
                # La boucle _reconcile_closed_positions se chargera de recuperer le vrai profit.
                return result
            else:
                # Meme direction: on garde la position, le trailing/breakeven s'en occupe
                logger.info(f"Deja {existing_dir} - position conservee, gestion active en cours")
                return result

        # Aucune position: filtrer et ouvrir si OK
        if not _passes_trade_filters(decision, symbol_info):
            return result

        # v4.1: Ajuster SL/TP selon l'ATR du symbole + HARD FLOOR
        indicators = decision.get("indicators", {})
        raw_sl = decision["stop_loss_pips"]
        raw_tp = decision["take_profit_pips"]
        stop_loss_pips, take_profit_pips = _get_atr_based_sl_tp(
            sym, indicators, raw_sl, raw_tp
        )
        # v4.1: HARD FLOOR - l'IA ne peut JAMAIS reduire le SL en dessous du minimum config
        cfg_floor = _ATR_SL_CONFIG.get(sym, _ATR_SL_CONFIG["EURUSD"])
        if stop_loss_pips < cfg_floor["min_sl"]:
            logger.warning(
                f"SL HARD FLOOR pour {sym}: {stop_loss_pips} -> {cfg_floor['min_sl']} pips "
                f"(IA={raw_sl}, ATR ajuste insuffisant)"
            )
            stop_loss_pips = cfg_floor["min_sl"]
            take_profit_pips = max(take_profit_pips, cfg_floor["min_tp"], int(stop_loss_pips * cfg_floor["tp_ratio"]))
        # --- Python Guardrails: Structural SL/TP validation & adjustment ---
        point = symbol_info.get("point", 0.00001)
        digits = symbol_info.get("digits", 5)

        tick = mt5.symbol_info_tick(sym)
        if tick is None:
            logger.error(f"Tick introuvable pour {sym}")
            return result

        if action == "BUY":
            entry = tick.ask
        else:
            entry = tick.bid

        required_sl_pips = stop_loss_pips
        structure = indicators.get("market_structure", {})

        if action == "BUY":
            swing_low = structure.get("last_swing_low")
            if swing_low and isinstance(swing_low, (int, float)) and swing_low > 0:
                dist_pips = (entry - swing_low) / (10 * point) + 2
                if dist_pips > required_sl_pips:
                    required_sl_pips = int(dist_pips)
                    logger.info(f"[{sym}] Ajustement structurel SL (BUY): swing low a {swing_low}, SL pips requis: {required_sl_pips}")
        elif action == "SELL":
            swing_high = structure.get("last_swing_high")
            if swing_high and isinstance(swing_high, (int, float)) and swing_high > 0:
                dist_pips = (swing_high - entry) / (10 * point) + 2
                if dist_pips > required_sl_pips:
                    required_sl_pips = int(dist_pips)
                    logger.info(f"[{sym}] Ajustement structurel SL (SELL): swing high a {swing_high}, SL pips requis: {required_sl_pips}")

        # Validation par rapport au SL maximum autorise
        sl_limits = SL_LIMITS_CONFIG.get(sym, {"min": 15, "max": 50})
        max_allowed_sl = sl_limits.get("max", 50)

        if required_sl_pips > max_allowed_sl:
            logger.warning(
                f"[{sym}] Le SL structurel requis ({required_sl_pips} pips) depasse la limite maximale autorisee "
                f"({max_allowed_sl} pips) pour ce symbole. Trade annule pour preserver le ratio de risque."
            )
            return result

        if required_sl_pips != stop_loss_pips:
            stop_loss_pips = required_sl_pips
            # Pour l'ajustement du SL structurel, on impose le ratio de securite minimum de 1.5R 
            # plutot que le ratio cible de 2.0 de la config afin de laisser le TP le plus proche et atteignable possible.
            min_tp = int(stop_loss_pips * 1.5)
            if take_profit_pips < min_tp:
                logger.info(f"[{sym}] Ajustement TP a {min_tp} pips pour maintenir le ratio minimum de 1.5 (SL={stop_loss_pips})")
                take_profit_pips = min_tp

        volume = calculate_position_size(balance, stop_loss_pips, symbol_info)

        if action == "BUY":
            sl_price = round(entry - (stop_loss_pips * 10 * point), digits)
            tp_price = round(entry + (take_profit_pips * 10 * point), digits)
        else:
            sl_price = round(entry + (stop_loss_pips * 10 * point), digits)
            tp_price = round(entry - (take_profit_pips * 10 * point), digits)

        trade_result = open_position(
            direction=action, volume=volume, stop_loss=sl_price,
            take_profit=tp_price, comment=f"IA confiance={decision['confidence']}%",
        )
        result.trade_result = trade_result
        return result

    logger.info(f"Decision: HOLD (confiance {decision['confidence']}%)")
    return result


def _check_pre_trade_guards(_action: str) -> StrategyResult | None:
    """Verifie les gardes pre-trade: marche ouvert, perte jour, compte, symbole."""
    result = StrategyResult(decision=None)
    if not is_market_open():
        logger.info("Marche ferme - aucune execution")
        return result
    if get_account_info() is None:
        logger.error("Impossible de recuperer les infos du compte")
        return result
    if get_symbol_info() is None:
        logger.error("Impossible de recuperer les infos du symbole")
        return result
    # Daily loss limit
    account = get_account_info()
    balance = account.get("balance", 0)
    daily_pnl = _get_daily_pnl()
    if balance > 0 and daily_pnl < 0 and abs(daily_pnl) / balance * 100 >= settings.max_daily_loss_pct:
        logger.warning(f"LIMITE PERTE JOURNALIERE ATTEINTE: {abs(daily_pnl)/balance*100:.1f}%")
        return result
    return None


def _passes_trade_filters(decision: dict, symbol_info: dict) -> bool:
    """Applique les filtres pre-trade: confiance, max positions, spread, circuit breaker, RSI/BB.

    v4.1: Ajoute le filtre symboles desactives (_DISABLED_SYMBOLS) et anti-range (_is_ranging_market)."""
    # v4.2: Filtre week-end - pas de nouvelle position de vendredi 20h30 UTC à lundi 00h00 UTC
    if is_weekend_closure(datetime.now(timezone.utc)):
        logger.info(f"Filtre week-end actif : aucun nouveau trade autorisé pour {settings.trading_symbol}")
        return False

    confidence = decision["confidence"]
    if confidence < settings.min_confidence_threshold:
        logger.info(f"Confiance {confidence}% < seuil {settings.min_confidence_threshold}%")
        return False
    # v4.1: Symboles desactives
    if settings.trading_symbol in _DISABLED_SYMBOLS:
        logger.info(f"Symbole {settings.trading_symbol} temporairement desactive - pas d'execution")
        return False
    if count_open_positions() >= settings.max_open_positions:
        logger.info("Max positions atteint - pas d'execution")
        return False
    spread = symbol_info.get("spread", 999)
    if spread > 30:
        logger.warning(f"Spread trop eleve: {spread} points > 30 max")
        return False
    # v4.0: Verifier le cooldown post TIME EXIT
    action = decision.get("action", "")
    if action in ("BUY", "SELL") and _is_cooldown_active(settings.trading_symbol, action):
        logger.info(f"Cooldown actif pour {settings.trading_symbol} {action} - pas d'execution")
        return False
    # v4.1: Filtre anti-range - HOLD si ADX < 25 depuis 3+ periodes (evite de trader dans un range)
    if action in ("BUY", "SELL") and _is_ranging_market(decision):
        logger.info(f"Marche en range (ADX bas) - pas d'execution pour {settings.trading_symbol}")
        return False
    if _circuit_breaker_active():
        logger.info("Circuit breaker actif - pas d'execution")
        return False
    consecutive_losses = _count_consecutive_losses()
    if consecutive_losses >= 4:
        logger.warning(f"CIRCUIT BREAKER: {consecutive_losses} pertes consecutives - pause 4h")
        _set_circuit_breaker_until(hours=4)
        return False
    # v3.0: Filtres RSI/BB conditionnes au regime de marche
    # En tendance forte (ADX > 25), le RSI peut rester surachete/survendu pendant des heures
    # et le prix surfe sur les bandes de Bollinger. On ne bloque PAS ces entrees.
    # En ranging (ADX <= 25), on applique les filtres mean-reversion.
    indicators = decision.get("indicators", {})
    rsi = indicators.get("rsi_14", 50) if indicators else 50
    bb_pos = indicators.get("bb_position_pct", 50) if indicators else 50
    action = decision.get("action", "")
    adx = indicators.get("adx_14", 20) if indicators else 20
    if adx is not None and adx <= 25:
        if action == "BUY" and rsi > 75:
            logger.info(f"Filtre RSI/BB (ranging): BUY bloque (RSI={rsi:.1f} > 75, ADX={adx:.1f})")
            return False
        if action == "SELL" and rsi < 25:
            logger.info(f"Filtre RSI/BB (ranging): SELL bloque (RSI={rsi:.1f} < 25, ADX={adx:.1f})")
            return False
        if action == "BUY" and isinstance(bb_pos, (int, float)) and bb_pos > 100:
            logger.info(f"Filtre RSI/BB (ranging): BUY bloque (BB_position={bb_pos:.0f}%, ADX={adx:.1f})")
            return False
        if action == "SELL" and isinstance(bb_pos, (int, float)) and bb_pos < 0:
            logger.info(f"Filtre RSI/BB (ranging): SELL bloque (BB_position={bb_pos:.0f}%, ADX={adx:.1f})")
            return False
    elif adx is not None and adx > 25:
        logger.debug(f"Filtres RSI/BB desactives: ADX={adx:.1f} > 25 (marche en tendance)")

    # --- FILTRE D'ESPACE PIVOT (OBSTACLE ROOM CHECK) ---
    entry = indicators.get("current_price")
    sl_pips = decision.get("stop_loss_pips", 0)
    point = symbol_info.get("point", 0.00001)

    if action == "BUY" and entry and sl_pips:
        r1 = indicators.get("pivot_r1")
        if r1 and isinstance(r1, (int, float)) and r1 > entry:
            dist_pips = (r1 - entry) / (10 * point)
            if dist_pips < sl_pips:
                logger.info(f"[{settings.trading_symbol}] Filtre Obstacle : BUY bloque (R1 a {dist_pips:.1f} pips < SL de {sl_pips} pips)")
                return False

    elif action == "SELL" and entry and sl_pips:
        s1 = indicators.get("pivot_s1")
        if s1 and isinstance(s1, (int, float)) and s1 < entry:
            dist_pips = (entry - s1) / (10 * point)
            if dist_pips < sl_pips:
                logger.info(f"[{settings.trading_symbol}] Filtre Obstacle : SELL bloque (S1 a {dist_pips:.1f} pips < SL de {sl_pips} pips)")
                return False

    return True


def _get_daily_pnl() -> float:
    """Calcule le P&L du jour : trades fermes + floating P&L (CRITICAL-02)."""
    try:
        db = get_db()
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        rows = db.execute(
            "SELECT COALESCE(SUM(profit), 0) FROM trades "
            "WHERE DATE(opened_at) = ? AND profit IS NOT NULL", [today]
        ).fetchall()
        realized_pnl = rows[0][0] if rows else 0.0
        # Ajouter le floating P&L des positions ouvertes
        positions = mt5.positions_get()
        floating_pnl = sum(p.profit for p in positions) if positions else 0.0
        return realized_pnl + floating_pnl
    except Exception:
        return 0.0


def _count_consecutive_losses() -> int:
    """Compte les pertes consecutives (HIGH-08)."""
    try:
        db = get_db()
        rows = db.execute(
            "SELECT profit FROM trades WHERE profit IS NOT NULL ORDER BY closed_at DESC LIMIT 10"
        ).fetchall()
        count = 0
        for r in rows:
            if r[0] is not None and r[0] < 0:
                count += 1
            else:
                break
        return count
    except Exception:
        return 0


def _set_circuit_breaker_until(hours: int = 4) -> None:
    """Active le circuit breaker pour N heures (HIGH-08)."""
    try:
        db = get_db()
        from datetime import datetime, timedelta
        until = (datetime.now() + timedelta(hours=hours)).isoformat()
        db.execute(
            "INSERT OR REPLACE INTO bot_state (key, value) VALUES ('circuit_breaker_until', ?)",
            [until],
        )
        db.commit()
    except Exception:
        pass


def _is_ranging_market(decision: dict) -> bool:
    """v4.1: Detecte un marche en range (ADX < seuil pendant N periodes consecutives).

    Utilise _RANGING_ADX_THRESHOLD (25.0) et _RANGING_CONSECUTIVE_BARS (3).
    L'etat est suivi dans _ranging_state (en memoire, non persiste).
    Retourne True si le marche est en range et qu'il faut bloquer les trades."""
    indicators = decision.get("indicators", {})
    adx = indicators.get("adx_14", 30) if indicators else 30
    sym = settings.trading_symbol

    if adx is None or adx > _RANGING_ADX_THRESHOLD:
        # ADX normal: reset le compteur
        _ranging_state[sym] = 0
        return False

    # ADX bas: incrementer le compteur
    current = _ranging_state.get(sym, 0) + 1
    _ranging_state[sym] = current

    if current >= _RANGING_CONSECUTIVE_BARS:
        logger.info(
            f"RANGE DETECTE pour {sym}: ADX={adx:.1f} < {_RANGING_ADX_THRESHOLD} "
            f"depuis {current} periodes - trading bloque"
        )
        return True

    logger.debug(f"ADX bas pour {sym}: {adx:.1f}, compteur={current}/{_RANGING_CONSECUTIVE_BARS}")
    return False


def _circuit_breaker_active() -> bool:
    """Verifie si le circuit breaker est actif (HIGH-08)."""
    try:
        db = get_db()
        row = db.execute(
            "SELECT value FROM bot_state WHERE key = 'circuit_breaker_until'"
        ).fetchone()
        if row is None:
            return False
        from datetime import datetime
        until = datetime.fromisoformat(row[0])
        return datetime.now() < until
    except Exception:
        return False


# ============================================================
# Gestion des positions (breakeven, trailing stop, time exit) v2.0
# ============================================================

def manage_open_positions() -> int:
    """Applique breakeven, trailing stop, time exit aux positions ouvertes.
    Appele au debut de chaque cycle. Retourne le nombre de modifications.
    v4.0: Active un cooldown apres TIME EXIT pour eviter le re-entry immediat.
    v4.2: Clôture d'urgence de fin de semaine à partir de vendredi 20h30 UTC."""
    sym = settings.trading_symbol
    modifications = 0

    # Clôture d'urgence du week-end
    now_utc = datetime.now(timezone.utc)
    if is_weekend_closure(now_utc):
        open_pos = get_open_positions(sym)
        if open_pos:
            logger.warning(f"[{sym}] Période de fermeture du week-end active. Clôture forcée de {len(open_pos)} position(s).")
            for pos in open_pos:
                res = close_position(pos["ticket"], sym)
                if res.success:
                    modifications += 1
            return modifications

    for pos in get_open_positions(sym):
        if _apply_breakeven(pos):
            modifications += 1
        elif _apply_trailing_stop(pos):
            modifications += 1
        if _check_time_exit(pos):
            close_position(pos["ticket"], sym)
            # v4.0: Cooldown pour eviter le re-entry immediat dans la meme direction
            direction = "BUY" if pos.get("type") == mt5.POSITION_TYPE_BUY else "SELL"
            _set_cooldown_after_exit(sym, direction)
            modifications += 1
    return modifications


def is_weekend_closure(dt: datetime) -> bool:
    """Détermine si on est dans la période de fermeture du week-end (de vendredi 20h30 UTC à dimanche 22h00 UTC)."""
    if dt.tzinfo is None:
        dt_utc = dt.replace(tzinfo=timezone.utc)
    else:
        dt_utc = dt.astimezone(timezone.utc)
        
    weekday = dt_utc.weekday()  # 0=Lundi, ..., 4=Vendredi, 5=Samedi, 6=Dimanche
    if weekday == 4:  # Vendredi
        if dt_utc.hour > 20 or (dt_utc.hour == 20 and dt_utc.minute >= 30):
            return True
    elif weekday == 5:  # Samedi
        return True
    elif weekday == 6:  # Dimanche (Fermé avant 22h00 UTC)
        if dt_utc.hour < 22:
            return True
    return False


def _apply_breakeven(pos: dict) -> bool:
    """Deplace le SL au prix d'entree quand le profit >= 1.2x SL initial.
    v3.0: seuil a 1.2R pour couvrir commissions/swaps et laisser respirer le trade."""
    entry_price = pos.get("price_open", 0)
    current_sl = pos.get("sl", 0)
    ticket = pos.get("ticket", 0)
    tick = mt5.symbol_info_tick(settings.trading_symbol)
    sym_info = mt5.symbol_info(settings.trading_symbol)

    if tick is None or sym_info is None or entry_price == 0:
        return False

    if pos.get("type") == mt5.POSITION_TYPE_BUY:
        sl_distance_pips = (entry_price - current_sl) / (10 * sym_info.point) if current_sl else 0
        profit_distance_pips = (tick.bid - entry_price) / (10 * sym_info.point)
        # v3.0: Breakeven a 1.2R (couvre commissions/swaps + marge de respiration)
        if profit_distance_pips >= sl_distance_pips * 1.2 and current_sl < entry_price:
            # Offset de 1.5 pips pour couvrir le spread et la commission
            breakeven_price = round(entry_price + (15 * sym_info.point), sym_info.digits)
            _modify_sl(ticket, breakeven_price)
            logger.info(f"BREAKEVEN: ticket {ticket}, SL deplace a {breakeven_price}")
            return True
    else:
        sl_distance_pips = (current_sl - entry_price) / (10 * sym_info.point) if current_sl else 0
        profit_distance_pips = (entry_price - tick.ask) / (10 * sym_info.point)
        # v3.0: Breakeven a 1.2R
        if profit_distance_pips >= sl_distance_pips * 1.2 and current_sl > entry_price:
            # Offset de 1.5 pips pour couvrir le spread et la commission
            breakeven_price = round(entry_price - (15 * sym_info.point), sym_info.digits)
            _modify_sl(ticket, breakeven_price)
            logger.info(f"BREAKEVEN: ticket {ticket}, SL deplace a {breakeven_price}")
            return True
    return False


def _apply_trailing_stop(pos: dict) -> bool:
    """Trailing stop: deplace le SL quand le profit >= 2x le SL initial."""
    entry_price = pos.get("price_open", 0)
    current_sl = pos.get("sl", 0)
    ticket = pos.get("ticket", 0)
    tick = mt5.symbol_info_tick(settings.trading_symbol)
    sym_info = mt5.symbol_info(settings.trading_symbol)

    if tick is None or sym_info is None or entry_price == 0:
        return False

    trail_distance_pips = 15  # distance de trailing en pips
    trail_distance = trail_distance_pips * 10 * sym_info.point
    sl_distance_pips = abs(entry_price - current_sl) / (10 * sym_info.point) if current_sl else 0

    if pos.get("type") == mt5.POSITION_TYPE_BUY:
        profit_distance_pips = (tick.bid - entry_price) / (10 * sym_info.point)
        if profit_distance_pips >= sl_distance_pips * 2:
            new_sl = tick.bid - trail_distance
            new_sl = round(new_sl, sym_info.digits)
            if new_sl > current_sl + sym_info.point:
                _modify_sl(ticket, new_sl)
                logger.info(f"TRAILING: ticket {ticket}, SL deplace a {new_sl}")
                return True
    else:
        profit_distance_pips = (entry_price - tick.ask) / (10 * sym_info.point)
        if profit_distance_pips >= sl_distance_pips * 2:
            new_sl = tick.ask + trail_distance
            new_sl = round(new_sl, sym_info.digits)
            if new_sl < current_sl - sym_info.point:
                _modify_sl(ticket, new_sl)
                logger.info(f"TRAILING: ticket {ticket}, SL deplace a {new_sl}")
                return True
    return False


def _check_time_exit(pos: dict) -> bool:
    """Ferme la position si la structure de marche s'inverse contre le trade.

    v4.0: Structure break base sur le 20-bar high/low (pas de fenetres glissantes
    qui creent des swings fantomes).
    - BUY: ferme si prix < SMA20 OU prix casse le lowest 20-bar
    - SELL: ferme si prix > SMA20 OU prix casse le highest 20-bar
    - Securite: stagnation totale >4h"""
    try:
        from datetime import datetime as dt
        ticket = pos.get("ticket", 0)
        pnl = pos.get("profit", 0)

        tick = mt5.symbol_info_tick(settings.trading_symbol)
        sym_info = mt5.symbol_info(settings.trading_symbol)
        if tick is None or sym_info is None:
            return False

        # Recuperer les 20 dernieres bougies (timeframe du symbole)
        tf_map = {"M15": mt5.TIMEFRAME_M15, "H1": mt5.TIMEFRAME_H1}
        timeframe = tf_map.get(settings.trading_timeframe, mt5.TIMEFRAME_M15)
        rates = mt5.copy_rates_from_pos(settings.trading_symbol, timeframe, 0, 20)
        if rates is None or len(rates) < 20:
            # Fallback: chronometre 4h
            db = get_db(symbol=settings.trading_symbol)
            row = db.execute("SELECT opened_at FROM trades WHERE ticket = ?", [ticket]).fetchone()
            if row is None:
                return False
            opened = dt.fromisoformat(row[0])
            age_minutes = (dt.now() - opened).total_seconds() / 60
            if age_minutes > 240 and abs(pnl) < 0.5:
                logger.info(f"TIME EXIT (fallback): ticket {ticket}, stagnation {age_minutes:.0f}min")
                return True
            return False

        close_prices = [r[4] for r in rates]
        highs = [r[2] for r in rates]
        lows = [r[3] for r in rates]
        current_price = tick.bid if pos.get("type") == mt5.POSITION_TYPE_BUY else tick.ask

        if pos.get("type") == mt5.POSITION_TYPE_BUY:
            # Structure break: prix casse le plus bas des 20 dernieres bougies
            lowest_20 = min(lows)
            if current_price < lowest_20:
                logger.info(f"TIME EXIT: ticket {ticket}, BUY casse lowest 20-bar ({current_price:.5f} < {lowest_20:.5f})")
                return True
        else:
            # Structure break: prix casse le plus haut des 20 dernieres bougies
            highest_20 = max(highs)
            if current_price > highest_20:
                logger.info(f"TIME EXIT: ticket {ticket}, SELL casse highest 20-bar ({current_price:.5f} > {highest_20:.5f})")
                return True

        # Securite: stagnation totale >4h
        db = get_db(symbol=settings.trading_symbol)
        row = db.execute("SELECT opened_at FROM trades WHERE ticket = ?", [ticket]).fetchone()
        if row is not None:
            opened = dt.fromisoformat(row[0])
            age_minutes = (dt.now() - opened).total_seconds() / 60
            if age_minutes > 240 and abs(pnl) < 0.5:
                logger.info(f"TIME EXIT: ticket {ticket}, stagnation totale {age_minutes:.0f}min")
                return True

    except Exception as e:
        logger.warning(f"TIME EXIT erreur: {e}")
    return False


def _modify_sl(ticket: int, new_sl: float) -> None:
    """Modifie le SL d'une position ouverte.
    v3.0: Verifie trade_stops_level du broker avant modification."""
    sym = settings.trading_symbol
    pos = []
    sym_info = mt5.symbol_info(sym)

    # Verifier la distance minimale SL autorisee par le broker
    if sym_info is not None:
        tick = mt5.symbol_info_tick(sym)
        if tick is not None:
            stops_level = sym_info.trade_stops_level * sym_info.point
            # Pour un SL, la distance minimale depuis le prix actuel
            pos = mt5.positions_get(ticket=ticket)
            if pos and len(pos) > 0:
                if pos[0].type == mt5.POSITION_TYPE_BUY:
                    distance_from_bid = tick.bid - new_sl
                    if distance_from_bid < stops_level and new_sl < tick.bid:
                        logger.warning(
                            f"SL rejete: distance {distance_from_bid:.5f} < stops_level {stops_level:.5f} "
                            f"(broker min). Ticket {ticket}, SL demande={new_sl}, bid={tick.bid}"
                        )
                        return
                else:
                    distance_from_ask = new_sl - tick.ask
                    if distance_from_ask < stops_level and new_sl > tick.ask:
                        logger.warning(
                            f"SL rejete: distance {distance_from_ask:.5f} < stops_level {stops_level:.5f} "
                            f"(broker min). Ticket {ticket}, SL demande={new_sl}, ask={tick.ask}"
                        )
                        return

    # Conserver le TP existant (BUG: MT5 supprime le TP si on ne le repasse pas)
    current_tp = pos[0].tp if pos and len(pos) > 0 else 0.0
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": sym,
        "position": ticket,
        "sl": new_sl,
        "tp": current_tp,
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.warning(f"Echec modification SL ticket {ticket}: {result.comment if result else 'None'}")
