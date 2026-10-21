@echo off
if not exist venv python -m venv venv
call venv\Scripts\activate
pip install -r requirements.txt
if not exist institutions.csv (
  echo institutions.csv not found. Copy institutions_sample.csv to institutions.csv first.
  pause
  exit /b 1
)
python scraper.py
pause
