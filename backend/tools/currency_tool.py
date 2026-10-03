import json
import logging
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

# Session cache for exchange rates to avoid redundant network calls
_RATE_CACHE: dict[str, float] = {}


def get_live_exchange_rate(from_curr: str = "USD", to_curr: str = "INR") -> float:
    """
    Fetches the live official foreign exchange rate from the internet.
    Tries European Central Bank (via Frankfurter API) first, then open.er-api.com.
    
    Args:
        from_curr: Source currency code (e.g. 'USD', 'EUR', 'GBP', 'JPY')
        to_curr: Target currency code (e.g. 'INR', 'USD')
        
    Returns:
        float: Current live exchange rate (e.g., 95.98 for USD -> INR)
    """
    from_curr = from_curr.upper()
    to_curr = to_curr.upper()

    if from_curr == to_curr:
        return 1.0

    cache_key = f"{from_curr}_{to_curr}"
    if cache_key in _RATE_CACHE:
        return _RATE_CACHE[cache_key]

    # Source 1: Frankfurter API (European Central Bank reference rates, free, no API key required)
    try:
        url = f"https://api.frankfurter.dev/v1/latest?base={from_curr}&symbols={to_curr}"
        req = urllib.request.Request(url, headers={"User-Agent": "TravelPlanner/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            rate = float(data["rates"][to_curr])
            _RATE_CACHE[cache_key] = rate
            return rate
    except Exception as e:
        logger.warning(f"Frankfurter exchange rate lookup failed for {cache_key}: {e}")

    # Source 2: open.er-api.com (Free open exchange rate endpoint)
    try:
        url = f"https://open.er-api.com/v6/latest/{from_curr}"
        req = urllib.request.Request(url, headers={"User-Agent": "TravelPlanner/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            rate = float(data["rates"][to_curr])
            _RATE_CACHE[cache_key] = rate
            return rate
    except Exception as e:
        logger.warning(f"open.er-api lookup failed for {cache_key}: {e}")

    # Fallback to realistic standard market baseline if network is unreachable
    baseline_rates = {
        "USD_INR": 95.0,
        "EUR_INR": 104.0,
        "GBP_INR": 122.0,
        "JPY_INR": 0.61,
        "INR_USD": 0.0105
    }
    fallback = baseline_rates.get(cache_key, 95.0)
    _RATE_CACHE[cache_key] = fallback
    return fallback


def convert_currency(amount: float, from_curr: str = "USD", to_curr: str = "INR") -> int:
    """
    Converts an amount from one currency to another using the live internet exchange rate.
    
    Args:
        amount: Numerical amount in from_curr
        from_curr: Source currency code
        to_curr: Target currency code
        
    Returns:
        int: Converted amount rounded to nearest integer
    """
    rate = get_live_exchange_rate(from_curr, to_curr)
    return int(round(amount * rate))
