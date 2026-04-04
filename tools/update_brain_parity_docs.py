from pathlib import Path
import re

docs = Path("docs")

def update_prd() -> None:
    p = docs / "PRD.md"
    txt = p.read_text(encoding="utf-8")

    txt = txt.replace(
        "- comparison route bazen lider sembol özetine düşüyor\n- dual-rationale ve explicit diff anlatımı zayıf\n- scan ve market_overview açıklamaları hâlâ fazla şablonsal\n- template-answer hissi tam kaybolmuş değil",
        "- comparison route dual-rationale + factor diff ile seal edildi\n- scan ve market_overview reasoning yüzeyi zenginleştirildi\n- single-symbol canlı giriş yüzeyi mevcut contract'larda stabil ve fail-closed\n- chat-facing brain surface, iskelet katmanıyla parity seviyesine geldi"
    )

    txt = re.sub(
        r"## 11\. Hemen Sonraki Adımlar[\s\S]*?## 12\. Referans Omurgası",
        "## 11. Hemen Sonraki Adımlar\n\n- Chat-facing brain surface parity checkpoint'ini resmi proof pack ile sabitle.\n- Live-safety bandını parity zincirine dahil et.\n- Ardından odağı veri hardening, vendor ingest ve execution-risk katmanlarına kaydır.\n\n## 12. Referans Omurgası",
        txt,
        flags=re.MULTILINE,
    )

    if "brain_parity_pack.ps1" not in txt:
        txt += "\n\n## 13. Brain Parity Checkpoint\n\n- `.\\tools\\brain_parity_pack.ps1 -Mode full` chat-facing brain surface parity kontrolü için ana pakettir.\n"

    p.write_text(txt, encoding="utf-8")

def update_validation() -> None:
    p = docs / "validation_protocol.md"
    txt = p.read_text(encoding="utf-8")

    if ".\\tools\\proof_pack.ps1 -Mode scan" not in txt:
        marker = "Comparison band:\n- .\\tools\\proof_pack.ps1 -Mode comparison\n- .\\tools\\brain_smoke_pack.ps1 -Mode comparison_only\n"
        repl = marker + "\nScan/overview band:\n- .\\tools\\proof_pack.ps1 -Mode scan\n"
        txt = txt.replace(marker, repl)

    if ".\\tools\\brain_parity_pack.ps1 -Mode full" not in txt:
        txt += "\n\n## Brain Parity Checkpoint\n- .\\tools\\brain_parity_pack.ps1 -Mode full\n"

    p.write_text(txt, encoding="utf-8")

def update_release() -> None:
    p = docs / "release_and_rollback.md"
    txt = p.read_text(encoding="utf-8")

    txt = re.sub(
        r"## Şu Anki Pratik Release Check[\s\S]*$",
        lambda _:
            "## Şu Anki Pratik Release Check\n"
            "- .\\tools\\proof_pack.ps1 -Mode comparison\n"
            "- .\\tools\\proof_pack.ps1 -Mode scan\n"
            "- .\\tools\\proof_pack.ps1 -Mode live\n"
            "- .\\tools\\brain_smoke_pack.ps1 -Mode core\n"
            "- .\\tools\\brain_parity_pack.ps1 -Mode full\n",
        txt,
        flags=re.MULTILINE,
    )

    p.write_text(txt, encoding="utf-8")

update_prd()
update_validation()
update_release()

print("docs refreshed:")
for name in ["PRD.md", "validation_protocol.md", "release_and_rollback.md"]:
    p = docs / name
    print(f"- {name} | {p.stat().st_size} bytes")
