from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import sqlite3
import uuid
import cv2
from pyzbar.pyzbar import decode
import json
from datetime import datetime
import time

app = Flask(__name__)
app.secret_key = 'your_pos_secret_key'  # Change for production


# Connect to the same database
def get_db_connection():
    conn = sqlite3.connect('petrol_fastag.db')
    conn.row_factory = sqlite3.Row  # This enables column access by name
    return conn


@app.route('/')
def home():
    return render_template('pos_home.html')


@app.route('/scan', methods=['GET', 'POST'])
def scan():
    if request.method == 'POST':
        try:
            # In a real application, this would access the camera
            # For demonstration, we'll assume the QR data is directly provided
            qr_data = request.form.get('qr_data')

            # In a real implementation, you would use:
            # camera = cv2.VideoCapture(0)
            # _, frame = camera.read()
            # decoded_objects = decode(frame)
            # for obj in decoded_objects:
            #     qr_data = obj.data.decode('utf-8')

            # Parse the QR data
            vehicle_data = json.loads(qr_data)

            # Get account information
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT a.id as account_id, a.balance, v.vehicle_number, v.vehicle_type, v.fuel_type, u.name
                FROM accounts a
                JOIN users u ON a.user_id = u.id
                JOIN vehicles v ON u.id = v.user_id
                WHERE v.id = ?
            ''', (vehicle_data['vehicle_id'],))

            account_info = cursor.fetchone()
            conn.close()

            if not account_info:
                flash('Account not found')
                return redirect(url_for('home'))

            # Pass account info to the payment page
            return render_template('payment.html',
                                   account_info=dict(account_info),
                                   vehicle_id=vehicle_data['vehicle_id'])

        except Exception as e:
            flash(f'Error scanning code: {str(e)}')
            return redirect(url_for('home'))

    return render_template('scan.html')


@app.route('/process_payment', methods=['POST'])
def process_payment():
    account_id = request.form.get('account_id')
    vehicle_id = request.form.get('vehicle_id')
    amount = float(request.form.get('amount', 0))

    if amount <= 0:
        flash('Please enter a valid amount')
        return redirect(url_for('scan'))

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Check if account has sufficient balance
        cursor.execute('SELECT balance FROM accounts WHERE id = ?', (account_id,))
        current_balance = cursor.fetchone()['balance']

        if current_balance < amount:
            flash('Insufficient balance')
            conn.close()
            return redirect(url_for('scan'))

        # Update account balance
        cursor.execute('UPDATE accounts SET balance = balance - ?, updated_at = ? WHERE id = ?',
                       (amount, datetime.now(), account_id))

        # Record transaction
        transaction_id = str(uuid.uuid4())
        cursor.execute(
            'INSERT INTO transactions (id, account_id, amount, transaction_type, timestamp) VALUES (?, ?, ?, ?, ?)',
            (transaction_id, account_id, -amount, 'DEBIT', datetime.now())
        )

        conn.commit()

        # Get updated balance
        cursor.execute('SELECT balance FROM accounts WHERE id = ?', (account_id,))
        new_balance = cursor.fetchone()['balance']
        conn.close()

        # Show success screen
        return render_template('transaction_success.html',
                               amount=amount,
                               new_balance=new_balance,
                               transaction_id=transaction_id,
                               timestamp=datetime.now())

    except Exception as e:
        conn.rollback()
        flash(f'Payment failed: {str(e)}')
        conn.close()
        return redirect(url_for('scan'))


@app.route('/manual_entry')
def manual_entry():
    return render_template('manual_entry.html')


@app.route('/find_vehicle', methods=['POST'])
def find_vehicle():
    vehicle_number = request.form.get('vehicle_number')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT v.id as vehicle_id, v.vehicle_number, v.vehicle_type, v.fuel_type, 
               a.id as account_id, a.balance, u.name
        FROM vehicles v
        JOIN users u ON v.user_id = u.id
        JOIN accounts a ON u.id = a.user_id
        WHERE v.vehicle_number = ?
    ''', (vehicle_number,))

    vehicle = cursor.fetchone()
    conn.close()

    if vehicle:
        return render_template('payment.html',
                               account_info=dict(vehicle),
                               vehicle_id=vehicle['vehicle_id'])
    else:
        flash('Vehicle not found')
        return redirect(url_for('manual_entry'))


if __name__ == '__main__':
    app.run(debug=True, port=5001)