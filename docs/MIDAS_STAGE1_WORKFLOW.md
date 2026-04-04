# Midas Stage-1 Workflow — Manuel Emir Girişi

Aşama-1 (Stage-1): Robot çıktılarından Midas uygulamasına manuel emir girişi. **Bu aşamada network broker entegrasyonu yok.**

## Günlük Akış

1. **live_today.ps1** — Günün stratejilerini çalıştır, `orders_intent.json` üret
2. **order_ticket_export** — Emir fişi (CSV + TXT) üret
3. **Midas app manuel giriş** — Üretilen fişi Midas’a elle gir
4. **trade_journal update** — İşlem günlüğünü güncelle
5. **weekly pack** — Haftalık özet ve değerlendirme

## order_ticket_export Kullanımı

```powershell
# Varsayılan çıktı: data/out/order_ticket/<DAY>/
python tools/order_ticket_export.py --orders path/to/orders_intent.json

# Özel çıktı dizini
python tools/order_ticket_export.py --orders path/to/orders_intent.json --out data/out/order_ticket/2025-01-15
```

PowerShell wrapper:

```powershell
.\tools\order_ticket_export.ps1 -Orders path/to/orders_intent.json
.\tools\order_ticket_export.ps1 -Orders path/to/orders_intent.json -Out data/out/order_ticket/2025-01-15
```

## Üretilen Dosyalar

| Dosya | Açıklama |
|-------|----------|
| `order_ticket.csv` | Sütunlar: day,symbol,side,qty,order_type,limit_price,notes |
| `order_ticket.txt` | Okunabilir özet, aynı sıralama (symbol, side) |

## Sıralama ve Kurallar

- Actions: `symbol` sonra `side` ile sıralı (deterministik)
- `order_type`: eksikse MARKET; sadece MARKET, LIMIT desteklenir
- `limit_price`: MARKET için boş

## Ağ ve Gizlilik

- Hiçbir network kullanılmaz
- Hiçbir secret (API key, token) yok
- Tüm işlem yerel dosya okuma/yazma
