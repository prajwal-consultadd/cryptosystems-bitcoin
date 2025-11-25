# 🤖 Bitcoin ATM Lead Qualification POC

An end-to-end **AI-powered lead generation system** designed to identify high-potential business locations for installing Bitcoin ATMs.  
The system evaluates client-provided ZIP codes, discovers nearby businesses using Google Places API, applies qualification filters, and uses an AI calling agent to confirm installation interest.

This POC automates the entire **discovery → qualification → outreach** pipeline.

---

## 🧨 Problem Statement

The client wants to identify and contact businesses that may be interested in hosting a Bitcoin ATM.  
For every ZIP code provided, the system must:

- Fetch nearby businesses from categories relevant to kiosk placement:  
  `gas_station`, `convenience_store`, `supermarket`, `liquor_store`, `pharmacy`, `jewelry_store`, `laundry`, `shopping_mall`, `restaurant`
- Retrieve detailed business information using Google APIs (phone number, operating hours, address, ratings)
- Apply qualification logic:
  - Business must be open **≥12 hours/day**
  - Must belong to approved categories
  - Must have a valid phone number
- Initiate outbound calls using an **AI voice agent** to confirm whether the business is willing to host a kiosk
- Deliver only the **interested** leads to the client

---

## 🚀 Approach

1. Client uploads or provides a list of ZIP codes.
2. ZIPs are validated and filtered based on client rules.
3. For each qualified ZIP:
   - Convert ZIP → Latitude & Longitude using the Zippopotam API  
   - Fetch nearby businesses using Google Places (Nearby Search)
   - Enrich each business using Google Place Details API
4. Apply business-level filters:
   - Category match  
   - Must operate at least 12 hours/day  
   - Valid phone number retrieval  
5. Export a clean CSV containing business information and contact numbers.
6. Feed these businesses into an **AI calling agent**.
7. AI agent tags the business response as:
   - **Interested**
   - **Not Interested**
   - **Callback Requested**
   - **Invalid / Unreachable**
8. Final qualified leads (Interested only) are provided to the client.

---

## 🏗️ Technical Architecture

The system follows a modular, end-to-end pipeline that transforms raw ZIP codes into fully verified Bitcoin ATM installation leads.  
Below is the complete architecture described in structured text form.

### **1. ZIP Intake & Pre-Filtering**
The client uploads a list of ZIP codes through a Streamlit-based UI or CSV file.  
A validation layer checks for formatting issues, duplicates, and applies client-defined filters (such as excluding restricted ZIPs or regions).  
Only valid and allowed ZIPs move forward.

### **2. Geolocation Resolution**
Each ZIP code is converted into latitude and longitude coordinates using the **Zippopotam API**.  
These coordinates are required for accurate business discovery in the next stage.

### **3. Business Discovery (Google Places API)**
Using the resolved geocoordinates, the system queries the **Google Places Nearby Search API** to fetch nearby businesses within a defined search radius.  
Only businesses belonging to specific categories are considered:
- gas_station  
- convenience_store  
- supermarket  
- liquor_store  
- pharmacy  
- jewelry_store  
- laundry  
- shopping_mall  
- restaurant  

For each discovered business, the **Google Place Details API** retrieves additional details:
- Contact number  
- Operating hours  
- Business rating  
- Full address  
- Google place_id  
- Metadata such as website or photos (if available)

### **4. Lead Qualification Engine**
All discovered businesses pass through the rules-based qualification layer:
- Business must be one of the approved categories  
- Must be open for at least **12 hours per day** (based on `opening_hours`)  
- Must have a valid phone number  
- Additional optional filters may include minimum rating or brand-level exclusions  

Only businesses that meet all criteria are considered qualified.

### **5. Lead Packaging & CSV Generation**
Qualified businesses are standardized, deduplicated, and exported into a structured CSV file.  
Each row contains:
- Business Name  
- Category  
- Phone Number  
- Address  
- Latitude & Longitude  
- Rating  
- Average Daily Open Hours  
- Source ZIP  
- place_id  

This CSV becomes the input for the AI calling agent.

### **6. AI Calling & Lead Verification**
A voice AI calling agent (integrated via **Twilio or similar telephony provider**) contacts each qualified business.  
The agent follows a kiosk-installation inquiry script and assigns a call outcome:
- **Interested**  
- **Not Interested**  
- **Callback Requested**  
- **Invalid / Unreachable**  

Only the *Interested* leads step forward.

### **7. Final Lead Delivery**
All interested businesses are delivered to the client in the form of:
- A final CSV  
- Optional email delivery  
- Optional CRM API webhook (future capability)

This completes the pipeline from ZIP → business discovery → qualification → AI calling → final verified lead.



---

## 🧩 Tech Stack

| Component | Purpose |
|----------|---------|
| **Python** | Core backend logic & pipeline orchestration |
| **Streamlit** | Front-end UI for ZIP upload & job execution |
| **Zippopotam API** | ZIP → coordinates lookup |
| **Google Places API** | Business discovery + details lookup |
| **Pandas** | Data transformation + CSV generation |


---

## 📂 Input Format

---

Upload a CSV with at least:

## 🧪 Run Locally

```bash
pythone -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && streamlit run app.py