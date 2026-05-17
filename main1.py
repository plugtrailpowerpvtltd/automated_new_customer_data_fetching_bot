import time
import pandas as pd
import gspread
import os
from io import StringIO
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options

# --- CONFIGURATION ---
from dotenv import load_dotenv
load_dotenv()
SHEET_NAME = "Customer_Data"
JSON_FILE = "credentials.json"

LOGIN_URL = "https://cpms.plugtrail.in/login"
DATA_PAGE_URL = "https://cpms.plugtrail.in/users"

USER_EMAIL = os.environ.get("LOGIN_EMAIL")
USER_PASSWORD = os.environ.get("LOGIN_PASSWORD")

# Column index (0-based) of "Synced" column in sheet
# Sheet columns: A=Name, B=Vehicle, C=Email, D=Phone, E=Wallet, F=Created Date, G=Blocked, H=Synced, I=WA Sent
SYNCED_COL_INDEX = 7   # Column H (0-based)
WA_SENT_COL_INDEX = 8  # Column I (0-based)

def automate_data_transfer():

    # ----------------------------------------
    # STEP 1 — Connect to Google Sheet
    # ----------------------------------------
    print("Step 1: Connecting to Google Sheets...")
    try:
        from oauth2client.service_account import ServiceAccountCredentials
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]

        if not os.path.exists(JSON_FILE):
            print("Error: credentials.json not found!")
            return

        creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_FILE, scope)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME).sheet1
        print("Connected to Google Sheet successfully.")
    except Exception as e:
        print(f"Connection Error: {e}")
        return

    # ----------------------------------------
    # STEP 2 — Read existing sheet data
    # ----------------------------------------
    print("Step 2: Reading existing sheet data...")
    existing_rows = sheet.get_all_values()  # Returns list of lists

    # First row = headers
    if existing_rows:
        headers = existing_rows[0]
        data_rows = existing_rows[1:]  # Skip header row
    else:
        headers = []
        data_rows = []

    # Check if headers already exist
    # If sheet is brand new, we will write headers ourselves
    sheet_is_empty = len(headers) == 0

    # Collect all rows that are already marked as Synced ✅
    # We use row number (from dashboard) as unique key
    # But since dashboard has no unique ID, we use Phone Number (column D = index 3)
    synced_phones = set()
    for row in data_rows:
        # Only consider rows that have Synced ✅ marked
        if len(row) > SYNCED_COL_INDEX and row[SYNCED_COL_INDEX].strip() == "✅":
            phone = row[3].strip() if len(row) > 3 else ""
            if phone:
                synced_phones.add(phone)

    print(f"Already synced users in sheet: {len(synced_phones)}")

    # ----------------------------------------
    # STEP 3 — Open browser & login
    # ----------------------------------------
    print("Step 3: Opening Dashboard in Headless Mode...")
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )

    driver.get(LOGIN_URL)
    time.sleep(5)

    print("Logging in...")
    try:
        if not USER_EMAIL or not USER_PASSWORD:
            raise ValueError("Email or Password missing in Environment Variables")

        driver.find_element(By.XPATH, "(//input)[1]").send_keys(USER_EMAIL)
        driver.find_element(By.CSS_SELECTOR, "input[type='password']").send_keys(USER_PASSWORD)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    except Exception as e:
        print(f"Login Error: {e}")
        driver.quit()
        return

    time.sleep(5)

    # ----------------------------------------
    # STEP 4 — Scrape all pages from dashboard
    # ----------------------------------------
    print("Step 4: Scraping Dashboard...")
    driver.get(DATA_PAGE_URL)
    time.sleep(3)

    all_customers = []
    page_number = 1

    while True:
        print(f"Scraping Page {page_number}...")
        try:
            dfs = pd.read_html(StringIO(driver.page_source))
            if len(dfs) > 0:
                df = dfs[0]
                all_customers.append(df)
                print(f"Page {page_number}: {len(df)} rows found.")
            else:
                print("No data found on this page.")
                break
        except Exception as e:
            print(f"Error reading table: {e}")
            break

        try:
            next_btn = driver.find_element(
                By.XPATH, "//button[@aria-label='Go to next page']"
            )
            if "Mui-disabled" in next_btn.get_attribute("class") or not next_btn.is_enabled():
                print("Last page reached.")
                break

            driver.execute_script("arguments[0].click();", next_btn)
            time.sleep(5)
            page_number += 1
        except:
            print("No next page found. Stopping.")
            break

    driver.quit()

    # ----------------------------------------
    # STEP 5 — Filter new users & write to sheet
    # ----------------------------------------
    if not all_customers:
        print("No data found on dashboard. Exiting.")
        return

    print("Step 5: Filtering new users...")
    final_df = pd.concat(all_customers, ignore_index=True)
    final_df = final_df.fillna("")

    # Write headers if sheet is empty
    if sheet_is_empty:
        new_headers = final_df.columns.values.tolist() + ["Synced", "WA Sent"]
        sheet.append_row(new_headers)
        print("Headers written to sheet.")

    # Filter out already synced users using Phone Number
    new_users = []
    for _, row in final_df.iterrows():
        phone = str(row.iloc[3]).strip()  # Column D = Phone Number
        if phone not in synced_phones:
            new_users.append(row)

    if not new_users:
        print("No new users found today. Sheet is already up to date ✅")
        return

    print(f"Found {len(new_users)} new users. Adding to sheet...")

    # Append new rows with Synced ✅ and WA Sent empty
    for row in new_users:
        row_data = row.values.tolist() + ["✅", ""]
        sheet.append_row(row_data)
        time.sleep(0.5)  # Avoid Google Sheets API rate limit

    print(f"Done! {len(new_users)} new users added to sheet successfully 🎉")


if __name__ == "__main__":
    automate_data_transfer()