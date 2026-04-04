from __future__ import annotations

from bist_core.services.chat_intent import classify_chat_intent, detect_top_n, extract_bist_symbols

KNOWN = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]


def test_extract_bist_symbols_handles_freeform_single_symbol() -> None:
    got = extract_bist_symbols("asels bugün alınır mı, giriş kaçtı mı?", known_symbols=KNOWN)
    assert got == ["ASELS"]


def test_extract_bist_symbols_handles_multiple_symbols() -> None:
    got = extract_bist_symbols("akbnk ile garan karşılaştır", known_symbols=KNOWN)
    assert got == ["AKBNK", "GARAN"]


def test_extract_bist_symbols_filters_noise_tokens() -> None:
    got = extract_bist_symbols("BIST ve KAP tarafında genel görünüm ne?", known_symbols=KNOWN)
    assert got == []


def test_detect_top_n_for_scan_prompt() -> None:
    assert detect_top_n("scan top 5 fırsat") == 5
    assert detect_top_n("ilk 10 hisseyi listele") == 10


def test_classify_chat_intent_scan() -> None:
    got = classify_chat_intent("scan top 5", known_symbols=KNOWN)
    assert got["intent"] == "scan"
    assert got["top_n"] == 5
    assert got["symbol_count"] == 0


def test_classify_chat_intent_comparison() -> None:
    got = classify_chat_intent("AKBNK ile GARAN karşılaştır", known_symbols=KNOWN)
    assert got["intent"] == "comparison"
    assert got["symbols"] == ["AKBNK", "GARAN"]


def test_classify_chat_intent_single_symbol() -> None:
    got = classify_chat_intent("ASELS için bugün giriş kaçtı mı?", known_symbols=KNOWN)
    assert got["intent"] == "single_symbol"
    assert got["symbols"] == ["ASELS"]


def test_classify_chat_intent_market_overview() -> None:
    got = classify_chat_intent("BIST genel görünüm ve sektör rotasyonu ne durumda?", known_symbols=KNOWN)
    assert got["intent"] == "market_overview"
    assert got["symbol_count"] == 0


def test_classify_chat_intent_handles_mi_yoksa_comparison() -> None:
    got = classify_chat_intent("thyao mu yoksa eregl mi daha iyi?", known_symbols=KNOWN)
    assert got["intent"] == "comparison"
    assert got["symbols"] == ["THYAO", "EREGL"]


def test_classify_chat_intent_debug_symbol() -> None:
    got = classify_chat_intent("why this score for ASELS", known_symbols=KNOWN)
    assert got["intent"] == "debug_symbol"
    assert got["symbols"] == ["ASELS"]


def test_classify_chat_intent_debug_ranking() -> None:
    got = classify_chat_intent("why this ranking for ASELS AKBNK GARAN", known_symbols=KNOWN)
    assert got["intent"] == "debug_ranking"
    assert got["symbols"] == ["ASELS", "AKBNK", "GARAN"]


def test_classify_chat_intent_debug_comparison() -> None:
    got = classify_chat_intent("compare details AKBNK ile GARAN", known_symbols=KNOWN)
    assert got["intent"] == "debug_comparison"
    assert got["symbols"] == ["AKBNK", "GARAN"]


def test_classify_chat_intent_debug_dataset() -> None:
    got = classify_chat_intent("validate dataset for ASELS", known_symbols=KNOWN)
    assert got["intent"] == "debug_dataset"
    assert got["symbols"] == ["ASELS"]
