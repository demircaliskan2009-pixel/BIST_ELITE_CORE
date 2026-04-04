# Validation Protocol

## Amaç
Her önemli değişiklikte şu sorulara deterministic cevap vermek:
- hangi katman değişti
- hangi test bandı koşuldu
- hangi acceptance gate hedeflendi
- sonuç go mu no-go mu

## Çalışma Kuralı
- sessiz fallback yok
- fail-closed varsayılan
- davranış değişikliği docs + test ile birlikte gelir
- full suite kırmızıysa hedefli yeşil bant belirtilmeden tamam denmez

## Mevcut Öncelikli Acceptance Gate
### Brain Parity — Comparison Enrichment
- comparison route iki sembolü de ayrı rationale ile açıklar
- A > B ve B < A görünür
- factor/diff scoring görünür
- leader-summary'ye çökmez
- live suppression korunur
- as-of transparency korunur

## Hedefli Kanıt Paketleri
Comparison band:
- .\tools\proof_pack.ps1 -Mode comparison
- .\tools\brain_smoke_pack.ps1 -Mode comparison_only

Scan/overview band:
- .\tools\proof_pack.ps1 -Mode scan

Core chat/brain band:
- .\tools\brain_smoke_pack.ps1 -Mode core

Live-safety band:
- .\tools\proof_pack.ps1 -Mode live

Full baseline:
- .\tools\proof_pack.ps1 -Mode baseline

## Go / No-Go
Go:
- hedefli test bandı yeşil
- yeni regression seal mevcut
- istenmeyen route kırılması yok
- live fail-closed davranışı bozulmamış

No-Go:
- hedef acceptance gate eksik
- test bandı kırmızı
- narrative kalite kaybı var
- live suppression veya as-of transparency bozulmuş


## Brain Parity Checkpoint
- .\tools\brain_parity_pack.ps1 -Mode full
