import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import re
import time
from gpt_chatbot import GPTChatbot
import config
import os
import json
from difflib import SequenceMatcher

# 스마트 검색 시스템 클래스
class SmartSearchSystem:
    def __init__(self):
        # 키워드 사전 로드
        try:
            with open('business_keywords.json', 'r', encoding='utf-8') as f:
                self.keyword_dict = json.load(f)
            
            with open('similar_industries.json', 'r', encoding='utf-8') as f:
                self.similar_industries = json.load(f)
        except FileNotFoundError:
            st.warning("키워드 사전 파일을 찾을 수 없습니다. 기본 검색 모드로 동작합니다.")
            self.keyword_dict = {}
            self.similar_industries = {}
    
    def find_exact_match(self, query):
        """1차 검색: DB에 있는 정확한 키워드 매칭 (구체적인 키워드 우선)"""
        query_lower = query.lower()
        exact_matches = []
        
        # 특정 키워드 그룹이 질문에 포함되어 있는지 먼저 확인
        priority_keywords = ['ai', '클라우드', '블록체인', 'iot', '바이오', '신재생에너지', '전기차', '반도체']
        question_has_priority_keyword = any(keyword in query_lower for keyword in priority_keywords)
        
        # 모든 키워드에서 정확한 매칭 찾기
        for category, keywords in self.keyword_dict.items():
            if category != 'all_keywords':
                for keyword in keywords:
                    if keyword.lower() in query_lower:
                        # 키워드 길이와 포함 여부에 따른 우선순위 계산
                        priority_score = 0
                        
                        # 1순위: 질문에 정확히 포함된 키워드
                        if keyword.lower() in query_lower:
                            priority_score += 1000
                        
                        # 2순위: 키워드 길이 (긴 것 우선) - 복합 키워드 우선
                        priority_score += len(keyword) * 10  # 길이에 더 큰 가중치
                        
                        # 3순위: 복합 키워드 우선 (공백이나 특수문자가 없는 긴 키워드)
                        if len(keyword) >= 4 and ' ' not in keyword and keyword.isalnum():
                            priority_score += 500
                        
                        # 4순위: 특정 키워드 그룹 우선 (AI, 클라우드, 블록체인 등) - 매우 높은 우선순위
                        if keyword.lower() in priority_keywords:
                            priority_score += 800  # 매우 높은 우선순위
                            
                            # 질문에 우선 키워드가 포함되어 있고, 현재 키워드가 그 중 하나라면 최우선 처리
                            if question_has_priority_keyword:
                                priority_score += 2000  # 추가 보너스
                        
                        # 5순위: 일반적인 단어 강력한 페널티 (솔루션, 플랫폼, 시스템 등)
                        general_words = ['솔루션', '플랫폼', '시스템', '서비스', '기술', '개발', '제공', '업계', '사업']
                        if keyword.lower() in general_words:
                            priority_score -= 600  # 강력한 페널티
                            
                            # 질문에 우선 키워드가 포함되어 있을 때는 일반 단어에 더 강한 페널티
                            if question_has_priority_keyword:
                                priority_score -= 1000  # 추가 페널티
                        
                        # 6순위: 카테고리별 가중치
                        category_weights = {
                            'it_software': 100,
                            'game': 100,
                            'finance': 100,
                            'manufacturing': 100,
                            'security': 100
                        }
                        priority_score += category_weights.get(category, 0)
                        
                        exact_matches.append({
                            'keyword': keyword,
                            'category': category,
                            'match_type': 'exact',
                            'confidence': 1.0,
                            'priority_score': priority_score
                        })
        
        # 우선순위 점수로 정렬 (높은 점수 우선)
        exact_matches.sort(key=lambda x: x['priority_score'], reverse=True)
        
        return exact_matches
    
    def find_similar_industries(self, query):
        """2차 검색: 유사성이 높은 업종 찾기"""
        query_lower = query.lower()
        similar_matches = []
        
        # 유사 업종 매핑에서 찾기
        for industry, related_keywords in self.similar_industries.items():
            if industry.lower() in query_lower:
                similar_matches.append({
                    'keyword': industry,
                    'related_keywords': related_keywords,
                    'match_type': 'similar_industry',
                    'confidence': 0.9
                })
        
        # 유사도 기반 매칭
        for keyword in self.keyword_dict.get('all_keywords', []):
            similarity = SequenceMatcher(None, query_lower, keyword.lower()).ratio()
            if similarity > 0.6:
                similar_matches.append({
                    'keyword': keyword,
                    'related_keywords': [keyword],
                    'match_type': 'similarity_based',
                    'confidence': similarity
                })
        
        return similar_matches
    
    def smart_search(self, query):
        """스마트 검색: 1차 정확 매칭 + 2차 유사 업종 검색"""
        # 1차 검색: 정확한 키워드 매칭
        exact_matches = self.find_exact_match(query)
        
        # 2차 검색: 유사 업종 검색
        similar_matches = self.find_similar_industries(query)
        
        # 결과 통합 및 정렬
        all_matches = exact_matches + similar_matches
        all_matches.sort(key=lambda x: x['confidence'], reverse=True)
        
        return all_matches

# 전역 변수로 스마트 검색 시스템 초기화
@st.cache_resource
def get_smart_search_system():
    return SmartSearchSystem()

# 페이지 설정
st.set_page_config(
    page_title="주요사항보고서 공시 DB",
    page_icon="📊",
    layout="wide"
)

# 세션 상태 초기화
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'gpt_chatbot' not in st.session_state:
    st.session_state.gpt_chatbot = None

# 데이터베이스 연결 함수
def get_db_connection():
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        return conn
    except Exception as e:
        st.error(f"데이터베이스 연결 오류: {e}")
        return None

# 데이터 검색 함수들
def search_by_sector(sector):
    """특정 섹터/산업의 기업들 검색"""
    conn = get_db_connection()
    if conn is None:
        return None
    
    query = """
    SELECT DISTINCT 
        공시보고서명,
        발행일자,
        공시발행_기업명,
        공시발행_기업_산업분류,
        평가대상기업명,
        평가대상_주요사업,
        유사기업,
        WACC,
        Link
    FROM 외평보고서 
    WHERE 공시발행_기업_산업분류 LIKE ? OR 평가대상_주요사업 LIKE ?
    ORDER BY 발행일자 DESC
    """
    
    try:
        df = pd.read_sql_query(query, conn, params=[f'%{sector}%', f'%{sector}%'])
        conn.close()
        return df
    except Exception as e:
        st.error(f"검색 오류: {e}")
        conn.close()
        return None

def search_similar_companies(business_keyword):
    """
    특정 사업 키워드와 관련된 유사기업 정보를 검색
    """
    try:
        conn = sqlite3.connect('외평보고서.db')
        
        # 음원, 가상자산 등 특정 키워드에 대한 더 정확한 검색
        query = """
        SELECT DISTINCT
            공시발행_기업명,
            공시발행_기업_산업분류,
            평가대상기업명,
            평가대상기업_산업분류,
            평가대상_주요사업,
            공시보고서명,
            발행일자,
            유사기업,
            Link
        FROM 외평보고서
        WHERE (
            평가대상_주요사업 LIKE ? OR 
            평가대상기업_산업분류 LIKE ? OR
            공시발행_기업_산업분류 LIKE ?
        )
        AND 유사기업 IS NOT NULL AND 유사기업 != ''
        ORDER BY 발행일자 DESC
        """
        
        # 키워드 매칭을 위한 패턴 생성
        keyword_pattern = f"%{business_keyword}%"
        
        df = pd.read_sql_query(query, conn, params=[keyword_pattern, keyword_pattern, keyword_pattern])
        conn.close()
        
        return df
        
    except Exception as e:
        st.error(f"검색 오류: {e}")
        return pd.DataFrame()

def search_financial_ratios(sector, start_date=None, end_date=None):
    """특정 섹터와 기간의 재무비율 검색"""
    conn = get_db_connection()
    if conn is None:
        return None
    
    # 기본 쿼리 (실제 존재하는 컬럼만 사용)
    query = """
    SELECT 
        공시발행_기업명,
        공시발행_기업_산업분류,
        발행일자,
        "EV/Sales",
        PSR,
        Ke,
        Kd,
        WACC,
        "D/E"
    FROM 외평보고서 
    WHERE (공시발행_기업_산업분류 LIKE ? OR 평가대상_주요사업 LIKE ?)
    """
    
    params = [f'%{sector}%', f'%{sector}%']
    
    # 날짜 필터 추가
    if start_date:
        query += " AND 발행일자 >= ?"
        params.append(start_date)
    if end_date:
        query += " AND 발행일자 <= ?"
        params.append(end_date)
    
    query += " ORDER BY 발행일자 DESC"
    
    try:
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        return df
    except Exception as e:
        st.error(f"검색 오류: {e}")
        conn.close()
        return None

def get_available_sectors():
    """사용 가능한 섹터 목록 조회"""
    conn = get_db_connection()
    if conn is None:
        return []
    
    query = """
    SELECT DISTINCT 공시발행_기업_산업분류 
    FROM 외평보고서 
    WHERE 공시발행_기업_산업분류 IS NOT NULL 
    AND 공시발행_기업_산업분류 != ''
    ORDER BY 공시발행_기업_산업분류
    """
    
    try:
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df['공시발행_기업_산업분류'].tolist()
    except Exception as e:
        st.error(f"섹터 목록 조회 오류: {e}")
        conn.close()
        return []

def initialize_gpt_chatbot(api_key: str):
    """GPT 챗봇 초기화"""
    try:
        if st.session_state.gpt_chatbot is None:
            st.session_state.gpt_chatbot = GPTChatbot(api_key)
        return st.session_state.gpt_chatbot
    except Exception as e:
        st.error(f"GPT 챗봇 초기화 실패: {e}")
        return None

def add_to_chat_history(question, answer, data=None):
    """채팅 히스토리에 대화 추가"""
    st.session_state.chat_history.append({
        'question': question,
        'answer': answer,
        'data': data,
        'timestamp': datetime.now()
    })

def display_chat_history():
    """채팅 히스토리 표시"""
    if not st.session_state.chat_history:
        return
    
    st.subheader("💬 대화 기록")
    
    for i, chat in enumerate(reversed(st.session_state.chat_history)):
        with st.expander(f"질문 {len(st.session_state.chat_history) - i}: {chat['question'][:50]}...", expanded=False):
            st.markdown(f"**질문:** {chat['question']}")
            st.markdown(f"**답변:** {chat['answer']}")
            
            if chat['data'] is not None and not chat['data'].empty:
                st.markdown("**관련 데이터:**")
                st.dataframe(chat['data'])
            
            st.markdown(f"*{chat['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}*")

def generate_structured_sentences(data):
    """검색된 데이터를 바탕으로 구조화된 문장을 자동 생성"""
    if data.empty:
        return "데이터가 없습니다."
    
    sentences = []
    
    for idx, row in data.iterrows():
        # 기본 정보 추출
        발행일자 = row.get('발행일자', 'N/A')
        공시발행_기업명 = row.get('공시발행_기업명', 'N/A')
        평가대상기업명 = row.get('평가대상기업명', 'N/A')
        공시보고서명 = row.get('공시보고서명', 'N/A')
        유사기업 = row.get('유사기업', 'N/A')
        Link = row.get('Link', '')
        
        # 공시보고서명이 없거나 비어있으면 기본값 사용
        if pd.isna(공시보고서명) or 공시보고서명 == '':
            공시보고서명 = "주요사항보고서"
        
        # 유사기업 정보 정리
        if pd.notna(유사기업) and 유사기업 != '':
            # 쉼표나 세미콜론으로 구분된 유사기업들을 리스트로 변환
            if isinstance(유사기업, str):
                similar_companies = [company.strip() for company in 유사기업.replace(';', ',').split(',') if company.strip()]
            else:
                similar_companies = [str(유사기업)]
            
            # 유사기업 리스트를 쉼표로 연결
            similar_companies_str = ', '.join(similar_companies)
            
            # 문장 생성
            sentence = f"{발행일자}\n{공시발행_기업명}은 「{공시보고서명}」에서 {평가대상기업명} 관련 평가 시 유사기업으로 {similar_companies_str}을 선정했다."
            
            # 링크가 있으면 추가
            if pd.notna(Link) and Link != '' and str(Link).strip() != '':
                sentence += f"\n\n원문은 여기에서 확인할 수 있다: {Link}"
            
            sentences.append(sentence)
    
    return "\n\n".join(sentences)

# 메인 앱
def main():
    st.title(" 주요사항보고서 공시 DB")
    st.markdown("---")
    
    # 사이드바 설정
    with st.sidebar:
        st.header("🔑 API 설정 (선택사항)")
        api_key = st.text_input("OpenAI API 키를 입력하세요 (선택사항)", type="password", help="API 키를 입력하면 GPT-4로 상세한 분석을 받을 수 있습니다.")
        
        if api_key:
            st.success("✅ API 키가 설정되었습니다! GPT-4 분석을 사용할 수 있습니다.")
        else:
            st.info("ℹ️ API 키 없이도 유사기업 정보를 표 형태로 확인할 수 있습니다.")
        
        st.markdown("---")
        st.header("📚 사용법")
        st.markdown("""
        **기본 사용 (API 키 없이):**
        - 유사기업 정보를 표 형태로 바로 확인 가능
        
        **고급 사용 (API 키 입력 시):**
        - GPT-4로 상세한 분석 및 인사이트 제공
        - 자연어로 된 종합적인 답변
        """)
        
        st.markdown("---")
        st.header("💡 예시 질문")
        st.markdown("""
        - "가상자산 사업 유사기업"
        - "음원 사업 유사기업"
        - "게임 업계 유사기업"
        - "금융업 기업들의 EV/Sales"
        """)
    
    # 메인 탭
    tab1,  tab2 = st.tabs(["💬 챗봇",  "🔍 데이터 검색"])
    
    with tab1:
        st.header("💬 챗봇과 대화하기")
        
        # 예시 질문 버튼들
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("가상자산 사업 유사기업"):
                st.session_state.example_question = "가상자산 사업을 하는 기업들이 선정한 유사기업은 무엇인가요?"
            if st.button("음원 사업 유사기업"):
                st.session_state.example_question = "음원 사업을 하는 기업들이 선정한 유사기업은 무엇인가요?"
            if st.button("AI 업계 유사기업"):
                st.session_state.example_question = "AI 업계 기업들이 선정한 유사기업은 무엇인가요?"
        
        with col2:
            if st.button("바이오 업계 유사기업"):
                st.session_state.example_question = "바이오 업계 기업들이 선정한 유사기업은 무엇인가요?"
            if st.button("게임 업계 유사기업"):
                st.session_state.example_question = "게임 업계 기업들이 선정한 유사기업은 무엇인가요?"
            if st.button("클라우드 유사기업"):
                st.session_state.example_question = "클라우드 사업을 하는 기업들이 선정한 유사기업은 무엇인가요?"
        
        with col3:
            if st.button("정보보안 업계 유사기업"):
                st.session_state.example_question = "정보보안 업계 기업들이 선정한 유사기업은 무엇인가요?"
            if st.button("금융업 기업들의 EV/Sales"):
                st.session_state.example_question = "2022년 이후 발행된 금융업 기업들의 EV/Sales 값은 어떻게 되나요?"
            if st.button("블록체인 유사기업"):
                st.session_state.example_question = "블록체인 사업을 하는 기업들이 선정한 유사기업은 무엇인가요?"
        
        # 사용자 입력
        user_question = st.text_input(
            "질문을 입력하세요:",
            value=st.session_state.get("example_question", ""),
            placeholder="예: 가상자산 사업을 하는 기업들이 선정한 유사기업은 무엇인가요?"
        )
        
        if st.button("질문하기") or user_question:
            if user_question:
                # API 키 없이도 답변 가능한 질문 유형들
                api_not_required_keywords = ["유사기업", "유사", "EV/Sales", "재무비율", "PSR", "WACC", "Ke", "Kd", "D/E"]
                api_not_required = any(keyword in user_question for keyword in api_not_required_keywords)
                
                if not api_key and not api_not_required:
                    st.error("❌ API 키를 먼저 입력해주세요.")
                    return
                
                # GPT 챗봇 초기화 (API 키가 있는 경우에만)
                chatbot = None
                if api_key:
                    try:
                        chatbot = initialize_gpt_chatbot(api_key)
                        if chatbot is None:
                            st.error("❌ GPT 챗봇 초기화 실패")
                            return
                    except Exception as e:
                        st.error(f"❌ GPT 챗봇 초기화 실패: {e}")
                        return
                
                # 데이터 검색
                if "유사기업" in user_question or "유사" in user_question:
                    # 스마트 검색 시스템으로 키워드 추출
                    smart_search = get_smart_search_system()
                    matches = smart_search.smart_search(user_question)
                    
                    if matches:
                        # 상위 매칭 결과로 검색
                        top_match = matches[0]
                        search_keyword = top_match['keyword']
                        
                        # 검색 결과 표시
                        st.info(f"🔍 스마트 검색 결과:")
                        st.info(f"   최적 매칭: '{search_keyword}' ({top_match['match_type']}, 신뢰도: {top_match['confidence']:.2f})")
                        
                        if 'related_keywords' in top_match and len(top_match['related_keywords']) > 1:
                            st.info(f"   관련 키워드: {', '.join(top_match['related_keywords'][:3])}")
                        
                        # 데이터베이스 검색
                        data = search_similar_companies(search_keyword)
                        
                        if not data.empty:
                            st.success(f"✅ '{search_keyword}' 관련 유사기업 {len(data)}건을 찾았습니다.")
                            
                            # 구조화된 문장으로 답변 생성 (API 없이도 답변 가능)
                            st.markdown("### 📊 유사기업 선정 정보")
                            
                            # 자동으로 구조화된 문장 생성
                            structured_answer = generate_structured_sentences(data)
                            if structured_answer and structured_answer.strip():
                                st.markdown(structured_answer)
                            else:
                                st.warning("구조화된 문장을 생성할 수 없습니다.")
                            
                            # 원본 데이터도 표 형태로 표시 (참고용)
                            st.markdown("### 📊 원본 데이터 (참고용)")
                            display_data = data.copy()
                            
                            # 주요사업 컬럼 길이 제한
                            if '평가대상_주요사업' in display_data.columns:
                                display_data['평가대상_주요사업'] = display_data['평가대상_주요사업'].astype(str).apply(
                                    lambda x: x[:50] + "..." if len(x) > 50 else x
                                )
                            
                            # 표 형태로 데이터 표시
                            st.dataframe(
                                display_data[['발행일자', '공시보고서명','공시발행_기업명', '평가대상기업명', '평가대상_주요사업', '유사기업', 'Link']],
                                width='stretch',
                                hide_index=True
                            )
                            
                            # 요약 정보 표시
                            st.markdown("### 📈 요약 정보")
                            col1, col2, col3 = st.columns(3)
                            
                            with col1:
                                st.metric("총 건수", len(data))
                            
                            with col2:
                                unique_companies = data['공시발행_기업명'].nunique()
                                st.metric("공시발행 기업 수", unique_companies)
                            
                            with col3:
                                unique_targets = data['평가대상기업명'].nunique()
                                st.metric("평가대상 기업 수", unique_targets)
                            
                            # API가 있는 경우 GPT 분석 추가 제공
                            if api_key:
                                st.markdown("---")
                                st.markdown("### 🤖 GPT-4 상세 분석 (선택사항)")
                                
                                if st.button("GPT-4로 상세 분석하기"):
                                    try:
                                        # 기존에 초기화된 챗봇 사용
                                        if chatbot is None:
                                            chatbot = initialize_gpt_chatbot(api_key)
                                        
                                        if chatbot is not None:
                                            question_type = chatbot.get_question_type(user_question)
                                            answer = chatbot.analyze_data_and_answer(user_question, data, question_type)
                                            
                                            st.markdown("#### 🤖 GPT-4 상세 분석")
                                            st.markdown(answer)
                                        else:
                                            st.error("❌ GPT 챗봇을 초기화할 수 없습니다.")
                                        
                                    except Exception as e:
                                        st.error(f"❌ GPT-4 분석 중 오류가 발생했습니다: {e}")
                                        st.info("데이터는 이미 위에 표시되어 있습니다.")
                            else:
                                st.info("💡 OpenAI API 키를 입력하면 GPT-4로 더 상세한 분석을 받을 수 있습니다.")
                            
                        else:
                            st.warning(f"'{search_keyword}'와 관련된 유사기업 데이터를 찾을 수 없습니다.")
                            st.info("다른 키워드로 검색해보세요.")
                            return
                    else:
                        # 스마트 검색으로 키워드를 찾지 못한 경우 기존 방식 사용
                        st.info("🔍 스마트 검색으로 키워드를 찾지 못했습니다. 기본 검색 모드로 전환합니다.")
                        
                        # 기존 키워드 추출 로직 (폴백)
                        business_keywords = []
                        question_lower = user_question.lower()
                        
                        # 미리 정의된 키워드에서 찾기
                        common_businesses = ['음원', '가상자산', '게임', '금융', '제조', '서비스', 'IT', '소프트웨어', '하드웨어', '바이오', '제약', '화학', '철강', '자동차', '건설', '부동산', '유통', '식품', '음료', '의류', '화장품', '여행', '항공', '선박', '에너지', '전력', '가스', '통신', '미디어', '교육', '의료', '보험', '은행', '증권', '투자', '펀드', '부동산신탁', '리츠', '정보보안', '보안', '사이버보안', '보안솔루션', '보안시스템']
                        
                        for business in common_businesses:
                            if business in question_lower:
                                business_keywords.append(business)
                                break
                        
                        if not business_keywords:
                            # 질문에서 직접 추출
                            import re
                            patterns = [r'(\w+)\s*사업', r'(\w+)\s*업종', r'(\w+)\s*기업', r'(\w+)\s*회사', r'(\w+)\s*업계']
                            for pattern in patterns:
                                matches = re.findall(pattern, user_question)
                                if matches:
                                    business_keywords.extend(matches)
                                    break
                        
                        if not business_keywords:
                            business_keywords = [user_question.replace('유사기업', '').replace('은', '').replace('는', '').replace('무엇인가요', '').replace('?', '').strip()]
                        
                        search_keyword = business_keywords[0] if business_keywords else "일반"
                        st.info(f"🔍 '{search_keyword}' 관련 유사기업을 검색 중...")
                        data = search_similar_companies(search_keyword)
                        
                        if data.empty:
                            st.warning(f"'{search_keyword}'와 관련된 유사기업 데이터를 찾을 수 없습니다.")
                            st.info("다른 키워드로 검색해보세요.")
                            return
                        
                        st.success(f"✅ '{search_keyword}' 관련 유사기업 {len(data)}건을 찾았습니다.")
                        
                        # 구조화된 문장으로 답변 생성 (API 없이도 답변 가능)
                        st.markdown("### 📊 유사기업 선정 정보")
                        
                        # 자동으로 구조화된 문장 생성
                        structured_answer = generate_structured_sentences(data)
                        if structured_answer and structured_answer.strip():
                            st.markdown(structured_answer)
                        else:
                            st.warning("구조화된 문장을 생성할 수 없습니다.")
                        
                        # 원본 데이터도 표 형태로 표시 (참고용)
                        st.markdown("### 📊 원본 데이터 (참고용)")
                        
                        # 데이터 정리 및 표시
                        display_data = data.copy()
                        
                        # 주요사업 컬럼 길이 제한
                        if '평가대상_주요사업' in display_data.columns:
                            display_data['평가대상_주요사업'] = display_data['평가대상_주요사업'].astype(str).apply(
                                lambda x: x[:50] + "..." if len(x) > 50 else x
                            )
                        
                        # 표 형태로 데이터 표시
                        st.dataframe(
                            display_data[['발행일자', '공시발행_기업명', '평가대상기업명', '평가대상_주요사업', '유사기업', '공시보고서명']],
                            width='stretch',
                            hide_index=True
                        )
                        
                        # 요약 정보 표시
                        st.markdown("### 📈 요약 정보")
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.metric("총 건수", len(data))
                        
                        with col2:
                            unique_companies = data['공시발행_기업명'].nunique()
                            st.metric("공시발행 기업 수", unique_companies)
                        
                        with col3:
                            unique_targets = data['평가대상기업명'].nunique()
                            st.metric("평가대상 기업 수", unique_targets)
                        
                        # API가 있는 경우 GPT 분석 추가 제공
                        if api_key:
                            st.markdown("---")
                            st.markdown("### 🤖 GPT-4 상세 분석 (선택사항)")
                            
                            if st.button("GPT-4로 상세 분석하기"):
                                try:
                                    # 기존에 초기화된 챗봇 사용
                                    if chatbot is None:
                                        chatbot = initialize_gpt_chatbot(api_key)
                                    
                                    if chatbot is not None:
                                        question_type = chatbot.get_question_type(user_question)
                                        answer = chatbot.analyze_data_and_answer(user_question, data, question_type)
                                        
                                        st.markdown("#### 🤖 GPT-4 상세 분석")
                                        st.markdown(answer)
                                    else:
                                        st.error("❌ GPT 챗봇을 초기화할 수 없습니다.")
                                    
                                except Exception as e:
                                    st.error(f"❌ GPT-4 분석 중 오류가 발생했습니다: {e}")
                                    st.info("데이터는 이미 위에 표시되어 있습니다.")
                        else:
                            st.info("💡 OpenAI API 키를 입력하면 GPT-4로 더 상세한 분석을 받을 수 있습니다.")
                
                elif "EV/Sales" in user_question or "재무비율" in user_question:
                    # 재무비율 검색 - 섹터 키워드 추출
                    sector_keywords = ['금융', 'IT', '제조', '서비스', '바이오', '게임', '소프트웨어', '화학', '철강', '자동차', '건설', '부동산', '유통', '식품', '음료', '의류', '화장품', '여행', '항공', '선박', '에너지', '전력', '가스', '통신', '미디어', '교육', '의료', '보험', '은행', '증권', '투자', '펀드', '부동산신탁', '리츠', '정보보안', '보안', '사이버보안', '보안솔루션', '보안시스템']
                    
                    sector = None
                    for keyword in sector_keywords:
                        if keyword in user_question:
                            sector = keyword
                            break
                    
                    # 섹터를 찾지 못한 경우 기본값
                    if sector is None:
                        sector = "금융"
                    
                    # 날짜 필터 추출 - 더 유연한 패턴 매칭
                    start_date = None
                    import re
                    
                    # 연도 패턴 찾기 (예: 2022, 2023, 2024 등)
                    year_patterns = [
                        r'(\d{4})년 이후',
                        r'(\d{4})년부터',
                        r'(\d{4}) 이후',
                        r'(\d{4})부터',
                        r'(\d{4})년'
                    ]
                    
                    for pattern in year_patterns:
                        match = re.search(pattern, user_question)
                        if match:
                            year = int(match.group(1))
                            start_date = f"{year}-01-01"
                            break
                    
                    data = search_financial_ratios(sector, start_date=start_date)
                    if not data.empty:
                        # 검색 조건 표시
                        search_info = f"✅ {sector}업 재무비율 데이터 {len(data)}건을 찾았습니다."
                        if start_date:
                            search_info += f" (검색 기간: {start_date} 이후)"
                        st.success(search_info)
                        
                        # 검색 조건 요약
                        st.info(f"🔍 검색 조건: 섹터='{sector}'" + (f", 시작일='{start_date}'" if start_date else ""))
                        
                        # 재무비율 데이터 표시
                        st.markdown("### 📊 재무비율 데이터")
                        
                        # EV/Sales 값이 있는 데이터만 필터링
                        if 'EV/Sales' in data.columns:
                            ev_sales_data = data[data['EV/Sales'].notna() & (data['EV/Sales'] != '')]
                            if not ev_sales_data.empty:
                                st.markdown("#### EV/Sales 값")
                                display_cols = ['공시발행_기업명', '공시발행_기업_산업분류', '발행일자', 'EV/Sales']
                                st.dataframe(ev_sales_data[display_cols], width='stretch', hide_index=True)
                                
                                # EV/Sales 통계
                                try:
                                    ev_sales_values = pd.to_numeric(ev_sales_data['EV/Sales'], errors='coerce')
                                    ev_sales_values = ev_sales_values.dropna()
                                    if not ev_sales_values.empty:
                                        st.markdown("#### EV/Sales 통계")
                                        col1, col2, col3, col4 = st.columns(4)
                                        with col1:
                                            st.metric("평균", f"{ev_sales_values.mean():.2f}")
                                        with col2:
                                            st.metric("중간값", f"{ev_sales_values.median():.2f}")
                                        with col3:
                                            st.metric("최소값", f"{ev_sales_values.min():.2f}")
                                        with col4:
                                            st.metric("최대값", f"{ev_sales_values.max():.2f}")
                                except:
                                    pass
                            else:
                                st.warning("EV/Sales 값이 있는 데이터가 없습니다.")
                        
                        # 전체 재무비율 데이터 표시
                        st.markdown("#### 전체 재무비율 데이터")
                        display_cols = ['공시발행_기업명', '공시발행_기업_산업분류', '발행일자', 'EV/Sales', 'PSR', 'WACC']
                        available_cols = [col for col in display_cols if col in data.columns]
                        st.dataframe(data[available_cols], width='stretch', hide_index=True)
                        
                        # API가 있는 경우 GPT 분석 추가 제공
                        if api_key:
                            st.markdown("---")
                            st.markdown("### 🤖 GPT-4 상세 분석 (선택사항)")
                            
                            if st.button("GPT-4로 재무비율 분석하기"):
                                try:
                                    # 기존에 초기화된 챗봇 사용
                                    if chatbot is None:
                                        chatbot = initialize_gpt_chatbot(api_key)
                                    
                                    if chatbot is not None:
                                        question_type = chatbot.get_question_type(user_question)
                                        answer = chatbot.analyze_data_and_answer(user_question, data, question_type)
                                        
                                        st.markdown("#### 🤖 GPT-4 상세 분석")
                                        st.markdown(answer)
                                    else:
                                        st.error("❌ GPT 챗봇을 초기화할 수 없습니다.")
                                    
                                except Exception as e:
                                    st.error(f"❌ GPT-4 분석 중 오류가 발생했습니다: {e}")
                                    st.info("데이터는 이미 위에 표시되어 있습니다.")
                        else:
                            st.info("💡 OpenAI API 키를 입력하면 GPT-4로 더 상세한 분석을 받을 수 있습니다.")
                        
                    else:
                        st.warning(f"{sector}업 재무비율 데이터를 찾을 수 없습니다.")
                        return
                else:
                    # 일반 기업 검색
                    data = search_by_sector(user_question)
                    if not data.empty:
                        st.success(f"✅ '{user_question}' 관련 데이터 {len(data)}건을 찾았습니다.")
                    else:
                        st.warning("관련 데이터를 찾을 수 없습니다.")
                        return
                
                # GPT 분석 및 답변 (재무비율 질문이 아닌 경우에만)
                if not ("EV/Sales" in user_question or "재무비율" in user_question) and chatbot is not None:
                    with st.spinner("🤖 GPT-4가 데이터를 분석하고 있습니다..."):
                        try:
                            question_type = chatbot.get_question_type(user_question)
                            answer = chatbot.analyze_data_and_answer(user_question, data, question_type)
                            
                            st.markdown("### 🤖 GPT-4 답변")
                            st.markdown(answer)
                        
                        except Exception as e:
                            st.error(f"❌ GPT-4 분석 중 오류가 발생했습니다: {e}")
                            st.info("다시 시도해보거나 다른 질문을 해보세요.")
            else:
                st.warning("질문을 입력해주세요.")
    
    with tab2:
        st.header("🔍 데이터 검색")
        
        # 검색 옵션
        search_option = st.selectbox(
            "검색 유형을 선택하세요:",
            ["기업명", "산업분류", "주요사업", "발행일자"]
        )
        
        if search_option == "기업명":
            search_term = st.text_input("기업명을 입력하세요:")
        elif search_option == "산업분류":
            search_term = st.text_input("산업분류를 입력하세요:")
        elif search_option == "주요사업":
            search_term = st.text_input("주요사업을 입력하세요:")
        else:  # 발행일자
            search_term = st.date_input("발행일자를 선택하세요:")
        
        if st.button("검색"):
            if search_term:
                # 검색 실행
                if search_option == "발행일자":
                    search_term = search_term.strftime("%Y-%m-%d")
                
                data = search_by_sector(str(search_term))
                
                if not data.empty:
                    st.success(f"✅ 검색 결과 {len(data)}건을 찾았습니다.")
                    
                    # 표시할 컬럼 선택 (존재하는 컬럼만)
                    display_columns = ['공시발행_기업명', '공시발행_기업_산업분류', '평가대상기업명', '평가대상_주요사업', '발행일자']
                    
                    # 추가 컬럼들이 존재하면 표시 컬럼에 추가
                    if '유사기업' in data.columns:
                        display_columns.append('유사기업')
                    if 'WACC' in data.columns:
                        display_columns.append('WACC')
                    if 'Link' in data.columns:
                        display_columns.append('Link')
                    
                    st.dataframe(data[display_columns], width='stretch', hide_index=True)
                else:
                    st.warning("검색 결과를 찾을 수 없습니다.")
            else:
                st.warning("검색어를 입력해주세요.")

if __name__ == "__main__":
    main()
