import webbrowser
import time
from datetime import datetime, timezone
import os
import json
import requests
import pytz

def NightyWeather():
    RETRIES = 3
    IMAGE_URL = "https://i.imgur.com/m0xu9yk.gif"
    SCRIPT_DATA_DIR = f"{getScriptsPath()}/scriptData"
    CONFIG_PATH = f"{SCRIPT_DATA_DIR}/NightyWeather.json"
    CACHE_PATH = f"{SCRIPT_DATA_DIR}/NightyWeatherCache.json"
    os.makedirs(SCRIPT_DATA_DIR, exist_ok=True)

    # Weather condition code to icon mapping (based on WeatherAPI documentation)
    def get_weather_icon_url(code, is_day):
        # Comprehensive mapping based on WeatherAPI condition codes
        condition_map = {
            # Clear/Sunny
            1000: 113,  # Sunny/Clear
            # Cloudy
            1003: 116,  # Partly cloudy
            1006: 119,  # Cloudy
            1009: 122,  # Overcast
            # Mist/Fog
            1030: 143,  # Mist
            1135: 248,  # Fog
            1147: 260,  # Freezing fog
            # Rain
            1063: 176,  # Patchy rain
            1150: 263,  # Patchy light drizzle
            1153: 266,  # Light drizzle
            1168: 281,  # Freezing drizzle
            1171: 284,  # Heavy freezing drizzle
            1180: 293,  # Patchy light rain
            1183: 296,  # Light rain
            1186: 299,  # Moderate rain at times
            1189: 302,  # Moderate rain
            1192: 305,  # Heavy rain at times
            1195: 308,  # Heavy rain
            1198: 311,  # Light freezing rain
            1201: 314,  # Moderate/heavy freezing rain
            1240: 353,  # Light rain shower
            1243: 356,  # Moderate/heavy rain shower
            1246: 359,  # Torrential rain shower
            # Snow
            1066: 179,  # Patchy snow
            1069: 182,  # Patchy sleet
            1072: 185,  # Patchy freezing drizzle
            1114: 227,  # Blowing snow
            1117: 230,  # Blizzard
            1204: 317,  # Light sleet
            1207: 320,  # Moderate/heavy sleet
            1210: 323,  # Patchy light snow
            1213: 326,  # Light snow
            1216: 329,  # Patchy moderate snow
            1219: 332,  # Moderate snow
            1222: 335,  # Patchy heavy snow
            1225: 338,  # Heavy snow
            1255: 368,  # Light snow showers
            1258: 371,  # Moderate/heavy snow showers
            # Sleet
            1249: 362,  # Light sleet showers
            1252: 365,  # Moderate/heavy sleet showers
            # Thunder
            1087: 200,  # Thundery outbreaks
            1273: 386,  # Patchy light rain with thunder
            1276: 389,  # Moderate/heavy rain with thunder
            1279: 392,  # Patchy light snow with thunder
            1282: 395,  # Moderate/heavy snow with thunder
            # Ice
            1237: 350,  # Ice pellets
            1261: 374,  # Light showers of ice pellets
            1264: 377   # Moderate/heavy showers of ice pellets
        }
        time_of_day = "day" if is_day == 1 else "night"
        icon_code = condition_map.get(code, 113)  # Fallback to sunny/clear icon
        return f"https://cdn.weatherapi.com/weather/128x128/{time_of_day}/{icon_code}.png"

    def get_setting(key=None):
        if not os.path.exists(CONFIG_PATH):
            return None if key else {}
        try:
            with open(CONFIG_PATH, 'r', encoding="utf-8") as f:
                data = json.load(f)
                return data.get(key) if key else data
        except Exception as e:
            print(f"Error reading settings: {e}", type_="ERROR")
            return None if key else {}

    def update_setting(key, value):
        settings = get_setting() or {}
        settings[key] = value
        try:
            with open(CONFIG_PATH, 'w', encoding="utf-8") as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            print(f"Error updating settings: {e}", type_="ERROR")

    def load_cache():
        if not os.path.exists(CACHE_PATH):
            return {"data": None, "timestamp": 0, "call_count": 0, "live_mode_warning_shown": False, "call_limit_warning_shown": False}
        try:
            with open(CACHE_PATH, 'r', encoding="utf-8") as f:
                cache = json.load(f)
                timestamp = cache.get("timestamp", 0)
                if not isinstance(timestamp, (int, float)) or timestamp < 0:
                    print("Invalid cache timestamp. Resetting cache.", type_="WARNING")
                    return {"data": None, "timestamp": 0, "call_count": 0, "live_mode_warning_shown": False, "call_limit_warning_shown": False}
                return cache
        except Exception as e:
            print(f"Corrupted cache file: {e}. Resetting cache.", type_="ERROR")
            return {"data": None, "timestamp": 0, "call_count": 0, "live_mode_warning_shown": False, "call_limit_warning_shown": False}

    def save_cache(data, timestamp=None, call_count=0, live_mode_warning_shown=False, call_limit_warning_shown=False):
        timestamp = timestamp or datetime.now(timezone.utc).timestamp()
        try:
            with open(CACHE_PATH, 'w', encoding="utf-8") as f:
                json.dump({
                    "data": data,
                    "timestamp": timestamp,
                    "call_count": call_count,
                    "live_mode_warning_shown": live_mode_warning_shown,
                    "call_limit_warning_shown": call_limit_warning_shown
                }, f, indent=2)
        except Exception as e:
            print(f"Error saving cache: {e}", type_="ERROR")

    # Initialize default settings
    defaults = {
        "api_key": "", "city": "", "tz_id": "UTC",
        "time_format": "12", "temp_unit": "C", "temp_precision": "integer", "cache_duration": 1800
    }
    for key, val in defaults.items():
        if get_setting(key) is None:
            update_setting(key, val)

    cache = load_cache()

    def reset_cache():
        save_cache(None, None, 0, False, False)

    def update_api_key(value):
        update_setting("api_key", value)
        reset_cache()
        print("API key updated! Weather data will refresh automatically. 🌤️", type_="SUCCESS")

    def fetch_city_suggestions(query):
        api_key = get_setting("api_key")
        if not api_key or not query:
            return []
        try:
            url = f"http://api.weatherapi.com/v1/search.json?key={api_key}&q={query}"
            response = requests.get(url, timeout=3)
            response.raise_for_status()
            return [
                {
                    "id": f"{item['name']}, {item['region']}, {item['country']}",
                    "title": f"{item['name']}, {item['region']}, {item['country']}"
                } for item in response.json()
            ]
        except Exception as e:
            print(f"City suggestion error: {e}", type_="ERROR")
            return []

    def update_city(value):
        value = value.strip()
        if not value or len(value) > 100:
            print("Invalid city name (e.g., 'Seoul').", type_="ERROR")
            return
        api_key = get_setting("api_key")
        if not api_key:
            print("API key required to validate city.", type_="ERROR")
            return
        try:
            url = f"http://api.weatherapi.com/v1/current.json?key={api_key}&q={value}&aqi=no"
            response = requests.get(url, timeout=3)
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                print(f"WeatherAPI error: {data['error']['message']}", type_="ERROR")
                return
            tz_id = data.get("location", {}).get("tz_id", "UTC")
            update_setting("city", value)
            update_setting("tz_id", tz_id)
            reset_cache()
            print(f"City updated to {value} (Timezone: {tz_id})! Weather and time will refresh automatically. 🏙️", type_="SUCCESS")
        except Exception as e:
            print(f"City validation error: {e}", type_="ERROR")

    def update_time_format(selected):
        update_setting("time_format", selected[0])
        print("Time format updated! Time display will refresh automatically. ⏰", type_="SUCCESS")

    def update_temp_unit(selected):
        update_setting("temp_unit", selected[0])
        reset_cache()
        print("Temperature unit updated! Weather data will refresh automatically. 🌡️", type_="SUCCESS")

    def update_temp_precision(selected):
        update_setting("temp_precision", selected[0])
        reset_cache()
        print("Temperature precision updated! Weather data will refresh automatically. 🔍", type_="SUCCESS")

    def update_cache_mode(selected):
        mode_map = {"live": 30, "5min": 300, "15min": 900, "30min": 1800, "60min": 3600}
        new_duration = mode_map.get(selected[0], 1800)
        update_setting("cache_duration", new_duration)
        reset_cache()
        print(f"Cache mode updated to {selected[0]}! Data refreshes every {new_duration}s. ⚙️", type_="SUCCESS")
        if selected[0] == "live" and not cache["live_mode_warning_shown"]:
            print("Live mode (30s): Frequent calls may hit limits. ⚠️", type_="WARNING")
            cache["live_mode_warning_shown"] = True
            save_cache(cache["data"], None, cache["call_count"], True, cache["call_limit_warning_shown"])

    if not get_setting("api_key") or not get_setting("city"):
        print("Set API key and city in GUI. 🌟", type_="INFO")

    cache_modes = [
        {"id": "live", "title": "Live (30s, may hit limits) ⚠️"},
        {"id": "5min", "title": "Every 5 Min 🕐"},
        {"id": "15min", "title": "Every 15 Min ⏰"},
        {"id": "30min", "title": "Every 30 Min ☕"},
        {"id": "60min", "title": "Every 60 Min 🌤️"}
    ]
    mode_reverse = {30: "live", 300: "5min", 900: "15min", 1800: "30min", 3600: "60min"}
    selected_mode = mode_reverse.get(get_setting("cache_duration"), "30min")

    # UI Setup
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
        print(f"Failed to load image: {e}", type_="ERROR")

    card.create_ui_element(UI.Input, label="API Key 🔑", show_clear_button=True, full_width=True, required=True, onInput=update_api_key, value=get_setting("api_key"))
    card.create_ui_element(
        UI.Input,
        label="City 🏙️",
        show_clear_button=True,
        full_width=True,
        required=True,
        onInput=update_city,
        value=get_setting("city"),
        autocomplete=True,
        onAutocomplete=fetch_city_suggestions
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
        selected_items=[get_setting("time_format")],
        onChange=update_time_format
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
        selected_items=[get_setting("temp_unit")],
        onChange=update_temp_unit
    )
    card.create_ui_element(
        UI.Select,
        label="Temperature Precision 🔍",
        full_width=True,
        mode="single",
        items=[
            {"id": "integer", "title": "Integer (e.g., 21°)"},
            {"id": "decimal", "title": "Decimal (e.g., 21.4°)"}
        ],
        selected_items=[get_setting("temp_precision")],
        onChange=update_temp_precision
    )
    card.create_ui_element(
        UI.Select,
        label="Cache Mode ⚙️",
        full_width=True,
        mode="single",
        items=cache_modes,
        selected_items=[selected_mode],
        onChange=update_cache_mode
    )
    card.create_ui_element(
        UI.Text,
        content="🌤️ {weatherTemp}: Current temperature\n🏙️ {city}: Selected city\n🕐 {time}: Local time\n☁️ {weatherState}: Current weather\n🖼️ {weathericon}: Weather icon",
        full_width=True
    )
    card.create_ui_element(
        UI.Text,
        content="ℹ️ Wait 30min after WeatherAPI signup for key approval.",
        full_width=True
    )
    card.create_ui_element(
        UI.Button,
        label="Visit WeatherAPI 🌐",
        variant="solid",
        size="md",
        color="default",
        full_width=True,
        onClick=lambda: webbrowser.open("https://www.weatherapi.com/") or print("Opening WeatherAPI website... 🌐", type_="INFO")
    )

    def fetch_weather_data():
        api_key = get_setting("api_key")
        city = get_setting("city")
        if not api_key or not city:
            return None
        current_time = datetime.now(timezone.utc).timestamp()
        cache_duration = get_setting("cache_duration") or 1800
        cache = load_cache()
        if cache_duration > 0 and cache["data"] and (current_time - cache["timestamp"]) < cache_duration:
            return cache["data"]
        if cache["timestamp"] and (current_time - cache["timestamp"]) > 86400:
            print("Cache expired (24h). Resetting.", type_="INFO")
            reset_cache()
            cache = load_cache()
        url = f"http://api.weatherapi.com/v1/current.json?key={api_key}&q={city}&aqi=no"
        for attempt in range(RETRIES):
            try:
                response = requests.get(url, timeout=3)
                if response.status_code == 429:
                    wait_time = 2 ** attempt
                    print(f"Rate limit hit. Retrying in {wait_time}s...", type_="WARNING")
                    time.sleep(wait_time)
                    continue
                response.raise_for_status()
                data = response.json()
                if "error" in data:
                    print(f"WeatherAPI error: {data['error']['message']}", type_="ERROR")
                    return cache["data"] if cache["data"] else None
                cache["call_count"] += 1
                if cache_duration == 30 and not cache["live_mode_warning_shown"]:
                    print("Live mode (30s): Frequent calls may hit limits. ⚠️", type_="WARNING")
                    cache["live_mode_warning_shown"] = True
                if cache["call_count"] > 900000 and not cache["call_limit_warning_shown"]:
                    print("Nearing 1M call limit. Adjust cache or upgrade. 📊", type_="WARNING")
                    cache["call_limit_warning_shown"] = True
                save_cache(data, None, cache["call_count"], cache["live_mode_warning_shown"], cache["call_limit_warning_shown"])
                return data
            except requests.exceptions.HTTPError as e:
                if response.status_code == 401:
                    print("Invalid API key.", type_="ERROR")
                    return cache["data"] if cache["data"] else None
                print(f"HTTP error: {e}", type_="ERROR")
            except Exception as e:
                print(f"Fetch error: {e}", type_="ERROR")
        print("Fetch failed after retries. Using cache if available.", type_="ERROR")
        return cache["data"] if cache["data"] else None

    def get_weather_temp():
        data = fetch_weather_data()
        if not data or "current" not in data:
            return "N/A"
        temp_unit = get_setting("temp_unit") or "C"
        temp_precision = get_setting("temp_precision") or "integer"
        temp_key = "temp_f" if temp_unit == "F" else "temp_c"
        temp_value = data['current'].get(temp_key)
        if temp_value is None:
            return "N/A"
        return f"{int(round(temp_value))}°{temp_unit}" if temp_precision == "integer" else f"{temp_value:.1f}°{temp_unit}"

    def get_city():
        return get_setting("city") or "Unknown"

    def get_time():
        try:
            tz_id = get_setting("tz_id") or "UTC"
            time_format = get_setting("time_format") or "12"
            tz = pytz.timezone(tz_id)
            local_time = datetime.now(timezone.utc).astimezone(tz)
            fmt = {
                "12": "%I:%M %p",
                "12s": "%I:%M:%S %p",
                "24": "%H:%M",
                "24s": "%H:%M:%S"
            }.get(time_format, "%I:%M %p")
            return local_time.strftime(fmt).lstrip("0")
        except Exception as e:
            print(f"Time error: {e}", type_="ERROR")
            return datetime.now(timezone.utc).strftime("%I:%M %p").lstrip("0")

    def get_weather_state():
        data = fetch_weather_data()
        return data["current"]["condition"]["text"].lower() if data and "current" in data and "condition" in data["current"] else "unknown"

    def get_weather_icon():
        data = fetch_weather_data()
        if data and "current" in data and "condition" in data["current"]:
            code = data["current"]["condition"]["code"]
            is_day = data["current"]["is_day"]
            return get_weather_icon_url(code, is_day)
        return "https://cdn.weatherapi.com/weather/128x128/day/113.png"  # Default to sunny icon

    addDRPCValue("weatherTemp", get_weather_temp)
    addDRPCValue("city", get_city)
    addDRPCValue("time", get_time)
    addDRPCValue("weatherState", get_weather_state)
    addDRPCValue("weathericon", get_weather_icon)

    print("NightyWeather running 🌤️", type_="SUCCESS")
    tab.render()
