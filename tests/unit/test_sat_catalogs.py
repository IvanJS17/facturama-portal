"""Tests for SAT catalog search API and database methods."""

import pytest
from src.models import PortalDatabase


@pytest.fixture
def db(tmp_path):
    """Create a fresh database for testing."""
    db_path = tmp_path / "test.db"
    database = PortalDatabase(f"sqlite:///{db_path}")
    database.init_schema()
    
    # Insert test data
    with database.connect() as conn:
        # ClaveProdServ test data
        conn.execute("""
            INSERT INTO sat_clave_prod_serv (code, description, incluir_iva, incluir_ieps)
            VALUES 
                ('01010101', 'No existe en el catálogo', 'Opcional', 'Opcional'),
                ('43232300', 'Servicios de consultoría en informática', 'Sí', 'No'),
                ('43231500', 'Servicios de desarrollo de software', 'Sí', 'No'),
                ('80101500', 'Servicios de gestión empresarial', 'Sí', 'No')
        """)
        
        # ClaveUnidad test data
        conn.execute("""
            INSERT INTO sat_clave_unidad (code, name, description, symbol)
            VALUES 
                ('E48', 'Servicio', 'Unidad de servicio', 'E48'),
                ('H87', 'Pieza', 'Unidad de pieza', 'H87'),
                ('ACT', 'Actividad', 'Unidad de actividad', 'ACT'),
                ('KGM', 'Kilogramo', 'Unidad de masa', 'kg')
        """)
        
        # RegimenFiscal test data
        conn.execute("""
            INSERT INTO sat_regimen_fiscal (code, description, aplica_fisica, aplica_moral)
            VALUES 
                ('601', 'General de Ley Personas Morales', 0, 1),
                ('605', 'Sueldos y Salarios e Ingresos Asimilados a Salarios', 1, 0),
                ('612', 'Personas Físicas con Actividades Empresariales y Profesionales', 1, 0),
                ('603', 'Personas Morales con Fines no Lucrativos', 0, 1)
        """)
        
        # FormaPago test data
        conn.execute("""
            INSERT INTO sat_forma_pago (code, description, bancarizado)
            VALUES 
                ('01', 'Efectivo', 0),
                ('03', 'Transferencia electrónica de fondos', 1),
                ('04', 'Tarjeta de crédito', 1)
        """)
        
        # MetodoPago test data
        conn.execute("""
            INSERT INTO sat_metodo_pago (code, description)
            VALUES 
                ('PUE', 'Pago en una sola exhibición'),
                ('PPD', 'Pago en parcialidades o diferido')
        """)
        
        conn.commit()
    
    return database


class TestSATClaveProdServSearch:
    """Test ClaveProdServ search functionality."""
    
    def test_search_by_code(self, db):
        """Search by exact code."""
        results = db.search_sat_clave_prod_serv("43232300")
        assert len(results) >= 1
        assert any(r["code"] == "43232300" for r in results)
    
    def test_search_by_description(self, db):
        """Search by description text."""
        results = db.search_sat_clave_prod_serv("consultoría")
        assert len(results) >= 1
        assert any("consultoría" in r["description"].lower() for r in results)
    
    def test_search_partial_code(self, db):
        """Search by partial code."""
        results = db.search_sat_clave_prod_serv("4323")
        assert len(results) >= 2  # Should match 43232300 and 43231500
    
    def test_search_no_results(self, db):
        """Search with no matching results."""
        results = db.search_sat_clave_prod_serv("xyznonexistent")
        assert len(results) == 0
    
    def test_search_limit(self, db):
        """Search respects limit parameter."""
        results = db.search_sat_clave_prod_serv("01", limit=2)
        assert len(results) <= 2


class TestSATClaveUnidadSearch:
    """Test ClaveUnidad search functionality."""
    
    def test_search_by_code(self, db):
        """Search by exact code."""
        results = db.search_sat_clave_unidad("E48")
        assert len(results) >= 1
        assert any(r["code"] == "E48" for r in results)
    
    def test_search_by_name(self, db):
        """Search by unit name."""
        results = db.search_sat_clave_unidad("Pieza")
        assert len(results) >= 1
        assert any("Pieza" in r["name"] for r in results)
    
    def test_search_by_symbol(self, db):
        """Search by unit symbol."""
        results = db.search_sat_clave_unidad("kg")
        assert len(results) >= 1
        assert any(r["symbol"] == "kg" for r in results)


class TestSATRegimenFiscalSearch:
    """Test RegimenFiscal search functionality."""
    
    def test_search_all(self, db):
        """Search without person type filter."""
        results = db.search_sat_regimen_fiscal("Personas")
        assert len(results) >= 3  # Multiple matches
    
    def test_search_fisica_only(self, db):
        """Search filtered by person type 'fisica'."""
        results = db.search_sat_regimen_fiscal("", person_type="fisica")
        assert len(results) >= 2
        # All results should be for fisica
        for r in results:
            assert r["aplica_fisica"] == 1
    
    def test_search_moral_only(self, db):
        """Search filtered by person type 'moral'."""
        results = db.search_sat_regimen_fiscal("", person_type="moral")
        assert len(results) >= 2
        # All results should be for moral
        for r in results:
            assert r["aplica_moral"] == 1
    
    def test_search_by_code(self, db):
        """Search by regime code."""
        results = db.search_sat_regimen_fiscal("601")
        assert len(results) >= 1
        assert any(r["code"] == "601" for r in results)


class TestSATFormaPagoSearch:
    """Test FormaPago search functionality."""
    
    def test_search_by_description(self, db):
        """Search by payment form description."""
        results = db.search_sat_forma_pago("Efectivo")
        assert len(results) >= 1
        assert any("Efectivo" in r["description"] for r in results)
    
    def test_search_by_code(self, db):
        """Search by payment form code."""
        results = db.search_sat_forma_pago("03")
        assert len(results) >= 1
        assert any(r["code"] == "03" for r in results)


class TestSATMetodoPagoSearch:
    """Test MetodoPago search functionality."""
    
    def test_search_by_description(self, db):
        """Search by payment method description."""
        results = db.search_sat_metodo_pago("exhibición")
        assert len(results) >= 1
        assert any("exhibición" in r["description"].lower() for r in results)
    
    def test_search_by_code(self, db):
        """Search by payment method code."""
        results = db.search_sat_metodo_pago("PUE")
        assert len(results) >= 1
        assert any(r["code"] == "PUE" for r in results)


class TestSATCatalogTables:
    """Test that SAT catalog tables are created correctly."""
    
    def test_tables_exist(self, db):
        """Verify all SAT catalog tables exist."""
        with db.connect() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'sat_%'"
            ).fetchall()
            table_names = [t["name"] for t in tables]
            
            assert "sat_clave_prod_serv" in table_names
            assert "sat_clave_unidad" in table_names
            assert "sat_regimen_fiscal" in table_names
            assert "sat_forma_pago" in table_names
            assert "sat_metodo_pago" in table_names
    
    def test_indexes_exist(self, db):
        """Verify indexes exist on SAT catalog tables."""
        with db.connect() as conn:
            indexes = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_sat_%'"
            ).fetchall()
            index_names = [i["name"] for i in indexes]
            
            assert "idx_sat_clave_prod_serv_code" in index_names
            assert "idx_sat_clave_unidad_code" in index_names
            assert "idx_sat_regimen_fiscal_code" in index_names
            assert "idx_sat_forma_pago_code" in index_names
            assert "idx_sat_metodo_pago_code" in index_names
