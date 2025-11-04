from flask import Flask, jsonify, request
from flask_cors import CORS
import feedparser
import sqlite3
import json
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import hashlib
import re

app = Flask(__name__)
CORS(app)

def init_db():
    conn = sqlite3.connect('alerts.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS alerts
                 (id TEXT PRIMARY KEY, title TEXT, description TEXT, link TEXT,
                  published TEXT, source TEXT, category TEXT, region TEXT,
                  severity TEXT, raw_data TEXT)''')
    conn.commit()
    conn.close()

# Expanded RSS Feed sources - major logistics sources
FEED_SOURCES = [
    # General Supply Chain News
    {'url': 'https://www.supplychaindive.com/feeds/news/', 'name': 'Supply Chain Dive', 'category': 'general'},
    {'url': 'https://www.inboundlogistics.com/articles/feed/', 'name': 'Inbound Logistics', 'category': 'general'},
    {'url': 'https://www.logisticsmgmt.com/rss/topic/containers-intermodal', 'name': 'Logistics Management', 'category': 'general'},
    
    # Freight & Shipping
    {'url': 'https://www.freightwaves.com/news/feed', 'name': 'FreightWaves', 'category': 'shipping'},
    {'url': 'https://www.joc.com/rss/all-news', 'name': 'JOC.com', 'category': 'port'},
    {'url': 'https://www.americanshipper.com/rss', 'name': 'American Shipper', 'category': 'shipping'},
    {'url': 'https://www.seatrade-maritime.com/rss.xml', 'name': 'Seatrade Maritime', 'category': 'shipping'},
    {'url': 'https://gcaptain.com/feed/', 'name': 'gCaptain Maritime', 'category': 'maritime'},
    
    # Trucking & Transportation
    {'url': 'https://www.ttnews.com/rss/articles/latest', 'name': 'Transport Topics', 'category': 'trucking'},
    {'url': 'https://www.truckinginfo.com/rss/feed/10/', 'name': 'Trucking Info', 'category': 'trucking'},
    {'url': 'https://www.overdriveonline.com/feed/', 'name': 'Overdrive', 'category': 'trucking'},
    
    # Rail
    {'url': 'https://www.railwayage.com/feed/', 'name': 'Railway Age', 'category': 'rail'},
    {'url': 'https://www.progressiverailroading.com/rss/', 'name': 'Progressive Railroading', 'category': 'rail'},
    
    # Air Cargo
    {'url': 'https://www.aircargonews.net/feed/', 'name': 'Air Cargo News', 'category': 'air'},
    {'url': 'https://www.aircargoweek.com/feed/', 'name': 'Air Cargo Week', 'category': 'air'},
    
    # Ports
    {'url': 'https://www.portechnology.org/feed/', 'name': 'Port Technology', 'category': 'port'},
    
    # Warehousing & 3PL
    {'url': 'https://www.dcvelocity.com/rss/', 'name': 'DC Velocity', 'category': 'warehousing'},
    {'url': 'https://www.mhlnews.com/rss-feeds', 'name': 'Material Handling & Logistics', 'category': 'warehousing'},
    
    # Trade & Customs
    {'url': 'https://www.joc.com/rss/maritime-news/trade-lanes', 'name': 'JOC Trade Lanes', 'category': 'trade'},
]

CATEGORY_KEYWORDS = {
    'port': ['port', 'harbor', 'terminal', 'dock', 'vessel', 'berth', 'anchorage', 'quay'],
    'shipping': ['shipping', 'freight', 'cargo', 'container', 'vessel', 'ocean freight', 'maritime'],
    'trucking': ['truck', 'trucking', 'driver', 'highway', 'road freight', 'motor carrier', 'cdl'],
    'rail': ['rail', 'train', 'railroad', 'freight train', 'intermodal', 'railway'],
    'air': ['air cargo', 'airline', 'aviation', 'airport', 'air freight', 'aircraft'],
    'warehousing': ['warehouse', 'distribution center', 'fulfillment', '3pl', 'storage'],
    'shortage': ['shortage', 'scarce', 'supply shortage', 'out of stock', 'unavailable', 'scarcity'],
    'delay': ['delay', 'delayed', 'postponed', 'late', 'behind schedule', 'backlog'],
    'disruption': ['disruption', 'disrupted', 'interrupted', 'suspended', 'halt', 'stoppage'],
    'customs': ['customs', 'tariff', 'duty', 'border', 'cbp', 'import', 'export'],
    'weather': ['storm', 'hurricane', 'typhoon', 'flood', 'snow', 'ice', 'weather'],
    'labor': ['strike', 'union', 'workers', 'labor dispute', 'walkout', 'protest']
}

# Granular North America regions
REGION_KEYWORDS = {
    # United States - 12 regions
    'us_northeast': ['new york', 'new jersey', 'pennsylvania', 'connecticut', 'massachusetts', 'rhode island', 'vermont', 'new hampshire', 'maine', 'boston', 'philadelphia', 'newark', 'jfk'],
    'us_southeast': ['florida', 'georgia', 'south carolina', 'north carolina', 'virginia', 'west virginia', 'miami', 'atlanta', 'charleston', 'norfolk', 'savannah', 'jacksonville'],
    'us_midwest': ['illinois', 'indiana', 'michigan', 'ohio', 'wisconsin', 'minnesota', 'iowa', 'chicago', 'detroit', 'cleveland', 'cincinnati', 'milwaukee'],
    'us_south_central': ['texas', 'oklahoma', 'arkansas', 'louisiana', 'houston', 'dallas', 'new orleans', 'san antonio', 'austin'],
    'us_great_plains': ['kansas', 'nebraska', 'south dakota', 'north dakota', 'kansas city', 'omaha'],
    'us_mountain': ['colorado', 'utah', 'wyoming', 'montana', 'idaho', 'denver', 'salt lake city'],
    'us_southwest': ['arizona', 'new mexico', 'nevada', 'phoenix', 'tucson', 'las vegas', 'albuquerque'],
    'us_west_coast': ['california', 'los angeles', 'long beach', 'oakland', 'san francisco', 'san diego', 'la', 'sf bay'],
    'us_pacific_northwest': ['washington', 'oregon', 'seattle', 'portland', 'tacoma', 'spokane'],
    'us_alaska': ['alaska', 'anchorage', 'fairbanks'],
    'us_hawaii': ['hawaii', 'honolulu', 'oahu', 'maui'],
    'us_territories': ['puerto rico', 'guam', 'virgin islands', 'san juan'],
    
    # Canada
    'canada_east': ['quebec', 'ontario', 'maritime', 'montreal', 'toronto', 'ottawa', 'halifax', 'new brunswick', 'nova scotia'],
    'canada_west': ['british columbia', 'alberta', 'saskatchewan', 'manitoba', 'vancouver', 'calgary', 'edmonton', 'winnipeg'],
    
    # Mexico
    'mexico_north': ['tijuana', 'mexicali', 'ciudad juarez', 'chihuahua', 'monterrey', 'nuevo laredo'],
    'mexico_central': ['mexico city', 'guadalajara', 'puebla', 'queretaro', 'cdmx'],
    'mexico_south': ['veracruz', 'merida', 'cancun', 'acapulco', 'oaxaca'],
    
    # Other regions
    'europe_north': ['uk', 'ireland', 'scandinavia', 'norway', 'sweden', 'denmark', 'finland', 'london', 'dublin'],
    'europe_west': ['france', 'belgium', 'netherlands', 'luxembourg', 'paris', 'rotterdam', 'antwerp', 'amsterdam'],
    'europe_central': ['germany', 'poland', 'czech', 'austria', 'switzerland', 'berlin', 'hamburg', 'vienna'],
    'europe_south': ['spain', 'italy', 'portugal', 'greece', 'barcelona', 'madrid', 'rome', 'athens'],
    'asia_east': ['china', 'japan', 'south korea', 'taiwan', 'shanghai', 'beijing', 'tokyo', 'seoul', 'hong kong'],
    'asia_southeast': ['singapore', 'malaysia', 'thailand', 'vietnam', 'indonesia', 'philippines', 'bangkok'],
    'asia_south': ['india', 'pakistan', 'bangladesh', 'mumbai', 'delhi', 'chennai'],
    'middle_east': ['dubai', 'saudi', 'uae', 'qatar', 'kuwait', 'jeddah', 'riyadh'],
    'latin_america': ['brazil', 'argentina', 'chile', 'colombia', 'peru', 'buenos aires', 'sao paulo', 'santos'],
    'africa': ['south africa', 'kenya', 'nigeria', 'egypt', 'durban', 'cape town', 'lagos', 'suez'],
    'oceania': ['australia', 'new zealand', 'sydney', 'melbourne', 'auckland']
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
    high_keywords = ['crisis', 'severe', 'critical', 'emergency', 'major disruption', 'suspended', 'closed', 'shutdown']
    medium_keywords = ['delay', 'congestion', 'shortage', 'limited', 'reduced', 'slowdown']
    if any(k in text for k in high_keywords): return 'high'
    if any(k in text for k in medium_keywords): return 'medium'
    return 'low'

def fetch_feeds():
    conn = sqlite3.connect('alerts.db')
    c = conn.cursor()
    new_alerts = 0
    for source in FEED_SOURCES:
        try:
            print(f"Fetching {source['name']}...")
            feed = feedparser.parse(source['url'])
            for entry in feed.entries[:20]:
                title = entry.get('title', 'No title')
                description = re.sub('<[^<]+?>', '', entry.get('summary', entry.get('description', '')))[:500]
                link = entry.get('link', '')
                published = entry.get('published', entry.get('updated', datetime.now().isoformat()))
                alert_id = hashlib.md5(f"{title}{link}".encode()).hexdigest()
                c.execute('SELECT id FROM alerts WHERE id = ?', (alert_id,))
                if c.fetchone(): continue
                full_text = f"{title} {description}"
                categories = categorize_text(full_text, CATEGORY_KEYWORDS)
                regions = categorize_text(full_text, REGION_KEYWORDS)
                severity = calculate_severity(title, description)
                c.execute('''INSERT INTO alerts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                         (alert_id, title, description, link, published, source['name'],
                          ','.join(categories), ','.join(regions), severity, json.dumps(entry)))
                new_alerts += 1
        except Exception as e:
            print(f"Error fetching {source['name']}: {str(e)}")
    conn.commit()
    conn.close()
    print(f"Fetched {new_alerts} new alerts")
    return new_alerts

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    conn = sqlite3.connect('alerts.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    category = request.args.get('category', '')
    region = request.args.get('region', '')
    severity = request.args.get('severity', '')
    search = request.args.get('search', '')
    date_range = request.args.get('date_range', '')  # New: last_24h, last_week, last_month, custom
    start_date = request.args.get('start_date', '')  # New: for custom range
    end_date = request.args.get('end_date', '')      # New: for custom range
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))
    
    query = 'SELECT * FROM alerts WHERE 1=1'
    params = []
    
    if category:
        query += ' AND category LIKE ?'
        params.append(f'%{category}%')
    if region:
        query += ' AND region LIKE ?'
        params.append(f'%{region}%')
    if severity:
        query += ' AND severity = ?'
        params.append(severity)
    if search:
        query += ' AND (title LIKE ? OR description LIKE ?)'
        params.extend([f'%{search}%', f'%{search}%'])
    
    # Date filtering
    if date_range == 'last_24h':
        query += ' AND published > datetime("now", "-1 day")'
    elif date_range == 'last_week':
        query += ' AND published > datetime("now", "-7 days")'
    elif date_range == 'last_month':
        query += ' AND published > datetime("now", "-30 days")'
    elif date_range == 'custom' and start_date and end_date:
        query += ' AND published BETWEEN ? AND ?'
        params.extend([start_date, end_date])
    
    query += ' ORDER BY published DESC LIMIT ? OFFSET ?'
    params.extend([limit, offset])
    
    c.execute(query, params)
    alerts = []
    for r in c.fetchall():
        alerts.append({
            'id': r['id'],
            'title': r['title'],
            'description': r['description'],
            'link': r['link'],
            'published': r['published'],
            'source': r['source'],
            'category': r['category'].split(','),
            'region': r['region'].split(','),
            'severity': r['severity']
        })
    
    # Build count query
    count_query = 'SELECT COUNT(*) as count FROM alerts WHERE 1=1'
    count_params = []
    
    if category:
        count_query += ' AND category LIKE ?'
        count_params.append(f'%{category}%')
    if region:
        count_query += ' AND region LIKE ?'
        count_params.append(f'%{region}%')
    if severity:
        count_query += ' AND severity = ?'
        count_params.append(severity)
    if search:
        count_query += ' AND (title LIKE ? OR description LIKE ?)'
        count_params.extend([f'%{search}%', f'%{search}%'])
    
    if date_range == 'last_24h':
        count_query += ' AND published > datetime("now", "-1 day")'
    elif date_range == 'last_week':
        count_query += ' AND published > datetime("now", "-7 days")'
    elif date_range == 'last_month':
        count_query += ' AND published > datetime("now", "-30 days")'
    elif date_range == 'custom' and start_date and end_date:
        count_query += ' AND published BETWEEN ? AND ?'
        count_params.extend([start_date, end_date])
    
    c.execute(count_query, count_params)
    total = c.fetchone()['count']
    conn.close()
    
    return jsonify({'alerts': alerts, 'total': total, 'limit': limit, 'offset': offset})

@app.route('/api/stats', methods=['GET'])
def get_stats():
    conn = sqlite3.connect('alerts.db')
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM alerts')
    total = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM alerts WHERE published > datetime("now", "-7 days")')
    last_7 = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM alerts WHERE published > datetime("now", "-1 day")')
    last_24 = c.fetchone()[0]
    c.execute('SELECT severity, COUNT(*) as count FROM alerts GROUP BY severity')
    severity_counts = {row[0]: row[1] for row in c.fetchall()}
    conn.close()
    return jsonify({
        'total_alerts': total,
        'last_7_days': last_7,
        'last_24_hours': last_24,
        'by_severity': severity_counts
    })

@app.route('/api/refresh', methods=['POST'])
def refresh_feeds():
    return jsonify({'message': f'Fetched {fetch_feeds()} new alerts'})

@app.route('/api/categories', methods=['GET'])
def get_categories():
    return jsonify({
        'categories': list(CATEGORY_KEYWORDS.keys()),
        'regions': list(REGION_KEYWORDS.keys()),
        'severities': ['low', 'medium', 'high'],
        'date_ranges': ['all_time', 'last_24h', 'last_week', 'last_month', 'custom']
    })

@app.route('/')
def index():
    """Serve the frontend HTML file"""
    from flask import send_file
    import os
    return send_file('index.html')

init_db()
scheduler = BackgroundScheduler()
scheduler.add_job(func=fetch_feeds, trigger="interval", hours=4)
scheduler.start()

if __name__ == '__main__':
    import os
    print("Fetching initial feed data...")
    fetch_feeds()
    print("Starting server...")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
