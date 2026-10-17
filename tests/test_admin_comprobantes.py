"""Pruebas unitarias para el módulo de Comprobantes de Servicios del Administrador (RF 2.7)."""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, date
import csv
import io

from app.models.comprobante_interno import ComprobanteInterno
from web.routes.admin import _obtener_comprobantes_admin
from web.app import create_app


class TestComprobantesAdmin(unittest.TestCase):
    """Test suite para el nuevo sector de comprobantes de servicio del administrador."""

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["SECRET_KEY"] = "test-secret"
        self.client = self.app.test_client()

    def test_generacion_nro_comprobante(self):
        """Verifica el formato del número de comprobante interno."""
        nro = ComprobanteInterno.generar_nro_comprobante(42, "recepcion")
        self.assertTrue(nro.startswith("REC-000042-"))
        self.assertEqual(len(nro), 19)

    def test_calculo_desglose_seguro_y_flete(self):
        """Verifica que el desglose de flete y seguro se calcule correctamente."""
        # Simulamos una fila con valor declarado superior a cobertura estándar
        fila = {
            "id_comprobante": 1,
            "nro_comprobante": "REC-000001-20261016",
            "tipo_comprobante": "recepcion",
            "fecha_emision": datetime.now(),
            "id_envio": 1,
            "nro_guia": "FOR-20261016-0001",
            "estado_actual": "recibido",
            "costo_total": 5000.0,
            "modalidad_pago": "efectivo",
            "valor_declarado": 100000.0,
            "cobertura_estandar": 50000.0,
            "porcentaje_excedente": 1.0,  # 1% sobre 50.000 = $500
            "monto_pagado": 5000.0,
        }

        vd = float(fila["valor_declarado"])
        cob = float(fila["cobertura_estandar"])
        pct = float(fila["porcentaje_excedente"])
        costo_seg = round((vd - cob) * (pct / 100.0), 2)
        subtotal_flete = round(fila["costo_total"] - costo_seg, 2)

        self.assertEqual(costo_seg, 500.0)
        self.assertEqual(subtotal_flete, 4500.0)

    @patch("web.routes.admin._obtener_comprobantes_admin")
    def test_acceso_admin_comprobantes_con_sesion(self, mock_obtener):
        """Verifica que un administrador pueda ingresar al sector de comprobantes."""
        mock_obtener.return_value = [
            {
                "id_comprobante": 1,
                "nro_comprobante": "REC-000001-20261016",
                "tipo_comprobante": "recepcion",
                "fecha_emision": datetime(2026, 10, 16, 10, 30),
                "id_envio": 1,
                "nro_guia": "FOR-20261016-0001",
                "estado_actual": "recibido",
                "costo_total": 3500.0,
                "modalidad_pago": "efectivo",
                "remitente": "Carlos Perez",
                "rem_dni": "28111222",
                "destinatario": "Ana Gomez",
                "dest_dni": "32333444",
                "localidad_destino": "Clorinda",
                "total_bultos": 2,
                "peso_total": 12.5,
                "monto_pagado": 3500.0,
                "costo_seguro": 0.0,
                "subtotal_flete": 3500.0,
                "esta_pagado": True,
            }
        ]

        with self.client.session_transaction() as sess:
            sess["usuario_id"] = 1
            sess["nombre"] = "Admin Test"
            sess["rol"] = "administrador"

        response = self.client.get("/admin/comprobantes")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Comprobantes de Servicios", html)
        self.assertIn("REC-000001-20261016", html)
        self.assertIn("FOR-20261016-0001", html)
        self.assertIn("Carlos Perez", html)
        self.assertIn("Clorinda", html)

    @patch("web.routes.admin._obtener_comprobantes_admin")
    def test_exportar_comprobantes_csv(self, mock_obtener):
        """Verifica la exportación del reporte de comprobantes en CSV con UTF-8 BOM."""
        mock_obtener.return_value = [
            {
                "id_comprobante": 1,
                "nro_comprobante": "REC-000001-20261016",
                "tipo_comprobante": "recepcion",
                "fecha_emision": datetime(2026, 10, 16, 10, 30),
                "id_envio": 1,
                "nro_guia": "FOR-20261016-0001",
                "estado_actual": "recibido",
                "costo_total": 3500.0,
                "modalidad_pago": "efectivo",
                "remitente": "Carlos Perez",
                "rem_dni": "28111222",
                "rem_tel": "3704112233",
                "destinatario": "Ana Gomez",
                "dest_dni": "32333444",
                "dest_tel": "3718445566",
                "localidad_destino": "Clorinda",
                "direccion_destino": "Av. San Martin 123",
                "total_bultos": 2,
                "peso_total": 12.5,
                "subtotal_flete": 3500.0,
                "costo_seguro": 0.0,
                "monto_pagado": 3500.0,
                "tipo_pago": "efectivo",
                "fecha_pago": datetime(2026, 10, 16, 10, 35),
                "esta_pagado": True,
            }
        ]

        with self.client.session_transaction() as sess:
            sess["usuario_id"] = 1
            sess["nombre"] = "Admin Test"
            sess["rol"] = "administrador"

        response = self.client.get("/admin/comprobantes/exportar.csv")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["Content-Type"].startswith("text/csv"))
        self.assertIn("attachment; filename=comprobantes_servicios_", response.headers["Content-Disposition"])

        csv_content = response.get_data(as_text=True)
        self.assertTrue(csv_content.startswith("\ufeff"))
        self.assertIn("Nro Comprobante,Nro Guia,Fecha Emision", csv_content)
        self.assertIn("REC-000001-20261016", csv_content)
        self.assertIn("FOR-20261016-0001", csv_content)

    def test_bloqueo_acceso_sin_login(self):
        """Verifica que usuarios no autenticados sean redirigidos al login."""
        response = self.client.get("/admin/comprobantes")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_bloqueo_acceso_rol_no_autorizado(self):
        """Verifica que usuarios con rol distinto a administrador no puedan acceder (403 o redirect)."""
        with self.client.session_transaction() as sess:
            sess["usuario_id"] = 2
            sess["nombre"] = "Chofer Test"
            sess["rol"] = "chofer"

        response = self.client.get("/admin/comprobantes")
        self.assertIn(response.status_code, [302, 403])

    @patch("web.routes.admin._obtener_comprobantes_admin")
    def test_vista_comprobantes_vacia(self, mock_obtener):
        """Verifica que se muestre el estado vacío amigable cuando no hay comprobantes."""
        mock_obtener.return_value = []

        with self.client.session_transaction() as sess:
            sess["usuario_id"] = 1
            sess["nombre"] = "Admin Test"
            sess["rol"] = "administrador"

        response = self.client.get("/admin/comprobantes")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("No se encontraron comprobantes de servicios", html)
        self.assertIn("0", html)  # Comprobantes emitidos: 0

    @patch("web.routes.admin._obtener_comprobantes_admin")
    def test_metricas_kpis_mixtas(self, mock_obtener):
        """Verifica cálculo correcto de métricas con pagos y pendientes."""
        mock_obtener.return_value = [
            {
                "id_comprobante": 1,
                "nro_comprobante": "REC-000001-20261016",
                "tipo_comprobante": "recepcion",
                "fecha_emision": datetime(2026, 10, 16, 10, 30),
                "id_envio": 1,
                "nro_guia": "FOR-20261016-0001",
                "estado_actual": "recibido",
                "costo_total": 4000.0,
                "modalidad_pago": "efectivo",
                "remitente": "Carlos",
                "rem_dni": "1",
                "destinatario": "Ana",
                "dest_dni": "2",
                "localidad_destino": "Formosa",
                "total_bultos": 1,
                "peso_total": 5.0,
                "subtotal_flete": 4000.0,
                "costo_seguro": 0.0,
                "monto_pagado": 4000.0,
                "esta_pagado": True,
            },
            {
                "id_comprobante": 2,
                "nro_comprobante": "REC-000002-20261016",
                "tipo_comprobante": "recepcion",
                "fecha_emision": datetime(2026, 10, 16, 11, 0),
                "id_envio": 2,
                "nro_guia": "FOR-20261016-0002",
                "estado_actual": "recibido",
                "costo_total": 6000.0,
                "modalidad_pago": "cuenta_corriente",
                "remitente": "Empresa SRL",
                "rem_dni": "30111222",
                "destinatario": "Sucursal Norte",
                "dest_dni": "30222333",
                "localidad_destino": "Pirané",
                "total_bultos": 3,
                "peso_total": 20.0,
                "subtotal_flete": 5500.0,
                "costo_seguro": 500.0,
                "monto_pagado": None,  # No pagado aún
                "esta_pagado": False,
            },
        ]

        with self.client.session_transaction() as sess:
            sess["usuario_id"] = 1
            sess["nombre"] = "Admin Test"
            sess["rol"] = "administrador"

        response = self.client.get("/admin/comprobantes")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        # Total facturado: 4000 + 6000 = 10000.00
        self.assertIn("$10000.00", html)
        # Total cobrado: 4000.00
        self.assertIn("$4000.00", html)
        # Pendientes: 1
        self.assertIn("Pendientes de Pago", html)
        # Badges presentes
        self.assertIn("Pagado", html)
        self.assertIn("Pendiente", html)


if __name__ == "__main__":
    unittest.main()
