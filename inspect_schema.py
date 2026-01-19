
import sqlite3
import pandas as pd

def inspect():
    conn = sqlite3.connect("hockey_stats.db")
    cursor = conn.cursor()
    
    # Tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("Tables:", tables)
    
    # DimGame Columns
    print("\n--- DimGame ---")
    df = pd.read_sql_query("SELECT * FROM DimGame LIMIT 1", conn)
    print(df.columns)
    
    conn.close()

if __name__ == "__main__":
    inspect()
