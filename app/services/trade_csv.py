from __future__ import annotations

import csv
from dataclasses import dataclass
from typing import TextIO

from pydantic import ValidationError

from app.schemas.trade import TradeCreate

REQUIRED_HEADERS = (
    "symbol",
    "side",
    "entry_price",
    "quantity",
    "opened_at",
)
OPTIONAL_HEADERS = (
    "exit_price",
    "closed_at",
    "pnl",
    "notes",
)
ALLOWED_HEADERS = REQUIRED_HEADERS + OPTIONAL_HEADERS
ROW_ERROR_FIELD = "__row__"


class InvalidTradeCsvHeaderError(ValueError):
    def __init__(
        self,
        *,
        missing_headers: tuple[str, ...] = (),
        unexpected_headers: tuple[str, ...] = (),
        duplicate_headers: tuple[str, ...] = (),
        has_no_header: bool = False,
        has_empty_header: bool = False,
    ) -> None:
        self.missing_headers = missing_headers
        self.unexpected_headers = unexpected_headers
        self.duplicate_headers = duplicate_headers

        message_parts: list[str] = []
        if has_no_header:
            message_parts.append("Trade CSV header is missing")
        if has_empty_header:
            message_parts.append("Trade CSV header contains an empty column name")
        if missing_headers:
            message_parts.append(
                "Missing required headers: " + ", ".join(missing_headers)
            )
        if unexpected_headers:
            message_parts.append("Unexpected headers: " + ", ".join(unexpected_headers))
        if duplicate_headers:
            message_parts.append("Duplicate headers: " + ", ".join(duplicate_headers))

        super().__init__("; ".join(message_parts))


@dataclass(frozen=True)
class TradeCsvFieldError:
    field: str
    message: str


@dataclass(frozen=True)
class TradeCsvRowError:
    row_number: int
    errors: tuple[TradeCsvFieldError, ...]


@dataclass(frozen=True)
class TradeCsvParseResult:
    total_rows: int
    valid_trades: tuple[TradeCreate, ...]
    row_errors: tuple[TradeCsvRowError, ...]

    def __post_init__(self) -> None:
        if self.total_rows != self.valid_rows + self.rejected_rows:
            raise ValueError("total_rows must equal valid_rows plus rejected_rows")

    @property
    def valid_rows(self) -> int:
        return len(self.valid_trades)

    @property
    def rejected_rows(self) -> int:
        return len(self.row_errors)


def parse_trade_csv(stream: TextIO) -> TradeCsvParseResult:
    reader = csv.DictReader(stream)
    _validate_headers(reader.fieldnames)
    reader.fieldnames = _normalize_headers(reader.fieldnames)

    valid_trades: list[TradeCreate] = []
    row_errors: list[TradeCsvRowError] = []
    total_rows = 0

    for row in reader:
        row_number = reader.line_num
        if _is_blank_row(row):
            continue

        total_rows += 1

        if None in row:
            row_errors.append(
                TradeCsvRowError(
                    row_number=row_number,
                    errors=(
                        TradeCsvFieldError(
                            field=ROW_ERROR_FIELD,
                            message="Unexpected extra values in row",
                        ),
                    ),
                )
            )
            continue

        normalized_row = _normalize_row(row)
        try:
            valid_trades.append(TradeCreate.model_validate(normalized_row))
        except ValidationError as exc:
            row_errors.append(
                TradeCsvRowError(
                    row_number=row_number,
                    errors=_convert_validation_error(exc),
                )
            )

    return TradeCsvParseResult(
        total_rows=total_rows,
        valid_trades=tuple(valid_trades),
        row_errors=tuple(row_errors),
    )


def _validate_headers(fieldnames: list[str] | None) -> None:
    if fieldnames is None:
        raise InvalidTradeCsvHeaderError(has_no_header=True)

    normalized_headers = _normalize_headers(fieldnames)
    if any(header == "" for header in normalized_headers):
        raise InvalidTradeCsvHeaderError(has_empty_header=True)

    seen_headers: set[str] = set()
    duplicate_headers: list[str] = []
    for header in normalized_headers:
        if header in seen_headers and header not in duplicate_headers:
            duplicate_headers.append(header)
        seen_headers.add(header)

    header_set = set(normalized_headers)
    missing_headers = tuple(
        header for header in REQUIRED_HEADERS if header not in header_set
    )
    unexpected_headers = tuple(
        header for header in normalized_headers if header not in ALLOWED_HEADERS
    )

    if missing_headers or unexpected_headers or duplicate_headers:
        raise InvalidTradeCsvHeaderError(
            missing_headers=missing_headers,
            unexpected_headers=unexpected_headers,
            duplicate_headers=tuple(duplicate_headers),
        )


def _normalize_headers(fieldnames: list[str] | None) -> list[str]:
    if fieldnames is None:
        return []
    return [header.strip() for header in fieldnames]


def _is_blank_row(row: dict[str | None, str | list[str] | None]) -> bool:
    return all(_is_blank_value(value) for value in row.values())


def _is_blank_value(value: str | list[str] | None) -> bool:
    if value is None:
        return True
    if isinstance(value, list):
        return all(_is_blank_value(item) for item in value)
    return value.strip() == ""


def _normalize_row(row: dict[str, str | None]) -> dict[str, str | None]:
    normalized_row: dict[str, str | None] = {}
    for field, value in row.items():
        stripped_value = value.strip() if isinstance(value, str) else value
        if field in OPTIONAL_HEADERS and stripped_value == "":
            normalized_row[field] = None
            continue
        normalized_row[field] = stripped_value

    return normalized_row


def _convert_validation_error(
    exc: ValidationError,
) -> tuple[TradeCsvFieldError, ...]:
    return tuple(
        TradeCsvFieldError(
            field=_format_error_location(error["loc"]),
            message=error["msg"],
        )
        for error in exc.errors()
    )


def _format_error_location(location: tuple[object, ...]) -> str:
    if not location:
        return ROW_ERROR_FIELD
    return ".".join(str(part) for part in location)
