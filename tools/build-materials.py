#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بيبني فهرس الخامات (materials.json) من API الفواتير بتاع أودو.

ليه الملف ده موجود أصلًا:
  الـ endpoint بتاع /api/analytics/invoices بيرجّع سطور فواتير — مش كتالوج
  منتجات — ومفيهوش بحث بالاسم، وكمان مش بيسمح بنداء من المتصفح (CORS).
  فبنسحب الخامات المختلفة مرة واحدة من هنا، ونشحن الناتج مع الصفحة،
  والبحث بيحصل محليًا من غير نت ومن غير ما التوكن ينزل على موبايل حد.

التشغيل:
    set NS_API_KEY=...            (ويندوز)   أو   export NS_API_KEY=...
    python tools/build-materials.py --pages 200 --date-from 2026-01-01

التوكن بييجي من متغيّر البيئة بس — متكتبوش في الملف ده، الريبو عام.
"""
import argparse, json, os, sys, time, urllib.request, urllib.error
from collections import Counter

API = "https://dev11-pcp-nagibselim-v17.odoo.com/api/analytics/invoices"
LIMIT = 500                      # السيرفر بيقصّ أي رقم أكبر من كده

# التصنيفات اللي تهمنا، وكل واحد بيتربط بنوع القماش في أمر التشغيل
TYPES = [
    ("قماش ستائر خفيف",    "light"),
    ("قماش ستارة تعتيم",   "blackout"),
    ("black out",          "blackout"),
    ("قماش تنجيد",         "heavy"),
]
ACC_HINT = "مستلزمات تشغيل ستارة"      # ريل / خشب / نهايات — بتتجمع لوحدها


def classify(cat: str):
    c = (cat or "").lower()
    if ACC_HINT in (cat or ""):
        return "accessory"
    for needle, kind in TYPES:
        if needle.lower() in c:
            return kind
    return None


def fetch(page, token, date_from, retries=3):
    body = json.dumps({"limit": LIMIT, "page": page, "date_from": date_from}).encode()
    req = urllib.request.Request(
        API, data=body,
        headers={"Content-Type": "application/json", "api-key": token})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)["result"]
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=200, help="أقصى عدد صفحات (٥٠٠ سطر للصفحة)")
    ap.add_argument("--date-from", default="2026-01-01")
    ap.add_argument("--out", default="materials.json")
    ap.add_argument("--stop-after", type=int, default=25,
                    help="يقف لو عدّى كذا صفحة من غير أي خامة جديدة")
    a = ap.parse_args()

    token = os.environ.get("NS_API_KEY")
    if not token:
        sys.exit("محتاج متغيّر البيئة NS_API_KEY (التوكن بتاع الـ API).")

    first = fetch(1, token, a.date_from)
    total_pages = first.get("pagination", {}).get("total_pages", 1)
    pages = min(a.pages, total_pages)
    print("إجمالي السطور: %s · صفحات متاحة: %s · هنسحب: %s"
          % (first.get("pagination", {}).get("total_records"), total_pages, pages))

    seen, cats, stale = {}, Counter(), 0
    for p in range(1, pages + 1):
        r = first if p == 1 else fetch(p, token, a.date_from)
        before = len(seen)
        for x in r.get("data", []):
            name = (x.get("product_name") or "").strip()
            cat = x.get("product_category") or ""
            kind = classify(cat)
            if not name or not kind:
                continue
            colour = (x.get("attribute_name") or "").replace("COLOR:", "").strip()
            key = (name, colour, kind)
            if key not in seen:
                seen[key] = {"n": name, "c": colour, "t": kind,
                             "cat": cat.split(" / ")[-1], "id": x.get("product_id")}
                cats[cat] += 1
        stale = stale + 1 if len(seen) == before else 0
        if p % 10 == 0 or p == pages:
            print("  صفحة %-4d · خامات مختلفة: %d" % (p, len(seen)))
        if stale >= a.stop_after:
            print("  وقفنا — %d صفحة من غير أي خامة جديدة." % stale)
            break

    items = sorted(seen.values(), key=lambda v: (v["t"], v["n"], v["c"]))
    out = {"built": time.strftime("%Y-%m-%d"), "source": "odoo analytics/invoices",
           "date_from": a.date_from, "count": len(items), "items": items}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    byt = Counter(v["t"] for v in items)
    print("\nاتكتب %s — %d خامة" % (a.out, len(items)))
    for k, lbl in (("light", "خفيف"), ("heavy", "تقيل"),
                   ("blackout", "بلاك اوت"), ("accessory", "إكسسوار")):
        print("   %-10s %d" % (lbl, byt.get(k, 0)))
    print("   الحجم: %.0f KB" % (os.path.getsize(a.out) / 1024))


if __name__ == "__main__":
    main()
