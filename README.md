# OpenRice Hong Kong New Restaurants Tracker

A web app that tracks newly listed restaurants on OpenRice Hong Kong for the latest 7-day window.

## Quick Setup (1 minute)

```bash
pip install -r requirements.txt
python app.py    # serves at http://127.0.0.1:7860
```

## Features

- Scrapes OpenRice HK for new restaurant listings from the past week
- Displays results in a clean table format (Name | Address)
- Automatic weekly updates every Monday at 02:00 HKT
- SQLite caching for reliable data serving
- Responsive design with Tailwind CSS

## Current Week

**28 Jul – 4 Aug 2025** (updates weekly)