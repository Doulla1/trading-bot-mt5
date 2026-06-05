import streamlit as st
import sqlite3
import pandas as pd
import json
import os
from pathlib import Path

# --- Configuration de la page ---
st.set_page_config(page_title="AI Trading Dashboard", page_icon="📈", layout="wide")

# Chemins
BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"

@st.cache_data(ttl=60)
def get_available_symbols():
    """Trouve toutes les bases de donnees par symbole."""
    symbols = []
    # Base globale par defaut
    if (DATA_DIR / "trading.db").exists():
        symbols.append("ALL / DEFAULT")
    
    # Dossiers de symboles
    if DATA_DIR.exists():
        for d in DATA_DIR.iterdir():
            if d.is_dir() and (d / "trading.db").exists():
                symbols.append(d.name.upper())
    return symbols

@st.cache_resource
def get_db_connection(symbol: str):
    """Retourne une connexion a la DB du symbole selectionne."""
    if symbol == "ALL / DEFAULT":
        path = DATA_DIR / "trading.db"
    else:
        path = DATA_DIR / symbol.lower() / "trading.db"
    
    if not path.exists():
        return None
        
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def load_trades(conn):
    try:
        # Tente de charger avec close_reason (si la migration est passee)
        df = pd.read_sql_query("SELECT * FROM trades ORDER BY opened_at DESC", conn)
        return df
    except Exception as e:
        st.error(f"Erreur de chargement des trades : {e}")
        return pd.DataFrame()

def load_analysis_log(conn, symbol, opened_at):
    """Trouve l'analyse IA (reasoning, JSONs) juste avant l'ouverture du trade."""
    query = """
        SELECT * FROM analysis_logs 
        WHERE symbol = ? AND timestamp <= ? AND was_executed = 1
        ORDER BY timestamp DESC LIMIT 1
    """
    try:
        cur = conn.cursor()
        cur.execute(query, (symbol, opened_at))
        row = cur.fetchone()
        return dict(row) if row else None
    except Exception:
        return None

# --- UI PRINCIPALE ---
st.title("🤖 AI Trading Dashboard")
st.markdown("Interface d'analyse quantificative et de debug des decisions de l'IA.")

symbols = get_available_symbols()
if not symbols:
    st.warning("Aucune donnee de trading trouvee dans le dossier 'data/'.")
    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.header("🔍 Filtres")
    selected_symbol = st.selectbox("Sélectionner une Devise", symbols)
    
    conn = get_db_connection(selected_symbol)
    if conn is None:
        st.error("Base de données introuvable.")
        st.stop()
        
    trades_df = load_trades(conn)
    
    if trades_df.empty:
        st.warning("Aucun trade enregistré pour ce symbole.")
        st.stop()
        
    # Filtre par Date
    if not trades_df.empty:
        st.divider()
        st.subheader("📅 Période")
        
        # Convertir en datetime pour pouvoir filtrer par date
        trades_df['opened_dt'] = pd.to_datetime(trades_df['opened_at'])
        min_date = trades_df['opened_dt'].min().date()
        max_date = trades_df['opened_dt'].max().date()
        
        # Sélecteur de date (autorise une seule date ou un intervalle)
        date_range = st.date_input("Filtrer par date(s)", [min_date, max_date], min_value=min_date, max_value=max_date)
        
        if len(date_range) == 2:
            start_date, end_date = date_range
            trades_df = trades_df[
                (trades_df['opened_dt'].dt.date >= start_date) & 
                (trades_df['opened_dt'].dt.date <= end_date)
            ].copy()
        elif len(date_range) == 1:
            start_date = date_range[0]
            trades_df = trades_df[trades_df['opened_dt'].dt.date == start_date].copy()
            
    if trades_df.empty:
        st.warning("Aucun trade sur cette période.")
        st.stop()
        
    # Stats Rapides (calculées sur les trades filtrés)
    closed_trades = trades_df[trades_df["closed_at"].notna()]
    if not closed_trades.empty:
        wins = len(closed_trades[closed_trades["profit"] > 0])
        total = len(closed_trades)
        winrate = (wins / total) * 100
        total_profit = closed_trades["profit"].sum()
        
        st.divider()
        st.metric("Total Profit", f"${total_profit:.2f}")
        st.metric("Winrate", f"{winrate:.1f}%", f"{wins}/{total} trades")
    
    st.divider()
    st.subheader("Naviguer dans les trades")
    
    # Creation d'une liste lisible pour le selectbox
    trade_options = []
    for idx, row in trades_df.iterrows():
        status = "✅" if pd.notna(row['profit']) and row['profit'] > 0 else ("❌" if pd.notna(row['profit']) else "⏳")
        profit_str = f"(${row['profit']:.2f})" if pd.notna(row['profit']) else "(Ouvert)"
        label = f"{status} {row['opened_at'][:16]} | {row['direction']} | {profit_str}"
        trade_options.append(label)
        
    selected_trade_idx = st.selectbox("Trades", range(len(trade_options)), format_func=lambda x: trade_options[x])

# --- MAIN AREA ---
if not trades_df.empty and selected_trade_idx is not None:
    trade = trades_df.iloc[selected_trade_idx]
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Ticket", trade["ticket"])
    col2.metric("Direction", trade["direction"])
    col3.metric("Volume", trade["volume"])
    
    is_closed = pd.notna(trade["closed_at"])
    if is_closed:
        profit_color = "normal" if trade["profit"] > 0 else "inverse"
        col4.metric("Profit", f"${trade['profit']:.2f}", delta_color=profit_color)
    else:
        col4.metric("Statut", "EN COURS")

    st.divider()
    
    # Infos d'entree/sortie
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("📥 Entrée")
        st.write(f"**Date:** {trade['opened_at']}")
        st.write(f"**Prix:** {trade['open_price']}")
        st.write(f"**Stop Loss:** {trade['stop_loss']}")
        st.write(f"**Take Profit:** {trade['take_profit']}")
        
    with c2:
        st.subheader("📤 Sortie")
        if is_closed:
            st.write(f"**Date:** {trade['closed_at']}")
            st.write(f"**Prix:** {trade['close_price']}")
            reason = trade.get('close_reason', 'N/A') if 'close_reason' in trade else 'N/A'
            st.write(f"**Raison:** `{reason}`")
        else:
            st.info("Position toujours ouverte.")

    # --- RAISONNEMENT DE L'IA ---
    st.divider()
    st.subheader("🧠 Cerveau de l'IA (Reasoning)")
    st.info(trade.get("reasoning", "Pas de raisonnement enregistré."))
    st.write(f"**Niveau de confiance estimé par l'IA :** {trade.get('confidence', 'N/A')}%")
    
    # --- ANALYSE SNAPSHOTS ---
    analysis = load_analysis_log(conn, trade["symbol"], trade["opened_at"])
    
    st.divider()
    if analysis:
        st.subheader("🕵️ Données techniques vues par l'IA au moment du trade")
        tab1, tab2, tab3 = st.tabs(["📊 Indicateurs", "📅 Calendrier", "🖼️ Graphique"])
        
        with tab1:
            if analysis.get("indicators_snapshot"):
                try:
                    indicators = json.loads(analysis["indicators_snapshot"])
                    st.json(indicators)
                except:
                    st.code(analysis["indicators_snapshot"])
            else:
                st.write("Pas de données d'indicateurs.")
                
        with tab2:
            if analysis.get("calendar_snapshot"):
                try:
                    cal = json.loads(analysis["calendar_snapshot"])
                    st.table(cal) if isinstance(cal, list) else st.json(cal)
                except:
                    st.code(analysis["calendar_snapshot"])
            else:
                st.write("Pas d'annonces au moment du trade.")
                
        with tab3:
            img_path = analysis.get("screenshot_path")
            if img_path and os.path.exists(img_path):
                st.image(img_path, caption="Graphique envoyé à la Vision IA")
            else:
                st.warning("Aucune capture d'écran sauvegardée ou OCR désactivé.")
    else:
        st.warning("⚠️ Snapshot des indicateurs introuvable pour ce trade spécifique.")
