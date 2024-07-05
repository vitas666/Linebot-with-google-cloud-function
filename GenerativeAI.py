import google.generativeai as genai
import os

api_key = os.environ["GEMINI_API_KEY"]='your Gemini API key'
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-pro')


def responseByAI(input):
    response = model.generate_content(input)
    return response.text
