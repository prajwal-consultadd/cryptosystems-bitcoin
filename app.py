import streamlit as st
import pandas as pd
import requests
import time
from bs4 import BeautifulSoup
import re
from dotenv import load_dotenv
import os
load_dotenv()

# ----------------------------- 
# Page Config 
# ----------------------------- 
st.set_page_config(page_title="Bitcoin ATM Lead Qualification", layout="wide")
st.title("🤖 Bitcoin ATM Lead Qualification (Enhanced Version)")
st.markdown("### Upload ZIP codes and auto-filter based on population density")

# ----------------------------- 
# Sidebar Upload 
# ----------------------------- 
uploaded_file = st.sidebar.file_uploader("Upload Excel with ZIP Codes", type=["xlsx"])

# ----------------------------- 
# API Config & Thresholds
# ----------------------------- 
CENSUS_API_KEY = os.getenv("CENSUS_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
BLENDED_TRANSACTIONS_THRESHOLD = 10000
POP_DENSITY_THRESHOLD = 400
REMOVAL_RATE_THRESHOLD= 0.4
MIN_DAILY_HOURS = 12

# --------------------------------------------------
# GOOGLE PLACE TYPES TO SEARCH
# --------------------------------------------------
PLACE_TYPES = [
    "gas_station",
    "convenience_store",
    "supermarket",
    "liquor_store",
    "pharmacy",
    "jewelry_store",
    "laundry",
    "shopping_mall",
    "restaurant",
]

# ----------------------------- 
# Function to Fetch Latitude and Longitude from Zippopotam API
# ----------------------------- 
def get_lat_long(zip_code):
    """
    Fetches latitude and longitude from Zippopotam API.
    Returns tuple (latitude, longitude) or ("Unknown", "Unknown") if error.
    """
    try:
        url = f"https://api.zippopotam.us/us/{zip_code}"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if "places" in data and len(data["places"]) > 0:
            latitude = data["places"][0].get("latitude", "Unknown")
            longitude = data["places"][0].get("longitude", "Unknown")
            return latitude, longitude
        return "Unknown", "Unknown" 
    except Exception as e:
        st.write(f"⚠️ City/State fetch error for ZIP `{zip_code}`: {str(e)}")
        return "Unknown", "Unknown"

# ----------------------------- 
# Function to Fetch All Data for a ZIP Code
# ----------------------------- 
def fetch_zip_data(zip_code, row):
    latitude, longitude = get_lat_long(zip_code)

    return {
        "Latitude": latitude,
        "Longitude": longitude
    }

# --------------------------------------------------
# Fetch Bitcoin ATMs/businesses for a location (DISPLAY ONLY - NO DETAILS)
# --------------------------------------------------
def get_bitcoin_locations(lat, lng, radius=1600):
    """
    Fetches Bitcoin-related businesses using Google Places API.
    Returns DataFrame with Bitcoin business information.
    """
    url = (
        f"https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        f"?location={lat},{lng}&radius={radius}&keyword=bitcoin&key={GOOGLE_API_KEY}"
    )
    
    results = []
    res = requests.get(url).json()
    
    for r in res.get("results", []):
        results.append({
            "name": r.get("name"),
            "address": r.get("vicinity"),
            "rating": r.get("rating", "N/A"),
        })
    
    return pd.DataFrame(results)

# --------------------------------------------------
# Fetch nearby POIs for categories
# --------------------------------------------------
def get_pois(lat, lng, radius=1600):
    """
    Fetches nearby points of interest using Google Places API.
    Returns DataFrame with business information.
    """
    results = []

    for place_type in PLACE_TYPES:
        url = (
            "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
            f"?location={lat},{lng}&radius={radius}&type={place_type}&key={GOOGLE_API_KEY}"
        )

        res = requests.get(url).json()

        for r in res.get("results", []):
            results.append({
                "place_id": r.get("place_id"),
                "name": r.get("name"),
                "address": r.get("vicinity"),
                "type": place_type,
            })

    return pd.DataFrame(results)

# --------------------------------------------------
# Fetch business details (phone, website, hours)
# --------------------------------------------------
def get_place_details(place_id):
    """
    Fetches detailed information for a specific place.
    Returns dictionary with business details.
    """
    url = (
        f"https://maps.googleapis.com/maps/api/place/details/json"
        f"?place_id={place_id}&fields=name,formatted_phone_number,website,opening_hours"
        f"&key={GOOGLE_API_KEY}"
    )

    res = requests.get(url).json()
    return res.get("result", {})

# --------------------------------------------------
# Calculate daily operating hours from opening_hours
# --------------------------------------------------
def calculate_daily_hours(opening_hours):
    """
    Calculates the average daily operating hours from Google Places opening_hours data.
    Returns average hours per day or 0 if data unavailable.
    """
    try:
        if not opening_hours or "periods" not in opening_hours:
            return 0
        
        periods = opening_hours.get("periods", [])
        if not periods:
            return 0
        
        # If open 24/7
        if len(periods) == 1 and "close" not in periods[0]:
            return 24
        
        daily_hours = []
        
        for period in periods:
            if "open" in period and "close" in period:
                open_time = period["open"].get("time", "0000")
                close_time = period["close"].get("time", "0000")
                
                # Convert time strings to hours
                open_hour = int(open_time[:2]) + int(open_time[2:]) / 60
                close_hour = int(close_time[:2]) + int(close_time[2:]) / 60
                
                # Handle cases where close time is next day (e.g., open until 2 AM)
                if close_hour < open_hour:
                    close_hour += 24
                
                hours = close_hour - open_hour
                daily_hours.append(hours)
        
        # Return average daily hours
        return round(sum(daily_hours) / len(daily_hours), 2) if daily_hours else 0
    
    except Exception as e:
        return 0

# --------------------------------------------------
# Scrape website for owner emails / phones
# --------------------------------------------------
def scrape_owner_info(website):
    """
    Scrapes website for contact information and owner details.
    Returns dictionary with emails, phones, and owner information.
    """
    try:
        html = requests.get(website, timeout=5).text
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)

        emails = list(set(re.findall(r'\S+@\S+\.\S+', text)))
        phones = list(set(re.findall(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', text)))

        owner_kw = ["owner", "manager", "founder", "ceo"]
        owner_lines = [line for line in text.split(".") if any(k in line.lower() for k in owner_kw)]

        return {
            "emails": emails,
            "phones": phones,
            "owner_lines": owner_lines[:5]
        }

    except Exception:
        return {"emails": [], "phones": [], "owner_lines": []}

# ----------------------------- 
# Main Logic 
# ----------------------------- 
if uploaded_file:
    df = pd.read_excel(uploaded_file)
    
    st.markdown("### 📋 Uploaded ZIP Code Preview")
    st.dataframe(df, width='stretch')
    
    # Validate ZIP code column exists
    if "zip_code" not in df.columns:
        st.error("❌ Excel must contain a 'zip_code' column.")
        st.stop()
    
    df_processed = df.copy()
    df_processed["zip_code"] = df_processed["zip_code"].astype(str).str.zfill(5)

    
    # Fetch data for each ZIP code
    st.info("📡 Fetching population, area, city, and state for each ZIP code...")
    
    progress_bar = st.progress(0)
    total_zips = len(df_processed)
    
    results = []
    for idx, row in df_processed.iterrows():
        zip_code = row["zip_code"]
        zip_data = fetch_zip_data(zip_code, row)
        results.append(zip_data)
        progress_bar.progress((idx + 1) / total_zips)
        time.sleep(0.2)

    
    progress_bar.empty()
    
    # Add fetched data to dataframe
    results_df = pd.DataFrame(results)
    df_processed = pd.concat([df_processed, results_df], axis=1)
    
    # Qualification Rules: 
    # 1. Blended Transactions (Population from ACS) >= BLENDED_TRANSACTIONS_THRESHOLD
    # 2. Population Density >= POP_DENSITY_THRESHOLD
    
    df_processed["Qualified"] = (
        (df_processed["Blended Pop Estimate"] >= BLENDED_TRANSACTIONS_THRESHOLD) &
        (df_processed["Pop Density"] >= POP_DENSITY_THRESHOLD) &
        (df_processed["Removal Rate"] <= REMOVAL_RATE_THRESHOLD)
    )
    
    # Detailed rejection reasons
    def get_rejection_reason(row):
        if row["Qualified"]:
            return ""
        reasons = []
        if row["Blended Pop Estimate"] < BLENDED_TRANSACTIONS_THRESHOLD:
            reasons.append("Low blended transactions")
        if row["Pop Density"] < POP_DENSITY_THRESHOLD:
            reasons.append("Low population density")
        if row["Removal Rate"] >= 0.4:
            reasons.append("High kiosk removal rate")
        return " | ".join(reasons)
    
    df_processed["RejectedReason"] = df_processed.apply(get_rejection_reason, axis=1)
    
    qualified = df_processed[df_processed["Qualified"] == True]
    rejected = df_processed[df_processed["Qualified"] == False]
    
    # ----------------------------- 
    # Tabs for Results 
    # ----------------------------- 
    tab1, tab2 = st.tabs(["✅ Qualified Leads", "❌ Rejected Leads"])
    
    with tab1:
        st.success(f"Qualified Leads: {len(qualified)}")
        st.dataframe(qualified, width='stretch')
        
        # Download button
        csv = qualified.to_csv(index=False)
        st.download_button(
            label="📥 Download Qualified Leads",
            data=csv,
            file_name="qualified_leads.csv",
            mime="text/csv"
        )
    
    with tab2:
        st.warning(f"Rejected Leads: {len(rejected)}")
        st.dataframe(rejected, width='stretch')
        
        # Download button
        csv = rejected.to_csv(index=False)
        st.download_button(
            label="📥 Download Rejected Leads",
            data=csv,
            file_name="rejected_leads.csv",
            mime="text/csv"
        )
    
    # ----------------------------- 
    # Summary Metrics 
    # ----------------------------- 
    st.markdown("---")
    st.subheader("📊 Summary Metrics")
    
    total = len(df_processed)
    approved = len(qualified)
    rejection_rate = round((total - approved) / total * 100, 2) if total > 0 else 0
    avg_population = int(df_processed["Blended Pop Estimate"].mean()) if total > 0 else 0
    avg_density = round(df_processed["Pop Density"].mean(), 2) if total > 0 else 0
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total ZIP Codes", total)
    col2.metric("Qualified", approved)
    col3.metric("Rejection Rate", f"{rejection_rate}%")
    col4.metric("Avg Blended Trans (Pop)", avg_population)
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Avg Pop Density", f"{avg_density} /sq mi")
    col2.metric("Total States", df_processed["State"].nunique())
    col3.metric("Total Cities", df_processed["City"].nunique())
    
    # --------------------------------------------------
    # PROCESS QUALIFIED ZIP CODES FOR BUSINESSES
    # --------------------------------------------------
    if len(qualified) > 0 and GOOGLE_API_KEY and GOOGLE_API_KEY != "":
        st.markdown("---")
        st.subheader("🔍 Fetch Businesses + Owner Details for Qualified ZIPs")
        
        if st.button("🚀 Start Business Search", type="primary"):
            all_results = []
            
            business_progress = st.progress(0)
            total_qualified = len(qualified)
            
            for idx, (_, row) in enumerate(qualified.iterrows()):
                zip_code = row["zip_code"]
                lat = row["Latitude"]
                lng = row["Longitude"]
                
                st.write(f"### Processing ZIP: `{zip_code}` ({idx+1}/{total_qualified})")
                
                # Check if we have valid coordinates
                if lat == "Unknown" or lng == "Unknown":
                    st.warning(f"⚠️ Skipping {zip_code} - No valid coordinates")
                    business_progress.progress((idx + 1) / total_qualified)
                    continue
                
                try:
                    lat = float(lat)
                    lng = float(lng)
                except:
                    st.warning(f"⚠️ Skipping {zip_code} - Invalid coordinates")
                    business_progress.progress((idx + 1) / total_qualified)
                    continue
                
                # Fetch Bitcoin ATM locations (DISPLAY ONLY - NO DETAIL FETCHING)
                bitcoin_df = get_bitcoin_locations(lat, lng)
                if len(bitcoin_df) > 0:
                    st.write(f"📍 **Bitcoin Locations Found: {len(bitcoin_df)}** (info only)")
                    st.dataframe(bitcoin_df, width='stretch')
                
                # Fetch nearby businesses (regular categories)
                poi_df = get_pois(lat, lng)
                st.write(f"Found {len(poi_df)} regular businesses")
                
                # Process regular businesses ONLY (exclude Bitcoin ATMs from detail fetching)
                if len(poi_df) > 0:
                    st.dataframe(poi_df, width='stretch')
                    
                    # Fetch details for each business
                    for _, poi in poi_df.iterrows():
                        try:
                            details = get_place_details(poi["place_id"])
                            website = details.get("website")
                            opening_hours = details.get("opening_hours")
                            
                            # Calculate daily operating hours
                            daily_hours = calculate_daily_hours(opening_hours)
                            
                            # Skip businesses that don't meet minimum hours requirement
                            if daily_hours < MIN_DAILY_HOURS:
                                # st.write(f"⏰ Skipping {poi['name']} - Only open {daily_hours} hours/day (minimum {MIN_DAILY_HOURS} required)")
                                continue
                            
                            # Scrape owner info if website exists
                            owner_data = scrape_owner_info(website) if website else {"emails": [], "phones": [], "owner_lines": []}
                            
                            all_results.append({
                                "ZIP": zip_code,
                                "City": row["City"],
                                "State": row["State"],
                                "Business Name": poi["name"],
                                "Address": poi["address"],
                                "Category": poi["type"],
                                "Daily Hours": daily_hours,
                                "Phone": details.get("formatted_phone_number"),
                                "Website": website,
                                "Owner Emails": ", ".join(owner_data["emails"]) if owner_data["emails"] else "",
                                "Owner Phones (Scraped)": ", ".join(owner_data["phones"]) if owner_data["phones"] else "",
                                "Owner Info Lines": " | ".join(owner_data["owner_lines"]) if owner_data["owner_lines"] else ""
                            })
                            
                            # Small delay to avoid rate limiting
                            time.sleep(0.3)
                        except Exception as e:
                            st.write(f"⚠️ Error fetching details for {poi['name']}: {str(e)}")
                
                business_progress.progress((idx + 1) / total_qualified)
                time.sleep(0.5)  # Delay between ZIPs
            
            business_progress.empty()
            
            # Display final results (EXCLUDING BITCOIN ATMs)
            if len(all_results) > 0:
                final_df = pd.DataFrame(all_results)
                
                st.markdown("## 🎯 Final Results (Regular Businesses Only - Bitcoin ATMs Excluded)")
                st.success(f"Found {len(final_df)} total businesses across {len(qualified)} qualified ZIP codes")
                
                # Show breakdown by category
                st.write("**Breakdown by Category:**")
                category_counts = final_df["Category"].value_counts()
                st.dataframe(category_counts, width='stretch')
                
                # Split results based on contact availability
                # Has contact if either Phone or Owner Phones (Scraped) is not empty
                has_contact = final_df[
                    (final_df["Phone"].notna() & (final_df["Phone"] != "")) | 
                    (final_df["Owner Phones (Scraped)"].notna() & (final_df["Owner Phones (Scraped)"] != ""))
                ]
                
                no_contact = final_df[
                    (final_df["Phone"].isna() | (final_df["Phone"] == "")) & 
                    (final_df["Owner Phones (Scraped)"].isna() | (final_df["Owner Phones (Scraped)"] == ""))
                ]
                
                # Create tabs for contact/no-contact results
                contact_tab1, contact_tab2 = st.tabs([
                    f"📞 With Contact Info ({len(has_contact)})", 
                    f"❌ Without Contact Info ({len(no_contact)})"
                ])
                
                with contact_tab1:
                    st.success(f"Businesses with contact information: {len(has_contact)}")
                    st.dataframe(has_contact, width='stretch')
                    
                    if len(has_contact) > 0:
                        st.download_button(
                            label="📥 Download Businesses WITH Contact Info",
                            data=has_contact.to_csv(index=False),
                            file_name="businesses_with_contact.csv",
                            mime="text/csv",
                        )
                
                with contact_tab2:
                    st.warning(f"Businesses without contact information: {len(no_contact)}")
                    st.dataframe(no_contact, width='stretch')
                    
                    if len(no_contact) > 0:
                        st.download_button(
                            label="📥 Download Businesses WITHOUT Contact Info",
                            data=no_contact.to_csv(index=False),
                            file_name="businesses_without_contact.csv",
                            mime="text/csv",
                        )
            else:
                st.warning("No businesses found in qualified ZIP codes")

else:
    st.info("⬆️ Please upload an Excel file with a 'zip_code' column to continue.")
    st.markdown("""
    ### 📝 Instructions:
    1. Upload an Excel file (.xlsx) with a column named **`zip_code`**
    2. The system will fetch:
       - **Population** (Census ACS API) - Used as Blended Transactions
       - **Land Area** in sq mi (Census GeoInfo API)
       - **Population Density** (calculated as Population / Area)
       - **City and State** (Zippopotam API)
    3. **Qualification Criteria:**
       - Blended Transactions (Population) ≥ 10,000
       - Population Density ≥ 400 people/sq mi
    4. Download qualified, rejected, or all data as CSV
    5. **New Feature:** View Bitcoin ATM locations in qualified ZIPs (informational only)
    6. **Business Search:** Fetch detailed contact info for non-Bitcoin businesses in qualified ZIPs
    """)