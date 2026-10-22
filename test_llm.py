# test_llm.py
# Maqsad: PEHLE test karo ki OpenRouter key chalti hai aur LLM jawab deta hai.
# Sirf EK post bhejenge. Agar yeh chala, phir saari 50 pe jayenge.
 
import os
from openai import OpenAI
from dotenv import load_dotenv
 
# --- .env file se key load karo (code mein seedha nahi likhte!) ---
load_dotenv()
api_key = os.getenv("OPENROUTER_API_KEY")
 
# check: key mili ya nahi?
if not api_key:
    print("ERROR: key nahi mili! .env file check karo.")
    exit()
 
print("Key .env se mil gayi.\n")
 
# --- OpenRouter se baat karne ka client banao ---
# (RAG mein bhi aise hi tha, bas base_url OpenRouter ka hai)
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key,
)
 
# --- Ek test post (abhi hardcoded, sirf test ke liye) ---
test_title = "My Stripe subscription billing keeps failing for monthly customers"
test_text = "I'm building a SaaS and every time a customer tries to pay monthly, the charge fails. I don't know how to fix the recurring billing. Need help."
 
# --- LLM ko poochne ke liye prompt banao ---
# Hum LLM ko batate hain: tum kaun ho, kya dekhna hai, kaise jawab dena hai.
prompt = f"""You are helping a Laravel/SaaS developer find potential clients on Reddit.
The developer specializes in: Laravel, Stripe billing, multi-tenant SaaS, real-time features.
 
Here is a Reddit post:
Title: {test_title}
Text: {test_text}
 
Is this post from someone who might need this developer's help?
Answer in this exact format:
MATCH: yes or no
REASON: one short sentence why"""
 
print("LLM se poochh rahe hain...\n")
 
# --- LLM ko request bhejo ---
response = client.chat.completions.create(
    model="meta-llama/llama-3.3-70b-instruct",   # ek acha free/sasta model
    messages=[
        {"role": "user", "content": prompt}
    ],
)
 
# --- LLM ka jawab nikaalo aur dikhao ---
answer = response.choices[0].message.content
print("LLM ka jawab:")
print("=" * 40)
print(answer)
print("=" * 40)
print("\nAgar upar MATCH aur REASON dikh raha hai, to key aur LLM dono chal rahe hain!")
 