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
    FALLBACK_IMAGE_URL = "https://i.imgur.com/placeholder.gif"
    SCRIPT_DATA_DIR = f"{getScriptsPath()}/scriptData"
    CONFIG_PATH = f"{SCRIPT_DATA_DIR}/NightyWeather.json"
    CACHE_PATH = f"{SCRIPT_DATA_DIR}/NightyWeatherCache.json"
    os.makedirs(SCRIPT_DATA_DIR, exist_ok=True)

    class Settings:
        """Manages settings for modularity and future extensions."""
        defaults = {
            "api_key": "", "city": "", "utc_offset": 0.0,
            "time_format": "12", "temp_unit": "C", "temp_precision": "int",
            "cache_duration": 300, "show_date": False
        }

        def __init__(self):
            self.data = self.load() or self.defaults
            for key, val in self.defaults.items():
                if key not in self.data:
                    self.data[key] = val
            self.save()

        def load(self):
            if not os.path.exists(CONFIG_PATH):
                return None
            try:
                with open(CONFIG_PATH, 'r', encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                print("Corrupted config. Resetting.", type="ERROR")
                return None

        def save(self):
            with open(CONFIG_PATH, 'w', encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)

        def get(self, key):
            return self.data.get(key)

        def update(self, key, value):
            if key == "utc_offset" and not (-14 <= value <= 14):
                return
            if key == "cache_duration" and value < 300:
                value = 300
            self.data[key] = value
            self.save()

    class Cache:
        """Manages cache for robustness and future extensions."""
        def __init__(self):
            self.data = self.load()

        def load(self):
            if not os.path.exists(CACHE_PATH):
                return self._default()
            try:
                with open(CACHE_PATH, 'r', encoding="utf-8") as f:
                    cache = json.load(f)
                    timestamp = cache.get("timestamp", 0)
                    if not isinstance(timestamp, (int, float)) or timestamp < 0:
                        print("Invalid cache timestamp. Resetting.", type="WARNING")
                        return self._default()
                    return cache
            except Exception:
                print("Corrupted cache. Resetting.", type="ERROR")
                return self._default()

        def _default(self):
            return {"data": None, "timestamp": 0, "call_count": 0, "call_limit_warning_shown": False}

        def save(self):
            with open(CACHE_PATH, 'w', encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)

    settings = Settings()
    cache = Cache()

    def update_api_key(value):
        settings.update("api_key", value)
        reset_cache()
        print("API key updated! Weather data will refresh automatically. 🌤️", type="SUCCESS")

    def update_city(value):
        value = value.strip()
        if value and len(value) <= 100 and re.match(r'^[\w\s\-,\u00C0-\u017F]+$', value):
            settings.update("city", value)
            reset_cache()
            print("City updated! Weather data will refresh automatically. 🏙️", type="SUCCESS")
        else:
            print("Invalid city name (e.g., 'Seoul'; no special chars).", type="ERROR")

    def update_utc_offset(selected):
        if not selected or not isinstance(selected, list) or len(selected) == 0:
            print("Invalid UTC offset selection.", type="ERROR")
            return
        try:
            offset = float(selected[0])
            settings.update("utc_offset", offset)
            print("UTC offset updated! Time will refresh automatically. 🌍", type="SUCCESS")
        except ValueError:
            print("Invalid UTC offset.", type="ERROR")

    def update_time_format(selected):
        valid_formats = ["12", "12s", "24", "24s"]
        if not selected or not isinstance(selected, list) or selected[0] not in valid_formats:
            print("Invalid time format selection.", type="ERROR")
            return
        settings.update("time_format", selected[0])
        print("Time format updated! Time display will refresh automatically. ⏰", type="SUCCESS")

    def update_temp_unit(selected):
        valid_units = ["C", "F"]
        if not selected or not isinstance(selected, list) or selected[0] not in valid_units:
            print("Invalid temp unit selection.", type="ERROR")
            return
        settings.update("temp_unit", selected[0])
        print("Temperature unit updated! Display will refresh automatically. 🌡️", type="SUCCESS")

    def update_temp_precision(selected):
        valid_precisions = ["int", "1dec"]
        if not selected or not isinstance(selected, list) or selected[0] not in valid_precisions:
            print("Invalid temp precision selection.", type="ERROR")
            return
        settings.update("temp_precision", selected[0])
        print("Temperature precision updated! Display will refresh automatically. 📐", type="SUCCESS")

    def update_cache_mode(selected):
        mode_map = {"5min": 300, "15min": 900, "30min": 1800, "60min": 3600}
        if not selected or not isinstance(selected, list) or selected[0] not in mode_map:
            print("Invalid cache mode selection.", type="ERROR")
            return
        new_duration = mode_map[selected[0]]
        settings.update("cache_duration", new_duration)
        reset_cache()
        print(f"Cache mode updated to {selected[0]}! Data refreshes every {new_duration}s. ⚙️", type="SUCCESS")

    def update_show_date(selected):
        valid_options = ["yes", "no"]
        if not selected or not isinstance(selected, list) or selected[0] not in valid_options:
            print("Invalid show date selection.", type="ERROR")
            return
        settings.update("show_date", selected[0] == "yes")
        print("Date display updated! Time will refresh automatically. 📅", type="SUCCESS")

    def reset_cache():
        cache.data["data"] = None
        cache.data["timestamp"] = 0
        cache.data["call_count"] = 0
        cache.data["call_limit_warning_shown"] = False
        cache.save()

    def refresh_weather():
        reset_cache()
        fetch_weather_data()
        print("Weather data refreshed manually! 🌤️", type="SUCCESS")

    if not settings.get("api_key") or not settings.get("city"):
        print("Set API key and city in GUI. 🌟", type="INFO")

    utc_offsets = [
        -12.0, -11.0, -10.0, -9.5, -9.0, -8.0, -7.0, -6.0, -5.0, -4.5, -4.0, -3.5, -3.0, -2.0, -1.0,
        0.0, 1.0, 2.0, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 5.75, 6.0, 6.5, 7.0, 8.0, 8.5, 9.0, 9.5,
        10.0, 10.5, 11.0, 12.0, 12.75, 13.0, 14.0
    ]
    offset_items = [
        {"id": str(off), "title": f"UTC{'-' if off < 0 else '+'}{abs(int(off)):02d}:{int((abs(off) - int(abs(off))) * 60):02d}"}
        for off in sorted(utc_offsets)
    ]

    cache_modes = [
        {"id": "5min", "title": "Every 5 Min 🕐"},
        {"id": "15min", "title": "Every 15 Min ⏰"},
        {"id": "30min", "title": "Every 30 Min ☕"},
        {"id": "60min", "title": "Every 60 Min 🌤️"}
    ]
    mode_reverse = {300: "5min", 900: "15min", 1800: "30min", 3600: "60min"}
    selected_mode = mode_reverse.get(settings.get("cache_duration"), "5min")

    tab = Tab(name="NightyWeather", title="Weather & Time 🌦️", icon="sun")
    container = tab.create_container(type="rows")
    card = container.create_card(height="full", width="full", gap=3)

    try:
        card.create_ui_element(
            UI.Image,
            url=IMAGE_URL,
            alt="Weather Showcase",
            width="100%",
            height="200px",
            rounded="md",
            fill_type="contain",
            border_color="#4B5EAA",
            border_width=2,
            margin="m-2",
            shadow=True
        )
    except Exception as e:
        print(f"Failed to load image: {str(e)}. Using fallback.", type="ERROR")
        card.create_ui_element(
            UI.Image,
            url=FALLBACK_IMAGE_URL,
            alt="Fallback",
            width="100%",
            height="200px",
            rounded="md",
            fill_type="contain",
            border_color="#4B5EAA",
            border_width=2,
            margin="m-2",
            shadow=True
        )

    card.create_ui_element(
        UI.Image,
        url=get_weather_icon,
        alt="Current Weather Icon",
        width="64px",
        height="64px",
        rounded="sm",
        fill_type="contain",
        margin="m-2",
        shadow=True
    )

    card.create_ui_element(
        UI.Input,
        label="API Key 🔑",
        show_clear_button=True,
        full_width=True,
        required=True,
        onInput=update_api_key,
        value=settings.get("api_key"),
        is_secure=True
    )
    card.create_ui_element(
        UI.Input,
        label="City 🏙️",
        show_clear_button=True,
        full_width=True,
        required=True,
        onInput=update_city,
        value=settings.get("city")
    )
    card.create_ui_element(
        UI.Select,
        label="UTC Offset 🌍",
        full_width=True,
        mode="single",
        items=offset_items,
        selected_items=[str(settings.get("utc_offset"))],
        onChange=update_utc_offset,
        tooltip="Select your timezone offset from UTC."
    )
    card.create_ui_element(
        UI.Select,
        label="Time Format ⏰",
        full_width=True,
        mode="single",
        items=[
            {"id": "12", "title": "12-hour (e.g., 7:58 AM)"},
            {"id": "12s", "title": "12-hour with seconds (e.g., 7:58:23 AM)"},
            {"id": "24", "title": "24-hour (e.g., 19:58)"},
            {"id": "24s", "title": "24-hour with seconds (e.g., 19:58:23)"}
        ],
        selected_items=[settings.get("time_format")],
        onChange=update_time_format,
        tooltip="Choose how time is displayed."
    )
    card.create_ui_element(
        UI.Select,
        label="Temperature Unit 🌡️",
        full_width=True,
        mode="single",
        items=[
            {"id": "C", "title": "Celsius (°C)"},
            {"id": "F", "title": "Fahrenheit (°F)"}
        ],
        selected_items=[settings.get("temp_unit")],
        onChange=update_temp_unit,
        tooltip="Select temperature scale."
    )
    card.create_ui_element(
        UI.Select,
        label="Temperature Precision 📏",
        full_width=True,
        mode="single",
        items=[
            {"id": "int", "title": "Integer (e.g., 22°)"},
            {"id": "1dec", "title": "Decimal (e.g., 21.7°)"}
        ],
        selected_items=[settings.get("temp_precision")],
        onChange=update_temp_precision,
        tooltip="Set decimal precision for temp."
    )
    card.create_ui_element(
        UI.Select,
        label="Cache Mode ⚙️",
        full_width=True,
        mode="single",
        items=cache_modes,
        selected_items=[selected_mode],
        onChange=update_cache_mode,
        tooltip="Higher intervals save API calls."
    )
    card.create_ui_element(
        UI.Select,
        label="Show Date with Time 📅",
        full_width=True,
        mode="single",
        items=[
            {"id": "yes", "title": "Yes (e.g., 7:58 PM - Oct 22)"},
            {"id": "no", "title": "No"}
        ],
        selected_items=["yes" if settings.get("show_date") else "no"],
        onChange=update_show_date,
        tooltip="Append date to time display."
    )
    card.create_ui_element(
        UI.Text,
        content="🌤️ {weatherTemp}: Current temperature\n🏙️ {city}: Selected city\n🕐 {time}: Local time (with optional date)\n☁️ {weatherState}: Weather condition\n🖼️ {weathericon}: Weather icon",
        full_width=True
    )
    card.create_ui_element(
        UI.Text,
        content="ℹ️ Wait 30min after WeatherAPI signup for key approval.",
        full_width=True
    )
    card.create_ui_element(
        UI.Button,
        label="Refresh Weather Now 🔄",
        variant="solid",
        size="md",
        color="default",
        full_width=True,
        onClick=refresh_weather
    )
    card.create_ui_element(
        UI.Button,
        label="Visit WeatherAPI 🌐",
        variant="solid",
        size="md",
        color="default",
        full_width=True,
        onClick=open_weatherapi
    )

    def open_weatherapi():
        webbrowser.open("https://www.weatherapi.com/")
        print("Opening WeatherAPI website... 🌐", type="INFO")

    def fetch_weather_data():
        try:
            api_key = settings.get("api_key")
            city = settings.get("city")
            if not api_key or not city:
                return None
            current_time = datetime.now(timezone.utc).timestamp()
            cache_duration = max(settings.get("cache_duration"), 300)
            if cache.data["data"] and (current_time - cache.data["timestamp"]) < cache_duration:
                return cache.data["data"]
            if cache.data["timestamp"] and (current_time - cache.data["timestamp"]) > 86400:
                print("Cache expired (24h). Resetting.", type="INFO")
                reset_cache()
            quoted_city = urllib.parse.quote(city)
            url = f"http://api.weatherapi.com/v1/current.json?key={api_key}&q={quoted_city}&aqi=no"
            for attempt in range(RETRIES):
                try:
                    response = requests.get(url, timeout=3)
                    if response.status_code == 429:
                        wait_time = 2 ** attempt
                        print(f"Rate limit hit. Retrying in {wait_time}s...", type="WARNING")
                        time.sleep(wait_time)
                        continue
                    response.raise_for_status()
                    data = response.json()
                    if "error" in data:
                        print(f"WeatherAPI error: {data['error']['message']}", type="ERROR")
                        return cache.data["data"]
                    cache.data["data"] = data
                    cache.data["timestamp"] = current_time
                    cache.data["call_count"] += 1
                    if cache.data["call_count"] > 900000 and not cache.data["call_limit_warning_shown"]:
                        print("Nearing 1M call limit. Adjust cache or upgrade. 📊", type="WARNING")
                        cache.data["call_limit_warning_shown"] = True
                    cache.save()
                    return data
                except requests.exceptions.HTTPError as e:
                    if response and response.status_code == 401:
                        print("Invalid API key.", type="ERROR")
                        return cache.data["data"]
            print("Fetch failed after retries. Using cache.", type="ERROR")
            return cache.data["data"]
        except (requests.RequestException, json.JSONDecodeError, Exception) as e:
            print(f"Fetch error: {str(e)}", type="ERROR")
            return cache.data["data"]

    def get_weather_temp():
        """Returns formatted temperature based on unit and precision settings."""
        data = fetch_weather_data()
        if not data or "current" not in data:
            return "N/A"
        temp_unit = settings.get("temp_unit") or "C"
        temp_key = "temp_f" if temp_unit == "F" else "temp_c"
        temp_precision = settings.get("temp_precision") or "int"
        raw_temp = data['current'].get(temp_key)
        if raw_temp is None:
            return "N/A"
        if temp_precision == "int":
            temp = int(round(raw_temp))
        else:
            temp = round(raw_temp, 1)
        return f"{temp:.{0 if temp_precision == 'int' else 1}f}°{temp_unit}"

    def get_city():
        """Returns the selected city or 'Unknown' if not set."""
        return settings.get("city") or "Unknown"

    def get_time():
        """Returns formatted local time with optional date based on settings."""
        try:
            utc_offset = float(settings.get("utc_offset") or 0.0)  # Validated in update
            time_format = settings.get("time_format") or "12"
            show_date = settings.get("show_date")
            utc_now = datetime.now(timezone.utc)
            target_time = utc_now + timedelta(seconds=utc_offset * 3600)
            if time_format == "12":
                fmt = "%I:%M %p"
            elif time_format == "12s":
                fmt = "%I:%M:%S %p"
            elif time_format == "24":
                fmt = "%H:%M"
            elif time_format == "24s":
                fmt = "%H:%M:%S"
            else:
                fmt = "%I:%M %p"  # Fallback
            time_str = target_time.strftime(fmt)
            # Remove leading zero in 12-hour format for hours < 10
            if time_format.startswith("12") and time_str[0] == "0":
                time_str = time_str[1:]
            # Handle midnight (00:XX AM/PM) in 12-hour format
            if time_format.startswith("12") and time_str.startswith("00:"):
                time_str = "12:" + time_str[3:]
            if show_date:
                date_str = target_time.strftime("%b %d")
                time_str += f" - {date_str}"
            return time_str
        except Exception as e:
            print(f"Time error: {str(e)}", type="ERROR")
            return datetime.now(timezone.utc).strftime("%I:%M %p")

    def get_weather_state():
        """Returns current weather condition or 'unknown' if unavailable."""
        data = fetch_weather_data()
        return data["current"]["condition"]["text"].lower() if data and "current" in data else "unknown"

    def get_weather_icon():
        """Returns URL for weather icon or empty string if unavailable."""
        data = fetch_weather_data()
        if data and "current" in data:
            icon_url = data["current"]["condition"]["icon"]
            if icon_url:
                return "https:" + icon_url.replace("64x64", "128x128")
        return ""

    addDRPCValue("weatherTemp", get_weather_temp)
    addDRPCValue("city", get_city)
    addDRPCValue("time", get_time)
    addDRPCValue("weatherState", get_weather_state)
    addDRPCValue("weathericon", get_weather_icon)

    print("NightyWeather running 🌤️", type="SUCCESS")
    tab.render()
