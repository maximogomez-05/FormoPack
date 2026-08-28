"""Tests del motor de Cotización — RF 2.2 / RF 2.3 / RF 2.4."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models.bulto import Bulto
from app.models.localidad import Localidad
from app.models.seguro import Seguro
from app.services.cotizador import Cotizador
from app.utils.exceptions import CotizacionError
from config.settings import CotizadorConfig


def test_cotizacion_simple():
    """Prueba cotización de un solo bulto a localidad urbana."""
    cotizador = Cotizador()
    localidad = Localidad(id_localidad=1, nombre="Formosa Capital", distancia_km=0)
    bulto = Bulto(id_bulto=1, id_envio=1, peso_real=5.0, peso_volumetrico=3.0)

    resultado = cotizador.calcular_tarifa([bulto], localidad)

    assert resultado["cantidad_bultos"] == 1
    assert resultado["costo_total"] > 0
    assert resultado["costo_seguro"] == 0.0
    assert len(resultado["tarifas_por_bulto"]) == 1

    # El aforo debe ser 5.0 (mayor que 3.0)
    assert resultado["detalle_bultos"][0]["peso_aforo"] == 5.0
    # Sin descuento para el primer bulto
    assert resultado["detalle_bultos"][0]["descuento_multibulto"] == "0%"

    print("  [OK] Cotización simple: 1 bulto a zona urbana")


def test_regla_multibulto():
    """Prueba regla: 100% al primer bulto, 50% descuento a los siguientes."""
    cotizador = Cotizador()
    localidad = Localidad(id_localidad=2, nombre="Clorinda", distancia_km=120)

    bultos = [
        Bulto(id_bulto=1, id_envio=1, peso_real=10.0, peso_volumetrico=5.0),
        Bulto(id_bulto=2, id_envio=1, peso_real=10.0, peso_volumetrico=5.0),
        Bulto(id_bulto=3, id_envio=1, peso_real=10.0, peso_volumetrico=5.0),
    ]

    resultado = cotizador.calcular_tarifa(bultos, localidad)

    assert resultado["cantidad_bultos"] == 3

    # Primer bulto: sin descuento
    detalle = resultado["detalle_bultos"]
    assert detalle[0]["descuento_multibulto"] == "0%"

    # Segundo y tercer bulto: 50% de descuento
    assert detalle[1]["descuento_multibulto"] == "50%"
    assert detalle[2]["descuento_multibulto"] == "50%"

    # La tarifa del 2do y 3er bulto debe ser ~50% de la del primero
    tarifa_1 = detalle[0]["tarifa_final"]
    tarifa_2 = detalle[1]["tarifa_final"]
    # Puede haber diferencia por tarifa mínima, pero debería ser menor
    assert tarifa_2 <= tarifa_1, f"Tarifa 2do bulto ({tarifa_2}) debería ser <= al primero ({tarifa_1})"

    print("  [OK] Regla Multibulto: 100% / 50% / 50%")


def test_aforo_volumetrico():
    """Prueba que se use el peso volumétrico cuando supera al real."""
    cotizador = Cotizador()
    localidad = Localidad(id_localidad=1, nombre="Formosa Capital", distancia_km=30)

    # Peso volumétrico (20kg) mayor que real (2kg) — caja grande liviana
    bulto = Bulto(id_bulto=1, id_envio=1, peso_real=2.0, peso_volumetrico=20.0)

    resultado = cotizador.calcular_tarifa([bulto], localidad)

    assert resultado["detalle_bultos"][0]["peso_aforo"] == 20.0
    print("  [OK] Aforo: Peso volumétrico tomado cuando supera al real")


def test_factor_zona():
    """Prueba factores de zona según distancia."""
    cotizador = Cotizador()
    bulto = Bulto(id_bulto=1, id_envio=1, peso_real=10.0, peso_volumetrico=5.0)

    zonas = [
        ("Urbano", 30, 1.0),
        ("Periurbano", 120, 1.5),
        ("Interior", 200, 2.0),
        ("Frontera", 450, 2.5),
    ]

    tarifas = []
    for nombre, km, factor_esperado in zonas:
        loc = Localidad(id_localidad=1, nombre=nombre, distancia_km=km)
        resultado = cotizador.calcular_tarifa([bulto], loc)
        assert resultado["factor_zona"] == factor_esperado, \
            f"Factor zona para {nombre} ({km} KM) esperado {factor_esperado}, obtenido {resultado['factor_zona']}"
        tarifas.append(resultado["costo_total"])

    # Verificar que a mayor distancia, mayor tarifa
    for i in range(len(tarifas) - 1):
        assert tarifas[i] <= tarifas[i + 1], \
            f"Tarifa zona {zonas[i][0]} ({tarifas[i]}) debería ser <= zona {zonas[i+1][0]} ({tarifas[i+1]})"

    print("  [OK] Factor de zona: tarifas crecen con la distancia")


def test_seguro_excedente():
    """Prueba costo de seguro cuando valor declarado supera cobertura."""
    cotizador = Cotizador()
    localidad = Localidad(id_localidad=1, nombre="Test", distancia_km=50)
    bulto = Bulto(id_bulto=1, id_envio=1, peso_real=5.0, peso_volumetrico=3.0)
    seguro = Seguro(id_seguro=1, cobertura_estandar=50000, porcentaje_excedente=2.0)

    # Sin excedente
    r1 = cotizador.calcular_tarifa([bulto], localidad, valor_declarado=30000, seguro=seguro)
    assert r1["costo_seguro"] == 0.0

    # Con excedente: (100000 - 50000) * 2% = 1000
    r2 = cotizador.calcular_tarifa([bulto], localidad, valor_declarado=100000, seguro=seguro)
    assert r2["costo_seguro"] == 1000.0
    assert r2["costo_total"] == r2["subtotal_flete"] + 1000.0

    print("  [OK] Seguro: Cálculo de excedente integrado en cotización")


def test_recargo_fragil():
    """Prueba recargo por paquete frágil."""
    cotizador = Cotizador()
    localidad = Localidad(id_localidad=1, nombre="Test", distancia_km=100)

    bulto_normal = Bulto(id_bulto=1, id_envio=1, peso_real=10.0, peso_volumetrico=5.0, es_fragil=False)
    bulto_fragil = Bulto(id_bulto=2, id_envio=1, peso_real=10.0, peso_volumetrico=5.0, es_fragil=True)

    r_normal = cotizador.calcular_tarifa([bulto_normal], localidad)
    r_fragil = cotizador.calcular_tarifa([bulto_fragil], localidad)

    assert r_fragil["costo_total"] >= r_normal["costo_total"], \
        "El bulto frágil debería costar igual o más que el normal"

    print("  [OK] Recargo: Bulto frágil cuesta más que normal")


def test_sin_bultos_error():
    """Prueba que cotizar sin bultos lance error."""
    cotizador = Cotizador()
    localidad = Localidad(id_localidad=1, nombre="Test", distancia_km=50)

    try:
        cotizador.calcular_tarifa([], localidad)
        assert False, "Debería lanzar CotizacionError sin bultos"
    except CotizacionError:
        pass

    print("  [OK] Error: Cotización sin bultos rechazada")


def test_cotizacion_completa_ejemplo_real():
    """Prueba de cotización completa simulando un caso real de la empresa.

    Escenario: 3 bultos a Clorinda (120 KM, zona periurbana).
    Bulto 1: 15kg real, 8kg vol → aforo 15kg → 100% tarifa
    Bulto 2: 5kg real, 12kg vol → aforo 12kg → 50% descuento
    Bulto 3: 3kg real, 3kg vol (frágil) → aforo 3kg → 50% desc + recargo frágil
    Seguro: valor declarado $80.000, cobertura $50.000, excedente 2%
    """
    cotizador = Cotizador()
    localidad = Localidad(id_localidad=2, nombre="Clorinda", distancia_km=120)
    seguro = Seguro(id_seguro=1, cobertura_estandar=50000, porcentaje_excedente=2.0)

    bultos = [
        Bulto(id_bulto=1, id_envio=1, peso_real=15.0, peso_volumetrico=8.0),
        Bulto(id_bulto=2, id_envio=1, peso_real=5.0, peso_volumetrico=12.0),
        Bulto(id_bulto=3, id_envio=1, peso_real=3.0, peso_volumetrico=3.0, es_fragil=True),
    ]

    resultado = cotizador.calcular_tarifa(bultos, localidad, valor_declarado=80000, seguro=seguro)

    assert resultado["cantidad_bultos"] == 3
    assert resultado["localidad_destino"] == "Clorinda"
    assert resultado["factor_zona"] == 1.5  # Periurbano
    assert resultado["costo_seguro"] == 600.0  # (80000 - 50000) * 2%
    assert resultado["costo_total"] > 0

    print(f"  [OK] Cotización real: 3 bultos a Clorinda = ${resultado['costo_total']}")
    print(f"       Desglose flete: ${resultado['subtotal_flete']} + Seguro: ${resultado['costo_seguro']}")

    for d in resultado["detalle_bultos"]:
        print(f"       Bulto {d['bulto_nro']}: aforo={d['peso_aforo']}kg, "
              f"desc={d['descuento_multibulto']}, tarifa=${d['tarifa_final']}")


def main():
    print("\n--- Pruebas Sprint 2 (Cotizador) ---")
    test_cotizacion_simple()
    test_regla_multibulto()
    test_aforo_volumetrico()
    test_factor_zona()
    test_seguro_excedente()
    test_recargo_fragil()
    test_sin_bultos_error()
    test_cotizacion_completa_ejemplo_real()
    print("--- Todas las pruebas del cotizador pasaron ---\n")


if __name__ == "__main__":
    main()
