import csv
import re
import tempfile
import os
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


def write_converted_csv(column_map: dict[str, tuple[str, type]], csv_bytes: bytes) -> tuple[str, int, str]:
    """Parse CSV, apply type conversions with Python, write clean CSV to temp file."""

    # Extract delimiter from parse_csv to use same delimiter in output
    text_content = csv_bytes.decode('utf-8')
    lines = text_content.split('\n')
    header_line = None
    for line in lines:
        if line.strip() and not line.startswith('Estrazione del'):
            header_line = line
            break

    delimiter = '|' if header_line and header_line.count('|') > header_line.count(';') else ';'

    temp_file = tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.csv',
        delete=False,
        encoding='utf-8',
        newline=''
    )

    row_count = 0

    try:
        writer = csv.writer(temp_file, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)

        # Write header
        db_field_names = [db_field for db_field, _ in column_map.values()]
        writer.writerow(db_field_names)

        # Write data rows
        for row in parse_csv(csv_bytes):
            converted_values = []

            for key, value in row.items():
                normalised_key = key.replace(" ", "").lower()
                if normalised_key in column_map:
                    db_field, type_fn = column_map[normalised_key]
                    try:
                        csv_value = type_fn(value)
                        # Write empty string for NULL values, not the string 'None'
                        if csv_value is None:
                            converted_values.append('')
                        else:
                            converted_values.append(str(csv_value))
                    except Exception as e:
                        logger.error(f"Error converting {normalised_key}='{value}': {e}")
                        raise

            writer.writerow(converted_values)
            row_count += 1
    finally:
        temp_file.close()

    logger.debug(f"Wrote {row_count} converted rows to {temp_file.name} with delimiter '{delimiter}'")
    return temp_file.name, row_count, delimiter


def ingest_file(file_type: str, csv_bytes: bytes, session, file_id: str) -> None:
    """Bulk ingest CSV: Python type conversions → cleaned CSV → DuckDB fast load."""
    from app.db.models import PriceHistory, StationHistory

    model_map = {
        "prezzo_alle_8": PriceHistory,
        "anagrafica_impianti_attivi": StationHistory,
    }

    model = model_map[file_type]
    column_map = model.column_mapping
    table_name = model.__tablename__
    db_field_names = [field for _, (field, _) in column_map.items()]

    # Delete old records for this file
    session.query(model).filter(model.file_id == file_id).delete()
    session.commit()

    # Convert types with Python, write clean CSV
    temp_csv_path, row_count, delimiter = write_converted_csv(column_map, csv_bytes)

    try:
        # Verify temp file exists and has content
        if not os.path.exists(temp_csv_path):
            raise FileNotFoundError(f"Temp CSV file not created: {temp_csv_path}")

        file_size = os.path.getsize(temp_csv_path)
        logger.debug(f"Temp CSV file size: {file_size} bytes, delimiter: '{delimiter}'")

        # Read the CSV file and insert records directly
        import duckdb

        # Get the underlying DuckDB connection from the SQLAlchemy engine
        conn = session.connection().connection

        # Read CSV and insert
        insert_query = f"""
        INSERT INTO {table_name} (id, {', '.join(db_field_names)}, file_id)
        SELECT uuid(), *, CAST('{file_id}' AS UUID) as file_id
        FROM read_csv_auto('{temp_csv_path}', sep='{delimiter}')
        """

        conn.execute(insert_query)
        session.commit()

        logger.info(f"Bulk ingested {row_count} records for file {file_id}")

    finally:
        try:
            os.unlink(temp_csv_path)
        except Exception as e:
            logger.warning(f"Could not delete temp file {temp_csv_path}: {e}")