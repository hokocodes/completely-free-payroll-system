
import threading
from gui import PayrollApp
from server import run_server
import tkinter as tk
import logging

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

    # Start HTTP server in a thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Start GUI
    root = tk.Tk()
    app = PayrollApp(root)
    print("Desktop GUI launched. For mobile clock-in and management:")
    print("1. Download and install ngrok from https://ngrok.com (free tier).")
    print("2. Run: ngrok http 8000")
    print("3. Copy the ngrok URL (e.g., https://abc123.ngrok.io) and share with employees.")
    print("4. Access admin panel at https://<ngrok-url>/admin from your mobile browser.")
    print("5. Use manager override at https://<ngrok-url>/override to set clock-in times.")
    print("Employees must be within 100m of Freezy Frenzy (17458 Northwest Fwy, Jersey Village, TX).")
    print("Use PIN 1234 for clock-in/out, admin, and override (change in data.py if needed).")
    root.mainloop()
