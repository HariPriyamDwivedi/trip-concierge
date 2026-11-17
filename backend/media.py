"""Memories: upload, metadata (EXIF time + GPS), thumbnails, places for the map.

Photos get a 640 px JPEG thumbnail and, when the camera recorded them, their
capture time and GPS position from EXIF. Typed place names are geocoded with
OpenStreetMap Nominatim (place names only, cached; GPS coordinates from photos
are never sent anywhere). Videos and other files keep the metadata the user gives.
"""

import datetime as dt
import io
import json
import logging
import os
import tempfile
import urllib.parse
import urllib.request
from typing import BinaryIO, Optional

from sqlalchemy import select

from .db import Database, GeoCache, Media, new_id

log = logging.getLogger("trip_concierge.media")

MAX_BYTES = 200 * 1024 * 1024  # per file
_BLOCKED = {".exe", ".bat", ".cmd", ".com", ".scr", ".msi", ".js", ".vbs", ".ps1", ".sh", ".apk", ".dll", ".html", ".htm", ".svg"}


def kind_of(content_type: str) -> str:
    top = (content_type or "").split("/")[0]
    return {"image": "photo", "video": "video", "audio": "audio"}.get(top, "file")


def check_upload(filename: str) -> None:
    ext = os.path.splitext(filename)[1].lower()
    if ext in _BLOCKED:
        raise ValueError(f"{ext} files can't be uploaded")


def _ratio(v) -> float:
    return float(v[0]) / float(v[1]) if isinstance(v, tuple) else float(v)


def photo_metadata(data: bytes) -> dict:
    """(thumbnail JPEG bytes, taken_at, lat, lng) from an image; {} if unreadable."""
    try:
        from PIL import ExifTags, Image, ImageOps
    except ImportError:
        return {}
    try:
        img = Image.open(io.BytesIO(data))
        exif = img.getexif()
        out: dict = {}
        sub = exif.get_ifd(ExifTags.IFD.Exif)
        raw = sub.get(ExifTags.Base.DateTimeOriginal) or exif.get(ExifTags.Base.DateTime)
        if raw:
            taken = dt.datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S")
            # Newer cameras record the zone offset (EXIF OffsetTimeOriginal, e.g. "+05:30").
            offset = sub.get(0x9011)
            if offset and len(str(offset)) == 6:
                sign = -1 if str(offset)[0] == "-" else 1
                hh, mm = int(str(offset)[1:3]), int(str(offset)[4:6])
                taken = taken.replace(tzinfo=dt.timezone(sign * dt.timedelta(hours=hh, minutes=mm)))
            else:
                # shortcut: no offset recorded -> treated as UTC (a few hours off at worst);
                # upgrade by inferring the zone from the photo's GPS position.
                taken = taken.replace(tzinfo=dt.timezone.utc)
            out["taken_at"] = taken
        gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
        if gps and 2 in gps and 4 in gps:
            lat = sum(_ratio(x) / 60**i for i, x in enumerate(gps[2]))
            lng = sum(_ratio(x) / 60**i for i, x in enumerate(gps[4]))
            out["lat"] = -lat if gps.get(1) == "S" else lat
            out["lng"] = -lng if gps.get(3) == "W" else lng
        thumb = ImageOps.exif_transpose(img).convert("RGB")
        thumb.thumbnail((640, 640))
        buf = io.BytesIO()
        thumb.save(buf, "JPEG", quality=80)
        out["thumb"] = buf.getvalue()
        return out
    except Exception as exc:  # not an image Pillow can read (e.g. HEIC): keep the original only
        log.info("no photo metadata: %s", exc)
        return {}


def _nominatim(place: str) -> Optional[tuple[float, float, str]]:
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({"q": place, "format": "json", "limit": 1})
    req = urllib.request.Request(url, headers={"User-Agent": "trip-concierge/0.1 (self-hosted demo)"})
    with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310 - fixed host
        hits = json.loads(resp.read())
    return (float(hits[0]["lat"]), float(hits[0]["lon"]), hits[0].get("display_name", place)) if hits else None


async def geocode(db: Database, place: str, *, lookup=None) -> Optional[tuple[float, float]]:
    """Coordinates for a place name, cached. None if unknown or lookups are off."""
    key = place.strip().lower()[:160]
    if not key or os.getenv("GEOCODER", "nominatim") == "off":
        return None
    async with db.session() as s:
        hit = await s.get(GeoCache, key)
        if hit:
            return (hit.lat, hit.lng) if hit.lat is not None else None
        try:
            found = (lookup or _nominatim)(place)
        except Exception as exc:
            log.warning("geocoding failed: %s", exc)
            return None  # not cached: try again next time
        s.add(GeoCache(query=key, lat=found[0] if found else None, lng=found[1] if found else None,
                       label=found[2][:200] if found else None))
        await s.commit()
        return (found[0], found[1]) if found else None


async def save_upload(
    db: Database,
    storage,
    *,
    user_id: str,
    upload,  # starlette UploadFile
    trip_id: Optional[str],
    caption: Optional[str],
    place: Optional[str],
    lat: Optional[float],
    lng: Optional[float],
    taken_at: Optional[dt.datetime],
) -> Media:
    filename = os.path.basename(upload.filename or "file")[:200] or "file"
    check_upload(filename)
    content_type = (upload.content_type or "application/octet-stream")[:120]
    media_id = new_id()
    base = f"users/{user_id}/{media_id}"
    kind = kind_of(content_type)

    # Spool to a temp file so big videos never sit in memory; enforce the size cap.
    with tempfile.SpooledTemporaryFile(max_size=16 * 1024 * 1024) as tmp:
        size = 0
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError(f"file is larger than {MAX_BYTES // 2**20} MB")
            tmp.write(chunk)
        if size == 0:
            raise ValueError("the file is empty")
        meta = {}
        if kind == "photo" and size <= 40 * 1024 * 1024:
            tmp.seek(0)
            meta = photo_metadata(tmp.read())
        tmp.seek(0)
        storage.put(f"{base}/original", tmp, content_type)
    thumb_key = None
    if meta.get("thumb"):
        thumb_key = f"{base}/thumb"
        storage.put(thumb_key, io.BytesIO(meta["thumb"]), "image/jpeg")

    lat = lat if lat is not None else meta.get("lat")
    lng = lng if lng is not None else meta.get("lng")
    if (lat is None or lng is None) and place:
        found = await geocode(db, place)
        if found:
            lat, lng = found
    media = Media(
        id=media_id, user_id=user_id, trip_id=trip_id, storage_key=f"{base}/original", thumb_key=thumb_key,
        filename=filename, content_type=content_type, size=size, kind=kind,
        caption=(caption or "").strip()[:2000] or None, place=(place or "").strip()[:120] or None,
        lat=lat, lng=lng, taken_at=taken_at or meta.get("taken_at"),
    )
    async with db.session() as s:
        s.add(media)
        await s.commit()
    return media


def media_json(m: Media, storage) -> dict:
    return {
        "id": m.id,
        "trip_id": m.trip_id,
        "kind": m.kind,
        "filename": m.filename,
        "content_type": m.content_type,
        "size": m.size,
        "caption": m.caption,
        "place": m.place,
        "lat": m.lat,
        "lng": m.lng,
        "taken_at": m.taken_at.isoformat() if m.taken_at else None,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "url": storage.url(m.storage_key, m.id, "original", m.filename, m.content_type),
        "thumb_url": storage.url(m.thumb_key, m.id, "thumb", m.filename, "image/jpeg") if m.thumb_key else None,
    }


def places(items: list[Media]) -> list[dict]:
    """Map pins: media with coordinates grouped by place (or ~1 km grid if unnamed)."""
    groups: dict[str, dict] = {}
    for m in items:
        if m.lat is None or m.lng is None:
            continue
        key = (m.place or "").strip().lower() or f"{round(m.lat, 2)},{round(m.lng, 2)}"
        g = groups.setdefault(key, {"place": m.place or f"{m.lat:.3f}, {m.lng:.3f}", "lat": 0.0, "lng": 0.0,
                                    "count": 0, "photos": 0, "videos": 0, "media_ids": []})
        g["lat"] += m.lat
        g["lng"] += m.lng
        g["count"] += 1
        g["photos"] += m.kind == "photo"
        g["videos"] += m.kind == "video"
        g["media_ids"].append(m.id)
    out = []
    for g in groups.values():
        g["lat"], g["lng"] = g["lat"] / g["count"], g["lng"] / g["count"]
        out.append(g)
    return sorted(out, key=lambda g: -g["count"])
