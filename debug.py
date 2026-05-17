import gspread
import traceback

print("--- DIAGNOSTIC TEST ---")
# Version ento chupistundi
print(f"Gspread Version: {gspread.__version__}")

try:
    print("Trying to connect...")
    # Direct Service Account method
    gc = gspread.service_account(filename='credentials.json')
    print("Authentication OK.")
    
    # Sheet Open
    sh = gc.open("Customer_Data")
    print("✅ SUCCESS! Sheet Title:", sh.title)
    
except Exception:
    print("❌ ERROR Vachindi! Full Details Kindha Unnayi:")
    # Idi error ni motham print chestundi (Empty ga undadu)
    traceback.print_exc()