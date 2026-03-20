import google.generativeai as genai
import os
import config

genai.configure(api_key=config.GEMINI_API_KEY)
model = genai.GenerativeModel('models/gemini-2.5-pro')

def responseByAI(input) -> dict:
    response = model.generate_content(input)
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
