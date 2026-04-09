import webbrowser
import time
from datetime import datetime, timezone, timedelta
import os
import json
import requests
import re
import threading

def NightyWeather():
    RETRIES = 4
    IMAGE_URL = "https://i.imgur.com/m0xu9yk.gif"
    SCRIPT_DATA_DIR = f"{getScriptsPath()}/scriptData"
    CONFIG_PATH = f"{SCRIPT_DATA_DIR}/NightyWeather.json"
    CACHE_PATH = f"{SCRIPT_DATA_DIR}/NightyWeatherCache.json"
    os.makedirs(SCRIPT_DATA_DIR, exist_ok=True)

    class Settings:
        """Manages settings for modularity and future extensions."""
        defaults = {
            "api_key": "18f4909568ec442da5e210931260603", "city": "Seoul", "utc_offset": 9.0,
            "time_format": "12", "temp_unit": "C", "temp_precision": "int",
            "cache_duration": 900, "show_date": False  # increased default cache duration
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
            except json.JSONDecodeError:
                print("Corrupted JSON in config. Resetting.", type="ERROR")
                return None
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
        """Manages cache for robustness and future extensions."""
        def __init__(self):
            self.data = self.load()
            if not isinstance(self.data, dict):
                self.data = self._default()

        def load(self):
            if not os.path.exists(CACHE_PATH):
                return self._default()
            try:
                with open(CACHE_PATH, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                    timestamp = cache.get("timestamp", 0)
                    if not isinstance(timestamp, (int, float)) or timestamp < 0:
                        print("Invalid cache timestamp. Resetting.", type="WARNING")
                        return self._default()
                    # Ensure required keys exist
                    for k, v in self._default().items():
                        if k not in cache:
                            cache[k] = v
                    return cache
            except json.JSONDecodeError:
                print("Corrupted JSON in cache. Resetting.", type="ERROR")
                return self._default()
            except Exception:
                print("Corrupted cache. Resetting.", type="ERROR")
                return self._default()

        def _default(self):
            return {
                "data": None,
                "timestamp": 0,
                "call_count": 0,
                "call_limit_warning_shown": False,
                "icon_url": "",
                "cooldown_until": 0
            }

        def save(self):
            # Atomic write to reduce corruption risk
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

    def update_city(value):
        value = value.strip()
        if value and len(value) <= 100 and re.match(r"^[\w\s\-,\u00C0-\u017F]+$", value):
            settings.update("city", value)
            reset_cache()
            print("City updated! Weather data will refresh automatically. 🏙️", type="SUCCESS")
        else:
            print("Invalid city name (e.g., 'Seoul'; no special chars).", type="ERROR")

    def update_utc_offset(selected):
        try:
            offset = float(selected[0])
            if -14 <= offset <= 14:
                settings.update("utc_offset", offset)
                print("UTC offset updated! Time will refresh automatically. 🌍", type="SUCCESS")
            else:
                print("UTC offset must be between -14 and +14.", type="ERROR")
        except ValueError:
            print("Invalid UTC offset.", type="ERROR")

    def update_time_format(selected):
        settings.update("time_format", selected[0])
        print("Time format updated! Time display will refresh automatically. ⏰", type="SUCCESS")

    def update_temp_unit(selected):
        settings.update("temp_unit", selected[0])
        print("Temperature unit updated! Display will refresh automatically. 🌡️", type="SUCCESS")

    def update_temp_precision(selected):
        settings.update("temp_precision", selected[0])
        print("Temperature precision updated! Display will refresh automatically. 📐", type="SUCCESS")

    def update_cache_mode(selected):
        mode_map = {"5min": 300, "15min": 900, "30min": 1800, "60min": 3600}
        new_duration = mode_map.get(selected[0], 900)
        settings.update("cache_duration", max(new_duration, 300))
        reset_cache()
        print(f"Cache mode updated to {selected[0]}! Data refreshes every {new_duration}s. ⚙️", type="SUCCESS")

    def update_show_date(selected):
        settings.update("show_date", selected[0] == "yes")
        print("Date display updated! Time will refresh automatically. 📅", type="SUCCESS")

    def reset_cache():
        cache.data = cache._default()
        cache.save()

    if not settings.get("api_key") or not settings.get("city"):
        print("Set API key and city in GUI. 🌟", type="INFO")

    utc_offsets = sorted([
        -12.0, -11.0, -10.0, -9.5, -9.0, -8.0, -7.0, -6.0, -5.0,
        -4.5, -4.0, -3.5, -3.0, -2.0, -1.0,
        0.0,
        1.0, 2.0, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 5.75,
        6.0, 6.5, 7.0, 8.0, 8.5, 9.0, 9.5,
        10.0, 10.5, 11.0, 12.0, 12.75, 13.0, 14.0
    ])

    offset_items = [
        {
            "id": str(off),
            "title": (
                f"UTC{'-' if off < 0 else '+'}"
                f"{abs(int(off)):02d}:"
                f"{int((abs(off) - int(abs(off))) * 60):02d}"
            )
        }
        for off in utc_offsets
    ]

    cache_modes = [
        {"id": "5min", "title": "Every 5 Min 🕐"},
        {"id": "15min", "title": "Every 15 Min ⏰"},
        {"id": "30min", "title": "Every 30 Min ☕"},
        {"id": "60min", "title": "Every 60 Min 🌤️"}
    ]
    mode_reverse = {300: "5min", 900: "15min", 1800: "30min", 3600: "60min"}
    selected_mode = mode_reverse.get(settings.get("cache_duration"), "15min")

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
        print(f"Failed to load image: {str(e)}. Showing placeholder.", type="ERROR")
        card.create_ui_element(
            UI.Text,
            content="⚠️ Unable to load weather image.",
            full_width=True
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
        onChange=update_utc_offset
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
        selected_items=[settings.get("temp_unit")],
        onChange=update_temp_unit
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
        UI.Select,
        label="Show Date with Time 📅",
        full_width=True,
        mode="single",
        items=[
            {"id": "yes", "title": "Yes (e.g., 7:58 PM - Oct 22)"},
            {"id": "no", "title": "No"}
        ],
        selected_items=["yes" if settings.get("show_date") else "no"],
        onChange=update_show_date
    )

    card.create_ui_element(
        UI.Text,
        content=(
            "🌤️ {weatherTemp}: Current temperature (e.g., 22°C)\n"
            "🏙️ {city}: Selected city\n"
            "🕐 {time}: Local time (with optional date)\n"
            "☁️ {weatherState}: Weather condition\n"
            "🖼️ {weathericon}: Weather icon"
        ),
        full_width=True
    )
    card.create_ui_element(
        UI.Text,
        content="ℹ️ Wait 30min after WeatherAPI signup for key approval.",
        full_width=True
    )

    def open_weatherapi():
        webbrowser.open("https://www.weatherapi.com/")
        print("Opening WeatherAPI website... 🌐", type="INFO")

    card.create_ui_element(
        UI.Button,
        label="Visit WeatherAPI 🌐",
        variant="solid",
        size="md",
        color="default",
        full_width=True,
        onClick=open_weatherapi
    )

    # ---------------------------
    # Robust fetch implementation (HTTPS only)
    # Single fetch loop updates cache; getters read cache only.
    # ---------------------------
    def fetch_weather_data():
        """
        Fetch current weather from WeatherAPI with retries, backoff, and caching.
        Always uses HTTPS. Returns parsed JSON on success or cached data on failure.
        This function is intended to be called only by the background fetch loop.
        """
        try:
            api_key = settings.get("api_key")
            city = settings.get("city")
            if not api_key or not city:
                return None

            current_time = datetime.now(timezone.utc).timestamp()
            cache_duration = max(settings.get("cache_duration") or 900, 300)

            # If in cooldown due to previous 429, skip network and return cached data
            cooldown_until = cache.data.get("cooldown_until", 0)
            if cooldown_until and current_time < cooldown_until:
                print("In cooldown after 429; using cached data.", type="INFO")
                return cache.data.get("data")

            # Use cached data if still fresh
            if cache.data.get("data") and (current_time - cache.data.get("timestamp", 0)) < cache_duration:
                return cache.data["data"]

            # If cache is older than 24h, reset to avoid stale state
            if cache.data.get("timestamp") and (current_time - cache.data.get("timestamp", 0)) > 86400:
                print("Cache expired (24h). Resetting.", type="INFO")
                reset_cache()

            url = "https://api.weatherapi.com/v1/current.json"
            params = {"key": api_key, "q": city, "aqi": "no"}
            session = requests.Session()

            backoff_base = 2
            connect_timeout = 5  # seconds
            read_timeout = 10    # seconds

            last_exception = None
            for attempt in range(1, RETRIES + 1):
                try:
                    resp = session.get(
                        url,
                        params=params,
                        timeout=(connect_timeout, read_timeout)
                    )

                    if resp.status_code == 429:
                        # On 429, set a cooldown and stop retrying aggressively.
                        wait_time = backoff_base ** attempt
                        cooldown = cache_duration  # use cache duration as cooldown window
                        cache.data["cooldown_until"] = current_time + cooldown
                        cache.data["timestamp"] = current_time  # mark timestamp so getters use cache
                        cache.save()
                        print(f"Rate limit hit (429). Entering cooldown for {cooldown}s.", type="WARNING")
                        last_exception = requests.exceptions.RetryError("429 rate limited")
                        # Do not retry further; break and return cached data
                        break

                    resp.raise_for_status()
                    data = resp.json()

                    if isinstance(data, dict) and "error" in data:
                        msg = data["error"].get("message", "Unknown API error")
                        print(f"WeatherAPI error: {msg}", type="ERROR")
                        return cache.data.get("data")

                    # Update cache with fetched data
                    cache.data["data"] = data
                    cache.data["timestamp"] = current_time
                    cache.data["call_count"] = cache.data.get("call_count", 0) + 1
                    cache.data["cooldown_until"] = 0

                    # Extract and normalize icon URL once and store it
                    icon_url = ""
                    try:
                        icon_url = data["current"]["condition"].get("icon", "") if data and "current" in data else ""
                        if icon_url:
                            if icon_url.startswith("//"):
                                icon_url = "https:" + icon_url
                            elif icon_url.startswith("/"):
                                icon_url = "https://api.weatherapi.com" + icon_url
                            icon_url = icon_url.replace("64x64", "128x128")
                    except Exception:
                        icon_url = ""

                    cache.data["icon_url"] = icon_url

                    if cache.data["call_count"] > 900000 and not cache.data.get("call_limit_warning_shown"):
                        print("Nearing 1M call limit. Adjust cache or upgrade. 📊", type="WARNING")
                        cache.data["call_limit_warning_shown"] = True

                    cache.save()
                    # Trigger UI/RPC refresh after successful fetch
                    try:
                        tab.render()
                    except Exception:
                        pass
                    return data

                except requests.exceptions.ConnectTimeout as e:
                    last_exception = e
                    wait_time = backoff_base ** attempt
                    print(
                        f"Connect timed out. Retrying in {wait_time}s... "
                        f"(attempt {attempt}/{RETRIES})",
                        type="WARNING"
                    )
                    time.sleep(wait_time)
                except requests.exceptions.ReadTimeout as e:
                    last_exception = e
                    wait_time = backoff_base ** attempt
                    print(
                        f"Read timed out. Retrying in {wait_time}s... "
                        f"(attempt {attempt}/{RETRIES})",
                        type="WARNING"
                    )
                    time.sleep(wait_time)
                except requests.exceptions.HTTPError as e:
                    status = getattr(e.response, "status_code", None)
                    if status == 401:
                        print("Invalid API key.", type="ERROR")
                        return cache.data.get("data")
                    if 400 <= (status or 0) < 500:
                        print(f"HTTP error {status}. Not retrying.", type="ERROR")
                        return cache.data.get("data")
                    last_exception = e
                    wait_time = backoff_base ** attempt
                    print(
                        f"Server error {status}. Retrying in {wait_time}s... "
                        f"(attempt {attempt}/{RETRIES})",
                        type="WARNING"
                    )
                    time.sleep(wait_time)
                except requests.exceptions.RequestException as e:
                    last_exception = e
                    wait_time = backoff_base ** attempt
                    print(
                        f"Request failed: {e}. Retrying in {wait_time}s... "
                        f"(attempt {attempt}/{RETRIES})",
                        type="WARNING"
                    )
                    time.sleep(wait_time)

            if last_exception:
                print(f"Fetch failed after {RETRIES} attempts: {last_exception}", type="ERROR")
            else:
                print(f"Fetch failed after {RETRIES} attempts.", type="ERROR")

            return cache.data.get("data")
        except Exception as e:
            print(f"Fetch error: {str(e)}", type="ERROR")
            return cache.data.get("data")

    # ---------------------------
    # Helper getters (read cache only; no network I/O)
    # ---------------------------
    def get_weather_temp():
        data = cache.data.get("data")
        if not data or "current" not in data:
            return "N/A"
        temp_unit = settings.get("temp_unit") or "C"
        temp_key = "temp_f" if temp_unit == "F" else "temp_c"
        temp_precision = settings.get("temp_precision") or "int"
        raw_temp = data["current"].get(temp_key)
        if raw_temp is None:
            return "N/A"
        if temp_precision == "int":
            temp = int(round(raw_temp))
        else:
            temp = round(raw_temp, 1)
        return f"{temp:.{0 if temp_precision == 'int' else 1}f}°{temp_unit}"

    def get_city():
        return settings.get("city") or "Unknown"

    def get_time():
        try:
            utc_offset = float(settings.get("utc_offset") or 0.0)
            utc_offset = max(min(utc_offset, 14), -14)
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
                fmt = "%I:%M %p"

            time_str = target_time.strftime(fmt)

            if time_format.startswith("12"):
                if time_str.startswith("0"):
                    time_str = time_str[1:]
                if time_str.startswith("00:"):
                    time_str = "12:" + time_str[3:]

            if show_date:
                date_str = target_time.strftime("%b %d")
                time_str += f" - {date_str}"

            return time_str
        except Exception as e:
            print(f"Time error: {str(e)}", type="ERROR")
            return datetime.now(timezone.utc).strftime("%I:%M %p")

    def get_weather_state():
        data = cache.data.get("data")
        return data["current"]["condition"]["text"].lower() if data and "current" in data else "unknown"

    def get_weather_icon():
        # Return cached icon URL (no network I/O here)
        return cache.data.get("icon_url", "")

    addDRPCValue("weatherTemp", get_weather_temp)
    addDRPCValue("city", get_city)
    addDRPCValue("time", get_time)
    addDRPCValue("weatherState", get_weather_state)
    addDRPCValue("weathericon", get_weather_icon)

    # ---------------------------
    # Background fetch loop: single controlled fetch cadence
    # ---------------------------
    def fetch_loop():
        while True:
            try:
                # Respect configured cache duration
                cache_duration = max(settings.get("cache_duration") or 900, 300)
                # Perform a single fetch which will update cache and call tab.render()
                fetch_weather_data()
                # Sleep until next scheduled fetch; if in cooldown, sleep until cooldown ends
                current_time = datetime.now(timezone.utc).timestamp()
                cooldown_until = cache.data.get("cooldown_until", 0)
                if cooldown_until and cooldown_until > current_time:
                    sleep_time = max(cooldown_until - current_time, 1)
                else:
                    sleep_time = cache_duration
                # Cap sleep_time to avoid extremely long sleeps
                sleep_time = max(1, min(sleep_time, 86400))
                time.sleep(sleep_time)
            except Exception as e:
                print(f"Background fetch loop error: {e}", type="ERROR")
                # Wait a bit before retrying loop to avoid tight error loop
                time.sleep(10)

    # Start background fetch thread as daemon so it doesn't block shutdown
    fetch_thread = threading.Thread(target=fetch_loop, name="NightyWeatherFetchLoop", daemon=True)
    fetch_thread.start()

    print("NightyWeather running 🌤️", type="SUCCESS")
    tab.render()
