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
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
SHEET_NAME = "Customer_Data"
JSON_FILE = "credentials.json"

LOGIN_URL = "https://cpms.plugtrail.in/login"
DATA_PAGE_URL = "https://cpms.plugtrail.in/users"

USER_EMAIL = os.environ.get("LOGIN_EMAIL")
USER_PASSWORD = os.environ.get("LOGIN_PASSWORD")

# Check first N pages only (newest users are on page 1)
PAGES_TO_CHECK = 2

def clean_phone(phone):
    """Normalize phone number — remove +, -, spaces so all formats match"""
    return str(phone).strip().replace("+", "").replace("-", "").replace(" ", "")

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
    # STEP 2 — Read existing phones from sheet
    # ----------------------------------------
    print("Step 2: Reading existing sheet data...")
    existing_rows = sheet.get_all_values()

    if existing_rows:
        headers = existing_rows[0]
        data_rows = existing_rows[1:]
    else:
        headers = []
        data_rows = []

    sheet_is_empty = len(headers) == 0

    # Collect ALL phone numbers — cleaned/normalized
    # Skip empty rows (rows where name AND phone are both empty)
    existing_phones = set()
    for row in data_rows:
        name = row[0].strip() if len(row) > 0 else ""
        phone = row[3].strip() if len(row) > 3 else ""

        # Skip completely empty rows
        if not name and not phone:
            continue

        if phone:
            cleaned = clean_phone(phone)
            if cleaned:
                existing_phones.add(cleaned)

    print(f"Total users already in sheet: {len(existing_phones)}")

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
    # STEP 4 — Scrape first PAGES_TO_CHECK pages
    # (Page 1 = newest users always)
    # ----------------------------------------
    print(f"Step 4: Scraping first {PAGES_TO_CHECK} pages (newest users)...")
    driver.get(DATA_PAGE_URL)
    time.sleep(3)

    all_customers = []
    current_page = 1

    while current_page <= PAGES_TO_CHECK:
        print(f"Scraping page {current_page}...")
        try:
            dfs = pd.read_html(StringIO(driver.page_source))
            if dfs:
                df = dfs[0]
                all_customers.append(df)
                print(f"Page {current_page}: {len(df)} rows found.")

                # Debug — print sample phones from dashboard
                if current_page == 1:
                    sample_phones = [
                        clean_phone(str(row.iloc[3]))
                        for _, row in df.iterrows()
                    ][:3]
                    print(f"Sample phones from dashboard: {sample_phones}")

            else:
                print("No data on this page.")
                break
        except Exception as e:
            print(f"Error reading table: {e}")
            break

        if current_page < PAGES_TO_CHECK:
            try:
                next_btn = driver.find_element(
                    By.XPATH, "//button[@aria-label='Go to next page']"
                )
                if "Mui-disabled" in next_btn.get_attribute("class") or not next_btn.is_enabled():
                    print("No more pages available.")
                    break
                driver.execute_script("arguments[0].click();", next_btn)
                time.sleep(3)
            except:
                print("Could not click next page.")
                break

        current_page += 1

    driver.quit()

    # ----------------------------------------
    # STEP 5 — Filter & add only new users
    # ----------------------------------------
    if not all_customers:
        print("No data fetched. Exiting.")
        return

    print("Step 5: Checking for new users...")
    final_df = pd.concat(all_customers, ignore_index=True)
    final_df = final_df.fillna("")

    # Debug — print sample phones from sheet
    sample_sheet_phones = list(existing_phones)[:3]
    print(f"Sample phones from sheet: {sample_sheet_phones}")

    # Write headers if sheet is empty
    if sheet_is_empty:
        new_headers = final_df.columns.values.tolist() + ["Synced", "WA Sent"]
        sheet.append_row(new_headers)
        print("Headers written to sheet.")

    # Filter only phones NOT already in sheet
    new_users = []
    skipped = 0
    for _, row in final_df.iterrows():
        phone = clean_phone(str(row.iloc[3]))
        if phone and phone not in existing_phones:
            new_users.append(row)
        else:
            skipped += 1

    print(f"Skipped {skipped} already existing users.")

    if not new_users:
        print(f"No new users found. All {len(existing_phones)} users up to date ✅")
        return

    print(f"Found {len(new_users)} new users! Adding to sheet...")

    # ----------------------------------------
    # Insert new users at TOP (row 2) not bottom
    # Reverse the list so latest stays on top
    # ----------------------------------------
    rows_to_insert = []
    for row in new_users:
        row_data = row.values.tolist() + ["✅", ""]
        rows_to_insert.append(row_data)

    # Insert all new rows at row 2 at once (faster than one by one)
    sheet.insert_rows(rows_to_insert, row=2)

    print(f"Done! {len(new_users)} new users added at top of sheet 🎉")
    print(f"Total in sheet now: {len(existing_phones) + len(new_users)}")


if __name__ == "__main__":
    automate_data_transfer()