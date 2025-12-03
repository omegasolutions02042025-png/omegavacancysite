"""
Utility script to dump columns of the users table for debugging migrations.
Writes results to columns_output.txt in the project root.
"""
import psycopg2
from pathlib import Path

OUTPUT_FILE = Path(__file__).resolve().parent.parent / "columns_output.txt"

def main():
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        database="omegasite",
        user="postgres",
        password="123546",
    )
    cur = conn.cursor()
    cur.execute(
        """
        SELECT column_name, data_type, column_default, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'users'
        ORDER BY ordinal_position
        """
    )
    rows = cur.fetchall()
    lines = []
    for name, dtype, default, nullable in rows:
        lines.append(
            f"{name:25} | {dtype:15} | default={default} | nullable={nullable}"
        )
    OUTPUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()

