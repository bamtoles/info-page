import streamlit as st
import google.generativeai as genai
import os, sys

st.set_page_config(page_title="고객 응대 챗봇", page_icon="🛍️")
st.title("고객 응대 챗봇 (Gemini + Streamlit)")

# 1) API 키
API_KEY = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    st.error("GEMINI_API_KEY가 설정되지 않았습니다. Streamlit Cloud Secrets에 추가하세요.")
    st.stop()

# 2) 설정 & 버전 표시
genai.configure(api_key=API_KEY)
st.sidebar.write(f"google-generativeai: **{genai.__version__}**")

# 3) 현재 키로 가능한 모델들(= generateContent 지원) 조회
with st.sidebar.expander("🔎 사용 가능한 모델 목록", expanded=False):
    try:
        available = [m for m in genai.list_models() if "generateContent" in getattr(m, "supported_generation_methods", [])]
        for m in available:
            st.write(m.name, m.supported_generation_methods)
    except Exception as e:
        st.error(f"모델 목록 조회 실패: {e}")
        st.stop()

# 4) 선호 모델 자동 선택(1.5-flash 우선 → pro → 나머지)
def pick_model_name(models):
    # 이름은 'models/...' 형식일 수 있으니 그대로 쓰되, 필요하면 접두사 제거해도 됩니다.
    def find(substr):
        return next((m.name for m in models if substr in m.name), None)
    return find("1.5-flash") or find("1.5-pro") or (models[0].name if models else None)

picked = pick_model_name(available)
if not picked:
    st.error("generateContent를 지원하는 모델을 찾지 못했습니다. 키 종류/권한을 확인하세요.")
    st.stop()

# (선택) 사이드바에서 수동 선택도 가능
model_name = st.sidebar.selectbox("사용할 모델", options=[m.name for m in available], index=[m.name for m in available].index(picked))

SYSTEM_PROMPT = """
당신은 아래 기준에 따라 답변하는 고객 응대용 AI 챗봇입니다.
--- [참고 기준 시작] ---
1) 정중하고 공감 어린 말투로 응답
2) 불편 사항을 구체적으로 정리(무엇/언제/어디서/어떻게) → 담당자 전달 안내
3) 끝에 이메일 주소 요청. 거부 시 “연락처 정보가 없어 검토 결과를 전달드릴 수 없어요” 고지
--- [참고 기준 끝] ---
추측하거나 사실이 아닌 내용은 말하지 마세요.
"""

# 모델 생성: 이름에 'models/' 접두사가 포함되어 있으면 그대로 사용 가능
model = genai.GenerativeModel(model_name=model_name, system_instruction=SYSTEM_PROMPT)

# 이하 기존 로직 유지
if "chat" not in st.session_state:
    st.session_state.chat = model.start_chat(history=[])
if "messages" not in st.session_state:
    st.session_state.messages = []

st.success("어떤 점이 불편하셨는지 알려주세요.")

for role, text in st.session_state.messages:
    with st.chat_message("ai" if role == "ai" else "user"):
        st.markdown(text)

user_msg = st.chat_input("불편/요청 사항을 입력하세요")
if user_msg:
    st.session_state.messages.append(("user", user_msg))
    with st.chat_message("user"):
        st.markdown(user_msg)
    with st.chat_message("ai"):
        try:
            resp = st.session_state.chat.send_message(user_msg)
            bot_text = resp.text
            st.session_state.messages.append(("ai", bot_text))
            st.markdown(bot_text)
        except Exception as e:
            st.error(f"오류: {e}")

if st.sidebar.button("🧹 대화 초기화"):
    st.session_state.messages = []
    st.session_state.chat = model.start_chat(history=[])
    st.rerun()
