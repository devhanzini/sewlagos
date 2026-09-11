# SewLagos – Nigerian Sewing Business Vending Application

**Lagos-focused startup** for custom and ready-to-wear Nigerian clothing (Ankara, Agbada, Bubu, Senator, traditional sets, kids wear).

## Features Implemented

### Customer Journey
1. **Registration** with Nigerian phone number (+234 / 0XXXXXXXXXX)
2. **Phone OTP verification** (demo shows OTP on screen; production → SMS gateway)
3. **Catalog** by category: Women / Men / Kids
   - Subcategories: Gowns, Traditional (Iro & Buba), Ankara, Bubu, Agbada, Senator, Dashiki, Kids traditional & Ankara
4. **Product detail** with realistic Naira prices and production lead times
5. **Order placement** with:
   - Customization notes
   - Delivery address + LGA
   - **Fixed delivery fee ₦1,000**
   - **Time slots**: Morning 9am–12pm, Afternoon 12pm–3pm, Evening 3pm–6pm
6. **Production timeline** calculated from product `production_days` + capacity calendar
7. **Wallet system** – fund and pay instantly (demo funding)
8. **Transaction receipts** printable
9. **Dashboard** – profile, orders, notifications, wallet balance
10. **Calendar** – upcoming deliveries + slot availability for next 14 days
11. **Order status tracking** with history timeline
12. **Admin panel** (`/admin`) – update order status through production pipeline

### Database (SQLite – production ready schema)
Full relational schema covering:
- Users (phone as primary identity, wallet, verification)
- Categories / Subcategories / Products
- Orders + Order Items + Status History
- Wallet Transactions
- Receipts
- Delivery Slots capacity
- Production Calendar (demand-aware lead times)
- Notifications
- Staff

See `schema.sql` for complete DDL.

### Prices (sample, realistic Lagos 2025/2026)
- Ankara Maxi Gown: ₦28,500 (~7 days)
- Beaded Bubu: ₦42,000 (~10 days)
- Iro & Buba + Gele: ₦55,000 (~10 days)
- Embroidered Agbada: ₦85,000 (~14 days)
- Senator: ₦32,000 (~7 days)
- Kids Mini Agbada: ₦25,000 (~7 days)
- etc.

## How to Run

```bash
cd sewlagos
pip install flask
python app.py
```

Open http://127.0.0.1:5000

### Demo Flow
1. Register with any Nigerian phone format
2. Enter the OTP shown on screen
3. Browse catalog → Order a design
4. Fund wallet (any amount ≥ ₦500)
5. Pay with wallet
6. View receipt, dashboard, calendar
7. Admin: go to `/admin` to advance order status

## Production Notes
- Replace demo OTP with Termii / Africa's Talking / Twilio SMS
- Integrate Paystack or Flutterwave for real wallet funding & payments
- Move to PostgreSQL
- Add real product images (Unsplash/African fashion stock or own photography)
- Add measurement form for fully custom orders
- Delivery rider assignment module
- Push notifications / WhatsApp status updates

Built for the Nigerian market with Lagos delivery logistics in mind.

## Deploy to GitHub

This repository is ready to push to your GitHub account.

### Option 1 – Create the repo on GitHub then push

1. Go to https://github.com/new
2. Repository name: `sewlagos` (or any name you like)
3. Keep it public or private, **do not** initialize with README
4. Click Create repository
5. Then run these commands in the project folder:

```bash
git remote add origin https://github.com/devhanzini/sewlagos.git
git push -u origin main
```

If GitHub asks for credentials, use a **Personal Access Token** (Settings → Developer settings → Personal access tokens) instead of your password.

### Option 2 – Using GitHub CLI (if installed)

```bash
gh repo create sewlagos --public --source=. --remote=origin --push
```

### After pushing

You can then connect the repo to:
- Railway / Render / Fly.io for free/cheap hosting
- Or Vercel (with a small adaptation)
- Or your own VPS

The app creates the SQLite database automatically on first run (`python app.py`).

## Flutterwave Integration (Wallet Funding)

SewLagos uses **Flutterwave** for real wallet funding.

### How it works
1. Customer enters amount on the Wallet page
2. App calls Flutterwave payments API
3. Customer is redirected to Flutterwave (Card / Bank Transfer / USSD)
4. After payment, Flutterwave redirects back to `/flutterwave/callback`
5. App verifies the transaction and credits the wallet
6. Flutterwave also sends a **webhook** to `/flutterwave/webhook` (most reliable for bank transfers)

### Setup (Test Mode – free)

1. Login to https://app.flutterwave.com
2. Go to **Settings → API Keys**
3. Copy your **Secret Key** (`FLWSECK_TEST-...` or live) and **Public Key**
4. (Recommended) Go to Settings → Webhooks and set a **Secret Hash**
5. Set environment variables:

```bash
# Linux / macOS
export FLW_SECRET_KEY=FLWSECK_TEST-xxxxxxxx
export FLW_PUBLIC_KEY=FLWPUBK_TEST-xxxxxxxx
export FLW_SECRET_HASH=your_secret_hash_here

# Windows (Command Prompt)
set FLW_SECRET_KEY=FLWSECK_TEST-xxxxxxxx
set FLW_PUBLIC_KEY=FLWPUBK_TEST-xxxxxxxx
set FLW_SECRET_HASH=your_secret_hash_here

# Windows (PowerShell)
$env:FLW_SECRET_KEY="FLWSECK_TEST-xxxxxxxx"
$env:FLW_PUBLIC_KEY="FLWPUBK_TEST-xxxxxxxx"
$env:FLW_SECRET_HASH="your_secret_hash_here"
```

6. Set Webhook URL in Flutterwave dashboard to:
   `https://your-domain.com/flutterwave/webhook`

### Demo fallback
If the secret key still contains `xxxxxxxx`, the app will credit the wallet in **demo mode** so you can test without real keys.

### Going Live
1. Complete Flutterwave business verification
2. Switch to **Live** keys
3. Update the environment variables on Railway/Render
4. Point the webhook to your live domain

