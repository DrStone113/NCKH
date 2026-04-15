"""
db_client.py — SQLite client cho Health Advice Chatbot Knowledge Base.

Quản lý toàn bộ schema và thao tác CRUD với các bảng:
  - medical_qa
  - embeddings
  - nutrition
  - exercises
  - conversation_logs
"""

import sqlite3
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class DBClient:
    """Client quản lý SQLite Knowledge Base cho chatbot y tế.

    Với db_path=':memory:', giữ một persistent connection duy nhất để
    tránh mất dữ liệu giữa các lần gọi (in-memory DB không chia sẻ
    giữa các connection khác nhau).
    Với db_path là file, mỗi phương thức tự mở/đóng connection.
    """

    def __init__(self, db_path: str) -> None:
        """
        Khởi tạo DBClient với đường dẫn đến file SQLite.

        Args:
            db_path: Đường dẫn tuyệt đối hoặc tương đối đến file .db,
                     hoặc ':memory:' cho in-memory database.
        """
        self.db_path = db_path
        # Persistent connection chỉ dùng cho in-memory DB
        self._conn: Optional[sqlite3.Connection] = None
        if db_path == ":memory:":
            self._conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._conn.execute("PRAGMA foreign_keys = ON")

    def _get_connection(self) -> sqlite3.Connection:
        """Trả về connection hiện tại (persistent hoặc mới)."""
        if self._conn is not None:
            return self._conn
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _release_connection(self, conn: sqlite3.Connection) -> None:
        """Đóng connection nếu không phải persistent."""
        if conn is not self._conn:
            conn.close()

    # ------------------------------------------------------------------
    # Schema initialization
    # ------------------------------------------------------------------

    def init_db(self) -> None:
        """
        Tạo tất cả bảng nếu chưa tồn tại.

        Bảng được tạo: medical_qa, embeddings, nutrition, exercises,
        conversation_logs cùng các index cần thiết.
        """
        ddl_statements = [
            """
            CREATE TABLE IF NOT EXISTS medical_qa (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                instruction TEXT    NOT NULL,
                input       TEXT    DEFAULT '',
                output      TEXT    NOT NULL,
                source      TEXT    NOT NULL,
                language    TEXT    DEFAULT 'en',
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS embeddings (
                id          INTEGER PRIMARY KEY,
                vector      BLOB    NOT NULL,
                model_name  TEXT    NOT NULL,
                FOREIGN KEY (id) REFERENCES medical_qa(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS nutrition (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                category        TEXT,
                description     TEXT    NOT NULL,
                kilocalories    REAL,
                protein_g       REAL,
                carbohydrate_g  REAL,
                fat_total_g     REAL,
                fiber_g         REAL,
                vitamins_json   TEXT,
                minerals_json   TEXT,
                source          TEXT    DEFAULT 'usda'
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_nutrition_description ON nutrition(description)",
            """
            CREATE TABLE IF NOT EXISTS exercises (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT    NOT NULL,
                category        TEXT,
                muscle_group    TEXT,
                equipment       TEXT,
                difficulty      TEXT,
                description     TEXT,
                instructions    TEXT
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_exercises_name ON exercises(name)",
            "CREATE INDEX IF NOT EXISTS idx_exercises_muscle ON exercises(muscle_group)",
            """
            CREATE TABLE IF NOT EXISTS conversation_logs (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id       TEXT    NOT NULL,
                user_message     TEXT    NOT NULL,
                bot_response     TEXT    NOT NULL,
                intent           TEXT,
                confidence       REAL,
                similarity_score REAL,
                timestamp        DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
        ]

        try:
            conn = self._get_connection()
            for stmt in ddl_statements:
                conn.execute(stmt)
            conn.commit()
            self._release_connection(conn)
            logger.info("Database initialized at %s", self.db_path)
        except sqlite3.Error as exc:
            logger.error("Failed to initialize database: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Batch inserts
    # ------------------------------------------------------------------

    def batch_insert_medical_qa(self, records: list[dict]) -> int:
        """
        Insert nhiều bản ghi vào bảng medical_qa.

        Args:
            records: Danh sách dict với các key: instruction, output, source,
                     và tùy chọn: input, language.

        Returns:
            Số bản ghi đã insert thành công.
        """
        if not records:
            return 0

        sql = """
            INSERT INTO medical_qa (instruction, input, output, source, language)
            VALUES (:instruction, :input, :output, :source, :language)
        """
        rows = [
            {
                "instruction": r["instruction"],
                "input": r.get("input", ""),
                "output": r["output"],
                "source": r["source"],
                "language": r.get("language", "en"),
            }
            for r in records
        ]

        try:
            conn = self._get_connection()
            conn.executemany(sql, rows)
            conn.commit()
            self._release_connection(conn)
            logger.debug("Inserted %d records into medical_qa", len(rows))
            return len(rows)
        except sqlite3.Error as exc:
            logger.error("batch_insert_medical_qa failed: %s", exc)
            raise

    def batch_insert_nutrition(self, records: list[dict]) -> int:
        """
        Insert nhiều bản ghi vào bảng nutrition.

        Args:
            records: Danh sách dict với key bắt buộc: description.
                     Tùy chọn: category, kilocalories, protein_g,
                     carbohydrate_g, fat_total_g, fiber_g,
                     vitamins_json, minerals_json, source.

        Returns:
            Số bản ghi đã insert thành công.
        """
        if not records:
            return 0

        sql = """
            INSERT INTO nutrition (
                category, description, kilocalories, protein_g,
                carbohydrate_g, fat_total_g, fiber_g,
                vitamins_json, minerals_json, source
            ) VALUES (
                :category, :description, :kilocalories, :protein_g,
                :carbohydrate_g, :fat_total_g, :fiber_g,
                :vitamins_json, :minerals_json, :source
            )
        """
        rows = [
            {
                "category": r.get("category"),
                "description": r["description"],
                "kilocalories": r.get("kilocalories"),
                "protein_g": r.get("protein_g"),
                "carbohydrate_g": r.get("carbohydrate_g"),
                "fat_total_g": r.get("fat_total_g"),
                "fiber_g": r.get("fiber_g"),
                "vitamins_json": r.get("vitamins_json"),
                "minerals_json": r.get("minerals_json"),
                "source": r.get("source", "usda"),
            }
            for r in records
        ]

        try:
            conn = self._get_connection()
            conn.executemany(sql, rows)
            conn.commit()
            self._release_connection(conn)
            logger.debug("Inserted %d records into nutrition", len(rows))
            return len(rows)
        except sqlite3.Error as exc:
            logger.error("batch_insert_nutrition failed: %s", exc)
            raise

    def batch_insert_exercises(self, records: list[dict]) -> int:
        """
        Insert nhiều bản ghi vào bảng exercises.

        Args:
            records: Danh sách dict với key bắt buộc: name.
                     Tùy chọn: category, muscle_group, equipment,
                     difficulty, description, instructions.

        Returns:
            Số bản ghi đã insert thành công.
        """
        if not records:
            return 0

        sql = """
            INSERT INTO exercises (
                name, category, muscle_group, equipment,
                difficulty, description, instructions
            ) VALUES (
                :name, :category, :muscle_group, :equipment,
                :difficulty, :description, :instructions
            )
        """
        rows = [
            {
                "name": r["name"],
                "category": r.get("category"),
                "muscle_group": r.get("muscle_group"),
                "equipment": r.get("equipment"),
                "difficulty": r.get("difficulty"),
                "description": r.get("description"),
                "instructions": r.get("instructions"),
            }
            for r in records
        ]

        try:
            conn = self._get_connection()
            conn.executemany(sql, rows)
            conn.commit()
            self._release_connection(conn)
            logger.debug("Inserted %d records into exercises", len(rows))
            return len(rows)
        except sqlite3.Error as exc:
            logger.error("batch_insert_exercises failed: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Embedding operations
    # ------------------------------------------------------------------

    def get_all_embeddings(self) -> list[tuple]:
        """
        Lấy tất cả embeddings từ bảng embeddings.

        Returns:
            Danh sách tuple (id, vector_blob, model_name).
        """
        sql = "SELECT id, vector, model_name FROM embeddings"
        try:
            conn = self._get_connection()
            rows = conn.execute(sql).fetchall()
            self._release_connection(conn)
            return rows
        except sqlite3.Error as exc:
            logger.error("get_all_embeddings failed: %s", exc)
            raise

    def save_embedding(self, qa_id: int, vector_blob: bytes, model_name: str) -> None:
        """
        Lưu hoặc cập nhật embedding cho một bản ghi medical_qa.

        Args:
            qa_id: ID của bản ghi trong bảng medical_qa.
            vector_blob: Numpy array đã serialize thành bytes.
            model_name: Tên model đã tạo embedding.
        """
        sql = """
            INSERT INTO embeddings (id, vector, model_name)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                vector = excluded.vector,
                model_name = excluded.model_name
        """
        try:
            conn = self._get_connection()
            conn.execute(sql, (qa_id, vector_blob, model_name))
            conn.commit()
            self._release_connection(conn)
        except sqlite3.Error as exc:
            logger.error("save_embedding failed for qa_id=%d: %s", qa_id, exc)
            raise

    def has_embedding(self, qa_id: int) -> bool:
        """
        Kiểm tra xem bản ghi đã có embedding chưa.

        Args:
            qa_id: ID của bản ghi trong bảng medical_qa.

        Returns:
            True nếu đã có embedding, False nếu chưa.
        """
        sql = "SELECT 1 FROM embeddings WHERE id = ? LIMIT 1"
        try:
            conn = self._get_connection()
            row = conn.execute(sql, (qa_id,)).fetchone()
            self._release_connection(conn)
            return row is not None
        except sqlite3.Error as exc:
            logger.error("has_embedding failed for qa_id=%d: %s", qa_id, exc)
            raise

    def get_all_qa_without_embeddings(self) -> list[dict]:
        """
        Lấy tất cả bản ghi medical_qa chưa có embedding.

        Returns:
            Danh sách dict với key: id, instruction.
        """
        sql = """
            SELECT mq.id, mq.instruction
            FROM medical_qa mq
            LEFT JOIN embeddings e ON mq.id = e.id
            WHERE e.id IS NULL
        """
        try:
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql).fetchall()
            result = [{"id": row["id"], "instruction": row["instruction"]} for row in rows]
            conn.row_factory = None
            self._release_connection(conn)
            return result
        except sqlite3.Error as exc:
            logger.error("get_all_qa_without_embeddings failed: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Lookup operations
    # ------------------------------------------------------------------

    def get_answer_by_id(self, id: int) -> Optional[str]:
        """
        Lấy câu trả lời từ bảng medical_qa theo ID.

        Args:
            id: Primary key của bản ghi.

        Returns:
            Chuỗi output nếu tìm thấy, None nếu không có.
        """
        sql = "SELECT output FROM medical_qa WHERE id = ?"
        try:
            conn = self._get_connection()
            row = conn.execute(sql, (id,)).fetchone()
            self._release_connection(conn)
            return row[0] if row else None
        except sqlite3.Error as exc:
            logger.error("get_answer_by_id failed for id=%d: %s", id, exc)
            raise

    def count_medical_qa(self) -> int:
        """
        Đếm tổng số bản ghi trong bảng medical_qa.

        Returns:
            Số nguyên — tổng số bản ghi.
        """
        sql = "SELECT COUNT(*) FROM medical_qa"
        try:
            conn = self._get_connection()
            row = conn.execute(sql).fetchone()
            self._release_connection(conn)
            return row[0]
        except sqlite3.Error as exc:
            logger.error("count_medical_qa failed: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Search operations
    # ------------------------------------------------------------------

    def search_nutrition(self, query: str) -> list[dict]:
        """
        Tìm kiếm thực phẩm theo tên (LIKE search trên cột description).

        Args:
            query: Chuỗi tìm kiếm.

        Returns:
            Danh sách dict chứa toàn bộ thông tin dinh dưỡng tìm được.
        """
        sql = """
            SELECT id, category, description, kilocalories, protein_g,
                   carbohydrate_g, fat_total_g, fiber_g,
                   vitamins_json, minerals_json, source
            FROM nutrition
            WHERE description LIKE ?
        """
        pattern = f"%{query}%"
        try:
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, (pattern,)).fetchall()
            result = [dict(row) for row in rows]
            conn.row_factory = None
            self._release_connection(conn)
            return result
        except sqlite3.Error as exc:
            logger.error("search_nutrition failed for query='%s': %s", query, exc)
            raise

    def search_exercises(self, query: str) -> list[dict]:
        """
        Tìm kiếm bài tập theo tên (LIKE search trên cột name).

        Args:
            query: Chuỗi tìm kiếm.

        Returns:
            Danh sách dict chứa toàn bộ thông tin bài tập tìm được.
        """
        sql = """
            SELECT id, name, category, muscle_group, equipment,
                   difficulty, description, instructions
            FROM exercises
            WHERE name LIKE ?
        """
        pattern = f"%{query}%"
        try:
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, (pattern,)).fetchall()
            result = [dict(row) for row in rows]
            conn.row_factory = None
            self._release_connection(conn)
            return result
        except sqlite3.Error as exc:
            logger.error("search_exercises failed for query='%s': %s", query, exc)
            raise

    # ------------------------------------------------------------------
    # Conversation logging
    # ------------------------------------------------------------------

    def log_conversation(
        self,
        session_id: str,
        user_msg: str,
        bot_resp: str,
        intent: Optional[str] = None,
        confidence: Optional[float] = None,
        similarity: Optional[float] = None,
    ) -> None:
        """
        Ghi log một lượt hội thoại vào bảng conversation_logs.

        Args:
            session_id: ID phiên hội thoại.
            user_msg: Tin nhắn của người dùng.
            bot_resp: Phản hồi của bot.
            intent: Intent được nhận diện (tùy chọn).
            confidence: Độ tin cậy của intent (tùy chọn).
            similarity: Cosine similarity của retrieval (tùy chọn).
        """
        sql = """
            INSERT INTO conversation_logs
                (session_id, user_message, bot_response, intent, confidence, similarity_score)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        try:
            conn = self._get_connection()
            conn.execute(sql, (session_id, user_msg, bot_resp, intent, confidence, similarity))
            conn.commit()
            self._release_connection(conn)
        except sqlite3.Error as exc:
            logger.error("log_conversation failed for session_id='%s': %s", session_id, exc)
            raise

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """
        Đóng persistent connection (nếu có).

        Với file-based DB, mỗi phương thức tự quản lý connection nên
        không cần làm gì thêm. Với in-memory DB, đóng connection sẽ
        xóa toàn bộ dữ liệu.
        """
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.debug("DBClient persistent connection closed.")
        else:
            logger.debug("DBClient.close() called — no persistent connection to close.")
