import requests
from datetime import datetime, timezone

# ====================== CONFIGURATION (EDIT HERE) ======================
API_KEY = "7a99c2df5d4c4f32870115238261004"                    # ← Put your WeatherAPI key here
CITY = "Seoul"
CACHE_DURATION_SECONDS = 900    # 15 minutes (weather refresh interval)
# =======================================================================

# In-memory cache (no files, no folders)
cache = {"data": None, "timestamp": 0}

# ==================== INDEPENDENT SYSTEM TIME (12H AM/PM) ====================
def get_time():
    """Completely independent - uses your PC's local time"""
    try:
        now = datetime.now()
        time_str = now.strftime("%I:%M %p")
        # Remove leading zero (7:58 PM instead of 07:58 PM)
        if time_str.startswith("0"):
            time_str = time_str[1:]
        return time_str
    except Exception:
        return datetime.now().strftime("%I:%M %p")

# ---------------------------
# Weather Fetch (15 min cache, in memory only)
# ---------------------------
def fetch_weather_data():
    try:
        if not API_KEY:
            return None

        current_time = datetime.now(timezone.utc).timestamp()

        # Use cached data if still fresh
        if cache["data"] and (current_time - cache["timestamp"]) < CACHE_DURATION_SECONDS:
            return cache["data"]

        url = "https://api.weatherapi.com/v1/current.json"
        params = {"key": API_KEY, "q": CITY, "aqi": "no"}

        resp = requests.get(url, params=params, timeout=(5, 10))
        resp.raise_for_status()
        data = resp.json()

        if isinstance(data, dict) and "error" in data:
            return cache["data"]   # return old cache on error

        # Update cache
        cache["data"] = data
        cache["timestamp"] = current_time
        return data

    except Exception:
        return cache["data"]   # return old cache on any error

# ---------------------------
# Getters for Discord Rich Presence
# ---------------------------
def get_weather_temp():
    data = fetch_weather_data()
    if not data or "current" not in data:
        return "N/A"
    raw_temp = data["current"].get("temp_c")
    if raw_temp is None:
        return "N/A"
    temp = int(round(raw_temp))
    return f"{temp}°C"

def get_city():
    return CITY

def get_weather_state():
    data = fetch_weather_data()
    if data and "current" in data:
        return data["current"]["condition"]["text"].lower()
    return "unknown"

def get_weather_icon():
    data = fetch_weather_data()
    if data and "current" in data:
        icon_url = data["current"]["condition"].get("icon")
        if icon_url:
            if icon_url.startswith("//"):
                icon_url = "https:" + icon_url
            return icon_url.replace("64x64", "128x128")
    return ""

# Register dynamic values
addDRPCValue("weatherTemp", get_weather_temp)
addDRPCValue("city", get_city)
addDRPCValue("time", get_time)
addDRPCValue("weatherState", get_weather_state)
addDRPCValue("weathericon", get_weather_icon)

print("NightyWeather running (Seoul + Auto Time)")