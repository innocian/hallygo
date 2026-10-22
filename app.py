import html
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import folium
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium

# ──────────────────────────────────────────────────────────────
# 기본 설정
# ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="전라남도 관광 대시보드", page_icon="🌊", layout="wide")

BASE_URL = "https://apis.data.go.kr/B551011/KorService2"
AREA_CODE_JEONNAM = "38"          # 전라남도 areaCode
FESTIVAL_YEAR = 2026
PAGE_SIZE = 500
TOTAL_SIGUNGU = 22                # 전라남도 시·군 수 (시 5 + 군 17)
KST = ZoneInfo("Asia/Seoul")

# contentTypeId → (표시명, 색상)
TYPE_META = {
    "12": ("관광지", "#0E7C86"),
    "14": ("문화시설", "#7B5EA7"),
    "15": ("축제·행사", "#E4572E"),
    "25": ("여행코스", "#3BB273"),
    "28": ("레포츠", "#F2A541"),
    "32": ("숙박", "#4A6FA5"),
    "38": ("쇼핑", "#D96C9B"),
    "39": ("음식점", "#8C6A4F"),
}
TYPE_COLORS = {name: color for name, color in TYPE_META.values()}
TYPE_COLORS["기타"] = "#9AA5B1"

STATUS_COLORS = {"진행중": "#E4572E", "예정": "#0E7C86", "종료": "#B0B8C1", "일정 미정": "#9AA5B1"}
INK = "#1F2A37"
MUTED = "#6B7785"
BRAND = "#0E7C86"

CSS = """
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
html, body, [class*="css"], .stApp { font-family: 'Pretendard', -apple-system, sans-serif; }
#MainMenu, footer { visibility: hidden; }
.block-container { padding-top: 2rem; max-width: 1280px; }

.hero {
  background: linear-gradient(135deg, #0E7C86 0%, #0B5560 55%, #093E47 100%);
  border-radius: 20px; padding: 28px 32px; color: #fff; margin-bottom: 18px;
  box-shadow: 0 10px 30px rgba(14,124,134,.25);
}
.hero h1 { font-size: 1.9rem; margin: 0 0 6px 0; font-weight: 800; }
.hero p { margin: 0; opacity: .85; font-size: .95rem; }

.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-bottom: 10px; }
.kpi {
  background: #fff; border: 1px solid #E6EBF0; border-radius: 16px; padding: 16px 18px;
  box-shadow: 0 2px 8px rgba(15,23,42,.04); border-top: 4px solid var(--c, #0E7C86);
}
.kpi .label { color: #6B7785; font-size: .82rem; }
.kpi .value { color: #1F2A37; font-size: 1.7rem; font-weight: 800; margin-top: 4px; }
.kpi .sub { color: #6B7785; font-size: .78rem; margin-top: 2px; }

.section-title { font-size: 1.05rem; font-weight: 700; color: #1F2A37; margin: 18px 0 4px; }
.section-desc { color: #6B7785; font-size: .85rem; margin-bottom: 8px; }
div[data-testid="stTabs"] button { font-weight: 600; }
</style>
"""


# ──────────────────────────────────────────────────────────────
# TourAPI 호출
# ──────────────────────────────────────────────────────────────
def _api_get(endpoint: str, params: dict) -> dict:
    """TourAPI 호출 (재시도 포함). 응답의 body 부분을 반환."""
    query = {
        "serviceKey": st.secrets["TOUR_API_KEY"],   # 디코딩된 인증키
        "MobileOS": "ETC",
        "MobileApp": "JeonnamTourDash",
        "_type": "json",
        **params,
    }
    last_err = None
    for attempt in range(3):
        try:
            res = requests.get(f"{BASE_URL}/{endpoint}", params=query, timeout=15)
            res.raise_for_status()
            body = res.json()["response"]
            header = body["header"]
            if header["resultCode"] != "0000":
                raise RuntimeError(f"{endpoint} 오류: {header.get('resultMsg')}")
            return body["body"]
        except (requests.RequestException, KeyError, ValueError, RuntimeError) as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{endpoint} 호출 실패: {last_err}")


def _fetch_all(endpoint: str, params: dict) -> list[dict]:
    """페이지네이션을 돌며 전체 항목을 수집."""
    rows, page = [], 1
    while True:
        body = _api_get(endpoint, {**params, "numOfRows": PAGE_SIZE, "pageNo": page})
        items = body.get("items")
        if not items:  # 결과 없음은 빈 문자열로 옴
            break
        item = items.get("item", [])
        if isinstance(item, dict):  # 결과가 1건이면 dict로 옴
            item = [item]
        rows.extend(item)
        if len(rows) >= int(body.get("totalCount", 0)) or not item:
            break
        page += 1
    return rows


@st.cache_data(ttl=3600, show_spinner="전라남도 관광 데이터를 불러오는 중입니다…")
def load_places() -> pd.DataFrame:
    rows = _fetch_all("areaBasedList2", {"areaCode": AREA_CODE_JEONNAM, "arrange": "A"})
    return pd.DataFrame(rows)


@st.cache_data(ttl=3600, show_spinner=False)
def load_festivals() -> pd.DataFrame:
    rows = _fetch_all(
        "searchFestival2",
        {
            "areaCode": AREA_CODE_JEONNAM,
            "eventStartDate": f"{FESTIVAL_YEAR}0101",
            "eventEndDate": f"{FESTIVAL_YEAR}1231",
            "arrange": "A",
        },
    )
    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────
# 전처리
# ──────────────────────────────────────────────────────────────
COLUMNS = [
    "contentid", "contenttypeid", "title", "addr1", "tel", "firstimage",
    "mapx", "mapy", "modifiedtime", "eventstartdate", "eventenddate",
]
SIGUNGU_RE = re.compile(r"전라남도\s+(\S+?[시군])")


def extract_sigungu(addr) -> str:
    m = SIGUNGU_RE.search(addr if isinstance(addr, str) else "")
    return m.group(1) if m else "미분류"


def _clean_image(series: pd.Series) -> pd.Series:
    return series.where(series.fillna("") != "")


def prepare_places(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reindex(columns=COLUMNS).copy()
    df["contenttypeid"] = df["contenttypeid"].astype(str)
    # 축제(15)는 searchFestival2 결과로만 다뤄 중복 집계를 막음
    df = df[df["contenttypeid"] != "15"]
    df["type"] = df["contenttypeid"].map(lambda c: TYPE_META.get(c, ("기타", ""))[0])
    df["sigungu"] = df["addr1"].map(extract_sigungu)
    df["lat"] = pd.to_numeric(df["mapy"], errors="coerce")
    df["lng"] = pd.to_numeric(df["mapx"], errors="coerce")
    df["image"] = _clean_image(df["firstimage"])
    df["tel"] = df["tel"].fillna("").map(lambda x: x or "-")
    df["modified"] = pd.to_datetime(df["modifiedtime"], format="%Y%m%d%H%M%S", errors="coerce")
    return df


def event_status(start, end, today) -> str:
    if pd.isna(start) or pd.isna(end):
        return "일정 미정"
    if end < today:
        return "종료"
    if start > today:
        return "예정"
    return "진행중"


def prepare_festivals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reindex(columns=COLUMNS).copy()
    df["start"] = pd.to_datetime(df["eventstartdate"].astype(str), format="%Y%m%d", errors="coerce")
    df["end"] = pd.to_datetime(df["eventenddate"].astype(str), format="%Y%m%d", errors="coerce")
    df["sigungu"] = df["addr1"].map(extract_sigungu)
    df["lat"] = pd.to_numeric(df["mapy"], errors="coerce")
    df["lng"] = pd.to_numeric(df["mapx"], errors="coerce")
    df["image"] = _clean_image(df["firstimage"])
    df["type"] = "축제·행사"
    today = pd.Timestamp(datetime.now(KST).date())
    df["status"] = [event_status(s, e, today) for s, e in zip(df["start"], df["end"])]
    return df


# ──────────────────────────────────────────────────────────────
# 공통 UI 헬퍼
# ──────────────────────────────────────────────────────────────
def style_fig(fig, height: int):
    fig.update_layout(
        height=height,
        template="plotly_white",
        margin=dict(l=10, r=20, t=50, b=10),
        font=dict(family="Pretendard, sans-serif", color=INK, size=13),
        title=dict(font=dict(size=16, color=INK), x=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, x=0),
        hoverlabel=dict(font_family="Pretendard, sans-serif"),
    )
    return fig


def kpi_cards(items):
    cards = "".join(
        f'<div class="kpi" style="--c:{color}">'
        f'<div class="label">{label}</div>'
        f'<div class="value">{value}</div>'
        f'<div class="sub">{sub}</div></div>'
        for label, value, sub, color in items
    )
    st.markdown(f'<div class="kpi-grid">{cards}</div>', unsafe_allow_html=True)


def apply_filters(df, sigungus, types, keyword):
    out = df[df["sigungu"].isin(sigungus)]
    if types is not None:
        out = out[out["type"].isin(types)]
    if keyword:
        out = out[out["title"].str.contains(keyword, case=False, na=False)]
    return out


def type_bar(df, type_name: str, color: str, title: str):
    sub = (
        df[df["type"] == type_name]
        .groupby("sigungu").size()
        .sort_values().reset_index(name="count")
    )
    if sub.empty:
        st.info(f"{title}: 해당 데이터가 없습니다.")
        return
    fig = px.bar(sub, x="count", y="sigungu", orientation="h", title=title, text="count")
    fig.update_traces(marker_color=color, textposition="outside", cliponaxis=False)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(title=None)
    st.plotly_chart(style_fig(fig, max(300, 26 * len(sub) + 90)), use_container_width=True)


def popup_html(row, extra: str = "") -> str:
    img = (
        f'<img src="{html.escape(row.image)}" '
        f'style="width:100%;border-radius:8px;margin-bottom:6px;">'
        if isinstance(row.image, str) else ""
    )
    return f"""
    <div style="font-family:Pretendard,sans-serif;width:230px;">
      {img}
      <div style="font-weight:700;font-size:14px;margin-bottom:2px;">{html.escape(str(row.title))}</div>
      <div style="color:#6B7785;font-size:12px;">{html.escape(str(row.type))} · {html.escape(str(row.sigungu))}</div>
      <div style="font-size:12px;margin-top:4px;">{html.escape(str(row.addr1 or ''))}</div>
      {f'<div style="font-size:12px;color:#E4572E;margin-top:4px;">{html.escape(extra)}</div>' if extra else ''}
    </div>"""


def build_map(df: pd.DataFrame) -> folium.Map:
    m = folium.Map(location=[34.9, 127.0], zoom_start=8, tiles="CartoDB positron", control_scale=True)
    for type_name, color in TYPE_COLORS.items():
        sub = df[df["type"] == type_name]
        if sub.empty:
            continue
        fg = folium.FeatureGroup(name=f"{type_name} ({len(sub):,})", show=True)
        cluster = MarkerCluster().add_to(fg)
        icon_html = (
            f'<div style="width:14px;height:14px;border-radius:50%;background:{color};'
            f'border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.35);"></div>'
        )
        for row in sub.itertuples():
            folium.Marker(
                location=[row.lat, row.lng],
                icon=folium.DivIcon(html=icon_html, icon_size=(14, 14), icon_anchor=(7, 7)),
                tooltip=str(row.title),
                popup=folium.Popup(popup_html(row), max_width=260),
            ).add_to(cluster)
        fg.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    return m


# ──────────────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────────────
st.markdown(CSS, unsafe_allow_html=True)

if "TOUR_API_KEY" not in st.secrets:
    st.error("API 키가 없습니다. Streamlit Secrets에 `TOUR_API_KEY`를 추가해 주세요.")
    st.stop()

try:
    places = prepare_places(load_places())
    festivals = prepare_festivals(load_festivals())
except Exception as e:  # 네트워크/인증/쿼터 오류 안내
    st.error(f"데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.\n\n{e}")
    st.stop()

# ── 사이드바 필터 ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🔎 필터")
    sigungu_opts = sorted(places["sigungu"].unique())
    sel_sigungu = st.multiselect("시·군", sigungu_opts, default=sigungu_opts)

    type_opts = [name for name, _ in TYPE_META.values() if name in set(places["type"])]
    sel_types = st.multiselect("관광유형", type_opts, default=type_opts)

    keyword = st.text_input("키워드", placeholder="예: 해수욕장, 다도해")
    st.caption("필터는 모든 탭에 공통 적용됩니다. (축제 탭은 유형 필터 제외)")

p = apply_filters(places, sel_sigungu, sel_types, keyword)
f = apply_filters(festivals, sel_sigungu, None, keyword)

# ── 헤더 ──────────────────────────────────────────────────────
now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
st.markdown(
    f"""
    <div class="hero">
      <h1>🌊 전라남도 관광 대시보드</h1>
      <p>한국관광공사 TourAPI 기준 · 기준 시각 {now_kst} (KST)</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── KPI ───────────────────────────────────────────────────────
covered = p.loc[p["sigungu"] != "미분류", "sigungu"].nunique()
n_places = len(p)
n_types = p["type"].nunique()
n_fest = len(f)
n_ongoing = int((f["status"] == "진행중").sum()) if n_fest else 0
n_upcoming = int((f["status"] == "예정").sum()) if n_fest else 0
coord_rate = (p["lat"].notna().mean() * 100) if n_places else 0.0

kpi_cards([
    ("총 시·군 수", f"{covered}", f"/ {TOTAL_SIGUNGU}개 시·군 중 데이터 보유", BRAND),
    ("관광 자원 수", f"{n_places:,}", "관광지·문화·숙박·음식 등 (축제 제외)", "#4A6FA5"),
    ("관광유형 수", f"{n_types}", "TourAPI contentTypeId 기준", "#3BB273"),
    ("2026 축제·행사", f"{n_fest:,}", f"진행 중 {n_ongoing} · 예정 {n_upcoming}", "#E4572E"),
    ("좌표 보유율", f"{coord_rate:.1f}%", "지도 표시 가능 비율", "#F2A541"),
])

if p.empty and f.empty:
    st.info("선택한 조건에 맞는 데이터가 없습니다. 필터를 조정해 주세요.")
    st.stop()

tab_overview, tab_map, tab_fest, tab_list = st.tabs(
    ["📊 개요", "🗺️ 지도", "🎉 2026 축제·행사", "📋 목록"]
)

# ── 개요 ──────────────────────────────────────────────────────
with tab_overview:
    c1, c2 = st.columns([3, 2])

    with c1:
        by_sigungu = (
            p[p["sigungu"] != "미분류"].groupby("sigungu").size()
            .sort_values().reset_index(name="count")
        )
        fig = px.bar(by_sigungu, x="count", y="sigungu", orientation="h",
                     title="시·군별 관광 자원 수", text="count")
        fig.update_traces(marker_color=BRAND, textposition="outside", cliponaxis=False)
        fig.update_xaxes(visible=False)
        fig.update_yaxes(title=None)
        st.plotly_chart(style_fig(fig, max(380, 26 * len(by_sigungu) + 90)), use_container_width=True)

    with c2:
        by_type = p.groupby("type").size().reset_index(name="count").sort_values("count", ascending=False)
        fig = px.pie(by_type, names="type", values="count", hole=0.55,
                     title="관광유형 분포", color="type", color_discrete_map=TYPE_COLORS)
        fig.update_traces(textinfo="percent", textfont_size=13)
        st.plotly_chart(style_fig(fig, 420), use_container_width=True)

    st.markdown('<div class="section-title">시·군 × 관광유형 히트맵</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-desc">어느 지역에 어떤 자원이 몰려 있는지 한눈에 비교합니다.</div>',
                unsafe_allow_html=True)
    pivot = pd.crosstab(p["sigungu"], p["type"])
    fig = px.imshow(
        pivot,
        color_continuous_scale=["#F3F8F9", "#7CC3C9", "#0E7C86", "#093E47"],
        aspect="auto", text_auto=True,
    )
    fig.update_layout(coloraxis_showscale=False)
    fig.update_xaxes(title=None, side="top")
    fig.update_yaxes(title=None)
    st.plotly_chart(style_fig(fig, max(420, 28 * len(pivot) + 120)), use_container_width=True)

    st.markdown('<div class="section-title">세부 유형 현황</div>', unsafe_allow_html=True)
    b1, b2 = st.columns(2)
    with b1:
        type_bar(p, "숙박", TYPE_COLORS["숙박"], "숙박 시설 현황 (시·군별)")
    with b2:
        type_bar(p, "레포츠", TYPE_COLORS["레포츠"], "레포츠 시설 현황 (시·군별)")

# ── 지도 ──────────────────────────────────────────────────────
with tab_map:
    geo = p.dropna(subset=["lat", "lng"])
    st.markdown('<div class="section-desc">'
                f'좌표가 있는 {len(geo):,}곳을 표시합니다. 우측 상단 레이어 메뉴에서 유형별로 켜고 끌 수 있습니다.'
                '</div>', unsafe_allow_html=True)
    if geo.empty:
        st.info("지도에 표시할 좌표 데이터가 없습니다.")
    else:
        st_folium(build_map(geo), height=600, use_container_width=True, returned_objects=[])

# ── 축제·행사 ─────────────────────────────────────────────────
with tab_fest:
    if f.empty:
        st.info("선택한 조건에 해당하는 2026년 축제·행사가 없습니다.")
    else:
        dated = f.dropna(subset=["start", "end"]).copy()

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("진행 중", n_ongoing)
        k2.metric("예정", n_upcoming)
        k3.metric("종료", int((f["status"] == "종료").sum()))
        k4.metric("행사 지역", f.loc[f["sigungu"] != "미분류", "sigungu"].nunique())

        if dated.empty:
            st.info("일정 정보가 있는 축제가 없습니다.")
        else:
            tl = dated.sort_values("start").head(60)
            st.markdown('<div class="section-title">축제 일정 타임라인</div>', unsafe_allow_html=True)
            if len(dated) > 60:
                st.markdown(f'<div class="section-desc">시작일 순으로 60건만 표시합니다 (전체 {len(dated):,}건).</div>',
                            unsafe_allow_html=True)
            fig = px.timeline(
                tl, x_start="start", x_end="end", y="title", color="status",
                color_discrete_map=STATUS_COLORS, hover_data=["sigungu"],
            )
            fig.update_yaxes(autorange="reversed", title=None)
            fig.update_xaxes(title=None)
            st.plotly_chart(style_fig(fig, max(420, 24 * len(tl) + 120)), use_container_width=True)

            st.markdown('<div class="section-title">월별 행사 시작 분포</div>', unsafe_allow_html=True)
            by_month = (
                dated.assign(month=dated["start"].dt.month)
                .groupby("month").size()
                .reindex(range(1, 13), fill_value=0)
                .reset_index(name="count")
            )
            by_month["month"] = by_month["month"].map(lambda m: f"{m}월")
            fig = px.bar(by_month, x="month", y="count", text="count")
            fig.update_traces(marker_color="#E4572E", textposition="outside", cliponaxis=False)
            fig.update_yaxes(visible=False)
            fig.update_xaxes(title=None)
            st.plotly_chart(style_fig(fig, 340), use_container_width=True)

        st.markdown('<div class="section-title">축제·행사 목록</div>', unsafe_allow_html=True)
        fest_view = f[["image", "title", "sigungu", "addr1", "start", "end", "status"]].sort_values("start")
        st.dataframe(
            fest_view,
            column_config={
                "image": st.column_config.ImageColumn("이미지", width="small"),
                "title": "행사명",
                "sigungu": "시·군",
                "addr1": "주소",
                "start": st.column_config.DateColumn("시작일", format="YYYY-MM-DD"),
                "end": st.column_config.DateColumn("종료일", format="YYYY-MM-DD"),
                "status": "상태",
            },
            hide_index=True,
            use_container_width=True,
            height=480,
        )

# ── 목록 ──────────────────────────────────────────────────────
with tab_list:
    view = (
        p[["image", "title", "type", "sigungu", "addr1", "tel", "modified"]]
        .sort_values(["sigungu", "title"])
        .reset_index(drop=True)
    )
    st.markdown(f'<div class="section-desc">총 {len(view):,}건 · 열 제목을 눌러 정렬할 수 있습니다.</div>',
                unsafe_allow_html=True)
    st.dataframe(
        view,
        column_config={
            "image": st.column_config.ImageColumn("이미지", width="small"),
            "title": "관광지명",
            "type": "유형",
            "sigungu": "시·군",
            "addr1": "주소",
            "tel": "전화",
            "modified": st.column_config.DatetimeColumn("최종 수정", format="YYYY-MM-DD"),
        },
        hide_index=True,
        use_container_width=True,
        height=560,
    )
    st.download_button(
        "CSV 다운로드",
        data=view.drop(columns=["image"]).to_csv(index=False).encode("utf-8-sig"),
        file_name="jeonnam_tourism.csv",
        mime="text/csv",
    )

st.caption("출처: 한국관광공사 국문 관광정보 서비스(TourAPI). 데이터는 1시간마다 갱신됩니다.")