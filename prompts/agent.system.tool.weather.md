### weather_tool
Fetch current weather and forecasts for any location. No API key required.
Supports text format (wttr.in) or structured JSON (Open-Meteo with 3-day forecast).
**Example usage**:
~~~json
{
    "thoughts": [
        "User wants to know the weather...",
    ],
    "headline": "Checking weather for New York",
    "tool_name": "weather_tool",
    "tool_args": {
        "location": "New York",
        "format": "text"
    }
}
~~~
**Parameters:**
- **location** (required): City name, e.g. "London", "Tokyo", "Paris"
- **format** (optional): "text" (default, compact) or "json" (structured with forecast, includes feels-like temp)
- **units** (optional): "metric" (default, °C/km/h) or "imperial" (°F/mph)
