#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import requests
from getpass import getpass

DIRECTIONS_API = "https://api.openrouteservice.org/v2/directions/driving-car"
GEOCODE_API = "https://api.openrouteservice.org/geocode/search"

def meters_to_km(m):
    try:
        return float(m) / 1000.0
    except Exception:
        return None

def meters_to_miles(m):
    try:
        return float(m) / 1609.344
    except Exception:
        return None

def seconds_to_hms(s):
    try:
        s = int(round(float(s)))
    except Exception:
        return "N/A"
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:02d}"

def read_api_key():
    key = os.getenv("ORS_API_KEY")
    if key:
        return key.strip()
    print("No ORS_API_KEY in environment.")
    key = getpass("Paste your OpenRouteService API key (input hidden): ").strip()
    if not key:
        print("Error: API key is required.")
        sys.exit(1)
    return key

def ask_float(prompt, default=None, allow_blank=True):
    while True:
        val = input(prompt).strip()
        if allow_blank and val == "":
            return default
        try:
            return float(val)
        except ValueError:
            print("Please enter a number (e.g., 8.5).")

def geocode_address(address, key):
    params = {
        "api_key": key,
        "text": address,
        "size": 1
    }
    try:
        r = requests.get(GEOCODE_API, params=params, timeout=20)
    except requests.exceptions.RequestException as e:
        print(f"Network error while geocoding '{address}': {e}")
        return None

    if r.status_code != 200:
        print(f"Error {r.status_code} geocoding '{address}': {r.text[:200]}")
        return None

    data = r.json()
    feats = data.get("features", [])
    if not feats:
        print(f"Error: No results found for address '{address}'.")
        return None

    coords = feats[0].get("geometry", {}).get("coordinates")
    if not coords or len(coords) != 2:
        print(f"Error: Invalid coordinates for '{address}'.")
        return None

    lon, lat = coords
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        print(f"Error: Out-of-range coordinates for '{address}'.")
        return None

    return [lon, lat]

def fetch_route(orig_coords, dest_coords, key):
    headers = {
        "Authorization": key,
        "Content-Type": "application/json"
    }
    body = {
        "coordinates": [orig_coords, dest_coords]
    }
    try:
        r = requests.post(DIRECTIONS_API, headers=headers, json=body, timeout=30)
    except requests.exceptions.RequestException as e:
        print(f"Network error calling directions API: {e}")
        return None, None

    content_type = r.headers.get("Content-Type", "")
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}

    if r.status_code == 200:
        return data, None
    else:
        # Mensagens comuns (ex.: 400/401/403/429/500)
        err = data if isinstance(data, dict) else {"error": str(data)}
        return None, {"status": r.status_code, "message": err}

def print_route(orig, dest, data, unit_system="metric", l_per_100km=None):
    """
    unit_system: 'metric' (km) or 'imperial' (miles)
    l_per_100km: float or None -> calcula consumo estimado se informado
    """
    routes = data.get("routes", [])
    if not routes:
        print("Error: No routes found in the response.")
        return

    route = routes[0]
    segments = route.get("segments", [])
    if not segments:
        print("Error: No segments found in the route.")
        return

    segment = segments[0]
    duration_s = segment.get("duration", None)
    distance_m = segment.get("distance", None)

    print("\nAPI Status: Successful route call.\n")
    print("=============================================")
    print(f"Directions from {orig} to {dest}")

    dur_str = seconds_to_hms(duration_s) if duration_s is not None else "N/A"

    if unit_system == "imperial":
        dist_val = meters_to_miles(distance_m)
        dist_label = "miles"
    else:
        dist_val = meters_to_km(distance_m)
        dist_label = "km"

    if dist_val is None:
        dist_str = "N/A"
    else:
        dist_str = f"{dist_val:.2f} {dist_label}"

    print(f"Trip Duration: {dur_str}")
    print(f"Distance: {dist_str}")

    if l_per_100km is not None and dist_val is not None and unit_system == "metric":
        fuel_used_l = dist_val * (l_per_100km / 100.0)
        print(f"Estimated Fuel Used: {fuel_used_l:.2f} L (at {l_per_100km:.1f} L/100km)")

    print("=============================================")

    steps = segment.get("steps", [])
    if steps:
        for idx, step in enumerate(steps, start=1):
            instruction = step.get("instruction", "N/A")
            step_m = step.get("distance", 0)
            if unit_system == "imperial":
                step_dist = meters_to_miles(step_m)
                step_label = "mi"
            else:
                step_dist = meters_to_km(step_m)
                step_label = "km"
            if step_dist is None:
                print(f"{idx}. {instruction}")
            else:
                print(f"{idx}. {instruction} ({step_dist:.2f} {step_label})")
    else:
        print("No step-by-step directions available.")

    print("=============================================\n")

def main():
    print("=== OpenRouteService Directions (JSON Parsing) ===")
    print("Type 'quit' or 'q' at any prompt to exit.\n")

    key = read_api_key()

    unit_choice = input("Units? [1] Metric (km)  [2] Imperial (miles) [default: 1]: ").strip()
    unit_system = "imperial" if unit_choice == "2" else "metric"

    l_per_100km = None
    if unit_system == "metric":
        l_per_100km = ask_float(
            "Optional: Enter fuel consumption in L/100km (blank to skip): ",
            default=None,
            allow_blank=True
        )

    while True:
        orig = input("\nStarting Location: ").strip()
        if orig.lower() in ("quit", "q"):
            break

        dest = input("Destination: ").strip()
        if dest.lower() in ("quit", "q"):
            break

        orig_coords = geocode_address(orig, key)
        dest_coords = geocode_address(dest, key)

        if not orig_coords or not dest_coords:
            print("Unable to geocode one or both addresses. Please try again.\n")
            continue

        data, error = fetch_route(orig_coords, dest_coords, key)
        if error:
            status = error.get("status")
            message = error.get("message")
            if status == 401:
                print("Error 401: Unauthorized. Check your API key (ORS_API_KEY).")
            elif status == 403:
                print("Error 403: Forbidden. Your API key may not have access to this endpoint.")
            elif status == 429:
                print("Error 429: Rate limit exceeded. Please wait and try again later.")
            elif status == 400:
                print("Error 400: Bad request. Check coordinates or request body.")
            else:
                print(f"Error {status}: {message}")
            continue

        print_route(orig, dest, data, unit_system=unit_system, l_per_100km=l_per_100km)

    print("\nBye! 👋")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted. Bye!")
