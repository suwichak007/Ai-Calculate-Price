"""
export_pdf.py — PDF report generator
  - generate_pdf(result: dict) → bytes

  Requires: reportlab
  pip install reportlab
"""

import io
import os
from datetime import datetime


def generate_pdf(result: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
    )
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    # ── Font: ลองโหลด Thai font ก่อน fallback เป็น Helvetica ────
    FONT      = "Helvetica"
    FONT_BOLD = "Helvetica-Bold"
    thai_font_paths = [
        "/usr/share/fonts/truetype/tlwg/Sarabun.ttf",
        "/usr/share/fonts/truetype/tlwg/Norasi.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansThai-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
    ]
    for fp in thai_font_paths:
        if os.path.exists(fp):
            try:
                pdfmetrics.registerFont(TTFont("Thai", fp))
                FONT = FONT_BOLD = "Thai"
                break
            except Exception:
                pass

    # ── Colors ────────────────────────────────────────────────
    DARK_BLUE = colors.HexColor("#1E3A5F")
    MID_BLUE  = colors.HexColor("#2563EB")
    LIGHT_BLUE= colors.HexColor("#EFF6FF")
    ACCENT    = colors.HexColor("#7C3AED")
    GREEN     = colors.HexColor("#059669")
    GREEN_LT  = colors.HexColor("#ECFDF5")
    GRAY_HDR  = colors.HexColor("#F1F5F9")
    GRAY_LINE = colors.HexColor("#E2E8F0")
    GRAY_TXT  = colors.HexColor("#64748B")
    WHITE     = colors.white

    def baht(n):  return f"\u0e3f{int(n):,}"
    def pct(n):   return f"{n:.2f}%"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=16*mm,  bottomMargin=16*mm,
    )
    story = []
    W = A4[0] - 36*mm  # usable width

    # ── Title ──────────────────────────────────────────────────
    title_data = [[
        Paragraph(
            '<font size="18" color="white"><b>ใบประเมินค่าใช้จ่าย Manday</b></font><br/>'
            '<font size="11" color="#BFCFFD">Manday Cost Estimate</font>',
            ParagraphStyle("t", fontName=FONT, alignment=TA_CENTER),
        )
    ]]
    title_tbl = Table(title_data, colWidths=[W])
    title_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), DARK_BLUE),
        ("TOPPADDING",    (0,0), (-1,-1), 14),
        ("BOTTOMPADDING", (0,0), (-1,-1), 14),
        ("ROUNDEDCORNERS", [8]),
    ]))
    story.append(title_tbl)
    story.append(Spacer(1, 6*mm))

    # ── Meta block ─────────────────────────────────────────────
    meta_data = [
        ["ผู้จัดทำ / ผู้ขอ",     result["requester_name"]],
        ["ชื่อโครงการ / ลูกค้า", result["project_name"]],
        ["วันที่จัดทำ",           datetime.now().strftime("%d/%m/%Y %H:%M")],
    ]
    meta_tbl = Table(meta_data, colWidths=[W*0.36, W*0.64])
    meta_tbl.setStyle(TableStyle([
        ("FONTNAME",      (0,0), (-1,-1), FONT),
        ("FONTSIZE",      (0,0), (-1,-1), 10),
        ("FONTNAME",      (0,0), (0,-1),  FONT_BOLD),
        ("TEXTCOLOR",     (0,0), (0,-1),  GRAY_TXT),
        ("BACKGROUND",    (0,0), (0,-1),  GRAY_HDR),
        ("BACKGROUND",    (1,0), (1,-1),  WHITE),
        ("GRID",          (0,0), (-1,-1), 0.5, GRAY_LINE),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 5*mm))

    # ── Section table helper ───────────────────────────────────
    def section_tbl(rows, col_w=None, header=None, header_color=MID_BLUE):
        if col_w is None:
            col_w = [W*0.55, W*0.45]
        data = []
        style_cmds = [
            ("FONTNAME",      (0,0), (-1,-1), FONT),
            ("FONTSIZE",      (0,0), (-1,-1), 10),
            ("GRID",          (0,0), (-1,-1), 0.4, GRAY_LINE),
            ("LEFTPADDING",   (0,0), (-1,-1), 8),
            ("RIGHTPADDING",  (0,0), (-1,-1), 8),
            ("TOPPADDING",    (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ]
        row_offset = 0
        if header:
            data.append([
                Paragraph(
                    f'<font color="white"><b>{header}</b></font>',
                    ParagraphStyle("h", fontName=FONT_BOLD, fontSize=11),
                )
            ])
            style_cmds += [
                ("SPAN",          (0,0), (-1,0)),
                ("BACKGROUND",    (0,0), (-1,0), header_color),
                ("TOPPADDING",    (0,0), (-1,0), 7),
                ("BOTTOMPADDING", (0,0), (-1,0), 7),
            ]
            row_offset = 1

        for i, (label, val, *opts) in enumerate(rows):
            r = i + row_offset
            bg    = opts[0] if opts else WHITE
            align = opts[1] if len(opts) > 1 else TA_RIGHT
            data.append([
                Paragraph(str(label), ParagraphStyle("l", fontName=FONT, fontSize=10)),
                Paragraph(str(val),   ParagraphStyle("v", fontName=FONT, fontSize=10, alignment=align)),
            ])
            if bg != WHITE:
                style_cmds.append(("BACKGROUND", (0,r), (-1,r), bg))

        tbl = Table(data, colWidths=col_w)
        tbl.setStyle(TableStyle(style_cmds))
        return tbl

    # ── Section 1: ข้อมูลพื้นฐาน ──────────────────────────────
    story.append(section_tbl([
        ("Manday รวมทุก Phase",     f"{int(result['manday'])} วัน", LIGHT_BLUE),
        ("Markup %",                pct(result["markup_pct"])),
    ], header="📋  ข้อมูลพื้นฐาน"))
    story.append(Spacer(1, 4*mm))

    # ── Section 2: ต้นทุนแยก 3 Phase ───────────────────────────
    phase_rows = [("Phase / หัวเรื่อง", "คน", "ครั้ง", "วัน/ครั้ง", "Rate", "ต้นทุน")]
    phase_total_rows = []
    for phase in result.get("phase_costs", []):
        phase_total_rows.append(len(phase_rows))
        phase_rows.append((
            phase["label"],
            "",
            "",
            "",
            f"{int(phase['manday'])} md",
            baht(phase["cost"]),
        ))
        for item in phase.get("items", []):
            phase_rows.append((
                item["title"],
                f"{int(item['person'])}",
                f"{int(item['times'])}",
                f"{int(item['days'])}",
                baht(item["rate"]),
                baht(item["cost"]),
            ))
    phase_rows += [
        ("รวมต้นทุน 3 Phase", "", "", "", "", baht(result.get("subtotal_cost", 0))),
        (f"กำไรหลังรวม 3 Phase ({result['markup_pct']}%)", "", "", "", "", baht(result.get("profit", 0))),
    ]
    phase_tbl = Table(phase_rows, colWidths=[W*.24, W*.10, W*.10, W*.13, W*.18, W*.25])
    style_cmds = [
        ("FONTNAME",      (0,0), (-1,-1), FONT),
        ("FONTSIZE",      (0,0), (-1,-1), 9),
        ("BACKGROUND",    (0,0), (-1,0), MID_BLUE),
        ("TEXTCOLOR",     (0,0), (-1,0), WHITE),
        ("FONTNAME",      (0,0), (-1,0), FONT_BOLD),
        ("ALIGN",         (1,1), (-1,-1), "RIGHT"),
        ("BACKGROUND",    (0,-2), (-1,-2), GRAY_HDR),
        ("BACKGROUND",    (0,-1), (-1,-1), LIGHT_BLUE),
        ("GRID",          (0,0), (-1,-1), 0.4, GRAY_LINE),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("RIGHTPADDING",  (0,0), (-1,-1), 6),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]
    for r in phase_total_rows:
        style_cmds.extend([
            ("BACKGROUND", (0,r), (-1,r), LIGHT_BLUE),
            ("FONTNAME", (0,r), (-1,r), FONT_BOLD),
            ("TEXTCOLOR", (0,r), (-1,r), MID_BLUE),
        ])
    phase_tbl.setStyle(TableStyle(style_cmds))
    story.append(section_tbl([], header="💰  ต้นทุนและราคาขาย"))
    story.append(phase_tbl)
    story.append(Spacer(1, 4*mm))

    # ── Section 3: ค่าเดินทาง ──────────────────────────────────
    td = result.get("travel_detail", {})
    travel_items = [
        (k, baht(v)) for k, v in [
            ("ค่าน้ำมัน",    td.get("fuel", 0)),
            ("ค่าโรงแรม",    td.get("hotel", 0)),
            ("เบี้ยเลี้ยง",   td.get("allowance", 0)),
            ("ค่าเครื่องบิน", td.get("flight", 0)),
            ("ค่าเช่ารถ",    td.get("rental", 0)),
            ("ค่า Taxi",     td.get("taxi", 0)),
            ("เบี้ยเดินทาง", td.get("travel_allow", 0)),
        ] if v > 0
    ]
    if travel_items:
        story.append(section_tbl(travel_items, header="✈️  รายละเอียดค่าเดินทาง (ต่อหน่วย)"))
        story.append(Spacer(1, 4*mm))

    # ── Grand total ────────────────────────────────────────────
    total_data = [[
        Paragraph(
            '<font color="white"><b>🏆  ยอดรวมทั้งหมด</b></font>',
            ParagraphStyle("tl", fontName=FONT_BOLD, fontSize=13),
        ),
        Paragraph(
            f'<font color="#059669"><b>{baht(result["total"])}</b></font>',
            ParagraphStyle("tv", fontName=FONT_BOLD, fontSize=14, alignment=TA_RIGHT),
        ),
    ]]
    total_tbl = Table(total_data, colWidths=[W*0.55, W*0.45])
    total_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (0,0), DARK_BLUE),
        ("BACKGROUND",    (1,0), (1,0), GREEN_LT),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ("GRID",          (0,0), (-1,-1), 1, GREEN),
        ("ROUNDEDCORNERS", [6]),
    ]))
    story.append(total_tbl)
    story.append(Spacer(1, 8*mm))

    # ── Footer ──────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", color=GRAY_LINE))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        f'จัดทำโดย: {result["requester_name"]}   |   '
        f'วันที่: {datetime.now().strftime("%d/%m/%Y")}   |   Manday Cost Chatbot',
        ParagraphStyle("footer", fontName=FONT, fontSize=8,
                       textColor=GRAY_TXT, alignment=TA_CENTER),
    ))

    doc.build(story)
    buf.seek(0)
    return buf.read()
