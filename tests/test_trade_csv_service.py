from io import StringIO

import pytest

from app.services.trade_csv import (
    InvalidTradeCsvHeaderError,
    parse_trade_csv,
)


def test_parse_trade_csv_accepts_full_valid_row() -> None:
    stream = StringIO(
        "symbol,side,entry_price,quantity,opened_at,exit_price,closed_at,pnl,notes\n"
        "AAPL,long,100.50,2,2024-01-02T10:00:00Z,"
        "110.25,2024-01-02T12:00:00Z,19.50,Planned breakout\n"
    )

    result = parse_trade_csv(stream)

    assert result.total_rows == 1
    assert result.valid_rows == 1
    assert result.rejected_rows == 0
    assert len(result.valid_trades) == 1
    assert result.valid_trades[0].symbol == "AAPL"
    assert result.valid_trades[0].side == "long"
    assert str(result.valid_trades[0].entry_price) == "100.50"
    assert str(result.valid_trades[0].exit_price) == "110.25"
    assert str(result.valid_trades[0].quantity) == "2"
    assert str(result.valid_trades[0].pnl) == "19.50"
    assert result.valid_trades[0].notes == "Planned breakout"
    assert result.row_errors == ()


def test_parse_trade_csv_accepts_required_only_valid_row() -> None:
    stream = StringIO(
        "symbol,side,entry_price,quantity,opened_at\n"
        "MSFT,short,250.75,3,2024-01-02T10:00:00Z\n"
    )

    result = parse_trade_csv(stream)

    trade = result.valid_trades[0]
    assert result.total_rows == 1
    assert result.valid_rows == 1
    assert trade.exit_price is None
    assert trade.closed_at is None
    assert trade.pnl is None
    assert trade.notes is None


def test_parse_trade_csv_accepts_multiple_valid_rows() -> None:
    stream = StringIO(
        "symbol,side,entry_price,quantity,opened_at\n"
        "AAPL,long,100,1,2024-01-02T10:00:00Z\n"
        "TSLA,short,200,2,2024-01-03T10:00:00Z\n"
    )

    result = parse_trade_csv(stream)

    assert result.total_rows == 2
    assert result.valid_rows == 2
    assert result.rejected_rows == 0
    assert tuple(trade.symbol for trade in result.valid_trades) == ("AAPL", "TSLA")


def test_parse_trade_csv_converts_empty_optional_values_to_none() -> None:
    stream = StringIO(
        "symbol,side,entry_price,quantity,opened_at,exit_price,closed_at,pnl,notes\n"
        "AAPL,long,100,1,2024-01-02T10:00:00Z, , , , \n"
    )

    result = parse_trade_csv(stream)

    trade = result.valid_trades[0]
    assert trade.exit_price is None
    assert trade.closed_at is None
    assert trade.pnl is None
    assert trade.notes is None


def test_parse_trade_csv_trims_cell_whitespace() -> None:
    stream = StringIO(
        "symbol,side,entry_price,quantity,opened_at,notes\n"
        "  AAPL  , long , 100.50 , 2 , 2024-01-02T10:00:00Z ,  planned  \n"
    )

    result = parse_trade_csv(stream)

    trade = result.valid_trades[0]
    assert trade.symbol == "AAPL"
    assert trade.side == "long"
    assert str(trade.entry_price) == "100.50"
    assert str(trade.quantity) == "2"
    assert trade.notes == "planned"


def test_parse_trade_csv_normalizes_header_whitespace_only() -> None:
    stream = StringIO(
        " symbol , side , entry_price , quantity , opened_at , notes \n"
        "AAPL,long,100,1,2024-01-02T10:00:00Z,test\n"
    )

    result = parse_trade_csv(stream)

    assert result.total_rows == 1
    assert result.valid_trades[0].notes == "test"


def test_parse_trade_csv_rejects_missing_headers() -> None:
    stream = StringIO("symbol,side,entry_price,quantity\nAAPL,long,100,1\n")

    with pytest.raises(InvalidTradeCsvHeaderError) as exc_info:
        parse_trade_csv(stream)

    assert exc_info.value.missing_headers == ("opened_at",)
    assert exc_info.value.unexpected_headers == ()
    assert exc_info.value.duplicate_headers == ()
    assert str(exc_info.value) == "Missing required headers: opened_at"


def test_parse_trade_csv_rejects_unexpected_headers() -> None:
    stream = StringIO(
        "symbol,side,entry_price,quantity,opened_at,broker\n"
        "AAPL,long,100,1,2024-01-02T10:00:00Z,IBKR\n"
    )

    with pytest.raises(InvalidTradeCsvHeaderError) as exc_info:
        parse_trade_csv(stream)

    assert exc_info.value.missing_headers == ()
    assert exc_info.value.unexpected_headers == ("broker",)
    assert exc_info.value.duplicate_headers == ()
    assert str(exc_info.value) == "Unexpected headers: broker"


def test_parse_trade_csv_rejects_duplicate_headers() -> None:
    stream = StringIO(
        "symbol,side,entry_price,quantity,opened_at, symbol \n"
        "AAPL,long,100,1,2024-01-02T10:00:00Z,MSFT\n"
    )

    with pytest.raises(InvalidTradeCsvHeaderError) as exc_info:
        parse_trade_csv(stream)

    assert exc_info.value.duplicate_headers == ("symbol",)
    assert str(exc_info.value) == "Duplicate headers: symbol"


def test_parse_trade_csv_rejects_empty_header() -> None:
    stream = StringIO(
        "symbol,side,entry_price,quantity,opened_at,\n"
        "AAPL,long,100,1,2024-01-02T10:00:00Z,\n"
    )

    with pytest.raises(InvalidTradeCsvHeaderError) as exc_info:
        parse_trade_csv(stream)

    assert exc_info.value.missing_headers == ()
    assert exc_info.value.unexpected_headers == ()
    assert exc_info.value.duplicate_headers == ()
    assert str(exc_info.value) == "Trade CSV header contains an empty column name"


def test_parse_trade_csv_rejects_empty_stream() -> None:
    stream = StringIO("")

    with pytest.raises(InvalidTradeCsvHeaderError) as exc_info:
        parse_trade_csv(stream)

    assert exc_info.value.missing_headers == ()
    assert exc_info.value.unexpected_headers == ()
    assert exc_info.value.duplicate_headers == ()
    assert str(exc_info.value) == "Trade CSV header is missing"


def test_parse_trade_csv_accepts_header_only_stream() -> None:
    stream = StringIO("symbol,side,entry_price,quantity,opened_at\n")

    result = parse_trade_csv(stream)

    assert result.total_rows == 0
    assert result.valid_rows == 0
    assert result.rejected_rows == 0
    assert result.valid_trades == ()
    assert result.row_errors == ()


def test_parse_trade_csv_ignores_blank_rows() -> None:
    stream = StringIO(
        "symbol,side,entry_price,quantity,opened_at\n"
        "\n"
        ",,,,\n"
        "AAPL,long,100,1,2024-01-02T10:00:00Z\n"
        "  ,  ,  ,  ,  \n"
        "\n"
    )

    result = parse_trade_csv(stream)

    assert result.total_rows == 1
    assert result.valid_rows == 1
    assert result.rejected_rows == 0


def test_parse_trade_csv_reports_invalid_side() -> None:
    stream = StringIO(
        "symbol,side,entry_price,quantity,opened_at\n"
        "AAPL,buy,100,1,2024-01-02T10:00:00Z\n"
    )

    result = parse_trade_csv(stream)

    assert result.total_rows == 1
    assert result.valid_rows == 0
    assert result.rejected_rows == 1
    assert result.row_errors[0].row_number == 2
    assert result.row_errors[0].errors[0].field == "side"
    assert "long" in result.row_errors[0].errors[0].message
    assert "short" in result.row_errors[0].errors[0].message


def test_parse_trade_csv_reports_invalid_quantity() -> None:
    stream = StringIO(
        "symbol,side,entry_price,quantity,opened_at\n"
        "AAPL,long,100,-1,2024-01-02T10:00:00Z\n"
    )

    result = parse_trade_csv(stream)

    assert result.row_errors[0].errors[0].field == "quantity"
    assert "greater than 0" in result.row_errors[0].errors[0].message


def test_parse_trade_csv_reports_invalid_entry_price() -> None:
    stream = StringIO(
        "symbol,side,entry_price,quantity,opened_at\n"
        "AAPL,long,0,1,2024-01-02T10:00:00Z\n"
    )

    result = parse_trade_csv(stream)

    assert result.row_errors[0].errors[0].field == "entry_price"
    assert "greater than 0" in result.row_errors[0].errors[0].message


def test_parse_trade_csv_reports_invalid_datetime() -> None:
    stream = StringIO(
        "symbol,side,entry_price,quantity,opened_at\nAAPL,long,100,1,not-a-datetime\n"
    )

    result = parse_trade_csv(stream)

    assert result.row_errors[0].errors[0].field == "opened_at"
    assert "datetime" in result.row_errors[0].errors[0].message


def test_parse_trade_csv_reports_missing_required_cell() -> None:
    stream = StringIO("symbol,side,entry_price,quantity,opened_at\nAAPL,long,100,1\n")

    result = parse_trade_csv(stream)

    assert result.row_errors[0].errors[0].field == "opened_at"


def test_parse_trade_csv_rejects_extra_row_values() -> None:
    stream = StringIO(
        "symbol,side,entry_price,quantity,opened_at\n"
        "AAPL,long,100,1,2024-01-02T10:00:00Z,EXTRA\n"
    )

    result = parse_trade_csv(stream)

    assert result.total_rows == 1
    assert result.valid_rows == 0
    assert result.rejected_rows == 1
    assert result.row_errors[0].row_number == 2
    assert result.row_errors[0].errors[0].field == "__row__"
    assert result.row_errors[0].errors[0].message == "Unexpected extra values in row"


def test_parse_trade_csv_preserves_valid_rows_when_other_rows_fail() -> None:
    stream = StringIO(
        "symbol,side,entry_price,quantity,opened_at\n"
        "AAPL,long,100,1,2024-01-02T10:00:00Z\n"
        "TSLA,buy,200,1,2024-01-03T10:00:00Z\n"
        "MSFT,short,300,2,2024-01-04T10:00:00Z\n"
    )

    result = parse_trade_csv(stream)

    assert result.total_rows == 3
    assert result.valid_rows == 2
    assert result.rejected_rows == 1
    assert tuple(trade.symbol for trade in result.valid_trades) == ("AAPL", "MSFT")
    assert result.row_errors[0].row_number == 3
    assert result.row_errors[0].errors[0].field == "side"


def test_parse_trade_csv_uses_physical_row_numbers() -> None:
    stream = StringIO(
        "symbol,side,entry_price,quantity,opened_at\n"
        "\n"
        "AAPL,long,100,1,2024-01-02T10:00:00Z\n"
        "TSLA,buy,200,1,2024-01-03T10:00:00Z\n"
    )

    result = parse_trade_csv(stream)

    assert result.total_rows == 2
    assert result.row_errors[0].row_number == 4


def test_parse_trade_csv_counts_are_consistent() -> None:
    stream = StringIO(
        "symbol,side,entry_price,quantity,opened_at\n"
        "AAPL,long,100,1,2024-01-02T10:00:00Z\n"
        "TSLA,buy,200,1,2024-01-03T10:00:00Z\n"
        "\n"
        "MSFT,short,300,2,2024-01-04T10:00:00Z\n"
    )

    result = parse_trade_csv(stream)

    assert result.total_rows == result.valid_rows + result.rejected_rows
    assert result.total_rows == 3
    assert result.valid_rows == 2
    assert result.rejected_rows == 1
