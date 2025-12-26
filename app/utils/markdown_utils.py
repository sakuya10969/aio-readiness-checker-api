import re

def normalize_markdown(text: str) -> str:
    if not text:
        return text

    # ```markdown や ``` を除去
    text = re.sub(r"^```[a-zA-Z]*\n", "", text)
    text = re.sub(r"\n```$", "", text)

    return text.strip()
