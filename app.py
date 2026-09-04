import os
import re
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from supabase import create_client, Client

# 페이지 기본 설정
st.set_page_config(page_title="키노사다리 초고속 A/B 패턴 분석기", page_icon="⚡", layout="centered")

# Supabase 연동 설정
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_KEY") or os.environ.get("SUPABASE_KEY")
    if not url or not key:
        return None
    try:
        return create_client(url, key)
    except Exception:
        return None

supabase = init_supabase()

# CSS 스타일 (원본 100% 복원)
st.markdown("""
<style>
    .block-container { 
        padding: 0.3rem 0.3rem 80px 0.3rem !important; 
    }
    h1, h2, h3 { display: none !important; }
    p, div, span { font-size: 0.8rem !important; line-height: 1.3 !important; }

    div[data-testid="stSegmentedControl"] {
        width: 100% !important;
    }
    div[data-testid="stSegmentedControl"] > div {
        display: flex !important;
        flex-direction: row !important;
        width: 100% !important;
        gap: 2px !important;
    }
    div[data-testid="stSegmentedControl"] button {
        flex: 1 1 25% !important;
        width: 25% !important;
        max-width: 25% !important;
        min-width: 0px !important;
        padding: 0.3rem 0rem !important;
        font-size: 0.85rem !important;
        font-weight: bold !important;
        height: 38px !important;
    }

    .ctrl-container .stButton {
        width: 100% !important;
        margin-bottom: 0.2rem !important;
    }
    .ctrl-container .stButton>button {
        padding: 0.5rem 0.1rem !important;
        font-size: 0.88rem !important;
        font-weight: bold !important;
        width: 100% !important;
    }

    .ctrl-container div[data-testid="stDownloadButton"] {
        width: 100% !important;
        margin-bottom: 0.2rem !important;
    }
    .ctrl-container div[data-testid="stDownloadButton"]>button {
        padding: 0.5rem 0.1rem !important;
        font-size: 0.88rem !important;
        font-weight: bold !important;
        width: 100% !important;
        background-color: #28a745 !important;
        color: white !important;
        border: none !important;
    }

    hr { margin: 0.3rem 0 !important; border-color: #ddd !important; }
</style>
""", unsafe_allow_html=True)

MAX_DATA_SIZE = 3000
ALL_COMBOS = ['우삼', '우사', '좌삼', '좌사']

ITEM_MAP = {
    '우사': ('우', '사', '짝'),
    '우삼': ('우', '삼', '홀'),
    '좌사': ('좌', '사', '홀'),
    '좌삼': ('좌', '삼', '짝')
}

ITEM_FULL_MAP = {
    '우사': '우사짝',
    '우삼': '우삼홀',
    '좌사': '좌사홀',
    '좌삼': '좌삼짝'
}

WEEKDAYS = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일']

# DB 처리 함수
def load_data_db():
    if not supabase:
        return []
    try:
        res = supabase.table("ladder_records").select("date, round, result, id").order("id", desc=False).execute()
        if res.data:
            return res.data
        return []
    except Exception:
        return []

def add_single_record_db(date_str, round_num, result_str):
    if supabase:
        try:
            supabase.table("ladder_records").insert({"date": str(date_str), "round": int(round_num), "result": str(result_str)}).execute()
            return True
        except Exception:
            return False
    return False

def add_bulk_records_db(records_list):
    if supabase and records_list:
        try:
            chunk_size = 100
            for i in range(0, len(records_list), chunk_size):
                chunk = records_list[i:i + chunk_size]
                supabase.table("ladder_records").insert(chunk).execute()
            return True
        except Exception:
            return False
    return False

def delete_last_record_db():
    if supabase:
        try:
            res = supabase.table("ladder_records").select("id").order("id", desc=True).limit(1).execute()
            if res.data:
                last_id = res.data[0]['id']
                supabase.table("ladder_records").delete().eq("id", last_id).execute()
                return True
        except Exception:
            pass
    return False

def clear_all_records_db():
    if supabase:
        try:
            supabase.table("ladder_records").delete().neq("id", -1).execute()
            return True
        except Exception:
            pass
    return False

# 원본 연산 엔진
def calculate_score_A_engine(stream, val1, val2):
    n = len(stream)
    if n < 2: return {val1: 50.0, val2: 50.0}
    s1, s2 = 50.0, 50.0

    if stream[-1] == stream[-2]:
        rec = stream[-1]
        streak = 2
        for idx in range(3, min(n + 1, 10)):
            if stream[-idx] == rec: streak += 1
            else: break
        bonus = 12.0 + (streak * 4.0)
        if rec == val1: s1 += bonus
        else: s2 += bonus

    if stream[-1] != stream[-2]:
        streak = 2
        for idx in range(3, min(n + 1, 10)):
            if stream[-idx + 1] != stream[-idx]: streak += 1
            else: break
        opp_val = val2 if stream[-1] == val1 else val1
        bonus = 10.0 + (streak * 3.5)
        if opp_val == val1: s1 += bonus
        else: s2 += bonus

    tot = s1 + s2
    return {val1: (s1/tot)*100.0, val2: (s2/tot)*100.0}

def analyze_A_engine_tuple(records_tuple):
    valid = [r for r in records_tuple if r[2] in ALL_COMBOS][-MAX_DATA_SIZE:]
    if len(valid) < 3: return None

    s_s = calculate_score_A_engine([ITEM_MAP[r[2]][0] for r in valid], '우', '좌')
    l_s = calculate_score_A_engine([ITEM_MAP[r[2]][1] for r in valid], '사', '삼')
    o_s = calculate_score_A_engine([ITEM_MAP[r[2]][2] for r in valid], '짝', '홀')

    probs = {}
    for c in ALL_COMBOS:
        s, l, o = ITEM_MAP[c]
        probs[c] = (s_s[s]/100.0) * (l_s[l]/100.0) * (o_s[o]/100.0)

    tot = sum(probs.values())
    norm_probs = {c: (p/tot)*100.0 for c, p in probs.items()}
    sorted_combos = sorted(norm_probs.items(), key=lambda x: x[1], reverse=True)

    return {
        'top': sorted_combos[0][0], 'top_prob': sorted_combos[0][1],
        'worst': sorted_combos[-1][0], 'worst_prob': sorted_combos[-1][1]
    }

def calculate_score_B_engine(stream, val1, val2):
    n = len(stream)
    if n < 4: return {val1: 50.0, val2: 50.0}
    s1, s2 = 50.0, 50.0

    if stream[-2] == stream[-3] and stream[-1] != stream[-2]:
        same_val = stream[-1]
        if same_val == val1: s1 += 22.0
        else: s2 += 22.0
    elif n >= 5 and stream[-3] == stream[-4] and stream[-1] == stream[-2] and stream[-1] != stream[-3]:
        opp_val = val2 if stream[-1] == val1 else val1
        if opp_val == val1: s1 += 25.0
        else: s2 += 25.0

    if n >= 6 and stream[-1] == stream[-2] and stream[-2] != stream[-3] and stream[-3] == stream[-4]:
        same_val = stream[-1]
        if same_val == val1: s1 += 20.0
        else: s2 += 20.0

    if n >= 6 and stream[-1] == stream[-5] and stream[-2] == stream[-4]:
        sym_val = stream[-3]
        if sym_val == val1: s1 += 24.0
        else: s2 += 24.0

    tot = s1 + s2
    return {val1: (s1/tot)*100.0, val2: (s2/tot)*100.0}

def analyze_B_engine_tuple(records_tuple):
    valid = [r for r in records_tuple if r[2] in ALL_COMBOS][-MAX_DATA_SIZE:]
    if len(valid) < 4: return None

    s_s = calculate_score_B_engine([ITEM_MAP[r[2]][0] for r in valid], '우', '좌')
    l_s = calculate_score_B_engine([ITEM_MAP[r[2]][1] for r in valid], '사', '삼')
    o_s = calculate_score_B_engine([ITEM_MAP[r[2]][2] for r in valid], '짝', '홀')

    probs = {}
    for c in ALL_COMBOS:
        s, l, o = ITEM_MAP[c]
        probs[c] = (s_s[s]/100.0) * (l_s[l]/100.0) * (o_s[o]/100.0)

    tot = sum(probs.values())
    norm_probs = {c: (p/tot)*100.0 for c, p in probs.items()}
    sorted_combos = sorted(norm_probs.items(), key=lambda x: x[1], reverse=True)

    return {
        'top': sorted_combos[0][0], 'top_prob': sorted_combos[0][1],
        'worst': sorted_combos[-1][0], 'worst_prob': sorted_combos[-1][1]
    }

@st.cache_data(show_spinner=False)
def calculate_ab_stats_cached(records_tuple, target_date=None, limit_recent=None):
    if limit_recent: eval_records = list(records_tuple[-limit_recent:])
    else: eval_records = list(records_tuple)

    n = len(eval_records)
    if n < 4: return None

    tot_a, tot_b = 0, 0
    a_win, b_win = 0, 0
    a_avoid_win, b_avoid_win = 0, 0

    for i in range(3, n):
        act = eval_records[i][2]
        if act not in ALL_COMBOS: continue
        if target_date and str(eval_records[i][0]).strip() != str(target_date).strip(): continue

        past_sub = tuple(eval_records[:i])
        
        res_a = analyze_A_engine_tuple(past_sub)
        res_b = analyze_B_engine_tuple(past_sub)

        if res_a:
            tot_a += 1
            if res_a['top'] == act: a_win += 1
            if res_a['worst'] != act: a_avoid_win += 1

        if res_b:
            tot_b += 1
            if res_b['top'] == act: b_win += 1
            if res_b['worst'] != act: b_avoid_win += 1

    return {
        'tot_a': tot_a, 'a_win': a_win, 'a_lose': tot_a - a_win, 'a_rate': (a_win/tot_a*100.0) if tot_a > 0 else 0.0,
        'a_avoid_win': a_avoid_win, 'a_avoid_lose': tot_a - a_avoid_win, 'a_avoid_rate': (a_avoid_win/tot_a*100.0) if tot_a > 0 else 0.0,
        'tot_b': tot_b, 'b_win': b_win, 'b_lose': tot_b - b_win, 'b_rate': (b_win/tot_b*100.0) if tot_b > 0 else 0.0,
        'b_avoid_win': b_avoid_win, 'b_avoid_lose': tot_b - b_avoid_win, 'b_avoid_rate': (b_avoid_win/tot_b*100.0) if tot_b > 0 else 0.0
    }

# 데이터베이스 연결 경고
if not supabase:
    st.warning("⚠️ Supabase 데이터베이스가 연동되지 않았습니다. Streamlit Secrets 설정을 확인해 주세요.")

if "show_bulk" not in st.session_state: st.session_state.show_bulk = False

records = load_data_db()
records_tuple = tuple((str(r['date']).strip(), int(r['round']), str(r['result']).strip()) for r in records)

# 1. 대량 입력 모드
if st.session_state.show_bulk:
    st.markdown("**📋 과거 데이터 한 번에 복사/붙여넣기**")
    b_date = st.date_input("입력할 날짜 선택", datetime.now())
    b_start_rd = st.number_input("시작 회차 번호", min_value=1, max_value=288, value=1)
    raw_text = st.text_area("텍스트 붙여넣기", height=180, placeholder="예시:\n우사 우삼 좌사 좌삼 우사")
    
    col_b1, col_b2 = st.columns(2)
    if col_b1.button("📥 데이터 일괄 추가", use_container_width=True):
        found_items = re.findall(r'우사|우삼|좌사|좌삼', raw_text)
        if found_items:
            curr_rd = int(b_start_rd)
            curr_dt = b_date
            bulk_list = []
            
            for item in found_items:
                bulk_list.append({
                    "date": curr_dt.strftime("%Y-%m-%d"),
                    "round": curr_rd,
                    "result": item
                })
                curr_rd += 1
                if curr_rd > 288:
                    curr_rd = 1
                    curr_dt = curr_dt + timedelta(days=1)
            
            if add_bulk_records_db(bulk_list):
                st.cache_data.clear()
                st.toast(f"총 {len(found_items)}개 일괄 등록 완료!")
                st.session_state.show_bulk = False
                st.rerun()

    if col_b2.button("❌ 취소", use_container_width=True):
        st.session_state.show_bulk = False
        st.rerun()

# 2. 최초 데이터 없을 때
elif not records:
    st.markdown("**⚙️ 최초 환경 설정**")
    init_date = st.date_input("날짜 선택", datetime.now())
    init_round = st.number_input("시작 회차 번호", min_value=1, max_value=288, value=1)
    
    sel = st.segmented_control(
        label="첫 결과 선택",
        options=ALL_COMBOS,
        selection_mode="single",
        label_visibility="collapsed",
        key="init_seg_ctrl"
    )

    if sel:
        if add_single_record_db(init_date.strftime("%Y-%m-%d"), int(init_round), sel):
            st.cache_data.clear()
            st.rerun()

# 3. 메인 분석 화면 (원본 100% 동일 표출)
else:
    last_rec = records[-1]
    last_dt_obj = datetime.strptime(str(last_rec['date']).strip(), "%Y-%m-%d")
    
    if int(last_rec['round']) >= 288:
        next_round = 1
        curr_date = (last_dt_obj + timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        next_round = int(last_rec['round']) + 1
        curr_date = str(last_rec['date']).strip()

    st.markdown(f"**날짜 : {curr_date} / 다음회차 : {next_round}회차**")
    if st.button("📋 텍스트 대량 추가", use_container_width=True):
        st.session_state.show_bulk = True
        st.rerun()

    st.markdown("---")

    # 원본 통계 표출
    all_stat = calculate_ab_stats_cached(records_tuple)
    today_stat = calculate_ab_stats_cached(records_tuple, target_date=curr_date)
    recent_3000_stat = calculate_ab_stats_cached(records_tuple, limit_recent=3000)

    st.markdown("**📊 전체 누적 통계 (패스 회차 제외)**")
    if all_stat:
        st.markdown(f"🅰️ **A (장줄/퐁당) 추천 적중률 : {all_stat['a_win']}승 {all_stat['a_lose']}패 (승률 {all_stat['a_rate']:.1f}%)**")
        st.markdown(f"   ⚠️ **A 지울 픽 성공률 : {all_stat['a_avoid_win']}승 {all_stat['a_avoid_lose']}패 (승률 {all_stat['a_avoid_rate']:.1f}%)**")
        st.markdown(f"🅱️ **B (박스/계단/데칼) 추천 적중률 : {all_stat['b_win']}승 {all_stat['b_lose']}패 (승률 {all_stat['b_rate']:.1f}%)**")
        st.markdown(f"   ⚠️ **B 지울 픽 성공률 : {all_stat['b_avoid_win']}승 {all_stat['b_avoid_lose']}패 (승률 {all_stat['b_avoid_rate']:.1f}%)**")

    # 오늘 통계
    st.markdown("---")
    st.markdown(f"**📅 오늘 데이터 통계 ({curr_date})**")
    if today_stat and today_stat['tot_a'] > 0:
        st.markdown(f"🅰️ **A 승률 : {today_stat['a_win']}승 {today_stat['a_lose']}패 ({today_stat['a_rate']:.1f}%)** / 🅱️ **B 승률 : {today_stat['b_win']}승 {today_stat['b_lose']}패 ({today_stat['b_rate']:.1f}%)**")
    else:
        st.markdown("오늘 기록된 데이터가 아직 없습니다.")

    # 최근 3000개 통계
    st.markdown("---")
    st.markdown("**⚡ 최근 3,000개 데이터 누적 통계**")
    if recent_3000_stat and recent_3000_stat['tot_a'] > 0:
        st.markdown(f"🅰️ **A 승률 : {recent_3000_stat['a_win']}승 {recent_3000_stat['a_lose']}패 ({recent_3000_stat['a_rate']:.1f}%)** / 🅱️ **B 승률 : {recent_3000_stat['b_win']}승 {recent_3000_stat['b_lose']}패 ({recent_3000_stat['b_rate']:.1f}%)**")
    else:
        st.markdown("누적 데이터 수량이 부족합니다.")

    st.markdown("---")

    # 원본 지울픽(Worst) 포함 추천 예측 표출 100% 복원
    curr_a_res = analyze_A_engine_tuple(records_tuple)
    curr_b_res = analyze_B_engine_tuple(records_tuple)

    st.markdown(f"**이번회차 A/B 패턴 분석 ( {next_round}회차 )**")
    if curr_a_res:
        st.markdown(f"🅰️ **[A: 장줄/퐁당] 추천: `{curr_a_res['top']}` ({ITEM_FULL_MAP[curr_a_res['top']]})** `확률 {curr_a_res['top_prob']:.1f}%` / ⚠️ **지울픽: `{curr_a_res['worst']}` ({ITEM_FULL_MAP[curr_a_res['worst']]})** `확률 {curr_a_res['worst_prob']:.1f}%`")
    if curr_b_res:
        st.markdown(f"🅱️ **[B: 박스/계단/데칼] 추천: `{curr_b_res['top']}` ({ITEM_FULL_MAP[curr_b_res['top']]})** `확률 {curr_b_res['top_prob']:.1f}%` / ⚠️ **지울픽: `{curr_b_res['worst']}` ({ITEM_FULL_MAP[curr_b_res['worst']]})** `확률 {curr_b_res['worst_prob']:.1f}%`")

    st.markdown("---")
    st.markdown("**결과 입력**")

    input_val = st.segmented_control(
        label="결과 선택",
        options=ALL_COMBOS,
        selection_mode="single",
        label_visibility="collapsed",
        key=f"seg_ctrl_{len(records)}"
    )

    if input_val:
        if add_single_record_db(curr_date, next_round, input_val):
            st.cache_data.clear()
            st.rerun()

    st.markdown("---")

    # 하단 제어 버튼 (되돌리기 등 정상 작동)
    st.markdown('<div class="ctrl-container">', unsafe_allow_html=True)
    if st.button("패스", use_container_width=True, key="btn_pass"):
        if add_single_record_db(curr_date, next_round, "PASS"):
            st.cache_data.clear()
            st.rerun()

    if st.button("직전취소 (되돌리기)", use_container_width=True, key="btn_cancel"):
        if delete_last_record_db():
            st.cache_data.clear()
            st.toast("직전 기록이 취소(되돌리기) 되었습니다.")
            st.rerun()

    if st.button("초기화", use_container_width=True, key="btn_reset"):
        if clear_all_records_db():
            st.cache_data.clear()
            st.toast("전체 데이터가 초기화되었습니다.")
            st.rerun()

    # TXT 백업 다운로드
    export_lines = [f"{r['date']}|{r['round']}|{r['result']}" for r in records]
    export_bytes = "\n".join(export_lines).encode("utf-8-sig")
    
    st.download_button(
        label="📥 현재 누적 데이터 TXT 다운로드 (백업)",
        data=export_bytes,
        file_name=f"ladder_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
        mime="text/plain",
        use_container_width=True,
        key="btn_download"
    )
    st.markdown('</div>', unsafe_allow_html=True)
