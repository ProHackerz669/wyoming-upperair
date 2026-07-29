"""
Constants used throughout the Wyoming package.
"""

BASE_URL = "https://weather.uwyo.edu/wsgi/sounding"

REQUEST_TIMEOUT_SECONDS = 45

REQUEST_DELAY_SECONDS = 0.3

DEFAULT_HEADERS = {
    "User-Agent": "wyoming-upperair"
}