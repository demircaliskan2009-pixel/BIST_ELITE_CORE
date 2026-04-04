# PRDV3 — Dürüst Durum Raporu / Honest Status

**Authority:** `docs/PRDV3_FINAL_GOD_ARCHITECTURE.md`  
**Amaç:** “Proof-pass” ile “ürün tamamlandı” iddiasını ayırmak.

---

## 1) Özet karar (Summary)

| İfade | Geçerli mi? |
|--------|-------------|
| “Core engine iyi durumda; execution/portfolio tarafında gerçek düzeltmeler yapıldı” | **Evet** (kod tabanına özgü; testlerle desteklenen kısımlar) |
| `tools/prdv3_final_acceptance.py` çıkışı = **PRDV3 ürün tamamlanması** | **Hayır** — tek başına E2E bütünlük kapısıdır; **os.environ içinde proof-only gevşetme yapmaz** (operatör env’i ne ise odur). |
| **PRDV3 gerçek ürün tamamlanması** | **Hayır** — aşağıdaki bloklar eksik veya kısmi. |

**Doğru ifade:** *E2E acceptance geçse bile PRDV3 product completion tek başına kanıtlanmış sayılmaz; `docs/PRDV3_HONEST_STATUS.md` §4 blokları hâlâ geçerli.*

---

## 2) Production vs proof-only (ayırim)

### Production / gerçek koşullar

- `live_runner` ve ilgili modüller **shell’den** veya operatör **bilinçli** env ile çalışır.
- `RealisticExecutionEngine` varsayılanları: `depth_per_unit`, `min_fill_ratio`, liquidity floor, border miss vb. **gevşetilmeden** (env ile override edilmedikçe).
- `build_portfolio_payload` eşikleri: `BIST_PORTFOLIO_MIN_CONF`, `BIST_PORTFOLIO_MIN_POSITION_FRAC` vb. **operatör/policy** değerleri.

### E2E acceptance (`tools/prdv3_final_acceptance.py`)

- Script **process env’ini değiştirmez** (BIST_REALISM_*, portfolio floor vb. **yok** — önceki proof-only injection kaldırıldı).
- `BIST_IDEAL_DATA_PATH` zorunlu; `BIST_LIVE_MAX_CYCLES`, sembol listesi vb. **shell’de** tanımlanır — ürün varsayılanları veya operatör politikası geçerlidir.
- `BIST_PRDV3_ACCEPTANCE_TIMEOUT_SEC` yalnızca subprocess süre sınırı (CI/operasyon); ürün eşiklerini değiştirmez.

---

## 3) Kodda yapılan gerçek düzeltmeler (false completion değil)

- **`PaperExecution`**: `size_fraction` ile `max_symbol_fraction` çakışmasında **headroom clamp** — risk tavanına uyum (ürün mantığı).
- **`MarketRealismMetrics.summary()`**: `fill_attempts`, `fills_ok` — gözlemlenebilirlik; `fills_ok + missed_trades == fill_attempts` tutarlılığı kabul scriptinde doğrulanır.
- **`live_runner`**: adaptive kapalıyken `SYSTEM_STATUS_REPORT` için `confidence_variance` / `action_diversity` yedekleri; `incomplete_cycles` vs. kısa koşu hataları.
- **`RealisticExecutionEngine`**: depth/liquidity için **documented** env override (operatör tuning; proof ile karıştırılmamalı).

---

## 4) PRDV3 ürün tamamlanması için bloklayıcı / eksik bloklar

Aşağıdakiler **PRDV3_FINAL_GOD_ARCHITECTURE.md** ile tam hizalanmış “ürün bitti” iddiası için **hâlâ eksik veya kısmi** sayılır:

1. **Risk state machine (§19):** `OperationalRiskFSM` + `RISK_METRICS` alanları var; **tam** broker-uyumlu FSM + tüm geçiş audit tablosu **kısmi** kalır.
2. **Learning / edge promotion (§9, §16):** Walk-forward + promotion gate’in **operasyonel** ve **tekrarlanabilir** tek pipeline’da birleşmesi; “proof-only threshold” ile karışmaması.
3. **Data hierarchy tam kanıt (§6):** `.G` / `.05` / Matriks / CSV sırasında her kademe için **fail-closed** saha doğrulaması ve tek rapor.
4. **Gerçek market stresi altında acceptance:** Harness gevşetmesi **olmadan** uzun koşu, yüksek sembol sayısı, üretim env.
5. **Broker / order lifecycle (§14):** Kağıt yolunda bile CREATED→…→CLOSED izlenebilirliği ve ürün iddiasıyla uyumlu minimal FSM.
6. **Audit / governance (§23):** Tek tip JSONL / olay şeması ile “her önemli aksiyon” kapsamı.
7. **BIST-özgü operasyon (§20):** Seans, taban/tavan, askı vb. için modül testleri + saha örnekleri (kısmi olanlar tamamlanmalı).
8. **UX (§17.3):** Türkçe birincil kullanıcı katmanı (ürün kararı).

---

## 5) Ne zaman “PRDV3 product completion” denebilir?

- Proof harness geçti diye değil;
- Üstteki bloklar **kod + test + operasyonel kanıt** ile kapatıldığında;
- Acceptance script’i artık env’i gevşetmediği için, **anlamlı** geçiş = doğru `BIST_IDEAL_DATA_PATH` + kasıtlı ürün/operatör env ile E2E başarı + üstteki maddelerin kodla kapanması.

---

*Bu dosya “false completion” önlemek için bilinçli olarak tutulur; PRDV2/PRDV3 fail-closed ruhuna uygundur.*
