"""HTMLから重要部分を抽出する機能"""
from bs4 import BeautifulSoup


def extract_important_sections(soup: BeautifulSoup) -> str:
    """
    ページの重要部分（見出しとその直後の段落）だけを抽出して返す。
    AIO観点で意味のある情報だけに絞ることで、トークン数とコストを削減する。
    """
    parts = []

    # H1
    h1 = soup.find("h1")
    if h1:
        parts.append(f"[H1] {h1.get_text(strip=True)}")
        p = h1.find_next_sibling("p")
        if p:
            parts.append(f"- {p.get_text(strip=True)}")

    # H2 / H3
    for tag in soup.find_all(["h2", "h3"]):
        heading = tag.get_text(strip=True)
        parts.append(f"[{tag.name.upper()}] {heading}")

        # 見出し直後の段落を取得
        p = tag.find_next_sibling("p")
        if p:
            parts.append(f"- {p.get_text(strip=True)}")

    # 何も取れなかった場合のフォールバック
    if not parts:
        body_text = soup.get_text(separator=" ", strip=True)
        return body_text[:3000]

    # まとめて返す（最後に長さを制限）
    return "\n".join(parts)[:3000]
