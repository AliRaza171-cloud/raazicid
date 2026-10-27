"""Long-term deprivation and DTM displacement without a database: reading tables, matching places, bands, sums."""

import io
import uuid
from datetime import date

from app.services.deprivation import band, match, number, parse_table, read_rows, summarise
from app.services.gazetteer import Place
from app.services.needs import score_idps
from app.services.sources.hapi_un import displacement


def test_numbers_and_shares():
    assert number("1,234", share=False) == 1234 and number("34%", share=True) == 0.34
    assert number(34, share=True) == 0.34 and number(0.34, share=True) == 0.34
    assert number("abc", share=False) is None and number("140%", share=True) is None and number("-5", share=False) is None


def test_pslm_style_table_with_title_rows_and_total_column():
    rows = [["Table 2.14a Literacy rate (10 years and older)"], [""],
            ["Province", "District", "Male", "Female", "Total"],
            ["Balochistan", "Kech District", "61", "39", "52"],
            ["Balochistan", "Quetta", "70", "48", "60"],
            ["Balochistan", "Total", "55", "30", "43"]]
    t = parse_table(rows, share=True, invert=True)
    assert t["used"] == {"place": "District", "value": "Total", "province": "Province"}
    assert t["rows"] == [("Kech District", "Balochistan", 0.48), ("Quetta", "Balochistan", 0.4)]   # 100% - literacy


def test_urban_rural_rows_keep_the_total():
    rows = [["District", "Area", "Out of school (%)"], ["Kech", "Urban", "20"], ["Kech", "Rural", "45"], ["Kech", "Total", "38"]]
    assert parse_table(rows, share=True)["rows"] == [("Kech", None, 0.38)]


def test_dtm_style_sheet_and_named_columns():
    rows = [["Admin 1 Name", "Admin 2 Name", "IDP Households", "IDP Individuals"],
            ["Sindh", "Dadu", 3100, 18500], ["Sindh", "Jacobabad", "1,200", "7,050"]]
    t = parse_table(rows, share=False)
    assert t["used"]["place"] == "Admin 2 Name" and t["used"]["value"] == "IDP Individuals"
    assert t["rows"][1] == ("Jacobabad", "Sindh", 7050.0)
    t2 = parse_table(rows, share=False, value_column="IDP Households")
    assert t2["rows"][0][2] == 3100 and parse_table(rows, share=False, value_column="Nope")["problems"]


def test_headerless_csv_and_province_only_table():
    assert parse_table(read_rows(b"Kech District;34%\nQuetta;0.21\n", "t.csv"), share=True)["rows"] == \
        [("Kech District", None, 0.34), ("Quetta", None, 0.21)]
    hies = [["Province", "Food insecure (%)"], ["Punjab", "21.5"], ["Sindh", "30.1"]]
    assert parse_table(hies, share=True)["rows"] == [("Punjab", None, 0.215), ("Sindh", None, 0.301)]


def test_excel_upload_is_read():
    from openpyxl import Workbook
    wb = Workbook()
    wb.active.append(["District", "Out of school %"])
    wb.active.append(["Kech", 41])
    buf = io.BytesIO()
    wb.save(buf)
    assert parse_table(read_rows(buf.getvalue(), "pslm.xlsx"), share=True)["rows"] == [("Kech", None, 0.41)]


def test_match_place_names_inside_province():
    bal = Place(uuid.uuid4(), "Balochistan", "province", None, None, None)
    sindh = Place(uuid.uuid4(), "Sindh", "province", None, None, None)
    kech = Place(uuid.uuid4(), "Kech", "region", bal.id, None, None)
    hyd_s = Place(uuid.uuid4(), "Hyderabad", "city", sindh.id, None, None)
    places = [bal, sindh, kech, hyd_s]
    assert match("Kech District", places) == kech and match("kech", places, bal) == kech
    assert match("Kech", places, sindh) is None and match("Atlantis", places) is None
    qambar = Place(uuid.uuid4(), "Qambar Shahdadkot", "region", sindh.id, None, None)
    assert match("Kambar Shahdadkot", places + [qambar], sindh) == qambar      # spelling differs between surveys


def test_bands_and_summaries():
    pool = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    assert band(0.8, pool) == "high" and band(0.5, pool) == "moderate" and band(0.1, pool) == "lower"
    assert band(0.5, [0.5, 0.6]) is None
    a, b, c, parent = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    vals = {a: {"value": 0.6, "source": "PSLM", "year": 2020}, b: {"value": 0.2, "source": "PSLM", "year": 2020}}
    s = summarise(vals, [parent, a, b, c], parent, True, pool)
    assert s["places"] == 2 and abs(s["value"] - 0.4) < 1e-9 and "average" in s["display"]
    assert summarise(vals, [a], a, True, pool)["display"] == "60%"
    ppl = {a: {"value": 1200, "source": "DTM", "year": 2022}, b: {"value": 800, "source": "DTM", "year": 2022}}
    assert summarise(ppl, [parent, a, b], parent, False, [1200, 800])["display"] == "2,000 people"
    assert summarise(vals, [c], c, True, pool) is None


def test_dtm_displacement_latest_round_and_no_double_count():
    rows = [
        {"operation": "Flood Response", "admin1_name": "Sindh", "admin2_name": "Dadu", "admin2_code": "PK1",
         "population": 10000, "reference_period_end": "2022-10-31", "reporting_round": 2},
        {"operation": "Flood Response", "admin1_name": "Sindh", "admin2_name": "Dadu", "admin2_code": "PK1",
         "population": 2500, "reference_period_end": "2022-10-31", "reporting_round": 2},          # another origin: adds up
        {"operation": "Flood Response", "admin1_name": "Sindh", "admin2_name": "Dadu", "admin2_code": "PK1",
         "population": 50000, "reference_period_end": "2022-09-30", "reporting_round": 1},         # older round: ignored
        {"operation": "Flood Response", "admin1_name": "Sindh", "admin2_name": None,
         "population": 99999, "reference_period_end": "2022-10-31", "reporting_round": 2},         # province total: ignored
    ]
    out = displacement(rows)
    assert len(out) == 1 and out[0]["people"] == 12500 and out[0]["period_end"] == date(2022, 10, 31)
    assert score_idps(12500) == 45 and score_idps(150_000) == 70 and score_idps(500) == 0
