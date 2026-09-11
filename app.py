#!/usr/bin/env python3
"""
SewLagos - Sewing Business Vending Application
Lagos, Nigeria focused startup for custom & ready designs.
Handles: Registration, Phone OTP, Catalog, Orders, Wallet, Calendar, Receipts, Dashboard.
"""

from flask import (
    Flask, render_template, request, redirect, url_for, session,
    flash, jsonify, g, abort
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, date
import sqlite3
import os
import random
import string
import json
import hmac
import hashlib
import requests as http_requests
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]
DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sewlagos.db")

# ---------- Flutterwave Configuration ----------
# Get keys from https://app.flutterwave.com → Settings → API Keys
FLW_SECRET_KEY = os.environ.get("FLW_SECRET_KEY", "")
FLW_PUBLIC_KEY = os.environ.get("FLW_PUBLIC_KEY", "")
FLW_SECRET_HASH = os.environ.get("FLW_SECRET_HASH", "")  # Set this in Flutterwave dashboard
FLW_BASE_URL = "https://api.flutterwave.com/v3"

# Fixed delivery fee
DELIVERY_FEE = 1000.00

# Delivery slots
SLOTS = {
    "morning": "9:00 AM – 12:00 PM",
    "afternoon": "12:00 PM – 3:00 PM",
    "evening": "3:00 PM – 6:00 PM"
}

# ---------- Flutterwave Helpers ----------
def flw_headers():
    return {
        "Authorization": f"Bearer {FLW_SECRET_KEY}",
        "Content-Type": "application/json"
    }

def flw_initialize(email, amount_naira, reference, callback_url, customer_name=None, phone=None, meta=None):
    """Initialize a Flutterwave payment. Amount is in Naira."""
    payload = {
        "tx_ref": reference,
        "amount": str(int(round(float(amount_naira)))),
        "currency": "NGN",
        "redirect_url": callback_url,
        "payment_options": "card,banktransfer,ussd",
        "customer": {
            "email": email or "customer@sewlagos.ng",
            "name": customer_name or "SewLagos Customer",
            "phonenumber": phone or ""
        },
        "customizations": {
            "title": "SewLagos Wallet Funding",
            "description": "Fund your SewLagos wallet",
            "logo": ""
        },
        "meta": meta or {}
    }
    try:
        resp = http_requests.post(
            f"{FLW_BASE_URL}/payments",
            headers=flw_headers(),
            json=payload,
            timeout=20
        )
        data = resp.json()
        if data.get("status") == "success":
            return data["data"]  # contains link, etc.
        return {"error": data.get("message", "Failed to initialize payment")}
    except Exception as e:
        return {"error": str(e)}

def flw_verify(transaction_id):
    """Verify a Flutterwave transaction by ID."""
    try:
        resp = http_requests.get(
            f"{FLW_BASE_URL}/transactions/{transaction_id}/verify",
            headers=flw_headers(),
            timeout=15
        )
        data = resp.json()
        if data.get("status") == "success" and data.get("data", {}).get("status") == "successful":
            return data["data"]
        return None
    except Exception:
        return None

def flw_verify_by_tx_ref(tx_ref):
    """Verify using tx_ref (fallback)."""
    try:
        resp = http_requests.get(
            f"{FLW_BASE_URL}/transactions/verify_by_reference",
            headers=flw_headers(),
            params={"tx_ref": tx_ref},
            timeout=15
        )
        data = resp.json()
        if data.get("status") == "success" and data.get("data", {}).get("status") == "successful":
            return data["data"]
        return None
    except Exception:
        return None

def credit_wallet(user_id, amount, reference, description="Wallet funding via Flutterwave"):
    """Credit user wallet and record transaction. Returns new balance or None on error."""
    db = get_db()
    # Prevent double-crediting the same reference
    existing = db.execute(
        "SELECT id FROM wallet_transactions WHERE reference = ?", (reference,)
    ).fetchone()
    if existing:
        return None  # already processed

    user = db.execute("SELECT wallet_balance FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return None
    new_bal = float(user["wallet_balance"]) + float(amount)
    db.execute("UPDATE users SET wallet_balance = ? WHERE id = ?", (new_bal, user_id))
    db.execute(
        """INSERT INTO wallet_transactions (user_id, type, amount, balance_after, description, reference)
           VALUES (?,?,?,?,?,?)""",
        (user_id, "credit", amount, new_bal, description, reference)
    )
    db.execute(
        "INSERT INTO notifications (user_id, title, message, type) VALUES (?,?,?,?)",
        (user_id, "Wallet Credited", f"₦{amount:,.0f} has been added to your wallet via Flutterwave.", "wallet")
    )
    db.commit()
    return new_bal

# ---------- Database helpers ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    with open(os.path.join(os.path.dirname(__file__), "schema.sql"), "r") as f:
        db.executescript(f.read())
    seed_data(db)
    db.commit()
    print("Database initialized and seeded.")

def seed_data(db):
    # Categories
    cats = [
        ("Women", "women", "Beautiful Nigerian & contemporary wear for women", 1),
        ("Men", "men", "Traditional and modern native wears for men", 2),
        ("Kids", "kids", "Adorable traditional and casual wears for children", 3),
    ]
    for name, slug, desc, order in cats:
        db.execute(
            "INSERT OR IGNORE INTO categories (name, slug, description, sort_order) VALUES (?,?,?,?)",
            (name, slug, desc, order)
        )

    # Subcategories
    subcats = [
        # Women
        (1, "Gowns", "gowns", "Ankara gowns, Bubu, Maxi, Occasion gowns"),
        (1, "Traditional Wear", "traditional-women", "Iro & Buba, Gele sets, Aso-Oke ensembles"),
        (1, "Ankara Wear", "ankara-women", "Ready-to-wear Ankara tops, skirts, sets"),
        (1, "Dashiki & Kaftan", "dashiki-kaftan-women", "Women's dashiki and flowing kaftans"),
        (1, "Bubu / Boubou", "bubu", "Free-flowing Bubu gowns"),
        # Men
        (2, "Agbada", "agbada", "Full ceremonial and casual Agbada sets"),
        (2, "Senator / Native", "senator", "Senator wears and modern native sets"),
        (2, "Dashiki", "dashiki-men", "Classic and modern Dashiki shirts"),
        (2, "Kaftan", "kaftan-men", "Embroidered and plain kaftans"),
        (2, "Traditional Sets", "traditional-men", "Complete traditional ensembles"),
        # Kids
        (3, "Traditional Kids", "traditional-kids", "Mini Agbada, Iro & Buba for children"),
        (3, "Ankara Kids", "ankara-kids", "Colorful Ankara outfits for kids"),
        (3, "Party Wear", "party-kids", "Occasion and party wears for children"),
    ]
    for cat_id, name, slug, desc in subcats:
        db.execute(
            "INSERT OR IGNORE INTO subcategories (category_id, name, slug, description) VALUES (?,?,?,?)",
            (cat_id, name, slug, desc)
        )

    # Products – realistic Lagos prices (Naira), Nigerian designs
    products = [
        # Women Gowns
        (1, "Elegant Ankara Maxi Gown", "ankara-maxi-gown", 
         "Vibrant multi-color Ankara maxi gown with side slit. Perfect for owambe and Sunday service. Fully lined.",
         28500, 7, "/static/images/ankara-gown1.jpg", "Ankara", 0),
        (1, "Beaded Bubu Gown – Royal Blue", "beaded-bubu-blue",
         "Luxurious free-flowing Bubu with crystal bead neckline. Soft Ankara cotton. One size free.",
         42000, 10, "/static/images/bubu1.jpg", "Ankara", 0),
        (1, "Aso-Oke Occasion Gown", "aso-oke-gown",
         "Hand-woven Aso-Oke gown with modern silhouette. Ideal for traditional weddings.",
         95000, 14, "/static/images/aso-oke-gown.jpg", "Aso-Oke", 1),
        (5, "Classic Adire Bubu", "adire-bubu",
         "Authentic indigo Adire print Bubu. Comfortable for everyday and events.",
         35000, 8, "/static/images/adire-bubu.jpg", "Adire", 0),
        # Women Traditional
        (2, "Iro & Buba Set with Gele", "iro-buba-gele",
         "Complete Yoruba traditional set: Iro, Buba, Gele and Ipele. Choose your fabric.",
         55000, 10, "/static/images/iro-buba.jpg", "Ankara/Aso-Oke", 1),
        (2, "George Wrapper & Blouse", "george-set",
         "Premium George fabric wrapper with matching blouse and coral beads option.",
         120000, 12, "/static/images/george.jpg", "George", 1),
        # Women Ankara
        (3, "Ankara Two-Piece Set", "ankara-2piece",
         "Crop top + high-waist skirt in matching Ankara. Ready to wear sizes S–XXL.",
         22000, 5, "/static/images/ankara-set.jpg", "Ankara", 0),
        (3, "Office Ankara Pencil Dress", "ankara-office",
         "Corporate-friendly Ankara dress with modest neckline and belt.",
         19500, 6, "/static/images/ankara-office.jpg", "Ankara", 0),
        # Men Agbada
        (6, "Embroidered Agbada Full Set", "agbada-embroidered",
         "3-piece Agbada (outer, buba, sokoto) + fila. Heavy embroidery on chest. Damask or lace options.",
         85000, 14, "/static/images/agbada1.jpg", "Damask/Lace", 1),
        (6, "Casual Ankara Agbada", "ankara-agbada",
         "Lightweight Ankara Agbada for everyday elegance. Comfortable fit.",
         45000, 9, "/static/images/agbada-ankara.jpg", "Ankara", 0),
        # Men Senator
        (7, "Classic Senator Native Wear", "senator-classic",
         "2-piece Senator with matching cap. Available in wine, navy, black, cream.",
         32000, 7, "/static/images/senator1.jpg", "Cotton/Cashmere", 0),
        (7, "Senator with Ankara Panels", "senator-ankara",
         "Modern Senator with Ankara front panel and sleeve cuffs. Statement piece.",
         48000, 8, "/static/images/senator-ankara.jpg", "Cotton + Ankara", 0),
        # Men Dashiki
        (8, "Premium Dashiki Shirt", "dashiki-premium",
         "Richly embroidered Dashiki in vibrant colors. Loose fit, hip length.",
         18000, 5, "/static/images/dashiki1.jpg", "Cotton", 0),
        (8, "Long Dashiki with Trousers", "dashiki-set",
         "Full Dashiki set with matching sokoto. Perfect for cultural events.",
         28000, 6, "/static/images/dashiki-set.jpg", "Cotton", 0),
        # Men Kaftan
        (9, "Embroidered Kaftan", "kaftan-embroidered",
         "Northern-style embroidered kaftan. Soft damask. Ideal for Jumat and events.",
         38000, 8, "/static/images/kaftan1.jpg", "Damask", 0),
        # Kids
        (11, "Mini Agbada for Boys", "kids-agbada",
         "Adorable 3-piece mini Agbada with cap. Ages 2–12. Custom sizing.",
         25000, 7, "/static/images/kids-agbada.jpg", "Ankara/Damask", 1),
        (11, "Girls Iro & Buba Set", "kids-iro-buba",
         "Cute traditional set for little queens. Includes gele.",
         22000, 6, "/static/images/kids-iro.jpg", "Ankara", 1),
        (12, "Ankara Party Dress for Girls", "kids-ankara-dress",
         "Fluffy Ankara dress with petticoat. Perfect for birthdays and parties.",
         16500, 5, "/static/images/kids-dress.jpg", "Ankara", 0),
        (12, "Boys Ankara Short Set", "kids-ankara-short",
         "Short sleeve Ankara top + shorts. Comfortable everyday wear.",
         12000, 4, "/static/images/kids-short.jpg", "Ankara", 0),
    ]
    for sub_id, name, slug, desc, price, days, img, fabric, custom in products:
        db.execute(
            """INSERT OR IGNORE INTO products 
               (subcategory_id, name, slug, description, base_price, production_days, image_url, fabric_type, is_custom)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (sub_id, name, slug, desc, price, days, img, fabric, custom)
        )

    # Demo staff
    db.execute(
        "INSERT OR IGNORE INTO staff (username, password_hash, full_name, role, phone) VALUES (?,?,?,?,?)",
        ("admin", generate_password_hash("admin123"), "SewLagos Manager", "manager", "+2348012345678")
    )

    # Production calendar for next 30 days
    today = date.today()
    for i in range(30):
        d = today + timedelta(days=i)
        cap = 20 if d.weekday() < 5 else 12  # Less on weekends
        db.execute(
            "INSERT OR IGNORE INTO production_calendar (work_date, available_capacity, booked) VALUES (?,?,0)",
            (d.isoformat(), cap)
        )

# ---------- Auth helpers ----------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login to continue.", "warning")
            return redirect(url_for("login"))
        db = get_db()
        user = db.execute("SELECT id FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        if user is None:
            session.clear()
            flash("Your session has expired. Please log in again.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def generate_order_number():
    now = datetime.now()
    return f"SL-{now.strftime('%Y%m%d')}-{random.randint(1000,9999)}"

def generate_receipt_number(order_id):
    return f"RCPT-SL-{order_id:06d}-{random.randint(100,999)}"

def generate_otp():
    return str(random.randint(100000, 999999))

def calculate_ready_date(production_days, start_date=None):
    """Calculate earliest ready date considering production capacity."""
    db = get_db()
    if start_date is None:
        start_date = date.today() + timedelta(days=1)
    current = start_date
    days_needed = production_days
    while days_needed > 0:
        row = db.execute(
            "SELECT available_capacity, booked FROM production_calendar WHERE work_date = ?",
            (current.isoformat(),)
        ).fetchone()
        if row and row["booked"] < row["available_capacity"]:
            days_needed -= 1
        current += timedelta(days=1)
        if (current - start_date).days > 60:  # Safety
            break
    return current

# ---------- Routes ----------
@app.route("/")
def index():
    db = get_db()
    categories = db.execute("SELECT * FROM categories ORDER BY sort_order").fetchall()
    featured = db.execute(
        """SELECT p.*, s.name as subcat_name, c.name as cat_name 
           FROM products p 
           JOIN subcategories s ON p.subcategory_id = s.id
           JOIN categories c ON s.category_id = c.id
           WHERE p.is_active = 1 LIMIT 8"""
    ).fetchall()
    return render_template("index.html", categories=categories, featured=featured, slots=SLOTS)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        full_name = request.form.get("full_name", "").strip()
        password = request.form.get("password", "")
        email = request.form.get("email", "").strip()
        address = request.form.get("address", "").strip()
        lga = request.form.get("lga", "").strip()

        if not phone.startswith("+234") and not phone.startswith("0"):
            flash("Use Nigerian phone format: +234XXXXXXXXXX or 0XXXXXXXXXX", "danger")
            return redirect(url_for("register"))

        # Normalize phone
        if phone.startswith("0"):
            phone = "+234" + phone[1:]
        elif not phone.startswith("+"):
            phone = "+234" + phone

        db = get_db()
        existing = db.execute("SELECT id FROM users WHERE phone = ?", (phone,)).fetchone()
        if existing:
            flash("Phone number already registered. Please login.", "warning")
            return redirect(url_for("login"))

        otp = generate_otp()
        otp_expires = datetime.now() + timedelta(minutes=10)
        pw_hash = generate_password_hash(password)

        db.execute(
            """INSERT INTO users (phone, full_name, email, password_hash, address, lga, otp_code, otp_expires)
               VALUES (?,?,?,?,?,?,?,?)""",
            (phone, full_name, email, pw_hash, address, lga, otp, otp_expires)
        )
        db.commit()
        user_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # In production: send SMS via Termii / Africa's Talking / Twilio
        # For demo we show OTP on screen
        session["pending_user_id"] = user_id
        session["demo_otp"] = otp  # Demo only
        flash(f"OTP sent to {phone}. (Demo OTP: {otp})", "info")
        return redirect(url_for("verify_phone"))

    return render_template("register.html")

@app.route("/verify-phone", methods=["GET", "POST"])
def verify_phone():
    if "pending_user_id" not in session:
        return redirect(url_for("register"))

    if request.method == "POST":
        otp = request.form.get("otp", "").strip()
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE id = ?", (session["pending_user_id"],)
        ).fetchone()
        if not user:
            flash("Session expired. Register again.", "danger")
            return redirect(url_for("register"))

        if user["otp_code"] == otp and datetime.fromisoformat(user["otp_expires"]) > datetime.now():
            db.execute(
                "UPDATE users SET phone_verified = 1, otp_code = NULL WHERE id = ?",
                (user["id"],)
            )
            db.commit()
            session.pop("pending_user_id", None)
            session.pop("demo_otp", None)
            session["user_id"] = user["id"]
            session["user_name"] = user["full_name"]
            flash("Phone verified successfully! Welcome to SewLagos.", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid or expired OTP.", "danger")

    return render_template("verify_phone.html", demo_otp=session.get("demo_otp"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        if phone.startswith("0"):
            phone = "+234" + phone[1:]

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            if not user["phone_verified"]:
                session["pending_user_id"] = user["id"]
                otp = generate_otp()
                db.execute(
                    "UPDATE users SET otp_code = ?, otp_expires = ? WHERE id = ?",
                    (otp, datetime.now() + timedelta(minutes=10), user["id"])
                )
                db.commit()
                session["demo_otp"] = otp
                flash(f"Please verify your phone first. (Demo OTP: {otp})", "warning")
                return redirect(url_for("verify_phone"))
            session["user_id"] = user["id"]
            session["user_name"] = user["full_name"]
            flash(f"Welcome back, {user['full_name']}!", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid phone or password.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("index"))

@app.route("/catalog")
@app.route("/catalog/<cat_slug>")
@app.route("/catalog/<cat_slug>/<sub_slug>")
def catalog(cat_slug=None, sub_slug=None):
    db = get_db()
    categories = db.execute("SELECT * FROM categories ORDER BY sort_order").fetchall()
    query = """
        SELECT p.*, s.name as subcat_name, s.slug as sub_slug, c.name as cat_name, c.slug as cat_slug
        FROM products p
        JOIN subcategories s ON p.subcategory_id = s.id
        JOIN categories c ON s.category_id = c.id
        WHERE p.is_active = 1
    """
    params = []
    if cat_slug:
        query += " AND c.slug = ?"
        params.append(cat_slug)
    if sub_slug:
        query += " AND s.slug = ?"
        params.append(sub_slug)
    query += " ORDER BY p.base_price"
    products = db.execute(query, params).fetchall()
    return render_template("catalog.html", products=products, categories=categories,
                           cat_slug=cat_slug, sub_slug=sub_slug)

@app.route("/product/<int:product_id>")
def product_detail(product_id):
    db = get_db()
    product = db.execute(
        """SELECT p.*, s.name as subcat_name, c.name as cat_name
           FROM products p
           JOIN subcategories s ON p.subcategory_id = s.id
           JOIN categories c ON s.category_id = c.id
           WHERE p.id = ?""", (product_id,)
    ).fetchone()
    if not product:
        flash("Product not found.", "danger")
        return redirect(url_for("catalog"))
    ready_date = calculate_ready_date(product["production_days"])
    return render_template("product.html", product=product, ready_date=ready_date, slots=SLOTS)

@app.route("/order/<int:product_id>", methods=["GET", "POST"])
@login_required
def place_order(product_id):
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not product:
        flash("Product not found.", "danger")
        return redirect(url_for("catalog"))

    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()

    if request.method == "POST":
        qty = int(request.form.get("quantity", 1))
        slot = request.form.get("delivery_slot")
        notes = request.form.get("notes", "")
        customization = request.form.get("customization", "")
        address = request.form.get("address") or user["address"]
        lga = request.form.get("lga") or user["lga"]

        if slot not in SLOTS:
            flash("Invalid delivery slot.", "danger")
            return redirect(url_for("place_order", product_id=product_id))

        # Calculate ready date then next available slot
        ready = calculate_ready_date(product["production_days"])
        # Prefer delivery on ready date or next day
        preferred_date = ready
        # Simple capacity check for slot
        for attempt in range(7):
            row = db.execute(
                "SELECT current_bookings, max_capacity FROM delivery_slots WHERE slot_date=? AND slot_time=?",
                (preferred_date.isoformat(), slot)
            ).fetchone()
            if not row:
                db.execute(
                    "INSERT INTO delivery_slots (slot_date, slot_time, current_bookings) VALUES (?,?,1)",
                    (preferred_date.isoformat(), slot)
                )
                break
            elif row["current_bookings"] < row["max_capacity"]:
                db.execute(
                    "UPDATE delivery_slots SET current_bookings = current_bookings + 1 WHERE slot_date=? AND slot_time=?",
                    (preferred_date.isoformat(), slot)
                )
                break
            preferred_date += timedelta(days=1)

        total_items = product["base_price"] * qty
        total = total_items + DELIVERY_FEE
        order_number = generate_order_number()

        # Create order
        cur = db.execute(
            """INSERT INTO orders (order_number, user_id, status, total_amount, delivery_fee,
               payment_method, payment_status, delivery_slot, preferred_delivery_date,
               delivery_address, delivery_lga, customer_notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (order_number, session["user_id"], "pending", total, DELIVERY_FEE,
             "wallet", "pending", slot, preferred_date.isoformat(),
             address, lga, notes)
        )
        order_id = cur.lastrowid

        db.execute(
            """INSERT INTO order_items (order_id, product_id, quantity, unit_price, customization, production_days)
               VALUES (?,?,?,?,?,?)""",
            (order_id, product_id, qty, product["base_price"], customization, product["production_days"])
        )

        # Book production capacity
        start = date.today() + timedelta(days=1)
        days_left = product["production_days"]
        cur_date = start
        while days_left > 0:
            row = db.execute(
                "SELECT booked, available_capacity FROM production_calendar WHERE work_date=?",
                (cur_date.isoformat(),)
            ).fetchone()
            if row and row["booked"] < row["available_capacity"]:
                db.execute(
                    "UPDATE production_calendar SET booked = booked + 1 WHERE work_date=?",
                    (cur_date.isoformat(),)
                )
                days_left -= 1
            cur_date += timedelta(days=1)

        db.execute(
            "INSERT INTO order_status_history (order_id, old_status, new_status, notes) VALUES (?,?,?,?)",
            (order_id, None, "pending", "Order placed by customer")
        )
        db.commit()

        flash(f"Order {order_number} created! Proceed to payment.", "success")
        return redirect(url_for("pay_order", order_id=order_id))

    ready_date = calculate_ready_date(product["production_days"])
    return render_template("order.html", product=product, user=user, ready_date=ready_date,
                           slots=SLOTS, delivery_fee=DELIVERY_FEE)

@app.route("/pay/<int:order_id>", methods=["GET", "POST"])
@login_required
def pay_order(order_id):
    db = get_db()
    order = db.execute(
        "SELECT * FROM orders WHERE id = ? AND user_id = ?",
        (order_id, session["user_id"])
    ).fetchone()
    if not order:
        flash("Order not found.", "danger")
        return redirect(url_for("dashboard"))

    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()

    if request.method == "POST":
        method = request.form.get("payment_method", "wallet")
        if method == "wallet":
            if user["wallet_balance"] < order["total_amount"]:
                flash("Insufficient wallet balance. Please fund your wallet.", "danger")
                return redirect(url_for("wallet"))
            # Debit wallet
            new_bal = user["wallet_balance"] - order["total_amount"]
            db.execute("UPDATE users SET wallet_balance = ? WHERE id = ?", (new_bal, user["id"]))
            ref = f"WAL-{order['order_number']}"
            db.execute(
                """INSERT INTO wallet_transactions (user_id, order_id, type, amount, balance_after, description, reference)
                   VALUES (?,?,?,?,?,?,?)""",
                (user["id"], order_id, "debit", order["total_amount"], new_bal,
                 f"Payment for order {order['order_number']}", ref)
            )
            db.execute(
                "UPDATE orders SET payment_status = 'paid', payment_method = 'wallet', status = 'confirmed' WHERE id = ?",
                (order_id,)
            )
            db.execute(
                "INSERT INTO order_status_history (order_id, old_status, new_status, notes) VALUES (?,?,?,?)",
                (order_id, "pending", "confirmed", "Paid via wallet")
            )
            # Create receipt
            receipt_no = generate_receipt_number(order_id)
            db.execute(
                "INSERT INTO receipts (order_id, receipt_number, data_json) VALUES (?,?,?)",
                (order_id, receipt_no, json.dumps({"order_number": order["order_number"], "amount": order["total_amount"]}))
            )
            # Notification
            db.execute(
                "INSERT INTO notifications (user_id, title, message, type) VALUES (?,?,?,?)",
                (user["id"], "Order Confirmed", f"Your order {order['order_number']} has been confirmed and is now in production queue.", "order")
            )
            db.commit()
            flash("Payment successful! Order confirmed.", "success")
            return redirect(url_for("order_detail", order_id=order_id))
        else:
            # Simulate bank transfer / COD
            db.execute(
                "UPDATE orders SET payment_method = ?, status = 'confirmed' WHERE id = ?",
                (method, order_id)
            )
            db.execute(
                "INSERT INTO order_status_history (order_id, old_status, new_status, notes) VALUES (?,?,?,?)",
                (order_id, "pending", "confirmed", f"Payment method: {method}")
            )
            receipt_no = generate_receipt_number(order_id)
            db.execute(
                "INSERT INTO receipts (order_id, receipt_number) VALUES (?,?)",
                (order_id, receipt_no)
            )
            db.commit()
            flash("Order confirmed. Complete payment as instructed.", "info")
            return redirect(url_for("order_detail", order_id=order_id))

    return render_template("pay.html", order=order, user=user)

@app.route("/wallet", methods=["GET", "POST"])
@login_required
def wallet():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    transactions = db.execute(
        "SELECT * FROM wallet_transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT 20",
        (session["user_id"],)
    ).fetchall()

    if request.method == "POST":
        amount = float(request.form.get("amount", 0))
        if amount < 500:
            flash("Minimum funding is ₦500.", "warning")
            return redirect(url_for("wallet"))

        # Create unique reference (tx_ref)
        reference = f"SLW-{session['user_id']}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(1000,9999)}"
        callback_url = url_for("flutterwave_callback", _external=True)

        # Initialize Flutterwave payment
        result = flw_initialize(
            email=user["email"] or f"user{user['id']}@sewlagos.ng",
            amount_naira=amount,
            reference=reference,
            callback_url=callback_url,
            customer_name=user["full_name"],
            phone=user["phone"],
            meta={"user_id": str(user["id"]), "purpose": "wallet_funding"}
        )

        if "error" in result:
            # Fallback for demo when keys are not configured
            if not FLW_SECRET_KEY:
                flash("Flutterwave keys not configured yet. Using demo credit for testing.", "warning")
                new_bal = credit_wallet(user["id"], amount, reference + "-DEMO", "Demo wallet funding (replace Flutterwave keys)")
                if new_bal is not None:
                    flash(f"Wallet funded with ₦{amount:,.0f} (demo mode).", "success")
                return redirect(url_for("wallet"))
            flash(f"Could not start payment: {result['error']}", "danger")
            return redirect(url_for("wallet"))

        # Redirect customer to Flutterwave checkout
        return redirect(result["link"])

    return render_template(
        "wallet.html",
        user=user,
        transactions=transactions,
        flw_public_key=FLW_PUBLIC_KEY
    )


@app.route("/flutterwave/callback")
@login_required
def flutterwave_callback():
    """Called by Flutterwave after customer completes (or cancels) payment."""
    status = request.args.get("status")
    tx_ref = request.args.get("tx_ref")
    transaction_id = request.args.get("transaction_id")

    if status != "successful" or not tx_ref:
        flash("Payment was cancelled or failed.", "warning")
        return redirect(url_for("wallet"))

    # Verify with Flutterwave
    data = None
    if transaction_id:
        data = flw_verify(transaction_id)
    if not data:
        data = flw_verify_by_tx_ref(tx_ref)

    if not data:
        flash("Payment verification failed. If money was deducted, contact support.", "warning")
        return redirect(url_for("wallet"))

    amount_naira = float(data.get("amount", 0))
    meta = data.get("meta") or {}
    user_id = meta.get("user_id") or session.get("user_id")

    if not user_id:
        flash("Could not identify user for this payment.", "danger")
        return redirect(url_for("wallet"))

    new_bal = credit_wallet(int(user_id), amount_naira, tx_ref, "Wallet funding via Flutterwave")
    if new_bal is not None:
        flash(f"Payment successful! ₦{amount_naira:,.0f} has been added to your wallet.", "success")
    else:
        flash("Payment received. Your wallet has been updated.", "success")

    return redirect(url_for("wallet"))


@app.route("/flutterwave/webhook", methods=["POST"])
def flutterwave_webhook():
    """
    Flutterwave server-to-server notification (most reliable for bank transfers).
    Configure this URL in Flutterwave Dashboard → Settings → Webhooks.
    Also set a Secret Hash and put the same value in FLW_SECRET_HASH env var.
    """
    secret_hash = request.headers.get("verif-hash", "")
    if not FLW_SECRET_HASH or not hmac.compare_digest(secret_hash, FLW_SECRET_HASH):
        return jsonify({"status": "invalid hash"}), 401

    try:
        event = request.get_json(force=True)
    except Exception:
        return jsonify({"status": "bad payload"}), 400

    # Flutterwave sends different event structures; handle successful charge
    data = event.get("data") or event
    status = data.get("status") or event.get("event")
    transaction_id = data.get("id")
    if status in ("successful", "charge.completed") and transaction_id:
        # Never trust amount/user/tx_ref straight from the webhook body -
        # re-verify the transaction against Flutterwave's API first.
        verified = flw_verify(transaction_id)
        if verified:
            tx_ref = verified.get("tx_ref")
            amount = float(verified.get("amount", 0))
            meta = verified.get("meta") or {}
            user_id = meta.get("user_id")

            if user_id and tx_ref:
                credit_wallet(int(user_id), amount, tx_ref, "Wallet funding via Flutterwave (webhook)")

    return jsonify({"status": "ok"}), 200


@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    orders = db.execute(
        """SELECT o.*, r.receipt_number 
           FROM orders o LEFT JOIN receipts r ON o.id = r.order_id
           WHERE o.user_id = ? ORDER BY o.created_at DESC LIMIT 10""",
        (session["user_id"],)
    ).fetchall()
    notifications = db.execute(
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 8",
        (session["user_id"],)
    ).fetchall()
    return render_template("dashboard.html", user=user, orders=orders, notifications=notifications, slots=SLOTS)

@app.route("/order/<int:order_id>")
@login_required
def order_detail(order_id):
    db = get_db()
    order = db.execute(
        "SELECT * FROM orders WHERE id = ? AND user_id = ?",
        (order_id, session["user_id"])
    ).fetchone()
    if not order:
        flash("Order not found.", "danger")
        return redirect(url_for("dashboard"))
    items = db.execute(
        """SELECT oi.*, p.name as product_name, p.image_url 
           FROM order_items oi JOIN products p ON oi.product_id = p.id
           WHERE oi.order_id = ?""", (order_id,)
    ).fetchall()
    history = db.execute(
        "SELECT * FROM order_status_history WHERE order_id = ? ORDER BY created_at",
        (order_id,)
    ).fetchall()
    receipt = db.execute("SELECT * FROM receipts WHERE order_id = ?", (order_id,)).fetchone()
    return render_template("order_detail.html", order=order, items=items, history=history,
                           receipt=receipt, slots=SLOTS)

@app.route("/receipt/<int:order_id>")
@login_required
def receipt(order_id):
    db = get_db()
    order = db.execute(
        "SELECT o.*, u.full_name, u.phone, u.email FROM orders o JOIN users u ON o.user_id = u.id WHERE o.id = ? AND o.user_id = ?",
        (order_id, session["user_id"])
    ).fetchone()
    if not order:
        flash("Receipt not found.", "danger")
        return redirect(url_for("dashboard"))
    items = db.execute(
        """SELECT oi.*, p.name as product_name 
           FROM order_items oi JOIN products p ON oi.product_id = p.id WHERE oi.order_id = ?""",
        (order_id,)
    ).fetchall()
    receipt = db.execute("SELECT * FROM receipts WHERE order_id = ?", (order_id,)).fetchone()
    return render_template("receipt.html", order=order, items=items, receipt=receipt, slots=SLOTS)

@app.route("/calendar")
@login_required
def calendar():
    db = get_db()
    # User's upcoming deliveries
    upcoming = db.execute(
        """SELECT o.*, p.name as product_name FROM orders o
           JOIN order_items oi ON o.id = oi.order_id
           JOIN products p ON oi.product_id = p.id
           WHERE o.user_id = ? AND o.status NOT IN ('delivered','cancelled')
           ORDER BY o.preferred_delivery_date""",
        (session["user_id"],)
    ).fetchall()
    # Next 14 days slots overview (demo)
    today = date.today()
    days = []
    for i in range(14):
        d = today + timedelta(days=i)
        slots_info = {}
        for s in ["morning", "afternoon", "evening"]:
            row = db.execute(
                "SELECT current_bookings, max_capacity FROM delivery_slots WHERE slot_date=? AND slot_time=?",
                (d.isoformat(), s)
            ).fetchone()
            slots_info[s] = {
                "booked": row["current_bookings"] if row else 0,
                "max": row["max_capacity"] if row else 15
            }
        days.append({"date": d, "slots": slots_info})
    return render_template("calendar.html", upcoming=upcoming, days=days, slots=SLOTS)

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if request.method == "POST":
        full_name = request.form.get("full_name")
        email = request.form.get("email")
        address = request.form.get("address")
        lga = request.form.get("lga")
        db.execute(
            "UPDATE users SET full_name=?, email=?, address=?, lga=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (full_name, email, address, lga, session["user_id"])
        )
        db.commit()
        session["user_name"] = full_name
        flash("Profile updated.", "success")
        return redirect(url_for("profile"))
    return render_template("profile.html", user=user)

@app.route("/api/notifications/read/<int:nid>", methods=["POST"])
@login_required
def mark_notification_read(nid):
    db = get_db()
    db.execute(
        "UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?",
        (nid, session["user_id"])
    )
    db.commit()
    return jsonify({"ok": True})

# Admin simple view (for demo)
@app.route("/admin")
def admin():
    if session.get("user_id") != 1 and "admin" not in session:  # Simple check
        # Allow demo login
        pass
    db = get_db()
    orders = db.execute(
        """SELECT o.*, u.full_name, u.phone FROM orders o JOIN users u ON o.user_id = u.id
           ORDER BY o.created_at DESC LIMIT 30"""
    ).fetchall()
    return render_template("admin.html", orders=orders, slots=SLOTS)

@app.route("/admin/update-status/<int:order_id>", methods=["POST"])
def admin_update_status(order_id):
    new_status = request.form.get("status")
    notes = request.form.get("notes", "")
    db = get_db()
    order = db.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()
    if order:
        db.execute("UPDATE orders SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_status, order_id))
        db.execute(
            "INSERT INTO order_status_history (order_id, old_status, new_status, notes) VALUES (?,?,?,?)",
            (order_id, order["status"], new_status, notes)
        )
        # Notify customer
        user_id = db.execute("SELECT user_id FROM orders WHERE id = ?", (order_id,)).fetchone()["user_id"]
        db.execute(
            "INSERT INTO notifications (user_id, title, message, type) VALUES (?,?,?,?)",
            (user_id, f"Order Status: {new_status.title()}", f"Your order status changed to {new_status}. {notes}", "order")
        )
        db.commit()
        flash(f"Order updated to {new_status}.", "success")
    return redirect(url_for("admin"))

# ---------- Init & Run ----------
if __name__ == "__main__":
    if not os.path.exists(DATABASE):
        with app.app_context():
            init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
