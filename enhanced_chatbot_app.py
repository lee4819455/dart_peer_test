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
from collections import Counter

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
            # Streamlit 컨텍스트가 있을 때만 경고 표시
            try:
                st.warning("키워드 사전 파일을 찾을 수 없습니다. 기본 검색 모드로 동작합니다.")
            except:
                # Streamlit 컨텍스트가 없으면 경고 없이 진행
                pass
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

def process_valuation_analysis(question):
    """밸류에이션 분석 질문들을 처리하는 함수"""
    try:
        question_lower = question.lower()
        
        # SQLite 데이터베이스에서 데이터 로드
        db_path = '외평보고서.db'
        if not os.path.exists(db_path):
            st.error(f"데이터베이스 파일을 찾을 수 없습니다: {db_path}")
            st.info("Excel 파일을 먼저 DB로 변환해주세요: python excel_to_db.py")
            return False
        
        import sqlite3
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query("SELECT * FROM 외평보고서", conn)
        conn.close()
        
        if df.empty:
            st.warning("데이터베이스에 데이터가 없습니다.")
            return False
        
        # DB에서 가져온 데이터는 이미 컬럼명이 정리되어 있음
        # 하지만 일부 컬럼명 수정이 필요할 수 있음
        column_mapping = {
            '평가대상 기업명': '평가대상기업명',  # 공백이 있는 컬럼명 수정
            '추정기간_현재가치_영업가치': '추정기간 현재가치 / 영업가치',
            'NOA_Enterprise_Value': 'NOA / Enterprise Value'
        }
        
        for old_col, new_col in column_mapping.items():
            if old_col in df.columns:
                df.rename(columns={old_col: new_col}, inplace=True)
        
        # 수치형 컬럼 변환
        numeric_columns = ['WACC', 'Ke', 'Kd', 'D/E', 'EV/Sales', 'PSR', 'PER', 'EV/EBITDA', 'PBR', 'NOA / Enterprise Value', '추정기간 현재가치 / 영업가치']
        for col in numeric_columns:
            if col in df.columns:
                # Handle both decimal format (0.178) and percentage format (17.78%)
                col_data = df[col].astype(str).str.replace(',', '').str.replace('\t', '')
                has_percent = col_data.str.contains('%', na=False)
                
                # Convert to numeric, removing % symbol
                numeric_data = pd.to_numeric(col_data.str.replace('%', ''), errors='coerce')
                
                # For values that had % symbol, divide by 100 to convert to decimal
                numeric_data[has_percent] = numeric_data[has_percent] / 100
                
                df[col] = numeric_data
        
        # g 컬럼 처리 (영구성장률)
        g_columns = ['g', '영구성장률', '영구성장', '영구성장율']
        for g_col in g_columns:
            if g_col in df.columns:
                df['g'] = pd.to_numeric(df[g_col].astype(str).str.replace(',', '').str.replace('%', ''), errors='coerce')
                break
        
        # 날짜 컬럼 변환
        if '발행일자' in df.columns:
            df['발행일자'] = pd.to_datetime(df['발행일자'], errors='coerce')
        
        # 1. 산업별 WACC 중앙값
        if "산업별" in question and "wacc" in question_lower and "중앙값" in question:
            if 'WACC' in df.columns and '공시발행_기업_산업분류' in df.columns:
                grp = df.groupby('공시발행_기업_산업분류')['WACC'].median().dropna().sort_values(ascending=False)
                if not grp.empty:
                    st.subheader('산업별 WACC 중앙값')
                    # Convert to percentage for display
                    grp_display = grp * 100
                    st.dataframe(grp_display.reset_index().rename(columns={'WACC': 'WACC 중앙값 (%)'}), hide_index=True, use_container_width=True)
                    
                    # 차트 생성
                    fig = px.bar(x=grp_display.values, y=grp_display.index, orientation='h', 
                                title='산업별 WACC 중앙값', labels={'x': 'WACC 중앙값 (%)', 'y': '산업분류'})
                    st.plotly_chart(fig, use_container_width=True)
                    return True
        
        # 2. 평가법인별 WACC 비교
        elif "평가법인" in question and "wacc" in question_lower and ("비교" in question or "중앙값" in question):
            if 'WACC' in df.columns and '평가법인' in df.columns:
                grp = df.groupby('평가법인')['WACC'].median().dropna().sort_values(ascending=False)
                if not grp.empty:
                    st.subheader('평가법인별 WACC 중앙값 비교')
                    # Convert to percentage for display
                    grp_display = grp * 100
                    st.dataframe(grp_display.reset_index().rename(columns={'WACC': 'WACC 중앙값 (%)'}), hide_index=True, use_container_width=True)
                    
                    # 차트 생성
                    fig = px.bar(x=grp_display.values, y=grp_display.index, orientation='h', 
                                title='평가법인별 WACC 중앙값', labels={'x': 'WACC 중앙값 (%)', 'y': '평가법인'})
                    st.plotly_chart(fig, use_container_width=True)
                    return True
        
        # 3. g ≥ WACC 위반 사례
        elif ("위반" in question or "g" in question_lower) and "wacc" in question_lower:
            if 'g' in df.columns and 'WACC' in df.columns:
                vio = df[(pd.to_numeric(df['g'], errors='coerce') >= pd.to_numeric(df['WACC'], errors='coerce'))]
                st.subheader('QC: g ≥ WACC 위반 사례')
                st.write(f'총 {len(vio)}건의 위반 사례가 발견되었습니다.')
                
                if not vio.empty:
                    display_cols = ['공시발행_기업명', '발행일자', 'g', 'WACC', '공시발행_기업_산업분류']
                    available_cols = [col for col in display_cols if col in vio.columns]
                    
                    if '발행일자' in vio.columns:
                        vio_sorted = vio.sort_values('발행일자', ascending=False)
                    else:
                        vio_sorted = vio
                    
                    st.dataframe(vio_sorted[available_cols], hide_index=True, use_container_width=True)
                    return True
        
        # 4. D/E 미기재 영향
        elif "미기재" in question and ("d/e" in question_lower or "부채비율" in question):
            if 'D/E' in df.columns and 'WACC' in df.columns:
                de = pd.to_numeric(df['D/E'], errors='coerce')
                w = pd.to_numeric(df['WACC'], errors='coerce')
                missing = w[de.isna()].dropna()
                present = w[de.notna()].dropna()
                
                st.subheader('QC: D/E 미기재가 WACC에 미치는 영향')
                
                pct_missing = (len(missing)/(len(missing)+len(present)))*100 if (len(missing)+len(present))>0 else 0
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric('D/E 미기재 비중', f'{pct_missing:.1f}%')
                with col2:
                    if len(missing) > 0:
                        st.metric('미기재 그룹 평균 WACC', f'{missing.mean() * 100:.2f}%')
                    else:
                        st.metric('미기재 그룹 평균 WACC', 'N/A')
                with col3:
                    if len(present) > 0:
                        st.metric('기재 그룹 평균 WACC', f'{present.mean() * 100:.2f}%')
                    else:
                        st.metric('기재 그룹 평균 WACC', 'N/A')
                
                if len(missing)>0 and len(present)>0:
                    st.metric('평균 WACC 차이(미기재-기재)', f'{(missing.mean()-present.mean()) * 100:.2f}%p')
                
                return True
        
        # 5. WACC Top 10 또는 상위 N개
        elif ("top" in question_lower or "상위" in question) and "wacc" in question_lower:
            if 'WACC' in df.columns:
                # 상위 N개 추출
                import re
                n = 10  # 기본값
                match = re.search(r'(?:top|상위)\s*(\d+)', question_lower)
                if match:
                    try:
                        n = int(match.group(1))
                    except:
                        n = 10
                
                display_cols = ['공시발행_기업명', '공시발행_기업_산업분류', '발행일자', 'WACC']
                available_cols = [col for col in display_cols if col in df.columns]
                
                topn = df[available_cols].dropna(subset=['WACC']).sort_values('WACC', ascending=False).head(n)
                
                st.subheader(f'랭킹: WACC Top {n}')
                # Convert WACC to percentage for display
                topn_display = topn.copy()
                topn_display['WACC'] = topn_display['WACC'] * 100
                topn_display = topn_display.rename(columns={'WACC': 'WACC (%)'})
                st.dataframe(topn_display, hide_index=True, use_container_width=True)
                
                # 차트 생성
                if not topn.empty:
                    fig = px.bar(x=topn['WACC'] * 100, y=topn['공시발행_기업명'], orientation='h',
                                title=f'WACC Top {n}', labels={'x': 'WACC (%)', 'y': '기업명'})
                    st.plotly_chart(fig, use_container_width=True)
                
                return True
        
        # 6. 최근 12개월 평가법인 TOP5
        elif "최근" in question and ("평가법인" in question or "회계법인" in question):
            if '평가법인' in df.columns and '발행일자' in df.columns:
                cutoff = df['발행일자'].max()
                if pd.notna(cutoff):
                    recent = df[df['발행일자'] >= (cutoff - pd.Timedelta(days=365))]
                    counts = recent.groupby('평가법인')['평가법인'].count().sort_values(ascending=False).head(5)
                    
                    st.subheader('랭킹: 최근 12개월 평가법인 TOP5')
                    st.dataframe(counts.reset_index(name='건수'), hide_index=True, use_container_width=True)
                    
                    # 차트 생성
                    fig = px.bar(x=counts.values, y=counts.index, orientation='h',
                                title='최근 12개월 평가법인 활동량 TOP5', labels={'x': '건수', 'y': '평가법인'})
                    st.plotly_chart(fig, use_container_width=True)
                    
                    return True
        
        # 7. 산업별 멀티플 중앙값
        elif "산업별" in question and "중앙값" in question and any(mult in question for mult in ['EV/EBITDA', 'EV/Sales', 'PSR', 'PER', 'PBR']):
            # 멀티플 종류 확인
            metric = None
            for mult in ['EV/EBITDA', 'EV/Sales', 'PSR', 'PER', 'PBR']:
                if mult in question:
                    metric = mult
                    break
            
            if not metric:
                metric = 'EV/EBITDA'  # 기본값
            
            if metric in df.columns and '공시발행_기업_산업분류' in df.columns:
                grp = df.groupby('공시발행_기업_산업분류')[metric].median().dropna().sort_values(ascending=False)
                if not grp.empty:
                    st.subheader(f'산업별 {metric} 중앙값')
                    st.dataframe(grp.reset_index().rename(columns={metric: f'{metric} 중앙값'}), hide_index=True, use_container_width=True)
                    
                    # 차트 생성
                    fig = px.bar(x=grp.values, y=grp.index, orientation='h',
                                title=f'산업별 {metric} 중앙값', labels={'x': f'{metric} 중앙값', 'y': '산업분류'})
                    st.plotly_chart(fig, use_container_width=True)
                    return True
        
        # 8. 영구현금흐름 비율 관련 (추정기간 현재가치 / 영업가치 컬럼 활용)
        elif "영구현금흐름" in question and "비율" in question:
            st.subheader('영구현금흐름 비율 분석')
            
            # 추정기간 현재가치 / 영업가치 컬럼이 있는지 확인
            if '추정기간 현재가치 / 영업가치' in df.columns:
                # 영구현금흐름 비율 계산: 1 - (추정기간 현재가치 / 영업가치)
                cash_flow_data = df[['평가대상기업명', '평가대상기업_산업분류', '발행일자', '추정기간 현재가치 / 영업가치']].dropna(subset=['추정기간 현재가치 / 영업가치'])
                
                if not cash_flow_data.empty:
                    # 이상값 필터링 (0과 1 사이의 값만 유효)
                    valid_data = cash_flow_data[
                        (cash_flow_data['추정기간 현재가치 / 영업가치'] >= 0) & 
                        (cash_flow_data['추정기간 현재가치 / 영업가치'] <= 1)
                    ].copy()
                    
                    if valid_data.empty:
                        st.warning("유효한 추정기간 현재가치 / 영업가치 데이터를 찾을 수 없습니다.")
                        return True
                    
                    # 영구현금흐름 비율 계산
                    valid_data['영구현금흐름_비율'] = 1 - valid_data['추정기간 현재가치 / 영업가치']
                    
                    # 50% 이상인 기업들 필터링
                    high_ratio_companies = valid_data[valid_data['영구현금흐름_비율'] >= 0.5]
                    
                    st.markdown("### 📊 영구현금흐름 비율이 50% 이상인 기업들")
                    
                    if not high_ratio_companies.empty:
                        # 상위 10개 기업 표시
                        top_companies = high_ratio_companies.sort_values('영구현금흐름_비율', ascending=False).head(10)
                        
                        # 데이터 표시
                        display_data = top_companies[['평가대상기업명', '평가대상기업_산업분류', '발행일자', '영구현금흐름_비율', '추정기간 현재가치 / 영업가치']].copy()
                        display_data['영구현금흐름_비율'] = display_data['영구현금흐름_비율'].apply(lambda x: f"{x:.1%}")
                        display_data['추정기간 현재가치 / 영업가치'] = display_data['추정기간 현재가치 / 영업가치'].apply(lambda x: f"{x:.1%}")
                        
                        st.dataframe(display_data, hide_index=True, use_container_width=True)
                        
                        # 차트 생성
                        fig = px.bar(x=top_companies['영구현금흐름_비율'], y=top_companies['평가대상기업명'], 
                                   orientation='h', title='영구현금흐름 비율 TOP10 (50% 이상)',
                                   labels={'x': '영구현금흐름 비율', 'y': '평가대상기업명'})
                        st.plotly_chart(fig, use_container_width=True)
                        
                        # 통계 정보
                        st.markdown("### 📈 통계 정보")
                        col1, col2, col3, col4 = st.columns(4)
                        
                        with col1:
                            st.metric("50% 이상 기업 수", len(high_ratio_companies))
                        with col2:
                            st.metric("전체 기업 수", len(valid_data))
                        with col3:
                            st.metric("50% 이상 비율", f"{len(high_ratio_companies)/len(valid_data)*100:.1f}%")
                        with col4:
                            st.metric("평균 영구현금흐름 비율", f"{valid_data['영구현금흐름_비율'].mean():.1%}")
                        
                        # 업종별 분석
                        if '평가대상기업_산업분류' in high_ratio_companies.columns:
                            st.markdown("### 🏭 업종별 영구현금흐름 비율 분석")
                            
                            # 업종별 50% 이상 기업 수
                            sector_high_ratio = high_ratio_companies.groupby('평가대상기업_산업분류').size().reset_index(name='50%_이상_기업수')
                            sector_total = valid_data.groupby('평가대상기업_산업분류').size().reset_index(name='전체_기업수')
                            
                            sector_analysis = sector_total.merge(sector_high_ratio, on='평가대상기업_산업분류', how='left')
                            sector_analysis['50%_이상_기업수'] = sector_analysis['50%_이상_기업수'].fillna(0)
                            sector_analysis['비율'] = sector_analysis['50%_이상_기업수'] / sector_analysis['전체_기업수'] * 100
                            sector_analysis = sector_analysis.sort_values('비율', ascending=False)
                            
                            st.dataframe(sector_analysis, hide_index=True, use_container_width=True)
                            
                            # 업종별 차트
                            fig = px.bar(x=sector_analysis['비율'], y=sector_analysis['평가대상기업_산업분류'], 
                                       orientation='h', title='업종별 영구현금흐름 비율 50% 이상 기업 비율',
                                       labels={'x': '50% 이상 기업 비율 (%)', 'y': '업종'})
                            st.plotly_chart(fig, use_container_width=True)
                        
                        # 분포 분석
                        st.markdown("### 📊 영구현금흐름 비율 분포")
                        fig = px.histogram(valid_data, x='영구현금흐름_비율', nbins=20, 
                                         title='영구현금흐름 비율 분포')
                        # 50% 기준선 추가
                        fig.add_vline(x=0.5, line_dash="dash", line_color="red", 
                                    annotation_text="50% 기준선", annotation_position="top")
                        st.plotly_chart(fig, use_container_width=True)
                        
                        # 해석 정보
                        st.markdown("### 💡 분석 해석")
                        st.info("""
                        **영구현금흐름 비율 해석:**
                        - **높은 비율 (50% 이상)**: 영구현금흐름이 전체 기업가치에서 차지하는 비중이 높은 기업
                        - **중간 비율 (30-50%)**: 적정 수준의 영구현금흐름 비중
                        - **낮은 비율 (30% 미만)**: 영구현금흐름 비중이 상대적으로 낮은 기업
                        
                        **영구현금흐름 비율이 높은 기업의 특징:**
                        - 장기적인 성장 전망이 좋은 기업
                        - 안정적인 현금흐름을 창출하는 기업
                        - 성숙한 사업 모델을 가진 기업
                        """)
                        
                        return True
                    else:
                        st.warning("영구현금흐름 비율이 50% 이상인 기업을 찾을 수 없습니다.")
                        st.info(f"현재 데이터에서 가장 높은 영구현금흐름 비율: {valid_data['영구현금흐름_비율'].max():.1%}")
                        return True
                else:
                    st.warning("추정기간 현재가치 / 영업가치 데이터가 있는 기업을 찾을 수 없습니다.")
                    return True
            else:
                st.subheader('영구현금흐름 비율 분석')
                st.info("현재 데이터베이스에는 '추정기간 현재가치 / 영업가치' 컬럼이 포함되어 있지 않습니다.")
                st.info("이 분석을 위해서는 추가적인 현금흐름 데이터가 필요합니다:")
                st.markdown("""
                - 추정기간 현재가치 / 영업가치 비율
                - 영구현금흐름 비율 계산을 위한 데이터
                """)
                return True
        
        # 9. 비영업용자산구성 관련 질문 (구체적인 키워드 우선)
        elif "비영업용자산구성" in question or ("비영업자산" in question and "구성" in question):
            st.info(f"🔍 비영업용자산구성 질문으로 인식: '{question}'")
            # 비영업용자산구성 컬럼이 있는지 확인
            if '비영업용자산구성' in df.columns:
                st.subheader('비영업용자산구성 분석')
                
                # 비영업용자산구성 데이터 정리
                non_operating_assets = df['비영업용자산구성'].dropna()
                
                if not non_operating_assets.empty:
                    # 업종별 비영업용자산구성 빈도 분석
                    if '평가대상기업_산업분류' in df.columns:
                        # 업종별로 그룹화하여 비영업용자산구성 빈도 계산
                        sector_assets = df[['평가대상기업_산업분류', '비영업용자산구성']].dropna()
                        
                        if not sector_assets.empty:
                            # 각 업종별로 비영업용자산구성 항목들을 분리하고 빈도 계산
                            asset_frequency = {}
                            
                            for sector in sector_assets['평가대상기업_산업분류'].unique():
                                sector_data = sector_assets[sector_assets['평가대상기업_산업분류'] == sector]
                                assets_list = []
                                
                                for assets in sector_data['비영업용자산구성']:
                                    if pd.notna(assets) and str(assets).strip() != '':
                                        # 쉼표로 구분된 자산 항목들을 분리
                                        items = [item.strip() for item in str(assets).split(',')]
                                        assets_list.extend(items)
                                
                                # 빈도 계산
                                asset_counter = Counter(assets_list)
                                asset_frequency[sector] = asset_counter
                            
                            # 전체 업종에서 가장 빈번한 비영업용자산구성 TOP5
                            st.markdown("### 📊 전체 업종 비영업용자산구성 TOP5")
                            
                            all_assets = []
                            for sector, counter in asset_frequency.items():
                                all_assets.extend(list(counter.elements()))
                            
                            if all_assets:
                                overall_counter = Counter(all_assets)
                                top5_overall = overall_counter.most_common(5)
                                
                                # 데이터프레임으로 표시
                                top5_df = pd.DataFrame(top5_overall, columns=['비영업용자산구성', '빈도'])
                                st.dataframe(top5_df, hide_index=True, use_container_width=True)
                                
                                # 차트 생성
                                fig = px.bar(x=top5_df['빈도'], y=top5_df['비영업용자산구성'], 
                                           orientation='h', title='전체 업종 비영업용자산구성 TOP5',
                                           labels={'x': '빈도', 'y': '비영업용자산구성'})
                                st.plotly_chart(fig, use_container_width=True)
                            
                            # 업종별 상세 분석
                            st.markdown("### 📈 업종별 비영업용자산구성 상세 분석")
                            
                            # 업종 선택
                            sectors = list(asset_frequency.keys())
                            selected_sector = st.selectbox("분석할 업종을 선택하세요:", sectors)
                            
                            if selected_sector and selected_sector in asset_frequency:
                                sector_counter = asset_frequency[selected_sector]
                                top5_sector = sector_counter.most_common(5)
                                
                                if top5_sector:
                                    st.markdown(f"#### {selected_sector} 업종 비영업용자산구성 TOP5")
                                    
                                    # 데이터프레임으로 표시
                                    sector_df = pd.DataFrame(top5_sector, columns=['비영업용자산구성', '빈도'])
                                    st.dataframe(sector_df, hide_index=True, use_container_width=True)
                                    
                                    # 차트 생성
                                    fig = px.bar(x=sector_df['빈도'], y=sector_df['비영업용자산구성'], 
                                               orientation='h', title=f'{selected_sector} 업종 비영업용자산구성 TOP5',
                                               labels={'x': '빈도', 'y': '비영업용자산구성'})
                                    st.plotly_chart(fig, use_container_width=True)
                                    
                                    # 통계 정보
                                    col1, col2, col3 = st.columns(3)
                                    with col1:
                                        st.metric("총 자산 유형 수", len(sector_counter))
                                    with col2:
                                        st.metric("총 기업 수", sum(sector_counter.values()))
                                    with col3:
                                        st.metric("평균 자산 유형 수", f"{sum(sector_counter.values())/len(sector_counter):.1f}")
                                
                                else:
                                    st.warning(f"{selected_sector} 업종의 비영업용자산구성 데이터가 없습니다.")
                            
                            # 전체 통계
                            st.markdown("### 📊 전체 통계")
                            col1, col2, col3, col4 = st.columns(4)
                            
                            with col1:
                                st.metric("분석 업종 수", len(asset_frequency))
                            with col2:
                                st.metric("총 기업 수", len(sector_assets))
                            with col3:
                                st.metric("데이터 있는 기업 수", len(non_operating_assets))
                            with col4:
                                data_coverage = len(non_operating_assets) / len(df) * 100 if len(df) > 0 else 0
                                st.metric("데이터 커버리지", f"{data_coverage:.1f}%")
                            
                            return True
                        else:
                            st.warning("업종별 비영업용자산구성 데이터를 찾을 수 없습니다.")
                            return True
                    else:
                        st.warning("산업분류 컬럼을 찾을 수 없습니다.")
                        return True
                else:
                    st.warning("비영업용자산구성 데이터가 없습니다.")
                    return True
            else:
                st.subheader('비영업자산 분석')
                st.info("현재 데이터베이스에는 비영업자산 상세 데이터가 포함되어 있지 않습니다.")
                st.info("이 분석을 위해서는 추가적인 재무 데이터가 필요합니다:")
                st.markdown("""
                - 기업가치 (Enterprise Value)
                - 비영업자산 총액
                - 비영업자산 구성 내역 (현금성자산, 투자증권, 부동산 등)
                - 비영업자산 비중 (기업가치 대비)
                """)
                return True
        
        # 10. 공시발행기업 투자 맵핑 분석
        elif "투자" in question and ("맵핑" in question or "매핑" in question or "투자맵" in question):
            st.subheader('공시발행기업 투자 맵핑 분석')
            
            # 투자 관련 거래만 필터링 (주식양수, 출자 등)
            if '공시발행_기업명' in df.columns and '평가대상기업명' in df.columns and '보고서목적' in df.columns:
                # 투자 관련 보고서목적 필터링
                investment_purposes = [
                    '타법인주식및출자양수결정',
                    '유상증자결정',
                    '유상증자',
                    '지분증권'
                ]
                
                investment_data = df[df['보고서목적'].isin(investment_purposes)].copy()
                
                if not investment_data.empty:
                    # 공시발행기업별 투자 현황
                    st.markdown("### 📈 공시발행기업별 투자 현황")
                    
                    # 투자 건수별 TOP 공시발행기업
                    investment_counts = investment_data.groupby('공시발행_기업명').agg({
                        '평가대상기업명': 'count',
                        '공시발행_기업_산업분류': 'first'
                    }).rename(columns={'평가대상기업명': '투자건수'}).reset_index()
                    
                    investment_counts = investment_counts.sort_values('투자건수', ascending=False).head(20)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**투자 활발한 기업 TOP20**")
                        display_investment = investment_counts[['공시발행_기업명', '공시발행_기업_산업분류', '투자건수']].copy()
                        st.dataframe(display_investment, hide_index=True, use_container_width=True)
                    
                    with col2:
                        # 투자 건수 차트
                        fig = px.bar(investment_counts.head(10), x='투자건수', y='공시발행_기업명', 
                                   orientation='h', title='투자 활발한 기업 TOP10')
                        fig.update_layout(yaxis={'categoryorder':'total ascending'})
                        st.plotly_chart(fig, use_container_width=True)
                    
                    # 투자 맵핑 네트워크 분석
                    st.markdown("### 🔗 투자 맵핑 네트워크")
                    
                    # 특정 공시발행기업 선택
                    top_investors = investment_counts.head(10)['공시발행_기업명'].tolist()
                    selected_investor = st.selectbox("공시발행기업을 선택하세요:", top_investors)
                    
                    if selected_investor:
                        investor_data = investment_data[investment_data['공시발행_기업명'] == selected_investor]
                        
                        if not investor_data.empty:
                            st.markdown(f"**{selected_investor}의 투자 포트폴리오**")
                            
                            # 투자 대상 분석
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                st.markdown("**투자 대상 기업 목록**")
                                portfolio = investor_data[['평가대상기업명', '평가대상기업_산업분류', '보고서목적', '발행일자']].copy()
                                portfolio = portfolio.sort_values('발행일자', ascending=False)
                                st.dataframe(portfolio, hide_index=True, use_container_width=True)
                            
                            with col2:
                                st.markdown("**투자 대상 업종 분포**")
                                sector_distribution = investor_data['평가대상기업_산업분류'].value_counts()
                                fig = px.pie(values=sector_distribution.values, 
                                           names=sector_distribution.index,
                                           title=f'{selected_investor}의 투자 업종 분포')
                                st.plotly_chart(fig, use_container_width=True)
                            
                            # 투자 통계
                            st.markdown(f"**{selected_investor}의 투자 통계**")
                            col_stat1, col_stat2, col_stat3 = st.columns(3)
                            
                            with col_stat1:
                                st.metric("총 투자 건수", len(investor_data))
                            with col_stat2:
                                st.metric("투자 대상 기업 수", investor_data['평가대상기업명'].nunique())
                            with col_stat3:
                                st.metric("투자 업종 수", investor_data['평가대상기업_산업분류'].nunique())
                    
                    # 해석 가이드
                    st.markdown("### 💡 투자 맵핑 분석 해석 가이드")
                    st.info("""
                    **투자 맵핑 분석 활용법:**
                    
                    1. **투자 활발도**: 어떤 기업이 적극적으로 투자하는지 확인
                    2. **포트폴리오 분석**: 선택된 기업의 투자 대상과 업종 다양성
                    3. **투자 패턴**: 기업별 투자 전략과 선호 업종 파악
                    
                    **주요 투자 유형:**
                    - **타법인주식및출자양수**: 다른 회사 지분 취득
                    - **유상증자**: 신주 발행을 통한 자금 조달
                    """)
                    
                else:
                    st.warning("투자 관련 데이터를 찾을 수 없습니다.")
            else:
                st.error("필요한 컬럼이 데이터에 없습니다.")
            
            return True

        # 11. 업종 간 거래 관계 분석 (보고서목적 기반)
        elif "업종" in question and ("양수" in question or "양도" in question or "거래" in question):
            st.subheader('업종 간 거래 관계 분석')
            
            # 공시발행 기업 업종과 평가대상기업 업종 간의 거래 관계 분석
            if '공시발행_기업_산업분류' in df.columns and '평가대상기업_산업분류' in df.columns and '보고서목적' in df.columns:
                # 업종 간 거래 데이터 정리 (보고서목적 포함)
                transaction_data = df[['공시발행_기업명', '공시발행_기업_산업분류', '평가대상기업명', '평가대상기업_산업분류', '보고서목적', '발행일자']].dropna()
                
                if not transaction_data.empty:
                    # 거래 목적별 분석
                    st.markdown("### 🎯 거래 목적별 분석")
                    
                    # 거래 목적별 건수
                    purpose_counts = transaction_data['보고서목적'].value_counts()
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**거래 목적별 건수 TOP10**")
                        purpose_df = purpose_counts.head(10).reset_index()
                        purpose_df.columns = ['거래목적', '건수']
                        st.dataframe(purpose_df, hide_index=True, use_container_width=True)
                    
                    with col2:
                        # 거래 목적별 파이 차트
                        fig = px.pie(values=purpose_counts.head(8).values, 
                                   names=purpose_counts.head(8).index,
                                   title='주요 거래 목적 분포')
                        st.plotly_chart(fig, use_container_width=True)
                    
                    # 업종 간 거래 매트릭스 생성
                    st.markdown("### 📊 업종 간 거래 관계 매트릭스")
                    
                    # 공시발행 업종 → 평가대상 업종 거래 빈도 계산
                    sector_transactions = transaction_data.groupby(['공시발행_기업_산업분류', '평가대상기업_산업분류']).size().reset_index(name='거래건수')
                    
                    # 피벗 테이블 생성
                    pivot_table = sector_transactions.pivot(index='공시발행_기업_산업분류', 
                                                          columns='평가대상기업_산업분류', 
                                                          values='거래건수').fillna(0)
                    
                    # 거래건수가 많은 순으로 정렬
                    pivot_table = pivot_table.sort_index()
                    pivot_table = pivot_table.sort_index(axis=1)
                    
                    st.dataframe(pivot_table.astype(int), use_container_width=True)
                    
                    # 히트맵 차트 생성
                    fig = go.Figure(data=go.Heatmap(
                        z=pivot_table.values,
                        x=pivot_table.columns,
                        y=pivot_table.index,
                        colorscale='Blues',
                        text=pivot_table.values,
                        texttemplate="%{text}",
                        textfont={"size": 10},
                        hoverongaps=False
                    ))
                    
                    fig.update_layout(
                        title='업종 간 거래 관계 히트맵',
                        xaxis_title='평가대상기업 업종',
                        yaxis_title='공시발행 기업 업종',
                        width=800,
                        height=600
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # 상위 거래 관계 분석
                    st.markdown("### 🔝 주요 업종 간 거래 관계 TOP10")
                    
                    # 거래건수 기준 상위 10개
                    top_transactions = sector_transactions.sort_values('거래건수', ascending=False).head(10)
                    
                    # 거래 관계 설명 추가
                    top_transactions['거래관계'] = top_transactions['공시발행_기업_산업분류'] + ' → ' + top_transactions['평가대상기업_산업분류']
                    
                    display_data = top_transactions[['거래관계', '거래건수']].copy()
                    st.dataframe(display_data, hide_index=True, use_container_width=True)
                    
                    # 차트 생성
                    fig = px.bar(top_transactions, x='거래건수', y='거래관계', 
                               orientation='h', title='주요 업종 간 거래 관계 TOP10',
                               labels={'거래건수': '거래 건수', '거래관계': '업종 간 거래 관계'})
                    fig.update_layout(yaxis={'categoryorder':'total ascending'})
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # 통계 정보
                    st.markdown("### 📈 거래 관계 통계")
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric("총 거래 건수", len(transaction_data))
                    with col2:
                        st.metric("공시발행 업종 수", len(transaction_data['공시발행_기업_산업분류'].unique()))
                    with col3:
                        st.metric("평가대상 업종 수", len(transaction_data['평가대상기업_산업분류'].unique()))
                    with col4:
                        st.metric("업종 간 거래 쌍", len(sector_transactions))
                    
                    # 거래 목적별 업종 분석
                    st.markdown("### 📈 거래 목적별 업종 분석")
                    
                    # 주요 거래 목적 선택
                    major_purposes = purpose_counts.head(5).index.tolist()
                    selected_purpose = st.selectbox("거래 목적을 선택하세요:", major_purposes)
                    
                    if selected_purpose:
                        purpose_data = transaction_data[transaction_data['보고서목적'] == selected_purpose]
                        
                        if not purpose_data.empty:
                            st.markdown(f"**{selected_purpose} 거래의 업종별 분석**")
                            
                            # 업종별 거래 현황
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                st.markdown("**공시발행 업종별 현황**")
                                issuing_counts = purpose_data['공시발행_기업_산업분류'].value_counts().head(10)
                                issuing_df = issuing_counts.reset_index()
                                issuing_df.columns = ['업종', '건수']
                                st.dataframe(issuing_df, hide_index=True, use_container_width=True)
                            
                            with col2:
                                st.markdown("**평가대상 업종별 현황**")
                                target_counts = purpose_data['평가대상기업_산업분류'].value_counts().head(10)
                                target_df = target_counts.reset_index()
                                target_df.columns = ['업종', '건수']
                                st.dataframe(target_df, hide_index=True, use_container_width=True)
                            
                            # 업종 간 조합 분석
                            st.markdown(f"**{selected_purpose} 거래의 업종 간 조합 TOP10**")
                            purpose_combinations = purpose_data.groupby(['공시발행_기업_산업분류', '평가대상기업_산업분류']).size().reset_index(name='거래건수')
                            purpose_combinations['거래조합'] = purpose_combinations['공시발행_기업_산업분류'] + ' → ' + purpose_combinations['평가대상기업_산업분류']
                            purpose_combinations = purpose_combinations.sort_values('거래건수', ascending=False).head(10)
                            
                            combo_display = purpose_combinations[['거래조합', '거래건수']].copy()
                            st.dataframe(combo_display, hide_index=True, use_container_width=True)
                            
                            # 차트 생성
                            if len(purpose_combinations) > 0:
                                fig = px.bar(purpose_combinations, x='거래건수', y='거래조합', 
                                           orientation='h', title=f'{selected_purpose} 거래의 업종 간 조합 TOP10')
                                fig.update_layout(yaxis={'categoryorder':'total ascending'})
                                st.plotly_chart(fig, use_container_width=True)
                    
                    # 특정 업종 분석
                    st.markdown("### 🎯 특정 업종 거래 분석")
                    
                    # 공시발행 업종 선택
                    issuing_sectors = sorted(transaction_data['공시발행_기업_산업분류'].unique())
                    selected_issuing_sector = st.selectbox("공시발행 업종을 선택하세요:", issuing_sectors)
                    
                    if selected_issuing_sector:
                        # 선택된 공시발행 업종의 거래 현황
                        selected_data = transaction_data[transaction_data['공시발행_기업_산업분류'] == selected_issuing_sector]
                        
                        st.markdown(f"**{selected_issuing_sector} 업종의 거래 현황:**")
                        
                        # 평가대상 업종별 거래 건수
                        target_sector_counts = selected_data.groupby('평가대상기업_산업분류').size().reset_index(name='거래건수')
                        target_sector_counts = target_sector_counts.sort_values('거래건수', ascending=False)
                        
                        st.dataframe(target_sector_counts, hide_index=True, use_container_width=True)
                        
                        # 차트 생성
                        if len(target_sector_counts) > 0:
                            fig = px.pie(target_sector_counts, values='거래건수', names='평가대상기업_산업분류', 
                                       title=f'{selected_issuing_sector} 업종의 평가대상 업종별 거래 비중')
                            st.plotly_chart(fig, use_container_width=True)
                        
                        # 거래 목적별 분석
                        st.markdown(f"**{selected_issuing_sector} 업종의 거래 목적별 현황:**")
                        purpose_in_sector = selected_data['보고서목적'].value_counts()
                        purpose_sector_df = purpose_in_sector.reset_index()
                        purpose_sector_df.columns = ['거래목적', '건수']
                        st.dataframe(purpose_sector_df, hide_index=True, use_container_width=True)
                        
                        # 구체적인 거래 내역
                        st.markdown(f"**{selected_issuing_sector} 업종의 구체적인 거래 내역:**")
                        display_transactions = selected_data[['공시발행_기업명', '평가대상기업명', '평가대상기업_산업분류', '보고서목적', '발행일자']].copy()
                        display_transactions = display_transactions.sort_values('발행일자', ascending=False)
                        st.dataframe(display_transactions, hide_index=True, use_container_width=True)
                    
                    # 해석 가이드
                    st.markdown("### 💡 분석 해석 가이드")
                    st.info("""
                    **업종 간 거래 관계 분석 해석:**
                    
                    1. **거래 목적별 분석**: 양수, 양도, 합병 등 거래 유형별 트렌드 파악
                    2. **업종별 거래 패턴**: 특정 업종이 주로 어떤 거래에 참여하는지 확인
                    3. **업종 간 관계**: 어떤 업종 조합에서 거래가 활발한지 분석
                    4. **시장 동향**: 거래 목적과 업종 조합으로 M&A 시장 트렌드 파악
                    
                    **주요 거래 유형:**
                    - **타법인주식및출자양수결정**: 다른 회사의 주식이나 지분을 사들이는 거래
                    - **회사합병결정**: 두 회사가 하나로 합치는 거래
                    - **타법인주식및출자양도결정**: 보유하고 있던 주식이나 지분을 파는 거래
                    - **영업양수/양도결정**: 사업 부문을 사고파는 거래
                    
                    **활용 방안:**
                    - M&A 시장 분석 및 예측
                    - 업종별 투자 전략 수립
                    - 거래 트렌드 파악
                    - 리스크 관리 및 기회 발견
                    """)
                    
                else:
                    st.warning("업종 간 거래 데이터를 찾을 수 없습니다.")
            else:
                st.error("필요한 컬럼(공시발행_기업_산업분류, 평가대상기업_산업분류)이 데이터에 없습니다.")

        elif "기업가치" in question and "비영업자산" in question and "많은" in question:
            st.subheader('기업가치 대비 비영업자산 분석 (NOA/Enterprise Value)')
            
            # NOA / Enterprise Value 컬럼이 있는지 확인
            if 'NOA / Enterprise Value' in df.columns:
                # NOA / Enterprise Value 데이터 정리
                noa_data = df[['평가대상기업명', '평가대상기업_산업분류', '발행일자', 'NOA / Enterprise Value']].dropna(subset=['NOA / Enterprise Value'])
                
                if not noa_data.empty:
                    # NOA / Enterprise Value 값이 높은 상위 기업들 (비영업자산 비중이 높은 기업들)
                    st.markdown("### 📊 기업가치 대비 비영업자산 비중이 높은 기업 TOP10")
                    
                    # 상위 10개 기업 선택
                    top_noa = noa_data.sort_values('NOA / Enterprise Value', ascending=False).head(10)
                    
                    # 데이터 표시
                    st.dataframe(top_noa, hide_index=True, use_container_width=True)
                    
                    # 차트 생성
                    fig = px.bar(x=top_noa['NOA / Enterprise Value'], y=top_noa['평가대상기업명'], 
                               orientation='h', title='기업가치 대비 비영업자산 비중 TOP10',
                               labels={'x': 'NOA / Enterprise Value 비율', 'y': '평가대상기업명'})
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # 통계 정보
                    st.markdown("### 📈 통계 정보")
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric("평균 NOA/EV 비율", f"{noa_data['NOA / Enterprise Value'].mean():.3f}")
                    with col2:
                        st.metric("중앙값 NOA/EV 비율", f"{noa_data['NOA / Enterprise Value'].median():.3f}")
                    with col3:
                        st.metric("최대값", f"{noa_data['NOA / Enterprise Value'].max():.3f}")
                    with col4:
                        st.metric("데이터 있는 기업 수", len(noa_data))
                    
                    # 업종별 분석
                    if '평가대상기업_산업분류' in noa_data.columns:
                        st.markdown("### 🏭 업종별 NOA/Enterprise Value 분석")
                        
                        # 업종별 평균 계산
                        sector_avg = noa_data.groupby('평가대상기업_산업분류')['NOA / Enterprise Value'].agg(['mean', 'count']).reset_index()
                        sector_avg = sector_avg[sector_avg['count'] >= 2]  # 2개 이상 데이터가 있는 업종만
                        sector_avg = sector_avg.sort_values('mean', ascending=False)
                        
                        if not sector_avg.empty:
                            st.dataframe(sector_avg.rename(columns={'mean': '평균 NOA/EV 비율', 'count': '기업 수'}), 
                                       hide_index=True, use_container_width=True)
                            
                            # 업종별 차트
                            fig = px.bar(x=sector_avg['mean'], y=sector_avg['평가대상기업_산업분류'], 
                                       orientation='h', title='업종별 평균 NOA/Enterprise Value 비율',
                                       labels={'x': '평균 NOA/EV 비율', 'y': '업종'})
                            st.plotly_chart(fig, use_container_width=True)
                    
                    # 분포 분석
                    st.markdown("### 📊 NOA/Enterprise Value 분포")
                    fig = px.histogram(noa_data, x='NOA / Enterprise Value', nbins=20, 
                                     title='NOA/Enterprise Value 분포')
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # 해석 정보
                    st.markdown("### 💡 분석 해석")
                    st.info("""
                    **NOA/Enterprise Value 비율 해석:**
                    - **높은 비율 (0.5 이상)**: 기업가치 대비 비영업자산이 많은 기업
                    - **중간 비율 (0.2-0.5)**: 적정 수준의 비영업자산 보유
                    - **낮은 비율 (0.2 미만)**: 비영업자산이 상대적으로 적은 기업
                    
                    **비영업자산이 많은 기업의 특징:**
                    - 현금성자산, 투자증권, 부동산 등 비영업용 자산을 많이 보유
                    - 영업활동과 직접적인 관련이 없는 자산의 비중이 높음
                    """)
                    
                    return True
                else:
                    st.warning("NOA / Enterprise Value 데이터가 있는 기업을 찾을 수 없습니다.")
                    return True
            else:
                st.subheader('기업가치 대비 비영업자산 분석')
                st.info("현재 데이터베이스에는 NOA / Enterprise Value 컬럼이 포함되어 있지 않습니다.")
                st.info("이 분석을 위해서는 추가적인 재무 데이터가 필요합니다:")
                st.markdown("""
                - 기업가치 (Enterprise Value)
                - 비영업자산 총액 (NOA)
                - NOA / Enterprise Value 비율
                """)
                st.info("💡 대신 '업종별 비영업용자산구성내역' 분석을 통해 비영업자산의 구성 요소를 확인할 수 있습니다.")
                return True
        
        # 11. 특정 연도 + 산업 평균 WACC
        elif any(year in question for year in ['2023', '2022', '2024', '2025']) and "wacc" in question_lower and "평균" in question:
            # 연도 추출
            import re
            year_match = re.search(r'(202[0-9])', question)
            if year_match:
                year = int(year_match.group(1))
                start_date = pd.Timestamp(f'{year}-01-01')
                end_date = pd.Timestamp(f'{year}-12-31')
                
                # 산업 키워드 추출
                sector_keywords = ['헬스케어', '제조', '제조업', '금융', '금융업', 'IT', '바이오', '게임', '소프트웨어', '소비재']
                sector = None
                for keyword in sector_keywords:
                    if keyword in question:
                        sector = keyword
                        break
                
                # 날짜 필터링
                if '발행일자' in df.columns:
                    df_filtered = df[(df['발행일자'] >= start_date) & (df['발행일자'] <= end_date)]
                else:
                    df_filtered = df
                
                # 산업 필터링
                if sector and '공시발행_기업_산업분류' in df_filtered.columns:
                    df_filtered = df_filtered[df_filtered['공시발행_기업_산업분류'].str.contains(sector, na=False)]
                
                if 'WACC' in df_filtered.columns:
                    wacc_values = pd.to_numeric(df_filtered['WACC'], errors='coerce').dropna()
                    
                    if len(wacc_values) > 0:
                        st.subheader(f'{year}년 {sector if sector else "전체"} 업종 WACC 분석')
                        
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric('평균 WACC', f'{wacc_values.mean() * 100:.2f}%')
                        with col2:
                            st.metric('중앙값 WACC', f'{wacc_values.median() * 100:.2f}%')
                        with col3:
                            st.metric('표준편차', f'{wacc_values.std() * 100:.2f}%')
                        with col4:
                            st.metric('표본수', len(wacc_values))
                        
                        # 분포 차트
                        fig = px.histogram(x=wacc_values * 100, nbins=20, title=f'{year}년 {sector if sector else "전체"} 업종 WACC 분포')
                        fig.update_layout(xaxis_title='WACC (%)')
                        st.plotly_chart(fig, use_container_width=True)
                        
                        return True
                    else:
                        st.warning(f"{year}년 {sector if sector else '전체'} 업종의 WACC 데이터를 찾을 수 없습니다.")
                        return True
        
        # 12. 연도별 주요통계
        elif any(year in question for year in ['2022', '2023', '2024', '2025']) and ("주요통계" in question or "통계" in question and "연도별" in question):
            import re
            year_match = re.search(r'(202[0-9])', question)
            if year_match:
                year = int(year_match.group(1))
                start_date = pd.Timestamp(f'{year}-01-01')
                end_date = pd.Timestamp(f'{year}-12-31')
                
                # 날짜 필터링
                if '발행일자' in df.columns:
                    df['발행일자'] = pd.to_datetime(df['발행일자'], errors='coerce')
                    df_filtered = df[(df['발행일자'] >= start_date) & (df['발행일자'] <= end_date)]
                else:
                    df_filtered = df
                
                if len(df_filtered) == 0:
                    st.warning(f"{year}년 데이터를 찾을 수 없습니다.")
                    return True
                
                st.subheader(f'{year}년 주요 통계')
                
                # 1. 기본 통계
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric('총 발행 건수', f'{len(df_filtered):,}건')
                with col2:
                    if '공시발행_기업명' in df_filtered.columns:
                        unique_companies = df_filtered['공시발행_기업명'].nunique()
                        st.metric('공시발행 기업 수', f'{unique_companies:,}개')
                with col3:
                    if '평가대상기업명' in df_filtered.columns:
                        unique_targets = df_filtered['평가대상기업명'].nunique()
                        st.metric('평가대상 기업 수', f'{unique_targets:,}개')
                with col4:
                    if '평가법인' in df_filtered.columns:
                        unique_firms = df_filtered['평가법인'].nunique()
                        st.metric('평가법인 수', f'{unique_firms:,}개')
                
                st.markdown("---")
                
                # 2. WACC 통계
                if 'WACC' in df_filtered.columns:
                    wacc_values = pd.to_numeric(df_filtered['WACC'], errors='coerce').dropna()
                    if len(wacc_values) > 0:
                        st.markdown("### 📊 WACC 통계")
                        col1, col2, col3, col4, col5 = st.columns(5)
                        with col1:
                            st.metric('평균', f'{wacc_values.mean() * 100:.2f}%')
                        with col2:
                            st.metric('중앙값', f'{wacc_values.median() * 100:.2f}%')
                        with col3:
                            st.metric('최소값', f'{wacc_values.min() * 100:.2f}%')
                        with col4:
                            st.metric('최대값', f'{wacc_values.max() * 100:.2f}%')
                        with col5:
                            st.metric('표준편차', f'{wacc_values.std() * 100:.2f}%')
                
                st.markdown("---")
                
                # 3. 업종별 분포
                if '공시발행_기업_산업분류' in df_filtered.columns:
                    st.markdown("### 🏭 업종별 분포 (TOP 10)")
                    sector_counts = df_filtered['공시발행_기업_산업분류'].value_counts().head(10)
                    sector_df = pd.DataFrame({
                        '업종': sector_counts.index,
                        '건수': sector_counts.values
                    })
                    st.dataframe(sector_df, hide_index=True, use_container_width=True)
                    
                    # 차트
                    fig = px.bar(sector_df, x='업종', y='건수', 
                                title=f'{year}년 업종별 발행 건수 (TOP 10)')
                    fig.update_layout(xaxis={'tickangle': 45})
                    st.plotly_chart(fig, use_container_width=True)
                
                st.markdown("---")
                
                # 4. 멀티플 통계
                st.markdown("### 💰 멀티플 중앙값")
                multiples = ['EV/EBITDA', 'EV/Sales', 'PER', 'PSR']
                available_multiples = [m for m in multiples if m in df_filtered.columns]
                
                if available_multiples:
                    multiple_stats = []
                    for multiple in available_multiples:
                        values = pd.to_numeric(df_filtered[multiple], errors='coerce').dropna()
                        if len(values) > 0:
                            multiple_stats.append({
                                '지표': multiple,
                                '중앙값': values.median(),
                                '평균': values.mean(),
                                '표본수': len(values)
                            })
                    
                    if multiple_stats:
                        multiple_df = pd.DataFrame(multiple_stats)
                        st.dataframe(multiple_df, hide_index=True, use_container_width=True)
                else:
                    st.info("멀티플 데이터가 없습니다.")
                
                st.markdown("---")
                
                # 5. 평가법인별 활동량
                if '평가법인' in df_filtered.columns:
                    st.markdown("### 🏢 평가법인별 활동량 (TOP 5)")
                    firm_counts = df_filtered['평가법인'].value_counts().head(5)
                    firm_df = pd.DataFrame({
                        '평가법인': firm_counts.index,
                        '건수': firm_counts.values
                    })
                    st.dataframe(firm_df, hide_index=True, use_container_width=True)
                    
                    # 차트
                    fig = px.bar(firm_df, x='평가법인', y='건수',
                                title=f'{year}년 평가법인별 활동량 (TOP 5)')
                    fig.update_layout(xaxis={'tickangle': 45})
                    st.plotly_chart(fig, use_container_width=True)
                
                st.markdown("---")
                
                # 6. 월별 발행 추이
                if '발행일자' in df_filtered.columns:
                    st.markdown("### 📅 월별 발행 추이")
                    df_monthly = df_filtered.copy()
                    df_monthly = df_monthly.copy()  # SettingWithCopyWarning 방지
                    df_monthly.loc[:, '월'] = df_monthly['발행일자'].dt.to_period('M').astype(str)
                    monthly_counts = df_monthly['월'].value_counts().sort_index()
                    monthly_df = pd.DataFrame({
                        '월': monthly_counts.index,
                        '건수': monthly_counts.values
                    })
                    
                    fig = px.line(monthly_df, x='월', y='건수',
                                 title=f'{year}년 월별 발행 추이',
                                 markers=True)
                    fig.update_layout(xaxis={'tickangle': 45})
                    st.plotly_chart(fig, use_container_width=True)
                
                return True
        
        # 13. 연도별 산업별 WACC 트렌드 분석
        elif "트렌드" in question and "wacc" in question_lower and ("연도별" in question or "산업별" in question):
            st.subheader('연도별 산업별 WACC 트렌드 분석')
            
            # 분석할 연도 목록
            years = [2022, 2023, 2024, 2025]
            
            # 분석할 산업 목록
            sectors = ['금융', '금융업', '소비재', '헬스케어', 'IT', '제조', '제조업', '바이오']
            
            # 연도별 산업별 WACC 데이터 수집
            trend_data = []
            
            for year in years:
                start_date = pd.Timestamp(f'{year}-01-01')
                end_date = pd.Timestamp(f'{year}-12-31')
                
                # 날짜 필터링
                if '발행일자' in df.columns:
                    df['발행일자'] = pd.to_datetime(df['발행일자'], errors='coerce')
                    df_year = df[(df['발행일자'] >= start_date) & (df['발행일자'] <= end_date)]
                else:
                    df_year = df
                
                for sector in sectors:
                    # 산업 필터링
                    if '공시발행_기업_산업분류' in df_year.columns:
                        df_sector = df_year[df_year['공시발행_기업_산업분류'].str.contains(sector, na=False)]
                    else:
                        df_sector = df_year
                    
                    # WACC 값 추출
                    if 'WACC' in df_sector.columns:
                        wacc_values = pd.to_numeric(df_sector['WACC'], errors='coerce').dropna()
                        if len(wacc_values) > 0:
                            trend_data.append({
                                '연도': year,
                                '산업': sector,
                                '평균_WACC': wacc_values.mean() * 100,
                                '중앙값_WACC': wacc_values.median() * 100,
                                '표본수': len(wacc_values)
                            })
            
            if trend_data:
                trend_df = pd.DataFrame(trend_data)
                
                # 산업별로 그룹화하여 표시
                st.markdown("### 📊 연도별 산업별 WACC 평균")
                
                # 피벗 테이블 생성 (연도 x 산업)
                pivot_avg = trend_df.pivot_table(
                    index='산업', 
                    columns='연도', 
                    values='평균_WACC', 
                    aggfunc='mean'
                )
                
                # 표본수가 0인 경우 제외
                pivot_avg = pivot_avg.fillna(0)
                
                st.dataframe(pivot_avg.round(2), use_container_width=True)
                
                # 라인 차트 생성 (산업별 트렌드)
                st.markdown("### 📈 산업별 WACC 트렌드 (라인 차트)")
                
                # 각 산업별로 라인 차트 생성
                fig = go.Figure()
                
                for sector in trend_df['산업'].unique():
                    sector_data = trend_df[trend_df['산업'] == sector].sort_values('연도')
                    if len(sector_data) > 0:
                        fig.add_trace(go.Scatter(
                            x=sector_data['연도'],
                            y=sector_data['평균_WACC'],
                            mode='lines+markers',
                            name=sector,
                            line=dict(width=2),
                            marker=dict(size=8)
                        ))
                
                fig.update_layout(
                    title='연도별 산업별 WACC 트렌드',
                    xaxis_title='연도',
                    yaxis_title='평균 WACC (%)',
                    hovermode='x unified',
                    height=500
                )
                st.plotly_chart(fig, use_container_width=True)
                
                # 히트맵 생성
                st.markdown("### 🔥 연도별 산업별 WACC 히트맵")
                
                fig_heatmap = go.Figure(data=go.Heatmap(
                    z=pivot_avg.values,
                    x=pivot_avg.columns,
                    y=pivot_avg.index,
                    colorscale='RdYlGn_r',  # 빨강-노랑-초록 (역순, 높은 값이 빨강)
                    text=pivot_avg.values.round(2),
                    texttemplate="%{text}%",
                    textfont={"size": 10},
                    hoverongaps=False,
                    colorbar=dict(title="WACC (%)")
                ))
                
                fig_heatmap.update_layout(
                    title='연도별 산업별 WACC 히트맵',
                    xaxis_title='연도',
                    yaxis_title='산업',
                    height=400
                )
                st.plotly_chart(fig_heatmap, use_container_width=True)
                
                # 상세 데이터 표시
                st.markdown("### 📋 상세 데이터")
                display_trend = trend_df.copy()
                display_trend['평균_WACC'] = display_trend['평균_WACC'].apply(lambda x: f"{x:.2f}%")
                display_trend['중앙값_WACC'] = display_trend['중앙값_WACC'].apply(lambda x: f"{x:.2f}%")
                display_trend = display_trend.sort_values(['산업', '연도'])
                st.dataframe(display_trend, hide_index=True, use_container_width=True)
                
                # 통계 요약
                st.markdown("### 📊 통계 요약")
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("분석 연도 수", len(years))
                with col2:
                    st.metric("분석 산업 수", len(trend_df['산업'].unique()))
                with col3:
                    st.metric("총 데이터 포인트", len(trend_df))
                with col4:
                    avg_wacc = trend_df['평균_WACC'].mean()
                    st.metric("전체 평균 WACC", f"{avg_wacc:.2f}%")
                
                return True
            else:
                st.warning("트렌드 분석을 위한 데이터를 찾을 수 없습니다.")
                return True
        
        return False
        
    except Exception as e:
        st.error(f"분석 중 오류가 발생했습니다: {e}")
        return False

# 페이지 설정
st.set_page_config(
    page_title="주요사항보고서 공시 DB",
    page_icon="📊",
    layout="wide"
)

# 언어 번역 딕셔너리
TRANSLATIONS = {
    'ko': {
        'title': '주요사항보고서 공시 DB',
        'sidebar_title': '📋 외평보고서 분석 시스템',
        'sidebar_desc': '외평보고서 데이터를 분석하고 검색할 수 있습니다.',
        'chat_tab': '💬 챗봇',
        'search_tab': '🔍 데이터 검색',
        'chat_header': '💬 예상 Q&A',
        'search_header': '🔍 데이터 검색',
        'search_type': '검색 유형을 선택하세요:',
        'company_name': '기업명',
        'industry': '산업분류',
        'business': '주요사업',
        'issue_date': '발행일자',
        'search_button': '검색',
        'enter_company': '기업명을 입력하세요:',
        'enter_industry': '산업분류를 입력하세요:',
        'enter_business': '주요사업을 입력하세요:',
        'select_date': '발행일자 기간을 선택하세요:',
        'example_questions': '예시 질문:',
        'wacc_analysis': '**WACC 분석**',
        'similar_companies': '**유사기업 분석**',
        'period_analysis': '**기간별 분석**',
        'noa_analysis': '**비영업자산 분석**',
        'qc_analysis': '**품질관리(QC)**',
        'industry_finance': '**연도별 금융업 분석**',
        'industry_consumer': '**연도별 소비재 분석**',
        'industry_healthcare': '**연도별 헬스케어 분석**',
        'industry_it': '**연도별 IT 분석**',
        'industry_manufacturing': '**연도별 제조업 분석**',
        'industry_bio': '**연도별 바이오 분석**',
        'transaction_rel': '**업종 간 거래 관계**',
        'other_analysis': '**기타 분석**',
        'yearly_stats': '**연도별 주요통계**',
        'wacc_trend': '**WACC 트렌드 분석**',
        # 버튼 텍스트
        'btn_virtual_asset': '가상자산 사업 유사기업',
        'btn_music': '음원 사업 유사기업',
        'btn_ai': 'AI 업계 유사기업',
        'btn_bio': '바이오 업계 유사기업',
        'btn_game': '게임 업계 유사기업',
        'btn_cloud': '클라우드 유사기업',
        'btn_security': '정보보안 업계 유사기업',
        'btn_finance_evsales': '금융업 기업들의 EV/Sales',
        'btn_blockchain': '블록체인 유사기업',
        'btn_industry_wacc': '산업별 WACC 중앙값',
        'btn_valuator_wacc': '평가법인별 WACC 비교',
        'btn_g_wacc': 'g ≥ WACC 위반',
        'btn_perpetual_cf': '영구현금흐름 비율',
        'btn_wacc_top10': 'WACC Top 10',
        'btn_high_noa': '비영업자산 비중 높은 기업',
        'btn_sector_noa': '업종별 비영업자산구성',
        'btn_de_missing': 'D/E 미기재 영향',
        'btn_recent_valuators': '최근 12개월 평가법인',
        'btn_transaction_matrix': '업종 간 거래 매트릭스',
        'btn_investment_mapping': '투자 맵핑 분석',
        'btn_multiple_median': '산업별 멀티플 중앙값',
        'btn_wacc_trend': '연도별 산업별 WACC 트렌드',
        # 섹션 제목
        'section_similar_q': '**유사기업 질문**',
        'section_industry_similar': '**업종별 유사기업**',
        'section_financial_ratio': '**재무비율 질문**',
        'section_valuation': '**밸류에이션 분석**',
        'section_cashflow': '**현금흐름 분석**',
        'section_noa': '**비영업자산 분석**',
        # 질문 텍스트
        'q_virtual_asset': '가상자산 사업을 하는 기업들이 선정한 유사기업은 무엇인가요?',
        'q_music': '음원 사업을 하는 기업들이 선정한 유사기업은 무엇인가요?',
        'q_ai': 'AI 업계 기업들이 선정한 유사기업은 무엇인가요?',
        'q_bio': '바이오 업계 기업들이 선정한 유사기업은 무엇인가요?',
        'q_game': '게임 업계 기업들이 선정한 유사기업은 무엇인가요?',
        'q_cloud': '클라우드 사업을 하는 기업들이 선정한 유사기업은 무엇인가요?',
        'q_security': '정보보안 업계 기업들이 선정한 유사기업은 무엇인가요?',
        'q_finance_evsales': '2022년 이후 발행된 금융업 기업들의 EV/Sales 값은 어떻게 되나요?',
        'q_blockchain': '블록체인 사업을 하는 기업들이 선정한 유사기업은 무엇인가요?',
        'q_industry_wacc': '산업별 WACC 중앙값은 어떻게 되나요?',
        'q_valuator_wacc': '평가법인별 WACC 중앙값을 비교해주세요',
        'q_g_wacc': 'g가 WACC보다 크거나 같은 위반 사례들을 보여주세요',
        'q_perpetual_cf': '영구현금흐름 비율이 50% 이상인 기업들을 보여주세요',
        'q_wacc_top10': 'WACC가 가장 높은 상위 10개 기업은 어디인가요?',
        'q_high_noa': '기업가치 대비 비영업자산이 많은 기업들을 보여주세요',
        'q_sector_noa': '업종별 비영업용자산구성내역 빈도를 TOP5 순서로 보여주세요',
        'q_de_missing': 'D/E 미기재가 WACC에 미치는 영향을 분석해주세요',
        'q_recent_valuators': '최근 12개월 동안 평가법인별 활동량 TOP5를 보여주세요',
        'q_transaction_matrix': '업종 간 거래 관계를 보여주세요',
        'q_investment_mapping': '공시발행기업의 투자 맵핑을 보여주세요',
        'q_multiple_median': '산업별 EV/EBITDA 중앙값을 비교해주세요',
        'q_wacc_trend': '연도별 산업별 WACC 트렌드를 보여주세요',
        # 입력 필드
        'input_question': '질문을 입력하세요:',
        'input_placeholder': '예: 가상자산 사업을 하는 기업들이 선정한 유사기업은 무엇인가요?',
        'btn_ask': '질문하기',
        # 사이드바
        'sidebar_usage': '📚 사용법',
        'sidebar_usage_desc': '**간편한 Q&A 분석:**',
        'sidebar_usage_point1': '- 예시 질문 버튼을 클릭하거나 직접 질문 입력',
        'sidebar_usage_point2': '- 유사기업, 재무비율, 밸류에이션 분석 등 다양한 정보 제공',
        'sidebar_usage_point3': '- API 키 없이도 모든 기능 사용 가능',
        'sidebar_examples': '💡 예시 질문',
        'sidebar_similar_title': '**유사기업 질문:**',
        'sidebar_similar_ex1': '- "가상자산 사업 유사기업"',
        'sidebar_similar_ex2': '- "음원 사업 유사기업"',
        'sidebar_similar_ex3': '- "게임 업계 유사기업"',
        'sidebar_financial_title': '**재무비율 질문:**',
        'sidebar_financial_ex1': '- "금융업 기업들의 EV/Sales"',
        'sidebar_financial_ex2': '- "산업별 WACC 중앙값"',
        'sidebar_financial_ex3': '- "평가법인별 WACC 비교"',
        'sidebar_valuation_title': '**밸류에이션 분석:**',
        'sidebar_valuation_ex1': '- "g가 WACC보다 큰 위반 사례"',
        'sidebar_valuation_ex2': '- "D/E 미기재 영향 분석"',
        'sidebar_valuation_ex3': '- "WACC Top 10"',
        'sidebar_new_title': '**새로운 분석:**',
        'sidebar_new_ex1': '- "영구현금흐름 비율이 50% 이상인 기업"',
        'sidebar_new_ex2': '- "업종별 비영업용자산구성내역 TOP5"',
        'sidebar_new_ex3': '- "2023년 헬스케어 WACC"',
        'sidebar_new_ex4': '- "2022년 IT업 WACC"',
        'sidebar_new_ex5': '- "2023년 바이오 WACC"',
        'sidebar_new_ex6': '- "연도별 금융업/소비재/헬스케어 WACC"',
    },
    'en': {
        'title': 'Key Disclosure Reports DB',
        'sidebar_title': '📋 Valuation Report Analysis System',
        'sidebar_desc': 'Analyze and search valuation report data.',
        'chat_tab': '💬 Chatbot',
        'search_tab': '🔍 Data Search',
        'chat_header': '💬 Expected Q&A',
        'search_header': '🔍 Data Search',
        'search_type': 'Select search type:',
        'company_name': 'Company Name',
        'industry': 'Industry',
        'business': 'Main Business',
        'issue_date': 'Issue Date',
        'search_button': 'Search',
        'enter_company': 'Enter company name:',
        'enter_industry': 'Enter industry:',
        'enter_business': 'Enter main business:',
        'select_date': 'Select date range:',
        'example_questions': 'Example Questions:',
        'wacc_analysis': '**WACC Analysis**',
        'similar_companies': '**Similar Companies Analysis**',
        'period_analysis': '**Period Analysis**',
        'noa_analysis': '**Non-Operating Assets Analysis**',
        'qc_analysis': '**Quality Control (QC)**',
        'industry_finance': '**Annual Finance Industry Analysis**',
        'industry_consumer': '**Annual Consumer Industry Analysis**',
        'industry_healthcare': '**Annual Healthcare Industry Analysis**',
        'industry_it': '**Annual IT Industry Analysis**',
        'industry_manufacturing': '**Annual Manufacturing Industry Analysis**',
        'industry_bio': '**Annual Bio Industry Analysis**',
        'transaction_rel': '**Inter-Industry Transaction Relations**',
        'other_analysis': '**Other Analysis**',
        'yearly_stats': '**Annual Key Statistics**',
        'wacc_trend': '**WACC Trend Analysis**',
        # 버튼 텍스트
        'btn_virtual_asset': 'Virtual Asset Business Similar Companies',
        'btn_music': 'Music Business Similar Companies',
        'btn_ai': 'AI Industry Similar Companies',
        'btn_bio': 'Bio Industry Similar Companies',
        'btn_game': 'Game Industry Similar Companies',
        'btn_cloud': 'Cloud Similar Companies',
        'btn_security': 'Information Security Industry Similar Companies',
        'btn_finance_evsales': 'Finance Industry EV/Sales',
        'btn_blockchain': 'Blockchain Similar Companies',
        'btn_industry_wacc': 'Industry WACC Median',
        'btn_valuator_wacc': 'Compare WACC by Valuation Firm',
        'btn_g_wacc': 'g ≥ WACC Violation',
        'btn_perpetual_cf': 'Perpetual Cash Flow Ratio',
        'btn_wacc_top10': 'WACC Top 10',
        'btn_high_noa': 'Companies with High Non-Operating Assets',
        'btn_sector_noa': 'Non-Operating Assets by Industry',
        'btn_de_missing': 'D/E Non-Disclosure Impact',
        'btn_recent_valuators': 'Valuation Firms (Last 12 Months)',
        'btn_transaction_matrix': 'Inter-Industry Transaction Matrix',
        'btn_investment_mapping': 'Investment Mapping Analysis',
        'btn_multiple_median': 'Industry Multiples Median',
        'btn_wacc_trend': 'Annual Industry WACC Trend',
        # 섹션 제목
        'section_similar_q': '**Similar Company Questions**',
        'section_industry_similar': '**Industry-Specific Similar Companies**',
        'section_financial_ratio': '**Financial Ratio Questions**',
        'section_valuation': '**Valuation Analysis**',
        'section_cashflow': '**Cash Flow Analysis**',
        'section_noa': '**Non-Operating Assets Analysis**',
        # 질문 텍스트
        'q_virtual_asset': 'What are the similar companies selected by companies in the virtual asset business?',
        'q_music': 'What are the similar companies selected by companies in the music business?',
        'q_ai': 'What are the similar companies selected by companies in the AI industry?',
        'q_bio': 'What are the similar companies selected by companies in the bio industry?',
        'q_game': 'What are the similar companies selected by companies in the game industry?',
        'q_cloud': 'What are the similar companies selected by companies in the cloud business?',
        'q_security': 'What are the similar companies selected by companies in the information security industry?',
        'q_finance_evsales': 'What are the EV/Sales values of finance industry companies issued after 2022?',
        'q_blockchain': 'What are the similar companies selected by companies in the blockchain business?',
        'q_industry_wacc': 'What is the industry WACC median?',
        'q_valuator_wacc': 'Please compare the WACC median by valuation firm',
        'q_g_wacc': 'Please show cases where g is greater than or equal to WACC',
        'q_perpetual_cf': 'Please show companies with perpetual cash flow ratio over 50%',
        'q_wacc_top10': 'What are the top 10 companies with the highest WACC?',
        'q_high_noa': 'Please show companies with high non-operating assets relative to enterprise value',
        'q_sector_noa': 'Please show the top 5 non-operating asset composition by industry in order',
        'q_de_missing': 'Please analyze the impact of D/E non-disclosure on WACC',
        'q_recent_valuators': 'Please show the top 5 valuation firms by activity in the last 12 months',
        'q_transaction_matrix': 'Please show inter-industry transaction relationships',
        'q_investment_mapping': 'Please show investment mapping of public offering companies',
        'q_multiple_median': 'Please compare industry EV/EBITDA medians',
        'q_wacc_trend': 'Please show annual industry WACC trends',
        # 입력 필드
        'input_question': 'Enter your question:',
        'input_placeholder': 'Example: What are the similar companies selected by companies in the virtual asset business?',
        'btn_ask': 'Ask',
        # 사이드바
        'sidebar_usage': '📚 Usage',
        'sidebar_usage_desc': '**Easy Q&A Analysis:**',
        'sidebar_usage_point1': '- Click example question buttons or directly enter questions',
        'sidebar_usage_point2': '- Provides various information such as similar companies, financial ratios, and valuation analysis',
        'sidebar_usage_point3': '- All functions available without an API key',
        'sidebar_examples': '💡 Example Questions',
        'sidebar_similar_title': '**Similar Company Questions:**',
        'sidebar_similar_ex1': '- "Virtual asset business similar companies"',
        'sidebar_similar_ex2': '- "Music business similar companies"',
        'sidebar_similar_ex3': '- "Game industry similar companies"',
        'sidebar_financial_title': '**Financial Ratio Questions:**',
        'sidebar_financial_ex1': '- "Finance industry EV/Sales"',
        'sidebar_financial_ex2': '- "Industry WACC median"',
        'sidebar_financial_ex3': '- "Compare WACC by valuation firm"',
        'sidebar_valuation_title': '**Valuation Analysis:**',
        'sidebar_valuation_ex1': '- "Cases where g is greater than WACC"',
        'sidebar_valuation_ex2': '- "D/E non-disclosure impact analysis"',
        'sidebar_valuation_ex3': '- "WACC Top 10"',
        'sidebar_new_title': '**New Analysis:**',
        'sidebar_new_ex1': '- "Companies with perpetual cash flow ratio over 50%"',
        'sidebar_new_ex2': '- "Top 5 non-operating asset composition by industry"',
        'sidebar_new_ex3': '- "2023 Healthcare WACC"',
        'sidebar_new_ex4': '- "2022 IT Industry WACC"',
        'sidebar_new_ex5': '- "2023 Bio WACC"',
        'sidebar_new_ex6': '- "Annual Finance/Consumer/Healthcare WACC"',
    }
}

# 세션 상태 초기화
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'gpt_chatbot' not in st.session_state:
    st.session_state.gpt_chatbot = None
if 'language' not in st.session_state:
    st.session_state.language = 'ko'  # 기본 언어는 한국어

# 영어 질문을 한글 질문으로 매핑하는 딕셔너리
EN_TO_KO_QUESTIONS = {
    # 유사기업 질문
    'What are the similar companies selected by companies in the virtual asset business?': '가상자산 사업을 하는 기업들이 선정한 유사기업은 무엇인가요?',
    'What are the similar companies selected by companies in the music business?': '음원 사업을 하는 기업들이 선정한 유사기업은 무엇인가요?',
    'What are the similar companies selected by companies in the AI industry?': 'AI 업계 기업들이 선정한 유사기업은 무엇인가요?',
    'What are the similar companies selected by companies in the bio industry?': '바이오 업계 기업들이 선정한 유사기업은 무엇인가요?',
    'What are the similar companies selected by companies in the game industry?': '게임 업계 기업들이 선정한 유사기업은 무엇인가요?',
    'What are the similar companies selected by companies in the cloud business?': '클라우드 사업을 하는 기업들이 선정한 유사기업은 무엇인가요?',
    'What are the similar companies selected by companies in the information security industry?': '정보보안 업계 기업들이 선정한 유사기업은 무엇인가요?',
    'What are the similar companies selected by companies in the blockchain business?': '블록체인 사업을 하는 기업들이 선정한 유사기업은 무엇인가요?',
    # 재무비율 질문
    'What are the EV/Sales values of finance industry companies issued after 2022?': '2022년 이후 발행된 금융업 기업들의 EV/Sales 값은 어떻게 되나요?',
    # 밸류에이션 분석
    'What is the industry WACC median?': '산업별 WACC 중앙값은 어떻게 되나요?',
    'Please compare the WACC median by valuation firm': '평가법인별 WACC 중앙값을 비교해주세요',
    'Please show cases where g is greater than or equal to WACC': 'g가 WACC보다 크거나 같은 위반 사례들을 보여주세요',
    # 현금흐름 분석
    'Please show companies with perpetual cash flow ratio over 50%': '영구현금흐름 비율이 50% 이상인 기업들을 보여주세요',
    'What are the top 10 companies with the highest WACC?': 'WACC가 가장 높은 상위 10개 기업은 어디인가요?',
    # 비영업자산 분석
    'Please show companies with high non-operating assets relative to enterprise value': '기업가치 대비 비영업자산이 많은 기업들을 보여주세요',
    'Please show the top 5 non-operating asset composition by industry in order': '업종별 비영업용자산구성내역 빈도를 TOP5 순서로 보여주세요',
    # 품질관리
    'Please analyze the impact of D/E non-disclosure on WACC': 'D/E 미기재가 WACC에 미치는 영향을 분석해주세요',
    'Please show the top 5 valuation firms by activity in the last 12 months': '최근 12개월 동안 평가법인별 활동량 TOP5를 보여주세요',
    # 거래 관계
    'Please show inter-industry transaction relationships': '업종 간 거래 관계를 보여주세요',
    'Please show investment mapping of public offering companies': '공시발행기업의 투자 맵핑을 보여주세요',
    # 기타 분석
    'Please compare industry EV/EBITDA medians': '산업별 EV/EBITDA 중앙값을 비교해주세요',
    'Please show annual industry WACC trends': '연도별 산업별 WACC 트렌드를 보여주세요',
    # 연도별 WACC 질문
    'What is the average WACC of the finance industry in 2022?': '2022년 금융업의 평균 WACC는 얼마인가요?',
    'What is the average WACC of the finance industry in 2023?': '2023년 금융업의 평균 WACC는 얼마인가요?',
    'What is the average WACC of the finance industry in 2024?': '2024년 금융업의 평균 WACC는 얼마인가요?',
    'What is the average WACC of the finance industry in 2025?': '2025년 금융업의 평균 WACC는 얼마인가요?',
    'What is the average WACC of the consumer industry in 2022?': '2022년 소비재의 평균 WACC는 얼마인가요?',
    'What is the average WACC of the consumer industry in 2023?': '2023년 소비재의 평균 WACC는 얼마인가요?',
    'What is the average WACC of the consumer industry in 2024?': '2024년 소비재의 평균 WACC는 얼마인가요?',
    'What is the average WACC of the consumer industry in 2025?': '2025년 소비재의 평균 WACC는 얼마인가요?',
    'What is the average WACC of the healthcare industry in 2022?': '2022년 헬스케어의 평균 WACC는 얼마인가요?',
    'What is the average WACC of the healthcare industry in 2023?': '2023년 헬스케어의 평균 WACC는 얼마인가요?',
    'What is the average WACC of the healthcare industry in 2024?': '2024년 헬스케어의 평균 WACC는 얼마인가요?',
    'What is the average WACC of the healthcare industry in 2025?': '2025년 헬스케어의 평균 WACC는 얼마인가요?',
    'What is the average WACC of the IT industry in 2022?': '2022년 IT의 평균 WACC는 얼마인가요?',
    'What is the average WACC of the IT industry in 2023?': '2023년 IT의 평균 WACC는 얼마인가요?',
    'What is the average WACC of the IT industry in 2024?': '2024년 IT의 평균 WACC는 얼마인가요?',
    'What is the average WACC of the IT industry in 2025?': '2025년 IT의 평균 WACC는 얼마인가요?',
    'What is the average WACC of the manufacturing industry in 2022?': '2022년 제조업의 평균 WACC는 얼마인가요?',
    'What is the average WACC of the manufacturing industry in 2023?': '2023년 제조업의 평균 WACC는 얼마인가요?',
    'What is the average WACC of the manufacturing industry in 2024?': '2024년 제조업의 평균 WACC는 얼마인가요?',
    'What is the average WACC of the manufacturing industry in 2025?': '2025년 제조업의 평균 WACC는 얼마인가요?',
    'What is the average WACC of the bio industry in 2022?': '2022년 바이오의 평균 WACC는 얼마인가요?',
    'What is the average WACC of the bio industry in 2023?': '2023년 바이오의 평균 WACC는 얼마인가요?',
    'What is the average WACC of the bio industry in 2024?': '2024년 바이오의 평균 WACC는 얼마인가요?',
    'What is the average WACC of the bio industry in 2025?': '2025년 바이오의 평균 WACC는 얼마인가요?',
    'What is the average WACC of all industries in 2024?': '2024년 전체 업종의 평균 WACC는 얼마인가요?',
    'What is the average WACC of all industries in 2025?': '2025년 전체 업종의 평균 WACC는 얼마인가요?',
    # 연도별 주요통계
    'Please show 2022 key statistics': '2022년 주요통계를 보여주세요',
    'Please show 2023 key statistics': '2023년 주요통계를 보여주세요',
    'Please show 2024 key statistics': '2024년 주요통계를 보여주세요',
    'Please show 2025 key statistics': '2025년 주요통계를 보여주세요',
}

def translate_question_to_korean(question):
    """영어 질문을 한글 질문으로 변환"""
    if question in EN_TO_KO_QUESTIONS:
        return EN_TO_KO_QUESTIONS[question]
    return question  # 매핑이 없으면 원본 반환

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
        return pd.DataFrame()
    
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
        return pd.DataFrame()

def search_by_company_name(company_name):
    """기업명으로 검색"""
    conn = get_db_connection()
    if conn is None:
        return pd.DataFrame()
    
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
    WHERE 공시발행_기업명 LIKE ? OR 평가대상기업명 LIKE ?
    ORDER BY 발행일자 DESC
    """
    
    try:
        df = pd.read_sql_query(query, conn, params=[f'%{company_name}%', f'%{company_name}%'])
        conn.close()
        return df
    except Exception as e:
        st.error(f"검색 오류: {e}")
        conn.close()
        return pd.DataFrame()

def search_by_business(business):
    """주요사업으로 검색"""
    conn = get_db_connection()
    if conn is None:
        return pd.DataFrame()
    
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
    WHERE 평가대상_주요사업 LIKE ?
    ORDER BY 발행일자 DESC
    """
    
    try:
        df = pd.read_sql_query(query, conn, params=[f'%{business}%'])
        conn.close()
        return df
    except Exception as e:
        st.error(f"검색 오류: {e}")
        conn.close()
        return pd.DataFrame()

def search_by_date_range(start_date_str, end_date_str=None):
    """발행일자 기간 범위로 검색"""
    conn = get_db_connection()
    if conn is None:
        return pd.DataFrame()
    
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
    WHERE 발행일자 >= ?
    """
    
    params = [start_date_str]
    
    if end_date_str:
        query += " AND 발행일자 <= ?"
        params.append(end_date_str)
    else:
        # 종료일이 없으면 시작일만 사용 (단일 날짜 검색)
        query += " AND 발행일자 <= ?"
        params.append(start_date_str)
    
    query += " ORDER BY 발행일자 DESC"
    
    try:
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        return df
    except Exception as e:
        st.error(f"검색 오류: {e}")
        conn.close()
        return pd.DataFrame()

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
    # 언어 선택
    lang = st.session_state.language
    t = TRANSLATIONS[lang]
    
    # 상단에 언어 전환 버튼
    col_lang1, col_lang2, col_lang_space = st.columns([1, 1, 10])
    with col_lang1:
        if st.button("🇰🇷 KR", key="lang_kr", use_container_width=True):
            st.session_state.language = 'ko'
            st.rerun()
    with col_lang2:
        if st.button("🇺🇸 EN", key="lang_en", use_container_width=True):
            st.session_state.language = 'en'
            st.rerun()
    
    st.title(f"📊 {t['title']}")
    st.markdown("---")
    
    # 사이드바 설정
    with st.sidebar:
        st.header(t['sidebar_usage'])
        st.markdown(f"""
        {t['sidebar_usage_desc']}
        - {t['sidebar_usage_point1']}
        - {t['sidebar_usage_point2']}
        - {t['sidebar_usage_point3']}
        """)
        
        st.markdown("---")
        st.header(t['sidebar_examples'])
        st.markdown(f"""
        {t['sidebar_similar_title']}
        - {t['sidebar_similar_ex1']}
        - {t['sidebar_similar_ex2']}
        - {t['sidebar_similar_ex3']}
        
        {t['sidebar_financial_title']}
        - {t['sidebar_financial_ex1']}
        - {t['sidebar_financial_ex2']}
        - {t['sidebar_financial_ex3']}
        
        {t['sidebar_valuation_title']}
        - {t['sidebar_valuation_ex1']}
        - {t['sidebar_valuation_ex2']}
        - {t['sidebar_valuation_ex3']}
        
        {t['sidebar_new_title']}
        - {t['sidebar_new_ex1']}
        - {t['sidebar_new_ex2']}
        - {t['sidebar_new_ex3']}
        - {t['sidebar_new_ex4']}
        - {t['sidebar_new_ex5']}
        - {t['sidebar_new_ex6']}
        """)
    
    # 메인 탭
    tab1,  tab2 = st.tabs([t['chat_tab'],  t['search_tab']])
    
    with tab1:
        st.header(t['chat_header'])
        
        # 예시 질문 버튼들
        col1, col2, col3, col4 = st.columns(4)
        
        # 첫 번째 행: 유사기업 질문들
        with col1:
            st.markdown(t['section_similar_q'])
            if st.button(t['btn_virtual_asset'], key="virtual_asset_companies"):
                st.session_state.example_question = t['q_virtual_asset']
            if st.button(t['btn_music'], key="music_companies"):
                st.session_state.example_question = t['q_music']
            if st.button(t['btn_ai'], key="ai_companies"):
                st.session_state.example_question = t['q_ai']
        
        with col2:
            st.markdown(t['section_industry_similar'])
            if st.button(t['btn_bio'], key="bio_companies"):
                st.session_state.example_question = t['q_bio']
            if st.button(t['btn_game'], key="game_companies"):
                st.session_state.example_question = t['q_game']
            if st.button(t['btn_cloud'], key="cloud_companies"):
                st.session_state.example_question = t['q_cloud']
        
        with col3:
            st.markdown(t['section_financial_ratio'])
            if st.button(t['btn_security'], key="security_companies"):
                st.session_state.example_question = t['q_security']
            if st.button(t['btn_finance_evsales'], key="finance_evsales"):
                st.session_state.example_question = t['q_finance_evsales']
            if st.button(t['btn_blockchain'], key="blockchain_companies"):
                st.session_state.example_question = t['q_blockchain']
        
        with col4:
            st.markdown(t['section_valuation'])
            if st.button(t['btn_industry_wacc'], key="industry_wacc_median"):
                st.session_state.example_question = t['q_industry_wacc']
            if st.button(t['btn_valuator_wacc'], key="valuator_wacc_compare"):
                st.session_state.example_question = t['q_valuator_wacc']
            if st.button(t['btn_g_wacc'], key="g_wacc_violation"):
                st.session_state.example_question = t['q_g_wacc']
        
        # 두 번째 행: 새로운 질문들
        st.markdown("---")
        col5, col6, col7, col8 = st.columns(4)
        
        with col5:
            st.markdown(t['section_cashflow'])
            if st.button(t['btn_perpetual_cf'], key="perpetual_cashflow_ratio"):
                st.session_state.example_question = t['q_perpetual_cf']
            if st.button(t['btn_wacc_top10'], key="wacc_top10"):
                st.session_state.example_question = t['q_wacc_top10']
        
        with col6:
            st.markdown(t['section_noa'])
            if st.button(t['btn_high_noa'], key="high_noa_companies"):
                st.session_state.example_question = t['q_high_noa']
            if st.button(t['btn_sector_noa'], key="sector_noa_composition"):
                st.session_state.example_question = t['q_sector_noa']
        
        with col7:
            st.markdown(t['qc_analysis'])
            if st.button(t['btn_de_missing'], key="de_missing_impact"):
                st.session_state.example_question = t['q_de_missing']
            if st.button(t['btn_recent_valuators'], key="recent_12m_valuators"):
                st.session_state.example_question = t['q_recent_valuators']
        
        
        # 세 번째 행: 추가 연도별+업종별 조합
        st.markdown("---")
        col9, col10, col11, col12, col13 = st.columns(5)
        
        with col9:
            st.markdown(t['industry_finance'])
            year_btn_text = {2022: "2022년 금융업 WACC" if lang == 'ko' else "2022 Finance WACC",
                             2023: "2023년 금융업 WACC" if lang == 'ko' else "2023 Finance WACC",
                             2024: "2024년 금융업 WACC" if lang == 'ko' else "2024 Finance WACC",
                             2025: "2025년 금융업 WACC" if lang == 'ko' else "2025 Finance WACC"}
            year_q_text = {2022: "2022년 금융업의 평균 WACC는 얼마인가요?" if lang == 'ko' else "What is the average WACC of the finance industry in 2022?",
                           2023: "2023년 금융업의 평균 WACC는 얼마인가요?" if lang == 'ko' else "What is the average WACC of the finance industry in 2023?",
                           2024: "2024년 금융업의 평균 WACC는 얼마인가요?" if lang == 'ko' else "What is the average WACC of the finance industry in 2024?",
                           2025: "2025년 금융업의 평균 WACC는 얼마인가요?" if lang == 'ko' else "What is the average WACC of the finance industry in 2025?"}
            for year in [2022, 2023, 2024, 2025]:
                if st.button(year_btn_text[year], key=f"finance_{year}_wacc"):
                    st.session_state.example_question = year_q_text[year]
        
        with col10:
            st.markdown(t['industry_consumer'])
            year_btn_text = {2022: "2022년 소비재 WACC" if lang == 'ko' else "2022 Consumer WACC",
                             2023: "2023년 소비재 WACC" if lang == 'ko' else "2023 Consumer WACC",
                             2024: "2024년 소비재 WACC" if lang == 'ko' else "2024 Consumer WACC",
                             2025: "2025년 소비재 WACC" if lang == 'ko' else "2025 Consumer WACC"}
            year_q_text = {2022: "2022년 소비재의 평균 WACC는 얼마인가요?" if lang == 'ko' else "What is the average WACC of the consumer industry in 2022?",
                           2023: "2023년 소비재의 평균 WACC는 얼마인가요?" if lang == 'ko' else "What is the average WACC of the consumer industry in 2023?",
                           2024: "2024년 소비재의 평균 WACC는 얼마인가요?" if lang == 'ko' else "What is the average WACC of the consumer industry in 2024?",
                           2025: "2025년 소비재의 평균 WACC는 얼마인가요?" if lang == 'ko' else "What is the average WACC of the consumer industry in 2025?"}
            for year in [2022, 2023, 2024, 2025]:
                if st.button(year_btn_text[year], key=f"consumer_{year}_wacc"):
                    st.session_state.example_question = year_q_text[year]
        
        with col11:
            st.markdown(t['industry_healthcare'])
            year_btn_text = {2022: "2022년 헬스케어 WACC" if lang == 'ko' else "2022 Healthcare WACC",
                             2023: "2023년 헬스케어 WACC" if lang == 'ko' else "2023 Healthcare WACC",
                             2024: "2024년 헬스케어 WACC" if lang == 'ko' else "2024 Healthcare WACC",
                             2025: "2025년 헬스케어 WACC" if lang == 'ko' else "2025 Healthcare WACC"}
            year_q_text = {2022: "2022년 헬스케어의 평균 WACC는 얼마인가요?" if lang == 'ko' else "What is the average WACC of the healthcare industry in 2022?",
                           2023: "2023년 헬스케어의 평균 WACC는 얼마인가요?" if lang == 'ko' else "What is the average WACC of the healthcare industry in 2023?",
                           2024: "2024년 헬스케어의 평균 WACC는 얼마인가요?" if lang == 'ko' else "What is the average WACC of the healthcare industry in 2024?",
                           2025: "2025년 헬스케어의 평균 WACC는 얼마인가요?" if lang == 'ko' else "What is the average WACC of the healthcare industry in 2025?"}
            for year in [2022, 2023, 2024, 2025]:
                if st.button(year_btn_text[year], key=f"healthcare_{year}_wacc"):
                    st.session_state.example_question = year_q_text[year]
        
        with col12:
            st.markdown(t['industry_it'])
            year_btn_text = {2022: "2022년 IT WACC" if lang == 'ko' else "2022 IT WACC",
                             2023: "2023년 IT WACC" if lang == 'ko' else "2023 IT WACC",
                             2024: "2024년 IT WACC" if lang == 'ko' else "2024 IT WACC",
                             2025: "2025년 IT WACC" if lang == 'ko' else "2025 IT WACC"}
            year_q_text = {2022: "2022년 IT의 평균 WACC는 얼마인가요?" if lang == 'ko' else "What is the average WACC of the IT industry in 2022?",
                           2023: "2023년 IT의 평균 WACC는 얼마인가요?" if lang == 'ko' else "What is the average WACC of the IT industry in 2023?",
                           2024: "2024년 IT의 평균 WACC는 얼마인가요?" if lang == 'ko' else "What is the average WACC of the IT industry in 2024?",
                           2025: "2025년 IT의 평균 WACC는 얼마인가요?" if lang == 'ko' else "What is the average WACC of the IT industry in 2025?"}
            for year in [2022, 2023, 2024, 2025]:
                if st.button(year_btn_text[year], key=f"it_{year}_wacc"):
                    st.session_state.example_question = year_q_text[year]
        
        with col13:
            st.markdown(t['industry_manufacturing'])
            year_btn_text = {2022: "2022년 제조업 WACC" if lang == 'ko' else "2022 Manufacturing WACC",
                             2023: "2023년 제조업 WACC" if lang == 'ko' else "2023 Manufacturing WACC",
                             2024: "2024년 제조업 WACC" if lang == 'ko' else "2024 Manufacturing WACC",
                             2025: "2025년 제조업 WACC" if lang == 'ko' else "2025 Manufacturing WACC"}
            year_q_text = {2022: "2022년 제조업의 평균 WACC는 얼마인가요?" if lang == 'ko' else "What is the average WACC of the manufacturing industry in 2022?",
                           2023: "2023년 제조업의 평균 WACC는 얼마인가요?" if lang == 'ko' else "What is the average WACC of the manufacturing industry in 2023?",
                           2024: "2024년 제조업의 평균 WACC는 얼마인가요?" if lang == 'ko' else "What is the average WACC of the manufacturing industry in 2024?",
                           2025: "2025년 제조업의 평균 WACC는 얼마인가요?" if lang == 'ko' else "What is the average WACC of the manufacturing industry in 2025?"}
            for year in [2022, 2023, 2024, 2025]:
                if st.button(year_btn_text[year], key=f"manufacturing_{year}_wacc"):
                    st.session_state.example_question = year_q_text[year]
        
        # 네 번째 행: 추가 업종 및 기타 분석
        st.markdown("---")
        col14, col15, col16, col17, col18 = st.columns(5)
        
        with col14:
            st.markdown(t['industry_bio'])
            year_btn_text = {2022: "2022년 바이오 WACC" if lang == 'ko' else "2022 Bio WACC",
                             2023: "2023년 바이오 WACC" if lang == 'ko' else "2023 Bio WACC",
                             2024: "2024년 바이오 WACC" if lang == 'ko' else "2024 Bio WACC",
                             2025: "2025년 바이오 WACC" if lang == 'ko' else "2025 Bio WACC"}
            year_q_text = {2022: "2022년 바이오의 평균 WACC는 얼마인가요?" if lang == 'ko' else "What is the average WACC of the bio industry in 2022?",
                           2023: "2023년 바이오의 평균 WACC는 얼마인가요?" if lang == 'ko' else "What is the average WACC of the bio industry in 2023?",
                           2024: "2024년 바이오의 평균 WACC는 얼마인가요?" if lang == 'ko' else "What is the average WACC of the bio industry in 2024?",
                           2025: "2025년 바이오의 평균 WACC는 얼마인가요?" if lang == 'ko' else "What is the average WACC of the bio industry in 2025?"}
            for year in [2022, 2023, 2024, 2025]:
                if st.button(year_btn_text[year], key=f"bio_{year}_wacc"):
                    st.session_state.example_question = year_q_text[year]
        
        with col15:
            st.markdown(t['transaction_rel'])
            if st.button(t['btn_transaction_matrix'], key="sector_transaction_matrix"):
                st.session_state.example_question = t['q_transaction_matrix']
            if st.button(t['btn_investment_mapping'], key="investment_mapping"):
                st.session_state.example_question = t['q_investment_mapping']
        
        with col16:
            st.markdown(t['other_analysis'])
            if st.button(t['btn_multiple_median'], key="industry_multiple_median"):
                st.session_state.example_question = t['q_multiple_median']
            year_btn_text = {2024: "2024년 전체 WACC" if lang == 'ko' else "2024 Overall WACC",
                             2025: "2025년 전체 WACC" if lang == 'ko' else "2025 Overall WACC"}
            year_q_text = {2024: "2024년 전체 업종의 평균 WACC는 얼마인가요?" if lang == 'ko' else "What is the average WACC of all industries in 2024?",
                           2025: "2025년 전체 업종의 평균 WACC는 얼마인가요?" if lang == 'ko' else "What is the average WACC of all industries in 2025?"}
            for year in [2024, 2025]:
                if st.button(year_btn_text[year], key=f"overall_{year}_wacc"):
                    st.session_state.example_question = year_q_text[year]
        
        with col17:
            st.markdown(t['yearly_stats'])
            year_btn_text = {2022: "2022년 주요통계" if lang == 'ko' else "2022 Key Statistics",
                             2023: "2023년 주요통계" if lang == 'ko' else "2023 Key Statistics",
                             2024: "2024년 주요통계" if lang == 'ko' else "2024 Key Statistics",
                             2025: "2025년 주요통계" if lang == 'ko' else "2025 Key Statistics"}
            year_q_text = {2022: "2022년 주요통계를 보여주세요" if lang == 'ko' else "Please show 2022 key statistics",
                           2023: "2023년 주요통계를 보여주세요" if lang == 'ko' else "Please show 2023 key statistics",
                           2024: "2024년 주요통계를 보여주세요" if lang == 'ko' else "Please show 2024 key statistics",
                           2025: "2025년 주요통계를 보여주세요" if lang == 'ko' else "Please show 2025 key statistics"}
            for year in [2022, 2023, 2024, 2025]:
                if st.button(year_btn_text[year], key=f"stats_{year}"):
                    st.session_state.example_question = year_q_text[year]
        
        with col18:
            st.markdown(t['wacc_trend'])
            if st.button(t['btn_wacc_trend'], key="wacc_trend_analysis"):
                st.session_state.example_question = t['q_wacc_trend']
        
        # 사용자 입력
        user_question = st.text_input(
            t['input_question'],
            value=st.session_state.get("example_question", ""),
            placeholder=t['input_placeholder']
        )
        
        if st.button(t['btn_ask'], key="ask_question") or user_question:
            if user_question:
                # 영어 질문을 한글 질문으로 변환 (내부 처리용)
                original_question = user_question
                user_question = translate_question_to_korean(user_question)
                
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
                        
                
                elif any(keyword in user_question for keyword in ["산업별", "중앙값", "WACC", "평가법인", "위반", "미기재", "Top", "상위", "최근", "영구현금흐름", "비영업용자산구성", "비영업자산", "업종", "거래", "투자", "맵핑", "매핑", "주요통계", "통계", "트렌드"]):
                    # 밸류에이션 분석 질문들 처리
                    st.info(f"🔍 밸류에이션 분석 질문으로 인식: '{user_question}'")
                    processed = process_valuation_analysis(user_question)
                    if processed:
                        return  # 처리되었으므로 함수 종료
                    else:
                        st.warning("해당 질문을 처리할 수 없습니다. 다른 질문을 시도해보세요.")
                        return
                
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
                
            else:
                st.warning("질문을 입력해주세요.")
    
    with tab2:
        st.header(t['search_header'])
        
        # 검색 옵션
        search_options = [t['company_name'], t['industry'], t['business'], t['issue_date']]
        search_option_map = {
            t['company_name']: "기업명",
            t['industry']: "산업분류", 
            t['business']: "주요사업",
            t['issue_date']: "발행일자"
        }
        
        search_option_display = st.selectbox(
            t['search_type'],
            search_options
        )
        search_option = search_option_map[search_option_display]
        
        if search_option == "기업명":
            search_term = st.text_input(t['enter_company'])
        elif search_option == "산업분류":
            search_term = st.text_input(t['enter_industry'])
        elif search_option == "주요사업":
            search_term = st.text_input(t['enter_business'])
        else:  # 발행일자
            # DB에서 최소/최대 날짜 가져오기
            conn = get_db_connection()
            min_date = None
            max_date = None
            if conn:
                try:
                    date_query = "SELECT MIN(발행일자) as min_date, MAX(발행일자) as max_date FROM 외평보고서 WHERE 발행일자 IS NOT NULL"
                    date_df = pd.read_sql_query(date_query, conn)
                    conn.close()
                    if not date_df.empty and pd.notna(date_df.iloc[0]['min_date']):
                        min_date = pd.to_datetime(date_df.iloc[0]['min_date']).date()
                        max_date = pd.to_datetime(date_df.iloc[0]['max_date']).date()
                except:
                    if conn:
                        conn.close()
            
            # 날짜 범위 선택 (시작일과 종료일)
            if min_date and max_date:
                # 기본값: 최근 1년
                from datetime import timedelta
                default_end = max_date
                default_start = max(default_end - timedelta(days=365), min_date)
                
                date_range = st.date_input(
                    t['select_date'],
                    value=(default_start, default_end),
                    min_value=min_date,
                    max_value=max_date,
                    help=t['select_date']
                )
            else:
                date_range = st.date_input(
                    t['select_date'],
                    value=None,
                    help=t['select_date']
                )
        
        if st.button(t['search_button'], key="search_button"):
            if search_option == "발행일자":
                # 날짜 범위 처리
                if date_range:
                    try:
                        if isinstance(date_range, tuple):
                            if len(date_range) == 2:
                                # 기간 범위 선택 (시작일, 종료일)
                                start_date = date_range[0]
                                end_date = date_range[1]
                                if start_date and end_date:
                                    start_date_str = start_date.strftime("%Y-%m-%d")
                                    end_date_str = end_date.strftime("%Y-%m-%d")
                                    data = search_by_date_range(start_date_str, end_date_str)
                                else:
                                    st.warning("시작일과 종료일을 모두 선택해주세요.")
                                    data = pd.DataFrame()
                            elif len(date_range) == 1:
                                # 단일 날짜만 선택 (튜플에 하나만)
                                start_date = date_range[0]
                                if start_date:
                                    start_date_str = start_date.strftime("%Y-%m-%d")
                                    data = search_by_date_range(start_date_str, start_date_str)
                                else:
                                    st.warning("발행일자를 선택해주세요.")
                                    data = pd.DataFrame()
                            else:
                                st.warning("발행일자를 선택해주세요.")
                                data = pd.DataFrame()
                        else:
                            # 단일 날짜 객체 (date 객체)
                            start_date_str = date_range.strftime("%Y-%m-%d")
                            data = search_by_date_range(start_date_str, start_date_str)
                    except Exception as e:
                        st.error(f"날짜 처리 오류: {e}")
                        data = pd.DataFrame()
                else:
                    st.warning("발행일자를 선택해주세요.")
                    data = pd.DataFrame()
            elif search_term:
                # 검색 옵션에 따라 다른 검색 함수 사용
                if search_option == "기업명":
                    data = search_by_company_name(str(search_term))
                elif search_option == "산업분류":
                    data = search_by_sector(str(search_term))
                elif search_option == "주요사업":
                    data = search_by_business(str(search_term))
                
            else:
                if search_option != "발행일자":
                    st.warning("검색어를 입력해주세요.")
                    data = pd.DataFrame()
            
            # 검색 결과 표시
            if 'data' in locals() and data is not None and not data.empty:
                # 검색 조건 표시
                if search_option == "발행일자" and date_range:
                    try:
                        if isinstance(date_range, tuple) and len(date_range) == 2 and date_range[0] and date_range[1]:
                            st.info(f"🔍 검색 기간: {date_range[0].strftime('%Y-%m-%d')} ~ {date_range[1].strftime('%Y-%m-%d')}")
                        else:
                            date_display = date_range[0] if (isinstance(date_range, tuple) and len(date_range) > 0) else date_range
                            if date_display:
                                st.info(f"🔍 검색 날짜: {date_display.strftime('%Y-%m-%d')}")
                    except:
                        pass
                
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
                if '공시보고서명' in data.columns:
                    display_columns.insert(0, '공시보고서명')
                
                # 존재하는 컬럼만 표시
                available_columns = [col for col in display_columns if col in data.columns]
                st.dataframe(data[available_columns], width='stretch', hide_index=True)
            elif 'data' in locals():
                    st.warning("검색 결과를 찾을 수 없습니다.")

if __name__ == "__main__":
    main()
