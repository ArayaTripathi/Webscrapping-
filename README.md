# India College & University Contact Scraper

Python project to process up to **1000 institutions in one run** and collect publicly listed contact details from official college/university websites.

## Default target

- State: Maharashtra
- Districts: Beed, Bhandara, Buldhana, Chandrapur, Dhule, Gadchiroli, Gondia, Hingoli, Jalgaon, Jalna

## Output fields

- College / University Name
- University Name
- Institution Type
- Email
- Phone
- TPO / Placement Email
- TPO / Placement Phone
- State
- District
- City
- Address
- Website
- Source URL
- Status

## Folder structure

```text
india_college_scraper/
├── scraper.py
├── requirements.txt
├── README.md
├── institutions_sample.csv
├── run_windows.bat
├── .gitignore
└── output/
```

## Windows setup

1. Install Python 3.10 or newer.
2. Open Command Prompt inside this folder.
3. Create virtual environment:

```bash
python -m venv venv
```

4. Activate it:

```bash
venv\Scripts\activate
```

5. Install libraries:

```bash
pip install -r requirements.txt
```

6. Copy `institutions_sample.csv` and rename the copy to `institutions.csv`.
7. Replace the sample rows with your real master list of institutions and official websites.
8. Run:

```bash
python scraper.py
```

You can also double-click `run_windows.bat` after `institutions.csv` is ready.

## Input CSV columns

```text
college_name,university_name,institution_type,website,state,district,city,address
```

Example:

```csv
ABC Engineering College,,College,https://abc.edu.in,Maharashtra,Beed,Beed,Full address
```

## Output

The scraper creates:

```text
output/college_contacts.csv
output/college_contacts.xlsx
```

## Useful commands

Process only 200 institutions:

```bash
python scraper.py --max-records 200
```

Process up to 1000 institutions:

```bash
python scraper.py --max-records 1000
```

Use 20 concurrent requests:

```bash
python scraper.py --concurrency 20
```

All Maharashtra districts:

```bash
python scraper.py --districts ""
```

Only Pune, Nashik and Nagpur:

```bash
python scraper.py --state Maharashtra --districts "Pune,Nashik,Nagpur"
```

Another state:

```bash
python scraper.py --state Karnataka --districts ""
```

## How it works

```text
Institution master list
        ↓
Filter state/district
        ↓
Open official website
        ↓
Check robots.txt
        ↓
Find Contact / Placement / TPO pages
        ↓
Extract public email and phone details
        ↓
Detect TPO/placement contact near relevant keywords
        ↓
Remove duplicates
        ↓
Save CSV + Excel
```

## Important

- `MAX_RECORDS=1000` means up to 1000 institutions can be processed in one run; it does **not** mean 1000 simultaneous requests.
- Recommended concurrency is **10-20**. Very high concurrency may trigger rate limits or block your IP.
- Use an official institution master list (for example, a government/official directory) as the source for `institutions.csv`.
- Some websites use JavaScript, CAPTCHAs, anti-bot protection, or image-based contact details; those records may remain blank.
- TPO numbers are collected only when publicly listed on an official institution page.
- Respect website Terms of Service, robots.txt, rate limits, privacy rules, and applicable law.

## Common problems

**ModuleNotFoundError**

```bash
pip install -r requirements.txt
```

**institutions.csv not found**

Create it by copying `institutions_sample.csv`.

**Many blank contacts**

The site may be JavaScript-only, unavailable, blocked, or may not publish the information publicly.
