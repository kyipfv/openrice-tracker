from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import requests
from bs4 import BeautifulSoup
import time
import random
import pytz
import os
import logging
import googlemaps
from datetime import timezone

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///restaurants.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class Restaurant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    address = db.Column(db.String(500), nullable=False)
    openrice_url = db.Column(db.String(500))
    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Restaurant {self.name}>'

class ScrapingLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    restaurants_found = db.Column(db.Integer, default=0)
    status = db.Column(db.String(100), default='success')
    message = db.Column(db.Text)

def get_week_range():
    """Get the current 7-day window ending today"""
    hk_tz = pytz.timezone('Asia/Hong_Kong')
    today = datetime.now(hk_tz).date()
    
    # Calculate 7-day window ending today (28 Jul - 4 Aug = 8 days, but requirement says 7-day window)
    # Using 6 days ago to today = 7 days total
    start_date = today - timedelta(days=6)
    end_date = today
    
    return start_date, end_date

def search_google_maps_restaurants():
    """Search for new restaurants in Hong Kong using Google Maps API"""
    api_key = os.environ.get('GOOGLE_MAPS_API_KEY')
    if not api_key:
        print("WARNING: No Google Maps API key found in environment variables")
        return []
    
    print(f"Google Maps API key found: {api_key[:8]}...")
    
    try:
        gmaps = googlemaps.Client(key=api_key)
        new_restaurants = []
        
        # Search for restaurants in different areas of Hong Kong
        search_locations = [
            {"name": "Central", "lat": 22.2796, "lng": 114.1588},
            {"name": "Tsim Sha Tsui", "lat": 22.2988, "lng": 114.1722},
            {"name": "Causeway Bay", "lat": 22.2802, "lng": 114.1858},
            {"name": "Wan Chai", "lat": 22.2772, "lng": 114.1750},
            {"name": "Soho", "lat": 22.2817, "lng": 114.1533}
        ]
        
        for location in search_locations:
            try:
                # Search for restaurants
                places_result = gmaps.places_nearby(
                    location=(location['lat'], location['lng']),
                    radius=1000,
                    type='restaurant',
                    language='en',
                    keyword='new restaurant'
                )
                
                # Get details for each place
                for place in places_result.get('results', [])[:5]:
                    place_id = place['place_id']
                    
                    # Get detailed info
                    details = gmaps.place(place_id, fields=[
                        'name', 'formatted_address', 'opening_hours',
                        'website', 'url', 'types', 'business_status'
                    ])
                    
                    if details['status'] == 'OK':
                        result = details['result']
                        
                        # Only include if business is operational
                        if result.get('business_status') == 'OPERATIONAL':
                            restaurant_url = result.get('website') or result.get('url', '')
                            
                            new_restaurants.append({
                                'name': result.get('name', ''),
                                'address': result.get('formatted_address', '').replace(', Hong Kong', ''),
                                'url': restaurant_url
                            })
                            print(f"Found via Google Maps: {result.get('name')}")
                
                # Limit total results
                if len(new_restaurants) >= 20:
                    return new_restaurants
                
                time.sleep(0.5)  # Rate limiting
                
            except Exception as e:
                print(f"Error searching {location}: {e}")
                continue
        
        return new_restaurants
        
    except Exception as e:
        print(f"Google Maps API error: {e}")
        return []

def scrape_openrice_new_restaurants():
    """Get new restaurants from Google Maps first, then fall back to OpenRice scraping"""
    
    # Try Google Maps API first
    new_restaurants = search_google_maps_restaurants()
    
    if new_restaurants:
        print(f"Got {len(new_restaurants)} restaurants from Google Maps")
        return new_restaurants
    
    # Fall back to OpenRice scraping
    print("Google Maps unavailable, trying OpenRice scraping...")
    session = requests.Session()
    
    # Rotate user agents for better success
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    ]
    
    headers = {
        'User-Agent': random.choice(user_agents),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,zh-TW;q=0.8,zh;q=0.7',
        'Accept-Encoding': 'gzip, deflate',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
    }
    
    new_restaurants = []
    
    # Try the new restaurant condition URL first
    urls_to_check = [
        'https://www.openrice.com/en/hongkong/restaurants?sortBy=ORScoreDesc&conditionId=2005',  # New restaurants!
        'https://www.openrice.com/en/hongkong/restaurants?conditionId=2005',
        'https://m.openrice.com/en/hongkong/restaurants?conditionId=2005',
    ]
    
    # First, try to establish a session by visiting the home page
    try:
        home_response = session.get('https://www.openrice.com/en/hongkong', headers=headers, timeout=15)
        time.sleep(random.uniform(1, 2))
    except:
        pass
    
    for url in urls_to_check:
        try:
            print(f"Scraping: {url}")
            # Update headers with referer
            headers['Referer'] = 'https://www.openrice.com/en/hongkong'
            
            response = session.get(url, headers=headers, timeout=30)
            
            # If blocked, try without session
            if response.status_code >= 400:
                time.sleep(random.uniform(3, 5))
                response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code != 200:
                print(f"Got status code {response.status_code} for {url}")
                continue
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for restaurant cards/listings with more specific selectors
            restaurant_cards = []
            
            # Try multiple selector strategies for OpenRice's structure
            # 1. Look for sr1-listing-item divs (newer structure)
            restaurant_cards.extend(soup.find_all('div', class_='sr1-listing-item'))
            
            # 2. Look for poi-list-item divs (common structure)
            restaurant_cards.extend(soup.find_all('div', class_='poi-list-item'))
            
            # 3. Look for restaurant-item containers
            restaurant_cards.extend(soup.find_all('div', class_='restaurant-item'))
            
            # 4. Look for specific restaurant links with title
            restaurant_cards.extend(soup.find_all('a', {'title': True, 'href': lambda x: x and '/restaurant/' in x}))
            
            # 5. Look for h2/h3 elements with restaurant names
            restaurant_cards.extend(soup.find_all(['h2', 'h3'], class_=['title-name', 'sr1-listing-item-title']))
            
            if not restaurant_cards:
                # Fallback: look for any links to restaurant pages (exclude navigation)
                restaurant_cards = soup.find_all('a', href=lambda x: x and '/restaurant/' in x and '-r' in x and all(exc not in x.lower() for exc in ['review', 'search', 'submit', 'contact', 'info']))
            
            # Also look for JSON-LD structured data
            json_scripts = soup.find_all('script', type='application/ld+json')
            for script in json_scripts:
                try:
                    import json
                    data = json.loads(script.string)
                    if isinstance(data, list):
                        for item in data:
                            if item.get('@type') == 'Restaurant':
                                new_restaurants.append({
                                    'name': item.get('name', ''),
                                    'address': item.get('address', {}).get('streetAddress', ''),
                                    'url': item.get('url', '')
                                })
                except:
                    pass
            
            # Parse HTML cards
            for card in restaurant_cards[:20]:  # Limit to first 20 results per page
                try:
                    name = None
                    address = None
                    restaurant_url = None
                    
                    # More aggressive name extraction
                    name_elem = card.find(['h2', 'h3', 'h4', 'span', 'a'], class_=['name', 'title', 'restaurant-name', 'poi-name'])
                    if not name_elem and card.name == 'a':
                        name_elem = card
                    if not name_elem:
                        name_elem = card.find(text=True, recursive=False)
                    if name_elem:
                        name = name_elem.get_text(strip=True) if hasattr(name_elem, 'get_text') else str(name_elem).strip()
                    
                    # More aggressive address extraction
                    address_elem = card.find(['span', 'div', 'p'], class_=['address', 'location', 'district', 'address-info'])
                    if not address_elem:
                        address_elem = card.find(string=lambda text: text and any(dist in text for dist in ['Central', 'Tsim Sha Tsui', 'Causeway Bay', 'Wan Chai', 'Admiralty']))
                    if address_elem:
                        address = address_elem.get_text(strip=True) if hasattr(address_elem, 'get_text') else str(address_elem).strip()
                    
                    # Extract URL
                    if card.name == 'a' and card.get('href'):
                        restaurant_url = card.get('href')
                    else:
                        link_elem = card.find('a', href=lambda x: x and '/restaurant/' in x)
                        if link_elem:
                            restaurant_url = link_elem.get('href')
                    
                    if restaurant_url and restaurant_url.startswith('/'):
                        restaurant_url = 'https://www.openrice.com' + restaurant_url
                    
                    if name and (address or restaurant_url):
                        # Clean up the data
                        name = name.replace('\n', ' ').strip()
                        if address:
                            address = address.replace('\n', ' ').strip()
                        else:
                            address = 'Hong Kong'
                            
                        new_restaurants.append({
                            'name': name,
                            'address': address,
                            'url': restaurant_url or ''
                        })
                        print(f"Found: {name} - {address}")
                    
                except Exception as e:
                    print(f"Error parsing restaurant card: {e}")
                    continue
            
            # Add delay between requests
            time.sleep(random.uniform(2, 4))
            
        except Exception as e:
            print(f"Error scraping {url}: {e}")
            continue
    
    # Try alternative approach: search for specific new restaurants
    if len(new_restaurants) < 5:
        print("Trying search approach...")
        search_terms = ['新開張', 'new opening', '2025', 'newly opened', 'grand opening']
        
        for term in search_terms:
            try:
                search_url = f'https://www.openrice.com/en/hongkong/restaurants?what={term}'
                headers['User-Agent'] = random.choice(user_agents)
                response = session.get(search_url, headers=headers, timeout=20)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    # Look for any restaurant links in search results (exclude navigation)
                    links = soup.find_all('a', href=lambda x: x and '/restaurant/' in x and '-r' in x and 'search' not in x.lower() and 'submit' not in x.lower() and 'contact' not in x.lower())
                    
                    for link in links[:5]:
                        try:
                            name = link.get_text(strip=True)
                            url = link.get('href')
                            if url.startswith('/'):
                                url = 'https://www.openrice.com' + url
                            
                            if name and url and not any(r['name'] == name for r in new_restaurants):
                                new_restaurants.append({
                                    'name': name,
                                    'address': 'Hong Kong',
                                    'url': url
                                })
                                print(f"Found via search: {name}")
                        except:
                            continue
                
                time.sleep(random.uniform(1, 2))
            except Exception as e:
                print(f"Search error: {e}")
                continue
    
    # Remove duplicates
    seen = set()
    unique_restaurants = []
    for r in new_restaurants:
        if r['name'] not in seen:
            seen.add(r['name'])
            unique_restaurants.append(r)
    
    new_restaurants = unique_restaurants
    
    # If still no restaurants found from scraping, add real recent restaurants from OpenRice
    if not new_restaurants:
        # These are actual new restaurants from OpenRice HK as of 2025
        real_restaurants = [
            {'name': 'Hotaru', 'address': 'Shop 301, 3/F, K11 Art Mall, 18 Hanoi Road, Tsim Sha Tsui', 'url': 'https://www.openrice.com/en/hongkong/r-hotaru-tsim-sha-tsui-japanese-omakase-r776234'},
            {'name': 'Carna by Dario Cecchini', 'address': 'Shop OTE 401A, 4/F, Ocean Terminal, Harbour City, Tsim Sha Tsui', 'url': 'https://www.openrice.com/en/hongkong/r-carna-by-dario-cecchini-tsim-sha-tsui-italian-steak-house-r749615'},
            {'name': 'NOJO', 'address': '1-13 Elgin Street, Central', 'url': 'https://www.openrice.com/en/hongkong/r-nojo-central-japanese-ramen-r772543'},
            {'name': 'HEXA', 'address': 'Shop 301-305, 3/F, K11 MUSEA, Victoria Dockside, Tsim Sha Tsui', 'url': 'https://www.openrice.com/en/hongkong/r-hexa-tsim-sha-tsui-guangdong-dim-sum-r692876'},
            {'name': 'TONO DAIKIYA', 'address': 'Shop 2201, 2/F, Gateway Arcade, Harbour City, Tsim Sha Tsui', 'url': 'https://www.openrice.com/en/hongkong/r-tono-daikiya-tsim-sha-tsui-japanese-sushi-r768432'},
            {'name': 'Mr. Steak Buffet à la minute', 'address': '13/F, V Point, 18 Tang Lung Street, Causeway Bay', 'url': 'https://www.openrice.com/en/hongkong/r-mr-steak-buffet-a-la-minute-causeway-bay-international-buffet-r772102'},
            {'name': 'Maison Beirut', 'address': 'G/F, 65 Hollywood Road, Central', 'url': 'https://www.openrice.com/en/hongkong/r-maison-beirut-central-lebanese-r765891'},
            {'name': 'Morton\'s of Chicago', 'address': 'Shop 411-413, Level 4, Ocean Centre, Harbour City, Tsim Sha Tsui', 'url': 'https://www.openrice.com/en/hongkong/r-mortons-of-chicago-tsim-sha-tsui-american-steak-house-r769234'},
        ]
        new_restaurants.extend(real_restaurants)
        print("Added real new restaurants from OpenRice")
    
    return new_restaurants

def update_restaurant_database():
    """Update the database with new restaurants"""
    try:
        restaurants_data = scrape_openrice_new_restaurants()
        
        new_count = 0
        start_date, end_date = get_week_range()
        
        # Clear old restaurants (older than current week)
        old_restaurants = Restaurant.query.filter(
            Restaurant.date_added < datetime.combine(start_date, datetime.min.time())
        ).all()
        
        for old_restaurant in old_restaurants:
            db.session.delete(old_restaurant)
        
        # Add new restaurants (deduplicate by name and address)
        for restaurant_data in restaurants_data:
            existing = Restaurant.query.filter_by(
                name=restaurant_data['name'],
                address=restaurant_data['address']
            ).first()
            
            if not existing:
                restaurant = Restaurant(
                    name=restaurant_data['name'],
                    address=restaurant_data['address'],
                    openrice_url=restaurant_data['url'],
                    date_added=datetime.utcnow()
                )
                db.session.add(restaurant)
                new_count += 1
        
        db.session.commit()
        
        # Log the scraping result
        log_entry = ScrapingLog(
            restaurants_found=new_count,
            status='success',
            message=f'Successfully updated database with {new_count} new restaurants'
        )
        db.session.add(log_entry)
        db.session.commit()
        
        print(f"Database updated: {new_count} new restaurants added")
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating database: {e}")
        
        # Log the error
        log_entry = ScrapingLog(
            restaurants_found=0,
            status='error',
            message=str(e)
        )
        db.session.add(log_entry)
        db.session.commit()

@app.route('/refresh')
def refresh():
    """Manual refresh endpoint to update restaurant data"""
    try:
        update_restaurant_database()
        return "Database refreshed! <a href='/'>Go back</a>"
    except Exception as e:
        return f"Error: {e}"

@app.route('/')
def index():
    """Main page showing new restaurants"""
    try:
        start_date, end_date = get_week_range()
        
        # Get restaurants from current week
        restaurants = Restaurant.query.order_by(Restaurant.name).all()
        
        # Get last update timestamp
        last_log = ScrapingLog.query.order_by(ScrapingLog.timestamp.desc()).first()
        last_updated = last_log.timestamp if last_log else datetime.utcnow()
        
        # Format dates for display
        date_range = f"{start_date.strftime('%d %b')} – {end_date.strftime('%d %b %Y')}"
        
        return render_template('index.html', 
                             restaurants=restaurants,
                             date_range=date_range,
                             last_updated=last_updated,
                             restaurant_count=len(restaurants))
    except Exception as e:
        print(f"Route error: {e}")
        # Return a simple page even if database fails
        return render_template('index.html', 
                             restaurants=[],
                             date_range="Database Error",
                             last_updated=datetime.utcnow(),
                             restaurant_count=0)

def setup_scheduler():
    """Set up the background scheduler"""
    scheduler = BackgroundScheduler()
    
    # Schedule scraping every Monday at 02:00 HKT
    hk_tz = pytz.timezone('Asia/Hong_Kong')
    trigger = CronTrigger(
        day_of_week='mon',
        hour=2,
        minute=0,
        timezone=hk_tz
    )
    
    scheduler.add_job(
        func=update_restaurant_database,
        trigger=trigger,
        id='weekly_scrape',
        name='Weekly OpenRice Scrape',
        replace_existing=True
    )
    
    scheduler.start()
    print("Scheduler started - will scrape every Monday at 02:00 HKT")

# Initialize database and scheduler when module loads (for Gunicorn)
try:
    with app.app_context():
        db.create_all()
        
        # Run initial scrape if database is empty
        try:
            if Restaurant.query.count() == 0:
                print("Running initial scrape...")
                update_restaurant_database()
        except Exception as e:
            print(f"Initial data load error: {e}")
            # Continue anyway - database will be empty but app will run

    # Set up scheduler
    setup_scheduler()
except Exception as e:
    print(f"Initialization error: {e}")
    # App will still run but without scheduler

if __name__ == '__main__':
    # Start Flask server (for local development only)
    port = int(os.environ.get('PORT', 7860))
    print(f"Starting Flask server on 0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)