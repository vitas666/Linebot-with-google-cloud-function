import google.genai as genai
import config

client = genai.Client(api_key=config.GEMINI_API_KEY)

def responseByAI(input_text: str) -> dict:
    response = client.models.generate_content(
        model='gemini-2.5-pro',
        contents=input_text
    )
    
    reply_text = response.text    
    usage = response.usage_metadata
    prompt_tokens = usage.prompt_token_count
    completion_tokens = usage.candidates_token_count
    total_tokens = usage.total_token_count

    return {
        "text_content": reply_text,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens
    }

if __name__ == "__main__":
    test_input = "請問台積電的股票基本資訊？"
    ai_response = responseByAI(test_input)
    print(ai_response)