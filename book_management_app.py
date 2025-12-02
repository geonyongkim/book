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
# 🚨 [필수 설정] 사용자의 구글 시트 주소 (유지)
# =========================================================
SHEET_URL = "https://docs.google.com/spreadsheets/d/1WyA_dM3_cxqurORJ1wbYACBFBgDG9-4b_wPk8nWbwhA/edit?gid=1353177291#gid=1353177291"

# --- [별점 옵션 정의] ---
STAR_OPTIONS = ["선택 안 함", "⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"]

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

# --- [함수 2] 데이터 로드 ---
def load_data():
    client = get_google_sheet_client()
    try:
        sh = client.open_by_url(SHEET_URL)
    except Exception as e:
        st.error(f"구글 시트 연결 오류: {e}")
        st.stop()

    # 1. Books 데이터
    try:
        wks_books = sh.worksheet("books")
        data_books = wks_books.get_all_records()
        books_df = pd.DataFrame(data_books)
        
        required_cols = [
            'ID', '제목', 'ISBN', '레벨', '상태', '표지URL', '음원URL',
            '횟수_첫째', '횟수_둘째', 
            '반응_첫째', '반응_둘째', 
            '메모_첫째', '메모_둘째'
        ]
        
        if books_df.empty:
            books_df = pd.DataFrame(columns=required_cols)
        else:
            for col in required_cols:
                if col not in books_df.columns: books_df[col] = ""
            for col in ['반응_첫째', '반응_둘째']:
                books_df[col] = books_df[col].replace("", "선택 안 함").fillna("선택 안 함")
            for col in ['횟수_첫째', '횟수_둘째']:
                books_df[col] = pd.to_numeric(books_df[col], errors='coerce').fillna(0)
            for col in ['ID', 'ISBN', '표지URL', '음원URL', '메모_첫째', '메모_둘째']:
                books_df[col] = books_df[col].astype(str)
            
    except gspread.exceptions.WorksheetNotFound:
        wks_books = sh.add_worksheet(title="books", rows=100, cols=20)
        wks_books.append_row([
            'ID', '제목', 'ISBN', '레벨', '상태', '표지URL', '음원URL',
            '횟수_첫째', '횟수_둘째', 
            '반응_첫째', '반응_둘째', 
            '메모_첫째', '메모_둘째'
        ])
        books_df = pd.DataFrame(columns=[
            'ID', '제목', 'ISBN', '레벨', '상태', '표지URL', '음원URL',
            '횟수_첫째', '횟수_둘째', 
            '반응_첫째', '반응_둘째', 
            '메모_첫째', '메모_둘째'
        ])

    # 2. Logs 데이터
    try:
        wks_logs = sh.worksheet("logs")
        data_logs = wks_logs.get_all_records()
        logs_df = pd.DataFrame(data_logs)
        
        required_log_cols = ['날짜', '책ID', '제목', '레벨', '누가']
        for col in required_log_cols:
            if col not in logs_df.columns: logs_df[col] = ""

        if logs_df.empty:
            logs_df = pd.DataFrame(columns=required_log_cols)
        else:
            logs_df['날짜'] = pd.to_datetime(logs_df['날짜'], errors='coerce')
            
    except gspread.exceptions.WorksheetNotFound:
        wks_logs = sh.add_worksheet(title="logs", rows=100, cols=6)
        wks_logs.append_row(['날짜', '책ID', '제목', '레벨', '누가'])
        logs_df = pd.DataFrame(columns=['날짜', '책ID', '제목', '레벨', '누가'])

    # 3. Board 데이터
    try:
        wks_board = sh.worksheet("board")
        data_board = wks_board.get_all_records()
        board_df = pd.DataFrame(data_board)
        
        if 'ID' not in board_df.columns:
            board_df['ID'] = [str(uuid.uuid4()) for _ in range(len(board_df))]
        
        if '날짜' not in board_df.columns: board_df['날짜'] = ""
        if '내용' not in board_df.columns: board_df['내용'] = ""
            
        if board_df.empty:
             board_df = pd.DataFrame(columns=['ID', '날짜', '내용'])
        else:
            board_df['ID'] = board_df['ID'].astype(str)
             
    except gspread.exceptions.WorksheetNotFound:
        wks_board = sh.add_worksheet(title="board", rows=100, cols=3)
        wks_board.append_row(['ID', '날짜', '내용'])
        board_df = pd.DataFrame(columns=['ID', '날짜', '내용'])

    return books_df, logs_df, board_df

# --- [함수 3] 데이터 저장 (책) ---
def save_books(df):
    client = get_google_sheet_client()
    sh = client.open_by_url(SHEET_URL)
    wks = sh.worksheet("books")
    
    save_cols = [
        'ID', '제목', 'ISBN', '레벨', '상태', '표지URL', '음원URL',
        '횟수_첫째', '횟수_둘째', 
        '반응_첫째', '반응_둘째', 
        '메모_첫째', '메모_둘째'
    ]
    for col in save_cols:
        if col not in df.columns: df[col] = ""
            
    df_tosave = df[save_cols].copy()
    header = df_tosave.columns.values.tolist()
    data = df_tosave.fillna("").values.tolist()
    
    wks.clear()
    wks.update(range_name='A1', values=[header] + data)

# --- [함수 4] 데이터 저장 (게시판) ---
def save_board(df):
    client = get_google_sheet_client()
    sh = client.open_by_url(SHEET_URL)
    wks = sh.worksheet("board")
    
    save_cols = ['ID', '날짜', '내용']
    for col in save_cols:
        if col not in df.columns: df[col] = ""
            
    df_tosave = df[save_cols].copy()
    header = df_tosave.columns.values.tolist()
    data = df_tosave.fillna("").values.tolist()
    
    wks.clear()
    wks.update(range_name='A1', values=[header] + data)

# --- [함수 5] 로그 추가 ---
def add_log(book_id, title, level, who):
    client = get_google_sheet_client()
    sh = client.open_by_url(SHEET_URL)
    wks = sh.worksheet("logs")
    today_str = datetime.now().strftime("%Y-%m-%d")
    wks.append_row([today_str, str(book_id), str(title), int(level), str(who)])

# --- [함수 6] 통합 스캔 ---
def scan_code(image_file):
    try:
        image = Image.open(image_file)
        attempts = [image, image.convert('L'), ImageEnhance.Contrast(image.convert('L')).enhance(2.0)]
        for img in attempts:
            decoded = decode(img)
            for obj in decoded: return obj.data.decode("utf-8")
    except Exception: pass
    return None

# --- [함수 7] 도서 검색 ---
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

st.set_page_config(page_title="아이 영어 독서 매니저 (Final)", layout="wide", page_icon="🧸")

with st.spinner("데이터 로딩 중..."):
    books_df, logs_df, board_df = load_data()

st.title("📚 Smart English Library v5.2")
st.caption("안정적인 게시판 | 직관적인 카드형 UI")

tab1, tab2, tab3, tab4 = st.tabs(["📊 대시보드", "📖 서재 관리", "➕ 새 책 등록", "📌 교육 정보 게시판"])

# --- [탭 1] 대시보드 ---
with tab1:
    st.markdown("### 📈 독서 통계")
    if books_df.empty:
        st.info("데이터가 없습니다.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("총 보유 도서", f"{len(books_df)}권")
        c2.metric("누적 읽은 횟수", f"{len(logs_df)}회")
        
        count_1 = int(books_df['횟수_첫째'].sum())
        count_2 = int(books_df['횟수_둘째'].sum())
        c3.metric("👦 첫째 독서", f"{count_1}회")
        c4.metric("👧 둘째 독서", f"{count_2}회")

        st.divider()
        col_chart1, col_chart2 = st.columns([2, 1])
        with col_chart1:
            st.subheader("🗓️ 월간 독서 추이")
            if not logs_df.empty:
                daily_counts = logs_df.groupby(['날짜', '누가']).size().reset_index(name='권수')
                fig = px.bar(daily_counts, x='날짜', y='권수', color='누가', barmode='group')
                st.plotly_chart(fig, use_container_width=True)
        with col_chart2:
            st.subheader("⭐ 별점 현황")
            target = st.radio("누구?", ["첫째", "둘째"], horizontal=True)
            col = '반응_첫째' if target == "첫째" else '반응_둘째'
            if not books_df.empty:
                r_data = books_df[books_df[col] != '선택 안 함'][col].value_counts().reset_index()
                r_data.columns = ['별점', '권수']
                if not r_data.empty: st.plotly_chart(px.pie(r_data, values='권수', names='별점', hole=0.4), use_container_width=True)

# --- [탭 2] 서재 관리 ---
with tab2:
    c_head, c_sort = st.columns([3, 2])
    with c_head: st.subheader("보유 도서 목록")
    with c_sort:
        sort_option = st.selectbox("정렬 기준", ["최신 등록순", "첫째 많이 읽은 책", "둘째 많이 읽은 책", "레벨 높은 순"])

    if not books_df.empty:
        display_df = books_df.copy()
        display_df['횟수_첫째'] = pd.to_numeric(display_df['횟수_첫째'], errors='coerce').fillna(0)
        display_df['횟수_둘째'] = pd.to_numeric(display_df['횟수_둘째'], errors='coerce').fillna(0)
        
        if sort_option == "최신 등록순": display_df = display_df.iloc[::-1]
        elif sort_option == "첫째 많이 읽은 책": display_df = display_df.sort_values(by='횟수_첫째', ascending=False)
        elif sort_option == "둘째 많이 읽은 책": display_df = display_df.sort_values(by='횟수_둘째', ascending=False)
        elif sort_option == "레벨 높은 순": display_df = display_df.sort_values(by='레벨', ascending=False)

        st.caption(f"총 {len(display_df)}권")

        for i, row in display_df.iterrows():
            with st.container(border=True): # 카드형 UI 적용
                c1, c2 = st.columns([1, 4])
                
                with c1:
                    img_url = row['표지URL'] if pd.notna(row['표지URL']) and str(row['표지URL']).startswith("http") else "https://via.placeholder.com/150?text=No+Image"
                    st.image(img_url, width=90)
                    
                    audio_url = str(row.get('음원URL', '')).strip()
                    if audio_url.startswith("http"):
                        st.link_button("🎧 음원 듣기", audio_url, use_container_width=True)
                    
                    search_query = f"{row['제목']} read a loud"
                    yt_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(search_query)}"
                    st.link_button("▶️ Read Aloud", yt_url, use_container_width=True)

                with c2:
                    # 제목 및 기본 정보
                    st.markdown(f"### {row['제목']}")
                    st.caption(f"ISBN: {row['ISBN']} | Lv.{row['레벨']}")
                    
                    # 읽기 카운트 버튼
                    b_read1, b_read2 = st.columns(2)
                    if b_read1.button(f"👦 첫째 읽기 (현재 {int(row['횟수_첫째'])}회)", key=f"r1_{row['ID']}", use_container_width=True):
                        idx = books_df[books_df['ID'] == row['ID']].index[0]
                        books_df.at[idx, '횟수_첫째'] += 1
                        save_books(books_df)
                        add_log(row['ID'], row['제목'], row['레벨'], "첫째")
                        st.toast("👦 첫째 기록 완료!")
                        st.rerun()
                        
                    if b_read2.button(f"👧 둘째 읽기 (현재 {int(row['횟수_둘째'])}회)", key=f"r2_{row['ID']}", use_container_width=True):
                        idx = books_df[books_df['ID'] == row['ID']].index[0]
                        books_df.at[idx, '횟수_둘째'] += 1
                        save_books(books_df)
                        add_log(row['ID'], row['제목'], row['레벨'], "둘째")
                        st.toast("👧 둘째 기록 완료!")
                        st.rerun()

                    # 수정 모드 (Expander)
                    with st.expander("✏️ 수정 / 별점 / 메모"):
                        t_edit, l_edit, s_edit = st.columns([2, 1, 1])
                        new_title = t_edit.text_input("제목 수정", value=row['제목'], key=f"tt_{row['ID']}")
                        new_lvl = l_edit.selectbox("레벨", [1,2,3,4,5], index=int(row['레벨'])-1, key=f"lv_{row['ID']}")
                        new_sts = s_edit.selectbox("상태", ["읽지 않음", "읽는 중", "완독"], index=["읽지 않음", "읽는 중", "완독"].index(row['상태']) if row['상태'] in ["읽지 않음", "읽는 중", "완독"] else 0, key=f"st_{row['ID']}")

                        new_img = st.text_input("표지 URL", value=row['표지URL'], key=f"url_{row['ID']}")
                        new_aud = st.text_input("음원 URL", value=row.get('음원URL', ''), key=f"aud_{row['ID']}")

                        st.markdown("---")
                        k1, k2 = st.columns(2)
                        with k1:
                            st.caption("👦 첫째 기록")
                            cr1 = row.get('반응_첫째', '선택 안 함')
                            nr1 = st.selectbox("별점", STAR_OPTIONS, index=STAR_OPTIONS.index(cr1) if cr1 in STAR_OPTIONS else 0, key=f"s1_{row['ID']}")
                            nm1 = st.text_area("메모", value=row.get('메모_첫째', ''), key=f"m1_{row['ID']}", height=60)
                        with k2:
                            st.caption("👧 둘째 기록")
                            cr2 = row.get('반응_둘째', '선택 안 함')
                            nr2 = st.selectbox("별점", STAR_OPTIONS, index=STAR_OPTIONS.index(cr2) if cr2 in STAR_OPTIONS else 0, key=f"s2_{row['ID']}")
                            nm2 = st.text_area("메모", value=row.get('메모_둘째', ''), key=f"m2_{row['ID']}", height=60)

                        bs1, bs2 = st.columns([1, 4])
                        if bs1.button("저장", key=f"sv_{row['ID']}"):
                            idx = books_df[books_df['ID'] == row['ID']].index[0]
                            books_df.at[idx, '제목'] = new_title
                            books_df.at[idx, '레벨'] = new_lvl
                            books_df.at[idx, '상태'] = new_sts
                            books_df.at[idx, '표지URL'] = new_img
                            books_df.at[idx, '음원URL'] = new_aud
                            books_df.at[idx, '반응_첫째'] = nr1
                            books_df.at[idx, '반응_둘째'] = nr2
                            books_df.at[idx, '메모_첫째'] = nm1
                            books_df.at[idx, '메모_둘째'] = nm2
                            save_books(books_df)
                            st.toast("저장 완료")
                            st.rerun()

                        if bs2.button("삭제", key=f"del_{row['ID']}"):
                            if st.session_state.get(f"ck_{row['ID']}"):
                                idx = books_df[books_df['ID'] == row['ID']].index[0]
                                books_df = books_df.drop(idx)
                                save_books(books_df)
                                st.rerun()
                            else:
                                st.session_state[f"ck_{row['ID']}"] = True
                                st.warning("삭제 확인 (한 번 더 클릭)")

# --- [탭 3] 새 책 등록 ---
with tab3:
    st.subheader("새 책 등록")
    # 세션 초기화
    if 'reg_title' not in st.session_state: 
        st.session_state.update({'reg_title':"", 'reg_isbn':"", 'reg_img':"", 'reg_audio':"", 'search_done':False})

    # 입력 방식 선택
    m = st.radio("입력 방식", ["📸 바코드 촬영", "🖼️ 갤러리 업로드", "✍️ 수동 입력"], horizontal=True, label_visibility="collapsed")
    
    img_f = None
    if m == "📸 바코드 촬영": img_f = st.camera_input("바코드", key="c_reg")
    elif m == "🖼️ 갤러리 업로드": img_f = st.file_uploader("바코드 사진", type=['jpg','png'])

    if img_f and not st.session_state['search_done']:
        c = scan_code(img_f)
        if c:
            st.toast("인식 성공")
            if st.session_state['reg_isbn'] != c:
                with st.spinner("검색 중..."):
                    t, i = search_book_info(c)
                    st.session_state.update({'reg_isbn': c, 'reg_title': t or "", 'reg_img': i or "", 'search_done': True})
                    st.rerun()

    if m == "✍️ 수동 입력":
        man = st.text_input("ISBN 입력", value=st.session_state['reg_isbn'])
        if man and man != st.session_state.get('last_m', ''):
             with st.spinner("검색..."):
                t, i = search_book_info(man)
                st.session_state.update({'reg_isbn': man, 'reg_title': t or "", 'reg_img': i or "", 'last_m': man})
                st.rerun()

    st.divider()
    with st.form("nb_form"):
        c1, c2 = st.columns(2)
        with c1:
            title = st.text_input("제목 *", value=st.session_state['reg_title'])
            isbn = st.text_input("ISBN", value=st.session_state['reg_isbn'])
            level = st.selectbox("레벨", [1,2,3,4,5])
        with c2:
            img_url = st.text_input("표지 URL", value=st.session_state['reg_img'])
            aud_url = st.text_input("음원 URL", value=st.session_state['reg_audio'])
        
        st.markdown("##### 초기 반응 (선택)")
        k1, k2 = st.columns(2)
        r1 = k1.selectbox("첫째 별점", STAR_OPTIONS)
        r2 = k2.selectbox("둘째 별점", STAR_OPTIONS)

        if st.form_submit_button("등록하기"):
            if not title: st.error("제목 필수")
            else:
                new_data = {
                    'ID': str(uuid.uuid4()), '제목': title, 'ISBN': isbn, '레벨': level, '상태': '읽지 않음',
                    '표지URL': img_url, '음원URL': aud_url,
                    '횟수_첫째': 0, '횟수_둘째': 0, '반응_첫째': r1, '반응_둘째': r2, '메모_첫째': "", '메모_둘째': ""
                }
                books_df = pd.concat([books_df, pd.DataFrame([new_data])], ignore_index=True)
                save_books(books_df)
                for k in ['reg_title', 'reg_isbn', 'reg_img', 'reg_audio', 'search_done', 'last_m']:
                    if k in st.session_state: del st.session_state[k]
                st.success("등록 완료")
                st.rerun()

    st.caption("Tip: 음원 QR은 등록 후 서재 관리에서 추가할 수 있습니다.")

# --- [탭 4] 교육 정보 게시판 (리뉴얼: 카드형 UI + 즉시 수정) ---
with tab4:
    st.header("📌 정보 게시판")
    st.caption("자유롭게 메모를 남기세요.")

    # 1. 새 글 작성 (상단 배치)
    with st.form("new_post", clear_on_submit=True):
        content = st.text_area("새로운 메모 작성", height=70, placeholder="내용을 입력하세요...")
        if st.form_submit_button("등록"):
            if content:
                new_row = {'ID': str(uuid.uuid4()), '날짜': datetime.now().strftime("%Y-%m-%d %H:%M"), '내용': content}
                board_df = pd.concat([board_df, pd.DataFrame([new_row])], ignore_index=True)
                save_board(board_df)
                st.success("등록됨")
                st.rerun()

    st.divider()

    # 2. 게시글 리스트 (카드형 UI + 수정 모드 전환)
    if not board_df.empty:
        # 'editing_id' 세션 상태 관리 (현재 수정 중인 글 ID)
        if 'editing_id' not in st.session_state: st.session_state['editing_id'] = None

        # 최신순 출력
        for i, row in board_df.iloc[::-1].iterrows():
            # 카드 박스
            with st.container(border=True):
                # [수정 모드]
                if st.session_state['editing_id'] == row['ID']:
                    edit_txt = st.text_area("내용 수정", value=row['내용'], key=f"txt_{row['ID']}", height=100)
                    b1, b2 = st.columns([1, 1])
                    if b1.button("완료", key=f"sav_{row['ID']}", use_container_width=True):
                        idx = board_df[board_df['ID'] == row['ID']].index[0]
                        board_df.at[idx, '내용'] = edit_txt
                        save_board(board_df)
                        st.session_state['editing_id'] = None # 수정 종료
                        st.rerun()
                    if b2.button("취소", key=f"cnl_{row['ID']}", use_container_width=True):
                        st.session_state['editing_id'] = None # 수정 취소
                        st.rerun()

                # [일반 모드]
                else:
                    st.markdown(f"**📅 {row['날짜']}**")
                    st.write(row['내용'])
                    
                    b1, b2 = st.columns([1, 1])
                    # 수정 버튼 -> 세션 상태 변경 -> 리런 -> 위쪽 [수정 모드] 진입
                    if b1.button("✏️ 수정", key=f"edt_{row['ID']}", use_container_width=True):
                        st.session_state['editing_id'] = row['ID']
                        st.rerun()
                    
                    # 삭제 버튼
                    if b2.button("🗑 삭제", key=f"del_{row['ID']}", use_container_width=True):
                        # 삭제 전 확인 (간단하게 session 없이 즉시 삭제 + 토스트)
                        # 실수 방지를 위해 간단한 confirm 로직 추가 가능하지만 UI 간결성을 위해 즉시 삭제 처리함
                        idx = board_df[board_df['ID'] == row['ID']].index[0]
                        board_df = board_df.drop(idx)
                        save_board(board_df)
                        st.toast("삭제되었습니다.")
                        st.rerun()
    else:
        st.info("작성된 메모가 없습니다.")
