import webbrowser
from datetime import datetime, timezone
import os
import json
import requests

def NightyWeather():
    SCRIPT_DATA_DIR = f"{getScriptsPath()}/scriptData"
    CONFIG_PATH = f"{SCRIPT_DATA_DIR}/NightyWeather.json"
    CACHE_PATH = f"{SCRIPT_DATA_DIR}/NightyWeatherCache.json"
    os.makedirs(SCRIPT_DATA_DIR, exist_ok=True)

    class Settings:
        defaults = {
            "api_key": "",
            "city": "Seoul",
            "cache_duration": 900,   # 15 minutes
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
            except Exception:
                print("Corrupted config. Resetting.", type="ERROR")
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
                return self._default()
            try:
                with open(CACHE_PATH, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                    for k, v in self._default().items():
                        if k not in cache:
                            cache[k] = v
                    return cache
            except Exception:
                print("Corrupted cache. Resetting.", type="ERROR")
                return self._default()

        def _default(self):
            return {
                "data": None,
                "timestamp": 0,
                "call_count": 0,
                "call_limit_warning_shown": False
            }

        def save(self):
            tmp_path = CACHE_PATH + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmp_path, CACHE_PATH)

    settings = Settings()
    cache = Cache()

    def update_api_key(value):
        settings.update("api_key", value)
        reset_cache()
        print("API key updated! Weather data will refresh automatically. 🌤️", type="SUCCESS")

    def reset_cache():
        cache.data["data"] = None
        cache.data["timestamp"] = 0
        cache.data["call_count"] = 0
        cache.data["call_limit_warning_shown"] = False
        cache.save()

    # ==================== TIME (Auto-detected, 12-hour format) ====================
    def get_time():
        try:
            now = datetime.now()                    # Uses your system's local time
            time_str = now.strftime("%I:%M %p")     # 12-hour with AM/PM
            
            # Remove leading zero (7:58 PM instead of 07:58 PM)
            if time_str.startswith("0"):
                time_str = time_str[1:]
                
            return time_str
        except Exception:
            return datetime.now().strftime("%I:%M %p")

    if not settings.get("api_key"):
        print("Please set your WeatherAPI key in the input field. 🌟", type="INFO")

    # Minimal UI: ONLY the API Key input
    tab = Tab(name="NightyWeather", title="Weather & Time 🌦️", icon="sun")
    container = tab.create_container(type="rows")
    card = container.create_card(height="full", width="full", gap=3)

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

    # ---------------------------
    # Fetch weather data (cached every 15 min, single attempt)
    # ---------------------------
    def fetch_weather_data():
        try:
            api_key = settings.get("api_key")
            if not api_key:
                return None

            current_time = datetime.now(timezone.utc).timestamp()
            cache_duration = 900  # 15 minutes fixed

            # Use cache if still fresh
            if cache.data.get("data") and (current_time - cache.data.get("timestamp", 0)) < cache_duration:
                return cache.data["data"]

            url = "https://api.weatherapi.com/v1/current.json"
            params = {"key": api_key, "q": "Seoul", "aqi": "no"}
            session = requests.Session()

            resp = session.get(url, params=params, timeout=(5, 10))
            resp.raise_for_status()
            data = resp.json()

            if isinstance(data, dict) and "error" in data:
                print(f"WeatherAPI error: {data['error'].get('message')}", type="ERROR")
                return cache.data.get("data")

            cache.data["data"] = data
            cache.data["timestamp"] = current_time
            cache.data["call_count"] = cache.data.get("call_count", 0) + 1
            cache.save()
            return data

        except requests.exceptions.HTTPError as e:
            status = getattr(e.response, "status_code", None)
            if status == 401:
                print("Invalid API key.", type="ERROR")
            else:
                print(f"HTTP error {status}.", type="ERROR")
            return cache.data.get("data")
        except Exception as e:
            print(f"Request failed: {str(e)}", type="WARNING")
            return cache.data.get("data")

    # ---------------------------
    # Getters
    # ---------------------------
    def get_weather_temp():
        data = fetch_weather_data()
        if not data or "current" not in data:
            return "N/A"
        raw_temp = data["current"].get("temp_c")
        if raw_temp is None:
            return "N/A"
        temp = int(round(raw_temp))        # Integer only
        return f"{temp}°C"

    def get_city():
        return "Seoul"

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

    addDRPCValue("weatherTemp", get_weather_temp)
    addDRPCValue("city", get_city)
    addDRPCValue("time", get_time)
    addDRPCValue("weatherState", get_weather_state)
    addDRPCValue("weathericon", get_weather_icon)

    print("NightyWeather running 🌤️ (Seoul + Auto 12H time)", type="SUCCESS")
    tab.render()