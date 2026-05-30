import sqlite3
import os

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
DB_PATH = os.path.join(DB_DIR, 'charging.db')


def _ensure_dir():
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR)


def get_conn():
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user'
        );

        CREATE TABLE IF NOT EXISTS pile_stats (
            pile_id TEXT PRIMARY KEY,
            total_charge_count INTEGER DEFAULT 0,
            total_charge_duration REAL DEFAULT 0.0,
            total_charge_power REAL DEFAULT 0.0
        );

        CREATE TABLE IF NOT EXISTS charging_details (
            detail_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            pile_id TEXT NOT NULL,
            energy_amount REAL NOT NULL,
            start_time TEXT NOT NULL,
            stop_time TEXT NOT NULL,
            charging_fee REAL NOT NULL,
            service_fee REAL NOT NULL,
            total_fee REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS fault_records (
            record_id TEXT PRIMARY KEY,
            pile_id TEXT NOT NULL,
            fault_time TEXT NOT NULL,
            fault_reason TEXT NOT NULL,
            is_resolved INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS system_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    ''')
    conn.commit()
    try:
        conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    conn.close()


def ensure_default_users():
    conn = get_conn()
    existing = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if existing == 0:
        conn.executemany(
            "INSERT OR IGNORE INTO users (user_id, password, role) VALUES (?, ?, ?)",
            [
                ("user1", "123456", "admin"),
                ("user2", "123456", "user"),
                ("user3", "123456", "user"),
            ]
        )
        conn.commit()
    conn.close()


def register_user(user_id, password, role='user'):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO users (user_id, password, role) VALUES (?, ?, ?)",
            (user_id, password, role)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def verify_user(user_id, password):
    conn = get_conn()
    row = conn.execute(
        "SELECT password, role FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    if row and row["password"] == password:
        return {"valid": True, "role": row["role"]}
    return {"valid": False, "role": None}


def get_user_role(user_id):
    conn = get_conn()
    row = conn.execute("SELECT role FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return row["role"] if row else None


def get_all_users():
    conn = get_conn()
    rows = conn.execute("SELECT user_id, role FROM users ORDER BY user_id").fetchall()
    conn.close()
    return [{"user_id": row["user_id"], "role": row["role"]} for row in rows]


def user_exists(user_id):
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return row is not None


def get_system_state(key):
    conn = get_conn()
    row = conn.execute("SELECT value FROM system_state WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else None


def set_system_state(key, value):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)",
        (key, str(value))
    )
    conn.commit()
    conn.close()


def load_pile_stats():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM pile_stats").fetchall()
    conn.close()
    result = {}
    for row in rows:
        result[row["pile_id"]] = {
            "total_charge_count": row["total_charge_count"],
            "total_charge_duration": row["total_charge_duration"],
            "total_charge_power": row["total_charge_power"]
        }
    return result


def save_pile_stats(pile_id, total_charge_count, total_charge_duration, total_charge_power):
    conn = get_conn()
    conn.execute(
        '''INSERT OR REPLACE INTO pile_stats 
           (pile_id, total_charge_count, total_charge_duration, total_charge_power)
           VALUES (?, ?, ?, ?)''',
        (pile_id, total_charge_count, total_charge_duration, total_charge_power)
    )
    conn.commit()
    conn.close()


def save_charging_detail(detail, user_id=None):
    conn = get_conn()
    conn.execute(
        '''INSERT INTO charging_details 
           (detail_id, user_id, pile_id, energy_amount, start_time, stop_time, 
            charging_fee, service_fee, total_fee)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (detail.detailId, user_id if user_id else 'unknown', detail.pileId, detail.energyAmount,
         detail.startTime.isoformat(), detail.stopTime.isoformat(),
         detail.chargingFee, detail.serviceFee, detail.totalFee)
    )
    conn.commit()
    conn.close()


def load_charging_details(user_id=None):
    conn = get_conn()
    if user_id:
        rows = conn.execute("SELECT * FROM charging_details WHERE user_id = ? ORDER BY stop_time DESC", (user_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM charging_details ORDER BY stop_time DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_pile_queue_info(pile_id):
    """获取指定充电桩的排队信息（返回队列中车辆的详细数据）。"""
    # 注：由于当前充电请求是内存状态，此函数仅返回数据库中已有统计，
    # 实时队列信息通过 /api/charging-area 接口返回
    return []


def save_fault_record(record):
    conn = get_conn()
    conn.execute(
        '''INSERT OR REPLACE INTO fault_records 
           (record_id, pile_id, fault_time, fault_reason, is_resolved)
           VALUES (?, ?, ?, ?, ?)''',
        (record.recordId, record.pileId, record.faultTime.isoformat(),
         record.faultReason, 1 if record.isResolved else 0)
    )
    conn.commit()
    conn.close()


def update_fault_resolved(record_id):
    conn = get_conn()
    conn.execute(
        "UPDATE fault_records SET is_resolved = 1 WHERE record_id = ?",
        (record_id,)
    )
    conn.commit()
    conn.close()


def load_fault_records():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM fault_records ORDER BY fault_time DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]
