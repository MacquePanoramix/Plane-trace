import os
import json
import time
import requests
from websocket import create_connection  # Requires: pip install websocket-client
from opensky_api import OpenSkyApi, TokenManager

# ==========================================
# Airline Dictionary (Expand this as needed!)
# ==========================================
AIRLINE_MAP = {
    "MSR": "EgyptAir",
    "KLM": "KLM Royal Dutch Airlines",
    "UAL": "United Airlines",
    "BAW": "British Airways",
    "DLH": "Lufthansa",
    "AFR": "Air France",
    "RYR": "Ryanair",
    "EZY": "EasyJet",
    "UAE": "Emirates",
    "QFA": "Qantas",
    "EXS": "Jet2",
    "ELY": "EL AI",
    "SAS": "Scandinavian Airlines",
    "EJU": "easyJet Europe"
}

# ==========================================
# 1. Initialization & Authentication
# ==========================================
print("Initializing Flight Tracker Pipeline...")
try:
    # Connects to OpenSky API using your credentials file
    api = OpenSkyApi(token_manager=TokenManager.from_json_file("credentials.json"))
    print("OpenSky API Authentication Successful!")
except Exception as e:
    print(f"Warning: Could not load credentials.json. Running anonymously. Error: {e}")
    api = OpenSkyApi()

# ==========================================
# 2. Global Memory & Storage
# ==========================================
plane_memory = {}       # Stores live updates from the local websocket
plane_cache = {}        # Secret weapon: Caches API results to protect rate limits
seen_addresses = set()  # Keeps track of which planes we have already printed
trail_points = []
failed_attempts = {}    # used to note down unknown planes, and last check time

if os.path.exists("trail_points.json"):
    try:
        with open("trail_points.json", "r") as f:
            trail_points = json.load(f)
        print(f"Success: Loaded {len(trail_points)} historical trail points from previous sessions!")
        
        # Add previously seen planes to our 'seen' set so we don't print them again
        for point in trail_points:
            seen_addresses.add(point["address"])
            
    except Exception as e:
        print(f"Warning: Could not read old trail points. Starting fresh. Error: {e}")

# ==========================================
# 3. Processor Layer: OpenSky API Enrichment
# ==========================================
def get_enriched_data(icao24):
    icao_lower = str(icao24).lower()

    if icao_lower in plane_cache:
        return plane_cache[icao_lower]
    
    if icao_lower in failed_attempts:
        time_since_last_try = time.time() - failed_attempts[icao_lower]
        if time_since_last_try < 300:
            # not 5 mins yet, don't check again through API
            return {"callsign": "Unknown", "company": "Unknown", "country": "Unknown"}
        else:
            print(f"5 Mins past, check {icao_lower} again！")

    print(f"Fetching details for {icao_lower} from OpenSky API...")
    try:
        s = api.get_states(icao24=icao_lower)
        if s and s.states:
            plane = s.states[0]
            callsign = plane.callsign.strip() if plane.callsign else "N/A"
            
            # Extract the first 3 characters to find the airline company
            prefix = callsign[:3].upper()
            company = AIRLINE_MAP.get(prefix, "Unknown Airline")
            
            details = {
                "callsign": callsign,
                "company": company,  # NEW: Added company name!
                "country": plane.origin_country
            }
            plane_cache[icao_lower] = details
            if icao_lower in failed_attempts:
                del failed_attempts[icao_lower]

            return details
    except Exception as e:
        print(f"Error while searching for {icao_lower}: {e}")

    failed_attempts[icao_lower] = time.time()
    return plane_cache[icao_lower]

# ==========================================
# 4. Message Handler Layer (UPDATED)
# ==========================================
def handle_message(msg):
    address = msg.get("address")
    
    # Ignore empty messages or heartbeats
    if address is None:
        return False  # <-- NEW: Tell the main loop no point was added

    if address not in plane_memory:
        plane_memory[address] = {
            "address": address, "speed": None, "heading": None, "altitude": None,
            "latitude": None, "longitude": None, "timestamp": None, "rssi": None,
            "receiver": None, "callsign": None, "company": None, "country": None
        }

    for field in ["speed", "heading", "altitude", "latitude", "longitude", "timestamp", "rssi", "receiver"]:
        if field in msg:
            plane_memory[address][field] = msg[field]

    has_position = (plane_memory[address]["latitude"] is not None and
                    plane_memory[address]["longitude"] is not None)

    if has_position:
        if plane_memory[address]["callsign"] is None:
            enriched_info = get_enriched_data(address)
            plane_memory[address]["callsign"] = enriched_info["callsign"]
            plane_memory[address]["company"] = enriched_info["company"]
            plane_memory[address]["country"] = enriched_info["country"]

        point = {
            "address": address,
            "latitude": plane_memory[address]["latitude"],
            "longitude": plane_memory[address]["longitude"],
            "altitude": plane_memory[address]["altitude"],
            "speed": plane_memory[address]["speed"],
            "heading": plane_memory[address]["heading"],
            "timestamp": plane_memory[address]["timestamp"],
            "rssi": plane_memory[address]["rssi"],
            "receiver": plane_memory[address]["receiver"],
            "callsign": plane_memory[address]["callsign"],
            "company": plane_memory[address]["company"],
            "country": plane_memory[address]["country"]
        }
        trail_points.append(point)

        if address not in seen_addresses:
            print(f"Plane memory now has a drawable plane: {address} ({plane_memory[address]['company']})")
            seen_addresses.add(address)
            
        return True  # <-- NEW: Successfully added a valid GPS point!
        
    return False # <-- NEW: Plane exists but no GPS data yet

# ==========================================
# 5. Storage Layer
# ==========================================
def save_data():
    """Saves our collected trail points to the JSON file for the website to read."""
    with open("trail_points.json", "w") as f:
        json.dump(trail_points, f, indent=2)
    print(f"Saved {len(trail_points)} trail points to trail_points.json!")

# ==========================================
# NEW: Startup Data Recovery Scan
# ==========================================
# ==========================================
# NEW: Startup Data Recovery Scan (UPGRADED)
# ==========================================
def run_startup_scan():
    """
    Scans the loaded historical trails for missing data using a two-pass system:
    1. Local Dictionary Check (Fast, saves API limits)
    2. API Historical Query (For completely missing callsigns)
    """
    print("\n--- Starting Pre-Flight Scan: Checking for missing airline data ---")
    unknown_addresses = set()
    local_fixes = 0

    # Pass 1: Fast Local Fix & Identify missing callsigns
    for point in trail_points:
        # 使用 .get() 抓取，如果舊資料沒有這個欄位，就會是 None
        callsign = point.get("callsign")
        company = point.get("company")

        # 情況 A：如果連呼號都沒有 (包含舊資料的 None)，標記起來準備問 API
        if callsign in [None, "N/A", "Unknown", ""]:
            unknown_addresses.add(point["address"])
        
        # 情況 B：如果有呼號，但沒有公司名稱 (例如剛把 ELY 加進字典)
        # 直接使用本地的 AIRLINE_MAP 進行光速修復！
        elif company in [None, "Unknown", "Unknown Airline"]:
            prefix = callsign[:3].upper()
            if prefix in AIRLINE_MAP:
                point["company"] = AIRLINE_MAP[prefix]
                local_fixes += 1

    # 如果有本地修復成功，馬上存檔
    if local_fixes > 0:
        print(f"Locally fixed {local_fixes} points using the updated AIRLINE_MAP!")
        save_data()

    # Pass 2: API Recovery
    if not unknown_addresses:
        print("All historical planes already have known callsigns! Scan complete.\n")
        return

    print(f"Found {len(unknown_addresses)} planes with missing callsigns. Attempting API recovery...")
    updated_count = 0

    for address in unknown_addresses:
        result = test_historical_callsign(address)
        
        if result["callsign"] not in ["N/A", "Unknown", ""]:
            for point in trail_points:
                if point["address"] == address:
                    point["callsign"] = result["callsign"]
                    point["company"] = result["company"]
            
            plane_cache[str(address).lower()] = result
            updated_count += 1
            
        time.sleep(2) 

    if updated_count > 0:
        save_data()
        print(f"--- Scan Complete: Successfully recovered info for {updated_count} planes via API! ---\n")
    else:
        print("--- Scan Complete: Could not recover any new info from API at this time. ---\n")    


def test_historical_callsign(icao24):
    """
    使用標準 REST API 查詢，包含偽裝 Header 以防被擋。
    """
    icao_lower = str(icao24).lower()
    
    # 計算時間 (48 小時範圍，這是 OpenSky 的限制)
    end_time = int(time.time())
    begin_time = end_time - (12 * 60 * 60)
    
    url = "https://opensky-network.org/api/flights/aircraft"
    params = {
        "icao24": icao_lower,
        "begin": begin_time,
        "end": end_time
    }
    
    # 偽裝成普通瀏覽器，避免 OpenSky 伺服器對爬蟲不友善
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    print(f"Fetching history for {icao_lower} via REST API...")
    
    try:
        response = requests.get(url, params=params, headers=headers)
        
        # 顯示詳細回傳訊息，這對除錯很有幫助！
        if response.status_code == 200:
            flights = response.json()
            if flights and len(flights) > 0:
                # 遍歷尋找第一個有效的呼號
                for f in flights:
                    if f.get("callsign"):
                        cs = f["callsign"].strip()
                        prefix = cs[:3].upper()
                        company = AIRLINE_MAP.get(prefix, "Unknown Airline")
                        print(f"  -> Success! Found: {cs} ({company})")
                        return {"callsign": cs, "company": company}
            print(f"  -> No flight records found for {icao24} in the last 48 hours.")
        else:
            print(f"  -> API 請求失敗 (狀態碼 {response.status_code}): {response.text}")
            
    except Exception as e:
        print(f"  -> Error occurred: {e}")
        
    return {"callsign": "N/A", "company": "Unknown"}

# ==========================================
# 6. Main Application Loop (UPDATED)
# ==========================================
def main():
    print("Starting Main Loop. Listening for ADS-B data...")
    valid_points_count = 0  # <-- NEW: Only count actual mapped points!
    
    ws_url = "ws://192.87.172.82:1338"

    try:
        if trail_points:
            run_startup_scan()

        print(f"Connecting to {ws_url}...")
        ws = create_connection(ws_url)
        print("Connected! Waiting for aircraft messages...")

        while True:
            raw_msg = ws.recv()
            msg = json.loads(raw_msg)

            # Check if the message actually contained a valid GPS point
            point_was_added = handle_message(msg)
            
            if point_was_added:
                valid_points_count += 1
                
                # Only save to file when we have collected 20 REAL GPS points
                if valid_points_count % 20 == 0:
                    save_data()

    except KeyboardInterrupt:
        print("\nProcess interrupted by user. Shutting down safely...")
        save_data()
    except Exception as e:
        print(f"\nA connection error occurred: {e}")
        save_data()


if __name__ == "__main__":
    print("--- test historical data begin ---")
    test_historical_callsign("4081A9")
    print("--- test historical data complete ---\n")

    main()
