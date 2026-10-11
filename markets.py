"""
markets.py — Louisiana's seven Nielsen television markets
================================================================================
Short keys (NO, SHV, …), names, 2024–25 Nielsen ranks and TV households, and
lookups from the names the data files use: station_spend.json spells a market
out ("Shreveport"), map_paths.json and county_dma.json carry Nielsen's own
("Shreveport, LA"). Shared by the page builders and the political-file summary.
"""

# Market keys, ranks and 2024-25 Nielsen TV households.
MARKETS = {
    'NO':  ('New Orleans',       50, 672790),
    'SHV': ('Shreveport',        91, 375030),
    'BR':  ('Baton Rouge',       95, 355760),
    'LAF': ('Lafayette',        124, 245210),
    'MON': ('Monroe–El Dorado', 142, 171300),
    'LKC': ('Lake Charles',     177,  97170),
    'ALX': ('Alexandria',       183,  85710),
}
# station_spend.json spells markets out; map_paths.json carries Nielsen's own names.
BY_NAME = {v[0]: k for k, v in MARKETS.items()}
BY_TOPO = {'New Orleans, LA': 'NO', 'Baton Rouge, LA': 'BR', 'Shreveport, LA': 'SHV',
           'Lafayette, LA': 'LAF', 'Lake Charles, LA': 'LKC',
           'Monroe, LA-El Dorado, AR': 'MON', 'Alexandria, LA': 'ALX'}
