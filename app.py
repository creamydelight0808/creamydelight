import os
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
CORS(app)

# Secret key for session management
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Database configuration - use PostgreSQL from env var, fallback to SQLite for local dev
database_url = os.environ.get('DATABASE_URL', '')
if database_url.startswith('postgres://'):
    # Render uses postgres:// but SQLAlchemy needs postgresql://
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

if database_url:
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, 'milk_tracker.db')}"

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


# ============================================================
# MODELS
# ============================================================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    address = db.Column(db.String(500), default='')
    phone = db.Column(db.String(20), default='')
    rate_per_litre = db.Column(db.Float, default=55.0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    deliveries = db.relationship('Delivery', backref='customer', lazy=True)
    payments = db.relationship('Payment', backref='customer', lazy=True)


class Delivery(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    quantity_litres = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('customer_id', 'date', name='uq_customer_date'),)


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    month = db.Column(db.Integer, nullable=False)  # 1-12
    year = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.String(500), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ============================================================
# AUTH ROUTES
# ============================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            return render_template('login.html', error='Invalid username or password')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ============================================================
# ROUTES - PAGES
# ============================================================

@app.route('/')
@login_required
def dashboard():
    return render_template('dashboard.html')


@app.route('/customers')
@login_required
def customers_page():
    return render_template('customers.html')


@app.route('/daily')
@login_required
def daily_page():
    return render_template('daily.html')


@app.route('/reports')
@login_required
def reports_page():
    return render_template('reports.html')


@app.route('/pay/<int:customer_id>')
@login_required
def payment_page(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    amount = request.args.get('amount', '0')
    month = request.args.get('month', str(datetime.now().month))
    year = request.args.get('year', str(datetime.now().year))
    month_names = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    month_name = month_names[int(month) - 1]
    return render_template('pay.html',
        customer_name=customer.name,
        amount=amount,
        month_name=month_name,
        year=year
    )


# ============================================================
# API - CUSTOMERS
# ============================================================

@app.route('/api/customers', methods=['GET'])
@login_required
def get_customers():
    active_only = request.args.get('active', 'true') == 'true'
    query = Customer.query
    if active_only:
        query = query.filter_by(is_active=True)
    customers = query.order_by(Customer.name).all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'address': c.address,
        'phone': c.phone,
        'rate_per_litre': c.rate_per_litre,
        'is_active': c.is_active
    } for c in customers])


@app.route('/api/customers', methods=['POST'])
@login_required
def add_customer():
    data = request.json
    if not data.get('name'):
        return jsonify({'error': 'Name is required'}), 400
    existing = Customer.query.filter_by(name=data['name']).first()
    if existing:
        return jsonify({'error': 'Customer already exists'}), 400
    customer = Customer(
        name=data['name'],
        address=data.get('address', ''),
        phone=data.get('phone', ''),
        rate_per_litre=float(data.get('rate_per_litre', 55.0))
    )
    db.session.add(customer)
    db.session.commit()
    return jsonify({'id': customer.id, 'name': customer.name}), 201


@app.route('/api/customers/<int:customer_id>', methods=['PUT'])
@login_required
def update_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    data = request.json
    if 'name' in data:
        customer.name = data['name']
    if 'address' in data:
        customer.address = data['address']
    if 'phone' in data:
        customer.phone = data['phone']
    if 'rate_per_litre' in data:
        customer.rate_per_litre = float(data['rate_per_litre'])
    if 'is_active' in data:
        customer.is_active = data['is_active']
    db.session.commit()
    return jsonify({'message': 'Updated'})


@app.route('/api/customers/<int:customer_id>', methods=['DELETE'])
@login_required
def delete_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    customer.is_active = False
    db.session.commit()
    return jsonify({'message': 'Deactivated'})


# ============================================================
# API - DELIVERIES
# ============================================================

@app.route('/api/deliveries', methods=['GET'])
@login_required
def get_deliveries():
    date_str = request.args.get('date')
    month = request.args.get('month')
    year = request.args.get('year')
    customer_id = request.args.get('customer_id')

    query = Delivery.query

    if date_str:
        d = datetime.strptime(date_str, '%Y-%m-%d').date()
        query = query.filter_by(date=d)
    elif month and year:
        start = date(int(year), int(month), 1)
        if int(month) == 12:
            end = date(int(year) + 1, 1, 1)
        else:
            end = date(int(year), int(month) + 1, 1)
        query = query.filter(Delivery.date >= start, Delivery.date < end)

    if customer_id:
        query = query.filter_by(customer_id=int(customer_id))

    deliveries = query.all()
    return jsonify([{
        'id': d.id,
        'customer_id': d.customer_id,
        'customer_name': d.customer.name,
        'date': d.date.isoformat(),
        'quantity_litres': d.quantity_litres
    } for d in deliveries])


@app.route('/api/deliveries', methods=['POST'])
@login_required
def add_delivery():
    data = request.json
    customer_id = data.get('customer_id')
    date_str = data.get('date')
    quantity = float(data.get('quantity_litres', 0))

    if not customer_id or not date_str:
        return jsonify({'error': 'customer_id and date required'}), 400

    d = datetime.strptime(date_str, '%Y-%m-%d').date()

    existing = Delivery.query.filter_by(customer_id=customer_id, date=d).first()
    if existing:
        existing.quantity_litres = quantity
    else:
        existing = Delivery(customer_id=customer_id, date=d, quantity_litres=quantity)
        db.session.add(existing)

    db.session.commit()
    return jsonify({'message': 'Saved'}), 201


@app.route('/api/deliveries/bulk', methods=['POST'])
@login_required
def bulk_delivery():
    """Save multiple deliveries at once (for daily entry form)"""
    data = request.json
    date_str = data.get('date')
    entries = data.get('entries', [])

    if not date_str:
        return jsonify({'error': 'date required'}), 400

    d = datetime.strptime(date_str, '%Y-%m-%d').date()

    for entry in entries:
        customer_id = entry.get('customer_id')
        quantity = float(entry.get('quantity_litres', 0))

        existing = Delivery.query.filter_by(customer_id=customer_id, date=d).first()
        if quantity > 0:
            if existing:
                existing.quantity_litres = quantity
            else:
                delivery = Delivery(customer_id=customer_id, date=d, quantity_litres=quantity)
                db.session.add(delivery)
        else:
            # Remove the record if quantity is 0 (don't store zero deliveries)
            if existing:
                db.session.delete(existing)

    db.session.commit()
    return jsonify({'message': f'Saved {len(entries)} entries'}), 201


# ============================================================
# API - PAYMENTS
# ============================================================

@app.route('/api/payments', methods=['GET'])
@login_required
def get_payments():
    customer_id = request.args.get('customer_id')
    month = request.args.get('month')
    year = request.args.get('year')

    query = Payment.query
    if customer_id:
        query = query.filter_by(customer_id=int(customer_id))
    if month:
        query = query.filter_by(month=int(month))
    if year:
        query = query.filter_by(year=int(year))

    payments = query.all()
    return jsonify([{
        'id': p.id,
        'customer_id': p.customer_id,
        'customer_name': p.customer.name,
        'amount': p.amount,
        'payment_date': p.payment_date.isoformat(),
        'month': p.month,
        'year': p.year,
        'notes': p.notes
    } for p in payments])


@app.route('/api/payments', methods=['POST'])
@login_required
def add_payment():
    data = request.json
    payment = Payment(
        customer_id=data['customer_id'],
        amount=float(data['amount']),
        payment_date=datetime.strptime(data['payment_date'], '%Y-%m-%d').date(),
        month=int(data['month']),
        year=int(data['year']),
        notes=data.get('notes', '')
    )
    db.session.add(payment)
    db.session.commit()
    return jsonify({'message': 'Payment recorded'}), 201


# ============================================================
# API - REPORTS
# ============================================================

@app.route('/api/reports/monthly', methods=['GET'])
@login_required
def monthly_report():
    month = int(request.args.get('month', datetime.now().month))
    year = int(request.args.get('year', datetime.now().year))

    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)

    customers = Customer.query.order_by(Customer.name).all()
    report = []

    total_litres_all = 0
    total_amount_all = 0
    total_received_all = 0

    for c in customers:
        deliveries = Delivery.query.filter(
            Delivery.customer_id == c.id,
            Delivery.date >= start,
            Delivery.date < end
        ).all()

        total_litres = round(sum(d.quantity_litres for d in deliveries), 2)
        total_amount = round(total_litres * c.rate_per_litre)  # Round to nearest integer (₹)

        payments = Payment.query.filter_by(
            customer_id=c.id, month=month, year=year
        ).all()
        total_received = round(sum(p.amount for p in payments))

        pending = total_amount - total_received

        if total_litres > 0 or total_received > 0:
            report.append({
                'customer_id': c.id,
                'customer_name': c.name,
                'rate_per_litre': c.rate_per_litre,
                'total_litres': total_litres,
                'total_amount': total_amount,
                'received_payment': total_received,
                'pending_payment': pending
            })

            total_litres_all += total_litres
            total_amount_all += total_amount
            total_received_all += total_received

    return jsonify({
        'month': month,
        'year': year,
        'customers': report,
        'summary': {
            'total_litres': round(total_litres_all, 2),
            'total_amount': round(total_amount_all),
            'total_received': round(total_received_all),
            'total_pending': round(total_amount_all - total_received_all)
        }
    })


@app.route('/api/reports/daily-summary', methods=['GET'])
@login_required
def daily_summary():
    date_str = request.args.get('date', date.today().isoformat())
    d = datetime.strptime(date_str, '%Y-%m-%d').date()

    deliveries = Delivery.query.filter_by(date=d).all()
    total_litres = sum(dv.quantity_litres for dv in deliveries)
    total_customers = len([dv for dv in deliveries if dv.quantity_litres > 0])

    return jsonify({
        'date': d.isoformat(),
        'total_litres': total_litres,
        'total_customers_served': total_customers,
        'deliveries': [{
            'customer_name': dv.customer.name,
            'quantity_litres': dv.quantity_litres
        } for dv in deliveries if dv.quantity_litres > 0]
    })


@app.route('/api/reports/customer-history', methods=['GET'])
@login_required
def customer_history():
    customer_id = request.args.get('customer_id')
    if not customer_id:
        return jsonify({'error': 'customer_id required'}), 400

    customer = Customer.query.get_or_404(int(customer_id))
    deliveries = Delivery.query.filter_by(customer_id=customer.id).order_by(Delivery.date).all()
    payments = Payment.query.filter_by(customer_id=customer.id).order_by(Payment.payment_date).all()

    return jsonify({
        'customer': {
            'id': customer.id,
            'name': customer.name,
            'rate_per_litre': customer.rate_per_litre
        },
        'deliveries': [{
            'date': d.date.isoformat(),
            'quantity_litres': d.quantity_litres
        } for d in deliveries],
        'payments': [{
            'date': p.payment_date.isoformat(),
            'amount': p.amount,
            'month': p.month,
            'year': p.year
        } for p in payments]
    })


# ============================================================
# SEED DATA FROM EXCEL
# ============================================================

@app.route('/api/seed', methods=['POST'])
@login_required
def seed_data():
    """Seed the database with initial data from the Excel sheet"""
    # Default rate
    RATE = 55.0

    # July 2026 customers and data
    july_data = {
        'Abhi': [1,1,1,1,1,1,1,1,1,1,2,1,2,1,1,1.5,0,0,0],
        'Ajay Kamat': [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0],
        'Ajmera 123/A': [0.5,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0],
        'Akshay': [0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0,0,0],
        'Ananth': [0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0,0,0],
        'Ashok Setu': [0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0],
        'Atma atte': [1.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,1,1,0.5,0.5,0,0,0],
        'Harish': [0.5,0.5,0.5,1,1,1,1,1,1,1,1,1,0,0,0,1,0,0,0],
        'Kuntappa house Ramaiah Layout': [1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,0,0,0],
        'Madhu 43 GF': [0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0],
        'Mangala FLAT 201': [1.5,1.5,1.5,1.5,1.5,1.5,1.5,1.5,1.5,1.5,1.5,1.5,1,1,1,1,1,1,1.5],
        'Mohan': [1,3,0,2,0,1,1.5,1,2,13,1,2,1.5,2.5,2,4,0,0,0],
        'Nagaraju Ramaiah Layout': [0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0],
        'Pradeep FLAT 301': [0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0,0,0],
        'Prema FLAT 205': [0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0,0,0],
        'Ramesh 4th cross': [1,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,0,0],
        'Rohit 98': [0,0,0,0,0,0.5,0.5,0,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0,0,0],
        'Roopa Amity Shelters F07': [0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0,0],
        'Saravana Mani Mestri': [0,0,0,0,0,0,0,1,1,1,1,1,1,1,1,1,0,0,0],
        'Satish Ramaiah Layout': [0.5,1,1,1,1,1,1,1,1,1,0,1,0,0,0,0,0,0,0],
        'Smitha': [0.5,0.5,0.5,0.5,0.5,0.5,0,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0,0,0],
        'Sooraj': [0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0.5,0,0,0],
        'Sujay Ramaiah Layout': [0.5,0,0.5,0,0.5,0,0.5,0,0.5,0,0.5,0,0,0,0.5,0,0,0,0],
        'Tanuja Annapoorneshwari Layout no 10': [0,0,0,0,0,1,0,0.5,0.5,0.5,0.5,0.5,0,0,0,0,0,0,0],
        '61 1st floor': [0,0,0,0,0,0,0,0,0.5,0,0,0,0,0,0,0,0,0,0],
        'Kuntappa house ground floor': [0,0,0,0,0,0,0,0,0,0.5,0,0,0,0,0,0,0,0,0],
        'JayaPrakash 401': [0,0,0,0,0,0,0,0,0,0,0,0.5,0.5,0.5,0.5,0.5,0,0,0],
        'Praveen Rana 45 Ramaiah layout': [0,0,0,0,0,0,0,0,0,0,0,0,2,2,2,2,0,0,0],
        'Channabasavaraju 91 Royal': [0,0,0,0,0,0,0,0,0,0,0,0,1,1,1,1,0,0,0],
        'G 22 Amity Shelter': [0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1,0,0,0],
        'Asha Home Maid': [0,0,0,0,0,0,0,0,0,0,0,0,0.5,0.5,0.5,0.5,0,0,0],
        'Krishna Hotel': [0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,2,0,0,0],
        'Sooraj Mani Mestri': [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.5,0.5,0,0,0],
        'Madan 47----2BR': [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.5,0,0,0],
        'Raghavendra royal Nisarga 18/2': [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.5,0,0,0],
        'Santosh royal nisarga 104': [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.5,0,0,0],
    }

    # July dates: 13th to 31st
    july_dates = [date(2026, 7, d) for d in range(13, 32)]

    # Create customers and deliveries
    for name, quantities in july_data.items():
        customer = Customer.query.filter_by(name=name).first()
        if not customer:
            customer = Customer(name=name, rate_per_litre=RATE)
            db.session.add(customer)
            db.session.flush()

        for i, qty in enumerate(quantities):
            if i < len(july_dates) and qty > 0:
                existing = Delivery.query.filter_by(
                    customer_id=customer.id, date=july_dates[i]
                ).first()
                if not existing:
                    delivery = Delivery(
                        customer_id=customer.id,
                        date=july_dates[i],
                        quantity_litres=qty
                    )
                    db.session.add(delivery)

    # Add payments for customers who paid
    paid_customers = {
        '61 1st floor': 27.5,
        'Kuntappa house ground floor': 27.5,
        'Santosh royal nisarga 104': 55.0,
    }
    for name, amount in paid_customers.items():
        customer = Customer.query.filter_by(name=name).first()
        if customer:
            existing_payment = Payment.query.filter_by(
                customer_id=customer.id, month=7, year=2026
            ).first()
            if not existing_payment:
                payment = Payment(
                    customer_id=customer.id,
                    amount=amount,
                    payment_date=date(2026, 7, 27),
                    month=7,
                    year=2026
                )
                db.session.add(payment)

    db.session.commit()
    return jsonify({'message': 'Database seeded with July 2026 data'}), 201


# ============================================================
# MAIN
# ============================================================

with app.app_context():
    db.create_all()

    # Create default admin user if none exists
    if not User.query.first():
        admin = User(username='mohandairyandpoultryfarm')
        admin.set_password('creamy2026')
        db.session.add(admin)
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
