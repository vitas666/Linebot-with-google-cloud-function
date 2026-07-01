from datetime import datetime
import os
import requests
import ast
import json
from Dictionary.FormDic import QUESTION_MAP
from GenerativeAI import responseByAI
import config
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from Dictionary.InvestmentPlan import investment_plans
from DB.DBConnection import save_user_holdings

# 表單中對應的題目 ID
NAME_QUESTION_ID = "2e4edcf0"       # 您的Line顯示名稱為？
HOLDINGS_QUESTION_ID = "5ccb5137"   # 您現在在金融市場的持倉情況

# Google Forms API 需要的 scope
SCOPES = [
    'https://www.googleapis.com/auth/forms.responses.readonly',
    'https://www.googleapis.com/auth/forms.body.readonly'
]
SERVICE_ACCOUNT_FILE = config.LINEBOT_SERVICE_ACCOUNT_FILE_NAME
FORM_ID = config.GOOGLE_FORM_URL_ID  #使用service account的話，id要拿編輯狀態的，不能拿預覽狀態的
CREDENTIALS = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=SCOPES,
)


def get_google_form_structure() -> dict:
    """
    使用 Google Forms API 取得表單結構（包含問題清單），只有修改問題的時候會用到，基本上不需要頻繁呼叫
    """
    authed_session = AuthorizedSession(CREDENTIALS)
    url = f"https://forms.googleapis.com/v1/forms/{FORM_ID}"
    response = authed_session.get(url)
    response.raise_for_status()
    return response.json()


def get_google_form_responses() -> str:
    """
    使用 Google Forms API 取得表單所有回應，純string
    """
    authed_session = AuthorizedSession(CREDENTIALS)
    url = f"https://forms.googleapis.com/v1/forms/{FORM_ID}/responses"
    response = authed_session.get(url)
    response.raise_for_status()
    data = response.json()
    return data


def get_struct_answers(answers_input: str) -> dict:
    clean_answers = []
    answers_dict = ast.literal_eval(answers_input)
    raw_answers = answers_dict['responses'][0]['answers']
    response_id = answers_dict['responses'][0]['responseId']
    create_time = answers_dict['responses'][0]['createTime']

    for q_id, data in raw_answers.items():
        # 1. 透過 QUESTION_MAP 找出對應的問題文字
        question_text = QUESTION_MAP.get(q_id, f"未知問題 (ID: {q_id})")
        # 2. 安全地提取使用者的回答
        try:
            # 依照 Google Forms API 結構層層往下拿
            answer_value = data['textAnswers']['answers'][0]['value']
        except (KeyError, IndexError, TypeError):
            # 防呆：如果使用者這題沒填，或是格式不如預期
            answer_value = "使用者無回答"
            
        # 3. 組裝成乾淨的結構
        clean_answers.append({
            "question_id": q_id,
            "question": question_text,
            "answer": answer_value
        })
        
    return {
        "response_id": response_id,
        "create_time": create_time,
        "structured_answers": clean_answers
    }


def parse_holdings_with_ai(holdings_text: str) -> list:
    """
    使用 AI 將使用者填寫的自由文字持倉，解析成結構化清單。

    輸入範例：
        "006208 5萬\n00894 12000\nMU10000\n富蘭克林全球高科技美元A基金40000"
    回傳範例：
        [
            {"stock_name": "006208", "amount": 50000},
            {"stock_name": "00894", "amount": 12000},
            {"stock_name": "MU", "amount": 10000},
            {"stock_name": "富蘭克林全球高科技美元A基金", "amount": 40000}
        ]

    - 若使用者填「無」或沒有持股，回傳空清單 []
    """
    if not holdings_text or holdings_text.strip() in ("", "無", "使用者無回答"):
        return []

    prompt = f"""
    你是一個資料解析器。請將下方使用者填寫的「金融市場持倉」自由文字，
    拆解成結構化的持股清單。

    【解析規則】
    1. 每一筆持股包含「持股名稱」與「持股金額」。
    2. 持股名稱可能是股票代碼(如 006208)、公司名稱(如 台積電)、或基金全名。
    3. 金額請一律換算成「新台幣整數」：例如「5萬」= 50000、「20萬」= 200000、「12000」= 12000。
    4. 名稱與金額之間可能有空格，也可能沒有(例如 MU10000 代表名稱 MU、金額 10000)。
    5. 若某筆無法判斷金額，amount 請填 null。
    6. 若使用者表示沒有持股(例如「無」)，請回傳空陣列 []。

    【使用者填寫內容】
    {holdings_text}

    【輸出格式要求】
    只回傳一個乾淨的 JSON 陣列，不要有任何說明文字或 markdown 標記，格式如下：
    [
        {{"stock_name": "台積電", "amount": 200000}}
    ]
    """

    ai_result = responseByAI(prompt)
    raw = ai_result.get("text_content", "").strip()

    # 移除 AI 可能加上的 markdown code fence
    if raw.startswith("```"):
        raw = raw.strip("`")
        # 去掉開頭可能的 "json" 標記
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        holdings = json.loads(raw)
        if isinstance(holdings, list):
            return holdings
        print("AI 回傳的持倉資料不是陣列格式。")
        return []
    except json.JSONDecodeError:
        print(f"解析持倉 JSON 失敗，原始回傳：{raw}")
        return []


def save_holdings_from_response(response: dict) -> int:
    """
    從單筆 Google 表單回應中，取出使用者名稱與持倉文字，
    透過 AI 解析後寫入 user_holdings 資料表。

    - response (dict): get_google_form_responses() 回傳的 responses 陣列中的單一元素
    - 回傳寫入的持股筆數
    """
    answers = response.get("answers", {})
    user_name = answers[NAME_QUESTION_ID]["textAnswers"]["answers"][0]["value"]
    holdings_text = answers[HOLDINGS_QUESTION_ID]["textAnswers"]["answers"][0]["value"]

    if not user_name:
        print("此回應缺少 Line 顯示名稱，略過持股寫入。")
        return 0

    holdings = parse_holdings_with_ai(holdings_text)
    return save_user_holdings(user_name, holdings)


def AIResponseToForm(form_responses: dict) -> dict:
    """
    將表單回應傳給AI進行分析，並回傳分析結果和token使用量
    """
    struct_answer = form_responses.get("structured_answers", [])
    answers_text = json.dumps(struct_answer, indent=2, ensure_ascii=False)
    plans_text = json.dumps(investment_plans, ensure_ascii=False)

    prompt = f"""
    你是一位專業且具備同理心的理財顧問，同時也是系統的路由核心。
    請根據【使用者問卷回答】，進行財務分析，並從【可用投資策略】中挑選最適合他的一個。
    
    【使用者問卷回答】
    {answers_text}

    【可用投資策略】
    {plans_text}
    
    【你的任務】
    1. 總結這位使用者的財務現況與風險承受度，結合可用投資策略內容，於plan_id: 1到4中，幫使用者找出最適合的投資策略。
    2. 給予幾個初步的理財觀念或建議, 並放到analysis_message之中
    3. 語氣要專業但親切，像是對朋友說話一樣。

    【輸出格式要求】
    請務必只回傳一個乾淨的 JSON 物件，格式如下：
    {{
        "assigned_plan_id": 1,  # 請填入最適合該使用者的 plan_id (數字)
        "analysis_message": # 請填入你對使用者的分析與建議 (文字)
    }}
    """
    
    # 這裡假設有一個函式 responseByAI 可以將資料傳給AI並得到分析結果
    ai_result = responseByAI(prompt)
    # analysis_result = ai_result['text_content']
    try:
        # 將 AI 回傳的 JSON 字串解析回 Python 字典
        ai_content_dict = json.loads(ai_result['text_content']) 
        
        analysis_message = ai_content_dict.get("analysis_message", "分析完成，請參考後續建議。")
        assigned_plan_id = ai_content_dict.get("assigned_plan_id", 1) # 預設給保守型
        
    except json.JSONDecodeError:
        print("AI 未回傳正確的 JSON 格式")
        analysis_message = "抱歉，系統分析時遇到一點小問題，但我已經收到您的表單了！"
        assigned_plan_id = 1

    # token_usage = {
    #     "prompt_tokens": ai_result['prompt_tokens'],
    #     "completion_tokens": ai_result['completion_tokens'],
    #     "total_tokens": ai_result['total_tokens']
    # }
    
    # return {
    #     "analysis_result": analysis_result, "token_usage": token_usage
    # }

    return {
        "analysis_result": analysis_message,
        "assigned_plan_id": assigned_plan_id,
        "token_usage": {
            "prompt_tokens": ai_result.get('prompt_tokens', 0),
            "completion_tokens": ai_result.get('completion_tokens', 0),
            "total_tokens": ai_result.get('total_tokens', 0)
        }
    }

if __name__ == "__main__":
    # form = get_google_form_structure()
    # print(json.dumps(form, indent=2, ensure_ascii=False))
    responses = get_google_form_responses()
    print(json.dumps(responses, indent=2, ensure_ascii=False))
    # saved_count = save_holdings_from_response(responses['responses'][0])
    # print(f"已寫入 {saved_count} 筆持股資料。")