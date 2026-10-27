"""Who works where (OCHA 3W) and NGO offices on OpenStreetMap, without a database or the internet."""

import uuid
from datetime import date

from app.services.ngo_sources import Presence, overpass_query, parse_osm, same_org, works_for


def test_same_org_names():
    assert same_org("Edhi Foundation", "EDHI Welfare Organization")
    assert same_org("Alkhidmat Foundation Pakistan", "Al-Khidmat Foundation") is False   # different spelling of the core word
    assert same_org("Norwegian Refugee Council", "NRC") and same_org("NRC", "Norwegian Refugee Council")
    assert same_org("Islamic Relief Pakistan", "Islamic Relief Worldwide Islamic Relief") is True
    assert not same_org("HANDS", "Muslim Hands") and not same_org("Islamic Relief", "Islamic Help")
    assert not same_org("Foundation", "Trust Pakistan")   # nothing distinctive


def test_works_for_groups_places_and_sectors():
    dadu, jac = uuid.uuid4(), uuid.uuid4()
    index = [Presence(dadu, "Dadu", "region", ["WASH"], "IRC", date(2025, 12, 31)),
             Presence(dadu, "Dadu", "region", ["WASH"], "International Rescue Committee", date(2025, 12, 31)),
             Presence(dadu, "Dadu", "region", ["Shelter"], "International Rescue Committee", date(2025, 12, 31)),
             Presence(jac, "Jacobabad", "region", ["Health"], "Save the Children", date(2025, 6, 30))]
    w = works_for("International Rescue Committee (IRC)", index)
    assert w.places == {"Dadu": ["WASH", "Shelter"]} and w.location_ids == {dadu}
    assert w.text() == "Works on Shelter, WASH in Dadu (OCHA 3W, Dec 2025)"
    assert works_for("Local Trust", index).text() is None


def test_parse_osm_offices():
    data = {"elements": [
        {"type": "node", "id": 1, "lat": 25.39, "lon": 68.37,
         "tags": {"name": "Hyderabad Welfare Trust", "office": "ngo", "addr:street": "Station Road", "addr:city": "Hyderabad",
                  "phone": "+92 22 1234567"}},
        {"type": "way", "id": 2, "center": {"lat": 25.4, "lon": 68.36}, "tags": {"name": "Darul Aman", "amenity": "social_facility",
                                                                                "social_facility": "shelter"}},
        {"type": "node", "id": 3, "lat": 25.0, "lon": 68.0, "tags": {"office": "ngo"}},                         # no name
        {"type": "node", "id": 4, "lat": 25.39, "lon": 68.37, "tags": {"name": "HYDERABAD WELFARE TRUST"}},   # repeat
    ]}
    rows = parse_osm(data)
    assert [r["name"] for r in rows] == ["Hyderabad Welfare Trust", "Darul Aman"]
    assert rows[0]["address"] == "Station Road, Hyderabad" and rows[0]["phone"] == "+92 22 1234567"
    assert rows[1]["lat"] == 25.4 and rows[1]["kind"] == "shelter" and rows[1]["url"] == "https://www.openstreetmap.org/way/2"
    q = overpass_query(25.39, 68.37, 15000)
    assert "around:15000,25.39,68.37" in q and '"office"~' in q and "social_facility" in q
    assert "Edhi" in q and "Saylani" in q and "JDC" in q and '"name"~' in q   # charity networks found by name too
    edhi = parse_osm({"elements": [{"type": "node", "id": 5, "lat": 27.8, "lon": 66.6,
                                    "tags": {"name": "Edhi Centre Khuzdar", "amenity": "ambulance_station"}}]})
    assert edhi[0]["name"] == "Edhi Centre Khuzdar" and edhi[0]["kind"] == "ambulance station"
