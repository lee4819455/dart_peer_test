# 📊 주요사항보고서 공시 DB

주요사항보고서 데이터를 기반으로 한 유사기업 검색 및 분석 챗봇 서비스입니다.

## 🌟 주요 기능

- **🔍 스마트 검색**: AI 기반 키워드 우선순위 시스템
- **💬 유사기업 분석**: 업종별 유사기업 자동 선정 정보
- **📈 데이터 시각화**: 구조화된 문장 자동 생성
- **🤖 GPT-4 통합**: OpenAI API를 통한 상세 분석 (선택사항)
- **📱 반응형 UI**: Streamlit 기반 모던한 웹 인터페이스

## 🚀 라이브 데모

[Streamlit Cloud에서 확인하기](https://your-app-url.streamlit.app)

## 🛠️ 기술 스택

- **Backend**: Python 3.9, Streamlit
- **Database**: SQLite
- **AI/ML**: OpenAI GPT-4, 스마트 키워드 매칭
- **Data Processing**: Pandas, SQLite
- **Deployment**: Streamlit Cloud, Docker

## 📋 설치 및 실행

### 로컬 실행

1. **저장소 클론**
```bash
git clone https://github.com/사용자명/저장소명.git
cd 저장소명
```

2. **의존성 설치**
```bash
pip install -r requirements.txt
```

3. **앱 실행**
```bash
streamlit run enhanced_chatbot_app.py
```

4. **브라우저에서 접속**
```
http://localhost:8501
```

### Docker 실행

```bash
# Docker 이미지 빌드
docker build -t streamlit-app .

# 컨테이너 실행
docker run -p 8501:8501 streamlit-app
```

## 📁 프로젝트 구조

```
├── enhanced_chatbot_app.py    # 메인 Streamlit 앱
├── gpt_chatbot.py            # GPT-4 통합 모듈
├── config.py                 # 설정 파일
├── requirements.txt          # Python 의존성
├── business_keywords.json    # 키워드 사전
├── similar_industries.json   # 유사 업종 매핑
├── Dockerfile               # Docker 설정
├── docker-compose.yml       # Docker Compose 설정
└── README.md               # 프로젝트 설명서
```

## 🔧 환경 설정

### 필수 파일
- `외평보고서.db`: SQLite 데이터베이스 파일
- `business_keywords.json`: 업종별 키워드 사전
- `similar_industries.json`: 유사 업종 매핑

### 환경 변수 (선택사항)
- `OPENAI_API_KEY`: OpenAI API 키 (GPT-4 분석용)

## 📊 사용법

### 1. 기본 검색 (API 키 없이)
- 유사기업 정보를 구조화된 문장으로 자동 생성
- 원본 데이터를 표 형태로 확인

### 2. 고급 분석 (API 키 입력 시)
- GPT-4를 통한 상세한 분석 및 인사이트
- 자연어로 된 종합적인 답변

### 3. 예시 질문
- "가상자산 사업 유사기업"
- "음원 사업 유사기업"
- "게임 업계 유사기업"
- "AI 업계 유사기업"

## 🚀 배포

### Streamlit Cloud (권장)
1. GitHub 저장소 연결
2. Main file path: `enhanced_chatbot_app.py`
3. 자동 배포

### Docker
```bash
docker-compose up -d
```

## 🤝 기여하기

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다. 자세한 내용은 `LICENSE` 파일을 참조하세요.

## 📞 문의

프로젝트에 대한 문의사항이 있으시면 [Issues](https://github.com/사용자명/저장소명/issues)를 통해 연락해 주세요.

## 🙏 감사의 말

- [Streamlit](https://streamlit.io/) - 웹 애플리케이션 프레임워크
- [OpenAI](https://openai.com/) - GPT-4 API
- [Pandas](https://pandas.pydata.org/) - 데이터 처리 라이브러리

---

⭐ 이 프로젝트가 도움이 되었다면 Star를 눌러주세요!
