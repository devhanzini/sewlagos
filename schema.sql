-- SewLagos Database Schema
-- Functional DBMS for sewing business: registration → order fulfillment
-- Optimized for Lagos, Nigeria market

PRAGMA foreign_keys = ON;

-- Users / Customers
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone VARCHAR(15) UNIQUE NOT NULL,          -- Primary identifier (Nigerian format +234...)
    phone_verified BOOLEAN DEFAULT 0,
    otp_code VARCHAR(6),
    otp_expires DATETIME,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(120),
    password_hash VARCHAR(255) NOT NULL,
    address TEXT,                               -- Delivery address in Lagos
    lga VARCHAR(50),                            -- Local Government Area (Ikeja, Surulere, etc.)
    gender VARCHAR(10),
    wallet_balance DECIMAL(12,2) DEFAULT 0.00,  -- Wallet in Naira
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1
);

-- Admin / Staff (for order processing)
CREATE TABLE staff (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100),
    role VARCHAR(30) DEFAULT 'tailor',          -- tailor, manager, delivery
    phone VARCHAR(15),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Categories (standard cataloging)
CREATE TABLE categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(50) NOT NULL UNIQUE,           -- Women, Men, Kids
    slug VARCHAR(50) UNIQUE,
    description TEXT,
    sort_order INTEGER DEFAULT 0
);

-- Subcategories
CREATE TABLE subcategories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES categories(id),
    name VARCHAR(80) NOT NULL,                  -- Gown, Traditional Wear, Ankara, Dashiki, Agbada, etc.
    slug VARCHAR(80),
    description TEXT,
    UNIQUE(category_id, name)
);

-- Products / Designs (ready designs with images & prices)
CREATE TABLE products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subcategory_id INTEGER NOT NULL REFERENCES subcategories(id),
    name VARCHAR(150) NOT NULL,
    slug VARCHAR(150),
    description TEXT,
    base_price DECIMAL(12,2) NOT NULL,          -- Price in Naira (fabric + sewing included for ready designs)
    production_days INTEGER NOT NULL DEFAULT 7, -- Base production time in days
    image_url TEXT,                             -- Path or URL to design image
    fabric_type VARCHAR(50),                    -- Ankara, Aso-Oke, Lace, Adire, etc.
    is_custom BOOLEAN DEFAULT 0,                -- Allows customer measurements/spec
    stock_status VARCHAR(20) DEFAULT 'available', -- available, limited, made-to-order
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Customer measurements (for custom orders)
CREATE TABLE measurements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    label VARCHAR(50),                          -- e.g. "My standard", "Wedding"
    bust DECIMAL(5,1),
    waist DECIMAL(5,1),
    hips DECIMAL(5,1),
    shoulder DECIMAL(5,1),
    sleeve_length DECIMAL(5,1),
    dress_length DECIMAL(5,1),
    neck DECIMAL(5,1),
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Orders
CREATE TABLE orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_number VARCHAR(20) UNIQUE NOT NULL,   -- e.g. SL-20260911-0001
    user_id INTEGER NOT NULL REFERENCES users(id),
    status VARCHAR(30) DEFAULT 'pending',       -- pending, confirmed, in_production, ready, out_for_delivery, delivered, cancelled
    total_amount DECIMAL(12,2) NOT NULL,        -- Items + delivery
    delivery_fee DECIMAL(12,2) DEFAULT 1000.00, -- Fixed 1000 Naira
    payment_method VARCHAR(20) DEFAULT 'wallet',-- wallet, bank_transfer, cash_on_delivery
    payment_status VARCHAR(20) DEFAULT 'pending', -- pending, paid, refunded
    delivery_slot VARCHAR(20),                  -- morning (9-12), afternoon (12-3), evening (3-6)
    preferred_delivery_date DATE,               -- Calculated from production_days + demand
    actual_delivery_date DATE,
    delivery_address TEXT NOT NULL,
    delivery_lga VARCHAR(50),
    customer_notes TEXT,
    admin_notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Order items
CREATE TABLE order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER DEFAULT 1,
    unit_price DECIMAL(12,2) NOT NULL,
    customization TEXT,                         -- Customer specs, fabric preference, etc.
    measurement_id INTEGER REFERENCES measurements(id),
    production_days INTEGER,                    -- Snapshot of production time
    status VARCHAR(30) DEFAULT 'pending'        -- pending, cutting, sewing, finishing, ready
);

-- Wallet transactions
CREATE TABLE wallet_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    order_id INTEGER REFERENCES orders(id),
    type VARCHAR(20) NOT NULL,                  -- credit, debit
    amount DECIMAL(12,2) NOT NULL,
    balance_after DECIMAL(12,2) NOT NULL,
    description TEXT,
    reference VARCHAR(50) UNIQUE,               -- Payment reference
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Receipts / Invoices
CREATE TABLE receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL UNIQUE REFERENCES orders(id),
    receipt_number VARCHAR(30) UNIQUE NOT NULL, -- RCPT-SL-...
    issued_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    pdf_path TEXT,                              -- Optional generated PDF path
    data_json TEXT                              -- Snapshot of receipt data
);

-- Order status history (for calendar & monitoring)
CREATE TABLE order_status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    old_status VARCHAR(30),
    new_status VARCHAR(30) NOT NULL,
    changed_by INTEGER,                         -- staff_id or user_id
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Delivery slots capacity (for calendar management)
CREATE TABLE delivery_slots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slot_date DATE NOT NULL,
    slot_time VARCHAR(20) NOT NULL,             -- morning, afternoon, evening
    max_capacity INTEGER DEFAULT 15,            -- Max deliveries per slot in Lagos
    current_bookings INTEGER DEFAULT 0,
    UNIQUE(slot_date, slot_time)
);

-- Production capacity / demand tracking (affects timeline)
CREATE TABLE production_calendar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_date DATE NOT NULL UNIQUE,
    available_capacity INTEGER DEFAULT 20,      -- Orders that can be started that day
    booked INTEGER DEFAULT 0,
    notes TEXT
);

-- Notifications / Updates
CREATE TABLE notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title VARCHAR(150),
    message TEXT,
    type VARCHAR(30) DEFAULT 'order',           -- order, wallet, promo, system
    is_read BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX idx_users_phone ON users(phone);
CREATE INDEX idx_orders_user ON orders(user_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_delivery_date ON orders(preferred_delivery_date);
CREATE INDEX idx_wallet_user ON wallet_transactions(user_id);
CREATE INDEX idx_order_items_order ON order_items(order_id);
CREATE INDEX idx_products_subcat ON products(subcategory_id);
CREATE INDEX idx_delivery_slots_date ON delivery_slots(slot_date);
