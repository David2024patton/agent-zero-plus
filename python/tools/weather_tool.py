"""
Agent Zero Tool: weather_tool
==============================
Fetch current weather and forecasts using free services (wttr.in, Open-Meteo).
No API key required.
"""

import aiohttp
from python.helpers.tool import Tool, Response
from python.helpers.print_style import PrintStyle


class WeatherTool(Tool):

    async def execute(self, **kwargs) -> Response:
        location = (self.args.get("location") or "").strip()
        format_type = (self.args.get("format") or "text").strip().lower()
        units = (self.args.get("units") or "metric").strip().lower()  # metric or imperial

        if not location:
            return Response(
                message="Error: 'location' is required. Example: 'New York', 'London', 'Tokyo'.",
                break_loop=False,
            )

        try:
            if format_type == "json":
                result = await self._fetch_open_meteo(location, units)
            else:
                result = await self._fetch_wttr(location, units)

            self.log.update(content=result[:500])
            return Response(message=result, break_loop=False)

        except Exception as e:
            PrintStyle().error(f"Weather tool error: {e}")
            return Response(message=f"Error fetching weather: {e}", break_loop=False)

    async def _fetch_wttr(self, location: str, units: str = "metric") -> str:
        """Fetch formatted weather from wttr.in."""
        unit_flag = "m" if units == "metric" else "u"
        url = f"https://wttr.in/{location}?format=4&{unit_flag}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return f"wttr.in returned status {resp.status}"
                text = await resp.text()
                return text.strip()

    async def _fetch_open_meteo(self, location: str, units: str = "metric") -> str:
        """Fetch JSON weather data from Open-Meteo (geocode + forecast)."""
        import json

        is_imperial = units == "imperial"
        temp_unit = "fahrenheit" if is_imperial else "celsius"
        wind_unit = "mph" if is_imperial else "kmh"
        precip_unit = "inch" if is_imperial else "mm"

        # Step 1: Geocode the location
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location}&count=1"
        async with aiohttp.ClientSession() as session:
            async with session.get(geo_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                geo_data = await resp.json()

            results = geo_data.get("results", [])
            if not results:
                return f"Location '{location}' not found."

            lat = results[0]["latitude"]
            lon = results[0]["longitude"]
            name = results[0].get("name", location)
            country = results[0].get("country", "")

            # Step 2: Fetch weather
            weather_url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={lat}&longitude={lon}"
                f"&current=temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code"
                f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
                f"&temperature_unit={temp_unit}&wind_speed_unit={wind_unit}&precipitation_unit={precip_unit}"
                f"&timezone=auto&forecast_days=3"
            )
            async with session.get(weather_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                weather_data = await resp.json()

        current = weather_data.get("current", {})
        daily = weather_data.get("daily", {})
        t_sym = "°F" if is_imperial else "°C"
        w_sym = "mph" if is_imperial else "km/h"
        p_sym = "in" if is_imperial else "mm"

        lines = [
            f"**Weather for {name}, {country}**",
            f"",
            f"**Current:**",
            f"- Temperature: {current.get('temperature_2m', 'N/A')}{t_sym}",
            f"- Feels Like: {current.get('apparent_temperature', 'N/A')}{t_sym}",
            f"- Humidity: {current.get('relative_humidity_2m', 'N/A')}%",
            f"- Wind: {current.get('wind_speed_10m', 'N/A')} {w_sym}",
            f"",
            f"**3-Day Forecast:**",
        ]

        dates = daily.get("time", [])
        highs = daily.get("temperature_2m_max", [])
        lows = daily.get("temperature_2m_min", [])
        precip = daily.get("precipitation_sum", [])

        for i in range(min(3, len(dates))):
            lines.append(
                f"- {dates[i]}: High {highs[i]}{t_sym}, Low {lows[i]}{t_sym}, Precip {precip[i]}{p_sym}"
            )

        return "\n".join(lines)

    def get_log_object(self):
        kvps = dict(self.args) if self.args else {}
        return self.agent.context.log.log(
            type="tool",
            heading=f"icon://cloud {self.agent.agent_name}: Checking Weather",
            content="",
            kvps=kvps,
        )
