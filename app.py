"""
app.py : Streamlit dashboard on top of ipl.db
Run:  streamlit run app.py
Streamlit re-runs this file top to bottom on every click; widgets return plain Python values.
"""

import sqlite3

import pandas as pd
import streamlit as st

DB_PATH = "ipl.db"

st.set_page_config(page_title="IPL Analytics", page_icon="🏏", layout="wide")


@st.cache_data   # remembers results so repeated queries are instant
def run_query(sql, params=()):
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(sql, conn, params=params)


st.title("🏏 IPL Analytics Dashboard")
st.caption("Ball-by-ball data from Cricsheet, stored in SQLite, queried with SQL, shown with Streamlit.")

seasons = run_query(
    "SELECT season FROM matches GROUP BY season ORDER BY MIN(match_date)"
)["season"].tolist()
season = st.sidebar.selectbox("Season", ["All"] + seasons)

# Filter trick: (? = 'All' OR m.season = ?)
# If 'All' is picked, the first part is true so nothing gets filtered.
season_params = (season, season)

tab_bat, tab_bowl, tab_toss, tab_h2h = st.tabs(
    ["Batting", "Bowling", "Toss & Teams", "Head to Head"]
)

# ---------------- Batting ----------------
with tab_bat:
    st.subheader("Top run scorers")
    phase = st.selectbox("Phase of the innings",
                         ["All", "powerplay", "middle", "death"], key="bat_phase")
    min_balls = st.slider("Minimum balls faced", 0, 500, 60, step=10)

    batting = run_query(
        """
        SELECT d.batter,
               SUM(d.batter_runs) AS runs,
               SUM(CASE WHEN d.wides = 0 THEN 1 ELSE 0 END) AS balls_faced,
               ROUND(100.0 * SUM(d.batter_runs)
                     / SUM(CASE WHEN d.wides = 0 THEN 1 ELSE 0 END), 2) AS strike_rate
        FROM deliveries d
        JOIN matches m ON m.match_id = d.match_id
        WHERE d.is_super_over = 0
          AND (? = 'All' OR m.season = ?)
          AND (? = 'All' OR d.phase = ?)
        GROUP BY d.batter
        HAVING balls_faced >= ?
        ORDER BY runs DESC
        LIMIT 10
        """,
        season_params + (phase, phase, min_balls),
    )
    left, right = st.columns([1, 1])
    left.dataframe(batting, hide_index=True, use_container_width=True)
    if not batting.empty:
        right.bar_chart(batting.set_index("batter")["runs"])

# ---------------- Bowling ----------------
with tab_bowl:
    st.subheader("Bowlers: economy and wickets")
    bphase = st.selectbox("Phase of the innings",
                          ["All", "powerplay", "middle", "death"], key="bowl_phase")
    min_legal = st.slider("Minimum legal balls bowled", 0, 600, 120, step=10)

    bowling = run_query(
        """
        SELECT d.bowler,
               SUM(d.is_legal_ball) AS legal_balls,
               SUM(d.is_bowler_wicket) AS wickets,
               ROUND(6.0 * SUM(d.batter_runs + d.wides + d.noballs)
                     / SUM(d.is_legal_ball), 2) AS economy
        FROM deliveries d
        JOIN matches m ON m.match_id = d.match_id
        WHERE d.is_super_over = 0
          AND (? = 'All' OR m.season = ?)
          AND (? = 'All' OR d.phase = ?)
        GROUP BY d.bowler
        HAVING legal_balls >= ?
        ORDER BY economy ASC
        LIMIT 10
        """,
        season_params + (bphase, bphase, min_legal),
    )
    left, right = st.columns([1, 1])
    left.dataframe(bowling, hide_index=True, use_container_width=True)
    if not bowling.empty:
        right.bar_chart(bowling.set_index("bowler")["economy"])

# ---------------- Toss and teams ----------------
with tab_toss:
    c1, c2 = st.columns(2)

    c1.subheader("Does winning the toss help?")
    toss = run_query(
        """
        SELECT toss_decision AS decision,
               COUNT(*) AS matches,
               ROUND(100.0 * SUM(CASE WHEN toss_winner = winner THEN 1 ELSE 0 END)
                     / COUNT(*), 1) AS toss_winner_win_pct
        FROM matches m
        WHERE winner IS NOT NULL
          AND (? = 'All' OR season = ?)
        GROUP BY toss_decision
        """,
        season_params,
    )
    c1.dataframe(toss, hide_index=True, use_container_width=True)

    c2.subheader("Team win %")
    teams = run_query(
        """
        WITH team_matches AS (
            SELECT team1 AS team, winner, season FROM matches WHERE winner IS NOT NULL
            UNION ALL
            SELECT team2 AS team, winner, season FROM matches WHERE winner IS NOT NULL
        )
        SELECT team,
               COUNT(*) AS played,
               ROUND(100.0 * SUM(CASE WHEN team = winner THEN 1 ELSE 0 END)
                     / COUNT(*), 1) AS win_pct
        FROM team_matches
        WHERE (? = 'All' OR season = ?)
        GROUP BY team
        ORDER BY win_pct DESC
        """,
        season_params,
    )
    c2.dataframe(teams, hide_index=True, use_container_width=True)

# ---------------- Head to head ----------------
with tab_h2h:
    st.subheader("Batter vs bowler")
    batters = run_query("SELECT DISTINCT batter FROM deliveries ORDER BY batter")["batter"].tolist()
    bowlers = run_query("SELECT DISTINCT bowler FROM deliveries ORDER BY bowler")["bowler"].tolist()

    c1, c2 = st.columns(2)
    pick_batter = c1.selectbox("Batter", batters)
    pick_bowler = c2.selectbox("Bowler", bowlers)

    h2h = run_query(
        """
        SELECT SUM(batter_runs) AS runs,
               SUM(CASE WHEN wides = 0 THEN 1 ELSE 0 END) AS balls,
               SUM(CASE WHEN is_bowler_wicket = 1 AND player_out = batter
                        THEN 1 ELSE 0 END) AS dismissals
        FROM deliveries
        WHERE batter = ? AND bowler = ?
        """,
        (pick_batter, pick_bowler),
    )
    # SUM() over zero rows gives NULL, meaning they never faced each other.
    if h2h.loc[0, "balls"] is None or pd.isna(h2h.loc[0, "balls"]):
        st.info("These two never faced each other in the data.")
    else:
        runs, balls, outs = (int(h2h.loc[0, c]) for c in ["runs", "balls", "dismissals"])
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Runs", runs)
        m2.metric("Balls", balls)
        m3.metric("Dismissals", outs)
        m4.metric("Strike rate", round(100 * runs / balls, 1))