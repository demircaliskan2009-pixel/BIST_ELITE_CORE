from pathlib import Path

repo = Path.cwd()
docs = repo / "docs"
docs.mkdir(parents=True, exist_ok=True)

prd_text = """# BIST ONLY ELITE — Full PRD v1

Bu markdown sürümü, DOCX belgesinin repo'ya taşınabilir metin eşdeğeridir.

## 1. Yönetici Özeti

Amaç: BIST-only çalışan, açıklanabilir, bağlam duyarlı, fail-closed ve ileride broker-mediated otomasyona uygun trading system inşa etmek.

Bugünkü durum: İskelet güçlü ve test-sealed. Beyin live-context güvenlik tarafında toparlandı. Ana açık comparison zekâsı, dual-rationale derinliği ve template hissinin azaltılmasıdır.

Bu PRD'nin rolü: scope'u dondurmak, acceptance gate'leri tanımlamak, faz sırasını sabitlemek ve mühendislik kararlarını tek anayasaya bağlamaktır.

North star: Çok sinyal veren bot değil; az ama daha kaliteli, neden-sonuçlu, execution-aware ve ölçülebilir şekilde daha iyi BIST botu.

## 2. Ürün Vizyonu ve Rekabet Üstünlüğü

- BIST-only uzmanlaşma
- Exchange-aware davranış
- Current-price-awareness
- True comparison engine
- Explainable / teaching-grade output
- Fail-closed disiplin
- Outcome-driven monthly improvement

## 3. Mevcut Sistem Durumu ve Parity Resmi

### Tamamlanan iskelet tarafı
- advisor chat runtime / service / adapter / quality / public entrypoint zinciri çalışıyor
- as-of metadata passthrough aktif
- live-context suppression metadata passthrough aktif
- dataclass dynamic attrs passthrough korunuyor
- public / service / runtime katmanları arasında metadata tutarlılığı regression ile korunuyor

### Güçlenen beyin tarafı
- kirli canlı veri ham haliyle kullanıcı metnine sızmıyor
- live_price_out_of_band suppression reason rotalar arasında korunuyor
- as-of fallback açıkça söyleniyor
- single_symbol / scan / market_overview / comparison rotalarında aynı live safety davranışı korunuyor

### Hâlâ açık ana boşluk
- comparison route bazen lider sembol özetine düşüyor
- dual-rationale ve explicit diff anlatımı zayıf
- scan ve market_overview açıklamaları hâlâ fazla şablonsal
- template-answer hissi tam kaybolmuş değil

## 4. Kapsam

Kapsam içi:
- BIST equities odaklı karar motoru
- all equities universe + güçlü exclusion / no-trade filtreleri
- intraday + swing değerlendirme
- al / bekle / izle / kaçın / senaryo iptal
- entry / stop / target / invalidation
- comparison / scan / market_overview / single-symbol analizleri
- live-test-ready manual advice output
- paper + small live için logging ve validation omurgası

Kapsam dışı (şimdilik):
- tam otomatik broker execution
- VIOP / forex / crypto / global markets
- HFT / co-location / sub-second optimizasyon
- kontrolsüz self-modifying live execution

## 5. Veri Katmanı

Mevcut kaynak:
- iDeal desktop ChartData (.G / .01 / .05 / .60)

Gelecek vendor adayı:
- Matriks Analist API, bütçe ve faz uygunsa

Data contracts:
- canonical OHLCV
- symbol master / instrument registry
- session calendar + phase engine
- corporate action handling
- KAP/event placeholder contract
- reproducible snapshots
- data QA gates

## 6. Beyin Katmanı

Karar motoru:
- deterministic decision objects
- entry band + no-chase
- current-price-awareness
- invalidation / stop bağlamı
- multi-timeframe explanation
- comparison engine: true dual-symbol + explicit diff
- scan rationale
- explainability contract

### Immediate next acceptance gate: comparison enrichment
- comparison route her zaman iki sembolün de rationale'ını içermeli
- A > B ve B < A açıkça yazılmalı
- factor/diff scoring görünmeli
- live suppression bozulmamalı
- as-of transparency bozulmamalı
- regression test ile dual-symbol contract kilitlenmeli

## 7. Risk, Gating ve No-Trade

- capital-aware sizing zorunlu
- risk tanımlı değilse trade önerisi verilmemeli
- minimum risk/getiri olmadan öneri üretilmemeli

No-trade:
- live fiyat güvenilmezse / out-of-band ise
- tradeability kısıtı varsa
- session phase aşırı riskliyse
- veri eksikliği / belirsizlik varsa
- stop/invalidation mantıklı kurulamıyorsa

## 8. Faz Planı

- Phase A — Data hardening
- Phase B — Brain parity
- Phase C — Risk & gating
- Phase D — Execution adapter
- Phase E — Paper trading
- Phase F — Small live
- Phase G — Guarded automation

## 9. Araçlar ve Maliyet Disiplini

- ChatGPT 5.4 Thinking — principal architect / PRD guardian / release manager
- Cursor Pro — tek ücretli ana üretici olması önerilir
- Claude Code — sadece büyük refactor / zor debug / bağımsız review gerektiğinde
- GitHub + Actions — source of truth / CI gates / regression seals
- n8n — gelecek fazda orchestrator
- Supabase — gelecek fazda persistent backbone

Maliyet disiplini:
- aynı anda birden çok ücretli coding agent yok
- önce deterministic evaluation, sonra live
- büyük refactor yerine küçük kanıtlanabilir patch
- ek SaaS yalnızca gerçek kaldıraç sağlarsa

## 10. Repo Dokümantasyonu

- docs/PRD.md ana anayasa olacak
- docs/market_rules_bist.md BIST rulebook özeti olacak
- docs/risk_policy.md varsayılan risk yaklaşımını tutacak
- docs/validation_protocol.md acceptance gate ve test bandını kilitleyecek
- docs/release_and_rollback.md release / rollback kurallarını tanımlayacak

## 11. Hemen Sonraki Adımlar

- comparison enrichment
- explicit diff / factor comparison
- regression seal
- live suppression + as-of transparency korunması
- ardından scan ve market_overview rationale ayrıştırması

## 12. Referans Omurgası

- Borsa İstanbul pay piyasası işleyiş ve fiyat marjı kaynakları
- BIST algoritmik işlem / PTRM prosedürleri
- KAP / PDP omurgası
- expectancy / drawdown / slippage / walk-forward validasyon literatürü
- Cursor / Claude / GitHub Actions / n8n resmi dokümantasyonu
"""

validation_text = """# Validation Protocol

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
- .\\tools\\proof_pack.ps1 -Mode comparison
- .\\tools\\brain_smoke_pack.ps1 -Mode comparison_only

Core chat/brain band:
- .\\tools\\brain_smoke_pack.ps1 -Mode core

Live-safety band:
- .\\tools\\proof_pack.ps1 -Mode live

Full baseline:
- .\\tools\\proof_pack.ps1 -Mode baseline

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
"""

release_text = """# Release and Rollback

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
- .\\tools\\proof_pack.ps1 -Mode comparison
- .\\tools\\brain_smoke_pack.ps1 -Mode core
"""

(docs / "PRD.md").write_text(prd_text, encoding="utf-8")
(docs / "validation_protocol.md").write_text(validation_text, encoding="utf-8")
(docs / "release_and_rollback.md").write_text(release_text, encoding="utf-8")

print("docs written:")
for name in ["PRD.md", "validation_protocol.md", "release_and_rollback.md"]:
    p = docs / name
    print(f"- {name} | {p.stat().st_size} bytes")
