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

def connect_to_database():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM USERS")
        records = cursor.fetchall()
        for row in records:
            print(row)

    except mysql.connector.Error as e:
        print(f"Error: {e}")

    finally:
        if conn and conn.is_connected():
            cursor.close()
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

        # 依序執行所有建立資料表的 SQL
        for sql in [table_form, table_investment, table_chat, table_porfolio]:
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

