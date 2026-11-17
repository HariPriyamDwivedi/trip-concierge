"""Memories: upload (photo EXIF time + GPS, thumbnails), listing, editing, map
pins, deleting, and privacy between users. Local storage, no network.
"""

import io

import pytest
from PIL import Image

from backend import media as media_mod
from tests.test_api import FakeService


def _jpeg_with_gps(lat=35.0116, lng=135.7681, when="2026:04:02 09:15:00", offset="+09:00"):
    img = Image.new("RGB", (1200, 800), (30, 120, 90))
    exif = Image.Exif()
    exif[0x0132] = when
    exif[0x8769] = {0x9003: when, 0x9011: offset}  # DateTimeOriginal, OffsetTimeOriginal

    def dms(v):
        d = int(v); m = int((v - d) * 60); s = round(((v - d) * 60 - m) * 60, 2)
        return (float(d), float(m), s)

    exif[0x8825] = {1: "N", 2: dms(lat), 3: "E", 4: dms(lng)}
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def no_network_geocoder(monkeypatch):
    known = {"goa": (15.4909, 73.8278, "Goa, India"), "kyoto": (35.0116, 135.7681, "Kyoto, Japan")}
    monkeypatch.setattr(media_mod, "_nominatim", lambda q: known.get(q.strip().lower()))


def test_photo_upload_reads_exif_and_makes_thumbnail(make_client):
    c = make_client(FakeService())
    m = c.post("/api/media", files={"file": ("kyoto.jpg", _jpeg_with_gps(), "image/jpeg")}, data={"place": "Kyoto"}).json()
    assert m["kind"] == "photo" and m["thumb_url"] == f"/api/media/{m['id']}/thumb"
    assert m["taken_at"] == "2026-04-02T09:15:00+09:00"  # camera's own zone kept
    assert abs(m["lat"] - 35.0116) < 1e-3 and abs(m["lng"] - 135.7681) < 1e-3  # from GPS, not geocoded
    thumb = c.get(m["thumb_url"])
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/jpeg"
    assert max(Image.open(io.BytesIO(thumb.content)).size) == 640
    assert c.get(m["url"]).content[:2] == b"\xff\xd8"  # original JPEG


def test_video_and_files_with_typed_place(make_client):
    c = make_client(FakeService())
    trip = c.post("/api/trips", json={}).json()["id"]
    v = c.post("/api/media", files={"file": ("beach.mp4", b"\x00\x00\x00\x18ftypmp42" + b"0" * 100, "video/mp4")},
               data={"place": "Goa", "trip_id": trip, "caption": "Sunset at Anjuna", "taken_at": "2026-12-28T18:05"}).json()
    assert v["kind"] == "video" and v["thumb_url"] is None
    assert (round(v["lat"], 2), round(v["lng"], 2)) == (15.49, 73.83)  # geocoded from the place name
    assert v["taken_at"] == "2026-12-28T18:05:00+00:00"  # wall clock read in the user's zone (UTC by default)
    f = c.post("/api/media", files={"file": ("menu.pdf", b"%PDF-1.4 x", "application/pdf")}, data={"trip_id": trip}).json()
    assert f["kind"] == "file" and f["lat"] is None
    assert [m["id"] for m in c.get(f"/api/media?trip_id={trip}&kind=video").json()] == [v["id"]]
    assert {t["id"]: t["media_count"] for t in c.get("/api/trips").json()}[trip] == 2


def test_map_places_group_memories(make_client):
    c = make_client(FakeService())
    for name in ("a.jpg", "b.jpg"):
        c.post("/api/media", files={"file": (name, _jpeg_with_gps(), "image/jpeg")}, data={"place": "Kyoto"})
    c.post("/api/media", files={"file": ("c.mp4", b"0" * 50, "video/mp4")}, data={"place": "Goa"})
    c.post("/api/media", files={"file": ("d.txt", b"notes", "text/plain")})  # no place -> not on the map
    pins = {p["place"]: p for p in c.get("/api/places").json()}
    assert set(pins) == {"Kyoto", "Goa"}
    assert (pins["Kyoto"]["count"], pins["Kyoto"]["photos"], pins["Goa"]["videos"]) == (2, 2, 1)
    assert pins["Kyoto"]["cover_url"].endswith("/thumb") and pins["Goa"]["cover_url"] is None
    assert c.get("/api/me").json()["stats"] == {"trips": 0, "memories": 4, "places": 2}


def test_edit_and_delete(make_client, tmp_path):
    c = make_client(FakeService())
    m = c.post("/api/media", files={"file": ("x.jpg", _jpeg_with_gps(), "image/jpeg")}).json()
    edited = c.patch(f"/api/media/{m['id']}", json={"caption": "Golden hour", "place": "Kyoto"}).json()
    assert (edited["caption"], edited["place"]) == ("Golden hour", "Kyoto")
    assert c.delete(f"/api/media/{m['id']}").json() == {"ok": True}
    assert c.get("/api/media").json() == [] and c.get(m["url"]).status_code == 404
    assert not list((tmp_path / "media").rglob("original"))  # stored files removed too


@pytest.mark.parametrize("name, data, ctype", [("run.exe", b"MZ", "application/octet-stream"), ("page.html", b"<script>", "text/html"),
                                               ("empty.jpg", b"", "image/jpeg")])
def test_rejects_dangerous_or_empty_files(make_client, name, data, ctype):
    c = make_client(FakeService())
    assert c.post("/api/media", files={"file": (name, data, ctype)}).status_code == 422


def test_rejects_half_coordinates_and_foreign_trip(make_client):
    a = make_client(FakeService())
    b = make_client(app=a.app, email="ben@example.test")
    other = b.post("/api/trips", json={}).json()["id"]
    f = {"file": ("x.txt", b"hi", "text/plain")}
    assert a.post("/api/media", files=f, data={"lat": "10"}).status_code == 422
    assert a.post("/api/media", files=f, data={"lat": "100", "lng": "10"}).status_code == 422
    assert a.post("/api/media", files=f, data={"trip_id": other}).status_code == 404


def test_users_cannot_see_each_others_memories(make_client):
    a = make_client(FakeService())
    b = make_client(app=a.app, email="ben@example.test")
    m = a.post("/api/media", files={"file": ("x.jpg", _jpeg_with_gps(), "image/jpeg")}, data={"place": "Kyoto"}).json()
    assert b.get("/api/media").json() == [] and b.get("/api/places").json() == []
    assert b.get(m["url"]).status_code == 404 and b.get(m["thumb_url"]).status_code == 404
    assert b.patch(f"/api/media/{m['id']}", json={"caption": "mine"}).status_code == 404
    assert b.delete(f"/api/media/{m['id']}").status_code == 404
