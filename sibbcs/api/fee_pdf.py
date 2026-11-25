# Copyright (c) 2026, South India Baptist Bible College & Seminary and contributors
# For license information, please see license.txt
"""A student's receipt and statement of account, drawn as PDFs.

Why this draws the page itself instead of rendering HTML. Frappe's own PDF path
(`frappe.utils.pdf.get_pdf`) shells out to `wkhtmltopdf`, which is not installed
on the college server and needs root to install. WeasyPrint is in the bench
environment, but it needs the system Pango library, which also needs root. This
module uses `reportlab`, which is plain Python, installs into the bench
environment with no root, and has no system dependency to go missing.

Drawing the layout directly (rather than converting HTML) also removes a whole
class of problem: a student's name or a payment reference is typed by a person,
and here it is only ever text in a table cell, never markup a renderer
interprets. `_text()` escapes it for reportlab's small paragraph markup anyway.

**The rupee sign needs a font that has it.** The standard PDF fonts do not. This
looks for DejaVu Sans (installed on the college server) and, if it is not there,
falls back to Helvetica and writes "Rs." in place of the sign, rather than
printing an empty box where the amount's currency should be. DejaVu does not
cover Indic scripts, so a name written in Tamil or Devanagari would print as
boxes; names in this system are entered in Latin script.
"""

import io
import os
import re
from xml.sax.saxutils import escape

import frappe
from frappe import _
from frappe.utils import flt, fmt_money, formatdate, today

COLLEGE_NAME = "South India Baptist Bible College & Seminary"
FOOTER = "This is a computer-generated document and needs no signature."

# Where DejaVu Sans lives on the distributions this might run on.
FONT_DIRS = (
	"/usr/share/fonts/truetype/dejavu",
	"/usr/share/fonts/dejavu",
	"/usr/share/fonts/TTF",
	"/usr/local/share/fonts",
)

INK = "#1c1e26"
MUTED = "#555a6e"
FAINT = "#7a7f93"
RULE = "#c8cad6"
HAIR = "#e6e7ee"
ACCENT = "#2d2a8c"

_fonts_cache = None

# Control characters other than tab and newline: they are legal in a database
# string and illegal in the XML reportlab parses a paragraph as.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _fonts():
	"""(regular, bold, has_rupee_sign) -- registered once per process."""
	global _fonts_cache
	if _fonts_cache:
		return _fonts_cache

	from reportlab.pdfbase import pdfmetrics
	from reportlab.pdfbase.ttfonts import TTFont

	for directory in FONT_DIRS:
		regular = os.path.join(directory, "DejaVuSans.ttf")
		bold = os.path.join(directory, "DejaVuSans-Bold.ttf")
		if os.path.exists(regular) and os.path.exists(bold):
			pdfmetrics.registerFont(TTFont("SibbcsSans", regular))
			pdfmetrics.registerFont(TTFont("SibbcsSans-Bold", bold))
			pdfmetrics.registerFontFamily("SibbcsSans", normal="SibbcsSans", bold="SibbcsSans-Bold")
			_fonts_cache = ("SibbcsSans", "SibbcsSans-Bold", True)
			return _fonts_cache

	_fonts_cache = ("Helvetica", "Helvetica-Bold", False)
	return _fonts_cache


def _plain(value):
	"""A value as text safe to draw: no control characters, and no rupee sign
	where the font has none."""
	text = _CONTROL.sub("", "" if value is None else str(value))
	if not _fonts()[2]:
		text = text.replace("₹", "Rs. ")
	return text


def _text(value):
	"""A value as reportlab paragraph markup that shows it literally."""
	return escape(_plain(value))


def _money(value):
	return fmt_money(flt(value), precision=2, currency="INR")


def _date(value):
	return formatdate(value, "dd MMM yyyy") if value else "—"


def _styles():
	from reportlab.lib import colors
	from reportlab.lib.enums import TA_RIGHT
	from reportlab.lib.styles import ParagraphStyle

	regular, bold, _rupee = _fonts()

	def style(name, **kw):
		kw.setdefault("fontName", regular)
		kw.setdefault("fontSize", 9)
		kw.setdefault("leading", kw["fontSize"] * 1.3)
		kw.setdefault("textColor", colors.HexColor(INK))
		return ParagraphStyle(name, **kw)

	muted = colors.HexColor(MUTED)
	return {
		"college": style("college", fontSize=8, textColor=muted),
		"title": style("title", fontName=bold, fontSize=19, leading=23),
		"h2": style("h2", fontName=bold, fontSize=11, leading=14, spaceBefore=14, spaceAfter=5),
		"body": style("body"),
		"muted": style("muted", textColor=muted),
		"label": style("label", textColor=muted),
		"value": style("value"),
		"strong": style("strong", fontName=bold),
		"total": style("total", fontName=bold, fontSize=15, leading=19),
		"th": style("th", fontName=bold, fontSize=7.5, textColor=muted),
		"th_num": style("th_num", fontName=bold, fontSize=7.5, textColor=muted, alignment=TA_RIGHT),
		"num": style("num", alignment=TA_RIGHT),
	}


def _paragraph(markup, style):
	from reportlab.platypus import Paragraph

	return Paragraph(markup, style)


def _spacer(height):
	from reportlab.platypus import Spacer

	return Spacer(1, height)


def _who(header, s, width):
	"""Who the document is about."""
	from reportlab.platypus import Table, TableStyle

	rows = [
		(_("Student"), header.get("student_name")),
		(_("Student ID"), header.get("student")),
		(_("Programme"), header.get("program_name") or header.get("program")),
	]
	table = Table(
		[[_paragraph(_text(k), s["label"]), _paragraph(_text(v), s["value"])] for k, v in rows],
		colWidths=[width * 0.22, width * 0.78],
	)
	table.setStyle(
		TableStyle(
			[
				("VALIGN", (0, 0), (-1, -1), "TOP"),
				("LEFTPADDING", (0, 0), (-1, -1), 0),
				("TOPPADDING", (0, 0), (-1, -1), 1.5),
				("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
			]
		)
	)
	return table


def _grid(rows, widths, s, numeric_from, head):
	"""A ruled table with a header row, long cells wrapping, numbers right."""
	from reportlab.lib import colors
	from reportlab.platypus import Table, TableStyle

	header = [
		_paragraph(_text(label), s["th_num"] if i >= numeric_from else s["th"])
		for i, label in enumerate(head)
	]
	table = Table([header, *rows], colWidths=widths, repeatRows=1)
	table.setStyle(
		TableStyle(
			[
				("VALIGN", (0, 0), (-1, -1), "TOP"),
				("LEFTPADDING", (0, 0), (-1, -1), 4),
				("RIGHTPADDING", (0, 0), (-1, -1), 4),
				("TOPPADDING", (0, 0), (-1, -1), 5),
				("BOTTOMPADDING", (0, 0), (-1, -1), 5),
				("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.HexColor(RULE)),
				("LINEBELOW", (0, 1), (-1, -1), 0.4, colors.HexColor(HAIR)),
			]
		)
	)
	return table


def _boxed(inner, width):
	"""A thin outline around one table."""
	from reportlab.lib import colors
	from reportlab.platypus import Table, TableStyle

	box = Table([[inner]], colWidths=[width])
	box.setStyle(
		TableStyle(
			[
				("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor(RULE)),
				("LEFTPADDING", (0, 0), (-1, -1), 10),
				("RIGHTPADDING", (0, 0), (-1, -1), 10),
				("TOPPADDING", (0, 0), (-1, -1), 8),
				("BOTTOMPADDING", (0, 0), (-1, -1), 8),
			]
		)
	)
	return box


def _facts(rows, s, width):
	"""Label / value pairs. A value may be a ready paragraph (for big figures)."""
	from reportlab.platypus import Table, TableStyle

	cells = [
		[
			_paragraph(_text(label), s["label"]),
			value if hasattr(value, "wrap") else _paragraph(_text(value), s["value"]),
		]
		for label, value in rows
	]
	table = Table(cells, colWidths=[width * 0.28, width * 0.72])
	table.setStyle(
		TableStyle(
			[
				("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
				("LEFTPADDING", (0, 0), (-1, -1), 0),
				("TOPPADDING", (0, 0), (-1, -1), 2.5),
				("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
			]
		)
	)
	return table


def _document(title, story_for):
	"""Wrap a body in the college letterhead and footer; return the PDF bytes."""
	from reportlab.lib import colors
	from reportlab.lib.pagesizes import A4
	from reportlab.lib.units import mm
	from reportlab.platypus import HRFlowable, SimpleDocTemplate

	regular, _bold, _rupee = _fonts()
	margin = 18 * mm
	# The frame pads each side by 6pt. Tables sized to the whole page stick out past
	# that padding and the headings above them look indented.
	width = A4[0] - 2 * margin - 12
	s = _styles()

	story = [
		_paragraph(_text(COLLEGE_NAME.upper()), s["college"]),
		_spacer(3),
		_paragraph(_text(title), s["title"]),
		HRFlowable(
			width="100%", thickness=1.6, color=colors.HexColor(ACCENT), spaceBefore=7, spaceAfter=11
		),
		*story_for(s, width),
	]

	def footer(canvas, doc):
		canvas.saveState()
		canvas.setFont(regular, 7.5)
		canvas.setFillColor(colors.HexColor(FAINT))
		canvas.drawString(margin, 11 * mm, _plain(_(FOOTER)))
		canvas.drawRightString(A4[0] - margin, 11 * mm, _plain(_("Page {0}").format(doc.page)))
		canvas.restoreState()

	buffer = io.BytesIO()
	doc = SimpleDocTemplate(
		buffer,
		pagesize=A4,
		leftMargin=margin,
		rightMargin=margin,
		topMargin=15 * mm,
		bottomMargin=20 * mm,
		title=_plain(title),
		author=COLLEGE_NAME,
	)
	doc.build(story, onFirstPage=footer, onLaterPages=footer)
	return buffer.getvalue()


def receipt_pdf(header, payment):
	"""One payment as a receipt."""

	def body(s, width):
		facts = [
			(_("Receipt no."), _paragraph(_text(payment["name"]), s["strong"])),
			(_("Received on"), _date(payment["received_on"])),
			(_("Paid by"), payment["mode"]),
		]
		if payment["reference_no"]:
			facts.append((_("Reference"), payment["reference_no"]))
		facts.append((_("Amount received"), _paragraph(_text(_money(payment["amount"])), s["total"])))

		story = [_who(header, s, width), _spacer(14), _boxed(_facts(facts, s, width - 20), width)]

		applied = [
			[
				_paragraph(_text(row["invoice"]), s["body"]),
				_paragraph(
					_text((row["fee_type"] or "") + (f" · {row['term']}" if row["term"] else "")),
					s["body"],
				),
				_paragraph(_text(_money(row["amount"])), s["num"]),
			]
			for row in payment["applied_to"]
		]
		if applied:
			story += [
				_paragraph(_text(_("Applied to")), s["h2"]),
				_grid(
					applied,
					[width * 0.26, width * 0.50, width * 0.24],
					s,
					numeric_from=2,
					head=[_("Invoice"), _("For"), _("Amount")],
				),
			]
		if flt(payment["unallocated_amount"]) > 0.005:
			story += [
				_spacer(10),
				_paragraph(
					_text(
						_("{0} of this payment is held as credit against future fees.").format(
							_money(payment["unallocated_amount"])
						)
					),
					s["body"],
				),
			]
		return story

	return _document(_("Payment receipt"), body)


def statement_pdf(header, statement):
	"""The whole account, oldest first, with a running balance."""

	def body(s, width):
		story = [
			_who(header, s, width),
			_spacer(4),
			_paragraph(_text(_("As on {0}").format(_date(today()))), s["muted"]),
			_spacer(8),
		]

		rows = [
			[
				_paragraph(_text(_date(row["date"])), s["body"]),
				_paragraph(
					_text(row["particulars"])
					+ (
						f"<br/><font size='7.5' color='{FAINT}'>{_text(row['reference'])}</font>"
						if row["reference"]
						else ""
					),
					s["body"],
				),
				_paragraph(_text(_money(row["charge"]) if row["charge"] else ""), s["num"]),
				_paragraph(_text(_money(row["credit"]) if row["credit"] else ""), s["num"]),
				_paragraph(_text(_money(row["balance"])), s["num"]),
			]
			for row in statement["rows"]
		]
		if rows:
			story.append(
				_grid(
					rows,
					[width * 0.15, width * 0.37, width * 0.16, width * 0.16, width * 0.16],
					s,
					numeric_from=2,
					head=[_("Date"), _("Particulars"), _("Charge"), _("Paid"), _("Balance")],
				)
			)
		else:
			story.append(_paragraph(_text(_("Nothing has been billed to this account yet.")), s["body"]))

		balance = flt(statement["balance"])
		standing = (
			_("Outstanding") if balance > 0.005 else _("In credit") if balance < -0.005 else _("Settled")
		)
		totals = [
			(_("Total charged"), _money(statement["charges"])),
			(_("Total paid or waived"), _money(statement["credits"])),
			(
				_("Balance"),
				_paragraph(
					f"{_text(_money(abs(balance)))}  <font size='9'>{_text(standing)}</font>", s["total"]
				),
			),
		]
		story += [_spacer(14), _boxed(_facts(totals, s, width - 20), width)]
		return story

	return _document(_("Statement of account"), body)
