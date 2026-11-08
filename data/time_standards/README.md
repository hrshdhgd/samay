# Historical time standards

Curated offsets that override tzdata for a region and date range. Entries are added only from
cited primary sources (Gazette notifications, government orders, railway time tables,
contemporary newspapers), never from memory. Research happens in sub-project 2.

One file per country, e.g. `in.yaml`:

```yaml
- country: IN            # ISO 3166 code, as in GeoNames
  admin1: "16"           # optional GeoNames admin1 code (16 = Maharashtra)
  admin2: null           # optional GeoNames admin2 code
  from: 1906-01-01       # inclusive
  to: 1955-10-01         # exclusive
  offset: "+04:51:00"
  name: Bombay Time
  confidence: verified   # verified | probable | low
  source:
    text: "<primary source title>"
    locus: "<page, notification number or clause>"
    verified: true
```

The most specific matching entry wins (admin2 over admin1 over country). Without a match,
tzdata decides.
