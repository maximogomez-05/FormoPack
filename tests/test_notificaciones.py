"""Pruebas unitarias para el Servicio de Notificaciones (RF 5.4)."""

import unittest
from unittest.mock import patch, MagicMock

from config.settings import EmailConfig
from app.services.servicio_notificacion import ServicioNotificacion
from app.models.envio import Envio
from app.models.cliente import Cliente


class TestServicioNotificacion(unittest.TestCase):
    def setUp(self):
        self.servicio = ServicioNotificacion()
        self.envio_mock = MagicMock(spec=Envio)
        self.envio_mock.nro_guia = "FPX-20231010-001"
        self.envio_mock.estado_actual = "recibido"

        self.cliente_mock = MagicMock(spec=Cliente)
        self.cliente_mock.nombre_completo = "Juan Perez"
        self.cliente_mock.email = "juan@example.com"
        
        # Patch DatabaseManager to avoid real DB connections during tests
        self.db_patcher = patch("app.core.database.DatabaseManager.get_instance")
        self.mock_get_instance = self.db_patcher.start()
        
        # Setup mock db connection
        self.mock_db = MagicMock()
        self.mock_conn = MagicMock()
        self.mock_cur = MagicMock()
        
        self.mock_get_instance.return_value = self.mock_db
        self.mock_db.get_connection.return_value = self.mock_conn
        self.mock_conn.cursor.return_value = self.mock_cur
        
        # Return a fake email for the other client
        self.mock_cur.fetchone.return_value = {"email": "otro@example.com"}

    def tearDown(self):
        self.db_patcher.stop()

    @patch("app.services.servicio_notificacion.smtplib.SMTP_SSL")
    def test_enviar_alerta_exitosa_ssl(self, mock_smtp_ssl):
        """Prueba que el email se envíe correctamente usando SSL."""
        # Simular config de settings
        EmailConfig.USER = "test@example.com"
        EmailConfig.PASSWORD = "secret"
        EmailConfig.PORT = 465
        EmailConfig.HOST = "smtp.gmail.com"
        EmailConfig.RECIPIENT = "admin@example.com"

        mock_server = MagicMock()
        mock_smtp_ssl.return_value = mock_server

        self.servicio.enviar_alerta_cambio_estado(
            self.envio_mock, self.cliente_mock, nuevo_estado="en_ruta", observacion="Saliendo"
        )

        mock_smtp_ssl.assert_called_once_with("smtp.gmail.com", 465)
        mock_server.login.assert_called_once_with("test@example.com", "secret")
        mock_server.send_message.assert_called_once()
        mock_server.quit.assert_called_once()

    @patch("app.services.servicio_notificacion.smtplib.SMTP")
    def test_enviar_alerta_exitosa_tls(self, mock_smtp):
        """Prueba que el email se envíe correctamente usando TLS (puerto 587)."""
        EmailConfig.USER = "test@example.com"
        EmailConfig.PASSWORD = "secret"
        EmailConfig.PORT = 587

        mock_server = MagicMock()
        mock_smtp.return_value = mock_server

        self.servicio.enviar_alerta_cambio_estado(self.envio_mock, self.cliente_mock)

        mock_smtp.assert_called_once_with("smtp.gmail.com", 587)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("test@example.com", "secret")
        mock_server.send_message.assert_called_once()

    @patch("app.services.servicio_notificacion.logger.warning")
    @patch("app.services.servicio_notificacion.smtplib.SMTP_SSL")
    def test_enviar_alerta_sin_credenciales(self, mock_smtp, mock_logger):
        """Prueba que no se intente enviar si faltan credenciales."""
        EmailConfig.USER = ""
        EmailConfig.PASSWORD = ""

        self.servicio.enviar_alerta_cambio_estado(self.envio_mock, self.cliente_mock)

        mock_smtp.assert_not_called()
        mock_logger.assert_called_with("Credenciales SMTP no configuradas. Omitiendo notificación por email.")

    @patch("app.services.servicio_notificacion.logger.warning")
    @patch("app.services.servicio_notificacion.smtplib.SMTP_SSL")
    def test_enviar_alerta_error_smtp(self, mock_smtp, mock_logger):
        """Prueba que los errores SMTP se capturen y logueen sin romper la ejecución."""
        EmailConfig.USER = "test@example.com"
        EmailConfig.PASSWORD = "secret"
        EmailConfig.PORT = 465

        mock_server = MagicMock()
        mock_server.login.side_effect = Exception("Auth failed")
        mock_smtp.return_value = mock_server

        self.servicio.enviar_alerta_cambio_estado(self.envio_mock, self.cliente_mock)

        mock_logger.assert_called_once()
        self.assertTrue("Error al enviar notificación por email" in mock_logger.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
