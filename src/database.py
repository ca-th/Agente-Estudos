import os #importa o modulo os para interagir com o sistema operacional
import psycopg #importa o moduulo psycog
from psycopg.rows import dict_row
from dotenv import load_dotenv #carrega as variaveis de ambiente do arquivo .env

load_dotenv()

DATABASE_URL =os.getenv("DATABASE_URL")

def get_connection():
    """"Abre uma conexão com o PostgreSQL da Neon retornando linhas como dicionarios"""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL nao encontrada")
    return psycopg.connect(DATABASE_URL, row_factory= dict_row)
    
if __name__ == "__main__":
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database(), version();")
                db_info = cur.fetchone()
                print(f"Conectado ao banco de dados" , db_info)
    except Exception as e:
        print("Erro ao conectar ao banco de dados:", e)