"use client";

import { useEffect, useMemo, useState } from "react";

/* 资讯研究档案库 v1.4 - 自选研判台模块
   8 视图：今日 / 机构研究 / 事件中心 / 新闻公告 / 个股追踪 / 行业追踪 / 报告检索 / 质量监控
   数据模型：content_type 8 主类型互斥 + content_subtype 二级 + institution/team + research_value/confidence */

const API = "https://reports.wmsora.vip/archive/api";

type Summary = {
  date: string; total_messages: number; today_messages: number; reports: number;
  research_today: number; news_today: number; announcement_today: number; market_today: number;
  review_pending: number; image_pending: number; verify_pending: number;
  source_topics: Record<string, number>; content_types: Record<string, number>;
  content_type_today: Record<string, number>; content_type_total: Record<string, number>;
  events_today: number; events_total: number; subtype_today: Record<string, number>;
  active_reports: number; candidate_reports: number;
};
type TimelineItem = {
  mid: string; date: string; source_topic: string; msg_type: string; from_user: string;
  relative_image_path: string; primary_category: string; secondary_category: string;
  confidence: string; review_required: number; entities_json: string; vision_status: string;
  continuation: number; dup_cnt: number; display_title: string; summary: string; source_name: string;
  content_type: string; content_subtype: string; institution: string; research_team: string;
  research_value: number; confidence_score: number; themes_json: string; message_role: string; original_source: string;
  normalized_hash?: string; similar_count?: number;
};
type Report = { series_id: number; title: string; institution: string; analyst: string; report_type: string; first_seen_at: string; last_seen_at: string; current_version: number; occurrence_count: number; status: string };
type Verification = { verification_id: number; report_id: number; institution: string; title: string; event_date: string; event_type: string; event_text: string; verification_status: string };
type EventItem = { event_id: number; event_title: string; event_type: string; industry: string; themes: string[]; occurred_date: string; stock_codes_json: string; stocks: string[]; source_count: number; institution_count: number; inst_n: number; importance_score: number; first_seen_at: string; last_seen_at: string; event_score?: number; status?: string; cluster_confidence?: number; update_count?: number; merge_status?: string; momentum_score?: number; momentum_peak?: number; trigger_type?: string; trigger_at?: string; momentum_curve?: any[]; messages?: any[]; roles?: Record<string, any[]>; propagation?: { first_at?: string; first_role?: string; first_source?: string; inst_first_at?: string; inst_first_source?: string; lead_minutes?: number | null; span_minutes?: number; msg_rate?: number; chain?: any[] } };

// v1.4 主类型标签（8 类互斥）
const CT_LABEL: Record<string, string> = {
  research_report: "正式研报", institution_view: "机构观点", research_activity: "调研纪要",
  news: "新闻", announcement: "正式公告", market: "行情", digest: "汇总/复盘", attachment: "图片", empty_invalid: "无效",
};
const CT_CLASS: Record<string, string> = {
  research_report: "arc-tag arc-purple", institution_view: "arc-tag arc-purple", research_activity: "arc-tag arc-purple",
  news: "arc-tag arc-gray", announcement: "arc-tag arc-orange", market: "arc-tag arc-blue",
  digest: "arc-tag arc-cyan", attachment: "arc-tag arc-cyan", empty_invalid: "arc-tag arc-gray",
};
// 旧 primary_category 兼容映射
const CAT_LABEL: Record<string, string> = {
  research: "研报", announcement: "公告", market: "行情", news: "快讯", image: "图片", empty_invalid: "无效",
};
const CAT_CLASS: Record<string, string> = {
  research: "arc-tag arc-purple", announcement: "arc-tag arc-orange", market: "arc-tag arc-blue",
  news: "arc-tag arc-gray", image: "arc-tag arc-cyan", empty_invalid: "arc-tag arc-gray",
};
const GROUP_ORDER = ["research", "announcement", "market", "news", "image", "empty_invalid"];
const GROUP_LABEL: Record<string, string> = {
  research: "📑 重点研究", announcement: "⚠️ 正式公告", market: "📊 市场行情",
  news: "📡 新闻快讯", image: "🖼 图片消息", empty_invalid: "无效",
};
const EVENT_TYPE_ICON: Record<string, string> = {
  "海外公司业绩": "🌍", "公司事件": "🏢", "行业事件": "🔬", "板块行情": "📈", "政策": "🏛", "传闻求证": "🕵️",
};
// v1.5 事件状态
const EVENT_STATUS_LABEL: Record<string, string> = {
  emerging: "新出现", heating: "升温中", stable: "持续", fading: "降温", closed: "已结束",
};
const EVENT_STATUS_CLASS: Record<string, string> = {
  emerging: "arc-ev-new", heating: "arc-ev-heat", stable: "arc-ev-stable", fading: "arc-ev-fade", closed: "arc-ev-closed",
};
// v1.5 事件内消息角色
const EV_ROLE_LABEL: Record<string, string> = {
  fact: "核心事实", source: "原始来源", research: "机构观点", commentary: "二次解读",
  mapping: "A股映射", update: "后续更新", summary: "汇总", attachment: "附件",
};
const EV_ROLE_ICON: Record<string, string> = {
  fact: "📰", source: "🏛", research: "🏦", commentary: "💬", mapping: "📈", update: "🔄", summary: "📋",
};
// v1.7 事件触发点
const TRIGGER_LABEL: Record<string, string> = {
  FIRST_INSTITUTION: "🎯 机构首次确认", STOCK_EXPANSION: "📈 股票映射扩展",
  CONSENSUS_BUILD: "🤝 机构共识形成", HEAT_BREAKOUT: "🔥 热度突破",
};
const TRIGGER_CLASS: Record<string, string> = {
  FIRST_INSTITUTION: "arc-trigger-inst", STOCK_EXPANSION: "arc-trigger-stock",
  CONSENSUS_BUILD: "arc-trigger-consensus", HEAT_BREAKOUT: "arc-trigger-heat",
};
// v1.9.1 研究状态（非交易状态）
const RESEARCH_STATE_LABEL: Record<string, string> = {
  cold: "❄️ 冷启动", warming: "🌡️ 升温中", focused: "🎯 聚焦", confirmed: "✅ 确认", fading: "📉 降温",
};

async function get<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch { return null; }
}
async function post(url: string, body: any): Promise<any | null> {
  try {
    const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    return res.ok ? await res.json() : null;
  } catch { return null; }
}

export default function ArchivePage() {
  const [tab, setTab] = useState("overview");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [reports, setReports] = useState<Report[]>([]);
  const [verifs, setVerifs] = useState<Verification[]>([]);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [eventDetail, setEventDetail] = useState<EventItem | null>(null);
  const [loading, setLoading] = useState(false);

  const [filterCat, setFilterCat] = useState("all");
  const [onlyToday, setOnlyToday] = useState(false);
  const [onlyHigh, setOnlyHigh] = useState(false);
  const [onlyWatch, setOnlyWatch] = useState(false);
  const [filterInst, setFilterInst] = useState("");
  const [filterStock, setFilterStock] = useState("");
  const [filterIndustry, setFilterIndustry] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [imgExpanded, setImgExpanded] = useState(false);
  const [focusExpanded, setFocusExpanded] = useState(false);
  const [subtypeExpand, setSubtypeExpand] = useState(false);
  const [toolbarExpand, setToolbarExpand] = useState(false);
  const [dupOpen, setDupOpen] = useState<Set<string>>(new Set());
  const [visionBusy, setVisionBusy] = useState<Set<string>>(new Set());
  const [drawer, setDrawer] = useState<any>(null);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [watchInput, setWatchInput] = useState("");
  const [savedQueries, setSavedQueries] = useState<Record<string, any>>({});
  const [queryName, setQueryName] = useState("");

  const [stockCode, setStockCode] = useState("");
  const [stockData, setStockData] = useState<any>(null);
  const [stockEvents, setStockEvents] = useState<any[]>(null);
  const [stockScore, setStockScore] = useState<any>(null);
  const [scoreDetail, setScoreDetail] = useState<any>(null);
  const [topicName, setTopicName] = useState("");
  const [topicData, setTopicData] = useState<any>(null);
  const [industries, setIndustries] = useState<any[]>([]);
  const [indLoading, setIndLoading] = useState(false);
  const [indDetail, setIndDetail] = useState<any>(null);
  const [graphMap, setGraphMap] = useState<any[]>([]);
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphDetail, setGraphDetail] = useState<any>(null);
  const [graphQ, setGraphQ] = useState("");
  const [graphAnalytics, setGraphAnalytics] = useState<any>(null);
  const [query, setQuery] = useState("");
  const [searchData, setSearchData] = useState<any>(null);
  const [reviewQueue, setReviewQueue] = useState<any[]>([]);
  const [detail, setDetail] = useState<any>(null);
  const [quality, setQuality] = useState<any>(null);
  const [vstats, setVstats] = useState<any>(null);
  const [reportDrawer, setReportDrawer] = useState<any>(null);
  const [reportTypeFilter, setReportTypeFilter] = useState("");
  const [researchDocs, setResearchDocs] = useState<any[]>([]);
  const [docStats, setDocStats] = useState<Record<string, any>>({});
  const [docFilterType, setDocFilterType] = useState("");
  const [docFilterInst, setDocFilterInst] = useState("");
  const [docQuality, setDocQuality] = useState("");
  const [docDetail, setDocDetail] = useState<any>(null);
  const [qcFold, setQcFold] = useState<Record<string, boolean>>({ "momentum": true, "models": true });
  const [docLoading, setDocLoading] = useState(false);
  const [eventTab, setEventTab] = useState("score");
  const [evDetailTab, setEvDetailTab] = useState("prop");
  const [watchpool, setWatchpool] = useState<any[]>([]);
  const [wpStats, setWpStats] = useState<Record<string, number>>({});
  const [wpStatus, setWpStatus] = useState("");
  const [wpOrder, setWpOrder] = useState("model");
  const [cockpit, setCockpit] = useState<any>(null);
  const [archiveVer, setArchiveVer] = useState("");

  useEffect(() => { loadOverview(); loadVersion(); }, []);
  useEffect(() => { if (tab === "reports") { loadReports(); loadResearchDocs(); } }, [tab, docFilterType, docFilterInst]);
  useEffect(() => { if (tab === "topic") { loadIndustries(); setIndDetail(null); setTopicData(null); } }, [tab]);
  useEffect(() => { if (tab === "graph") { loadGraphMap(); setGraphDetail(null); } }, [tab]);
  useEffect(() => { if (tab === "events") loadEvents(); }, [tab]);
  useEffect(() => { if (tab === "watchpool") loadWatchpool(); }, [tab, wpStatus, wpOrder]);
  useEffect(() => { if (tab === "review") loadReview(); }, [tab]);
  useEffect(() => { if (tab === "quality") loadQuality(); }, [tab]);

  // 自选股：默认研判台 5 只 + localStorage 覆盖
  useEffect(() => {
    try {
      const saved = localStorage.getItem("arc_watchlist");
      if (saved) setWatchlist(JSON.parse(saved));
      else setWatchlist(["001309", "603986", "301308", "688525", "300502"]);
      const sq = localStorage.getItem("arc_saved_queries");
      if (sq) setSavedQueries(JSON.parse(sq));
    } catch { setWatchlist(["001309", "603986", "301308", "688525", "300502"]); }
  }, []);

  useEffect(() => { try { localStorage.setItem("arc_watchlist", JSON.stringify(watchlist)); } catch { } }, [watchlist]);
  useEffect(() => { try { localStorage.setItem("arc_saved_queries", JSON.stringify(savedQueries)); } catch { } }, [savedQueries]);

  const addWatch = () => {
    const code = watchInput.trim();
    if (/^\d{6}$/.test(code) && !watchlist.includes(code)) setWatchlist([...watchlist, code]);
    setWatchInput("");
  };
  const removeWatch = (code: string) => setWatchlist(watchlist.filter((c) => c !== code));
  const saveQuery = () => {
    const name = queryName.trim();
    if (!name) return;
    const state = { filterCat, onlyToday, onlyHigh, onlyWatch, filterInst, filterStock, filterIndustry, dateFrom, dateTo };
    setSavedQueries({ ...savedQueries, [name]: state });
    setQueryName("");
  };
  const loadQuery = (name: string) => {
    const q = savedQueries[name];
    if (!q) return;
    setFilterCat(q.filterCat); setOnlyToday(q.onlyToday); setOnlyHigh(q.onlyHigh); setOnlyWatch(q.onlyWatch);
    setFilterInst(q.filterInst); setFilterStock(q.filterStock); setFilterIndustry(q.filterIndustry);
    setDateFrom(q.dateFrom); setDateTo(q.dateTo);
  };
  const clearFilters = () => {
    setFilterCat("all"); setOnlyToday(false); setOnlyHigh(false); setOnlyWatch(false);
    setFilterInst(""); setFilterStock(""); setFilterIndustry(""); setDateFrom(""); setDateTo("");
  };

  async function loadVersion() {
    try {
      const res = await fetch(`${API}/version`, { cache: "no-store" });
      if (res.ok) { const j = await res.json(); if (j && j.version) setArchiveVer(j.version); }
    } catch { /* 保留默认 */ }
  }
  async function loadOverview() {
    setLoading(true);
    const [s, t, c] = await Promise.all([get<Summary>(`${API}/dashboard/summary`), get<{ timeline: TimelineItem[] }>(`${API}/timeline?limit=150`), get<any>(`${API}/dashboard/cockpit`)]);
    if (s) setSummary(s);
    if (t) setTimeline(t.timeline);
    if (c) setCockpit(c);
    setLoading(false);
  }
  async function loadReports() { setReports((await get<{ reports: Report[] }>(`${API}/reports`))?.reports || []); }
  async function loadResearchDocs() {
    setDocLoading(true);
    const q = new URLSearchParams({ min_quality: "50" });
    if (docFilterType) q.set("type", docFilterType);
    if (docFilterInst) q.set("inst", docFilterInst);
    const d = await get<any>(`${API}/research-documents?${q.toString()}`);
    if (d) { setResearchDocs(d.documents || []); setDocStats({ type_counts: d.type_counts || {}, stats: d.stats || {}, total: d.total || 0 }); }
    setDocLoading(false);
  }
  async function openDocDetail(id: number) { setDocDetail(await get<any>(`${API}/research-documents?id=${id}`)); }
  async function loadEvents() { setEvents((await get<{ events: EventItem[] }>(`${API}/events`))?.events || []); }
  async function loadWatchpool() {
    const q = `${API}/watchpool${wpStatus ? `?status=${wpStatus}` : ""}${wpOrder && !wpStatus ? `?order=${wpOrder}` : wpStatus ? `&order=${wpOrder}` : ""}`;
    const d = await get<{ pool: any[]; stats: Record<string, number> }>(q);
    if (d) { setWatchpool(d.pool); setWpStats(d.stats); }
  }
  async function wpAdvance(pid: number) {
    await post(`${API}/watchpool/advance`, { pool_id: pid });
    loadWatchpool();
  }
  async function wpNote(pid: number, note: string) {
    if (!note) return;
    await post(`${API}/watchpool/note`, { pool_id: pid, note });
    loadWatchpool();
  }
  async function openEvent(id: number) { setEventDetail(await get<EventItem>(`${API}/events?id=${id}`)); }
  async function loadReview() {
    const [r, v] = await Promise.all([get<{ review_queue: any[] }>(`${API}/review`), get<{ verifications: Verification[] }>(`${API}/verifications`)]);
    if (r) setReviewQueue(r.review_queue);
    if (v) setVerifs(v.verifications);
  }
  async function loadQuality() { setQuality(await get<any>(`${API}/quality`)); setVstats(await get<any>(`${API}/validation/stats`)); }
  async function searchStock() { if (!stockCode.trim()) return; const c = stockCode.trim(); setStockData(await get<any>(`${API}/stocks/research?code=${encodeURIComponent(c)}`)); setStockEvents((await get<{ events: any[] }>(`${API}/stocks/events?code=${encodeURIComponent(c)}`))?.events || null); setStockScore(await get<any>(`${API}/research-score?code=${encodeURIComponent(c)}`)); }
  async function searchStockByCode(c: string) { if (!c) return; setStockData(await get<any>(`${API}/stocks/research?code=${encodeURIComponent(c)}`)); setStockEvents((await get<{ events: any[] }>(`${API}/stocks/events?code=${encodeURIComponent(c)}`))?.events || null); setStockScore(await get<any>(`${API}/research-score?code=${encodeURIComponent(c)}`)); }
  async function searchTopic() { if (!topicName.trim()) return; setTopicData(await get<any>(`${API}/industry?topic=${encodeURIComponent(topicName.trim())}`)); }
  async function loadIndustries() {
    setIndLoading(true);
    const d = await get<any>(`${API}/industries`);
    if (d) setIndustries(d.industries || []);
    setIndLoading(false);
  }
  async function openIndustry(id: number) { setIndDetail(await get<any>(`${API}/industries?id=${id}`)); }
  async function loadGraphMap() {
    setGraphLoading(true);
    const [d, a] = await Promise.all([
      get<any>(`${API}/graph?mode=map`),
      get<any>(`${API}/graph?mode=analytics`),
    ]);
    if (d) setGraphMap(d.industries || []);
    if (a) setGraphAnalytics(a);
    setGraphLoading(false);
  }
  async function openGraphEntity(type: string, id: any) {
    const d = await get<any>(`${API}/graph?type=${type}&id=${encodeURIComponent(String(id))}`);
    if (d) setGraphDetail(d);
  }
  async function searchGraph() {
    const q = graphQ.trim();
    if (!q) return;
    if (/^\d{6}$/.test(q)) { await openGraphEntity("stock", q); return; }
    setGraphDetail(await get<any>(`${API}/industry?topic=${encodeURIComponent(q)}`));
  }
  async function doSearch() { if (!query.trim()) return; setSearchData(await get<any>(`${API}/search?q=${encodeURIComponent(query.trim())}`)); }
  async function openDetail(id: number) { setDetail(await get<any>(`${API}/reports/${id}`)); setDrawer(null); }
  async function openReportDrawer(id: number) { setReportDrawer(await get<any>(`${API}/reports/${id}`)); }
  async function openDrawer(mid: string) {
    if (!mid) return;
    setDrawerLoading(true);
    setDrawer(await get<any>(`${API}/message?mid=${encodeURIComponent(mid)}`));
    setDrawerLoading(false);
  }
  async function visionRequest(mid: string) {
    setVisionBusy((s) => new Set(s).add(mid));
    await post(`${API}/vision/request`, { mid });
    setTimeout(() => setVisionBusy((s) => { const n = new Set(s); n.delete(mid); return n; }), 1500);
  }
  async function visionInvalid(mid: string) {
    await post(`${API}/vision/invalid`, { mid });
    window.location.reload();
  }
  async function reclassify(mid: string, category: string, secondary: string) {
    await post(`${API}/reclassify`, { mid, category, secondary });
    window.location.reload();
  }

  const parseEntities = (t: any) => { try { return JSON.parse(t.entities_json || "{}"); } catch { return {}; } };
  const parseThemes = (t: any) => { try { return JSON.parse(t.themes_json || "[]"); } catch { return []; } };
  const isWatchRelated = (t: TimelineItem) => {
    const e = parseEntities(t);
    const stocks = (e.stocks || []).map(String);
    const text = `${t.display_title || ""} ${t.summary || ""}`;
    return stocks.some((c) => watchlist.includes(c)) || watchlist.some((c) => text.includes(c));
  };
  const grouped = useMemo(() => {
    let list = timeline;
    if (onlyToday && summary) list = list.filter((t) => (t.date || "").startsWith(summary.date));
    if (onlyHigh) list = list.filter((t) => (t.confidence_score ?? (t.confidence === "high" ? 0.9 : 0)) >= 0.85);
    if (onlyWatch) list = list.filter((t) => isWatchRelated(t));
    if (filterInst) list = list.filter((t) => (t.institution || "").includes(filterInst) || (t.source_name || "").includes(filterInst) || (t.display_title || "").includes(filterInst));
    if (filterStock) list = list.filter((t) => isWatchRelated(t) || (t.summary || "").includes(filterStock));
    if (filterIndustry) list = list.filter((t) => parseThemes(t).some((x: string) => x.includes(filterIndustry)));
    if (dateFrom) list = list.filter((t) => (t.date || "").slice(0, 10) >= dateFrom);
    if (dateTo) list = list.filter((t) => (t.date || "").slice(0, 10) <= dateTo);
    // v1.4.2：同 normalized_hash 折叠 → 来源聚合层
    // 主展示按来源价值排序（机构原始+50 / 官方来源+40 / 首次出现+20 / 股票映射+10 / 最新+5），
    // 而非简单取最新。其余挂到 dup 列表，默认折叠，点击展开显示来源列表。
    const byHash = new Map<string, TimelineItem[]>();
    list.forEach((t) => {
      const h = t.normalized_hash || "";
      if (!h) return;
      if (!byHash.has(h)) byHash.set(h, []);
      byHash.get(h)!.push(t);
    });
    const priority = (t: TimelineItem) => {
      let p = 0;
      if (t.institution) p += 50;            // 机构原始来源
      if (t.original_source) p += 40;        // 官方/媒体来源
      if (["original", "commentary"].includes(t.message_role)) p += 25; // 内容角色
      const e = parseEntities(t);
      if ((e.stocks || []).length > 0) p += 10;  // 股票映射
      return p;
    };
    const collapsed = new Map<string, string[]>();
    const keep = new Set<string>();
    byHash.forEach((arr, h) => {
      if (arr.length <= 1) { keep.add(arr[0].mid); return; }
      // 主展示 = priority 最高；同分取最早（首次出现 +20 隐含在 date 排序）
      const sorted = [...arr].sort((a, b) => {
        const pa = priority(a), pb = priority(b);
        if (pa !== pb) return pb - pa;
        return String(a.date).localeCompare(String(b.date));
      });
      keep.add(sorted[0].mid);
      collapsed.set(h, sorted.slice(1).map((x) => x.mid));
    });
    list = list.filter((t) => keep.has(t.mid) || dupOpen.has(t.normalized_hash || ""));
    const groups: Record<string, TimelineItem[]> = {};
    GROUP_ORDER.forEach((g) => { groups[g] = []; });
    list.forEach((t) => {
      const cat = t.primary_category || "news";
      if (filterCat === "all" || cat === filterCat || (filterCat === "research" && ["research_report", "institution_view", "research_activity"].includes(t.content_type))) (groups[cat] || groups.news).push(t);
    });
    const rank = (t: TimelineItem) => {
      let r = 0;
      if (isWatchRelated(t)) r += 4;
      if ((t.confidence_score ?? 0) >= 0.85 || t.confidence === "high") r += 2;
      if (t.review_required) r += 1;
      return r;
    };
    GROUP_ORDER.forEach((g) => { (groups[g] || []).sort((a, b) => rank(b) - rank(a) || String(b.date).localeCompare(String(a.date))); });
    return groups;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeline, filterCat, onlyToday, onlyHigh, onlyWatch, filterInst, filterStock, filterIndustry, dateFrom, dateTo, summary, watchlist, dupOpen]);

  const imgItems = grouped.image || [];
  const imgPending = imgItems.filter((i) => i.vision_status === "pending" || i.vision_status === "queued").length;

  // v1.4.2：重复组内非主展示消息的 mid 集合（展开时变体样式）——按来源价值判定
  const dupMids = useMemo(() => {
    const byHash = new Map<string, TimelineItem[]>();
    timeline.forEach((t) => {
      const hh = t.normalized_hash || "";
      if (!hh) return;
      if (!byHash.has(hh)) byHash.set(hh, []);
      byHash.get(hh)!.push(t);
    });
    const prio = (t: TimelineItem) => {
      let p = 0;
      if (t.institution) p += 50;
      if (t.original_source) p += 40;
      if (["original", "commentary"].includes(t.message_role)) p += 25;
      const e = parseEntities(t);
      if ((e.stocks || []).length > 0) p += 10;
      return p;
    };
    const notMain = new Set<string>();
    byHash.forEach((arr) => {
      if (arr.length <= 1) return;
      const sorted = [...arr].sort((a, b) => {
        const pa = prio(a), pb = prio(b);
        if (pa !== pb) return pb - pa;
        return String(a.date).localeCompare(String(b.date));
      });
      sorted.slice(1).forEach((x) => notMain.add(x.mid));
    });
    return notMain;
  }, [timeline]);

  const hotIndustries = () => {
    const cnt: Record<string, number> = {};
    timeline.forEach((t) => {
      parseThemes(t).forEach((i: string) => { cnt[i] = (cnt[i] || 0) + 1; });
    });
    return Object.entries(cnt).sort((a, b) => b[1] - a[1]).slice(0, 10);
  };

  // v1.4 视图：今日 / 机构研究 / 事件中心 / 新闻公告 / 个股追踪 / 行业追踪 / 报告检索 / 质量监控
  const TABS = [
    ["overview", "今日"], ["reports", "机构研究"], ["events", "事件中心"], ["watchpool", "研究队列"],
    ["news", "新闻公告"], ["stock", "个股追踪"], ["topic", "行业追踪"], ["graph", "研究图谱"],
    ["search", "报告检索"], ["quality", "质量监控"],
  ] as const;
  const FILTERS = [
    ["all", "全部"], ["research", "研究"], ["news", "快讯"], ["announcement", "公告"],
    ["market", "行情"], ["digest", "汇总"], ["image", "图片"], ["empty_invalid", "无效"],
  ] as const;
  const goTab = (t: string) => { setTab(t); window.scrollTo(0, 0); };

  // 工具：星级显示
  const stars = (v: number) => {
    if (!v) return null;
    const n = Math.min(5, Math.max(1, Math.round(v / 20)));
    return <span className="arc-stars" title={`研究价值 ${v}/100`}>{"★".repeat(n)}<em>{"☆".repeat(5 - n)}</em><b>{v}</b></span>;
  };
  // 工具：机构+团队显示
  const instName = (t: any) => {
    if (t.institution) return t.research_team ? `${t.institution}·${t.research_team}` : t.institution;
    return t.source_name || "";
  };
  // 工具：重复组智能标签（v1.4.2 来源聚合）
  const dupLabel = (t: TimelineItem) => {
    const n = t.similar_count || 0;
    // 组内是否有机构原始来源（主展示即原文）→ 查看原始来源
    if (t.institution || t.message_role === "original") return "▾ 查看原始来源";
    // 跨来源传播（from_user 不同）→ 传播链
    const sameUser = timeline.filter((x) => x.normalized_hash && x.normalized_hash === t.normalized_hash && x.from_user === t.from_user).length;
    if (sameUser < n + 1) return `▾ ${n + 1} 个来源传播链`;
    return `▾ ${n + 1} 个相同来源`;
  };
  // 工具：消息角色中文
  const roleLabel = (r?: string) => ({
    original: "原始", forward: "转发", summary: "汇总", commentary: "解读", attachment: "附件",
  }[r || ""] || r || "");
  const roleClass = (r?: string) => ({
    original: "arc-role-original", forward: "arc-role-forward", summary: "arc-role-summary", commentary: "arc-role-commentary", attachment: "arc-role-attachment",
  }[r || ""] || "");

  return (
    <div className="arc-page">
      <div className="arc-head">
        <h1>📚 资讯研究</h1>
        <p>六源资讯 → 8类归档 → 事件归并 → 研报追踪（档案库 {archiveVer || "v2.3.4c"} · 观察期 · 参数冻结）</p>
      </div>
      <div className="arc-tabs">
        {TABS.map(([id, label]) => (
          <button key={id} className={tab === id ? "active" : ""} onClick={() => goTab(id)}>{label}</button>
        ))}
      </div>
      <div className="arc-body">

        {/* ============ 今日 ============ */}
        {tab === "overview" && (
          <>
            {/* v2.0：今日研究驾驶舱 */}
            {cockpit && (
              <div className="arc-cockpit">
                <div className="arc-cp-section">
                  <div className="arc-cp-title">🔥 今日升温事件 <em className="arc-group-count">{(cockpit.hot_events || []).length}</em></div>
                  <div className="arc-cp-events">
                    {(cockpit.hot_events || []).slice(0, 4).map((e: any, i: number) => (
                      <div key={i} className="arc-cp-event" onClick={() => { goTab("events"); openEvent(e.event_id); }}>
                        <div className="arc-cp-event-head">
                          <span className="arc-cp-mom">🔥 {e.momentum_score}</span>
                          <span className={`arc-ev-status ${EVENT_STATUS_CLASS[e.status] || ""}`}>{EVENT_STATUS_LABEL[e.status] || e.status}</span>
                          <span className="arc-cp-event-title">{e.event_title?.slice(0, 30)}</span>
                        </div>
                        {(e.top_stocks || []).length > 0 && (
                          <div className="arc-cp-stocks">
                            {(e.top_stocks || []).slice(0, 2).map((s: any, j: number) => (
                              <span key={j} className={`arc-cp-stock ${s.research_score >= 80 ? "arc-cp-stock-high" : ""}`}>
                                {s.stock_code} {s.stock_name || ""} <b>RS {s.research_score}</b>
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                    {(cockpit.hot_events || []).length === 0 && <div className="arc-empty">今日暂无升温事件</div>}
                  </div>
                </div>
                <div className="arc-cp-section">
                  <div className="arc-cp-title">💡 今日重点研究 <em className="arc-group-count">{(cockpit.focus_stocks || []).length}</em></div>
                  <div className="arc-cp-focus">
                    {(cockpit.focus_stocks || []).slice(0, focusExpanded ? undefined : 6).map((f: any, i: number) => (
                      <div key={i} className="arc-cp-focus-item" onClick={() => { goTab("stock"); setStockCode(f.stock_code); searchStockByCode(f.stock_code); }}>
                        <span className="arc-cp-rank">{i + 1}</span>
                        <div className="arc-cp-focus-main">
                          <div className="arc-cp-focus-name">{f.stock_name || f.stock_code} <span className="arc-cp-focus-code">{f.stock_code}</span></div>
                          <div className="arc-cp-focus-sum">{(f.summary || "").slice(0, 46)}</div>
                        </div>
                        <div className="arc-cp-focus-side">
                          <b className="arc-cp-rs">{f.research_score}</b>
                          <span className={`arc-rs-state arc-rs-state-${f.research_state || "cold"}`}>{RESEARCH_STATE_LABEL[f.research_state] || f.research_state}</span>
                        </div>
                      </div>
                    ))}
                    {(cockpit.focus_stocks || []).length === 0 && <div className="arc-empty">今日暂无重点研究（RS≥70）</div>}
                  </div>
                  {(cockpit.focus_stocks || []).length > 6 && (
                    <button className="arc-cp-focus-toggle" onClick={() => setFocusExpanded(!focusExpanded)}>
                      {focusExpanded ? "收起 ▲" : `展开全部（${(cockpit.focus_stocks || []).length}）▼`}
                    </button>
                  )}
                </div>
              </div>
            )}
            {summary && (
              <>
                {/* v1.4.1：KPI 压缩成紧凑横排（标签在上/数字在下，高度 ~64px） */}
                <div className="arc-kpis">
                  <div className="arc-kpi arc-link" onClick={() => goTab("overview")}><span>今日新增</span><b>{summary.today_messages}</b></div>
                  <div className="arc-kpi arc-link" onClick={() => goTab("reports")}><span>重点研究</span><b>{(summary.content_type_today?.research_report || 0) + (summary.content_type_today?.institution_view || 0) + (summary.content_type_today?.research_activity || 0)}</b></div>
                  <div className="arc-kpi arc-link arc-kpi-hot" onClick={() => goTab("events")}><span>重点事件</span><b>{summary.events_today} →</b></div>
                  <div className="arc-kpi arc-link" onClick={() => goTab("reports")}><span>机构档案</span><b>{summary.active_reports}</b></div>
                  <div className="arc-kpi arc-link arc-kpi-warn" onClick={() => goTab("quality")}><span>待处理</span><b>{summary.review_pending} →</b></div>
                </div>
                <div className="arc-total-line">
                  📊 全部：研报 <b>{summary.total_research ?? summary.reports}</b> · 新闻 <b>{summary.total_news ?? "—"}</b> · 正式公告 <b>{summary.content_type_total?.announcement ?? "—"}</b> · 行情 <b>{summary.content_type_total?.market ?? "—"}</b> · 事件 <b>{summary.events_total}</b> · 图片 <b>{summary.content_type_total?.attachment ?? "—"}</b>
                </div>
                {/* v1.4.1：今日子类弱化为一行小字，可点击展开 */}
                <div className="arc-hotline">
                  <span className="arc-hotline-label">热门分类</span>
                  {Object.entries(summary.subtype_today || {}).slice(0, 5).map(([k, v]) => (
                    <span key={k} className="arc-hotline-item">{k} <em>{v as number}</em></span>
                  ))}
                  <span className="arc-hotline-more" onClick={() => setSubtypeExpand(!subtypeExpand)}>{subtypeExpand ? "收起 ▲" : "更多 ▾"}</span>
                </div>
                {subtypeExpand && (
                  <div className="arc-hotline arc-hotline-expand">
                    {Object.entries(summary.subtype_today || {}).slice(5).map(([k, v]) => (
                      <span key={k} className="arc-hotline-item">{k} <em>{v as number}</em></span>
                    ))}
                  </div>
                )}
              </>
            )}
            {/* v1.4.1：筛选区压缩成两行工具栏 */}
            <div className="arc-toolbar">
              <div className="arc-toolbar-row1">
                <div className="arc-filter-group">
                  {FILTERS.map(([id, label]) => (
                    <button key={id} className={filterCat === id ? "active" : ""} onClick={() => setFilterCat(id)}>{label}</button>
                  ))}
                </div>
                <div className="arc-toolbar-checks">
                  <label className="arc-check"><input type="checkbox" checked={onlyToday} onChange={(e) => setOnlyToday(e.target.checked)} /> 今日新增</label>
                  <label className="arc-check"><input type="checkbox" checked={onlyHigh} onChange={(e) => setOnlyHigh(e.target.checked)} /> 高置信度</label>
                  <label className="arc-check"><input type="checkbox" checked={onlyWatch} onChange={(e) => setOnlyWatch(e.target.checked)} /> ⭐自选股</label>
                </div>
                <div className="arc-toolbar-actions">
                  <button className={`arc-btn ${watchlist.length ? "arc-btn-blue" : ""}`} onClick={() => setToolbarExpand(!toolbarExpand)}>自选股 {watchlist.length}{toolbarExpand ? " ▲" : ""}</button>
                  {Object.keys(savedQueries).length > 0 && <button className="arc-btn" onClick={() => setToolbarExpand(!toolbarExpand)}>已保存查询 {Object.keys(savedQueries).length} ▾</button>}
                </div>
              </div>
              <div className="arc-toolbar-row2">
                <input className="arc-finput" placeholder="机构/团队" value={filterInst} onChange={(e) => setFilterInst(e.target.value)} />
                <input className="arc-finput" placeholder="股票代码" value={filterStock} onChange={(e) => setFilterStock(e.target.value)} />
                <input className="arc-finput" placeholder="行业/主题" value={filterIndustry} onChange={(e) => setFilterIndustry(e.target.value)} />
                <input className="arc-finput arc-fdate" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
                <span className="arc-filter-sep">~</span>
                <input className="arc-finput arc-fdate" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
                <button className="arc-btn" onClick={clearFilters}>清除</button>
                <span className="arc-filter-count">{Object.values(grouped).reduce((a, g) => a + g.length, 0)} 条</span>
              </div>
              {toolbarExpand && (
                <div className="arc-toolbar-expand">
                  <div className="arc-toolbar-line">
                    <span className="arc-filter-label">自选股：</span>
                    {watchlist.map((c) => <span key={c} className="arc-watch-chip">{c}<em onClick={() => removeWatch(c)}>×</em></span>)}
                    <input className="arc-finput arc-fwatch" placeholder="添加6位代码" value={watchInput} onChange={(e) => setWatchInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addWatch()} />
                    <button className="arc-btn" onClick={addWatch}>＋</button>
                  </div>
                  {Object.keys(savedQueries).length > 0 && (
                    <div className="arc-toolbar-line">
                      <span className="arc-filter-label">常用查询：</span>
                      {Object.keys(savedQueries).map((name) => <button key={name} className="arc-btn arc-btn-blue" onClick={() => loadQuery(name)}>{name}</button>)}
                      <input className="arc-finput arc-fwatch" placeholder="保存当前筛选为…" value={queryName} onChange={(e) => setQueryName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && saveQuery()} />
                      <button className="arc-btn" onClick={saveQuery}>保存</button>
                    </div>
                  )}
                </div>
              )}
            </div>
            {GROUP_ORDER.filter((g) => (grouped[g] || []).length > 0 && (filterCat === "all" || filterCat === g || (filterCat === "research" && g === "research"))).map((g) => (
              <div key={g} className="arc-group">
                <div className="arc-section-title">{GROUP_LABEL[g]} <em className="arc-group-count">{grouped[g].length}</em></div>
                {g === "image" ? (
                  <div className="arc-img-collapse">
                    <div className="arc-img-head" onClick={() => setImgExpanded(!imgExpanded)}>
                      <span>🖼 图片消息 · {imgItems.length} 条（{imgPending} 条待 Vision 分析）</span>
                      <button className="arc-btn">{imgExpanded ? "收起 ▲" : "展开 ▼"}</button>
                    </div>
                    {imgExpanded && imgItems.map((it, i) => (
                      <div key={i} className="arc-tl-item arc-tl-imgrow" onClick={() => openDrawer(it.mid)}>
                        <div className="arc-tl-time">{it.date?.slice(5, 16)}</div>
                        <span className="arc-tag arc-cyan">图片</span>
                        <span className="arc-tl-topic">{it.source_topic}</span>
                        <div className="arc-tl-img">
                          {it.relative_image_path && <a className="arc-btn" href={`https://reports.wmsora.vip/${it.relative_image_path}`} target="_blank" rel="noreferrer">查看图片</a>}
                          <button className="arc-btn arc-btn-blue" disabled={visionBusy.has(it.mid)} onClick={(e) => { e.stopPropagation(); visionRequest(it.mid); }}>{visionBusy.has(it.mid) ? "已入队" : "开始分析"}</button>
                          <button className="arc-btn" onClick={(e) => { e.stopPropagation(); visionInvalid(it.mid); }}>标记无效</button>
                        </div>
                        <span className={`arc-tag ${it.vision_status === "done" ? "arc-blue" : it.vision_status === "invalid" ? "arc-gray" : "arc-orange"}`}>
                          {it.vision_status === "pending" || it.vision_status === "queued" ? "待分析" : it.vision_status === "done" ? "已分析" : "已确认"}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="arc-timeline arc-timeline-compact">
                    {grouped[g].map((it, i) => {
                      const entities = parseEntities(it);
                      const stockTags = (entities.stocks || []).slice(0, 3);
                      const themes = parseThemes(it).slice(0, 2);
                      const watchHit = isWatchRelated(it);
                      const ct = it.content_type || it.primary_category;
                      // v1.4.1：标签分级——主类型彩色、子类浅灰、主题小字、机构纯文本
                      const primaryTag = <span className={CT_CLASS[ct] || CAT_CLASS[it.primary_category] || "arc-tag"}>{CT_LABEL[ct] || CAT_LABEL[it.primary_category] || ct}</span>;
                      const subTag = it.content_subtype ? <span className="arc-tag arc-subtag">{it.content_subtype}</span> : null;
                      const inst = instName(it);
                      const h = it.normalized_hash || "";
                      // 重复组展开时：非最新一条加变体样式（浅色+缩进标记）
                      const isDupVariant = dupMids.has(it.mid);
                      return (
                        <div key={i} className={`arc-tl-row arc-row-v14 ${watchHit ? "arc-watch-row" : ""} ${isDupVariant ? "arc-dup-variant" : ""}`} onClick={() => openDrawer(it.mid)}>
                          <div className="arc-tl-time">{it.date?.slice(5, 16)}</div>
                          <div className="arc-tl-cats">
                            {primaryTag}
                            {subTag}
                            {it.message_role && <span className={`arc-tag arc-role ${roleClass(it.message_role)}`}>{roleLabel(it.message_role)}</span>}
                          </div>
                          <div className="arc-tl-main">
                            <div className="arc-tl-title">{watchHit ? "⭐ " : ""}{it.display_title || "资讯"}</div>
                            <div className="arc-tl-sub">
                              {isDupVariant && <span className="arc-tl-note">← 重复来源</span>}
                              {inst && <span className="arc-tl-inst">{inst}</span>}
                              {themes.map((x: string) => <span key={x} className="arc-tl-theme">{x}</span>)}
                              {stockTags.map((c: string) => <code key={c}>{c}</code>)}
                              {isDupVariant && it.from_user && <span className="arc-tl-src">来自 {it.from_user} · {it.source_topic}</span>}
                              {it.dup_cnt > 1 && <span className="arc-tl-note">含{it.dup_cnt}条</span>}
                              {it.similar_count > 0 && (
                                <span className="arc-tl-dup" onClick={(e) => { e.stopPropagation(); const h = it.normalized_hash || ""; setDupOpen((s) => { const n = new Set(s); if (n.has(h)) n.delete(h); else n.add(h); return n; }); }}>
                                  {dupOpen.has(it.normalized_hash || "") ? "▴ 收起" : dupLabel(it)}
                                </span>
                              )}
                            </div>
                          </div>
                          <div className="arc-tl-score">
                            {stars(it.research_value)}
                            {it.review_required ? <span className="arc-tag arc-orange">待复核</span> : null}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            ))}
            {!loading && Object.values(grouped).every((g) => g.length === 0) && <div className="arc-empty">暂无资讯</div>}
          </>
        )}

        {/* ============ 机构研究 → 研究对象中心（v2.3.1） ============ */}
        {tab === "reports" && (
          <div className="arc-reports">
            {(() => {
              const typeCounts: Record<string, number> = docStats.type_counts || {};
              const insts = [...new Set(researchDocs.flatMap((d) => d.institutions || []))].filter(Boolean).sort();
              const filtered = researchDocs.filter((d) => {
                if (docQuality === "high" && d.quality_level !== "high") return false;
                if (docQuality === "medium" && d.quality_level === "low") return false;
                return true;
              });
              const high = (docStats.stats?.high || 0), med = (docStats.stats?.medium || 0);
              return (
                <>
                  <div className="arc-filters">
                    <span className="arc-filter-label">📚 研究对象 <b>{docStats.total || filtered.length}</b> <em className="arc-group-count">high {high} · medium {med}</em></span>
                    <div className="arc-filter-group" style={{ marginTop: 6 }}>
                      <button className={docQuality === "" ? "active" : ""} onClick={() => setDocQuality("")}>全部质量</button>
                      <button className={docQuality === "high" ? "active" : ""} onClick={() => setDocQuality("high")}>★★★★★ {high}</button>
                      <button className={docQuality === "medium" ? "active" : ""} onClick={() => setDocQuality("medium")}>★★★ {med}</button>
                    </div>
                    <div className="arc-filter-group" style={{ marginTop: 6 }}>
                      <button className={docFilterType === "" ? "active" : ""} onClick={() => setDocFilterType("")}>全部类型</button>
                      {Object.entries(typeCounts).map(([t, n]) => (
                        <button key={t} className={docFilterType === t ? "active" : ""} onClick={() => setDocFilterType(t)}>
                          {t} <em className="arc-group-count">{n as number}</em>
                        </button>
                      ))}
                    </div>
                    <div className="arc-filter-group" style={{ marginTop: 6 }}>
                      <select className="arc-finput" style={{ width: 200 }} value={docFilterInst} onChange={(e) => setDocFilterInst(e.target.value)}>
                        <option value="">🏦 全部机构</option>
                        {insts.map((x) => <option key={x} value={x}>{x}</option>)}
                      </select>
                      <span className="arc-tag arc-gray" style={{ marginLeft: 8 }}>点击卡片查看详情</span>
                    </div>
                  </div>
                  <div className="arc-doc-list">
                    {docLoading && <div className="arc-empty">加载中…</div>}
                    {!docLoading && filtered.length === 0 && <div className="arc-empty">暂无符合条件的研究对象</div>}
                    {filtered.map((d) => (
                      <div key={d.doc_id} className="arc-doc-card arc-clickable" onClick={() => openDocDetail(d.doc_id)}>
                        <div className="arc-doc-head">
                          <div className="arc-doc-title">{d.title || "未提取标题"}</div>
                          <div className="arc-doc-score">
                            <span className={`arc-doc-ql arc-doc-${d.quality_level}`}>{d.quality_level === "high" ? "HIGH" : d.quality_level === "medium" ? "MED" : "LOW"}</span>
                            <b>{d.quality_score}</b>
                          </div>
                        </div>
                        <div className="arc-doc-meta-line">
                          <span className="arc-tag arc-purple">{d.research_type || "未分类"}</span>
                          {(d.institutions || []).map((x: string, i: number) => <span key={i} className="arc-tag arc-blue">🏦 {x}</span>)}
                          <span className="arc-tag">来源 {d.source_count}</span>
                          <span className="arc-tag arc-gray">{d.first_seen_at?.slice(5, 16)}</span>
                        </div>
                        {d.summary && <div className="arc-doc-summary">{d.summary}</div>}
                        {(d.stocks?.length > 0 || d.event_relations?.length > 0) && (
                          <div className="arc-doc-assoc">
                            {d.stocks?.length > 0 && (
                              <div className="arc-doc-row"><b>📈 关联股票</b>
                                <span>{(d.stocks as any[]).map((s: any, i: number) => <code key={i} className="arc-doc-code" title={s.name || s.code}>{s.name || s.code}</code>)}</span>
                              </div>
                            )}
                            {d.event_relations?.length > 0 && (
                              <div className="arc-doc-row"><b>🔥 关联事件</b>
                                <span>{(d.event_relations as any[]).slice(0, 3).map((e: any, i: number) => (
                                  <span key={i} className="arc-tag arc-orange">{e.title.slice(0, 18)}{e.momentum ? ` · ${e.momentum}` : ""}</span>
                                ))}</span>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </>
              );
            })()}
          </div>
        )}

        {/* ============ 事件中心（v1.5 语义事件层） ============ */}
        {tab === "events" && (
          <div className="arc-panel">
            <div className="arc-section-title">🔥 重点事件（{events.length} 个{summary ? ` · 今日 ${summary.events_today}` : ""}）</div>
            <div className="arc-filter-group" style={{ marginBottom: 10 }}>
              <button className={eventTab === "score" ? "active" : ""} onClick={() => setEventTab("score")}>综合评分</button>
              <button className={eventTab === "heat" ? "active" : ""} onClick={() => setEventTab("heat")}>🔥 热度</button>
              <button className={eventTab === "new" ? "active" : ""} onClick={() => setEventTab("new")}>新出现</button>
              <button className={eventTab === "heatup" ? "active" : ""} onClick={() => setEventTab("heatup")}>升温中</button>
              <button className={eventTab === "inst" ? "active" : ""} onClick={() => setEventTab("inst")}>机构最多</button>
            </div>
            <div className="arc-event-list">
              {events
                .filter((e) => {
                  if (eventTab === "new") return e.status === "emerging";
                  if (eventTab === "heatup") return e.status === "heating";
                  return true;
                })
                .sort((a, b) => {
                  if (eventTab === "heat") return (b.momentum_score ?? 0) - (a.momentum_score ?? 0);
                  if (eventTab === "inst") return (b.inst_n ?? 0) - (a.inst_n ?? 0) || (b.event_score ?? 0) - (a.event_score ?? 0);
                  return (b.event_score ?? 0) - (a.event_score ?? 0) || (b.importance_score ?? 0) - (a.importance_score ?? 0);
                })
                .map((e) => {
                const icon = EVENT_TYPE_ICON[e.event_type] || "📌";
                const st = e.status || "stable";
                const mom = e.momentum_score || 0;
                const momBar = "█".repeat(Math.min(10, Math.max(1, Math.round(mom / 10))));
                const evStocks = (e.stocks || (() => { try { return JSON.parse(e.stock_codes_json || "[]"); } catch { return []; } })()).slice(0, 8);
                const span = (() => {
                  try {
                    const f = new Date(e.first_seen_at?.replace(" ", "T"));
                    const l = new Date(e.last_seen_at?.replace(" ", "T"));
                    const h = Math.round((l.getTime() - f.getTime()) / 3600000);
                    if (h < 1) return "1h内";
                    if (h < 24) return `${h}h`;
                    return `${Math.round(h / 24)}天`;
                  } catch { return ""; }
                })();
                return (
                  <div key={e.event_id} className="arc-event-card" onClick={() => openEvent(e.event_id)}>
                    <div className="arc-event-head">
                      <span className="arc-event-star" title={`事件评分 ${e.event_score ?? 0}/100`}>{"★".repeat(Math.min(5, Math.max(1, Math.round((e.event_score ?? 0) / 20))))}<em>{"☆".repeat(5 - Math.min(5, Math.max(1, Math.round((e.event_score ?? 0) / 20))))}</em></span>
                      {mom > 0 && <span className="arc-mom" title={`当前热度 ${mom}/100 · 峰值 ${e.momentum_peak || 0}`}>🔥 {mom}<em>{momBar}</em></span>}
                      <span className={`arc-ev-status ${EVENT_STATUS_CLASS[st]}`}>{EVENT_STATUS_LABEL[st] || st}</span>
                      <span className="arc-event-title">{icon} {e.event_title}</span>
                      <span className="arc-tag arc-purple">{e.event_type}</span>
                    </div>
                    <div className="arc-event-meta">
                      <span className="arc-tag">{e.occurred_date}</span>
                      <span className="arc-tag arc-orange">{e.source_count} 独立来源</span>
                      <span className="arc-tag arc-blue">{e.inst_n ?? e.institution_count} 机构</span>
                      <span className="arc-tag">{e.update_count ?? 0} 次更新</span>
                      {span && <span className="arc-tag arc-gray">持续 {span}</span>}
                      {e.cluster_confidence && e.cluster_confidence < 0.85 && <span className="arc-tag arc-orange" title="跨日语义归并，置信度略低">疑似归并</span>}
                      {e.trigger_type && <span className={`arc-trigger ${TRIGGER_CLASS[e.trigger_type] || ""}`} title={e.trigger_at || ""}>{TRIGGER_LABEL[e.trigger_type] || e.trigger_type}</span>}
                      {e.themes?.slice(0, 3).map((t: string) => <span key={t} className="arc-tag">{t}</span>)}
                    </div>
                    {evStocks.length > 0 && <div className="arc-tl-tags">关联A股：{evStocks.map((c: string) => <code key={c}>{c}</code>)}</div>}
                    <div className="arc-event-foot">首次 {e.first_seen_at?.slice(5, 16)} · 最新 {e.last_seen_at?.slice(5, 16)} · 点击展开 →</div>
                  </div>
                );
              })}
              {events.length === 0 && <div className="arc-empty">暂无事件</div>}
            </div>
          </div>
        )}

        {/* ============ 研究队列（v1.8 事件驱动研究候选层 / v2.0 更名） ============ */}
        {tab === "watchpool" && (
          <div className="arc-panel">
            <div className="arc-section-title">🔬 研究队列 <em className="arc-group-count">{Object.values(wpStats).reduce((a, b) => a + b, 0)}</em> <span className="arc-wp-note">股票研究列表（v2.2.2 按股票聚合）· 不构成交易建议</span></div>
            <div className="arc-filter-group" style={{ marginBottom: 10 }}>
              <button className={wpStatus === "" ? "active" : ""} onClick={() => setWpStatus("")}>全部 {Object.values(wpStats).reduce((a, b) => a + b, 0)}</button>
              {["EVENT_FOUND", "RESEARCH", "WATCH", "MODEL_CHECK", "TRIAL_READY"].map((s) => (
                <button key={s} className={wpStatus === s ? "active" : ""} onClick={() => setWpStatus(s)}>{s.replace("_", " ")} {wpStats[s] || 0}</button>
              ))}
              <span className="arc-filter-sep" style={{ marginLeft: 8 }}></span>
              <button className={`arc-btn ${wpOrder === "model" ? "arc-btn-blue" : ""}`} onClick={() => setWpOrder("model")}>模型分</button>
              <button className={`arc-btn ${wpOrder === "momentum" ? "arc-btn-blue" : ""}`} onClick={() => setWpOrder("momentum")}>热度</button>
              <button className={`arc-btn ${wpOrder === "confidence" ? "arc-btn-blue" : ""}`} onClick={() => setWpOrder("confidence")}>置信度</button>
            </div>
            <div className="arc-wp-list">
              {watchpool.map((p: any, _wpIdx: number) => {
                const md = p.model_detail || {};
                const events = p.events || [];
                const maxMomentum = Math.max(0, ...events.map((e: any) => e.momentum_score || 0));
                return (
                  <div key={p.stock_code} className="arc-wp-card">
                    <div className="arc-wp-head">
                      <span className="arc-wp-code">{p.stock_code}</span>
                      <span className="arc-wp-name">{p.stock_name || "—"}</span>
                      <span className={`arc-wp-status arc-wp-st-${(p.state || "EVENT_FOUND").toLowerCase()}`}>{(p.state || "EVENT_FOUND").replace("_", " ")}</span>
                      {p.rs != null && <span className="arc-tag arc-blue">🧠 RS {p.rs}</span>}
                      {p.model_score > 0 && <span className="arc-tag arc-purple">🤖 模型 {Math.round(p.model_score)}分 {md.model || ""}</span>}
                      <span className="arc-wp-impact">🔥 {maxMomentum} · {events.length} 个事件</span>
                    </div>
                    {events.length > 0 && (
                      <div className="arc-wp-events">
                        <div className="arc-wp-events-title">关联事件（{events.length}）</div>
                        {events.slice(0, 3).map((ev: any, i: number) => (
                          <div key={i} className="arc-wp-event" onClick={() => { goTab("events"); openEvent(ev.event_id); }}>
                            🔥 {ev.momentum_score} · {ev.event_title?.slice(0, 50)} <em>查看事件 →</em>
                          </div>
                        ))}
                        {events.length > 3 && <div className="arc-wp-events-more">另有 {events.length - 3} 个事件…</div>}
                      </div>
                    )}
                    {md.matched && md.matched.length > 0 && (
                      <div className="arc-wp-model-matches">模型匹配：{md.matched.slice(0, 3).map((m: string, i: number) => <span key={i} className="arc-tag arc-gray">{m.slice(0, 14)}</span>)}</div>
                    )}
                    <div className="arc-wp-ops">
                      <button className="arc-btn arc-btn-blue" onClick={() => p.pool_ids?.[0] && wpAdvance(p.pool_ids[0])}>推进 →</button>
                      <span className="arc-wp-note-hint">按股票聚合 · 状态取最高优先级</span>
                    </div>
                  </div>
                );
              })}
              {watchpool.length === 0 && <div className="arc-empty">暂无候选（需 Momentum≥60 + 机构确认 + 非风险关系）</div>}
            </div>
          </div>
        )}

        {/* ============ 新闻公告（v1.4 分开显示） ============ */}
        {tab === "news" && (
          <div className="arc-timeline arc-timeline-compact">
            <div className="arc-section-title">📡 新闻 / 正式公告 / 行情（v1.4 分开）</div>
            {timeline.filter((it) => ["news", "announcement", "market", "digest"].includes(it.content_type || it.primary_category)).map((it, i) => {
              const ct = it.content_type || it.primary_category;
              const inst = instName(it);
              return (
                <div key={i} className="arc-tl-row arc-row-v14" onClick={() => openDrawer(it.mid)}>
                  <div className="arc-tl-time">{it.date?.slice(5, 16)}</div>
                  <div className="arc-tl-cats">
                    <span className={CT_CLASS[ct] || CAT_CLASS[it.primary_category] || "arc-tag"}>{CT_LABEL[ct] || CAT_LABEL[it.primary_category] || ct}</span>
                    {it.content_subtype && <span className="arc-tag arc-subtag">{it.content_subtype}</span>}
                  </div>
                  <div className="arc-tl-main">
                    <div className="arc-tl-title">{it.display_title || "资讯"}</div>
                    <div className="arc-tl-sub">
                      {inst && <span className="arc-tl-inst">{inst}</span>}
                      {parseThemes(it).slice(0, 2).map((x: string) => <span key={x} className="arc-tl-theme">{x}</span>)}
                    </div>
                  </div>
                  <div className="arc-tl-score">
                    {stars(it.research_value)}
                    {it.review_required ? <span className="arc-tag arc-orange">待复核</span> : null}
                  </div>
                </div>
              );
            })}
            {timeline.filter((it) => ["news", "announcement", "market", "digest"].includes(it.content_type || it.primary_category)).length === 0 && <div className="arc-empty">暂无</div>}
          </div>
        )}

        {/* ============ 个股追踪 ============ */}
        {tab === "stock" && (
          <div className="arc-panel">
            <div className="arc-section-title">🔍 个股追踪</div>
            <div className="arc-searchbar">
              <input placeholder="输入股票代码，如 603979" value={stockCode} onChange={(e) => setStockCode(e.target.value)} onKeyDown={(e) => e.key === "Enter" && searchStock()} />
              <button onClick={searchStock}>查询</button>
            </div>
            {!stockData && <div className="arc-empty-default"><div className="arc-empty">暂无查询结果——输入股票代码开始追踪</div><div className="arc-hint">📈 可查询 002436（兴森科技）/ 603979（博迈科）/ 688585（上纬新材）</div></div>}
            {stockData && (
              <>
                {/* 2026-08-12：股票基础信息（代码/名称解析结果） */}
                <div className="arc-stock-basic">
                  <span className="arc-stock-code">{stockData.code}</span>
                  {stockData.name && <span className="arc-stock-name">{stockData.name}</span>}
                  <span className="arc-tag arc-gray">相关研报 {stockData.report_count}</span>
                  <span className="arc-tag arc-gray">提及消息 {stockData.message_count}</span>
                </div>
                {/* v1.9：🧠 Research Score（研究综合分） */}
                {stockScore?.score && (
                  <div className="arc-rs-block">
                    <div className="arc-rs-main">
                      <div className="arc-rs-score">
                        <span className="arc-rs-num">{stockScore.score.research_score}</span>
                        <span className={`arc-rs-status arc-rs-st-${stockScore.score.score_status}`}>{stockScore.score.score_status}</span>
                        <span className={`arc-rs-state arc-rs-state-${stockScore.score.research_state || "cold"}`}>{RESEARCH_STATE_LABEL[stockScore.score.research_state] || stockScore.score.research_state}</span>
                        <span className="arc-rs-tag">研究综合分 · 非买入建议</span>
                      </div>
                      <div className="arc-rs-dims">
                        <div className="arc-rs-dim"><b>事件</b><span>{stockScore.score.event_score}/30</span><i style={{ width: `${stockScore.score.event_score / 30 * 100}%` }}></i></div>
                        <div className="arc-rs-dim"><b>十模型</b><span>{stockScore.score.model_score}/35</span><i style={{ width: `${stockScore.score.model_score / 35 * 100}%` }}></i></div>
                        <div className="arc-rs-dim"><b>技术</b><span>{stockScore.score.technical_score}/20</span><i style={{ width: `${stockScore.score.technical_score / 20 * 100}%` }}></i></div>
                        <div className="arc-rs-dim"><b>资金</b><span>{stockScore.score.capital_score}/15</span><i style={{ width: `${stockScore.score.capital_score / 15 * 100}%` }}></i></div>
                      </div>
                      <div className="arc-rs-side">
                        {/* v1.9.1：趋势迷你曲线 */}
                        {(stockScore.trend || []).length > 1 && (
                          <div className="arc-rs-trend" title="研究综合分趋势">
                            <div className="arc-rs-trend-bars">
                              {(stockScore.trend || []).map((t: any, i: number) => (
                                <div key={i} className="arc-rs-trend-col" title={`${t.d} · ${t.score}分`}>
                                  <div className="arc-rs-trend-bar" style={{ height: `${Math.max(8, (t.score || 0))}%` }}></div>
                                  <span className="arc-rs-trend-date">{t.d.slice(5)}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        <div className="arc-rs-change">
                          <span className={stockScore.score.score_change >= 0 ? "arc-rs-change-up" : "arc-rs-change-down"}>
                            {stockScore.score.score_change >= 0 ? "↑" : "↓"} {Math.abs(stockScore.score.score_change || 0)} 较前日
                          </span>
                          {stockScore.score.score_change !== 0 && (
                            <button className="arc-btn" onClick={() => setScoreDetail(stockScore)}>变化原因 →</button>
                          )}
                        </div>
                        <button className="arc-btn arc-btn-blue" onClick={() => setScoreDetail(stockScore)}>查看评分解释 →</button>
                      </div>
                    </div>
                    {/* v2.0：研究结论（Research Summary） */}
                    {stockScore.score.summary_info && (
                      <div className="arc-rsum">
                        <div className="arc-rsum-sum">{stockScore.score.summary_info.summary}</div>
                        <div className="arc-rsum-rows">
                          <div className="arc-rsum-row">
                            <b>✅ 优势</b>
                            <span>{(stockScore.score.summary_info.positive || []).slice(0, 3).map((p: any) => p.label).join(" · ")}</span>
                          </div>
                          <div className="arc-rsum-row arc-rsum-risk">
                            <b>⚠️ 风险</b>
                            <span>{(stockScore.score.summary_info.risk || []).slice(0, 2).map((p: any) => p.label).join(" · ") || "暂无明显风险"}</span>
                          </div>
                          <div className="arc-rsum-row arc-rsum-suggest">
                            <b>📋 建议</b>
                            <span>{stockScore.score.summary_info.suggestion} <em className="arc-rsum-safe">（非买入建议）</em></span>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}
                {/* v1.8.1：个股事件催化（事件→个股联动） */}
                {stockEvents && stockEvents.length > 0 && (
                  <div className="arc-sec-events">
                    <div className="arc-section-title">🎯 事件催化 <em className="arc-group-count">{stockEvents.length}</em></div>
                    <div className="arc-se-list">
                      {stockEvents.map((e: any, i: number) => (
                        <div key={i} className="arc-se-card" onClick={() => { goTab("events"); openEvent(e.event_id); }}>
                          <div className="arc-se-head">
                            <span className="arc-se-mom" title={`热度 ${e.momentum_score}/100`}>🔥 {e.momentum_score}</span>
                            <span className={`arc-ev-status ${EVENT_STATUS_CLASS[e.status] || ""}`}>{EVENT_STATUS_LABEL[e.status] || e.status}</span>
                            <span className="arc-se-title">{e.event_title?.slice(0, 34)}</span>
                            <span className={`arc-tag ${e.relation_type === "直接受益" ? "arc-red" : "arc-gray"}`}>{e.relation_type}</span>
                            <span className="arc-se-impact" title={`影响 ${e.impact_score}/100`}>{"★".repeat(Math.min(5, Math.max(1, Math.round((e.impact_score || 0) / 20))))}<em>{e.impact_score}</em></span>
                          </div>
                          <div className="arc-se-meta">
                            <span className="arc-tag">首次 {e.first_seen_at?.slice(5, 16)}</span>
                            {e.institutions?.length > 0 && (
                              <span className="arc-tag arc-blue">机构 {e.institutions.slice(0, 3).join(" / ")}</span>
                            )}
                            {e.trigger_type && <span className="arc-tag arc-purple">{TRIGGER_LABEL[e.trigger_type] || e.trigger_type}</span>}
                            {e.logic && <span className="arc-se-logic">{e.logic.slice(0, 60)}</span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                <div className="arc-section-title">相关研报（{stockData.report_count}）</div>
                {stockData.reports?.length > 0 ? stockData.reports?.map((r: any, i: number) => (
                  <div key={i} className="arc-report-card arc-clickable" onClick={() => openReportDrawer(r.series_id)}>
                    <div className="arc-report-inst">{r.institution}</div>
                    <div className="arc-report-title">{r.title}</div>
                    <div className="arc-report-meta"><span className="arc-tag arc-purple">v{r.current_version}</span><span className="arc-tag arc-orange">{r.status}</span><span className="arc-tag">点击查看详情 →</span></div>
                  </div>
                )) : <div className="arc-empty">暂无相关研报</div>}
                <div className="arc-section-title">提及消息（{stockData.message_count}）</div>
                {stockData.messages?.length > 0 ? stockData.messages?.map((m: any, i: number) => (
                  <div key={i} className="stock-message-row arc-clickable" onClick={() => m.mid && openDrawer(m.mid)}>
                    <div className="arc-tl-time">{m.date?.slice(5, 16)}</div>
                    <span className={`arc-tag stock-message-source ${CAT_CLASS[m.primary_category] || ""}`}>{CAT_LABEL[m.primary_category]}</span>
                    <div className="arc-tl-main">
                      <div className="stock-message-title">{m.content?.slice(0, 120)}</div>
                      {Number(m.dup_cnt) > 1 && <div className="arc-dup-hint">另有 {Number(m.dup_cnt) - 1} 条重复/转发记录</div>}
                    </div>
                    <span className="arc-tl-view">详情 →</span>
                  </div>
                )) : <div className="arc-empty">暂无提及消息</div>}
              </>
            )}
          </div>
        )}

        {/* ============ 行业追踪 → 行业实体中心（v2.3.2） ============ */}
        {tab === "topic" && (
          <div className="arc-panel">
            <div className="arc-section-title">🏭 行业追踪 <em className="arc-group-count" style={{ marginLeft: 6 }}>v2.3.2 行业实体化</em></div>
            {indDetail ? (
              <>
                <div className="arc-filter-group" style={{ marginBottom: 10 }}>
                  <button onClick={() => { setIndDetail(null); loadIndustries(); }}>← 返回行业列表</button>
                  <span className="arc-tag arc-purple">L{indDetail.entity?.level}</span>
                  <span className="arc-tag arc-blue">🔥 热度 {indDetail.stats?.heat}</span>
                  <span className="arc-tag">研究对象 {indDetail.stats?.doc_count}</span>
                  <span className="arc-tag">机构 {indDetail.stats?.inst_count}</span>
                  <span className="arc-tag">事件 {indDetail.stats?.event_count}</span>
                  <span className="arc-tag arc-gray">{indDetail.entity?.category || ""}</span>
                </div>
                <div className="arc-section-title">🔥 行业事件（{indDetail.events?.length || 0}）</div>
                {(indDetail.events || []).length > 0 ? (indDetail.events || []).map((ev: any, i: number) => (
                  <div key={i} className="arc-ind-event" onClick={() => { goTab("events"); openEvent(ev.event_id); }}>
                    <span className="arc-ind-mom">🔥 {ev.momentum_score}</span>
                    <span className={`arc-ev-status ${EVENT_STATUS_CLASS[ev.status] || ""}`}>{EVENT_STATUS_LABEL[ev.status] || ev.status}</span>
                    <div className="arc-ind-event-main">
                      <div className="arc-ind-event-title">{ev.event_title}</div>
                      <div className="arc-ind-event-meta">{ev.institution_count || 0} 机构 · {ev.source_count || 0} 来源 · {String(ev.first_seen_at || "").slice(0, 16)}</div>
                    </div>
                  </div>
                )) : <div className="arc-empty">暂无行业事件（事件归并层未生成该行业事件）</div>}

                <div className="arc-section-title">📚 研究对象（{indDetail.documents?.length || 0}）</div>
                {(indDetail.documents || []).length > 0 ? (indDetail.documents || []).map((d: any, i: number) => (
                  <div key={i} className="arc-doc-card arc-clickable" onClick={() => openDocDetail(d.doc_id)}>
                    <div className="arc-doc-head">
                      <div className="arc-doc-title">{d.title}</div>
                      <div className="arc-doc-score"><b>{d.quality_score}</b></div>
                    </div>
                    {d.institution && <div className="arc-doc-meta-line"><span className="arc-tag arc-blue">🏦 {d.institution}</span></div>}
                  </div>
                )) : <div className="arc-empty">暂无研究对象</div>}

                {indDetail.children?.length > 0 && (
                  <>
                    <div className="arc-section-title">🗂 子行业</div>
                    <div className="arc-ind-child-grid">
                      {indDetail.children.map((c: any, i: number) => (
                        <div key={i} className="arc-ind-child arc-clickable" onClick={() => openIndustry(c.entity_id)}>
                          <b>{c.name}</b>
                          <span className={`arc-ind-heat ${c.heat >= 70 ? "arc-ind-heat-hot" : c.heat >= 40 ? "arc-ind-heat-warm" : ""}`}>🔥 {c.heat}</span>
                          <span className="arc-tag">{c.doc_count} 对象</span>
                          <span className="arc-tag">{c.event_count} 事件</span>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </>
            ) : (
              <>
                <div className="arc-searchbar">
                  <input placeholder="搜索行业实体（如 AI算力 / 光模块 / 新能源车）" value={topicName} onChange={(e) => setTopicName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && searchTopic()} />
                  <button onClick={searchTopic}>搜索</button>
                </div>
                <div className="arc-section-title">🔥 热门行业（Industry Momentum = 对象+机构+事件+Momentum+RS）</div>
                {indLoading && <div className="arc-empty">加载中…</div>}
                {!indLoading && industries.length === 0 && <div className="arc-empty">暂无行业数据</div>}
                <div className="arc-ind-grid">
                  {industries.filter((x) => x.heat > 0).map((ind: any, i: number) => (
                    <div key={i} className={`arc-ind-card arc-clickable ${ind.level === 1 ? "arc-ind-card-top" : ""}`} onClick={() => openIndustry(ind.entity_id)}>
                      <div className="arc-ind-card-head">
                        <b>{ind.name}</b>
                        <span className={`arc-ind-heat ${ind.heat >= 70 ? "arc-ind-heat-hot" : ind.heat >= 40 ? "arc-ind-heat-warm" : ""}`}>🔥 {ind.heat}</span>
                      </div>
                      <div className="arc-ind-card-meta">
                        <span>📚 {ind.doc_count}</span>
                        <span>🏦 {ind.inst_count}</span>
                        <span>🔥 {ind.event_count}</span>
                        <span className="arc-tag arc-gray">L{ind.level}</span>
                      </div>
                      {ind.top_stocks?.length > 0 && (
                        <div className="arc-ind-card-stocks">
                          {(ind.top_stocks as any[]).map((s: any, j: number) => (
                            <span key={j} className="arc-tag arc-blue">{s.code}{s.rs ? ` RS${s.rs}` : ""}</span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
                {topicData && (
                  <>
                    <div className="arc-section-title">🔎 搜索结果：{topicData.industry}</div>
                    {topicData.events?.length > 0 && (
                      <>
                        <div className="arc-section-title">🔥 行业事件</div>
                        {(topicData.events || []).map((ev: any, i: number) => (
                          <div key={i} className="arc-ind-event" onClick={() => { goTab("events"); openEvent(ev.event_id); }}>
                            <span className="arc-ind-mom">🔥 {ev.momentum_score}</span>
                            <div className="arc-ind-event-main"><div className="arc-ind-event-title">{ev.event_title}</div></div>
                          </div>
                        ))}
                      </>
                    )}
                    {topicData.research_stocks?.length > 0 && (
                      <>
                        <div className="arc-section-title">🎯 重点研究股票</div>
                        {(topicData.research_stocks || []).map((s: any, i: number) => (
                          <div key={i} className="arc-ind-stock" onClick={() => { goTab("stock"); setStockCode(s.stock_code); searchStockByCode(s.stock_code); }}>
                            <span className="arc-ind-stock-code">{s.stock_code}</span>
                            <span className="arc-ind-stock-name">{s.stock_name}</span>
                            <span className="arc-tag arc-blue">🧠 RS {s.rs}</span>
                          </div>
                        ))}
                      </>
                    )}
                  </>
                )}
              </>
            )}
          </div>
        )}

        {/* ============ 研究图谱（v2.3.3 Research Graph） ============ */}
        {tab === "graph" && (
          <div className="arc-panel">
            <div className="arc-section-title">🕸 研究图谱 <em className="arc-group-count" style={{ marginLeft: 6 }}>v2.3.3 研究对象×行业×事件×股票×机构</em></div>
            <div className="arc-searchbar">
              <input placeholder="输入股票代码（6位）或行业关键词，如 300502 / AI算力" value={graphQ} onChange={(e) => setGraphQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && searchGraph()} />
              <button onClick={searchGraph}>图谱查询</button>
            </div>
            {graphDetail ? (
              <>
                <div className="arc-filter-group" style={{ marginBottom: 10 }}>
                  <button onClick={() => setGraphDetail(null)}>← 返回研究地图</button>
                  <span className="arc-tag arc-purple">{graphDetail.mode === "stock" ? `股票 ${graphDetail.code}` : graphDetail.mode === "entity" ? graphDetail.type : graphDetail.industry || ""}</span>
                  {graphDetail.name && <b className="arc-graph-name">{graphDetail.name}</b>}
                  {graphDetail.graph_score != null && <span className="arc-tag arc-blue">🕸 GS {graphDetail.graph_score}</span>}
                  {graphDetail.rs != null && <span className="arc-tag arc-blue">🧠 RS {graphDetail.rs}</span>}
                  {graphDetail.centrality?.centrality != null && <span className="arc-tag arc-orange">⭐ 中心度 {graphDetail.centrality.centrality}</span>}
                  {graphDetail.confidence?.score != null && <span className="arc-tag arc-purple">✅ 可信度 {graphDetail.confidence.score}</span>}
                  {graphDetail.trend_dir && <span className="arc-tag">趋势 {graphDetail.trend_dir}</span>}
                  <span className="arc-tag">文档 {graphDetail.doc_count || 0}</span>
                  <span className="arc-tag">事件 {graphDetail.event_count || 0}</span>
                  <span className="arc-tag">股票 {graphDetail.stock_count || 0}</span>
                  <span className="arc-tag">机构 {graphDetail.inst_count || 0}</span>
                  <span className="arc-tag">行业 {graphDetail.industry_count || 0}</span>
                </div>
                {graphDetail.centrality?.reasons?.length > 0 && (
                  <div className="arc-graph-reasons">{graphDetail.centrality.reasons.map((r: string, i: number) => <span key={i} className="arc-tag arc-gray">{r}</span>)}</div>
                )}
                {graphDetail.radar?.length > 0 && (
                  <div className="arc-graph-reasons"><b style={{ marginRight: 6 }}>优势方向:</b>{graphDetail.radar.map((r: any, i: number) => <span key={i} className="arc-tag arc-blue">{r.name} {r.pct}%</span>)}</div>
                )}
                {graphDetail.trend?.length > 0 && (
                  <div className="arc-graph-trend arc-graph-trend-lg">
                    {(graphDetail.trend as any[]).map((p: any, i: number) => (
                      <span key={i} className="arc-graph-trend-bar" style={{ height: Math.max(4, Math.min(40, p.value / 60)) }} title={`${p.date} ${p.value}`} />
                    ))}
                  </div>
                )}
                {graphDetail.events?.length > 0 && (
                  <>
                    <div className="arc-section-title">🔥 关联事件</div>
                    {(graphDetail.events || []).map((ev: any, i: number) => (
                      <div key={i} className="arc-ind-event" onClick={() => { setGraphDetail(null); goTab("events"); openEvent(ev.event_id); }}>
                        <span className="arc-ind-mom">🔥 {ev.momentum}</span>
                        <span className={`arc-ev-status ${EVENT_STATUS_CLASS[ev.status] || ""}`}>{EVENT_STATUS_LABEL[ev.status] || ev.status}</span>
                        <div className="arc-ind-event-main"><div className="arc-ind-event-title">{ev.title || ev.event_title}</div></div>
                      </div>
                    ))}
                  </>
                )}
                {graphDetail.stocks?.length > 0 && (
                  <>
                    <div className="arc-section-title">📈 关联股票</div>
                    <div className="arc-ind-stock-grid">
                      {(graphDetail.stocks || []).map((s: any, i: number) => (
                        <span key={i} className="arc-tag arc-blue arc-clickable" title="查看股票图谱" onClick={() => openGraphEntity("stock", s.code)}>
                          {s.name || s.code}{s.rs != null ? ` RS${s.rs}` : ""}
                        </span>
                      ))}
                    </div>
                  </>
                )}
                {graphDetail.industries?.length > 0 && (
                  <>
                    <div className="arc-section-title">🏭 关联行业</div>
                    <div className="arc-ind-stock-grid">
                      {(graphDetail.industries || []).map((x: any, i: number) => (
                        <span key={i} className="arc-tag arc-orange arc-clickable" onClick={() => openGraphEntity("industry", x.industry_id)}>{x.name}</span>
                      ))}
                    </div>
                  </>
                )}
                {graphDetail.institutions?.length > 0 && (
                  <>
                    <div className="arc-section-title">🏦 关联机构</div>
                    <div className="arc-ind-stock-grid">
                      {(graphDetail.institutions || []).map((x: any, i: number) => (
                        <span key={i} className="arc-tag">{x.name}</span>
                      ))}
                    </div>
                  </>
                )}
                {graphDetail.documents?.length > 0 && (
                  <>
                    <div className="arc-section-title">📚 关联研究对象</div>
                    {(graphDetail.documents || []).slice(0, 8).map((d: any, i: number) => (
                      <div key={i} className="arc-doc-card arc-clickable" onClick={() => openDocDetail(d.doc_id)}>
                        <div className="arc-doc-head">
                          <div className="arc-doc-title">{d.title || d.display_title}</div>
                          <div className="arc-doc-score"><b>{d.quality_score ?? d.research_value}</b></div>
                        </div>
                      </div>
                    ))}
                  </>
                )}
              </>
            ) : (
              <>
                <div className="arc-section-title">🗺 研究地图（Graph Score = 机构×4 + 文档×3 + 事件×2 + 股票×2 + 行业×1）</div>
                {graphLoading && <div className="arc-empty">加载中…</div>}
                {!graphLoading && graphAnalytics && (
                  <>
                    <div className="arc-section-title">🔥 热门主题</div>
                    <div className="arc-ind-grid">
                      {(graphAnalytics.hot_topics || []).map((t: any, i: number) => (
                        <div key={i} className={`arc-ind-card arc-clickable ${i === 0 ? "arc-ind-card-top" : ""}`} onClick={() => openGraphEntity("industry", t.entity_id)}>
                          <div className="arc-ind-card-head">
                            <b>{t.name}</b>
                            <span className={`arc-ind-heat ${t.gs >= 300 ? "arc-ind-heat-hot" : t.gs >= 100 ? "arc-ind-heat-warm" : ""}`}>GS {t.gs} <em className="arc-trend">{t.trend_dir}</em></span>
                          </div>
                          {t.trend?.length > 0 && (
                            <div className="arc-graph-trend">
                              {(t.trend as any[]).slice(-5).map((p: any, j: number) => (
                                <span key={j} className="arc-graph-trend-bar" style={{ height: Math.max(4, Math.min(28, p.value / 100)) }} title={`${p.date} ${p.value}`} />
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                    <div className="arc-section-title">⭐ 核心股票（研究中心度）</div>
                    <div className="arc-graph-stocks">
                      {(graphAnalytics.core_stocks || []).slice(0, 10).map((s: any, i: number) => (
                        <span key={i} className="arc-graph-stock arc-clickable" onClick={() => openGraphEntity("stock", s.code)}>
                          {s.name || s.code} <b>{s.centrality}</b>
                        </span>
                      ))}
                    </div>
                    <div className="arc-section-title">🏦 核心机构（研究影响力）</div>
                    <div className="arc-graph-stocks">
                      {(graphAnalytics.core_institutions || []).slice(0, 8).map((x: any, i: number) => (
                        <span key={i} className="arc-graph-stock arc-clickable" onClick={() => openGraphEntity("institution", x.inst_id)}>
                          {x.name} <b>{x.graph_score}</b>
                        </span>
                      ))}
                    </div>
                  </>
                )}
                <div className="arc-section-title">🗂 行业研究地图</div>
                {!graphLoading && graphMap.length === 0 && <div className="arc-empty">暂无图谱数据</div>}
                <div className="arc-graph-map">
                  {graphMap.map((top: any, i: number) => (
                    <div key={i} className="arc-graph-top">
                      <div className="arc-graph-top-head arc-clickable" onClick={() => openGraphEntity("industry", top.entity_id)}>
                        <b>{top.name}</b>
                        <span className="arc-tag arc-blue">总GS {top._agg?.graph_score}</span>
                        <span className="arc-tag">{top._agg?.doc_count} 文档</span>
                        <span className="arc-tag">{top._agg?.event_count} 事件</span>
                        <span className="arc-tag">{top._agg?.stock_count} 股票</span>
                        <span className="arc-tag">{top._agg?.inst_count} 机构</span>
                        {top.trend_dir && <span className="arc-tag arc-gray">趋势 {top.trend_dir}</span>}
                      </div>
                      {(top.contributions || []).length > 0 && (
                        <div className="arc-graph-contrib">
                          <span className="arc-graph-contrib-label">驱动:</span>
                          {(top.contributions as any[]).slice(0, 3).map((c: any, j: number) => (
                            <span key={j} className="arc-graph-contrib-item">{"①②③"[j] || "•"} {c.name} {c.pct}%</span>
                          ))}
                        </div>
                      )}
                      <div className="arc-graph-children">
                        {(top.children || []).slice(0, 5).map((ch: any, j: number) => (
                          <span key={j} className="arc-graph-child arc-clickable" onClick={() => openGraphEntity("industry", ch.entity_id)}>
                            {ch.name} <em>GS{ch.graph_score}</em>
                          </span>
                        ))}
                        {(top.children || []).length > 5 && <span className="arc-graph-more">+{(top.children || []).length - 5} 更多</span>}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}


        {/* ============ 报告检索 ============ */}
        {tab === "search" && (
          <div className="arc-panel">
            <div className="arc-section-title">🔎 报告检索</div>
            <div className="arc-searchbar">
              <input placeholder="搜索机构/股票/关键词，如 博迈科 / 国金 / FPSO" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && doSearch()} />
              <button onClick={doSearch}>搜索</button>
            </div>
            {!searchData && (
              <div className="arc-empty-default">
                <div className="arc-section-title">📑 最近报告</div>
                <div className="arc-report-grid">{reports.slice(0, 3).map((r, i) => <div key={i} className="arc-report-card"><div className="arc-report-inst">{r.institution}</div><div className="arc-report-title">{r.title}</div></div>)}</div>
                <div className="arc-section-title">🧪 待验证观点</div>
                {verifs.slice(0, 3).map((v, i) => <div key={i} className="arc-tl-row"><span className="arc-tag arc-orange">{v.verification_status}</span><div className="arc-tl-main"><div className="arc-tl-title">{v.institution}｜{v.title}</div></div></div>)}
              </div>
            )}
            {searchData && (
              <>
                {searchData.reports?.length > 0 && (<><div className="arc-section-title">匹配研报（{searchData.reports.length}）</div>{searchData.reports.map((r: any, i: number) => <div key={i} className="arc-report-card"><div className="arc-report-inst">{r.institution}</div><div className="arc-report-title">{r.title}</div></div>)}</>)}
                <div className="arc-section-title">匹配消息（{searchData.count}）</div>
                {searchData.results?.map((m: any, i: number) => <div key={i} className="arc-tl-row"><div className="arc-tl-time">{m.date?.slice(5, 16)}</div><span className={CAT_CLASS[m.primary_category] || "arc-tag"}>{CAT_LABEL[m.primary_category]}</span><div className="arc-tl-main"><div className="arc-tl-title">{m.content?.slice(0, 80)}</div></div></div>)}
              </>
            )}
          </div>
        )}

        {/* ============ 复盘中心（原 review） ============ */}
        {tab === "review" && (
          <div className="arc-panel">
            <div className="arc-section-title">🧪 观点验证（{verifs.length} 条）</div>
            <div className="arc-report-grid">
              {verifs.map((v, i) => (
                <div key={i} className="arc-report-card">
                  <div className="arc-report-inst">{v.institution}</div>
                  <div className="arc-report-title">{v.title}</div>
                  <div className="arc-report-meta"><span className={v.verification_status === "待验证" ? "arc-tag arc-orange" : v.verification_status === "已验证" ? "arc-tag arc-red" : "arc-tag arc-gray"}>{v.verification_status}</span><span className="arc-tag">{v.event_type}</span><span className="arc-tag">{v.event_date?.slice(0, 10)}</span></div>
                </div>
              ))}
              {verifs.length === 0 && <div className="arc-empty">暂无验证记录</div>}
            </div>
            <div className="arc-section-title">⚠️ 人工复核队列（{reviewQueue.length}）</div>
            {reviewQueue.map((m, i) => (
              <div key={i} className="arc-tl-row">
                <div className="arc-tl-time">{m.date?.slice(5, 16)}</div>
                <span className="arc-tag arc-orange">{m.secondary_category || m.primary_category}</span>
                <div className="arc-tl-main"><div className="arc-tl-title">{m.content?.slice(0, 60)}</div><div className="arc-tl-summary">{m.review_reason}</div></div>
                <div className="arc-tl-ops">
                  <button className="arc-btn arc-btn-blue" onClick={() => reclassify(m.message_id, "research", "行业研究/主题策略")}>→ 研报</button>
                  <button className="arc-btn" onClick={() => reclassify(m.message_id, "news", "其他快讯")}>→ 快讯</button>
                  <button className="arc-btn" onClick={() => reclassify(m.message_id, "news", "交流纪要/调研反馈")}>→ 交流纪要</button>
                  <button className="arc-btn" onClick={() => reclassify(m.message_id, "empty_invalid", "")}>→ 无效</button>
                </div>
              </div>
            ))}
            {reviewQueue.length === 0 && <div className="arc-empty">复核队列已清空 🎉</div>}
          </div>
        )}

        {/* ============ 质量监控（v2.3.4 Observation Mode） ============ */}
        {tab === "quality" && (
          <div className="arc-panel">
            {/* v2.3.4f 第一层：今日健康概览（健康评分 + 状态灯） */}
            {quality?.quality_center?.health && (
              <div className="arc-qc-health">
                <div className="arc-qc-health-score">
                  <div className="arc-qc-health-ring" style={{ background: `conic-gradient(#22c55e ${quality.quality_center.health.score * 3.6}deg, #e5e7eb 0deg)` }}>
                    <div className="arc-qc-health-ring-in"><b>{quality.quality_center.health.score}</b><span>/100</span></div>
                  </div>
                  <div className="arc-qc-health-label">Research<br />Health</div>
                </div>
                <div className="arc-qc-health-dims">
                  {Object.entries(quality.quality_center.health.dims || {}).map(([k, v]: [string, any], i: number) => (
                    <div key={i} className="arc-qc-health-dim">
                      <span>{k}</span>
                      <div className="arc-qc-health-bar"><div className={`arc-qc-health-fill ${v >= 70 ? "arc-qc-fill-good" : v >= 40 ? "arc-qc-fill-warn" : "arc-qc-fill-bad"}`} style={{ width: `${v}%` }} /></div>
                      <b>{v}</b>
                    </div>
                  ))}
                </div>
                <div className="arc-qc-status">
                  {(quality.quality_center.system_status && Object.entries(quality.quality_center.system_status).filter(([k]) => k !== "recent_run").map(([k, v]: [string, any], i: number) => (
                    <span key={i} className={`arc-qc-status-item ${v === "正常" ? "arc-qc-status-ok" : "arc-qc-status-warn"}`}>{k} <b>{v === "正常" ? "●" : "◐"}</b></span>
                  )))}
                  <span className="arc-qc-status-run">最近运行 {quality.quality_center.system_status?.recent_run}</span>
                </div>
              </div>
            )}
            {/* v2.3.4 Observation Mode：研究系统健康 */}
            {quality?.observation?.system_health && (
              <div className="arc-obs-block">
                <div className="arc-section-title">🧭 研究系统健康 <em className="arc-group-count">v2.3.4 Observation Mode · 稳定积累期</em></div>
                <div className="arc-stats arc-stats-6">
                  <div className="arc-stat"><b>{quality.observation.system_health.doc_total}</b><span>研究对象</span></div>
                  <div className="arc-stat"><b>{quality.observation.system_health.doc_high}</b><span>高质量≥50</span></div>
                  <div className="arc-stat"><b>{quality.observation.system_health.industry_total}</b><span>行业实体</span></div>
                  <div className="arc-stat"><b>{quality.observation.system_health.graph_relations}</b><span>图谱关系</span></div>
                  <div className="arc-stat"><b>{quality.observation.system_health.validation_total}</b><span>验证样本</span></div>
                  <div className={`arc-stat ${(quality.observation.system_health.t5_done || 0) >= 100 ? "" : "arc-warn"}`}><b>{quality.observation.system_health.t5_done}<em style={{fontSize:11,fontWeight:400}}>/{quality.observation.system_health.target_t5}</em></b><span>T+5 完成</span></div>
                </div>
                <div className="arc-obs-meta">T+1 {quality.observation.system_health.t1_done} · T+3 {quality.observation.system_health.t3_done} · 目标 T+5≥{quality.observation.system_health.target_t5} / 交易日≥{quality.observation.system_health.target_days} 后评估 v2.4</div>
                {quality.observation.rs_layers && Object.keys(quality.observation.rs_layers).length > 0 && (
                  <>
                    <div className="arc-section-title">🎯 RS 排序能力（分层 × 表现）</div>
                    <div className="arc-val-tiers">
                      {Object.entries(quality.observation.rs_layers).map((entry: [string, any]) => {
                        const k = entry[0]; const v = entry[1];
                        if (!v.n) return null;
                        return (
                          <div key={k} className={`arc-val-tier ${(v.hit_rate || 0) >= 70 ? "arc-val-tier-good" : (v.hit_rate || 0) >= 40 ? "" : "arc-val-tier-bad"}`}>
                            <b>{k}</b>
                            <span>n={v.n}</span>
                            <span>T+1 <b>{v.t1_avg ?? "—"}%</b></span>
                            <span>T+3 <b>{v.t3_avg ?? "—"}%</b></span>
                            <span>T+5 <b className="arc-val-up">{v.t5_avg ?? "—"}%</b></span>
                            <span>命中率 <b>{v.hit_rate ?? "—"}%</b></span>
                          </div>
                        );
                      })}
                    </div>
                  </>
                )}
                <div className="arc-section-title arc-qc-foldable" onClick={() => setQcFold({ ...qcFold, momentum: !qcFold.momentum })}>
                  {qcFold.momentum ? "▶" : "▼"} 🔥 Event Momentum 分层（事件热度验证）
                </div>
                {!qcFold.momentum && quality.observation.momentum_layers && Object.keys(quality.observation.momentum_layers).length > 0 && (
                  <>
                    <div className="arc-section-title" style={{ display: "none" }}>🔥 Event Momentum 分层（事件热度验证）</div>
                    <div className="arc-val-tiers">
                      {Object.entries(quality.observation.momentum_layers).map((entry: [string, any]) => {
                        const k = entry[0]; const v = entry[1];
                        if (!v.n) return null;
                        return (
                          <div key={k} className={`arc-val-tier ${(v.hit_rate || 0) >= 65 ? "arc-val-tier-good" : (v.hit_rate || 0) >= 50 ? "" : "arc-val-tier-bad"}`}>
                            <b>🔥 {k}</b>
                            <span>n={v.n}</span>
                            <span>命中率 <b>{v.hit_rate ?? "—"}%</b></span>
                          </div>
                        );
                      })}
                    </div>
                  </>
                )}
                <div className="arc-section-title arc-qc-foldable" onClick={() => setQcFold({ ...qcFold, models: !qcFold.models })}>
                  {qcFold.models ? "▶" : "▼"} 🧮 十大模型贡献（权重不变，只统计）
                </div>
                {!qcFold.models && quality.observation.model_contrib && Object.keys(quality.observation.model_contrib).length > 0 && (
                  <>
                    <div className="arc-section-title" style={{ display: "none" }}>🧮 十大模型贡献（权重不变，只统计）</div>
                    <div className="arc-val-tiers">
                      {Object.entries(quality.observation.model_contrib).sort((a: any, b: any) => b[1].n - a[1].n).slice(0, 8).map((entry: [string, any]) => {
                        const k = entry[0]; const v = entry[1];
                        if (!v.n) return null;
                        return (
                          <div key={k} className={`arc-val-tier ${(v.hit_rate || 0) >= 70 ? "arc-val-tier-good" : ""}`}>
                            <b>{k}</b>
                            <span>n={v.n}</span>
                            <span>命中率 <b>{v.hit_rate ?? "—"}%</b></span>
                          </div>
                        );
                      })}
                    </div>
                  </>
                )}
                {quality.observation.snapshots?.length > 0 && (
                  <>
                    <div className="arc-section-title">📈 每日快照（v2.4 调参历史）</div>
                    <div className="arc-obs-snaps">
                      {quality.observation.snapshots.slice(0, 7).map((s: any, i: number) => (
                        <span key={i} className="arc-obs-snap">{s.snap_date?.slice(5)} <b>样本{s.validation_total}</b> <em>T+5:{s.t5_done}</em></span>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}
            {/* v2.1：研究验证统计 */}
            {vstats && (
              <div className="arc-val-block">
                <div className="arc-section-title">🧪 研究验证（Research Validation） <em className="arc-group-count">{vstats.validated} 已验证</em></div>
                <div className="arc-stats arc-stats-6">
                  <div className="arc-stat"><b>{vstats.validated}</b><span>已验证样本</span></div>
                  <div className={`arc-stat ${vstats.hit_rate >= 50 ? "" : "arc-warn"}`}><b>{vstats.hit_rate}%</b><span>命中率(最大涨≥5%)</span></div>
                  <div className="arc-stat"><b>{vstats.hit_count}</b><span>命中数</span></div>
                  <div className="arc-stat"><b>{vstats.stats?.pending || 0}</b><span>待验证</span></div>
                  <div className="arc-stat"><b>{vstats.stats?.flat || 0}</b><span>持平</span></div>
                  <div className="arc-stat arc-warn"><b>{vstats.stats?.miss || 0}</b><span>未命中</span></div>
                </div>
                <div className="arc-val-note">⏳ {vstats.note} · 真实前瞻验证随每日 cron 自动累积 · 📸 v2.3.4c 起每样本保存 model/event/graph 快照（可解释当时评分）</div>
              </div>
            )}
            {quality?.quality_center && (
              <>
                <div className="arc-section-title">🟢 系统健康 · 研究链完整性</div>
                <div className="arc-qc-pipeline">
                  {(() => {
                    const p = quality.quality_center.pipeline || {};
                    const stages = [
                      ["原始消息", p.raw], ["归一化", p.normalized], ["研究对象", p.document],
                      ["RS评分股", p.rs_stocks], ["验证样本", p.validation],
                    ];
                    return (
                      <>
                        <div className="arc-qc-flow">
                          {stages.map((s, i) => (
                            <div key={i} className="arc-qc-flow-item">
                              <div className="arc-qc-stage">
                                <b>{s[1] ?? 0}</b><span>{s[0]}</span>
                              </div>
                              {i < stages.length - 1 && <div className="arc-qc-arrow">→</div>}
                            </div>
                          ))}
                        </div>
                        <div className="arc-qc-rate">
                          <span className="arc-tag arc-blue">📈 股票关联率 <b>{(p.doc_stock_rate ?? 0) * 10}%</b></span>
                          <span className="arc-tag arc-blue">🔗 事件关联率 <b>{p.doc_event_rate ?? 0}%</b></span>
                          <span className="arc-tag arc-gray">归一化 {p.normalized}/{p.raw} ({(p.normalized && p.raw) ? Math.round(p.normalized / p.raw * 100) : 0}%)</span>
                        </div>
                      </>
                    );
                  })()}
                </div>

                <div className="arc-section-title">🧹 数据异常中心（异常排行榜）</div>
                <div className="arc-qc-anomaly">
                  {(() => {
                    const ia = quality.quality_center.institution_anomalies || {};
                    const real = (ia.real || []).slice(0, 10); const noise = (ia.noise || []).slice(0, 10);
                    return (
                      <>
                        <div className="arc-qc-anom-col">
                          <div className="arc-qc-anom-title">🏛 机构异常 TOP10</div>
                          <div className="arc-qc-leaderboard">
                            {(real || []).map((x, i) => (
                              <div key={i} className="arc-qc-lb-row">
                                <span className="arc-qc-lb-rank">{i + 1}</span>
                                <span className="arc-qc-lb-name">{x.name}</span>
                                <b className="arc-qc-lb-count">{x.count}次</b>
                                <span className={`arc-qc-lb-type ${x.type?.includes("噪声") ? "arc-qc-type-noise" : x.type?.includes("待确认") ? "arc-qc-type-warn" : "arc-qc-type-good"}`}>{x.type}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                        <div className="arc-qc-anom-col">
                          <div className="arc-qc-anom-title">🚫 B类噪声（自动忽略 <b>{ia.noise_total || 0}</b> 次）</div>
                          <div className="arc-qc-leaderboard">
                            {(noise || []).map((x, i) => (
                              <div key={i} className="arc-qc-lb-row">
                                <span className="arc-qc-lb-rank">{i + 1}</span>
                                <span className="arc-qc-lb-name">{x.name}</span>
                                <b className="arc-qc-lb-count">{x.count}次</b>
                                <span className="arc-qc-lb-type arc-qc-type-noise">{x.type}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      </>
                    );
                  })()}
                </div>

                <div className="arc-section-title">🛠 低置信度修复建议</div>
                <div className="arc-qc-repair">
                  {(quality.quality_center.repair_suggestions || []).map((r: any, i: number) => (
                    <div key={i} className="arc-qc-repair-item">
                      <div className="arc-qc-repair-head">
                        <b>{r.issue}</b>
                        <span className="arc-tag arc-orange">{r.count}</span>
                      </div>
                      <div className="arc-qc-repair-body">
                        <span className="arc-tag arc-blue">⚙ 可自动 {r.auto}</span>
                        <span className="arc-tag arc-gray">👤 需人工 {r.manual}</span>
                        <span className="arc-qc-repair-action">{r.action}</span>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="arc-section-title">📊 低置信度原因分布（{quality.quality_center.low_conf_reasons?.reduce((a, b) => a + b.count, 0) || 0}）</div>
                <div className="arc-qc-reasons">
                  {(quality.quality_center.low_conf_reasons || []).map((r: any, i: number) => (
                    <div key={i} className="arc-qc-reason">
                      <span className="arc-qc-reason-name">{r.reason}</span>
                      <div className="arc-qc-reason-bar"><div className="arc-qc-reason-fill" style={{ width: `${r.pct}%` }} /></div>
                      <b>{r.count}</b><em>{r.pct}%</em>
                    </div>
                  ))}
                </div>

                {(() => { const mb = quality.quality_center.merge_benefit || {}; return mb.documents ? (
                  <div className="arc-qc-merge">
                    <div className="arc-section-title">🗜 归并效果（research_document 聚合）</div>
                    <div className="arc-qc-merge-body">
                      <span>原消息 <b>{mb.orig_messages}</b></span>
                      <span className="arc-qc-merge-arrow">→</span>
                      <span>研究对象 <b>{mb.documents}</b></span>
                      <span className="arc-qc-merge-arrow">→</span>
                      <span className="arc-tag arc-blue">减少 <b>{mb.reduction}%</b></span>
                      <span className="arc-tag arc-gray">多源归并 {mb.merged_docs} 组</span>
                    </div>
                  </div>
                ) : null; })()}
                {quality.quality_center.duplicate_documents?.length > 0 && (
                  <>
                    <div className="arc-section-title">🔁 重复研究对象（document 级）</div>
                    <div className="arc-qc-dupdocs">
                      {(quality.quality_center.duplicate_documents || []).map((d: any, i: number) => (
                        <div key={i} className="arc-qc-dupdoc">
                          <div className="arc-qc-dupdoc-title">{d.title}</div>
                          <div className="arc-qc-dupdoc-meta">
                            <span className="arc-tag">{d.docs} 条文档</span>
                            <span className="arc-tag">{d.sources} 个来源</span>
                            <span className="arc-tag">{d.institutions} 家机构</span>
                            <span className="arc-tag arc-gray">doc #{d.doc_ids.join(", ")}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </>
            )}
            <div className="arc-section-title">🩺 待处理任务（Action Queue）</div>
            {!quality ? <div className="arc-empty">加载中…</div> : (
              <>
                <div className="arc-stats arc-stats-6">
                  <div className={`arc-stat ${(quality.summary?.unmatched_institutions || 0) > 0 ? "arc-warn" : ""}`}><b>{quality.summary?.unmatched_institutions || 0}</b><span>机构未匹配</span></div>
                  <div className={`arc-stat ${(quality.summary?.vision_failed || 0) > 0 ? "arc-warn" : ""}`}><b>{quality.summary?.vision_failed || 0}</b><span>Vision 待处理</span></div>
                  <div className={`arc-stat ${(quality.summary?.low_confidence || 0) > 0 ? "arc-warn" : ""}`}><b>{quality.summary?.low_confidence || 0}</b><span>低置信度</span></div>
                  <div className={`arc-stat ${(quality.summary?.duplicate_reports || 0) > 0 ? "arc-warn" : ""}`}><b>{quality.summary?.duplicate_reports || 0}</b><span>疑似重复研报</span></div>
                  <div className={`arc-stat ${(quality.summary?.ambiguous_stocks || 0) > 0 ? "arc-warn" : ""}`}><b>{quality.summary?.ambiguous_stocks || 0}</b><span>股票代码歧义</span></div>
                  <div className={`arc-stat ${(quality.summary?.news_duplicates || 0) > 0 ? "arc-warn" : ""}`}><b>{quality.summary?.news_duplicates || 0}</b><span>新闻近似重复</span></div>
                  <div className={`arc-stat ${(quality.summary?.stale_verifications || 0) > 0 ? "arc-warn" : ""}`}><b>{quality.summary?.stale_verifications || 0}</b><span>长期未验证</span></div>
                </div>

                <div className="arc-section-title">🏛 机构名称未匹配（{quality.unmatched_institutions?.length || 0}）</div>
                <div className="arc-timeline">
                  {(quality.unmatched_institutions || []).map((x: any, i: number) => (
                    <div key={i} className="arc-unmatched-row">
                      <span className="arc-tag arc-orange">{x.name}</span>
                      <div className="arc-tl-main">
                        <div className="arc-tl-title">出现 {x.count} 次 · 未收录映射表</div>
                        {x.reports?.map((r: any, j: number) => (
                          <div key={j} className="arc-tl-summary">#{r.series_id} {r.title?.slice(0, 40)}</div>
                        ))}
                      </div>
                    </div>
                  ))}
                  {!quality.unmatched_institutions?.length && <div className="arc-empty">全部机构已标准化 ✅</div>}
                </div>

                <div className="arc-section-title">🖼 Vision 待处理（{quality.vision_failed?.count || 0}）</div>
                <div className="arc-qc-vision">
                  {(quality.vision_failed?.items || []).map((x: any, i: number) => {
                    const mid = String(x.message_id || "");
                    const id = mid.split(":")[1] || mid;
                    return (
                      <div key={i} className="arc-qc-vision-item">
                        <div className="arc-qc-vision-main">
                          <span className="arc-tag arc-orange">🖼 {x.vision_status === "queued" ? "等待OCR" : x.vision_status}</span>
                          <span className="arc-tag">📰 图片研报</span>
                          <span className="arc-tag">🕓 {x.date?.slice(5, 16)}</span>
                          <span className="arc-tag arc-gray">📱 Telegram</span>
                          <span className="arc-tag arc-blue">ID {id}</span>
                        </div>
                      </div>
                    );
                  })}
                  {!quality.vision_failed?.count && <div className="arc-empty">Vision 队列已清空 ✅</div>}
                </div>

                <div className="arc-section-title">⚠️ 低置信度分类（{quality.low_confidence?.count || 0}）</div>
                <div className="arc-timeline">
                  {(quality.low_confidence?.items || []).map((x: any, i: number) => (
                    <div key={i} className="arc-tl-row"><div className="arc-tl-time">{x.date?.slice(5, 16)}</div><span className="arc-tag arc-orange">{x.secondary_category || x.primary_category}</span><div className="arc-tl-main"><div className="arc-tl-title">{x.review_reason || "低置信"}</div></div></div>
                  ))}
                  {!quality.low_confidence?.count && <div className="arc-empty">无低置信度消息 ✅</div>}
                </div>

                <div className="arc-section-title">🔁 疑似重复研报（{quality.duplicate_reports?.length || 0}）</div>
                <div className="arc-timeline">
                  {(quality.duplicate_reports || []).map((x: any, i: number) => (
                    <div key={i} className="arc-tl-row"><span className="arc-tag arc-orange">series {x.series_ids.join(",")}</span><div className="arc-tl-main"><div className="arc-tl-title">{x.title}</div></div></div>
                  ))}
                  {!quality.duplicate_reports?.length && <div className="arc-empty">无重复研报 ✅</div>}
                </div>

                <div className="arc-section-title">📰 新闻近似重复（{quality.news_duplicates?.length || 0}）</div>
                <div className="arc-timeline">
                  {(quality.news_duplicates || []).map((x: any, i: number) => (
                    <div key={i} className="arc-tl-row"><span className="arc-tag arc-orange">{x.count} 条</span><div className="arc-tl-main"><div className="arc-tl-title">{x.title}</div><div className="arc-tl-summary">{x.items?.map((it: any) => it.date?.slice(5, 16)).join(" / ")}</div></div></div>
                  ))}
                  {!quality.news_duplicates?.length && <div className="arc-empty">无新闻近似重复 ✅</div>}
                </div>

                <div className="arc-section-title">❓ 股票代码歧义（{quality.ambiguous_stocks?.length || 0}）</div>
                <div className="arc-timeline">
                  {(quality.ambiguous_stocks || []).map((x: any, i: number) => (
                    <div key={i} className="arc-tl-row"><span className="arc-tag arc-orange">{x.entity_id}</span><div className="arc-tl-main"><div className="arc-tl-title">{x.institution}｜{x.title?.slice(0, 50)}</div></div></div>
                  ))}
                  {!quality.ambiguous_stocks?.length && <div className="arc-empty">无歧义代码 ✅</div>}
                </div>

                <div className="arc-section-title">⏳ 长期未验证观点（{quality.stale_verifications?.length || 0}，超过7天）</div>
                <div className="arc-timeline">
                  {(quality.stale_verifications || []).map((x: any, i: number) => (
                    <div key={i} className="arc-tl-row"><span className="arc-tag arc-orange">{x.days} 天</span><div className="arc-tl-main"><div className="arc-tl-title">{x.institution}｜{x.title?.slice(0, 50)}</div></div></div>
                  ))}
                  {!quality.stale_verifications?.length && <div className="arc-empty">无长期未验证观点 ✅</div>}
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {/* 事件详情抽屉（v1.5：评分/状态/角色分层） */}
      {eventDetail && (
        <div className="arc-drawer-mask" onClick={() => setEventDetail(null)}>
          <div className="arc-drawer" onClick={(e) => e.stopPropagation()}>
            <div className="arc-drawer-title">🔥 {eventDetail.event_title}</div>
            <div className="arc-drawer-meta-line">
              <span className="arc-tag arc-purple">{eventDetail.event_type}</span>
              <span className={`arc-ev-status ${EVENT_STATUS_CLASS[eventDetail.status || "stable"]}`}>{EVENT_STATUS_LABEL[eventDetail.status || "stable"]}</span>
              <span className="arc-event-star" title={`事件评分 ${eventDetail.event_score ?? 0}/100`}>{"★".repeat(Math.min(5, Math.max(1, Math.round((eventDetail.event_score ?? 0) / 20))))}</span>
              <span className="arc-tag">{eventDetail.occurred_date}</span>
              <button className="arc-detail-close" onClick={() => setEventDetail(null)}>✕</button>
            </div>
            <div className="arc-drawer-meta-line">
              <span className="arc-tag arc-orange">{eventDetail.source_count} 独立来源</span>
              <span className="arc-tag arc-blue">{eventDetail.inst_n ?? eventDetail.institution_count} 机构</span>
              <span className="arc-tag">{eventDetail.update_count ?? 0} 次更新</span>
              {eventDetail.cluster_confidence && <span className="arc-tag">聚类置信度 {eventDetail.cluster_confidence}</span>}
              <span className="arc-tag">首次 {eventDetail.first_seen_at?.slice(5, 16)}</span>
              <span className="arc-tag">最新 {eventDetail.last_seen_at?.slice(5, 16)}</span>
              {eventDetail.themes?.map((t: string) => <span key={t} className="arc-tag">{t}</span>)}
            </div>
            {(eventDetail.stocks || []).length > 0 && (
              <div className="arc-detail-row"><b>📈 关联A股</b><span>{(eventDetail.stocks || []).map((c: string) => <code key={c}>{c}</code>)}</span></div>
            )}
            {/* 关联个股现已在「🧩 角色明细」Tab 内展示（v1.6.1） */}
            {/* v1.7：Momentum 面板（热度曲线 + 触发点） */}
            {(eventDetail.momentum_curve || []).length > 0 && (
              <div className="arc-mom-panel">
                <div className="arc-mom-head">
                  <span className="arc-mom-big" title={`当前热度 ${eventDetail.momentum_score ?? 0}/100`}>🔥 {eventDetail.momentum_score ?? 0}</span>
                  <span className="arc-mom-peak">峰值 {eventDetail.momentum_peak ?? 0}</span>
                  {eventDetail.trigger_type && <span className={`arc-trigger ${TRIGGER_CLASS[eventDetail.trigger_type] || ""}`}>{TRIGGER_LABEL[eventDetail.trigger_type] || eventDetail.trigger_type}{eventDetail.trigger_at ? ` @${eventDetail.trigger_at.slice(5, 16)}` : ""}</span>}
                </div>
                <div className="arc-mom-bars">
                  {(eventDetail.momentum_curve || []).map((c: any, i: number) => (
                    <div key={i} className="arc-mom-bar-col" title={`${c.bucket_hour.slice(5, 16)} · ${c.momentum_score}分 消息${c.msg_count} 机构${c.inst_count}`}>
                      <div className="arc-mom-bar" style={{ height: `${Math.max(8, c.momentum_score)}%` }}></div>
                      <span className="arc-mom-bar-time">{c.bucket_hour.slice(11, 16)}</span>
                    </div>
                  ))}
                </div>
                <div className="arc-mom-note">热度 = 消息速度25% + 新来源20% + 新机构20% + 股票映射15% + 机构响应10% + 时长衰减10%</div>
              </div>
            )}
            {/* v1.6.1：传播链 Tab（时间轴：谁最早说→谁确认→怎么扩散） */}
            <div className="arc-ev-detail-tabs">
              <button className={evDetailTab === "prop" ? "active" : ""} onClick={() => setEvDetailTab("prop")}>📡 传播链</button>
              <button className={evDetailTab === "roles" ? "active" : ""} onClick={() => setEvDetailTab("roles")}>🧩 角色明细</button>
            </div>
            {evDetailTab === "prop" && eventDetail.propagation && (
              <div className="arc-ev-prop">
                <div className="arc-prop-metrics">
                  <div className="arc-prop-metric"><b>{eventDetail.propagation.first_at?.slice(5, 16)}</b><span>首次发现</span></div>
                  <div className="arc-prop-metric"><b>{eventDetail.propagation.inst_first_at ? eventDetail.propagation.inst_first_at.slice(5, 16) : "—"}</b><span>机构确认</span></div>
                  <div className="arc-prop-metric arc-prop-lead"><b>{eventDetail.propagation.lead_minutes != null ? `${eventDetail.propagation.lead_minutes}分` : "—"}</b><span>机构领先</span></div>
                  <div className="arc-prop-metric"><b>{eventDetail.propagation.span_minutes}分</b><span>持续时间</span></div>
                  <div className="arc-prop-metric"><b>{eventDetail.propagation.msg_rate}/h</b><span>传播速率</span></div>
                </div>
                <div className="arc-prop-timeline">
                  {(eventDetail.propagation.chain || []).map((n: any, i: number) => (
                    <div key={i} className="arc-prop-node">
                      <div className="arc-prop-rail">
                        <span className={`arc-prop-dot arc-prop-role-${n.role}`}></span>
                        {i < (eventDetail.propagation.chain || []).length - 1 && <span className="arc-prop-line"></span>}
                      </div>
                      <div className="arc-prop-body">
                        <div className="arc-prop-head">
                          <span className="arc-prop-time">{n.at?.slice(11, 16)}</span>
                          <span className={`arc-tag arc-role ${roleClass(n.role)}`}>{EV_ROLE_ICON[n.role] || "📄"} {EV_ROLE_LABEL[n.role] || n.role}</span>
                          <span className="arc-prop-source">{n.institution || n.source || "—"}</span>
                          {(n.count || 1) > 1 && <span className="arc-tag arc-gray">×{n.count}</span>}
                          {i === 0 && <span className="arc-tag arc-blue">首发</span>}
                          {(n.role === "research" || n.institution) && i > 0 && <span className="arc-tag arc-purple">机构确认</span>}
                        </div>
                        {n.content && <div className="arc-prop-content">{n.content}</div>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {evDetailTab === "roles" && (
              <>
                {(eventDetail.stocks_detail || []).length > 0 && (
                  <div className="arc-ev-stocks">
                    <div className="arc-section-title">🎯 关联个股 <em className="arc-group-count">{(eventDetail.stocks_detail || []).length}</em></div>
                    <div className="arc-ev-stock-list">
                      {(eventDetail.stocks_detail || []).slice(0, 10).map((s: any, i: number) => (
                        <div key={i} className={`arc-ev-stock ${s.is_holding ? "arc-ev-stock-hold" : ""}`}>
                          <div className="arc-ev-stock-head">
                            <span className="arc-ev-stock-code">{s.code}</span>
                            <span className="arc-ev-stock-name">{s.name || "—"}</span>
                            <span className={`arc-tag ${s.relation_type === "直接受益" ? "arc-red" : s.relation_type === "风险影响" ? "arc-orange" : "arc-gray"}`}>{s.relation_type}</span>
                            {s.is_holding && <span className="arc-tag arc-red">🔴 持仓</span>}
                            {s.research_score ? <span className="arc-tag arc-purple" title={`研究综合分 ${s.research_score} · ${s.research_status || ""}`}>🧠 {s.research_score}</span> : null}
                            <span className="arc-ev-stock-impact" title={`影响强度 ${s.impact_score}/100`}>{"★".repeat(Math.min(5, Math.max(1, Math.round((s.impact_score || 0) / 20))))}<em>{s.impact_score}</em></span>
                          </div>
                          {s.logic && <div className="arc-ev-stock-logic">{s.logic}</div>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {/* 角色分层（v1.5）：fact → source → research → commentary → mapping → update */}
                {eventDetail.roles && Object.entries(eventDetail.roles).map(([role, msgs]) => (
                  <div key={role} className="arc-ev-role-block">
                    <div className="arc-section-title">{EV_ROLE_ICON[role] || "📄"} {EV_ROLE_LABEL[role] || role} <em className="arc-group-count">{(msgs as any[]).length}</em></div>
                    <div className="arc-timeline">
                      {(msgs as any[]).map((m: any, i: number) => (
                        <div key={i} className="arc-tl-row arc-row-v14">
                          <div className="arc-tl-time">{m.date?.slice(5, 16)}</div>
                          <div className="arc-tl-cats">
                            <span className="arc-tag arc-gray">{m.institution || m.source_topic || "—"}</span>
                          </div>
                          <div className="arc-tl-main"><div className="arc-tl-title">{(m.content || "").slice(0, 140)}</div></div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </>
            )}
            {!eventDetail.roles && (eventDetail.messages?.length || 0) > 0 && (
              <div className="arc-section-title">关联消息（{eventDetail.messages?.length} 条）</div>
            )}
          </div>
        </div>
      )}

      {/* Research Score 解释抽屉（v1.9） */}
      {scoreDetail?.score && (
        <div className="arc-drawer-mask" onClick={() => setScoreDetail(null)}>
          <div className="arc-drawer" onClick={(e) => e.stopPropagation()}>
            <div className="arc-drawer-title">🧠 {scoreDetail.score.stock_name || scoreDetail.code} · Research Score {scoreDetail.score.research_score}</div>
            <div className="arc-drawer-meta-line">
              <span className={`arc-rs-status arc-rs-st-${scoreDetail.score.score_status}`}>{scoreDetail.score.score_status}</span>
              <span className="arc-tag">参数 {scoreDetail.score.parameter_version}</span>
              <span className="arc-tag">{scoreDetail.score.created_at?.slice(0, 16)}</span>
              <button className="arc-detail-close" onClick={() => setScoreDetail(null)}>✕</button>
            </div>
            <div className="arc-section-title">📊 四维构成</div>
            <div className="arc-rs-detail-dims">
              <div className="arc-rs-detail-dim"><b>事件强度</b><span>{scoreDetail.score.event_score}/30</span></div>
              <div className="arc-rs-detail-dim"><b>十大模型</b><span>{scoreDetail.score.model_score}/35</span></div>
              <div className="arc-rs-detail-dim"><b>技术状态</b><span>{scoreDetail.score.technical_score}/20</span></div>
              <div className="arc-rs-detail-dim"><b>资金状态</b><span>{scoreDetail.score.capital_score}/15</span></div>
            </div>
            <div className="arc-section-title">✅ 贡献项</div>
            <div className="arc-rs-expl-list">
              {(scoreDetail.score.explanation?.contributions || []).map((x: any, i: number) => (
                <div key={i} className="arc-rs-expl-item"><span>+{x.delta}</span>{x.label}</div>
              ))}
              {(scoreDetail.score.explanation?.penalties || []).map((x: any, i: number) => (
                <div key={`p${i}`} className="arc-rs-expl-item arc-rs-expl-neg"><span>{x.delta}</span>{x.label}</div>
              ))}
              {(scoreDetail.score.explanation?.contributions || []).length === 0 && (scoreDetail.score.explanation?.penalties || []).length === 0 && <div className="arc-empty">暂无解释</div>}
            </div>
            {/* v1.9.1：变化原因 */}
            {scoreDetail.score.score_change !== 0 && (
              <>
                <div className="arc-section-title">📈 评分变化 {scoreDetail.score.score_change > 0 ? `+${scoreDetail.score.score_change}` : scoreDetail.score.score_change} 较前日</div>
                <div className="arc-rs-expl-list">
                  {(scoreDetail.score.change_reason || []).map((x: any, i: number) => (
                    <div key={i} className={`arc-rs-expl-item ${(x.delta || 0) < 0 ? "arc-rs-expl-neg" : ""}`}><span>{x.delta > 0 ? `+${x.delta}` : x.delta}</span>{x.label}</div>
                  ))}
                </div>
              </>
            )}
            {(scoreDetail.score.missing || []).length > 0 && (
              <>
                <div className="arc-section-title">⚠️ 缺失条件</div>
                <div className="arc-rs-missing-list">
                  {(scoreDetail.score.missing || []).map((m: string, i: number) => (
                    <div key={i} className="arc-rs-missing-item">× {m}</div>
                  ))}
                </div>
              </>
            )}
            <div className="arc-rs-safety">安全边界：研究排序层，不构成买入建议，不改变交易状态</div>
          </div>
        </div>
      )}

      {/* 研究对象详情抽屉（v2.3.1） */}
      {docDetail && (
        <div className="arc-drawer-mask" onClick={() => setDocDetail(null)}>
          <div className="arc-drawer arc-doc-drawer" onClick={(e) => e.stopPropagation()}>
            <div className="arc-doc-drawer-head">
              <div className="arc-drawer-title">{docDetail.title || "未提取标题"}</div>
              <button className="arc-detail-close" onClick={() => setDocDetail(null)}>✕</button>
            </div>
            <div className="arc-drawer-meta-line">
              <span className={`arc-doc-ql arc-doc-${docDetail.quality_level}`}>{docDetail.quality_level === "high" ? "HIGH" : docDetail.quality_level === "medium" ? "MEDIUM" : "LOW"}</span>
              <b className="arc-doc-score-big">{docDetail.quality_score}</b>
              <span className="arc-tag arc-purple">{docDetail.research_type || "未分类"}</span>
              {(docDetail.institutions || []).map((x: string, i: number) => <span key={i} className="arc-tag arc-blue">🏦 {x}</span>)}
              <span className="arc-tag">来源 {docDetail.source_count}</span>
              <span className="arc-tag arc-gray">{docDetail.first_seen_at?.slice(0, 16)}</span>
            </div>
            <div className="arc-drawer-meta-line">
              <span className="arc-tag arc-gray">最近 {docDetail.last_seen_at?.slice(0, 16)}</span>
              <span className="arc-tag">机构 {docDetail.institution_count}</span>
            </div>
            {docDetail.summary && (
              <div className="arc-doc-drawer-summary">
                <div className="arc-section-title">💡 核心观点</div>
                <div className="arc-doc-summary-text">{docDetail.summary}</div>
              </div>
            )}
            {(docDetail.stocks?.length > 0 || docDetail.event_relations?.length > 0) && (
              <div className="arc-doc-drawer-assoc">
                <div className="arc-section-title">🔗 关联</div>
                {docDetail.stocks?.length > 0 && (
                  <div className="arc-detail-row"><b>📈 股票</b><span>
                    {(docDetail.stocks as any[]).map((s: any, i: number) => <code key={i} className="arc-doc-code">{s.name || s.code}</code>)}
                  </span></div>
                )}
                {docDetail.event_relations?.length > 0 && (
                  <div className="arc-detail-row"><b>🔥 事件</b><span>
                    {(docDetail.event_relations as any[]).map((e: any, i: number) => (
                      <span key={i} className="arc-tag arc-orange">{e.title}{e.momentum ? ` · ${e.momentum}` : ""}</span>
                    ))}
                  </span></div>
                )}
              </div>
            )}
            {docDetail.source_chain?.length > 0 && (
              <div className="arc-doc-chain">
                <div className="arc-section-title">🕓 来源链（{docDetail.source_chain.length}）</div>
                {docDetail.source_chain.map((c: any, i: number) => (
                  <div key={i} className="arc-doc-chain-item">
                    <div className="arc-doc-chain-head">
                      <span className="arc-tag arc-cyan">{c.date?.slice(5, 16)}</span>
                      <span className="arc-tag">{c.source_topic || "—"}</span>
                      {c.institution ? <span className="arc-tag arc-blue">🏦 {c.institution}</span> : null}
                      <span className="arc-tag arc-gray">{c.from_user || "—"}</span>
                    </div>
                    <details className="arc-doc-chain-raw">
                      <summary>展开原文 ▼</summary>
                      <pre className="arc-doc-chain-pre">{c.raw_text}</pre>
                    </details>
                  </div>
                ))}
              </div>
            )}
            <div className="arc-rs-safety" style={{ marginTop: 10 }}>研究对象 = 归并后的多来源资讯聚合 · 质量分 = 机构/研报/股票/摘要加权 · 数据治理层 v2.3.1</div>
          </div>
        </div>
      )}

      {/* 研报详情抽屉 */}
      {reportDrawer && (
        <div className="arc-drawer-mask" onClick={() => setReportDrawer(null)}>
          <div className="arc-drawer" onClick={(e) => e.stopPropagation()}>
            <div className="arc-drawer-title">{reportDrawer.series?.title || "研报详情"}</div>
            <div className="arc-drawer-meta-line">
              <span className="arc-tag arc-purple">{reportDrawer.series?.institution || "未知机构"} · {reportDrawer.series?.report_type || ""}</span>
              <span className="arc-tag">v{reportDrawer.series?.current_version}</span>
              <span className="arc-tag">出现 {reportDrawer.series?.occurrence_count} 次</span>
              <span className="arc-tag arc-orange">{reportDrawer.verifications?.[0]?.verification_status || "待验证"}</span>
              <button className="arc-detail-close" onClick={() => setReportDrawer(null)}>✕</button>
            </div>
            <div className="arc-drawer-meta-line">
              <span className="arc-tag arc-gray">首发 {reportDrawer.series?.first_seen_at?.slice(0, 10)}</span>
              <span className="arc-tag arc-gray">最近 {reportDrawer.series?.last_seen_at?.slice(0, 10)}</span>
              <span className={`arc-tag ${reportDrawer.series?.status === "active" ? "arc-blue" : "arc-gray"}`}>{reportDrawer.series?.status}</span>
            </div>
            {reportDrawer.versions?.map((v: any, i: number) => (
              <div key={i} className="arc-drawer-fields">
                <div className="arc-section-title">版本 v{v.version_no} {v.changed_summary ? <em className="arc-change">{v.changed_summary}</em> : null}</div>
                {v.core_view ? <div className="arc-detail-row"><b>💡 核心观点</b><span>{v.core_view}</span></div> : null}
                {v.logic ? <div className="arc-detail-row"><b>🧠 推荐逻辑</b><span>{v.logic}</span></div> : null}
                {v.catalysts ? <div className="arc-detail-row"><b>⚡ 催化因素</b><span>{v.catalysts}</span></div> : null}
                {v.risks ? <div className="arc-detail-row"><b>⚠️ 风险因素</b><span>{v.risks}</span></div> : null}
                {v.valuation ? <div className="arc-detail-row"><b>💰 估值/目标价</b><span>{v.valuation}</span></div> : null}
                {v.stock_codes_json && JSON.parse(v.stock_codes_json).length > 0 ? (
                  <div className="arc-detail-row"><b>📈 涉及股票</b><span>{(JSON.parse(v.stock_codes_json) as string[]).map((c) => <code key={c}>{c}</code>)}</span></div>
                ) : null}
              </div>
            ))}
            {reportDrawer.verifications && reportDrawer.verifications.length > 0 && (
              <div className="arc-verify-block">
                <div className="arc-section-title">🧪 后续验证</div>
                {reportDrawer.verifications.map((v: any, i: number) => (
                  <div key={i} className="arc-verify-item">
                    <span className={v.verification_status === "待验证" ? "arc-tag arc-orange" : v.verification_status === "已验证" ? "arc-tag arc-red" : "arc-tag arc-gray"}>{v.verification_status}</span>
                    <span className="arc-tag">{v.event_type}</span>
                    <span className="arc-verify-text">{v.event_text}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* 消息详情抽屉（四层：标题/元信息/AI摘要/关联+原文） */}
      {drawer && (
        <div className="arc-drawer-mask" onClick={() => setDrawer(null)}>
          <div className="arc-drawer" onClick={(e) => e.stopPropagation()}>
            <div className="arc-drawer-title">{drawer.title || drawer.display_title || "未提取标题"}{stars(drawer.research_value)}</div>
            <div className="arc-drawer-meta-line">
              <span className={CT_CLASS[drawer.content_type] || CAT_CLASS[drawer.primary_category] || "arc-tag"}>{CT_LABEL[drawer.content_type] || CAT_LABEL[drawer.primary_category] || drawer.content_type}</span>
              {drawer.content_subtype && <span className="arc-tag">{drawer.content_subtype}</span>}
              <span className="arc-tag">{drawer.source_topic}</span>
              <span className="arc-tag arc-gray">{drawer.date}</span>
              <button className="arc-detail-close" onClick={() => setDrawer(null)}>✕</button>
            </div>
            <div className="arc-drawer-meta-line">
              {drawer.institution && <span className="arc-tag arc-purple">{drawer.institution}{drawer.research_team ? `·${drawer.research_team}` : ""}</span>}
              {drawer.original_source && <span className="arc-tag">原始来源：{drawer.original_source}</span>}
              {drawer.source_name ? <span className="arc-tag">采集：{drawer.source_name}</span> : null}
              {drawer.from_user && drawer.from_user !== drawer.source_name ? <span className="arc-tag arc-gray">转发：{drawer.from_user}</span> : null}
            </div>
            {drawer.summary && (
              <div className="arc-drawer-summary">📝 <b>摘要</b>：{drawer.summary}</div>
            )}
            {drawer.msg_type === "image" && (
              <div className="arc-drawer-img">
                {drawer.relative_image_path && <img src={`https://reports.wmsora.vip/${drawer.relative_image_path}`} alt="资讯图片" />}
                {drawer.vision_summary ? <div className="arc-drawer-vision">🤖 Vision：{drawer.vision_summary}</div> : <span className="arc-tag arc-orange">待 Vision 分析</span>}
              </div>
            )}
            <div className="arc-drawer-assoc">
              {(drawer.stocks?.length > 0 || drawer.industries?.length > 0) && (
                <div className="arc-detail-row"><b>关联</b><span>
                  {drawer.stocks?.map((c: string) => <code key={c}>{c}</code>)}
                  {drawer.industries?.map((x: string) => <span key={x} className="arc-tag">{x}</span>)}
                </span></div>
              )}
              {drawer.report && (
                <div className="arc-drawer-report">
                  <div className="arc-report-inst">{drawer.report.institution}</div>
                  <div className="arc-report-title">{drawer.report.title}</div>
                  <div className="arc-report-meta">
                    <span className="arc-tag arc-purple">v{drawer.report.current_version}</span>
                    <span className={drawer.verification_status === "待验证" ? "arc-tag arc-orange" : "arc-tag arc-blue"}>{drawer.verification_status || "待验证"}</span>
                    <button className="arc-btn" onClick={() => openReportDrawer(drawer.report.series_id)}>查看研报</button>
                  </div>
                </div>
              )}
              <div className="arc-detail-row"><b>置信度</b><span>{(drawer.confidence_score ?? 0).toFixed(2)} {drawer.confidence ? `(${drawer.confidence})` : ""}</span></div>
              {drawer.sentiment ? <div className="arc-detail-row"><b>情绪</b><span>{drawer.sentiment}</span></div> : null}
              {drawer.review_required ? <div className="arc-detail-row"><b>复核</b><span className="arc-tag arc-orange">{drawer.review_reason_detail || drawer.review_reason || "待复核"}</span></div> : null}
            </div>
            <div className="arc-drawer-text">{drawer.raw_text}</div>
            <div className="arc-drawer-meta">
              {drawer.message_id ? <span className="arc-tag">ID：{drawer.message_id}</span> : null}
              {drawer.reply_to_message_id ? <span className="arc-tag">回复：{drawer.reply_to_message_id}</span> : null}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
