# SmartCLM Models Documentation

## 📋 개요

SmartCLM의 데이터베이스 모델 구조와 Document metadata 활용 방법을 설명합니다.

## 🏗️ 데이터베이스 구조

### 핵심 테이블

- **User**: 사용자 정보
- **Room**: 협업 단위 (방)
- **Document**: 모든 문서 (계약서, 법령, 참고자료 등)
- **Chunk**: 문서 청크 (RAG/AI 검색용)

## 📄 Document Metadata 구조

### 기본 구조

```json
{
  "type": "문서 유형",
  "category": "세부 카테고리",
  "variables": {},
  "extracted_info": {},
  "processing_info": {},
  "custom_fields": {}
}
```

## 🔄 Variables vs Extracted_Info 차이점

### Variables (변수)

- **목적**: 초안작성/템플릿 치환용
- **특징**: 사용자가 입력하거나 AI가 추출한 **구체적인 값**
- **용도**: `{{계약상대방}}`, `{{계약금액}}` 같은 플레이스홀더 치환

### Extracted_Info (추출 정보)

- **목적**: 분석/검색/분류용
- **특징**: AI가 문서에서 **구조화된 정보**로 추출한 메타데이터
- **용도**: 문서 분석, 검색 필터링, 자동 분류

## 📝 문서 유형별 Metadata 예시

### 1. 계약서 (Contract)

```json
{
  "type": "contract",
  "category": "서비스계약서",
  "variables": {
    "계약상대방": "ABC 주식회사",
    "계약금액": "1,000만원",
    "계약기간": "2024.01.01 ~ 2024.12.31",
    "담당자": "김철수"
  },
  "extracted_info": {
    "당사자": {
      "갑": "우리회사",
      "을": "ABC 주식회사"
    },
    "계약금액": {
      "금액": "1,000만원",
      "통화": "KRW",
      "지급방식": "월말 후불"
    },
    "주요조항": ["제1조 계약의 목적", "제2조 계약금액", "제3조 지급조건"],
    "리스크요소": ["손해배상", "해지조항"]
  },
  "processing_info": {
    "ai_model": "claude-3-sonnet",
    "extraction_date": "2024-01-15T10:30:00Z",
    "confidence_score": 0.95
  }
}
```

### 2. 표준계약서 (Standard Contract) - **특별한 경우**

```json
{
  "type": "standard_contract",
  "category": "공정위표준계약서",
  "variables": {
    "fields": [
      // 입력 필드 정의 (템플릿용)
      {
        "name": "계약상대방",
        "type": "text",
        "required": true,
        "description": "계약을 체결하는 상대방 회사명",
        "placeholder": "예: ABC 주식회사"
      },
      {
        "name": "계약금액",
        "type": "number",
        "required": true,
        "description": "계약 총 금액",
        "placeholder": "예: 10000000"
      },
      {
        "name": "계약기간",
        "type": "date_range",
        "required": true,
        "description": "계약 시작일과 종료일"
      }
    ]
  },
  "extracted_info": {
    "template_version": "2024.01",
    "issuing_authority": "공정거래위원회",
    "contract_type": "서비스계약서"
  },
  "processing_info": {
    "template_ready": true,
    "variable_count": 15
  }
}
```

### 3. 법령 (Law)

```json
{
  "type": "law",
  "category": "민법",
  "extracted_info": {
    "법령명": "민법",
    "조항": "제105조",
    "제목": "법률행위의 무효",
    "시행일": "1960-01-01",
    "개정이력": [
      {
        "개정일": "2021-12-21",
        "개정내용": "일부개정"
      }
    ]
  },
  "processing_info": {
    "law_category": "민사법",
    "relevance_score": 0.9
  }
}
```

### 4. 판례 (Legal Case)

```json
{
  "type": "legal_case",
  "category": "대법원판례",
  "extracted_info": {
    "사건번호": "2020다12345",
    "판결일": "2020-12-15",
    "법원": "대법원",
    "주문": "원고의 청구를 기각한다",
    "판시사항": "계약해지의 효력에 관한 판시사항",
    "판결요지": "계약해지는 해지의 의사표시가 상대방에게 도달한 때에 효력이 생긴다",
    "관련법령": ["민법 제544조", "민법 제105조"]
  },
  "processing_info": {
    "case_type": "계약관계",
    "precedent_value": "binding"
  }
}
```

### 5. 가이드라인 (Guideline)

```json
{
  "type": "guideline",
  "category": "공정위가이드라인",
  "extracted_info": {
    "발행기관": "공정거래위원회",
    "발행일": "2023-06-15",
    "제목": "표준계약서 작성 가이드라인",
    "적용범위": "서비스계약서",
    "주요내용": ["계약서 작성 원칙", "필수 조항", "금지 조항"]
  },
  "processing_info": {
    "guideline_type": "계약서작성",
    "compliance_level": "mandatory"
  }
}
```

## 🔧 공통 필드

### processing_info (모든 문서)

```json
{
  "processing_info": {
    "ai_model": "claude-3-sonnet",
    "extraction_date": "2024-01-15T10:30:00Z",
    "processing_time": 45.2,
    "confidence_score": 0.95,
    "extraction_method": "ai_auto_extraction",
    "version": "1.0"
  }
}
```

### custom_fields (사용자 정의)

```json
{
  "custom_fields": {
    "프로젝트코드": "PRJ-2024-001",
    "담당부서": "법무팀",
    "우선순위": "high",
    "검토상태": "pending",
    "비고": "긴급 검토 필요"
  }
}
```

## 🎯 활용 시나리오

### 1. 문서 검색/필터링

```python
# 특정 유형의 계약서만 검색
documents = session.query(Document).filter(
    Document.metadata['type'].astext == 'contract'
)

# 특정 금액 범위의 계약서 검색
documents = session.query(Document).filter(
    Document.metadata['extracted_info']['계약금액']['금액'].astext.cast(Integer) > 10000000
)
```

### 2. AI 자동 분류

```python
# AI가 추출한 정보로 자동 태깅
auto_tags = [
    metadata.get('type'),
    metadata.get('category'),
    *metadata.get('extracted_info', {}).get('주요조항', [])
]
```

### 3. 초안작성 (표준계약서 → 계약서)

```python
# 표준계약서의 변수 정의로 UI 폼 생성
template_doc = get_document(template_id)
fields = template_doc.metadata['variables']['fields']

# 사용자 입력값으로 초안 생성
user_inputs = {
    "계약상대방": "ABC 주식회사",
    "계약금액": "1,000만원"
}

# HTML 템플릿에 변수 치환
draft_html = replace_variables(template_doc.html_content, user_inputs)
```

### 4. 문서 비교

```python
# 두 계약서의 변수 비교
doc1_vars = doc1.metadata.get('variables', {})
doc2_vars = doc2.metadata.get('variables', {})
differences = compare_variables(doc1_vars, doc2_vars)
```

## 📊 Variables vs Extracted_Info 비교표

| 구분           | Variables                     | Extracted_Info                                      |
| -------------- | ----------------------------- | --------------------------------------------------- |
| **목적**       | 초안작성/템플릿 치환          | 분석/검색/분류                                      |
| **형태**       | 단순 값 (String/Number)       | 구조화된 객체                                       |
| **용도**       | `{{변수명}}` 치환             | AI 분석, 검색 필터                                  |
| **표준계약서** | 입력 필드 정의                | 템플릿 메타데이터                                   |
| **일반계약서** | 실제 값                       | 추출된 구조화 정보                                  |
| **예시**       | `"계약상대방": "ABC주식회사"` | `"당사자": {"갑": "우리회사", "을": "ABC주식회사"}` |

## 🛠️ 구현 가이드

### 1. Metadata 생성 함수

```python
def create_document_metadata(
    doc_type: str,
    category: str,
    extracted_info: dict,
    variables: dict = None,
    custom_fields: dict = None
) -> dict:
    return {
        "type": doc_type,
        "category": category,
        "variables": variables or {},
        "extracted_info": extracted_info,
        "processing_info": {
            "ai_model": "claude-3-sonnet",
            "extraction_date": datetime.utcnow().isoformat(),
            "confidence_score": 0.95
        },
        "custom_fields": custom_fields or {}
    }
```

### 2. 표준계약서 Variables 생성

```python
def create_standard_contract_variables(fields: list) -> dict:
    return {
        "fields": [
            {
                "name": field["name"],
                "type": field["type"],
                "required": field.get("required", False),
                "description": field.get("description", ""),
                "placeholder": field.get("placeholder", "")
            }
            for field in fields
        ]
    }
```

### 3. Metadata 업데이트 함수

```python
def update_document_metadata(
    document_id: int,
    updates: dict,
    session: AsyncSession
):
    doc = session.get(Document, document_id)
    if doc:
        current_metadata = doc.metadata or {}
        current_metadata.update(updates)
        doc.metadata = current_metadata
        session.commit()
```

## ⚠️ 주의사항

1. **JSON 필드 인덱싱**: 자주 검색되는 필드는 별도 컬럼으로 분리 고려
2. **데이터 크기**: JSON 필드가 너무 커지면 성능 저하 가능
3. **스키마 버전 관리**: metadata 구조 변경 시 마이그레이션 필요
4. **데이터 검증**: JSON 스키마 검증으로 데이터 무결성 보장
5. **표준계약서 특별 처리**: `variables.fields`는 입력 필드 정의, 실제 값은 아님

## 🔄 확장 가능성

- **워크플로우 상태**: `workflow_status`, `approval_history`
- **알림 설정**: `notification_preferences`
- **접근 권한**: `access_control`, `sharing_settings`
- **분석 결과**: `risk_analysis`, `compliance_check`
- **버전 관리**: `version_history`, `change_log`
