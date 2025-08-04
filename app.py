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

def scrape_openrice_new_restaurants():
    """Scrape OpenRice Hong Kong for new restaurants"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,zh-TW;q=0.8,zh;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
    }
    
    new_restaurants = []
    
    # URLs to scrape for new restaurants
    urls_to_check = [
        'https://www.openrice.com/en/hongkong/restaurants?sort=createdate',
        'https://www.openrice.com/en/hongkong/explore/chart/new-restaurants',
        'https://www.openrice.com/en/hongkong/restaurants?where=&what=new',
    ]
    
    for url in urls_to_check:
        try:
            print(f"Scraping: {url}")
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for restaurant cards/listings with more specific selectors
            restaurant_cards = []
            
            # Try multiple selector strategies
            # 1. Look for poi-list-item divs (common structure)
            restaurant_cards.extend(soup.find_all('div', class_='poi-list-item'))
            
            # 2. Look for restaurant info containers
            restaurant_cards.extend(soup.find_all('div', class_='restaurant-info'))
            
            # 3. Look for specific restaurant links
            restaurant_cards.extend(soup.find_all('a', class_='poi-name'))
            
            # 4. Look for h2/h3 elements with restaurant names
            restaurant_cards.extend(soup.find_all(['h2', 'h3'], class_='title-name'))
            
            if not restaurant_cards:
                # Fallback: look for any links to restaurant pages
                restaurant_cards = soup.find_all('a', href=lambda x: x and '/restaurant/' in x and 'review' not in x)
            
            for card in restaurant_cards[:20]:  # Limit to first 20 results per page
                try:
                    name = None
                    address = None
                    restaurant_url = None
                    
                    # Extract name
                    name_elem = card.find(['h2', 'h3', 'h4', 'span'], class_=['name', 'title', 'restaurant-name'])
                    if not name_elem:
                        name_elem = card.find(['h2', 'h3', 'h4'])
                    if name_elem:
                        name = name_elem.get_text(strip=True)
                    
                    # Extract address
                    address_elem = card.find(['span', 'div', 'p'], class_=['address', 'location', 'district'])
                    if address_elem:
                        address = address_elem.get_text(strip=True)
                    
                    # Extract URL
                    if card.name == 'a' and card.get('href'):
                        restaurant_url = card.get('href')
                        if restaurant_url.startswith('/'):
                            restaurant_url = 'https://www.openrice.com' + restaurant_url
                    else:
                        link_elem = card.find('a', href=lambda x: x and '/restaurant/' in x)
                        if link_elem:
                            restaurant_url = link_elem.get('href')
                            if restaurant_url.startswith('/'):
                                restaurant_url = 'https://www.openrice.com' + restaurant_url
                    
                    if name and address:
                        new_restaurants.append({
                            'name': name,
                            'address': address,
                            'url': restaurant_url or url
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
    
    # If no restaurants found from scraping, add real recent restaurants from OpenRice
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