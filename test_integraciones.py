import sys
import logging

# Configurar logging para ver la salida en consola
logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

# Mock classes para probar el envío de emails sin necesidad de base de datos
class MockCliente:
    def __init__(self, email):
        self.email = email
        self.id_cliente = 999

class MockEnvio:
    def __init__(self, nro_guia, direccion, bultos, pago, estado):
        self.id_envio = 999
        self.nro_guia = nro_guia
        self.direccion_destino = direccion
        self.cantidad_bultos = bultos
        self.modalidad_pago = pago
        self.estado_actual = estado
        self.id_remitente = 999
        self.id_destinatario = 999

def test_mercadopago():
    print("\n--- INICIANDO TEST DE MERCADO PAGO ---")
    try:
        from app.services.mercadopago_service import MercadoPagoService
        mp = MercadoPagoService()
        
        print(">> Generando preferencia de prueba para un envío simulado de $1500...")
        preferencia = mp.crear_preferencia(
            nro_guia="TEST-MP-123",
            descripcion="Test Sistema FormoPack Express",
            monto=1500.00
        )
        
        print("[OK] EXITO: Preferencia creada correctamente.")
        print(f"ID Preferencia: {preferencia['id']}")
        print(f"URL de Pago (Sandbox): {preferencia['sandbox_init_point']}")
        return True
    except Exception as e:
        print(f"[ERROR] en Mercado Pago: {e}")
        return False

def test_email(correo_destino):
    print("\n--- INICIANDO TEST DE NOTIFICACIONES (EMAIL HTML) ---")
    try:
        from app.services.servicio_notificacion import ServicioNotificacion
        
        envio_mock = MockEnvio(
            nro_guia="FP-2026-9999",
            direccion="Av. San Martín 1234, Formosa",
            bultos=2,
            pago="digital",
            estado="en_ruta"
        )
        cliente_mock = MockCliente(email=correo_destino)
        
        servicio = ServicioNotificacion()
        print(f">> Enviando alerta HTML de prueba a: {correo_destino}...")
        
        servicio.enviar_alerta_cambio_estado(
            envio=envio_mock,
            cliente=cliente_mock,
            nuevo_estado="entregado",
            observacion="Paquete recibido por el titular en puerta."
        )
        
        print(f"[OK] EXITO: El codigo se ejecuto sin errores. (Verifica tu bandeja de entrada).")
        return True
    except Exception as e:
        print(f"[ERROR] en Notificaciones: {e}")
        return False

if __name__ == "__main__":
    test_mercadopago()
    test_email("maximo.gomezfsa@gmail.com")
    print("\n--- TESTS FINALIZADOS ---")
