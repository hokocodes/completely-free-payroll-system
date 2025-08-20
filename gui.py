
import tkinter as tk
from tkinter import messagebox, simpledialog
from data import load_employees, save_employee, load_time_logs, save_time_logs, ADMIN_PIN_HASH
from payrollutils import calculate_hours, calculate_pay
import hashlib
import datetime
import csv

class PayrollApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Freezy Frenzy Payroll & Time Clock")
        self.employees = load_employees()
        self.time_logs = load_time_logs()

        # Main frame
        self.main_frame = tk.Frame(root)
        self.main_frame.pack(padx=10, pady=10)

        # Employee selection
        tk.Label(self.main_frame, text="Select Employee ID:").pack()
        self.employee_id_var = tk.StringVar(self.root)
        self.employee_id_var.set(list(self.employees.keys())[0] if self.employees else "")
        self.employee_menu = tk.OptionMenu(self.main_frame, self.employee_id_var, *self.employees.keys() if self.employees else [""])
        self.employee_menu.pack()

        # Clock in/out buttons
        tk.Button(self.main_frame, text="Clock In", command=self.clock_in).pack(pady=5)
        tk.Button(self.main_frame, text="Clock Out", command=self.clock_out).pack(pady=5)
        tk.Button(self.main_frame, text="Admin Panel", command=self.open_admin_panel).pack(pady=5)

        # Status label
        self.status_var = tk.StringVar(value="Welcome! Select an employee or use mobile clock-in.")
        tk.Label(self.main_frame, textvariable=self.status_var).pack(pady=10)

    def clock_in(self):
        employee_id = self.employee_id_var.get()
        print(f"[DEBUG] Attempting to clock in employee_id: {employee_id}")
        print(f"[DEBUG] Available employee IDs: {self.employees.keys()}")
        if not employee_id:
            messagebox.showerror("Error", "Please select an employee.")
            return
        if employee_id in self.time_logs and self.time_logs[employee_id].get('clock_in'):
            messagebox.showerror("Error", "Employee already clocked in.")
            return
        self.time_logs[employee_id] = {
            'name': self.employees[employee_id]['name'],
            'clock_in': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'sessions': self.time_logs.get(employee_id, {}).get('sessions', [])
        }
        save_time_logs(self.time_logs)
        self.status_var.set(f"{self.employees[employee_id]['name']} clocked in at {self.time_logs[employee_id]['clock_in']}.")

    def clock_out(self):
        employee_id = self.employee_id_var.get()
        if not employee_id or employee_id not in self.time_logs or not self.time_logs[employee_id].get('clock_in'):
            messagebox.showerror("Error", "Employee not clocked in.")
            return
        clock_out_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        hours = calculate_hours(self.time_logs[employee_id]['clock_in'], clock_out_time)
        self.time_logs[employee_id]['sessions'].append({
            'clock_in': self.time_logs[employee_id]['clock_in'],
            'clock_out': clock_out_time,
            'hours': hours
        })
        del self.time_logs[employee_id]['clock_in']
        save_time_logs(self.time_logs)
        self.status_var.set(f"{self.employees[employee_id]['name']} clocked out. Hours: {hours:.2f}.")

    def open_admin_panel(self):
        pin = simpledialog.askstring("Admin Login", "Enter PIN:", show='*')
        if pin and hashlib.sha256(pin.encode()).hexdigest() == ADMIN_PIN_HASH:
            self.show_admin_panel()
        else:
            messagebox.showerror("Error", "Invalid PIN.")

    def show_admin_panel(self):
        admin_window = tk.Toplevel(self.root)
        admin_window.title("Admin Panel")

        # Add employee
        tk.Label(admin_window, text="Add Employee").pack()
        tk.Label(admin_window, text="Employee ID:").pack()
        emp_id_entry = tk.Entry(admin_window)
        emp_id_entry.pack()
        tk.Label(admin_window, text="Name:").pack()
        name_entry = tk.Entry(admin_window)
        name_entry.pack()
        tk.Label(admin_window, text="Hourly Rate ($):").pack()
        rate_entry = tk.Entry(admin_window)
        rate_entry.pack()
        tk.Label(admin_window, text="SSN:").pack()
        ssn_entry = tk.Entry(admin_window)
        ssn_entry.pack()
        tk.Label(admin_window, text="Address:").pack()
        address_entry = tk.Entry(admin_window)
        address_entry.pack()
        tk.Button(admin_window, text="Save Employee", command=lambda: self.add_employee(
            emp_id_entry.get(), name_entry.get(), rate_entry.get(), ssn_entry.get(), address_entry.get())).pack(pady=5)

        # Manager override
        tk.Label(admin_window, text="Manager Override: Set Clock-In Time").pack()
        tk.Label(admin_window, text="Employee ID:").pack()
        override_id_entry = tk.Entry(admin_window)
        override_id_entry.pack()
        tk.Label(admin_window, text="Clock-In Time (YYYY-MM-DD HH:MM:SS):").pack()
        override_time_entry = tk.Entry(admin_window)
        override_time_entry.pack()
        tk.Button(admin_window, text="Set Clock-In", command=lambda: self.override_clock_in(
            override_id_entry.get(), override_time_entry.get())).pack(pady=5)

        # Run payroll
        tk.Button(admin_window, text="Run Payroll", command=self.run_payroll).pack(pady=5)

    def add_employee(self, emp_id, name, rate, ssn, address):
        try:
            if not all([emp_id, name, rate, ssn, address]):
                messagebox.showerror("Error", "All fields are required.")
                return
            rate = float(rate)
            if emp_id in self.employees:
                messagebox.showerror("Error", "Employee ID already exists.")
                return
            save_employee(emp_id, name, rate, ssn, address)
            self.employees = load_employees()
            print(f"[DEBUG] Employees after add: {self.employees}")
            self.employee_menu['menu'].delete(0, 'end')
            for emp_id_key in self.employees.keys():
                self.employee_menu['menu'].add_command(label=emp_id_key, command=tk._setit(self.employee_id_var, emp_id_key))
            self.employee_id_var.set(emp_id) # Set the newly added employee as selected
            messagebox.showinfo("Success", "Employee added.")
        except ValueError:
            messagebox.showerror("Error", "Invalid hourly rate.")

    def override_clock_in(self, emp_id, clock_in_time):
        if not emp_id or emp_id not in self.employees:
            messagebox.showerror("Error", "Invalid Employee ID.")
            return
        if emp_id in self.time_logs and self.time_logs[emp_id].get('clock_in'):
            messagebox.showerror("Error", "Employee already clocked in.")
            return
        try:
            datetime.datetime.strptime(clock_in_time, "%Y-%m-%d %H:%M:%S")
            self.time_logs[emp_id] = {
                'name': self.employees[emp_id]['name'],
                'clock_in': clock_in_time,
                'sessions': self.time_logs.get(emp_id, {}).get('sessions', []),
                'manager_override': True
            }
            save_time_logs(self.time_logs)
            messagebox.showinfo("Success", f"Clock-in time set to {clock_in_time} for {self.employees[emp_id]['name']}.")
        except ValueError:
            messagebox.showerror("Error", "Invalid time format. Use YYYY-MM-DD HH:MM:SS.")

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
        messagebox.showinfo("Payroll Complete", "Payroll report generated as payroll_report.csv.\nNote: Tax calculations are estimates; verify with a professional.")
