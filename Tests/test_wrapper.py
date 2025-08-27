"""
Test wrapper for the python_data_fetcher Google Cloud Function.
This allows you to test your function locally before deploying.
"""

import sys, pathlib
sys.path.append(str(pathlib.Path(__file__).parent.parent))

import json
from datetime import date
import timeit
import asyncio
import gc
import random
import requests
import threading
import time

random.seed(0) # Set seed for reproducibility

from unittest.mock import Mock, MagicMock
from main import collect_financial_data, app

import DataFetcher_Constants as Constants

def prepare_test_data(test_data):
    """Prepare test data for direct function call (no mock request needed)."""
    return test_data["data"]

class TestDataConstructor:
    """Centralized test data constructor for security indicators."""
    
    # Define security indicators
    US_SYMBOLS = ["GOOG", "SCHD", "NVDA", "VOO", "DGRO", "JEPI", "IBIT", "IAU"]
    EUROPEAN_SYMBOLS = ['ASML', 'SAP', 'NESN.SW', 'ROG.SW', 'NOVN.SW', 'MC.PA', 'OR.PA', 'SAN.PA', 'INGA.AS', 'SIE.DE']
    TASE_INDICATORS = ["5138094", "1104249", "1144633", "1183441", \
                        "5111422", "5117379", "1159094", "1159169", "1186063"]
    FIFTY_INDICATORS = [ 
        # Major US Tech Stocks (10)
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'NVDA', 'NFLX', 'ADBE', 'CRM',

        # US Financial Sector (5)
        'JPM', 'BAC', 'WFC', 'GS', 'MS',

        # US Healthcare & Pharma (5)
        'JNJ', 'PFE', 'UNH', 'ABBV', 'MRK',

        # US Energy & Utilities (5)
        'XOM', 'CVX', 'COP', 'EOG', 'SLB',

        # US Consumer & Retail (5)
        'WMT', 'HD', 'PG', 'KO', 'PEP',

        # Israeli Stocks - Tel Aviv Stock Exchange (10)
        '1144633', '1081124', '126.1.CHKP', '273011', '746016', '1100007', '695437', '1119478', '126.1.FSLR', '1101534',

        # European Stocks (5)
        'ASML', 'SAP', 'NESN.SW', 'ROG.SW', 'NOVN.SW',

        # Asian Stocks (5)
        'TSM', 'BABA', 'JD', 'NIO', 'BIDU'
    ]

    @classmethod
    def create_test_data(cls, data_type="missing", how_many_each=None, random_choice=True, custom_indicators=None, targetDate=None, **kwargs):
        """
        Create test data for different scenarios.
        
        Args:
            data_type (str): Type of test data to create
                - "us": Only US stock symbols
                - "eu": Only EU stock symbols
                - "tase": Only TASE indicators  
                - "mixed": Mix of US symbols and TASE indicators
                - "custom": Use custom_indicators parameter
                - "empty": Empty indicators array
                - "missing": No 'indicators' field (wrong structure)
            how_many_each (int): Number of each type of indicator to include (default: None, indicating all)
            custom_indicators (list): Custom list of indicators (used with data_type="custom")
            date (str): Target date for data fetching (format: YYYY-MM-DD)
            **kwargs: Additional optional data features
        
        Returns:
            dict: JSON structure with 'data' field containing the request data
        """

        # Default to current date if not provided
        if not targetDate:
            targetDate = date.today().strftime("%m/%d/%Y") 

        # Base data structure
        base_data = {
            "indicators": [],
            "date": targetDate
        }

        if random_choice:
            GET_LIST = lambda indicatorList: random.sample(indicatorList, how_many_each) if how_many_each is not None else indicatorList
        else:
            GET_LIST = lambda indicatorList: indicatorList[:how_many_each] if how_many_each is not None else indicatorList

        # Add any additional features passed via kwargs
        base_data.update(kwargs)
        
        if data_type == "us":
            base_data["indicators"] = GET_LIST(cls.US_SYMBOLS)  # All US symbols

        elif data_type == "tase":
            base_data["indicators"] = GET_LIST(cls.TASE_INDICATORS)

        elif data_type == "eu":
            base_data["indicators"] = GET_LIST(cls.EUROPEAN_SYMBOLS)

        elif data_type == "mixed":
            # Interleave US symbols and TASE indicators
            us_symbols      = GET_LIST(cls.US_SYMBOLS)
            eu_symbols      = GET_LIST(cls.EUROPEAN_SYMBOLS)
            tase_indicators = GET_LIST(cls.TASE_INDICATORS)

            mixed_list = us_symbols + eu_symbols + tase_indicators

            # Shuffle the mixed list
            random.shuffle(mixed_list)

            base_data["indicators"] = mixed_list
        
        elif data_type == "custom" and custom_indicators:
            base_data["indicators"] = custom_indicators

            if random_choice:
                random.shuffle(base_data["indicators"])

        elif data_type == "empty":
            base_data["indicators"] = []
        
        elif data_type == "missing":
            # Wrong structure - missing 'indicators' field, using old 'data' field
            return {"data": cls.US_SYMBOLS[:2], "date": targetDate}
        
        else:
            # Default to mixed
            return cls.create_test_data("mixed", targetDate=targetDate, **kwargs)

        # Wrap in 'data' field as expected by the function
        return {"data": base_data}
    
    @classmethod
    def get_example_data(cls):
        """Get example data for interactive testing."""
        return {
            "US Symbols": cls.create_test_data("us", targetDate="01/15/2024"),
            "European Symbols": cls.create_test_data("eu", targetDate="01/16/2024"),
            "TASE Numbers": cls.create_test_data("tase", targetDate="01/17/2024"),
            "Mixed List": cls.create_test_data("mixed", targetDate="01/18/2024"),
            "Custom Example": cls.create_test_data("custom", 
                                                 custom_indicators=["AAPL", "5138094", "GOOGL"], 
                                                 targetDate="01/19/2024",
                                                 market="mixed")
        }


def test_function_with_valid_data():
    """Test the function with valid security indicators."""
    print("Testing with valid security indicators...")
    
    # Use TestDataConstructor to create mixed test data with specific date
    test_data = TestDataConstructor.create_test_data("mixed", targetDate="01/15/2024")
    
    data = prepare_test_data(test_data)
    response = collect_financial_data(**data)

    print(f"Indicators: {test_data['data']['indicators']}")
    print(f"Date: {test_data['data']['date']}")
    print(f"Response: {response}")
    print("-" * 50)


def test_function_with_missing_data():
    """Test the function with missing 'indicators' field."""
    print("Testing with missing 'indicators' field...")
    
    # Use TestDataConstructor to create invalid test data
    test_data = TestDataConstructor.create_test_data("missing", targetDate="15/01/2024")

    data = prepare_test_data(test_data)
    response = collect_financial_data(**data)
    
    print(f"Request Data: {test_data}")
    print(f"Response: {response}")
    print("-" * 50)


def test_function_with_empty_request():
    """Test the function with empty request."""
    print("Testing with empty request...")
    
    # Create empty request data
    response = collect_financial_data()
    
    print(f"Response: {response}")
    print("-" * 50)


def test_function_with_tase_indicators():
    """Test the function with Israeli TASE numeric indicators."""
    print("Testing with Israeli TASE numeric indicators...")
    
    # Use TestDataConstructor to create TASE-only test data with today's date
    test_data = TestDataConstructor.create_test_data("tase_only", targetDate=date.today().strftime("%m/%d/%Y"))

    start_time = timeit.default_timer()
    data = prepare_test_data(test_data)
    response = collect_financial_data(**data)
    end_time = timeit.default_timer()

    print(f"TASE Indicators: {test_data['data']['indicators']}")
    print(f"Date: {test_data['data']['date']}")
    print(f"Response: {response}")
    print(f"Time taken: {end_time - start_time} seconds")
    print("-" * 50)

    # Use TestDataConstructor to create TASE-only test data with different date
    test_data = TestDataConstructor.create_test_data("tase_only", targetDate="01/16/2024")

    start_time = timeit.default_timer()
    data = prepare_test_data(test_data)
    response = collect_financial_data(**data)
    end_time = timeit.default_timer()

    print(f"TASE Indicators: {test_data['data']['indicators']}")
    print(f"Date: {test_data['data']['date']}")
    print(f"Response: {response}")
    print(f"Time taken: {end_time - start_time} seconds")
    print("-" * 50)


def test_function_with_mixed_indicators():
    """Test the function with mixed US symbols and TASE numeric indicators in one list."""
    print("Testing with mixed US symbols and TASE indicators in one list...")
    
    skip_today = False  # Skip today's date for this test

    if not skip_today:
        # Use TestDataConstructor to create mixed test data with today's date
        test_data = TestDataConstructor.create_test_data("mixed", targetDate=date.today().strftime("%m/%d/%Y"))

        start_time = timeit.default_timer()
        data = prepare_test_data(test_data)
        response = collect_financial_data(**data)
        end_time = timeit.default_timer()

        # Response is already a dict, no need to parse JSON
        try:
            parsed_response = response
        except Exception as e:
            print(f"❌ Error parsing response: {str(e)}")
            return
        
        print(f"fetcher status - {parsed_response['status']}")
        print(f"fetcher status code - {parsed_response['status_code']}")
        print(f"{parsed_response['message']}\n")

        data = parsed_response.get('data', None)
        if data:
            print(f"Required date: {data['date']}")
            N_indicators = len(data.get('indicators', []))

            indicators = data.get('indicators', [])
            names = data.get('names', [])
            fetched_prices = data.get('fetched_prices', [])
            expense_rates = data.get('expense_rates', [])
            actual_dates = data.get('actual_dates', [])
            currencies = data.get('currencies', [])
            messages = data.get('messages', [])

            for i in range(N_indicators):
                print(f"📈 Indicator: {indicators[i]}")
                print(f"   Name: {names[i]}")
                print(f"   Fetched Price: {fetched_prices[i]}")
                print(f"   Expense Rate: {expense_rates[i]}")
                print(f"   Actual Date: {actual_dates[i]}")
                print(f"   Currency: {currencies[i]}")
                print(f"   Message: {messages[i]}")
                print()

        print(f"Time taken: {end_time - start_time} seconds")
        print("-" * 50)

    # Use TestDataConstructor to create mixed test data with weekend date
    test_data = TestDataConstructor.create_test_data("mixed", targetDate="01/20/2024")
    
    start_time = timeit.default_timer()
    data = prepare_test_data(test_data)
    response = collect_financial_data(**data)
    end_time = timeit.default_timer()

    # Response is already a dict, no need to parse JSON
    try:
        parsed_response = response
    except Exception as e:
        print(f"❌ Error parsing response: {str(e)}")
        return
        
    print(f"fetcher status - {parsed_response['status']}")
    print(f"fetcher status code - {parsed_response['status_code']}")
    print(f"{parsed_response['message']}\n")

    data = parsed_response.get('data', None)
    if data:
        print(f"Required date: {data['date']}")
        N_indicators = len(data.get('indicators', []))

        indicators = data.get('indicators', [])
        names = data.get('names', [])
        fetched_prices = data.get('fetched_prices', [])
        expense_rates = data.get('expense_rates', [])
        actual_dates = data.get('actual_dates', [])
        messages = data.get('messages', [])

        for i in range(N_indicators):
            print(f"📈 Indicator: {indicators[i]}")
            print(f"   Name: {names[i]}")
            print(f"   Fetched Price: {fetched_prices[i]}")
            print(f"   Expense Rate: {expense_rates[i]}")
            print(f"   Actual Date: {actual_dates[i]}")
            print(f"   Message: {messages[i]}")
            print()

    print(f"Time taken: {end_time - start_time} seconds")
    print("-" * 50)

def test_function_with_us_only():
    """Test the function with US symbols only."""
    print("Testing with US symbols only...")
    
    # Use TestDataConstructor to create US-only test data with recent date
    test_data = TestDataConstructor.create_test_data("us_only", targetDate="01/15/2024")
    
    data = prepare_test_data(test_data)
    response = collect_financial_data(**data)
    
    print(f"US Symbols: {test_data['data']['indicators']}")
    print(f"Date: {test_data['data']['date']}")
    print(f"Response: {response}")
    print("-" * 50)


def test_function_with_empty_data():
    """Test the function with empty indicators array."""
    print("Testing with empty indicators array...")
    
    # Use TestDataConstructor to create empty test data
    test_data = TestDataConstructor.create_test_data("empty", targetDate="01/18/2024")
    
    data = prepare_test_data(test_data)
    response = collect_financial_data(**data)
    
    print(f"Empty Indicators: {test_data['data']['indicators']}")
    print(f"Date: {test_data['data']['date']}")
    print(f"Response: {response}")
    print("-" * 50)


def test_specific_tase_historical():
    """Test specific TASE securities with parallel processing - multiple breakpoints!"""
    print("Testing multiple TASE historical data with parallel processing...")
    
    # Multiple TASE indicators to test parallel async processing
    # 5117379: Expected March 8th, 2022 at 1.0944 ILS
    # 5138094: Another TASE security for parallel testing
    test_data = {
        "data": {
            "indicators": ["5117379", "1104249"],  # Multiple indicators for parallel processing
            "date": "03/05/2022"  # March 5th, 2022 (weekend)
        }
    }
    
    start_time = timeit.default_timer()
    data = prepare_test_data(test_data)
    response = collect_financial_data(**data)
    end_time = timeit.default_timer()
    
    print(f"TASE Indicators: {test_data['data']['indicators']}")
    print(f"Target Date: {test_data['data']['date']} (March 5th, 2022)")
    print(f"Expected for 5117379: March 8th, 2022 at 1.0944 ILS")
    print(f"Expected for 1104249: Some historical price (not validated)")
    print(f"Time taken: {end_time - start_time:.2f} seconds")
    print("👀 Watch for multiple browser windows and breakpoint hits!")
    
    # Parse response to check results
    try:
        # The function returns a dict directly now, not a JSON string
        if isinstance(response, dict):
            result = response
            data = result.get('data', {})
            
            if data.get('fetched_prices') and len(data['fetched_prices']) > 0:
                print(f"📊 RESULTS FOR ALL INDICATORS:")
                
                for i, indicator in enumerate(data.get('indicators', [])):
                    fetched_price = data['fetched_prices'][i] if i < len(data['fetched_prices']) else None
                    actual_date = data['actual_dates'][i] if i < len(data['actual_dates']) else None
                    security_name = data['names'][i] if i < len(data['names']) else None
                    message = data['messages'][i] if i < len(data['messages']) else None
                    
                    print(f"\n   Indicator {indicator}:")
                    print(f"     Security Name: {security_name}")
                    print(f"     Actual Date Found: {actual_date}")
                    print(f"     Fetched Price: {fetched_price} ILS")
                    print(f"     Message: {message}")
                
                # Validate only the first indicator (5117379)
                if len(data['fetched_prices']) > 0:
                    first_fetched_price = data['fetched_prices'][0]
                    first_actual_date = data['actual_dates'][0]
                    
                    # Validation for first indicator only
                    expected_price = 1.0944
                    expected_date = "08/03/2022"  # March 8th in DD/MM/YYYY format
                    
                    price_match = abs(first_fetched_price - expected_price) < 0.001 if first_fetched_price else False
                    date_match = first_actual_date == expected_date
                    
                    print(f"\n✅ VALIDATION FOR 5117379 ONLY:")
                    print(f"   Price Match (±0.001): {'✅ PASS' if price_match else '❌ FAIL'}")
                    print(f"   Date Match: {'✅ PASS' if date_match else '❌ FAIL'}")
                    
                    if price_match and date_match:
                        print(f"🎉 PERFECT MATCH for 5117379! Parallel processing working!")
                    else:
                        print(f"⚠️  5117379 differs from expected values, but parallel processing still worked!")
            else:
                print(f"❌ No price data retrieved")
        else:
            print(f"❌ Response is not a dict: {type(response)}")
            
    except Exception as e:
        print(f"❌ Error parsing response: {e}")
    
    print(f"Response Status: {response.get('status', 'N/A')}")
    print("-" * 50)


def test_function_with_custom_data():
    """Test the function with custom security indicators and additional features."""
    print("Testing with custom security indicators and additional features...")
    
    # Use TestDataConstructor with custom data and additional features
    custom_indicators = ["AAPL", "5138094", "NVDA"]
    test_data = TestDataConstructor.create_test_data(
        "custom", 
        custom_indicators=custom_indicators,
        targetDate="01/19/2024",
        market="mixed",
        request_type="historical",
        currency="USD"
    )
    
    data = prepare_test_data(test_data)
    response = collect_financial_data(**data)
    
    print(f"Custom Indicators: {test_data['data']['indicators']}")
    print(f"Date: {test_data['data']['date']}")
    print(f"Additional Features: {dict((k, v) for k, v in test_data['data'].items() if k not in ['indicators', 'date'])}")
    print(f"Response: {response}")
    print("-" * 50)

def test_function_with_large_custom_data():
    """Test the function with custom security indicators and additional features."""
    print("Testing with custom security indicators and additional features...")
    
    SpacerLen = 30

    # # Test alot of symbols for today's price
    # test_data = TestDataConstructor.create_test_data("custom", 
    #     custom_indicators=TestDataConstructor.FIFTY_INDICATORS,
    # )

    # print("=" * SpacerLen + " Starting http request " + "=" * SpacerLen)
    # test_http_post_request(test_data)
    # print("=" * SpacerLen + " Finished http request " + "=" * SpacerLen)

    # Test alot of symbols for historical price
    test_data = TestDataConstructor.create_test_data("custom", 
        custom_indicators=TestDataConstructor.FIFTY_INDICATORS,
        targetDate="05/20/2000",
    )

    print("=" * SpacerLen + " Starting http request " + "=" * SpacerLen)
    test_http_post_request(test_data)
    print("=" * SpacerLen + " Finished http request " + "=" * SpacerLen)

    print("=" * SpacerLen + " Test End " + "=" * SpacerLen)

def test_function_with_european_stocks():
    """Test the function with European stock symbols only."""
    print("Testing with European stock symbols only...")
    
    # Use TestDataConstructor to create European-only test data
    test_data = TestDataConstructor.create_test_data("eu")
    
    start_time = timeit.default_timer()
    data = prepare_test_data(test_data)
    response = collect_financial_data(**data)
    end_time = timeit.default_timer()
    
    print(f"European Symbols: {test_data['data']['indicators']}")
    print(f"Date: {test_data['data']['date']}")
    print(f"Time taken: {end_time - start_time:.2f} seconds")
    
    # Parse and display response
    if isinstance(response, dict):
        print(f"Status: {response.get('status', 'N/A')}")
        print(f"Message: {response.get('message', 'N/A')}")
        
        data_response = response.get('data', {})
        if data_response:
            indicators = data_response.get('indicators', [])
            names = data_response.get('names', [])
            fetched_prices = data_response.get('fetched_prices', [])
            actual_dates = data_response.get('actual_dates', [])
            currencies = data_response.get('currencies', [])
            messages = data_response.get('messages', [])
            
            print(f"\n📊 RESULTS FOR EUROPEAN STOCKS:")
            for i, indicator in enumerate(indicators):
                print(f"📈 {indicator}:")
                print(f"   Name: {names[i]}")
                print(f"   Price: {fetched_prices[i]}")
                print(f"   Currency: {currencies[i]}")
                print(f"   Date: {actual_dates[i]}")
                print(f"   Message: {messages[i]}")
                print()
    else:
        print(f"Response: {response}")
    
    print("-" * 50)

def test_multiple_sequential_calls():
    """Test multiple sequential calls to ensure no async loop conflicts."""
    print("Testing multiple sequential calls...")
    
    test_cases = [
        ("US Symbols", TestDataConstructor.create_test_data("us", targetDate="01/15/2024")),
        ("European Symbols", TestDataConstructor.create_test_data("eu", targetDate="01/16/2024")),
        ("TASE Indicators", TestDataConstructor.create_test_data("tase", targetDate="01/17/2024")),
        ("Mixed Indicators", TestDataConstructor.create_test_data("mixed", targetDate="01/18/2024"))
    ]
    
    for test_name, test_data in test_cases:
        print(f"\n--- Testing {test_name} ---")
        start_time = timeit.default_timer()
        
        try:
            data = prepare_test_data(test_data)
            response = collect_financial_data(**data)
            end_time = timeit.default_timer()
            
            print(f"✅ {test_name} - Success")
            print(f"   Indicators: {test_data['data']['indicators']}")
            print(f"   Time taken: {end_time - start_time:.2f} seconds")
            print(f"   response: {response}")
            
        except Exception as e:
            end_time = timeit.default_timer()
            print(f"❌ {test_name} - Failed: {str(e)}")
            print(f"   Time taken: {end_time - start_time:.2f} seconds")
    
    print("\n" + "="*50)
    print("Multiple sequential calls test completed!")


def test_tase_current_price_only():
    """Test TASE current price fetching specifically (fast method)"""
    print("\n" + "="*60)
    print("🚀 TESTING: TASE Current Price (Fast Method)")
    print("="*60)

    # Test data for current/today's price (no date = current/today's price)
    test_data = TestDataConstructor.create_test_data("tase_only", targetDate="")
    
    start_time = timeit.default_timer()
    
    try:
        data = prepare_test_data(test_data)
        response = collect_financial_data(**data)
        
        end_time = timeit.default_timer()
        execution_time = end_time - start_time

        # Response is already a dict, no need to parse JSON
        try:
            parsed_response = response
        except Exception as e:
            print(f"❌ Error parsing response: {str(e)}")
            return

        print(f"fetcher status - {parsed_response['status']}")
        print(f"fetcher status code - {parsed_response['status_code']}")
        print(f"{parsed_response['message']}\n")

        data = parsed_response.get('data', None)
        if data:
            print(f"Required date: {data['date']}")
            N_indicators = len(data.get('indicators', []))

            indicators = data.get('indicators', [])
            names = data.get('names', [])
            fetched_prices = data.get('fetched_prices', [])
            expense_rates = data.get('expense_rates', [])
            actual_dates = data.get('actual_dates', [])
            messages = data.get('messages', [])

            for i in range(N_indicators):
                print(f"📈 Indicator: {indicators[i]}")
                print(f"   Name: {names[i]}")
                print(f"   Fetched Price: {fetched_prices[i]}")
                print(f"   Expense Rate: {expense_rates[i]}")
                print(f"   Actual Date: {actual_dates[i]}")
                print(f"   Message: {messages[i]}")
                print()

        print(f"\n⏱️  Execution time: {execution_time:.2f} seconds")
                    
    except Exception as e:
        print(f"❌ Exception occurred: {str(e)}")
    
    print("\n" + "="*50)
    print("TASE current price test completed!")


def test_tase_historical_only():
    """Test TASE historical data fetching specifically (Selenium method)"""
    print("\n" + "="*60)
    print("🚀 TESTING: TASE Historical Data (Selenium Method)")
    print("="*60)
    
    # Test data for historical price
    test_data = TestDataConstructor.create_test_data("custom", \
                custom_indicators=["5138094", "1186063", "1104249", "1144633"], \
                targetDate="01/05/2021")
    # Handpicked securities for TASE historical data fetching
    
    start_time = timeit.default_timer()
    
    try:
        data = prepare_test_data(test_data)
        response = collect_financial_data(**data)
        
        end_time = timeit.default_timer()
        execution_time = end_time - start_time
        
        # Response is already a dict, no need to parse JSON
        try:
            parsed_response = response
        except Exception as e:
            print(f"❌ Error parsing response: {str(e)}")
            return

        print(f"fetcher status - {parsed_response['status']}")
        print(f"fetcher status code - {parsed_response['status_code']}")
        print(f"{parsed_response['message']}\n")

        data = parsed_response.get('data', None)
        if data:
            print(f"Required date: {data['date']}")
            N_indicators = len(data.get('indicators', []))

            indicators = data.get('indicators', [])
            names = data.get('names', [])
            fetched_prices = data.get('fetched_prices', [])
            expense_rates = data.get('expense_rates', [])
            actual_dates = data.get('actual_dates', [])
            messages = data.get('messages', [])

            for i in range(N_indicators):
                print(f"📈 Indicator: {indicators[i]}")
                print(f"   Name: {names[i]}")
                print(f"   Fetched Price: {fetched_prices[i]}")
                print(f"   Expense Rate: {expense_rates[i]}")
                print(f"   Actual Date: {actual_dates[i]}")
                print(f"   Message: {messages[i]}")
                print()

        print(f"\n⏱️  Execution time: {execution_time:.2f} seconds")
                    
    except Exception as e:
        print(f"❌ Exception occurred: {str(e)}")
    
    print("\n" + "="*50)
    print("TASE historical data test completed!")


def test_yfinance_only():
    """Test YFinance data fetching specifically"""
    print("\n" + "="*60)
    print("🚀 TESTING: YFinance Data (API Method)")
    print("="*60)
    
    # Test data for YFinance
    test_data = TestDataConstructor.create_test_data("us", targetDate="01/01/2024")
    
    start_time = timeit.default_timer()
    
    try:
        data = prepare_test_data(test_data)
        response = collect_financial_data(**data)
        
        end_time = timeit.default_timer()
        execution_time = end_time - start_time
        
        print(f"\n⏱️  Execution time: {execution_time:.2f} seconds")
        print(f"📊 Response: {response}")
        
        print(f"✅ YFinance data test completed successfully!")
        print(f"🔍 Request data: {test_data['data']['indicators']}")
        print(f"📅 Target date: {test_data['data']['date']}")
                    
    except Exception as e:
        print(f"❌ Exception occurred: {str(e)}")
    
    print("\n" + "="*50)
    print("YFinance data test completed!")


def start_flask_server():
    """Start Flask server in a separate thread for testing."""
    try:
        app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False, threaded=True)
    except Exception as e:
        print(f"❌ Flask server error: {e}")


def test_http_post_request(test_data = None):
    """Test the Flask app via HTTP POST request."""
    print("\n" + "="*60)
    print("🌐 TESTING: HTTP POST Request to Flask Server")
    print("="*60)
    
    # Start Flask server in background thread
    server_thread = threading.Thread(target=start_flask_server, daemon=True)
    server_thread.start()
    
    # Wait for server to start and check if it's responding
    url = "http://127.0.0.1:5000/"
    max_retries = 10
    server_ready = False
    
    for i in range(max_retries):
        try:
            # Simple health check - try to connect
            response = requests.get("http://127.0.0.1:5000/", timeout=1)
            server_ready = True
            break
        except:
            print(f"⏳ Waiting for server to start... ({i+1}/{max_retries})")
            time.sleep(0.5)
    
    if not server_ready:
        print("❌ Failed to start Flask server")
        return
    
    # Test data
    if test_data == None:
        test_data = TestDataConstructor.create_test_data("mixed", 
                                                         targetDate="01/15/2024", 
                                                         how_many_each=3)

    # Flask endpoint URL
    url = "http://127.0.0.1:5000/"
    
    try:
        print(f"🚀 Sending POST request to {url}")
        print(f"📊 Request data: {test_data}")
        
        start_time = timeit.default_timer()
        
        # Calculate timeout based on number of indicators
        api_timeout = len(test_data['data']['indicators']) * 20.0

        # Send POST request
        response = requests.post(
            url, 
            headers={'Content-Type': 'application/json'},
            json=test_data,
            timeout=api_timeout
        )
        
        end_time = timeit.default_timer()
        execution_time = end_time - start_time
        
        print(f"\n✅ HTTP Response received!")
        print(f"📈 Status Code: {response.status_code}")
        print(f"⏱️  Execution time: {execution_time:.2f} seconds")
        
        if response.status_code == 200:
            try:
                response_data = response.json()
                
                # Validate response structure
                if 'status' in response_data and 'data' in response_data:
                    print(f"✅ Response structure is valid")
                    print(f"🔍 Status: {response_data['status']}")
                    print(f"🔍 Message: {response_data.get('message', 'N/A')}")

                    for i, indicator in enumerate(response_data['data']['indicators']):
                        print(f"  - Indicator: {indicator}")
                        print(f"  - name: {response_data['data']['names'][i]}")
                        print(f"  - price: {response_data['data']['fetched_prices'][i]}")
                        print(f"  - expense_rate: {response_data['data']['expense_rates'][i]}")
                        print(f"  - actual_date: {response_data['data']['actual_dates'][i]}")
                        print(f"  - currency: {response_data['data']['currencies'][i]}")
                        print(f"  - message: {response_data['data']['messages'][i]}\n")
                else:
                    print(f"❌ Response structure is invalid")
                    
            except json.JSONDecodeError as e:
                print(f"❌ Failed to parse JSON response: {e}")
                print(f"📄 Raw response: {response.text}")
        else:
            print(f"❌ HTTP request failed with status {response.status_code}")
            print(f"📄 Response text: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print(f"❌ Failed to connect to Flask server at {url}")
        print(f"💡 Make sure the server is running")
    except requests.exceptions.Timeout:
        print(f"❌ Request timed out after 30 seconds")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    
    print("\n" + "="*50)
    print("HTTP POST request test completed!")


def test_http_post_multiple_requests():
    """Test multiple HTTP POST requests to check server stability."""
    print("\n" + "="*60)
    print("🌐 TESTING: Multiple HTTP POST Requests")
    print("="*60)
    
    # Start Flask server in background thread
    server_thread = threading.Thread(target=start_flask_server, daemon=True)
    server_thread.start()
    
    # Wait for server to start
    time.sleep(2)
    
    url = "http://127.0.0.1:5000/"
    
    test_cases = [
        ("US Only", TestDataConstructor.create_test_data("us_only", targetDate="01/15/2024")),
        ("TASE Only", TestDataConstructor.create_test_data("tase_only", targetDate="01/16/2024")),
        ("Mixed", TestDataConstructor.create_test_data("mixed", targetDate="01/17/2024"))
    ]
    
    for test_name, test_data in test_cases:
        print(f"\n--- Testing {test_name} ---")
        
        try:
            start_time = timeit.default_timer()
            
            response = requests.post(
                url, 
                json=test_data,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            end_time = timeit.default_timer()
            execution_time = end_time - start_time
            
            if response.status_code == 200:
                print(f"✅ {test_name} - Success (Status: {response.status_code})")
                print(f"⏱️  Time: {execution_time:.2f} seconds")
                
                try:
                    response_data = response.json()
                    print(f"📊 Status: {response_data.get('status', 'N/A')}")
                    print(f"💬 Message: {response_data.get('message', 'N/A')}")
                except:
                    print(f"📄 Raw response length: {len(response.text)} chars")
            else:
                print(f"❌ {test_name} - Failed (Status: {response.status_code})")
                
        except Exception as e:
            print(f"❌ {test_name} - Error: {e}")
    
    print("\n" + "="*50)
    print("Multiple HTTP POST requests test completed!")


if __name__ == "__main__":
    Constants.PRODUCTION = False
    Constants.DEBUG_MODE = False  # Enable debug mode for browser visibility
    Constants.BYPASS_ASYNC_CHECKUP = False  # Bypass async check

    print("=" * 60)
    print("Testing Local Data Fetcher API (Direct Function Calls)")
    print("Security Indicators Test Suite")
    print(f"python_data_fetcher version {Constants.VERSION}")
    print(f"Debug mode is set to {Constants.DEBUG_MODE}")
    print(f"Async bypass is set to {Constants.BYPASS_ASYNC_CHECKUP}")
    print("=" * 60)
    
    # Uncomment to test individual components:
    # test_tase_current_price_only()      # Fast TASE current prices
    # test_tase_historical_only()         # TASE historical data with Selenium
    # test_yfinance_only()                # YFinance US stock data
    
    # Test European stocks
    # test_function_with_european_stocks()         # European stocks only
    # test_function_with_limited_european_stocks() # Limited European stocks (first 3)
    
    # Test HTTP POST requests to Flask server
    # test_http_post_request()                # Single HTTP POST request
    # test_http_post_multiple_requests()      # Multiple HTTP POST requests

    # Large scale testing
    test_function_with_large_custom_data()

    # Test the specific TASE historical case
    # test_specific_tase_historical()
    
    # Test multiple sequential calls to check for async loop issues
    # test_multiple_sequential_calls()
    
    # Simple test call with mixed security indicators
    # test_function_with_valid_data()
    
    # Comment out other tests for now
    # test_function_with_us_only()
    # test_function_with_european_stocks()
    # test_function_with_tase_indicators() 
    # test_function_with_mixed_indicators()
    # test_function_with_missing_data()
    # test_function_with_empty_request()
    
    print("Testing complete!")
