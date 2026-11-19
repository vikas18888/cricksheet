# cricksheet
Ball-by-ball IPL analysis with Python, SQL (SQLite) and a Streamlit dashboard.
# IPL Analytics: Python + SQL

Ball-by-ball IPL analysis using Python, SQLite and Streamlit.

## Setup
1. Download `ipl_json.zip` from https://cricsheet.org/downloads/ and extract it into `data/ipl_json/`
2. `pip install -r requirements.txt`
3. `python load_data.py` (creates ipl.db)
4. `python -m streamlit run app.py`

## Files
- `load_data.py`: reads Cricsheet JSON and loads it into SQLite
- `queries.sql`: 13 analysis queries (GROUP BY, CTEs, window functions, indexes)
- `app.py`: Streamlit dashboard

Data: Cricsheet (cricsheet.org)
