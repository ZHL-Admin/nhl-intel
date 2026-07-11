from atlas.manifest import Manifest, ManifestEntry


def _entry(key="g/pbp", path="g/pbp.json"):
    return ManifestEntry(key=key, url="http://x", path=path, status=200, bytes=10,
                         sha256="abc", fetched_at="2026-07-10T00:00:00+00:00",
                         from_cache=False)


def test_record_and_roundtrip(tmp_path):
    mpath = tmp_path / "manifest.json"
    m = Manifest(mpath)
    m.record(_entry())
    m.save()

    m2 = Manifest(mpath)
    assert m2.get("g/pbp").status == 200
    assert m2.get("g/pbp").sha256 == "abc"


def test_has_requires_file_present(tmp_path):
    mpath = tmp_path / "manifest.json"
    m = Manifest(mpath)
    m.record(_entry(path="g/pbp.json"))
    # File does not exist -> has() is False even though the entry is recorded.
    assert m.has("g/pbp") is False

    (tmp_path / "g").mkdir()
    (tmp_path / "g" / "pbp.json").write_text("{}")
    assert m.has("g/pbp") is True


def test_save_is_atomic_no_tmp_left(tmp_path):
    mpath = tmp_path / "manifest.json"
    m = Manifest(mpath)
    m.record(_entry())
    m.save()
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []
