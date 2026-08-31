import os
import re
import copy
import pandas as pd
import streamlit as st
from datetime import datetime

# 페이지 기본 설정
st.set_page_config(page_title="키노사다리 구멍분석기", page_icon="📊", layout="centered")

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

ITEM_MAP = {
    '우사': ('우', '사', '짝'),
    '우삼': ('우', '삼', '홀'),
    '좌사': ('좌', '사', '홀'),
    '좌삼': ('좌', '삼', '짝')
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

# [회차 길이에 따른 가중치 보완된] 4대 패턴 분석 함수
def analyze_pure_pattern(stream, val1, val2):
    n = len(stream)
    if n < 4:
        return "-", 50.0, "관망(패스)"

    # 1. 🔥 장줄 구간 (3연속 이상)
    if stream[-1] == stream[-2] == stream[-3]:
        rec = stream[-1]
        streak = 3
        for idx in range(4, min(n + 1, 10)):
            if stream[-idx] == rec:
                streak += 1
            else:
                break
        prob = min(68.0 + (streak * 3.5), 92.0)
        return rec, prob, f"🔥 {rec} 장줄({streak}연속)"

    # 2. ⚡ 퐁당 구간 (연속 꺾임 깊이 가중치 적용)
    if stream[-1] != stream[-2] and stream[-2] != stream[-3]:
        streak = 3
        for idx in range(4, min(n + 1, 10)):
            if stream[-idx + 1] != stream[-idx]:
                streak += 1
            else:
                break
        opp_val = val2 if stream[-1] == val1 else val1
        prob = min(72.0 + (streak * 2.0), 90.0)
        return opp_val, prob, f"⚡ 퐁당({streak}회 지속)"

    # 3. 📦 투박스(2-2) / 삼박스(3-3) 패턴 (누적 회차 깊이 반영)
    if n >= 4:
        # 투박스 진행 시점 (2개-2개 패턴 중 1개 나온 시점 ➔ 2개째 채우기)
        if stream[-2] == stream[-3] and stream[-1] != stream[-2]:
            streak = 3
            # 과거 투박스 리듬 연속성 스캔
            for idx in range(4, min(n, 12)):
                if (idx % 2 == 1 and stream[-idx] == stream[-idx+1]) or (idx % 2 == 0 and stream[-idx] != stream[-idx+1]):
                    streak += 1
                else:
                    break
            same_val = stream[-1]
            prob = min(73.0 + (streak * 2.0), 92.0)
            return same_val, prob, f"📦 투박스 진행({streak}회차 유지)"

        # 투박스 완료 시점 (2개-2개 완성 후 꺾기)
        elif stream[-3] == stream[-4] and stream[-1] == stream[-2] and stream[-1] != stream[-3]:
            opp_val = val2 if stream[-1] == val1 else val1
            return opp_val, 76.0, "📦 투박스 완료(꺾기)"

    # 4. 📶 계단 패턴 (1-2-3 / 3-2-1)
    if n >= 6:
        if stream[-1] == stream[-2] and stream[-2] != stream[-3] and stream[-3] == stream[-4] and stream[-4] != stream[-5]:
            same_val = stream[-1]
            return same_val, 77.0, "📶 123 계단(이음)"
        elif stream[-1] == stream[-2] == stream[-3] and stream[-3] != stream[-4] and stream[-4] == stream[-5] and stream[-5] != stream[-6]:
            opp_val = val2 if stream[-1] == val1 else val1
            return opp_val, 76.0, "📶 123 계단(꺾기)"
        elif stream[-1] == stream[-2] and stream[-2] != stream[-3] and stream[-3] == stream[-4] == stream[-5]:
            opp_val = val2 if stream[-1] == val1 else val1
            return opp_val, 75.0, "📶 321 계단(꺾기)"

    return "-", 50.0, "⚠️ 조건미부합(패스)"

# 메인 예측 분석 함수
def analyze_prediction(records):
    valid_records = [r for r in records if r['result'] in ITEM_MAP][-MAX_DATA_SIZE:]
    if len(valid_records) < 4:
        return None

    s_stream = [ITEM_MAP[r['result']][0] for r in valid_records]
    l_stream = [ITEM_MAP[r['result']][1] for r in valid_records]
    o_stream = [ITEM_MAP[r['result']][2] for r in valid_records]

    rec_s, prob_s, pat_s = analyze_pure_pattern(s_stream, '우', '좌')
    rec_l, prob_l, pat_l = analyze_pure_pattern(l_stream, '사', '삼')
    rec_o, prob_o, pat_o = analyze_pure_pattern(o_stream, '짝', '홀')

    indicators = []
    if rec_s != "-": indicators.append(('출발', rec_s, prob_s, pat_s))
    if rec_l != "-": indicators.append(('줄수', rec_l, prob_l, pat_l))
    if rec_o != "-": indicators.append(('홀짝', rec_o, prob_o, pat_o))

    if len(indicators) >= 2:
        indicators.sort(key=lambda x: x[2], reverse=True)
        top1, top2 = indicators[0], indicators[1]
        top_combination_str = f"🔥 [{top1[0]}:{top1[1]}] + [{top2[0]}:{top2[1]}]"
        status_text = f"🎯 핵심 구멍 감지 [{top1[0]}:{top1[3]} | {top2[0]}:{top2[3]}]"
    elif len(indicators) == 1:
        top1 = indicators[0]
        top2 = None
        top_combination_str = f"🔥 [{top1[0]}:{top1[1]}] (단독 추천)"
        status_text = f"🎯 핵심 구멍 감지 [{top1[0]}:{top1[3]}]"
    else:
        top1, top2 = None, None
        top_combination_str = "관망 (패스 추천)"
        status_text = "⚠️ 전 구멍 패턴 미성립 ➔ 관망 권장"

    return {
        'rec_s': rec_s, 'prob_s': prob_s, 'pat_s': pat_s,
        'rec_l': rec_l, 'prob_l': prob_l, 'pat_l': pat_l,
        'rec_o': rec_o, 'prob_o': prob_o, 'pat_o': pat_o,
        'top1': top1, 'top2': top2,
        'top_combination': top_combination_str,
        'status': status_text
    }

def calculate_detailed_stats(records, target_date=None, limit_recent=None):
    if limit_recent:
        eval_records = records[-limit_recent:]
    else:
        eval_records = records

    n = len(eval_records)
    if n < 5:
        return None

    tot_count = 0
    c_win, s_win, l_win, o_win = 0, 0, 0, 0

    for i in range(4, n):
        act = eval_records[i]['result']
        if act not in ITEM_MAP:
            continue

        if target_date and eval_records[i]['date'] != target_date:
            continue

        past_sub = eval_records[:i]
        pred = analyze_prediction(past_sub)
        if pred and (pred['top1'] is not None):
            act_s, act_l, act_o = ITEM_MAP[act]
            
            tot_count += 1
            s_ok = (pred['rec_s'] == act_s) if pred['rec_s'] != "-" else False
            l_ok = (pred['rec_l'] == act_l) if pred['rec_l'] != "-" else False
            o_ok = (pred['rec_o'] == act_o) if pred['rec_o'] != "-" else False
            
            t1_val = pred['top1'][1]
            t1_name = pred['top1'][0]
            t1_ok = (t1_val == act_s) if t1_name == '출발' else ((t1_val == act_l) if t1_name == '줄수' else (t1_val == act_o))
            
            if pred['top2']:
                t2_val = pred['top2'][1]
                t2_name = pred['top2'][0]
                t2_ok = (t2_val == act_s) if t2_name == '출발' else ((t2_val == act_l) if t2_name == '줄수' else (t2_val == act_o))
            else:
                t2_ok = False
            
            if t1_ok or t2_ok:
                c_win += 1
            if s_ok: s_win += 1
            if l_ok: l_win += 1
            if o_ok: o_win += 1

    if tot_count == 0:
        return None

    return {
        'total': tot_count,
        'c_win': c_win, 'c_lose': tot_count - c_win, 'c_rate': (c_win/tot_count)*100.0 if tot_count>0 else 0.0,
        's_win': s_win, 's_lose': tot_count - s_win, 's_rate': (s_win/tot_count)*100.0 if tot_count>0 else 0.0,
        'l_win': l_win, 'l_lose': tot_count - l_win, 'l_rate': (l_win/tot_count)*100.0 if tot_count>0 else 0.0,
        'o_win': o_win, 'o_lose': tot_count - o_win, 'o_rate': (o_win/tot_count)*100.0 if tot_count>0 else 0.0,
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
    st.markdown("글자 사이 공백, 줄바꿈, 회차 구분 상관없이 `우사`, `우삼`, `좌사`, `좌삼` 문자를 자동으로 찾아 연속 등록합니다.")
    
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

    # 1. 전체 누적 통계
    all_stat = calculate_detailed_stats(records)
    st.markdown("**전체 누적 통계 (패스 회차 제외)**")
    if all_stat:
        st.markdown(f"추천 적중 : {all_stat['total']}개 / {all_stat['c_win']}승 {all_stat['c_lose']}패 / 승율 {all_stat['c_rate']:.1f}%")
        st.markdown(f"출발 : {all_stat['s_win']}승 {all_stat['s_lose']}패 ({all_stat['s_rate']:.1f}%) | 줄수 : {all_stat['l_win']}승 {all_stat['l_lose']}패 ({all_stat['l_rate']:.1f}%) | 홀짝 : {all_stat['o_win']}승 {all_stat['o_lose']}패 ({all_stat['o_rate']:.1f}%)")
    else:
        st.markdown("데이터 축적 중...")

    st.markdown("---")

    # 2. 최근 3000개 누적 통계
    recent_stat = calculate_detailed_stats(records, limit_recent=MAX_DATA_SIZE)
    recent_cnt = min(len(records), MAX_DATA_SIZE)
    st.markdown(f"**최근 {recent_cnt}개 누적 통계 (패스 회차 제외)**")
    if recent_stat:
        st.markdown(f"추천 적중 : {recent_stat['total']}개 / {recent_stat['c_win']}승 {recent_stat['c_lose']}패 / 승율 {recent_stat['c_rate']:.1f}%")
        st.markdown(f"출발 : {recent_stat['s_win']}승 {recent_stat['s_lose']}패 ({recent_stat['s_rate']:.1f}%) | 줄수 : {recent_stat['l_win']}승 {recent_stat['l_lose']}패 ({recent_stat['l_rate']:.1f}%) | 홀짝 : {recent_stat['o_win']}승 {recent_stat['o_lose']}패 ({recent_stat['o_rate']:.1f}%)")
    else:
        st.markdown("데이터 축적 중...")

    st.markdown("---")

    # 3. 오늘 통계
    try:
        dt_obj = datetime.strptime(curr_date, "%Y-%m-%d")
        w_str = WEEKDAYS[dt_obj.weekday()]
    except Exception:
        w_str = ""

    today_stat = calculate_detailed_stats(records, target_date=curr_date)
    st.markdown(f"**오늘 : {curr_date} {w_str}**")
    if today_stat:
        st.markdown(f"추천 적중 : {today_stat['total']}개 / {today_stat['c_win']}승 {today_stat['c_lose']}패 / 승율 {today_stat['c_rate']:.1f}%")
        st.markdown(f"출발 : {today_stat['s_win']}승 {today_stat['s_lose']}패 ({today_stat['s_rate']:.1f}%) | 줄수 : {today_stat['l_win']}승 {today_stat['l_lose']}패 ({today_stat['l_rate']:.1f}%) | 홀짝 : {today_stat['o_win']}승 {today_stat['o_lose']}패 ({today_stat['o_rate']:.1f}%)")
    else:
        st.markdown("데이터 축적 중...")

    st.markdown("---")

    # 4. 이전 회차 분석
    if len(records) >= 5:
        prev_sub = records[:-1]
        prev_pred = analyze_prediction(prev_sub)
        prev_actual = last_rec['result']
        
        if prev_actual == "PASS":
            st.markdown(f"**이전회차 ( {last_rec['round']}회차 )**")
            st.markdown(f"결과 : **패스(PASS)** ➔ **통계 제외**")
        elif prev_pred and prev_pred['top1']:
            act_s, act_l, act_o = ITEM_MAP[prev_actual]
            t1_val = prev_pred['top1'][1]
            t1_name = prev_pred['top1'][0]
            
            t1_ok = (t1_val == act_s) if t1_name == '출발' else ((t1_val == act_l) if t1_name == '줄수' else (t1_val == act_o))
            if prev_pred['top2']:
                t2_val = prev_pred['top2'][1]
                t2_name = prev_pred['top2'][0]
                t2_ok = (t2_val == act_s) if t2_name == '출발' else ((t2_val == act_l) if t2_name == '줄수' else (t2_val == act_o))
            else:
                t2_ok = False
                
            c_res = "성공" if (t1_ok or t2_ok) else "실패"
            
            st.markdown(f"**이전회차 ( {last_rec['round']}회차 )**")
            st.markdown(f"결과 : **{prev_actual} ({act_o})** / 예측 : **{prev_pred['top_combination']}** ➔ **{c_res}**")
        else:
            st.markdown(f"**이전회차 ( {last_rec['round']}회차 )**")
            st.markdown(f"결과 : **{prev_actual}** / 예측 : **관망(패스)**")
    st.markdown("---")

    # 5. 이번회차 독립 예측 표출
    curr_pred = analyze_prediction(records)
    if curr_pred:
        st.markdown(f"**구간 : {curr_pred['status']}**")
        st.markdown("---")
        st.markdown(f"**이번회차 독립 구멍 예측 ( {next_round}회차 )**")
        st.markdown(f"출발 : **{curr_pred['rec_s']}** `{curr_pred['prob_s']:.1f}%` ({curr_pred['pat_s']})")
        st.markdown(f"줄수 : **{curr_pred['rec_l']}** `{curr_pred['prob_l']:.1f}%` ({curr_pred['pat_l']})")
        st.markdown(f"홀짝 : **{curr_pred['rec_o']}** `{curr_pred['prob_o']:.1f}%` ({curr_pred['pat_o']})")
        st.markdown(f"🎯 **최고 확률 추천 구멍 : {curr_pred['top_combination']}**")
    else:
        st.markdown("**구간 : 분석 데이터 부족**")
        st.markdown("---")
        st.markdown(f"**이번회차예측 ( {next_round}회차 )**\n데이터 축적 중...")

    st.markdown("---")
    st.markdown("**결과 입력**")

    # 결과 입력 버튼 (4개)
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

    # 제어 버튼 (4개)
    m1, m2, m3, m4 = st.columns(4)
    if m1.button("패스", use_container_width=True):
        push_backup()
        st.session_state.records.append({'date': curr_date, 'round': next_round, 'result': "PASS"})
        save_data(st.session_state.records)
        st.toast(f"{next_round}회차 패스 처리 완료")
        st.rerun()

    if m2.button("직전취소", use_container_width=True):
        if st.session_state.records:
            push_backup()
            st.session_state.records.pop()
            save_data(st.session_state.records)
            st.toast("직전회차 취소")
            st.rerun()

    if m3.button("초기화", use_container_width=True):
        push_backup()
        st.session_state.records = []
        if os.path.exists(DATA_FILE): os.remove(DATA_FILE)
        st.toast("초기화 완료")
        st.rerun()

    if m4.button("되돌리기", use_container_width=True):
        if st.session_state.history_stack:
            st.session_state.records = st.session_state.history_stack.pop()
            save_data(st.session_state.records)
            st.toast("되돌리기 완료!")
            st.rerun()

    st.markdown("---")

    # 6. 세부 결과 표 (당일 최신순 정렬)
    st.markdown("**세부 결과**")
    if len(records) >= 5:
        rows = []
        today_indices = [idx for idx, r in enumerate(records) if r['date'] == curr_date]
        
        for i in reversed(today_indices):
            if i < 4:
                continue
            p_sub = records[:i]
            pr = analyze_prediction(p_sub)
            act_item = records[i]['result']
            rd_num = records[i]['round']
            
            if act_item == "PASS":
                rows.append({
                    "회차": f"{rd_num}회",
                    "실제 결과": "패스 (PASS)",
                    "추천 구멍": "-",
                    "적중 여부": "통계 제외"
                })
            elif pr:
                act_s, act_l, act_o = ITEM_MAP[act_item]
                if pr['top1']:
                    t1_val = pr['top1'][1]
                    t1_name = pr['top1'][0]
                    t1_ok = (t1_val == act_s) if t1_name == '출발' else ((t1_val == act_l) if t1_name == '줄수' else (t1_val == act_o))
                    if pr['top2']:
                        t2_val = pr['top2'][1]
                        t2_name = pr['top2'][0]
                        t2_ok = (t2_val == act_s) if t2_name == '출발' else ((t2_val == act_l) if t2_name == '줄수' else (t2_val == act_o))
                    else:
                        t2_ok = False
                    c_chk = "성공" if (t1_ok or t2_ok) else "실패"
                else:
                    c_chk = "관망(패스)"
                
                rows.append({
                    "회차": f"{rd_num}회",
                    "실제 결과": f"{act_item} ({act_o})",
                    "추천 구멍": pr['top_combination'],
                    "적중 여부": c_chk
                })
        
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, hide_index=True, use_container_width=True)
        else:
            st.markdown("오늘 세부 결과 기록 없음")
    else:
        st.markdown("기록 축적 중...")
