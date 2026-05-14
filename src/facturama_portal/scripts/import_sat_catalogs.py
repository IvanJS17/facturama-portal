#!/usr/bin/env python3
"""
Script para importar catálogos SAT del Excel a la base de datos SQLite.

Uso:
    python -m facturama_portal.scripts.import_sat_catalogs [ruta_excel]

Si no se proporciona ruta, busca en data/sat-catalog/
"""
import sys
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import xlrd


def parse_date(value):
    """Convert Excel date number to Python date string."""
    if not value or value == '':
        return None
    try:
        if isinstance(value, (int, float)):
            # Excel date serial number (days since 1899-12-30)
            dt = datetime(1899, 12, 30) + timedelta(days=int(value))
            return dt.strftime('%Y-%m-%d')
        return None
    except:
        return None


def import_clave_prod_serv(wb, conn):
    """Import ClaveProdServ catalog."""
    sheet = wb.sheet_by_name('c_ClaveProdServ')
    cursor = conn.cursor()
    count = 0
    
    print(f"Importando c_ClaveProdServ ({sheet.nrows - 5} registros)...")
    
    for row_idx in range(5, sheet.nrows):
        code = str(int(sheet.cell_value(row_idx, 0))) if sheet.cell_value(row_idx, 0) else None
        if not code:
            continue
            
        description = str(sheet.cell_value(row_idx, 1)).strip()
        iva = str(sheet.cell_value(row_idx, 2)).strip() or None
        ieps = str(sheet.cell_value(row_idx, 3)).strip() or None
        complemento = str(sheet.cell_value(row_idx, 4)).strip() or None
        fecha_inicio = parse_date(sheet.cell_value(row_idx, 5))
        fecha_fin = parse_date(sheet.cell_value(row_idx, 6))
        
        cursor.execute(
            """
            INSERT OR REPLACE INTO sat_clave_prod_serv 
                (code, description, incluir_iva, incluir_ieps, complemento, fecha_inicio, fecha_fin)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (code, description, iva, ieps, complemento, fecha_inicio, fecha_fin)
        )
        
        count += 1
        if count % 5000 == 0:
            conn.commit()
            print(f"  ...{count} registros procesados")
    
    conn.commit()
    print(f"✓ c_ClaveProdServ: {count} registros importados")
    return count


def import_clave_unidad(wb, conn):
    """Import ClaveUnidad catalog."""
    sheet = wb.sheet_by_name('c_ClaveUnidad')
    cursor = conn.cursor()
    count = 0
    
    print(f"Importando c_ClaveUnidad ({sheet.nrows - 5} registros)...")
    
    for row_idx in range(5, sheet.nrows):
        code = str(sheet.cell_value(row_idx, 0)).strip()
        if not code:
            continue
            
        name = str(sheet.cell_value(row_idx, 1)).strip()
        description = str(sheet.cell_value(row_idx, 2)).strip() or None
        symbol = str(sheet.cell_value(row_idx, 6)).strip() or None
        fecha_inicio = parse_date(sheet.cell_value(row_idx, 4))
        fecha_fin = parse_date(sheet.cell_value(row_idx, 5))
        
        cursor.execute(
            """
            INSERT OR REPLACE INTO sat_clave_unidad 
                (code, name, description, symbol, fecha_inicio, fecha_fin)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (code, name, description, symbol, fecha_inicio, fecha_fin)
        )
        
        count += 1
    
    conn.commit()
    print(f"✓ c_ClaveUnidad: {count} registros importados")
    return count


def import_regimen_fiscal(wb, conn):
    """Import RegimenFiscal catalog."""
    sheet = wb.sheet_by_name('c_RegimenFiscal')
    cursor = conn.cursor()
    count = 0
    
    print(f"Importando c_RegimenFiscal ({sheet.nrows - 6} registros)...")
    
    for row_idx in range(6, sheet.nrows):
        code = str(int(sheet.cell_value(row_idx, 0))) if sheet.cell_value(row_idx, 0) else None
        if not code:
            continue
            
        description = str(sheet.cell_value(row_idx, 1)).strip()
        fisica = 1 if str(sheet.cell_value(row_idx, 2)).strip().lower() == 'sí' else 0
        moral = 1 if str(sheet.cell_value(row_idx, 3)).strip().lower() == 'sí' else 0
        fecha_inicio = parse_date(sheet.cell_value(row_idx, 4))
        fecha_fin = parse_date(sheet.cell_value(row_idx, 5))
        
        cursor.execute(
            """
            INSERT OR REPLACE INTO sat_regimen_fiscal 
                (code, description, aplica_fisica, aplica_moral, fecha_inicio, fecha_fin)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (code, description, fisica, moral, fecha_inicio, fecha_fin)
        )
        
        count += 1
    
    conn.commit()
    print(f"✓ c_RegimenFiscal: {count} registros importados")
    return count


def import_forma_pago(wb, conn):
    """Import FormaPago catalog."""
    sheet = wb.sheet_by_name('c_FormaPago')
    cursor = conn.cursor()
    count = 0
    
    print(f"Importando c_FormaPago ({sheet.nrows - 6} registros)...")
    
    for row_idx in range(6, sheet.nrows):
        code = str(int(sheet.cell_value(row_idx, 0))) if sheet.cell_value(row_idx, 0) else None
        if not code:
            continue
            
        description = str(sheet.cell_value(row_idx, 1)).strip()
        bancarizado = 1 if str(sheet.cell_value(row_idx, 2)).strip().lower() == 'sí' else 0
        fecha_inicio = parse_date(sheet.cell_value(row_idx, 12))
        fecha_fin = parse_date(sheet.cell_value(row_idx, 13))
        
        cursor.execute(
            """
            INSERT OR REPLACE INTO sat_forma_pago 
                (code, description, bancarizado, fecha_inicio, fecha_fin)
            VALUES (?, ?, ?, ?, ?)
            """,
            (code, description, bancarizado, fecha_inicio, fecha_fin)
        )
        
        count += 1
    
    conn.commit()
    print(f"✓ c_FormaPago: {count} registros importados")
    return count


def import_metodo_pago(wb, conn):
    """Import MetodoPago catalog."""
    sheet = wb.sheet_by_name('c_MetodoPago')
    cursor = conn.cursor()
    count = 0
    
    print(f"Importando c_MetodoPago ({sheet.nrows - 6} registros)...")
    
    for row_idx in range(6, sheet.nrows):
        code = str(sheet.cell_value(row_idx, 0)).strip()
        if not code:
            continue
            
        description = str(sheet.cell_value(row_idx, 1)).strip()
        fecha_inicio = parse_date(sheet.cell_value(row_idx, 2))
        fecha_fin = parse_date(sheet.cell_value(row_idx, 3))
        
        cursor.execute(
            """
            INSERT OR REPLACE INTO sat_metodo_pago 
                (code, description, fecha_inicio, fecha_fin)
            VALUES (?, ?, ?, ?)
            """,
            (code, description, fecha_inicio, fecha_fin)
        )
        
        count += 1
    
    conn.commit()
    print(f"✓ c_MetodoPago: {count} registros importados")
    return count


def main():
    if len(sys.argv) > 1:
        excel_path = sys.argv[1]
    else:
        # Default path
        excel_path = Path(__file__).parent.parent.parent.parent / 'data' / 'sat-catalog' / 'catCFDI_V_33_31032023.xls'
    
    if not Path(excel_path).exists():
        print(f"Error: No se encontró el archivo: {excel_path}")
        print("Uso: python -m facturama_portal.scripts.import_sat_catalogs [ruta_excel]")
        sys.exit(1)
    
    print(f"Cargando Excel: {excel_path}")
    wb = xlrd.open_workbook(str(excel_path))
    print(f"Hojas disponibles: {wb.sheet_names()}")
    print()
    
    # Get database path
    db_path = Path(__file__).parent.parent.parent.parent / 'facturama_portal.db'
    if not db_path.exists():
        print(f"Error: No se encontró la base de datos: {db_path}")
        print("Ejecuta primero la aplicación para crear la base de datos.")
        sys.exit(1)
    
    print(f"Base de datos: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    
    # Ensure tables exist
    print("Verificando/creando tablas SAT...")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sat_clave_prod_serv (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL,
            incluir_iva TEXT,
            incluir_ieps TEXT,
            complemento TEXT,
            fecha_inicio TEXT,
            fecha_fin TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_sat_clave_prod_serv_code ON sat_clave_prod_serv(code);

        CREATE TABLE IF NOT EXISTS sat_clave_unidad (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT,
            symbol TEXT,
            fecha_inicio TEXT,
            fecha_fin TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_sat_clave_unidad_code ON sat_clave_unidad(code);

        CREATE TABLE IF NOT EXISTS sat_regimen_fiscal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL,
            aplica_fisica INTEGER NOT NULL DEFAULT 0,
            aplica_moral INTEGER NOT NULL DEFAULT 0,
            fecha_inicio TEXT,
            fecha_fin TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_sat_regimen_fiscal_code ON sat_regimen_fiscal(code);

        CREATE TABLE IF NOT EXISTS sat_forma_pago (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL,
            bancarizado INTEGER NOT NULL DEFAULT 0,
            fecha_inicio TEXT,
            fecha_fin TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_sat_forma_pago_code ON sat_forma_pago(code);

        CREATE TABLE IF NOT EXISTS sat_metodo_pago (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL,
            fecha_inicio TEXT,
            fecha_fin TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_sat_metodo_pago_code ON sat_metodo_pago(code);
    """)
    conn.commit()
    print("✓ Tablas SAT verificadas/creadas")
    print()
    
    try:
        # Import catalogs
        total = 0
        total += import_clave_prod_serv(wb, conn)
        total += import_clave_unidad(wb, conn)
        total += import_regimen_fiscal(wb, conn)
        total += import_forma_pago(wb, conn)
        total += import_metodo_pago(wb, conn)
        
        print()
        print(f"✓ Importación completa: {total} registros totales")
        
        # Show summary
        cursor = conn.cursor()
        for table in ['sat_clave_prod_serv', 'sat_clave_unidad', 'sat_regimen_fiscal', 'sat_forma_pago', 'sat_metodo_pago']:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"  - {table}: {count} registros")
        
    finally:
        conn.close()


if __name__ == '__main__':
    main()
