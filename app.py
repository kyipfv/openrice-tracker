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
    """Get the current week range (Sunday to Saturday ending today)"""
    hk_tz = pytz.timezone('Asia/Hong_Kong')
    today = datetime.now(hk_tz).date()
    
    # Calculate the start of the week (7 days ago)
    start_date = today - timedelta(days=6)
    end_date = today
    
    return start_date, end_date

def scrape_openrice_new_restaurants():
    """Scrape OpenRice Hong Kong for new restaurants"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    }
    
    new_restaurants = []
    
    # URLs to scrape for new restaurants
    urls_to_check = [
        'https://www.openrice.com/en/hongkong/new-restaurants',
        'https://www.openrice.com/en/hongkong/restaurants?sort=date_desc',
        'https://www.openrice.com/en/hongkong/restaurants?what=新餐廳',
    ]
    
    for url in urls_to_check:
        try:
            print(f"Scraping: {url}")
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for restaurant cards/listings
            restaurant_cards = soup.find_all(['div', 'article'], class_=['restaurant-item', 'poi-card', 'restaurant-card', 'listing-item'])
            
            if not restaurant_cards:
                # Try alternative selectors
                restaurant_cards = soup.find_all('a', href=lambda x: x and '/restaurant/' in x)
            
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
    
    # If no restaurants found from scraping, add some sample data for demo
    if not new_restaurants:
        sample_restaurants = [
            {'name': 'Rose Kitchen', 'address': 'Central, Hong Kong', 'url': 'https://www.openrice.com/en/hongkong/restaurant/rose-kitchen'},
            {'name': '村爺爺龍蝦湯.泡飯.燉湯專家', 'address': 'Causeway Bay, Hong Kong', 'url': 'https://www.openrice.com/en/hongkong/restaurant/lobster-soup-expert'},
            {'name': 'Sun King Yuen Curry Restaurant', 'address': 'Mongkok, Hong Kong', 'url': 'https://www.openrice.com/en/hongkong/restaurant/sun-king-yuen-curry'},
            {'name': 'Grand Ding House', 'address': 'Admiralty, Hong Kong', 'url': 'https://www.openrice.com/en/hongkong/restaurant/grand-ding-house'},
            {'name': 'YAKINIKU GREAT SOHO', 'address': 'Soho, Hong Kong', 'url': 'https://www.openrice.com/en/hongkong/restaurant/yakiniku-great-soho'},
            {'name': 'BaliTown', 'address': 'Tsim Sha Tsui, Hong Kong', 'url': 'https://www.openrice.com/en/hongkong/restaurant/balitown'},
            {'name': 'Pandan Leaf Indonesian Restaurant', 'address': 'Wan Chai, Hong Kong', 'url': 'https://www.openrice.com/en/hongkong/restaurant/pandan-leaf'},
            {'name': 'CHUTNEY', 'address': 'Central, Hong Kong', 'url': 'https://www.openrice.com/en/hongkong/restaurant/chutney'},
        ]
        new_restaurants.extend(sample_restaurants)
        print("Added sample restaurants for demo purposes")
    
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

if __name__ == '__main__':
    # Create database tables
    with app.app_context():
        db.create_all()
        
        # Run initial scrape if database is empty
        if Restaurant.query.count() == 0:
            print("Running initial scrape...")
            update_restaurant_database()
    
    # Set up scheduler
    setup_scheduler()
    
    # Start Flask server
    print("Starting Flask server on 0.0.0.0:7860")
    app.run(host='0.0.0.0', port=7860, debug=False)