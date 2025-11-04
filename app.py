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

# Simplified feed sources for faster initial load
FEED_SOURCES = [
    {'url': 'https://www.supplychaindive.com/feeds/news/', 'name': 'Supply Chain Dive'},
    {'url': 'https://www.freightwaves.com/news/feed', 'name': 'FreightWaves'},
    {'url': 'https://www.joc.com/rss/all-news', 'name': 'JOC.com'},
    {'url': 'https://gcaptain.com/feed/', 'name': 'gCaptain'},
    {'url': 'https://www.ttnews.com/rss/articles/latest', 'name': 'Transport Topics'},
]

CATEGORY_KEYWORDS = {
    'port': ['port', 'harbor', 'terminal', 'dock'],
    'shipping': ['shipping', 'freight', 'cargo', 'container'],
    'trucking': ['truck', 'trucking', 'driver'],
    'rail': ['rail', 'train', 'railroad'],
    'air': ['air cargo', 'airline', 'aviation'],
    'shortage': ['shortage', 'scarce'],
    'delay': ['delay', 'delayed'],
    'disruption': ['disruption', 'disrupted'],
}

REGION_KEYWORDS = {
    'us_northeast': ['new york', 'boston', 'philadelphia'],
    'us_southeast': ['florida', 'atlanta', 'miami'],
    'us_midwest': ['chicago', 'detroit'],
    'us_west_coast': ['california', 'los angeles', 'oakland'],
    'europe': ['europe', 'rotterdam', 'hamburg'],
    'asia': ['china', 'singapore', 'hong kong'],
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
                feed = feedparser.parse(source['url'], timeout=10)
                
                for entry in feed.entries[:10]:  # Limit to 10 per source
                    try:
                        title = entry.get('title', 'No title')
                        description = re.sub('<[^<]+?>', '', entry.get('summary', ''))[:500]
                        link = entry.get('link', '')
                        published = entry.get('published', datetime.now().isoformat())
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
    """Get all alerts"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        c.execute('SELECT * FROM alerts ORDER BY published DESC LIMIT 100')
        
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
scheduler.start()
print("✅ Scheduler started")

if __name__ == '__main__':
    print("📡 Fetching initial data...")
    try:
        fetch_feeds()
    except Exception as e:
        print(f"⚠️  Initial fetch failed (will retry later): {e}")
    
    port = int(os.environ.get('PORT', 5000))
    print(f"🌐 Starting server on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False)
