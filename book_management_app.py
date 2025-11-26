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

# --- [반응 옵션 정의] ---
REACTION_OPTIONS = ["선택 안 함", "😄 재미있어요", "😓 어려워요", "🎨 그림이 좋았어요", "🐣 스스로 읽었어요", "💤 관심 없어요"]

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

# --- [함수 2] 데이터 로드 (스키마 업데이트 포함) ---
def load_data():
    client = get_google_sheet_client()
    try:
        sh = client.open_by_url(SHEET_URL)
    except Exception as e:
        st.error(f"구글 시트 연결 오류: {e}")
        st.stop()

    # 1. Books 데이터 로드
    try:
        wks_books = sh.worksheet("books")
        data_books = wks_books.get_all_records()
        books_df = pd.DataFrame(data_books)
        
        # [변경] 새로운 컬럼 구조 정의 (음원URL, 아이별 반응, 메모 추가)
        required_cols = [
            'ID', '제목', 'ISBN', '레벨', '읽은횟수', '상태', 
            '반응_첫째', '반응_둘째', '반응_메모', '표지URL', '음원URL'
        ]
        
        if books_df.empty:
            books_df = pd.DataFrame(columns=required_cols)
        else:
            # 누락된 컬럼 자동 추가
            for col in required_cols:
                if col not in books_df.columns:
                    books_df[col] = ""
            
            # NaN 및 타입 처리
            for col in ['반응_첫째', '반응_둘째']:
                books_df[col] = books_df[col].replace("", "선택 안 함").fillna("선택 안 함")
            
            books_df['ISBN'] = books_df['ISBN'].astype(str)
            books_df['표지URL'] = books_df['표지URL'].astype(str)
            books_df['음원URL'] = books_df['음원URL'].astype(str)
            books_df['반응_메모'] = books_df['반응_메모'].astype(str)
            
    except gspread.exceptions.WorksheetNotFound:
        wks_books = sh.add_worksheet(title="books", rows=100, cols=15)
        # 초기 헤더 생성
        wks_books.append_row([
            'ID', '제목', 'ISBN', '레벨', '읽은횟수', '상태', 
            '반응_첫째', '반응_둘째', '반응_메모', '표지URL', '음원URL'
        ])
        books_df = pd.DataFrame(columns=[
            'ID', '제목', 'ISBN', '레벨', '읽은횟수', '상태', 
            '반응_첫째', '반응_둘째', '반응_메모', '표지URL', '음원URL'
        ])

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

# --- [함수 3] 데이터 저장 ---
def save_books(df):
    client = get_google_sheet_client()
    sh = client.open_by_url(SHEET_URL)
    wks = sh.worksheet("books")
    
    # 데이터프레임의 컬럼 순서를 보장 (표시 순서대로 저장)
    save_cols = [
        'ID', '제목', 'ISBN', '레벨', '읽은횟수', '상태', 
        '반응_첫째', '반응_둘째', '반응_메모', '표지URL', '음원URL'
    ]
    
    # 없는 컬럼은 빈 값으로 채움
    for col in save_cols:
        if col not in df.columns:
            df[col] = ""
            
    df_tosave = df[save_cols].copy()
    
    header = df_tosave.columns.values.tolist()
    data = df_tosave.fillna("").values.tolist()
    
    wks.clear()
    wks.update(range_name='A1', values=[header] + data)

# --- [함수 4] 로그 추가 ---
def add_log(book_id, title, level):
    client = get_google_sheet_client()
    sh = client.open_by_url(SHEET_URL)
    wks = sh.worksheet("logs")
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    wks.append_row([today_str, str(book_id), str(title), int(level)])

# --- [함수 5] 바코드/QR 스캔 (통합) ---
def scan_code(image_file):
    try:
        image = Image.open(image_file)
        # 이미지 보정 시도 (인식률 향상)
        attempts = [
            image,
            image.convert('L'), # 흑백
            ImageEnhance.Contrast(image.convert('L')).enhance(2.0) # 대비 강조
        ]
        
        for img in attempts:
            decoded = decode(img)
            for obj in decoded:
                return obj.data.decode("utf-8") # QR이든 바코드든 문자열 리턴
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

st.set_page_config(page_title="아이 영어 독서 매니저 (Pro)", layout="wide", page_icon="☁️")

# 데이터 로드
with st.spinner("구글 시트와 연결 중..."):
    books_df, logs_df = load_data()

st.title("📚 Smart English Library v4.0")
st.caption("구글 스프레드시트 연동 | QR 음원 지원 | 아이별 반응 기록")

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
            st.subheader("🧸 아이 반응 (첫째 vs 둘째)")
            # 첫째, 둘째 반응 비교
            if not books_df.empty:
                # 탭으로 구분하여 보여주기
                sub_t1, sub_t2 = st.tabs(["첫째 반응", "둘째 반응"])
                with sub_t1:
                    r1_counts = books_df[books_df['반응_첫째'] != '선택 안 함']['반응_첫째'].value_counts().reset_index()
                    r1_counts.columns = ['반응', '권수']
                    if not r1_counts.empty:
                        fig_r1 = px.pie(r1_counts, values='권수', names='반응', hole=0.4, title="첫째 반응")
                        st.plotly_chart(fig_r1, use_container_width=True)
                    else: st.caption("데이터 없음")
                with sub_t2:
                    r2_counts = books_df[books_df['반응_둘째'] != '선택 안 함']['반응_둘째'].value_counts().reset_index()
                    r2_counts.columns = ['반응', '권수']
                    if not r2_counts.empty:
                        fig_r2 = px.pie(r2_counts, values='권수', names='반응', hole=0.4, title="둘째 반응")
                        st.plotly_chart(fig_r2, use_container_width=True)
                    else: st.caption("데이터 없음")
        
        st.divider()
        st.subheader("🏆 Top 5 많이 읽은 책")
        if not books_df.empty:
            books_df['읽은횟수'] = pd.to_numeric(books_df['읽은횟수'], errors='coerce').fillna(0)
            top_books = books_df.sort_values(by='읽은횟수', ascending=False).head(5)
            for idx, row in top_books.iterrows():
                st.write(f"**{int(row['읽은횟수'])}회** | {row['제목']} (Lv.{row['레벨']})")

# --- [탭 2] 서재 관리 ---
with tab2:
    c_head, c_sort = st.columns([3, 2])
    with c_head: st.subheader("보유 도서 관리")
    with c_sort:
        sort_option = st.selectbox("정렬", ["최신 등록순", "자주 읽은 책", "안 읽은 책", "레벨 높은 순"])

    if not books_df.empty:
        # 데이터 정제
        books_df['읽은횟수'] = pd.to_numeric(books_df['읽은횟수'], errors='coerce').fillna(0)
        books_df['레벨'] = pd.to_numeric(books_df['레벨'], errors='coerce').fillna(1)
        
        display_df = books_df.copy()
        
        if sort_option == "최신 등록순": display_df = display_df.iloc[::-1]
        elif sort_option == "자주 읽은 책": display_df = display_df.sort_values(by='읽은횟수', ascending=False)
        elif sort_option == "안 읽은 책": display_df = display_df.sort_values(by='읽은횟수', ascending=True)
        elif sort_option == "레벨 높은 순": display_df = display_df.sort_values(by='레벨', ascending=False)

        st.caption(f"총 {len(display_df)}권")

        for i, row in display_df.iterrows():
            with st.container():
                c1, c2 = st.columns([1, 5])
                
                # 왼쪽: 이미지
                with c1: 
                    img_url = row['표지URL']
                    if pd.isna(img_url) or str(img_url).strip() == "":
                        img_url = "https://via.placeholder.com/150?text=No+Image"
                    st.image(img_url, width=80)
                    
                    # [추가] 음원 바로가기 버튼 (URL이 있을 경우에만)
                    if pd.notna(row.get('음원URL')) and str(row['음원URL']).startswith("http"):
                        st.link_button("🎵 음원 듣기", row['음원URL'], help="등록된 음원 링크로 이동합니다.")

                # 오른쪽: 정보 및 기능
                with c2:
                    # 1. 기본 정보 수정 (제목)
                    new_title = st.text_input("제목", value=row['제목'], key=f"tit_{row['ID']}", label_visibility="collapsed")
                    
                    # 2. 상세 정보 수정 및 기능 (확장 메뉴)
                    with st.expander("📝 상세 정보 / 반응 기록 / 음원 등록"):
                        st.caption(f"ISBN: {row['ISBN']}")
                        
                        # [A] 표지 URL 수정
                        new_img_url = st.text_input("표지 이미지 URL", value=row['표지URL'], key=f"img_{row['ID']}")
                        
                        # [B] 음원 QR 등록 및 수동 입력
                        st.markdown("---")
                        st.markdown("**🎵 음원(QR) 관리**")
                        # (1) 수동 입력
                        new_audio_url = st.text_input("음원 주소 (직접 입력)", value=row.get('음원URL', ''), key=f"aud_{row['ID']}", placeholder="http://...")
                        
                        # (2) QR 스캔 (카메라)
                        qr_cam = st.camera_input("또는 QR을 찍어 주소 입력", key=f"cam_{row['ID']}")
                        if qr_cam:
                            scanned_url = scan_code(qr_cam)
                            if scanned_url:
                                st.success(f"QR 인식 성공: {scanned_url}")
                                new_audio_url = scanned_url # 인식된 URL로 덮어쓰기

                        # [C] 아이별 반응 및 메모
                        st.markdown("---")
                        st.markdown("**🧸 아이 반응 기록**")
                        rc1, rc2 = st.columns(2)
                        
                        # 인덱스 안전하게 찾기
                        r1_val = row.get('반응_첫째', '선택 안 함')
                        r2_val = row.get('반응_둘째', '선택 안 함')
                        idx1 = REACTION_OPTIONS.index(r1_val) if r1_val in REACTION_OPTIONS else 0
                        idx2 = REACTION_OPTIONS.index(r2_val) if r2_val in REACTION_OPTIONS else 0
                        
                        with rc1: new_r1 = st.selectbox("첫째 반응", REACTION_OPTIONS, index=idx1, key=f"r1_{row['ID']}")
                        with rc2: new_r2 = st.selectbox("둘째 반응", REACTION_OPTIONS, index=idx2, key=f"r2_{row['ID']}")
                        
                        new_note = st.text_area("독서 메모 (에피소드 등)", value=row.get('반응_메모', ''), key=f"note_{row['ID']}", height=80)

                    # 3. 레벨 및 상태 (메인 노출)
                    ec1, ec2 = st.columns([1, 1.2])
                    with ec1: new_lvl = st.selectbox("레벨", [1,2,3,4,5], index=int(row['레벨'])-1, key=f"l_{row['ID']}", label_visibility="collapsed")
                    with ec2: 
                        s_idx = ["읽지 않음", "읽는 중", "완독"].index(row['상태']) if row['상태'] in ["읽지 않음", "읽는 중", "완독"] else 0
                        new_sts = st.selectbox("상태", ["읽지 않음", "읽는 중", "완독"], index=s_idx, key=f"s_{row['ID']}", label_visibility="collapsed")

                    # [저장 로직 통합]
                    # 변경 사항이 있는지 확인
                    has_changed = (
                        new_title != row['제목'] or 
                        new_img_url != row['표지URL'] or 
                        new_audio_url != row.get('음원URL', '') or
                        new_lvl != row['레벨'] or 
                        new_sts != row['상태'] or 
                        new_r1 != row.get('반응_첫째') or 
                        new_r2 != row.get('반응_둘째') or
                        new_note != row.get('반응_메모')
                    )

                    if has_changed:
                        with st.spinner("변경사항 저장 중..."):
                            real_idx = books_df[books_df['ID'] == row['ID']].index[0]
                            books_df.at[real_idx, '제목'] = new_title
                            books_df.at[real_idx, '표지URL'] = new_img_url
                            books_df.at[real_idx, '음원URL'] = new_audio_url
                            books_df.at[real_idx, '레벨'] = new_lvl
                            books_df.at[real_idx, '상태'] = new_sts
                            books_df.at[real_idx, '반응_첫째'] = new_r1
                            books_df.at[real_idx, '반응_둘째'] = new_r2
                            books_df.at[real_idx, '반응_메모'] = new_note
                            save_books(books_df)
                        st.toast(f"✅ '{new_title}' 수정 완료")
                        st.rerun()

                    # 4. 버튼 영역
                    b1, b2, b3 = st.columns([1.5, 1, 1])
                    if b1.button(f"➕ 읽기 추가 ({int(row['읽은횟수'])})", key=f"btn_r_{row['ID']}"):
                        with st.spinner("기록 중..."):
                            real_idx = books_df[books_df['ID'] == row['ID']].index[0]
                            books_df.at[real_idx, '읽은횟수'] += 1
                            if books_df.at[real_idx, '상태'] == '읽지 않음': books_df.at[real_idx, '상태'] = '읽는 중'
                            save_books(books_df)
                            add_log(row['ID'], new_title, new_lvl)
                        st.toast("📖 독서 횟수 추가됨!")
                        st.rerun()
                    
                    if b3.button("🗑 삭제", key=f"btn_d_{row['ID']}"):
                        if st.session_state.get(f"del_{row['ID']}"):
                             with st.spinner("삭제 중..."):
                                real_idx = books_df[books_df['ID'] == row['ID']].index[0]
                                books_df = books_df.drop(real_idx)
                                save_books(books_df)
                             st.rerun()
                        else:
                             st.session_state[f"del_{row['ID']}"] = True
                             st.warning("한 번 더 누르면 삭제됩니다.")
                st.divider()
    else: st.info("등록된 책이 없습니다.")

# --- [탭 3] 새 책 등록 ---
with tab3:
    st.subheader("새 책 입고")
    
    # 세션 상태 초기화
    if 'reg_title' not in st.session_state: 
        st.session_state.update({
            'reg_title':"", 'reg_isbn':"", 'reg_img':"", 'reg_audio':"", 
            'search_done':False
        })

    # 1. 책 정보 입력 방식 (바코드/사진/수동)
    st.markdown("#### 1️⃣ 책 정보 입력")
    input_method = st.radio("입력 방식", ["📸 바코드 스캔", "📂 바코드 사진 업로드", "✍️ 수동 입력"], horizontal=True)
    
    img_file = None 
    if input_method == "📸 바코드 스캔": img_file = st.camera_input("책 뒷면 바코드 촬영", key="cam_book")
    elif input_method == "📂 바코드 사진 업로드": img_file = st.file_uploader("바코드 사진 선택", type=['png', 'jpg', 'jpeg'])

    # 바코드 처리 로직
    if img_file and not st.session_state.get('search_done'):
        code_val = scan_code(img_file)
        if code_val:
            st.toast(f"바코드 인식 성공: {code_val}")
            if st.session_state['reg_isbn'] != code_val:
                with st.spinner("도서 정보 검색 중..."):
                    t, i = search_book_info(code_val)
                    st.session_state.update({'reg_isbn': code_val, 'reg_title': t or "", 'reg_img': i or "", 'search_done': True})
                    st.rerun()
        else: st.error("바코드 인식 실패. 다시 찍거나 수동 입력을 이용하세요.")

    if input_method == "✍️ 수동 입력":
        manual_isbn = st.text_input("ISBN 직접 입력", value=st.session_state['reg_isbn'])
        if manual_isbn and manual_isbn != st.session_state.get('last_manual', ''):
             with st.spinner("검색 중..."):
                t, i = search_book_info(manual_isbn)
                st.session_state.update({'reg_isbn': manual_isbn, 'reg_title': t or "", 'reg_img': i or "", 'last_manual': manual_isbn})
                st.rerun()
    
    st.divider()

    # 2. 상세 정보 입력 폼
    with st.form("reg_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            title = st.text_input("제목 *", value=st.session_state['reg_title'])
            isbn = st.text_input("ISBN", value=st.session_state['reg_isbn'])
            level = st.selectbox("레벨", [1,2,3,4,5])
            status = st.selectbox("상태", ["읽지 않음", "읽는 중", "완독"])
        with c2:
            img_url = st.text_input("표지 URL", value=st.session_state['reg_img'])
            # 음원 URL (수동 입력)
            audio_url_input = st.text_input("음원 URL (직접 입력 혹은 아래 QR스캔)", value=st.session_state['reg_audio'], key="aud_input")

        st.markdown("---")
        st.markdown("**🧸 아이 반응 & 메모**")
        rc1, rc2 = st.columns(2)
        with rc1: r1 = st.selectbox("첫째 반응", REACTION_OPTIONS)
        with rc2: r2 = st.selectbox("둘째 반응", REACTION_OPTIONS)
        note = st.text_area("독서 메모", height=80, placeholder="아이들의 반응이나 읽어줄 때 에피소드를 기록하세요.")

        submit_btn = st.form_submit_button("책 등록하기")
            
        if submit_btn:
            if not title: st.error("책 제목은 필수입니다.")
            else:
                with st.spinner("저장 중..."):
                    new_data = {
                        'ID': str(uuid.uuid4()), 
                        '제목': title, 'ISBN': isbn, '레벨': level, 
                        '읽은횟수': 0, '상태': status, 
                        '반응_첫째': r1, '반응_둘째': r2, '반응_메모': note,
                        '표지URL': img_url, '음원URL': audio_url_input
                    }
                    books_df = pd.concat([books_df, pd.DataFrame([new_data])], ignore_index=True)
                    save_books(books_df)
                    
                    # 입력 필드 초기화
                    for key in ['reg_title', 'reg_isbn', 'reg_img', 'reg_audio', 'search_done', 'last_manual']:
                        if key in st.session_state: del st.session_state[key]
                st.success("등록 완료!")
                st.rerun()

    # 3. (폼 밖) 음원 QR 스캔 기능
    # 폼 안에 카메라를 넣으면 리런될 때 입력값이 날아갈 수 있어서 폼 밖에 배치하고 세션에 저장
    st.markdown("#### 🎵 음원 QR 스캔 (선택)")
    st.caption("책에 있는 음원 QR코드를 찍으면 위 '음원 URL' 칸에 자동 입력됩니다.")
    qr_cam_reg = st.camera_input("음원 QR 촬영", key="cam_audio_reg")
    if qr_cam_reg:
        detected_url = scan_code(qr_cam_reg)
        if detected_url:
            st.success(f"QR 인식 성공: {detected_url}")
            if st.session_state['reg_audio'] != detected_url:
                st.session_state['reg_audio'] = detected_url
                st.rerun()
