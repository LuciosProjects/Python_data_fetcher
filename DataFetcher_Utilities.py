import numpy as np
from datetime import date
import pandas as pd
import time
import re
from dataclasses import dataclass
import requests
from bs4 import BeautifulSoup

from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains

import DataFetcher_Constants as Constants
from DataFetcher_Constants import E_FetchType
from SilentBrowser import SilentBrowser

# Globals
SB = SilentBrowser(make_null=True)
''' Instance of the SilentBrowser for headless browsing '''

_REQUEST_SESSION = None
''' Session for HTTP requests '''

# Classes
@dataclass
class fetchRequest:
    """
        Represents a request for data fetching.
    """
    indicator: str
    name: str = ""
    date: str = ""
    fetched_price: float | None = None  # Use None to indicate no price fetched
    expense_rate: float | None = None  # Use None to indicate no expense rates
    actual_date: str = ""
    success: bool = True
    message: str = ""
    currency: str = ""

    def __post_init__(self):
        # Ensure date is a string
        if not isinstance(self.date, str):
            self.date = str(self.date)

@dataclass(frozen=False)
class data_fetcher_flags:
    """Flags to control data fetching behavior"""

    ASYNC_AVAILABLE: bool = False
    ''' Flag to indicate if async processing is available '''

    ASYNC_MODE: bool = False
    ''' Flag to indicate if async processing is enabled '''

    ASYNC_FAILED: bool = False
    ''' Flag to indicate if async processing has failed, it is initialized to False '''

    NEED_HISTORICAL: bool = False
    ''' Flag to indicate if historical data is needed '''
    NEED_YFINANCE: bool = False
    ''' Flag to indicate if YFinance data is needed '''
    NEED_TASE_FAST: bool = False
    ''' Flag to indicate if TASE data is needed '''

FLAGS = data_fetcher_flags()

# Functions
def initialize_output_dict() -> dict:
    '''
        Initializes the output dictionary for data fetching functions.
    '''

    # Initialize output dictionary
    output = {  
                "status": "success", # We assume success by default, spread positivity around the world
                "status_code": 200, # HTTP status code, 200 is default for success
                "message": "Data fetched without errors",
                "data": {"indicators": [], 
                         "names": [], # Placeholder for security names
                         "fetched_prices": [], # Placeholder for fetched prices
                         "expense_rates": [], # Placeholder for expense rates
                         "actual_dates": [], # Placeholder for actual dates
                         "currencies": [], # Placeholder for currencies
                         "messages": [], # Placeholder for messages
                         "date": None}
            }
    
    return output

def get_request_session():
    """Get or create a requests session for connection reuse"""
    global _REQUEST_SESSION
    if _REQUEST_SESSION is None:
        _REQUEST_SESSION = requests.Session()
        _REQUEST_SESSION.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        })
    return _REQUEST_SESSION

def find_closest_date(data_frame, target_date):
    """
    Find the closest available date in the dataframe to the target date.
    
    Args:
        data_frame (pd.DataFrame): DataFrame with date index
        target_date (date): Target date to find closest match for
        
    Returns:
        pd.Timestamp or None: Closest available date or None if no valid data
    """
    if data_frame.empty:
        return None
    
    # Convert target_date to timestamp for comparison
    target_timestamp = pd.Timestamp(target_date)
    
    # Filter out rows with all NaN values
    valid_data = data_frame.dropna(how='all')
    
    if valid_data.empty:
        return None
    
    # Find the closest date for each symbol
    # First try to find exact match
    dates = valid_data.index
    closest_idx = np.argmin(np.abs((dates - target_timestamp)))

    return dates[closest_idx]

def safe_extract_value(data):
    """Safely extract value from pandas data, handling various formats"""
    try:
        if hasattr(data, 'values') and len(data.values) > 0:
            # If it's a Series, get the first (or only) value
            value = data.values[0] if hasattr(data.values, '__len__') else data.values
        else:
            # Direct value access
            value = data
        
        # Check if value is NaN
        if pd.isna(value):
            return None
        
        return float(value)
    except:
        return None

def safe_extract_volume(data):
    """Safely extract volume as integer"""
    try:
        value = safe_extract_value(data)
        if value is None:
            return None
        return int(value)
    except:
        return None

def safe_extract_date_string(date_obj):
    """Safely convert date object to string"""
    try:
        if hasattr(date_obj, 'strftime'):
            return date_obj.strftime(Constants.GENERAL_DATE_FORMAT)
        elif hasattr(date_obj, 'date'):
            return date_obj.date().strftime(Constants.GENERAL_DATE_FORMAT)
        else:
            return str(date_obj)[:10]  # Take first 10 chars (YYYY-MM-DD)
    except:
        return str(date_obj)[:10]

def safe_extract_date_obj(date_obj):
    """Safely convert date object to date for comparison"""
    try:
        if hasattr(date_obj, 'date'):
            return date_obj.date()
        elif hasattr(date_obj, 'to_pydatetime'):
            return date_obj.to_pydatetime().date()
        else:
            return pd.to_datetime(date_obj).date()
    except:
        return date_obj
    
def random_delay(min_seconds=Constants.API_CALL_DELAY - 0.05, max_seconds=Constants.API_CALL_DELAY + 0.05):
    """
    Add a random delay to simulate human behavior.
    """

    delay = np.random.uniform(min_seconds, max_seconds)
    time.sleep(delay)

def classify_fetch_types(indicators: list[str], target_date: date) -> list[E_FetchType]:
    """
        Classify a list of indicators into their fetch types.

        Args:
            indicators (list[str]): List of security indicators.
            target_date (date): Target date for the indicators.

        Returns:
            tuple[bool, list[E_FetchType]]: A tuple containing a success flag and a list of fetch types.
    """

    N_indicators = len(indicators)

    has_tase, is_tase_indicator = has_tase_indicators(indicators)
    is_historical = has_tase and target_date != date.today().strftime(Constants.GENERAL_DATE_FORMAT)

    fetch_types = [E_FetchType.NULL]*N_indicators
    for i in range(N_indicators):
        if is_tase_indicator[i]:
            fetch_types[i] = E_FetchType.TASE_HISTORICAL if is_historical else E_FetchType.TASE_FAST

            if not FLAGS.NEED_HISTORICAL and fetch_types[i] == E_FetchType.TASE_HISTORICAL:
                FLAGS.NEED_HISTORICAL = True
            elif not FLAGS.NEED_TASE_FAST and fetch_types[i] == E_FetchType.TASE_FAST:
                FLAGS.NEED_TASE_FAST = True
        else:
            fetch_types[i] = E_FetchType.YFINANCE

            if not FLAGS.NEED_YFINANCE:
                FLAGS.NEED_YFINANCE = True

    return fetch_types

def make_fetch_caches(fetcher_data: dict, fetch_types: list) -> tuple[list, list, list]:

    target_date = fetcher_data["data"]["date"]

    YFinance_fetch_cache = []
    TASE_Fast_fetch_cache = []
    TASE_Historical_fetch_cache = []

    for i, indicator in enumerate(fetcher_data["data"]["indicators"]):
        request = fetchRequest(indicator=indicator, date=target_date)
        if fetch_types[i] == E_FetchType.YFINANCE:
            YFinance_fetch_cache.append((i, request))
        elif fetch_types[i] == E_FetchType.TASE_FAST:
            request.actual_date = target_date
            TASE_Fast_fetch_cache.append((i, request))
        elif fetch_types[i] == E_FetchType.TASE_HISTORICAL:
            TASE_Historical_fetch_cache.append((i, request))

    return YFinance_fetch_cache, TASE_Fast_fetch_cache, TASE_Historical_fetch_cache

def add_attempt2msg(request: fetchRequest, attempt: int):
    """
    Add attempt information to the request message.
    
    Args:
        request (fetchRequest): The request object to update.
        attempt (int): The current attempt number.
    """

    if attempt < Constants.MAX_ATTEMPTS - 1:
        request.message += f" - Retrying ({attempt + 1}/{Constants.MAX_ATTEMPTS})"
    else:
        request.message += f" - Giving up after {Constants.MAX_ATTEMPTS} attempts"

# TASE specific functions
def has_tase_indicators(indicators: list[str]) -> tuple[bool, list[bool]]:
    """
    Check if the list of indicators contains any TASE indicators.
    
    Args:
        indicators (list[str]): List of financial indicators.
        
    Returns:
        bool: True if any indicator is a TASE indicator, False otherwise.
    """

    is_tase_indicators = [indicator.isdigit() for indicator in indicators]
    return any(is_tase_indicators), is_tase_indicators

def extract_security_name_from_html(html: str) -> str:
    """
    Extract security name using multiple regex patterns.
    
    Args:
        html_content (str): Raw HTML content
        
    Returns:
        str: Security name or empty string if not found
    """

    match = re.search(Constants.NAME_PATTERN, html, re.IGNORECASE)
    if match:
        return match.group(1)

    return ""

def extract_current_price_from_html(html: str) -> float | None:
    """
    Extract price from raw HTML using multiple regex patterns.
    
    Args:
        html (str): Raw HTML content
        
    Returns:
        float | None: Price as decimal or None if not found
    """

    # Use regex to find the price element           
    price_element = re.search(r'<span class=".*?">שער</span><span class=".*?">' + Constants.NUMBER_PATTERN + '</span>', html, re.IGNORECASE)
    if price_element:
        try:
            return float(price_element.group(1).replace(",", ""))/100.0 # Israeli security prices are priced in ILAs
        except (ValueError, IndexError):
            return None

    return None

def get_expense_rate(soup: BeautifulSoup) -> float:
    """
    Get the expense rate for a specific indicator and date.
    """

    all_text = soup.get_text() 

    # The actual expense rate components are stored here
    expense_secondary_patterns = {  'standard': ['ניהול', 0],
                                    'trustee': ['נאמן', 0],
                                    'trustee_diff': ['ניהול משתנים', 0],
                                    'trustee_actual': ['ניהול משתנים בפועל', 0]}

    matches = re.finditer(Constants.EXPENSE_PATTERNS['main'], all_text, re.IGNORECASE)

    expense_rate = 0.0

    for match in matches:
        # Look for percentage patterns near this match
        start_pos = max(0, match.start() - 200)
        end_pos = min(len(all_text), match.end() + 200)
        context = all_text[start_pos:end_pos]

        # The actual expense rate value components should appear right after the expense secondary patterns
        for category, (secondary_pattern, _) in expense_secondary_patterns.items():
            if secondary_pattern in context:
                # Look for percentage patterns in the context
                pattern =  r'' + Constants.EXPENSE_PATTERNS['main'][0:-1] + ' ' + \
                            secondary_pattern + \
                            '(' + Constants.EXPENSE_PATTERNS['percentage'] + ')'

                # percentage_matches = re.findall(pattern, context)
                percentage_match = re.search(pattern, context)
                
                if percentage_match:
                    try:
                        expense_secondary_patterns[category][1] = float(percentage_match.group(1))
                    except (ValueError, IndexError):
                        # Failed to parse expense rate
                        continue

        # Handle logic for expense rate results
        expense_rate = expense_secondary_patterns['standard'][1] +\
                       expense_secondary_patterns['trustee'][1] +\
                       max([expense_secondary_patterns['trustee_diff'][1], expense_secondary_patterns['trustee_actual'][1]])

    return expense_rate

async def fetch_historical_data_enhanced_with_dedicated_browser(request: fetchRequest) -> bool:
    """
    Async version using dedicated browser instance for true parallelization.
    Each task gets its own WebDriver to avoid race conditions completely!
    """
    
    # Create a dedicated browser instance for this task
    dedicated_browser = SilentBrowser(headless=True)
    
    try:
        url = Constants.BASE_TASE_URL(request.indicator)
        
        # Navigate to page with dedicated browser
        if not dedicated_browser.navigate_to(url):
            request.message = "Failed to navigate to page for historical data"
            return False
        
        # Wait for page to fully load
        dedicated_browser._random_delay(Constants.TASE_PAGELOAD_DELAYS[0], Constants.TASE_PAGELOAD_DELAYS[1])
        
        # Get security name
        name_element = dedicated_browser.driver.find_element(By.XPATH, '/html/body/div[1]/div[4]/main/div/div[1]/div[1]/div/h2')
        if name_element:
            request.name = name_element.text.strip()
        else:
            request.name = ""

        # Navigate graph to present the maximum timespan
        try:
            element = dedicated_browser.driver.find_element(By.XPATH, "/html/body/div[1]/div[4]/main/div/div[1]/div[4]/div/div/ul/li[6]/button")

            if element and element.is_displayed() and element.is_enabled():
                dedicated_browser.driver.execute_script("arguments[0].click();", element)
                dedicated_browser._random_delay(Constants.TASE_CHART_DELAYS[0], Constants.TASE_CHART_DELAYS[1])
            else:
                request.message = "Chart timespan button not available or not interactable"
                return False
        except Exception as e:
            request.message = f"Exception while finding chart timespan button: {str(e)}"
            return False

        target_date = pd.to_datetime(request.actual_date, dayfirst=True)
        try:
            # From this point we assume the max span is successfully pressed

            # Find target date
            date_element = dedicated_browser.driver.find_element(By.XPATH, "/html/body/div[1]/div[4]/main/div/div[1]/div[4]/div/div/div/div[2]/div[1]/span[2]")
            price_element = dedicated_browser.driver.find_element(By.XPATH, "/html/body/div[1]/div[4]/main/div/div[1]/div[4]/div/div/div/div[2]/div[2]/span[2]")
            datatip_container = dedicated_browser.driver.find_element(By.CSS_SELECTOR, \
                                                            "#graph-year5 > div:nth-child(1) > svg > g:nth-child(1)") \
                                                            .find_elements(By.XPATH, "./*")
            
            # Initialize ActionChains before the loop
            actions = ActionChains(dedicated_browser.driver)

            # Move to the earliest datatip in the chart
            actions.move_to_element(datatip_container[0]).perform()
            dedicated_browser._random_delay(Constants.TASE_ELEMENT_DELAYS[0], Constants.TASE_ELEMENT_DELAYS[1])  # Allow UI to update

            current_date = pd.to_datetime(date_element.text, dayfirst=True)

            if current_date > target_date:
                # Earliest date is after target date, searching is unnecessary
                request.actual_date = current_date.strftime(Constants.THEMARKER_DATE_FORMAT)
                request.fetched_price = float(price_element.text)/100.0
                request.message = f"Target date {target_date.strftime(Constants.GENERAL_DATE_FORMAT)} is after available data. Using earliest available."

                return True
            else:
                # Smart heuristic search - your brilliant approach!
                N_DataTips = len(datatip_container)
                span_delta_days = (date.today() - current_date.date()).days
                min_delta_days = span_delta_days
                
                # Calculate proportional position based on date range
                initial_guess = int(float((target_date - current_date).days) / span_delta_days * N_DataTips)
                initial_guess = max(0, min(initial_guess, N_DataTips - 1))  # Clamp to valid range
                
                # Track visited elements to avoid redundant checks
                visited = set()
                best_match_date = request.date
                best_match_price = request.fetched_price
                
                # Start from the smart initial guess
                current_idx = initial_guess
                
                while current_idx not in visited and 0 <= current_idx < N_DataTips:
                    visited.add(current_idx)
                    
                    # Move to element and get data
                    actions.move_to_element(datatip_container[current_idx]).perform()
                    dedicated_browser._random_delay(Constants.TASE_ELEMENT_DELAYS[0], Constants.TASE_ELEMENT_DELAYS[1])
                    
                    current_date = pd.to_datetime(date_element.text, dayfirst=True)
                    temp_delta_days = abs((current_date - target_date).days)
                    
                    # Update best match if closer
                    if temp_delta_days < min_delta_days:
                        min_delta_days      = temp_delta_days
                        best_match_date     = current_date.strftime(Constants.THEMARKER_DATE_FORMAT)
                        best_match_price    = float(price_element.text.replace(",", ""))/100.0
                    
                    # Perfect match found
                    if temp_delta_days == 0:
                        break
                    
                    # Smart directional search based on date comparison
                    if current_date < target_date:
                        # Target is later, move forward in chart
                        current_idx += 1
                    elif current_date > target_date:
                        # Target is earlier, move backward in chart  
                        current_idx -= 1
                    else:
                        # Target is the same, reset to initial guess
                        current_idx = initial_guess
                        break

                    # Safety check: if we've visited too many elements, break
                    if len(visited) > min(20, N_DataTips // 2):  # Limit search scope
                        break

                request.actual_date     = best_match_date
                request.fetched_price   = best_match_price
                request.message         = f"Found best match for target date {request.date}."

                if not request.fetched_price:
                    request.message = "Could not extract price from chart"
                    return False
                
                return True
        except Exception as e:
            request.message = "Could not find any valid data points in chart"
            return False
        
    except Exception as e:
        request.message = f"Error in dedicated browser historical fetch: {str(e)}"
        return False
    
    finally:
        # Always cleanup the dedicated browser
        try:
            if dedicated_browser and hasattr(dedicated_browser, 'driver') and dedicated_browser.driver:
                dedicated_browser.close()
        except Exception as cleanup_error:
            print(f"Warning: Error during dedicated browser cleanup: {cleanup_error}")

# Async functions
def should_use_async_in_cloud(indicators: list) -> bool:
    """
    Determine if async processing should be used in Google Cloud Functions.
    
    Args:
        indicators: List of indicators to fetch
        
    Returns:
        bool: Whether to use async processing
    """

    if Constants.BYPASS_ASYNC_CHECKUP:
        print("Bypassing async checkup")
        return True
    
    # Check if we're in Google Cloud Functions
    # is_gcf = os.environ.get("K_SERVICE") is not None or os.environ.get("FUNCTION_NAME") is not None
    
    indicator_count = len(indicators)

    return indicator_count > 1