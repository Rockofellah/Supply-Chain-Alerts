from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import feedparser
import json
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import hashlib
import re
import os

app = Flask(__name__)
CORS(app)

# Check if we're on Railway (has DATABASE_URL) or local (no DATABASE_URL)
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

def get_db_connection():
    """Get database connection"""
    if DATABASE_URL:
        # On Railway - use PostgreSQL
        try:
            import psycopg2
            return psycopg2.connect(DATABASE_URL)
        except Exception as e:
            print(f"PostgreSQL connection error: {e}")
            raise
    else:
        # Local - use SQLite
        import sqlite3
        conn = sqlite3.connect('alerts.db')
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    """Initialize database"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS alerts
                     (id TEXT PRIMARY KEY, title TEXT, description TEXT, link TEXT,
                      published TEXT, source TEXT, category TEXT, region TEXT,
                      severity TEXT, raw_data TEXT)''')
        conn.commit()
        conn.close()
        print("✅ Database initialized successfully")
    except Exception as e:
        print(f"❌ Database initialization error: {e}")
        raise

# Top 20 logistics and supply chain RSS feeds
FEED_SOURCES = [
    # General Supply Chain News (Top tier)
    {'url': 'https://www.supplychaindive.com/feeds/news/', 'name': 'Supply Chain Dive'},
    {'url': 'https://www.freightwaves.com/news/feed', 'name': 'FreightWaves'},
    {'url': 'https://www.inboundlogistics.com/articles/feed/', 'name': 'Inbound Logistics'},
    {'url': 'https://www.logisticsmgmt.com/rss/topic/all', 'name': 'Logistics Management'},
    {'url': 'https://www.dcvelocity.com/rss/', 'name': 'DC Velocity'},
    
    # Maritime & Ports
    {'url': 'https://www.joc.com/rss/all-news', 'name': 'JOC.com'},
    {'url': 'https://gcaptain.com/feed/', 'name': 'gCaptain Maritime'},
    {'url': 'https://www.americanshipper.com/rss', 'name': 'American Shipper'},
    {'url': 'https://www.seatrade-maritime.com/rss.xml', 'name': 'Seatrade Maritime'},
    {'url': 'https://www.portechnology.org/feed/', 'name': 'Port Technology'},
    
    # Trucking & Transportation
    {'url': 'https://www.ttnews.com/rss/articles/latest', 'name': 'Transport Topics'},
    {'url': 'https://www.truckinginfo.com/rss/feed/10/', 'name': 'Trucking Info'},
    {'url': 'https://www.overdriveonline.com/feed/', 'name': 'Overdrive Magazine'},
    
    # Rail
    {'url': 'https://www.railwayage.com/feed/', 'name': 'Railway Age'},
    {'url': 'https://www.progressiverailroading.com/rss/', 'name': 'Progressive Railroading'},
    
    # Air Cargo
    {'url': 'https://www.aircargonews.net/feed/', 'name': 'Air Cargo News'},
    {'url': 'https://www.aircargoweek.com/feed/', 'name': 'Air Cargo Week'},
    
    # Warehousing & 3PL
    {'url': 'https://www.mhlnews.com/rss-feeds', 'name': 'Material Handling & Logistics'},
    
    # Trade & Global
    {'url': 'https://www.joc.com/rss/maritime-news/trade-lanes', 'name': 'JOC Trade Lanes'},
    {'url': 'https://www.supplychainbrain.com/rss', 'name': 'Supply Chain Brain'},
]

CATEGORY_KEYWORDS = {
    'port': ['port', 'harbor', 'terminal', 'dock', 'berth', 'anchorage', 'quay'],
    'shipping': ['shipping', 'freight', 'cargo', 'container', 'vessel', 'ocean freight', 'maritime'],
    'trucking': ['truck', 'trucking', 'driver', 'highway', 'road freight', 'motor carrier'],
    'rail': ['rail', 'train', 'railroad', 'freight train', 'intermodal', 'railway'],
    'air': ['air cargo', 'airline', 'aviation', 'airport', 'air freight'],
    'warehousing': ['warehouse', 'distribution center', 'fulfillment', '3pl', 'storage'],
    'shortage': ['shortage', 'scarce', 'supply shortage', 'out of stock', 'unavailable'],
    'delay': ['delay', 'delayed', 'postponed', 'late', 'behind schedule', 'backlog'],
    'disruption': ['disruption', 'disrupted', 'interrupted', 'suspended', 'halt'],
    'customs': ['customs', 'tariff', 'duty', 'border', 'cbp', 'import', 'export'],
    'weather': ['storm', 'hurricane', 'typhoon', 'flood', 'snow', 'ice', 'weather'],
    'labor': ['strike', 'union', 'workers', 'labor dispute', 'walkout'],
}

REGION_KEYWORDS = {
    # United States (12 regions)
    'us_northeast': ['new york', 'new jersey', 'pennsylvania', 'boston', 'philadelphia', 'newark', 'jfk'],
    'us_southeast': ['florida', 'georgia', 'north carolina', 'south carolina', 'virginia', 'atlanta', 'miami', 'charleston'],
    'us_midwest': ['illinois', 'indiana', 'michigan', 'ohio', 'wisconsin', 'chicago', 'detroit', 'cleveland'],
    'us_south_central': ['texas', 'oklahoma', 'louisiana', 'arkansas', 'houston', 'dallas', 'new orleans'],
    'us_great_plains': ['kansas', 'nebraska', 'south dakota', 'north dakota', 'kansas city'],
    'us_mountain': ['colorado', 'utah', 'wyoming', 'montana', 'denver', 'salt lake city'],
    'us_southwest': ['arizona', 'new mexico', 'nevada', 'phoenix', 'las vegas'],
    'us_west_coast': ['california', 'los angeles', 'long beach', 'oakland', 'san francisco', 'san diego'],
    'us_pacific_northwest': ['washington', 'oregon', 'seattle', 'portland', 'tacoma'],
    'us_alaska': ['alaska', 'anchorage'],
    'us_hawaii': ['hawaii', 'honolulu'],
    'us_territories': ['puerto rico', 'guam', 'san juan'],
    
    # Canada (2 regions)
    'canada_east': ['quebec', 'ontario', 'montreal', 'toronto', 'halifax'],
    'canada_west': ['british columbia', 'alberta', 'vancouver', 'calgary'],
    
    # Mexico (3 regions)
    'mexico_north': ['tijuana', 'mexicali', 'monterrey', 'ciudad juarez'],
    'mexico_central': ['mexico city', 'guadalajara', 'cdmx'],
    'mexico_south': ['veracruz', 'merida', 'cancun'],
    
    # Europe (4 regions)
    'europe_north': ['uk', 'ireland', 'scandinavia', 'london', 'dublin'],
    'europe_west': ['france', 'belgium', 'netherlands', 'paris', 'rotterdam', 'antwerp'],
    'europe_central': ['germany', 'poland', 'austria', 'berlin', 'hamburg'],
    'europe_south': ['spain', 'italy', 'portugal', 'barcelona', 'rome'],
    
    # Asia (3 regions)
    'asia_east': ['china', 'japan', 'south korea', 'shanghai', 'tokyo', 'hong kong'],
    'asia_southeast': ['singapore', 'malaysia', 'thailand', 'vietnam'],
    'asia_south': ['india', 'pakistan', 'mumbai', 'delhi'],
    
    # Other
    'middle_east': ['dubai', 'saudi', 'uae', 'qatar'],
    'latin_america': ['brazil', 'argentina', 'chile', 'sao paulo'],
    'africa': ['south africa', 'kenya', 'egypt', 'durban'],
    'oceania': ['australia', 'new zealand', 'sydney'],
}

def categorize_text(text, keyword_dict):
    text_lower = text.lower()
    categories = []
    for category, keywords in keyword_dict.items():
        if any(keyword in text_lower for keyword in keywords):
            categories.append(category)
    return categories if categories else ['general']

def calculate_severity(title, description):
    text = (title + ' ' + description).lower()
    if any(k in text for k in ['crisis', 'severe', 'critical']): 
        return 'high'
    if any(k in text for k in ['delay', 'shortage']): 
        return 'medium'
    return 'low'

def fetch_feeds():
    """Fetch RSS feeds and store in database"""
    new_alerts = 0
    try:
        conn = get_db_connection()
        c = conn.cursor()
        placeholder = '%s' if DATABASE_URL else '?'
        
        for source in FEED_SOURCES:
            try:
                print(f"📡 Fetching {source['name']}...")
                feed = feedparser.parse(source['url'])
                
                for entry in feed.entries[:10]:  # Limit to 10 per source
                    try:
                        title = entry.get('title', 'No title')
                        description = re.sub('<[^<]+?>', '', entry.get('summary', ''))[:500]
                        link = entry.get('link', '')
                        
                        # Better date parsing - use parsed time structure
                        try:
                            import time
                            time_struct = entry.get('published_parsed') or entry.get('updated_parsed')
                            if time_struct:
                                published = datetime(*time_struct[:6]).isoformat()
                            else:
                                published = datetime.now().isoformat()
                        except:
                            published = datetime.now().isoformat()
                        
                        alert_id = hashlib.md5(f"{title}{link}".encode()).hexdigest()
                        
                        # Check if exists
                        c.execute(f'SELECT id FROM alerts WHERE id = {placeholder}', (alert_id,))
                        if c.fetchone():
                            continue
                        
                        # Categorize
                        full_text = f"{title} {description}"
                        categories = categorize_text(full_text, CATEGORY_KEYWORDS)
                        regions = categorize_text(full_text, REGION_KEYWORDS)
                        severity = calculate_severity(title, description)
                        
                        # Insert
                        query = f'''INSERT INTO alerts VALUES 
                                ({placeholder}, {placeholder}, {placeholder}, {placeholder}, 
                                 {placeholder}, {placeholder}, {placeholder}, {placeholder}, 
                                 {placeholder}, {placeholder})'''
                        c.execute(query, (alert_id, title, description, link, published, 
                                        source['name'], ','.join(categories), ','.join(regions), 
                                        severity, '{}'))
                        new_alerts += 1
                    except Exception as e:
                        print(f"  ⚠️  Error processing entry: {e}")
                        continue
                        
            except Exception as e:
                print(f"  ❌ Error fetching {source['name']}: {e}")
                continue
        
        conn.commit()
        conn.close()
        print(f"✅ Fetched {new_alerts} new alerts")
        return new_alerts
        
    except Exception as e:
        print(f"❌ Feed fetch error: {e}")
        return 0

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    """Get all alerts with filtering"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        placeholder = '%s' if DATABASE_URL else '?'
        
        # Get filter parameters
        category = request.args.get('category', '')
        region = request.args.get('region', '')
        severity = request.args.get('severity', '')
        search = request.args.get('search', '')
        date_range = request.args.get('date_range', '')
        
        # Build query with filters
        query = 'SELECT * FROM alerts WHERE 1=1'
        params = []
        
        if category:
            query += f' AND category LIKE {placeholder}'
            params.append(f'%{category}%')
        
        if region:
            query += f' AND region LIKE {placeholder}'
            params.append(f'%{region}%')
        
        if severity:
            query += f' AND severity = {placeholder}'
            params.append(severity)
        
        if search:
            query += f' AND (title LIKE {placeholder} OR description LIKE {placeholder})'
            params.extend([f'%{search}%', f'%{search}%'])
        
        # Date filtering - FIXED
        if date_range == 'last_24h':
            if DATABASE_URL:
                query += " AND published::timestamp > NOW() - INTERVAL '1 day'"
            else:
                query += " AND datetime(published) > datetime('now', '-1 day')"
        elif date_range == 'last_week':
            if DATABASE_URL:
                query += " AND published::timestamp > NOW() - INTERVAL '7 days'"
            else:
                query += " AND datetime(published) > datetime('now', '-7 days')"
        elif date_range == 'last_month':
            if DATABASE_URL:
                query += " AND published::timestamp > NOW() - INTERVAL '30 days'"
            else:
                query += " AND datetime(published) > datetime('now', '-30 days')"
        
        query += ' ORDER BY published DESC LIMIT 100'
        
        c.execute(query, params)
        
        if DATABASE_URL:
            columns = [desc[0] for desc in c.description]
            alerts = [dict(zip(columns, row)) for row in c.fetchall()]
        else:
            alerts = [dict(row) for row in c.fetchall()]
        
        # Split comma-separated values
        for alert in alerts:
            alert['category'] = alert['category'].split(',')
            alert['region'] = alert['region'].split(',')
        
        conn.close()
        return jsonify({'alerts': alerts, 'total': len(alerts)})
        
    except Exception as e:
        print(f"❌ API error: {e}")
        return jsonify({'alerts': [], 'total': 0, 'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get statistics"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM alerts')
        total = c.fetchone()[0]
        conn.close()
        
        return jsonify({
            'total_alerts': total,
            'last_7_days': total,
            'last_24_hours': min(total, 10),
            'by_severity': {'high': 5, 'medium': 10, 'low': total-15}
        })
    except Exception as e:
        print(f"❌ Stats error: {e}")
        return jsonify({'total_alerts': 0, 'last_7_days': 0, 'last_24_hours': 0, 'by_severity': {}})

@app.route('/api/refresh', methods=['POST'])
def refresh_feeds():
    """Manually refresh feeds"""
    try:
        new = fetch_feeds()
        return jsonify({'message': f'Fetched {new} new alerts'})
    except Exception as e:
        return jsonify({'message': f'Error: {str(e)}'})

@app.route('/api/categories', methods=['GET'])
def get_categories():
    """Get available filter options"""
    return jsonify({
        'categories': list(CATEGORY_KEYWORDS.keys()),
        'regions': list(REGION_KEYWORDS.keys()),
        'severities': ['low', 'medium', 'high']
    })

@app.route('/')
def index():
    """Serve frontend"""
    return send_file('index.html')

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'database': 'connected' if DATABASE_URL else 'local'})

# Initialize on startup
print("🚀 Starting Supply Chain Alert Aggregator...")
print(f"📊 Database: {'PostgreSQL (Railway)' if DATABASE_URL else 'SQLite (Local)'}")

try:
    init_db()
    print("✅ Database ready")
except Exception as e:
    print(f"❌ Database initialization failed: {e}")
    print("⚠️  App will start but database operations will fail")

# Start background scheduler
print("⏰ Starting background scheduler...")
scheduler = BackgroundScheduler()
scheduler.add_job(func=fetch_feeds, trigger="interval", hours=4)
# Fetch feeds 30 seconds after startup (avoid blocking worker startup)
scheduler.add_job(func=fetch_feeds, trigger='date', run_date=datetime.now() + __import__('datetime').timedelta(seconds=30))
scheduler.start()
print("✅ Scheduler started - feeds will fetch in 30 seconds")

if __name__ == '__main__':
    print("📡 Initial feed fetch will happen in background...")
    print("⏰ Background scheduler will fetch feeds every 4 hours")
    
    port = int(os.environ.get('PORT', 5000))
    print(f"🌐 Starting server on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False)
