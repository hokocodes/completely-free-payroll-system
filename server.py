
import http.server
import socketserver
import cgi
from urllib.parse import parse_qs
import logging
import socket
import hashlib
import datetime
import csv
from data import load_employees, load_time_logs, save_time_logs, save_employee, ADMIN_PIN_HASH
from payrollutils import haversine_distance, calculate_hours, calculate_pay, SHOP_LAT, SHOP_LON, ALLOWED_RADIUS_METERS

class TimeClockHandler(http.server.SimpleHTTPRequestHandler):
    employees = load_employees()
    time_logs = load_time_logs()

    def do_GET(self):
        logging.info(f"GET request from {self.client_address}")
        if self.path == "/style.css":
            self.send_response(200)
            self.send_header("Content-type", "text/css")
            self.end_headers()
            with open("style.css", 'rb') as f:
                self.wfile.write(f.read())
            return
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        if self.path == "/style.css":
            with open("style.css", 'rb') as f:
                self.send_response(200)
                self.send_header("Content-type", "text/css")
                self.end_headers()
                self.wfile.write(f.read())
                return
        elif self.path == "/report":
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
        if hashlib.sha256(pin.encode()).hexdigest() != ADMIN_PIN_HASH:
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
            <link rel="stylesheet" href="/style.css">
        </head>
        <body>
            <h2>Manager Override: Set Clock-In Time</h2>
            <form method="POST" action="/set_override">
                Employee ID: <input type="text" name="employee_id"><br><br>
                Clock-In Time (YYYY-MM-DD HH:MM:SS): <input type="text" name="clock_in_time" id="clock_in_time"><br><br>
                PIN: <input type="password" name="pin"><br><br>
                <input type="submit" value="Set Clock-In">
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
            gross, federal_tax, state_tax, net_pay = calculate_pay(total_hours, self.employees[emp_id]['hourly_rate'])
            report_lines.append(f"<p>Employee: {data['name']} (ID: {emp_id})</p>")
            report_lines.append(f"<p>SSN: {self.employees[emp_id]['ssn']}</p>")
            report_lines.append(f"<p>Address: {self.employees[emp_id]['address']}</p>")
            report_lines.append(f"<p>Total Hours: {total_hours:.2f}</p>")
            report_lines.append(f"<p>Gross Pay: ${gross:.2f}</p>")
            report_lines.append(f"<p>Federal Tax (15%): ${federal_tax:.2f}</p>")
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
            if hashlib.sha256(pin.encode()).hexdigest() == ADMIN_PIN_HASH:
                response = self.save_employee(employee_id, name, hourly_rate, ssn, address)
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
        else:
            if employee_id not in self.employees:
                response = "<h2>Error: Invalid Employee ID</h2><a href='/'>Back</a>"
            elif hashlib.sha256(pin.encode()).hexdigest() != ADMIN_PIN_HASH:
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
            <link rel="stylesheet" href="/style.css">
        </head>
        <body>
            <h2>Add Employee</h2>
            <form method="POST" action="/save_employee">
                Employee ID: <input type="text" name="employee_id"><br><br>
                Name: <input type="text" name="name"><br><br>
                Hourly Rate ($): <input type="text" name="hourly_rate"><br><br>
                SSN: <input type="text" name="ssn"><br><br>
                Address: <input type="text" name="address"><br><br>
                PIN: <input type="password" name="pin"><br><br>
                <input type="submit" value="Save Employee">
            </form>
            <form method="POST" action="/run_payroll">
                PIN: <input type="password" name="pin"><br><br>
                <input type="submit" value="Run Payroll">
            </form>
            <form action="/override" method="GET">
                PIN: <input type="password" name="pin"><br><br>
                <input type="submit" value="Manager Override">
            </form>
            <a href='/report'>View Payroll Report</a><br>
            <a href='/'>Back</a>
        </body>
        </html>
        """

    def save_employee(self, employee_id, name, hourly_rate, ssn, address):
        try:
            hourly_rate = float(hourly_rate)
            if not all([employee_id, name, ssn, address]):
                return "<h2>Error: All fields required</h2><a href='/'>Back</a>"
            if employee_id in self.employees:
                return "<h2>Error: Employee ID exists</h2><a href='/'>Back</a>"
            save_employee(employee_id, name, hourly_rate, ssn, address)
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

    def run_payroll(self):
        pay_period_start = (datetime.datetime.now() - datetime.timedelta(days=14)).strftime("%Y-%m-%d")
        report = ["Payroll Report", f"Pay Period: {pay_period_start} to {datetime.datetime.now().strftime('%Y-%m-%d')}\n"]
        for emp_id, data in self.time_logs.items():
            if 'sessions' not in data:
                continue
            total_hours = sum(session['hours'] for session in data['sessions'] if session['clock_out'] >= pay_period_start)
            if total_hours == 0:
                continue
            gross, federal_tax, state_tax, net_pay = calculate_pay(total_hours, self.employees[emp_id]['hourly_rate'])
            report.append(f"Employee: {data['name']} (ID: {emp_id})")
            report.append(f"SSN: {self.employees[emp_id]['ssn']}")
            report.append(f"Address: {self.employees[emp_id]['address']}")
            report.append(f"Total Hours: {total_hours:.2f}")
            report.append(f"Gross Pay: ${gross:.2f}")
            report.append(f"Federal Tax (15%): ${federal_tax:.2f}")
            report.append(f"State Tax: ${state_tax:.2f}")
            report.append(f"Net Pay: ${net_pay:.2f}\n")

        with open("payroll_report.csv", 'w', newline='') as f:
            writer = csv.writer(f)
            for line in report:
                writer.writerow([line])
        return "<h2>Payroll report generated as payroll_report.csv</h2><a href='/'>Back</a>"

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
