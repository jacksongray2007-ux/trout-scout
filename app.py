import os
import json
import urllib.request
from datetime import datetime
import streamlit as st
from google import genai
from google.genai import types

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

def fetch_usgs(spot_key: str) -> dict:
    spot = RIVER_SPOTS[spot_key]
    url = f"https://waterservices.usgs.gov/nwis/iv/?format=json&sites={spot['usgs_site']}&parameterCd=00060,00010"
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            data = json.loads(response.read().decode())
        cfs, temp_f = None, None
        for series in data.get("value", {}).get("timeSeries", []):
            code = series["variable"]["variableCode"][0]["value"]
            vals = series["values"][0]["value"]
            if vals:
                v = float(vals[-1]["value"])
                if code == "00060" and v > 0:
                    cfs = int(v)
                elif code == "00010" and v > -50:
                    temp_f = round((v * 9 / 5) + 32, 1)
        lo, hi = spot["prime_cfs_range"]
        if cfs is None:
            status = "Sensor Offline"
        elif cfs > hi:
            status = "HIGH / BLOWN OUT"
        elif cfs < lo:
            status = "LOW & CLEAR"
        else:
            status = "PRIME FLOW"
        return {
            "river": spot["name"],
            "current_cfs": cfs,
            "prime_cfs_window": f"{lo}-{hi} CFS",
            "water_temp_f": temp_f if temp_f else 47.0,
            "temp_is_estimated": temp_f is None,
            "flow_status": status,
            "notes": spot["notes"]
        }
    except Exception as e:
        return {"river": spot["name"], "current_cfs": None, "flow_status": "Offline", "error": str(e)}

def fetch_weather(spot_key: str) -> dict:
    spot = RIVER_SPOTS[spot_key]
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={spot['lat']}&longitude={spot['lon']}"
        f"&current=temperature_2m,cloud_cover,precipitation,surface_pressure,wind_speed_10m"
        f"&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch"
    )
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            curr = json.loads(response.read().decode()).get("current", {})
        cloud = curr.get("cloud_cover", 50)
        return {
            "air_temp_f": f"{curr.get('temperature_2m')}°F",
            "cloud_cover_pct": cloud,
            "sky": "Overcast (Prime BWO hatch weather)" if cloud >= 60 else "Clear / Sunny",
            "wind_mph": f"{curr.get('wind_speed_10m')} mph",
            "precip_in": f"{curr.get('precipitation')} in",
            "pressure_hpa": curr.get("surface_pressure")
        }
    except Exception:
        return {"sky": "Unavailable"}

@st.cache_data(ttl=600)
def get_all_live_data():
    report = {}
    for k in RIVER_SPOTS:
        report[k] = fetch_usgs(k)
        report[k]["weather"] = fetch_weather(k)
    return report

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Agent Settings")
    default_key = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", ""))
    api_key = st.text_input("Gemini API Key", value=default_key, type="password")
    st.divider()
    st.subheader("⚡ One-Click Scout")
    quick_prompt = None
    if st.button("🏆 Best River & Flies Right Now", use_container_width=True):
        quick_prompt = "Rank the best river near Eugene to fish for trout right now based on the live gauges, and give me exact dry flies, 2-fly nymph rig (point + dropper with hook sizes), streamers, and tippet."
    if st.button("🦟 What's Hatching Today?", use_container_width=True):
        quick_prompt = "Based on today's water temps and cloud cover, what bugs are hatching on the McKenzie and Middle Fork and how should I rig up?"

# --- LIVE GAUGE DASHBOARD ---
st.title("🎣 Eugene Fly-Fishing Scout Agent")
st.caption("Live USGS Water Gauges + Open-Meteo Weather + Hatch & Rig Recommender")

live_data = get_all_live_data()
cols = st.columns(4)
for idx, (key, data) in enumerate(live_data.items()):
    with cols[idx]:
        cfs_txt = f"{data['current_cfs']:,} CFS" if data.get("current_cfs") else "Offline"
        temp_txt = f"{data['water_temp_f']}°F" + (" (est)" if data.get("temp_is_estimated") else "")
        st.metric(label=data["river"], value=cfs_txt, delta=f"{data['flow_status']} • {temp_txt}")

st.divider()

# --- CHAT ---
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Live USGS gauges are loaded above. Ask where to fish today or open the top-left menu (`>`) and tap **Best River & Flies Right Now**!"}
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
            with st.spinner("Analyzing live flows, water temps, and hatches..."):
                client = genai.Client(api_key=api_key)
                today_str = datetime.now().strftime("%B %d, %Y")
                system_instruction = f"""
                You are an expert local fly-fishing guide in Eugene, Oregon. Today's date is {today_str}.
                Here is the REAL-TIME USGS river gauge and Open-Meteo weather data fetched seconds ago:
                {json.dumps(live_data, indent=2)}

                Use this exact live data to answer the angler's question. Always include:
                1. **#1 River Pick & Backup** (cite exact CFS, water temp, and why it beats the others today)
                2. **Exact Fly Box & Rig** (Dry flies, 2-fly Point + Dropper nymph rig with exact hook sizes, Streamers, and Tippet size matched to today's season, water temp, and cloud cover)
                3. **Tactical Game Plan** (where trout are holding at today's flows)
                """

                contents = []
                for m in st.session_state.messages:
                    role = "user" if m["role"] == "user" else "model"
                    contents.append(types.Content(role=role, parts=[types.Part.from_text(text=m["content"])]))

                response = None
                last_error = None
                for model_id in ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"]:
                    try:
                        response = client.models.generate_content(
                            model=model_id,
                            contents=contents,
                            config=types.GenerateContentConfig(
                                system_instruction=system_instruction,
                                temperature=0.3,
                            )
                        )
                        if response and response.text:
                            break
                    except Exception as err:
                        last_error = err
                        continue

                if response and response.text:
                    st.markdown(response.text)
                    st.session_state.messages.append({"role": "assistant", "content": response.text})
                else:
                    st.error(f"Google's servers are temporarily busy. Wait 10 seconds and try again. Details: {last_error}")
