"""Long-term deprivation layer and IOM DTM displacement end-to-end. Skipped without TEST_DATABASE_URL."""

import io
import uuid
from datetime import date

from openpyxl import Workbook
from sqlalchemy import delete, select

from app.models import NeedIndicator, Source
from app.models.enums import SourceKind
from app.services.deprivation import facts_for
from app.services.needs import recompute
from tests.test_auth_api import API
from tests.test_donations_api import admin_headers, area


def up(client, h, measure, name, content, **form):
    data = {"measure": measure, "source": form.pop("source", "PSLM 2019-20"), "year": str(form.pop("year", 2020)),
            **{k: str(v).lower() if isinstance(v, bool) else v for k, v in form.items()}}
    return client.post(f"{API}/admin/deprivation/upload", headers=h, data=data, files={"file": (name, content, "text/csv")})


def test_deprivation_layer_and_dtm(client, db):
    h = admin_headers(client, db)
    sid = db.scalar(select(Source.id).where(Source.kind == SourceKind.hdx_hapi))
    lyari = uuid.UUID(area(db, "Lyari"))
    recent = NeedIndicator(location_id=lyari, indicator="idps_present", value=150000, source_id=sid,
                           period_end=date.today(), meta={"operations": ["Flood Response"], "round": 3})
    db.add(recent)
    db.commit()
    try:
        # A PSLM-style table: province column, literacy rate turned into "cannot read", a new district added under Sindh
        csv = ("Province,District,Total\nSindh,Karachi South District,72\nSindh,Hyderabad,61\nSindh,Tharparkar,28\n"
               "Sindh,Sukkur,55\nPunjab,Lahore,78\nSindh,Atlantis,50\nSindh,Total,62\n").encode()
        r = up(client, h, "illiteracy", "lit.csv", csv, invert=True)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["used"] == {"place": "District", "value": "Total", "province": "Province"}
        assert body["matched"] == 6 and body["added_places"] >= 1          # Tharparkar and Atlantis are new under Sindh
        # An Excel sheet from DTM: column named by the admin
        wb = Workbook()
        wb.active.append(["Admin 1", "Admin 2", "IDP Households", "IDP Individuals"])
        wb.active.append(["Sindh", "Hyderabad", 300, 1800])
        buf = io.BytesIO()
        wb.save(buf)
        r = up(client, h, "displaced", "dtm.xlsx", buf.getvalue(), source="IOM DTM baseline", year=2022, value_column="IDP Households")
        assert r.status_code == 200 and r.json()["matched"] == 1, r.text
        assert up(client, h, "nonsense", "t.csv", b"Lyari,1").status_code == 422
        assert up(client, h, "displaced", "t.pdf", b"x").status_code == 422
        bad = up(client, h, "displaced", "t.csv", b"District,Households\nDadu,5\n", value_column="Individuals")
        assert bad.status_code == 422 and "Individuals" in bad.json()["detail"]["message"]

        sindh = client.get(f"{API}/admin/deprivation", headers=h, params={"parent_id": area(db, "Sindh")}).json()
        tharparkar = next(x for x in sindh["rows"] if x["name"] == "Tharparkar")
        assert tharparkar["values"]["illiteracy"]["display"] == "72%" and tharparkar["values"]["illiteracy"]["band"] == "high"
        karachi = next(x for x in sindh["rows"] if x["name"] == "Karachi")
        assert karachi["values"]["illiteracy"]["places"] >= 1
        # Displaced: the uploaded table for Hyderabad, and DTM via HDX for Lyari (inside Karachi) where nothing was uploaded
        assert next(x for x in sindh["rows"] if x["name"] == "Hyderabad")["values"]["displaced"]["display"] == "300 people"
        assert karachi["values"]["displaced"]["source"].startswith("IOM DTM via HDX")
        assert {t["measure"]: t["rows"] for t in sindh["tables"]}["illiteracy"] == 6
        assert client.get(f"{API}/admin/deprivation/template", headers=h).json()["csv"].startswith("province,place,value")
        assert any("cannot read" in f for f in facts_for(db, uuid.UUID(area(db, "Sindh")), ["books"]))

        # Need levels: recent DTM displacement counts; the deprivation tables never do
        recompute(db)
        needs = client.get(f"{API}/needs", headers=h, params={"parent_id": area(db, "Karachi")}).json()
        south = next(x for x in needs["children"] if x["name"] == "Karachi South")
        relief = next(n for n in south["needs"] if n["name"] == "Emergency relief")
        assert any("150,000 displaced people" in r["why"] for r in relief["reasons"])
        assert all("PSLM" not in r["source"] for n in south["needs"] for r in n["reasons"])

        # Old DTM figures (2022) are no need signal, but stay in the deprivation layer
        recent.period_end = date(2022, 10, 31)
        db.commit()
        recompute(db)
        needs = client.get(f"{API}/needs", headers=h, params={"parent_id": area(db, "Karachi")}).json()
        south = next(x for x in needs["children"] if x["name"] == "Karachi South")
        assert all("displaced" not in r["why"] for n in south["needs"] for r in n["reasons"])

        assert client.delete(f"{API}/admin/deprivation/illiteracy", headers=h).json() == {"removed": "illiteracy"}
    finally:
        db.execute(delete(NeedIndicator).where(NeedIndicator.indicator.like("dep:%")))
        db.execute(delete(NeedIndicator).where(NeedIndicator.id == recent.id))
        db.commit()
        recompute(db)
