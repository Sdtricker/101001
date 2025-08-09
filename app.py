import os
import time
import logging
import subprocess
from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Configure logging for debugging
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)

def scrape_card_data(driver, card_id: str, card_title: str) -> list[str]:
    """Scrape data from a specific card on the page"""
    results = []
    try:
        card_container = driver.find_element(By.ID, card_id)
        all_spans_in_card = card_container.find_elements(By.TAG_NAME, 'span')
        for span in all_spans_in_card:
            text = span.text.strip()
            if text and text != card_title and "No " not in text and " Located" not in text:
                results.append(text)
    except NoSuchElementException:
        print(f"  - Card with id='{card_id}' not found. Skipping.")
    return results

def get_email_info_from_page(email: str) -> dict:
    """Main function to scrape email information from pentester.com"""
    options = ChromeOptions()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-features=VizDisplayCompositor')
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument('user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36')
    
    # Get chromium binary path dynamically
    try:
        chromium_path = subprocess.check_output(['which', 'chromium']).decode('utf-8').strip()
        options.binary_location = chromium_path
    except subprocess.CalledProcessError:
        # Fallback to common paths
        options.binary_location = '/usr/bin/chromium-browser'

    # Get chromedriver path dynamically
    try:
        chromedriver_path = subprocess.check_output(['which', 'chromedriver']).decode('utf-8').strip()
        service = ChromeService(executable_path=chromedriver_path)
        driver = webdriver.Chrome(service=service, options=options)
    except subprocess.CalledProcessError:
        # Fallback to default
        driver = webdriver.Chrome(options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    final_data = {}
    try:
        driver.get("https://pentester.com/")
        wait = WebDriverWait(driver, 20)
        input_field = wait.until(EC.element_to_be_clickable((By.NAME, "target")))
        submit_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@type='submit']")))
        input_field.send_keys(email)
        time.sleep(0.5)
        submit_button.click()
        WebDriverWait(driver, 60).until(EC.url_contains("/scans/"))
        time.sleep(10)

        final_data['email'] = email
        cards_to_scrape = {
            "data_breaches":  ("breaches", "DATA BREACHES"),
            "passwords":      ("passwords", "PASSWORDS"),
            "usernames":      ("usernames", "USERNAMES"),
            "phone_numbers":  ("phoneNumbers", "PHONE NUMBERS"),
            "ips":            ("ips", "IPS"),
            "related_emails": ("relatedEmails", "RELATED EMAILS"),
            "locations":      ("locations", "LOCATIONS"),
            "companies":      ("companies", "COMPANIES")
        }

        for key, (card_id, card_title) in cards_to_scrape.items():
            final_data[key] = scrape_card_data(driver, card_id, card_title)

    except TimeoutException:
        final_data["error"] = "Process timed out."
    except Exception as e:
        final_data["error"] = str(e)
    finally:
        driver.quit()

    return final_data

@app.route('/email', methods=['GET'])
def scan_email():
    """API endpoint to scan an email address"""
    try:
        # Get email parameter from query string
        email = request.args.get('email')
        
        if not email:
            return jsonify({
                "error": "Email parameter is required"
            }), 400
        
        # Validate email format (basic validation)
        if '@' not in email or '.' not in email:
            return jsonify({
                "error": "Invalid email format"
            }), 400
        
        # Perform the email scan
        data = get_email_info_from_page(email)
        
        return jsonify(data)
        
    except Exception as e:
        return jsonify({
            "error": f"An error occurred: {str(e)}"
        }), 500

@app.route('/', methods=['GET'])
def health_check():
    """Basic health check endpoint"""
    return jsonify({
        "status": "ok",
        "message": "Email Scanner API is running",
        "endpoints": {
            "scan_email": "/email?email=someone@example.com"
        }
    })

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        "error": "Endpoint not found",
        "available_endpoints": ["/", "/email"]
    }), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return jsonify({
        "error": "Internal server error"
    }), 500

if __name__ == '__main__':
    # Get port from environment variable (for Render deployment) or default to 5000
    port = int(os.environ.get('PORT', 5000))
    
    # Run the Flask app
    app.run(
        host='0.0.0.0',
        port=port,
        debug=True
    )
