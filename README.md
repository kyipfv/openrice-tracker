# OpenRice Hong Kong New Restaurants Tracker

A web app that tracks newly listed restaurants in Hong Kong for the latest 7-day window using Google Maps API.

## Quick Setup (1 minute)

```bash
pip install -r requirements.txt

# Optional: Set Google Maps API key for fresh data
export GOOGLE_MAPS_API_KEY2="your-api-key-here"

python app.py    # serves at http://127.0.0.1:7860
```

## Google Maps API Setup (Recommended)

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project or select existing
3. Enable "Places API" and "Maps JavaScript API"
4. Create credentials (API Key)
5. Set the environment variable: `export GOOGLE_MAPS_API_KEY2="your-key"`

Without API key: Falls back to sample restaurant data

## Features

- Scrapes OpenRice HK for new restaurant listings from the past week
- Displays results in a clean table format (Name | Address)
- Automatic weekly updates every Monday at 02:00 HKT
- SQLite caching for reliable data serving
- Responsive design with Tailwind CSS

## Current Week

**28 Jul – 4 Aug 2025** (updates weekly)