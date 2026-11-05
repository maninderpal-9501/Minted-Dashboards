#!/usr/bin/env python3
"""Build Minted's Excel files from a Minted tool's JSON, cell for cell like Minted's own templates.

  python3 minted_xlsx.py everyday  po.json        [-o DDED103126.xlsx]   # minted_build_everyday_po
  python3 minted_xlsx.py seasonal  po.json        [-o DDHOL102325.xlsx]  # minted_build_seasonal_po
  python3 minted_xlsx.py tracker   billing.json   [-o rows.xlsx] [--rows new|all|differs|cancelled]  # minted_billing_report

The JSON is the tool's result as returned (the object with "success": true). Totals are written as Excel
formulas, like the templates, so a quantity or price changed in Excel recalculates. If LibreOffice is
installed the file is recalculated once so viewers that don't calculate (previews, some importers) show values.
This mirrors minted-xlsx.js used by the pages; keep the two in step.
Needs: openpyxl.
"""
import argparse, datetime as dt, json, os, shutil, subprocess, sys, tempfile
from openpyxl import Workbook
from openpyxl.styles import Font

PRICES = {"FLAT": 0.30, "FOIL": 0.40, "BOX": 0.82, "BAND": 0.23}   # Minted's "Pricing table" tab
MINTED = ["Minted, LLC", None, "747 Front Street, 2nd floor", "San Francisco, CA 94111", "919-264-6219 | phone", "415.399.1717 | fax"]
ENVELOPES = [("Kraft", "19215W"), ("silver", "19212W"), ("White", 19238)]
USD = '_("$"* #,##0.00_);_("$"* \\(#,##0.00\\);_("$"* "-"??_);_(@_)'
USD4 = '"$"#,##0.0000_);[Red]\\("$"#,##0.0000\\)'
USD3 = '"$"#,##0.000_);[Red]\\("$"#,##0.000\\)'
INT = '_(* #,##0_);_(* \\(#,##0\\);_(* "-"??_);_(@_)'
BOLD = Font(bold=True)


def d(s):
    return dt.datetime.strptime(str(s)[:10], "%Y-%m-%d") if s else None


def num_or_text(u):
    s = str(u or "")
    return int(s) if s.isdigit() and len(s) <= 15 else s


def unit(print_type):
    return PRICES["FOIL"] if "foil" in str(print_type or "").lower() else PRICES["FLAT"]


def put(ws, addr, v, z=None, bold=False):
    if v is None or v == "":
        return
    ws[addr] = v
    if z:
        ws[addr].number_format = z
    if bold:
        ws[addr].font = BOLD


def widths(ws, cols):
    for i, w in enumerate(cols):
        ws.column_dimensions[chr(65 + i) if i < 26 else "A" + chr(65 + i - 26)].width = w


def pricing(wb):
    ws = wb.create_sheet("Pricing table")
    for a, b, v in (("A1", "B1", "FLAT"), ("A2", "B2", "FOIL"), ("A5", "B5", "SHIPPING BOX"), ("A6", "B6", "BELLY BAND")):
        put(ws, a, v)
        put(ws, b, {"FLAT": PRICES["FLAT"], "FOIL": PRICES["FOIL"], "SHIPPING BOX": PRICES["BOX"], "BELLY BAND": PRICES["BAND"]}[v], USD3)
    widths(ws, [16, 10])


def header(ws, h, title, lab, val, cust, dest):
    put(ws, title + "1", "PURCHASE ORDER", bold=True)
    for i, t in enumerate(MINTED):
        put(ws, "A%d" % (3 + i), t)
    put(ws, lab + "5", "Minted P.O. NO.")
    put(ws, val + "5", h.get("po_name"))
    put(ws, lab + "6", "ORDER DATE")
    put(ws, val + "6", d(h.get("order_date")), "mmmm d, yyyy")
    put(ws, cust + "7", "CUSTOMER ID")
    put(ws, val + "7", h.get("customer_id") or "Minted")
    v = h.get("vendor") or {}
    put(ws, "A10", "VENDOR")
    put(ws, "B10", v.get("name")); put(ws, "B11", v.get("address1")); put(ws, "B12", v.get("city_state_zip"))
    put(ws, lab + "10", "Final Destination")
    if isinstance(dest, str):
        put(ws, val + "10", dest)
    elif dest:
        put(ws, val + "10", dest.get("name")); put(ws, val + "11", dest.get("address1")); put(ws, val + "12", dest.get("city_state_zip"))


def everyday(p):
    h, ls = p.get("header") or {}, p.get("lines") or []
    wb = Workbook(); ws = wb.active; ws.title = "MASTER PO"
    last = max(38, 18 + len(ls)); tot = last + 2
    header(ws, h, "E", "E", "F", "D", h.get("final_destination"))
    for a, t in (("A15", "SHIPPING METHOD"), ("D15", "SHIPPING TERMS/FOB "), ("I15", "Ship Date"), ("J15", "DELIVERY DATE")):
        put(ws, a, t, bold=True)
    put(ws, "A16", h.get("shipping_method")); put(ws, "D16", h.get("shipping_terms"))
    put(ws, "I16", "=F6+14", "mm-dd-yy"); put(ws, "J16", "=I16+7", "mm-dd-yy")
    for i, t in enumerate(["SKU #", "UPC", "UPC for C-Box Label", "Description", "Print Type", "Envelope Type", "Foil Color", "Prod qty", "Unit Cost", "Total Cost"]):
        put(ws, chr(65 + i) + "18", t, bold=True)
    cards = 0
    for k, l in enumerate(ls):
        r = 19 + k; cards += l.get("prod_qty") or 0
        put(ws, "A%d" % r, l.get("sku_number")); put(ws, "B%d" % r, num_or_text(l.get("upc")), "0"); put(ws, "C%d" % r, l.get("upc_c_box"))
        put(ws, "D%d" % r, l.get("description")); put(ws, "E%d" % r, l.get("print_type")); put(ws, "F%d" % r, l.get("envelope_type"))
        put(ws, "G%d" % r, l.get("foil_color")); put(ws, "H%d" % r, l.get("prod_qty"))
        put(ws, "I%d" % r, "=VLOOKUP(E%d,'Pricing table'!A:B,2,0)" % r, USD4)
        put(ws, "J%d" % r, "=H%d*I%d" % (r, r), USD)
    put(ws, "H%d" % tot, "=SUM(H19:H%d)" % last, INT, True)
    put(ws, "I%d" % tot, "SUBTOTAL", bold=True); put(ws, "J%d" % tot, "=SUM(J19:J%d)" % last, USD, True)
    put(ws, "I%d" % (tot + 1), "Packaging/materials", bold=True)
    put(ws, "J%d" % (tot + 1), "=('Pricing table'!B5*'Extra Summaries for Order'!F5)", USD, True)
    put(ws, "I%d" % (tot + 2), "TOTAL"); put(ws, "J%d" % (tot + 2), "=SUM(J%d:J%d)" % (tot, tot + 1), USD)
    for m in ("D15:H15", "D16:H16", "F5:G5", "F6:G6", "A15:C15", "A16:C16"):
        ws.merge_cells(m)
    widths(ws, [15, 15, 19, 30, 11, 14, 11, 10, 12, 13])
    es = wb.create_sheet("Extra Summaries for Order")
    put(es, "A1", "Summary for Full Order", bold=True); es.merge_cells("A1:F1")
    for a, t in (("A3", "Envelope type"), ("B3", "Minted Item#"), ("C3", "Prod Qty"), ("E3", "Total # of Distribution locations")):
        put(es, a, t, bold=True)
    put(es, "F3", (p.get("totals") or {}).get("distribution_locations") or 1, bold=True)
    for i, (env, item) in enumerate(ENVELOPES):
        r = 4 + i; put(es, "A%d" % r, env); put(es, "B%d" % r, item)
        put(es, "C%d" % r, "=SUMIF('MASTER PO'!$F$18:$F$%d,'Extra Summaries for Order'!A%d,'MASTER PO'!$H$18:$H$%d)" % (last, r, last), INT)
    put(es, "E5", "Total C-boxes (240 cards / box)", bold=True); put(es, "F5", "='MASTER PO'!H%d/240" % tot, bold=True)
    put(es, "A7", "Total", bold=True); put(es, "C7", "=SUM(C4:C6)", INT, True)
    widths(es, [16, 13, 10, 3, 30, 8])
    pricing(wb)
    sub = sum(round((l.get("prod_qty") or 0) * (l.get("unit_cost") if l.get("unit_cost") is not None else unit(l.get("print_type"))), 2) for l in ls)
    pack = round(cards / 240 * PRICES["BOX"], 2)
    return wb, (h.get("po_name") or "DDED") + ".xlsx", {"cards": cards, "subtotal": round(sub, 2), "packaging": pack, "total": round(sub + pack, 2)}


DIST_COLS = ["PurchaseNumber", "Carrier", "Service", "Fedex Account#", "ShipToName", "ShipToAddr1", "ShipToAddr2", "ShipToCity",
             "ShipToStateOrProvince", "ShipToPostalCode", "ShipToCountryCode", "UPC", "Item Desc", "Qty", "ShipByDate", "DeliverByDate",
             "Print Type", "Envelope Type", "SKU", "Belly Band Count", "SKU Cost", "Belly Band Cost", "Total Line Cost"]


def band(q):
    return 0 if q < 2 else 1 if q < 13 else 2


def col(i):
    return chr(65 + i)


def seasonal(p):
    h, ls, dist = p.get("header") or {}, p.get("master_lines") or [], p.get("distribution") or []
    by_upc = {str(l.get("upc")): l for l in ls}
    wb = Workbook(); ws = wb.active; ws.title = "MASTER PO"
    last = max(39, 18 + len(ls)); tot = last + 2; dend = len(dist) + 1
    header(ws, h, "D", "D", "E", "C", h.get("final_destination") or "See Distribution PO")
    for a, t in (("A15", "SHIPPING METHOD"), ("C15", "SHIPPING TERMS/FOB "), ("H15", "Ship Date"), ("I15", "DELIVERY DATE")):
        put(ws, a, t, bold=True)
    put(ws, "A16", h.get("shipping_method")); put(ws, "C16", h.get("shipping_terms"))
    put(ws, "H16", "=I16-7", "mm-dd-yy"); put(ws, "I16", d(h.get("delivery_date")), "mm-dd-yy")
    for i, t in enumerate(["SKU #", "UPC", "Description", "Print Type", "Envelope Type", "Foil Color", "Prod qty", "Unit Cost", "Total Cost"]):
        put(ws, col(i) + "18", t, bold=True)
    cards = 0; sub = 0.0
    for k, l in enumerate(ls):
        r = 19 + k; cards += l.get("prod_qty") or 0
        sub += round((l.get("prod_qty") or 0) * (l.get("unit_cost") if l.get("unit_cost") is not None else unit(l.get("print_type"))), 2)
        put(ws, "A%d" % r, l.get("sku_number")); put(ws, "B%d" % r, num_or_text(l.get("upc")), "0"); put(ws, "C%d" % r, l.get("description"))
        put(ws, "D%d" % r, l.get("print_type")); put(ws, "E%d" % r, l.get("envelope_type")); put(ws, "F%d" % r, l.get("foil_color"))
        put(ws, "G%d" % r, "=SUMIF('Distribution PO'!$L:$L,'MASTER PO'!B%d,'Distribution PO'!$N:$N)" % r)
        put(ws, "H%d" % r, "=VLOOKUP(D%d,'Pricing table'!A:B,2,0)" % r, USD4)
        put(ws, "I%d" % r, "=G%d*H%d" % (r, r), USD)
    put(ws, "G%d" % tot, "=SUM(G19:G%d)" % last, INT, True)
    put(ws, "H%d" % tot, "SUBTOTAL", bold=True); put(ws, "I%d" % tot, "=SUM(I19:I%d)" % last, USD, True)
    put(ws, "H%d" % (tot + 1), "Packaging/materials", bold=True)
    put(ws, "I%d" % (tot + 1), "=('Pricing table'!B5*'Extra Summaries for Order'!F3)+('Pricing table'!B6*SUM('Distribution PO'!T2:T%d))" % dend, USD, True)
    put(ws, "H%d" % (tot + 2), "TOTAL"); put(ws, "I%d" % (tot + 2), "=SUM(I%d:I%d)" % (tot, tot + 1), USD)
    for m in ("A16:B16", "E6:F6", "C16:D16", "C15:D15", "E5:F5"):
        ws.merge_cells(m)
    widths(ws, [15, 15, 40, 11, 14, 11, 10, 12, 13])
    dw = wb.create_sheet("Distribution PO")
    for i, t in enumerate(DIST_COLS):
        put(dw, col(i) + "1", t, bold=True)
    bands = 0
    for k, x in enumerate(dist):
        r = 2 + k; l = by_upc.get(str(x.get("UPC")), {}); q = int(x.get("Qty") or 0); bands += band(q)
        vals = [x.get("PurchaseNumber"), x.get("Carrier"), x.get("Service"), num_or_text(x.get("FedexAccount")), x.get("ShipToName"),
                x.get("ShipToAddr1"), x.get("ShipToAddr2"), x.get("ShipToCity"), x.get("ShipToStateOrProvince"), None,
                x.get("ShipToCountryCode"), num_or_text(x.get("UPC")), x.get("ItemDesc"), q]
        for i, v in enumerate(vals):
            put(dw, col(i) + str(r), v, "0" if i == 11 else None)
        if x.get("ShipToPostalCode"):
            dw["J%d" % r] = str(x.get("ShipToPostalCode")); dw["J%d" % r].number_format = "@"   # keeps 08012
        put(dw, "Q%d" % r, l.get("print_type")); put(dw, "R%d" % r, l.get("envelope_type")); put(dw, "S%d" % r, l.get("sku_number"))
        put(dw, "T%d" % r, "=IF(N%d<2,0,IF(N%d<13,1,2))" % (r, r))
        put(dw, "V%d" % r, "=T%d*'Pricing table'!$B$6" % r, USD)
        put(dw, "W%d" % r, "=U%d+V%d" % (r, r), USD)
    widths(dw, [14, 8, 9, 13, 10, 26, 12, 16, 8, 10, 8, 14, 40, 6, 11, 12, 10, 12, 14, 9, 9, 10, 11])
    locs = (p.get("summary") or {}).get("locations") or 0
    es = wb.create_sheet("Extra Summaries for Order")
    put(es, "A1", "Summary for Full Order", bold=True); es.merge_cells("A1:F1")
    for a, t in (("A3", "Envelope type"), ("B3", "Minted Item#"), ("C3", "Prod Qty"), ("E3", "Total # of Distribution locations")):
        put(es, a, t, bold=True)
    put(es, "F3", locs, bold=True)
    for i, (env, item) in enumerate(ENVELOPES):
        r = 4 + i; put(es, "A%d" % r, env.lower()); put(es, "B%d" % r, item)
        put(es, "C%d" % r, "=SUMIF('MASTER PO'!$E$19:$E$%d,'Extra Summaries for Order'!A%d,'MASTER PO'!$G$19:$G$%d)" % (last, r, last), INT)
    put(es, "A7", "Total", bold=True); put(es, "C7", "=SUM(C4:C6)", INT, True)
    widths(es, [16, 13, 10, 3, 30, 8])
    pricing(wb)
    pack = round(locs * PRICES["BOX"] + bands * PRICES["BAND"], 2)
    return wb, (h.get("po_name") or "DDHOL") + ".xlsx", {"cards": cards, "subtotal": round(sub, 2), "packaging": pack,
                                                          "total": round(sub + pack, 2), "belly_bands": bands, "locations": locs}


TRACKER = ["", "Partner", "TYPE", "Product", "PO Issued Date", "Expected Ship Date", "PO#", "PO $", "Total Qty", "MBO Order #", "PO Link",
           "Commercial Invoice #", "Sent to Vendor (Y/N)", "Commercial Invoice Prepared (Y/N)", "Packing List Prepared (Y/N)",
           "FCR Approved by Minted", "FCR Number", "FOB Point", "Shipped Date", "Delivered Date", "Shipping Cost", "Tracking #"]
FROM = {"Partner": "Partner", "TYPE": "Type", "Product": "Product", "PO Issued Date": "PO Issued Date", "Expected Ship Date": "Expected Ship Date",
        "PO#": "PO#", "PO $": "PO $", "Total Qty": "Total Qty", "FOB Point": "FOB Point", "Shipped Date": "Shipped Date",
        "Delivered Date": "Delivered Date", "Shipping Cost": "Shipping Cost", "Tracking #": "Tracking #"}
GROUPS = {"B1": "Program", "L1": "Formula", "M1": "For SC - Target Only", "R1": "For SC"}


def pick_rows(p, which):
    rows = p.get("rows") or []
    if which == "all":
        return rows
    def kind(r):   # same buckets as the Billing Check page
        c = r.get("tracker_check")
        if c == "not in tracker":
            return "new"
        if c == "differs":
            return "differs"
        if r.get("Expected Ship Date") == "Cancelled":
            return "cancelled"
        return "matches"
    return [r for r in rows if kind(r) == which]


def tracker(p, which):
    rows = pick_rows(p, which)
    wb = Workbook(); ws = wb.active; ws.title = "PO Tracker"
    for a, t in GROUPS.items():
        put(ws, a, t)
    for i, t in enumerate(TRACKER):
        if t:
            put(ws, col(i) + "2", t, bold=True)
    for k, r in enumerate(rows):
        row = 3 + k
        for i, c in enumerate(TRACKER):
            if not c or c not in FROM:
                continue
            v = r.get(FROM[c]); a = col(i) + str(row)
            if v is None or v == "":
                continue
            if "Date" in c and len(str(v)) >= 10 and str(v)[4] == "-":
                put(ws, a, d(v), "M/d/yyyy")
            elif c in ("PO $", "Shipping Cost") and isinstance(v, (int, float)):
                put(ws, a, v, '"$"#,##0.00')
            elif c == "Total Qty" and isinstance(v, (int, float)):
                put(ws, a, v, "#,##0")
            elif c == "Tracking #":
                put(ws, a, num_or_text(v))
            else:
                put(ws, a, v)
    widths(ws, [3, 10, 10, 14, 13, 13, 15, 10, 9, 11, 9, 12, 9, 11, 11, 11, 10, 12, 12, 12, 11, 15])
    month = ((p.get("period") or {}).get("month")) or "month"
    return wb, "DoorDash PO tracker rows %s%s.xlsx" % (month, "" if which == "all" else " " + which), {"rows": len(rows)}


def recalc(path):
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        try:
            subprocess.run([soffice, "--headless", "--calc", "--convert-to", "xlsx:Calc MS Excel 2007 XML", "--outdir", tmp, path],
                           check=True, capture_output=True, timeout=120)
            out = os.path.join(tmp, os.path.basename(path))
            if os.path.exists(out):
                shutil.copyfile(out, path)
                return True
        except Exception:
            return False
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", choices=["everyday", "seasonal", "tracker"])
    ap.add_argument("json_file")
    ap.add_argument("-o", "--out")
    ap.add_argument("--rows", default="new", choices=["new", "all", "differs", "matches", "cancelled"], help="tracker only (default new)")
    ap.add_argument("--no-recalc", action="store_true")
    a = ap.parse_args()
    p = json.load(open(a.json_file))
    p = p.get("payload", p)
    if not p.get("success", True):
        sys.exit("The tool did not succeed: %s" % p.get("error"))
    wb, name, info = everyday(p) if a.kind == "everyday" else seasonal(p) if a.kind == "seasonal" else tracker(p, a.rows)
    out = a.out or name
    wb.save(out)
    info["recalculated"] = False if a.no_recalc else recalc(out)
    info["file"] = out
    print(json.dumps(info))


if __name__ == "__main__":
    main()
