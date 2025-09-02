"""
Async optimized data fetching for parallel processing of multiple indicators.
Optimized for Google Cloud Functions with proper resource management.
"""

import asyncio
from typing import List
import logging
import os
import pandas as pd

import DataFetcher_Utilities as Utilities
import DataFetcher_Constants as Constants
from DataFetcher_Utilities import fetchRequest, FLAGS

from DF_TheMarker import fetch_tase_fast, fetch_tase_historical
from DF_YFinance import fetch_yfinance_data

# Suppress warnings
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# Google Cloud Functions optimized settings
GCF_MAX_CONCURRENT = int(os.environ.get("GCF_MAX_CONCURRENT", "5"))  # Limit concurrent connections
GCF_TIMEOUT = int(os.environ.get("GCF_TIMEOUT", "30"))  # Shorter timeout for cloud
GCF_CONNECTOR_LIMIT = int(os.environ.get("GCF_CONNECTOR_LIMIT", "10"))  # Connection pool limit

# Override constants with environment variables if available (for Cloud Run tuning)
MAX_BROWSERS = min([int(os.environ.get("MAX_BROWSERS", str(Constants.MAX_CONCURRENT_BROWSERS))), Constants.MAX_CONCURRENT_BROWSERS])
MAX_REQUESTS = min([int(os.environ.get("MAX_REQUESTS", str(Constants.MAX_CONCURRENT_REQUESTS))), Constants.MAX_CONCURRENT_REQUESTS])

# Concurrency control semaphores - will be created fresh for each request to avoid event loop conflicts
    
# Async Caller Functions - Use Dedicated Browsers for True Parallelization
async def fetch_yfinance_data_async(requests: List[fetchRequest], request_semaphore: asyncio.Semaphore) -> List[fetchRequest]:
    """
    Async caller for YFinance data fetching.
    Limited by semaphore to control concurrent API requests.
    """

    async with request_semaphore:  # Limit concurrent API requests
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

async def fetch_tase_fast_price_async(request: fetchRequest, request_semaphore: asyncio.Semaphore) -> fetchRequest:
    """
    Async caller for TASE current price fetching using fast requests method.
    Limited by semaphore to control concurrent requests.
    """
    async with request_semaphore:  # Limit concurrent API requests
        try:
            loop = asyncio.get_event_loop()
            # Run the sync current price function in executor (no browser needed)
            await loop.run_in_executor(None, fetch_tase_fast, request)
        except Exception as e:
            request.success = False
            request.message = f"Error in async TASE current price fetch: {str(e)}"

    return request

async def fetch_tase_historical_data_async(request: fetchRequest, browser_semaphore: asyncio.Semaphore) -> fetchRequest:
    """
    Async caller for TASE historical data with DEDICATED browser instance.
    Limited by semaphore to control concurrent browser instances.
    """
    async with browser_semaphore:  # Limit concurrent browser instances
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
    Async fetch multiple indicators in parallel with concurrency limits.
    
    Args:
        fetcher_data: Dictionary containing indicators and date
        
    Returns:
        List of completed fetchRequest objects
    """

    # Create fresh semaphores for this request to avoid event loop conflicts
    request_semaphore = asyncio.Semaphore(MAX_REQUESTS)
    browser_semaphore = asyncio.Semaphore(MAX_BROWSERS)

    # Categorize indicators
    N_indicators = len(fetcher_data["data"]["indicators"])
    results = [fetchRequest("")]*N_indicators # Initialize results with empty request objects

    # Classify indicators' fetch type
    fetch_types = Utilities.classify_fetch_types(fetcher_data["data"]["indicators"], fetcher_data["data"]["date"])
    YFinance_fetch_cache, TASE_Fast_fetch_cache, TASE_Historical_fetch_cache = Utilities.make_fetch_caches(fetcher_data, fetch_types)

    # Debugging output
    print(f"fetch_indicators_async:")
    print(f"indicators: {fetcher_data['data']['indicators']}")
    print(f"fetch_types: {fetch_types}")
    print(f"Flags: yfinance: {FLAGS.NEED_YFINANCE}, tase_fast: {FLAGS.NEED_TASE_FAST}, tase_historical: {FLAGS.NEED_HISTORICAL}")


    # Process async groups in parallel
    tasks = []
    
    # YFinance tasks (single batch with all requests)
    if FLAGS.NEED_YFINANCE:
        yf_requests = [YFinance_fetch_cache[i][1] for i in range(len(YFinance_fetch_cache))]
        task = asyncio.create_task(fetch_yfinance_data_async(yf_requests, request_semaphore))
        tasks.append((None, task, 'yfinance_all'))

    # TASE fast tasks (fully parallel)
    if FLAGS.NEED_TASE_FAST:
        for idx, request in TASE_Fast_fetch_cache:
            task = asyncio.create_task(fetch_tase_fast_price_async(request, request_semaphore))
            tasks.append((idx, task, f'tase_fast_{request.indicator}'))

    if FLAGS.NEED_HISTORICAL:
        for idx, request in TASE_Historical_fetch_cache:
            request.date = pd.to_datetime(request.date).strftime(Constants.THEMARKER_DATE_FORMAT)

            task = asyncio.create_task(fetch_tase_historical_data_async(request, browser_semaphore))
            tasks.append((idx, task, f'tase_historical_{request.indicator}'))
    
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
    Uses simplified event loop management with proper cleanup.
    """
    
    created_new_loop = False
    
    try:
        # Try to get existing loop first
        try:
            loop = asyncio.get_running_loop()
            # If we're already in an event loop, we need to handle this differently
            # This shouldn't happen in Cloud Run but let's be safe
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, data_fetcher_manager_async(fetcher_data))
                future.result()
        except RuntimeError:
            # No running loop, which is the normal case for Cloud Run
            # Create and run our own loop
            created_new_loop = True
            asyncio.run(data_fetcher_manager_async(fetcher_data))
            
    except Exception as e:
        fetcher_data["status"] = "failed"
        fetcher_data["message"] = f"Async execution failed: {str(e)}"
        FLAGS.ASYNC_FAILED = True
    
    finally:
        # Clean up our own loop if we created one
        if created_new_loop:
            try:
                # Get the loop we just used (if it still exists)
                try:
                    current_loop = asyncio.get_event_loop()
                    
                    # Only clean up if it's not running (asyncio.run should have closed it)
                    if current_loop.is_closed():
                        # Loop is already closed by asyncio.run - good!
                        pass
                    else:
                        # Unusual case - clean up any remaining tasks
                        pending_tasks = [task for task in asyncio.all_tasks(current_loop) 
                                       if not task.done()]
                        if pending_tasks:
                            # Cancel only our remaining tasks
                            for task in pending_tasks:
                                task.cancel()
                        
                        # Let the loop finish cleanly
                        if not current_loop.is_closed():
                            current_loop.close()
                            
                except RuntimeError:
                    # No loop to clean up - this is fine
                    pass
                    
            except Exception as cleanup_error:
                # Don't let cleanup errors affect the main result
                # Just log it if we had logging
                pass