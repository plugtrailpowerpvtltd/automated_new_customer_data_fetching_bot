import gspread
from oauth2client.service_account import ServiceAccountCredentials

print("Testing Connection (Master Method)...")

try:
    # Old Style Authentication (Idi eppudu fail avvadu)
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    client = gspread.authorize(creds)
    
    # Sheet Open
    sh = client.open("Customer_Data") # Nee sheet peru ikkada correct ga undali
    print("✅ SUCCESS! Connection Kalisindi.")
    print("Sheet Peru:", sh.title)

except Exception as e:
    print("❌ ERROR Vachindi:", e)