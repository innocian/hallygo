import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium

st.set_page_config(
    page_title='남도 감성 여행 · 전남 관광 대시보드',
    page_icon='🌿',
    layout='wide',
    initial_sidebar_state='expanded'
)

# 감성적인 여행·관광 테마 커스텀 CSS 적용
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Pretendard:wght@300;400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, sans-serif;
    }
    
    /* 메인 배경 톤 */
    .stApp {
        background: linear-gradient(180deg, #fbfbfa 0%, #f4f6f8 100%);
    }

    /* 사이드바 스타일링 */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #ffffff 0%, #f7fafc 100%);
        border-right: 1px solid #e9ecef;
    }

    /* 헤더 히어로 배너 */
    .hero-header {
        background: linear-gradient(135deg, #0f766e 0%, #0284c7 60%, #38bdf8 100%);
        padding: 2.2rem 2.5rem;
        border-radius: 18px;
        color: white;
        margin-bottom: 1.8rem;
        box-shadow: 0 10px 25px -5px rgba(15, 118, 110, 0.25);
    }
    .hero-title {
        font-size: 2.2rem;
        font-weight: 700;
        letter-spacing: -0.02em;
        margin: 0;
        display: flex;
        align-items: center;
        gap: 0.6rem;
    }
    .hero-sub {
        font-size: 1.05rem;
        font-weight: 300;
        opacity: 0.92;
        margin-top: 0.6rem;
        line-height: 1.5;
    }

    /* 메트릭 카드 감성 스타일 */
    [data-testid="stMetric"] {
        background: white;
        padding: 1.2rem 1.4rem;
        border-radius: 14px;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.04);
        border: 1px solid #f1f3f5;
        border-top: 4px solid #0f766e;
    }
    [data-testid="stMetricLabel"] {
        color: #64748b;
        font-size: 0.92rem;
        font-weight: 500;
    }
    [data-testid="stMetricValue"] {
        color: #0f172a;
        font-size: 1.9rem;
        font-weight: 700;
    }

    /* 탭 디자인 정돈 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 48px;
        background-color: white;
        border-radius: 10px 10px 0 0;
        border: 1px solid #e2e8f0;
        border-bottom: none;
        padding: 0 20px;
        font-weight: 600;
        color: #475569;
    }
    .stTabs [aria-selected="true"] {
        background-color: #0f766e !important;
        color: white !important;
        border-color: #0f766e !important;
    }

    /* 다운로드 버튼 여행 스타일 */
    div.stDownloadButton > button {
        background: linear-gradient(135deg, #0f766e 0%, #0d9488 100%);
        color: white;
        border: none;
        border-radius: 10px;
        padding: 0.6rem 1.4rem;
        font-weight: 600;
        box-shadow: 0 4px 12px rgba(15, 118, 110, 0.2);
        transition: all 0.2s ease;
    }
    div.stDownloadButton > button:hover {
        background: linear-gradient(135deg, #115e59 0%, #0f766e 100%);
        box-shadow: 0 6px 16px rgba(15, 118, 110, 0.35);
        transform: translateY(-1px);
    }
</style>
""", unsafe_allow_html=True)

# 감성 헤더 영역
st.markdown("""
<div class="hero-header">
    <div class="hero-title">🌿 푸른 바다와 자연의 쉼표, 전라남도 여행</div>
    <div class="hero-sub">청정 남도의 다채로운 관광 명소, 미식, 힐링 코스를 한눈에 살펴보는 여행 큐레이션 대시보드입니다.</div>
</div>
""", unsafe_allow_html=True)

TYPE_NAMES = {
    '12': '관광지', '14': '문화시설',
    '25': '여행코스', '28': '레포츠', '32': '숙박',
    '38': '쇼핑', '39': '음식점'
}

SIGUNGU = [
    '목포시', '여수시', '순천시', '나주시', '광양시',
    '담양군', '곡성군', '구례군', '고흥군', '보성군',
    '화순군', '장흥군', '강진군', '해남군', '영암군',
    '무안군', '함평군', '영광군', '장성군', '완도군',
    '진도군', '신안군'
]

# 관광 정보 API: 페이지별 수집 후 1시간 동안 캐시
@st.cache_data(ttl=3600)
def load_data():
    url = 'https://apis.data.go.kr/B551011/KorService2/areaBasedList2'
    params = {
        'serviceKey': st.secrets['TOUR_API_KEY'],
        'MobileOS': 'ETC',
        'MobileApp': 'TourDashboard',
        '_type': 'json',
        'areaCode': 38,
        'numOfRows': 1000,
        'pageNo': 1
    }

    rows = []
    while True:
        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()['response']
        if data['header']['resultCode'] != '0000':
            raise RuntimeError(data['header']['resultMsg'])

        body = data['body']
        items = body.get('items')
        if not items:
            break

        item = items['item']
        if isinstance(item, dict):
            item = [item]
        rows.extend(item)

        if len(rows) >= int(body['totalCount']):
            break
        params['pageNo'] += 1

    return pd.DataFrame(rows)


try:
    df = load_data()
    print(df[['mapy', 'mapx']].dtypes)
except Exception as e:
    st.error('관광 데이터를 불러오지 못했습니다: ' + str(e))
    st.stop()

if df.empty:
    st.info('조회된 관광 데이터가 없습니다.')
    st.stop()

# 관광지 데이터 전처리
columns = ['title', 'addr1', 'contenttypeid', 'mapy', 'mapx', 'tel']
df = df.reindex(columns=columns).copy()
df['contenttypeid'] = df['contenttypeid'].astype(str)
df = df[df['contenttypeid'] != '15'].copy()
df['관광유형'] = df['contenttypeid'].map(TYPE_NAMES).fillna('기타')
df['시군'] = df['addr1'].fillna('').str.split().str[1]
df['시군'] = df['시군'].where(df['시군'].isin(SIGUNGU), '미분류')
df['mapy'] = pd.to_numeric(df['mapy'], errors='coerce')
df['mapx'] = pd.to_numeric(df['mapx'], errors='coerce')

# 사이드바 검색 조건
with st.sidebar:
    st.markdown("### 🧭 어디로 떠나볼까요?")
    st.caption("원하는 지역과 테마를 골라 맞춤 여행지를 찾아보세요.")
    selected_sigungu = st.selectbox('📍 시·군 선택', ['전체'] + sorted(SIGUNGU))
    selected_type = st.selectbox('🏷️ 관광 테마', ['전체'] + list(TYPE_NAMES.values()) + ['기타'])
    keyword = st.text_input('🔍 여행지명 검색', placeholder='예: 오동도, 죽녹원')
    st.markdown("---")
    st.caption("자료 출처: 한국관광공사 TourAPI 4.0")

p = df.copy()
if selected_sigungu != '전체':
    p = p[p['시군'] == selected_sigungu]
if selected_type != '전체':
    p = p[p['관광유형'] == selected_type]
if keyword:
    p = p[p['title'].fillna('').str.contains(keyword, case=False, regex=False)]

st.caption('✨ 한국관광공사 TourAPI 연동 · 1시간 자동 캐시 갱신')
c1, c2, c3 = st.columns(3)
c1.metric('🏞️ 여행지 보유 시·군', f"{p[p['시군'] != '미분류']['시군'].nunique()}곳")
c2.metric('📍 탐색된 명소 수', f"{len(p):,}개")
c3.metric('🏷️ 관광 테마 카테고리', f"{p['관광유형'].nunique()}종류")

st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(['📊 여행 트렌드 & 통계', '🗺️ 감성 여행 지도', '📋 추천 관광 명소 목록'])

# 감성적인 에메랄드/오션/노을 컬러 팔레트
TRAVEL_COLORS = ['#0f766e', '#0284c7', '#06b6d4', '#f59e0b', '#f97316', '#10b981', '#8b5cf6', '#ec4899']

with tab1:
    left, right = st.columns(2)
    with left:
        st.subheader('📍 시·군별 인기 명소 분포')
        count = p[p['시군'] != '미분류']['시군'].value_counts()
        if not count.empty:
            fig = px.bar(
                x=count.index,
                y=count.values,
                labels={'x': '지역(시·군)', 'y': '등록 명소 수'},
                color=count.values,
                color_continuous_scale='Teal'
            )
            fig.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(family='Pretendard, sans-serif', color='#334155'),
                coloraxis_showscale=False,
                margin=dict(l=20, r=20, t=30, b=30)
            )
            fig.update_xaxes(showgrid=False)
            fig.update_yaxes(gridcolor='#f1f5f9')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info('표시할 관광 데이터가 없습니다.')

    with right:
        st.subheader('🏷️ 여행 테마별 구성비')
        count = p['관광유형'].value_counts()
        if not count.empty:
            fig = px.pie(
                names=count.index,
                values=count.values,
                hole=0.45,
                color_discrete_sequence=TRAVEL_COLORS
            )
            fig.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(family='Pretendard, sans-serif', color='#334155'),
                legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5),
                margin=dict(l=20, r=20, t=30, b=50)
            )
            fig.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info('표시할 관광 데이터가 없습니다.')

with tab2:
    st.subheader('🗺️ 감성 남도 맵 둘러보기')
    geo = p.dropna(subset=['mapy', 'mapx'])
    # 한국 주변을 벗어난 잘못된 좌표 제외
    geo = geo[(geo['mapy'] >= 33) & (geo['mapy'] <= 36) &
              (geo['mapx'] >= 125) & (geo['mapx'] <= 129)]

    if geo.empty:
        st.info('지도에 표시할 관광지가 없습니다.')
    else:
        m = folium.Map(
            location=[geo['mapy'].median(), geo['mapx'].median()],
            zoom_start=10
        )
        cluster = MarkerCluster().add_to(m)
        for i, row in geo.iterrows():
            popup_html = f"""
            <div style="font-family: 'Pretendard', sans-serif; min-width: 170px; padding: 4px;">
                <span style="font-size: 11px; color: #0f766e; font-weight: 700; background: #ccfbf1; padding: 2px 7px; border-radius: 9999px;">
                    {row.get('관광유형', '명소')}
                </span>
                <h4 style="margin: 7px 0 4px 0; color: #0f172a; font-size: 14px; font-weight: 700;">{row['title']}</h4>
                <p style="margin: 0; font-size: 12px; color: #64748b; line-height: 1.4;">{row['addr1'] if pd.notna(row['addr1']) else ''}</p>
                {f'<p style="margin: 4px 0 0 0; font-size: 11px; color: #0284c7;">📞 {row["tel"]}</p>' if pd.notna(row.get('tel')) and row['tel'] else ''}
            </div>
            """
            folium.Marker(
                location=[row['mapy'], row['mapx']],
                tooltip=str(row['title']),
                popup=folium.Popup(popup_html, max_width=260),
                icon=folium.Icon(color='cadetblue', icon='info-sign')
            ).add_to(cluster)
            
        st.markdown(f"총 **{len(geo):,}개**의 명소가 지도에 표시되었습니다. 마커를 클릭해 명소 이름과 정보를 확인해보세요.")
        st_folium(m, height=600, use_container_width=True, returned_objects=[])

with tab3:
    st.subheader('📋 상세 명소 & 편의정보')
    if p.empty:
        st.info('조건에 맞는 관광지가 없습니다.')
    else:
        view = p[['title', '시군', '관광유형', 'addr1', 'tel']].copy()
        view = view.rename(columns={
            'title': '관광지명',
            'addr1': '주소',
            'tel': '전화번호'
            }
        )

        st.dataframe(view, use_container_width=True, hide_index=True)
        st.download_button(
            '📥 전남 여행지 목록 다운로드 (CSV)',
            view.to_csv(index=False).encode('utf-8-sig'),
            file_name='jeonnam_tourism.csv',
            mime='text/csv'
        )