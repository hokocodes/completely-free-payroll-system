
import csv
import json
import os
import hashlib

# File paths for local storage
EMPLOYEES_FILE = "employees.csv"
TIME_LOGS_FILE = "timelogs.json"
BACKUP_TIME_LOGS_FILE = "timelogs_backup.json"
ADMIN_PIN_HASH = hashlib.sha256("1234".encode()).hexdigest()  # Default PIN: 1234

def init_employees_file():
    if not os.path.exists(EMPLOYEES_FILE):
        with open(EMPLOYEES_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["employee_id", "name", "hourly_rate", "ssn", "address"])

def load_employees():
    employees = {}
    try:
        with open(EMPLOYEES_FILE, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                employees[row['employee_id']] = {
                    'name': row['name'],
                    'hourly_rate': float(row['hourly_rate']),
                    'ssn': row['ssn'],
                    'address': row['address']
                }
    except FileNotFoundError:
        init_employees_file()
    return employees

def save_employee(employee_id, name, hourly_rate, ssn, address):
    employees = load_employees()
    employees[employee_id] = {
        'name': name,
        'hourly_rate': hourly_rate,
        'ssn': ssn,
        'address': address
    }
    with open(EMPLOYEES_FILE, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["employee_id", "name", "hourly_rate", "ssn", "address"])
        for emp_id, data in employees.items():
            writer.writerow([emp_id, data['name'], data['hourly_rate'], data['ssn'], data['address']])

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
