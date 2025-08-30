from datetime import date

import json
from flask import Flask, request, jsonify

# To increase the timeout for a Google Cloud Function (GCF), you must set the "timeout" parameter when deploying the function.
# This cannot be set in code, but only via the deployment command or in the Google Cloud Console.
# Example (gcloud CLI):
# gcloud functions deploy python_data_fetch --timeout=540s ...
# The maximum allowed timeout for HTTP functions is 540 seconds (9 minutes).

import DataFetcher_Utilities as Utilities
import DataFetcher_Constants as Constants
from DataFetcher_Utilities import fetchRequest, FLAGS
from SilentBrowser import SilentBrowser

from DF_TheMarker import fetch_tase_fast, fetch_tase_historical
from DF_YFinance import fetch_yfinance_data

# Import async optimization
try:
    from DataFetcher_Async import run_async_data_fetch
    FLAGS.ASYNC_AVAILABLE = True # Set async availability
except ImportError:
    run_async_data_fetch = None  # Define for type checking
    print("Async optimization not available. Install aiohttp for faster performance: pip install aiohttp")

app = Flask(__name__)
@app.route('/', methods=['POST'])

def python_data_fetch():
    """
        This cloud function fetches financial data from outside of Google sheets
        and returns a JSON response.

        Input:
        - request: Flask Request object containing the JSON body with 'data'

        Output:
        - JSON response with a message
        
    """

    # Initialize output dictionary
    output = Utilities.initialize_output_dict()

    # Parse JSON body
    request_json = request.get_json(silent=True)
    
    if not request_json or "data" not in request_json:
        output["status"] = "error"
        output["status_code"] = 400
        output["message"] = "Invalid input structure. Expected format: {'data': {'indicators': [...], 'date': 'MM/DD/YYYY', ...}}"
        return jsonify(output)

    indicators = request_json["data"].get("indicators", [])
    target_date = request_json["data"].get("date", None)  # Optional date, if not provided, current date will be used

    output["data"]["indicators"] = indicators

    if target_date == None or target_date.strip() == "":
        output["data"]["date"] = date.today().strftime(Constants.GENERAL_DATE_FORMAT)  # Default to current date if not provided
    else:
        output["data"]["date"] = target_date

    # Main processing logic here
    data_fetcher_manager(output)

    # Prepare a JSON response
    # Check environment variable to determine if running in production
    if Constants.PRODUCTION:
        # In production (cloud), return jsonify directly
        return jsonify(output)
    else:
        # In development, you can use make_response for more control or debugging
        return json.dumps(output)


def collect_financial_data(**kwargs) -> dict:
    """
        This function collects financial data from various sources based on the indicators provided.

        Args:
            kwargs: Arbitrary keyword arguments containing:
                - indicators (list[str]): List of indicator names to fetch data for.
        
        Returns:
            dict: The output dictionary containing the fetched data or error messages.
    """

    # Initialize output dictionary
    output = Utilities.initialize_output_dict()

    data = kwargs.get("data", None)

    # Parse indicators from kwargs
    if data is not None:
        indicators = data.get("indicators", None)

        if indicators is not None:
            output["data"]["indicators"] = indicators
        else:
            output["status"] = "error"
            output["status_code"] = 400
            output["message"] = "Invalid input structure."

        # Parse target date from kwargs
        target_date = data.get("date", None)

        if target_date == None or target_date.strip() == "":
            output["data"]["date"] = date.today().strftime(Constants.GENERAL_DATE_FORMAT)  # Default to current date if not provided
        else:
            output["data"]["date"] = target_date

        data_fetcher_manager(output)
    else:
        output["status"] = "error"
        output["status_code"] = 400
        output["message"] = "Invalid input structure."

    return output


def data_fetcher_manager(fetcher_data):
    """
        This function manages the data fetching process and 
        updates the fetcher_data dictionary, given as input.

        Args:
            fetcher_data (dict): The data to be fetched.
        
        Returns:
            List of success flags. The fetcher data dictionary is passed by reference, 
            so any changes to it will be reflected outside this function.
    """

    # Try async optimization first if available and requested
    if Utilities.should_use_async_in_cloud(fetcher_data["data"]["indicators"]) and \
        FLAGS.ASYNC_AVAILABLE and run_async_data_fetch and not FLAGS.ASYNC_FAILED:

        FLAGS.ASYNC_MODE = True # Enable async mode
        try:
            run_async_data_fetch(fetcher_data)
            return
        except Exception as e:
            # Fall through to sequential processing
            print(f"Async processing failed, falling back to sequential: {str(e)}")

    N_indicators = len(fetcher_data["data"]["indicators"])
    results = [fetchRequest("")]*N_indicators # Initialize results with empty request objects

    # Classify indicators' fetch type
    fetch_types = Utilities.classify_fetch_types(fetcher_data["data"]["indicators"], fetcher_data["data"]["date"])
    YFinance_fetch_cache, TASE_Fast_fetch_cache, TASE_Historical_fetch_cache = Utilities.make_fetch_caches(fetcher_data, fetch_types)

    # Original sequential processing (fallback)
    fetch_success = [False]*len(fetcher_data["data"]["indicators"])

    # YFinance data fetching
    if FLAGS.NEED_YFINANCE:
        requests = [YFinance_fetch_cache[i][1] for i in range(len(YFinance_fetch_cache))]
        fetch_yfinance_data(requests)

        for i, request in enumerate(requests):
            results[YFinance_fetch_cache[i][0]] = request # overwrite previous result

    # TASE Fast data fetching
    if FLAGS.NEED_TASE_FAST:
        for i, request in TASE_Fast_fetch_cache:
            fetch_tase_fast(request)
            results[i] = request # overwrite previous result

    # Loop for TASE historical data fetching
    if FLAGS.NEED_HISTORICAL:
        for i, request in TASE_Historical_fetch_cache:
            fetch_tase_historical(request)
            results[i] = request # overwrite previous result
        
        if not FLAGS.ASYNC_MODE and Utilities.SB.is_open():
            Utilities.SB.close() # Close the browser if it's open

    # Assign results to fetcher_data
    for i, result in enumerate(results):
        fetcher_data["data"]["fetched_prices"].append(result.fetched_price) # Append fetched price
        fetcher_data["data"]["expense_rates"].append(result.expense_rate) # Append expense rate
        fetcher_data["data"]["names"].append(result.name) # Append security name
        fetcher_data["data"]["actual_dates"].append(result.actual_date) # Append actual date
        fetcher_data["data"]["currencies"].append(result.currency) # Append currency
        fetcher_data["data"]["messages"].append(result.message) # Append status message
        fetch_success[i] = result.success

    if any(not fetch for fetch in fetch_success):
        fetcher_data["status"] = "partial_success"
    elif all(not fetch for fetch in fetch_success):
        fetcher_data["status"] = "failed"
