"""LLM による詳細診断"""
from openai import AzureOpenAI, RateLimitError
from config import endpoint, deployment, subscription_key, api_version
import json


def get_llm_scores(url: str, page_text: str) -> dict:
    """
    LLMによる各指標のスコア判定（0-100点）を返す。
    ルールベーススコアと組み合わせて使用する。
    """
    if not (subscription_key and endpoint and deployment):
        return {}

    client = AzureOpenAI(
        api_version=api_version,
        azure_endpoint=endpoint,
        api_key=subscription_key,
    )

    short_text = page_text[:4000]  # LLM評価用には少し長めに

    prompt = f"""
あなたはWebページのAIO（AI検索時代）適性を評価する専門家です。
以下のURLとページ内容から、各評価指標について0〜100点でスコアを付けてください。

【評価指標】
1. Crawl/Index健全性: title/description有無、noindex、canonical、重複
2. 回答性: 見出し構造（H1/H2）、要点サマリ、定義文、箇条書き、FAQ/HowToの充実度
3. 信頼性: 著者/運営者情報、問い合わせ、会社情報、更新日、参照リンク
4. 構造化データ: Schema.org（FAQPage/HowTo/Product/Article/Breadcrumb等）の有無
5. コンテンツ一貫性: 同一テーマでの網羅性、コンテンツの厚み

【出力形式（厳密にJSONのみ）】
{{
  "Crawl/Index健全性": 0-100,
  "回答性": 0-100,
  "信頼性": 0-100,
  "構造化データ": 0-100,
  "コンテンツ一貫性": 0-100
}}

URL: {url}
ページ内容（重要部分）:
{short_text}

JSONのみを出力してください（説明文は不要）:
"""

    try:
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=500,
            model=deployment,
        )
        content = response.choices[0].message.content.strip()

        # JSONを抽出（```json コードブロックがある場合に対応）
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        scores = json.loads(content)
        # スコアを0-100の範囲に制限
        for key in scores:
            scores[key] = max(0, min(100, int(scores[key])))
        return scores

    except Exception as e:
        # エラー時は空のdictを返す（ルールベースのみで継続）
        return {}


def analyze_page_with_llm(url: str, page_text: str, scores: dict) -> str:
    """
    重要部分とスコアをAzure OpenAIに渡して、構造化された示唆レポートを生成する。
    構成: 診断スコア6項目の評価、問題点（最大3つ）、改善TODO（最大3つ）。
    """
    if not (subscription_key and endpoint and deployment):
        return "Azure OpenAI API情報が設定されていません。"

    client = AzureOpenAI(
        api_version=api_version,
        azure_endpoint=endpoint,
        api_key=subscription_key,
    )

    # 念のためダブルで長さ制限
    short_text = page_text[:3000]

    prompt = f"""
あなたはプロのWebマーケティングコンサルタントです。
以下のURLとページ内容、診断スコアをもとに、AIO（AI検索・エージェント時代）の観点から
構造化された改善提案を日本語で作成してください。

【診断スコア】
- Crawl/Index健全性: {scores.get("Crawl/Index健全性", 0)}
- 回答性: {scores.get("回答性", 0)}
- 信頼性: {scores.get("信頼性", 0)}
- 構造化データ: {scores.get("構造化データ", 0)}
- コンテンツ一貫性: {scores.get("コンテンツ一貫性", 0)}

【レポート構成（必ずこの順・見出しで）】

### 1. Crawl/Index健全性
- 現状評価（2〜3行）
- 改善すべき具体的なポイントを箇条書きで3〜5個
- 特にAIO時代に重要になる理由を1〜2行でコメント

### 2. 回答性（AIに引用されやすい構造）
- 現状評価（2〜3行）
- 改善すべき具体的なポイントを箇条書きで3〜5個（FAQ/HowToの有無も含めて評価）
- 特にAIO時代に重要になる理由を1〜2行でコメント

### 3. E-E-A-T proxy（信頼性）
- 現状評価（2〜3行）
- 改善すべき具体的なポイントを箇条書きで3〜5個
- 特にAIO時代に重要になる理由を1〜2行でコメント

### 4. 構造化データ（Schema）
- 現状評価（2〜3行）
- 改善すべき具体的なポイントを箇条書きで3〜5個
- 特にAIO時代に重要になる理由を1〜2行でコメント

### 5. コンテンツの一貫性/網羅性
- 現状評価（2〜3行）
- 改善すべき具体的なポイントを箇条書きで3〜5個
- 特にAIO時代に重要になる理由を1〜2行でコメント

### 6. 問題点（最大3つ）
各問題点について「- 問題: [具体的な問題] - 理由: [1行で理由]」の形式で3つ以内

### 7. 改善TODO（最大3つ）
各TODOについて「- [TODO名]: [具体的な改善内容] - 優先度: [High/Mid/Low] - 理由: [1行で理由]」の形式で3つ
優先度はスコアが低い項目をHigh、中程度をMid、高い項目をLowとして判定

【出力フォーマットの条件】
- Markdownで出力する
- 箇条書きは - を使う
- 1つ1つの指摘は「どの部分をどう直すか」が分かるレベルまで具体的に書く
- 文体は「です・ます調」で簡潔に

--- URL ---
{url}

--- Page Text（重要部分のみ） ---
{short_text}
"""

    try:
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=4096,
            model=deployment,
        )
        return response.choices[0].message.content

    except RateLimitError:
        return (
            "#### ※API利用上限に達しました\n\n"
            "- Azure OpenAI API のレート制限／利用上限に達している可能性があります。\n"
            "- しばらく時間をおいて再度お試しください。\n"
            "- 継続利用する場合は、Azureポータルの Usage / Billing からクレジット残高をご確認ください。"
        )
    except Exception as e:
        return (
            "#### ※AI詳細診断でエラーが発生しました\n\n"
            f"- エラー内容: {e}\n"
            "- プロンプトや入力内容を見直すか、時間をおいて再度お試しください。"
        )


def analyze_domain_with_llm(results: list) -> str:
    """
    ドメイン全体の示唆を生成する。
    上位3課題、最優先の改善ロードマップ（2週間/1ヶ月/3ヶ月の3段階）、
    最初に直すべきURL Top10を出力。
    """
    if not (subscription_key and endpoint and deployment):
        return "Azure OpenAI API情報が設定されていません。"

    client = AzureOpenAI(
        api_version=api_version,
        azure_endpoint=endpoint,
        api_key=subscription_key,
    )

    # 結果をサマリ化
    summary_lines = []
    url_scores = []
    for result in results:
        if result.get("ステータス") != "OK":
            continue
        url = result.get("URL", "")
        total_score = result.get("総合スコア", 0)
        url_scores.append({"url": url, "score": total_score})
        summary_lines.append(
            f"- {url}: 総合スコア {total_score} "
            f"(回答性:{result.get('回答性',0)}, "
            f"信頼性:{result.get('信頼性',0)}, "
            f"構造化データ:{result.get('構造化データ',0)}, "
            f"Crawl/Index健全性:{result.get('Crawl/Index健全性',0)}, "
            f"コンテンツ一貫性:{result.get('コンテンツ一貫性',0)})"
        )

    # スコアでソートしてTop10
    url_scores.sort(key=lambda x: x["score"])
    top10_urgent = [item["url"] for item in url_scores[:10]]

    prompt = f"""
あなたはプロのWebマーケティングコンサルタントです。
以下のドメイン全体の診断結果をもとに、AIO（AI検索・エージェント時代）の観点から
ドメイン全体の改善戦略を日本語で作成してください。

【診断結果サマリ】
{chr(10).join(summary_lines[:50])}  # 最大50件まで

【優先的に改善すべきURL Top10（スコア順）】
{chr(10).join(f"- {url}" for url in top10_urgent)}

【出力形式（必ずこの順・見出しで）】

### ドメイン全体の上位3課題
1. **[課題名]**: [詳細説明]
2. **[課題名]**: [詳細説明]
3. **[課題名]**: [詳細説明]

### 最優先の改善ロードマップ

#### 2週間で着手すべき施策
- [具体的な施策とURL/対象ページ]

#### 1ヶ月で着手すべき施策
- [具体的な施策とURL/対象ページ]

#### 3ヶ月で着手すべき施策
- [具体的な施策とURL/対象ページ]

### 最初に直すべきURL Top10
優先順位順に、各URLについて「- 1. [URL]: [改善理由と優先度]」の形式（番号は1から10まで）

【出力フォーマットの条件】
- Markdownで出力する
- 箇条書きは - を使う
- 具体的で実行可能な内容にする
- 文体は「です・ます調」で簡潔に
- 課題名は「FAQ不足」「信頼情報不足」「構造化データ不足」などの具体的な表現を使う
"""

    try:
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=8192,
            model=deployment,
        )
        return response.choices[0].message.content

    except RateLimitError:
        return (
            "#### ※API利用上限に達しました\n\n"
            "- Azure OpenAI API のレート制限／利用上限に達している可能性があります。"
        )
    except Exception as e:
        return (
            "#### ※ドメイン分析でエラーが発生しました\n\n"
            f"- エラー内容: {e}\n"
        )
