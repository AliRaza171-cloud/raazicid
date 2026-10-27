"""NGO finder for places in need, without a database: what counts as a gap, which 3W organisations qualify."""

import uuid

from app.services.sources.ngo_gaps import NeedSpot, NgoSpot, candidates_from_3w, covered, gaps_of, is_ngo_name

JHANG, LYARI, KARACHI = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def spot(loc, cat=4, level=2, score=60, lat=31.27, lng=72.32, radius=30, inside=None):
    return NeedSpot(loc, cat, "blankets", level, score, lat, lng, radius, inside or {loc})


def test_gap_when_no_ngo_nearby_takes_the_item():
    need = spot(JHANG)
    food_only = NgoSpot(31.27, 72.33, uuid.uuid4(), {1})
    far_any = NgoSpot(31.52, 74.35, uuid.uuid4(), set())          # Lahore, 230 km away
    assert gaps_of([need], [food_only, far_any]) == [need]
    near_any = NgoSpot(31.30, 72.35, uuid.uuid4(), set())          # takes everything, 4 km away
    assert gaps_of([need], [near_any]) == [] and covered(need, [near_any])


def test_filed_inside_the_place_counts_even_without_a_map_position():
    need = spot(KARACHI, lat=None, lng=None, inside={KARACHI, LYARI})
    assert covered(need, [NgoSpot(30.0, 69.0, LYARI, {4})])      # approximate pin, but filed in Lyari
    assert not covered(need, [NgoSpot(24.86, 67.0, uuid.uuid4(), {4})])


def test_only_high_or_urgent_and_highest_first():
    some = spot(JHANG, level=1, score=40)
    high = spot(LYARI, level=2, score=60, lat=24.87, lng=67.0)
    urgent = spot(KARACHI, level=3, score=90, lat=24.86, lng=67.01)
    assert gaps_of([some, high, urgent], []) == [urgent, high]


def test_3w_candidates_serve_the_need_and_are_ngos():
    sectors = {"NRC": ["Shelter and NFI"], "UNHCR": ["Shelter and NFI"], "AKF": ["Education"],
               "PDMA Punjab": ["Shelter"], "Islamic Relief": ["Emergency Shelter", "WASH"]}
    names = {"NRC": "Norwegian Refugee Council"}
    got = candidates_from_3w(sectors, names, "blankets")
    assert [n for n, _ in got] == ["Norwegian Refugee Council", "Islamic Relief"]
    assert is_ngo_name("Edhi Foundation") and not is_ngo_name("World Food Programme") and not is_ngo_name("UNICEF")
