import psycopg2
from tests.conftest import DB_URL
conn = psycopg2.connect(DB_URL)
cur = conn.cursor()
cur.execute("SELECT name FROM tenants WHERE id = 1")
print(cur.fetchone())
