import base64, sys, time
from pathlib import Path
import requests

USER = 'jmreyesfactura'
PASSWORD = 'SRK_facturaapi26!.'
BASE = 'https://apisandbox.facturama.mx'
CSD_PASS = '12345678a'
DL = Path('/home/ivan/.hermes/projects/facturama-portal/downloads')
MORAL = Path('/tmp/csd-pruebas/csd-pruebas/Personas Morales')

RECEIVER = {"Rfc": "FUNK671228PH6", "Name": "KARLA FUENTE NOLASCO",
            "CfdiUse": "G03", "FiscalRegime": "612", "TaxZipCode": "01160"}

iss = {"id": 2, "rfc": "H&E951128469", "name": "HERRERIA & ELECTRICOS",
       "zip": "06002", "regime": "601"}

sys.path.insert(0, '/home/ivan/.hermes/projects/facturama-portal')
from src.app import create_app
app = create_app()

with app.app_context():
    db = app.extensions['portal_db']
    db.save_issuer({
        'legal_name': iss['name'], 'rfc': iss['rfc'],
        'tax_regime': iss['regime'], 'zip_code': iss['zip'],
        'email': '', 'active': True,
    }, issuer_id=iss['id'])
    for s in db.list_series(iss['id']):
        with db.connect() as conn:
            conn.execute("UPDATE invoice_series SET next_folio = 1 WHERE id = ?", (s['id'],))
print('DB updated')

for cer in MORAL.rglob('*H&E951128469*.cer'):
    key = cer.with_suffix('.key')
    if key.exists():
        cer_path, key_path = str(cer), str(key)
        break
print(f'CSD: {Path(cer_path).name}')

with open(cer_path, 'rb') as f:
    cert_b64 = base64.b64encode(f.read()).decode()
with open(key_path, 'rb') as f:
    key_b64 = base64.b64encode(f.read()).decode()

r = requests.post(f'{BASE}/api-lite/csds', auth=(USER, PASSWORD), json={
    'Rfc': iss['rfc'], 'Certificate': cert_b64,
    'PrivateKey': key_b64, 'PrivateKeyPassword': CSD_PASS,
})
print(f'CSD upload: {r.status_code}')
time.sleep(0.4)

with app.app_context():
    db = app.extensions['portal_db']
    product = dict(db.list_products(issuer_id=iss['id'])[0])
    sl = db.list_series(iss['id'])
    serie = dict(sl[0])
    folio = db.get_next_folio(iss['id'], serie['series'])
    
    qty, unit = 1.0, float(product['price'])
    subt, iva = round(qty*unit,2), round(qty*unit*0.16,2)
    total = round(subt+iva,2)
    
    payload = {
        'NameId':'1','CfdiType':'I','ExpeditionPlace':iss['zip'],
        'PaymentForm':'03','PaymentMethod':'PUE','Currency':'MXN',
        'Serie':serie['series'],'Folio':str(folio),
        'Issuer':{'Rfc':iss['rfc'],'Name':iss['name'],'FiscalRegime':iss['regime']},
        'Receiver':RECEIVER,
        'Items':[{
            'ProductCode':product['product_code'],
            'IdentificationNumber':product['identification_number'],
            'Description':product['name'],'Unit':product['unit'],
            'UnitCode':product['unit_code'],'UnitPrice':unit,'Quantity':qty,
            'Subtotal':subt,'TaxObject':product['tax_object'],
            'Taxes':[{'Name':'IVA','Rate':0.16,'Total':iva,'Base':subt,'IsRetention':False}],
            'Total':total,
        }],
        'Subtotal':subt,'Total':total,
    }
    
    r = requests.post(f'{BASE}/api-lite/3/cfdis', auth=(USER, PASSWORD), json=payload)
    
    if r.status_code in (200,201):
        cfdi = r.json()
        fid = cfdi.get('Id','')
        uuid_val = ''
        comp = cfdi.get('Complement',{})
        if isinstance(comp,dict) and comp.get('TaxStamp'):
            uuid_val = comp['TaxStamp'].get('Uuid','')
        print(f'TIMBRADO! id={fid} uuid={uuid_val}')
        
        db.save_cfdi({
            'facturama_id':fid,'uuid':uuid_val,'issuer_id':iss['id'],
            'client_id':1,'recipient_rfc':RECEIVER['Rfc'],
            'recipient_name':RECEIVER['Name'],'total':total,
            'status':'active','cfdi_type':'I','payment_form':'03','payment_method':'PUE',
            'serie':serie['series'],'folio':folio,
            'items':[{'product_id':product['id'],'issuer_id':iss['id'],'client_id':1,
                     'name':product['name'],'description':product['name'],
                     'product_code':product['product_code'],
                     'identification_number':product['identification_number'],
                     'quantity':qty,'unit_price':unit,'subtotal':subt,'total':total}],
            'raw_payload':{'request':payload,'response':cfdi},
        })
        
        for fmt in ('xml','pdf'):
            r2 = requests.get(f'{BASE}/cfdi/{fmt}/issuedLite/{fid}', auth=(USER, PASSWORD))
            if r2.status_code == 200:
                d = r2.json()
                content = base64.urlsafe_b64decode(d['Content'].encode())
                fpath = DL / f'{fid}.{fmt}'
                fpath.write_bytes(content)
                print(f'{fmt.upper()}: {len(content)} bytes')
    else:
        print(f'FAIL: {r.status_code} {r.text[:350]}')
