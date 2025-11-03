import streamlit as st
import google.generativeai as genai
import os

st.set_page_config(page_title="고객 응대 챗봇", page_icon="🛍️")
st.title("고객 응대 챗봇 (Gemini + Streamlit)")
st.caption("정중 응대 · 불편 수집 · 담당자 전달 · 이메일 수집")

# --- 1) API 키 불러오기 (secrets > env > 입력 백업) ---
API_KEY = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    with st.expander("🔐 API 키가 없나요? 여기를 눌러 임시 입력"):
        API_KEY = st.text_input("Gemini API 키", type="password")
    if not API_KEY:
        st.info("`.streamlit/secrets.toml` 또는 배포 환경의 Secrets에 GEMINI_API_KEY를 저장하면 자동으로 인식됩니다.")
        st.stop()

# --- 2) Gemini 설정 ---
try:
    genai.configure(api_key=API_KEY)
except Exception as e:
    st.error(f"API 키 설정 오류: {e}")
    st.stop()

# --- 3) 시스템 프롬프트 정의 ---
SYSTEM_PROMPT = """
당신은 아래 기준에 따라 답변하는 고객 응대용 AI 챗봇입니다.

--- [참고 기준 시작] ---
1) 사용자는 쇼핑몰 구매 과정에서 겪은 불편/불만을 언급합니다. 정중하고 공감 어린 말투로 응답하세요.
2) 사용자의 불편 사항을 구체적으로 정리하여(무엇이/언제/어디서/어떻게) 수집하고, 이를 고객 응대 담당자에게 전달한다는 취지로 안내하세요.
3) 마지막에는 담당자 확인 후 회신을 위해 이메일 주소를 요청하세요.
   - 사용자가 연락 제공을 원치 않으면: 
     "죄송하지만, 연락처 정보를 받지 못하여 담당자의 검토 내용을 받으실 수 없어요."라고 정중히 고지하세요.
--- [참고 기준 끝] ---

반드시 위 기준을 따르며, 추측하거나 사실이 아닌 내용은 말하지 마세요.
"""

# --- 4) 모델/세션 초기화 ---
@st.cache_resource(show_spinner=False)
def _get_model():
    return genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction=SYSTEM_PROMPT
    )

model = _get_model()

if "chat" not in st.session_state:
    st.session_state.chat = model.start_chat(history=[])
if "messages" not in st.session_state:
    st.session_state.messages = []  # [(role, text)]

st.success("어떤 점이 불편하셨는지 알려주세요. 가능한 한 자세히 도와드릴게요.")

# --- 5) 과거 대화 표시 ---
for role, text in st.session_state.messages:
    with st.chat_message("ai" if role == "ai" else "user"):
        st.markdown(text)

# --- 6) 입력창 ---
user_msg = st.chat_input("불편/요청 사항을 입력하세요")
if user_msg:
    st.session_state.messages.append(("user", user_msg))
    with st.chat_message("user"):
        st.markdown(user_msg)

    with st.chat_message("ai"):
        with st.spinner("답변 생성 중..."):
            try:
                resp = st.session_state.chat.send_message(user_msg)
                bot_text = resp.text
                st.session_state.messages.append(("ai", bot_text))
                st.markdown(bot_text)
            except Exception as e:
                err = str(e)
                if "400" in err and "prompt" in err.lower():
                    st.error("요청 텍스트가 너무 깁니다(토큰 제한). 내용을 조금 줄여 주세요.")
                else:
                    st.error(f"오류가 발생했습니다: {e}")

# --- 7) 리셋 버튼 ---
cols = st.columns(2)
with cols[0]:
    if st.button("🧹 대화 초기화"):
        st.session_state.messages = []
        st.session_state.chat = model.start_chat(history=[])
        st.rerun()
with cols[1]:
    st.caption("TIP: 이메일 주소는 마지막에 꼭 남겨 주세요.")
