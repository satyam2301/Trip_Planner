import os
import sys
from pathlib import Path
import time
import uuid
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

# Add project root to sys.path so 'backend' modules are resolvable
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

load_dotenv(ROOT_DIR / ".env")

# Page configuration
st.set_page_config(
    page_title="AI Travel Planner | Autonomous Multi-Agent System",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS styling (loaded from separate external stylesheet)
CSS_PATH = Path(__file__).resolve().parent / "style.css"
if CSS_PATH.exists():
    with open(CSS_PATH, "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


# --- Vector Brand Icon (Modern Compass Rose - Crisp, Theme-Adaptive Vector) ---
BRAND_ICON_SVG = """<div class='brand-icon-box'>
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10" stroke="url(#brandGrad)" stroke-width="2.2"/>
        <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" fill="url(#brandGrad)" stroke="none"/>
        <defs>
            <linearGradient id="brandGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="var(--brand-stop-start)"/>
                <stop offset="100%" stop-color="var(--brand-stop-end)"/>
            </linearGradient>
        </defs>
    </svg>
</div>"""


# --- Helper: Modern JS Bridge via st.iframe (Includes Dynamic Theme Sync) ---
def run_js_bridge(script_content: str = ""):
    """Executes a JS script using st.iframe while synchronizing theme state with parent DOM."""
    theme_sync_js = """
    (function() {
        function syncTheme() {
            try {
                const doc = window.parent.document;
                const stApp = doc.querySelector('.stApp');
                if (stApp) {
                    const bg = window.parent.getComputedStyle(stApp).backgroundColor;
                    const rgb = bg.match(/\\d+/g);
                    if (rgb && rgb.length >= 3) {
                        const lum = 0.299 * parseInt(rgb[0]) + 0.587 * parseInt(rgb[1]) + 0.114 * parseInt(rgb[2]);
                        const theme = lum < 128 ? 'dark' : 'light';
                        if (stApp.getAttribute('data-theme') !== theme) {
                            stApp.setAttribute('data-theme', theme);
                            doc.documentElement.setAttribute('data-theme', theme);
                        }
                    }
                }
            } catch(e) {}
        }
        syncTheme();
    })();
    """
    html_content = f"<script>{theme_sync_js}\n{script_content}</script>"
    if hasattr(st, "iframe"):
        st.iframe(html_content, height=1)
    else:
        components.html(html_content, height=0)


# Run initial theme detection
run_js_bridge()


# --- Backend & Auth Imports ---
from backend.main import app, stream_travel_planner    
from backend.tools.currency_tool import get_live_exchange_rate

# Always reload pdf_generator to prevent stale in-memory cached bytecode
import importlib
import backend.pdf_generator
importlib.reload(backend.pdf_generator)
from backend.pdf_generator import generate_itinerary_pdf

from backend.auth import (
    register_user,
    authenticate_user,
    create_session_token,
    validate_session_token,
    validate_password_complexity,
    get_user_saved_sessions,
    format_user_thread_id
)


# --- Session State & Authentication Initialization ---
if "user" not in st.session_state:
    st.session_state.user = None
if "session_token" not in st.session_state:
    st.session_state.session_token = None
if "current_state" not in st.session_state:
    st.session_state.current_state = None
if "active_thread_id" not in st.session_state:
    st.session_state.active_thread_id = None


# --- Check URL Query Parameter for 30-Day Session Token ---
query_token = st.query_params.get("session")
if st.session_state.user is None and query_token:
    validated_user = validate_session_token(query_token)
    if validated_user:
        st.session_state.user = validated_user
        st.session_state.session_token = query_token
    else:
        # Token expired or invalid
        st.query_params.clear()


# --- Local Storage JS Bridge for Seamless 30-Day Auto-Login ---
# If user is not yet logged in and no query param was in the URL, check browser's localStorage
if st.session_state.user is None and not query_token:
    run_js_bridge("""
    (function() {
        try {
            const token = window.parent.localStorage.getItem('travel_planner_session_token');
            const params = new URLSearchParams(window.parent.location.search);
            if (token && !params.get('session')) {
                params.set('session', token);
                window.parent.location.search = params.toString();
            }
        } catch (e) {
            console.warn("LocalStorage auth sync notice:", e);
        }
    })();
    """)


# ==============================================================================
# 🔒 AUTHENTICATION SCREEN (Shown when user is not logged in)
# ==============================================================================
if st.session_state.user is None:
    st.markdown(
        f"""
        <div class='auth-header-wrapper'>
            <div class='brand-header-title' style='justify-content: center;'>
                {BRAND_ICON_SVG}
                <span class='brand-text'>AI Travel Planner</span>
            </div>
            <div class='animated-tagline-container' style='justify-content: center; margin: 0.5rem 0;'>
                <span class='typewriter-text'>Plan your dream trip with personalized itineraries.</span>
            </div>
            <div class='auth-sub-header'>
                Sign in or create an account to access your personal autonomous travel agents. Your session will remain securely active for 30 days.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    col1, col2, col3 = st.columns([1, 1.8, 1])
    with col2:
        tab_login, tab_signup = st.tabs(["🔑 Sign In", "✨ Create Account"])

        # Tab 1: Sign In
        with tab_login:
            st.markdown("#### Welcome Back")
            with st.form("login_form"):
                login_email = st.text_input("Email Address", placeholder="name@example.com")
                login_pass = st.text_input("Password", type="password", placeholder="Enter your password")
                remember_me = st.checkbox("Keep me signed in", value=True)
                login_submitted = st.form_submit_button("🚀 Sign In", type="primary", width="stretch")

            if login_submitted:
                if not login_email or not login_pass:
                    st.error("Please enter both email and password.")
                else:
                    auth_res = authenticate_user(login_email, login_pass)
                    if auth_res.get("success"):
                        user = auth_res.get("user")
                        token = create_session_token(user["id"], user["email"], user.get("full_name", ""))
                        st.session_state.user = user
                        st.session_state.session_token = token
                        st.query_params["session"] = token

                        # Sync token into browser localStorage for 30 days persistence
                        run_js_bridge(f"""
                        try {{
                            window.parent.localStorage.setItem('travel_planner_session_token', '{token}');
                        }} catch (e) {{}}
                        """)

                        st.success(f"Welcome back, {user.get('full_name', 'Traveler')}! Logging you in...")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(auth_res.get("error", "Invalid email or password."))

        # Tab 2: Create Account
        with tab_signup:
            st.markdown("#### New Traveler Registration")
            st.caption("🔒 **Password Requirements:** Minimum 8 characters, containing uppercase (A-Z), lowercase (a-z), a number (0-9), and a symbol/sign (e.g. `!@#$%^&*`).")
            with st.form("signup_form"):
                signup_name = st.text_input("Full Name", placeholder="e.g. Satyam Kumar")
                signup_email = st.text_input("Email Address", placeholder="name@example.com")
                signup_pass = st.text_input(
                    "Password",
                    type="password",
                    placeholder="e.g. Travel@2026",
                    help="Must have min 8 chars, uppercase, lowercase, digit, and symbol."
                )
                signup_pass_confirm = st.text_input("Confirm Password", type="password", placeholder="Re-enter your password")
                signup_submitted = st.form_submit_button("✨ Create Account & Get Started", type="primary", width="stretch")

            if signup_submitted:
                if not signup_email or not signup_pass:
                    st.error("Please provide both email and password.")
                elif signup_pass != signup_pass_confirm:
                    st.error("Passwords do not match. Please re-enter.")
                else:
                    is_valid_pwd, pwd_err = validate_password_complexity(signup_pass)
                    if not is_valid_pwd:
                        st.error(f"⚠️ {pwd_err}")
                    else:
                        reg_res = register_user(signup_email, signup_pass, signup_name)
                        if reg_res.get("success"):
                            user = reg_res.get("user")
                            token = create_session_token(user["id"], user["email"], user.get("full_name", ""))
                            st.session_state.user = user
                            st.session_state.session_token = token
                            st.query_params["session"] = token

                            # Sync token into browser localStorage
                            run_js_bridge(f"""
                            try {{
                                window.parent.localStorage.setItem('travel_planner_session_token', '{token}');
                            }} catch (e) {{}}
                            """)

                            st.success("Account registered successfully! Redirecting...")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error(reg_res.get("error", "Registration failed."))

    # Stop rendering the rest of the application until authorized
    st.stop()


# ==============================================================================
# 🔓 AUTHORIZED APPLICATION VIEW
# ==============================================================================
current_user = st.session_state.user
user_id = current_user.get("id")
user_name = current_user.get("full_name") or current_user.get("email", "Traveler").split("@")[0]
user_email = current_user.get("email", "")

# Initialize user-isolated thread ID if not set
if not st.session_state.active_thread_id or not st.session_state.active_thread_id.startswith(f"user_{user_id}_"):
    st.session_state.active_thread_id = format_user_thread_id(user_id, f"trip_{uuid.uuid4().hex[:6]}")

# Ensure session token is preserved in browser local storage
if st.session_state.session_token:
    run_js_bridge(f"""
    try {{
        window.parent.localStorage.setItem('travel_planner_session_token', '{st.session_state.session_token}');
    }} catch (e) {{}}
    """)


# --- Sidebar ---
with st.sidebar:
    # User Profile & 30-Day Session Widget
    initials = "".join([p[0].upper() for p in user_name.split() if p])[:2] or "TR"
    st.markdown(f"""
    <div class='user-profile-card'>
        <div class='avatar-circle'>{initials}</div>
        <div style='flex: 1; min-width: 0;'>
            <div style='font-size: 0.95rem; font-weight: 700; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'>{user_name}</div>
            <div style='font-size: 0.78rem; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'>{user_email}</div>
            <div class='active-pill'><span class='pulse-dot'></span> 30-Day Session</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("🚪 Sign Out", width="stretch"):
        st.session_state.user = None
        st.session_state.session_token = None
        st.session_state.current_state = None
        st.query_params.clear()
        run_js_bridge("""
        try {
            window.parent.localStorage.removeItem('travel_planner_session_token');
            window.parent.location.search = '';
        } catch (e) {}
        """)
        st.rerun()

    st.markdown("---")
    st.markdown("## 🧭 Travel Planner Control")
    st.caption("Autonomous 5-Agent Pipeline with LangGraph & PostgreSQL")

    # Live Forex Card
    try:
        live_rate = get_live_exchange_rate("USD", "INR")
    except Exception:
        live_rate = 86.5

    st.markdown(f"""
    <div class='forex-card'>
        <div style='display: flex; justify-content: space-between; align-items: center;'>
            <span style='font-size: 0.78rem; color: var(--text-muted); font-weight: 600;'>💱 LIVE FOREX</span>
            <span style='font-size: 0.72rem; color: var(--accent-emerald); font-weight: 600;'>ECB Rate</span>
        </div>
        <div style='font-size: 1.25rem; font-weight: 700; color: var(--accent-cyan); margin-top: 0.2rem;'>
            $1 USD = <span style='color: var(--text-primary);'>₹{live_rate:.2f} INR</span>
        </div>
        <div style='font-size: 0.72rem; color: var(--text-muted); margin-top: 0.15rem;'>Live conversion for flight & hotel benchmarks</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    # Session Management with User Isolation
    st.subheader("💾 Saved Trips & History")
    user_saved_threads = get_user_saved_sessions(user_id)

    if user_saved_threads:
        # Format friendly names for dropdown by stripping user prefix
        display_options = ["-- Select a past trip --"]
        thread_map = {}
        for t in user_saved_threads:
            friendly_name = t.replace(f"user_{user_id}_", "")
            display_options.append(friendly_name)
            thread_map[friendly_name] = t

        selected_display = st.selectbox(
            "📂 Load Past Trip from Database:",
            options=display_options,
            index=0
        )
        if selected_display != "-- Select a past trip --":
            actual_thread_id = thread_map[selected_display]
            if st.button("📥 Load Trip", width="stretch"):
                try:
                    snapshot = app.get_state({"configurable": {"thread_id": actual_thread_id}})
                    if snapshot and snapshot.values:
                        st.session_state.current_state = snapshot.values
                        st.session_state.active_thread_id = actual_thread_id
                        st.success(f"Loaded `{selected_display}` successfully!")
                        st.rerun()
                except Exception as e:
                    st.error(f"Error loading state: {e}")
    else:
        st.caption("No past saved trips found for your account yet.")

    thread_input = st.text_input(
        "Active Session ID:",
        value=st.session_state.active_thread_id,
        help="Trip data is isolated to your account and checkpointed in PostgreSQL."
    )
    if thread_input != st.session_state.active_thread_id:
        st.session_state.active_thread_id = thread_input

    st.markdown("---")

    # Quick Example Prompts
    st.subheader("💡 Example Queries")
    example_prompts = [
        "Plan a 3 day trip to Goa on a mid budget",
        "Plan a 7 day trip from Delhi to Tokyo and Kyoto in July on a mid budget, interested in temples and vegetarian food",
        "Plan a 5 day trip to Paris and Rome in September on a balanced budget"
    ]
    
    for ex in example_prompts:
        label = ex.split(" in ")[0][:35] + "..."
        if st.button(label, key=f"ex_{hash(ex)}", width="stretch"):
            st.session_state.default_prompt = ex
            st.rerun()

    st.markdown("---")
    st.markdown("### 🤖 Active Agents")
    st.markdown("""
    - `1. 🌤️ Weather Agent` 
    - `2. ✈️ Flight Agent` 
    - `3. 🏨 Hotel Agent` 
    - `4. 🏛️ Places Agent` 
    - `5. 🗺️ Master Itinerary` 
    """)


# --- Main Application Header ---
st.markdown(f"""
<div style='display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.8rem; margin-bottom: 0.3rem;'>
    <div class='brand-header-title'>
        {BRAND_ICON_SVG}
        <span class='brand-text'>AI Travel Planner</span>
    </div>
    <div class='live-badge'>⚡ 5 Autonomous Agents Active</div>
</div>
""", unsafe_allow_html=True)
st.markdown(
    f"""
    <div class='sub-header'>
        <div style='color: var(--text-secondary); font-size: 0.95rem; margin-bottom: 0.3rem;'>
            Welcome back, <b style='color: var(--accent-cyan);'>{user_name}</b>!
        </div>
        <div class='animated-tagline-container'>
            <span class='typewriter-text'>Plan your dream trip with personalized itineraries.</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

# Quick Trip Inspiration Pills
st.markdown("<div style='font-size: 0.82rem; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.45rem;'>💡 Quick Trip Inspirations:</div>", unsafe_allow_html=True)
pill_c1, pill_c2, pill_c3, pill_c4 = st.columns(4)
with pill_c1:
    if st.button("🏖️ Goa Hostels (Budget)", key="pill_goa", width="stretch"):
        st.session_state.default_prompt = "Plan a 3 day trip to Goa on a low budget under 800 per day looking for hostels like zostel"
        st.rerun()
with pill_c2:
    if st.button("⛩️ Tokyo & Kyoto (7D)", key="pill_tokyo", width="stretch"):
        st.session_state.default_prompt = "Plan a 7 day trip from Delhi to Tokyo and Kyoto in July on a mid budget, interested in temples and vegetarian food"
        st.rerun()
with pill_c3:
    if st.button("🥐 Paris & Rome (5D)", key="pill_europe", width="stretch"):
        st.session_state.default_prompt = "Plan a 5 day romantic trip to Paris and Rome in September on a balanced budget"
        st.rerun()
with pill_c4:
    if st.button("🏔️ Manali Backpacker (4D)", key="pill_manali", width="stretch"):
        st.session_state.default_prompt = "Plan a 4 day backpacker trip to Manali and Old Manali staying in budget hostels under 700 per day"
        st.rerun()

# User Query Input
default_text = st.session_state.get(
    "default_prompt",
    "Plan a trip of 3 days to Goa on a mid budget"
)

with st.form("travel_form"):
    user_query = st.text_area(
        "Enter your travel plan or question:",
        value=default_text,
        height=105,
        placeholder="e.g. Plan a 10 day family trip to Italy (Rome, Florence, Venice) in October on a balanced budget with vegetarian meals..."
    )
    
    col_submit, col_info = st.columns([1.2, 4.8])
    with col_submit:
        submitted = st.form_submit_button("🚀 Plan My Trip", type="primary", width="stretch")
    with col_info:
        st.caption("✨ *Once generated, you will be able to download your complete itinerary blueprint as a styled PDF.*")

# --- Execution Workflow ---
if submitted and user_query:
    # Ensure thread_id has user isolation prefix
    clean_thread = thread_input or f"trip_{uuid.uuid4().hex[:6]}"
    st.session_state.active_thread_id = format_user_thread_id(user_id, clean_thread)
    st.session_state.current_state = None

    st.markdown("### ⚡ Live Multi-Agent Execution Progress")
    
    status_container = st.status("🚀 Launching Autonomous Travel Agents...", expanded=True)
    
    agent_progress_state = {
        "weather_agent": False,
        "flight_agent": False,
        "hotel_agent": False,
        "places_agent": False,
        "itinerary_agent": False
    }

    try:
        final_accumulated_state = {}
        for event in stream_travel_planner(user_query=user_query, thread_id=st.session_state.active_thread_id):
            for node_name, node_output in event.items():
                final_accumulated_state.update(node_output)
                
                if node_name == "weather_agent":
                    agent_progress_state["weather_agent"] = True
                    status_container.write("🌤️ **Weather Agent Complete**: Historical climate profile analyzed & optimal dates identified.")
                elif node_name == "flight_agent":
                    agent_progress_state["flight_agent"] = True
                    status_container.write("✈️ **Flight Agent Complete**: Live Google Flights scraped and route pricing benchmarked.")
                elif node_name == "hotel_agent":
                    agent_progress_state["hotel_agent"] = True
                    status_container.write("🏨 **Hotel Agent Complete**: Accommodations discovered with verified Google & Booking links.")
                elif node_name == "places_agent":
                    agent_progress_state["places_agent"] = True
                    status_container.write("🏛️ **Attractions & Dining Agent Complete**: Sights clustered & authentic web photos retrieved.")
                elif node_name == "itinerary_agent":
                    agent_progress_state["itinerary_agent"] = True
                    status_container.write("🗺️ **Master Itinerary Agent Complete**: Day-by-day master plan, photos & financial ledger generated.")

        status_container.update(
            label="🎉 All 5 Agents Successfully Completed & Saved to PostgreSQL!",
            state="complete",
            expanded=False
        )

        st.session_state.current_state = final_accumulated_state
        st.success("Travel plan successfully generated and stored in database!")
        st.rerun()

    except Exception as e:
        status_container.update(label="❌ Error executing agent pipeline", state="error")
        st.error(f"Execution Error: {str(e)}")


# --- Results Dashboard ---
state = st.session_state.current_state

if state:
    # Summary Metrics Row
    dest = state.get("destination", "Destination")
    days = state.get("duration_days", 7)
    travel_date = state.get("travel_date", "Flexible")
    total_calls = state.get("llm_calls", 0)

    st.markdown("---")
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(f"<div class='metric-card metric-card-dest'><div class='metric-val'>📍 {dest}</div><div class='metric-lbl'>Destination</div></div>", unsafe_allow_html=True)
    with m2:
        st.markdown(f"<div class='metric-card metric-card-duration'><div class='metric-val'>⏱️ {days} Days</div><div class='metric-lbl'>Trip Duration</div></div>", unsafe_allow_html=True)
    with m3:
        st.markdown(f"<div class='metric-card metric-card-dates'><div class='metric-val'>📅 {travel_date}</div><div class='metric-lbl'>Optimal Travel Window</div></div>", unsafe_allow_html=True)
    with m4:
        st.markdown(f"<div class='metric-card metric-card-calls'><div class='metric-val'>🧠 {total_calls} Calls</div><div class='metric-lbl'>LLM Invocations</div></div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Quick PDF Export & Dashboard Actions
    row_title, row_btn = st.columns([2.8, 1.2])
    with row_title:
        st.markdown(f"#### 🧭 Complete Travel Blueprint & Agent Research")
    with row_btn:
        try:
            pdf_bytes = generate_itinerary_pdf(state, traveler_name=user_name)
            clean_dest = str(dest).replace(" ", "_").replace(",", "")
            st.download_button(
                label="📄 Download Itinerary (PDF)",
                data=pdf_bytes,
                file_name=f"Trip_{clean_dest}_Itinerary.pdf",
                mime="application/pdf",
                type="primary",
                width="stretch",
                key="btn_download_pdf_top"
            )
        except Exception as e:
            st.warning(f"Could not generate top PDF export: {e}")

    # Output Tabs for Every Agent
    tab_itinerary, tab_weather, tab_flights, tab_hotels, tab_places, tab_debug = st.tabs([
        "🗺️ Master Itinerary",
        "🌤️ Climate & Weather",
        "✈️ Flights",
        "🏨 Hotels & Stays",
        "🏛️ Attractions & Dining",
        "🔍 Agent State & Logs"
    ])

    with tab_itinerary:
        itin_head, itin_dl = st.columns([2.8, 1.2])
        with itin_head:
            st.markdown("### 🗺️ Master Day-by-Day Itinerary & Budget Ledger")
        with itin_dl:
            try:
                pdf_bytes = generate_itinerary_pdf(state, traveler_name=user_name)
                clean_dest = str(dest).replace(" ", "_").replace(",", "")
                st.download_button(
                    label="📥 Export PDF Itinerary",
                    data=pdf_bytes,
                    file_name=f"Trip_{clean_dest}_Itinerary.pdf",
                    mime="application/pdf",
                    width="stretch",
                    key="btn_download_pdf_tab"
                )
            except Exception as e:
                st.warning(f"Could not generate tab PDF export: {e}")
        
        # Interactive Visual Photo Gallery
        place_images = state.get("place_images", [])
        if place_images:
            st.markdown("#### 📸 Destination Visual Highlights")
            num_cols = min(len(place_images), 3)
            cols = st.columns(num_cols)
            for i, img in enumerate(place_images[:6]):
                with cols[i % num_cols]:
                    st.image(img["url"], caption=f"📍 {img['name']} ({img.get('city', '')})", width="stretch")
            st.markdown("---")

        itinerary_text = state.get("itinerary", "")
        if itinerary_text:
            st.markdown(itinerary_text)
        else:
            st.info("Itinerary has not been generated yet.")

    with tab_weather:
        st.markdown("### 🌤️ Weather & Climate Intelligence (Node 1)")
        st.caption("Historical ERA5 analysis & optimal window selection via Open-Meteo")
        weather_text = state.get("weather_results", "")
        if weather_text:
            st.markdown(weather_text)
        else:
            st.info("Weather results not available.")

    with tab_flights:
        st.markdown("### ✈️ Flight Discovery & Pricing Benchmarks (Node 2)")
        st.caption("Live Google Flights discovery via `fast-flights` / SerpApi")
        flight_text = state.get("flight_results", "")
        if flight_text:
            st.markdown(flight_text)
        else:
            st.info("Flight results not available.")

    with tab_hotels:
        st.markdown("### 🏨 Hotel & Lodging Discovery (Node 3)")
        st.caption("Tavily live search with verified deep booking links & ECB live currency conversion")
        hotel_text = state.get("hotel_results", "")
        if hotel_text:
            st.markdown(hotel_text)
        else:
            st.info("Hotel results not available.")

    with tab_places:
        st.markdown("### 🏛️ Attractions, Sights & Dining Guide (Node 4)")
        st.caption("Curated sights by neighborhood with authentic photos, local foods and Indian/vegetarian recommendations")
        
        place_images = state.get("place_images", [])
        if place_images:
            st.markdown("#### 📸 Featured Sightseeing Gallery")
            num_cols = min(len(place_images), 3)
            p_cols = st.columns(num_cols)
            for i, img in enumerate(place_images[:6]):
                with p_cols[i % num_cols]:
                    st.image(img["url"], caption=f"📍 {img['name']} ({img.get('city', '')})", width="stretch")
            st.markdown("---")

        places_text = state.get("places_results", "")
        if places_text:
            st.markdown(places_text)
        else:
            st.info("Attractions & dining results not available.")

    with tab_debug:
        st.markdown("### 🔍 Raw State & PostgreSQL Checkpoint Data")
        st.caption("Complete TravelState snapshot currently saved in the database")
        
        # Display state without the full message history clutter
        display_dict = {k: v for k, v in state.items() if k != "message"}
        st.json(display_dict)
        
        if "message" in state:
            with st.expander(f"💬 Conversation Messages ({len(state['message'])})"):
                for idx, msg in enumerate(state["message"], 1):
                    msg_type = getattr(msg, "type", "message")
                    st.markdown(f"**[{idx}] {msg_type.upper()}:**")
                    st.text(getattr(msg, "content", str(msg)))

else:
    # Empty State Guidance with Modern Walkthrough Feature Cards
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<div style='font-size: 0.95rem; font-weight: 600; color: var(--text-secondary); margin-bottom: 0.8rem;'>✨ HOW IT WORKS — AUTONOMOUS 5-AGENT SYSTEM</div>", unsafe_allow_html=True)
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        st.markdown("""
        <div class='feature-card'>
            <div style='font-size: 1.8rem; margin-bottom: 0.5rem;'>🌤️ ✈️</div>
            <div style='font-weight: 700; font-size: 1.05rem; color: var(--accent-cyan); margin-bottom: 0.35rem;'>1. Climate & Live Flights</div>
            <div style='font-size: 0.86rem; color: var(--text-secondary); line-height: 1.55;'>
                Leverages historical ERA5 archives via Open-Meteo to pick the optimal weather window, then searches Google Flights for real-time fares and airline route benchmarks.
            </div>
        </div>
        """, unsafe_allow_html=True)
    with fc2:
        st.markdown("""
        <div class='feature-card'>
            <div style='font-size: 1.8rem; margin-bottom: 0.5rem;'>🏨 💰</div>
            <div style='font-weight: 700; font-size: 1.05rem; color: var(--accent-emerald); margin-bottom: 0.35rem;'>2. Smart Budget Stays & Forex</div>
            <div style='font-size: 0.86rem; color: var(--text-secondary); line-height: 1.55;'>
                Automatically detects budget tier — dorms/hostels (Zostel, Hosteller) under ₹800/night for backpackers, or boutique resorts, complete with verified booking links & live ECB currency conversion.
            </div>
        </div>
        """, unsafe_allow_html=True)
    with fc3:
        st.markdown("""
        <div class='feature-card'>
            <div style='font-size: 1.8rem; margin-bottom: 0.5rem;'>🏛️ 🗺️</div>
            <div style='font-weight: 700; font-size: 1.05rem; color: var(--accent-amber); margin-bottom: 0.35rem;'>3. Visual Sights & Master Plan</div>
            <div style='font-size: 0.86rem; color: var(--text-secondary); line-height: 1.55;'>
                Clusters attractions by district with authentic web photo galleries, authentic dining options, and synthesizes everything into a day-by-day itinerary with an itemized financial ledger.
            </div>
        </div>
        """, unsafe_allow_html=True)
