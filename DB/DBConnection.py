import mysql.connector
from mysql.connector import Error
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
import json
from datetime import datetime

localhost = '127.0.0.1'
db_config = {
    'user': config.DB_USER,
    'password': config.DB_PASSWORD,
    'host': localhost,
    'database': 'MASTER'
}

db_pool = mysql.connector.pooling.MySQLConnectionPool(
    pool_name="my_linebot_connection_pool",
    pool_size=5,
    pool_reset_session=True,
    **db_config
)

def get_connection():
    return db_pool.get_connection()

def test_database_connection():
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 1. 確認實際連到哪一個 database (排除連錯 schema 的可能)
        cursor.execute("SELECT DATABASE()")
        current_db = cursor.fetchone()[0]
        print(f"目前連線的 database: {current_db}")

        # 2. 列出此 database 下所有的 table (確認 table 是否存在、名稱大小寫)
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        if tables:
            print(f"共有 {len(tables)} 個 table:")
            for t in tables:
                print(f"  - {t[0]}")
        else:
            print("這個 database 底下沒有任何 table。")

        for t in tables:
            table_name = t[0]
            try:
                # 這裡使用 f-string 帶入 table 名稱。
                # 注意：資料表名稱不能當作 cursor.execute(sql, params) 的參數帶入，必須直接組進 SQL 字串中。
                cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
                count = cursor.fetchone()[0]
                print(f"  - [{table_name}]: {count} rows")
                
            except mysql.connector.Error as table_err:
                # 預防某些 table 因為權限或其他原因無法讀取時，不影響其他 table 的檢查
                print(f"  - [{table_name}]: 無法查詢資料筆數 (錯誤: {table_err})")

    except mysql.connector.Error as e:
        print(f"Error: {e}")

    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
            print("Connection closed")


def init_database():
    """
    統一的資料庫初始化函數。
    一次連線，依序建立所有所需的資料表。
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 1. 表單原始資料表
        table_form = """
        CREATE TABLE IF NOT EXISTS form_responses (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id VARCHAR(255),
            response_id VARCHAR(255) UNIQUE,
            create_time DATETIME,
            answers_json JSON,
            ai_analysis TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """

        # 2. 投資策略知識庫 (RAG 檢索來源)
        table_investment = """
        CREATE TABLE IF NOT EXISTS investment_plans (
            plan_id INT AUTO_INCREMENT PRIMARY KEY,
            plan_name VARCHAR(100) NOT NULL,
            target_audience TEXT,
            core_strategy TEXT,
            recommended_assets TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """

        # 3. 對話紀錄表 (包含 user 和 assistant 的對話)
        table_chat = """
        CREATE TABLE IF NOT EXISTS chat_history (
            chat_id INT AUTO_INCREMENT PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            session_id VARCHAR(255),           -- 若需要區分同用戶的不同次對話
            role ENUM('user', 'assistant', 'system') NOT NULL,
            message TEXT NOT NULL,
            prompt_tokens INT,
            completion_tokens INT,
            total_tokens INT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        
        table_porfolio = """
        CREATE TABLE IF NOT EXISTS user_portfolios (
            user_id VARCHAR(255) PRIMARY KEY,          -- 綁定 Line User ID
            tracked_symbols JSON,                      -- 存放使用者持有的標的代碼 (如：["2330", "0050"])
            is_subscribed BOOLEAN DEFAULT FALSE,       -- 開關推播功能的 Flag
            last_notified_at DATETIME,                 -- 紀錄上次推播時間，避免重複洗頻
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        );
        """

        # 5. 股票代碼與名稱對照表
        table_stock_name = """
        CREATE TABLE IF NOT EXISTS stock_name_mapping (
            stock_id VARCHAR(50) PRIMARY KEY,
            stock_name VARCHAR(255) NOT NULL
        );
        """

        # 0. 使用者基本資料表 (以 Line UID 為主鍵，取代原本存在 Google Sheet 的對照)
        table_users = """
        CREATE TABLE IF NOT EXISTS USERS (
            uid VARCHAR(255) PRIMARY KEY,          -- Line User ID
            user_name VARCHAR(255) NOT NULL,       -- Line 顯示名稱
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """

        # 6. 使用者持股明細表 (由 Google 表單解析而來)
        table_holdings = """
        CREATE TABLE IF NOT EXISTS user_holdings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_name VARCHAR(255) NOT NULL,      -- Line 顯示名稱
            stock_name VARCHAR(255) NOT NULL,     -- 持股名稱 (代碼或公司/基金名稱)
            amount BIGINT,                        -- 對應的持股金額 (新台幣，整數)
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_user_name (user_name)
        );
        """

        # 依序執行所有建立資料表的 SQL
        for sql in [table_users, table_form, table_investment, table_chat, table_porfolio, table_stock_name, table_holdings]:
            cursor.execute(sql)
            
        conn.commit()
        print("All database tables initialized successfully.")

    except Error as e:
        print(f"Error initializing database: {e}")

    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def save_form_response(response: dict):
    '''This function saves the raw form response only into the MySQL database.'''
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        response_id = response["response_id"]
        create_time = response["create_time"]
        answers_json = json.dumps(response["structured_answers"], ensure_ascii=False)

        sql = """
        INSERT INTO form_responses (response_id, create_time, answers_json)
        VALUES (%s, %s, %s)
        """

        values = (
            response_id,
            create_time,
            answers_json
        )

        cursor.execute(sql, values)
        conn.commit()

        print("Saved response:", response_id)
    except:
        print("Error while saving response:", sys.exc_info()[0])



def save_chat_message(user_id, session_id, role, message, prompt_tokens, completion_tokens, total_tokens):
    """
    將單筆對話紀錄存入 MySQL 的 chat_history 資料表。
    
    - user_id (str): 使用者的唯一識別碼 (例如 Line User ID)
    - session_id (str): 此次對話的 Session ID，用於將多句對話歸類為同一次諮詢
    - role (str): 發話者角色，必須是 'user', 'assistant' 或 'system'
    - message (str): 對話內容文本
    - prompt_tokens (int): Prompt 的 token 數量
    - completion_tokens (int): Completion 的 token 數量
    - total_tokens (int): 總 token 數量

    - 成功時回傳該筆紀錄的 ID (lastrowid)，失敗則回傳 None
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        sql = """
        INSERT INTO chat_history 
        (user_id, session_id, role, message, prompt_tokens, completion_tokens, total_tokens)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        values = (user_id, session_id, role, message, prompt_tokens, completion_tokens, total_tokens)

        cursor.execute(sql, values)
        conn.commit()
        
        inserted_id = cursor.lastrowid
        print(f"成功儲存 {role} 的訊息 (ID: {inserted_id})")
        return inserted_id

    except Error as e:
        print(f"儲存對話紀錄時發生錯誤: {e}")
        if conn:
            conn.rollback()
        return None

    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


def get_recent_chat_history(user_id: str, session_id: str, max_messages=10, max_tokens=3000):
    '''撈取該使用者特定 Session 的最近 N 筆對話紀錄，供 AI 參考上下文'''
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # 1. 數量防線：先從資料庫撈出最新的 N 筆 (注意這裡是 DESC，先拿最新的)
        sql = """
        SELECT role, message, total_tokens 
        FROM chat_history 
        WHERE user_id = %s AND session_id = %s
        ORDER BY created_at DESC 
        LIMIT %s
        """
        cursor.execute(sql, (user_id, session_id, max_messages))
        recent_records = cursor.fetchall()

        # 2. Token 防線：計算累積 Token，並裁切
        accumulated_tokens = 0
        safe_history = []
        
        # 從最新的對話開始往前檢查
        for record in recent_records:
            # 防呆：如果是早期沒紀錄到 token 的舊資料，給個預估值 (例如 50)
            token_cost = record.get('total_tokens') or 50 
            
            if accumulated_tokens + token_cost > max_tokens:
                print(f"達到 Token 上限 ({accumulated_tokens}/{max_tokens})，截斷更早的歷史紀錄。")
                break # 超過安全上限，後面的舊對話就不帶了
                
            accumulated_tokens += token_cost
            safe_history.append({
                "role": record["role"],
                "content": record["message"]
            })

        # 3. 翻轉順序：因為剛才是 DESC 撈出來的，丟給 LLM 閱讀時必須是「由舊到新」
        safe_history.reverse()
        return safe_history

    except Exception as e:
        print(f"讀取對話紀錄時發生錯誤: {e}")
        return []
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


def get_user_specific_strategy(user_id: str):
    """
    [每次使用者傳訊息時執行]
    只從 MySQL 撈出該使用者專屬的那一條策略。
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 透過 JOIN 語法，用 user_id 找出他的 plan_id，再拉出核心策略
        sql = """
        SELECT p.plan_name, p.core_strategy, p.recommended_assets
        FROM user_portfolios u
        JOIN investment_plans p ON u.plan_id = p.plan_id
        WHERE u.user_id = %s
        """
        cursor.execute(sql, (user_id,))
        strategy = cursor.fetchone()
        
        return strategy
    except Exception as e:
        print(f"撈取策略失敗: {e}")
        return None
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


def save_stock_name_mapping(name_mapping: dict):
    """
    將股票代碼與名稱的對照表批次寫入 MySQL 的 stock_name_mapping 資料表。
    若代碼已存在則更新名稱 (upsert)。

    - name_mapping (dict): {stock_id: stock_name} 形式的對照表
    - 成功時回傳寫入的筆數，失敗則回傳 0
    """
    if not name_mapping:
        print("沒有可寫入的股票名稱資料。")
        return 0

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 確保資料表存在
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_name_mapping (
            stock_id VARCHAR(50) PRIMARY KEY,
            stock_name VARCHAR(255) NOT NULL
        );
        """)

        sql = """
        INSERT INTO stock_name_mapping (stock_id, stock_name)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE stock_name = VALUES(stock_name)
        """
        values = list(name_mapping.items())

        cursor.executemany(sql, values)
        conn.commit()

        print(f"成功寫入 {cursor.rowcount} 筆股票名稱對照資料。")
        return len(values)

    except Error as e:
        print(f"寫入股票名稱對照表時發生錯誤: {e}")
        if conn:
            conn.rollback()
        return 0

    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


def get_stock_info_from_db(target_str: str):
    """
    從 MySQL 的 stock_name_mapping 撈取股票資訊。
    不管輸入「代號」還是「名稱」，都能回傳 (代號, 名稱)；找不到回傳 (None, None)。
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        sql = """
        SELECT stock_id, stock_name
        FROM stock_name_mapping
        WHERE stock_id = %s OR stock_name = %s
        LIMIT 1
        """
        cursor.execute(sql, (target_str, target_str))
        row = cursor.fetchone()

        if row:
            return row[0], row[1]
        return None, None

    except Error as e:
        print(f"讀取股票名稱對照表時發生錯誤: {e}")
        return None, None

    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


def save_user_holdings(user_name: str, holdings: list):
    """
    將某位使用者的持股清單寫入 MySQL 的 user_holdings 資料表。
    採「先刪後增」策略：每次寫入前先清掉該使用者的舊持股，再存入最新清單，
    避免重複填表造成資料累積。

    - user_name (str): Line 顯示名稱
    - holdings (list): [{"stock_name": "台積電", "amount": 200000}, ...]
    - 成功時回傳寫入的筆數，失敗則回傳 0
    """
    if not user_name:
        print("缺少 user_name，無法寫入持股資料。")
        return 0

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 確保資料表存在
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_holdings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_name VARCHAR(255) NOT NULL,
            stock_name VARCHAR(255) NOT NULL,
            amount BIGINT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_user_name (user_name)
        );
        """)

        # 1. 先刪除該使用者的舊持股
        cursor.execute("DELETE FROM user_holdings WHERE user_name = %s", (user_name,))

        # 2. 過濾出有效持股 (需有名稱)，並插入
        values = [
            (user_name, h.get("stock_name"), h.get("amount"))
            for h in holdings
            if h.get("stock_name")
        ]

        if values:
            sql = """
            INSERT INTO user_holdings (user_name, stock_name, amount)
            VALUES (%s, %s, %s)
            """
            cursor.executemany(sql, values)

        conn.commit()
        print(f"成功更新 {user_name} 的持股，共 {len(values)} 筆。")
        return len(values)

    except Error as e:
        print(f"寫入持股資料時發生錯誤: {e}")
        if conn:
            conn.rollback()
        return 0

    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


def get_user_holdings(user_name: str):
    """
    讀取某位使用者目前的持股清單。

    - user_name (str): Line 顯示名稱
    - 回傳 list[dict]，例如：
        [{"stock_name": "台積電", "amount": 200000}, ...]
      找不到或發生錯誤時回傳空清單 []。
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        sql = """
        SELECT stock_name, amount
        FROM user_holdings
        WHERE user_name = %s
        ORDER BY amount DESC
        """
        cursor.execute(sql, (user_name,))
        return cursor.fetchall()

    except Error as e:
        print(f"讀取持股資料時發生錯誤: {e}")
        return []

    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


def register_user(uid: str, user_name: str) -> bool:
    """
    將使用者的 Line UID 與顯示名稱寫入 MySQL 的 USERS 資料表。
    (取代原本存放於 Google Sheet 的做法)

    - 若該 uid 尚未存在 -> 新增，回傳 True (代表這是新註冊的使用者)
    - 若該 uid 已存在   -> 更新顯示名稱 (使用者可能改名)，回傳 False

    - uid (str): Line User ID
    - user_name (str): Line 顯示名稱
    """
    if not uid:
        print("缺少 uid，無法註冊使用者。")
        return False

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 確保資料表存在
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS USERS (
            uid VARCHAR(255) PRIMARY KEY,
            user_name VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        sql = """
        INSERT INTO USERS (uid, user_name)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE user_name = VALUES(user_name)
        """
        cursor.execute(sql, (uid, user_name))
        conn.commit()

        # cursor.rowcount == 1 代表是新插入的一筆 (全新使用者)
        is_new_user = cursor.rowcount == 1
        if is_new_user:
            print(f"新使用者註冊成功: {user_name} ({uid})")
        else:
            print(f"使用者已存在，已更新顯示名稱: {user_name} ({uid})")
        return is_new_user

    except Error as e:
        print(f"註冊使用者時發生錯誤: {e}")
        if conn:
            conn.rollback()
        return False

    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


def get_user_by_uid(uid: str):
    """
    以 Line UID 為索引，取得使用者的基本資料。

    - uid (str): Line User ID
    - 回傳 dict，例如 {"uid": "...", "user_name": "...", "created_at": ...}
      找不到或發生錯誤時回傳 None。
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT uid, user_name, created_at FROM USERS WHERE uid = %s",
            (uid,)
        )
        return cursor.fetchone()

    except Error as e:
        print(f"讀取使用者資料時發生錯誤: {e}")
        return None

    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


def get_all_user_uids():
    """
    取得所有已註冊使用者的 UID 清單 (例如用於群發推播)。

    - 回傳 list[str]，找不到或發生錯誤時回傳空清單 []。
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT uid FROM USERS")
        return [row[0] for row in cursor.fetchall()]

    except Error as e:
        print(f"讀取使用者清單時發生錯誤: {e}")
        return []

    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


if __name__ == "__main__":
    # 測試資料庫連線與初始化
    test_database_connection()
    print(get_user_holdings("YongHan"))
