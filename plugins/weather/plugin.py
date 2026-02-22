"""
Weather Plugin
Fetches weather data using OpenWeatherMap API (free tier)
"""
import os
import time
from typing import Any, Optional

import httpx

from src.plugins.base import IPlugin, PluginMetadata, PluginResult, PluginStatus


class WeatherPlugin(IPlugin):
    """
    Weather information plugin using OpenWeatherMap API.

    Features:
    - Current weather data
    - 7-day forecast (requires API key)
    - Multiple location formats (city, coordinates)
    - Temperature in Celsius or Fahrenheit
    - Free tier supported
    """

    def __init__(self) -> None:
        """Initialize weather plugin."""
        metadata = PluginMetadata(
            name="weather",
            version="1.0.0",
            description="Get weather information using OpenWeatherMap API",
            author="Ironclaw Team",
            dependencies=[],
            max_execution_time_seconds=10,
            max_memory_mb=128,
            max_cpu_percent=20.0,
            requires_network=True,
            allowed_domains=["api.openweathermap.org"],
            requires_permissions=["network.http"],
            enabled=True,
            tags=["weather", "api", "utility"],
        )
        super().__init__(metadata)

        # API configuration
        self.api_key = os.getenv("OPENWEATHER_API_KEY", "")
        self.base_url = "https://api.openweathermap.org/data/2.5"

    async def execute(self, **kwargs: Any) -> PluginResult:
        """
        Get weather information.

        Args:
            location: City name (e.g., "London" or "London,UK") (required)
            units: Temperature units - "metric" (Celsius) or "imperial" (Fahrenheit) (default: metric)
            forecast: Get 7-day forecast instead of current weather (default: False)

        Returns:
            PluginResult with weather data
        """
        start_time = time.time()

        try:
            # Check API key
            if not self.api_key:
                return PluginResult(
                    status=PluginStatus.FAILED,
                    error="OpenWeatherMap API key not configured. "
                    "Set OPENWEATHER_API_KEY environment variable. "
                    "Get free key at: https://openweathermap.org/api",
                )

            # Extract parameters
            location = kwargs.get("location", "").strip()
            units = kwargs.get("units", "metric")
            forecast = kwargs.get("forecast", False)

            if not location:
                return PluginResult(
                    status=PluginStatus.FAILED,
                    error="Location parameter is required",
                )

            # Fetch weather data
            if forecast:
                data = await self._get_forecast(location, units)
            else:
                data = await self._get_current_weather(location, units)

            execution_time_ms = int((time.time() - start_time) * 1000)

            return PluginResult(
                status=PluginStatus.SUCCESS,
                data=data,
                execution_time_ms=execution_time_ms,
            )

        except httpx.HTTPStatusError as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            return PluginResult(
                status=PluginStatus.FAILED,
                error=f"API error: {e.response.status_code} - {e.response.text}",
                execution_time_ms=execution_time_ms,
            )

        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            return PluginResult(
                status=PluginStatus.FAILED,
                error=f"Weather fetch failed: {str(e)}",
                execution_time_ms=execution_time_ms,
            )

    async def validate(self, **kwargs: Any) -> bool:
        """
        Validate weather request parameters.

        Args:
            location: Location name
            units: Temperature units

        Returns:
            True if valid, False otherwise
        """
        location = kwargs.get("location", "").strip()
        if not location or len(location) > 100:
            return False

        units = kwargs.get("units", "metric")
        if units not in ("metric", "imperial"):
            return False

        return True

    async def _get_current_weather(
        self, location: str, units: str
    ) -> dict[str, Any]:
        """
        Get current weather for location.

        Args:
            location: City name
            units: Temperature units

        Returns:
            Dictionary with current weather data
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/weather",
                params={
                    "q": location,
                    "appid": self.api_key,
                    "units": units,
                },
                timeout=8.0,
            )
            response.raise_for_status()
            data = response.json()

        # Extract relevant data
        temp_unit = "°C" if units == "metric" else "°F"

        return {
            "location": data["name"],
            "country": data["sys"]["country"],
            "temperature": data["main"]["temp"],
            "feels_like": data["main"]["feels_like"],
            "temp_min": data["main"]["temp_min"],
            "temp_max": data["main"]["temp_max"],
            "temperature_unit": temp_unit,
            "humidity": data["main"]["humidity"],
            "pressure": data["main"]["pressure"],
            "weather": data["weather"][0]["main"],
            "description": data["weather"][0]["description"],
            "wind_speed": data["wind"]["speed"],
            "clouds": data["clouds"]["all"],
        }

    async def _get_forecast(self, location: str, units: str) -> dict[str, Any]:
        """
        Get 7-day forecast for location.

        Args:
            location: City name
            units: Temperature units

        Returns:
            Dictionary with forecast data
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/forecast",
                params={
                    "q": location,
                    "appid": self.api_key,
                    "units": units,
                    "cnt": 40,  # 5 days, 8 forecasts per day (3-hour intervals)
                },
                timeout=8.0,
            )
            response.raise_for_status()
            data = response.json()

        # Extract relevant data
        temp_unit = "°C" if units == "metric" else "°F"

        forecast_list = []
        for item in data["list"][:24]:  # First 3 days (8 items per day)
            forecast_list.append(
                {
                    "datetime": item["dt_txt"],
                    "temperature": item["main"]["temp"],
                    "feels_like": item["main"]["feels_like"],
                    "temp_min": item["main"]["temp_min"],
                    "temp_max": item["main"]["temp_max"],
                    "weather": item["weather"][0]["main"],
                    "description": item["weather"][0]["description"],
                    "humidity": item["main"]["humidity"],
                    "wind_speed": item["wind"]["speed"],
                }
            )

        return {
            "location": data["city"]["name"],
            "country": data["city"]["country"],
            "temperature_unit": temp_unit,
            "forecast": forecast_list,
            "forecast_count": len(forecast_list),
        }

    async def cleanup(self) -> None:
        """No cleanup needed for weather plugin."""
        pass
