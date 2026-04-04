# Release and Rollback

## Release Kuralı
Bir değişiklik release-ready sayılabilmesi için:
- hedeflenen acceptance gate tanımlı olmalı
- ilgili regression seal eklenmiş olmalı
- hedefli test bandı yeşil olmalı
- diff anlaşılır ve küçük olmalı
- no silent fallback korunmalı

## Küçük Patch Politikası
- tek patch = tek açık problem
- bir patch birden fazla fazı aynı anda hedeflemez
- test ve docs aynı turda güncellenir
- büyük refactor yerine küçük doğrulanabilir patch tercih edilir

## Rollback Tetikleyicileri
- hedefli test bandı kırmızıya dönerse
- comparison route tekrar leader-summary'ye çökerse
- live suppression reason kaybolursa
- as-of note beklenen route'ta kaybolursa
- public / service / runtime parity bozulursa

## Rollback Mantığı
- son güvenli commit/tag'e dön
- hedefli smoke pack'i tekrar çalıştır
- kırılan contract'i yazılı tanımla
- aynı oturumda geniş refactor başlatma

## Şu Anki Pratik Release Check
- .\tools\proof_pack.ps1 -Mode comparison
- .\tools\proof_pack.ps1 -Mode scan
- .\tools\proof_pack.ps1 -Mode live
- .\tools\brain_smoke_pack.ps1 -Mode core
- .\tools\brain_parity_pack.ps1 -Mode full
