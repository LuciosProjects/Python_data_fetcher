import yfinance as yf
import pandas as pd
from datetime import timedelta  
import logging, warnings

import DataFetcher_Utilities as Utilities
from DataFetcher_Utilities import fetchRequest
import DataFetcher_Constants as Constants

# Suppress yfinance warnings and logging
logging.getLogger('yfinance').setLevel(logging.CRITICAL)
warnings.filterwarnings('ignore', category=FutureWarning, module='yfinance')

# Functions
def fetch_yfinance_data(requests: list[fetchRequest]):
    """
    Fetches data from Yahoo Finance for a given indicator and date.
    If exact date is not available, finds the closest available date.

    Args:
        requests (list[fetchRequest]): List of fetchRequest objects
        
    Returns:
        None
    """

    # Parse the target date
    try:
        target_date = pd.to_datetime(requests[0].date).date()
    except Exception as e:
        message = f"Invalid date format: {requests[0].date}. Error: {str(e)}"
        for request in requests:
            request.message = message
        return

    tickers = [request.indicator for request in requests]    
    try:
        tckrs = yf.Tickers(tickers)
    except:
        # Tickers object creation is not crucial to the function, so we can proceed without it
        message = "Failed to create Tickers object."

        for request in requests:
            request.message = message
        return

    for attempt in range(Constants.MAX_ATTEMPTS):
        # pause for a brief moment to avoid rate limiting
        Utilities.random_delay()

        try:
            # Try to get data around the target date (look back and forward)
            start_date = target_date - timedelta(days=Constants.INITIAL_DAYS_HALF_SPAN + attempt*Constants.HALF_SPAN_INCREMENT)
            end_date = target_date + timedelta(days=Constants.INITIAL_DAYS_HALF_SPAN + attempt*Constants.HALF_SPAN_INCREMENT)  # Look ahead a few days too
            
            response = yf.download(
                tickers, 
                start=start_date.strftime(Constants.YFINANCE_DATE_FORMAT), 
                end=end_date.strftime(Constants.YFINANCE_DATE_FORMAT),
                ignore_tz=True,
                progress=False,  # Suppress progress bar
                # auto_adjust=True  # Automatically adjust for splits and dividends 
                # (not needed since the default is already True)
            )

            if response is None or response.empty:
                # If no data available, set message and continue to next attempt
                message = f"No data available from {start_date} to {end_date}"
                continue

            if "Close" not in response:
                # No 'Close' data found in response
                continue

            # Store the results in the request object
            loop_failed = False
            for _, (symbol, data) in enumerate(response["Close"].items()):
                # Get matching request
                matched_request = None
                for req in requests:
                    if req.indicator == symbol:
                        matched_request = req
                        break

                if matched_request is None:
                    loop_failed = True
                    break  # try a larger date range

                # Find the closest date to our target
                closest_date = Utilities.find_closest_date(data, target_date)
                
                if closest_date is None:
                    # If no valid data found, set message and continue to next attempt
                    loop_failed = True
                    matched_request.message = f"No valid data found for {symbol} around {target_date}"
                    break
                else:
                    matched_request.actual_date = Utilities.safe_extract_date_string(closest_date)

                matched_request.fetched_price = Utilities.safe_extract_value(data.loc[closest_date])

                if tckrs.tickers[symbol] is not None:
                    matched_request.name = tckrs.tickers[symbol].info.get("longName","")  # Set the name to the ticker symbol
                    matched_request.expense_rate = tckrs.tickers[symbol].info.get("netExpenseRatio", 0.0)
                    # matched_request.currency = tckrs.tickers[symbol].info.get("currency", "")
                    matched_request.currency = 'USD'

                # Set success message
                closest_date_obj = pd.to_datetime(closest_date).date()
                if closest_date_obj == target_date:
                    matched_request.message = f"Data fetched for {symbol} on exact date {target_date}"
                else:
                    matched_request.message = f"Exact date {target_date} not available for {symbol}. Using closest date {closest_date_obj}"
                
                matched_request.success = True  # Mark as successful

            if not loop_failed:
                # If we successfully fetched data, break out of the loop
                return
        except Exception as e:
            message = f"Attempt {attempt + 1} failed: {str(e)}"
            if attempt < Constants.MAX_ATTEMPTS - 1:
                continue

    message = f"Failed to fetch yfinance data for after {Constants.MAX_ATTEMPTS} attempts"
    for request in requests:
        request.success = False
        request.message = message
