"""スコアリングロジック（ルールベース）"""
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import json
import re


def _check_crawl_index_health(soup: BeautifulSoup, url: str) -> dict:
    """Crawl/Index健全性を評価"""
    score = 0
    details = []

    # title有無
    title_tag = soup.find("title")
    if title_tag and title_tag.get_text(strip=True):
        score += 25
        details.append("titleあり")
    else:
        details.append("titleなし")

    # description有無
    meta_desc = soup.find("meta", {"name": "description"})
    if meta_desc and meta_desc.get("content", "").strip():
        score += 25
        details.append("descriptionあり")
    else:
        details.append("descriptionなし")

    # noindexチェック（あれば減点）
    noindex = soup.find("meta", {"name": "robots"}) or soup.find(
        "meta", {"name": "googlebot"}
    )
    if noindex and "noindex" in (noindex.get("content") or "").lower():
        score -= 30
        details.append("noindex検出")
        if score < 0:
            score = 0

    # canonical有無
    canonical = soup.find("link", {"rel": "canonical"})
    if canonical and canonical.get("href"):
        score += 20
        details.append("canonicalあり")
    else:
        details.append("canonicalなし")

    # 重複チェック（簡易：title/descriptionの文字列長が極端に短い場合は減点）
    if title_tag:
        title_len = len(title_tag.get_text(strip=True))
        if title_len < 10:
            score -= 10
            details.append("titleが短すぎる可能性")
    if meta_desc:
        desc_len = len(meta_desc.get("content", ""))
        if desc_len < 50:
            score -= 10
            details.append("descriptionが短すぎる可能性")

    score = max(0, min(100, score))
    return {"score": score, "details": details}


def _check_answerability(soup: BeautifulSoup, full_text: str) -> dict:
    """回答性（AIに引用されやすい構造）を評価"""
    score = 0
    details = []

    # 見出し構造
    h1_count = len(soup.find_all("h1"))
    h2_count = len(soup.find_all("h2"))
    h3_count = len(soup.find_all("h3"))

    if h1_count == 1:
        score += 20
        details.append("H1が1つ")
    elif h1_count > 1:
        score += 10
        details.append(f"H1が{h1_count}つ（複数）")
    else:
        details.append("H1なし")

    if h2_count >= 3:
        score += 20
        details.append(f"H2が{h2_count}つ（良好）")
    elif h2_count > 0:
        score += 10
        details.append(f"H2が{h2_count}つ")
    else:
        details.append("H2なし")

    # 要点サマリ（「まとめ」「要約」「結論」などのセクション）
    summary_keywords = ["まとめ", "要約", "結論", "ポイント", "まとめて", "要点"]
    has_summary = any(
        kw in full_text for kw in summary_keywords
    ) or bool(soup.find(["section", "div"], class_=re.compile("summary|conclusion", re.I)))
    if has_summary:
        score += 15
        details.append("要点サマリあり")

    # 定義文（「とは」「である」など）
    definition_patterns = [
        r"とは[、。]",
        r"とは、",
        r"とは\s*[^とは]{10,}",
        r"である[。]",
    ]
    definition_count = sum(
        len(re.findall(pattern, full_text)) for pattern in definition_patterns
    )
    if definition_count >= 3:
        score += 15
        details.append("定義文が3つ以上")
    elif definition_count > 0:
        score += 10
        details.append(f"定義文が{definition_count}つ")

    # 箇条書きの多さ
    ul_count = len(soup.find_all("ul"))
    ol_count = len(soup.find_all("ol"))
    li_count = len(soup.find_all("li"))
    total_lists = ul_count + ol_count
    if li_count >= 10:
        score += 20
        details.append(f"箇条書きが{li_count}項目以上")
    elif li_count >= 5:
        score += 15
        details.append(f"箇条書きが{li_count}項目")
    elif li_count > 0:
        score += 10
        details.append(f"箇条書きが{li_count}項目")

    # テキスト量（コンテンツの厚み）
    text_len = len(full_text)
    if text_len > 8000:
        score += 10
        details.append("テキスト量：8000文字以上")
    elif text_len > 4000:
        score += 5
        details.append("テキスト量：4000文字以上")
    elif text_len < 1000:
        score -= 10
        details.append("テキスト量不足（1000文字未満）")

    # FAQ/HowToの有無（回答性に含める）
    faq_keywords = [
        "よくある質問",
        "FAQ",
        "Q&A",
        "Q and A",
        "質問",
        "よくあるご質問",
        "よくある",
    ]
    howto_keywords = [
        "How to",
        "使い方",
        "方法",
        "手順",
        "ステップ",
        "やり方",
        "ガイド",
    ]

    has_faq_keyword = any(
        kw.lower() in full_text.lower() for kw in faq_keywords
    )
    has_howto_keyword = any(
        kw.lower() in full_text.lower() for kw in howto_keywords
    )

    # FAQセクション検出
    faq_indicators = soup.find_all(
        ["h1", "h2", "h3"], string=re.compile("FAQ|よくある|質問", re.I)
    )
    if faq_indicators:
        score += 15
        details.append("FAQセクション検出")
    elif has_faq_keyword:
        score += 10
        details.append("FAQキーワードあり")

    # HowToセクション検出
    howto_indicators = soup.find_all(
        ["h1", "h2", "h3"], string=re.compile("How|使い方|手順|方法", re.I)
    )
    if howto_indicators:
        score += 15
        details.append("HowToセクション検出")
    elif has_howto_keyword:
        score += 10
        details.append("HowToキーワードあり")

    score = max(0, min(100, score))
    return {"score": score, "details": details}


def _check_eeat_proxy(soup: BeautifulSoup, full_text: str) -> dict:
    """E-E-A-T proxy（信頼性指標）を評価"""
    score = 0
    details = []

    # 著者情報
    author_meta = soup.find("meta", {"name": "author"}) or soup.find(
        "meta", {"property": "article:author"}
    )
    author_keywords = ["著者", "作者", "執筆", "writer", "author"]
    has_author_meta = bool(author_meta and author_meta.get("content"))
    has_author_keyword = any(kw in full_text for kw in author_keywords)
    if has_author_meta or has_author_keyword:
        score += 20
        details.append("著者情報あり")

    # 運営者情報
    operator_keywords = ["運営", "運営者", "会社", "企業", "組織", "運営会社"]
    has_operator = any(kw in full_text for kw in operator_keywords)
    if has_operator:
        score += 15
        details.append("運営者情報あり")

    # 問い合わせ情報
    contact_keywords = [
        "お問い合わせ",
        "問い合わせ",
        "連絡先",
        "contact",
        "メール",
        "電話",
    ]
    contact_links = soup.find_all("a", href=re.compile("contact|mailto|tel"))
    has_contact_keyword = any(kw in full_text for kw in contact_keywords)
    if contact_links or has_contact_keyword:
        score += 20
        details.append("問い合わせ情報あり")

    # 会社情報
    company_keywords = [
        "会社概要",
        "企業情報",
        "about",
        "会社名",
        "所在地",
        "設立",
    ]
    has_company = any(kw in full_text for kw in company_keywords)
    if has_company:
        score += 15
        details.append("会社情報あり")

    # 更新日
    date_patterns = [
        r"更新日[：:]\s*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})",
        r"最終更新[：:]\s*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})",
        r"(\d{4}年\d{1,2}月\d{1,2}日)\s*更新",
    ]
    date_meta = soup.find("meta", {"property": "article:modified_time"}) or soup.find(
        "meta", {"property": "article:published_time"}
    )
    has_date_meta = bool(date_meta)
    has_date_text = any(re.search(pattern, full_text) for pattern in date_patterns)
    if has_date_meta or has_date_text:
        score += 15
        details.append("更新日情報あり")

    # 参照リンク（外部リンク）
    external_links = soup.find_all("a", href=re.compile("^https?://"))
    if len(external_links) >= 5:
        score += 15
        details.append("外部リンクが5つ以上")
    elif len(external_links) > 0:
        score += 10
        details.append(f"外部リンクが{len(external_links)}つ")

    score = max(0, min(100, score))
    return {"score": score, "details": details}


def _check_structured_data(soup: BeautifulSoup) -> dict:
    """構造化データ（Schema.org）を評価"""
    score = 0
    details = []
    schema_types = set()

    ld_scripts = soup.find_all("script", {"type": "application/ld+json"})
    for script in ld_scripts:
        try:
            data = json.loads(script.string)
            # リストの場合も対応
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        schema_type = item.get("@type", "")
                        if schema_type:
                            schema_types.add(schema_type)
            elif isinstance(data, dict):
                schema_type = data.get("@type", "")
                if schema_type:
                    schema_types.add(schema_type)
        except:
            pass

    # 重要なスキーマタイプを評価
    important_types = {
        "FAQPage": 30,
        "HowTo": 30,
        "Product": 25,
        "Article": 25,
        "BlogPosting": 25,
        "BreadcrumbList": 20,
        "Organization": 20,
        "WebPage": 15,
        "WebSite": 15,
    }

    for schema_type in schema_types:
        for key, points in important_types.items():
            if key in schema_type:
                score += points
                details.append(f"Schema: {schema_type}検出")
                break

    # マイクロデータも簡易検出
    microdata_items = soup.find_all(attrs={"itemtype": True})
    if microdata_items:
        score += 10
        details.append(f"マイクロデータが{len(microdata_items)}個")

    score = max(0, min(100, score))
    return {"score": score, "details": details}


def _check_content_consistency(soup: BeautifulSoup, full_text: str) -> dict:
    """コンテンツの一貫性/網羅性を評価（簡易版）"""
    score = 50  # デフォルト
    details = []

    # テキスト量での評価
    text_len = len(full_text)
    if text_len < 500:
        score -= 30
        details.append("コンテンツが薄い（500文字未満）")
    elif text_len < 1000:
        score -= 20
        details.append("コンテンツがやや薄い（1000文字未満）")
    elif text_len > 5000:
        score += 20
        details.append("コンテンツが充実（5000文字以上）")

    # 見出しの階層構造の適切性
    h1_count = len(soup.find_all("h1"))
    h2_count = len(soup.find_all("h2"))
    if h1_count == 1 and h2_count >= 2:
        score += 20
        details.append("見出し構造が適切")
    elif h1_count == 0 or h2_count == 0:
        score -= 15
        details.append("見出し構造が不十分")

    # コンテンツの多様性（リスト、段落、画像など）
    p_count = len(soup.find_all("p"))
    img_count = len(soup.find_all("img"))
    list_count = len(soup.find_all(["ul", "ol"]))

    if p_count >= 5 and (img_count > 0 or list_count > 0):
        score += 10
        details.append("コンテンツ要素が多様")
    elif p_count < 3:
        score -= 10
        details.append("段落が少ない")

    score = max(0, min(100, score))
    return {"score": score, "details": details}


def calculate_scores(
    url: str, soup: BeautifulSoup, full_text: str, llm_scores: dict = None
) -> dict:
    """
    URL、HTMLパース結果、全文テキストから各種スコアを計算して返す。
    ルールベース70% + LLM判定30%で計算。

    Args:
        url: 評価対象のURL
        soup: BeautifulSoupオブジェクト
        full_text: ページの全文テキスト
        llm_scores: LLMによる判定スコア（dict、各項目0-100点、None可）

    Returns:
        dict: 各スコア（Crawl/Index健全性、回答性、E-E-A-T、
              構造化データ、コンテンツ一貫性、総合スコア）を含む辞書
    """
    # ルールベース評価
    crawl_index = _check_crawl_index_health(soup, url)
    answerability = _check_answerability(soup, full_text)  # FAQ/HowToを含む
    eeat = _check_eeat_proxy(soup, full_text)
    structured = _check_structured_data(soup)
    consistency = _check_content_consistency(soup, full_text)

    # LLMスコアとの合成（70%ルールベース + 30%LLM）
    if llm_scores:
        rule_weight = 0.7
        llm_weight = 0.3

        crawl_index_score = round(
            crawl_index["score"] * rule_weight
            + llm_scores.get("Crawl/Index健全性", crawl_index["score"]) * llm_weight
        )
        answerability_score = round(
            answerability["score"] * rule_weight
            + llm_scores.get("回答性", answerability["score"]) * llm_weight
        )
        eeat_score = round(
            eeat["score"] * rule_weight
            + llm_scores.get("E-E-A-T", eeat["score"]) * llm_weight
        )
        structured_score = round(
            structured["score"] * rule_weight
            + llm_scores.get("構造化データ", structured["score"]) * llm_weight
        )
        consistency_score = round(
            consistency["score"] * rule_weight
            + llm_scores.get("コンテンツ一貫性", consistency["score"]) * llm_weight
        )
    else:
        # LLMスコアがない場合はルールベースのみ
        crawl_index_score = crawl_index["score"]
        answerability_score = answerability["score"]
        eeat_score = eeat["score"]
        structured_score = structured["score"]
        consistency_score = consistency["score"]

    # 総合スコア（重み付け平均）
    total = round(
        0.20 * crawl_index_score
        + 0.30 * answerability_score  # FAQ/HowToを含む回答性の重みを上げる
        + 0.20 * eeat_score
        + 0.15 * structured_score
        + 0.15 * consistency_score
    )

    return {
        "Crawl/Index健全性": crawl_index_score,
        "回答性": answerability_score,
        "信頼性": eeat_score,
        "構造化データ": structured_score,
        "コンテンツ一貫性": consistency_score,
        "総合スコア": total,
    }
