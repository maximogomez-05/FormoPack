"""Tests unitarios para los modelos del dominio — Sprint 2."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models.cliente import Cliente
from app.models.localidad import Localidad
from app.models.seguro import Seguro
from app.models.bulto import Bulto
from app.models.envio import Envio
from app.models.pago import Pago, PagoEfectivo, PagoDigital
from app.models.turno_caja import TurnoCaja
from app.models.comprobante_interno import ComprobanteInterno
from app.models.historial_estado import HistorialEstado
from app.utils.exceptions import ValidationError, TurnoCajaError
from config.settings import EstadosEnvio


def test_cliente_validacion():
    """Prueba validación de datos obligatorios de Cliente."""
    # Datos válidos
    Cliente.validar_datos("12345678", "Juan Perez", "3704123456")
    print("  [OK] Cliente: Validación de datos correctos")

    # DNI vacío
    try:
        Cliente.validar_datos("", "Juan Perez", "3704123456")
        assert False, "Debería fallar sin DNI"
    except ValidationError:
        pass

    # Teléfono vacío
    try:
        Cliente.validar_datos("12345678", "Juan Perez", "")
        assert False, "Debería fallar sin teléfono"
    except ValidationError:
        pass

    # DNI muy corto
    try:
        Cliente.validar_datos("123", "Juan Perez", "3704123456")
        assert False, "Debería fallar con DNI muy corto"
    except ValidationError:
        pass

    print("  [OK] Cliente: Validación de datos inválidos")


def test_cliente_from_db():
    """Prueba factory from_db_row de Cliente."""
    row = {
        "id_cliente": 1,
        "dni": "12345678",
        "nombre_completo": "Juan Perez",
        "telefono": "3704123456",
    }
    cliente = Cliente.from_db_row(row)
    assert cliente.id_cliente == 1
    assert cliente.dni == "12345678"
    assert "Juan Perez" in cliente.obtener_datos_contacto()
    print("  [OK] Cliente: Factory from_db_row y obtenerDatosContacto")


def test_localidad_corredor():
    """Prueba clasificación por corredor de ruta."""
    casos = [
        (30.0, "urbano"),
        (100.0, "periurbano"),
        (200.0, "interior"),
        (400.0, "frontera"),
    ]
    for km, esperado in casos:
        loc = Localidad(id_localidad=1, nombre="Test", distancia_km=km)
        assert loc.obtener_corredor_centro() == esperado, f"Esperado {esperado} para {km} KM"
    print("  [OK] Localidad: Clasificación de corredores por KM")


def test_seguro_cobertura():
    """Prueba cálculo de costo de seguro."""
    seguro = Seguro(id_seguro=1, cobertura_estandar=50000.0, porcentaje_excedente=2.0)

    # Valor dentro de cobertura: costo = 0
    assert seguro.calcular_costo_cobertura(30000.0) == 0.0
    assert seguro.calcular_costo_cobertura(50000.0) == 0.0

    # Valor excedente: (80000 - 50000) * 2% = 600
    assert seguro.calcular_costo_cobertura(80000.0) == 600.0

    # Valor alto: (200000 - 50000) * 2% = 3000
    assert seguro.calcular_costo_cobertura(200000.0) == 3000.0

    print("  [OK] Seguro: Cálculo de cobertura y excedente")


def test_bulto_aforo():
    """Prueba cálculo de aforo (mayor entre peso real y volumétrico)."""
    # Peso real mayor
    b1 = Bulto(id_bulto=1, id_envio=1, peso_real=10.0, peso_volumetrico=5.0)
    assert b1.calcular_aforo() == 10.0

    # Peso volumétrico mayor
    b2 = Bulto(id_bulto=2, id_envio=1, peso_real=3.0, peso_volumetrico=8.0)
    assert b2.calcular_aforo() == 8.0

    # Pesos iguales
    b3 = Bulto(id_bulto=3, id_envio=1, peso_real=5.0, peso_volumetrico=5.0)
    assert b3.calcular_aforo() == 5.0

    print("  [OK] Bulto: Cálculo de aforo (max real vs volumétrico)")


def test_envio_ciclo_vida():
    """Prueba ciclo de vida de estados del envío."""
    envio = Envio(
        id_envio=1,
        nro_guia="FPX-20260827-0001",
        id_remitente=1,
        id_destinatario=2,
        id_localidad_destino=1,
        direccion_destino="Av. San Martin 123",
    )
    assert envio.estado_actual == EstadosEnvio.RECIBIDO
    assert envio.cantidad_bultos == 0

    # Agregar bultos
    bulto = Bulto(id_bulto=1, id_envio=1, peso_real=5.0, peso_volumetrico=3.0)
    envio.agregar_bulto(bulto)
    assert envio.cantidad_bultos == 1

    # Cambiar estado
    envio.registrar_estado(EstadosEnvio.EN_PLANTA)
    assert envio.estado_actual == EstadosEnvio.EN_PLANTA

    envio.registrar_estado(EstadosEnvio.EN_RUTA)
    assert envio.estado_actual == EstadosEnvio.EN_RUTA

    envio.registrar_estado(EstadosEnvio.ENTREGADO)
    assert envio.estado_actual == EstadosEnvio.ENTREGADO

    # Estado inválido
    try:
        envio.registrar_estado("estado_falso")
        assert False, "Debería fallar con estado inválido"
    except ValueError:
        pass

    print("  [OK] Envio: Ciclo de vida de estados y gestión de bultos")


def test_pago_efectivo_vuelto():
    """Prueba cálculo de vuelto en pago efectivo."""
    pago = PagoEfectivo(
        id_pago=1, id_envio=1, monto=1500.0, monto_entregado=2000.0,
    )
    assert pago.vuelto == 500.0
    assert pago.tipo_pago == "efectivo"
    assert pago.procesar_pago() is True
    print("  [OK] PagoEfectivo: Cálculo de vuelto")


def test_pago_digital():
    """Prueba generación de QR en pago digital."""
    pago = PagoDigital(
        id_pago=2, id_envio=1, monto=1500.0,
        billetera_virtual="MercadoPago",
    )
    assert pago.tipo_pago == "digital"
    qr = pago.generar_qr(1500.0)
    assert qr.startswith("QR-")
    assert pago.id_transaccion_qr == qr
    print("  [OK] PagoDigital: Generación de QR y billetera")


def test_turno_caja():
    """Prueba apertura, ingreso y cierre de turno de caja."""
    turno = TurnoCaja(
        id_turno=1,
        id_recepcionista=2,
        saldo_inicial=5000.0,
    )
    assert turno.estado_caja == "abierto"
    assert turno.total_caja == 5000.0

    # Registrar ingresos con pagos mock
    pago_ef = PagoEfectivo(id_pago=1, id_envio=1, monto=1500.0, monto_entregado=2000.0)
    pago_dig = PagoDigital(id_pago=2, id_envio=2, monto=2000.0, billetera_virtual="MP")

    turno.registrar_ingreso(pago_ef)
    assert turno.ingresos_efectivo == 1500.0

    turno.registrar_ingreso(pago_dig)
    assert turno.ingresos_digitales == 2000.0
    assert turno.total_ingresos == 3500.0
    assert turno.total_caja == 6500.0  # 5000 + 1500

    # Cierre
    resumen = turno.realizar_cierre_caja()
    assert turno.estado_caja == "cerrado"
    assert resumen["total_caja_fisica"] == 6500.0
    assert resumen["ingresos_digitales"] == 2000.0

    # No se puede cerrar dos veces
    try:
        turno.realizar_cierre_caja()
        assert False, "Debería fallar al cerrar turno ya cerrado"
    except TurnoCajaError:
        pass

    # No se puede registrar ingreso en caja cerrada
    try:
        turno.registrar_ingreso(pago_ef)
        assert False, "Debería fallar al registrar en caja cerrada"
    except TurnoCajaError:
        pass

    print("  [OK] TurnoCaja: Apertura, ingresos discriminados y cierre")


def test_historial_estado():
    """Prueba creación de registros de historial."""
    h = HistorialEstado(
        id_historial=1,
        id_envio=1,
        estado="recibido",
        ubicacion="Sucursal Formosa",
        observacion="Envio recibido en mostrador",
    )
    d = h.to_dict()
    assert d["estado"] == "recibido"
    assert d["ubicacion"] == "Sucursal Formosa"
    print("  [OK] HistorialEstado: Creación y serialización")


def test_serialization():
    """Prueba serialización to_dict de todos los modelos."""
    cliente = Cliente(id_cliente=1, dni="12345678", nombre_completo="Test", telefono="123")
    assert "id_cliente" in cliente.to_dict()

    loc = Localidad(id_localidad=1, nombre="Test", distancia_km=100)
    assert "corredor" in loc.to_dict()

    seguro = Seguro(id_seguro=1, cobertura_estandar=50000, porcentaje_excedente=2.0)
    assert "cobertura_estandar" in seguro.to_dict()

    bulto = Bulto(id_bulto=1, id_envio=1, peso_real=5, peso_volumetrico=3)
    assert "peso_aforo" in bulto.to_dict()

    comprobante = ComprobanteInterno(id_comprobante=1, id_envio=1, nro_comprobante="REC-001")
    assert "nro_comprobante" in comprobante.to_dict()

    print("  [OK] Serialización to_dict() de todos los modelos")


def main():
    print("\n--- Pruebas Sprint 2 (Modelos de Dominio) ---")
    test_cliente_validacion()
    test_cliente_from_db()
    test_localidad_corredor()
    test_seguro_cobertura()
    test_bulto_aforo()
    test_envio_ciclo_vida()
    test_pago_efectivo_vuelto()
    test_pago_digital()
    test_turno_caja()
    test_historial_estado()
    test_serialization()
    print("--- Todas las pruebas de modelos pasaron ---\n")


if __name__ == "__main__":
    main()
