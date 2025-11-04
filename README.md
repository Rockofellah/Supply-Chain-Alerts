# Supply Chain Alert Aggregator

## 🚀 Quick Start (3 Steps)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run backend
python app.py

# 3. Open frontend (new terminal)
python -m http.server 8000
# Visit: http://localhost:8000
```

## ✨ What You Built

A **complete, working MVP** with:
- Real-time RSS aggregation from 5 major sources
- Auto-categorization by type (port, shipping, trucking, etc.)
- Regional tagging (North America, Europe, Asia-Pacific, etc.)
- Severity scoring (low/medium/high)
- Advanced filtering and full-text search  
- REST API ready for expansion
- Modern, responsive UI
- Background updates every 4 hours

## 📦 Files

- **app.py** - Flask backend (150 lines)
- **index.html** - Complete frontend (HTML/CSS/JS)
- **requirements.txt** - Python dependencies
- **.gitignore** - Git configuration

## 🎯 Next Steps

### This Week:
1. Add 3-5 more RSS sources
2. Customize UI colors
3. Deploy to Railway.app or Render.com
4. Share with 5 potential users

### Next 2 Weeks:
1. Implement user authentication
2. Add email notifications
3. Integrate Stripe for payments
4. Create landing page
5. Start marketing

## 🔌 API Endpoints

```
GET  /api/alerts        - Get filtered alerts
GET  /api/stats         - Dashboard statistics
GET  /api/categories    - Available filters
POST /api/refresh       - Manual feed refresh
```

## 📡 Current Data Sources

1. Supply Chain Dive
2. FreightWaves  
3. JOC.com
4. DHL Logistics
5. Inbound Logistics

## 💰 Monetization

**Free Tier:**
- Last 7 days of alerts
- Basic filtering
- 4-hour updates

**Premium ($9.99/month):**
- 90-day history
- Custom filters
- Hourly updates
- Email notifications
- CSV export

## 🐛 Troubleshooting

**Module not found:**
```bash
pip install -r requirements.txt --upgrade
```

**Port 5000 in use:**
```bash
lsof -ti:5000 | xargs kill -9
```

**No alerts loading:**
- Wait 30 seconds after startup
- Check terminal for errors
- Click the Refresh button

## 📚 Tech Stack

- **Backend:** Python, Flask, SQLite
- **Frontend:** Vanilla JS, CSS3
- **Data:** RSS feeds via Feedparser
- **Scheduler:** APScheduler

## 🎓 Learn More

Full development guide and iteration roadmap coming soon!

For now:
1. Run the app
2. Test all features  
3. Read through app.py
4. Start adding your own sources

## 🚀 Deploy

**Railway.app (easiest):**
```bash
npm i -g @railway/cli
railway login
railway init
railway up
```

**Render.com:**
- Connect GitHub repo
- Build: `pip install -r requirements.txt`
- Start: `python app.py`

---

**Built for supply chain professionals who need reliable disruption alerts in one place.**

**Ready to ship? Let's go! 🚀**
