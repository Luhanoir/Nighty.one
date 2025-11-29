import webbrowser
import time
from datetime import datetime, timezone, timedelta
import os
import json
import requests
import re
import urllib.parse

def NightyWeather():
    RETRIES = 3
    IMAGE_URL = "https://i.imgur.com/m0xu9yk.gif"
    SCRIPT_DATA_DIR = f"{getScriptsPath()}/scriptData"
    CONFIG_PATH = f"{SCRIPT_DATA_DIR}/NightyWeather.json"
    CACHE_PATH = f"{SCRIPT_DATA_DIR}/NightyWeatherCache.json"
    os.makedirs(SCRIPT_DATA_DIR, exist_ok=True)

    class Settings:
        defaults = {
            "api_key": "", "city": "", "utc_offset": 0.0,
            "time_format": "12", "temp_unit": "C", "temp_precision": "int",
            "cache_duration": 300, "show_date": False
        }

        def __init__(self):
            self.data = self.load() or self.defaults.copy()
            for key, val in self.defaults.items():
                if key not in self.data:
                    self.data[key] = val
            self.save()

        def load(self):
            if not os.path.exists(CONFIG_PATH):
                return None
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, Exception):
                print("Corrupted config. Resetting to defaults.", type="ERROR")
                return None

        def save(self):
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)

        def get(self, key):
            return self.data.get(key)

        def update(self, key, value):
            self.data[key] = value
            self.save()

    class Cache:
        def __init__(self):
            self.data = self.load()

        def load(self):
            if not os.path.exists(CACHE_PATH):
                return {"data": None, "timestamp": 0}
            try:
                with open(CACHE_PATH, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                    if not isinstance(cache.get("timestamp"), (int, float)):
                        return {"data": None, "timestamp": 0}
                    return cache
            except (json.JSONDecodeError, Exception):
                return {"data": None, "timestamp": 0}

        def save(self):
            with open(CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)

    settings = Settings()
    cache = Cache()

    def reset_cache():
        cache.data["data"] = None
        cache.data["timestamp"] = 0
        cache.save()

    def update_api_key(value):
        settings.update("api_key", value.strip())
        reset_cache()
        print("API key updated! Weather will refresh shortly.", type="SUCCESS")

    def update_city(value):
        value = value.strip()
        if value and len(value) <= 100 and re.match(r"^[\w\s\-\,\.\u00C0-\u017F]+$", value):
            settings.update("city", value)
            reset_cache()
            print("City updated! Refreshing weather...", type="SUCCESS")
        else:
            print("Invalid city name. Use letters, spaces, commas, hyphens only.", type="ERROR")

    def update_utc_offset(selected):
        try:
            offset = float(selected[0])
            if -14 <= offset <= 14:
                settings.update("utc_offset", offset)
                print("UTC offset updated!", type="SUCCESS")
            else:
                print("Offset must be between -14 and +14.", type="ERROR")
        except:
            print("Invalid UTC offset.", type="ERROR")

    def update_time_format(selected):
        settings.update("time_format", selected[0])
        print("Time format changed!", type="SUCCESS")

    def update_temp_unit(selected):
        settings.update("temp_unit", selected[0])
        print("Temperature unit updated!", type="SUCCESS")

    def update_temp_precision(selected):
        settings.update("temp_precision", selected[0])
        print("Temperature precision updated!", type="SUCCESS")

    def update_cache_mode(selected):
        mode_map = {"5min": 300, "15min": 900, "30min": 1800, "60min": 3600}
        duration = mode_map.get(selected[0], 300)
        settings.update("cache_duration", duration)
        reset_cache()
        print(f"Cache mode → {selected[0]}", type="SUCCESS")

    def update_show_date(selected):
        settings.update("show_date", selected[0] == "yes")
        print("Date display toggled!", type="SUCCESS")

    # Early exit helpers
    def config_missing():
        return not settings.get("api_key") or not settings.get("city")

    # UTC offset list
    utc_offsets = [-12, -11, -10, -9.5, -9, -8, -7, -6, -5, -4.5, -4, -3.5, -3, -2, -1,
                   0, 1, 2, 3, 3.5, 4, 4.5, 5, 5.5, 5.75, 6, 6.5, 7, 8, 8.5, 9, 9.5,
                   10, 10.5, 11, 12, 12.75, 13, 14]
    offset_items = [
        {"id": str(off), "title": f"UTC{'-' if off < 0 else '+'}{abs(int(off)):02d}:{int((abs(off) % 1) * 60):02d}"}
        for off in utc_offsets
    ]

    cache_modes = [
        {"id": "5min", "title": "Every 5 Min"},
        {"id": "15min", "title": "Every 15 Min"},
        {"id": "30min", "title": "Every 30 Min"},
        {"id": "60min", "title": "Every 60 Min"}
    ]
    mode_reverse = {300: "5min", 900: "15min", 1800: "30min", 3600: "60min"}
    selected_mode = mode_reverse.get(settings.get("cache_duration"), "5min")

    # UI
    tab = Tab(name="NightyWeather", title="Weather & Time", icon="sun")
    container = tab.create_container(type="rows")
    card = container.create_card(height="full", width="full", gap=3)

    try:
        card.create_ui_element(UI.Image, url=IMAGE_URL, width="100%", height="200px",
                               rounded="md", fill_type="contain", border_color="#4B5EAA",
                               border_width=2, margin="m-2", shadow=True)
    except:
        card.create_ui_element(UI.Text, content="Weather Showcase", full_width=True, style="heading")

    card.create_ui_element(UI.Input, label="API Key", placeholder="Enter your WeatherAPI.com key",
                           show_clear_button=True, full_width=True, required=True,
                           onInput=update_api_key, value=settings.get("api_key"), is_secure=True)

    card.create_ui_element(UI.Input, label="City", placeholder="e.g. Paris, Tokyo, New York",
                           show_clear_button=True, full_width=True, required=True,
                           onInput=update_city, value=settings.get("city"))

    card.create_ui_element(UI.Select, label="UTC Offset", full_width=True, mode="single",
                           items=offset_items, selected_items=[str(settings.get("utc_offset"))],
                           onChange=update_utc_offset)

    card.create_ui_element(UI.Select, label="Time Format", full_width=True, mode="single", items=[
        {"id": "12", "title": "12-hour (7:58 PM)"},
        {"id": "12s", "title": "12-hour + seconds (7:58:23 PM)"},
        {"id": "24", "title": "24-hour (19:58)"},
        {"id": "24s", "title": "24-hour + seconds (19:58:23)"}
    ], selected_items=[settings.get("time_format")], onChange=update_time_format)

    card.create_ui_element(UI.Select, label="Temperature Unit", full_width=True, mode="single", items=[
        {"id": "C", "title": "Celsius (°C)"},
        {"id": "F", "title": "Fahrenheit (°F)"}
    ], selected_items=[settings.get("temp_unit")], onChange=update_temp_unit)

    card.create_ui_element(UI.Select, label="Precision", full_width=True, mode="single", items=[
        {"id": "int", "title": "Whole number (22°)"},
        {"id": "1dec", "title": "One decimal (22.4°)"}
    ], selected_items=[settings.get("temp_precision")], onChange=update_temp_precision)

    card.create_ui_element(UI.Select, label="Refresh Cache", full_width=True, mode="single",
                           items=cache_modes, selected_items=[selected_mode], onChange=update_cache_mode)

    card.create_ui_element(UI.Select, label="Show Date", full_width=True, mode="single", items=[
        {"id": "yes", "title": "Yes (7:58 PM - Oct 22)"},
        {"id": "no", "title": "No"}
    ], selected_items=["yes" if settings.get("show_date") else "no"], onChange=update_show_date)

    card.create_ui_element(UI.Text, content="Preview → {weatherTemp} • {city} • {time} • {weatherState}", full_width=True, style="caption")
    card.create_ui_element(UI.Text, content="Tip: New WeatherAPI keys may take up to 30 min to activate.", full_width=True, style="caption")

    def open_weatherapi():
        webbrowser.open("https://www.weatherapi.com/")
        print("Opening WeatherAPI.com...", type="INFO")

    card.create_ui_element(UI.Button, label="Get Free API Key → WeatherAPI.com", variant="solid",
                           color="primary", full_width=True, onClick=open_weatherapi)

    # ——— Weather Fetching ———
    def fetch_weather_data():
        if config_missing():
            return None

        now = datetime.now(timezone.utc).timestamp()
        duration = max(settings.get("cache_duration"), 300)

        # Serve from cache if fresh
        if cache.data["data"] and (now - cache.data["timestamp"]) < duration:
            return cache.data["data"]

        # Auto-expire very old cache (7 days)
        if cache.data["timestamp"] and (now - cache.data["timestamp"]) > 604800:
            print("Cache older than 7 days → clearing.", type="INFO")
            reset_cache()

        api_key = settings.get("api_key")
        city = settings.get("city")
        url = f"https://api.weatherapi.com/v1/current.json?key={api_key}&q={urllib.parse.quote_plus(city)}&aqi=no"

        for attempt in range(RETRIES):
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 429:
                    wait = 2 ** attempt
                    print(f"Rate limited. Retrying in {wait}s...", type="WARNING")
                    time.sleep(wait)
                    continue
                if response.status_code in (401, 403):
                    print("Invalid or revoked API key!", type="ERROR")
                    reset_cache()
                    return None
                response.raise_for_status()
                data = response.json()
                if "error" in data:
                    print(f"WeatherAPI: {data['error']['message']}", type="ERROR")
                    return cache.data["data"] or None

                # Success → update cache
                cache.data["data"] = data
                cache.data["timestamp"] = now
                cache.save()
                return data

            except requests.exceptions.RequestException as e:
                print(f"Network error (attempt {attempt+1}): {e}", type="ERROR")
                if attempt == RETRIES - 1:
                    return cache.data["data"]  # final fallback

        return cache.data["data"]

    # ——— Output Functions ———
    def get_weather_temp():
        if config_missing(): return "N/A"
        data = fetch_weather_data()
        if not data or "current" not in data: return "N/A"
        unit = settings.get("temp_unit")
        key = "temp_f" if unit == "F" else "temp_c"
        temp = data["current"].get(key)
        if temp is None: return "N/A"
        prec = settings.get("temp_precision")
        if prec == "int":
            temp = int(round(temp))
            return f"{temp}°{unit}"
        else:
            return f"{temp:.1f}°{unit}"

    def get_city():
        return settings.get("city") or "Unknown City"

    def get_time():
        if config_missing(): return "?:??"
        try:
            offset = float(settings.get("utc_offset", 0))
            offset = max(min(offset, 14), -14)
            fmt = settings.get("time_format")
            show_date = settings.get("show_date")

            now = datetime.now(timezone.utc) + timedelta(hours=offset)

            formats = {
                "12": "%I:%M %p",
                "12s": "%I:%M:%S %p",
                "24": "%H:%M",
                "24s": "%H:%M:%S"
            }
            time_str = now.strftime(formats.get(fmt, "%I:%M %p")).lstrip("0")
            if time_str.startswith(":"): time_str = "12" + time_str[1:]

            if show_date:
                time_str += now.strftime(" - %b %d")

            return time_str
        except:
            return datetime.now(timezone.utc).strftime("%I:%M %p")

    def get_weather_state():
        if config_missing(): return "unknown"
        data = fetch_weather_data()
        if not data or "current" not in data: return "unknown"
        return data["current"]["condition"]["text"].lower()

    def get_weather_icon():
        if config_missing(): return ""
        data = fetch_weather_data()
        if not data or "current" not in data: return ""
        icon = data["current"]["condition"]["icon"]
        if icon:
            return "https:" + icon.replace("64x64", "128x128")
        return ""

    # Register DRPC values
    addDRPCValue("weatherTemp", get_weather_temp)
    addDRPCValue("city", get_city)
    addDRPCValue("time", get_time)
    addDRPCValue("weatherState", get_weather_state)
    addDRPCValue("weathericon", get_weather_icon)

    print("NightyWeather → Ready & Beautiful", type="SUCCESS")
    tab.render()