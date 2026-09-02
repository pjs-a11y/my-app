import os
import re
import copy
import pandas as pd
import streamlit as st
from datetime import datetime

# 페이지 기본 설정
st.set_page_config(page_title="키노사다리 초고속 A/B 패턴 분석기", page_icon="⚡", layout="centered")

# 모바일 강제 가로 4등분 레이아웃 CSS
st.markdown("""
<style>
    .block-container { padding: 0.3rem 0.3rem !important; }
    h1, h2, h3 { display: none !important; }
    p, div, span { font-size: 0.8rem !important; line-height: 1.3 !important; }
    
    /* 결과 입력 4등분 버튼 컨테이너 */
    .btn-grid {
        display: flex !important;
        flex-direction: row !important;
        justify-content: space-between !important;
        align-items: center !important;
        width: 100% !important;
        gap: 4px !important;
        margin-bottom: 0.5rem !important;
    }
    .btn-grid form {
        flex: 1 !important;
        margin: 0 !important;
    }
    .btn-grid button {
        width: 100% !important;
        padding: 0.5rem 0rem !important;
        font-size: 0.85rem !important;
        font-weight: bold !important;
        background-color: #ffffff !important;
        border: 1px solid #d0d0d0 !important;
        border-radius: 6px !important;
        color: #333333 !important;
    }
    .btn-grid button:active {
        background-color: #e0e0e0 !important;
    }

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

# 🅰️ [A 엔진 연산]
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

# 🅱️ [B 엔진 연산]
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

# ⚡ 캐싱된 통계 집계 함수
@st.cache_data(show_spinner=False)
def calculate_ab_stats_cached(records_tuple, target_date=None, limit_recent=None):
    if limit_recent: eval_records = records_tuple[-limit_recent:]
    else: eval_records = records_tuple

    n = len(eval_records)
    if n < 4: return None

    tot_a, tot_b = 0, 0
    a_win, b_win = 0, 0
    a_avoid_win, b_avoid_win = 0, 0

    for i in range(3, n):
        act = eval_records[i][2]
        if act not in ALL_COMBOS: continue
        if target_date and eval_records[i][0] != target_date: continue

        past_sub = eval_records[:i]
        
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

# 백업 상태 관리
if "records" not in st.session_state: st.session_state.records = load_data()
if "history_stack" not in st.session_state: st.session_state.history_stack = []
if "show_bulk" not in st.session_state: st.session_state.show_bulk = False

def push_backup():
    st.session_state.history_stack.append(copy.deepcopy(st.session_state.records))
    if len(st.session_state.history_stack) > 10: st.session_state.history_stack.pop(0)

records = st.session_state.records
records_tuple = tuple((r['date'], r['round'], r['result']) for r in records)

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
        st.cache_data.clear()
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

    # 1. 전체 누적 통계
    all_stat = calculate_ab_stats_cached(records_tuple)
    st.markdown("**전체 누적 통계 (패스 회차 제외)**")
    if all_stat:
        st.markdown(f"🅰️ **A (장줄/퐁당) 추천 적중률 : {all_stat['a_win']}승 {all_stat['a_lose']}패 (승률 {all_stat['a_rate']:.1f}%)**")
        st.markdown(f"   ⚠️ **A 지울 픽 성공률 : {all_stat['a_avoid_win']}승 {all_stat['a_avoid_lose']}패 (승률 {all_stat['a_avoid_rate']:.1f}%)**")
        st.markdown(f"🅱️ **B (박스/계단/데칼) 추천 적중률 : {all_stat['b_win']}승 {all_stat['b_lose']}패 (승률 {all_stat['b_rate']:.1f}%)**")
        st.markdown(f"   ⚠️ **B 지울 픽 성공률 : {all_stat['b_avoid_win']}승 {all_stat['b_avoid_lose']}패 (승률 {all_stat['b_avoid_rate']:.1f}%)**")
    else:
        st.markdown("데이터 축적 중...")

    st.markdown("---")

    # 2. 최근 3000개 누적 통계
    recent_stat = calculate_ab_stats_cached(records_tuple, limit_recent=MAX_DATA_SIZE)
    recent_cnt = min(len(records), MAX_DATA_SIZE)
    st.markdown(f"**최근 {recent_cnt}개 누적 통계 (패스 회차 제외)**")
    if recent_stat:
        st.markdown(f"🅰️ **A (장줄/퐁당) 추천 적중률 : {recent_stat['a_win']}승 {recent_stat['a_lose']}패 (승률 {recent_stat['a_rate']:.1f}%)**")
        st.markdown(f"   ⚠️ **A 지울 픽 성공률 : {recent_stat['a_avoid_win']}승 {recent_stat['a_avoid_lose']}패 (승률 {recent_stat['a_avoid_rate']:.1f}%)**")
        st.markdown(f"🅱️ **B (박스/계단/데칼) 추천 적중률 : {recent_stat['b_win']}승 {recent_stat['b_lose']}패 (승률 {recent_stat['b_rate']:.1f}%)**")
        st.markdown(f"   ⚠️ **B 지울 픽 성공률 : {recent_stat['b_avoid_win']}승 {recent_stat['b_avoid_lose']}패 (승률 {recent_stat['b_avoid_rate']:.1f}%)**")
    else:
        st.markdown("데이터 축적 중...")

    st.markdown("---")

    # 3. 오늘 누적 통계
    try:
        dt_obj = datetime.strptime(curr_date, "%Y-%m-%d")
        w_str = WEEKDAYS[dt_obj.weekday()]
    except Exception:
        w_str = ""

    today_stat = calculate_ab_stats_cached(records_tuple, target_date=curr_date)
    st.markdown(f"**오늘 누적 통계 ({curr_date} {w_str})**")
    if today_stat:
        st.markdown(f"🅰️ **A (장줄/퐁당) 추천 적중률 : {today_stat['a_win']}승 {today_stat['a_lose']}패 (승률 {today_stat['a_rate']:.1f}%)**")
        st.markdown(f"   ⚠️ **A 지울 픽 성공률 : {today_stat['a_avoid_win']}승 {today_stat['a_avoid_lose']}패 (승률 {today_stat['a_avoid_rate']:.1f}%)**")
        st.markdown(f"🅱️ **B (박스/계단/데칼) 추천 적중률 : {today_stat['b_win']}승 {today_stat['b_lose']}패 (승률 {today_stat['b_rate']:.1f}%)**")
        st.markdown(f"   ⚠️ **B 지울 픽 성공률 : {today_stat['b_avoid_win']}승 {today_stat['b_avoid_lose']}패 (승률 {today_stat['b_avoid_rate']:.1f}%)**")
    else:
        st.markdown("데이터 축적 중...")

    st.markdown("---")

    # 4. 직전 회차 결과
    if len(records_tuple) >= 4:
        prev_sub = records_tuple[:-1]
        prev_a_res = analyze_A_engine_tuple(prev_sub)
        prev_b_res = analyze_B_engine_tuple(prev_sub)
        prev_actual = last_rec['result']
        
        st.markdown(f"**직전회차 결과 ( {last_rec['round']}회차 )**")
        if prev_actual == "PASS":
            st.markdown("결과 : **패스(PASS)** ➔ **통계 제외**")
        else:
            act_full = ITEM_FULL_MAP.get(prev_actual, prev_actual)
            
            a_ok = "추천적중 🎯" if prev_a_res and prev_a_res['top'] == prev_actual else "추천미적중"
            a_avoid_ok = "안나옴 성공 🎯" if prev_a_res and prev_a_res['worst'] != prev_actual else "나와버림 ❌"

            b_ok = "추천적중 🎯" if prev_b_res and prev_b_res['top'] == prev_actual else "추천미적중"
            b_avoid_ok = "안나옴 성공 🎯" if prev_b_res and prev_b_res['worst'] != prev_actual else "나와버림 ❌"

            st.markdown(f"실제 결과 : **{prev_actual} ({act_full})**")
            if prev_a_res:
                st.markdown(f"🅰️ **A 추천 ({prev_a_res['top']}) ➔ {a_ok}** / **지울픽 ({prev_a_res['worst']}) ➔ {a_avoid_ok}**")
            if prev_b_res:
                st.markdown(f"🅱️ **B 추천 ({prev_b_res['top']}) ➔ {b_ok}** / **지울픽 ({prev_b_res['worst']}) ➔ {b_avoid_ok}**")

    st.markdown("---")

    # 5. 이번회차 A/B 예측 추천 표출
    curr_a_res = analyze_A_engine_tuple(records_tuple)
    curr_b_res = analyze_B_engine_tuple(records_tuple)

    st.markdown(f"**이번회차 A/B 패턴 분석 ( {next_round}회차 )**")
    
    if curr_a_res:
        st.markdown(f"🅰️ **[A: 장줄/퐁당] 추천: `{curr_a_res['top']}` ({ITEM_FULL_MAP[curr_a_res['top']]})** `확률 {curr_a_res['top_prob']:.1f}%`")
        st.markdown(f"   ⚠️ **지울 픽(안 나올 확률 높음): `{curr_a_res['worst']}` ({ITEM_FULL_MAP[curr_a_res['worst']]})** `확률 {curr_a_res['worst_prob']:.1f}%`")
    
    st.markdown(" ")
    
    if curr_b_res:
        st.markdown(f"🅱️ **[B: 박스/계단/데칼] 추천: `{curr_b_res['top']}` ({ITEM_FULL_MAP[curr_b_res['top']]})** `확률 {curr_b_res['top_prob']:.1f}%`")
        st.markdown(f"   ⚠️ **지울 픽(안 나올 확률 높음): `{curr_b_res['worst']}` ({ITEM_FULL_MAP[curr_b_res['worst']]})** `확률 {curr_b_res['worst_prob']:.1f}%`")

    st.markdown("---")
    st.markdown("**결과 입력**")

    # 🟢 스마트폰 완벽 가로 4등분 HTML/CSS 버튼
    st.markdown("""
    <div class="btn-grid">
        <form action="" method="post" style="display:inline;"><button type="submit" name="input_btn" value="우삼">우삼</button></form>
        <form action="" method="post" style="display:inline;"><button type="submit" name="input_btn" value="우사">우사</button></form>
        <form action="" method="post" style="display:inline;"><button type="submit" name="input_btn" value="좌삼">좌삼</button></form>
        <form action="" method="post" style="display:inline;"><button type="submit" name="input_btn" value="좌사">좌사</button></form>
    </div>
    """, unsafe_allow_html=True)

    # 4등분 버튼 클릭 감지 처리 (쿼리 파라미터 / 폼 제출 대응)
    input_val = None
    for combo in ALL_COMBOS:
        if st.button(combo, key=f"btn_alt_{combo}", use_container_width=True):
            input_val = combo
            break

    if input_val:
        push_backup()
        st.session_state.records.append({'date': curr_date, 'round': next_round, 'result': input_val})
        save_data(st.session_state.records)
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")

    # 🟢 [기능 제어 버튼] 세로(Vertical) 순차 배열
    if st.button("패스", use_container_width=True, key="btn_pass"):
        push_backup()
        st.session_state.records.append({'date': curr_date, 'round': next_round, 'result': "PASS"})
        save_data(st.session_state.records)
        st.cache_data.clear()
        st.toast(f"{next_round}회차 패스")
        st.rerun()

    if st.button("직전취소", use_container_width=True, key="btn_cancel"):
        if st.session_state.records:
            push_backup()
            st.session_state.records.pop()
            save_data(st.session_state.records)
            st.cache_data.clear()
            st.rerun()

    if st.button("초기화", use_container_width=True, key="btn_reset"):
        push_backup()
        st.session_state.records = []
        if os.path.exists(DATA_FILE): os.remove(DATA_FILE)
        st.cache_data.clear()
        st.rerun()

    if st.button("되돌리기", use_container_width=True, key="btn_undo"):
        if st.session_state.history_stack:
            st.session_state.records = st.session_state.history_stack.pop()
            save_data(st.session_state.records)
            st.cache_data.clear()
            st.rerun()

    st.markdown("---")

    # 6. 당일 세부 결과 전체 표출
    st.markdown("**오늘 세부 결과 (A/B 적중 리스트)**")
    if len(records_tuple) >= 4:
        rows = []
        today_indices = [idx for idx, r in enumerate(records_tuple) if r[0] == curr_date]
        
        for i in reversed(today_indices):
            if i < 3: continue
            p_sub = records_tuple[:i]
            res_a_prev = analyze_A_engine_tuple(p_sub)
            res_b_prev = analyze_B_engine_tuple(p_sub)
            act_item = records_tuple[i][2]
            rd_num = records_tuple[i][1]
            
            if act_item == "PASS":
                continue

            act_full = ITEM_FULL_MAP.get(act_item, act_item)

            a_match = "적중 🎯" if res_a_prev and res_a_prev['top'] == act_item else "미적중"
            b_match = "적중 🎯" if res_b_prev and res_b_prev['top'] == act_item else "미적중"

            rows.append({
                "회차": f"{rd_num}회",
                "실제 결과": f"{act_item} ({act_full})",
                "A 추천/지울픽": f"{res_a_prev['top']} / {res_a_prev['worst']}" if res_a_prev else "-",
                "A 적중": a_match,
                "B 추천/지울픽": f"{res_b_prev['top']} / {res_b_prev['worst']}" if res_b_prev else "-",
                "B 적중": b_match
            })
        
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, hide_index=True, use_container_width=True)
        else:
            st.markdown("오늘 유효한 회차가 없습니다.")
