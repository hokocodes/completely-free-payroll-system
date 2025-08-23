
import datetime
import math

# Shop location (Freezy Frenzy: 17458 Northwest Fwy, Jersey Village, TX 77040)
SHOP_LAT = 29.8814  # Latitude
SHOP_LON = -95.5693  # Longitude
ALLOWED_RADIUS_METERS = 100  # Allow clock-in/out within 100 meters

def calculate_hours(clock_in, clock_out):
    in_time = datetime.datetime.strptime(clock_in, "%Y-%m-%d %H:%M:%S")
    out_time = datetime.datetime.strptime(clock_out, "%Y-%m-%d %H:%M:%S")
    return (out_time - in_time).total_seconds() / 3600

def calculate_pay(hours, hourly_rate):
    gross = hours * hourly_rate
    federal_tax = gross * 0.15  # 15% federal tax estimate
    state_tax = 0  # No state income tax in Texas
    net_pay = gross - federal_tax
    return gross, federal_tax, state_tax, net_pay

def calculate_pay_with_profile(hours, hourly_rate, is_nonresident_alien=False):
    gross, federal_tax, state_tax, net_pay = calculate_pay(hours, hourly_rate)
    if is_nonresident_alien:
        # Simplified placeholder: 30% federal withholding for NRAs
        federal_tax = gross * 0.30
        net_pay = gross - federal_tax
    return gross, federal_tax, state_tax, net_pay

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c  # Distance in meters
