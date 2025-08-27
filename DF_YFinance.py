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
    Fetches data from Yahoo Finance for multiple indicators with efficient error handling.
    Progressively removes successfully processed indicators and continues with remaining ones.
    Falls back to inception date if target date is not available.

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
            request.success = False
        return

    for request in requests:
        # Initialize all requests success to false for retry logic
        request.success = False

    # Keep track of remaining requests to process (references to original requests)
    remaining_requests = [req for req in requests if not req.success]

    for attempt in range(Constants.MAX_ATTEMPTS):
        if not remaining_requests:
            break  # All requests have been processed
            
        # pause for a brief moment to avoid rate limiting
        Utilities.random_delay()

        # Get tickers for remaining requests
        remaining_tickers = [req.indicator for req in remaining_requests]
        N_tckrs = len(remaining_tickers)
        
        try:
            # Create Tickers object for remaining tickers
            tckrs = yf.Tickers(remaining_tickers)
        except Exception as e:
            message = f"Failed to create Tickers object: {str(e)}"
            for request in remaining_requests:
                request.message = message
                request.success = False
            return

        try:
            # Try to get data around the target date (look back and forward)
            start_date = target_date - timedelta(days=Constants.INITIAL_DAYS_HALF_SPAN + attempt*Constants.HALF_SPAN_INCREMENT)
            end_date = target_date + timedelta(days=Constants.INITIAL_DAYS_HALF_SPAN + attempt*Constants.HALF_SPAN_INCREMENT)
            
            response = yf.download(
                remaining_tickers, 
                start=start_date.strftime(Constants.YFINANCE_DATE_FORMAT), 
                end=end_date.strftime(Constants.YFINANCE_DATE_FORMAT),
                ignore_tz=True,
                progress=False,  # Suppress progress bar
                timeout=Constants.API_SINGLE_TICKER_TIMEOUT * N_tckrs,
                auto_adjust=True,  # Explicitly set to avoid warnings
                threads=True  # Enable multithreading for better performance
            )

            if response is None or response.empty or "Close" not in response:
                continue  # Try next attempt
            
            for symbol, data in response["Close"].items():
                # Find the corresponding request
                matched_request = None
                for req in remaining_requests:
                    if req.indicator == symbol:
                        matched_request = req
                        break

                if matched_request is None:
                    continue

                # Try to find data for target date
                closest_date = Utilities.find_closest_date(data, target_date)
                
                if closest_date is not None:
                    # Successfully found data for target date
                    process_successful_request(matched_request, data, closest_date, target_date, tckrs, symbol)
                else:
                    # No data for target date - try inception date approach
                    try_inception_date(matched_request, tckrs, symbol)

            # Remove successfully processed requests from remaining list
            remaining_requests = [req for req in requests if not req.success]

        except Exception as e:
            # Log the error and continue to next attempt
            continue

    # Mark any remaining unprocessed requests as failed
    # Note: We work with the original requests list to ensure all are handled
    for request in requests:
        if not request.success:
            request.message = f"Failed to fetch YFinance data after {Constants.MAX_ATTEMPTS} attempts"


def process_successful_request(request, data, closest_date, target_date, tckrs, symbol):
    """Process a request that has valid data."""
    request.actual_date = Utilities.safe_extract_date_string(closest_date)
    request.fetched_price = Utilities.safe_extract_value(data.loc[closest_date])

    # Try to get additional info safely
    if tckrs and hasattr(tckrs, 'tickers') and symbol in tckrs.tickers and tckrs.tickers[symbol] is not None:
        Utilities.extract_info_data(request, tckrs.tickers[symbol])

    # Set success message
    closest_date_obj = pd.to_datetime(closest_date).date()
    if closest_date_obj == target_date:
        request.message = f"Data fetched for {symbol} on exact date {target_date}"
    else:
        request.message = f"Exact date {target_date} not available for {symbol}. Using closest date {closest_date_obj}"
    
    request.success = True


def try_inception_date(request, tckrs, symbol):
    """Try to get the inception date (first available data) for a symbol."""
    try:
        if tckrs and hasattr(tckrs, 'tickers') and symbol in tckrs.tickers and tckrs.tickers[symbol] is not None:
            ticker = tckrs.tickers[symbol]
            
            # Get historical data for a very long period to find inception
            inception_data = ticker.history(period="max", auto_adjust=True)
            
            if not inception_data.empty:
                # Get the first available date
                inception_date = inception_data.index[0]
                first_price = inception_data['Close'].iloc[0]
                
                request.actual_date = Utilities.safe_extract_date_string(inception_date)
                request.fetched_price = Utilities.safe_extract_value(first_price)
                
                # Set additional info
                Utilities.extract_info_data(request, ticker)
                
                request.message = f"Target date not available for {symbol}. Using inception date {inception_date.date()}"
                request.success = True
    except Exception:
        pass
    
