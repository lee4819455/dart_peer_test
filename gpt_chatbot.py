import openai
import pandas as pd
import json
from typing import Optional, Dict, Any
import config

class GPTChatbot:
    def __init__(self, api_key: str):
        """GPT 챗봇 초기화"""
        if not api_key:
            raise ValueError("OpenAI API 키가 제공되지 않았습니다.")
        
        self.api_key = api_key
        self.client = openai.OpenAI(api_key=api_key)
    
    def analyze_data_and_answer(self, question: str, data: pd.DataFrame, question_type: str = "일반") -> str:
        """
        데이터를 분석하고 GPT-4를 통해 자연스러운 답변 생성
        
        Args:
            question: 사용자 질문
            data: 검색된 데이터
            question_type: 질문 유형 (유사기업, 재무비율, 기업검색, 일반)
        
        Returns:
            GPT-4가 생성한 자연스러운 답변
        """
        try:
            # 데이터를 문자열로 변환
            data_summary = self._format_data_for_gpt(data)
            
            # 프롬프트 구성
            if question_type in config.QUESTION_PROMPTS:
                context_prompt = config.QUESTION_PROMPTS[question_type].format(
                    business=question_type if question_type == "유사기업" else "",
                    sector=question_type if question_type in ["재무비율", "기업검색"] else ""
                )
            else:
                context_prompt = config.QUESTION_PROMPTS["일반"]
            
            # GPT-4 요청 메시지 구성
            messages = [
                {"role": "system", "content": config.SYSTEM_PROMPT},
                {"role": "user", "content": f"""
질문: {question}

{context_prompt}

데이터:
{data_summary}

위 데이터를 바탕으로 질문에 답변해주세요. 답변은 자연스러운 한국어로 작성하고, 
데이터의 맥락과 의미를 포함하여 전문적이면서도 이해하기 쉽게 설명해주세요.
GPT-4의 강력한 분석 능력을 활용하여 데이터에서 인사이트를 도출하고, 
사용자가 실제로 궁금해할 만한 추가 정보도 포함해주세요.
"""}
            ]
            
            # GPT-4 API 호출 (토큰 수 최적화)
            response = self.client.chat.completions.create(
                model="gpt-4",  # GPT-4 모델 사용
                messages=messages,
                max_tokens=1500,  # 게임 업계 등 데이터가 많은 경우를 위해 증가
                temperature=0.3,  # 더 일관된 답변을 위해 낮은 온도 설정
                top_p=0.9,  # 높은 품질의 답변을 위한 top_p 설정
                frequency_penalty=0.1,  # 반복 방지
                presence_penalty=0.1   # 새로운 정보 제공 장려
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            return f"GPT-4 분석 중 오류가 발생했습니다: {str(e)}"
    
    def _format_data_for_gpt(self, data: pd.DataFrame) -> str:
        """
        데이터프레임을 GPT-4가 이해하기 쉬운 형태로 변환 (토큰 수 최적화)
        
        Args:
            data: 검색된 데이터프레임
        
        Returns:
            포맷된 데이터 문자열
        """
        if data.empty:
            return "검색된 데이터가 없습니다."
        
        # 데이터 요약 정보 (간결하게)
        summary = f"총 {len(data)}건의 데이터가 검색되었습니다.\n\n"
        
        # 유사기업 데이터인 경우 특별한 포맷팅 적용
        if '유사기업' in data.columns and '공시발행_기업명' in data.columns:
            summary += "=== 유사기업 선정 정보 ===\n"
            
            # 데이터가 많을 경우 더 효율적인 요약 제공
            if len(data) > 15:
                # 데이터가 매우 많은 경우 통계적 요약
                summary += f"총 {len(data)}건의 유사기업 선정 데이터가 있습니다.\n\n"
                
                # 주요 기업별 요약
                company_counts = data['공시발행_기업명'].value_counts().head(5)
                summary += "주요 공시발행 기업 (상위 5개):\n"
                for company, count in company_counts.items():
                    summary += f"  - {company}: {count}건\n"
                
                # 산업분류별 요약
                industry_counts = data['평가대상기업_산업분류'].value_counts().head(3)
                summary += f"\n평가대상 기업 산업분류 (상위 3개):\n"
                for industry, count in industry_counts.items():
                    summary += f"  - {industry}: {count}건\n"
                
                # 처음 8건만 상세 표시 (토큰 절약)
                display_data = data.head(8)
                summary += f"\n=== 상세 정보 (처음 8건) ===\n"
            else:
                # 데이터가 적당한 경우 처음 10건 표시
                display_data = data.head(10)
                summary += f"총 {len(data)}건의 데이터를 분석합니다.\n\n"
            
            for idx, row in display_data.iterrows():
                summary += f"\n{idx+1}. {row.get('발행일자', 'N/A')}\n"
                summary += f"   공시발행기업: {row.get('공시발행_기업명', 'N/A')}\n"
                summary += f"   평가대상기업: {row.get('평가대상기업명', 'N/A')}\n"
                # 주요사업이 길면 잘라서 표시 (더 짧게)
                main_business = str(row.get('평가대상_주요사업', ''))
                if len(main_business) > 80:
                    summary += f"   주요사업: {main_business[:80]}...\n"
                else:
                    summary += f"   주요사업: {main_business}\n"
                summary += f"   공시보고서명: {row.get('공시보고서명', 'N/A')}\n"
                summary += f"   유사기업: {row.get('유사기업', 'N/A')}\n"
                # 링크 정보가 있으면 포함
                if 'Link' in row and pd.notna(row.get('Link')) and str(row.get('Link')).strip() != '':
                    summary += f"   원문링크: {row.get('Link')}\n"
                summary += "   ---\n"
            
            if len(data) > 8:
                summary += f"\n... 외 {len(data) - 8}건의 데이터가 더 있습니다."
                summary += f"\n※ 전체 데이터는 원본 데이터베이스에서 확인 가능합니다."
        else:
            # 일반적인 데이터 포맷팅 (간결하게)
            for col in data.columns:
                if col in ['공시발행_기업명', '평가대상기업명', '유사기업']:
                    # 기업명 관련 컬럼은 고유값만 표시 (최대 5개)
                    unique_values = data[col].dropna().unique()
                    if len(unique_values) > 0:
                        summary += f"{col}: {', '.join(unique_values[:5])}"
                        if len(unique_values) > 5:
                            summary += f" 외 {len(unique_values) - 5}개"
                        summary += "\n"
                
                elif col in ['발행일자']:
                    # 날짜 컬럼은 범위만 표시
                    dates = pd.to_datetime(data[col], errors='coerce').dropna()
                    if len(dates) > 0:
                        summary += f"{col}: {dates.min().strftime('%Y-%m-%d')} ~ {dates.max().strftime('%Y-%m-%d')}\n"
                
                elif col in ['EV/Sales', 'PSR', 'Ke', 'Kd', 'WACC', 'D/E']:
                    # 재무비율 컬럼은 기본 통계만 표시
                    numeric_data = pd.to_numeric(data[col], errors='coerce').dropna()
                    if len(numeric_data) > 0:
                        summary += f"{col}: 평균 {numeric_data.mean():.2f}, 범위 {numeric_data.min():.2f}~{numeric_data.max():.2f}\n"
                
                elif col in ['공시발행_기업_산업분류', '평가대상_주요사업']:
                    # 산업분류는 상위 3개만 표시
                    value_counts = data[col].value_counts().head(3)
                    if len(value_counts) > 0:
                        summary += f"{col} (상위 3개): {', '.join([f'{k}({v}건)' for k, v in value_counts.items()])}\n"
        
        # 상세 데이터 샘플은 제거하여 토큰 수 절약
        summary += f"\n※ 상세 데이터는 원본 데이터베이스에서 확인 가능합니다."
        
        return summary
    
    def get_question_type(self, question: str) -> str:
        """
        질문의 타입을 분류하여 적절한 프롬프트 선택
        """
        question_lower = question.lower()
        
        # 유사기업 관련 질문 (음원, 가상자산, 게임 등 특정 사업 포함)
        if any(keyword in question_lower for keyword in ['유사기업', '유사', '비교', '선정', 'peer', '피어', '음원', '가상자산', '게임', '금융', '제조', '서비스', '정보보안', '보안', '사이버보안', '보안솔루션', '보안시스템']):
            return "유사기업"
        
        # 재무비율 관련 질문 (실제 DB에 있는 컬럼명으로 수정)
        elif any(keyword in question_lower for keyword in ['ev/sales', 'psr', 'ke', 'kd', 'wacc', 'd/e', '재무비율', '비율', '평가']):
            return "재무비율"
        
        # 기업 검색 관련 질문
        elif any(keyword in question_lower for keyword in ['기업', '회사', '업종', '산업', '섹터', 'sector']):
            return "기업검색"
        
        # 기본 타입
        else:
            return "일반"
    
    def generate_follow_up_questions(self, question: str, data: pd.DataFrame) -> list:
        """
        현재 질문과 데이터를 바탕으로 후속 질문 제안 (GPT-4 활용)
        
        Args:
            question: 현재 질문
            data: 검색된 데이터
        
        Returns:
            후속 질문 리스트
        """
        try:
            # 후속 질문 생성을 위한 프롬프트
            follow_up_prompt = f"""
현재 질문: {question}

검색된 데이터: {self._format_data_for_gpt(data)}

위 질문과 데이터를 바탕으로 사용자가 추가로 궁금해할 만한 후속 질문 3개를 한국어로 제안해주세요.
GPT-4의 강력한 분석 능력을 활용하여 다음을 고려해주세요:

1. 현재 질문과 논리적으로 연결되는 질문
2. 데이터에서 추가로 분석할 수 있는 관점
3. 실무적으로 유용한 인사이트를 얻을 수 있는 질문
4. 금융 분석의 관점에서 중요한 추가 정보

각 질문은 구체적이고 실용적이어야 하며, 데이터에서 답변할 수 있는 내용이어야 합니다.

답변 형식:
1. [첫 번째 후속 질문]
2. [두 번째 후속 질문]  
3. [세 번째 후속 질문]
"""
            
            messages = [
                {"role": "system", "content": "당신은 사용자의 질문을 분석하여 관련된 후속 질문을 제안하는 금융 분석 전문가입니다. GPT-4의 강력한 분석 능력을 활용하여 실용적이고 통찰력 있는 질문을 제안해주세요."},
                {"role": "user", "content": follow_up_prompt}
            ]
            
            response = self.client.chat.completions.create(
                model="gpt-4",  # GPT-4 모델 사용
                messages=messages,
                max_tokens=400,  # 후속 질문 생성을 위해 토큰 수 증가
                temperature=0.4,  # 창의적이면서도 일관된 질문 생성을 위한 온도 설정
                top_p=0.9
            )
            
            # 응답을 질문 리스트로 파싱
            content = response.choices[0].message.content
            questions = []
            
            # 번호가 있는 질문들을 추출
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                if line and (line.startswith('1.') or line.startswith('2.') or line.startswith('3.')):
                    question_text = line.split('.', 1)[1].strip()
                    if question_text:
                        questions.append(question_text)
            
            return questions[:3]  # 최대 3개 반환
            
        except Exception as e:
            return ["데이터에 대한 추가 질문이 있으시면 말씀해주세요."]
