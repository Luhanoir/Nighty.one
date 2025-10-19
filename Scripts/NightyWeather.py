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
                    if not isinstance(timestamp, (int, float)) or timestamp < 0:
                        print("Invalid cache timestamp. Resetting cache.", type_="WARNING")
                        return {"data": None, "timestamp": 0, "call_count": 0, "live_mode_warning_shown": False, "call_limit_warning_shown": False}
                    return cache
            except Exception:
                print("Corrupted cache file. Resetting cache.", type_="ERROR")
        return {"data": None, "timestamp": 0, "call_count": 0, "live_mode_warning_shown": False, "call_limit_warning_shown": False}

    def save_cache(data, timestamp=None, call_count=0, live_mode_warning_shown=False, call_limit_warning_shown=False):
        timestamp = timestamp or datetime.now(timezone.utc).timestamp()
        with open(CACHE_PATH, 'w', encoding="utf-8") as f:
            json.dump({
                "data": data,
                "timestamp": timestamp,
                "call_count": call_count,
                "live_mode_warning_shown": live_mode_warning_shown,
                "call_limit_warning_shown": call_limit_warning_shown
            }, f, indent=2)

    # Initialize defaults if missing
    defaults = {
        "api_key": "", "city": "", "utc_offset": 0.0,
        "time_format": "12", "temp_unit": "C", "temp_precision": "int", "cache_duration": 1800,
        # New options defaults
        "weather_text_case": "title", "icon_size": "medium", "show_humidity": False, "show_wind": False,
        "date_format": "short"
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
                update_setting("utc_offset", offset)
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
        print("Temperature unit updated! Display will refresh automatically. 🌡️", type_="SUCCESS")

    def update_temp_precision(selected):
        update_setting("temp_precision", selected[0])
        print("Temperature precision updated! Display will refresh automatically. 📐", type_="SUCCESS")

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

    # New option handlers
    def update_weather_text_case(selected):
        update_setting("weather_text_case", selected[0])
        print("Weather text case updated! Descriptions will adjust automatically. 📝", type_="SUCCESS")

    def update_icon_size(selected):
        update_setting("icon_size", selected[0])
        print("Icon size updated! Weather icons will resize in display. 🖼️", type_="SUCCESS")

    def update_show_humidity(checked):
        update_setting("show_humidity", checked)
        print(f"Humidity display {'enabled' if checked else 'disabled'}! 💧", type_="SUCCESS")

    def update_show_wind(checked):
        update_setting("show_wind", checked)
        print(f"Wind display {'enabled' if checked else 'disabled'}! 💨", type_="SUCCESS")

    def update_date_format(selected):
        update_setting("date_format", selected[0])
        print("Date format updated! Date display will refresh automatically. 📅", type_="SUCCESS")

    # Check for required settings
    if not get_setting("api_key") or not get_setting("city"):
        print("Set API key and city in GUI. 🌟", type_="INFO")

    # UTC offsets configuration
    utc_offsets = sorted([-12.0, -11.0, -10.0, -9.5, -9.0, -8.0, -7.0, -6.0, -5.0, -4.5, -4.0, -3.5, -3.0, -2.0, -1.0,
                          0.0, 1.0, 2.0, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 5.75, 6.0, 6.5, 7.0, 8.0, 8.5, 9.0, 9.5,
                          10.0, 10.5, 11.0, 12.0, 12.75, 13.0, 14.0])
    offset_items = [{"id": str(off), "title": f"UTC{'-' if off < 0 else '+'}{abs(int(off)):02d}:{int((abs(off) - int(abs(off))) * 60):02d}"} for off in utc_offsets]

    # Cache modes configuration
    cache_modes = [
        {"id": "live", "title": "Live (30s, may hit limits) ⚠️"},
        {"id": "5min", "title": "Every 5 Min 🕐"},
        {"id": "15min", "title": "Every 15 Min ⏰"},
        {"id": "30min", "title": "Every 30 Min ☕"},
        {"id": "60min", "title": "Every 60 Min 🌤️"}
    ]
    mode_reverse = {30: "live", 300: "5min", 900: "15min", 1800: "30min", 3600: "60min"}
    selected_mode = mode_reverse.get(get_setting("cache_duration"), "30min")

    # Create tab and main container
    tab = Tab(name="NightyWeather", title="Weather & Time 🌦️", icon="sun")
    container = tab.create_container(type="rows")
    
    # Core Settings Card: Basic inputs and selects
    core_card = container.create_card(height="auto", width="full", gap=2, title="Core Settings ⚙️")
    
    try:
        core_card.create_ui_element(
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

    core_card.create_ui_element(UI.Input, label="API Key 🔑", show_clear_button=True, full_width=True, required=True, onInput=update_api_key, value=get_setting("api_key"))
    core_card.create_ui_element(UI.Input, label="City 🏙️", show_clear_button=True, full_width=True, required=True, onInput=update_city, value=get_setting("city"))
    core_card.create_ui_element(UI.Select, label="UTC Offset 🌍", full_width=True, mode="single", items=offset_items, selected_items=[str(get_setting("utc_offset"))], onChange=update_utc_offset)
    core_card.create_ui_element(UI.Select, label="Time Format ⏰", full_width=True, mode="single", items=[
        {"id": "12", "title": "12-hour (e.g., 7:58 PM)"},
        {"id": "12s", "title": "12-hour with seconds (e.g., 7:58:23 PM)"},
        {"id": "24", "title": "24-hour (e.g., 19:58)"},
        {"id": "24s", "title": "24-hour with seconds (e.g., 19:58:23)"}
    ], selected_items=[get_setting("time_format")], onChange=update_time_format)
    core_card.create_ui_element(UI.Select, label="Temperature Unit 🌡️", full_width=True, mode="single", items=[
        {"id": "C", "title": "Celsius (°C)"},
        {"id": "F", "title": "Fahrenheit (°F)"}
    ], selected_items=[get_setting("temp_unit")], onChange=update_temp_unit)
    core_card.create_ui_element(UI.Select, label="Temperature Precision 📏", full_width=True, mode="single", items=[
        {"id": "int", "title": "Integer (e.g., 22°)"},
        {"id": "1dec", "title": "One Decimal (e.g., 22.4°)"}
    ], selected_items=[get_setting("temp_precision")], onChange=update_temp_precision)
    core_card.create_ui_element(UI.Select, label="Cache Mode ⚙️", full_width=True, mode="single", items=cache_modes, selected_items=[selected_mode], onChange=update_cache_mode)

    # New Card 1: Weather Text & Icon Options
    text_icon_card = container.create_card(height="auto", width="full", gap=2, title="Weather Text & Icon Options 📝🖼️")
    text_icon_card.create_ui_element(UI.Select, label="Weather Condition Text Case", full_width=True, mode="single", items=[
        {"id": "title", "title": "Title Case (e.g., Partly Cloudy)"},
        {"id": "lower", "title": "Lowercase (e.g., partly cloudy)"},
        {"id": "upper", "title": "Uppercase (e.g., PARTLY CLOUDY)"}
    ], selected_items=[get_setting("weather_text_case")], onChange=update_weather_text_case)
    text_icon_card.create_ui_element(UI.Select, label="Weather Icon Size", full_width=True, mode="single", items=[
        {"id": "small", "title": "Small (32x32 px)"},
        {"id": "medium", "title": "Medium (64x64 px)"},
        {"id": "large", "title": "Large (128x128 px)"}
    ], selected_items=[get_setting("icon_size")], onChange=update_icon_size)

    # New Card 2: Additional Data Toggles
    extra_data_card = container.create_card(height="auto", width="full", gap=2, title="Additional Data Options 📊")
    extra_data_card.create_ui_element(UI.Switch, label="Show Humidity 💧", checked=get_setting("show_humidity"), onChange=update_show_humidity)
    extra_data_card.create_ui_element(UI.Switch, label="Show Wind Speed 💨", checked=get_setting("show_wind"), onChange=update_show_wind)

    # New Card 3: Date Display Options
    date_card = container.create_card(height="auto", width="full", gap=2, title="Date Display Options 📅")
    date_card.create_ui_element(UI.Select, label="Date Format", full_width=True, mode="single", items=[
        {"id": "short", "title": "Short (e.g., Oct 19)"},
        {"id": "medium", "title": "Medium (e.g., Oct 19, 2025)"},
        {"id": "long", "title": "Long (e.g., Saturday, October 19, 2025)"},
        {"id": "none", "title": "Hide Date"}
    ], selected_items=[get_setting("date_format")], onChange=update_date_format)

    # Display Info Card: Updated with new placeholders
    display_card = container.create_card(height="auto", width="full", gap=2, title="Display Preview 📺")
    display_card.create_ui_element(UI.Text, content="🌤️ {weatherTemp}: Current temperature (e.g., 22°C or 71.6°F)\n🏙️ {city}: Your selected city (e.g., Seoul or New York)\n🕐 {time}: Local time (e.g., 7:58 PM or 19:58:23)\n📅 {date}: Current date in chosen format (e.g., Oct 19, 2025)\n☁️ {weatherState}: Weather condition (e.g., partly cloudy)\n🖼️ {weathericon}: Weather icon (size-adjustable)\n💧 {humidity}: Humidity % (if enabled)\n💨 {windSpeed}: Wind speed (if enabled)\n\nUse these in your RPC display for dynamic updates!", full_width=True)

    # New: RPC Showcase Card - Displays current active RPC values as a mock profile preview
    rpc_showcase_card = container.create_card(height="auto", width="full", gap=2, title="Active RPC Showcase 👤 (User Profile Preview)")

    # Function to generate current RPC preview text
    def generate_rpc_preview():
        try:
            # Call getters to get current values
            temp = get_weather_temp()
            city_val = get_city()
            time_val = get_time()
            date_val = get_date()
            state = get_weather_state()
            humidity_val = get_humidity()
            wind_val = get_wind_speed()
            
            # Mock Discord profile format (e.g., as it might appear in User Profile tab)
            preview = f"""🚀 Current Active RPC Status (via Nighty Selfbot):

📍 Location: {city_val}
🕐 Time: {time_val}
📅 Date: {date_val}
🌡️ Temperature: {temp}
☁️ Condition: {state}
{humidity_val if humidity_val else ''}
{wind_val if wind_val else ''}

💡 Tip: This is a live snapshot of your RPC values. Changes in settings update your Discord profile instantly via Nighty!
🔄 Reload this tab or adjust settings to see updates. View full profile in Nighty's User Profile tab."""
            return preview
        except Exception as e:
            return f"Preview generation error: {str(e)}\nEnsure API key and city are set."

    # Add the preview text element
    rpc_showcase_card.create_ui_element(UI.Text, content=generate_rpc_preview(), full_width=True)

    # Optional: Add a refresh button to regenerate preview (if UI supports dynamic updates; otherwise, reload tab)
    def refresh_preview():
        # This would require re-rendering, but for now, log/print current state
        print(generate_rpc_preview(), type_="INFO")
        print("RPC preview refreshed! Check console or reload tab for visual update. 🔄", type_="SUCCESS")

    rpc_showcase_card.create_ui_element(
        UI.Button,
        label="Refresh RPC Preview 🔄",
        variant="outline",
        size="md",
        color="default",
        full_width=True,
        onClick=refresh_preview
    )

    # Action Card: Button and info text
    action_card = container.create_card(height="auto", width="full", gap=2, title="Actions & Info ℹ️")
    action_card.create_ui_element(UI.Text, content="ℹ️ Wait 30min after WeatherAPI signup for key approval.", full_width=True)

    def open_weatherapi():
        webbrowser.open("https://www.weatherapi.com/")
        print("Opening WeatherAPI website... 🌐", type_="INFO")

    action_card.create_ui_element(
        UI.Button,
        label="Visit WeatherAPI 🌐",
        variant="solid",
        size="md",
        color="default",
        full_width=True,
        onClick=open_weatherapi
    )

    # Weather fetching function (unchanged)
    def fetch_weather_data():
        try:
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
                    cache["timestamp"] = datetime.now(timezone.utc).timestamp()
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

    # Updated Getter functions with new options
    def get_weather_temp():
        data = fetch_weather_data()
        if not data or "current" not in data:
            return "N/A"
        temp_unit = get_setting("temp_unit") or "C"
        temp_key = "temp_f" if temp_unit == "F" else "temp_c"
        temp_precision = get_setting("temp_precision") or "int"
        raw_temp = data['current'].get(temp_key)
        if raw_temp is None:
            return "N/A"
        if temp_precision == "int":
            temp = int(round(raw_temp))
            return f"{temp}°{temp_unit}"
        else:
            temp = round(raw_temp, 1)
            return f"{temp:.1f}°{temp_unit}"

    def get_city():
        return get_setting("city") or "Unknown"

    def get_time():
        try:
            utc_offset = float(get_setting("utc_offset") or 0.0)
            time_format = get_setting("time_format") or "12"
            if not -14 <= utc_offset <= 14:
                raise ValueError("Invalid UTC offset")
            utc_now = datetime.now(timezone.utc)
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

    def get_date():
        date_format = get_setting("date_format") or "short"
        utc_now = datetime.now(timezone.utc)
        utc_offset = float(get_setting("utc_offset") or 0.0)
        target_time = utc_now + timedelta(seconds=int(utc_offset * 3600))
        if date_format == "short":
            return target_time.strftime("%b %d")
        elif date_format == "medium":
            return target_time.strftime("%b %d, %Y")
        elif date_format == "long":
            return target_time.strftime("%A, %B %d, %Y")
        else:  # "none"
            return ""

    def get_weather_state():
        data = fetch_weather_data()
        if not data or "current" not in data or "condition" not in data["current"]:
            return "unknown"
        text = data["current"]["condition"]["text"]
        case = get_setting("weather_text_case") or "title"
        if case == "lower":
            return text.lower()
        elif case == "upper":
            return text.upper()
        else:  # title
            return text.title()

    def get_weather_icon():
        data = fetch_weather_data()
        if data and "current" in data and "condition" in data["current"]:
            icon_url = data["current"]["condition"]["icon"]
            if icon_url:
                size_map = {"small": "32x32", "medium": "64x64", "large": "128x128"}
                size = size_map.get(get_setting("icon_size"), "64x64")
                icon_url = "https:" + icon_url.replace("64x64", size)
                return icon_url
        return ""

    def get_humidity():
        if not get_setting("show_humidity"):
            return ""
        data = fetch_weather_data()
        return f"{data['current']['humidity']}% humidity" if data and "current" in data else ""

    def get_wind_speed():
        if not get_setting("show_wind"):
            return ""
        data = fetch_weather_data()
        if data and "current" in data:
            unit = "mph" if get_setting("temp_unit") == "F" else "kph"
            return f"{data['current'][f'wind_{unit}']:.1f} {unit}" if f'wind_{unit}' in data['current'] else ""
        return ""

    # Register RPC values (updated with new ones)
    addDRPCValue("weatherTemp", get_weather_temp)
    addDRPCValue("city", get_city)
    addDRPCValue("time", get_time)
    addDRPCValue("date", get_date)
    addDRPCValue("weatherState", get_weather_state)
    addDRPCValue("weathericon", get_weather_icon)
    addDRPCValue("humidity", get_humidity)
    addDRPCValue("windSpeed", get_wind_speed)

    print("NightyWeather running with new options! 🌤️", type_="SUCCESS")
    tab.render()
