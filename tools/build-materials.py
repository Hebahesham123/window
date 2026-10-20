#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بيبني فهرس الخامات والإكسوار (materials.json) من API قائمة أسعار أودو.

المصدر: /api/pricelist/templates  و  /api/pricelist/variants
قائمة الأسعار «استهلاكي» (id 86). كل منتج بيجي بكوده الحقيقي
(default_code — نفس الكود اللي في أمر التشغيل الورقي) وسعره وألوانه.

ليه الفهرس مشحون مع الصفحة بدل ما المتصفح ينده الـ API:
  الـ API مابيبعتش ترويسة Access-Control-Allow-Origin، يعني المتصفح
  هيمنع النداء من الموقع. وكمان التوكن مينفعش ينزل على موبايل البايعين
  والريبو عام. فبنسحب مرة واحدة من على الجهاز والبحث بيشتغل محليًا.

التشغيل:
    set NS_API_KEY=...              (ويندوز)   أو   export NS_API_KEY=...
    python tools/build-materials.py

التوكن بييجي من متغيّر البيئة بس — متكتبوش هنا، الريبو عام.
"""
import argparse, json, os, sys, time, urllib.parse, urllib.request
from collections import Counter

BASE = "https://dev11-pcp-nagibselim-v17.odoo.com"
PAGE = 500                         # السيرفر بيقصّ أي رقم أكبر

# التصنيف → نوع القماش في أمر التشغيل
def kind_of(cat: str):
    c = cat or ""
    if "قماش ستائر خفيف" in c:            return "light"
    if "قماش ستارة تعتيم" in c or "black out" in c.lower(): return "blackout"
    if "قماش تنجيد" in c:                 return "heavy"
    if "ستارة جاهزة" in c:                return "ready"
    if ("مستلزمات تشغيل ستارة" in c or "اكسسوارات" in c
            or "رول اب" in c or "خامات ستارة" in c):      return "acc"
    return None

# آخر جزء في مسار التصنيف → بند الإكسوار في الجدول
BUCKET = {
    "خشب": "wood", "ريل": "rail", "كابولى": "kabRail", "كابولي": "kabRail",
    "شماعة": "shammaa", "ماسورة": "masoura", "نهايات": "nehaya",
    "فرانشة": "fransha", "بلتكانة": "baltakana", "بوردر": "border",
    "مرابط": "marabet", "رول اب": "rollup", "اكسسوار مستورد": "imported",
}
def bucket_of(cat: str):
    for part in reversed([p.strip() for p in (cat or "").split("/")]):
        if part in BUCKET:
            return BUCKET[part]
    return "other"


def api(path, token, **q):
    url = BASE + path + ("?" + urllib.parse.urlencode(q) if q else "")
    req = urllib.request.Request(url, headers={"API-Key": token})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="materials.json")
    ap.add_argument("--no-variants", action="store_true",
                    help="يتخطى سحب الألوان (أسرع بس من غير كود لون)")
    a = ap.parse_args()

    token = os.environ.get("NS_API_KEY")
    if not token:
        sys.exit("محتاج متغيّر البيئة NS_API_KEY (توكن الـ API).")

    # ١) كل المنتجات
    tpl, page = [], 1
    while True:
        r = api("/api/pricelist/templates", token, page=page, limit=PAGE)
        if r.get("status") != "success":
            sys.exit("الـ API ردّ: " + json.dumps(r, ensure_ascii=False)[:200])
        d = r.get("data", [])
        tpl += d
        tot = r["pagination"]["total_records"]
        print("  صفحة %-3d — %d/%d" % (page, len(tpl), tot))
        if len(d) < PAGE or len(tpl) >= tot:
            break
        page += 1

    # ٢) اللي يخصنا بس
    keep = []
    for t in tpl:
        k = kind_of(t.get("product_category"))
        if not k:
            continue
        t["_k"] = k
        if k == "acc":
            t["_b"] = bucket_of(t.get("product_category"))
        keep.append(t)
    print("\nمنتجات تخص الستائر: %d من %d" % (len(keep), len(tpl)))

    # ٣) الألوان للمنتجات اللي ليها أكتر من واحد
    items, multi = [], [t for t in keep if (t.get("variant_count") or 1) > 1]
    if not a.no_variants:
        print("سحب الألوان لـ %d منتج…" % len(multi))
    for i, t in enumerate(keep):
        base = {"n": (t.get("template_name") or "").strip(),
                "code": t.get("default_code") or "",
                "t": t["_k"], "cat": (t.get("product_category") or "").split(" / ")[-1],
                "p": round(float(t.get("price") or 0), 2),
                "u": t.get("uom") or ""}
        if t["_k"] == "acc":
            base["b"] = t["_b"]
        n_var = t.get("variant_count") or 1
        if a.no_variants or n_var <= 1:
            items.append(base)
            continue
        try:
            v = api("/api/pricelist/variants", token, template_id=t["template_id"])
            rows = v.get("data") or []
        except Exception:
            rows = []
        if not rows:
            items.append(base)
            continue
        for x in rows:
            it = dict(base)
            it["c"] = (x.get("attribute_name") or "").strip()
            if x.get("default_code"):
                it["code"] = x["default_code"]
            if x.get("price"):
                it["p"] = round(float(x["price"]), 2)
            items.append(it)
        if (i + 1) % 40 == 0:
            print("    … %d/%d" % (i + 1, len(keep)))

    # نجمّع الألوان تحت المنتج الواحد — بيصغّر الملف لحوالي الخُمس
    g = {}
    for x in items:
        k = (x["n"], x["code"], x["t"], x.get("b", ""))
        e = g.setdefault(k, {"n": x["n"].strip(), "code": x["code"], "t": x["t"],
                             "cat": x.get("cat", ""), "p": int(round(x.get("p") or 0)),
                             "cols": []})
        c = (x.get("c") or "").strip()
        if c and c not in e["cols"]:
            e["cols"].append(c)
        if x.get("b"):
            e["b"] = x["b"]
    grouped = sorted(g.values(), key=lambda v: (v["t"], v.get("b", ""), v["n"]))
    out = {"built": time.strftime("%Y-%m-%d"), "source": "odoo pricelist 86 (استهلاكي)",
           "groups": len(grouped), "variants": len(items), "items": grouped}
    items = grouped
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    by = Counter(v["t"] for v in items)
    print("\nاتكتب %s — %d صنف" % (a.out, len(items)))
    for k, lbl in (("light", "خفيف"), ("heavy", "تقيل"), ("blackout", "بلاك اوت"),
                   ("ready", "ستارة جاهزة"), ("acc", "إكسوار")):
        if by.get(k):
            print("   %-12s %d" % (lbl, by[k]))
    bb = Counter(v.get("b") for v in items if v["t"] == "acc")
    if bb:
        print("   بنود الإكسوار: " + " · ".join("%s %d" % (k, v) for k, v in bb.most_common()))
    print("   الحجم: %.0f KB" % (os.path.getsize(a.out) / 1024))


if __name__ == "__main__":
    main()
