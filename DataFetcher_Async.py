"""
Async optimized data fetching for parallel processing of multiple indicators.
Optimized for Google Cloud Functions with proper resource management.
"""

import asyncio
from typing import List
import logging
import os

import DataFetcher_Utilities as Utilities
from DataFetcher_Utilities import fetchRequest, FLAGS

from DF_TheMarker import fetch_tase_fast, fetch_tase_historical
from DF_YFinance import fetch_yfinance_data

# Suppress warnings
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# Google Cloud Functions optimized settings
GCF_MAX_CONCURRENT = int(os.environ.get("GCF_MAX_CONCURRENT", "5"))  # Limit concurrent connections
GCF_TIMEOUT = int(os.environ.get("GCF_TIMEOUT", "30"))  # Shorter timeout for cloud
GCF_CONNECTOR_LIMIT = int(os.environ.get("GCF_CONNECTOR_LIMIT", "10"))  # Connection pool limit
    
# Async Caller Functions - Use Dedicated Browsers for True Parallelization
async def fetch_yfinance_data_async(requests: List[fetchRequest]) -> List[fetchRequest]:
    """
    Async caller for YFinance data fetching.
    """
    try:
        loop = asyncio.get_event_loop()
        # Run the sync YFinance function in executor (no browser needed)
        await loop.run_in_executor(None, fetch_yfinance_data, requests)

    except Exception as e:
        for request in requests:
            request.fetched_price = None
            request.success = False
            request.message = f"Error in async YFinance fetch: {str(e)}"

    return requests

async def fetch_tase_fast_price_async(request: fetchRequest) -> fetchRequest:
    """
    Async caller for TASE current price fetching using fast requests method.
    """
    try:
        loop = asyncio.get_event_loop()
        # Run the sync current price function in executor (no browser needed)
        await loop.run_in_executor(None, fetch_tase_fast, request)
    except Exception as e:
        request.success = False
        request.message = f"Error in async TASE current price fetch: {str(e)}"

    return request

async def fetch_tase_historical_data_async(request: fetchRequest) -> fetchRequest:
    """
    Async caller for TASE historical data with DEDICATED browser instance.
    Each call gets its own browser - no race conditions!
    """
    
    try:
        # Run the sync function in executor for true parallelism
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, fetch_tase_historical, request)
    except Exception as e:
        request.success = False
        request.message = f"Error in async TASE historical fetch: {str(e)}"

    return request

async def fetch_indicators_async(fetcher_data) -> List[fetchRequest]:
    """
    Async fetch multiple indicators in parallel.
    
    Args:
        fetcher_data: Dictionary containing indicators and date
        
    Returns:
        List of completed fetchRequest objects
    """
    

    # Categorize indicators
    N_indicators = len(fetcher_data["data"]["indicators"])
    results = [fetchRequest("")]*N_indicators # Initialize results with empty request objects

    # Classify indicators' fetch type
    fetch_types = Utilities.classify_fetch_types(fetcher_data["data"]["indicators"], fetcher_data["data"]["date"])
    YFinance_fetch_cache, TASE_Fast_fetch_cache, TASE_Historical_fetch_cache = Utilities.make_fetch_caches(fetcher_data, fetch_types)
    
    # Process async groups in parallel
    tasks = []
    
    # YFinance tasks (fully parallel)
    if FLAGS.NEED_YFINANCE:
        yf_requests = [YFinance_fetch_cache[i][1] for i in range(len(YFinance_fetch_cache))]
        task = asyncio.create_task(fetch_yfinance_data_async(yf_requests))
        tasks.append((None, task, 'yfinance'))

    # TASE fast tasks (fully parallel)
    if FLAGS.NEED_TASE_FAST:
        for idx, request in TASE_Fast_fetch_cache:
            task = asyncio.create_task(fetch_tase_fast_price_async(request))
            tasks.append((idx, task, 'tase_fast'))

    if FLAGS.NEED_HISTORICAL:
        for idx, request in TASE_Historical_fetch_cache:
            task = asyncio.create_task(fetch_tase_historical_data_async(request))
            tasks.append((idx, task, 'tase_historical'))
    
    # Await all async tasks to ensure completion (no need to gather results)
    if tasks:
        await asyncio.wait([task for _, task, _ in tasks])

    if FLAGS.NEED_YFINANCE:
        for i, request in YFinance_fetch_cache:
            results[i] = request

    if FLAGS.NEED_TASE_FAST:
        for i, request in TASE_Fast_fetch_cache:
            results[i] = request
    
    if FLAGS.NEED_HISTORICAL:
        for i, request in TASE_Historical_fetch_cache:
            results[i] = request

    return results

async def data_fetcher_manager_async(fetcher_data):
    """
    Async version of data_fetcher_manager with parallel processing.
    
    Args:
        fetcher_data: Dictionary containing indicators and date
        
    Returns:
        List of success flags for each indicator
    """
    
    # Fetch all indicators with async optimization
    requests = await fetch_indicators_async(fetcher_data)
    
    # Populate results
    fetch_success = []
    for request in requests:
        fetch_success.append(request.success)
        
        fetcher_data["data"]["fetched_prices"].append(request.fetched_price)
        fetcher_data["data"]["expense_rates"].append(request.expense_rate)
        fetcher_data["data"]["names"].append(request.name)
        fetcher_data["data"]["actual_dates"].append(request.actual_date)
        fetcher_data["data"]["currencies"].append(request.currency)
        fetcher_data["data"]["messages"].append(request.message)
    
    # Update overall status
    if any(not fetch for fetch in fetch_success):
        fetcher_data["status"] = "partial_success"
    elif all(not fetch for fetch in fetch_success):
        fetcher_data["status"] = "failed"

# Convenience function for easy integration
def run_async_data_fetch(fetcher_data):
    """
    Run async data fetching optimized for Google Cloud Functions.
    Always starts with a clean event loop to avoid conflicts.
    """

    # STEP 1: Clean up any existing loops aggressively
    try:
        # Check if there's an existing loop
        try:
            existing_loop = asyncio.get_event_loop()
            if existing_loop and not existing_loop.is_closed():
                # Cancel all pending tasks
                pending_tasks = asyncio.all_tasks(existing_loop)
                if pending_tasks:
                    for task in pending_tasks:
                        task.cancel()

                # Close the existing loop
                existing_loop.close()

        except RuntimeError:
            # No existing loop or already closed - this is fine
            pass
    except Exception as e:
        fetcher_data["status"] = "failed"
        fetcher_data["message"] = f"Error during loop cleanup: {e}"
        FLAGS.ASYNC_FAILED = True

    # Step 2: Create a fresh event loop for this invocation
    try:
        # Always create a new, clean event loop for GCF
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)

        # STEP 3: Run our async function with the clean loop
        try:
            new_loop.run_until_complete(data_fetcher_manager_async(fetcher_data))
        except Exception as e:
            fetcher_data["status"] = "failed"
            fetcher_data["message"] = f"Async execution failed: {e}"
            FLAGS.ASYNC_FAILED = True
    except Exception as e:
        fetcher_data["status"] = "failed"
        fetcher_data["message"] = f"Critical async error: {e}"
        FLAGS.ASYNC_FAILED = True
    finally:
        # Step 4: Clean up the event loop
        try:
            current_loop = asyncio.get_event_loop()
            if current_loop and not current_loop.is_closed():
                # Cancel any remaining tasks
                pending_tasks = asyncio.all_tasks(current_loop)
                if pending_tasks:
                    for task in pending_tasks:
                        task.cancel()

                # Close the existing loop
                current_loop.close()

        except Exception as e:
            fetcher_data["status"] = "failed"
            fetcher_data["message"] = f"Error during final cleanup: {e}"