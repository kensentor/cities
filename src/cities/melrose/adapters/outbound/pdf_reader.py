"""LogReader over pdfplumber: extracts positioned lines and hands them to the line grammar."""

from __future__ import annotations

import io

import pdfplumber
from pdfminer.pdfparser import PDFSyntaxError
from pdfplumber.utils.exceptions import PdfminerException

from cities.melrose.adapters.outbound.log_grammar import Line, parse
from cities.melrose.domain.entries import ReadLog
from cities.melrose.ports.outbound import LogReader, LogUnreadable

# Characters closer than this are one word; matches how the log's Courier text is spaced.
X_TOLERANCE = 1.5


class PdfLogReader(LogReader):
    __slots__ = ()

    def read(self, pdf: bytes) -> ReadLog:
        try:
            with pdfplumber.open(io.BytesIO(pdf)) as document:
                lines: list[Line] = []
                page_texts: list[str] = []
                for number, page in enumerate(document.pages, start=1):
                    page_texts.append(page.extract_text(x_tolerance=X_TOLERANCE) or "")
                    for extracted in page.extract_text_lines(x_tolerance=X_TOLERANCE):
                        chars = extracted["chars"]
                        lines.append(
                            Line(
                                page=number,
                                text=extracted["text"],
                                x1=float(extracted["x1"]),
                                char_width=float(chars[-1]["x1"] - chars[-1]["x0"]),
                            )
                        )
        except (PdfminerException, PDFSyntaxError, ValueError, KeyError) as exc:
            raise LogUnreadable(str(exc) or type(exc).__name__) from exc
        return parse(lines, page_texts)
