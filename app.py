import os
import json
import urllib.request
from datetime import datetime
import streamlit as st
from google import genai
from google.genai import types

# --- PAGE SETUP ---
st.set_page_config(page_title="Eugene Trout Scout AI", page_icon="🎣", layout="wide")

RIVER_SPOTS = {
    "mckenzie_vida": {
        "name": "McKenzie (Vida)",
        "usgs_site": "14162500",
        "lat": 44.1248,
        "lon": -122.4706,
        "prime_cfs_range": (1200, 3500),
        "notes": "Premier wild redside rainbow water. Wading gets tough above 3,200 CFS."
    },
    "mckenzie_hayden": {
        "name": "McKenzie (Hayden Bridge)",
        "usgs_site": "14164900",
        "lat": 44.0712,
        "lon": -122.9645,
        "prime_cfs_range": (1500, 4800),
        "notes": "15 mins from Eugene. Great pocket water and riffles for redsides & cutthroat."
    },
    "middle_fork_dexter": {
        "name": "Middle Fork (Dexter)",
        "usgs_site": "14150000",
        "lat": 43.9457,
        "lon": -122.8373,
        "prime_cfs_range": (1200, 4000),
        "notes": "Tailwater below Dexter Dam—stays cleaner and warmer in cold weather."
    },
    "north_fork_middle_fork": {
        "name": "North Fork Middle Fork (Westfir)",
        "usgs_site": "14147500",
        "lat": 43.7568,
        "lon": -122.5053,
        "prime_cfs_range": (150, 900),
        "notes": "Fly-fishing only (barbless). Small canyon freestone; clears fast after rain."
    }
}

# --- AGENT TOOLS ---
def get_live_river_conditions(spot_key: str) -> str:
    """Fetches real-time CFS flow rate and water temperature from the USGS Water Services API.
    
    Args:
        spot_key: One of 'mckenzie_vida', 'mckenzie_hayden', 'middle_fork_dexter', 'north_fork_middle_fork'
    """
    spot = RIVER_SPOTS.get(spot_key)
    if not spot:
        return json.dumps({"error": "Invalid spot key"})

    site_id = spot["usgs_site"]
    url = f"https://waterservices.usgs.gov/nwis/iv/?format=json&sites={site_id}&parameterCd=00060,00010"

    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            data = json.loads(response.read().decode())

        time_series = data.get("value", {}).get("timeSeries", [])
        cfs = None
        temp_f = None

        for series in time_series:
            param_code = series["variable"]["variableCode"][0]["value"]
            values = series["values"][0]["value"]
            if values:
                latest_val = float(values[-1]["value"])
                if param_code == "00060" and latest_val > 0:
                    cfs = int(latest_val)
                elif param_code == "00010" and latest_val > -50:
                    temp_f = round((latest_val * 9/5) + 32, 1)

        min_cfs, max_cfs = spot["prime_cfs_range"]
        if cfs is None:
            status = "Sensor Offline"
        elif cfs > max_cfs:
            status = "HIGH / BLOWN OUT"
        elif cfs < min_cfs:
            status = "LOW & CLEAR"
        else:
            status = "PRIME FLOW"

        return json.dumps({
            "river": spot["name"],
            "current_cfs": cfs,
            "prime_cfs_window": f"{min_cfs}-{max_cfs} CFS",
            "water_temp_f": temp_f if temp_f else 47.0,
            "temp_is_estimated": temp_f is None,
            "flow_status": status,
            "local_notes": spot["notes"]
        })
    except Exception as e:
        return json.dumps({"river": spot["name"], "error": str(e)})

def get_river_weather(spot_key: str) -> str:
    """Fetches current weather, cloud cover, wind, and barometric pressure for a river spot.
    
    Args:
        spot_key: One of 'mckenzie_vida', 'mckenzie_hayden', 'middle_fork_dexter', 'north_fork_middle_fork'
    """
    spot = RIVER_SPOTS.get(spot_key)
    if not spot:
        return json.dumps({"error": "Invalid spot key"})

    lat, lon = spot["lat"], spot["lon"]
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,cloud_cover,precipitation,surface_pressure,wind_speed_10m"
        f"&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch"
    )

    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            data = json.loads(response.read().decode())
        curr = data.get("current", {})
        cloud_pct = curr.get("cloud_cover", 50)
        return json.dumps({
            "river": spot["name"],
            "air_temp_f": f"{curr.get('temperature_2m')}°F",
            "cloud_cover_pct": cloud_pct,
            "sky_condition": "Overcast (BWO Hatch Weather)" if cloud_pct >= 60 else "Clear / Bright",
            "wind_mph": f"{curr.get('wind_speed_10m')} mph",
            "precip_in": f"{curr.get('precipitation')} in",
            "pressure_hpa": curr.get("surface_pressure")
        })
    except Exception as e:
        return json.dumps({"error": str(e)})

def get_fly_box_recommendations(month: int, water_temp_f: float, flow_status: str, is_overcast: bool) -> str:
    """Generates exact fly patterns, hook sizes, tippet, and rigging advice for Willamette/McKenzie trout.
    
    Args:
        month: Numeric month (1-12)
        water_temp_f: Water temperature in Fahrenheit
        flow_status: Current flow status ('PRIME FLOW', 'LOW & CLEAR', or 'HIGH / BLOWN OUT')
        is_overcast: True if cloud cover >= 60%, False otherwise
    """
    if month in [11, 12, 1, 2]:
        season = "Late Fall / Winter"
        hatches = "Blue-Winged Olives (BWOs) #18-22 & Midges #20-24 (12pm-3pm window)"
        dries = ["Parachute Adams (#18-20)", "BWO Sparkle Dun (#18-20)", "Griffith's Gnat (#20-22)"]
        nymphs = [
            "Point (Heavy): Pat's Rubber Legs (Black/Brown #10-12) or Mega Prince (#12-14)",
            "Dropper: Zebra Midge (Black/Silver #18-20) or Jig Pheasant Tail (#16-18)",
            "Off-Color Wildcard: Pink/Red Squirmy Wormy (#12)"
        ]
        streamers = ["Olive or Black Woolly Bugger (#6-10)", "Sculpzilla (#6-8)"]
        tippet = "4X fluorocarbon to point fly, 5X-6X to dropper/dries"
    elif month in [3, 4, 5]:
        season = "Spring"
        hatches = "March Browns (#12-14), BWOs (#16-18), Early Caddis (#14-16)"
        dries = ["Parachute March Brown (#12-14)", "Elk Hair Caddis (#14-16)", "BWO Comparadun (#16-18)"]
        nymphs = ["Point: Beadhead Prince Nymph (#12-14)", "Dropper: Pheasant Tail (#16) or Olive Soft Hackle (#14)"]
        streamers = ["Olive/White Sparkle Minnow (#6)", "Black Woolly Bugger (#8)"]
        tippet = "4X for dries/streamers, 5X fluorocarbon for nymphs"
    elif month in [6, 7, 8]:
        season = "Summer"
        hatches = "Green McKenzie Caddis (#12-14), Golden Stoneflies (#8), PMDs (#16)"
        dries = ["Chubby Chernobyl (#8-10)", "Green Elk Hair Caddis (#12-14)", "PMD Sparkle Dun (#16)"]
        nymphs = ["Dropper under Chubby: Beadhead Prince (#14-16) or Perdigon (#16)"]
        streamers = ["Olive Sculpzilla (#6) along undercut banks at dawn/dusk"]
        tippet = "3X-4X for Chubby/Stones, 5X for PMDs & droppers"
    else:
        season = "Fall"
        hatches = "October Caddis (#8-10), BWOs (#16-18), Mahogany Duns (#14-16)"
        dries = ["Orange Stimulator / Chubby Chernobyl (#8-10)", "Purple Haze (#14-16)", "BWO Cripple (#18)"]
        nymphs = ["Point: October Caddis Pupa (#10) or Possie Bugger (#10)", "Dropper: Jig Pheasant Tail (#16)"]
        streamers = ["Sex Dungeon (#4) or Olive/Copper Woolly Bugger (#6)"]
        tippet = "3X-4X for streamers/October Caddis, 5X for nymphs"

    return json.dumps({
        "season": season,
        "active_hatches": hatches,
        "dry_flies": dries,
        "two_fly_nymph_rig": nymphs,
        "streamers": streamers,
        "tippet": tippet,
        "overcast_bonus": is_overcast,
        "flow_status": flow_status
    })

# --- SIDEBAR: API KEY & QUICK PROMPTS ---
with st.sidebar:
    st.header("⚙️ Agent Settings")
    default_key = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", ""))
    api_key = st.text_input(
        "Gemini API Key",
        value=default_key,
        type="password",
        help="Saved automatically via Streamlit Secrets"
    )
    st.divider()
    st.subheader("⚡ One-Click Scout")
    quick_prompt = None
    if st.button("🏆 Best River & Flies Right Now", use_container_width=True):
        quick_prompt = "Check all 4 rivers right now, rank the best spot near Eugene for trout, and give me exact dry flies, nymph rig, streamers, and tippet to tie on."
    if st.button("🦟 What's Hatching Today?", use_container_width=True):
        quick_prompt = "Check today's water temps and cloud cover on the McKenzie and Middle Fork, and tell me what bugs are hatching and how to rig up."

# --- HEADER & LIVE GAUGE CARDS ---
st.title("🎣 Eugene Fly-Fishing Scout Agent")
st.caption("Live USGS Water Gauges + Open-Meteo Weather + Autonomous Hatch Matching")

@st.cache_data(ttl=600)
def fetch_dashboard_metrics():
    return {k: json.loads(get_live_river_conditions(k)) for k in RIVER_SPOTS}

metrics = fetch_dashboard_metrics()
cols = st.columns(4)
for idx, (key, data) in enumerate(metrics.items()):
    with cols[idx]:
        cfs_display = f"{data.get('current_cfs'):,} CFS" if data.get("current_cfs") else "Offline"
        temp_display = f"{data.get('water_temp_f')}°F" + (" (est)" if data.get("temp_is_estimated") else "")
        st.metric(
            label=data.get("river", key),
            value=cfs_display,
            delta=f"{data.get('flow_status')} • {temp_display}"
        )

st.divider()

# --- CHAT INTERFACE ---
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Live USGS gauges are loaded above. Ask me where to fish today or open the top-left menu (`>`) and tap **Best River & Flies Right Now**!"}
    ]

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

user_input = st.chat_input("Ask where to fish, what flies to tie on, or how to rig up...")
prompt = quick_prompt or user_input

if prompt:
    if not api_key:
        st.error("Please enter your Gemini API Key in the sidebar first!")
    else:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Scouting live gauges, cloud cover, and hatch charts..."):
                client = genai.Client(api_key=api_key)
                today_str = datetime.now().strftime("%B %d, %Y (Month %m)")
                system_instruction = f"""
                You are an expert local fly-fishing guide based in Eugene, Oregon. Today is {today_str}.
                Always check `get_live_river_conditions` for all 4 local rivers, check `get_river_weather` for the top spots, 
                and call `get_fly_box_recommendations` using today's month, water temp, flow status, and cloud cover (>=60% is overcast).
                Give a crisp, well-formatted breakdown:
                1. **#1 River Pick & Backup** (with live CFS, water temp, and why)
                2. **Exact Fly Box & Rig** (Dry flies, 2-fly Point+Dropper nymph rig with sizes, Streamers, and Tippet)
                3. **Tactical Game Plan** (where trout are holding at today's flows)
                """
                
                history = []
                for m in st.session_state.messages[:-1]:
                    role = "user" if m["role"] == "user" else "model"
                    history.append(types.Content(role=role, parts=[types.Part.from_text(text=m["content"])]))

                chat = client.chats.create(
                    model="gemini-3.8-flash",
                    history=history,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        tools=[get_live_river_conditions, get_river_weather, get_fly_box_recommendations],
                        temperature=0.2,
                    )
                )
                response = chat.send_message(prompt)
                st.markdown(response.text)
                st.session_state.messages.append({"role": "assistant", "content": response.text})
