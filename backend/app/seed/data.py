"""Starting data. Safe to edit; the seed script only adds what is missing."""

CATEGORIES = [
    # (id, slug, name, is_perishable)
    (1, "food", "Food", True),
    (2, "grocery_ration", "Grocery / ration", False),
    (3, "clothes", "Clothes", False),
    (4, "blankets", "Blankets", False),
    (5, "winter_support", "Winter support", False),
    (6, "hygiene", "Hygiene items", False),
    (7, "baby", "Baby items", False),
    (8, "household", "Household items", False),
    (9, "school_supplies", "School supplies", False),
    (10, "books", "Books", False),
    (11, "mobility_aids", "Wheelchairs / mobility aids", False),
    (12, "emergency_relief", "Emergency relief", False),
]

SOURCES = [
    # (id, kind, name, every_minutes)
    (1, "gdacs", "GDACS disaster alerts", 30),
    (2, "reliefweb", "ReliefWeb (Pakistan)", 360),
    (3, "hdx_hapi", "HDX HAPI (IPC, food prices, poverty)", 43200),
    (4, "pbs_spi", "PBS weekly prices (SPI)", 10080),
    (5, "pmd", "PMD weather advisories", 360),
    (6, "web_search", "Claude web search", None),
    (7, "upload", "Manual upload", None),
    (8, "ai_needs", "AI web scan for current needs", None),
]

# Province -> cities. Rural districts from IPC/HDX (e.g. Tharparkar, Kech) are added in Phase 6
# as level "region" directly under their province, matched by HDX admin2 code.
PROVINCES = {
    "Sindh": ["Karachi", "Hyderabad", "Sukkur", "Larkana", "Mirpur Khas"],
    "Punjab": ["Lahore", "Faisalabad", "Rawalpindi", "Multan", "Gujranwala"],
    "Khyber Pakhtunkhwa": ["Peshawar", "Mardan", "Mingora", "Abbottabad", "Dera Ismail Khan"],
    "Balochistan": ["Quetta", "Gwadar", "Turbat", "Khuzdar"],
    "Islamabad Capital Territory": ["Islamabad"],
    "Gilgit-Baltistan": ["Gilgit"],
    "Azad Jammu and Kashmir": ["Muzaffarabad"],
}

# City -> region (district) -> areas. Karachi filled in as the pilot city; add others the same way.
CITY_REGIONS = {
    "Karachi": {
        "Karachi South": ["Lyari", "Saddar", "Clifton"],
        "Karachi East": ["Gulshan-e-Iqbal", "PECHS", "Jamshed Town"],
        "Karachi West": ["Orangi Town", "Baldia Town"],
        "Karachi Central": ["North Nazimabad", "Gulberg"],
        "Korangi": ["Korangi", "Landhi"],
        "Malir": ["Malir", "Shah Faisal Colony"],
        "Keamari": ["Keamari", "Mauripur"],
    },
}

# name, category slugs, start_month, end_month, hijri_month, days_before_event, weight
SEASONAL_RULES = [
    ("Winter", ["blankets", "winter_support", "clothes"], 12, 2, None, None, 3.0),
    ("Monsoon and floods", ["emergency_relief", "hygiene", "grocery_ration", "blankets"], 7, 9, None, None, 3.0),
    ("Summer heat", ["hygiene", "food"], 5, 6, None, None, 1.5),
    ("Ramadan", ["grocery_ration", "food"], None, None, 9, None, 3.0),
    ("Eid al-Fitr", ["clothes", "baby"], None, None, 10, 14, 2.0),
    ("Eid al-Adha", ["clothes", "baby"], None, None, 12, 14, 2.0),
    ("School year start (spring)", ["school_supplies", "books"], 4, 4, None, None, 2.0),
    ("School year start (August)", ["school_supplies", "books"], 8, 8, None, None, 2.0),
]

# Approximate centre points (lat, lng), used for maps, alerts from GDACS and relief camps.
PLACE_COORDS = {
    "Sindh": (25.9, 68.5), "Punjab": (31.2, 72.7), "Khyber Pakhtunkhwa": (34.6, 72.1), "Balochistan": (28.5, 65.5),
    "Islamabad Capital Territory": (33.69, 73.05), "Gilgit-Baltistan": (35.8, 74.98), "Azad Jammu and Kashmir": (33.9, 73.8),
    "Karachi": (24.8607, 67.0011), "Hyderabad": (25.396, 68.3578), "Sukkur": (27.7052, 68.8574), "Larkana": (27.559, 68.2264),
    "Mirpur Khas": (25.5276, 69.0111), "Lahore": (31.5204, 74.3587), "Faisalabad": (31.4504, 73.135),
    "Rawalpindi": (33.5651, 73.0169), "Multan": (30.1575, 71.5249), "Gujranwala": (32.1877, 74.1945),
    "Peshawar": (34.0151, 71.5249), "Mardan": (34.198, 72.0404), "Mingora": (34.7717, 72.36), "Abbottabad": (34.1688, 73.2215),
    "Dera Ismail Khan": (31.8313, 70.9017), "Quetta": (30.1798, 66.975), "Gwadar": (25.1264, 62.3225), "Turbat": (26.0023, 63.044),
    "Khuzdar": (27.8, 66.6167), "Islamabad": (33.6844, 73.0479), "Gilgit": (35.9208, 74.3144), "Muzaffarabad": (34.37, 73.4711),
    "Karachi South": (24.85, 67.02), "Karachi East": (24.92, 67.08), "Karachi West": (24.94, 66.98), "Karachi Central": (24.93, 67.04),
    "Korangi": (24.83, 67.13), "Malir": (24.9, 67.2), "Keamari": (24.85, 66.95),
}

# Other spellings found in reports and news, so places are recognised in text
PLACE_ALIASES = {
    "Khyber Pakhtunkhwa": ["KP", "KPK", "Khyber-Pakhtunkhwa", "NWFP"],
    "Balochistan": ["Baluchistan"],
    "Sindh": ["Sind"],
    "Gilgit-Baltistan": ["Gilgit Baltistan", "GB"],
    "Azad Jammu and Kashmir": ["AJK", "Azad Kashmir", "Azad Jammu & Kashmir"],
    "Islamabad Capital Territory": ["ICT"],
    "Dera Ismail Khan": ["D.I. Khan", "DI Khan"],
    "Mingora": ["Swat"],
}
