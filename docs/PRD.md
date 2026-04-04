# BIST ONLY ELITE — Full PRD v1

Bu markdown sürümü, DOCX belgesinin repo'ya taşınabilir metin eşdeğeridir.

BIST ONLY ELITE
Tam Kapsamlı PRD v1
BIST-only, live-test-ready, explainable ve ileride broker-mediated otomasyona uygun trading system için ürün gereksinimleri dokümanı
Hazırlanma bağlamı: mevcut handoff promptu, canlı durum özeti ve live-test-ready roadmap omurgası temel alınmıştır.
1. Yönetici Özeti
Amaç: BIST-only çalışan, açıklanabilir, bağlam duyarlı, fail-closed ve ileride broker-mediated otomasyona uygun trading system inşa etmek.
Bugünkü durum: İskelet artık güçlü ve test-sealed. Beyin özellikle live-context güvenlik tarafında toparlandı. En büyük açık comparison zekâsı.
Bu PRD'nin rolü: Scope'u dondurmak, acceptance gate'leri tanımlamak, faz sırasını sabitlemek ve mühendislik kararlarını tek anayasaya bağlamak.
North star: Rakiplerden daha çok sinyal veren bot değil; az ama daha kaliteli, neden-sonuçlu, execution-aware ve ölçülebilir şekilde daha iyi BIST botu.
Mevcut olgunluk resmi
2. Ürün Vizyonu ve Rekabet Üstünlüğü
Ürün vizyonu
BIST-only çalışan, tüm BIST hisse evrenini bağlama göre tarayan, seçici, öğretici, explainable ve zamanla outcome'larla daha iyi hale gelen bir investment intelligence system inşa edilecektir.
Rakiplerden ayrışma sütunları
BIST-only uzmanlaşma — genel amaçlı değil, Borsa İstanbul mikro yapısı ve kural setiyle tasarlanmış sistem.
Exchange-aware davranış — seans yapısı, fiyat limitleri, devre kesici ve VBTS/VBMS benzeri kısıt rejimlerini karar ve no-trade katmanına işlemek.
Current-price-awareness — sadece yön değil, şu an giriş kaçtı mı, fiyat hâlâ uygun mu, beklemek daha mı doğru sorularına cevap.
True comparison engine — A vs B kıyasını tek-hisse özetine düşürmeden dual-rationale ile yapmak.
Explainable / teaching-grade output — neden bu hisse, neden şimdi, neden değil, hangi koşulda iptal olur sorularını öğretici şekilde açıklamak.
Fail-closed disiplin — belirsizlikte trade zorlamamak, sessiz fallback kullanmamak.
Outcome-driven monthly improvement — hata sınıflarını ve sürüm performansını izleyerek aylık iyileştirme döngüsü.
North-star ürün hedefi
Bu ürünün amacı çok sinyal üretmek değil; az ama yüksek kaliteli, neden-sonuçlu, risk sonrası da ayakta kalan ve BIST'te rakiplerinden ölçülebilir şekilde daha iyi karar üreten bir bot olmaktır.
3. Mevcut Sistem Durumu ve Parity Resmi
Tamamlanan iskelet tarafı
advisor chat runtime / service / adapter / quality / public entrypoint zinciri çalışıyor.
as-of metadata passthrough aktif.
live-context suppression metadata passthrough aktif.
dataclass dynamic attrs passthrough korunuyor.
public / service / runtime katmanları arasında metadata tutarlılığı regression ile korunuyor.
Güçlenen beyin tarafı
Kirli canlı veri ham haliyle kullanıcı metnine sızmıyor.
live_price_out_of_band suppression reason rotalar arasında korunuyor.
as-of fallback açıkça söyleniyor.
single_symbol / scan / market_overview / comparison rotalarında aynı live safety davranışı korunuyor.
Hâlâ açık ana boşluk
Comparison route bazen lider sembolün tek-hisse özetine düşüyor.
Dual-rationale ve explicit diff anlatımı zayıf.
Scan ve market_overview açıklamaları hâlâ fazla şablonsal.
Template-answer hissi tam kaybolmuş değil.
4. Kapsam / Kapsam Dışı
Kapsam içi
BIST pay piyasası (equities) odaklı karar motoru.
All equities universe, fakat güçlü exclusion / no-trade filtreleri ile.
Intraday + swing bakış açılarını aynı sistem içinde taşıyan multi-timeframe değerlendirme.
Signal/advice layer: al / bekle / izle / kaçın / senaryo iptal.
Entry / stop / target / invalidation üretimi.
Comparison, scan, market_overview ve single-symbol analizleri.
Manual broker uygulaması için live-test-ready advice output.
Paper trading ve small live aşamasına uygun logging ve validation omurgası.
Kapsam dışı (şimdilik)
Tam otomatik broker execution'ın bugünkü fazda üretim devreye alınması.
VIOP, forex, crypto veya global marketler.
HFT / co-location / sub-second execution optimizasyonu.
Kontrolsüz self-modifying live execution.
Yasal veya kurumsal erişim gerektiren altyapıyı bugünkü fazda zorlamak.
5. Kullanıcılar ve Kullanım Senaryoları
Ana kullanıcılar
Birincil operatör: sistemi yöneten ve manuel/paper/live geçiş kararlarını veren kullanıcı.
İkincil kullanıcılar: aile içi kullanım / soru-cevap / tavsiye tüketimi.
Gelecekte: dashboard üzerinden sinyal ve karar geçmişine bakan kullanıcılar.
Temel kullanım senaryoları
6. Pazar, Evren, Timeframe ve Tarama Politikası
Evren ve timeframe
Universe = all BIST equities.
Primary style = both: intraday + swing.
Desteklenen timeframe ailesi = 1m, 5m, 15m, 60m, günlük, haftalık.
Karar mantığı = multi-timeframe confluence; tek timeframe'e kör bağlı olunmayacak.
Dominant timeframe + confirming timeframe mantığı zamanla decision object içinde açıkça taşınmalı.
Exclusion / no-trade varsayılanları
Aşırı düşük likidite / işlem derinliği yetersiz hisseler.
Anormal spread / execution kalitesi zayıf hisseler.
VBTS / gross settlement / emir türü kısıtı nedeniyle tradeability bozulan hisseler.
Devre kesici veya fiyat limitine aşırı yakınlık.
Veri kalitesi bozuk, timestamp anomalili veya corporate action ayarı belirsiz enstrümanlar.
Belirsizlik durumunda sessiz fallback yerine NO TRADE.
7. Veri Katmanı (Data Layer) Gereksinimleri
Mevcut kaynaklar ve yön
Şimdiki kaynak — iDeal desktop ChartData dosyaları (.G / .01 / .05 / .60).
Gelecek vendor adayı — Matriks Analist API (REST bar + MQTT market + meta services), bütçe ve faz uygunsa.
Amaç — her vendor'u normalize OHLCV + metadata + session-aware tek kontrata çevirmek.
Data contracts
Canonical OHLCV şeması.
Symbol master / instrument registry.
Session calendar + phase engine.
Corporate action handling plan (adjusted/unadjusted ayrımı).
KAP/event placeholder contract.
Versioned reproducible snapshots.
Data QA gates: missing bars, malformed vendor file, timestamp drift, symbol ambiguity.
Data layer Definition of Done
Aynı input aynı normalized output üretir.
Snapshot üretimi tekrar edilebilir.
Regression testleri yeşil.
Backtest, paper ve live öneri katmanı aynı veri kontratını paylaşır.
8. Beyin Katmanı (Decision / Reasoning Layer)
Karar motorunun üretmesi gereken ana yetenekler
Deterministic decision objects: ENTER / AVOID / HOLD / EXIT / WATCH.
Entry band ve no-chase mantığı.
Current-price-awareness: fiyat uygun mu, giriş kaçtı mı, geri çekilme beklenmeli mi.
Invalidation ve stop mantığının bağlamla ilişkisi.
Multi-timeframe explanation: dominant + confirming timeframe.
Comparison engine: true dual-symbol, explicit diff, leader-summary'e düşmeyen kıyas.
Scan rationale: liderin neden önde olduğu ve diğerlerinin neden geride kaldığı.
Explainability contract: why now / why not / what invalidates / what changes the view.
Immediate next acceptance gate: comparison enrichment
Comparison route her zaman iki sembolün de rationale'ını içermeli.
A > B ve B < A açıkça yazılmalı.
En az kaba ama açık bir factor/diff scoring tablosu bulunmalı.
Live suppression ve as-of transparency davranışı bozulmamalı.
Regression test ile dual-symbol contract kilitlenmeli.
Brain parity için ek acceptance gate'ler
Scan ve market_overview çıktılarını lider özeti olmaktan çıkarma.
Template-answer hissini belirgin azaltma.
No silent fallback rate = 0.
Explainability completeness testi.
Route-specific narrative quality testi.
9. Risk, Gating ve No-Trade Politikası
Risk yaklaşımı
Kullanıcı işlemi başlatmadan önce risk profili sorulabilir; ancak PRD varsayılan sistem risk çerçevesi de tanımlamalıdır. Kullanıcı profili sonradan runtime override olarak uygulanabilir.
Capital-aware sizing zorunlu olmalı.
Maksimum günlük zarar, işlem başına risk, maksimum açık pozisyon sayısı runtime profilinden alınmalı.
Risk tanımlı değilse trade önerisi verilmemeli.
Minimum risk/getiri eşiği olmadan trade önerisi üretilmemeli.
No-trade kuralları
Live fiyat güvenilmezse veya out-of-band ise.
Tradeability kısıtı varsa (VBTS/VBMS/gross settlement vb.).
Session phase execution açısından aşırı riskliyse.
Belirsizlik veya veri eksikliği varsa.
Stop/invalidation mantıklı şekilde kurulamadıysa.
10. Execution Yol Haritası
Execution bir anda değil, aşamalı açılacaktır.
11. Validasyon ve Ölçüm Çerçevesi
Ana validasyon zinciri
Data QA
Deterministic contract tests
Backtest (cost/slippage dahil)
Walk-forward / out-of-sample
Shadow / paper trading
Small live
Guarded automation
Ana metrikler
Expectancy after costs/slippage
Max drawdown ve recovery behavior
Profit factor / avg R
Regime robustness
Execution quality
Reliability / auditability
İkincil aspirational metrik
A-grade trade'lerde yüksek precision ve uygun rejimde %85 civarı hit quality. Bu hedef, expectancy ve tail risk pahasına optimize edilmeyecektir.
12. Faz Planı, Go/No-Go ve Definition of Done
Phase A — Data hardening
İş paketi — Parser, normalize OHLCV, symbol master, session engine, QA gates, reproducible snapshots.
Go/No-Go — Data contract seal, clean snapshots, deterministic ingest.
Phase B — Brain parity
İş paketi — Comparison enrichment, scan/overview rationale ayrıştırma, current-price-awareness ve explanation contract.
Go/No-Go — Corporate-grade reasoning outputs + acceptance gates.
Phase C — Risk & gating
İş paketi — Risk profile contract, tradability gates, ambiguity=no-trade, kill switch.
Go/No-Go — Fail-closed risk engine.
Phase D — Execution adapter
İş paketi — Paper simulator, order state machine, costs/slippage, reconciliation.
Go/No-Go — Execution-capable but guarded engine.
Phase E — Paper trading
İş paketi — Daily simulated decisions, weekly scorecards, error taxonomy.
Go/No-Go — Stable paper performance.
Phase F — Small live
İş paketi — Micro-size, manual approval first, rollback readiness.
Go/No-Go — Controlled real-world validation.
Phase G — Guarded automation
İş paketi — Broker-mediated partial/full automation with hard kill-switches.
Go/No-Go — Only after paper + small live stability.
13. Araçlar, Agent Rol Dağılımı ve Maliyet Disiplini
Önerilen araç politikası
ChatGPT 5.4 Thinking — principal architect, quant PM, PRD guardian, release manager.
Cursor Pro — tek ücretli ana üretici olması önerilir; repo içi agentic coding için birincil araç.
Claude Code — şimdilik opsiyonel; sadece büyük refactor / zor debug / bağımsız review gerektiğinde.
GitHub + Actions — source of truth, CI gates, regression seals.
n8n — gelecek fazda orchestrator; beyin değil süreç yöneticisi.
Supabase — gelecek fazda persistent backbone / auth / dashboard backend.
Blackbox AI — ancak ücretsiz yardımcı gerektiğinde, ikincil ve opsiyonel.
Maliyet disiplini
Aynı anda birden çok ücretli AI coding agent alınmayacak.
Önce paper ve deterministic evaluation; erken live ile maliyet çıkarma mantığı yok.
Büyük refactor yerine küçük, kanıtlanabilir patch'ler tercih edilecek.
Ek SaaS araçları ancak gerçek operasyonel kaldıraç sağlarsa devreye girecek.
14. Repo Dokümantasyonu ve Operasyon Kuralları
docs/PRD.md ana anayasa olacak.
docs/market_rules_bist.md BIST rulebook özeti olacak.
docs/risk_policy.md varsayılan risk yaklaşımını tutacak.
docs/validation_protocol.md hangi test / metrik / acceptance gate ile ilerlediğimizi kilitleyecek.
docs/release_and_rollback.md geri alma ve release koşullarını tanımlayacak.
Önemli davranış değişiklikleri docs ve test ile birlikte gelecek.
15. Hemen Sonraki Adımlar
Şimdiki tek öncelik drift etmeden comparison enrichment'tir.
Comparison route'u dual-rationale üreten hale getir.
Explicit diff / factor comparison ekle.
Regression test ile contract kilitle.
Live suppression + as-of transparency davranışını bozma.
Ardından scan ve market_overview rationale ayrıştırmasına geç.
Bunlar kapandıktan sonra repo içi PRD/docs dosyalarını resmileştir.
16. Referans Omurgası
Bu PRD'nin profesyonel çerçevesi şu kaynak sınıflarına dayandırılmıştır:
Borsa İstanbul Pay Piyasası işleyiş, fiyat marjı ve circuit breaker kaynakları.
BIST algoritmik işlem ve PTRM prosedürleri (müşterinin doğrudan borsaya emir iletemeyeceği broker-mediated yaklaşım).
KAP / PDP kamuya açıklama omurgası.
Expectancy, drawdown, cost/slippage ve walk-forward validasyon literatürü.
Cursor, Claude, GitHub Actions ve n8n resmi dokümantasyonu.
Not: PRD'deki hedef ve kabul kriterleri, botu sadece çalışan değil ölçülebilir şekilde güçlü ve güvenilir hale getirmek için yazılmıştır.
Bu doküman repo içi docs/PRD.md üretimi için ana taslak olarak kullanılmalıdır.