"""Utilitaires : météo (Open-Meteo, gratuit et sans clé)."""
import asyncio
import datetime

import aiohttp

from libs import web
from libs.assistant.tools.base import ToolContext, tool, _int

WEATHER_CODES = {
    0: "ciel dégagé", 1: "plutôt dégagé", 2: "partiellement nuageux", 3: "couvert",
    45: "brouillard", 48: "brouillard givrant", 51: "bruine légère", 53: "bruine", 55: "bruine forte",
    56: "bruine verglaçante", 57: "bruine verglaçante forte", 61: "pluie faible", 63: "pluie",
    65: "forte pluie", 66: "pluie verglaçante", 67: "forte pluie verglaçante", 71: "neige faible",
    73: "neige", 75: "forte neige", 77: "grains de neige", 80: "averses faibles", 81: "averses",
    82: "fortes averses", 85: "averses de neige", 86: "fortes averses de neige", 95: "orage",
    96: "orage avec grêle", 99: "orage avec forte grêle",
}
DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def format_weather(place: dict, data: dict) -> str:
    current, daily = data.get("current", {}), data.get("daily", {})
    name = ", ".join(filter(None, [place.get("name"), place.get("admin1"), place.get("country")]))
    lines = [f"Météo à {name} :",
             f"- Maintenant : {current.get('temperature_2m')}°C (ressenti {current.get('apparent_temperature')}°C), "
             f"{WEATHER_CODES.get(current.get('weather_code'), 'temps inconnu')}, "
             f"vent {current.get('wind_speed_10m')} km/h"]
    for i, day in enumerate(daily.get("time", [])):
        date = datetime.date.fromisoformat(day)
        lines.append(
            f"- {DAYS[date.weekday()]} {date:%d.%m} : {daily['temperature_2m_min'][i]}° / "
            f"{daily['temperature_2m_max'][i]}°C, {WEATHER_CODES.get(daily['weather_code'][i], '?')}, "
            f"pluie {daily['precipitation_probability_max'][i] or 0} %")
    return "\n".join(lines) + "\n(Source : Open-Meteo)"


@tool("weather", "Météo actuelle et prévisions d'une ville (jusqu'à 7 jours). Plus fiable que web_search pour la météo.",
      {"city": ("string", "Ville, ex : « Lausanne » ou « Paris, France »"),
       "days": ("integer", "Nombre de jours de prévisions (1 à 7, défaut 3)")},
      required=("city",))
async def weather(ctx: ToolContext, city: str, days: int = 3) -> str:
    name, _, country = city.partition(",")
    try:
        async with aiohttp.ClientSession(headers={"User-Agent": web.USER_AGENT}, timeout=web.TIMEOUT) as session:
            async with session.get("https://geocoding-api.open-meteo.com/v1/search",
                                   params={"name": name.strip(), "count": 5, "language": "fr"}) as response:
                places = (await response.json()).get("results") or []
            if country.strip():
                wanted = country.strip().lower()
                places = [p for p in places if wanted in (p.get("country", "") + p.get("country_code", "")).lower()] or places
            if not places:
                return f"Erreur : ville « {city} » introuvable."
            place = places[0]
            async with session.get("https://api.open-meteo.com/v1/forecast", params={
                    "latitude": place["latitude"], "longitude": place["longitude"], "timezone": "auto",
                    "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                    "forecast_days": _int(days, 3, 1, 7)}) as response:
                if response.status != 200:
                    return f"Erreur : Open-Meteo a répondu HTTP {response.status}."
                data = await response.json()
    except (aiohttp.ClientError, asyncio.TimeoutError) as error:
        return f"Erreur : météo indisponible ({error or type(error).__name__})."
    return format_weather(place, data)
