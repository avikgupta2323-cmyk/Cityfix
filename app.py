import streamlit as st
import math
import io
import base64
import uuid
import time
import smtplib
import ssl
import random
from datetime import datetime, timedelta
from PIL import Image

# ─────────────────────────────────────────────
# SESSION STATE INITIALIZATION
# ─────────────────────────────────────────────
defaults = {
    "users": {},
    "issues": [],
    "votes_registry": [],
    "comments": {},
    "notifications": {},
    "current_user": None,
    "page": "splash",
    "admin_authenticated": False,
    "session_flags": {},
    "issues_loaded": False,
    "pending_otp": None,
    "selected_issue_id": None,
    "signup_step": "form",
    "signup_data": {},
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ─────────────────────────────────────────────
# GLOBAL CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
body, .stApp { background-color: #0E1117 !important; color: #FFFFFF !important; }
.stButton > button {
  background-color: #00ff26 !important; color: #000000 !important;
  border: none; border-radius: 8px; font-weight: 700;
}
.stButton > button:hover { background-color: #00cc1e !important; }
.stProgress > div > div { background-color: #E0FF00 !important; }
h1, h2, h3 { color: #FFFFFF !important; }
p, label, .stMarkdown { color: #000000 !important; background: transparent !important; }
.stTextInput > div > div > input {
  background-color: #1A1D24 !important;
  color: #FFFFFF !important;
  border: 1px solid #E0FF00 !important;
}
.stSelectbox > div > div {
  background-color: #1A1D24 !important;
  color: #FFFFFF !important;
}
.stTextArea > div > div > textarea {
  background-color: #1A1D24 !important;
  color: #FFFFFF !important;
  border: 1px solid #E0FF00 !important;
}
.stTabs [data-baseweb="tab"] {
  background-color: #1A1D24 !important;
  color: #C0C0C0 !important;
}
.stTabs [aria-selected="true"] {
  background-color: #E0FF00 !important;
  color: #000000 !important;
}
.stSidebar { background-color: #0E1117 !important; }
.stSidebar .stButton > button {
  width: 100% !important;
  text-align: left !important;
  background-color: #1A1D24 !important;
  color: #FFFFFF !important;
  border: 1px solid #333 !important;
  margin-bottom: 4px !important;
}
.stSidebar .stButton > button:hover {
  background-color: #E0FF00 !important;
  color: #000000 !important;
  border-color: #E0FF00 !important;
}
@keyframes urgencyPulse {
  0%   { box-shadow: 0 0 8px rgba(255,30,30,0.4); }
  50%  { box-shadow: 0 0 24px rgba(255,30,30,0.9); }
  100% { box-shadow: 0 0 8px rgba(255,30,30,0.4); }
}
.urgent-card { animation: urgencyPulse 1.5s infinite; border: 1px solid #FF1E1E !important; }
@keyframes flashBanner {
  0%,100%{background:#00FF99;color:#003322;}
  50%{background:#003322;color:#00FF99;}
}
.flash-banner { animation: flashBanner 1s infinite; padding:12px 20px; border-radius:8px; font-weight:700; text-align:center; font-size:18px; }
@keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:0.4;transform:scale(1.3)} }
.loader { width:20px;height:20px;background:#E0FF00;border-radius:50%;animation:pulse 1.2s infinite;margin:20px auto; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────

def compress_image(uploaded_file, max_width=1024):
    img = Image.open(uploaded_file)
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=75, optimize=True)
    return base64.b64encode(buffer.getvalue()).decode()


def haversine(lat1, lon1, lat2, lon2):
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def priority_score(issue):
    severity_map = {"Low": 1, "Medium": 2, "High": 3}
    hours_elapsed = (datetime.now() - issue["created_at"]).total_seconds() / 3600
    return (issue["votes"] * 10) + (severity_map[issue["severity"]] * 15) - (hours_elapsed * 0.1)


@st.cache_resource
def get_geocoder():
    from geopy.geocoders import Nominatim
    return Nominatim(user_agent="cityfix_app")


def get_locality(lat, lon):
    try:
        geocoder = get_geocoder()
        location = geocoder.reverse(f"{lat},{lon}", timeout=5)
        if location and location.raw.get("address"):
            addr = location.raw["address"]
            return addr.get("suburb") or addr.get("neighbourhood") or addr.get("city_district") or addr.get("city") or "Unknown Locality"
        return "Unknown Locality"
    except Exception:
        return "Unknown Locality"


def status_badge(status):
    styles = {
        "Reported": ("background:#2A2A2A;border:1px solid #888888;color:#C0C0C0;", "Reported"),
        "Verified": ("background:#003CFF;border:1px solid #001A99;color:#FFFFFF;", "Verified"),
        "In Progress": ("background:#FF6600;border:1px solid #CC5200;color:#000000;", "In Progress"),
        "Fixed": ("background:#00FF99;border:1px solid #009955;color:#003322;", "Fixed"),
        "Qualified for Municipal Escalation": ("background:#E0FF00;border:1px solid #b8cc00;color:#000000;", "⚖️ Qualified for Escalation"),
    }
    s, label = styles.get(status, ("background:#2A2A2A;border:1px solid #888;color:#C0C0C0;", status))
    return f'<span style="{s}padding:4px 12px;border-radius:999px;font-size:12px;font-weight:600;">{label}</span>'


def card(content_html, urgent=False):
    extra_class = ' class="urgent-card"' if urgent else ''
    extra_style = "" if urgent else "border: 1px solid #E0FF00;"
    return f"""<div{extra_class} style="
      background: #1A1D24;
      {extra_style}
      border-radius: 10px;
      box-shadow: 0 0 12px rgba(224, 255, 0, 0.15);
      padding: 20px;
      margin-bottom: 16px;
    ">{content_html}</div>"""


def img_html(issue):
    if issue.get("image_b64"):
        return f'<img src="data:image/jpeg;base64,{issue["image_b64"]}" style="width:100%;border-radius:8px;max-height:200px;object-fit:cover;">'
    elif issue.get("image_url"):
        return f'<img src="{issue["image_url"]}" style="width:100%;border-radius:8px;max-height:200px;object-fit:cover;">'
    else:
        return '<div style="width:100%;height:120px;background:#2A2A2A;border-radius:8px;display:flex;align-items:center;justify-content:center;color:#555;">No Image</div>'


def add_notification(user_id, icon, message):
    if user_id not in st.session_state["notifications"]:
        st.session_state["notifications"][user_id] = []
    st.session_state["notifications"][user_id].append({
        "icon": icon, "message": message,
        "timestamp": datetime.now()
    })


def update_civic_points(user_id, points):
    if user_id in st.session_state["users"]:
        st.session_state["users"][user_id]["civic_points"] += points
    if st.session_state["current_user"] and st.session_state["current_user"]["id"] == user_id:
        st.session_state["current_user"]["civic_points"] += points


def nav_to(page):
    st.session_state["page"] = page
    st.rerun()


# ─────────────────────────────────────────────
# MOCK DATA
# ─────────────────────────────────────────────
if not st.session_state["issues_loaded"]:
    mock_issues = [
        {
            "id": str(uuid.uuid4()),
            "title": "Deep Pothole at Hitech City Metro Station",
            "category": "Road Issues", "severity": "High", "votes": 83,
            "status": "Reported", "locality": "Madhapur",
            "lat": 17.4474, "lon": 78.3814,
            "creator_id": "mock_user_1",
            "description": "Massive pothole right at the exit of Hitech City metro station causing vehicles to swerve dangerously.",
            "created_at": datetime.now() - timedelta(hours=6),
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e4/Pothole_on_a_road_in_India.jpg/640px-Pothole_on_a_road_in_India.jpg",
            "image_b64": None,
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Overflowing Commercial Garbage Dump",
            "category": "Garbage", "severity": "Medium", "votes": 45,
            "status": "Verified", "locality": "Kondapur",
            "lat": 17.4611, "lon": 78.3688,
            "creator_id": "mock_user_2",
            "description": "Garbage bins overflowing since 3 days. Stench and health hazard for nearby residents.",
            "created_at": datetime.now() - timedelta(hours=18),
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2f/Garbage_pile.jpg/640px-Garbage_pile.jpg",
            "image_b64": None,
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Completely Dark Streetlights near DLF Gate 2",
            "category": "Streetlights", "severity": "High", "votes": 92,
            "status": "In Progress", "locality": "Gachibowli",
            "lat": 17.4428, "lon": 78.3571,
            "creator_id": "mock_user_3",
            "description": "Entire stretch of 200m near DLF Gate 2 has no working streetlights. Very unsafe at night.",
            "created_at": datetime.now() - timedelta(hours=30),
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5e/Broken_street_light.jpg/480px-Broken_street_light.jpg",
            "image_b64": None,
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Major Pipeline Water Leakage on Main Road",
            "category": "Water Leakage", "severity": "Low", "votes": 12,
            "status": "Fixed", "locality": "Miyapur",
            "lat": 17.4933, "lon": 78.3404,
            "creator_id": "mock_user_4",
            "description": "Underground pipeline burst causing water wastage and road damage near bus stop.",
            "created_at": datetime.now() - timedelta(hours=72),
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d9/Water_leak.jpg/480px-Water_leak.jpg",
            "image_b64": None,
        },
    ]
    st.session_state["issues"] = mock_issues
    st.session_state["issues_loaded"] = True

# ─────────────────────────────────────────────
# SIDEBAR NAVIGATION
# ─────────────────────────────────────────────
if st.session_state["current_user"] and st.session_state["page"] not in ("splash", "login"):
    with st.sidebar:
        st.markdown('<h2 style="color:#E0FF00">⚡ CityFix</h2>', unsafe_allow_html=True)
        user = st.session_state["current_user"]
        st.markdown(f'<p style="color:#C0C0C0;font-size:13px;">👤 {user["name"]} | 🏆 {user["civic_points"]} pts</p>', unsafe_allow_html=True)
        st.markdown("<hr style='border-color:#333'>", unsafe_allow_html=True)
        nav_items = [
            ("🏠 Home", "home"), ("📸 Report Issue", "report"),
            ("📍 Nearby Issues", "nearby"), ("🗺️ City Map", "map"),
            ("📋 My Reports", "my_reports"), ("🗳️ Voting", "voting"),
            ("🔔 Notifications", "notifications"), ("📤 Share & Download", "share"),
            ("👤 Profile", "profile"), ("🔐 Admin Panel", "admin"),
        ]
        for label, page_key in nav_items:
            if st.button(label, key=f"nav_{page_key}"):
                st.session_state["page"] = page_key
                st.rerun()

# ─────────────────────────────────────────────
# MODULE 1 — SPLASH SCREEN
# ─────────────────────────────────────────────
def page_splash():
    st.markdown("""
    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:80vh;text-align:center;">
      <div style="font-size:72px;font-weight:900;color:#E0FF00;letter-spacing:-2px;margin-bottom:12px;">⚡ CityFix</div>
      <div style="font-size:22px;color:#FFFFFF;margin-bottom:8px;">Your Voice for a Better City</div>
      <div style="font-size:14px;color:#C0C0C0;margin-bottom:24px;">Hyderabad Civic Issue Reporting Platform</div>
      <div class="loader"></div>
    </div>
    """, unsafe_allow_html=True)
    col1, col2, col3 = st.columns([2, 1, 2])
    with col2:
        if st.button("Enter CityFix →"):
            nav_to("login")


# ─────────────────────────────────────────────
# MODULE 2 — LOGIN / SIGN UP
# ─────────────────────────────────────────────
def page_login():
    st.markdown('<h1 style="text-align:center;color:#E0FF00;margin-bottom:4px;">⚡ CityFix</h1>', unsafe_allow_html=True)
    st.markdown('<p style="text-align:center;color:#C0C0C0;margin-bottom:24px;">Hyderabad\'s Civic Issue Platform</p>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab_login, tab_signup = st.tabs(["Log In", "Sign Up"])

        # --- LOG IN TAB ---
        with tab_login:
            st.markdown('<div style="height:12px"></div>', unsafe_allow_html=True)
            email_in = st.text_input("Email", key="login_email", placeholder="you@example.com")
            pass_in = st.text_input("Password", type="password", key="login_pass", placeholder="••••••••")

            if st.button("Log In", key="btn_login"):
                found = None
                for uid, u in st.session_state["users"].items():
                    if u["email"] == email_in and u.get("password") == pass_in:
                        found = u
                        break
                if found:
                    st.session_state["current_user"] = found
                    nav_to("home")
                else:
                    st.error("❌ Invalid email or password.")

            st.markdown('<div style="text-align:center;margin:12px 0;color:#555;">— or —</div>', unsafe_allow_html=True)

            if st.button("🔵 Continue with Google", key="btn_google", use_container_width=True):
                st.markdown("""
                <div style="background:#1A1D24;border:1px solid #4285F4;border-radius:8px;padding:12px 16px;margin-top:4px;">
                  <div style="color:#4285F4;font-weight:700;margin-bottom:4px;">Google OAuth not configured</div>
                  <div style="color:#C0C0C0;font-size:13px;">
                    To enable Google login, register a Google OAuth 2.0 app at
                    <b>console.cloud.google.com</b>, set the redirect URI, and add
                    <b>GOOGLE_CLIENT_ID</b> and <b>GOOGLE_CLIENT_SECRET</b> as environment secrets.<br><br>
                    For now, use <b>Sign Up</b> or the <b>Demo Account</b> button below.
                  </div>
                </div>""", unsafe_allow_html=True)

            if st.button("🎮 Use Demo Account", key="btn_demo"):
                demo_id = "demo_" + str(uuid.uuid4())[:8]
                demo = {
                    "id": demo_id, "name": "Demo Citizen", "email": "demo@cityfix.app",
                    "password": "demo", "lat": 17.4474, "lon": 78.3814,
                    "locality": "Madhapur", "civic_points": 150,
                    "reports": [], "created_at": datetime.now()
                }
                st.session_state["users"][demo_id] = demo
                st.session_state["current_user"] = demo
                nav_to("home")

        # --- SIGN UP TAB ---
        with tab_signup:
            st.markdown('<div style="height:12px"></div>', unsafe_allow_html=True)

            if st.session_state["signup_step"] == "form":
                name_su = st.text_input("Full Name", key="su_name", placeholder="Rahul Sharma")
                email_su = st.text_input("Email", key="su_email", placeholder="rahul@example.com")
                pass_su = st.text_input("Password", type="password", key="su_pass", placeholder="Min 6 characters")
                lat_su = st.number_input("Your Latitude", value=17.4474, format="%.6f", key="su_lat")
                lon_su = st.number_input("Your Longitude", value=78.3814, format="%.6f", key="su_lon")

                if st.button("Send OTP", key="btn_send_otp"):
                    if not name_su or not email_su or not pass_su:
                        st.error("Please fill all fields.")
                    elif len(pass_su) < 6:
                        st.error("Password must be at least 6 characters.")
                    else:
                        otp = str(random.randint(100000, 999999))
                        st.session_state["pending_otp"] = otp
                        st.session_state["signup_data"] = {
                            "name": name_su, "email": email_su,
                            "password": pass_su, "lat": lat_su, "lon": lon_su
                        }
                        # Try sending OTP via SMTP
                        sent = False
                        try:
                            context = ssl.create_default_context()
                            with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
                                server.login("noreply.cityfix@gmail.com", "placeholder")
                                server.sendmail("noreply.cityfix@gmail.com", email_su,
                                    f"Subject: CityFix OTP\n\nYour OTP is: {otp}")
                            sent = True
                        except Exception:
                            sent = False

                        if not sent:
                            st.markdown(f"""
                            <div style="background:#1A1D24;border:2px solid #E0FF00;border-radius:8px;padding:14px;margin-top:8px;">
                              <span style="color:#E0FF00;font-weight:700;">Mail server busy.</span>
                              <span style="color:#C0C0C0;"> Please try requesting your OTP again in a few moments.</span><br>
                              <span style="color:#888;font-size:12px;">(Dev mode: OTP is <b style="color:#E0FF00">{otp}</b>)</span>
                            </div>""", unsafe_allow_html=True)
                        st.session_state["signup_step"] = "otp"
                        st.rerun()

            elif st.session_state["signup_step"] == "otp":
                data = st.session_state["signup_data"]
                st.markdown(f'<p style="color:#C0C0C0;">OTP sent to <b>{data["email"]}</b></p>', unsafe_allow_html=True)
                otp_input = st.text_input("Enter 6-digit OTP", key="otp_field", placeholder="123456", max_chars=6)

                if st.button("Verify & Create Account", key="btn_verify"):
                    if otp_input == st.session_state["pending_otp"]:
                        locality = get_locality(data["lat"], data["lon"])
                        uid = str(uuid.uuid4())
                        new_user = {
                            "id": uid, "name": data["name"], "email": data["email"],
                            "password": data["password"], "lat": data["lat"], "lon": data["lon"],
                            "locality": locality, "civic_points": 0,
                            "reports": [], "created_at": datetime.now()
                        }
                        st.session_state["users"][uid] = new_user
                        st.session_state["current_user"] = new_user
                        st.session_state["signup_step"] = "form"
                        st.session_state["pending_otp"] = None

                        placeholder = st.empty()
                        placeholder.markdown(f"""
                        <div style="background:#1A1D24;border:2px solid #00FF99;border-radius:10px;padding:24px;text-align:center;">
                          <div style="font-size:32px;margin-bottom:8px;">🎉</div>
                          <div style="color:#00FF99;font-size:20px;font-weight:700;">Welcome to the team, {data["name"]}!</div>
                          <div style="color:#C0C0C0;margin-top:8px;">Your coordinates place you in <b style="color:#E0FF00">{locality}</b>.</div>
                          <div style="color:#888;margin-top:4px;">Gathering data for your micro-locality...</div>
                        </div>""", unsafe_allow_html=True)
                        time.sleep(2)
                        placeholder.empty()
                        nav_to("home")
                    else:
                        st.error("❌ Incorrect OTP. Please try again.")

                if st.button("← Back", key="btn_back_otp"):
                    st.session_state["signup_step"] = "form"
                    st.rerun()


# ─────────────────────────────────────────────
# MODULE 3 — HOME DASHBOARD
# ─────────────────────────────────────────────
def page_home():
    user = st.session_state["current_user"]
    st.markdown(f'<h1>Hi, {user["name"]} 👋</h1>', unsafe_allow_html=True)

    # User info card
    st.markdown(card(f"""
    <div style="display:flex;gap:32px;flex-wrap:wrap;">
      <div><span style="color:#888;font-size:12px;">LOCATION</span><br><span style="color:#FFFFFF;font-size:16px;">📍 {user["locality"]}</span></div>
      <div><span style="color:#888;font-size:12px;">COORDINATES</span><br><span style="color:#FFFFFF;font-size:16px;">{user["lat"]:.4f}, {user["lon"]:.4f}</span></div>
      <div><span style="color:#888;font-size:font-size:12px;">CIVIC POINTS</span><br><span style="color:#E0FF00;font-size:20px;font-weight:700;">🏆 {user["civic_points"]}</span></div>
    </div>
    """), unsafe_allow_html=True)

    # Action Grid
    st.markdown('<h3>Quick Actions</h3>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(card('<div style="text-align:center;font-size:40px;margin-bottom:8px;">📸</div><div style="text-align:center;color:#FFFFFF;font-weight:700;">Report an Issue</div>'), unsafe_allow_html=True)
        if st.button("Report Issue", key="home_report"):
            nav_to("report")
    with c2:
        st.markdown(card('<div style="text-align:center;font-size:40px;margin-bottom:8px;">📍</div><div style="text-align:center;color:#FFFFFF;font-weight:700;">View Nearby Issues</div>'), unsafe_allow_html=True)
        if st.button("Nearby Issues", key="home_nearby"):
            nav_to("nearby")
    with c3:
        st.markdown(card('<div style="text-align:center;font-size:40px;margin-bottom:8px;">📋</div><div style="text-align:center;color:#FFFFFF;font-weight:700;">My Reports</div>'), unsafe_allow_html=True)
        if st.button("My Reports", key="home_myreports"):
            nav_to("my_reports")

    # Search Bar
    st.markdown('<h3>Search Issues</h3>', unsafe_allow_html=True)
    search_q = st.text_input("🔍 Search civic issues...", placeholder="e.g. pothole, garbage, streetlight", key="home_search")
    if search_q:
        results = [i for i in st.session_state["issues"]
                   if search_q.lower() in i["title"].lower()
                   or search_q.lower() in i["description"].lower()
                   or search_q.lower() in i["category"].lower()]
        if results:
            for issue in results:
                is_urgent = issue["severity"] == "High" and issue["votes"] > 70
                st.markdown(card(f"""
                <div style="display:flex;gap:16px;align-items:flex-start;">
                  <div style="flex:0 0 80px;">{img_html(issue)}</div>
                  <div style="flex:1;">
                    <div style="color:#FFFFFF;font-weight:700;">{issue["title"]}</div>
                    <div style="margin-top:4px;">{status_badge(issue["status"])} &nbsp; <span style="color:#888;font-size:12px;">{issue["category"]} | {issue["locality"]}</span></div>
                    <div style="color:#E0FF00;font-size:13px;margin-top:4px;">👍 {issue["votes"]} votes</div>
                  </div>
                </div>""", urgent=is_urgent), unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#888;">No issues match your search.</p>', unsafe_allow_html=True)

    # Leaderboard
    st.markdown('<h3>🏆 Community Leaderboard</h3>', unsafe_allow_html=True)
    all_users = list(st.session_state["users"].values())
    all_users.sort(key=lambda u: u["civic_points"], reverse=True)
    top5 = all_users[:5]
    if top5:
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        rows = "".join([f"<tr><td style='color:#E0FF00;font-size:20px;'>{medals[i]}</td><td style='color:#FFFFFF;padding:8px 16px;'>{u['name']}</td><td style='color:#C0C0C0;'>{u['locality']}</td><td style='color:#E0FF00;font-weight:700;'>{u['civic_points']} pts</td></tr>" for i, u in enumerate(top5)])
        st.markdown(card(f"""
        <table style="width:100%;border-collapse:collapse;">
          <thead><tr><th style="color:#888;text-align:left;padding:4px 8px;">#</th><th style="color:#888;text-align:left;padding:4px 16px;">Name</th><th style="color:#888;text-align:left;">Locality</th><th style="color:#888;text-align:left;">Points</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>"""), unsafe_allow_html=True)
    else:
        st.markdown('<p style="color:#888;">No citizens registered yet. Be the first!</p>', unsafe_allow_html=True)


# ─────────────────────────────────────────────
# MODULE 4 — REPORT AN ISSUE
# ─────────────────────────────────────────────
def page_report():
    st.markdown('<h1>📸 Report an Issue</h1>', unsafe_allow_html=True)
    user = st.session_state["current_user"]

    tab_upload, tab_camera = st.tabs(["📁 Upload Photo", "📷 Take Photo"])
    image_b64 = None

    with tab_upload:
        uploaded = st.file_uploader("Upload an image of the issue", type=["jpg", "jpeg", "png", "webp"], key="report_upload")
        if uploaded:
            image_b64 = compress_image(uploaded)
            st.markdown(f'<img src="data:image/jpeg;base64,{image_b64}" style="width:100%;border-radius:8px;max-height:300px;object-fit:cover;">', unsafe_allow_html=True)
            st.session_state["report_b64"] = image_b64

    with tab_camera:
        st.markdown("""
        <div style="position:relative;">
          <div style="position:absolute;top:0;left:0;right:0;bottom:0;
            background: linear-gradient(rgba(224,255,0,0.2) 1px,transparent 1px) 0 33%/100% 33%,
                        linear-gradient(90deg,rgba(224,255,0,0.2) 1px,transparent 1px) 33% 0/33% 100%;
            pointer-events:none;z-index:10;border-radius:8px;"></div>
        </div>""", unsafe_allow_html=True)
        camera_img = st.camera_input("Take a photo", key="report_camera")
        if camera_img:
            image_b64 = compress_image(camera_img)
            st.session_state["report_b64"] = image_b64

    st.markdown('<h3>Issue Details</h3>', unsafe_allow_html=True)
    description = st.text_area(
        "Description",
        placeholder="e.g., Deep pothole on the left lane right after the metro pillar, causing traffic to slow down...",
        height=100, key="report_desc"
    )
    category = st.selectbox(
        "Category",
        ["Road Issues", "Garbage", "Drainage", "Water Leakage", "Streetlights", "Stray Animals", "Parks", "Illegal Dumping", "Other"],
        key="report_cat"
    )
    severity = st.radio("Severity", ["Low", "Medium", "High"], horizontal=True, key="report_sev")

    st.markdown('<h3>Location</h3>', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        lat = st.number_input("Latitude", value=user["lat"], format="%.6f", key="report_lat")
    with col2:
        lon = st.number_input("Longitude", value=user["lon"], format="%.6f", key="report_lon")

    b64 = st.session_state.get("report_b64") or image_b64

    if st.button("🚀 Submit Issue", key="btn_submit_issue"):
        if not description:
            st.error("Please add a description.")
            return

        # 30-meter duplicate check
        same_cat = [i for i in st.session_state["issues"] if i["category"] == category and i["status"] != "Fixed"]
        nearby_dup = None
        for existing in same_cat:
            dist = haversine(lat, lon, existing["lat"], existing["lon"])
            if dist < 30:
                nearby_dup = (existing, dist)
                break

        if nearby_dup and not st.session_state["session_flags"].get("bypass_dup"):
            ex_issue, ex_dist = nearby_dup
            st.markdown(card(f"""
            <div style="color:#FF6600;font-size:18px;font-weight:700;margin-bottom:12px;">⚠️ Wait! Is this the same issue?</div>
            <div style="color:#C0C0C0;margin-bottom:12px;">Someone else already flagged this nearby.</div>
            <div style="display:flex;gap:12px;align-items:flex-start;">
              <div style="flex:0 0 80px;">{img_html(ex_issue)}</div>
              <div>
                <div style="color:#FFFFFF;font-weight:700;">{ex_issue["title"]}</div>
                <div style="color:#888;font-size:13px;">{ex_dist:.0f} meters away • {ex_issue["category"]} • {ex_issue["locality"]}</div>
                <div style="margin-top:6px;">{status_badge(ex_issue["status"])}</div>
              </div>
            </div>"""), unsafe_allow_html=True)

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("👍 Support Existing Issue Instead", key="btn_support_existing"):
                    uid = st.session_state["current_user"]["id"]
                    eid = ex_issue["id"]
                    if (uid, eid) not in st.session_state["votes_registry"]:
                        st.session_state["votes_registry"].append((uid, eid))
                        ex_issue["votes"] += 1
                        update_civic_points(uid, 10)
                        add_notification(ex_issue["creator_id"], "🗳️", f"Your issue '{ex_issue['title']}' got a new vote!")
                        st.success("✅ You've supported the existing issue. +10 civic points!")
                    else:
                        st.info("You already voted on this issue.")
                    st.session_state["session_flags"].pop("bypass_dup", None)
            with col_b:
                if st.button("No, This Is Different — Submit Anyway", key="btn_bypass_dup"):
                    st.session_state["session_flags"]["bypass_dup"] = True
                    st.rerun()
            return

        # Clear bypass flag
        st.session_state["session_flags"].pop("bypass_dup", None)

        # Create new issue
        locality = get_locality(lat, lon)
        new_issue = {
            "id": str(uuid.uuid4()),
            "title": f"{category} Issue in {locality}",
            "category": category, "severity": severity,
            "votes": 0, "status": "Reported",
            "locality": locality, "lat": lat, "lon": lon,
            "creator_id": user["id"],
            "description": description,
            "created_at": datetime.now(),
            "image_url": None, "image_b64": b64,
        }
        st.session_state["issues"].append(new_issue)
        update_civic_points(user["id"], 50)
        user["reports"].append(new_issue["id"])
        if user["id"] in st.session_state["users"]:
            st.session_state["users"][user["id"]]["reports"].append(new_issue["id"])
        st.session_state["report_b64"] = None
        st.success("✅ Issue reported! +50 civic points earned.")
        time.sleep(1)
        nav_to("nearby")


# ─────────────────────────────────────────────
# MODULE 5 — NEARBY ISSUES
# ─────────────────────────────────────────────
def page_nearby():
    import folium
    from streamlit_folium import st_folium

    st.markdown('<h1>📍 Nearby Issues</h1>', unsafe_allow_html=True)
    user = st.session_state["current_user"]

    tab_map, tab_list = st.tabs(["🗺️ Map View", "📋 List View"])

    color_map = {
        "Road Issues": "red", "Garbage": "darkred", "Drainage": "purple",
        "Water Leakage": "blue", "Streetlights": "orange",
        "Stray Animals": "green", "Parks": "darkgreen",
        "Illegal Dumping": "gray", "Other": "cadetblue"
    }

    with tab_map:
        m = folium.Map(location=[17.3850, 78.4867], zoom_start=13,
                       tiles="CartoDB dark_matter")
        folium.Circle(
            location=[user["lat"], user["lon"]],
            radius=500, color="#E0FF00", fill=True, fill_opacity=0.1,
            popup="500m from your home"
        ).add_to(m)
        folium.CircleMarker(
            location=[user["lat"], user["lon"]],
            radius=8, color="#E0FF00", fill=True, fill_opacity=1,
            popup="Your Location"
        ).add_to(m)
        for issue in st.session_state["issues"]:
            clr = color_map.get(issue["category"], "cadetblue")
            img_tag = f'<img src="{issue["image_url"]}" style="width:120px;border-radius:4px;">' if issue.get("image_url") else ""
            popup_html = f"""<div style="min-width:160px;">
              {img_tag}
              <b>{issue["title"][:40]}</b><br>
              {issue["category"]} | {issue["locality"]}<br>
              👍 {issue["votes"]} votes<br>
              Status: {issue["status"]}
            </div>"""
            folium.CircleMarker(
                location=[issue["lat"], issue["lon"]],
                radius=10, color=clr, fill=True, fill_opacity=0.8,
                popup=folium.Popup(popup_html, max_width=200),
                tooltip=issue["title"][:40]
            ).add_to(m)
        st_folium(m, width=None, height=500)

    with tab_list:
        col_cat, col_sev = st.columns(2)
        with col_cat:
            cat_filter = st.selectbox("Filter by Category", ["All"] + ["Road Issues", "Garbage", "Drainage", "Water Leakage", "Streetlights", "Stray Animals", "Parks", "Illegal Dumping", "Other"], key="nearby_cat")
        with col_sev:
            sev_filter = st.selectbox("Filter by Severity", ["All", "Low", "Medium", "High"], key="nearby_sev")

        filtered = st.session_state["issues"]
        if cat_filter != "All":
            filtered = [i for i in filtered if i["category"] == cat_filter]
        if sev_filter != "All":
            filtered = [i for i in filtered if i["severity"] == sev_filter]

        if not filtered:
            st.markdown('<p style="color:#888;">No issues match the selected filters.</p>', unsafe_allow_html=True)
        for issue in filtered:
            dist = haversine(user["lat"], user["lon"], issue["lat"], issue["lon"])
            dist_note = f'📍 <span style="color:#E0FF00;font-weight:600;">{dist:.0f} meters from your home [Under 500 meters]</span>' if dist < 500 else f'📍 {dist/1000:.1f} km from your home'
            is_urgent = issue["severity"] == "High" and issue["votes"] > 70
            sev_colors = {"Low": "#00FF99", "Medium": "#FF6600", "High": "#FF1E1E"}
            sev_color = sev_colors.get(issue["severity"], "#888")
            content = f"""
            <div style="display:flex;gap:16px;align-items:flex-start;">
              <div style="flex:0 0 120px;">{img_html(issue)}</div>
              <div style="flex:1;">
                <div style="color:#FFFFFF;font-size:17px;font-weight:700;">{issue["title"]}</div>
                <div style="margin:6px 0;">{status_badge(issue["status"])} &nbsp;
                  <span style="background:{sev_color}22;border:1px solid {sev_color};color:{sev_color};padding:2px 10px;border-radius:999px;font-size:11px;font-weight:600;">{issue["severity"]}</span>
                  &nbsp; <span style="background:#222;border:1px solid #444;color:#C0C0C0;padding:2px 10px;border-radius:999px;font-size:11px;">{issue["category"]}</span>
                </div>
                <div style="color:#E0FF00;font-size:13px;">👍 {issue["votes"]} votes | 📍 {issue["locality"]}</div>
                <div style="font-size:12px;margin-top:4px;">{dist_note}</div>
              </div>
            </div>"""
            st.markdown(card(content, urgent=is_urgent), unsafe_allow_html=True)
            if st.button(f"View Details →", key=f"nearby_detail_{issue['id']}"):
                st.session_state["selected_issue_id"] = issue["id"]
                nav_to("issue_detail")


# ─────────────────────────────────────────────
# MODULE 6 — ISSUE DETAILS
# ─────────────────────────────────────────────
def page_issue_detail():
    issue_id = st.session_state.get("selected_issue_id")
    issue = next((i for i in st.session_state["issues"] if i["id"] == issue_id), None)
    if not issue:
        st.error("Issue not found.")
        if st.button("← Back to Nearby"):
            nav_to("nearby")
        return

    user = st.session_state["current_user"]

    if st.button("← Back"):
        nav_to("nearby")

    st.markdown(f'<h2>{issue["title"]}</h2>', unsafe_allow_html=True)

    col_img, col_meta = st.columns([1, 1])
    with col_img:
        st.markdown(img_html(issue), unsafe_allow_html=True)
    with col_meta:
        sev_colors = {"Low": "#00FF99", "Medium": "#FF6600", "High": "#FF1E1E"}
        sc = sev_colors.get(issue["severity"], "#888")
        st.markdown(card(f"""
        <div style="line-height:2;">
          <div style="color:#888;font-size:12px;">CATEGORY</div>
          <div style="color:#FFFFFF;font-weight:600;">{issue["category"]}</div>
          <div style="color:#888;font-size:12px;margin-top:8px;">SEVERITY</div>
          <div><span style="background:{sc}22;border:1px solid {sc};color:{sc};padding:3px 12px;border-radius:999px;font-size:12px;font-weight:700;">{issue["severity"]}</span></div>
          <div style="color:#888;font-size:12px;margin-top:8px;">STATUS</div>
          <div>{status_badge(issue["status"])}</div>
          <div style="color:#888;font-size:12px;margin-top:8px;">LOCALITY</div>
          <div style="color:#FFFFFF;">📍 {issue["locality"]}</div>
          <div style="color:#888;font-size:12px;margin-top:8px;">COORDINATES</div>
          <div style="color:#C0C0C0;font-size:13px;">{issue["lat"]}, {issue["lon"]}</div>
          <div style="color:#888;font-size:12px;margin-top:8px;">REPORTED</div>
          <div style="color:#C0C0C0;font-size:13px;">{issue["created_at"].strftime("%d %b %Y, %H:%M")}</div>
          <div style="color:#888;font-size:12px;margin-top:8px;">VOTES</div>
          <div style="color:#E0FF00;font-size:22px;font-weight:700;">👍 {issue["votes"]}</div>
        </div>"""), unsafe_allow_html=True)

    # Description
    st.markdown(card(f'<div style="color:#888;font-size:12px;margin-bottom:6px;">DESCRIPTION</div><div style="color:#C0C0C0;line-height:1.7;">{issue["description"]}</div>'), unsafe_allow_html=True)

    # Voting block
    st.markdown('<h3>Vote on This Issue</h3>', unsafe_allow_html=True)
    uid = user["id"]
    iid = issue["id"]
    if issue["creator_id"] == uid:
        st.button("🚫 You cannot vote on your own report", disabled=True, key=f"selfvote_{iid}")
    elif (uid, iid) in st.session_state["votes_registry"]:
        st.button("✅ Vote Cast Successfully", disabled=True, key=f"voted_{iid}")
        st.markdown('<p style="color:#00FF99;font-size:13px;">You already supported this issue.</p>', unsafe_allow_html=True)
    else:
        if st.button("👍 Support This Issue (+10 pts)", key=f"vote_{iid}"):
            st.session_state["votes_registry"].append((uid, iid))
            issue["votes"] += 1
            update_civic_points(uid, 10)
            add_notification(issue["creator_id"], "🗳️", f"Your issue '{issue['title']}' got a new vote! Total: {issue['votes']}")
            total_residents = max(len(st.session_state["users"]), 1)
            if issue["votes"] / total_residents >= 0.60:
                issue["status"] = "Qualified for Municipal Escalation"
                add_notification(issue["creator_id"], "🏛️", f"Your issue has reached 60% support and qualifies for Municipal Escalation!")
            if issue["votes"] >= 100:
                add_notification(issue["creator_id"], "🎉", f"Your issue reached 100 votes! Ready for escalation.")
            st.success("✅ Vote cast! +10 civic points.")
            st.rerun()

    # Comments
    st.markdown('<h3>💬 Community Discussion</h3>', unsafe_allow_html=True)
    comment_text = st.text_input("Add a comment...", key=f"comment_input_{iid}", placeholder="Share your thoughts or updates...")
    if st.button("Post Comment", key=f"post_comment_{iid}"):
        if comment_text.strip():
            if iid not in st.session_state["comments"]:
                st.session_state["comments"][iid] = []
            st.session_state["comments"][iid].append({
                "user": user["name"], "text": comment_text.strip(),
                "timestamp": datetime.now()
            })
            update_civic_points(uid, 5)
            st.success("Comment posted! +5 civic points.")
            st.rerun()

    if iid in st.session_state["comments"] and st.session_state["comments"][iid]:
        for c in st.session_state["comments"][iid]:
            st.markdown(card(f"""
            <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
              <span style="color:#E0FF00;font-weight:600;">{c["user"]}</span>
              <span style="color:#555;font-size:12px;">{c["timestamp"].strftime("%d %b, %H:%M")}</span>
            </div>
            <div style="color:#C0C0C0;">{c["text"]}</div>"""), unsafe_allow_html=True)

    # Social Share
    st.markdown('<h3>📤 Share This Issue</h3>', unsafe_allow_html=True)
    share_url = f"https://cityfix.app/issue/{iid}"
    wa_msg = f"Hey neighbors, there's a {issue['category']} issue reported in {issue['locality']} on CityFix. Please vote to escalate it! {share_url}"
    st.markdown(f"""
    <div style="display:flex;gap:12px;flex-wrap:wrap;">
      <a href="https://api.whatsapp.com/send?text={wa_msg.replace(' ', '+')}" target="_blank"
         style="background:#25D366;color:#FFFFFF;padding:8px 20px;border-radius:8px;text-decoration:none;font-weight:600;">📱 WhatsApp</a>
      <a href="https://www.facebook.com/sharer/sharer.php?u={share_url}" target="_blank"
         style="background:#1877F2;color:#FFFFFF;padding:8px 20px;border-radius:8px;text-decoration:none;font-weight:600;">📘 Facebook</a>
    </div>""", unsafe_allow_html=True)
    st.code(share_url)


# ─────────────────────────────────────────────
# MODULE 7 — COMMUNITY VOTING
# ─────────────────────────────────────────────
def page_voting():
    st.markdown('<h1>🗳️ Community Voting</h1>', unsafe_allow_html=True)

    if not st.session_state["issues"]:
        st.info("No issues to vote on.")
        return

    open_issues = [i for i in st.session_state["issues"] if i["status"] not in ("Fixed",)]
    if not open_issues:
        st.info("No open issues to vote on.")
        return

    issue_titles = {i["id"]: i["title"] for i in open_issues}
    selected_id = st.selectbox("Select an issue to vote on:", list(issue_titles.keys()),
                                format_func=lambda x: issue_titles[x], key="voting_select")
    issue = next((i for i in open_issues if i["id"] == selected_id), None)
    if not issue:
        return

    total_residents = max(len(st.session_state["users"]), 1)
    vote_pct = issue["votes"] / total_residents

    st.markdown(card(f"""
    <div style="color:#FFFFFF;font-size:20px;font-weight:700;margin-bottom:8px;">{issue["title"]}</div>
    <div style="color:#C0C0C0;margin-bottom:6px;">📍 {issue["locality"]} | {issue["category"]}</div>
    <div style="color:#C0C0C0;line-height:1.6;">{issue["description"]}</div>"""), unsafe_allow_html=True)

    if issue["votes"] >= 100 or vote_pct >= 0.60:
        st.markdown('<div class="flash-banner">🎉 Ready for Municipal Escalation!</div>', unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="color:#FFFFFF;font-size:18px;font-weight:700;margin-bottom:8px;">
          Needed: 100 Votes | Current: <span style="color:#E0FF00;">{issue["votes"]} Votes</span>
        </div>""", unsafe_allow_html=True)
        st.progress(min(issue["votes"] / 100, 1.0))

    uid = st.session_state["current_user"]["id"]
    iid = issue["id"]
    if issue["creator_id"] == uid:
        st.button("🚫 Cannot vote on your own issue", disabled=True, key=f"voting_selfvote_{iid}")
    elif (uid, iid) in st.session_state["votes_registry"]:
        st.button("✅ You already voted", disabled=True, key=f"voting_alreadyvoted_{iid}")
    else:
        if st.button("👍 Cast Your Vote (+10 pts)", key=f"voting_cast_{iid}"):
            st.session_state["votes_registry"].append((uid, iid))
            issue["votes"] += 1
            update_civic_points(uid, 10)
            add_notification(issue["creator_id"], "🗳️", f"Your issue '{issue['title']}' got a new vote!")
            if issue["votes"] / total_residents >= 0.60:
                issue["status"] = "Qualified for Municipal Escalation"
            st.success("✅ Vote cast! +10 civic points.")
            st.rerun()

    # Recent activity
    st.markdown('<h3>Recent Comments</h3>', unsafe_allow_html=True)
    comments = st.session_state["comments"].get(iid, [])
    if comments:
        for c in reversed(comments[-5:]):
            st.markdown(card(f'<span style="color:#E0FF00;font-weight:600;">{c["user"]}</span> <span style="color:#555;font-size:12px;">· {c["timestamp"].strftime("%d %b, %H:%M")}</span><br><span style="color:#C0C0C0;">{c["text"]}</span>'), unsafe_allow_html=True)
    else:
        st.markdown('<p style="color:#888;">No comments yet. Be the first to comment in Issue Details.</p>', unsafe_allow_html=True)


# ─────────────────────────────────────────────
# MODULE 8 — CITY MAP  (+ Heat Map)
# ─────────────────────────────────────────────

def _neighborhood_health(issues):
    """Return dict: locality -> {score, open, fixed, critical_votes, issues}."""
    from collections import defaultdict
    zones = defaultdict(lambda: {"open": 0, "fixed": 0, "deductions": 0, "critical_votes": 0, "issues": []})
    sev_deduct = {"Low": 5, "Medium": 10, "High": 18}
    for iss in issues:
        loc = iss["locality"]
        zones[loc]["issues"].append(iss)
        if iss["status"] == "Fixed":
            zones[loc]["fixed"] += 1
        else:
            zones[loc]["open"] += 1
            zones[loc]["deductions"] += sev_deduct.get(iss["severity"], 5)
            if iss["severity"] == "High":
                zones[loc]["critical_votes"] += iss["votes"]
    result = {}
    for loc, z in zones.items():
        raw = max(0, 100 - z["deductions"] + z["fixed"] * 3)
        result[loc] = {
            "score": min(100, raw),
            "open": z["open"],
            "fixed": z["fixed"],
            "critical_votes": z["critical_votes"],
            "issues": z["issues"],
        }
    return result


def _health_color(score):
    if score >= 80: return "#00FF99", "Healthy"
    if score >= 60: return "#E0FF00", "Moderate"
    if score >= 40: return "#FF6600", "Stressed"
    return "#FF1E1E", "Critical"


def page_map():
    import folium
    from folium.plugins import HeatMap, MarkerCluster
    from streamlit_folium import st_folium

    st.markdown('<h1>🗺️ City Map</h1>', unsafe_allow_html=True)
    user = st.session_state["current_user"]
    issues = st.session_state["issues"]

    color_map = {
        "Road Issues": "red", "Garbage": "darkred", "Drainage": "purple",
        "Water Leakage": "blue", "Streetlights": "orange",
        "Stray Animals": "green", "Parks": "darkgreen",
        "Illegal Dumping": "gray", "Other": "cadetblue"
    }
    color_hex = {
        "red": "#FF4444", "darkred": "#8B0000", "purple": "#9933FF",
        "blue": "#3399FF", "orange": "#FF9900", "green": "#33CC33",
        "darkgreen": "#006400", "gray": "#888888", "cadetblue": "#5F9EA0"
    }

    tab_issue, tab_heat, tab_zones = st.tabs(["🗺️ Issue Map", "🔥 Heat Map", "📊 Zone Analytics"])

    # ── TAB 1: Issue Map (with cluster) ──────────────────────────
    with tab_issue:
        m = folium.Map(location=[17.3850, 78.4867], zoom_start=12, tiles="CartoDB dark_matter")
        folium.Circle(
            location=[user["lat"], user["lon"]],
            radius=500, color="#E0FF00", fill=True, fill_opacity=0.1
        ).add_to(m)
        folium.CircleMarker(
            location=[user["lat"], user["lon"]],
            radius=10, color="#E0FF00", fill=True, fill_opacity=1,
            tooltip="📍 Your Location"
        ).add_to(m)
        cluster = MarkerCluster(name="Issues").add_to(m)
        for issue in issues:
            clr = color_map.get(issue["category"], "cadetblue")
            img_tag = f'<img src="{issue["image_url"]}" style="width:120px;border-radius:4px;">' if issue.get("image_url") else ""
            popup_html = f"""<div style="min-width:160px;">
              {img_tag}
              <b>{issue["title"][:40]}</b><br>
              {issue["category"]}<br>
              👍 {issue["votes"]} votes<br>
              Status: {issue["status"]}
            </div>"""
            folium.CircleMarker(
                location=[issue["lat"], issue["lon"]],
                radius=12, color=color_hex.get(clr, "#888"), fill=True, fill_opacity=0.85,
                popup=folium.Popup(popup_html, max_width=220),
                tooltip=f"{issue['title'][:30]} | {issue['votes']} votes"
            ).add_to(cluster)
        st_folium(m, width=None, height=540, key="map_issue")
        legend_html = "".join([
            f'<span style="display:inline-flex;align-items:center;gap:6px;margin:4px 12px 4px 0;">'
            f'<span style="width:14px;height:14px;border-radius:50%;background:{color_hex.get(v,"#888")};display:inline-block;"></span>'
            f'<span style="color:#C0C0C0;font-size:13px;">{k}</span></span>'
            for k, v in color_map.items()
        ])
        st.markdown(card(f'<div style="color:#888;font-size:12px;margin-bottom:8px;">CATEGORY LEGEND</div><div style="display:flex;flex-wrap:wrap;">{legend_html}</div>'), unsafe_allow_html=True)

    # ── TAB 2: Heat Map ───────────────────────────────────────────
    with tab_heat:
        sev_weight = {"Low": 1, "Medium": 2, "High": 3}

        # Controls
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            weight_mode = st.selectbox(
                "Weight by", ["Severity × Votes", "Vote Count Only", "Raw Count (Equal Weight)"],
                key="hm_weight"
            )
        with col_b:
            cat_filter = st.selectbox(
                "Filter Category", ["All Categories"] + list(color_map.keys()),
                key="hm_cat"
            )
        with col_c:
            radius_px = st.slider("Blur Radius", 10, 60, 25, key="hm_radius")

        filtered = issues if cat_filter == "All Categories" else [i for i in issues if i["category"] == cat_filter]

        heat_data = []
        for iss in filtered:
            if weight_mode == "Severity × Votes":
                w = sev_weight.get(iss["severity"], 1) * max(iss["votes"], 1)
            elif weight_mode == "Vote Count Only":
                w = max(iss["votes"], 1)
            else:
                w = 1
            heat_data.append([iss["lat"], iss["lon"], w])

        hm = folium.Map(location=[17.3850, 78.4867], zoom_start=12, tiles="CartoDB dark_matter")

        # User marker
        folium.CircleMarker(
            location=[user["lat"], user["lon"]],
            radius=10, color="#E0FF00", fill=True, fill_opacity=1,
            tooltip="📍 Your Location"
        ).add_to(hm)

        if heat_data:
            HeatMap(
                heat_data,
                radius=radius_px,
                blur=radius_px // 2,
                min_opacity=0.4,
                max_zoom=15,
                gradient={
                    "0.0": "#003CFF",
                    "0.3": "#9933FF",
                    "0.55": "#FF6600",
                    "0.75": "#FF1E1E",
                    "1.0": "#FFFFFF",
                }
            ).add_to(hm)

        # Neighborhood health zone circles
        zone_data = _neighborhood_health(issues)
        # Approximate zone centre coords (centroid of issues in that locality)
        from collections import defaultdict
        loc_coords = defaultdict(list)
        for iss in issues:
            loc_coords[iss["locality"]].append((iss["lat"], iss["lon"]))
        for loc, coords in loc_coords.items():
            clat = sum(c[0] for c in coords) / len(coords)
            clon = sum(c[1] for c in coords) / len(coords)
            zinfo = zone_data.get(loc, {"score": 100, "open": 0, "fixed": 0})
            zcolor, zlabel = _health_color(zinfo["score"])
            folium.Circle(
                location=[clat, clon],
                radius=800,
                color=zcolor,
                fill=True,
                fill_opacity=0.12,
                weight=2,
                tooltip=f"{loc}: {zlabel} ({zinfo['score']}/100) | {zinfo['open']} open issues"
            ).add_to(hm)
            folium.Marker(
                location=[clat, clon],
                icon=folium.DivIcon(
                    html=f'<div style="font-size:11px;font-weight:700;color:{zcolor};text-shadow:0 0 4px #000,0 0 4px #000;white-space:nowrap;">{loc}<br>{zinfo["score"]}/100</div>',
                    icon_size=(90, 32),
                    icon_anchor=(45, 16),
                ),
                tooltip=f"{loc} — {zlabel}"
            ).add_to(hm)

        st_folium(hm, width=None, height=540, key="map_heat")

        # Heat map legend
        gradient_html = """
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px;">
          <span style="color:#888;font-size:12px;">HEAT INTENSITY:</span>
          <div style="display:flex;align-items:center;gap:4px;">
            <span style="width:100px;height:12px;border-radius:6px;background:linear-gradient(to right,#003CFF,#9933FF,#FF6600,#FF1E1E,#FFFFFF);display:inline-block;"></span>
          </div>
          <span style="color:#888;font-size:11px;">Low →</span><span style="color:#FFFFFF;font-size:11px;">High</span>
        </div>
        <div style="color:#888;font-size:12px;margin-bottom:6px;">NEIGHBORHOOD HEALTH ZONES:</div>
        <div style="display:flex;gap:16px;flex-wrap:wrap;">
          <span style="color:#00FF99;font-size:13px;">🟢 80–100 Healthy</span>
          <span style="color:#E0FF00;font-size:13px;">🟡 60–79 Moderate</span>
          <span style="color:#FF6600;font-size:13px;">🟠 40–59 Stressed</span>
          <span style="color:#FF1E1E;font-size:13px;">🔴 0–39 Critical</span>
        </div>"""
        st.markdown(card(gradient_html), unsafe_allow_html=True)

    # ── TAB 3: Zone Analytics ─────────────────────────────────────
    with tab_zones:
        st.markdown('<h3>📊 Neighborhood Civic Health Scores</h3>', unsafe_allow_html=True)

        zone_data = _neighborhood_health(issues)
        if not zone_data:
            st.markdown('<p style="color:#888;">No issues yet to analyze.</p>', unsafe_allow_html=True)
        else:
            sorted_zones = sorted(zone_data.items(), key=lambda x: x[1]["score"])

            # Summary KPIs
            avg_score = sum(z["score"] for z in zone_data.values()) / len(zone_data)
            total_open = sum(z["open"] for z in zone_data.values())
            total_fixed = sum(z["fixed"] for z in zone_data.values())
            worst = sorted_zones[0][0]
            best = sorted_zones[-1][0]

            kc1, kc2, kc3, kc4 = st.columns(4)
            for col, label, value, color in [
                (kc1, "Avg Health Score", f"{avg_score:.0f}/100", "#E0FF00"),
                (kc2, "Open Issues", str(total_open), "#FF6600"),
                (kc3, "Fixed Issues", str(total_fixed), "#00FF99"),
                (kc4, "Needs Attention", worst, "#FF1E1E"),
            ]:
                with col:
                    st.markdown(card(f'<div style="color:#888;font-size:11px;">{label}</div><div style="color:{color};font-size:22px;font-weight:900;">{value}</div>'), unsafe_allow_html=True)

            st.markdown('<h3>Zone Breakdown</h3>', unsafe_allow_html=True)

            for loc, zinfo in sorted_zones:
                score = zinfo["score"]
                zcolor, zlabel = _health_color(score)
                bar_pct = score

                cat_counts = {}
                for iss in zinfo["issues"]:
                    cat_counts[iss["category"]] = cat_counts.get(iss["category"], 0) + 1
                top_cats = sorted(cat_counts.items(), key=lambda x: -x[1])[:3]
                cat_html = " ".join([f'<span style="background:#222;border:1px solid #444;color:#C0C0C0;padding:2px 8px;border-radius:999px;font-size:11px;">{c} ×{n}</span>' for c, n in top_cats])

                is_worst = (loc == worst)
                is_best = (loc == best)
                badge = ' <span style="background:#FF1E1E22;border:1px solid #FF1E1E;color:#FF1E1E;padding:2px 8px;border-radius:999px;font-size:11px;">⚠️ Needs Attention</span>' if is_worst else (' <span style="background:#00FF9922;border:1px solid #00FF99;color:#00FF99;padding:2px 8px;border-radius:999px;font-size:11px;">🌟 Top Locality</span>' if is_best else "")

                content = f"""
                <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px;">
                  <div style="flex:1;min-width:180px;">
                    <div style="color:#FFFFFF;font-size:17px;font-weight:700;">📍 {loc}{badge}</div>
                    <div style="margin:6px 0;display:flex;flex-wrap:wrap;gap:4px;">{cat_html}</div>
                    <div style="color:#888;font-size:13px;">
                      {zinfo["open"]} open · {zinfo["fixed"]} fixed · {zinfo["critical_votes"]} critical votes
                    </div>
                  </div>
                  <div style="flex:0 0 140px;text-align:right;">
                    <div style="color:{zcolor};font-size:28px;font-weight:900;">{score}/100</div>
                    <div style="color:{zcolor};font-size:13px;font-weight:600;">{zlabel}</div>
                  </div>
                </div>
                <div style="margin-top:10px;">
                  <div style="height:8px;background:#2A2A2A;border-radius:4px;overflow:hidden;">
                    <div style="width:{bar_pct}%;height:100%;background:{zcolor};border-radius:4px;transition:width 0.5s;"></div>
                  </div>
                </div>"""
                st.markdown(card(content), unsafe_allow_html=True)


# ─────────────────────────────────────────────
# MODULE 9 — MY REPORTS
# ─────────────────────────────────────────────
def page_my_reports():
    st.markdown('<h1>📋 My Reports</h1>', unsafe_allow_html=True)
    user = st.session_state["current_user"]
    my_issues = [i for i in st.session_state["issues"] if i["creator_id"] == user["id"]]

    if not my_issues:
        st.markdown(card("""
        <div style="text-align:center;padding:20px;">
          <div style="font-size:48px;margin-bottom:12px;">📭</div>
          <div style="color:#FFFFFF;font-size:18px;font-weight:700;margin-bottom:8px;">No reports yet!</div>
          <div style="color:#C0C0C0;margin-bottom:16px;">Be the first in your locality to report a civic issue.</div>
        </div>"""), unsafe_allow_html=True)
        if st.button("📸 Report Now", key="my_report_cta"):
            nav_to("report")
        return

    status_steps = ["Reported", "Verified", "In Progress", "Fixed"]

    for issue in my_issues:
        sev_colors = {"Low": "#00FF99", "Medium": "#FF6600", "High": "#FF1E1E"}
        sc = sev_colors.get(issue["severity"], "#888")
        is_urgent = issue["severity"] == "High" and issue["votes"] > 70

        # Status trail
        def step_html(s):
            idx = status_steps.index(s) if s in status_steps else -1
            cur_idx = status_steps.index(issue["status"]) if issue["status"] in status_steps else -1
            done = idx <= cur_idx
            return (
                f'<div style="display:flex;flex-direction:column;align-items:center;flex:1;">'
                f'<div style="width:16px;height:16px;border-radius:50%;background:{"#E0FF00" if done else "#2A2A2A"};border:2px solid {"#E0FF00" if done else "#444"};"></div>'
                f'<div style="font-size:11px;margin-top:4px;color:{"#E0FF00" if done else "#555"};">{s}</div>'
                f'</div>'
            )

        trail = "".join([step_html(s) for s in status_steps])
        connector = '<div style="flex:1;height:2px;background:#333;margin:7px -8px 0;"></div>'
        trail_html = f'<div style="display:flex;align-items:flex-start;margin-top:12px;position:relative;">{trail}</div>'

        content = f"""
        <div style="display:flex;gap:16px;align-items:flex-start;">
          <div style="flex:0 0 100px;">{img_html(issue)}</div>
          <div style="flex:1;">
            <div style="color:#FFFFFF;font-size:16px;font-weight:700;">{issue["title"]}</div>
            <div style="margin:6px 0;">{status_badge(issue["status"])} &nbsp;
              <span style="background:{sc}22;border:1px solid {sc};color:{sc};padding:2px 10px;border-radius:999px;font-size:11px;">{issue["severity"]}</span>
            </div>
            <div style="color:#888;font-size:13px;">{issue["category"]} | {issue["locality"]} | {issue["created_at"].strftime("%d %b %Y")}</div>
            <div style="color:#E0FF00;font-size:13px;">👍 {issue["votes"]} votes</div>
          </div>
        </div>
        <div style="margin-top:12px;">
          <div style="color:#888;font-size:11px;margin-bottom:4px;">STATUS PROGRESS</div>
          {trail_html}
        </div>"""

        st.markdown(card(content, urgent=is_urgent), unsafe_allow_html=True)
        if st.button(f"View Details", key=f"myreport_detail_{issue['id']}"):
            st.session_state["selected_issue_id"] = issue["id"]
            nav_to("issue_detail")


# ─────────────────────────────────────────────
# MODULE 10 — NOTIFICATIONS
# ─────────────────────────────────────────────
def page_notifications():
    st.markdown('<h1>🔔 Notifications</h1>', unsafe_allow_html=True)
    uid = st.session_state["current_user"]["id"]
    notifs = st.session_state["notifications"].get(uid, [])

    if not notifs:
        st.markdown(card("""
        <div style="text-align:center;padding:20px;">
          <div style="font-size:48px;margin-bottom:12px;">🔕</div>
          <div style="color:#FFFFFF;font-size:18px;font-weight:700;">No notifications yet.</div>
          <div style="color:#C0C0C0;margin-top:8px;">Start engaging with your community!</div>
        </div>"""), unsafe_allow_html=True)
        return

    def relative_time(dt):
        diff = datetime.now() - dt
        s = diff.total_seconds()
        if s < 60: return f"{int(s)}s ago"
        if s < 3600: return f"{int(s/60)}m ago"
        if s < 86400: return f"{int(s/3600)}h ago"
        return dt.strftime("%d %b")

    for notif in reversed(notifs):
        st.markdown(card(f"""
        <div style="display:flex;justify-content:space-between;align-items:flex-start;">
          <div style="display:flex;gap:12px;align-items:flex-start;">
            <span style="font-size:24px;">{notif["icon"]}</span>
            <div style="color:#C0C0C0;">{notif["message"]}</div>
          </div>
          <span style="color:#555;font-size:12px;white-space:nowrap;margin-left:12px;">{relative_time(notif["timestamp"])}</span>
        </div>"""), unsafe_allow_html=True)


# ─────────────────────────────────────────────
# MODULE 11 — DOWNLOAD & SHARE HUB
# ─────────────────────────────────────────────
def page_share():
    from fpdf import FPDF

    st.markdown('<h1>📤 Share & Download Hub</h1>', unsafe_allow_html=True)

    issues = st.session_state["issues"]
    if not issues:
        st.info("No issues available.")
        return

    issue_titles = {i["id"]: i["title"] for i in issues}
    sel_id = st.selectbox("Select an issue:", list(issue_titles.keys()),
                           format_func=lambda x: issue_titles[x], key="share_select")
    issue = next((i for i in issues if i["id"] == sel_id), None)
    if not issue:
        return

    total_residents = max(len(st.session_state["users"]), 1)
    vote_ratio = issue["votes"] / total_residents
    unlocked = vote_ratio >= 0.60 or issue["status"] == "Qualified for Municipal Escalation"

    st.markdown(card(f"""
    <div style="color:#FFFFFF;font-size:18px;font-weight:700;margin-bottom:8px;">{issue["title"]}</div>
    <div style="color:#C0C0C0;margin-bottom:8px;">{issue["category"]} | {issue["locality"]}</div>
    <div style="display:flex;gap:16px;">
      <div style="color:#C0C0C0;">👍 {issue["votes"]} votes</div>
      <div style="color:#C0C0C0;">👥 {total_residents} registered citizens</div>
      <div style="color:#{"00FF99" if unlocked else "888"};font-weight:700;">{"✅ Unlocked" if unlocked else "🔒 " + str(round(vote_ratio*100,1)) + "% / 60% required"}</div>
    </div>"""), unsafe_allow_html=True)

    st.markdown('<h3>📄 Official PDF Complaint</h3>', unsafe_allow_html=True)
    if not unlocked:
        st.markdown("""
        <button disabled title="Needs 60% neighborhood support to unlock"
          style="background:#333;color:#666;border:none;border-radius:8px;padding:10px 24px;font-weight:700;cursor:not-allowed;font-size:15px;">
          🔒 Download Official PDF (Needs 60% support)
        </button>""", unsafe_allow_html=True)
    else:
        def generate_pdf(iss):
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 20)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 10, "CityFix — Official Complaint Document", ln=True, align="C")
            pdf.set_font("Helvetica", size=10)
            pdf.cell(0, 6, f"Complaint ID: {iss['id']}", ln=True)
            pdf.cell(0, 6, f"Generated: {datetime.now().strftime('%d %b %Y, %H:%M')}", ln=True)
            pdf.ln(4)
            pdf.set_font("Helvetica", "B", 13)
            pdf.cell(0, 8, iss["title"], ln=True)
            pdf.set_font("Helvetica", size=11)
            pdf.cell(0, 6, f"Category: {iss['category']}  |  Severity: {iss['severity']}", ln=True)
            pdf.cell(0, 6, f"Locality: {iss['locality']}", ln=True)
            pdf.cell(0, 6, f"Coordinates: {iss['lat']}, {iss['lon']}", ln=True)
            pdf.cell(0, 6, f"Status: {iss['status']}", ln=True)
            pdf.cell(0, 6, f"Community Votes: {iss['votes']}", ln=True)
            pdf.ln(4)
            pdf.multi_cell(0, 6, f"Description: {iss['description']}")
            pdf.ln(6)
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_fill_color(224, 255, 0)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 10, f"Endorsed via Community Consensus ({len(st.session_state['users'])} Registered Citizens)", ln=True, fill=True, align="C")
            return bytes(pdf.output())

        pdf_bytes = generate_pdf(issue)
        st.download_button(
            label="📥 Download Official PDF",
            data=pdf_bytes,
            file_name=f"CityFix_{issue['id'][:8]}.pdf",
            mime="application/pdf"
        )

    st.markdown('<h3>📱 Share on Social Media</h3>', unsafe_allow_html=True)
    share_url = f"https://cityfix.app/issue/{issue['id']}"
    wa_msg = f"Hey neighbors, I just reported a {issue['category']} issue in {issue['locality']} on CityFix. We need more votes to escalate to GHMC. Please vote!"
    fb_url = f"https://www.facebook.com/sharer/sharer.php?u={share_url}"
    st.markdown(f"""
    <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px;">
      <a href="https://api.whatsapp.com/send?text={wa_msg.replace(' ','+')}" target="_blank"
         style="background:#25D366;color:#FFFFFF;padding:10px 24px;border-radius:8px;text-decoration:none;font-weight:700;">📱 WhatsApp</a>
      <a href="{fb_url}" target="_blank"
         style="background:#1877F2;color:#FFFFFF;padding:10px 24px;border-radius:8px;text-decoration:none;font-weight:700;">📘 Facebook</a>
    </div>
    <div style="color:#888;margin-bottom:8px;">Copy link to share:</div>""", unsafe_allow_html=True)
    st.code(share_url)


# ─────────────────────────────────────────────
# MODULE 12 — PROFILE & GAMIFICATION
# ─────────────────────────────────────────────
def page_profile():
    user = st.session_state["current_user"]
    st.markdown('<h1>👤 My Profile</h1>', unsafe_allow_html=True)

    initials = "".join(w[0].upper() for w in user["name"].split()[:2])
    my_issues = [i for i in st.session_state["issues"] if i["creator_id"] == user["id"]]
    has_fixed = any(i["status"] == "Fixed" for i in my_issues)

    # User card
    st.markdown(card(f"""
    <div style="display:flex;gap:20px;align-items:center;flex-wrap:wrap;">
      <div style="width:72px;height:72px;border-radius:50%;background:#1A1D24;border:3px solid #E0FF00;
           display:flex;align-items:center;justify-content:center;font-size:28px;font-weight:700;color:#E0FF00;flex-shrink:0;">
        {initials}
      </div>
      <div>
        <div style="color:#FFFFFF;font-size:22px;font-weight:700;">{user["name"]}</div>
        <div style="color:#C0C0C0;font-size:14px;">{user["email"]}</div>
        <div style="color:#C0C0C0;font-size:14px;">📍 {user["locality"]}</div>
        <div style="color:#888;font-size:12px;">{user["lat"]:.4f}, {user["lon"]:.4f} • Member since {user["created_at"].strftime("%b %Y")}</div>
      </div>
    </div>"""), unsafe_allow_html=True)

    # Civic Points
    st.markdown('<h3>💰 Civic Points Wallet</h3>', unsafe_allow_html=True)
    st.markdown(card(f"""
    <div style="text-align:center;padding:12px 0;">
      <div style="font-size:56px;font-weight:900;color:#E0FF00;">{user["civic_points"]}</div>
      <div style="color:#C0C0C0;margin-bottom:16px;">Total Civic Points</div>
      <div style="text-align:left;max-width:320px;margin:0 auto;">
        <div style="color:#888;font-size:13px;margin-bottom:6px;">How you earn points:</div>
        <div style="color:#C0C0C0;font-size:13px;line-height:2;">
          +50 pts — Verified report submitted<br>
          +10 pts — Vote cast on an issue<br>
          +5 pts — Comment posted<br>
          +100 pts — Your issue marked Fixed
        </div>
      </div>
    </div>"""), unsafe_allow_html=True)

    # Achievement Badges
    st.markdown('<h3>🏅 Achievement Badges</h3>', unsafe_allow_html=True)
    badges = [
        {"icon": "🌱", "name": "Civic Novice", "desc": "Welcome aboard!", "unlocked": True},
        {"icon": "📰", "name": "Local Reporter", "desc": "3+ reports submitted", "unlocked": len(my_issues) >= 3},
        {"icon": "🏛️", "name": "Community Pillar", "desc": "300+ civic points", "unlocked": user["civic_points"] >= 300},
        {"icon": "🦸", "name": "Hyderabad Hero", "desc": "An issue you reported was fixed", "unlocked": has_fixed},
    ]

    cols = st.columns(4)
    for i, badge in enumerate(badges):
        with cols[i]:
            if badge["unlocked"]:
                st.markdown(card(f"""
                <div style="text-align:center;padding:12px 4px;">
                  <div style="font-size:36px;">{badge["icon"]}</div>
                  <div style="color:#E0FF00;font-weight:700;font-size:13px;margin-top:8px;">{badge["name"]}</div>
                  <div style="color:#888;font-size:11px;margin-top:4px;">{badge["desc"]}</div>
                  <div style="color:#00FF99;font-size:11px;margin-top:6px;">✅ Unlocked</div>
                </div>"""), unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="background:#111;border:1px solid #333;border-radius:10px;padding:20px 4px;margin-bottom:16px;text-align:center;">
                  <div style="font-size:36px;filter:grayscale(1);opacity:0.4;">{badge["icon"]}🔒</div>
                  <div style="color:#555;font-weight:700;font-size:13px;margin-top:8px;">{badge["name"]}</div>
                  <div style="color:#444;font-size:11px;margin-top:4px;">{badge["desc"]}</div>
                  <div style="color:#444;font-size:11px;margin-top:6px;">🔒 Locked</div>
                </div>""", unsafe_allow_html=True)

    st.markdown('<div style="height:16px"></div>', unsafe_allow_html=True)
    if st.button("🚪 Logout", key="btn_logout"):
        st.session_state["current_user"] = None
        st.session_state["admin_authenticated"] = False
        nav_to("login")


# ─────────────────────────────────────────────
# MODULE 13 — ADMIN & MUNICIPAL MATRIX
# ─────────────────────────────────────────────
def page_admin():
    if not st.session_state["admin_authenticated"]:
        st.markdown('<h1>🔐 Admin Panel</h1>', unsafe_allow_html=True)
        st.markdown(card("""
        <div style="text-align:center;padding:12px;">
          <div style="font-size:48px;margin-bottom:8px;">🔒</div>
          <div style="color:#FFFFFF;font-size:18px;font-weight:700;margin-bottom:4px;">Restricted Access</div>
          <div style="color:#C0C0C0;font-size:14px;">Municipal administrator access only</div>
        </div>"""), unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            pwd = st.text_input("Enter Admin Password", type="password", key="admin_pwd")
            if st.button("Access Admin Panel", key="btn_admin_access"):
                if pwd == "Avikgupta23":
                    st.session_state["admin_authenticated"] = True
                    st.rerun()
                else:
                    st.error("❌ Access Denied. Incorrect password.")
        st.stop()

    st.markdown('<h1>🏛️ Admin & Municipal Matrix</h1>', unsafe_allow_html=True)

    tab_queue, tab_ai, tab_dispatch, tab_helpline = st.tabs(["📊 Priority Queue", "✍️ AI Escalation Mail", "📨 Ward Officer Dispatch", "📞 Helpline Directory"])

    # TAB 1: Priority Queue
    with tab_queue:
        sorted_issues = sorted(st.session_state["issues"], key=priority_score, reverse=True)
        for rank, issue in enumerate(sorted_issues, 1):
            score = priority_score(issue)
            sev_colors = {"Low": "#00FF99", "Medium": "#FF6600", "High": "#FF1E1E"}
            sc = sev_colors.get(issue["severity"], "#888")

            st.markdown(card(f"""
            <div style="display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap;">
              <div style="color:#E0FF00;font-size:28px;font-weight:900;min-width:36px;">#{rank}</div>
              <div style="flex:0 0 80px;">{img_html(issue)}</div>
              <div style="flex:1;min-width:200px;">
                <div style="color:#FFFFFF;font-weight:700;">{issue["title"]}</div>
                <div style="margin:4px 0;">{status_badge(issue["status"])} &nbsp;
                  <span style="background:{sc}22;border:1px solid {sc};color:{sc};padding:2px 8px;border-radius:999px;font-size:11px;">{issue["severity"]}</span>
                </div>
                <div style="color:#888;font-size:13px;">{issue["category"]} | {issue["locality"]} | 👍 {issue["votes"]} votes</div>
                <div style="color:#E0FF00;font-size:13px;margin-top:4px;">Priority Score: <b>{score:.1f}</b></div>
              </div>
            </div>"""), unsafe_allow_html=True)

            status_options = ["Reported", "Verified", "In Progress", "Fixed", "Qualified for Municipal Escalation"]
            cur_idx = status_options.index(issue["status"]) if issue["status"] in status_options else 0
            new_status = st.selectbox(
                "Update Status", status_options,
                index=cur_idx, key=f"admin_status_{issue['id']}"
            )
            if st.button(f"Update Status", key=f"admin_update_{issue['id']}"):
                old_status = issue["status"]
                issue["status"] = new_status
                add_notification(issue["creator_id"], "🏛️", f"Your issue '{issue['title']}' status updated to: {new_status}")
                if new_status == "Fixed" and old_status != "Fixed":
                    update_civic_points(issue["creator_id"], 100)
                    add_notification(issue["creator_id"], "✅", f"Your issue '{issue['title']}' has been FIXED! +100 civic points!")
                st.success(f"Status updated to: {new_status}")
                st.rerun()

    # TAB 2: AI Escalation Mail
    with tab_ai:
        st.markdown('<h3>✍️ AI Municipal Escalation Mail Generator</h3>', unsafe_allow_html=True)
        if not st.session_state["issues"]:
            st.info("No issues available.")
        else:
            titles = {i["id"]: i["title"] for i in st.session_state["issues"]}
            sel_id = st.selectbox("Select issue for escalation:", list(titles.keys()),
                                   format_func=lambda x: titles[x], key="ai_mail_select")
            issue = next((i for i in st.session_state["issues"] if i["id"] == sel_id), None)

            if issue and st.button("✍️ Draft AI Municipal Mail", key="btn_draft_mail"):
                total_res = max(len(st.session_state["users"]), 1)
                pct = round((issue["votes"] / total_res) * 100, 1)
                mail_lines = [
                    f"To: GHMC Ward Officer, {issue['locality']} Zone",
                    f"Subject: Urgent Civic Infrastructure Complaint — {issue['category']} | ID: {issue['id'][:8]}",
                    "",
                    "Dear Officer,",
                    "",
                    "This is an official escalation filed through the CityFix Citizen Platform on behalf of",
                    f"{issue['votes']} verified residents of {issue['locality']}, Hyderabad.",
                    "",
                    f"Nature of Issue: {issue['title']}",
                    f"Coordinates: {issue['lat']}, {issue['lon']}",
                    f"Reported On: {issue['created_at'].strftime('%d %b %Y, %H:%M')}",
                    f"Community Support: {issue['votes']} votes ({pct}% of neighborhood)",
                    "",
                    f"Description: {issue['description']}",
                    "",
                    "This issue has cleared the 60% community threshold and qualifies for immediate municipal review.",
                    "We respectfully request on-site inspection and resolution within 7 working days.",
                    "",
                    "Regards,",
                    "CityFix Platform | Citizen Governance Division",
                ]

                placeholder = st.empty()
                full_text = ""
                for line in mail_lines:
                    full_text += line + "\n"
                    placeholder.markdown(card(f'<pre style="color:#C0C0C0;font-family:monospace;white-space:pre-wrap;font-size:13px;">{full_text}</pre>'), unsafe_allow_html=True)
                    time.sleep(0.04)

    # TAB 3: Ward Officer Email Dispatch
    with tab_dispatch:
        from fpdf import FPDF

        st.markdown('<h3>📨 Ward Officer Email Dispatch</h3>', unsafe_allow_html=True)

        if "dispatch_log" not in st.session_state:
            st.session_state["dispatch_log"] = []

        all_issues = st.session_state["issues"]
        qualified = [i for i in all_issues
                     if i["status"] == "Qualified for Municipal Escalation"
                     or i["votes"] >= 50]

        if not qualified:
            st.markdown(card("""
            <div style="text-align:center;padding:20px;">
              <div style="font-size:48px;margin-bottom:8px;">📭</div>
              <div style="color:#FFFFFF;font-size:18px;font-weight:700;">No qualified issues yet.</div>
              <div style="color:#C0C0C0;margin-top:8px;">Issues need 50+ votes or Municipal Escalation status to appear here.</div>
            </div>"""), unsafe_allow_html=True)
        else:
            # ── Issue multi-select ───────────────────────────────
            st.markdown(card(f"""
            <div style="display:flex;gap:24px;flex-wrap:wrap;">
              <div style="text-align:center;">
                <div style="color:#E0FF00;font-size:28px;font-weight:900;">{len(qualified)}</div>
                <div style="color:#888;font-size:12px;">Qualified Issues</div>
              </div>
              <div style="text-align:center;">
                <div style="color:#FF6600;font-size:28px;font-weight:900;">{sum(i["votes"] for i in qualified)}</div>
                <div style="color:#888;font-size:12px;">Total Community Votes</div>
              </div>
              <div style="text-align:center;">
                <div style="color:#00FF99;font-size:28px;font-weight:900;">{len(set(i["locality"] for i in qualified))}</div>
                <div style="color:#888;font-size:12px;">Localities Affected</div>
              </div>
              <div style="text-align:center;">
                <div style="color:#FFFFFF;font-size:28px;font-weight:900;">{len(st.session_state["dispatch_log"])}</div>
                <div style="color:#888;font-size:12px;">Dispatches Sent</div>
              </div>
            </div>"""), unsafe_allow_html=True)

            issue_labels = {
                i["id"]: f"[{i['votes']}v · {i['severity']}] {i['title'][:55]} — {i['locality']}"
                for i in qualified
            }
            selected_ids = st.multiselect(
                "Select issues to include in this dispatch bundle:",
                options=list(issue_labels.keys()),
                format_func=lambda x: issue_labels[x],
                default=[qualified[0]["id"]] if qualified else [],
                key="dispatch_select"
            )

            if not selected_ids:
                st.markdown('<p style="color:#888;margin-top:8px;">Select at least one issue to compose a dispatch.</p>', unsafe_allow_html=True)
            else:
                sel_issues = [i for i in qualified if i["id"] in selected_ids]
                localities = list(dict.fromkeys(i["locality"] for i in sel_issues))
                categories = list(dict.fromkeys(i["category"] for i in sel_issues))
                total_votes = sum(i["votes"] for i in sel_issues)
                total_residents = max(len(st.session_state["users"]), 1)
                avg_pct = round((total_votes / (total_residents * len(sel_issues))) * 100, 1)

                st.markdown('<h3 style="margin-top:16px;">📋 Compose Dispatch</h3>', unsafe_allow_html=True)

                # Pre-filled form
                col_to, col_cc = st.columns(2)
                with col_to:
                    ward_zone = localities[0] if len(localities) == 1 else "Multiple Zones"
                    to_email = st.text_input(
                        "To (Ward Officer Email)",
                        value=f"wardofficer.{localities[0].lower().replace(' ','')}.ghmc@hyderabad.gov.in",
                        key="dispatch_to"
                    )
                with col_cc:
                    cc_email = st.text_input(
                        "CC (Commissioner / Deputy)",
                        value="commissioner.ghmc@hyderabad.gov.in",
                        key="dispatch_cc"
                    )

                subject_default = (
                    f"CityFix Bundle Escalation — {len(sel_issues)} Issue{'s' if len(sel_issues)>1 else ''} "
                    f"| {', '.join(localities[:2])}{'...' if len(localities)>2 else ''} Zone | {datetime.now().strftime('%d %b %Y')}"
                )
                subject = st.text_input("Subject", value=subject_default, key="dispatch_subject")

                # Auto-compose body
                issue_lines = "\n".join([
                    f"  {idx+1}. [{iss['severity']} | {iss['category']}] {iss['title']}\n"
                    f"     Location: {iss['locality']} ({iss['lat']}, {iss['lon']})\n"
                    f"     Votes: {iss['votes']} | Reported: {iss['created_at'].strftime('%d %b %Y')}\n"
                    f"     Status: {iss['status']}\n"
                    f"     ID: {iss['id'][:12]}"
                    for idx, iss in enumerate(sel_issues)
                ])
                auto_body = (
                    f"To: GHMC Ward Officer(s), {', '.join(localities)} Zone(s)\n"
                    f"CC: GHMC Commissioner\n\n"
                    f"Dear Officer,\n\n"
                    f"This is an official multi-issue escalation bundle filed through the CityFix Citizen "
                    f"Governance Platform on {datetime.now().strftime('%d %B %Y')} on behalf of the "
                    f"registered citizens of Hyderabad.\n\n"
                    f"SUMMARY\n"
                    f"{'─'*40}\n"
                    f"Total Issues in Bundle : {len(sel_issues)}\n"
                    f"Localities Covered     : {', '.join(localities)}\n"
                    f"Categories             : {', '.join(categories)}\n"
                    f"Aggregate Community Votes : {total_votes} ({avg_pct}% avg neighborhood support)\n"
                    f"{'─'*40}\n\n"
                    f"ISSUE DETAILS\n\n"
                    f"{issue_lines}\n\n"
                    f"All issues listed above have cleared the community threshold and qualify for "
                    f"immediate on-site inspection. We respectfully request resolution within 7 working "
                    f"days and written acknowledgement of this escalation.\n\n"
                    f"A full PDF complaint bundle is attached to this email for official records.\n\n"
                    f"Regards,\n"
                    f"CityFix Platform | Citizen Governance Division\n"
                    f"Hyderabad Civic Issue Reporting System\n"
                    f"Generated: {datetime.now().strftime('%d %b %Y, %H:%M IST')}"
                )
                body = st.text_area("Email Body", value=auto_body, height=280, key="dispatch_body")

                # ── PDF Bundle generator ──────────────────────────
                def generate_bundle_pdf(issues_list, email_body_text):
                    pdf = FPDF()

                    # Cover page
                    pdf.add_page()
                    pdf.set_fill_color(0, 0, 0)
                    pdf.rect(0, 0, 210, 297, "F")
                    pdf.set_font("Helvetica", "B", 24)
                    pdf.set_text_color(224, 255, 0)
                    pdf.ln(30)
                    pdf.cell(0, 12, "CityFix", ln=True, align="C")
                    pdf.set_font("Helvetica", "B", 14)
                    pdf.set_text_color(255, 255, 255)
                    pdf.cell(0, 8, "Official Multi-Issue Escalation Bundle", ln=True, align="C")
                    pdf.set_font("Helvetica", size=10)
                    pdf.set_text_color(192, 192, 192)
                    pdf.cell(0, 6, f"Generated: {datetime.now().strftime('%d %B %Y, %H:%M IST')}", ln=True, align="C")
                    pdf.ln(10)
                    # Summary box (white bg)
                    pdf.set_fill_color(255, 255, 255)
                    pdf.set_text_color(0, 0, 0)
                    pdf.set_font("Helvetica", "B", 11)
                    pdf.cell(0, 8, f"Bundle Summary", ln=True, align="C", fill=True)
                    pdf.set_font("Helvetica", size=10)
                    pdf.cell(0, 6, f"Total Issues: {len(issues_list)}  |  Localities: {', '.join(dict.fromkeys(i['locality'] for i in issues_list))}", ln=True, align="C", fill=True)
                    pdf.cell(0, 6, f"Total Votes: {sum(i['votes'] for i in issues_list)}  |  Date: {datetime.now().strftime('%d %b %Y')}", ln=True, align="C", fill=True)
                    pdf.ln(10)
                    # Email body excerpt
                    pdf.set_font("Helvetica", "B", 10)
                    pdf.set_text_color(0, 0, 0)
                    pdf.cell(0, 7, "COVER LETTER", ln=True)
                    pdf.set_font("Helvetica", size=9)
                    for line in email_body_text.split("\n")[:30]:
                        try:
                            pdf.multi_cell(0, 5, line if line.strip() else " ")
                        except Exception:
                            pdf.multi_cell(0, 5, line.encode("latin-1", "replace").decode("latin-1"))

                    # One page per issue
                    for idx, iss in enumerate(issues_list, 1):
                        pdf.add_page()
                        pdf.set_font("Helvetica", "B", 14)
                        pdf.set_text_color(0, 0, 0)
                        pdf.cell(0, 10, f"Issue #{idx} of {len(issues_list)}", ln=True)
                        pdf.set_fill_color(224, 255, 0)
                        pdf.set_text_color(0, 0, 0)
                        pdf.set_font("Helvetica", "B", 12)
                        safe_title = iss["title"].encode("latin-1", "replace").decode("latin-1")
                        pdf.cell(0, 9, safe_title, ln=True, fill=True)
                        pdf.ln(3)
                        pdf.set_font("Helvetica", size=10)
                        pdf.set_fill_color(255, 255, 255)
                        fields = [
                            ("Complaint ID", iss["id"]),
                            ("Category", iss["category"]),
                            ("Severity", iss["severity"]),
                            ("Locality", iss["locality"]),
                            ("Coordinates", f"{iss['lat']}, {iss['lon']}"),
                            ("Status", iss["status"]),
                            ("Community Votes", str(iss["votes"])),
                            ("Reported On", iss["created_at"].strftime("%d %b %Y, %H:%M")),
                            ("Reporter ID", iss["creator_id"]),
                        ]
                        for label, value in fields:
                            pdf.set_font("Helvetica", "B", 10)
                            pdf.cell(55, 7, f"{label}:", border="B")
                            pdf.set_font("Helvetica", size=10)
                            safe_val = str(value).encode("latin-1", "replace").decode("latin-1")
                            pdf.cell(0, 7, safe_val, border="B", ln=True)
                        pdf.ln(4)
                        pdf.set_font("Helvetica", "B", 10)
                        pdf.cell(0, 7, "Description:", ln=True)
                        pdf.set_font("Helvetica", size=10)
                        safe_desc = iss["description"].encode("latin-1", "replace").decode("latin-1")
                        pdf.multi_cell(0, 6, safe_desc)
                        pdf.ln(6)
                        # Stamp
                        pdf.set_fill_color(224, 255, 0)
                        pdf.set_text_color(0, 0, 0)
                        pdf.set_font("Helvetica", "B", 10)
                        pdf.cell(0, 8,
                            f"Endorsed by CityFix Citizen Platform — {iss['votes']} community votes",
                            ln=True, fill=True, align="C"
                        )

                    return bytes(pdf.output())

                # ── Action buttons ───────────────────────────────
                st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
                col_pdf, col_send = st.columns(2)

                with col_pdf:
                    if st.button("📄 Generate & Preview PDF Bundle", key="btn_gen_pdf"):
                        with st.spinner("Generating PDF bundle..."):
                            pdf_bytes = generate_bundle_pdf(sel_issues, body)
                            st.session_state["dispatch_pdf"] = pdf_bytes
                            st.session_state["dispatch_pdf_issues"] = len(sel_issues)
                        st.success(f"✅ PDF bundle ready — {len(sel_issues)} issues compiled.")

                    if st.session_state.get("dispatch_pdf"):
                        st.download_button(
                            label=f"📥 Download PDF Bundle ({st.session_state['dispatch_pdf_issues']} Issues)",
                            data=st.session_state["dispatch_pdf"],
                            file_name=f"CityFix_Bundle_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                            mime="application/pdf",
                            key="btn_dl_pdf"
                        )

                with col_send:
                    if st.button("🚀 Send Dispatch to Ward Officer", key="btn_send_dispatch"):
                        with st.spinner("Connecting to mail server..."):
                            pdf_bytes = generate_bundle_pdf(sel_issues, body)
                            sent = False
                            error_msg = ""
                            try:
                                import email as email_lib
                                from email.mime.multipart import MIMEMultipart
                                from email.mime.text import MIMEText
                                from email.mime.application import MIMEApplication

                                msg = MIMEMultipart()
                                msg["From"] = "noreply.cityfix@gmail.com"
                                msg["To"] = to_email
                                msg["CC"] = cc_email
                                msg["Subject"] = subject
                                msg.attach(MIMEText(body, "plain"))
                                attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
                                attachment.add_header("Content-Disposition", "attachment",
                                    filename=f"CityFix_Bundle_{datetime.now().strftime('%Y%m%d')}.pdf")
                                msg.attach(attachment)

                                context = ssl.create_default_context()
                                with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
                                    server.login("noreply.cityfix@gmail.com", "placeholder_pass")
                                    server.sendmail(msg["From"], [to_email, cc_email], msg.as_string())
                                sent = True
                            except Exception as e:
                                error_msg = str(e)

                        dispatch_record = {
                            "timestamp": datetime.now(),
                            "to": to_email,
                            "cc": cc_email,
                            "subject": subject,
                            "issues": [i["title"][:40] for i in sel_issues],
                            "issue_ids": [i["id"] for i in sel_issues],
                            "votes_total": total_votes,
                            "localities": localities,
                            "sent": sent,
                            "pdf_size_kb": round(len(pdf_bytes) / 1024, 1),
                        }
                        st.session_state["dispatch_log"].append(dispatch_record)
                        st.session_state["dispatch_pdf"] = pdf_bytes

                        if sent:
                            st.success("✅ Dispatch sent successfully!")
                        else:
                            st.markdown(f"""
                            <div style="background:#1A1D24;border:2px solid #E0FF00;border-radius:10px;padding:16px;margin-top:8px;">
                              <div style="color:#E0FF00;font-weight:700;font-size:16px;margin-bottom:8px;">📬 Dispatch Logged (Mail Server Unavailable)</div>
                              <div style="color:#C0C0C0;font-size:13px;margin-bottom:8px;">
                                The SMTP server is not configured in this environment. Your dispatch has been <b>logged and the PDF is ready to download</b>.
                                Forward the PDF to:
                              </div>
                              <div style="color:#FFFFFF;font-size:14px;font-weight:600;">📧 {to_email}</div>
                              <div style="color:#C0C0C0;font-size:13px;">CC: {cc_email}</div>
                              <div style="color:#555;font-size:11px;margin-top:8px;">Technical: {error_msg[:120]}</div>
                            </div>""", unsafe_allow_html=True)

                        for iss in sel_issues:
                            add_notification(iss["creator_id"], "🏛️",
                                f"Your issue '{iss['title'][:35]}...' was included in an official dispatch to GHMC ward officer.")

                # ── Dispatch Log ──────────────────────────────────
                if st.session_state["dispatch_log"]:
                    st.markdown('<h3 style="margin-top:24px;">📜 Dispatch History</h3>', unsafe_allow_html=True)
                    for rec in reversed(st.session_state["dispatch_log"]):
                        status_icon = "✅" if rec["sent"] else "📬"
                        status_label = "Sent" if rec["sent"] else "Logged (Download Ready)"
                        status_col = "#00FF99" if rec["sent"] else "#E0FF00"
                        issues_preview = "<br>".join([f"• {t}" for t in rec["issues"][:4]])
                        if len(rec["issues"]) > 4:
                            issues_preview += f"<br><span style='color:#555'>+ {len(rec['issues'])-4} more</span>"

                        st.markdown(card(f"""
                        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap;">
                          <div style="flex:1;min-width:220px;">
                            <div style="color:#FFFFFF;font-weight:700;margin-bottom:4px;">{rec["subject"][:60]}...</div>
                            <div style="color:#888;font-size:12px;margin-bottom:8px;">
                              📧 {rec["to"]} &nbsp;|&nbsp; 📋 CC: {rec["cc"]}<br>
                              🕐 {rec["timestamp"].strftime("%d %b %Y, %H:%M")} &nbsp;|&nbsp;
                              📍 {", ".join(rec["localities"][:3])} &nbsp;|&nbsp;
                              👍 {rec["votes_total"]} votes &nbsp;|&nbsp;
                              📎 {rec["pdf_size_kb"]} KB PDF
                            </div>
                            <div style="color:#C0C0C0;font-size:12px;line-height:1.8;">{issues_preview}</div>
                          </div>
                          <div style="text-align:right;flex-shrink:0;">
                            <div style="font-size:22px;">{status_icon}</div>
                            <div style="color:{status_col};font-size:12px;font-weight:700;">{status_label}</div>
                            <div style="color:#888;font-size:11px;">{len(rec["issues"])} issue{'s' if len(rec['issues'])!=1 else ''}</div>
                          </div>
                        </div>"""), unsafe_allow_html=True)

    # TAB 4: Helpline Directory
    with tab_helpline:
        st.markdown('<h3>📞 Municipal Helpline Directory</h3>', unsafe_allow_html=True)
        helplines = [
            ("🏛️ GHMC Helpline", "21111111", "Greater Hyderabad Municipal Corporation"),
            ("💧 Water Board", "155313", "Hyderabad Metropolitan Water Supply & Sewerage Board"),
            ("⚡ Power Distribution", "1912", "Southern Power Distribution Company (TGSPDCL)"),
        ]
        for icon_name, number, desc in helplines:
            st.markdown(card(f"""
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
              <div>
                <div style="color:#FFFFFF;font-size:18px;font-weight:700;">{icon_name}</div>
                <div style="color:#888;font-size:13px;">{desc}</div>
              </div>
              <div style="color:#E0FF00;font-size:28px;font-weight:900;">📞 {number}</div>
            </div>"""), unsafe_allow_html=True)

    st.markdown('<div style="height:16px"></div>', unsafe_allow_html=True)
    if st.button("🚪 Exit Admin Mode", key="btn_exit_admin"):
        st.session_state["admin_authenticated"] = False
        nav_to("home")


# ─────────────────────────────────────────────
# MAIN ROUTING
# ─────────────────────────────────────────────
page = st.session_state["page"]

if st.session_state["current_user"] is None and page not in ("splash", "login"):
    st.session_state["page"] = "login"
    page = "login"

if page == "splash":
    page_splash()
elif page == "login":
    page_login()
elif page == "home":
    page_home()
elif page == "report":
    page_report()
elif page == "nearby":
    page_nearby()
elif page == "issue_detail":
    page_issue_detail()
elif page == "voting":
    page_voting()
elif page == "map":
    page_map()
elif page == "my_reports":
    page_my_reports()
elif page == "notifications":
    page_notifications()
elif page == "share":
    page_share()
elif page == "profile":
    page_profile()
elif page == "admin":
    page_admin()
else:
    st.error(f"Unknown page: {page}")
    if st.button("Go Home"):
        nav_to("home")
