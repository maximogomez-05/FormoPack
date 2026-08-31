"""
Generador de Comprobante Interno PDF — ReportLab
Comprobante de Control Interno (NO FISCAL)
"""

from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT


def generar_comprobante_pdf(envio: dict, detalle: dict) -> bytes:
    """Genera el PDF del Comprobante de Control Interno.

    Args:
        envio: Diccionario con datos del envío (resultado de query BD).
        detalle: Diccionario con bultos y pago asociado.

    Returns:
        Bytes del PDF generado.
    """
    import io
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()

    # Estilos personalizados
    estilo_titulo = ParagraphStyle(
        "titulo",
        parent=styles["Heading1"],
        fontSize=18,
        textColor=colors.HexColor("#1a1a2e"),
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    estilo_subtitulo = ParagraphStyle(
        "subtitulo",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#555555"),
        alignment=TA_CENTER,
        spaceAfter=2,
    )
    estilo_no_fiscal = ParagraphStyle(
        "no_fiscal",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#cc0000"),
        alignment=TA_CENTER,
        spaceAfter=12,
    )
    estilo_label = ParagraphStyle(
        "label",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#666666"),
    )
    estilo_valor = ParagraphStyle(
        "valor",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#1a1a2e"),
        fontName="Helvetica-Bold",
    )
    estilo_nro_guia = ParagraphStyle(
        "nro_guia",
        parent=styles["Normal"],
        fontSize=22,
        textColor=colors.HexColor("#e94560"),
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        spaceBefore=8,
        spaceAfter=8,
    )

    elementos = []

    # ── ENCABEZADO ──
    elementos.append(Paragraph("FORMOPACK LOGÍSTICA", estilo_titulo))
    elementos.append(Paragraph("Sistema de Gestión Operativa", estilo_subtitulo))
    elementos.append(Paragraph(
        "DOCUMENTO DE CONTROL INTERNO — NO VÁLIDO COMO FACTURA",
        estilo_no_fiscal,
    ))
    elementos.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#e94560")))
    elementos.append(Spacer(1, 0.3 * cm))

    # ── NÚMERO DE GUÍA ──
    nro_guia = envio.get("nro_guia", "N/A")
    elementos.append(Paragraph(f"Guía: {nro_guia}", estilo_nro_guia))
    elementos.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#dddddd")))
    elementos.append(Spacer(1, 0.4 * cm))

    # ── DATOS DEL ENVÍO ──
    fecha_str = ""
    if envio.get("fecha_creacion"):
        try:
            fc = envio["fecha_creacion"]
            if hasattr(fc, "strftime"):
                fecha_str = fc.strftime("%d/%m/%Y %H:%M")
            else:
                fecha_str = str(fc)
        except Exception:
            fecha_str = str(envio.get("fecha_creacion", ""))

    datos_envio = [
        ["Fecha de emisión:", fecha_str or datetime.now().strftime("%d/%m/%Y %H:%M")],
        ["Estado:", (envio.get("estado_actual", "")).upper()],
        ["Modalidad de pago:", (envio.get("modalidad_pago", "")).upper()],
    ]

    tabla_info = Table(datos_envio, colWidths=[5 * cm, 11 * cm])
    tabla_info.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#555555")),
        ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#1a1a2e")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elementos.append(tabla_info)
    elementos.append(Spacer(1, 0.4 * cm))

    # ── REMITENTE / DESTINATARIO ──
    elementos.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#dddddd")))
    elementos.append(Spacer(1, 0.3 * cm))

    datos_partes = [
        ["REMITENTE", "DESTINATARIO"],
        [
            envio.get("remitente", "N/A"),
            envio.get("destinatario", "N/A"),
        ],
        [
            f"DNI: {envio.get('rem_dni', 'N/A')}",
            f"DNI: {envio.get('dest_dni', 'N/A')}",
        ],
        [
            f"Tel: {envio.get('rem_tel', 'N/A')}",
            f"Tel: {envio.get('dest_tel', 'N/A')}",
        ],
    ]

    tabla_partes = Table(datos_partes, colWidths=[8 * cm, 8 * cm])
    tabla_partes.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
    ]))
    elementos.append(tabla_partes)
    elementos.append(Spacer(1, 0.4 * cm))

    # ── DESTINO ──
    elementos.append(Paragraph(
        f"<b>Destino:</b> {envio.get('localidad_destino', 'N/A')} — {envio.get('direccion_destino', 'N/A')}",
        styles["Normal"],
    ))
    elementos.append(Spacer(1, 0.4 * cm))

    # ── BULTOS ──
    bultos = detalle.get("bultos", [])
    if bultos:
        elementos.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#dddddd")))
        elementos.append(Spacer(1, 0.3 * cm))

        encabezado_bultos = [["#", "Peso Real (kg)", "Peso Vol. (kg)", "Aforo (kg)", "Frágil"]]
        filas_bultos = []
        for i, b in enumerate(bultos, 1):
            peso_real = float(b.get("peso_real", 0))
            peso_vol = float(b.get("peso_volumetrico", 0))
            aforo = max(peso_real, peso_vol)
            fragil = "SÍ" if b.get("es_fragil") else "NO"
            filas_bultos.append([str(i), f"{peso_real:.2f}", f"{peso_vol:.2f}", f"{aforo:.2f}", fragil])

        tabla_bultos = Table(
            encabezado_bultos + filas_bultos,
            colWidths=[1.5 * cm, 3.5 * cm, 3.5 * cm, 3.5 * cm, 2 * cm],
        )
        tabla_bultos.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e94560")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9f9f9")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ]))
        elementos.append(tabla_bultos)
        elementos.append(Spacer(1, 0.4 * cm))

    # ── TOTALES ──
    elementos.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1a1a2e")))
    elementos.append(Spacer(1, 0.3 * cm))

    costo_total = float(envio.get("costo_total", 0))
    pago = detalle.get("pago")
    monto_pago = float(pago.get("monto", 0)) if pago else 0
    tipo_pago = (pago.get("tipo_pago", "efectivo")).upper() if pago else "—"

    datos_total = [
        ["Subtotal:", f"${costo_total:.2f}"],
        ["Tipo de cobro:", tipo_pago],
        ["TOTAL COBRADO:", f"${monto_pago:.2f}"],
    ]

    tabla_total = Table(datos_total, colWidths=[12 * cm, 4 * cm])
    tabla_total.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
        ("FONTSIZE", (0, 2), (-1, 2), 13),
        ("TEXTCOLOR", (0, 2), (-1, 2), colors.HexColor("#e94560")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elementos.append(tabla_total)
    elementos.append(Spacer(1, 1 * cm))

    # ── PIE ──
    elementos.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#dddddd")))
    pie_estilo = ParagraphStyle("pie", parent=styles["Normal"], fontSize=8,
                                 textColor=colors.HexColor("#999999"), alignment=TA_CENTER)
    elementos.append(Paragraph(
        "Este documento es un comprobante de control interno y no tiene valor fiscal. "
        f"Emitido el {datetime.now().strftime('%d/%m/%Y a las %H:%M')}.",
        pie_estilo,
    ))

    doc.build(elementos)
    buffer.seek(0)
    return buffer.read()
