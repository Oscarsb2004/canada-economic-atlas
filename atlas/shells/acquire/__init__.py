"""
Acquire shells: everything that reads from outside the repository.

Every request goes through `fetcher.Fetcher`, so politeness, retries and the
cache are decided once, and the golden-master recorder (verify/golden.py) sees
every exchange.
"""
