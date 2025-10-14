import webbrowser
import time
from datetime import datetime, timezone, timedelta
import os
import json
import requests
import threading

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
        if os.path.exists(CACHE_PATH):
            try:
                with open(CACHE_PATH, 'r', encoding="utf-8") as f:
                    cache = json.load(f)
                    timestamp = cache.get("timestamp", 0)
                    # Validate UTC timestamp
                    if not isinstance(timestamp, (int, float)) or timestamp < 0:
                        print("Invalid cache timestamp. Resetting cache.", type_="WARNING")
                        return {"data": None, "timestamp": 0, "call_count": 0, "live_mode_warning_shown": False, "call_limit_warning_shown": False}
                    return cache
            except Exception:
                print("Corrupted cache file. Resetting cache.", type_="ERROR")
        return {"data": None, "timestamp": 0, "call_count": 0, "live_mode_warning_shown": False, "call_limit_warning_shown": False}

    def save_cache(data, timestamp=None, call_count=0, live_mode_warning_shown=False, call_limit_warning_shown=False):
        # Always use UTC timestamp
        timestamp = timestamp or datetime.now(timezone.utc).timestamp()
        with open(CACHE_PATH, 'w', encoding="utf-8") as f:
            json.dump({
                "data": data,
                "timestamp": timestamp,
                "call_count": call_count,
                "live_mode_warning_shown": live_mode_warning_shown,
                "call_limit_warning_shown": call_limit_warning_shown
            }, f, indent=2)

    defaults = {
        "api_key": "", "city": "", "utc_offset": 0.0,  # Changed from gmt_offset
        "time_format": "12", "temp_unit": "C", "cache_duration": 1800
    }
    for key, val in defaults.items():
        if get_setting(key) is None:
            update_setting(key, val)

    cache = load_cache()

    def update_api_key(value):
        update_setting("api_key", value)
        cache["data"] = None
        cache["timestamp"] = 0
        cache["call_count"] = 0
        cache["live_mode_warning_shown"] = False
        cache["call_limit_warning_shown"] = False
        save_cache(None, None, 0, False, False)
        print("API key updated! Weather data will refresh automatically. 🌤️", type_="SUCCESS")

    def update_city(value):
        value = value.strip()
        if value and len(value) <= 100:
            update_setting("city", value)
            cache["data"] = None
            cache["timestamp"] = 0
            cache["call_count"] = 0
            cache["live_mode_warning_shown"] = False
            cache["call_limit_warning_shown"] = False
            save_cache(None, None, 0, False, False)
            print("City updated! Weather data will refresh automatically. 🏙️", type_="SUCCESS")
        else:
            print("Invalid city name (e.g., 'Seoul').", type_="ERROR")

    def update_utc_offset(selected):
        try:
            offset = float(selected[0])
            if -14 <= offset <= 14:
                update_setting("utc_offset", offset)  # Changed from gmt_offset
                print("UTC offset updated! Time will refresh automatically. 🌍", type_="SUCCESS")
            else:
                print("UTC offset must be between -14 and +14.", type_="ERROR")
        except ValueError:
            print("Invalid UTC offset.", type_="ERROR")

    def update_time_format(selected):
        update_setting("time_format", selected[0])
        print("Time format updated! Time display will refresh automatically. ⏰", type_="SUCCESS")

    def update_temp_unit(selected):
        update_setting("temp_unit", selected[0])
        cache["data"] = None
        cache["timestamp"] = 0
        cache["call_count"] = 0
        cache["live_mode_warning_shown"] = False
        cache["call_limit_warning_shown"] = False
        save_cache(None, None, 0, False, False)
        print("Temperature unit updated! Weather data will refresh automatically. 🌡️", type_="SUCCESS")

    def update_cache_mode(selected):
        mode_map = {"live": 30, "5min": 300, "15min": 900, "30min": 1800, "60min": 3600}
        new_duration = mode_map.get(selected[0], 1800)
        update_setting("cache_duration", new_duration)
        cache["data"] = None
        cache["timestamp"] = 0
        cache["call_count"] = 0
        cache["live_mode_warning_shown"] = False if selected[0] == "live" else cache["live_mode_warning_shown"]
        cache["call_limit_warning_shown"] = False
        save_cache(None, None, 0, cache["live_mode_warning_shown"], False)
        print(f"Cache mode updated to {selected[0]}! Data refreshes every {new_duration}s. ⚙️", type_="SUCCESS")
        if selected[0] == "live" and not cache["live_mode_warning_shown"]:
            print("Live mode (30s): Frequent calls may hit limits. ⚠️", type_="WARNING")
            cache["live_mode_warning_shown"] = True
            save_cache(None, None, 0, True, cache["call_limit_warning_shown"])

    if not get_setting("api_key") or not get_setting("city"):
        print("Set API key and city in GUI. 🌟", type_="INFO")

    # Updated UTC offset list (same values, relabeled as UTC)
    utc_offsets = sorted([-12.0, -11.0, -10.0, -9.5, -9.0, -8.0, -7.0, -6.0, -5.0, -4.5, -4.0, -3.5, -3.0, -2.0, -1.0,
                          0.0, 1.0, 2.0, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 5.75, 6.0, 6.5, 7.0, 8.0, 8.5, 9.0, 9.5,
                          10.0, 10.5, 11.0, 12.0, 12.75, 13.0, 14.0])
    offset_items = [{"id": str(off), "title": f"UTC{'-' if off < 0 else '+'}{abs(int(off)):02d}:{int((abs(off) - int(abs(off))) * 60):02d}"} for off in utc_offsets]

    cache_modes = [
        {"id": "live", "title": "Live (30s, may hit limits) ⚠️"},
        {"id": "5min", "title": "Every 5 Min 🕐"},
        {"id": "15min", "title": "Every 15 Min ⏰"},
        {"id": "30min", "title": "Every 30 Min ☕"},
        {"id": "60min", "title": "Every 60 Min 🌤️"}
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
    card.create_ui_element(UI.Input, label="City 🏙️", show_clear_button=True, full_width=True, required=True, onInput=update_city, value=get_setting("city"))
    card.create_ui_element(UI.Select, label="UTC Offset 🌍", full_width=True, mode="single", items=offset_items, selected_items=[str(get_setting("utc_offset"))], onChange=update_utc_offset)  # Changed label
    card.create_ui_element(UI.Select, label="Time Format ⏰", full_width=True, mode="single", items=[
        {"id": "12", "title": "12-hour (e.g., 7:58 AM)"},
        {"id": "12s", "title": "12-hour with seconds (e.g., 7:58:23 AM)"},
        {"id": "24", "title": "24-hour (e.g., 19:58)"},
        {"id": "24s", "title": "24-hour with seconds (e.g., 19:58:23)"}
    ], selected_items=[get_setting("time_format")], onChange=update_time_format)
    card.create_ui_element(UI.Select, label="Temperature Unit 🌡️", full_width=True, mode="single", items=[
        {"id": "C", "title": "Celsius (°C)"},
        {"id": "F", "title": "Fahrenheit (°F)"}
    ], selected_items=[get_setting("temp_unit")], onChange=update_temp_unit)
    card.create_ui_element(UI.Select, label="Cache Mode ⚙️", full_width=True, mode="single", items=cache_modes, selected_items=[selected_mode], onChange=update_cache_mode)

    card.create_ui_element(UI.Text, content="🌤️ {weatherTemp}: Current temperature in your chosen unit (e.g., 22°C or 72°F)\n🏙️ {city}: Your selected city or location (e.g., Seoul or New York)\n🕐 {time}: Local time adjusted for UTC offset (e.g., 7:58 PM or 19:58:23)\n☁️ {weatherState}: Current weather condition description (e.g., sunny, partly cloudy, or rainy)\n🖼️ {weathericon}: Displays the current weather condition as a small icon image in the designated small image section, automatically updated based on real-time weather data (e.g., a sun icon for sunny weather) use only small image url to avoid distortion", full_width=True)
    card.create_ui_element(UI.Text, content="ℹ️ Wait 30min after WeatherAPI signup for key approval.", full_width=True)

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
        try:
            api_key = get_setting("api_key")
            city = get_setting("city")
            if not api_key or not city:
                return None
            current_time = datetime.now(timezone.utc).timestamp()  # Use UTC
            cache_duration = get_setting("cache_duration") or 1800
            cache = load_cache()
            if cache_duration > 0 and cache["data"] and (current_time - cache["timestamp"]) < cache_duration:
                return cache["data"]
            if cache["timestamp"] and (current_time - cache["timestamp"]) > 86400:
                print("Cache expired (24h). Resetting.", type_="INFO")
                cache["data"] = None
                cache["timestamp"] = 0
                cache["call_count"] = 0
                cache["live_mode_warning_shown"] = False
                cache["call_limit_warning_shown"] = False
                save_cache(None, None, 0, False, False)
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
                    cache["timestamp"] = datetime.now(timezone.utc).timestamp()  # Use UTC
                    cache["call_count"] = cache.get("call_count", 0) + 1
                    live_mode_warning_shown = cache["live_mode_warning_shown"]
                    call_limit_warning_shown = cache["call_limit_warning_shown"]
                    if cache_duration == 30 and not live_mode_warning_shown:
                        print("Live mode (30s): Frequent calls may hit limits. ⚠️", type_="WARNING")
                        live_mode_warning_shown = True
                    if cache["call_count"] > 900000 and not call_limit_warning_shown:
                        print("Nearing 1M call limit. Adjust cache or upgrade. 📊", type_="WARNING")
                        call_limit_warning_shown = True
                    save_cache(data, None, cache["call_count"], live_mode_warning_shown, call_limit_warning_shown)
                    return data
                except requests.exceptions.HTTPError as e:
                    if response and response.status_code == 401:
                        return cache["data"] if cache["data"] else None
                    raise
            print("Fetch failed after retries. Using cache if available.", type_="ERROR")
            return cache["data"] if cache["data"] else None
        except Exception as e:
            print(f"Fetch error: {str(e)}", type_="ERROR")
            return cache["data"] if cache["data"] else None

    def get_weather_temp():
        data = fetch_weather_data()
        if not data or "current" not in data:
            return "N/A"
        temp_unit = get_setting("temp_unit") or "C"
        temp_key = "temp_f" if temp_unit == "F" else "temp_c"
        return f"{int(round(data['current'][temp_key]))}°{temp_unit}" if temp_key in data["current"] else "N/A"

    def get_city():
        return get_setting("city") or "Unknown"

    def get_time():
        try:
            utc_offset = float(get_setting("utc_offset") or 0.0)  # Changed from gmt_offset
            time_format = get_setting("time_format") or "12"
            if not -14 <= utc_offset <= 14:
                raise ValueError("Invalid UTC offset")
            utc_now = datetime.now(timezone.utc)  # Always start with UTC
            target_time = utc_now + timedelta(seconds=int(utc_offset * 3600))
            if time_format == "12":
                fmt = "%I:%M %p"
            elif time_format == "12s":
                fmt = "%I:%M:%S %p"
            elif time_format == "24":
                fmt = "%H:%M"
            elif time_format == "24s":
                fmt = "%H:%M:%S"
            else:
                fmt = "%I:%M %p"
            return target_time.strftime(fmt).lstrip("0")
        except Exception as e:
            print(f"Time error: {str(e)}", type_="ERROR")
            return datetime.now(timezone.utc).strftime("%I:%M %p").lstrip("0")

    def get_weather_state():
        data = fetch_weather_data()
        return data["current"]["condition"]["text"].lower() if data and "current" in data and "condition" in data["current"] else "unknown"

    def get_weather_icon():
        data = fetch_weather_data()
        if data and "current" in data and "condition" in data["current"]:
            code = data["current"]["condition"]["code"]
            is_day = data["current"]["is_day"]
            time_of_day = "day" if is_day == 1 else "night"
            code_to_icon = {
                1000: 113, 1003: 116, 1006: 119, 1009: 122, 1030: 143, 1063: 176, 1066: 179, 1069: 182,
                1072: 185, 1087: 200, 1114: 227, 1117: 230, 1135: 248, 1147: 260, 1150: 263, 1153: 266,
                1168: 281, 1171: 284, 1180: 293, 1183: 296, 1186: 299, 1189: 302, 1192: 305, 1195: 308,
                1198: 311, 1201: 314, 1204: 317, 1207: 320, 1210: 323, 1213: 326, 1216: 329, 1219: 332,
                1222: 335, 1225: 338, 1237: 350, 1240: 353, 1243: 356, 1246: 359, 1249: 362, 1252: 365,
                1255: 368, 1258: 371, 1261: 374, 1264: 377, 1273: 386, 1276: 389, 1279: 392, 1282: 395
            }
            icon_code = code_to_icon.get(code)
            if icon_code:
                return f"https://cdn.weatherapi.com/weather/128x128/{time_of_day}/{icon_code}.png"
        return ""

    addDRPCValue("weatherTemp", get_weather_temp)
    addDRPCValue("city", get_city)
    addDRPCValue("time", get_time)
    addDRPCValue("weatherState", get_weather_state)
    addDRPCValue("weathericon", get_weather_icon)

    print("NightyWeather running 🌤️", type_="SUCCESS")
    tab.render()
