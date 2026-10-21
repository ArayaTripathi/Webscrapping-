import pandas as pd
import requests
import re
import time
import os

SERPER_API_KEY = "96a2b7d9063213e140199ff464fbb0e8fd562d40"
INPUT_CSV = "institutions.csv"
OUTPUT_CSV = "colleges_with_contacts.csv"
OUTPUT_XLSX = "colleges_with_contacts.xlsx"

EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b')

# Indian mobile: 10 digits starting with 6-9, optionally with +91 or 0
# Landline: STD code + 6-8 digits (e.g., 022-27482400, 020 25695560)
PHONE_RE = re.compile(
    r'(?:(?:\+91[\-\s]?)|(?:0[\-\s]?))?[6-9]\d{9}|'
    r'\b0\d{2,4}[\-\s]?\d{6,8}\b'
)

def search_college_contacts(college_name, city="", state=""):
    url = "https://google.serper.dev/search"
    query = f"{college_name} {city} contact us phone number email tpo"
    payload = {
        "q": query.strip(),
        "gl": "in"
    }
    headers = {
        'X-API-KEY': SERPER_API_KEY,
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            
            snippets = []
            
            # Knowledge graph if present
            kg = data.get("knowledgeGraph", {})
            if kg:
                for k in ["phone", "email", "description"]:
                    if kg.get(k):
                        snippets.append(str(kg.get(k)))
            
            # Organic snippets & titles
            for res in data.get("organic", [])[:5]:
                snippets.append(res.get("title", ""))
                snippets.append(res.get("snippet", ""))
                
            combined_text = " ".join(snippets)
            return combined_text
        else:
            print(f"Error {response.status_code}: {response.text}")
            return ""
    except Exception as e:
        print(f"Request failed for {college_name}: {e}")
        return ""

def extract_emails(text):
    if not text:
        return ""
    matches = EMAIL_RE.findall(text)
    # Filter dummy/file extension emails
    clean_emails = []
    for em in matches:
        em_lower = em.lower()
        if any(bad in em_lower for bad in ['.png', '.jpg', '.jpeg', '.webp', '.svg', 'example.com', 'sentry.io', 'domain.com']):
            continue
        if em_lower not in [c.lower() for c in clean_emails]:
            clean_emails.append(em)
    return ", ".join(clean_emails[:3])

def extract_phones(text):
    if not text:
        return ""
    matches = PHONE_RE.findall(text)
    clean_phones = []
    for ph in matches:
        ph_clean = re.sub(r'[^\d+]', '', ph)
        # Avoid year strings or pin codes mistaken as phone
        if len(ph_clean) < 8 or len(ph_clean) > 13:
            continue
        if ph.strip() not in clean_phones:
            clean_phones.append(ph.strip())
    return ", ".join(clean_phones[:3])

def extract_tpo(text):
    if not text:
        return ""
    # Look for patterns like TPO / Training & Placement Officer: <number or email>
    tpo_match = re.search(r'(?:tpo|placement[s]?|training\s*&\s*placement)[^\.\n;]{0,50}?(?:(\+91[\-\s]?[6-9]\d{9}|[6-9]\d{9}|0\d{2,4}[\-\s]?\d{6,8})|([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}))', text, re.IGNORECASE)
    if tpo_match:
        phone = tpo_match.group(1) or ""
        email = tpo_match.group(2) or ""
        return (phone + " " + email).strip()
    return ""

def main():
    if not os.path.exists(INPUT_CSV):
        print(f"Error: {INPUT_CSV} not found!")
        return

    # Check if we can resume from existing output
    if os.path.exists(OUTPUT_CSV):
        print(f"Resuming from existing {OUTPUT_CSV}...")
        df = pd.read_csv(OUTPUT_CSV)
    else:
        df = pd.read_csv(INPUT_CSV)
        
    for col in ['contact_no', 'email_id', 'tpo_contact']:
        if col not in df.columns:
            df[col] = ""

    total = len(df)
    print(f"Starting contact extraction for {total} institutions via Serper API...")

    # Identify column name for college
    college_col = 'college_name' if 'college_name' in df.columns else 'College_Name'
    city_col = 'city' if 'city' in df.columns else 'City'
    state_col = 'state' if 'state' in df.columns else 'State'

    processed_count = 0
    for idx, row in df.iterrows():
        college = str(row[college_col]).strip()
        city = str(row.get(city_col, '')).strip() if pd.notna(row.get(city_col)) else ""
        state = str(row.get(state_col, '')).strip() if pd.notna(state_col in df.columns and row.get(state_col)) else ""

        # Skip if already populated
        curr_phone = str(row.get('contact_no', '')).strip()
        curr_email = str(row.get('email_id', '')).strip()
        if curr_phone not in ["", "nan"] and curr_email not in ["", "nan"]:
            continue

        print(f"[{idx+1}/{total}] Searching: {college} ({city})...", flush=True)
        search_text = search_college_contacts(college, city, state)

        phone = extract_phones(search_text)
        email = extract_emails(search_text)
        tpo = extract_tpo(search_text)

        df.at[idx, 'contact_no'] = phone if phone else "Not Found"
        df.at[idx, 'email_id'] = email if email else "Not Found"
        df.at[idx, 'tpo_contact'] = tpo if tpo else "Not Found"

        print(f"    -> Phone: {phone or 'N/A'} | Email: {email or 'N/A'}", flush=True)

        processed_count += 1
        
        # Save every 5 records to persist progress
        if processed_count % 5 == 0:
            df.to_csv(OUTPUT_CSV, index=False)
            try:
                df.to_excel(OUTPUT_XLSX, index=False)
            except Exception:
                pass

        time.sleep(0.3)  # Fast delay (Serper supports high QPS)

    df.to_csv(OUTPUT_CSV, index=False)
    try:
        df.to_excel(OUTPUT_XLSX, index=False)
    except Exception:
        pass
    print(f"\nProcessing complete! Saved to {OUTPUT_CSV} and {OUTPUT_XLSX}")

if __name__ == '__main__':
    main()
