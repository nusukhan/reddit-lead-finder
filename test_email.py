# test_email.py
# Maqsad: PEHLE test karo ki Gmail app password chalta hai aur email jata hai.
# Sirf ek chhota "hello" email bhejenge. Agar aa gaya, phir leads wali email.
 
import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv
 
# --- .env se cheezein load karo ---
load_dotenv()
gmail_address = os.getenv("GMAIL_ADDRESS")       # bhejne wala
app_password = os.getenv("GMAIL_APP_PASSWORD")   # app password
to_email = os.getenv("TO_EMAIL")                 # jahan aayega
 
# check: sab mila?
if not gmail_address or not app_password or not to_email:
    print("ERROR: .env mein GMAIL_ADDRESS / GMAIL_APP_PASSWORD / TO_EMAIL check karo.")
    exit()
 
print(f"Bhejne wala: {gmail_address}")
print(f"Jaayega: {to_email}\n")
 
# --- Email banao ---
msg = EmailMessage()
msg["Subject"] = "Test email from your Reddit lead-finder"
msg["From"] = gmail_address
msg["To"] = to_email
msg.set_content("Agar ye email mil gaya, to lead-finder email bhej sakta hai! 🎉\n\n- Nusu's lead-finder")
 
print("Email bhej rahe hain...")
 
# --- Gmail ke server se baat kar ke bhejo ---
try:
    # Gmail ka SMTP server, SSL ke sath (port 465)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_address, app_password)   # app password se login
        server.send_message(msg)
    print("\nEmail bhej diya! Apna inbox (umar@brevlox.com) check karo.")
    print("(Spam folder bhi dekh lena, pehli dafa wahan ja sakta hai.)")
except Exception as e:
    print(f"\nERROR: email nahi gaya. Wajah:\n{e}")
    print("\nAam wajah: app password galat, ya spaces reh gaye, ya 2-step off.")

