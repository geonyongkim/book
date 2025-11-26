import streamlit as st
import pandas as pd
import uuid
import requests
import urllib.parse
from PIL import Image, ImageEnhance
from pyzbar.pyzbar import decode
from datetime import datetime, timedelta
import plotly.express as px

# [Google Sheets 연동 라이브러리]
import gspread
from google.oauth2.service_account import Credentials

# =========================================================
# 🚨 [필수 설정] 아래 주소를 사용자님의 구글 시트 주소로 바꿔주세요!
# =========================================================
SHEET_URL = "https://docs.google.com/spreadsheets/d/1WyA_dM3_cxqurORJ1wbYACBFBgDG9-4b_wPk8nWbwhA/edit?gid=1353177291#gid=1353177291" 
# (브라우저 주소창에 있는 링크를 그대로 복사해서 위 따옴표 안에 넣으세요)

# --- [반응 옵션 정의] ---
REACTION_OPTIONS = ["선택 안 함", "😄 재미있어요", "😓 어려워요", "🎨 그림이 마음에 들어요", "🐣 스스로 읽을 수 있어요"]

# --- [함수 1] 구글 시트 연결 ---
@st.cache_resource
def get_google_sheet_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes
    )
    client = gspread.authorize(credentials)
    return client

# --- [함수 2] 데이터 로드 (URL로 접속) ---
def load_data():
    client = get_google_sheet_client()
    try:
        # [변경] 이름 대신 URL로 엽니다 (오류 해결의 핵심)
        sh = client.open_by_url(SHEET_URL)
    except gspread.exceptions.APIError:
        st.error("❌ 구글 시트를 열 수 없습니다. URL이 정확한지, 서비스 계정이 '편집자'로 초대되었는지 확인해주세요.")
        st.stop()
    except gspread.exceptions.NoValidUrlKeyFound:
        st.error("❌ URL 형식이 잘못되었습니다. 구글 시트 주소를 전체 복사해서 넣어주세요.")
        st.stop()

    # 1. Books 데이터 로드
    try:
        wks_books = sh.worksheet("books")
        data_books = wks_books.get_all_records()
        books_df = pd.DataFrame(data_books)
        
        required_cols = ['ID', '제목', 'ISBN', '레벨', '읽은횟수', '상태', '반응', '표지URL']
        if books_df.empty:
            books_df = pd.DataFrame(columns=required_cols)
        else:
            for col in required_cols:
                if col not in books_df.columns:
                    books_df[col] = ""
            # NaN 처리
            books_df['반응'] = books_df['반응'].replace("", "선택 안 함").fillna("선택 안 함")
            books_df['ISBN'] = books_df['ISBN'].astype(str)
            
    except gspread.exceptions.WorksheetNotFound:
        wks_books = sh.add_worksheet(title="books", rows=100, cols=10)
        wks_books.append_row(['ID', '제목', 'ISBN', '레벨', '읽은횟수', '상태', '반응', '표지URL'])
        books_df = pd.DataFrame(columns=['ID', '제목', 'ISBN', '레벨', '읽은횟수', '상태', '반응', '표지URL'])

    # 2. Logs 데이터 로드
    try:
        wks_logs = sh.worksheet("logs")
        data_logs = wks_logs.get_all_records()
        logs_df = pd.DataFrame(data_logs)
        
        if logs_df.empty:
            logs_df = pd.DataFrame(columns=['날짜', '책ID', '제목', '레벨'])
        else:
            logs_df['날짜'] = pd.to_datetime(logs_df['날짜'])
            
    except gspread.exceptions.WorksheetNotFound:
        wks_logs = sh.add_worksheet(title="logs", rows=100, cols=5)
        wks_logs.append_row(['날짜', '책ID', '제목', '레벨'])
        logs_df = pd.DataFrame(columns=['날짜', '책ID', '제목', '레벨'])

    return books_df, logs_df

# --- [함수 3] 데이터 저장 (URL로 접속) ---
def save_books(df):
    client = get_google_sheet_client()
    sh = client.open_by_url(SHEET_URL) # [변경]
    wks = sh.worksheet("books")
    
    header = df.columns.values.tolist()
    data = df.fillna("").values.tolist()
    
    wks.clear()
    wks.update(range_name='A1', values=[header] + data)

# --- [함수 4] 로그 추가 (URL로 접속) ---
def add_log(book_id, title, level):
    client = get_google_sheet_client()
    sh = client.open_by_url(SHEET_URL) # [변경]
    wks = sh.worksheet("logs")
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    wks.append_row([today_str, str(book_id), str(title), int(level)])

# --- [함수 5] 바코드 스캔 ---
def scan_barcode(image_file):
    try:
        image = Image.open(image_file)
        attempts = [
            image.convert('L'), 
            image.convert('L').crop((image.size[0]*0.2, image.size[1]*0.2, image.size[0]*0.8, image.size[1]*0.8)),
            ImageEnhance.Sharpness(image.convert('L').crop((image.size[0]*0.35, image.size[1]*0.35, image.size[0]*0.65, image.size[1]*0.65))).enhance(2.0)
        ]
        for img in attempts:
            decoded = decode(img)
            for obj in decoded: return obj.data.decode("utf-8")
    except Exception: pass
    return None

# --- [함수 6] 도서 검색 ---
def search_book_info(isbn):
    if not isbn: return None, None
    clean_isbn = str(isbn).strip().replace("-", "").replace(" ", "")
    try:
        r = requests.get(f"https://www.googleapis.com/books/v1/volumes?q=isbn:{clean_isbn}").json()
        if "items" in r:
            return r["items"][0]["volumeInfo"].get("title", ""), r["items"][0]["volumeInfo"].get("imageLinks", {}).get("thumbnail", "")
    except: pass
    try:
        r = requests.get(f"https://openlibrary.org/api/books?bibkeys=ISBN:{clean_isbn}&jscmd=data&format=json").json()
        if f"ISBN:{clean_isbn}" in r:
            bk = r[f"ISBN:{clean_isbn}"]
            cv = bk.get("cover", {})
            return bk.get("title", ""), (cv.get("medium") or cv.get("large") or cv.get("small", ""))
    except: pass
    return None, None

# =========================================================
# 메인 UI
# =========================================================

st.set_page_config(page_title="아이 영어 독서 매니저 (Cloud)", layout="wide", page_icon="☁️")

# 데이터 로드
with st.spinner("구글 시트와 연결 중..."):
    books_df, logs_df = load_data()

st.title("📚 Smart English Library v3.1")
st.caption("구글 스프레드시트와 실시간 연동됩니다.")

tab1, tab2, tab3 = st.tabs(["📊 상세 대시보드", "📖 서재 관리", "➕ 새 책 등록"])

# --- [탭 1] 상세 대시보드 ---
with tab1:
    st.markdown("### 📈 독서 현황 브리핑")
    if logs_df.empty and books_df.empty:
        st.info("데이터가 없습니다. 책을 등록해주세요.")
    else:
        today = pd.Timestamp.now().normalize()
        this_month_start = today.replace(day=1)
        
        daily_reads = logs_df[logs_df['날짜'] == today]
        month_reads = logs_df[logs_df['날짜'] >= this_month_start]
        
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("총 보유 도서", f"{len(books_df)}권")
        kpi2.metric("총 누적 읽기", f"{len(logs_df)}회")
        kpi3.metric("이번 달 독서", f"{len(month_reads)}회")
        kpi4.metric("오늘 읽은 책", f"{len(daily_reads)}권")
        st.divider()
        
        c1, c2 = st.columns([1, 1])
        with c1:
            st.subheader("🗓️ 최근 30일 독서")
            if not logs_df.empty:
                last_30 = logs_df[logs_df['날짜'] >= (today - timedelta(days=29))]
                daily_counts = last_30.groupby('날짜').size().reset_index(name='권수')
                fig = px.bar(daily_counts, x='날짜', y='권수', text_auto=True, color_discrete_sequence=['#4C78A8'])
                st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.subheader("🧸 아이 반응")
            if not books_df.empty:
                reaction_counts = books_df[books_df['반응'] != '선택 안 함']['반응'].value_counts().reset_index()
                reaction_counts.columns = ['반응', '권수']
                if not reaction_counts.empty:
                    fig2 = px.pie(reaction_counts, values='권수', names='반응', hole=0.4)
                    st.plotly_chart(fig2, use_container_width=True)
        st.divider()

        r1, r2 = st.columns(2)
        with r1:
            st.subheader("🏆 Top 5 읽은 책")
            if not books_df.empty:
                books_df['읽은횟수'] = pd.to_numeric(books_df['읽은횟수'], errors='coerce').fillna(0)
                top_books = books_df.sort_values(by='읽은횟수', ascending=False).head(5)
                for idx, row in top_books.iterrows():
                    st.write(f"**{int(row['읽은횟수'])}회** | {row['제목']} (Lv.{row['레벨']})")
        with r2:
            st.subheader("📚 레벨별 보유")
            if not books_df.empty:
                lvl_counts = books_df['레벨'].value_counts().sort_index()
                st.bar_chart(lvl_counts)

# --- [탭 2] 서재 관리 ---
with tab2:
    c_head, c_sort = st.columns([3, 2])
    with c_head: st.subheader("보유 도서 관리")
    with c_sort:
        sort_option = st.selectbox("정렬", ["최신 등록순", "자주 읽은 책", "안 읽은 책", "아이 반응별", "레벨 높은 순"])

    if not books_df.empty:
        books_df['읽은횟수'] = pd.to_numeric(books_df['읽은횟수'], errors='coerce').fillna(0)
        books_df['레벨'] = pd.to_numeric(books_df['레벨'], errors='coerce').fillna(1)
        display_df = books_df.copy()
        
        if sort_option == "최신 등록순": display_df = display_df.iloc[::-1]
        elif sort_option == "자주 읽은 책": display_df = display_df.sort_values(by='읽은횟수', ascending=False)
        elif sort_option == "안 읽은 책": display_df = display_df.sort_values(by='읽은횟수', ascending=True)
        elif sort_option == "아이 반응별": display_df = display_df.sort_values(by='반응', ascending=False)
        elif sort_option == "레벨 높은 순": display_df = display_df.sort_values(by='레벨', ascending=False)

        st.caption(f"총 {len(display_df)}권")

        for i, row in display_df.iterrows():
            with st.container():
                c1, c2 = st.columns([1, 5])
                with c1: st.image(row['표지URL'] if pd.notna(row['표지URL']) and str(row['표지URL']).startswith("http") else "https://via.placeholder.com/150", width=80)
                with c2:
                    st.markdown(f"#### **{row['제목']}**")
                    st.text(f"ISBN: {row['ISBN']}")

                    ec1, ec2, ec3 = st.columns([1, 1.2, 2.5])
                    real_idx = books_df[books_df['ID'] == row['ID']].index[0]

                    with ec1: new_lvl = st.selectbox("레벨", [1,2,3,4,5], index=int(row['레벨'])-1, key=f"l_{row['ID']}", label_visibility="collapsed")
                    with ec2: 
                        s_idx = ["읽지 않음", "읽는 중", "완독"].index(row['상태']) if row['상태'] in ["읽지 않음", "읽는 중", "완독"] else 0
                        new_sts = st.selectbox("상태", ["읽지 않음", "읽는 중", "완독"], index=s_idx, key=f"s_{row['ID']}", label_visibility="collapsed")
                    with ec3:
                        r_idx = REACTION_OPTIONS.index(row['반응']) if row['반응'] in REACTION_OPTIONS else 0
                        new_react = st.selectbox("반응", REACTION_OPTIONS, index=r_idx, key=f"r_{row['ID']}", label_visibility="collapsed")

                    if new_lvl != row['레벨'] or new_sts != row['상태'] or new_react != row['반응']:
                        with st.spinner("저장 중..."):
                            books_df.at[real_idx, '레벨'] = new_lvl
                            books_df.at[real_idx, '상태'] = new_sts
                            books_df.at[real_idx, '반응'] = new_react
                            save_books(books_df)
                        st.toast(f"✅ 수정 완료")
                        st.rerun()

                    search_query = f"{row['제목']} read a loud"
                    youtube_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(search_query)}"

                    b1, b2, b3 = st.columns([1.2, 1.2, 1])
                    if b1.button(f"➕ 읽기 추가 ({int(row['읽은횟수'])})", key=f"btn_r_{row['ID']}"):
                        with st.spinner("기록 중..."):
                            books_df.at[real_idx, '읽은횟수'] += 1
                            if books_df.at[real_idx, '상태'] == '읽지 않음': books_df.at[real_idx, '상태'] = '읽는 중'
                            save_books(books_df)
                            add_log(row['ID'], row['제목'], new_lvl)
                        st.toast("📖 기록 완료")
                        st.rerun()
                    with b2: st.link_button("🎧 오디오 찾기", youtube_url)
                    if b3.button("🗑 삭제", key=f"btn_d_{row['ID']}"):
                        if st.session_state.get(f"del_{row['ID']}"):
                             with st.spinner("삭제 중..."):
                                books_df = books_df.drop(real_idx)
                                save_books(books_df)
                             st.rerun()
                        else:
                             st.session_state[f"del_{row['ID']}"] = True
                             st.warning("삭제 확인")
                st.divider()
    else: st.info("등록된 책 없음")

# --- [탭 3] 새 책 등록 ---
with tab3:
    st.subheader("새 책 입고")
    if 'auto_title' not in st.session_state: st.session_state.update({'auto_title':"", 'auto_isbn':"", 'auto_img':"", 'search_done':False})

    input_method = st.radio("입력 방식", ["📸 바코드 스캔", "📂 사진 업로드", "✍️ 수동 입력"], horizontal=True)
    
    img_file = None 
    if input_method == "📸 바코드 스캔": img_file = st.camera_input("바코드 촬영")
    elif input_method == "📂 사진 업로드": img_file = st.file_uploader("사진 선택", type=['png', 'jpg', 'jpeg'])

    if img_file and not st.session_state.get('search_done'):
        isbn_val = scan_barcode(img_file)
        if isbn_val:
            st.toast(f"인식 성공: {isbn_val}")
            if st.session_state['auto_isbn'] != isbn_val:
                with st.spinner("검색 중..."):
                    t, i = search_book_info(isbn_val)
                    st.session_state.update({'auto_isbn': isbn_val, 'auto_title': t or "", 'auto_img': i or "", 'search_done': True})
                    st.rerun()
        else: st.error("인식 실패")

    if input_method == "✍️ 수동 입력":
        manual_isbn = st.text_input("ISBN 입력", value=st.session_state['auto_isbn'])
        if manual_isbn and manual_isbn != st.session_state.get('last_manual', ''):
             with st.spinner("검색 중..."):
                t, i = search_book_info(manual_isbn)
                st.session_state.update({'auto_isbn': manual_isbn, 'auto_title': t or "", 'auto_img': i or "", 'last_manual': manual_isbn})
                st.rerun()
    st.divider()

    with st.form("reg_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            title = st.text_input("제목", value=st.session_state['auto_title'])
            isbn = st.text_input("ISBN", value=st.session_state['auto_isbn'])
            level = st.selectbox("레벨", [1,2,3,4,5])
        with c2:
            img_url = st.text_input("표지 URL", value=st.session_state['auto_img'])
            status = st.selectbox("상태", ["읽지 않음", "읽는 중", "완독"])
            reaction = st.selectbox("반응", REACTION_OPTIONS)
            
        if st.form_submit_button("등록하기"):
            if not title: st.error("제목 필수")
            else:
                with st.spinner("저장 중..."):
                    new_data = {'ID': str(uuid.uuid4()), '제목': title, 'ISBN': isbn, '레벨': level, '읽은횟수': 0, '상태': status, '반응': reaction, '표지URL': img_url}
                    books_df = pd.concat([books_df, pd.DataFrame([new_data])], ignore_index=True)
                    save_books(books_df)
                    for key in ['auto_title', 'auto_isbn', 'auto_img', 'search_done', 'last_manual']:
                        if key in st.session_state: del st.session_state[key]
                st.success("완료!")
                st.rerun()
