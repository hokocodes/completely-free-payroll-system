import tkinter as tk
from tkinter import messagebox, simpledialog
from data import (
    load_employees,
    save_employee,
    load_time_logs,
    save_time_logs,
    ADMIN_PIN_HASH,
    edit_time_log_session,
)
from payrollutils import calculate_hours, calculate_pay_with_profile
import hashlib
import datetime
import csv
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from reportlab.lib import colors
import tkinter.ttk as ttk
import server

class PayrollApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Freezy Frenzy Payroll & Time Clock")
        self.employees = load_employees()
        self.time_logs = load_time_logs()
        # Load .env relative to project root to ensure variables are available
        try:
            this_dir = os.path.dirname(__file__)
            env_path = os.path.join(this_dir, ".env")
            load_dotenv(env_path, override=True)
        except Exception:
            load_dotenv()
        try:
            if not any(
                isinstance(h, RotatingFileHandler) for h in logging.getLogger().handlers
            ):
                file_handler = RotatingFileHandler(
                    "app.log", maxBytes=1_000_000, backupCount=3
                )
                file_handler.setLevel(logging.INFO)
                formatter = logging.Formatter(
                    "%(asctime)s %(levelname)s [%(name)s] %(message)s"
                )
                file_handler.setFormatter(formatter)
                logging.getLogger().addHandler(file_handler)
                logging.getLogger().setLevel(logging.INFO)
        except Exception:
            pass
        self.root = root
        self.root.title("Freezy Frenzy Payroll & Time Clock")
        self.employees = load_employees()
        self.time_logs = load_time_logs()

        # Main frame
        self.main_frame = tk.Frame(root)
        self.main_frame.pack(padx=10, pady=10)

        # Employee selection
        tk.Label(self.main_frame, text="Employee ID:").pack()
        self.employee_id_entry = tk.Entry(self.main_frame)
        self.employee_id_entry.pack()
        
        # PIN entry
        tk.Label(self.main_frame, text="PIN:").pack()
        self.pin_entry = tk.Entry(self.main_frame, show="*")
        self.pin_entry.pack()

        # Clock in/out buttons
        tk.Button(self.main_frame, text="Clock In", command=self.clock_in).pack(pady=5)
        tk.Button(self.main_frame, text="Clock Out", command=self.clock_out).pack(pady=5)
        tk.Button(self.main_frame, text="Admin Panel", command=self.open_admin_panel).pack(
            pady=5
        )

        # Status label
        self.status_var = tk.StringVar(
            value="Welcome! Enter your Employee ID and PIN to clock in/out."
        )
        tk.Label(self.main_frame, textvariable=self.status_var).pack(pady=10)

    def clock_in(self):
        employee_id = self.employee_id_entry.get()
        pin = self.pin_entry.get()
        
        if not employee_id or not pin:
            messagebox.showerror("Error", "Please enter both Employee ID and PIN.")
            return
            
        if employee_id not in self.employees:
            messagebox.showerror("Error", "Employee ID not found.")
            return
            
        if self.employees[employee_id].get('pin') != pin:
            messagebox.showerror("Error", "Invalid PIN.")
            return
            
        if employee_id in self.time_logs and self.time_logs[employee_id].get(
            "clock_in"
        ):
            messagebox.showerror("Error", "Employee already clocked in.")
            return
            
        self.time_logs[employee_id] = {
            "name": self.employees[employee_id]["name"],
            "clock_in": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sessions": self.time_logs.get(employee_id, {}).get("sessions", []),
        }
        save_time_logs(self.time_logs)
        self.status_var.set(
            f"{self.employees[employee_id]['name']} clocked in at {self.time_logs[employee_id]['clock_in']}."
        )
        # Clear PIN entry after successful clock in
        self.pin_entry.delete(0, tk.END)

    def clock_out(self):
        employee_id = self.employee_id_entry.get()
        pin = self.pin_entry.get()
        
        if not employee_id or not pin:
            messagebox.showerror("Error", "Please enter both Employee ID and PIN.")
            return
            
        if employee_id not in self.employees:
            messagebox.showerror("Error", "Employee ID not found.")
            return
            
        if self.employees[employee_id].get('pin') != pin:
            messagebox.showerror("Error", "Invalid PIN.")
            return
            
        if (
            not employee_id
            or employee_id not in self.time_logs
            or not self.time_logs[employee_id].get("clock_in")
        ):
            messagebox.showerror("Error", "Employee not clocked in.")
            return
        clock_out_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        hours = calculate_hours(self.time_logs[employee_id]["clock_in"], clock_out_time)
        self.time_logs[employee_id]["sessions"].append(
            {
                "clock_in": self.time_logs[employee_id]["clock_in"],
                "clock_out": clock_out_time,
                "hours": hours,
            }
        )
        del self.time_logs[employee_id]["clock_in"]
        save_time_logs(self.time_logs)
        self.status_var.set(
            f"{self.employees[employee_id]['name']} clocked out. Hours: {hours:.2f}."
        )
        # Clear PIN entry after successful clock out
        self.pin_entry.delete(0, tk.END)

    def open_admin_panel(self):
        pin = simpledialog.askstring("Admin Login", "Enter PIN:", show="*")
        if pin and hashlib.sha256(pin.encode()).hexdigest() == ADMIN_PIN_HASH:
            self.show_admin_panel()
        else:
            messagebox.showerror("Error", "Invalid PIN.")

    def show_admin_panel(self):
        admin_window = tk.Toplevel(self.root)
        admin_window.title("Admin Panel")

        notebook = ttk.Notebook(admin_window)
        notebook.pack(fill="both", expand=True)

        # Add Employee Tab
        add_employee_frame = tk.Frame(notebook)
        notebook.add(add_employee_frame, text="Add Employee")
        tk.Label(add_employee_frame, text="Add Employee").pack()
        tk.Label(add_employee_frame, text="Employee ID:").pack()
        emp_id_entry = tk.Entry(add_employee_frame)
        emp_id_entry.pack()
        tk.Label(add_employee_frame, text="Name:").pack()
        name_entry = tk.Entry(add_employee_frame)
        name_entry.pack()
        tk.Label(add_employee_frame, text="Hourly Rate ($):").pack()
        rate_entry = tk.Entry(add_employee_frame)
        rate_entry.pack()
        tk.Label(add_employee_frame, text="SSN:").pack()
        ssn_entry = tk.Entry(add_employee_frame)
        ssn_entry.pack()
        tk.Label(add_employee_frame, text="Address:").pack()
        address_entry = tk.Entry(add_employee_frame)
        address_entry.pack()
        tk.Label(add_employee_frame, text="Email:").pack()
        email_entry = tk.Entry(add_employee_frame)
        email_entry.pack()
        tk.Label(add_employee_frame, text="Visa Status:").pack()
        visa_entry = tk.Entry(add_employee_frame)
        visa_entry.pack()
        tk.Label(add_employee_frame, text="Nonresident Alien (yes/no):").pack()
        nra_entry = tk.Entry(add_employee_frame)
        nra_entry.pack()
        tk.Label(add_employee_frame, text="PIN (for clock in/out):").pack()
        pin_entry = tk.Entry(add_employee_frame, show="*")
        pin_entry.pack()
        tk.Button(
            add_employee_frame,
            text="Save Employee",
            command=lambda: self.add_employee(
                emp_id_entry.get(),
                name_entry.get(),
                rate_entry.get(),
                ssn_entry.get(),
                address_entry.get(),
                email_entry.get(),
                visa_entry.get(),
                nra_entry.get(),
                "",
                "",
                "",
                "",
                pin_entry.get(),
            ),
        ).pack(pady=5)

        # Edit Employee Tab
        edit_employee_frame = tk.Frame(notebook)
        notebook.add(edit_employee_frame, text="Edit Employee")
        tk.Label(edit_employee_frame, text="Employee ID:").pack()
        edit_emp_id_entry = tk.Entry(edit_employee_frame)
        edit_emp_id_entry.pack()
        tk.Label(edit_employee_frame, text="Name (leave blank to keep):").pack()
        edit_name_entry = tk.Entry(edit_employee_frame)
        edit_name_entry.pack()
        tk.Label(edit_employee_frame, text="Hourly Rate (leave blank to keep):").pack()
        edit_rate_entry = tk.Entry(edit_employee_frame)
        edit_rate_entry.pack()
        tk.Label(edit_employee_frame, text="SSN (leave blank to keep):").pack()
        edit_ssn_entry = tk.Entry(edit_employee_frame)
        edit_ssn_entry.pack()
        tk.Label(edit_employee_frame, text="Address (leave blank to keep):").pack()
        edit_address_entry = tk.Entry(edit_employee_frame)
        edit_address_entry.pack()
        tk.Label(edit_employee_frame, text="Email (leave blank to keep):").pack()
        edit_email_entry = tk.Entry(edit_employee_frame)
        edit_email_entry.pack()
        tk.Label(edit_employee_frame, text="Visa Status (leave blank to keep):").pack()
        edit_visa_entry = tk.Entry(edit_employee_frame)
        edit_visa_entry.pack()
        tk.Label(
            edit_employee_frame, text="Nonresident Alien yes/no (leave blank to keep):"
        ).pack()
        edit_nra_entry = tk.Entry(edit_employee_frame)
        edit_nra_entry.pack()
        tk.Label(edit_employee_frame, text="PIN (leave blank to keep):").pack()
        edit_pin_entry = tk.Entry(edit_employee_frame, show="*")
        edit_pin_entry.pack()
        tk.Button(
            edit_employee_frame,
            text="Update Employee",
            command=lambda: self.update_employee(
                edit_emp_id_entry.get(),
                edit_name_entry.get(),
                edit_rate_entry.get(),
                edit_ssn_entry.get(),
                edit_address_entry.get(),
                edit_email_entry.get(),
                edit_visa_entry.get(),
                edit_nra_entry.get(),
                edit_pin_entry.get(),
            ),
        ).pack(pady=5)
        
        # Store references to edit fields for easy access
        self.edit_fields = {
            'emp_id': edit_emp_id_entry,
            'name': edit_name_entry,
            'rate': edit_rate_entry,
            'ssn': edit_ssn_entry,
            'address': edit_address_entry,
            'email': edit_email_entry,
            'visa_status': edit_visa_entry,
            'nra': edit_nra_entry,
            'pin': edit_pin_entry
        }

        # Payment Method Tab
        payment_frame = tk.Frame(notebook)
        notebook.add(payment_frame, text="Payment Method")
        tk.Label(payment_frame, text="Employee ID:").pack()
        pay_emp_id_entry = tk.Entry(payment_frame)
        pay_emp_id_entry.pack()
        tk.Label(
            payment_frame, text="Payment Method (direct_deposit/payroll_card):"
        ).pack()
        pay_method_entry = tk.Entry(payment_frame)
        pay_method_entry.pack()
        tk.Label(payment_frame, text="Bank Routing #:").pack()
        pay_routing_entry = tk.Entry(payment_frame)
        pay_routing_entry.pack()
        tk.Label(payment_frame, text="Bank Account #:").pack()
        pay_account_entry = tk.Entry(payment_frame)
        pay_account_entry.pack()
        tk.Label(payment_frame, text="Payroll Card ID:").pack()
        pay_card_entry = tk.Entry(payment_frame)
        pay_card_entry.pack()
        tk.Button(
            payment_frame,
            text="Update Payment Method",
            command=lambda: self.update_payment_method(
                pay_emp_id_entry.get(),
                pay_method_entry.get(),
                pay_routing_entry.get(),
                pay_account_entry.get(),
                pay_card_entry.get(),
            ),
        ).pack(pady=5)

        # Manager Override Tab
        override_frame = tk.Frame(notebook)
        notebook.add(override_frame, text="Manager Override")
        tk.Label(override_frame, text="Manager Override: Set Clock-In Time").pack()
        tk.Label(override_frame, text="Employee ID:").pack()
        override_id_entry = tk.Entry(override_frame)
        override_id_entry.pack()
        tk.Label(override_frame, text="Clock-In Time (YYYY-MM-DD HH:MM:SS):").pack()
        override_time_entry = tk.Entry(override_frame)
        override_time_entry.pack()
        tk.Button(
            override_frame,
            text="Set Clock-In",
            command=lambda: self.override_clock_in(
                override_id_entry.get(), override_time_entry.get()
            ),
        ).pack(pady=5)
        tk.Label(override_frame, text="Manager Override: Set Clock-Out Time").pack()
        tk.Label(override_frame, text="Employee ID:").pack()
        override_out_id_entry = tk.Entry(override_frame)
        override_out_id_entry.pack()
        tk.Label(override_frame, text="Clock-Out Time (YYYY-MM-DD HH:MM:SS):").pack()
        override_out_time_entry = tk.Entry(override_frame)
        override_out_time_entry.pack()
        tk.Button(
            override_frame,
            text="Set Clock-Out",
            command=lambda: self.override_clock_out(
                override_out_id_entry.get(), override_out_time_entry.get()
            ),
        ).pack(pady=5)

        # Run Payroll Tab
        payroll_frame = tk.Frame(notebook)
        notebook.add(payroll_frame, text="Run Payroll")
        tk.Button(payroll_frame, text="Run Payroll", command=self.run_payroll).pack(
            pady=20
        )

        # View Employees Tab
        view_employees_frame = tk.Frame(notebook)
        notebook.add(view_employees_frame, text="View Employees")
        
        # Create Treeview for employees table
        columns = ("ID", "Name", "Hourly Rate", "SSN", "Address", "Email", "Visa Status", "Nonresident Alien", "PIN")
        employee_tree = ttk.Treeview(view_employees_frame, columns=columns, show="headings", height=15)
        
        # Set column headings
        for col in columns:
            employee_tree.heading(col, text=col)
            if col == "Address":
                employee_tree.column(col, width=200, minwidth=150)
            elif col == "PIN":
                employee_tree.column(col, width=80, minwidth=60)
            else:
                employee_tree.column(col, width=120, minwidth=100)
        
        # Add scrollbars
        v_scrollbar = ttk.Scrollbar(view_employees_frame, orient="vertical", command=employee_tree.yview)
        h_scrollbar = ttk.Scrollbar(view_employees_frame, orient="horizontal", command=employee_tree.xview)
        employee_tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        # Pack the treeview and scrollbars
        employee_tree.pack(side="left", fill="both", expand=True)
        v_scrollbar.pack(side="right", fill="y")
        h_scrollbar.pack(side="bottom", fill="x")
        
        # Store references to the tree and functions for later use
        self.employee_tree = employee_tree
        self.populate_employee_table_func = lambda: self.populate_employee_table()
        
        # Bind double-click to edit employee
        employee_tree.bind("<Double-1>", lambda event: self.populate_edit_fields_from_tree(employee_tree.selection()[0] if employee_tree.selection() else ""))
        
        # Bind right-click to show context menu
        employee_tree.bind("<Button-3>", self.show_context_menu_from_tree)
        
        # Debug: Print tree selection when it changes
        def debug_selection(event):
            selection = employee_tree.selection()
            print(f"[DEBUG] Tree selection changed: {selection}, type: {type(selection)}")
        employee_tree.bind("<<TreeviewSelect>>", debug_selection)
        
        # Populate table initially
        self.populate_employee_table()
        
        # Add refresh button
        refresh_button = tk.Button(view_employees_frame, text="Refresh Table", command=self.populate_employee_table)
        refresh_button.pack(pady=5)

        # View Time Logs Tab
        view_time_logs_frame = tk.Frame(notebook)
        notebook.add(view_time_logs_frame, text="View Time Logs")
        
        # Create Treeview for time logs table
        time_logs_columns = ("Employee ID", "Name", "Type", "Time", "Hours", "Location")
        time_logs_tree = ttk.Treeview(view_time_logs_frame, columns=time_logs_columns, show="headings", height=15)
        
        # Set column headings
        for col in time_logs_columns:
            time_logs_tree.heading(col, text=col)
            time_logs_tree.column(col, width=120)
        
        # Add scrollbars
        time_logs_v_scrollbar = ttk.Scrollbar(view_time_logs_frame, orient="vertical", command=time_logs_tree.yview)
        time_logs_h_scrollbar = ttk.Scrollbar(view_time_logs_frame, orient="horizontal", command=time_logs_tree.xview)
        time_logs_tree.configure(yscrollcommand=time_logs_v_scrollbar.set, xscrollcommand=time_logs_h_scrollbar.set)
        
        # Pack the treeview and scrollbars
        time_logs_tree.pack(side="left", fill="both", expand=True)
        time_logs_v_scrollbar.pack(side="right", fill="y")
        time_logs_h_scrollbar.pack(side="bottom", fill="x")
        
        # Store reference to the time logs tree
        self.time_logs_tree = time_logs_tree
        
        # Populate time logs table initially
        self.populate_time_logs_table()
        
        # Add refresh button
        time_logs_refresh_button = tk.Button(view_time_logs_frame, text="Refresh Table", command=self.populate_time_logs_table)
        time_logs_refresh_button.pack(pady=5)
        
        # Bind right-click to show context menu for time logs
        self.time_logs_tree.bind("<Button-3>", self.show_time_log_context_menu)

    def update_employee(
        self, emp_id, name, rate, ssn, address, email, visa_status, nra, pin
    ):
        if emp_id not in self.employees:
            messagebox.showerror("Error", "Employee ID not found.")
            return
        try:
            new_rate = float(rate) if rate else self.employees[emp_id]["hourly_rate"]
        except ValueError:
            messagebox.showerror("Error", "Invalid hourly rate.")
            return
        current = self.employees[emp_id]
        save_employee(
            emp_id,
            name or current["name"],
            new_rate,
            ssn or current["ssn"],
            address or current["address"],
            email or current.get("email", ""),
            visa_status or current.get("visa_status", ""),
            (nra or current.get("w4_nonresident_alien", "")),
            current.get("payment_method", ""),
            current.get("bank_routing", ""),
            current.get("bank_account", ""),
            current.get("payroll_card_id", ""),
            pin or current.get("pin", ""),
        )
        server.TimeClckHandler.employees = load_employees()
        messagebox.showinfo("Success", "Employee updated.")

    def update_payment_method(self, emp_id, method, routing, account, card_id):
        if emp_id not in self.employees:
            messagebox.showerror("Error", "Employee ID not found.")
            return
        current = self.employees[emp_id]
        save_employee(
            emp_id,
            current["name"],
            current["hourly_rate"],
            current["ssn"],
            current["address"],
            current.get("email", ""),
            current.get("visa_status", ""),
            current.get("w4_nonresident_alien", ""),
            method or current.get("payment_method", ""),
            routing or current.get("bank_routing", ""),
            account or current.get("bank_account", ""),
            card_id or current.get("payroll_card_id", ""),
        )
        self.employees = load_employees()
        messagebox.showinfo("Success", "Payment method updated.")

    def add_employee(
        self,
        emp_id,
        name,
        rate,
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
        try:
            if not all([emp_id, name, rate, ssn, address]):
                messagebox.showerror("Error", "All fields are required.")
                return
            rate = float(rate)
            if emp_id in self.employees:
                messagebox.showerror("Error", "Employee ID already exists.")
                return
            save_employee(
                emp_id,
                name,
                rate,
                ssn,
                address,
                email,
                visa_status,
                w4_nonresident_alien,
                payment_method,
                bank_routing,
                bank_account,
                payroll_card_id,
                pin,
            )
            self.employees = load_employees()
            print(f"[DEBUG] Employees after add: {self.employees}")
            # Update the employee menu if it exists (for backward compatibility)
            if hasattr(self, 'employee_menu'):
                self.employee_menu["menu"].delete(0, "end")
                for emp_id_key in self.employees.keys():
                    self.employee_menu["menu"].add_command(
                        label=emp_id_key,
                        command=tk._setit(self.employee_id_var, emp_id_key),
                    )
                self.employee_id_var.set(emp_id)  # Set the newly added employee as selected
            messagebox.showinfo("Success", "Employee added.")
        except ValueError:
            messagebox.showerror("Error", "Invalid hourly rate.")
    
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

    def populate_edit_fields_from_tree(self, emp_id):
        """Populate edit employee tab fields from tree selection"""
        print(f"[DEBUG] populate_edit_fields_from_tree called with emp_id: {emp_id}")
        print(f"[DEBUG] Available employee IDs: {list(self.employees.keys())}")
        print(f"[DEBUG] Employee ID type: {type(emp_id)}, Employees keys types: {[type(k) for k in self.employees.keys()]}")
        if emp_id in self.employees and hasattr(self, 'edit_fields'):
            print("[DEBUG] Employee found and edit_fields exist")
            emp_data = self.employees[emp_id]
            
            # Find the admin window and switch to edit tab
            for widget in self.root.winfo_children():
                if isinstance(widget, tk.Toplevel) and widget.title() == "Admin Panel":
                    print("[DEBUG] Found admin panel window")
                    # Find the notebook in the admin window
                    for child in widget.winfo_children():
                        if isinstance(child, ttk.Notebook):
                            print("[DEBUG] Found notebook, switching to edit tab")
                            # Switch to edit employee tab (index 1)
                            child.select(1)
                            break
                    break
            
            # Populate the fields using stored references
            self.edit_fields['emp_id'].delete(0, tk.END)
            self.edit_fields['emp_id'].insert(0, emp_id)
            self.edit_fields['name'].delete(0, tk.END)
            self.edit_fields['name'].insert(0, emp_data.get("name", ""))
            self.edit_fields['rate'].delete(0, tk.END)
            self.edit_fields['rate'].insert(0, str(emp_data.get("hourly_rate", "")))
            self.edit_fields['ssn'].delete(0, tk.END)
            self.edit_fields['ssn'].insert(0, emp_data.get("ssn", ""))
            self.edit_fields['address'].delete(0, tk.END)
            self.edit_fields['address'].insert(0, emp_data.get("address", ""))
            self.edit_fields['email'].delete(0, tk.END)
            self.edit_fields['email'].insert(0, emp_data.get("email", ""))
            self.edit_fields['visa_status'].delete(0, tk.END)
            self.edit_fields['visa_status'].insert(0, emp_data.get("visa_status", ""))
            self.edit_fields['nra'].delete(0, tk.END)
            self.edit_fields['nra'].insert(0, emp_data.get("w4_nonresident_alien", ""))
            self.edit_fields['pin'].delete(0, tk.END)
            self.edit_fields['pin'].insert(0, emp_data.get("pin", ""))
            print("[DEBUG] Fields populated successfully")
        else:
            print(f"[DEBUG] Employee not found or edit_fields don't exist. emp_id: {emp_id}, has_edit_fields: {hasattr(self, 'edit_fields')}")

    def delete_employee_from_tree(self, emp_id):
        """Delete employee from tree selection"""
        if emp_id in self.employees:
            emp_name = self.employees[emp_id]["name"]
            if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete employee {emp_name} (ID: {emp_id})?"):
                # Remove from employees
                del self.employees[emp_id]
                # Remove from time logs if exists
                if emp_id in self.time_logs:
                    del self.time_logs[emp_id]
                # Save changes
                self.save_all_employees()
                save_time_logs(self.time_logs)
                # Refresh the table
                self.populate_employee_table()
                messagebox.showinfo("Success", f"Employee {emp_name} has been deleted.")

    def show_context_menu_from_tree(self, event):
        """Show context menu for tree selection"""
        selection = self.employee_tree.selection()
        print(f"[DEBUG] Context menu triggered. Selection: {selection}")
        if selection:
            emp_id = selection[0]
            print(f"[DEBUG] Employee ID selected: {emp_id}")
            context_menu = tk.Menu(self.root, tearoff=0)
            context_menu.add_command(label="Edit Employee", command=lambda: self.populate_edit_fields_from_tree(emp_id))
            context_menu.add_command(label="Delete Employee", command=lambda: self.delete_employee_from_tree(emp_id))
            context_menu.tk_popup(event.x_root, event.y_root)
        else:
            print("[DEBUG] No selection found")

    def populate_employee_table(self):
        """Populate the employee table with current data"""
        print("[DEBUG] populate_employee_table called")
        print(f"[DEBUG] Available employees: {list(self.employees.keys())}")
        if hasattr(self, 'employee_tree'):
            # Clear existing items
            for item in self.employee_tree.get_children():
                self.employee_tree.delete(item)
            
            # Add employee data
            for emp_id, emp_data in self.employees.items():
                print(f"[DEBUG] Inserting employee: {emp_id}")
                item_id = self.employee_tree.insert("", "end", iid=emp_id, values=(
                    emp_id,
                    emp_data.get("name", ""),
                    f"${emp_data.get('hourly_rate', 0):.2f}",
                    emp_data.get("ssn", ""),
                    emp_data.get("address", "")[:50] + "..." if len(emp_data.get("address", "")) > 50 else emp_data.get("address", ""),
                    emp_data.get("email", ""),
                    emp_data.get("visa_status", ""),
                    emp_data.get("w4_nonresident_alien", ""),
                    emp_data.get("pin", "")
                ))
                print(f"[DEBUG] Item inserted with ID: {item_id}")
            print(f"[DEBUG] Tree children: {self.employee_tree.get_children()}")
        else:
            print("[DEBUG] employee_tree not found")

    def override_clock_in(self, emp_id, clock_in_time):
        if not emp_id or emp_id not in self.employees:
            messagebox.showerror("Error", "Invalid Employee ID.")
            return
        if emp_id in self.time_logs and self.time_logs[emp_id].get("clock_in"):
            messagebox.showerror("Error", "Employee already clocked in.")
            return
        try:
            datetime.datetime.strptime(clock_in_time, "%Y-%m-%d %H:%M:%S")
            self.time_logs[emp_id] = {
                "name": self.employees[emp_id]["name"],
                "clock_in": clock_in_time,
                "sessions": self.time_logs.get(emp_id, {}).get("sessions", []),
                "manager_override": True,
            }
            save_time_logs(self.time_logs)
            self.time_logs = load_time_logs() # Reload time logs after saving
            messagebox.showinfo(
                "Success",
                f"Clock-in time set to {clock_in_time} for {self.employees[emp_id]['name']}.",
            )
        except ValueError:
            messagebox.showerror(
                "Error", "Invalid time format. Use YYYY-MM-DD HH:MM:SS."
            )

    def override_clock_out(self, emp_id, clock_out_time):
        if not emp_id or emp_id not in self.employees:
            messagebox.showerror("Error", "Invalid Employee ID.")
            return
        if emp_id not in self.time_logs or not self.time_logs[emp_id].get("clock_in"):
            messagebox.showerror("Error", "Employee not clocked in.")
            return
        try:
            datetime.datetime.strptime(clock_out_time, "%Y-%m-%d %H:%M:%S")
            clock_in_time = self.time_logs[emp_id]["clock_in"]
            hours = calculate_hours(clock_in_time, clock_out_time)
            self.time_logs[emp_id]["sessions"].append(
                {
                    "clock_in": clock_in_time,
                    "clock_out": clock_out_time,
                    "hours": hours,
                    "manager_override": True,
                }
            )
            del self.time_logs[emp_id]["clock_in"]
            save_time_logs(self.time_logs)
            self.time_logs = load_time_logs() # Reload time logs after saving
            messagebox.showinfo(
                "Success",
                f"Clock-out time set to {clock_out_time} for {self.employees[emp_id]['name']}. Hours: {hours:.2f}",
            )
        except ValueError:
            messagebox.showerror(
                "Error", "Invalid time format. Use YYYY-MM-DD HH:MM:SS."
            )

    def run_payroll(self):
        pay_period_start = (
            datetime.datetime.now() - datetime.timedelta(days=14)
        ).strftime("%Y-%m-%d")
        report = [
            "Payroll Report",
            f"Pay Period: {pay_period_start} to {datetime.datetime.now().strftime('%Y-%m-%d')}\n",
        ]
        payments = [
            ["employee_id", "name", "method", "routing", "account", "amount", "date"]
        ]
        tax_deposits = [["date", "federal_withholding_total"]]
        total_federal = 0.0
        os.makedirs("paystubs", exist_ok=True)
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        for emp_id, data in self.time_logs.items():
            if "sessions" not in data:
                continue
            total_hours = sum(
                session["hours"]
                for session in data["sessions"]
                if session["clock_out"] >= pay_period_start
            )
            if total_hours == 0:
                continue
            is_nra = str(
                self.employees[emp_id].get("w4_nonresident_alien", "")
            ).lower() in ["yes", "true", "1"]
            rate = self.employees[emp_id]["hourly_rate"]
            gross, federal_tax, state_tax, net_pay = calculate_pay_with_profile(
                total_hours, rate, is_nra
            )
            report.append(f"Employee: {data['name']} (ID: {emp_id})")
            report.append(f"SSN: {self.employees[emp_id]['ssn']}")
            report.append(f"Address: {self.employees[emp_id]['address']}")
            report.append(f"Total Hours: {total_hours:.2f}")
            report.append(f"Gross Pay: ${gross:.2f}")
            report.append(f"Federal Tax: ${federal_tax:.2f}")
            report.append(f"State Tax: ${state_tax:.2f}")
            report.append(f"Net Pay: ${net_pay:.2f}\n")

            total_federal += federal_tax
            method = self.employees[emp_id].get("payment_method", "") or "payroll_card"
            routing = self.employees[emp_id].get("bank_routing", "")
            account = self.employees[emp_id].get("bank_account", "")
            payroll_card_id = self.employees[emp_id].get("payroll_card_id", "")
            routing_mask = (routing[-4:]).rjust(len(routing), "•") if routing else ""
            account_mask = (
                (account[-4:]).rjust(len(account), "•") if account else payroll_card_id
            )
            payments.append(
                [
                    emp_id,
                    data["name"],
                    method,
                    routing_mask,
                    account_mask,
                    f"{net_pay:.2f}",
                    today,
                ]
            )

            email_addr = self.employees[emp_id].get("email", "")
            stub_path = os.path.join("paystubs", f"{emp_id}_{today}.html")
            with open(stub_path, "w", encoding="utf-8") as sf:
                sf.write(f"""
                <html><body>
                <h3>Paystub - {today}</h3>
                <p>Employee: {data['name']} (ID: {emp_id})</p>
                <p>Total Hours: {total_hours:.2f}</p>
                <p>Hourly Rate: ${rate:.2f}</p>
                <p>Gross Pay: ${gross:.2f}</p>
                <p>Federal Tax: ${federal_tax:.2f}</p>
                <p>State Tax: ${state_tax:.2f}</p>
                <p>Net Pay: ${net_pay:.2f}</p>
                <p>Payment Method: {method}</p>
                </body></html>
                """)

            # PDF paystub (styled)
            pdf_path = os.path.join("paystubs", f"{emp_id}_{today}.pdf")
            c = canvas.Canvas(pdf_path, pagesize=LETTER)
            width, height = LETTER
            margin = 54

            # Outer border removed for cleaner spacing

            header_h = 70
            c.setFillColor(colors.HexColor("#2E3A59"))
            c.roundRect(
                margin,
                height - margin - header_h,
                width - 2 * margin,
                header_h,
                12,
                stroke=0,
                fill=1,
            )
            c.setFillColor(colors.white)
            company_name = "Freezy Frenzy"
            company_address = "17458 Northwest Fwy, Jersey Village, TX 77040"
            c.setFont("Helvetica-Bold", 20)
            c.drawString(margin + 16, height - margin - 40, f"{company_name}")
            c.setFont("Helvetica", 10)
            c.drawString(margin + 16, height - margin - 56, company_address)
            c.setFont("Helvetica", 12)
            c.drawRightString(
                width - margin - 16, height - margin - 46, f"Paystub • {today}"
            )

            content_top = height - margin - header_h - 12

            col_gap = 12
            col_w = (width - 2 * margin - col_gap) / 2
            box_h = 100
            c.setStrokeColor(colors.HexColor("#8792B0"))
            c.roundRect(margin, content_top - box_h, col_w, box_h, 8, stroke=1, fill=0)
            c.setFillColor(colors.HexColor("#2E3A59"))
            c.setFont("Helvetica-Bold", 11)
            c.drawString(margin + 10, content_top - 18, "Employee")
            c.setFillColor(colors.black)
            c.setFont("Helvetica", 10)
            c.drawString(margin + 10, content_top - 36, f"Name: {data['name']}")
            c.drawString(margin + 10, content_top - 52, f"Employee ID: {emp_id}")
            addr = self.employees[emp_id].get("address", "") or ""
            parts = [
                p.strip() for p in addr.replace("\n", ", ").split(",") if p.strip()
            ]
            if len(parts) >= 3:
                addr_line1 = ", ".join(parts[:-2])
                addr_line2 = ", ".join(parts[-2:])
            elif len(parts) == 2:
                addr_line1 = parts[0]
                addr_line2 = parts[1]
            else:
                words = addr.split()
                split_index = max(1, min(len(words), len(words) // 2))
                addr_line1 = " ".join(words[:split_index])
                addr_line2 = " ".join(words[split_index:])
            c.drawString(margin + 10, content_top - 68, "Address:")
            c.drawString(margin + 70, content_top - 68, addr_line1)
            if addr_line2:
                c.drawString(margin + 70, content_top - 84, addr_line2)

            c.roundRect(
                margin + col_w + col_gap,
                content_top - box_h,
                col_w,
                box_h,
                8,
                stroke=1,
                fill=0,
            )
            c.setFillColor(colors.HexColor("#2E3A59"))
            c.setFont("Helvetica-Bold", 11)
            c.drawString(margin + col_w + col_gap + 10, content_top - 18, "Pay Period")
            c.setFillColor(colors.black)
            c.setFont("Helvetica", 10)
            c.drawString(
                margin + col_w + col_gap + 10,
                content_top - 36,
                f"Start: {pay_period_start}",
            )
            c.drawString(
                margin + col_w + col_gap + 10, content_top - 52, f"End: {today}"
            )

            earnings_top = content_top - box_h - 16
            earnings_h = 180
            c.setStrokeColor(colors.HexColor("#8792B0"))
            c.roundRect(
                margin,
                earnings_top - earnings_h,
                width - 2 * margin,
                earnings_h,
                8,
                stroke=1,
                fill=0,
            )
            c.setFillColor(colors.HexColor("#2E3A59"))
            c.setFont("Helvetica-Bold", 11)
            c.drawString(margin + 10, earnings_top - 18, "Earnings & Deductions")
            c.setFillColor(colors.black)
            c.setFont("Helvetica", 10)

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
            row("Hourly Rate", f"${rate:.2f}")
            row("Gross Pay", f"${gross:.2f}")
            row("Federal Tax", f"${federal_tax:.2f}")
            row("State Tax", f"${state_tax:.2f}")

            net_box_h = 70
            net_box_y = margin + 30
            c.setStrokeColor(colors.HexColor("#2E3A59"))
            c.roundRect(
                margin, net_box_y, width - 2 * margin, net_box_h, 10, stroke=1, fill=0
            )
            c.setFont("Helvetica-Bold", 12)
            c.setFillColor(colors.HexColor("#2E3A59"))
            c.drawString(margin + 16, net_box_y + net_box_h - 24, "Net Pay")
            c.setFillColor(colors.black)
            c.setFont("Helvetica-Bold", 18)
            c.drawRightString(
                width - margin - 16, net_box_y + net_box_h - 28, f"${net_pay:.2f}"
            )

            c.setFont("Helvetica", 8)
            c.setFillColor(colors.HexColor("#666666"))
            c.drawCentredString(
                width / 2, margin + 10, "This is a computer-generated paystub."
            )

            c.showPage()
            c.save()

            try:
                print("Reading SMTP_HOST from environment")
                smtp_host = 'smtp.gmail.com'
                print("SMTP_HOST: {}".format(smtp_host))

                print("Reading SMTP_PORT from environment")
                smtp_port = int(os.getenv("SMTP_PORT", "0") or 0)
                print("SMTP_PORT: {}".format(smtp_port))

                print("Reading SMTP_USER from environment")
                smtp_user = os.getenv("SMTP_USER")
                print("SMTP_USER: {}".format(smtp_user))

                print("Reading SMTP_PASS from environment")
                smtp_pass = os.getenv("SMTP_PASS")
                print("SMTP_PASS: {}".format('***' if smtp_pass else None))

                print("Reading FROM_EMAIL from environment or using SMTP_USER")
                from_email = os.getenv("FROM_EMAIL") or smtp_user
                print("FROM_EMAIL: {}".format(from_email))

                print("Reading SMTP_USE_SSL from environment")
                smtp_use_ssl = str(os.getenv("SMTP_USE_SSL", "true")).lower() in [
                    "1",
                    "true",
                    "yes",
                ]
                print("SMTP_USE_SSL: {}".format(smtp_use_ssl))

                print("Reading SMTP_USE_STARTTLS from environment")
                smtp_use_starttls = str(
                    os.getenv("SMTP_USE_STARTTLS", "false")
                ).lower() in ["1", "true", "yes"]
                print("SMTP_USE_STARTTLS: {}".format(smtp_use_starttls))

                print("Checking if all SMTP and email parameters are present")
                if (
                    smtp_host
                    and smtp_port
                    and smtp_user
                    and smtp_pass
                    and from_email
                    and email_addr
                ):
                    logging.info(
                        f"SMTP attempt host={smtp_host} port={smtp_port} ssl={smtp_use_ssl} starttls={smtp_use_starttls} from={from_email} to={email_addr}"
                    )

                    logging.debug(f"Opening HTML paystub at {stub_path} for reading")
                    with open(stub_path, "r", encoding="utf-8") as f:
                        html_content = f.read()
                        logging.debug("Read HTML content for paystub email")

                    logging.debug("Creating MIMEMultipart message for paystub email")
                    msg = MIMEMultipart("alternative")
                    msg["Subject"] = f"Paystub - {today}"
                    logging.debug(f"Set email subject: Paystub - {today}")
                    msg["From"] = from_email
                    logging.debug(f"Set email from: {from_email}")
                    msg["To"] = email_addr
                    logging.debug(f"Set email to: {email_addr}")

                    logging.debug("Attaching HTML content to email")
                    part = MIMEText(html_content, "html")
                    msg.attach(part)

                    if smtp_use_ssl:
                        logging.info("Using SMTP_SSL for sending paystub email")
                        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
                            logging.debug("Logging in to SMTP server with SSL")
                            server.login(smtp_user, smtp_pass)
                            logging.debug("Sending email via SMTP_SSL")
                            server.sendmail(from_email, [email_addr], msg.as_string())
                    else:
                        logging.info("Using SMTP (non-SSL) for sending paystub email")
                        with smtplib.SMTP(smtp_host, smtp_port) as server:
                            if smtp_use_starttls:
                                logging.debug("Starting TLS for SMTP connection")
                                server.starttls()
                            logging.debug("Logging in to SMTP server")
                            server.login(smtp_user, smtp_pass)
                            logging.debug("Sending email via SMTP")
                            server.sendmail(from_email, [email_addr], msg.as_string())
                    logging.info(f"SMTP sent paystub to {email_addr}")
                else:
                    logging.warning(
                        "SMTP not configured or recipient email missing; skipping send"
                    )
            except Exception as e:
                logging.error(f"Failed to send paystub email to {email_addr}: {e}")

        with open("payroll_report.csv", "w", newline="") as f:
            writer = csv.writer(f)
            for line in report:
                writer.writerow([line])
        with open("payments.csv", "w", newline="") as pf:
            writer = csv.writer(pf)
            writer.writerows(payments)
        with open("tax_deposit.csv", "w", newline="") as tf:
            tf_writer = csv.writer(tf)
            tax_deposits.append([today, f"{total_federal:.2f}"])
            tf_writer.writerows(tax_deposits)
        with open("w2_summary.csv", "w", newline="") as wf:
            w = csv.writer(wf)
            w.writerow(
                [
                    "employee_id",
                    "name",
                    "ssn",
                    "wages",
                    "federal_income_tax_withheld",
                    "year",
                ]
            )
            year = datetime.datetime.now().strftime("%Y")
            for emp_id, data in self.time_logs.items():
                if "sessions" not in data:
                    continue
                hours_ytd = 0
                for s in data["sessions"]:
                    if s.get("clock_out", "").startswith(year):
                        hours_ytd += s.get("hours", 0)
                if hours_ytd == 0:
                    continue
                is_nra = str(
                    self.employees[emp_id].get("w4_nonresident_alien", "")
                ).lower() in ["yes", "true", "1"]
                gross, fed, state, net = calculate_pay_with_profile(
                    hours_ytd, self.employees[emp_id]["hourly_rate"], is_nra
                )
                w.writerow(
                    [
                        emp_id,
                        data["name"],
                        self.employees[emp_id]["ssn"],
                        f"{gross:.2f}",
                        f"{fed:.2f}",
                        year,
                    ]
                )
        messagebox.showinfo(
            "Payroll Complete",
            "Payroll report generated as payroll_report.csv. Payments/taxes CSVs and paystubs created. Email sent if configured.",
        )

    def populate_time_logs_table(self):
        """Populate the time logs table with all clock-ins and clock-outs"""
        # Clear existing items
        self.time_logs_tree.delete(*self.time_logs_tree.get_children())
        
        # Get current time logs
        current_time_logs = load_time_logs()
        
        # Add current clock-ins
        for emp_id, data in current_time_logs.items():
            if 'clock_in' in data:
                # Current clock-in
                location_info = ""
                if 'last_location' in data:
                    lat = data['last_location'].get('lat', '')
                    lon = data['last_location'].get('lon', '')
                    if lat and lon:
                        location_info = f"Lat: {lat:.4f}, Lon: {lon:.4f}"
                
                self.time_logs_tree.insert("", "end", iid=f"{emp_id}_active", values=(
                    emp_id,
                    data.get('name', ''),
                    'Clock In',
                    data['clock_in'],
                    'Active',
                    location_info
                ))
            
            # Add completed sessions
            if 'sessions' in data:
                for idx, session in enumerate(data['sessions']):
                    location_info = ""
                    if 'location' in session:
                        lat = session['location'].get('lat', '')
                        lon = session['location'].get('lon', '')
                        if lat and lon:
                            location_info = f"Lat: {lat:.4f}, Lon: {lon:.4f}"
                    
                    # Clock-in entry
                    self.time_logs_tree.insert("", "end", iid=f"{emp_id}_{idx}_in", values=(
                        emp_id,
                        data.get('name', ''),
                        'Clock In',
                        session['clock_in'],
                        f"{session['hours']:.2f}",
                        location_info,
                        idx # Store index for editing
                    ))
                    
                    # Clock-out entry
                    self.time_logs_tree.insert("", "end", iid=f"{emp_id}_{idx}_out", values=(
                        emp_id,
                        data.get('name', ''),
                        'Clock Out',
                        session['clock_out'],
                        f"{session['hours']:.2f}",
                        location_info,
                        idx # Store index for editing
                    ))

    def show_time_log_context_menu(self, event):
        """Show context menu for time log selection"""
        selected_item = self.time_logs_tree.focus()
        if selected_item:
            item_values = self.time_logs_tree.item(selected_item, 'values')
            if item_values:
                emp_id = item_values[0]
                session_index = item_values[6] if len(item_values) > 6 else None

                context_menu = tk.Menu(self.root, tearoff=0)
                if session_index is not None:
                    context_menu.add_command(label="Edit Time Log", command=lambda: self.edit_time_log_entry(emp_id, int(session_index)))
                context_menu.tk_popup(event.x_root, event.y_root)

    def edit_time_log_entry(self, emp_id, session_index):
        """Opens a dialog to edit a specific time log entry."""
        logs = load_time_logs()
        if emp_id not in logs or 'sessions' not in logs[emp_id] or not (0 <= session_index < len(logs[emp_id]['sessions'])):
            messagebox.showerror("Error", "Time log entry not found.")
            return

        session = logs[emp_id]['sessions'][session_index]
        current_clock_in = session['clock_in']
        current_clock_out = session['clock_out']

        edit_window = tk.Toplevel(self.root)
        edit_window.title("Edit Time Log Entry")

        tk.Label(edit_window, text=f"Employee ID: {emp_id}").pack(pady=5)
        tk.Label(edit_window, text=f"Session Index: {session_index}").pack(pady=5)

        tk.Label(edit_window, text="New Clock-In Time (YYYY-MM-DD HH:MM:SS):").pack(pady=5)
        new_clock_in_entry = tk.Entry(edit_window, width=30)
        new_clock_in_entry.insert(0, current_clock_in)
        new_clock_in_entry.pack(pady=5)

        tk.Label(edit_window, text="New Clock-Out Time (YYYY-MM-DD HH:MM:SS):").pack(pady=5)
        new_clock_out_entry = tk.Entry(edit_window, width=30)
        new_clock_out_entry.insert(0, current_clock_out)
        new_clock_out_entry.pack(pady=5)

        def save_edits():
            updated_clock_in = new_clock_in_entry.get()
            updated_clock_out = new_clock_out_entry.get()
            
            if not updated_clock_in or not updated_clock_out:
                messagebox.showerror("Error", "Both clock-in and clock-out times are required.")
                return

            try:
                datetime.datetime.strptime(updated_clock_in, "%Y-%m-%d %H:%M:%S")
                datetime.datetime.strptime(updated_clock_out, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                messagebox.showerror("Error", "Invalid time format. Use YYYY-MM-DD HH:MM:SS.")
                return
            
            if edit_time_log_session(emp_id, session_index, updated_clock_in, updated_clock_out):
                messagebox.showinfo("Success", "Time log updated successfully.")
                self.populate_time_logs_table() # Refresh the table
                edit_window.destroy()
            else:
                messagebox.showerror("Error", "Failed to update time log.")

        tk.Button(edit_window, text="Save Changes", command=save_edits).pack(pady=10)
        tk.Button(edit_window, text="Cancel", command=edit_window.destroy).pack(pady=5)
