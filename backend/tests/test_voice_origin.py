from app.main import voice_origin_allowed


def test_voice_accepts_same_origin_development_and_lan_hosts():
    assert voice_origin_allowed("http://localhost:5173", "localhost:5173")
    assert voice_origin_allowed("http://192.168.1.20:8080", "192.168.1.20:8080")
    assert voice_origin_allowed("https://travel.example", "travel.example")


def test_voice_rejects_cross_origin_and_malformed_origin():
    assert not voice_origin_allowed("https://other.example", "travel.example")
    assert not voice_origin_allowed("https://travel.example.evil", "travel.example")
    assert not voice_origin_allowed("https://travel.example/path", "travel.example")
    assert not voice_origin_allowed("", "travel.example")
