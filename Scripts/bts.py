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

    def get_setting(key=None):
        if not os.path.exists(CONFIG_PATH):
            return None if key else {}
        try:
            with open(CONFIG_PATH, 'r', encoding="utf-8") as f:
                data = json.load(f)
                return data.get(key) if key else data
        except Exception:
            return None if key else {}

    def update_setting(key, value):
        settings = get_setting() or {}
        settings[key] = value
        with open(CONFIG_PATH, 'w', encoding="utf-8") as f:
            json.dump(settings, f, indent=2)

    def load_cache():
        if not os.path.exists(CACHE_PATH):
            return {"data": None, "timestamp": 0, "call_count": 0, "live_mode_warning_shown": False}
        try:
            with open(CACHE_PATH, 'r', encoding="utf-8") as f:
                cache = json.load(f)
                timestamp = cache.get("timestamp", 0)
                if not isinstance(timestamp, (int, float)) or timestamp < 0:
                    print("Invalid cache timestamp. Resetting cache.", type_="WARNING")
                    return {"data": None, "timestamp": 0, "call_count": 0, "live_mode_warning_shown": False}
                return cache
        except Exception:
            print("Corrupted cache file. Resetting cache.", type_="ERROR")
            return {"data": None, "timestamp": 0, "call_count": 0, "live_mode_warning_shown": False}

    def save_cache(data, timestamp=None, call_count=0, live_mode_warning_shown=False):
        timestamp = timestamp or datetime.now(timezone.utc).timestamp()
        with open(CACHE_PATH, 'w', encoding="utf-8") as f:
            json.dump({
                "data": data,
                "timestamp": timestamp,
                "call_count": call_count,
                "live_mode_warning_shown": live_mode_warning_shown
            }, f, indent=2)

    defaults = {
        "api_key": "", "city": "", "tz_id": "UTC",
        "time_format": "12", "temp_unit": "C", "temp_precision": "integer", "cache_duration": 1800
    }
    for key, val in defaults.items():
        if get_setting(key) is None:
            update_setting(key, val)

    cache = load_cache()

    def reset_cache():
        cache["data"] = None
        cache["timestamp"] = 0
        cache["call_count"] = 0
        cache["live_mode_warning_shown"] = False
        save_cache(None)

    def update_api_key(value):
        update_setting("api_key", value)
        reset_cache()
        print("API key updated! Weather data will refresh automatically. 🌤️", type_="SUCCESS")

    def fetch_city_suggestions(query):
        if not query or not get_setting("api_key"):
            return []
        try:
            url = f"http://api.weatherapi.com/v1/search.json?key={get_setting('api_key')}&q={query}"
            response = requests.get(url, timeout=3)
            response.raise_for_status()
            return [
                {"id": f"{item['name']}, {item['region']}, {item['country']}", "title": f"{item['name']}, {item['region']}, {item['country']}"}
                for item in response.json()
            ]
        except Exception as e:
            print(f"City suggestion error: {str(e)}", type_="ERROR")
            return []

    def update_city(value):
        value = value.strip()
        if not value or len(value) > 100:
            print("Invalid city name (e.g., 'Seoul').", type_="ERROR")
            return
        if not get_setting("api_key"):
            print("API key required to validate city.", type_="ERROR")
            return
        try:
            url = f"http://api.weatherapi.com/v1/current.json?key={get_setting('api_key')}&q={value}&aqi=no"
            response = requests.get(url, timeout=3)
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                print(f"WeatherAPI error: {data['error']['message']}", type_="ERROR")
                return
            update_setting("city", value)
            update_setting("tz_id", data.get("location", {}).get("tz_id", "UTC"))
            reset_cache()
            print(f"City updated to {value}! Weather and time will refresh automatically. 🏙️", type_="SUCCESS")
        except Exception as e:
            print(f"City validation error: {str(e)}", type_="ERROR")

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
            save_cache(None)

    if not get_setting("api_key") or not get_setting("city"):
        print("Set API key and city in GUI. 🌟", type_="INFO")

    cache_modes = [
        {"id": "live", "title": "Live (30s)"},
        {"id": "5min", "title": "Every 5 Min"},
        {"id": "15min", "title": "Every 15 Min"},
        {"id": "30min", "title": "Every 30 Min"},
        {"id": "60min", "title": "Every 60 Min"}
    ]
    mode_reverse = {30: "live", 300: "5min", 900: "15min", 1800: "30min", 3600: "60min"}
    selected_mode = mode_reverse.get(get_setting("cache_duration"), "30min")

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
        print(f"Failed to load image: {str(e)}", type_="ERROR")

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
        content="🌤️ {weatherTemp}: Current temperature\n🏙️ {city}: Selected city\n🕐 {time}: Local time\n☁️ {weatherState}: Weather condition\n🖼️ {weathericon}: Weather icon",
        full_width=True
    )
    card.create_ui_element(
        UI.Text,
        content="ℹ️ Wait 30min after WeatherAPI signup for key approval.",
        full_width=True
    )

    def open_weatherapi():
        webbrowser.open("https://www.weatherapi.com/")
        print("Opening WeatherAPI website... 🌐", type_="INFO")

    card.create_ui_element(
        UI.Button,
        label="Visit WeatherAPI 🌐",
        variant="solid",
        size="md",
        color="default",
        full_width=True,
        onClick=open_weatherapi
    )

    def fetch_weather_data():
        api_key = get_setting("api_key")
        city = get_setting("city")
        if not api_key or not city:
            print("Missing API key or city.", type_="ERROR")
            return None
        current_time = datetime.now(timezone.utc).timestamp()
        cache_duration = get_setting("cache_duration") or 1800
        cache = load_cache()
        if cache_duration > 0 and cache["data"] and (current_time - cache["timestamp"]) < cache_duration:
            return cache["data"]
        if cache["timestamp"] and (current_time - cache["timestamp"]) > 86400:
            print("Cache expired (24h). Resetting.", type_="INFO")
            reset_cache()
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
                cache["data"] = data
                cache["timestamp"] = current_time
                cache["call_count"] = cache.get("call_count", 0) + 1
                if cache_duration == 30 and not cache["live_mode_warning_shown"]:
                    print("Live mode (30s): Frequent calls may hit limits. ⚠️", type_="WARNING")
                    cache["live_mode_warning_shown"] = True
                save_cache(data, current_time, cache["call_count"], cache["live_mode_warning_shown"])
                return data
            except requests.exceptions.HTTPError as e:
                if response.status_code == 401:
                    print("Invalid API key.", type_="ERROR")
                    return cache["data"] if cache["data"] else None
                raise
            except Exception as e:
                print(f"Fetch error: {str(e)}", type_="ERROR")
                if attempt == RETRIES - 1:
                    return cache["data"] if cache["data"] else None
        return None

    def get_weather_temp():
        data = fetch_weather_data()
        if not data or "current" not in data:
            return "N/A"
        temp_unit = get_setting("temp_unit") or "C"
        temp_precision = get_setting("temp_precision") or "integer"
        temp_key = "temp_f" if temp_unit == "F" else "temp_c"
        temp_value = data["current"].get(temp_key)
        if temp_value is None:
            return "N/A"
        return f"{int(round(temp_value))}°{temp_unit}" if temp_precision == "integer" else f"{temp_value:.1f}°{temp_unit}"

    def get_city():
        return get_setting("city") or "Unknown"

    def get_time():
        try:
            tz = pytz.timezone(get_setting("tz_id") or "UTC")
            time_format = get_setting("time_format") or "12"
            local_time = datetime.now(timezone.utc).astimezone(tz)
            fmt = {
                "12": "%I:%M %p",
                "12s": "%I:%M:%S %p",
                "24": "%H:%M",
                "24s": "%H:%M:%S"
            }.get(time_format, "%I:%M %p")
            return local_time.strftime(fmt).lstrip("0")
        except Exception as e:
            print(f"Time error: {str(e)}", type_="ERROR")
            return datetime.now(timezone.utc).strftime("%I:%M %p").lstrip("0")

    def get_weather_state():
        data = fetch_weather_data()
        return data["current"]["condition"]["text"].lower() if data and "current" in data and "condition" in data["current"] else "unknown"

    def get_weather_icon():
        data = fetch_weather_data()
        if not data or "current" not in data or "condition" not in data["current"]:
            print("No weather data or condition available for icon.", type_="ERROR")
            return ""
        icon_path = data["current"]["condition"].get("icon")
        if not icon_path:
            print("No icon path provided by WeatherAPI.", type_="ERROR")
            return ""
        # Ensure the icon path starts with the correct base URL and is absolute
        if icon_path.startswith("//"):
            icon_url = f"https:{icon_path}"
        elif icon_path.startswith("/"):
            icon_url = f"https://cdn.weatherapi.com{icon_path}"
        else:
            icon_url = f"https://cdn.weatherapi.com/{icon_path}"
        # Verify the icon URL is reachable
        try:
            response = requests.head(icon_url, timeout=3)
            if response.status_code != 200:
                print(f"Invalid icon URL: {icon_url} (Status: {response.status_code})", type_="ERROR")
                return ""
            return icon_url
        except Exception as e:
            print(f"Error validating icon URL {icon_url}: {str(e)}", type_="ERROR")
            return ""

    addDRPCValue("weatherTemp", get_weather_temp)
    addDRPCValue("city", get_city)
    addDRPCValue("time", get_time)
    addDRPCValue("weatherState", get_weather_state)
    addDRPCValue("weathericon", get_weather_icon)

    print("NightyWeather running 🌤️", type_="SUCCESS")
    tab.render()
