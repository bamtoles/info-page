import streamlit as st
import google.generativeai as genai
import os, re, time, uuid, csv, datetime
from pathlib import Path

st.set_page_config(page_title="고객 응대 챗봇", page_icon="🛍️")
st.title("고객 응대 챗봇 (Gemini + Streamlit)")
st.caption("정중 응대 · 불편 수집 · 담당자 전달 · 이메일 수집")

# -----------------------------
# 0) 공통 유틸
# -----------------------------
def today_str():
    return datetime.datetime.now().strftime("%Y-%m-%d")

def now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")

# 세션 ID (한 번 생성 후 유지)
if "session_id" not in st.session_state:
    st.session_state.session_id = uuid.uuid4().hex[:10]

# -----------------------------
# 1) API 키
# -----------------------------
API_KEY = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    with st.expander("🔐 GEMINI_API_KEY가 없나요? 여기를 눌러 임시 입력"):
        API_KEY = st.text_input("Gemini API 키", type="password")
    if not API_KEY:
        st.error("GEMINI_API_KEY가 설정되지 않았습니다. Streamlit Cloud Secrets에 추가하세요.")
        st.stop()

genai.configure(api_key=API_KEY)
st.sidebar.write(f"google-generativeai 버전: **{genai.__version__}**")

# -----------------------------
# 2) 사용가능 모델 조회 + 기본값을 2.0-flash로
# -----------------------------
try:
    raw_models = list(genai.list_models())
    avail = [m for m in raw_models if "generateContent" in getattr(m, "supported_generation_methods", [])]
    names = [m.name.replace("models/", "") for m in avail]
except Exception as e:
    st.error(f"모델 목록 조회 실패: {e}")
    st.stop()

# 실습에선 2.0/2.5 중 '비-실험(-exp 없는)' 모델만 사용
def is_safe(n: str) -> bool:
    if "-exp" in n:     # 실험 모델 제외
        return False
    return bool(re.match(r"^gemini-(2\.0|2\.5)-", n))

safe = [n for n in names if is_safe(n)]

# 선호 순서: 2.0-flash → 2.5-flash → 2.0-pro → 2.5-pro
PREF = ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.0-pro", "gemini-2.5-pro"]

def pick_default():
    # 1) 선호 목록에서 첫 매칭
    for want in PREF:
        if want in safe:
            return want
    # 2) 그래도 없으면 safe의 첫 번째나 names 첫 번째
    return safe[0] if safe else (names[0] if names else None)

default_model = pick_default()
if not default_model:
    st.error("사용 가능한 generateContent 모델을 찾지 못했습니다. 키/권한/리전을 확인하세요.")
    st.stop()

# 사이드바: 모델 선택(기본값을 gemini-2.0-flash로 세팅)
opts = safe if safe else names
default_index = opts.index(default_model)
model_name = st.sidebar.selectbox("사용할 모델", options=opts, index=default_index)

# -----------------------------
# 3) 시스템 프롬프트
# -----------------------------
SYSTEM_PROMPT = """
당신은 아래 기준에 따라 답변하는 고객 응대용 AI 챗봇입니다.

--- [참고 기준 시작] ---
1) 사용자는 쇼핑몰 구매 과정에서 겪은 불편/불만을 언급합니다. 정중하고 공감 어린 말투로 응답하세요.
2) 사용자의 불편 사항을 구체적으로 정리하여(무엇이/언제/어디서/어떻게) 수집하고, 이를 고객 응대 담당자에게 전달한다는 취지로 안내하세요.
3) 마지막에는 담당자 확인 후 회신을 위해 이메일 주소를 요청하세요.
   - 사용자가 연락 제공을 원치 않으면:
     "죄송하지만, 연락처 정보를 받지 못하여 담당자의 검토 내용을 받으실 수 없어요."라고 정중히 고지하세요.
--- [참고 기준 끝] ---

추측하거나 사실이 아닌 내용은 말하지 마세요.
"""

# -----------------------------
# 4) 모델/세션 초기화
# -----------------------------
@st.cache_resource(show_spinner=False)
def get_model(name: str):
    return genai.GenerativeModel(model_name=name, system_instruction=SYSTEM_PROMPT)

model = get_model(model_name)

if "chat" not in st.session_state:
    st.session_state.chat = model.start_chat(history=[])
if "messages" not in st.session_state:
    st.session_state.messages = []  # [(role, text)]

st.success(f"선택된 모델: **{model_name}**  | 세션ID: `{st.session_state.session_id}`")

# -----------------------------
# 5) 대화 자동 기록 옵션 (CSV)
# -----------------------------
st.sidebar.markdown("### 📝 자동 기록")
save_enabled = st.sidebar.checkbox("대화 자동 기록 (CSV)", value=False,
                                   help="체크하면 로그 폴더에 CSV로 자동 저장됩니다.")
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
log_path = log_dir / f"chat_{today_str()}.csv"

def append_log(role: str, text: str):
    if not save_enabled:
        return
    # CSV 헤더: ts, session_id, model, role, text
    new_file = not log_path.exists()
    with open(log_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["timestamp", "session_id", "model", "role", "text"])
        writer.writerow([now_iso(), st.session_state.session_id, model_name, role, text])

# 로그 파일 다운로드 버튼
if log_path.exists():
    with open(log_path, "rb") as f:
        st.sidebar.download_button("📥 오늘 로그 다운로드", f, file_name=log_path.name)

# -----------------------------
# 6) 이전 대화 표시
# -----------------------------
for role, text in st.session_state.messages:
    with st.chat_message("ai" if role == "ai" else "user"):
        st.markdown(text)

# -----------------------------
# 7) 안전하게 전송 (429 방어 포함)
# -----------------------------
def send_safely(msg: str):
    try:
        return st.session_state.chat.send_message(msg)
    except Exception as e:
        s = str(e)
        if "429" in s:
            # 최근 6턴만 유지하고 잠깐 대기 후 재시도
            trimmed = st.session_state.chat.history[-6:]
            st.session_state.chat = model.start_chat(history=trimmed)
            time.sleep(2)
            return st.session_state.chat.send_message(msg)
        raise

# -----------------------------
# 8) 입력/응답 & 자동 기록
# -----------------------------
if prompt := st.chat_input("불편/요청 사항을 입력하세요"):
    st.session_state.messages.append(("user", prompt))
    append_log("user", prompt)

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("ai"):
        with st.spinner("답변 생성 중..."):
            try:
                resp = send_safely(prompt)
                bot_text = resp.text
                st.markdown(bot_text)
                st.session_state.messages.append(("ai", bot_text))
                append_log("ai", bot_text)
            except Exception as e:
                st.error(f"오류: {e}")

# -----------------------------
# 9) 도구: 대화 초기화
# -----------------------------
cols = st.columns(2)
with cols[0]:
    if st.button("🧹 대화 초기화"):
        st.session_state.messages = []
        st.session_state.chat = model.start_chat(history=[])
        st.rerun()
with cols[1]:
    st.caption("TIP: 이메일 주소는 마지막에 꼭 남겨 주세요.")
