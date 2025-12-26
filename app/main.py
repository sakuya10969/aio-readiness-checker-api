"""FastAPIアプリケーション - AIO Readiness Checker API"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
import httpx
from bs4 import BeautifulSoup

from app.config import endpoint, deployment, subscription_key
from app.core.extractor import extract_important_sections
from app.core.scorer import calculate_scores
from app.core.analyzer import analyze_page_with_llm, get_llm_scores
from app.utils.markdown_utils import normalize_markdown

app = FastAPI(title="AIO Readiness Checker API", version="1.0.0")

# CORS設定（フロントエンドからのアクセスを許可）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 本番環境では適切なオリジンを指定
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# リクエストモデル
class CheckRequest(BaseModel):
    urls: List[str] = Field(..., description="診断したいURLのリスト")

# レスポンスモデル（フロントエンドのsnake_caseインターフェースに合わせる）
class ResultRow(BaseModel):
    url: str
    status: str
    total_score: int = Field(..., alias="total_score")
    crawl_index: int = Field(..., alias="crawl_index")
    answerability: int
    reliability: int
    structured_data: int = Field(..., alias="structured_data")
    consistency: int
    llm_report: Optional[str] = Field(None, alias="llm_report")

    class Config:
        populate_by_name = True

class CheckResponse(BaseModel):
    results: List[ResultRow]

@app.get("/")
async def root():
    """ヘルスチェックエンドポイント"""
    return {"message": "AIO Readiness Checker API", "status": "ok"}

@app.post("/aio-check", response_model=CheckResponse)
async def aio_check(request: CheckRequest):
    """
    URLリストを受け取り、AIO適性を診断して結果を返す

    Args:
        request: 診断したいURLのリストを含むリクエスト

    Returns:
        CheckResponse: 各URLの診断結果を含むレスポンス
    """
    if not request.urls:
        raise HTTPException(status_code=400, detail="URLリストが空です")

    results = []

    # httpx.AsyncClientを使用して非同期でHTTPリクエストを実行
    async with httpx.AsyncClient(timeout=30.0) as client:
        for url in request.urls:
            url = url.strip()
            if not url:
                continue

            try:
                # HTML取得
                resp = await client.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                resp.raise_for_status()
                html = resp.text
                soup = BeautifulSoup(html, "html.parser")
            except Exception as e:
                # エラー時は失敗ステータスで返す
                results.append(
                    ResultRow(
                        url=url,
                        status=f"取得失敗: {str(e)}",
                        total_score=0,
                        crawl_index=0,
                        answerability=0,
                        reliability=0,
                        structured_data=0,
                        consistency=0,
                    )
                )
                continue

            # ページ本文（全文）
            full_text = soup.get_text(separator=" ", strip=True)

            # AIO観点で重要な部分だけ抽出（見出し＋直後の段落）
            important_text = extract_important_sections(soup)

            # LLMによるスコア判定（オプション）
            llm_scores = {}
            if subscription_key and endpoint and deployment:
                try:
                    llm_scores = get_llm_scores(url, important_text)
                except Exception:
                    # LLMエラー時はルールベースのみで継続
                    pass

            # スコア計算（ルールベース70% + LLM判定30%）
            scores = calculate_scores(url, soup, full_text, llm_scores)

            # LLMレポート生成（オプション）
            llm_report = None
            if subscription_key and endpoint and deployment:
                try:
                    scores_dict = {
                        "Crawl/Index健全性": scores.get("Crawl/Index健全性", 0),
                        "回答性": scores.get("回答性", 0),
                        "信頼性": scores.get("信頼性", 0),
                        "構造化データ": scores.get("構造化データ", 0),
                        "コンテンツ一貫性": scores.get("コンテンツ一貫性", 0),
                    }
                    llm_report = analyze_page_with_llm(url, important_text, scores_dict)
                except Exception:
                    # LLMレポート生成エラー時はスキップ
                    pass

            # 結果をResultRow形式に変換
            result = ResultRow(
                url=url,
                status="OK",
                total_score=scores.get("総合スコア", 0),
                crawl_index=scores.get("Crawl/Index健全性", 0),
                answerability=scores.get("回答性", 0),
                reliability=scores.get("信頼性", 0),
                structured_data=scores.get("構造化データ", 0),
                consistency=scores.get("コンテンツ一貫性", 0),
                llm_report=normalize_markdown(llm_report),
            )
            results.append(result)

    return CheckResponse(results=results)
