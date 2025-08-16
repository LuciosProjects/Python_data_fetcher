"""
Quick test runner for the Google Cloud Function.
Run this script to quickly test your function with different scenarios.
"""

from test_wrapper import (
    test_function_with_valid_data,
    test_function_with_tase_indicators,
    test_function_with_mixed_indicators,
    test_function_with_missing_data, 
    test_function_with_empty_request,
    interactive_test,
    create_mock_request
)
from main import python_data_fetch


def quick_test():
    """Run a quick test with sample security indicators."""
    print("Quick Test - Sample Security Indicators from Google Sheets")
    print("=" * 50)
    
    # Simulate security indicators that might come from Google Sheets - all in one list
    sheets_data = {
        "data": { 
            "indicators": ["AAPL", "GOOGL", "MSFT", "TSLA", "5138094", "1144633", "1183441"], # Indicators metadata, must be provided
            "date": "" # Date metadata, if not provided, current date will be used
        }
    }
    
    mock_request = create_mock_request(sheets_data)
    response = python_data_fetch(mock_request)
    
    print(f"Security Indicators: {sheets_data['data']}")
    print(f"Response: {response}")
    print("-" * 50)


if __name__ == "__main__":
    print("🚀 Google Cloud Function Test Runner")
    print("Security Indicators Data Fetcher")
    print("=" * 50)
    
    # Quick test first
    quick_test()
    
    # Ask user what they want to do
    print("\nChoose testing mode:")
    print("1. Run all automated tests (US symbols, TASE indicators, mixed)")
    print("2. Interactive testing")
    print("3. Exit")
    
    choice = input("\nEnter your choice (1-3): ")
    
    if choice == "1":
        print("\n" + "=" * 50)
        test_function_with_valid_data()
        test_function_with_tase_indicators()
        test_function_with_mixed_indicators()
        test_function_with_missing_data()
        test_function_with_empty_request()
        
    elif choice == "2":
        print("\n" + "=" * 50)
        interactive_test()
        
    print("\n✅ Testing complete!")
