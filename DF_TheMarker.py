from datetime import date, timedelta
import pandas as pd
import re

from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains

import requests
from bs4 import BeautifulSoup

from SilentBrowser import SilentBrowser
import DataFetcher_Utilities as Utilities
from DataFetcher_Utilities import fetchRequest, FLAGS
import DataFetcher_Constants as Constants

def fetch_tase_fast(request: fetchRequest):
    """
    Fast method to fetch current price using requests (no browser needed).
    
    Args:
        request (fetchRequest): The request object to update
        
    Returns:
        nothing, it updates the request object with fetched data
    """
    
    url = Constants.BASE_TASE_URL(request.indicator)

    for attempt in range(Constants.MAX_ATTEMPTS):
        try:
            if FLAGS.ASYNC_MODE:
                # In async mode, use a dedicated session and not the global one to avoid access conflicts
                session = requests.Session()
                session.headers.update({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                })
            else:
                # Sequential mode, use the global session
                session = Utilities.get_request_session()

            response = session.get(url, timeout=Constants.SILENT_BROWSER_TIMEOUT)

            if response.status_code != 200:
                request.message = f"HTTP {response.status_code}: Failed to fetch page"
                request.success = False
                Utilities.add_attempt2msg(request, attempt)
                continue
            else:
                Utilities.random_delay(Constants.TASE_CHART_DELAYS[0], Constants.TASE_CHART_DELAYS[1])  # Add a random delay to avoid rate limiting

            raw_html = response.text
            soup = BeautifulSoup(response.content, 'html.parser')

            request.name = Utilities.extract_security_name_from_html(raw_html)

            if request.name == "":
                request.message = "Failed to extract security name"
                request.success = False
                Utilities.add_attempt2msg(request, attempt)
                continue

            request.fetched_price = Utilities.extract_current_price_from_html(raw_html)

            if request.fetched_price is None:
                request.message = "Failed to extract price"
                request.success = False
                Utilities.add_attempt2msg(request, attempt)
                continue

            request.expense_rate = Utilities.get_expense_rate(soup)

            request.message = "Price fetched successfully (fast method)"
            request.success = True
            break # after a successful fetch, there's no need for further attempts
        except requests.exceptions.Timeout:
            request.message = "Request timeout - page took too long to load"
            request.success = False
            Utilities.add_attempt2msg(request, attempt)
        except requests.exceptions.RequestException as e:
            request.message = f"Request failed: {str(e)}"
            request.success = False
            Utilities.add_attempt2msg(request, attempt)
        except Exception as e:
            request.message = f"Unexpected error in TASE fast fetch: {str(e)}"
            request.success = False
            Utilities.add_attempt2msg(request, attempt)

def fetch_tase_historical(request: fetchRequest):

    """
    Fetch historical data for a specific indicator and date.
    """

    url = Constants.BASE_TASE_URL(request.indicator)

    for attempt in range(Constants.MAX_ATTEMPTS):
        try:
            if FLAGS.ASYNC_MODE:
                # In async mode, use a dedicated browser instance and not the global one to avoid access conflicts
                browser = SilentBrowser(headless=not Constants.DEBUG_MODE,
                                        enable_javascript=True,
                                        wait_timeout=Constants.SILENT_BROWSER_TIMEOUT)
            else:
                # Sequential mode, use the global session
                if not hasattr(Utilities.SB, 'driver') or Utilities.SB.driver is None:
                    Utilities.SB.restart_browser(headless=not Constants.DEBUG_MODE, # Show browser when debugging
                                                enable_javascript=True, 
                                                wait_timeout=Constants.SILENT_BROWSER_TIMEOUT)
                browser = Utilities.SB
            
            # Navigate to page in the dedicated window
            if not browser.navigate_to(url):
                request.message = "Failed to navigate to page for historical data"
                request.success = False
                Utilities.add_attempt2msg(request, attempt)
                continue
            
            # Wait for page to fully load
            browser._random_delay(Constants.TASE_PAGELOAD_DELAYS[0], Constants.TASE_PAGELOAD_DELAYS[1])

            # Get security name
            name_element = browser.driver.find_element(By.XPATH, '/html/body/div[1]/div[4]/main/div/div[1]/div[1]/div/h2')
            if name_element:
                request.name = name_element.text.strip()
            else:
                request.message = "Failed to extract security name"
                request.success = False
                Utilities.add_attempt2msg(request, attempt)
                continue

            # Get expense rate
            expense_element = browser.driver.find_element(By.XPATH, '/html/body/div[1]/div[4]/main/div/div[1]/div[7]/div[2]/div[2]/div/table')
            if expense_element:
                expense_text        = expense_element.text
                expenseCategories   = { 'standard': ['ניהול', 0],
                                        'trustee': ['נאמן', 0],
                                        'trustee_diff': ['ניהול משתנים', 0],
                                        'trustee_actual': ['ניהול משתנים בפועל', 0]}

                for category, (label, _) in expenseCategories.items():
                    if label in expense_text:
                        match = re.search(r'דמי\s+' + label + r'\s+(\d+(?:\.\d+)?)', 
                                          expense_text)
                        expenseCategories[category][1] = float(match.group(1)) if match else 0.0

                request.expense_rate =  expenseCategories['standard'][1] + \
                                        expenseCategories['trustee'][1] + \
                                        max([expenseCategories['trustee_diff'][1],expenseCategories['trustee_actual'][1]])
            else:
                request.expense_rate = 0.0

            # Navigate graph to present the maximum timespan
            try:
                element = browser.driver.find_element(By.XPATH, "/html/body/div[1]/div[4]/main/div/div[1]/div[4]/div/div/ul/li[6]/button")

                if element and element.is_displayed() and element.is_enabled():
                    browser.driver.execute_script("arguments[0].click();", element)
                    browser._random_delay(Constants.TASE_CHART_DELAYS[0], Constants.TASE_CHART_DELAYS[1])
                else:
                    request.message = "Chart timespan button not available or not interactable"
                    request.success = False
                    Utilities.add_attempt2msg(request, attempt)
                    continue
            except Exception as e:
                request.message = f"Exception while finding chart timespan button: {str(e)}"
                request.success = False
                Utilities.add_attempt2msg(request, attempt)
                continue

            target_date = pd.to_datetime(request.date, dayfirst=True)
            try:
                # From this point we assume the max span is successfully pressed

                # Find target date
                date_element = browser.driver.find_element(By.XPATH, "/html/body/div[1]/div[4]/main/div/div[1]/div[4]/div/div/div/div[2]/div[1]/span[2]")
                price_element = browser.driver.find_element(By.XPATH, "/html/body/div[1]/div[4]/main/div/div[1]/div[4]/div/div/div/div[2]/div[2]/span[2]")
                datatip_container = browser.driver.find_element(By.CSS_SELECTOR, \
                                                                "#graph-year5 > div:nth-child(1) > svg > g:nth-child(1)") \
                                                                .find_elements(By.XPATH, "./*")
                
                # Initialize ActionChains before the loop
                actions = ActionChains(browser.driver)

                # For each element in container, figure the date (only the date)
                # Instead of extracting a date attribute, simulate hovering over each element
                # and read the date displayed in the UI (which updates dynamically)

                # Move to the earliest datatip in the chart
                actions.move_to_element(datatip_container[0]).perform()
                browser._random_delay(Constants.TASE_ELEMENT_DELAYS[0], Constants.TASE_ELEMENT_DELAYS[1])  # Allow UI to update

                current_date = pd.to_datetime(date_element.text, dayfirst=True)

                if current_date > target_date:
                    # Earliest date is after target date, searching is unnecessary
                    request.actual_date = current_date.strftime(Constants.THEMARKER_DATE_FORMAT)
                    request.fetched_price = float(price_element.text.replace(",", ""))/100.0
                    request.message = f"Target date {target_date.strftime(Constants.GENERAL_DATE_FORMAT)} is after available data. Using earliest available."

                    request.success = True
                    break
                else:
                    # Smart heuristic search with your original approach - much better than blind binary search!
                    N_DataTips = len(datatip_container)
                    span_delta_days = (date.today() - current_date.date()).days
                    min_delta_days = span_delta_days
                    
                    # Your brilliant heuristic: calculate proportional position based on date range
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
                        browser._random_delay(Constants.TASE_ELEMENT_DELAYS[0], Constants.TASE_ELEMENT_DELAYS[1])
                        
                        current_date = pd.to_datetime(date_element.text, dayfirst=True)
                        temp_delta_days = abs((current_date - target_date).days)
                        
                        # Update best match if closer
                        if temp_delta_days < min_delta_days:
                            min_delta_days      = temp_delta_days
                            best_match_date     = current_date.strftime(Constants.GENERAL_DATE_FORMAT)
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
                    request.message         = f"Found best match for target date {request.date} on date {request.actual_date}."

                    if not request.fetched_price:
                        request.message = "Could not extract price from chart"
                        request.success = False
                        Utilities.add_attempt2msg(request, attempt)
                        continue
                    
                    request.success = True
                    break
            except Exception as e:
                request.message = "Could not find any valid data points in chart"
                request.success = False
                Utilities.add_attempt2msg(request, attempt)
                continue
        except Exception as e:
            request.message = f"Error occurred while fetching historical data: {str(e)}"
            request.success = False
            Utilities.add_attempt2msg(request, attempt)