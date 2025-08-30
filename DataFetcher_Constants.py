
import numpy as np
from enum import Enum

# Enums
class E_FetchType(Enum):
    NULL            = -1
    YFINANCE        = 0
    TASE_FAST       = 1
    TASE_HISTORICAL = 2


# General Constants for Data Fetcher
VERSION                = "1.2.4" # Version of the Data Fetcher
PRODUCTION             = True    # Set to True for production environment

DEBUG_MODE             = False   # When True, browser will be visible for debugging
BYPASS_ASYNC_CHECKUP   = False   # Bypass async checkup for debugging

# Concurrency Control
MAX_CONCURRENT_BROWSERS = 4      # Maximum concurrent browser instances (Selenium)
MAX_CONCURRENT_REQUESTS = 5      # Maximum concurrent API requests (YFinance)

API_SINGLE_TICKER_TIMEOUT   = 20    # Timeout for single ticker API calls (increased for better reliability)
API_CALL_DELAY              = 0.3   # Delay in seconds between API calls (increased to avoid rate limits)
API_CALL_DELAY_STD          = 0.01  # Standard delay for API calls

MAX_ATTEMPTS                = 3     # Maximum attempts to fetch data
INITIAL_DAYS_HALF_SPAN      = 5     # Maximum days to look back & forward for data
HALF_SPAN_INCREMENT         = 5     # Increment for looking back/forward days

GENERAL_DATE_FORMAT     = "%m/%d/%Y"  # General date format used across the application

# DataBase
DB_TTL = int(60*60*24*365) # Time-to-live for database entries (in seconds)

# Silent Browser Constants
SILENT_BROWSER_TIMEOUT = 60  # Timeout for silent browser operations

# YFinance Constants
YFINANCE_DATE_FORMAT    = "%Y-%m-%d"  # Date format used by Yahoo Finance

# TASE Constants
BASE_TASE_URL           = lambda indicator: "https://finance.themarker.com/etf/" + f"{indicator}" # Base URL for TheMarker
THEMARKER_DATE_FORMAT   = "%d/%m/%Y"  # Date format used by TheMarker

NAME_PATTERN        = r'<title>([^-]+?)\s*-\s*[^<]*</title>'
EXPENSE_PATTERNS    = { 'main': r'דמי*',
                        'percentage': r'\d+(?:\.\d+)?'}
NUMBER_PATTERN      = r'(\d+(?:,\d{3})*(?:\.\d+)?)'

# TASE Delays
TASE_DELAYS = {
    "Chart": {  "Description": "Chart Interaction Delays",
                "Reason": "Visual rendering and human observation need time",
                "delays": np.array([1.0, 2.0]), # Delay values default to production version
                "ratio2debug": 3.0
                },
    "PageLoad": {   "Description": "Page Load Waits",
                    "Reason": "Visual feedback helps verify successful loads",
                    "delays": np.array([3.0, 5.0]),
                    "ratio2debug": 2.0
                },
    "Element": {   "Description": "Element Location",
                   "Reason": "Allows visual confirmation of element highlighting",
                   "delays": np.array([0.25, 0.7]),
                   "ratio2debug": 2.5
                },
    "Mouse": {   "Description": "Mouse Movements/Clicks",
                   "Reason": "Visual tracking of mouse actions",
                   "delays": np.array([0.3, 0.5]),
                   "ratio2debug": 3.0
               }
}

# Optimized delay calculation function
def get_adaptive_delay(delay_type: str, delay_index: int = 0):
    """Get adaptive delay based on debug mode and delay type"""
    delay_config = TASE_DELAYS.get(delay_type, TASE_DELAYS["Element"])
    base_delay = delay_config["delays"][min(delay_index, len(delay_config["delays"]) - 1)]
    return base_delay * delay_config["ratio2debug"] if DEBUG_MODE else base_delay

TASE_CHART_DELAYS       = TASE_DELAYS["Chart"]["delays"] * TASE_DELAYS["Chart"]["ratio2debug"] if DEBUG_MODE else TASE_DELAYS["Chart"]["delays"]
TASE_PAGELOAD_DELAYS    = TASE_DELAYS["PageLoad"]["delays"] * TASE_DELAYS["PageLoad"]["ratio2debug"] if DEBUG_MODE else TASE_DELAYS["PageLoad"]["delays"]
TASE_ELEMENT_DELAYS     = TASE_DELAYS["Element"]["delays"] * TASE_DELAYS["Element"]["ratio2debug"] if DEBUG_MODE else TASE_DELAYS["Element"]["delays"]
TASE_MOUSE_DELAYS       = TASE_DELAYS["Mouse"]["delays"] * TASE_DELAYS["Mouse"]["ratio2debug"] if DEBUG_MODE else TASE_DELAYS["Mouse"]["delays"]