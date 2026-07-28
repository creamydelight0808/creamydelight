# Creamy Delight - Milk Tracker

A web-based milk delivery tracking application for managing daily milk deliveries, customer billing, and payment tracking.

## Features

- **Dashboard** - Overview of daily/monthly sales, revenue, and pending payments
- **Customer Management** - Add, edit, deactivate customers with individual rate settings
- **Daily Entry** - Quick daily milk quantity entry for all customers
- **Billing Reports** - Monthly billing reports with payment tracking
- **Payment Recording** - Track received and pending payments per customer

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

Open http://localhost:5000 in your browser.

## First Time Setup

1. Click "Load Excel Data" on the dashboard to seed July 2026 data
2. Start adding daily entries for new days

## Tech Stack

- **Backend:** Python Flask + SQLAlchemy + SQLite
- **Frontend:** Bootstrap 5 + Chart.js
- **Database:** SQLite (local file)
