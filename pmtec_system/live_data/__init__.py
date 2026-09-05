"""
PMTEC LVC Live Data Package (P2-3).

Real-world sensor data source adapters for the LVC Live layer.
Provides normalized real-time data feeds from:
  - ADS-B: OpenSky Network API (real aircraft positions, free, no key)
  - AIS: Maritime vessel tracking (simulated with real API support)
  - OpenWeather: Open-Meteo API (real weather conditions, free, no key)

All adapters normalize data into LiveSensorData dicts and inject
into the LVC Live layer via the LiveDataAdapterManager.

Usage:
  from live_data import LiveAdapterManager
  manager = LiveAdapterManager()
  manager.start_all()  # starts background polling threads
  manager.inject_into_lvc(engine.lvc)  # injects current data
"""

from .adapter_manager import LiveAdapterManager, LiveDataAdapterBase

__all__ = ["LiveAdapterManager", "LiveDataAdapterBase"]
