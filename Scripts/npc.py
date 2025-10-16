import webbrowser
import time
import json
import requests
import pytz
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
import os

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Assuming external UI (e.g., Tab, UI elements) and getScriptsPath()
# If not defined, fallback to user dir
def getScriptsPath():
    try:
        return globals().get('getScriptsPath', lambda: os.path.expanduser('~/.nightyweather'))()
    except:
        return os.path.expanduser('~/.nightyweather')

class WeatherConfig:
    def __init__(self, script_data_dir: str):
        self.script_data_dir = Path(script_data_dir)
        self.script_data_dir.mkdir(exist_ok=True)
        self.config_path = self.script_data_dir / "NightyWeather.json"
        self.cache_path = self.script_data_dir / "NightyWeatherCache.json"
        self.defaults = {
            "api_key": "", "city": "", "tz_id": "UTC",
            "time_format": "12", "temp_unit": "C", "temp_precision": "integer", "cache_duration": 1800
        }
        self._load_config()
        self.cache = self._load_cache()
        self._apply_defaults()

    def _load_config(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding="utf-8") as f:
                    self.config = json.load(f)
            except Exception as e:
                logger.error(f"Corrupted config: {e}. Resetting.")
                self.config = {}
        else:
            self.config = {}

    def _save_config(self):
        with open(self.config_path, 'w', encoding="utf-8") as f:
            json.dump(self.config, f, indent=2)

    def _load_cache(self):
        if self.cache_path.exists():
            try:
                with open(self.cache_path, 'r', encoding="utf-8") as f:
                    cache = json.load(f)
                    timestamp = cache.get("timestamp", 0)
                    if not isinstance(timestamp, (int, float)) or abs(time.time() - timestamp) > 86400 * 2:  # Allow 2-day skew
                        logger.warning("Invalid cache timestamp. Resetting.")
                        return self._default_cache()
                    return cache
            except Exception as e:
                logger.error(f"Corrupted cache: {e}. Resetting.")
        return self._default_cache()

    def _save_cache(self):
        timestamp = time.time()
        with open(self.cache_path, 'w', encoding="utf-8") as f:
            json.dump({
                "data": self.cache.get("data"),
                "timestamp": timestamp,
                "call_count": self.cache.get("call_count", 0),
                "live_mode_warning_shown": self.cache.get("live_mode_warning_shown", False),
                "call_limit_warning_shown": self.cache.get("call_limit_warning_shown", False)
            }, f, indent=2)

    def _default_cache(self):
        return {"data": None, "timestamp": 0, "call_count": 0, "live_mode_warning_shown": False, "call_limit_warning_shown": False}

    def _apply_defaults(self):
        for key, val in self.defaults.items():
            if key not in self.config:
                self.config[key] = val
                self._save_config()

    def get(self, key: str, default=None):
        return self.config.get(key, default)

    def set(self, key: str, value):
        self.config[key] = value
        self._save_config()
        if key in ["api_key", "city"]:
            self.reset_cache()

    def reset_cache(self):
        self.cache = self._default_cache()
        self._save_cache()

    def update_cache_duration(self, duration: int):
        self.set("cache_duration", duration)
        self.reset_cache()
        mode = self._duration_to_mode(duration)
        logger.info(f"Cache mode updated to {mode} ({duration}s).")

    def _duration_to_mode(self, duration: int) -> str:
        mode_map = {30: "live", 300: "5min", 900: "15min", 1800: "30min", 3600: "60min"}
        return mode_map.get(duration, "custom")

def fetch_city_suggestions(config: WeatherConfig, query: str) -> list[dict]:
    api_key = config.get("api_key")
    if not api_key or not query:
        return []
    try:
        url = f"http://api.weatherapi.com/v1/search.json?key={api_key}&q={query}"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        return [{"id": f"{item['name']}, {item['region']}, {item['country']}", "title": f"{item['name']}, {item['region']}, {item['country']}"} for item in data]
    except Exception as e:
        logger.error(f"City suggestion error: {e}")
        return []

def validate_and_update_city(config: WeatherConfig, city: str) -> bool:
    city = city.strip()
    if not city or len(city) > 100 or not re.match(r'^[\w\s,.-]+$', city):  # Basic sanitization
        logger.error("Invalid city name.")
        return False
    api_key = config.get("api_key")
    if not api_key or not re.match(r'^[a-zA-Z0-9]{16}$', api_key):
        logger.error("Invalid API key.")
        return False
    try:
        url = f"http://api.weatherapi.com/v1/current.json?key={api_key}&q={city}&aqi=no"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            logger.error(f"API error: {data['error']['message']}")
            return False
        tz_id = data.get("location", {}).get("tz_id", "UTC")
        config.set("city", city)
        config.set("tz_id", tz_id)
        config.reset_cache()
        logger.info(f"City updated to {city} (TZ: {tz_id}).")
        return True
    except Exception as e:
        logger.error(f"City validation error: {e}")
        return False

def fetch_weather_data(config: WeatherConfig, retries: int = 3) -> dict | None:
    api_key, city = config.get("api_key"), config.get("city")
    if not api_key or not city:
        return None
    current_time = time.time()
    cache_duration = config.get("cache_duration", 1800)
    if cache_duration > 0 and config.cache["data"] and (current_time - config.cache["timestamp"]) < cache_duration:
        return config.cache["data"]
    if config.cache["timestamp"] and abs(current_time - config.cache["timestamp"]) > 86400:
        logger.info("Cache expired (24h). Resetting.")
        config.reset_cache()
    url = f"http://api.weatherapi.com/v1/current.json?key={api_key}&q={city}&aqi=no"
    total_wait = 0
    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 429:
                wait_time = min(2 ** attempt, 16)  # Cap at 16s
                total_wait += wait_time
                if total_wait > 30:  # Total timeout
                    logger.error("Rate limit timeout exceeded.")
                    return config.cache.get("data")
                logger.warning(f"Rate limit. Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                logger.error(f"API error: {data['error']['message']}")
                return config.cache.get("data")
            config.cache["data"] = data
            config.cache["timestamp"] = current_time
            config.cache["call_count"] = config.cache.get("call_count", 0) + 1
            if config.get("cache_duration") == 30 and not config.cache["live_mode_warning_shown"]:
                logger.warning("Live mode: Frequent calls may hit limits.")
                config.cache["live_mode_warning_shown"] = True
            if config.cache["call_count"] > 900000 and not config.cache["call_limit_warning_shown"]:
                logger.warning("Nearing 1M call limit. Upgrade plan.")
                config.cache["call_limit_warning_shown"] = True
            config._save_cache()
            return data
        except requests.exceptions.HTTPError as e:
            if response and response.status_code == 401:
                logger.error("Invalid API key.")
                return config.cache.get("data")
            raise
    logger.error("Fetch failed after retries.")
    return config.cache.get("data")

def get_weather_temp(config: WeatherConfig) -> str:
    data = fetch_weather_data(config)
    if not data or "current" not in data:
        return "N/A"
    temp_unit = config.get("temp_unit", "C")
    temp_precision = config.get("temp_precision", "integer")
    temp_key = "temp_f" if temp_unit == "F" else "temp_c"
    temp_value = data['current'].get(temp_key)
    if temp_value is None:
        return "N/A"
    if temp_precision == "integer":
        return f"{int(round(temp_value))}°{temp_unit}"
    return f"{temp_value:.1f}°{temp_unit}"

def get_city(config: WeatherConfig) -> str:
    return config.get("city", "Unknown")

def get_time(config: WeatherConfig) -> str:
    try:
        tz_id = config.get("tz_id", "UTC")
        tz = pytz.timezone(tz_id)
        utc_now = datetime.now(timezone.utc)
        local_time = utc_now.astimezone(tz)
        time_format = config.get("time_format", "12")
        fmt_map = {"12": "%I:%M %p", "12s": "%I:%M:%S %p", "24": "%H:%M", "24s": "%H:%M:%S"}
        fmt = fmt_map.get(time_format, "%I:%M %p")
        return local_time.strftime(fmt).lstrip("0")
    except pytz.UnknownTimeZoneError:
        logger.error(f"Invalid timezone: {tz_id}. Falling back to UTC.")
        return datetime.now(timezone.utc).strftime("%I:%M %p").lstrip("0")
    except Exception as e:
        logger.error(f"Time error: {e}")
        return datetime.now(timezone.utc).strftime("%I:%M %p").lstrip("0")

def get_weather_state(config: WeatherConfig) -> str:
    data = fetch_weather_data(config)
    return data["current"]["condition"]["text"].lower() if data and "current" in data and "condition" in data["current"] else "unknown"

def get_weather_icon(config: WeatherConfig) -> str:
    data = fetch_weather_data(config)
    if data and "current" in data and "condition" in data["current"]:
        return data["current"]["condition"]["icon"]  # Use API's direct icon URL (handles day/night)
    return ""

# UI Setup (assuming external UI lib like 'UI', 'Tab')
def NightyWeather():
    IMAGE_URL = "https://i.imgur.com/m0xu9yk.gif"
    config = WeatherConfig(getScriptsPath() + "/scriptData")
    if not config.get("api_key") or not config.get("city"):
        logger.info("Set API key and city in GUI.")

    def update_api_key(value: str):
        if re.match(r'^[a-zA-Z0-9]{16}$', value):
            config.set("api_key", value)
            config.reset_cache()
            logger.info("API key updated!")
        else:
            logger.error("Invalid API key format.")

    def update_city(value: str):
        if validate_and_update_city(config, value):
            pass  # Success logged in validate

    def update_time_format(selected: list):
        config.set("time_format", selected[0])

    def update_temp_unit(selected: list):
        config.set("temp_unit", selected[0])
        config.reset_cache()

    def update_temp_precision(selected: list):
        config.set("temp_precision", selected[0])
        config.reset_cache()

    def update_cache_mode(selected: list):
        mode_map = {"live": 30, "5min": 300, "15min": 900, "30min": 1800, "60min": 3600}
        duration = mode_map.get(selected[0], 1800)
        config.update_cache_duration(duration)
        if selected[0] == "live" and not config.cache["live_mode_warning_shown"]:
            logger.warning("Live mode: May hit API limits.")
            config.cache["live_mode_warning_shown"] = True
            config._save_cache()

    def open_weatherapi():
        webbrowser.open("https://www.weatherapi.com/")
        logger.info("Opening WeatherAPI...")

    # Cache modes for UI
    cache_modes = [
        {"id": "live", "title": "Live (30s, may hit limits) ⚠️"},
        {"id": "5min", "title": "Every 5 Min 🕐"},
        {"id": "15min", "title": "Every 15 Min ⏰"},
        {"id": "30min", "title": "Every 30 Min ☕"},
        {"id": "60min", "title": "Every 60 Min 🌤️"}
    ]
    selected_mode = config._duration_to_mode(config.get("cache_duration", 1800))

    tab = Tab(name="NightyWeather", title="Weather & Time 🌦️", icon="sun")
    container = tab.create_container(type="rows")
    card = container.create_card(height="full", width="full", gap=3)

    # Image
    try:
        card.create_ui_element(
            UI.Image, url=IMAGE_URL, alt="Weather Showcase",
            width="100%", height="200px", rounded="md", fill_type="contain",
            border_color="#4B5EAA", border_width=2, margin="m-2", shadow=True
        )
    except Exception as e:
        logger.error(f"Image load failed: {e}")

    # Inputs/Selects
    card.create_ui_element(UI.Input, label="API Key 🔑", show_clear_button=True, full_width=True, required=True,
                           onInput=update_api_key, value=config.get("api_key"))
    card.create_ui_element(UI.Input, label="City 🏙️", show_clear_button=True, full_width=True, required=True,
                           onInput=update_city, value=config.get("city"), autocomplete=True,
                           onAutocomplete=lambda q: fetch_city_suggestions(config, q))
    card.create_ui_element(UI.Select, label="Time Format ⏰", full_width=True, mode="single",
                           items=[{"id": k, "title": v} for k, v in {
                               "12": "12-hour (e.g., 7:58 AM)", "12s": "12-hour with seconds (e.g., 7:58:23 AM)",
                               "24": "24-hour (e.g., 19:58)", "24s": "24-hour with seconds (e.g., 19:58:23)"
                           }.items()], selected_items=[config.get("time_format")], onChange=update_time_format)
    card.create_ui_element(UI.Select, label="Temperature Unit 🌡️", full_width=True, mode="single",
                           items=[{"id": "C", "title": "Celsius (°C)"}, {"id": "F", "title": "Fahrenheit (°F)"}],
                           selected_items=[config.get("temp_unit")], onChange=update_temp_unit)
    card.create_ui_element(UI.Select, label="Temperature Precision 🔍", full_width=True, mode="single",
                           items=[{"id": "integer", "title": "Integer (e.g., 21°)"}, {"id": "decimal", "title": "Decimal (e.g., 21.4°)"}],
                           selected_items=[config.get("temp_precision")], onChange=update_temp_precision)
    card.create_ui_element(UI.Select, label="Cache Mode ⚙️", full_width=True, mode="single",
                           items=cache_modes, selected_items=[selected_mode], onChange=update_cache_mode)

    # Info texts
    card.create_ui_element(UI.Text, content=(
        "🌤️ {weatherTemp}: Current temperature in your chosen unit and precision (e.g., 22°C or 72.4°F)\n"
        "🏙️ {city}: Your selected city or location (e.g., Seoul or New York)\n"
        "🕐 {time}: Local time for the selected city (e.g., 7:58 PM or 19:58:23)\n"
        "☁️ {weatherState}: Current weather condition description (e.g., sunny, partly cloudy, or rainy)\n"
        "🖼️ {weathericon}: Displays the current weather condition as a small icon image, automatically updated based on real-time weather data (e.g., a sun icon for sunny weather)"
    ), full_width=True)
    card.create_ui_element(UI.Text, content="ℹ️ Wait 30min after WeatherAPI signup for key approval.", full_width=True)

    card.create_ui_element(UI.Button, label="Visit WeatherAPI 🌐", variant="solid", size="md", color="default",
                           full_width=True, onClick=open_weatherapi)

    # Register RPC values
    addDRPCValue("weatherTemp", lambda: get_weather_temp(config))
    addDRPCValue("city", lambda: get_city(config))
    addDRPCValue("time", lambda: get_time(config))
    addDRPCValue("weatherState", lambda: get_weather_state(config))
    addDRPCValue("weathericon", lambda: get_weather_icon(config))

    logger.info("NightyWeather running 🌤️")
    tab.render()
