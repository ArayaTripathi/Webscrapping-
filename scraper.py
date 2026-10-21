import argparse
import asyncio
import random
import re
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import aiohttp
import pandas as pd
import requests as req_lib
from bs4 import BeautifulSoup

# Suppress SSL warnings from the requests fallback
warnings.filterwarnings("ignore", message="Unverified HTTPS")

# Thread pool for running synchronous requests fallback
_EXECUTOR = ThreadPoolExecutor(max_workers=8)

DEFAULT_DISTRICTS = [
    "Raigad", "Ratnagiri", "Wardha", "Yavatmal", "Parbhani",
    "Palghar", "Nandurbar", "Beed", "Bhandara", "Buldhana",
    "Chandrapur", "Dhule", "Gadchiroli", "Gondia", "Hingoli",
    "Jalgaon", "Jalna"
]

# Rotate between realistic browser User-Agents to bypass basic bot detection
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?:\+91[\-\s]?)?(?:[6-9]\d{9}|0\d{2,4}[\-\s]?\d{6,8})")
ROBOTS_CACHE: dict = {}


def random_headers() -> dict:
    ua = random.choice(USER_AGENTS)
    return {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
        "DNT": "1",
    }


def unique(values):
    out, seen = [], set()
    for v in values:
        v = (v or "").strip()
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def clean_email(v):
    v = v.strip().lower()
    if v.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
        return ""
    return v


async def robots_allowed(session, url, headers):
    p = urlparse(url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    ua = headers.get("User-Agent", "*")
    cache_key = (robots_url, ua)
    if cache_key in ROBOTS_CACHE:
        return ROBOTS_CACHE[cache_key].can_fetch(ua, url)

    rp = RobotFileParser()
    try:
        async with session.get(robots_url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as r:
            if r.status == 200:
                rp.parse((await r.text(errors="ignore")).splitlines())
            else:
                # If robots.txt missing/forbidden, treat as fully open
                rp.parse([])
    except Exception:
        rp.parse([])
    ROBOTS_CACHE[cache_key] = rp
    return rp.can_fetch(ua, url)


def _sync_fetch(url: str, timeout_secs: int) -> str | None:
    """
    Synchronous fallback using requests (urllib3 TLS stack).
    Some servers block aiohttp but allow requests.
    """
    hdrs = random_headers()
    try:
        r = req_lib.get(
            url, headers=hdrs, timeout=timeout_secs,
            allow_redirects=True, verify=False
        )
        ct = r.headers.get("Content-Type", "")
        if r.status_code == 200 and "text/html" in ct:
            return r.text
    except Exception:
        pass
    return None


async def fetch_with_retry(session, url, timeout_secs, retries=3, skip_robots=False):
    """
    Fetch a URL with:
    - Rotating User-Agent on each attempt
    - Exponential back-off between retries
    - Optional robots.txt skip for retry pass
    - Synchronous requests fallback on final attempt (bypasses aiohttp fingerprinting)
    """
    for attempt in range(retries):
        hdrs = random_headers()

        # Last attempt: use synchronous requests as fallback (different TLS fingerprint)
        if attempt == retries - 1:
            loop = asyncio.get_event_loop()
            html = await loop.run_in_executor(
                _EXECUTOR, _sync_fetch, url, timeout_secs
            )
            return html  # None or content

        try:
            if not skip_robots:
                if not await robots_allowed(session, url, hdrs):
                    return None

            timeout = aiohttp.ClientTimeout(total=timeout_secs + attempt * 5)
            async with session.get(
                url, headers=hdrs, timeout=timeout,
                allow_redirects=True
            ) as r:
                ct = r.headers.get("Content-Type", "")
                if r.status == 200 and "text/html" in ct:
                    return await r.text(errors="ignore")
                if r.status in (403, 429, 503):
                    wait = (2 ** attempt) + random.uniform(1, 3)
                    await asyncio.sleep(wait)
                    continue
                return None
        except asyncio.TimeoutError:
            pass
        except Exception:
            pass

        wait = (1.5 ** attempt) + random.uniform(0.5, 2)
        await asyncio.sleep(wait)

    return None


def extract_contacts(html):
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)
    emails = unique(clean_email(x) for x in EMAIL_RE.findall(text))
    phones = unique(PHONE_RE.findall(text))
    return emails, phones, text


def discover_pages(html, base_url):
    soup = BeautifulSoup(html, "lxml")
    keywords = [
        "contact", "contact us", "placement", "training and placement",
        "training & placement", "tpo", "placement cell", "career", "about",
        "reach us", "connect", "enquiry"
    ]
    links = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        label = a.get_text(" ", strip=True).lower()
        if any(k in f"{label} {href.lower()}" for k in keywords):
            u = urljoin(base_url, href)
            if urlparse(u).netloc == urlparse(base_url).netloc:
                links.append(u)
    return unique(links)[:8]


def tpo_details(text):
    compact = re.sub(r"\s+", " ", text)
    lower = compact.lower()
    keywords = [
        "training and placement officer", "training & placement officer",
        "placement officer", "placement coordinator", "placement cell", "tpo",
        "t&p officer", "t & p officer"
    ]
    email = phone = ""
    for keyword in keywords:
        pos = lower.find(keyword)
        if pos == -1:
            continue
        ctx = compact[max(0, pos - 200):pos + 500]
        if not email:
            found = EMAIL_RE.findall(ctx)
            email = clean_email(found[0]) if found else ""
        if not phone:
            found = PHONE_RE.findall(ctx)
            phone = found[0] if found else ""
        if email and phone:
            break
    return email, phone


async def scrape_one(session, row, sem, timeout, skip_robots=False):
    async with sem:
        website = str(row.get("website", "")).strip()
        result = {
            "college_name": row.get("college_name", ""),
            "university_name": row.get("university_name", ""),
            "institution_type": row.get("institution_type", ""),
            "email": "", "phone": "", "tpo_email": "", "tpo_phone": "",
            "state": row.get("state", ""), "district": row.get("district", ""),
            "city": row.get("city", ""), "address": row.get("address", ""),
            "website": website, "source_url": "", "status": ""
        }
        if not website.startswith(("http://", "https://")):
            result["status"] = "Invalid website"
            return result

        # Small random initial delay to stagger requests
        await asyncio.sleep(random.uniform(0.3, 1.2))

        home = await fetch_with_retry(session, website, timeout, retries=3, skip_robots=skip_robots)
        if not home:
            result["status"] = "Website unavailable or blocked"
            return result

        emails, phones, _ = extract_contacts(home)
        sources = [website]
        all_emails, all_phones = list(emails), list(phones)
        tpo_email = tpo_phone = ""

        for page in discover_pages(home, website):
            await asyncio.sleep(random.uniform(0.5, 1.5))
            html = await fetch_with_retry(session, page, timeout, retries=2, skip_robots=skip_robots)
            if not html:
                continue
            e, p, text = extract_contacts(html)
            all_emails.extend(e)
            all_phones.extend(p)
            sources.append(page)
            te, tp = tpo_details(text)
            tpo_email = tpo_email or te
            tpo_phone = tpo_phone or tp

        all_emails, all_phones = unique(all_emails), unique(all_phones)
        result["email"] = all_emails[0] if all_emails else ""
        result["phone"] = all_phones[0] if all_phones else ""
        result["tpo_email"] = tpo_email
        result["tpo_phone"] = tpo_phone
        result["source_url"] = " | ".join(unique(sources))
        result["status"] = "Scraped"
        return result


async def main(args):
    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(
            f"{input_path} not found. Run fetch_colleges.py first or add institutions manually."
        )

    df = pd.read_csv(input_path)
    for col in ["college_name", "university_name", "institution_type", "website",
                "state", "district", "city", "address"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str).str.strip()

    if args.state:
        df = df[df["state"].str.lower() == args.state.lower()]
    districts = [x.strip() for x in args.districts.split(",") if x.strip()]
    if districts:
        wanted = {x.lower() for x in districts}
        df = df[df["district"].str.lower().isin(wanted)]

    # --retry-blocked mode: load previous output and only redo failed rows
    if args.retry_blocked and Path(args.output_csv).exists():
        prev = pd.read_csv(args.output_csv)
        blocked_names = set(
            prev.loc[prev["status"] != "Scraped", "college_name"].str.strip()
        )
        blocked_df = df[df["college_name"].isin(blocked_names)].copy()
        good_df = prev[prev["status"] == "Scraped"].copy()
        print(f"Re-trying {len(blocked_df)} previously blocked institutions …")
        print(f"Keeping {len(good_df)} already-scraped records.")
        process_df = blocked_df
    else:
        df = df.drop_duplicates(subset=["college_name", "website"]).head(args.max_records)
        process_df = df
        good_df = pd.DataFrame()

    print(f"Institutions to process: {len(process_df)}")

    sem = asyncio.Semaphore(args.concurrency)
    connector = aiohttp.TCPConnector(limit=args.concurrency, ssl=False)
    results = []

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [
            scrape_one(session, row, sem, args.timeout, skip_robots=args.skip_robots)
            for _, row in process_df.iterrows()
        ]
        for i, fut in enumerate(asyncio.as_completed(tasks), 1):
            r = await fut
            results.append(r)
            status_icon = "OK" if r["status"] == "Scraped" else "--"
            print(f"  [{i}/{len(tasks)}] [{status_icon}] {r['college_name']} - {r['status']}")

    out = pd.DataFrame(results)

    # Merge with kept good results if retry mode
    if not good_df.empty:
        out = pd.concat([good_df, out], ignore_index=True)

    csv_path = Path(args.output_csv)
    xlsx_path = Path(args.output_excel)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(csv_path, index=False, encoding="utf-8-sig")
    out.to_excel(xlsx_path, index=False)

    scraped_n = (out["status"] == "Scraped").sum()
    blocked_n = (out["status"] != "Scraped").sum()
    print(f"\n{'='*55}")
    print(f"  Done!")
    print(f"  Total records : {len(out)}")
    print(f"  Scraped OK    : {scraped_n}")
    print(f"  Still blocked : {blocked_n}")
    print(f"  CSV  : {csv_path}")
    print(f"  Excel: {xlsx_path}")
    print(f"{'='*55}")


def parse_args():
    p = argparse.ArgumentParser(description="India College Contact Scraper")
    p.add_argument("--input", default="institutions.csv")
    p.add_argument("--output-csv", default="output/college_contacts.csv")
    p.add_argument("--output-excel", default="output/college_contacts.xlsx")
    p.add_argument("--max-records", type=int, default=1000)
    p.add_argument("--concurrency", type=int, default=10,
                   help="Simultaneous requests (1-30, recommended 8-15)")
    p.add_argument("--timeout", type=int, default=30,
                   help="Per-request timeout in seconds (increased for slow govt sites)")
    p.add_argument("--state", default="Maharashtra")
    p.add_argument("--districts", default=",".join(DEFAULT_DISTRICTS))
    p.add_argument("--retry-blocked", action="store_true",
                   help="Re-scrape only rows that were blocked in the previous run")
    p.add_argument("--skip-robots", action="store_true",
                   help="Skip robots.txt check (use for retry pass on govt sites)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if not 1 <= args.concurrency <= 30:
        raise ValueError("Use concurrency between 1 and 30.")
    asyncio.run(main(args))
