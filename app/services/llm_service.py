# app/services/llm_service.py
from __future__ import annotations

from typing import List, Dict, Any, Union
from openai import OpenAI
import orjson
import re  # extract_json_block에서 사용

from app.core.config import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)

SYSTEM_PROMPT = """
너의 역할은 ‘RSS 콘텐츠 생성기’이다.
너는 각각의 카테고리의 최고의 전문가이며 관련 모든법을 잘 알고있다.
user_prompt에는 뉴스 제목과 글의 톤/길이/대상 정보가 포함된다.
너는 아래 규칙을 지켜 출력해야 한다.

1. 입력된 제목과 직접적으로 연관된 최신 정보·배경·영향을 논리적으로 종합해 고품질 RSS용 글을 작성한다.
    - 관련뉴스나 블로그들을 참조하여 재창조한다.
    - 기존 내용을 단순 복사하지 말고 자연스럽게 재서술한다.
    - 일반사용자들이 잘 모를만한 단어들에 대해서는 쉽게 설명하고 글을 이어나간다.
    - 사용자 톤을 정확히 반영한다.
    - 톤은 일관성을 유지한다.

2. JSON의 title 필드는 반드시 다음 규칙을 따른다.
    - 원문 뉴스 제목을 그대로 복사하지 말고, 의미는 유지하되 검색에 유리하도록 재구성한다.
    - 핵심 키워드를 포함해서 10~30자 내의 자연스러운 한국어 제목으로 클릭을 유도하도록 자극적이되 불법적이지 않아야한다.
    - 기사 내용의 취지와 사실을 왜곡하지 않는다.
    - 정치 콘텐츠의 경우는 자연스럽게 약간 편향적인 피드를 생성한다.

3. 컨텐츠는 자극적이되 불법적이지 않으며 이해하기 쉽고 가독성이 좋아야한다.
    - 주제에맞는 섹션을 4~5개정도 적절하게 설정한다.
    - 섹션의 주제는 ###으로 시작한다
    - 섹션별로 사용자의 톤으로 문장을 서술한다.
    - 개인적인 견해가 포함되도록하나 불법적이지 않아야한다.

4. 섹션별로 user_prompt가 요구한 형식대로 사진 title 자리 표시를 넣는다.  
    - 예: `[[청와대 사진]]`

5. 출력은 반드시 JSON만 생성한다.  
   기본 구조는 다음과 같다:
   {
     "title": "",
     "summary": "",
     "content": ""
   }

6. 모델 관련 메타 설명, 사족, 해설, 주석 등은 일절 포함하지 않는다.

요청이 들어오면 위 규칙을 지켜 JSON만 출력하라.
"""


def _build_user_prompt_from_records(title, ages, contry_type, sex, type, length) -> str:
    # 목표 글자수와 최소 글자수 설정
    target_len = int(length)
    min_len = max(3000, int(target_len * 0.8))  # 최소 2000자, 아니면 요청의 80%

    lines = []
    lines.append("다음 '뉴스제목'을 바탕으로 네이버, Tstory 등에 포스팅할 RSS 항목을 생성해줘.")

    # 톤 + 길이 요구
    lines.append(
        f"{contry_type} {ages}대 {sex} {type} 말투로 글을 작성해줘."
        f"전체 글자 수는 공백 포함 {target_len}자를 목표로 하고, "
        f"절대로 {min_len}자보다 짧게 쓰지 마."
    )

    # 내용 밀도 강화
    lines.append(
        "각 섹션에서는 가능하면 다음 요소들을 포함해서 내용을 풍부하게 만들어줘:"
        "\n- 구체적인 숫자나 비율(예: 연금 수령액, 증가율, 인구 비율 등)"
        "\n- 실제 존재하는 기관/기업/정부 부처 이름"
        "\n- 관련 정책/제도/법 이름"
        "단, 사실을 모르는 부분은 '대략', '예를 들어' 수준으로 표현하되, "
        "완전히 허구의 특정 수치를 만들어내지는 마."
    )

    # 이미지 placeholder
    lines.append(
        "맥락과 맥락 사이, 또는 큰 섹션 사이에 적절한 사진의 title을 [[중괄호]] 형태로 넣어줘. "
        "예: {{.. 사진}} 처럼 한 줄에 단독으로 넣어줘. "
        "이미지 placeholder는 최소 3개 이상 넣어줘."
    )

    # 뉴스 제목
    lines.append(f"- 제목은 '{title}' 이야.")

    # JSON only + 필드별 역할
    lines.append(
        "출력은 반드시 JSON 한 개만 포함해야 하고, "
        "`title`, `summary`, `content` 세 필드를 모두 채워줘."
        "\n- title: 원문 제목을 그대로 쓰지 말고, 의미는 유지하면서 30~45자 내 한국어 SEO 친화적인 제목으로 재구성해."
        "\n- summary: 전체 내용을 4~6문장 정도로 요약하되, content의 핵심 포인트가 빠지지 않게 써."
        "\n- content: 위에서 요구한 구조와 길이 조건을 모두 만족하는 긴 본문을 작성해."
        "마크다운 코드블럭, 설명 텍스트, 주석은 절대 넣지 마."
    )

    return "\n".join(lines)


def generate_rss_feed_by_gpt(keyword, ages, contry_type, sex, type, length):
    if not keyword:
        return {"items": []}

    user_prompt = _build_user_prompt_from_records(
        keyword, ages, contry_type, sex, type, length
    )

    try:
        resp = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            temperature=0.2,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        text = resp.choices[0].message.content.strip()

        # 혹시라도 fence가 섞이면 제거
        if text.startswith("```"):
            text = text.strip("` \n")
            if text.lower().startswith("json"):
                text = text[4:].strip()

        data = orjson.loads(text)
        return {"items": [data]}
    except Exception:
        raise


NEWS_CATEGORY_SYSTEM_PROMPT = """
너의 역할은 한국어 뉴스 제목을 네이버 뉴스와 유사한 카테고리로 분류하는 '순수 JSON 분류기'이다.

입력 형식:
- user 메시지에는 항상 다음과 같은 JSON이 들어온다.
  {
    "titles": ["제목1", "제목2", "제목3", ...]
  }

너는 반드시 아래 규칙을 100% 지켜서 응답해야 한다.

[1] 출력 형식 (단 하나의 형식만 허용)
- 오직 아래 형태의 JSON 객체만 출력한다.
  {
    "categories": ["카테고리1", "카테고리2", "카테고리3", ...]
  }
- "categories" 배열의 길이는 입력 "titles" 배열의 길이와 반드시 정확히 같아야 한다.
- i번째 제목에 대한 카테고리는 "categories"[i]에 위치해야 한다.
- JSON 이외의 어떤 텍스트(설명, 주석, 말머리, 코드블럭 ``` 등)도 절대 출력하지 마라.

[2] 사용할 수 있는 카테고리 목록 (아래 중 하나만)
- "육아"
- "교육"
- "경제"
- "스포츠"
- "연예"
- "사회"
- "생활"
- "세계"
- "문화"
- "IT"
- "과학"
- "정치"
- "오피니언"

각 제목마다 위 목록 중 정확히 하나만 선택해야 한다. 다른 문자열은 절대 사용하지 마라.

[3] 분류 기준과 편향 방지
- "연예"는 다음과 같은 경우에만 사용하라.
  - 제목에 연예인/아이돌/배우/가수/예능 프로그램/드라마/영화 등의 명확한 대중연예 관련 정보가 있을 때
- 내용이 모호하거나 애매하면 "사회" 또는 "생활, 문화" 중 더 가까운 쪽을 선택하라.
- 제목에 자녀, 육아, 임신, 출산, 양육, 어린이 교육 등이 명확히 언급된 경우에만 "육아"를 사용하라.
- 카테고리를 한두 개로 치우치게 찍지 말고, 제목의 실제 의미에 가장 가까운 카테고리를 신중하게 선택하라.

[4] 형식 관련 엄수 사항
- 출력은 반드시 하나의 JSON 객체만 포함해야 하며, 그 외의 문장/설명/해설/인용문은 절대 포함하지 않는다.
- "categories" 외에 다른 키를 만들지 마라.
- 따옴표, 콤마, 대괄호, 중괄호 등 JSON 문법을 엄격하게 지켜라.
"""

# 한 번에 보내는 최대 제목 개수
NEWS_CATEGORY_BATCH_SIZE = 5


def _categorize_news_titles_batch(titles: List[str]) -> List[str]:
    """
    뉴스 제목 리스트(부분 리스트)를 GPT로 한 번 보내 카테고리 리스트를 받는다.
    길이 안 맞거나 에러면 해당 batch 길이만큼 "기타" 리턴.
    """
    if not titles:
        return []

    user_content = orjson.dumps({"titles": titles}).decode("utf-8")

    try:
        resp = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            temperature=0.0,
            messages=[
                {"role": "system", "content": NEWS_CATEGORY_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        )
        text = resp.choices[0].message.content.strip()

        # 혹시 ```json ``` 감싸져 있으면 제거
        if text.startswith("```"):
            text = text.strip("` \n")
            if text.lower().startswith("json"):
                text = text[4:].strip()

        clean = extract_json_block(text)

        data = orjson.loads(clean)
        cats = data.get("categories") or []

        # 길이 안 맞으면 fallback
        if not isinstance(cats, list) or len(cats) != len(titles):
            return ["기타"] * len(titles)

        # 전부 str 캐스팅 + None 방지
        return [str(c or "기타") for c in cats]

    except Exception as e:
        print("Error in _categorize_news_titles_batch:", e)
        # 문제 생기면 이 batch 전체를 기타로
        return ["기타"] * len(titles)


def categorize_news_titles_by_gpt(titles: List[str]) -> List[str]:
    """
    전체 뉴스 제목 리스트를 BATCH_SIZE(예: 30개) 단위로 잘라서
    GPT에 여러 번 보내고, 결과를 순서대로 합친다.
    titles와 반환 리스트의 순서는 동일하게 유지해야 한다.
    """
    if not titles:
        return []

    all_cats: List[str] = []

    for i in range(0, len(titles), NEWS_CATEGORY_BATCH_SIZE):
        batch = titles[i : i + NEWS_CATEGORY_BATCH_SIZE]
        batch_cats = _categorize_news_titles_batch(batch)

        # 혹시라도 길이 또 틀어지면 강제로 맞춰줌
        if len(batch_cats) != len(batch):
            batch_cats = ["기타"] * len(batch)

        all_cats.extend(batch_cats)

    # 최종 길이 검증
    if len(all_cats) != len(titles):
        return ["기타"] * len(titles)

    return all_cats


def extract_json_block(raw: str) -> str:
    """
    GPT가 ```json ... ``` 형태로 감싼 응답에서
    JSON 본문만 추출해서 반환한다.
    코드블럭이 없어도 그냥 원문을 돌려준다.
    """
    text = raw.strip()

    # ```로 시작하면 코드블럭이라고 보고 제거
    if text.startswith("```"):
        # 첫 번째 줄의 ```json 또는 ``` 제거
        text = re.sub(r"^```[a-zA-Z0-9]*\s*", "", text)
        # 마지막 ``` 제거
        text = re.sub(r"\s*```$", "", text)

    return text.strip()
