"""Emit 4 real CFDI invoices via Facturama sandbox API."""
import base64
import json
import sys
import time
import zipfile
from pathlib import Path

import requests

USER = "jmreyesfactura"
PASSWORD = "SRK_facturaapi26!."
BASE_URL = "https://apisandbox.facturama.mx"
CSD_PASS = "12345678a"
DOWNLOADS = Path("/home/ivan/.hermes/projects/facturama-portal/downloads")
DOWNLOADS.mkdir(parents=True, exist_ok=True)

PROJECT = Path("/home/ivan/.hermes/projects/facturama-portal")


def find_csd(rfc_hint, search_dir):
    """Find .cer and .key files in search_dir (recursive)."""
    for cer in search_dir.rglob(f"*{rfc_hint}*.cer"):
        key = cer.with_suffix(".key")
        if key.exists():
            return str(cer), str(key)
    # fallback: any
    for cer in search_dir.rglob("*.cer"):
        key = cer.with_suffix(".key")
        if key.exists():
            return str(cer), str(key)
    return None, None


# ── Download CSDs ──
print("Downloading CSDs...")
zip_path = Path("/tmp/csd-pruebas.zip")
extract_dir = Path("/tmp/csd-pruebas")
extract_dir.mkdir(parents=True, exist_ok=True)
if not zip_path.exists():
    r = requests.get("https://cdnfacturama.azureedge.net/content/csd-pruebas.zip")
    zip_path.write_bytes(r.content)

with zipfile.ZipFile(zip_path) as zf:
    zf.extractall(extract_dir)

# The zip has a nested "csd-pruebas/" folder
moral_dir = extract_dir / "csd-pruebas" / "Personas Morales"
fisica_dir = extract_dir / "csd-pruebas" / "Personas Fisicas"
print(f"Moral CSDs: {moral_dir.exists()}, Fisica CSDs: {fisica_dir.exists()}")


# ── Issuers ──
issuers = [
    {"id": 1, "name": "ESCUELA KEMPER URGATE", "rfc": "EKU9003173C9",
     "zip": "42501", "hint": "IIA040805DZ4", "dir": moral_dir},
    {"id": 2, "name": "HERRERIA Y ELECTRICOS", "rfc": "HE951128469",
     "zip": "06002", "hint": "HE951128469", "dir": moral_dir},
    {"id": 3, "name": "SERVICIOS INTEGRALES DEL GOLFO", "rfc": "SIG951208JK1",
     "zip": "86400", "hint": "URE180429TM6", "dir": moral_dir},
    {"id": 4, "name": "CONSTRUCTORA DEL NORTE SA", "rfc": "CON980415KL2",
     "zip": "64000", "hint": "EWE1709045U0", "dir": moral_dir},
]

# DB
sys.path.insert(0, str(PROJECT))
from src.app import create_app

results = []

for iss in issuers:
    tag = f"{iss['rfc']} ({iss['name']})"
    print(f"\n{'='*55}\n{tag}")

    # ── CSD ──
    cer_path, key_path = find_csd(iss["hint"], iss["dir"])
    if not cer_path:
        print("  SKIP: no CSD found")
        continue

    with open(cer_path, "rb") as f:
        cert_b64 = base64.b64encode(f.read()).decode()
    with open(key_path, "rb") as f:
        key_b64 = base64.b64encode(f.read()).decode()

    csd_payload = {
        "Rfc": iss["rfc"],
        "Certificate": cert_b64,
        "PrivateKey": key_b64,
        "PrivateKeyPassword": CSD_PASS,
    }
    r = requests.post(f"{BASE_URL}/api-lite/csds", auth=(USER, PASSWORD), json=csd_payload)
    if r.status_code in (200, 400):
        print(f"  CSD: OK (status {r.status_code})")
    else:
        print(f"  CSD FAIL: {r.status_code} {r.text[:200]}")
        continue
    time.sleep(0.3)

    # ── DB data ──
    app = create_app()
    with app.app_context():
        db = app.extensions["portal_db"]

        clients = db.list_clients(issuer_id=iss["id"])
        products = db.list_products(issuer_id=iss["id"])
        if not clients or not products:
            print(f"  SKIP: clients={len(clients)} products={len(products)}")
            continue
        client = dict(clients[0])
        product = dict(products[0])

        series_list = db.list_series(iss["id"])
        if not series_list:
            db.create_series(iss["id"], "FAC", 1)
            series_list = db.list_series(iss["id"])
        serie = dict(series_list[0])
        folio = db.get_next_folio(iss["id"], serie["series"])

        qty = 1.0
        unit = float(product["price"])
        subt = round(qty * unit, 2)
        iva = round(subt * 0.16, 2)
        total = round(subt + iva, 2)

        payload = {
            "NameId": "1", "CfdiType": "I",
            "ExpeditionPlace": iss["zip"],
            "PaymentForm": "03", "PaymentMethod": "PUE", "Currency": "MXN",
            "Serie": serie["series"], "Folio": str(folio),
            "Issuer": {"Rfc": iss["rfc"], "Name": iss["name"], "FiscalRegime": "601"},
            "Receiver": {"Rfc": client["rfc"], "Name": client["legal_name"],
                         "CfdiUse": client["cfdi_use"], "FiscalRegime": client["tax_regime"],
                         "TaxZipCode": client["zip_code"]},
            "Items": [{
                "ProductCode": product["product_code"],
                "IdentificationNumber": product["identification_number"],
                "Description": product["name"],
                "Unit": product["unit"], "UnitCode": product["unit_code"],
                "UnitPrice": unit, "Quantity": qty,
                "Subtotal": subt, "TaxObject": product["tax_object"],
                "Taxes": [{"Name": "IVA", "Rate": 0.16, "Total": iva, "Base": subt, "IsRetention": False}],
                "Total": total,
            }],
            "Subtotal": subt, "Total": total,
        }

        print(f"  Emitting {serie['series']}-{folio} to {client['legal_name']} (${total:.2f})...")
        r = requests.post(f"{BASE_URL}/api-lite/3/cfdis", auth=(USER, PASSWORD), json=payload)

        if r.status_code not in (200, 201):
            print(f"  EMIT FAIL: {r.status_code}")
            print(f"  {r.text[:400]}")
            continue

        cfdi = r.json()
        fid = cfdi.get("Id", "")
        uuid_val = ""
        comp = cfdi.get("Complement", {})
        if isinstance(comp, dict) and comp.get("TaxStamp"):
            uuid_val = comp["TaxStamp"].get("Uuid", "")

        print(f"  OK! id={fid} uuid={uuid_val[:36] if uuid_val else '?'}")

        # Save to DB
        db.save_cfdi({
            "facturama_id": fid, "uuid": uuid_val,
            "issuer_id": iss["id"], "client_id": client["id"],
            "recipient_rfc": client["rfc"], "recipient_name": client["legal_name"],
            "total": total, "status": "active", "cfdi_type": "I",
            "payment_form": "03", "payment_method": "PUE",
            "serie": serie["series"], "folio": folio,
            "items": [{
                "product_id": product["id"], "issuer_id": iss["id"],
                "client_id": client["id"], "name": product["name"],
                "description": product["name"],
                "product_code": product["product_code"],
                "identification_number": product["identification_number"],
                "quantity": qty, "unit_price": unit, "subtotal": subt, "total": total,
            }],
            "raw_payload": {"request": payload, "response": cfdi},
        })

        # Download XML + PDF
        for fmt in ("xml", "pdf"):
            r2 = requests.get(f"{BASE_URL}/cfdi/{fmt}/issuedLite/{fid}", auth=(USER, PASSWORD))
            if r2.status_code == 200:
                data = r2.json()
                content = base64.urlsafe_b64decode(data["Content"].encode())
                fpath = DOWNLOADS / f"{fid}.{fmt}"
                fpath.write_bytes(content)
                print(f"  {fmt.upper()}: {len(content)} bytes")
            else:
                print(f"  {fmt.upper()} FAIL: {r2.status_code}")

        results.append({
            "issuer": iss["name"], "client": client["legal_name"],
            "facturama_id": fid, "uuid": uuid_val,
            "serie_folio": f"{serie['series']}-{folio}", "total": total,
        })
        time.sleep(0.3)


# ── Summary ──
print(f"\n{'='*60}")
print(f"DONE: {len(results)}/{len(issuers)} emitted and timbrados")
for r in results:
    print(f"  {r['issuer']} → {r['client']}")
    print(f"    {r['serie_folio']}  ${r['total']:.2f}  id={r['facturama_id']}")
    print(f"    uuid={r['uuid'][:36]}")
