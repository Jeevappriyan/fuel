from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
import qrcode
import uuid
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Change for production


# Create database if it doesn't exist
def initialize_db():
    conn = sqlite3.connect('petrol_fastag.db')
    cursor = conn.cursor()

    # Create tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT,
            phone TEXT UNIQUE,
            email TEXT UNIQUE,
            created_at TIMESTAMP
        )
        ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vehicles (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            vehicle_number TEXT UNIQUE,
            vehicle_type TEXT,
            fuel_type TEXT,
            barcode_path TEXT,
            created_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            balance REAL DEFAULT 0.0,
            updated_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY,
            account_id TEXT,
            amount REAL,
            transaction_type TEXT,
            timestamp TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        )
        ''')

    conn.commit()
    conn.close()


@app.route('/')
def home():
    return render_template('home.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name')
        phone = request.form.get('phone')
        email = request.form.get('email')
        vehicle_number = request.form.get('vehicle_number')
        vehicle_type = request.form.get('vehicle_type')
        fuel_type = request.form.get('fuel_type')

        conn = sqlite3.connect('petrol_fastag.db')
        cursor = conn.cursor()

        try:
            # Create user
            user_id = str(uuid.uuid4())
            cursor.execute(
                'INSERT INTO users (id, name, phone, email, created_at) VALUES (?, ?, ?, ?, ?)',
                (user_id, name, phone, email, datetime.now())
            )

            # Create account
            account_id = str(uuid.uuid4())
            cursor.execute(
                'INSERT INTO accounts (id, user_id, updated_at) VALUES (?, ?, ?)',
                (account_id, user_id, datetime.now())
            )

            # Create vehicle and generate barcode
            vehicle_id = str(uuid.uuid4())

            # Generate QR code data - a JSON string containing important information
            qr_data = f"{{\"vehicle_id\":\"{vehicle_id}\",\"vehicle_number\":\"{vehicle_number}\",\"vehicle_type\":\"{vehicle_type}\",\"fuel_type\":\"{fuel_type}\",\"account_id\":\"{account_id}\"}}"

            # Generate QR code image
            os.makedirs('static/barcodes', exist_ok=True)
            barcode_filename = f"barcode_{vehicle_id}.png"
            barcode_path = f"static/barcodes/{barcode_filename}"
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(qr_data)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            img.save(barcode_path)

            # Save vehicle to database
            cursor.execute(
                'INSERT INTO vehicles (id, user_id, vehicle_number, vehicle_type, fuel_type, barcode_path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (vehicle_id, user_id, vehicle_number, vehicle_type, fuel_type, barcode_filename, datetime.now())
            )

            conn.commit()
            flash('Registration successful! You can now add money to your account.')
            return redirect(url_for('view_vehicle', vehicle_id=vehicle_id))

        except Exception as e:
            conn.rollback()
            flash(f'Registration failed: {str(e)}')

        finally:
            conn.close()

    return render_template('register.html')


@app.route('/vehicle/<vehicle_id>')
def view_vehicle(vehicle_id):
    conn = sqlite3.connect('petrol_fastag.db')
    cursor = conn.cursor()

    # Get vehicle and account details
    cursor.execute('''
            SELECT v.*, a.balance 
            FROM vehicles v
            JOIN users u ON v.user_id = u.id
            JOIN accounts a ON u.id = a.user_id
            WHERE v.id = ?
        ''', (vehicle_id,))

    vehicle = cursor.fetchone()
    conn.close()

    if vehicle:
        # Convert to dictionary for easy access in template
        vehicle_data = {
            'id': vehicle[0],
            'user_id': vehicle[1],
            'vehicle_number': vehicle[2],
            'vehicle_type': vehicle[3],
            'fuel_type': vehicle[4],
            'barcode_path': vehicle[5],
            'created_at': vehicle[6],
            'balance': vehicle[7]
        }
        return render_template('vehicle.html', vehicle=vehicle_data)
    else:
        flash('Vehicle not found')
        return redirect(url_for('home'))


@app.route('/add_money/<account_id>', methods=['GET', 'POST'])
def add_money(account_id):
    if request.method == 'POST':
        amount = float(request.form.get('amount', 0))

        if amount <= 0:
            flash('Please enter a valid amount')
            return redirect(url_for('add_money', account_id=account_id))

        conn = sqlite3.connect('petrol_fastag.db')
        cursor = conn.cursor()

        try:
            # Update account balance
            cursor.execute('UPDATE accounts SET balance = balance + ?, updated_at = ? WHERE id = ?',
                           (amount, datetime.now(), account_id))

            # Record transaction
            transaction_id = str(uuid.uuid4())
            cursor.execute(
                'INSERT INTO transactions (id, account_id, amount, transaction_type, timestamp) VALUES (?, ?, ?, ?, ?)',
                (transaction_id, account_id, amount, 'CREDIT', datetime.now())
            )

            conn.commit()
            flash(f'Successfully added {amount} to your account')

            # Get user_id and redirect to user dashboard
            cursor.execute('SELECT user_id FROM accounts WHERE id = ?', (account_id,))
            user_id = cursor.fetchone()[0]

            # Get first vehicle to redirect
            cursor.execute('SELECT id FROM vehicles WHERE user_id = ? LIMIT 1', (user_id,))
            vehicle_result = cursor.fetchone()

            conn.close()

            if vehicle_result:
                return redirect(url_for('view_vehicle', vehicle_id=vehicle_result[0]))
            else:
                return redirect(url_for('home'))

        except Exception as e:
            conn.rollback()
            flash(f'Failed to add money: {str(e)}')
            conn.close()

    return render_template('add_money.html', account_id=account_id)


if __name__ == '__main__':
    initialize_db()
    app.run(debug=True, port=5000)