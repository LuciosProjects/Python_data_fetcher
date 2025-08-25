"""
Silent Selenium automation for Israeli financial websites.
This module provides a headless browser setup for scraping Israeli securities data.
"""

import time
import random
import logging

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

import DataFetcher_Constants as Constants

# Suppress selenium logging
logging.getLogger('selenium').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

class SilentBrowser:
    """
    A silent, headless browser for automating Israeli financial websites.
    Designed to be stealthy and avoid detection.
    """

    def __init__(self, 
                 headless=True, 
                 wait_timeout=10, 
                 window_size="1920,1080", 
                 enable_javascript=False, 
                 make_null=False):
        """
        Initialize the silent browser.
        
        Args:
            headless (bool): Run browser in headless mode (invisible)
            wait_timeout (int): Seconds to wait for elements
            window_size (str): Browser window size as "width,height"
            enable_javascript (bool): Enable JavaScript execution (must be set at initialization)
            make_null (bool): Skip browser setup if True
        """

        if Constants.DEBUG_MODE:
            self.headless = False  # Force headless mode off in debug mode
        else:
            self.headless = headless
            
        self.wait_timeout   = wait_timeout
        self.window_size    = window_size
        self.enable_javascript = enable_javascript
        self.current_url    = None  # Track if a URL is currently open
        self.is_url_loaded  = False  # Boolean flag for URL status

        if not make_null:
            self._setup_browser()
    
    def _setup_browser(self):
        """Setup Chrome browser with stealth options."""
        chrome_options = Options()
        
        if self.headless:
            chrome_options.add_argument("--headless")
        
        # Stealth options to avoid detection
        chrome_options.add_argument(f"--window-size={self.window_size}")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins")
        chrome_options.add_argument("--disable-images")  # Faster loading
        
        # JavaScript control - must be set at browser initialization
        if not self.enable_javascript:
            chrome_options.add_argument("--disable-javascript")
        
        # User agent to look like a real browser
        chrome_options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        
        # Suppress logging
        chrome_options.add_argument("--log-level=3")
        chrome_options.add_argument("--silent")
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        try:
            # Use WebDriver Manager to automatically handle ChromeDriver
            service = Service(ChromeDriverManager().install())
            self.driver: webdriver.Chrome = webdriver.Chrome(service=service, options=chrome_options)

            # Remove automation indicators
            self.driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            
            # Set up wait object
            self.wait: WebDriverWait = WebDriverWait(self.driver, self.wait_timeout)
            
        except Exception as e:
            raise Exception(f"SilentBrowser::_setup_browser - Failed to initialize browser: {str(e)}")
    
    def is_javascript_enabled(self):
        """
        Check if JavaScript is enabled in the browser.
        
        Returns:
            bool: True if JavaScript is enabled, False otherwise
        """
        return self.enable_javascript
    
    def get_current_url_status(self):
        """
        Get current URL and load status.
        
        Returns:
            dict: Contains 'url', 'is_loaded', and 'title' information
        """
        try:
            current_driver_url = self.driver.current_url
            title = self.driver.title if self.is_url_loaded else None
            
            return {
                'url': self.current_url,
                'driver_url': current_driver_url,
                'is_loaded': self.is_url_loaded,
                'title': title
            }
        except Exception:
            return {
                'url': self.current_url,
                'driver_url': None,
                'is_loaded': self.is_url_loaded,
                'title': None
            }

    def navigate_to(self, url, wait_for_element=None):
        """
        Navigate to a URL and optionally wait for an element.
        
        Args:
            url (str): URL to navigate to
            wait_for_element (tuple): Optional (By, locator) to wait for
            
        Returns:
            bool: True if navigation successful, False otherwise
        """
        try:
            self.driver.get(url)
            self.current_url = url
            self.is_url_loaded = True
            self._random_delay(0.5, 2.0)
            
            if wait_for_element:
                by, locator = wait_for_element
                self.wait.until(EC.presence_of_element_located((by, locator)))
            
            return True
        except Exception as e:
            print(f"SilentBrowser::navigate_to - Navigation to '{url}' failed: {str(e)}")
            self.is_url_loaded = False
            return False
    
    def click_element(self, by, locator, wait_timeout=None):
        """
        Silently click an element.
        
        Args:
            by: Selenium By type (By.ID, By.CLASS_NAME, etc.)
            locator (str): Element locator
            wait_timeout (int): Seconds to wait for element (uses instance default if None)
            
        Returns:
            bool: True if click successful, False otherwise
        """
        # Use instance timeout if not specified
        timeout = wait_timeout if wait_timeout is not None else self.wait_timeout
        
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((by, locator))
            )
            
            # Scroll element into view
            self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
            self._random_delay(0.2, 0.5)
            
            # Click using JavaScript to avoid interception
            self.driver.execute_script("arguments[0].click();", element)
            self._random_delay(0.5, 1.5)
            
            return True
        except TimeoutException:
            print(f"SilentBrowser::click_element - Element not found or not clickable: {locator}")
            return False
        except Exception as e:
            print(f"SilentBrowser::click_element - Click failed: {str(e)}")
            return False
    
    def fill_text(self, by, locator, text, clear_first=True):
        """
        Fill text into an input field.
        
        Args:
            by: Selenium By type
            locator (str): Element locator
            text (str): Text to input
            clear_first (bool): Clear field before typing
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            element = self.wait.until(EC.presence_of_element_located((by, locator)))
            
            if clear_first:
                element.clear()
            
            # Type with human-like delays
            for char in text:
                element.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))
            
            self._random_delay(0.3, 0.7)
            return True
        except Exception as e:
            print(f"SilentBrowser::fill_text - Text input failed: {str(e)}")
            return False
    
    def get_text(self, by, locator):
        """
        Get text from an element.
        
        Args:
            by: Selenium By type
            locator (str): Element locator
            
        Returns:
            str or None: Element text or None if not found
        """
        try:
            element = self.wait.until(EC.presence_of_element_located((by, locator)))
            return element.text.strip()
        except Exception as e:
            print(f"SilentBrowser::get_text - Get text failed: {str(e)}")
            return None
    
    def wait_for_element(self, by, locator, timeout=None):
        """
        Wait for an element to appear.
        
        Args:
            by: Selenium By type
            locator (str): Element locator
            timeout (int): Seconds to wait (uses instance default if None)
            
        Returns:
            WebElement or None: Element if found, None otherwise
        """
        # Use instance timeout if not specified
        wait_time = timeout if timeout is not None else self.wait_timeout
        
        try:
            return WebDriverWait(self.driver, wait_time).until(
                EC.presence_of_element_located((by, locator))
            )
        except TimeoutException:
            return None
    
    def _random_delay(self, min_seconds, max_seconds):
        """Add random delay to simulate human behavior."""
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)
    
    def restart_browser(self, 
                        enable_javascript=None, 
                        headless=None, 
                        wait_timeout=None, 
                        window_size=None):
        """
        Restart the browser with new settings, allowing JavaScript toggle.
        
        Args:
            enable_javascript (bool, optional): Enable/disable JavaScript (None to keep current)
            headless (bool, optional): Headless mode (None to keep current)
            wait_timeout (int, optional): Wait timeout (None to keep current)
            window_size (str, optional): Window size (None to keep current)
            
        Returns:
            bool: True if restart successful, False otherwise
        """
        try:
            # Store current URL to restore after restart
            current_url_backup = getattr(self, 'current_url', None)
            
            # Close existing browser if it exists
            if hasattr(self, 'driver') and self.driver:
                self.driver.quit()
            
            # Update settings if provided
            if enable_javascript is not None:
                self.enable_javascript = enable_javascript
            if headless is not None:
                if Constants.DEBUG_MODE:
                    self.headless = False  # Force visible in debug mode
                else:
                    self.headless = headless
            if wait_timeout is not None:
                self.wait_timeout = wait_timeout
            if window_size is not None:
                self.window_size = window_size
            
            # Reset URL tracking
            self.current_url = None
            self.is_url_loaded = False
            
            # Setup new browser with updated settings
            self._setup_browser()
            
            # Optionally restore the previous URL
            if current_url_backup:
                print(f"Browser restarted. Previous URL was: {current_url_backup}")
                print("Use navigate_to() to reload the page if needed.")
            
            return True
            
        except Exception as e:
            print(f"SilentBrowser::restart_browser - Browser restart failed: {str(e)}")
            return False
    
    def toggle_javascript_and_restart(self, enable_javascript):
        """
        Convenience method to toggle JavaScript and restart browser.
        
        Args:
            enable_javascript (bool): True to enable JavaScript, False to disable
            
        Returns:
            bool: True if restart successful, False otherwise
        """
        print(f"{'Enabling' if enable_javascript else 'Disabling'} JavaScript and restarting browser...")
        return self.restart_browser(enable_javascript=enable_javascript)

    def is_open(self):
        """Check if the browser is open."""
        return hasattr(self, 'driver') and self.driver is not None

    def close(self):
        """Close the browser."""
        if hasattr(self, 'driver') and self.driver:
            self.driver.quit()

    def quit(self):
        """Alias for close() to maintain compatibility."""
        self.close()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


# Quick usage example
def test_silent_browser():
    """Test the silent browser with JavaScript toggle functionality."""
    url = "https://finance.themarker.com/etf/5138094"

    with SilentBrowser(headless=True, enable_javascript=False) as browser:
        print(f"🔧 JavaScript initially: {'Enabled' if browser.is_javascript_enabled() else 'Disabled'}")
        
        # Navigate to a test site
        if browser.navigate_to(url):
            print("✅ Navigation successful")
            
            # Get page title
            title = browser.driver.title
            print(f"📄 Page title: {title}")
            
            # Demonstrate JavaScript toggle
            print("\n🔄 Toggling JavaScript and restarting...")
            if browser.toggle_javascript_and_restart(True):
                print(f"🔧 JavaScript now: {'Enabled' if browser.is_javascript_enabled() else 'Disabled'}")
                
                # Navigate again with JavaScript enabled
                if browser.navigate_to(url):
                    print("✅ Navigation successful with JavaScript enabled")
                    title = browser.driver.title
                    print(f"📄 Page title: {title}")
                else:
                    print("❌ Navigation failed after restart")
            else:
                print("❌ Browser restart failed")
        else:
            print("❌ Navigation failed")

if __name__ == "__main__":
    test_silent_browser()
