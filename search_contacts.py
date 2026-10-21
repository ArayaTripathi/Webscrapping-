import argparse, random, re, time, warnings
from pathlib import Path
from urllib.parse import urlparse
import pandas as pd
import requests
from bs4 import BeautifulSoup

warnings.filterwarnings("ignore")

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?:\+91[\-\s]?)?(?:[6-9]\d{9}|0\d{2,4}[\-\s]?\d{6,8})")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]

BAD_EMAIL = ["example","domain","sentry","noreply","no-reply","lorem","privacy",
             "unsubscribe","w3.org","schema","google","facebook","twitter","youtube",
             "jquery","bootstrap","cloudflare"]

# Domains that may have useful college contact info
GOOD_DOMAINS = [".ac.in", ".edu.in", ".edu", ".org.in", ".org",
                "justdial", "sulekha", "collegedunia", "shiksha",
                "mapsofindia", "indiamart", "yellowpages"]

SKIP_DOMAINS = ["google","youtube","facebook","twitter","instagram","linkedin",
                "wikipedia","wikimedia","amazon","flipkart","zomato","swiggy"]


def hdrs():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
        "DNT": "1",
        "Connection": "keep-alive",
    }


def fetch(url, timeout=12):
    try:
        r = requests.get(url, headers=hdrs(), timeout=timeout, verify=False, allow_redirects=True)
        ct = r.headers.get("content-type", "")
        if r.status_code == 200 and "text" in ct:
            return r.text
    except Exception:
        pass
    return None


def google_links(query, num=5):
    """Return organic result links from Google search."""
    url = f"https://www.google.com/search?q={requests.utils.quote(query)}&num={num}&hl=en"
    html = fetch(url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/url?q="):
            actual = href.split("/url?q=")[1].split("&")[0]
            parsed = urlparse(actual)
            host = parsed.netloc.lower()
            if not actual.startswith("http"):
                continue
            if any(s in host for s in SKIP_DOMAINS):
                continue
            if actual not in links:
                links.append(actual)
        if len(links) >= num:
            break
    return links


def clean_emails(lst):
    seen, out = set(), []
    for e in lst:
        el = e.lower().strip()
        if any(b in el for b in BAD_EMAIL):
            continue
        if el not in seen:
            seen.add(el)
            out.append(el)
    return out


def clean_phones(lst):
    seen, out = set(), []
    for p in lst:
        digits = re.sub(r"\D", "", p)
        if len(digits) < 10:
            continue
        if digits not in seen:
            seen.add(digits)
            out.append(p.strip())
    return out


def is_tpo(text, pos, win=300):
    snip = text[max(0, pos - win): pos + win].lower()
    return any(k in snip for k in ["tpo", "placement", "training & placement", "career center", "internship coordinator"])


def extract_contacts_from_page(html, college_name):
    """Extract emails and phones, separating TPO from general."""
    emails, phones, tpo_emails, tpo_phones = [], [], [], []
    
    # Only look in body text, avoid script/style content
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "head"]):
        tag.decompose()
    clean_text = soup.get_text(separator=" ")

    for m in EMAIL_RE.finditer(clean_text):
        e = m.group()
        if any(b in e.lower() for b in BAD_EMAIL):
            continue
        if is_tpo(clean_text, m.start()):
            tpo_emails.append(e)
        else:
            emails.append(e)

    for m in PHONE_RE.finditer(clean_text):
        p = m.group()
        if is_tpo(clean_text, m.start()):
            tpo_phones.append(p)
        else:
            phones.append(p)

    return (clean_emails(emails), clean_phones(phones),
            clean_emails(tpo_emails), clean_phones(tpo_phones))


def get_contacts(college_name, city, district):
    result = {
        "email": "", "phone": "", "tpo_email": "", "tpo_phone": "",
        "source_url": "", "status": "No data",
    }

    query = f'"{college_name}" {city} Maharashtra contact phone email'
    links = google_links(query, num=4)

    if not links:
        # Try broader query
        query2 = f"{college_name} {district} Maharashtra phone"
        links = google_links(query2, num=3)

    if not links:
        result["status"] = "Google: no links"
        return result

    all_emails, all_phones, all_tpo_emails, all_tpo_phones = [], [], [], []
    found_url = ""

    for link in links[:3]:
        page = fetch(link)
        if not page:
            continue
        if not found_url:
            found_url = link
        e, p, te, tp = extract_contacts_from_page(page, college_name)
        all_emails += e
        all_phones += p
        all_tpo_emails += te
        all_tpo_phones += tp
        time.sleep(0.7)

    all_emails = clean_emails(all_emails)
    all_phones = clean_phones(all_phones)
    all_tpo_emails = clean_emails(all_tpo_emails)
    all_tpo_phones = clean_phones(all_tpo_phones)

    if all_emails or all_phones:
        result["email"] = all_emails[0] if all_emails else ""
        result["phone"] = all_phones[0] if all_phones else ""
        result["tpo_email"] = all_tpo_emails[0] if all_tpo_emails else ""
        result["tpo_phone"] = all_tpo_phones[0] if all_tpo_phones else ""
        result["source_url"] = found_url
        result["status"] = "Search: found"
    else:
        result["status"] = "Search: no contacts"

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="output/college_contacts.csv")
    parser.add_argument("--output", default="output/college_contacts.csv")
    parser.add_argument("--delay", type=float, default=2.5)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    df = pd.read_csv(args.input, dtype=str).fillna("")

    # Reset wrongly found entries from previous bad run (same phone on all = bad)
    bad_phones = {"7205202742"}
    for col in ["phone", "tpo_phone"]:
        df.loc[df[col].isin(bad_phones), col] = ""
    df.loc[df["phone"].isin(bad_phones), "status"] = "Invalid website"

    mask = (
        (df["email"] == "") & (df["phone"] == "") &
        (df["status"].str.contains("Invalid|unavailable|blocked|no website|No data|Search|Google", case=False, na=False))
    )
    todo = df[mask].copy()
    if args.limit > 0:
        todo = todo.head(args.limit)

    total = len(todo)
    print(f"Colleges to search: {total}")
    found = 0

    for i, (idx, row) in enumerate(todo.iterrows(), 1):
        name = row["college_name"]
        city = row.get("city", "")
        district = row.get("district", "")
        print(f"[{i:>3}/{total}] {name[:57]:<57}", end="", flush=True)

        c = get_contacts(name, city, district)
        for col in ["email", "phone", "tpo_email", "tpo_phone", "source_url", "status"]:
            if c.get(col):
                df.at[idx, col] = c[col]

        if c["status"] == "Search: found":
            found += 1
            info = (c["email"] or c["phone"])[:38]
            print(f" FOUND: {info}")
        else:
            print(f" {c['status']}")

        if i % 20 == 0:
            df.to_csv(args.output, index=False, encoding="utf-8-sig")
            print(f"\n--- Checkpoint {i}/{total}, found={found} ---\n")

        time.sleep(args.delay)

    # Final save
    df.to_csv(args.output, index=False, encoding="utf-8-sig")
    xlsx = Path(args.output).with_suffix(".xlsx")
    try:
        df.to_excel(xlsx, index=False)
    except Exception as ex:
        print(f"Excel error: {ex}")

    has = df[(df["email"] != "") | (df["phone"] != "")]
    print(f"\nDone. Searched={total}  Found={found}")
    print(f"CSV:   {args.output}")
    print(f"Excel: {xlsx}")
    print(f"\nDistrict contact coverage:")
    for d in sorted(df["district"].unique()):
        dt = len(df[df["district"] == d])
        df2 = len(has[has["district"] == d])
        pct = int(100 * df2 / dt) if dt else 0
        bar = "#" * (pct // 5) + "-" * (20 - pct // 5)
        print(f"  {d:20s}: {df2:>3}/{dt:<3} [{bar}] {pct}%")


if __name__ == "__main__":
    main()
