
import csv
import json
import os
import hashlib

# File paths for local storage
EMPLOYEES_FILE = "employees.csv"
TIME_LOGS_FILE = "timelogs.json"
BACKUP_TIME_LOGS_FILE = "timelogs_backup.json"
ADMIN_PIN_HASH = hashlib.sha256("5197".encode()).hexdigest()  # Admin PIN: 5197

def init_employees_file():
    if not os.path.exists(EMPLOYEES_FILE):
        with open(EMPLOYEES_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "employee_id",
                "name",
                "hourly_rate",
                "ssn",
                "address",
                "email",
                "visa_status",
                "w4_nonresident_alien",
                "payment_method",
                "bank_routing",
                "bank_account",
                "payroll_card_id",
                "pin"
            ])

def load_employees():
    employees = {}
    try:
        with open(EMPLOYEES_FILE, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Backward compatibility for older CSVs without new columns
                def get_val(key, default=""):
                    return row[key] if key in row and row[key] is not None else default

                employees[row['employee_id']] = {
                    'name': get_val('name'),
                    'hourly_rate': float(get_val('hourly_rate', 0) or 0),
                    'ssn': get_val('ssn'),
                    'address': get_val('address'),
                    'email': get_val('email'),
                    'visa_status': get_val('visa_status'),
                    'w4_nonresident_alien': get_val('w4_nonresident_alien'),
                    'payment_method': get_val('payment_method'),
                    'bank_routing': get_val('bank_routing'),
                    'bank_account': get_val('bank_account'),
                    'payroll_card_id': get_val('payroll_card_id'),
                    'pin': get_val('pin'),
                }
    except FileNotFoundError:
        init_employees_file()
    return employees

def save_employee(
    employee_id,
    name,
    hourly_rate,
    ssn,
    address,
    email="",
    visa_status="",
    w4_nonresident_alien="",
    payment_method="",
    bank_routing="",
    bank_account="",
    payroll_card_id="",
    pin="",
):
    employees = load_employees()
    employees[employee_id] = {
        'name': name,
        'hourly_rate': hourly_rate,
        'ssn': ssn,
        'address': address,
        'email': email,
        'visa_status': visa_status,
        'w4_nonresident_alien': w4_nonresident_alien,
        'payment_method': payment_method,
        'bank_routing': bank_routing,
        'bank_account': bank_account,
        'payroll_card_id': payroll_card_id,
        'pin': pin,
    }
    with open(EMPLOYEES_FILE, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            "employee_id",
            "name",
            "hourly_rate",
            "ssn",
            "address",
            "email",
            "visa_status",
            "w4_nonresident_alien",
            "payment_method",
            "bank_routing",
            "bank_account",
            "payroll_card_id",
            "pin",
        ])
        for emp_id, data in employees.items():
            writer.writerow([
                emp_id,
                data.get('name', ''),
                data.get('hourly_rate', 0),
                data.get('ssn', ''),
                data.get('address', ''),
                data.get('email', ''),
                data.get('visa_status', ''),
                data.get('w4_nonresident_alien', ''),
                data.get('payment_method', ''),
                data.get('bank_routing', ''),
                data.get('bank_account', ''),
                data.get('payroll_card_id', ''),
                data.get('pin', ''),
            ])

def load_time_logs():
    try:
        with open(TIME_LOGS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_time_logs(logs):
    with open(TIME_LOGS_FILE, 'w') as f:
        json.dump(logs, f, indent=2)
    with open(BACKUP_TIME_LOGS_FILE, 'w') as f:
        json.dump(logs, f, indent=2)
