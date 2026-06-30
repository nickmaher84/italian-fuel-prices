import csv
import re

import logging

logger = logging.getLogger(__name__)


def parse_csv(csv_bytes: bytes):
    text = csv_bytes.decode('utf-8')
    lines = text.split('\n')

    extraction_date: str | None = None
    filtered_lines: list[tuple[int, str]] = []

    for idx, line in enumerate(lines, 1):
        if line.startswith('Estrazione del'):
            match = re.search(r'(\d{4}-\d{2}-\d{2})', line)
            if match:
                extraction_date = match.group(1)
                logger.debug(f"Extraction date found on row {idx}: {extraction_date}")
        else:
            if line.strip():
                filtered_lines.append((idx, line))

    header: str | None = None
    for idx, line in filtered_lines:
        if line.strip():
            header = line
            logger.debug(f"Header found on row {idx}: {header}")
            break

    if header is None:
        raise ValueError("No header row found")

    delimiter: str = '|' if header.count('|') > header.count(';') else ';'
    logger.debug(f"File delimiter is {delimiter}")
    delimiter_count = header.count(delimiter)

    for idx, line in filtered_lines:
        if line.count(delimiter) != delimiter_count:
            logger.error(f"Row {idx} has incorrect number of columns: {line}")

    csv_text = '\n'.join([line for idx, line in filtered_lines if line.count(delimiter) == delimiter_count])
    reader = csv.DictReader(csv_text.splitlines(), delimiter=delimiter)
    for row in reader:
        row['extraction_date'] = extraction_date
        yield row


def ingest_file(file_type: str, csv_bytes: bytes, session, file_id: str) -> None:
    from app.db.models import PriceHistory, StationHistory

    model_map = {
        "prezzo_alle_8": PriceHistory,
        "anagrafica_impianti_attivi": StationHistory,
    }

    model = model_map[file_type]
    column_map = model.column_mapping

    session.query(model).filter(model.file_id == file_id).delete()
    session.commit()

    for row in parse_csv(csv_bytes):
        mapped_row: dict[str, object] = {}
        for csv_col, csv_value in row.items():
            model_field, type_fn = column_map[csv_col.replace(" ", "").lower()]
            if csv_value and csv_value.strip():
                try:
                    mapped_row[model_field] = type_fn(csv_value)
                except Exception as e:
                    logger.error(f"Error converting {csv_col}: {e}")
                    raise e
        mapped_row['file_id'] = file_id
        record = model(**mapped_row)
        session.add(record)
    session.commit()