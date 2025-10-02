from typing import Any, Dict

import httpx
from fastmcp import FastMCP

mcp = FastMCP("weather")

api_url = "https://api.open-meteo.com/v1"
user_agent = "weather-app/1.0"


async def get_coordinates(location: str) -> tuple[float, float]:
    """Get latitude and longitude for a location name"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={
                "name": location,
                "count": 1,
                "language": "en",
                "format": "json",
            },
            headers={"User-Agent": user_agent},
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("results"):
                result = data["results"][0]
                return result["latitude"], result["longitude"]
        raise ValueError(
            f"Could not find coordinates for location: {location}"
        )


@mcp.tool()
async def get_weather(location: str) -> Dict[str, Any]:
    """Get current weather information for a location

    Args:
        location: The name of the city/location (e.g., "San Francisco, CA")

    Returns:
        Dict containing weather data including temperature, wind speed, etc.
    """
    try:
        # Get coordinates for the location
        latitude, longitude = await get_coordinates(location)

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{api_url}/forecast",
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current_weather": True,
                    "hourly": "temperature_2m,relative_humidity_2m,weather_code",
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min",
                    "timezone": "auto",
                    "forecast_days": 1,
                },
                headers={"User-Agent": user_agent},
            )

            if response.status_code == 200:
                weather_data = response.json()

                # Format the response
                current = weather_data.get("current_weather", {})
                daily = weather_data.get("daily", {})

                formatted_response = {
                    "location": location,
                    "coordinates": {
                        "latitude": latitude,
                        "longitude": longitude,
                    },
                    "current_weather": {
                        "temperature": f"{current.get('temperature', 'N/A')}°C",
                        "wind_speed": f"{current.get('windspeed', 'N/A')} km/h",
                        "wind_direction": f"{current.get('winddirection', 'N/A')}°",
                        "weather_code": current.get("weathercode", "N/A"),
                        "time": current.get("time", "N/A"),
                    },
                    "daily_forecast": {
                        "max_temperature": f"{daily.get('temperature_2m_max', [None])[0]}°C"
                        if daily.get("temperature_2m_max")
                        else "N/A",
                        "min_temperature": f"{daily.get('temperature_2m_min', [None])[0]}°C"
                        if daily.get("temperature_2m_min")
                        else "N/A",
                    },
                    "status": "success",
                }

                return formatted_response
            else:
                return {
                    "error": f"Unable to fetch weather data. Status code: {response.status_code}",
                    "status": "error",
                }

    except Exception as e:
        return {
            "error": f"Error fetching weather data: {str(e)}",
            "status": "error",
        }


if __name__ == "__main__":
    mcp.run(transport="stdio")
