import os
import re
import copy
import pandas as pd
import streamlit as st
from datetime import datetime

# 페이지 기본 설정
st.set_page_config(page_title="키노사다리 전회차 양상 추종 분석기", page_icon="📊", layout="centered")

# 모바일 세로 스크롤 최소화 및 가로 버튼 레이아웃 CSS
st.markdown("""
<style>
    .block-container { padding: 0.5rem 0.6rem !important; }
    h1, h2, h3 { display: none !important; }
    p, div, span { font-size: 0.82rem !important; line-height: 1.35 !important; }
    .stButton>button { padding: 0.35rem 0.05rem !important; font-size: 0.82rem !important; font-weight: bold; }
    hr { margin: 0.3rem 0 !important; border-color: #ddd !important; }
</style>
""", unsafe_allow_html=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
DATA_FILE = os.path.join(BASE_DIR, "ladder_data_history.txt")
MAX_DATA_SIZE = 3000

ALL_COMBOS = ['우사', '우삼', '좌사', '좌삼']

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

def load_data():
    records = []
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split('|')
                    if len(parts) == 3:
                        records.append({'date': parts[0], 'round': int(parts[1]), 'result': parts[2]})
        except Exception:
            pass
    return records

def save_data(records):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            for r in records[-MAX_DATA_SIZE:]:
                f.write(f"{r['date']}|{r['round']}|{r['result']}\n")
    except Exception:
        pass

# 단일 트랙용 전회차 양상(SAME/DIFF) 추종 스캔 엔진
def calculate_trend_follow_score(stream, val1, val2):
    n = len(stream)
    if n < 4:
        return {val1: 50.0, val2: 50.0}

    score1, score2 = 50.0, 50.0
    
    # 직전 양상 확인 (직전 2개가 같았는가, 달랐는가)
    last_val = stream[-1]
    is_same = (stream[-1] == stream[-2])

    # 1. 직전이 '같은 속성(SAME)'으로 나왔다면 ➔ 이번에도 '같은 속성' 추종 가점
    if is_same:
        if last_val == val1: score1 += 28.0
        else: score2 += 28.0
    # 2. 직전이 '다른 속성(DIFF)'으로 나왔다면 ➔ 이번에도 '다른 속성(꺾임)' 추종 가점
    else:
        opp_val = val2 if last_val == val1 else val1
        if opp_val == val1: score1 += 28.0
        else: score2 += 28.0

    # 장줄 보정 (3연속 이상 지속 시 추종 가중치 추가 강화)
    if n >= 4 and stream[-1] == stream[-2] == stream[-3]:
        if last_val == val1: score1 += 12.0
        else: score2 += 12.0

    tot = score1 + score2
    return {val1: (score1 / tot) * 100.0, val2: (score2 / tot) * 100.0}

# 3구멍 독립 스캔 및 전회차 추종 4조합 분석 엔진
def analyze_combo_prediction(records):
    valid_records = [r for r in records if r['result'] in ALL_COMBOS][-MAX_DATA_SIZE:]
    if len(valid_records) < 4:
        return None

    s_stream = [ITEM_MAP[r['result']][0] for r in valid_records]
    s_scores = calculate_trend_follow_score(s_stream, '우', '좌')

    l_stream = [ITEM_MAP[r['result']][1] for r in valid_records]
    l_scores = calculate_trend_follow_score(l_stream, '사', '삼')

    o_stream = [ITEM_MAP[r['result']][2] for r in valid_records]
    o_scores = calculate_trend_follow_score(o_stream, '짝', '홀')

    combo_probs = {}
    for combo in ALL_COMBOS:
        s_val, l_val, o_val = ITEM_MAP[combo]
        p_s = s_scores[s_val] / 100.0
        p_l = l_scores[l_val] / 100.0
        p_o = o_scores[o_val] / 100.0
        combo_probs[combo] = p_s * p_l * p_o

    tot_p = sum(combo_probs.values())
    final_probs = {c: (p / tot_p) * 100.0 for c, p in combo_probs.items()}

    sorted_combos = sorted(final_probs.items(), key=lambda x: x[1], reverse=True)

    worst1 = sorted_combos[-1][0]
    worst2 = sorted_combos[-2][0]

    return {
        'worst1_avoid': worst1,
        'worst1_full': ITEM_FULL_MAP[worst1],
        'worst1_prob': sorted_combos[-1][1],
        'worst2_avoid': worst2,
        'worst2_full': ITEM_FULL_MAP[worst2],
        'worst2_prob': sorted_combos[-2][1],
        'top_recommend': sorted_combos[0][0],
        'top_full': ITEM_FULL_MAP[sorted_combos[0][0]],
        'top_prob': sorted_combos[0][1],
        'all_probs': final_probs
    }

# 지우기 승률 집계 함수
def calculate_combo_stats(records, target_date=None, limit_recent=None):
    if limit_recent:
        eval_records = records[-limit_recent:]
    else:
        eval_records = records

    n = len(eval_records)
    if n < 5:
        return None

    tot_count = 0
    avoid1_win = 0
    avoid2_win = 0
    dual_avoid_win = 0

    for i in range(4, n):
        act = eval_records[i]['result']
        if act not in ALL_COMBOS:
            continue

        if target_date and eval_records[i]['date'] != target_date:
            continue

        past_sub = eval_records[:i]
        pred = analyze_combo_prediction(past_sub)
        if pred:
            tot_count += 1
            if pred['worst1_avoid'] != act:
                avoid1_win += 1
            if pred['worst2_avoid'] != act:
                avoid2_win += 1
            if pred['worst1_avoid'] != act and pred['worst2_avoid'] != act:
                dual_avoid_win += 1

    if tot_count == 0:
        return None

    return {
        'total': tot_count,
        'avoid1_win': avoid1_win,
        'avoid1_rate': (avoid1_win / tot_count) * 100.0,
        'avoid2_win': avoid2_win,
        'avoid2_rate': (avoid2_win / tot_count) * 100.0,
        'dual_avoid_win': dual_avoid_win,
        'dual_avoid_rate': (dual_avoid_win / tot_count) * 100.0
    }

# 백업 상태 관리
if "records" not in st.session_state:
    st.session_state.records = load_data()
if "history_stack" not in st.session_state:
    st.session_state.history_stack = []
if "show_bulk" not in st.session_state:
    st.session_state.show_bulk = False

def push_backup():
    st.session_state.history_stack.append(copy.deepcopy(st.session_state.records))
    if len(st.session_state.history_stack) > 10:
        st.session_state.history_stack.pop(0)

records = st.session_state.records

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
            push_backup()
            curr_rd = int(b_start_rd)
            dt_str = b_date.strftime("%Y-%m-%d")
            for item in found_items:
                st.session_state.records.append({'date': dt_str, 'round': curr_rd, 'result': item})
                curr_rd += 1
                if curr_rd > 288: curr_rd = 1
            save_data(st.session_state.records)
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
    
    col1, col2, col3, col4 = st.columns(4)
    sel = None
    if col1.button("우삼"): sel = "우삼"
    elif col2.button("우사"): sel = "우사"
    elif col3.button("좌삼"): sel = "좌삼"
    elif col4.button("좌사"): sel = "좌사"

    if sel:
        push_backup()
        st.session_state.records.append({'date': init_date.strftime("%Y-%m-%d"), 'round': int(init_round), 'result': sel})
        save_data(st.session_state.records)
        st.rerun()

# 3. 메인 분석 화면
else:
    last_rec = records[-1]
    curr_date = last_rec['date']
    next_round = last_rec['round'] + 1
    if next_round > 288: next_round = 1

    st.markdown(f"**날짜 : {curr_date} / 다음회차 : {next_round}회차**")
    if st.button("📋 텍스트 대량 추가", use_container_width=True):
        st.session_state.show_bulk = True
        st.rerun()

    st.markdown("---")

    # 1. 전체 누적 승률
    all_stat = calculate_combo_stats(records)
    st.markdown("**전체 누적 통계 (패스 회차 제외)**")
    if all_stat:
        st.markdown(f"⚠️ **지울 픽 1순위 성공률 : {all_stat['avoid1_win']}승 / {all_stat['total']}회 (승률 {all_stat['avoid1_rate']:.1f}%)**")
        st.markdown(f"⚠️ **지울 픽 2순위 성공률 : {all_stat['avoid2_win']}승 / {all_stat['total']}회 (승률 {all_stat['avoid2_rate']:.1f}%)**")
        st.markdown(f"🔥 **1·2순위 동시 지우기 성공률 : {all_stat['dual_avoid_win']}승 / {all_stat['total']}회 (승률 {all_stat['dual_avoid_rate']:.1f}%)**")
    else:
        st.markdown("데이터 축적 중...")

    st.markdown("---")

    # 2. 최근 3000개 누적 승률
    recent_stat = calculate_combo_stats(records, limit_recent=MAX_DATA_SIZE)
    recent_cnt = min(len(records), MAX_DATA_SIZE)
    st.markdown(f"**최근 {recent_cnt}개 누적 통계 (패스 회차 제외)**")
    if recent_stat:
        st.markdown(f"⚠️ **지울 픽 1순위 성공률 : {recent_stat['avoid1_win']}승 / {recent_stat['total']}회 (승률 {recent_stat['avoid1_rate']:.1f}%)**")
        st.markdown(f"⚠️ **지울 픽 2순위 성공률 : {recent_stat['avoid2_win']}승 / {recent_stat['total']}회 (승률 {recent_stat['avoid2_rate']:.1f}%)**")
        st.markdown(f"🔥 **1·2순위 동시 지우기 성공률 : {recent_stat['dual_avoid_win']}승 / {recent_stat['total']}회 (승률 {recent_stat['dual_avoid_rate']:.1f}%)**")
    else:
        st.markdown("데이터 축적 중...")

    st.markdown("---")

    # 3. 오늘 누적 승률
    try:
        dt_obj = datetime.strptime(curr_date, "%Y-%m-%d")
        w_str = WEEKDAYS[dt_obj.weekday()]
    except Exception:
        w_str = ""

    today_stat = calculate_combo_stats(records, target_date=curr_date)
    st.markdown(f"**오늘 누적 통계 ({curr_date} {w_str})**")
    if today_stat:
        st.markdown(f"⚠️ **지울 픽 1순위 성공률 : {today_stat['avoid1_win']}승 / {today_stat['total']}회 (승률 {today_stat['avoid1_rate']:.1f}%)**")
        st.markdown(f"⚠️ **지울 픽 2순위 성공률 : {today_stat['avoid2_win']}승 / {today_stat['total']}회 (승률 {today_stat['avoid2_rate']:.1f}%)**")
        st.markdown(f"🔥 **1·2순위 동시 지우기 성공률 : {today_stat['dual_avoid_win']}승 / {today_stat['total']}회 (승률 {today_stat['dual_avoid_rate']:.1f}%)**")
    else:
        st.markdown("데이터 축적 중...")

    st.markdown("---")

    # 4. 직전 회차 결과
    if len(records) >= 5:
        prev_sub = records[:-1]
        prev_pred = analyze_combo_prediction(prev_sub)
        prev_actual = last_rec['result']
        
        st.markdown(f"**직전회차 결과 ( {last_rec['round']}회차 )**")
        if prev_actual == "PASS":
            st.markdown("결과 : **패스(PASS)** ➔ **통계 제외**")
        elif prev_pred:
            a1_res = "성공" if prev_pred['worst1_avoid'] != prev_actual else "실패"
            a2_res = "성공" if prev_pred['worst2_avoid'] != prev_actual else "실패"
            
            st.markdown(f"실제 결과 : **{prev_actual} ({ITEM_FULL_MAP[prev_actual]})**")
            st.markdown(f"⚠️ 지울 픽 1순위 : **{prev_pred['worst1_avoid']}** ➔ **{a1_res}**")
            st.markdown(f"⚠️ 지울 픽 2순위 : **{prev_pred['worst2_avoid']}** ➔ **{a2_res}**")
        else:
            st.markdown(f"실제 결과 : **{prev_actual}**")

    st.markdown("---")

    # 5. 이번회차 안 나올 확률 & 양상 추종 분석 표출
    curr_pred = analyze_combo_prediction(records)
    if curr_pred:
        st.markdown(f"**이번회차 전회차 양상 추종 통분석 ( {next_round}회차 )**")
        st.markdown(f"⚠️ **가장 안 나올 조합 (지울 픽 1순위) : {curr_pred['worst1_avoid']} ({curr_pred['worst1_full']})** `출현확률 {curr_pred['worst1_prob']:.1f}%`")
        st.markdown(f"⚠️ **두 번째 안 나올 조합 (지울 픽 2순위) : {curr_pred['worst2_avoid']} ({curr_pred['worst2_full']})** `출현확률 {curr_pred['worst2_prob']:.1f}%`")
    else:
        st.markdown("데이터 축적 중...")

    st.markdown("---")
    st.markdown("**결과 입력**")

    c1, c2, c3, c4 = st.columns(4)
    b_um = c1.button("우삼", use_container_width=True)
    b_us = c2.button("우사", use_container_width=True)
    b_jm = c3.button("좌삼", use_container_width=True)
    b_js = c4.button("좌사", use_container_width=True)

    input_val = None
    if b_um: input_val = "우삼"
    elif b_us: input_val = "우사"
    elif b_jm: input_val = "좌삼"
    elif b_js: input_val = "좌사"

    if input_val:
        push_backup()
        st.session_state.records.append({'date': curr_date, 'round': next_round, 'result': input_val})
        save_data(st.session_state.records)
        st.rerun()

    st.markdown("---")

    m1, m2, m3, m4 = st.columns(4)
    if m1.button("패스", use_container_width=True):
        push_backup()
        st.session_state.records.append({'date': curr_date, 'round': next_round, 'result': "PASS"})
        save_data(st.session_state.records)
        st.toast(f"{next_round}회차 패스")
        st.rerun()

    if m2.button("직전취소", use_container_width=True):
        if st.session_state.records:
            push_backup()
            st.session_state.records.pop()
            save_data(st.session_state.records)
            st.rerun()

    if m3.button("초기화", use_container_width=True):
        push_backup()
        st.session_state.records = []
        if os.path.exists(DATA_FILE): os.remove(DATA_FILE)
        st.rerun()

    if m4.button("되돌리기", use_container_width=True):
        if st.session_state.history_stack:
            st.session_state.records = st.session_state.history_stack.pop()
            save_data(st.session_state.records)
            st.rerun()

    st.markdown("---")

    # 세부 결과 표 (당일 최신순)
    st.markdown("**세부 결과 (지운 픽 적중 여부)**")
    if len(records) >= 5:
        rows = []
        today_indices = [idx for idx, r in enumerate(records) if r['date'] == curr_date]
        
        for i in reversed(today_indices):
            if i < 4:
                continue
            p_sub = records[:i]
            pr = analyze_combo_prediction(p_sub)
            act_item = records[i]['result']
            rd_num = records[i]['round']
            
            if act_item == "PASS":
                rows.append({
                    "회차": f"{rd_num}회",
                    "실제 결과": "패스 (PASS)",
                    "지울 픽 1순위": "-",
                    "지울 픽 2순위": "-",
                    "지우기 성공 여부": "통계 제외"
                })
            elif pr:
                a1_ok = "성공" if pr['worst1_avoid'] != act_item else "실패"
                a2_ok = "성공" if pr['worst2_avoid'] != act_item else "실패"
                dual_ok = "2개 모두 성공" if (pr['worst1_avoid'] != act_item and pr['worst2_avoid'] != act_item) else "1개 이상 나와버림"
                
                rows.append({
                    "회차": f"{rd_num}회",
                    "실제 결과": f"{act_item} ({ITEM_FULL_MAP[act_item]})",
                    "지울 픽 1순위": f"{pr['worst1_avoid']} ({pr['worst1_full']})",
                    "지울 픽 2순위": f"{pr['worst2_avoid']} ({pr['worst2_full']})",
                    "동시 지우기 성공": dual_ok
                })
        
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, hide_index=True, use_container_width=True)
