"""Azure OpenAI設定の読み込み"""
import os
from dotenv import load_dotenv

# Azure OpenAI のキーとエンドポイントを .env から取得
load_dotenv()
endpoint = os.getenv("AZ_OPENAI_ENDPOINT")
deployment = os.getenv("AZ_OPENAI_DEPLOYMENT")
subscription_key = os.getenv("AZ_OPENAI_KEY")
api_version = os.getenv("AZ_OPENAI_API_VERSION", "2025-04-01-preview")
