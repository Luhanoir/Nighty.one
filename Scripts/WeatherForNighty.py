@nightyScript(
    name="NightyWeather",
    author="Luhan",
    description="Simple Seoul weather + real local time. Time is completely independent from API. Weather updates every 15 minutes.",
    usage="weatherTemp: Current temperature (e.g. 12°C)\ncity: City name (Seoul)\ntime: Local PC time in 12H format (e.g. 7:58 PM)\nweatherState: Weather condition\nweathericon: Weather icon URL"
)
def NightyWeather():
    import requests
    from datetime import datetime, timezone

    # ====================== CONFIGURATION (EDIT HERE) ======================
    API_KEY = "7a99c2df5d4c4f32870115238261004"                    # ← Put your WeatherAPI key here
    CITY = "Seoul"
    CACHE_DURATION_SECONDS = 900    # 15 minutes - change if you want different refresh rate
    # =======================================================================

    # In-memory cache only (no files)
    cache = {"data": None, "timestamp": 0}

    # ==================== INDEPENDENT SYSTEM TIME ====================
    def get_time():
        """Fully independent - uses your PC's real local time"""
        try:
            now = datetime.now()
            time_str = now.strftime("%I:%M %p")
            if time_str.startswith("0"):
                time_str = time_str[1:]
            return time_str
        except Exception:
            return datetime.now().strftime("%I:%M %p")

    # Weather fetch with simple in-memory cache
    def fetch_weather_data():
        try:
            if not API_KEY:
                return None

            current_time = datetime.now(timezone.utc).timestamp()

            # Return cached data if still valid
            if cache["data"] and (current_time - cache["timestamp"]) < CACHE_DURATION_SECONDS:
                return cache["data"]

            url = "https://api.weatherapi.com/v1/current.json"
            params = {"key": API_KEY, "q": CITY, "aqi": "no"}

            resp = requests.get(url, params=params, timeout=(5, 10))
            resp.raise_for_status()
            data = resp.json()

            if isinstance(data, dict) and "error" in data:
                return cache.get("data")

            cache["data"] = data
            cache["timestamp"] = current_time
            return data

        except Exception:
            return cache.get("data")

    # Getters
    def get_weather_temp():
        data = fetch_weather_data()
        if not data or "current" not in data:
            return "N/A"
        raw = data["current"].get("temp_c")
        if raw is None:
            return "N/A"
        return f"{int(round(raw))}°C"

    def get_city():
        return CITY

    def get_weather_state():
        data = fetch_weather_data()
        if data and "current" in data:
            return data["current"]["condition"]["text"].lower()
        return "unknown"

    def get_weather_icon():
        data = fetch_weather_data()
        if data and "current" in data:
            icon = data["current"]["condition"].get("icon")
            if icon:
                if icon.startswith("//"):
                    icon = "https:" + icon
                return icon.replace("64x64", "128x128")
        return ""

    # Register for Discord Rich Presence
    addDRPCValue("weatherTemp", get_weather_temp)
    addDRPCValue("city", get_city)
    addDRPCValue("time", get_time)
    addDRPCValue("weatherState", get_weather_state)
    addDRPCValue("weathericon", get_weather_icon)

    print("NightyWeather running (Seoul + Auto Time)")