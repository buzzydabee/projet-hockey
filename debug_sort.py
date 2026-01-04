
import pandas as pd

# Mock data simulating 4 periods
data = {
    'Team': ['A', 'B', 'C'],
    'V/MJ': [
        [0.0, 0.0, 0.0, 0.1],  # Low start, small rise
        [0.0, 0.0, 0.0, 0.9],  # Low start, BIG rise (Should be top if sorted by last)
        [0.5, 0.5, 0.5, 0.5]   # Consistent mid
    ]
}

df = pd.DataFrame(data)

print("Original:")
print(df)

# Sort by Column V/MJ (Simulating default Pandas/Python sort of lists)
df_sorted = df.sort_values(by='V/MJ', ascending=False)
print("\nSorted Descending (Standard List Sort):")
print(df_sorted)

# Expected: 
# [0.5, ...] > [0.0, ...]
# So C will be first. 
# Then compare [0.0, 0.0, 0.0, 0.1] vs [0.0, 0.0, 0.0, 0.9]
# 0.9 > 0.1, so B > A.
# Order should be C, B, A. 
# Even though B has the highest *last* value (0.9).

# Check Logic used in app.py for DEFAULT sort
df['SortKey'] = df['V/MJ'].apply(lambda x: x[-1])
df_default = df.sort_values(by='SortKey', ascending=False)
print("\nSorted by Last Period (App Logic):")
print(df_default)
# Order should be B (0.9), C (0.5), A (0.1).
