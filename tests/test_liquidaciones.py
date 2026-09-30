"""Tests para el módulo de Liquidaciones de Chofer (RF 5.6)."""

import pytest
from datetime import date

from app.models.liquidacion import Liquidacion


class TestLiquidacionModel:
    """Tests del modelo Liquidacion."""

    def test_crear_liquidacion_basica(self):
        """Verificar creación con datos mínimos."""
        liq = Liquidacion(
            id_chofer=1,
            nombre_chofer="Juan Pérez",
            fecha_desde=date(2026, 9, 1),
            fecha_hasta=date(2026, 9, 30),
        )
        assert liq.id_chofer == 1
        assert liq.nombre_chofer == "Juan Pérez"
        assert liq.total_envios == 0
        assert liq.entregados == 0
        assert liq.fallidos == 0
        assert liq.monto_facturado == 0.0

    def test_calcular_rendimiento_sin_envios(self):
        """Sin envíos, rendimiento es 0%."""
        liq = Liquidacion(
            id_chofer=1,
            nombre_chofer="Test",
            fecha_desde=date(2026, 1, 1),
            fecha_hasta=date(2026, 1, 31),
            total_envios=0,
            entregados=0,
        )
        assert liq.calcular_rendimiento() == 0.0

    def test_calcular_rendimiento_completo(self):
        """10 envíos, 8 entregados = 80%."""
        liq = Liquidacion(
            id_chofer=1,
            nombre_chofer="Test",
            fecha_desde=date(2026, 1, 1),
            fecha_hasta=date(2026, 1, 31),
            total_envios=10,
            entregados=8,
            fallidos=2,
        )
        assert liq.calcular_rendimiento() == 80.0
        assert liq.calcular_tasa_fallo() == 20.0

    def test_calcular_rendimiento_perfecto(self):
        """Todos entregados = 100%."""
        liq = Liquidacion(
            id_chofer=2,
            nombre_chofer="María López",
            fecha_desde=date(2026, 9, 1),
            fecha_hasta=date(2026, 9, 30),
            total_envios=5,
            entregados=5,
            fallidos=0,
        )
        assert liq.calcular_rendimiento() == 100.0
        assert liq.calcular_tasa_fallo() == 0.0

    def test_to_dict_contiene_rendimiento(self):
        """to_dict incluye campos calculados."""
        liq = Liquidacion(
            id_chofer=1,
            nombre_chofer="Test",
            fecha_desde=date(2026, 9, 1),
            fecha_hasta=date(2026, 9, 30),
            total_envios=20,
            entregados=15,
            fallidos=3,
            pendientes=2,
            monto_facturado=45000.0,
            km_recorridos=1200.0,
            total_hojas=4,
        )
        d = liq.to_dict()
        assert d["rendimiento"] == 75.0
        assert d["tasa_fallo"] == 15.0
        assert d["monto_facturado"] == 45000.0
        assert d["km_recorridos"] == 1200.0
        assert d["total_hojas"] == 4
        assert d["pendientes"] == 2
        assert d["fecha_desde"] == "2026-09-01"
        assert d["fecha_hasta"] == "2026-09-30"

    def test_propiedades_privadas(self):
        """Verificar encapsulamiento POO."""
        liq = Liquidacion(
            id_chofer=1,
            nombre_chofer="Test",
            fecha_desde=date(2026, 1, 1),
            fecha_hasta=date(2026, 1, 31),
            total_hojas=3,
            km_recorridos=500.0,
        )
        # Las propiedades son accesibles
        assert liq.total_hojas == 3
        assert liq.km_recorridos == 500.0
        assert liq.hojas_detalle == []

        # Los atributos privados existen con prefijo _
        assert hasattr(liq, '_id_chofer')
        assert hasattr(liq, '_nombre_chofer')
        assert hasattr(liq, '_monto_facturado')

    def test_repr(self):
        """Representación legible del objeto."""
        liq = Liquidacion(
            id_chofer=1,
            nombre_chofer="Carlos",
            fecha_desde=date(2026, 9, 1),
            fecha_hasta=date(2026, 9, 30),
            total_envios=10,
            entregados=7,
        )
        repr_str = repr(liq)
        assert "Carlos" in repr_str
        assert "70.0%" in repr_str

    def test_hojas_detalle_copia_defensiva(self):
        """hojas_detalle retorna una copia, no la lista interna."""
        detalle = [{"nro_despacho": "D-001", "cant_envios": 5}]
        liq = Liquidacion(
            id_chofer=1,
            nombre_chofer="Test",
            fecha_desde=date(2026, 1, 1),
            fecha_hasta=date(2026, 1, 31),
            hojas_detalle=detalle,
        )
        copia = liq.hojas_detalle
        copia.append({"nro_despacho": "D-002"})
        assert len(liq.hojas_detalle) == 1  # Original no modificado


class TestLiquidacionController:
    """Tests del controlador (requieren BD activa)."""

    def test_import_controller(self):
        """Verificar que se puede importar el controlador."""
        from app.controllers.liquidacion_controller import LiquidacionController
        ctrl = LiquidacionController()
        assert ctrl is not None

    def test_validacion_fechas(self):
        """fecha_desde > fecha_hasta debe lanzar ValidationError."""
        from app.controllers.liquidacion_controller import LiquidacionController
        from app.utils.exceptions import ValidationError

        ctrl = LiquidacionController()
        with pytest.raises(ValidationError):
            ctrl.generar_liquidacion(
                id_chofer=1,
                fecha_desde=date(2026, 9, 30),
                fecha_hasta=date(2026, 9, 1),
            )
