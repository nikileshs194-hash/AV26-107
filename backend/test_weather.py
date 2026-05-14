from services.weather_service import get_weather

print("Starting Test...")

weather = get_weather()

print("Weather Data:")
print(weather)