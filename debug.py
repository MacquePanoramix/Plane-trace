import time
from datetime import datetime
from opensky_api import OpenSkyApi, TokenManager

print("初始化 OpenSky API...")
try:
    api = OpenSkyApi(token_manager=TokenManager.from_json_file("credentials.json"))
    print("✅ 認證成功！")
except Exception as e:
    print(f"⚠️ 找不到憑證，使用匿名模式: {e}")
    api = OpenSkyApi()

def test_schiphol_arrivals():
    print("\n" + "="*50)
    print("🛬 正在查詢降落於 史基浦機場 (EHAM) 的航班...")
    print("="*50)

    # 為了避開 OpenSky 的結算延遲，我們故意查「24小時前 ~ 48小時前」的資料
    current_time = int(time.time())
    
    # 從現在往回推 36 個小時 -> 剛好是前天的 16:00 (下午4點)
    begin_time = current_time - (36 * 60 * 60) 
    
    # 終點設定在起點的「2 個小時後」 -> 前天的 18:00 (下午6點)
    end_time = begin_time + (2 * 60 * 60)
    
    str_begin = datetime.fromtimestamp(begin_time).strftime('%Y-%m-%d %H:%M:%S')
    str_end = datetime.fromtimestamp(end_time).strftime('%Y-%m-%d %H:%M:%S')

    print(f"📅 搜尋範圍: {str_begin} 到 {str_end}")
    
    try:
        print("📡 正在向 OpenSky 請求抵達航班資料 (這可能需要幾秒鐘)...")
        # 呼叫專門查「抵達某機場」的 API (這次指令名字絕對對了！)
        arrivals = api.get_arrivals_by_airport(airport="EHAM", begin=begin_time, end=end_time)
        
        if arrivals is None or len(arrivals) == 0:
            print("❌ 找不到任何降落紀錄，這也太怪了！")
            return
            
        print(f"✅ 成功找到 {len(arrivals)} 筆降落紀錄！為妳列出最新的 5 架飛機：\n")
        
        # 我們只取前 5 筆資料印出來看
        for i, flight in enumerate(arrivals[:5]):
            callsign = flight.callsign.strip() if flight.callsign else "N/A (空白呼號)"
            icao = flight.icao24.lower()
            
            # 把時間戳記換成人類時間
            if flight.lastSeen:
                arr_time = datetime.fromtimestamp(flight.lastSeen).strftime('%Y-%m-%d %H:%M:%S')
            else:
                arr_time = "未知"
                
            dep_airport = flight.estDepartureAirport or "未知出發地"
            
            print(f"✈️ 航班 {i+1}:")
            print(f"   - 呼號 (Callsign): {callsign}")
            print(f"   - ICAO 代碼:       {icao}")
            print(f"   - 從哪裡飛來:      {dep_airport}")
            print(f"   - 降落史基浦時間:  {arr_time}")
            print("-" * 40)
            
    except Exception as e:
        print(f"💥 發生 API 錯誤: {e}")

def test_raw_states():
    print("\n📡 正在直接暴力撈取荷蘭上空的飛行狀態...")
    # 荷蘭的經緯度範圍 (約略)
    # bbox = (min_lat, min_lon, max_lat, max_lon)
    try:
        # 抓取整個荷蘭範圍的即時狀態
        states = api.get_states(bbox=(50.75, 3.3, 53.5, 7.2))
        
        if states and states.states:
            print(f"✅ 成功撈到 {len(states.states)} 架正在飛的飛機！")
            for i, s in enumerate(states.states[:5]):
                print(f"✈️ {i+1}: 呼號={s.callsign}, ICAO={s.icao24}, 國籍={s.origin_country}")
        else:
            print("❌ 沒抓到飛機... 可能現在荷蘭上空真的沒飛機（但這不可能啊！）")
    except Exception as e:
        print(f"💥 錯誤: {e}")

if __name__ == "__main__":
    test_raw_states()