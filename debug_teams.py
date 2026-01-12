import sqlite3
import pandas as pd

conn = sqlite3.connect("hockey_stats.db")
q = "SELECT date FROM DimGame WHERE home_team_id = 22 OR visitor_team_id = 22"
dates = pd.read_sql(q, conn)
for d in dates['date']:
    print(d)
conn.close()
