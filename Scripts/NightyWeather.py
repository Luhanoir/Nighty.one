import webbrowser
import time
import json
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
import threading

class NightyWeather:
    """A class to manage weather and time display with caching and configuration."""
    RETRIES = 3
    IMAGE_URL = "https://i.imgur.com/m0xu9yk.gif"
    DEFAULTS = {
        "api_key": "", "city": "", "utc_offset": 0.0,
        "time_format": "12", "temp_unit": "C", "temp_precision": "int", "cache_duration": 1800
    }
    CACHE_MODES = {
        "live": 30, "5min": 300, "15min": 900, "30min": 1800, "60min": 3600
    }

    def __init__(self, script_data_dir):
        self.script_data_dir = Path(script_data_dir) / "scriptData"
        self.config_path = self.script_data_dir / "NightyWeather.json"
        self.cache_path = self.script_data_dir / "NightyWeatherCache.json"
        self.script_data_dir.mkdir(parents=True, exist_ok=True)
        self.cache = self._load_cache()
        self._initialize_settings()
        self._setup_ui()

    def _load_cache(self):
        """Load and validate cache from file."""
        if not self.cache_path.exists():
            return {"data": None, "timestamp": 0, "call_count": 0, "live_mode_warning_shown": False, "call_limit_warning_shown": False}
        try:
            with self.cache_path.open('r', encoding="utf-8") as f:
                cache = json.load(f)
                timestamp = cache.get("timestamp", 0)
                if not isinstance(timestamp, (int, float)) or timestamp < 0:
                    print("Invalid cache timestamp. Resetting cache.", type_="WARNING")
                    return {"data": None, "timestamp": 0, "call_count": 0, "live_mode_warning_shown": False, "call_limit_warning_shown": False}
                return cache
        except Exception:
            print("Corrupted cache file. Resetting cache.", type_="ERROR")
            return {"data": None, "timestamp": 0, "call_count": 0, "live_mode_warning_shown": False, "call_limit_warning_shown": False}

    def _save_cache(self, data=None, timestamp=None, call_count=0, live_mode_warning_shown=False, call_limit_warning_shown=False):
        """Save cache to file with UTC timestamp."""
        timestamp = timestamp or datetime.now(timezone.utc).timestamp()
        cache_data = {
            "data": data,
            "timestamp": timestamp,
            "call_count": call_count,
            "live_mode_warning_shown": live_mode_warning_shown,
            "call_limit_warning_shown": call_limit_warning_shown
        }
        with self.cache_path.open('w', encoding="utf-8") as f:
            json.dump(cache_data, f, indent=2)

    def _get_setting(self, key=None):
        """Retrieve a single setting or all settings."""
        if not self.config_path.exists():
            return None if key else {}
        try:
            with self.config_path.open('r', encoding="utf-8") as f:
                data = json.load(f)
                return data.get(key) if key else data
        except Exception:
            return None if key else {}

    def _update_setting(self, key, value):
        """Update a setting and save to file."""
        settings = self._get_setting() or {}
        settings[key] = value
        with self.config_path.open('w', encoding="utf-8") as f:
            json.dump(settings, f, indent=2)

    def _initialize_settings(self):
        """Initialize default settings if not present."""
        for key, val in self.DEFAULTS.items():
            if self._get_setting(key) is None:
                self._update_setting(key, val)

    def _reset_cache(self):
        """Reset cache and related metadata."""
        self.cache["data"] = None
        self.cache["timestamp"] = 0
        self.cache["call_count"] = 0
        self.cache["live_mode_warning_shown"] = False
        self.cache["call_limit_warning_shown"] = False
        self._save_cache()

    def update_api_key(self, value):
        """Update API key and reset cache."""
        self._update_setting("api_key", value)
        self._reset_cache()
        print("API key updated! Weather data will refresh automatically. 🌤️", type_="SUCCESS")

    def update_city(self, value):
        """Update city and reset cache."""
        value = value.strip()
        if value and len(value) <= 100:
            self._update_setting("city", value)
            self._reset_cache()
            print("City updated! Weather data will refresh automatically. 🏙️", type_="SUCCESS")
        else:
            print("Invalid city name (e.g., 'Seoul').", type_="ERROR")

    def update_utc_offset(self, selected):
        """Update UTC offset."""
        try:
            offset = float(selected[0])
            if -14 <= offset <= 14:
                self._update_setting("utc_offset", offset)
                print("UTC offset updated! Time will refresh automatically. 🌍", type_="SUCCESS")
            else:
                print("UTC offset must be between -14 and +14.", type_="ERROR")
        except ValueError:
            print("Invalid UTC offset.", type_="ERROR")

    def update_time_format(self, selected):
        """Update time format."""
        self._update_setting("time_format", selected[0])
        print("Time format updated! Time display will refresh automatically. ⏰", type_="SUCCESS")

    def update_temp_unit(self, selected):
        """Update temperature unit."""
        self._update_setting("temp_unit", selected[0])
        print("Temperature unit updated! Display will refresh automatically. 🌡️", type_="SUCCESS")

    def update_temp_precision(self, selected):
        """Update temperature precision."""
        self._update_setting("temp_precision", selected[0])
        print("Temperature precision updated! Display will refresh automatically. 📐", type_="SUCCESS")

    def update_cache_mode(self, selected):
        """Update cache mode and reset cache if needed."""
        new_duration = self.CACHE_MODES.get(selected[0], 1800)
        self._update_setting("cache_duration", new_duration)
        self._reset_cache()
        print(f"Cache mode updated to {selected[0]}! Data refreshes every {new_duration}s. ⚙️", type_="SUCCESS")
        if selected[0] == "live" and not self.cache["live_mode_warning_shown"]:
            print("Live mode (30s): Frequent calls may hit limits. ⚠️", type_="WARNING")
            self.cache["live_mode_warning_shown"] = True
            self._save_cache(live_mode_warning_shown=True)

    def _fetch_weather_data(self):
        """Fetch weather data from API or return cached data."""
        api_key = self._get_setting("api_key")
        city = self._get_setting("city")
        if not api_key or not city:
            return None

        current_time = datetime.now(timezone.utc).timestamp()
        cache_duration = self._get_setting("cache_duration") or 1800
        if cache_duration > 0 and self.cache["data"] and (current_time - self.cache["timestamp"]) < cache_duration:
            return self.cache["data"]

        if self.cache["timestamp"] and (current_time - self.cache["timestamp"]) > 86400:
            print("Cache expired (24h). Resetting.", type_="INFO")
            self._reset_cache()

        url = f"http://api.weatherapi.com/v1/current.json?key={api_key}&q={city}&aqi=no"
        for attempt in range(self.RETRIES):
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
                    return self.cache["data"] if self.cache["data"] else None
                self.cache["data"] = data
                self.cache["timestamp"] = current_time
                self.cache["call_count"] += 1
                if self._get_setting("cache_duration") == 30 and not self.cache["live_mode_warning_shown"]:
                    print("Live mode (30s): Frequent calls may hit limits. ⚠️", type_="WARNING")
                    self.cache["live_mode_warning_shown"] = True
                if self.cache["call_count"] > 900000 and not self.cache["call_limit_warning_shown"]:
                    print("Nearing 1M call limit. Adjust cache or upgrade. 📊", type_="WARNING")
                    self.cache["call_limit_warning_shown"] = True
                self._save_cache(data, current_time, self.cache["call_count"], self.cache["live_mode_warning_shown"], self.cache["call_limit_warning_shown"])
                return data
            except requests.exceptions.HTTPError as e:
                if response and response.status_code == 401:
                    return self.cache["data"] if self.cache["data"] else None
                print(f"Fetch error: {str(e)}", type_="ERROR")
                return self.cache["data"] if self.cache["data"] else None
        print("Fetch failed after retries. Using cache if available.", type_="ERROR")
        return self.cache["data"] if self.cache["data"] else None

    def get_weather_temp(self):
        """Get formatted temperature."""
        data = self._fetch_weather_data()
        if not data or "current" not in data:
            return "N/A"
        temp_unit = self._get_setting("temp_unit") or "C"
        temp_key = "temp_f" if temp_unit == "F" else "temp_c"
        temp_precision = self._get_setting("temp_precision") or "int"
        raw_temp = data['current'].get(temp_key)
        if raw_temp is None:
            return "N/A"
        if temp_precision == "int":
            temp = int(round(raw_temp))
            return f"{temp}°{temp_unit}"
        return f"{round(raw_temp, 1):.1f}°{temp_unit}"

    def get_city(self):
        """Get city name."""
        return self._get_setting("city") or "Unknown"

    def get_time(self):
        """Get formatted local time based on UTC offset."""
        try:
            utc_offset = float(self._get_setting("utc_offset") or 0.0)
            time_format = self._get_setting("time_format") or "12"
            if not -14 <= utc_offset <= 14:
                raise ValueError("Invalid UTC offset")
            utc_now = datetime.now(timezone.utc)
            target_time = utc_now + timedelta(seconds=int(utc_offset * 3600))
            formats = {
                "12": "%I:%M %p",
                "12s": "%I:%M:%S %p",
                "24": "%H:%M",
                "24s": "%H:%M:%S"
            }
            return target_time.strftime(formats.get(time_format, "%I:%M %p")).lstrip("0")
        except Exception as e:
            print(f"Time error: {str(e)}", type_="ERROR")
            return datetime.now(timezone.utc).strftime("%I:%M %p").lstrip("0")

    def get_weather_state(self):
        """Get current weather condition."""
        data = self._fetch_weather_data()
        return data["current"]["condition"]["text"].lower() if data and "current" in data and "condition" in data["current"] else "unknown"

    def get_weather_icon(self):
        """Get weather icon URL."""
        data = self._fetch_weather_data()
        if data and "current" in data and "condition" in data["current"]:
            icon_url = data["current"]["condition"]["icon"]
            if icon_url:
                return "https:" + icon_url.replace("64x64", "128x128")
        return ""

    def _setup_ui(self):
        """Set up the user interface."""
        if not self._get_setting("api_key") or not self._get_setting("city"):
            print("Set API key and city in GUI. 🌟", type_="INFO")

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
        selected_mode = next((k for k, v in self.CACHE_MODES.items() if v == self._get_setting("cache_duration")), "30min")

        tab = Tab(name="NightyWeather", title="Weather & Time 🌦️", icon="sun")
        container = tab.create_container(type="rows")
        card = container.create_card(height="full", width="full", gap=3)

        try:
            card.create_ui_element(
                UI.Image,
                url=self.IMAGE_URL,
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

        card.create_ui_element(UI.Input, label="API Key 🔑", show_clear_button=True, full_width=True, required=True, onInput=self.update_api_key, value=self._get_setting("api_key"))
        card.create_ui_element(UI.Input, label="City 🏙️", show_clear_button=True, full_width=True, required=True, onInput=self.update_city, value=self._get_setting("city"))
        card.create_ui_element(UI.Select, label="UTC Offset 🌍", full_width=True, mode="single", items=offset_items, selected_items=[str(self._get_setting("utc_offset"))], onChange=self.update_utc_offset)
        card.create_ui_element(UI.Select, label="Time Format ⏰", full_width=True, mode="single", items=[
            {"id": "12", "title": "12-hour (e.g., 7:58 AM)"},
            {"id": "12s", "title": "12-hour with seconds (e.g., 7:58:23 AM)"},
            {"id": "24", "title": "24-hour (e.g., 19:58)"},
            {"id": "24s", "title": "24-hour with seconds (e.g., 19:58:23)"}
        ], selected_items=[self._get_setting("time_format")], onChange=self.update_time_format)
        card.create_ui_element(UI.Select, label="Temperature Unit 🌡️", full_width=True, mode="single", items=[
            {"id": "C", "title": "Celsius (°C)"},
            {"id": "F", "title": "Fahrenheit (°F)"}
        ], selected_items=[self._get_setting("temp_unit")], onChange=self.update_temp_unit)
        card.create_ui_element(UI.Select, label="Temperature Precision 📏", full_width=True, mode="single", items=[
            {"id": "int", "title": "Integer (e.g., 22°C)"},
            {"id": "1dec", "title": "One Decimal (e.g., 21.7°C)"}
        ], selected_items=[self._get_setting("temp_precision")], onChange=self.update_temp_precision)
        card.create_ui_element(UI.Select, label="Cache Mode ⚙️", full_width=True, mode="single", items=cache_modes, selected_items=[selected_mode], onChange=self.update_cache_mode)
        card.create_ui_element(UI.Text, content="🌤️ {weatherTemp}: Current temperature\n🏙️ {city}: Selected city\n🕐 {time}: Local time\n☁️ {weatherState}: Weather condition\n🖼️ {weathericon}: Weather icon", full_width=True)
        card.create_ui_element(UI.Text, content="ℹ️ Wait 30min after WeatherAPI signup for key approval.", full_width=True)
        card.create_ui_element(
            UI.Button,
            label="Visit WeatherAPI 🌐",
            variant="solid",
            size="md",
            color="default",
            full_width=True,
            onClick=lambda: (webbrowser.open("https://www.weatherapi.com/"), print("Opening WeatherAPI website... 🌐", type_="INFO"))
        )

        addDRPCValue("weatherTemp", self.get_weather_temp)
        addDRPCValue("city", self.get_city)
        addDRPCValue("time", self.get_time)
        addDRPCValue("weatherState", self.get_weather_state)
        addDRPCValue("weathericon", self.get_weather_icon)

        print("NightyWeather running 🌤️", type_="SUCCESS")
        tab.render()

def run_nighty_weather(script_data_dir):
    """Run the NightyWeather application."""
    NightyWeather(script_data_dir)
