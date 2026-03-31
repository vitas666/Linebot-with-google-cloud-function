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

# Google Forms API 需要的 scope
SCOPES = ['https://www.googleapis.com/auth/forms.responses.readonly']
SERVICE_ACCOUNT_FILE = config.LINEBOT_SERVICE_ACCOUNT_FILE_NAME
FORM_ID = config.GOOGLE_FORM_URL_ID  #使用service account的話，id要拿編輯狀態的，不能拿預覽狀態的

get_test_txt = "{'responses': [{'responseId': 'ACYDBNgqb6A3tXAGktdNqvm8rCVPnBlkszXAqqL6WmO6Nakkvhvu9VD_qkiVYQx7u_abcRc', 'createTime': '2026-02-10T07:11:41.267Z', 'lastSubmittedTime': '2026-02-10T07:11:41.267201Z', 'answers': {'39da25f3': {'questionId': '39da25f3', 'textAnswers': {'answers': [{'value': '單身/沒有扶養義務'}]}}, '5be54049': {'questionId': '5be54049', 'textAnswers': {'answers': [{'value': '股票/ETF/期貨/虛擬貨幣/金融商品'}]}}, '73e938fa': {'questionId': '73e938fa', 'textAnswers': {'answers': [{'value': '沒有'}]}}, '17e95034': {'questionId': '17e95034', 'textAnswers': {'answers': [{'value': '個股佔比大於ETF'}]}}, '308f6275': {'questionId': '308f6275', 'textAnswers': {'answers': [{'value': '暫時沒有'}]}}, '60483d20': {'questionId': '60483d20', 'textAnswers': {'answers': [{'value': '一年以上'}]}}, '35a2cdf3': {'questionId': '35a2cdf3', 'textAnswers': {'answers': [{'value': '房租'}]}}, '113225a5': {'questionId': '113225a5', 'textAnswers': {'answers': [{'value': '30'}]}}, '566fef82': {'questionId': '566fef82', 'textAnswers': {'answers': [{'value': '部分賣出，考慮低點加碼'}]}}}}]}"

def get_google_form_responses() -> str:
    """
    使用 Google Forms API 取得表單回應，純string
    """
    # 用 Service Account 的 json 來構造憑證
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES,
    )

    # 建立 authorized session
    authed_session = AuthorizedSession(credentials)

    # API endpoint（v1）
    url = f"https://forms.googleapis.com/v1/forms/{FORM_ID}/responses"

    response = authed_session.get(url)
    response.raise_for_status()

    data = response.json()
    # 例如 data["responses"] 就是所有回應
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

