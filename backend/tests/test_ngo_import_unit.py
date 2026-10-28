"""Importing an admin's NGO list, without a database: reading the table, items, matching names."""

from app.services.ngo_import import category_ids, parse_rows, same_ngo

CATS = {"Food": 1, "Grocery / ration": 2, "Blankets": 4, "Hygiene items": 6, "Emergency relief": 12}


def test_reads_any_column_order_and_several_districts():
    rows = [
        ["My NGO list"],                                                  # a title above the headings
        ["Phone", "NGO Name", "Districts", "Takes", "Website", "Email"],
        ["+92 305 3044806", "SACH", "Badin; Sujawal ; Tharparkar", "Food; Grocery / ration", "https://sachpk.org", "contact@sachpk.org"],
        ["", "", "", "", "", ""],
        ["0300-3400337", "Pakistan Red Crescent Society - Dadu", "Dadu", "", "", ""],
        ["", "No district NGO", "", "", "", ""],
    ]
    got, problems = parse_rows(rows)
    assert [r.name for r in got] == ["SACH", "Pakistan Red Crescent Society - Dadu"]
    assert got[0].districts == ["Badin", "Sujawal", "Tharparkar"] and got[0].takes == ["Food", "Grocery / ration"]
    assert got[0].phone == "+92 305 3044806" and got[0].email == "contact@sachpk.org" and got[1].takes == []
    assert problems == ["Row 6: needs both a name and a district"]


def test_no_heading_row():
    got, problems = parse_rows([["a", "b"], ["c", "d"]])
    assert got == [] and "name" in problems[0]


def test_bad_map_position_is_dropped():
    got, problems = parse_rows([["name", "district", "lat", "lng"], ["X Trust", "Dadu", "51.5", "-0.1"]])
    assert got[0].lat is None and "not in Pakistan" in problems[0]


def test_items_by_name():
    ids, unknown = category_ids(["food", "Grocery", "blankets ", "rations", "Emergency relief"], CATS)
    assert ids == [1, 2, 4, 12] and unknown == ["rations"]


def test_same_ngo_in_a_district():
    assert same_ngo("Saylani Welfare International Trust", "Saylani Welfare Trust - Numaish Branch")
    assert same_ngo("Edhi Foundation", "EDHI Welfare Organization")
    assert not same_ngo("Sukaar Foundation", "Thardeep Rural Development Programme")
