from bist_core.providers.disclosures.normalize import normalize_kap_item


def test_normalize_kap_item() -> None:
    raw = {
        "disclosureId": "12345",
        "stockCode": "akbnk",
        "title": "Özel Durum Açıklaması",
        "publishedAt": "2026-03-08T10:00:00Z",
        "url": "https://example.test/disclosure/12345",
        "category": "genel",
    }

    rec = normalize_kap_item(raw)

    assert rec.provider_name == "kap"
    assert rec.disclosure_id == "12345"
    assert rec.symbol == "AKBNK"
    assert rec.title == "Özel Durum Açıklaması"
    assert rec.published_at == "2026-03-08T10:00:00Z"
    assert rec.url == "https://example.test/disclosure/12345"
    assert rec.category == "GENEL"
