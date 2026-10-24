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
