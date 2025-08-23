
import http.server
import socketserver
import cgi
from urllib.parse import parse_qs
import logging
import socket
import hashlib
import datetime
import csv
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from data import load_employees, load_time_logs, save_time_logs, save_employee, ADMIN_PIN_HASH
from payrollutils import haversine_distance, calculate_hours, calculate_pay, calculate_pay_with_profile, SHOP_LAT, SHOP_LON, ALLOWED_RADIUS_METERS

class TimeClockHandler(http.server.SimpleHTTPRequestHandler):
    # Load .env relative to this file to avoid CWD issues
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'), override=True)
    # Configure file logging for SMTP and app events
    try:
        if not any(isinstance(h, RotatingFileHandler) for h in logging.getLogger().handlers):
            file_handler = RotatingFileHandler('app.log', maxBytes=1_000_000, backupCount=3)
            file_handler.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s %(levelname)s [%(name)s] %(message)s')
            file_handler.setFormatter(formatter)
            logging.getLogger().addHandler(file_handler)
            logging.getLogger().setLevel(logging.INFO)
    except Exception:
        pass
    employees = load_employees()
    time_logs = load_time_logs()

    def do_GET(self):
        logging.info(f"GET request from {self.client_address}")
        
        # Handle CSS file
        if self.path == "/style.css":
            self.send_response(200)
            self.send_header("Content-type", "text/css")
            self.end_headers()
            with open("style.css", 'rb') as f:
                self.wfile.write(f.read())
            return
        
        # Handle JSON endpoints first
        if self.path == "/get_employees":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            import json
            employees_list = []
            for emp_id, emp_data in self.employees.items():
                employees_list.append({
                    'employee_id': emp_id,
                    'name': emp_data.get('name', ''),
                    'hourly_rate': emp_data.get('hourly_rate', 0),
                    'ssn': emp_data.get('ssn', ''),
                    'address': emp_data.get('address', ''),
                    'email': emp_data.get('email', ''),
                    'visa_status': emp_data.get('visa_status', ''),
                    'w4_nonresident_alien': emp_data.get('w4_nonresident_alien', ''),
                    'pin': emp_data.get('pin', '')
                })
            self.wfile.write(json.dumps(employees_list).encode())
            return
        
        # Handle HTML endpoints
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        
        if self.path == "/report":
            response = self.view_report()
        elif self.path.startswith("/override"):
            pin = parse_qs(self.path.split('?')[1] if '?' in self.path else '').get('pin', [''])[0]
            pin = pin.strip()
            print(f"[DEBUG] Override GET - Received PIN: {pin}")
            print(f"[DEBUG] Override GET - ADMIN_PIN_HASH: {ADMIN_PIN_HASH}")
            if hashlib.sha256(pin.encode()).hexdigest() == ADMIN_PIN_HASH:
                response = self.override_form()
            else:
                response = "<h2>Invalid PIN</h2><a href='/'>Back</a>"
        elif self.path.startswith("/status"):
            params = parse_qs(self.path.split('?')[1] if '?' in self.path else '')
            employee_id = params.get('employee_id', [''])[0]
            pin = params.get('pin', [''])[0]
            response = self.show_status(employee_id, pin)
        else:
            response = """
            <html>
            <head>
                <title>Freezy Frenzy Time Clock</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <link rel="stylesheet" href="/style.css">
            </head>
            <body>
                <h2>Freezy Frenzy Employee Clock-In/Out</h2>
                <form action="/status" method="GET">
                    Employee ID: <input type="text" name="employee_id"><br><br>
                    PIN: <input type="password" name="pin"><br><br>
                    <input type="submit" value="Check Status">
                </form>
                <br>
                <form method="POST" action="/" onsubmit="return getLocation()">
                    Employee ID: <input type="text" name="employee_id"><br><br>
                    PIN: <input type="password" name="pin"><br><br>
                    <input type="hidden" name="latitude" id="latitude">
                    <input type="hidden" name="longitude" id="longitude">
                    <input type="submit" name="action" value="Clock In">
                    <input type="submit" name="action" value="Clock Out">
                </form>
                <br>
                <form method="POST" action="/admin">
                    PIN: <input type="password" name="pin"><br><br>
                    <input type="submit" value="Admin Panel">
                </form>
                <script>
                    function getLocation() {
                        if (navigator.geolocation) {
                            navigator.geolocation.getCurrentPosition(
                                (position) => {
                                    document.getElementById("latitude").value = position.coords.latitude;
                                    document.getElementById("longitude").value = position.coords.longitude;
                                    document.forms[1].submit();
                                },
                                (error) => {
                                    alert("Please enable location services to clock in/out.");
                                    return false;
                                }
                            );
                        } else {
                            alert("Geolocation not supported by your browser.");
                            return false;
                        }
                        return false;
                    }
                </script>
            </body>
            </html>
            """
        
        self.wfile.write(response.encode())

    def show_status(self, employee_id, pin):
        if not employee_id or employee_id not in self.employees:
            return "<h2>Error: Invalid Employee ID</h2><a href='/'>Back</a>"
        if self.employees[employee_id].get('pin') != pin:
            return "<h2>Error: Invalid PIN</h2><a href='/'>Back</a>"
        status = "Not clocked in."
        if employee_id in self.time_logs and self.time_logs[employee_id].get('clock_in'):
            status = f"Clocked in since {self.time_logs[employee_id]['clock_in']}"
            if self.time_logs[employee_id].get('manager_override'):
                status += " (Manager Override)"
        return f"""
        <html>
        <head>
            <title>Employee Status</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <link rel="stylesheet" href="/style.css">
        </head>
        <body>
            <h2>Employee Status</h2>
            <p>Employee: {self.employees[employee_id]['name']} (ID: {employee_id})</p>
            <p>Status: {status}</p>
            <a href='/'>Back to Clock-In/Out</a>
        </body>
        </html>
        """

    def override_form(self):
        html_content = """
        <html>
        <head>
            <title>Manager Override</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <link rel="stylesheet" href="/style.css">
        </head>
        <body>
            <h2>Manager Override: Set Clock-In/Out Time</h2>
            <form method="POST" action="/set_override">
                Employee ID: <input type="text" name="employee_id"><br><br>
                Clock-In Time (YYYY-MM-DD HH:MM:SS): <input type="text" name="clock_in_time" id="clock_in_time"><br><br>
                PIN: <input type="password" name="pin"><br><br>
                <input type="submit" value="Set Clock-In">
            </form>
            <form method="POST" action="/set_override_clockout">
                Employee ID: <input type="text" name="employee_id"><br><br>
                Clock-Out Time (YYYY-MM-DD HH:MM:SS): <input type="text" name="clock_out_time" id="clock_out_time"><br><br>
                PIN: <input type="password" name="pin"><br><br>
                <input type="submit" value="Set Clock-Out">
            </form>
            <script>
                function getCurrentDateTime() {
                    const now = new Date();
                    const year = now.getFullYear();
                    const month = String(now.getMonth() + 1).padStart(2, '0');
                    const day = String(now.getDate()).padStart(2, '0');
                    const hours = String(now.getHours()).padStart(2, '0');
                    const minutes = String(now.getMinutes()).padStart(2, '0');
                    const seconds = String(now.getSeconds()).padStart(2, '0');
                    return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
                }
                document.getElementById('clock_in_time').value = getCurrentDateTime();
                document.getElementById('clock_out_time').value = getCurrentDateTime();
            </script>
            <a href='/'>Back</a>
        </body>
        </html>
        """
        return html_content

    def view_report(self):
        pay_period_start = (datetime.datetime.now() - datetime.timedelta(days=14)).strftime("%Y-%m-%d")
        report_lines = []
        report_lines.append("<html><head><title>Payroll Report</title><link rel=\"stylesheet\" href=\"/style.css\"></head><body>")
        report_lines.append("<h2>Payroll Report</h2>")
        report_lines.append(f"<p>Pay Period: {pay_period_start} to {datetime.datetime.now().strftime('%Y-%m-%d')}</p>")
        for emp_id, data in self.time_logs.items():
            if 'sessions' not in data:
                continue
            total_hours = sum(session['hours'] for session in data['sessions'] if session['clock_out'] >= pay_period_start)
            if total_hours == 0:
                continue
            is_nra = str(self.employees[emp_id].get('w4_nonresident_alien', '')).lower() in ['yes', 'true', '1']
            gross, federal_tax, state_tax, net_pay = calculate_pay_with_profile(total_hours, self.employees[emp_id]['hourly_rate'], is_nra)
            report_lines.append(f"<p>Employee: {data['name']} (ID: {emp_id})</p>")
            report_lines.append(f"<p>SSN: {self.employees[emp_id]['ssn']}</p>")
            report_lines.append(f"<p>Address: {self.employees[emp_id]['address']}</p>")
            report_lines.append(f"<p>Total Hours: {total_hours:.2f}</p>")
            report_lines.append(f"<p>Gross Pay: ${gross:.2f}</p>")
            report_lines.append(f"<p>Federal Tax: ${federal_tax:.2f}</p>")
            report_lines.append(f"<p>State Tax: ${state_tax:.2f}</p>")
            report_lines.append(f"<p>Net Pay: ${net_pay:.2f}</p><br>")
        report_lines.append("<a href='/'>Back</a>")
        report_lines.append("</body></html>")
        return "\n".join(report_lines)

    def do_POST(self):
        logging.info(f"POST request from {self.client_address}")
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode()
        params = parse_qs(post_data)

        employee_id = params.get('employee_id', [''])[0]
        pin = params.get('pin', [''])[0]
        action = params.get('action', [''])[0]
        latitude = params.get('latitude', [''])[0]
        longitude = params.get('longitude', [''])[0]
        clock_in_time = params.get('clock_in_time', [''])[0]

        response = ""
        if self.path == "/admin":
            if hashlib.sha256(pin.encode()).hexdigest() == ADMIN_PIN_HASH:
                response = self.admin_form()
            else:
                response = "<h2>Invalid PIN</h2><a href='/'>Back</a>"
        elif self.path == "/save_employee":
            employee_id = params.get('employee_id', [''])[0]
            name = params.get('name', [''])[0]
            hourly_rate = params.get('hourly_rate', [''])[0]
            ssn = params.get('ssn', [''])[0]
            address = params.get('address', [''])[0]
            email = params.get('email', [''])[0]
            visa_status = params.get('visa_status', [''])[0]
            w4_nonresident_alien = 'yes' if ('w4_nonresident_alien' in params) else ''
            pin = params.get('pin', [''])[0]
            payment_method = params.get('payment_method', [''])[0]
            bank_routing = params.get('bank_routing', [''])[0]
            bank_account = params.get('bank_account', [''])[0]
            payroll_card_id = params.get('payroll_card_id', [''])[0]
            if hashlib.sha256(pin.encode()).hexdigest() == ADMIN_PIN_HASH:
                response = self.save_employee(employee_id, name, hourly_rate, ssn, address, email, visa_status, w4_nonresident_alien, payment_method, bank_routing, bank_account, payroll_card_id, pin)
            else:
                response = "<h2>Invalid PIN</h2><a href='/'>Back</a>"
        elif self.path == "/update_employee":
            employee_id = params.get('employee_id', [''])[0]
            name = params.get('name', [''])[0]
            hourly_rate = params.get('hourly_rate', [''])[0]
            ssn = params.get('ssn', [''])[0]
            address = params.get('address', [''])[0]
            email = params.get('email', [''])[0]
            visa_status = params.get('visa_status', [''])[0]
            w4_nonresident_alien = 'yes' if ('w4_nonresident_alien' in params) else ''
            pin = params.get('pin', [''])[0]
            if hashlib.sha256(pin.encode()).hexdigest() == ADMIN_PIN_HASH:
                if employee_id not in self.employees:
                    response = "<h2>Error: Employee not found</h2><a href='/'>Back</a>"
                else:
                    try:
                        hourly_rate = float(hourly_rate) if hourly_rate else self.employees[employee_id]['hourly_rate']
                        save_employee(
                            employee_id,
                            name or self.employees[employee_id]['name'],
                            hourly_rate,
                            ssn or self.employees[employee_id]['ssn'],
                            address or self.employees[employee_id]['address'],
                            email or self.employees[employee_id].get('email',''),
                            visa_status or self.employees[employee_id].get('visa_status',''),
                            w4_nonresident_alien or self.employees[employee_id].get('w4_nonresident_alien',''),
                            self.employees[employee_id].get('payment_method',''),
                            self.employees[employee_id].get('bank_routing',''),
                            self.employees[employee_id].get('bank_account',''),
                            self.employees[employee_id].get('payroll_card_id',''),
                            pin or self.employees[employee_id].get('pin',''),
                        )
                        self.employees = load_employees()
                        response = "<h2>Employee updated</h2><a href='/'>Back</a>"
                    except ValueError:
                        response = "<h2>Error: Invalid hourly rate</h2><a href='/'>Back</a>"
            else:
                response = "<h2>Invalid PIN</h2><a href='/'>Back</a>"
        elif self.path == "/update_payment_method":
            employee_id = params.get('employee_id', [''])[0]
            payment_method = params.get('payment_method', [''])[0]
            bank_routing = params.get('bank_routing', [''])[0]
            bank_account = params.get('bank_account', [''])[0]
            payroll_card_id = params.get('payroll_card_id', [''])[0]
            if hashlib.sha256(pin.encode()).hexdigest() == ADMIN_PIN_HASH:
                if employee_id not in self.employees:
                    response = "<h2>Error: Employee not found</h2><a href='/'>Back</a>"
                else:
                    emp = self.employees[employee_id]
                    save_employee(
                        employee_id,
                        emp['name'],
                        emp['hourly_rate'],
                        emp['ssn'],
                        emp['address'],
                        emp.get('email',''),
                        emp.get('visa_status',''),
                        emp.get('w4_nonresident_alien',''),
                        payment_method or emp.get('payment_method',''),
                        bank_routing or emp.get('bank_routing',''),
                        bank_account or emp.get('bank_account',''),
                        payroll_card_id or emp.get('payroll_card_id',''),
                    )
                    self.employees = load_employees()
                    response = "<h2>Payment method updated</h2><a href='/'>Back</a>"
            else:
                response = "<h2>Invalid PIN</h2><a href='/'>Back</a>"
        elif self.path == "/delete_employee":
            if hashlib.sha256(pin.encode()).hexdigest() == ADMIN_PIN_HASH:
                if employee_id not in self.employees:
                    response = "<h2>Error: Employee not found</h2><a href='/'>Back</a>"
                else:
                    emp_name = self.employees[employee_id]['name']
                    # Remove from employees
                    del self.employees[employee_id]
                    # Remove from time logs if exists
                    if employee_id in self.time_logs:
                        del self.time_logs[employee_id]
                    # Save changes
                    self.save_all_employees()
                    save_time_logs(self.time_logs)
                    response = f"<h2>Employee {emp_name} has been deleted</h2><a href='/'>Back</a>"
            else:
                response = "<h2>Invalid PIN</h2><a href='/'>Back</a>"
        elif self.path == "/run_payroll":
            if hashlib.sha256(pin.encode()).hexdigest() == ADMIN_PIN_HASH:
                response = self.run_payroll()
            else:
                response = "<h2>Invalid PIN</h2><a href='/'>Back</a>"
        elif self.path == "/set_override":
            print(f"[DEBUG] Override POST - Received employee_id: {employee_id}")
            print(f"[DEBUG] Override POST - Received clock_in_time: {clock_in_time}")
            print(f"[DEBUG] Override POST - Received PIN: {pin}")
            if hashlib.sha256(pin.encode()).hexdigest() == ADMIN_PIN_HASH:
                response = self.override_clock_in(employee_id, clock_in_time)
            else:
                response = "<h2>Invalid PIN</h2><a href='/'>Back</a>"
        elif self.path == "/set_override_clockout":
            clock_out_time = params.get('clock_out_time', [''])[0]
            if hashlib.sha256(pin.encode()).hexdigest() == ADMIN_PIN_HASH:
                response = self.override_clock_out(employee_id, clock_out_time)
            else:
                response = "<h2>Invalid PIN</h2><a href='/'>Back</a>"
        else:
            if employee_id not in self.employees:
                response = "<h2>Error: Invalid Employee ID</h2><a href='/'>Back</a>"
            elif self.employees[employee_id].get('pin') != pin:
                response = "<h2>Error: Invalid PIN</h2><a href='/'>Back</a>"
            elif not latitude or not longitude:
                response = "<h2>Error: Location not provided</h2><a href='/'>Back</a>"
            else:
                try:
                    lat = float(latitude)
                    lon = float(longitude)
                    distance = haversine_distance(lat, lon, SHOP_LAT, SHOP_LON)
                    if distance > ALLOWED_RADIUS_METERS:
                        response = f"<h2>Error: You are {distance:.0f}m away from Freezy Frenzy. Must be within {ALLOWED_RADIUS_METERS}m.</h2><a href='/'>Back</a>"
                    elif action == "Clock In":
                        if employee_id in self.time_logs and self.time_logs[employee_id].get('clock_in'):
                            response = "<h2>Error: Already clocked in</h2><a href='/'>Back</a>"
                        else:
                            clock_in_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            self.time_logs[employee_id] = {
                                'name': self.employees[employee_id]['name'],
                                'clock_in': clock_in_time,
                                'sessions': self.time_logs.get(employee_id, {}).get('sessions', []),
                                'last_location': {'lat': lat, 'lon': lon}
                            }
                            save_time_logs(self.time_logs)
                            response = f"<h2>Clocked in at {clock_in_time}</h2><p>Employee: {self.employees[employee_id]['name']}</p><a href='/'>Back</a>"
                    elif action == "Clock Out":
                        if employee_id not in self.time_logs or not self.time_logs[employee_id].get('clock_in'):
                            response = "<h2>Error: Not clocked in</h2><a href='/'>Back</a>"
                        else:
                            clock_out_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            hours = calculate_hours(self.time_logs[employee_id]['clock_in'], clock_out_time)
                            self.time_logs[employee_id]['sessions'].append({
                                'clock_in': self.time_logs[employee_id]['clock_in'],
                                'clock_out': clock_out_time,
                                'hours': hours,
                                'location': {'lat': lat, 'lon': lon}
                            })
                            del self.time_logs[employee_id]['clock_in']
                            save_time_logs(self.time_logs)
                            response = f"<h2>Clocked out at {clock_out_time}. Hours: {hours:.2f}</h2><p>Employee: {self.employees[employee_id]['name']}</p><a href='/'>Back</a>"
                except ValueError:
                    response = "<h2>Error: Invalid location data</h2><a href='/'>Back</a>"

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(response.encode())

    def admin_form(self):
        return """
        <html>
        <head>
            <title>Admin Panel</title>
            <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
            <link rel=\"stylesheet\" href=\"/style.css\">
            <style>
                .tab { display: none; }
                .tab.active { display: block; }
                .tab-buttons button { margin-right: 10px; }
            </style>
                            <script>
                    function showTab(tabId) {
                        console.log('Switching to tab:', tabId);
                        var tabs = document.getElementsByClassName('tab');
                        for (var i = 0; i < tabs.length; i++) {
                            tabs[i].classList.remove('active');
                        }
                        var targetTab = document.getElementById(tabId);
                        if (targetTab) {
                            targetTab.classList.add('active');
                            console.log('Tab', tabId, 'is now active');
                        } else {
                            console.error('Could not find tab:', tabId);
                        }
                        
                        // Load employees when view-employees tab is shown
                        if (tabId === 'view-employees') {
                            console.log('Loading employees for view-employees tab');
                            setTimeout(loadEmployees, 100); // Small delay to ensure DOM is ready
                        }
                    }
                    
                    function loadEmployees() {
                        console.log('Loading employees...');
                        fetch('/get_employees')
                            .then(response => {
                                console.log('Response status:', response.status);
                                return response.json();
                            })
                            .then(data => {
                                console.log('Employees data:', data);
                                const tbody = document.getElementById('employees-tbody');
                                if (!tbody) {
                                    console.error('Could not find employees-tbody element');
                                    return;
                                }
                                tbody.innerHTML = '';
                                
                                if (data.length === 0) {
                                    tbody.innerHTML = '<tr><td colspan=\"5\" style=\"text-align: center; padding: 20px;\">No employees found</td></tr>';
                                    return;
                                }
                                
                                data.forEach(emp => {
                                    const row = document.createElement('tr');
                                    row.style.cursor = 'pointer';
                                    row.onclick = function() { editEmployee(emp); };
                                    row.innerHTML = `
                                        <td style=\"border: 1px solid #ddd; padding: 8px;\">${emp.employee_id}</td>
                                        <td style=\"border: 1px solid #ddd; padding: 8px;\">${emp.name}</td>
                                        <td style=\"border: 1px solid #ddd; padding: 8px;\" class=\"hide-mobile\">$${emp.hourly_rate}</td>
                                        <td style=\"border: 1px solid #ddd; padding: 8px;\" class=\"hide-mobile\">${emp.ssn}</td>
                                        <td style=\"border: 1px solid #ddd; padding: 8px;\">
                                            <button onclick=\"editEmployee(${JSON.stringify(emp).replace(/"/g, '&quot;')})\" style=\"padding: 5px 10px; background-color: #2196F3; color: white; border: none; border-radius: 3px; cursor: pointer; margin-right: 5px;\">Edit</button>
                                            <button onclick=\"deleteEmployee('${emp.employee_id}', '${emp.name}')\" style=\"padding: 5px 10px; background-color: #f44336; color: white; border: none; border-radius: 3px; cursor: pointer;\">Delete</button>
                                        </td>
                                    `;
                                    tbody.appendChild(row);
                                });
                                console.log('Employees table populated with', data.length, 'rows');
                            })
                            .catch(error => {
                                console.error('Error loading employees:', error);
                                const tbody = document.getElementById('employees-tbody');
                                if (tbody) {
                                    tbody.innerHTML = '<tr><td colspan=\"5\" style=\"text-align: center; padding: 20px; color: red;\">Error loading employees: ' + error.message + '</td></tr>';
                                }
                            });
                    }
                    
                    function editEmployee(emp) {
                        // Populate edit form fields
                        document.getElementById('edit_emp_id').value = emp.employee_id;
                        document.getElementById('edit_name').value = emp.name;
                        document.getElementById('edit_rate').value = emp.hourly_rate;
                        document.getElementById('edit_ssn').value = emp.ssn;
                        document.getElementById('edit_address').value = emp.address || '';
                        document.getElementById('edit_email').value = emp.email || '';
                        document.getElementById('edit_visa').value = emp.visa_status || '';
                        document.getElementById('edit_nra').checked = emp.w4_nonresident_alien === 'yes' || emp.w4_nonresident_alien === 'true' || emp.w4_nonresident_alien === '1';
                        document.getElementById('edit_pin').value = emp.pin || '';
                        
                        // Switch to edit tab
                        showTab('edit-employee');
                    }
                    
                    function deleteEmployee(empId, empName) {
                        const adminPin = document.getElementById('admin_pin_for_actions').value;
                        if (!adminPin) {
                            alert('Please enter the Admin PIN first');
                            return;
                        }
                        if (confirm('Are you sure you want to delete employee ' + empName + ' (ID: ' + empId + ')?')) {
                            fetch('/delete_employee', {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/x-www-form-urlencoded',
                                },
                                body: 'employee_id=' + encodeURIComponent(empId) + '&pin=' + encodeURIComponent(adminPin)
                            })
                            .then(response => response.text())
                            .then(data => {
                                alert('Employee deleted successfully');
                                loadEmployees();
                            })
                            .catch(error => {
                                console.error('Error deleting employee:', error);
                                alert('Error deleting employee');
                            });
                        }
                    }
                    
                    function refreshEmployees() {
                        loadEmployees();
                    }
                    
                    window.onload = function() {
                        showTab('add-employee');
                    }
                </script>
        </head>
        <body>
            <h2>Admin Panel</h2>
            <div class=\"tab-buttons\">
                <button onclick=\"showTab('add-employee')\">Add Employee</button>
                <button onclick=\"showTab('edit-employee')\">Edit Employee</button>
                <button onclick=\"showTab('view-employees')\">View Employees</button>
                <button onclick=\"showTab('payment-method')\">Payment Method</button>
                <button onclick=\"showTab('run-payroll')\">Run Payroll</button>
                <button onclick=\"showTab('manager-override')\">Manager Override</button>
                <button onclick=\"showTab('view-report')\">View Report</button>
            </div>
            <div id=\"add-employee\" class=\"tab\">
                <h3>Add Employee</h3>
                <form method=\"POST\" action=\"/save_employee\">
                    Employee ID: <input type=\"text\" name=\"employee_id\"><br><br>
                    Name: <input type=\"text\" name=\"name\"><br><br>
                    Hourly Rate ($): <input type=\"text\" name=\"hourly_rate\"><br><br>
                    SSN: <input type=\"text\" name=\"ssn\"><br><br>
                    Address: <input type=\"text\" name=\"address\"><br><br>
                    Email: <input type=\"email\" name=\"email\"><br><br>
                    Visa Status: <input type=\"text\" name=\"visa_status\"><br><br>
                    Nonresident Alien (W-4): <input type=\"checkbox\" name=\"w4_nonresident_alien\"><br><br>
                    PIN: <input type=\"password\" name=\"pin\"><br><br>
                    <input type=\"submit\" value=\"Save Employee\">
                </form>
            </div>
            <div id=\"edit-employee\" class=\"tab\">
                <h3>Edit Employee</h3>
                <form method=\"POST\" action=\"/update_employee\">
                    Employee ID: <input type=\"text\" name=\"employee_id\" id=\"edit_emp_id\"><br><br>
                    Name: <input type=\"text\" name=\"name\" id=\"edit_name\"><br><br>
                    Hourly Rate ($): <input type=\"text\" name=\"hourly_rate\" id=\"edit_rate\"><br><br>
                    SSN: <input type=\"text\" name=\"ssn\" id=\"edit_ssn\"><br><br>
                    Address: <input type=\"text\" name=\"address\" id=\"edit_address\"><br><br>
                    Email: <input type=\"email\" name=\"email\" id=\"edit_email\"><br><br>
                    Visa Status: <input type=\"text\" name=\"visa_status\" id=\"edit_visa\"><br><br>
                    Nonresident Alien (W-4): <input type=\"checkbox\" name=\"w4_nonresident_alien\" id=\"edit_nra\"><br><br>
                    PIN: <input type=\"password\" name=\"pin\" id=\"edit_pin\"><br><br>
                    <input type=\"submit\" value=\"Update Employee\">
                </form>
            </div>
            <div id=\"view-employees\" class=\"tab\">
                <h3>View All Employees</h3>
                <div style=\"margin-bottom: 20px; padding: 15px; background-color: #f8f9fa; border-radius: 8px; border: 1px solid #dee2e6;\">
                    <strong>Admin PIN Required for Actions:</strong><br>
                    <input type=\"password\" id=\"admin_pin_for_actions\" placeholder=\"Enter Admin PIN\" style=\"width: 200px; margin-top: 10px; padding: 8px; border: 1px solid #ddd; border-radius: 4px;\">
                </div>
                <div id=\"employees-table\" class=\"table-container\">
                    <table style=\"width: 100%; border-collapse: collapse; margin-top: 20px;\">
                        <thead>
                            <tr style=\"background-color: #f2f2f2;\">
                                <th style=\"border: 1px solid #ddd; padding: 8px; text-align: left;\">ID</th>
                                <th style=\"border: 1px solid #ddd; padding: 8px; text-align: left;\">Name</th>
                                <th style=\"border: 1px solid #ddd; padding: 8px; text-align: left;\" class=\"hide-mobile\">Rate</th>
                                <th style=\"border: 1px solid #ddd; padding: 8px; text-align: left;\" class=\"hide-mobile\">SSN</th>
                                <th style=\"border: 1px solid #ddd; padding: 8px; text-align: left;\">Actions</th>
                            </tr>
                        </thead>
                        <tbody id=\"employees-tbody\">
                            <!-- Employee rows will be populated here -->
                        </tbody>
                    </table>
                </div>
                <button onclick=\"refreshEmployees()\" style=\"margin-top: 20px; padding: 10px; background-color: #4CAF50; color: white; border: none; border-radius: 4px; cursor: pointer;\">Refresh Table</button>
            </div>
            <div id=\"payment-method\" class=\"tab\">
                <h3>Payment Method</h3>
                <form method=\"POST\" action=\"/update_payment_method\">
                    Employee ID: <input type=\"text\" name=\"employee_id\"><br><br>
                    Payment Method: 
                    <select name=\"payment_method\">
                        <option value=\"direct_deposit\">Direct Deposit</option>
                        <option value=\"payroll_card\">Payroll Card</option>
                    </select><br><br>
                    Bank Routing #: <input type=\"text\" name=\"bank_routing\"><br><br>
                    Bank Account #: <input type=\"text\" name=\"bank_account\"><br><br>
                    Payroll Card ID: <input type=\"text\" name=\"payroll_card_id\"><br><br>
                    PIN: <input type=\"password\" name=\"pin\"><br><br>
                    <input type=\"submit\" value=\"Update Payment Method\">
                </form>
            </div>
            <div id=\"run-payroll\" class=\"tab\">
                <h3>Run Payroll</h3>
                <form method=\"POST\" action=\"/run_payroll\">
                    PIN: <input type=\"password\" name=\"pin\"><br><br>
                    <input type=\"submit\" value=\"Run Payroll\">
                </form>
            </div>
            <div id=\"manager-override\" class=\"tab\">
                <h3>Manager Override</h3>
                <form method=\"POST\" action=\"/set_override\">
                    Employee ID: <input type=\"text\" name=\"employee_id\"><br><br>
                    Clock-In Time (YYYY-MM-DD HH:MM:SS): <input type=\"text\" name=\"clock_in_time\" id=\"clock_in_time\"><br><br>
                    PIN: <input type=\"password\" name=\"pin\"><br><br>
                    <input type=\"submit\" value=\"Set Clock-In\">
                </form>
                <form method=\"POST\" action=\"/set_override_clockout\">
                    Employee ID: <input type=\"text\" name=\"employee_id\"><br><br>
                    Clock-Out Time (YYYY-MM-DD HH:MM:SS): <input type=\"text\" name=\"clock_out_time\" id=\"clock_out_time\"><br><br>
                    PIN: <input type=\"password\" name=\"pin\"><br><br>
                    <input type=\"submit\" value=\"Set Clock-Out\">
                </form>
                <script>
                    function getCurrentDateTime() {
                        const now = new Date();
                        const year = now.getFullYear();
                        const month = String(now.getMonth() + 1).padStart(2, '0');
                        const day = String(now.getDate()).padStart(2, '0');
                        const hours = String(now.getHours()).padStart(2, '0');
                        const minutes = String(now.getMinutes()).padStart(2, '0');
                        const seconds = String(now.getSeconds()).padStart(2, '0');
                        return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
                    }
                    document.addEventListener('DOMContentLoaded', function() {
                        document.getElementById('clock_in_time').value = getCurrentDateTime();
                        document.getElementById('clock_out_time').value = getCurrentDateTime();
                    });
                </script>
            </div>
            <div id=\"view-report\" class=\"tab\">
                <h3>View Payroll Report</h3>
                <a href='/report' target='_blank'>Open Payroll Report</a>
            </div>
            <br>
            <a href='/'>Back</a>
        </body>
        </html>
        """

    def save_employee(self, employee_id, name, hourly_rate, ssn, address, email="", visa_status="", w4_nonresident_alien="", payment_method="", bank_routing="", bank_account="", payroll_card_id="", pin=""):
        try:
            hourly_rate = float(hourly_rate)
            if not all([employee_id, name, ssn, address]):
                return "<h2>Error: All fields required</h2><a href='/'>Back</a>"
            if employee_id in self.employees:
                return "<h2>Error: Employee ID exists</h2><a href='/'>Back</a>"
            save_employee(employee_id, name, hourly_rate, ssn, address, email, visa_status, w4_nonresident_alien, payment_method, bank_routing, bank_account, payroll_card_id, pin)
            self.employees = load_employees()
            return "<h2>Employee added</h2><a href='/'>Back</a>"
        except ValueError:
            return "<h2>Error: Invalid hourly rate</h2><a href='/'>Back</a>"

    def override_clock_in(self, employee_id, clock_in_time):
        if not employee_id or employee_id not in self.employees:
            return "<h2>Error: Invalid Employee ID</h2><a href='/'>Back</a>"
        if employee_id in self.time_logs and self.time_logs[employee_id].get('clock_in'):
            return "<h2>Error: Employee already clocked in</h2><a href='/'>Back</a>"
        try:
            datetime.datetime.strptime(clock_in_time, "%Y-%m-%d %H:%M:%S")
            self.time_logs[employee_id] = {
                'name': self.employees[employee_id]['name'],
                'clock_in': clock_in_time,
                'sessions': self.time_logs.get(employee_id, {}).get('sessions', []),
                'manager_override': True
            }
            save_time_logs(self.time_logs)
            return f"<h2>Clock-in time set to {clock_in_time} for {self.employees[employee_id]['name']}</h2><a href='/'>Back</a>"
        except ValueError:
            return "<h2>Error: Invalid time format (use YYYY-MM-DD HH:MM:SS)</h2><a href='/'>Back</a>"

    def override_clock_out(self, employee_id, clock_out_time):
        if not employee_id or employee_id not in self.employees:
            return "<h2>Error: Invalid Employee ID</h2><a href='/'>Back</a>"
        if employee_id not in self.time_logs or not self.time_logs[employee_id].get('clock_in'):
            return "<h2>Error: Not clocked in</h2><a href='/'>Back</a>"
        try:
            datetime.datetime.strptime(clock_out_time, "%Y-%m-%d %H:%M:%S")
            clock_in_time = self.time_logs[employee_id]['clock_in']
            hours = calculate_hours(clock_in_time, clock_out_time)
            self.time_logs[employee_id]['sessions'].append({
                'clock_in': clock_in_time,
                'clock_out': clock_out_time,
                'hours': hours,
                'manager_override': True
            })
            del self.time_logs[employee_id]['clock_in']
            save_time_logs(self.time_logs)
            return f"<h2>Clock-out time set to {clock_out_time} for {self.employees[employee_id]['name']}. Hours: {hours:.2f}</h2><a href='/'>Back</a>"
        except ValueError:
            return "<h2>Error: Invalid time format (use YYYY-MM-DD HH:MM:SS)</h2><a href='/'>Back</a>"

    def run_payroll(self):
        pay_period_start = (datetime.datetime.now() - datetime.timedelta(days=14)).strftime("%Y-%m-%d")
        report = ["Payroll Report", f"Pay Period: {pay_period_start} to {datetime.datetime.now().strftime('%Y-%m-%d')}\n"]
        payments = [["employee_id","name","method","routing","account","amount","date"]]
        tax_deposits = [["date","federal_withholding_total"]]
        total_federal = 0.0

        os.makedirs("paystubs", exist_ok=True)
        today = datetime.datetime.now().strftime("%Y-%m-%d")

        for emp_id, data in self.time_logs.items():
            if 'sessions' not in data:
                continue
            total_hours = sum(session['hours'] for session in data['sessions'] if session['clock_out'] >= pay_period_start)
            if total_hours == 0:
                continue
            is_nra = str(self.employees[emp_id].get('w4_nonresident_alien', '')).lower() in ['yes', 'true', '1']
            hourly_rate = self.employees[emp_id]['hourly_rate']
            gross, federal_tax, state_tax, net_pay = calculate_pay_with_profile(total_hours, hourly_rate, is_nra)

            report.append(f"Employee: {data['name']} (ID: {emp_id})")
            report.append(f"Total Hours: {total_hours:.2f}")
            report.append(f"Gross Pay: ${gross:.2f}")
            report.append(f"Federal Tax: ${federal_tax:.2f}")
            report.append(f"Net Pay: ${net_pay:.2f}\n")

            total_federal += federal_tax

            method = self.employees[emp_id].get('payment_method','') or 'payroll_card'
            routing = self.employees[emp_id].get('bank_routing','')
            account = self.employees[emp_id].get('bank_account','')
            payroll_card_id = self.employees[emp_id].get('payroll_card_id','')
            routing_mask = (routing[-4:]).rjust(len(routing), '•') if routing else ''
            account_mask = (account[-4:]).rjust(len(account), '•') if account else payroll_card_id
            payments.append([emp_id, data['name'], method, routing_mask, account_mask, f"{net_pay:.2f}", today])

            # Generate paystub HTML
            email_addr = self.employees[emp_id].get('email','')
            stub_path = os.path.join('paystubs', f"{emp_id}_{today}.html")
            with open(stub_path, 'w', encoding='utf-8') as sf:
                sf.write(f"""
                <html><body>
                <h3>Paystub - {today}</h3>
                <p>Employee: {data['name']} (ID: {emp_id})</p>
                <p>Total Hours: {total_hours:.2f}</p>
                <p>Hourly Rate: ${hourly_rate:.2f}</p>
                <p>Gross Pay: ${gross:.2f}</p>
                <p>Federal Tax: ${federal_tax:.2f}</p>
                <p>State Tax: ${state_tax:.2f}</p>
                <p>Net Pay: ${net_pay:.2f}</p>
                <p>Payment Method: {method}</p>
                </body></html>
                """)

            # Generate paystub PDF (styled)
            pdf_path = os.path.join('paystubs', f"{emp_id}_{today}.pdf")
            c = canvas.Canvas(pdf_path, pagesize=LETTER)
            width, height = LETTER
            margin = 54

            # Outer border removed for cleaner spacing

            # Header banner
            header_h = 70
            c.setFillColor(colors.HexColor("#2E3A59"))
            c.roundRect(margin, height - margin - header_h, width - 2*margin, header_h, 12, stroke=0, fill=1)
            c.setFillColor(colors.white)
            company_name = "Freezy Frenzy"
            company_address = "17458 Northwest Fwy, Jersey Village, TX 77040"
            c.setFont("Helvetica-Bold", 20)
            c.drawString(margin + 16, height - margin - 40, f"{company_name}")
            c.setFont("Helvetica", 10)
            c.drawString(margin + 16, height - margin - 56, company_address)
            c.setFont("Helvetica", 12)
            c.drawRightString(width - margin - 16, height - margin - 46, f"Paystub • {today}")

            content_top = height - margin - header_h - 12

            # Employee and Period boxes
            col_gap = 12
            col_w = (width - 2*margin - col_gap) / 2
            box_h = 100
            # Employee box
            c.setStrokeColor(colors.HexColor("#8792B0"))
            c.roundRect(margin, content_top - box_h, col_w, box_h, 8, stroke=1, fill=0)
            c.setFillColor(colors.HexColor("#2E3A59"))
            c.setFont("Helvetica-Bold", 11)
            c.drawString(margin + 10, content_top - 18, "Employee")
            c.setFillColor(colors.black)
            c.setFont("Helvetica", 10)
            c.drawString(margin + 10, content_top - 36, f"Name: {data['name']}")
            c.drawString(margin + 10, content_top - 52, f"Employee ID: {emp_id}")
            addr = self.employees[emp_id].get('address', '') or ''
            parts = [p.strip() for p in addr.replace('\n', ', ').split(',') if p.strip()]
            if len(parts) >= 3:
                addr_line1 = ', '.join(parts[:-2])
                addr_line2 = ', '.join(parts[-2:])
            elif len(parts) == 2:
                addr_line1 = parts[0]
                addr_line2 = parts[1]
            else:
                # Fallback simple wrap if no commas present
                words = addr.split()
                split_index = max(1, min(len(words), len(words) // 2))
                addr_line1 = ' '.join(words[:split_index])
                addr_line2 = ' '.join(words[split_index:])
            c.drawString(margin + 10, content_top - 68, "Address:")
            c.drawString(margin + 70, content_top - 68, addr_line1)
            if addr_line2:
                c.drawString(margin + 70, content_top - 84, addr_line2)
            # Method shown in net section or can be appended here if needed

            # Period box
            c.roundRect(margin + col_w + col_gap, content_top - box_h, col_w, box_h, 8, stroke=1, fill=0)
            c.setFillColor(colors.HexColor("#2E3A59"))
            c.setFont("Helvetica-Bold", 11)
            c.drawString(margin + col_w + col_gap + 10, content_top - 18, "Pay Period")
            c.setFillColor(colors.black)
            c.setFont("Helvetica", 10)
            c.drawString(margin + col_w + col_gap + 10, content_top - 36, f"Start: {pay_period_start}")
            c.drawString(margin + col_w + col_gap + 10, content_top - 52, f"End: {today}")

            # Earnings box
            earnings_top = content_top - box_h - 16
            earnings_h = 180
            c.setStrokeColor(colors.HexColor("#8792B0"))
            c.roundRect(margin, earnings_top - earnings_h, width - 2*margin, earnings_h, 8, stroke=1, fill=0)
            c.setFillColor(colors.HexColor("#2E3A59"))
            c.setFont("Helvetica-Bold", 11)
            c.drawString(margin + 10, earnings_top - 18, "Earnings & Deductions")
            c.setFillColor(colors.black)
            c.setFont("Helvetica", 10)

            # Table rows
            row_y = earnings_top - 40
            row_h = 22
            left_x = margin + 14
            right_x = width - margin - 14
            def row(label, value):
                nonlocal row_y
                c.drawString(left_x, row_y, label)
                c.drawRightString(right_x, row_y, value)
                c.setStrokeColor(colors.HexColor("#E1E5EE"))
                c.line(margin + 10, row_y - 6, width - margin - 10, row_y - 6)
                row_y -= row_h

            row("Hours", f"{total_hours:.2f}")
            row("Hourly Rate", f"${hourly_rate:.2f}")
            row("Gross Pay", f"${gross:.2f}")
            row("Federal Tax", f"${federal_tax:.2f}")
            row("State Tax", f"${state_tax:.2f}")

            # Net pay highlight box
            net_box_h = 70
            net_box_y = margin + 30
            c.setStrokeColor(colors.HexColor("#2E3A59"))
            c.roundRect(margin, net_box_y, width - 2*margin, net_box_h, 10, stroke=1, fill=0)
            c.setFont("Helvetica-Bold", 12)
            c.setFillColor(colors.HexColor("#2E3A59"))
            c.drawString(margin + 16, net_box_y + net_box_h - 24, "Net Pay")
            c.setFillColor(colors.black)
            c.setFont("Helvetica-Bold", 18)
            c.drawRightString(width - margin - 16, net_box_y + net_box_h - 28, f"${net_pay:.2f}")

            # Footer note
            c.setFont("Helvetica", 8)
            c.setFillColor(colors.HexColor("#666666"))
            c.drawCentredString(width / 2, margin + 10, "This is a computer-generated paystub.")

            c.showPage()
            c.save()

            # Email paystub if SMTP configured and email provided
            try:
                smtp_host = os.getenv('SMTP_HOST')
                smtp_port = int(os.getenv('SMTP_PORT', '0') or 0)
                smtp_user = os.getenv('SMTP_USER')
                smtp_pass = os.getenv('SMTP_PASS')
                from_email = os.getenv('FROM_EMAIL') or smtp_user
                smtp_use_ssl = str(os.getenv('SMTP_USE_SSL', 'true')).lower() in ['1','true','yes']
                smtp_use_starttls = str(os.getenv('SMTP_USE_STARTTLS', 'false')).lower() in ['1','true','yes']
                if smtp_host and smtp_port and smtp_user and smtp_pass and from_email and email_addr:
                    logging.info(f"SMTP attempt host={smtp_host} port={smtp_port} ssl={smtp_use_ssl} starttls={smtp_use_starttls} from={from_email} to={email_addr}")
                    with open(stub_path, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                    msg = MIMEMultipart('alternative')
                    msg['Subject'] = f"Paystub - {today}"
                    msg['From'] = from_email
                    msg['To'] = email_addr
                    part = MIMEText(html_content, 'html')
                    msg.attach(part)
                    if smtp_use_ssl:
                        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
                            server.login(smtp_user, smtp_pass)
                            server.sendmail(from_email, [email_addr], msg.as_string())
                    else:
                        with smtplib.SMTP(smtp_host, smtp_port) as server:
                            if smtp_use_starttls:
                                server.starttls()
                            server.login(smtp_user, smtp_pass)
                            server.sendmail(from_email, [email_addr], msg.as_string())
                    logging.info(f"SMTP sent paystub to {email_addr}")
                else:
                    logging.warning("SMTP not configured or recipient email missing; skipping send")
            except Exception as e:
                logging.error(f"Failed to send paystub email to {email_addr}: {e}")

        tax_deposits.append([today, f"{total_federal:.2f}"])

        with open("payroll_report.csv", 'w', newline='') as f:
            writer = csv.writer(f)
            for line in report:
                writer.writerow([line])

        with open("payments.csv", 'w', newline='') as pf:
            writer = csv.writer(pf)
            writer.writerows(payments)

        with open("tax_deposit.csv", 'w', newline='') as tf:
            writer = csv.writer(tf)
            writer.writerows(tax_deposits)

        with open("w2_summary.csv", 'w', newline='') as wf:
            w = csv.writer(wf)
            w.writerow(["employee_id","name","ssn","wages","federal_income_tax_withheld","year"])
            year = datetime.datetime.now().strftime('%Y')
            for emp_id, data in self.time_logs.items():
                if 'sessions' not in data:
                    continue
                hours_ytd = 0
                for s in data['sessions']:
                    if s.get('clock_out','').startswith(year):
                        hours_ytd += s.get('hours', 0)
                if hours_ytd == 0:
                    continue
                is_nra = str(self.employees[emp_id].get('w4_nonresident_alien', '')).lower() in ['yes','true','1']
                gross, fed, state, net = calculate_pay_with_profile(hours_ytd, self.employees[emp_id]['hourly_rate'], is_nra)
                w.writerow([emp_id, data['name'], self.employees[emp_id]['ssn'], f"{gross:.2f}", f"{fed:.2f}", year])

        return "<h2>Payroll complete. Generated payroll_report.csv, payments.csv, tax_deposit.csv, w2_summary.csv and paystubs/ (emails sent if configured).</h2><a href='/'>Back</a>"

    def save_all_employees(self):
        """Save all employees to the CSV file"""
        with open("employees.csv", "w", newline="") as f:
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
            for emp_id, data in self.employees.items():
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

def run_server():
    PORT = 8000
    server = socketserver.TCPServer(("0.0.0.0", PORT), TimeClockHandler)
    logging.info(f"HTTP server running at http://{get_local_ip()}:{PORT}")
    server.serve_forever()

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ip
