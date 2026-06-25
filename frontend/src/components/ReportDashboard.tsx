import React, { useEffect, useState, useCallback, useRef } from 'react';
import { datasets } from '../api';
import toast from 'react-hot-toast';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  LineChart, Line,
} from 'recharts';
import {
  BarChart3, Table2, Filter, Search, Loader2,
  TrendingUp, Wallet, Package, Percent, AlertCircle, Database, Settings2,
  FileDown, RefreshCw, ToggleLeft, ToggleRight, Layers,
} from 'lucide-react';
import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';

interface ReportGroup {
  name: string;
  plan_qty: number; plan_cost: number;
  actual_qty: number; actual_cost: number;
  execution_pct_qty: number; execution_pct_cost: number;
  count: number;
  volume: { uom: string; qty: number }[];
}

interface TrendPoint {
  month: string;
  plan_cost: number;
  actual_cost: number;
  actual_qty: number;
  cumulative_actual_cost: number;
}

interface TopVolumeItem {
  name: string;
  volume_qty: number;
  uom: string;
  plan_cost: number;
  actual_cost: number;
}

interface ReportData {
  summary: {
    total_plan_qty: number; total_plan_cost: number;
    total_actual_qty: number; total_actual_cost: number;
    execution_pct_qty: number; execution_pct_cost: number;
    total_rows: number;
    volume_by_uom: { uom: string; qty: number }[];
  };
  groups: ReportGroup[];
  directions: string[];
  budget_elements: string[];
  trend: TrendPoint[];
  top_volume: TopVolumeItem[];
}

const fmt = (v: number) => {
  if (Math.abs(v) >= 1_000_000) return (v / 1_000_000).toFixed(2) + ' млн';
  if (Math.abs(v) >= 1_000) return (v / 1_000).toFixed(2) + ' тыс';
  return v.toLocaleString('ru-RU', { maximumFractionDigits: 2 });
};

const ReportDashboard: React.FC = () => {
  const [allDatasets, setAllDatasets] = useState<any[]>([]);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [loadingDs, setLoadingDs] = useState(true);
  const [data, setData] = useState<ReportData | null>(null);
  const [loading, setLoading] = useState(false);
  const [direction, setDirection] = useState('');
  const [budgetEl, setBudgetEl] = useState('');
  const [search, setSearch] = useState('');
  const [showTable, setShowTable] = useState(false);
  const [chartMode, setChartMode] = useState<'qty' | 'cost'>('cost');
  const [viewMode, setViewMode] = useState<'cost' | 'volume'>('cost');
  const [groupBy, setGroupBy] = useState<'material' | 'category' | 'month'>('material');
  const [yearFilter, setYearFilter] = useState<number | ''>('');
  const [error, setError] = useState('');

  const [colMap, setColMap] = useState<Record<string, string>>({});
  const [planQtyCol, setPlanQtyCol] = useState('');
  const [planCostCol, setPlanCostCol] = useState('');
  const [actualQtyCol, setActualQtyCol] = useState('');
  const [actualCostCol, setActualCostCol] = useState('');
  const [groupCol, setGroupCol] = useState('');
  const [directionCol, setDirectionCol] = useState('');
  const [budgetCol, setBudgetCol] = useState('');
  const [unitCol, setUnitCol] = useState('');
  const [yearCol, setYearCol] = useState('');
  const [monthCol, setMonthCol] = useState('');
  const [showColConfig, setShowColConfig] = useState(false);
  const [overriddenCols, setOverriddenCols] = useState<Set<string>>(new Set());
  const [exportingPdf, setExportingPdf] = useState(false);
  const reportRef = useRef<HTMLDivElement>(null);
  const pdfContentRef = useRef<HTMLDivElement>(null);

  const colLabel = (id: string) => id ? (colMap[id] || id) : '—';
  const availableCols = Object.entries(colMap).map(([id, header]) => ({
    id, header: header || id,
  }));

  const [suggestionsData, setSuggestionsData] = useState<Record<string, any>>({});

  const currentYear = new Date().getFullYear();
  const yearOptions = [currentYear, currentYear - 1, currentYear - 2, currentYear - 3];

  useEffect(() => {
    setLoadingDs(true);
    datasets.list(0, 200, false)
      .then(res => {
        const items = res.data.items || [];
        setAllDatasets(items);
        if (items.length > 0) setSelectedIds([items[0].id]);
      })
      .catch(() => setError('Ошибка загрузки таблиц'))
      .finally(() => setLoadingDs(false));
  }, []);

  useEffect(() => {
    if (selectedIds.length === 0) return;
    setOverriddenCols(new Set());
    setShowColConfig(false);
    datasets.suggestColumns(selectedIds)
      .then(res => {
        const cm = res.data.col_map || {};
        setColMap(cm);
        setSuggestionsData(res.data.suggestions || {});
        const sugs = res.data.suggestions || {};
        const firstKey = Object.keys(sugs)[0];
        if (firstKey) {
          const m = sugs[firstKey];
          setPlanQtyCol(m.plan_qty || '');
          setPlanCostCol(m.plan_cost || '');
          setActualQtyCol(m.actual_qty || '');
          setActualCostCol(m.actual_cost || '');
          setGroupCol(m.group || '');
          setDirectionCol(m.direction || '');
          setBudgetCol(m.budget || '');
          setUnitCol(m.unit || '');
          setYearCol(m.year || '');
          setMonthCol(m.month || '');
        }
      })
      .catch(() => {});
  }, [selectedIds]);

  const handleColChange = (setter: (v: string) => void, key: string, value: string) => {
    setter(value);
    setOverriddenCols(prev => {
      const next = new Set(prev);
      if (value) next.add(key);
      else next.delete(key);
      return next;
    });
  };

  const fetchReport = useCallback(async () => {
    if (selectedIds.length === 0) return;
    setLoading(true);
    setError('');
    try {
      const params: Record<string, any> = { dataset_ids: selectedIds, include_rows: false, group_by: groupBy };

      if (yearFilter) params.year_filter = yearFilter;

      const hasOverrides = overriddenCols.size > 0;
      if (hasOverrides) {
        if (planQtyCol) params.plan_qty_col = planQtyCol;
        if (planCostCol) params.plan_cost_col = planCostCol;
        if (actualQtyCol) params.actual_qty_col = actualQtyCol;
        if (actualCostCol) params.actual_cost_col = actualCostCol;
        if (groupCol) params.group_col = groupCol;
        if (directionCol) params.direction_col = directionCol;
        if (budgetCol) params.budget_col = budgetCol;
        if (unitCol) params.unit_col = unitCol;
        if (yearCol) params.year_col = yearCol;
        if (monthCol) params.month_col = monthCol;
      } else if (Object.keys(suggestionsData).length > 0) {
        const mappings: Record<string, any> = {};
        for (const [dsId, s] of Object.entries(suggestionsData)) {
          const sug = s as any;
          mappings[dsId] = {
            plan_qty: sug.plan_qty || '',
            plan_cost: sug.plan_cost || '',
            actual_qty: sug.actual_qty || '',
            actual_cost: sug.actual_cost || '',
            group: sug.group || '',
            direction: sug.direction || '',
            budget: sug.budget || '',
            unit: sug.unit || '',
            year: sug.year || '',
            month: sug.month || '',
          };
        }
        params.mappings_json = JSON.stringify(mappings);
      }

      if (direction) params.filter_val = direction;
      else if (budgetEl) params.filter_val = budgetEl;
      if (search) params.search = search;
      const res = await datasets.getReport(params as any);
      setData(res.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Ошибка загрузки отчёта');
    } finally {
      setLoading(false);
    }
  }, [selectedIds, overriddenCols, planQtyCol, planCostCol, actualQtyCol, actualCostCol, groupCol, directionCol, budgetCol, unitCol, yearCol, monthCol, direction, budgetEl, search, suggestionsData, groupBy, yearFilter]);

  useEffect(() => { fetchReport(); }, [fetchReport]);

  const toggleDataset = (id: number) => {
    setSelectedIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  };

  const handleResetMapping = () => {
    setOverriddenCols(new Set());
    setShowColConfig(false);
    setPlanQtyCol('');
    setPlanCostCol('');
    setActualQtyCol('');
    setActualCostCol('');
    setGroupCol('');
    setDirectionCol('');
    setBudgetCol('');
    setUnitCol('');
    setYearCol('');
    setMonthCol('');
  };

  const handleExportPdf = async () => {
    if (!data) return;
    setExportingPdf(true);
    try {
      const dsNames = allDatasets.filter(d => selectedIds.includes(d.id)).map(d => d.name).join(', ');
      const sum = data.summary;

      const groupRows = data.groups
        .filter(g => g.plan_qty > 0 || g.actual_qty > 0)
        .slice(0, 50)
        .map(g => {
          const volStr = g.volume?.map(v => `${fmt(v.qty)} ${v.uom}`).join(' + ') || '';
          return `<tr>
            <td style="text-align:left;padding:3px 8px;font-size:10px;border-bottom:1px solid #ddd">${g.name}</td>
            <td style="text-align:right;padding:3px 8px;font-size:10px;border-bottom:1px solid #ddd">${fmt(g.plan_qty)}</td>
            <td style="text-align:right;padding:3px 8px;font-size:10px;border-bottom:1px solid #ddd">${fmt(g.actual_qty)}</td>
            <td style="text-align:right;padding:3px 8px;font-size:10px;border-bottom:1px solid #ddd">${g.execution_pct_qty}%</td>
            <td style="text-align:right;padding:3px 8px;font-size:10px;border-bottom:1px solid #ddd">${fmt(g.plan_cost)} ₽</td>
            <td style="text-align:right;padding:3px 8px;font-size:10px;border-bottom:1px solid #ddd">${fmt(g.actual_cost)} ₽</td>
            <td style="text-align:right;padding:3px 8px;font-size:10px;border-bottom:1px solid #ddd">${g.execution_pct_cost}%</td>
            ${volStr ? `<td style="text-align:right;padding:3px 8px;font-size:10px;border-bottom:1px solid #ddd">${volStr}</td>` : ''}
          </tr>`;
        }).join('\n');

      if (pdfContentRef.current) {
        pdfContentRef.current.innerHTML = `<!DOCTYPE html>
<div style="font-family:'Segoe UI',Arial,sans-serif;padding:30px 40px;color:#222;width:700px">
  <div style="font-size:22px;font-weight:bold;margin-bottom:2px">Отчёт план/факт</div>
  <div style="font-size:11px;color:#666;margin-bottom:16px">Дата: ${new Date().toLocaleDateString('ru-RU')} | Таблицы: ${dsNames}${direction ? ' | Фильтр: ' + direction : ''}${budgetEl ? ' | Фильтр: ' + budgetEl : ''}${yearFilter ? ' | Год: ' + yearFilter : ''}</div>

  <div style="font-size:14px;font-weight:600;margin:14px 0 6px">Сводка</div>
  <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px">
    <div style="background:#f0f0f5;padding:10px 14px;border-radius:6px;min-width:120px">
      <div style="font-size:16px;font-weight:bold">${fmt(sum.total_plan_qty)}</div>
      <div style="font-size:9px;color:#666">Кол-во план</div>
    </div>
    <div style="background:#f0f0f5;padding:10px 14px;border-radius:6px;min-width:120px">
      <div style="font-size:16px;font-weight:bold">${fmt(sum.total_actual_qty)}</div>
      <div style="font-size:9px;color:#666">Кол-во факт</div>
    </div>
    <div style="background:#f0f0f5;padding:10px 14px;border-radius:6px;min-width:120px">
      <div style="font-size:16px;font-weight:bold">${sum.execution_pct_qty}%</div>
      <div style="font-size:9px;color:#666">Исполнение по кол-ву</div>
    </div>
    <div style="background:#f0f0f5;padding:10px 14px;border-radius:6px;min-width:120px">
      <div style="font-size:16px;font-weight:bold">${fmt(sum.total_plan_cost)} ₽</div>
      <div style="font-size:9px;color:#666">Стоимость план</div>
    </div>
    <div style="background:#f0f0f5;padding:10px 14px;border-radius:6px;min-width:120px">
      <div style="font-size:16px;font-weight:bold">${fmt(sum.total_actual_cost)} ₽</div>
      <div style="font-size:9px;color:#666">Стоимость факт</div>
    </div>
    <div style="background:#f0f0f5;padding:10px 14px;border-radius:6px;min-width:120px">
      <div style="font-size:16px;font-weight:bold">${sum.execution_pct_cost}%</div>
      <div style="font-size:9px;color:#666">Исполнение по стоимости</div>
    </div>
  </div>

  ${sum.volume_by_uom?.length ? `<div style="font-size:11px;color:#444;margin-bottom:10px">
    <b>Реальный объём:</b> ${sum.volume_by_uom.map((v: any) => `${fmt(v.qty)} ${v.uom}`).join(' + ')}
  </div>` : ''}

  <div style="font-size:14px;font-weight:600;margin:14px 0 6px">Детализация по группам</div>
  <table style="border-collapse:collapse;width:100%">
    <thead><tr style="background:#eee">
      <th style="text-align:left;padding:4px 8px;font-size:9px;color:#555;border-bottom:2px solid #bbb">Группа</th>
      <th style="text-align:right;padding:4px 8px;font-size:9px;color:#555;border-bottom:2px solid #bbb">Кол-во план</th>
      <th style="text-align:right;padding:4px 8px;font-size:9px;color:#555;border-bottom:2px solid #bbb">Кол-во факт</th>
      <th style="text-align:right;padding:4px 8px;font-size:9px;color:#555;border-bottom:2px solid #bbb">% (кол-во)</th>
      <th style="text-align:right;padding:4px 8px;font-size:9px;color:#555;border-bottom:2px solid #bbb">Стоимость план</th>
      <th style="text-align:right;padding:4px 8px;font-size:9px;color:#555;border-bottom:2px solid #bbb">Стоимость факт</th>
      <th style="text-align:right;padding:4px 8px;font-size:9px;color:#555;border-bottom:2px solid #bbb">% (стоим.)</th>
      ${sum.volume_by_uom?.length ? '<th style="text-align:right;padding:4px 8px;font-size:9px;color:#555;border-bottom:2px solid #bbb">Объём</th>' : ''}
    </tr></thead>
    <tbody>${groupRows}
    <tr style="font-weight:bold">
      <td style="text-align:left;padding:5px 8px;font-size:10px;border-top:2px solid #333">Итого</td>
      <td style="text-align:right;padding:5px 8px;font-size:10px;border-top:2px solid #333">${fmt(sum.total_plan_qty)}</td>
      <td style="text-align:right;padding:5px 8px;font-size:10px;border-top:2px solid #333">${fmt(sum.total_actual_qty)}</td>
      <td style="text-align:right;padding:5px 8px;font-size:10px;border-top:2px solid #333">${sum.execution_pct_qty}%</td>
      <td style="text-align:right;padding:5px 8px;font-size:10px;border-top:2px solid #333">${fmt(sum.total_plan_cost)} ₽</td>
      <td style="text-align:right;padding:5px 8px;font-size:10px;border-top:2px solid #333">${fmt(sum.total_actual_cost)} ₽</td>
      <td style="text-align:right;padding:5px 8px;font-size:10px;border-top:2px solid #333">${sum.execution_pct_cost}%</td>
      ${sum.volume_by_uom?.length ? `<td style="text-align:right;padding:5px 8px;font-size:10px;border-top:2px solid #333">${sum.volume_by_uom.map((v: any) => `${fmt(v.qty)} ${v.uom}`).join(' + ')}</td>` : ''}
    </tr></tbody>
  </table>

  ${data.trend?.length ? `
  <div style="font-size:14px;font-weight:600;margin:16px 0 6px">Динамика по месяцам</div>
  <table style="border-collapse:collapse;width:100%">
    <thead><tr style="background:#eee">
      <th style="text-align:left;padding:4px 8px;font-size:9px;color:#555;border-bottom:2px solid #bbb">Месяц</th>
      <th style="text-align:right;padding:4px 8px;font-size:9px;color:#555;border-bottom:2px solid #bbb">План</th>
      <th style="text-align:right;padding:4px 8px;font-size:9px;color:#555;border-bottom:2px solid #bbb">Факт</th>
      <th style="text-align:right;padding:4px 8px;font-size:9px;color:#555;border-bottom:2px solid #bbb">Накопленный факт</th>
    </tr></thead>
    <tbody>${data.trend.map((t: any) => `<tr>
      <td style="text-align:left;padding:3px 8px;font-size:10px;border-bottom:1px solid #ddd">${t.month}</td>
      <td style="text-align:right;padding:3px 8px;font-size:10px;border-bottom:1px solid #ddd">${fmt(t.plan_cost)} ₽</td>
      <td style="text-align:right;padding:3px 8px;font-size:10px;border-bottom:1px solid #ddd">${fmt(t.actual_cost)} ₽</td>
      <td style="text-align:right;padding:3px 8px;font-size:10px;border-bottom:1px solid #ddd">${fmt(t.cumulative_actual_cost)} ₽</td>
    </tr>`).join('\n')}</tbody>
  </table>` : ''}
</div>`;

        await new Promise(r => setTimeout(r, 100));
      }

      let canvas: HTMLCanvasElement;
      if (pdfContentRef.current) {
        canvas = await html2canvas(pdfContentRef.current, {
          scale: 2,
          useCORS: true,
          backgroundColor: '#ffffff',
          width: 700,
          logging: false,
        });
      } else if (reportRef.current) {
        canvas = await html2canvas(reportRef.current, {
          scale: 2,
          useCORS: true,
          backgroundColor: '#ffffff',
        });
      } else return;

      const imgData = canvas.toDataURL('image/png');
      const pdf = new jsPDF('p', 'mm', 'a4');
      const pageW = pdf.internal.pageSize.getWidth();
      const pageH = pdf.internal.pageSize.getHeight();
      const margin = 10;
      const imgW = pageW - 2 * margin;
      const imgH = (canvas.height * imgW) / canvas.width;

      let curY = margin;
      let remH = imgH;
      pdf.addImage(imgData, 'PNG', margin, curY, imgW, imgH);
      remH -= pageH;
      while (remH > 0) {
        curY = margin - remH;
        pdf.addPage();
        pdf.addImage(imgData, 'PNG', margin, curY, imgW, imgH);
        remH -= pageH;
      }

      pdf.save(`otchet-plan-fakt-${new Date().toISOString().slice(0, 10)}.pdf`);

      if (pdfContentRef.current) {
        pdfContentRef.current.innerHTML = '';
      }
    } catch {
      toast.error('Ошибка создания PDF');
    } finally {
      setExportingPdf(false);
    }
  };

  const ColSelect = ({ value, onChange, label, colKey }: { value: string; onChange: (v: string) => void; label: string; colKey: string }) => (
    <div>
      <label className="text-xs text-slate-500 mb-1 block">{label}</label>
      <select value={value} onChange={e => handleColChange(onChange, colKey, e.target.value)}
        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
      >
        <option value="">— не выбрано —</option>
        {availableCols.map(c => (
          <option key={c.id} value={c.id}>{c.header}</option>
        ))}
      </select>
    </div>
  );

  if (loadingDs) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex items-center gap-2 text-slate-500">
          <Loader2 className="w-5 h-5 animate-spin text-indigo-500" />
          Загрузка таблиц...
        </div>
      </div>
    );
  }

  if (allDatasets.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4 text-slate-400">
        <Database className="w-12 h-12" />
        <p className="text-lg">Нет доступных таблиц</p>
        <p className="text-sm">Импортируйте Excel-файл в разделе "Таблицы"</p>
      </div>
    );
  }

  const chartData = data?.groups.filter(g => g.plan_qty > 0 || g.actual_qty > 0) || [];
  const isQty = chartMode === 'qty';
  // const isVolume = viewMode === 'volume';

  const hasOverrides = overriddenCols.size > 0;

  const MappingBadge = ({ label, colId }: { label: string; colId: string }) => (
    <span className="inline-flex items-center gap-1 text-slate-600">
      <span className="text-slate-400">{label}:</span>
      <span className="font-medium">{colLabel(colId)}</span>
    </span>
  );

  return (
    <div className="space-y-6" ref={reportRef}>
      <div ref={pdfContentRef} style={{ position: 'absolute', left: '-9999px', top: 0, width: 700 }} />
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Отчёт план/факт</h2>
          <p className="text-slate-500 mt-1">Исполнение поставок материалов</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex rounded-lg border border-slate-200 overflow-hidden">
            <button onClick={() => setViewMode('cost')}
              className={`px-3 py-2 text-xs font-medium transition-colors ${viewMode === 'cost' ? 'bg-indigo-600 text-white' : 'bg-white text-slate-600 hover:bg-slate-50'}`}>
              <Wallet className="w-3.5 h-3.5 inline mr-1" />Суммы
            </button>
            <button onClick={() => setViewMode('volume')}
              className={`px-3 py-2 text-xs font-medium transition-colors ${viewMode === 'volume' ? 'bg-indigo-600 text-white' : 'bg-white text-slate-600 hover:bg-slate-50'}`}>
              <Package className="w-3.5 h-3.5 inline mr-1" />Объём
            </button>
          </div>
          {data && !loading && (
            <button onClick={handleExportPdf} disabled={exportingPdf}
              className="flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition-colors disabled:opacity-50"
            >
              {exportingPdf ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileDown className="w-4 h-4" />}
              {exportingPdf ? 'Сохранение...' : 'PDF'}
            </button>
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-slate-700 font-medium">
            <Filter className="w-4 h-4" /> Фильтры
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {allDatasets.map(ds => {
            const dsSug = suggestionsData[ds.id];
            const dsType = dsSug?._table_type;
            const typeLabel = dsType === 'plan' ? 'план' : dsType === 'fact' ? 'факт' : null;
            return (
              <button key={ds.id} onClick={() => toggleDataset(ds.id)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors flex items-center gap-1.5 ${
                  selectedIds.includes(ds.id)
                    ? 'bg-indigo-100 border-indigo-300 text-indigo-700'
                    : 'bg-white border-slate-200 text-slate-600 hover:border-slate-300'
                }`}
              >
                {ds.name}
                {typeLabel && (
                  <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                    dsType === 'plan' ? 'bg-indigo-200 text-indigo-700' : 'bg-emerald-200 text-emerald-700'
                  }`}>
                    {typeLabel}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Mapping summary */}
        {Object.keys(colMap).length > 0 && (
          <div className="bg-slate-50 rounded-lg px-4 py-2.5 border border-slate-200 flex items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
              <span className="text-slate-400">Подобрано:</span>
              <MappingBadge label="Кол-во план" colId={planQtyCol} />
              <MappingBadge label="Стоимость план" colId={planCostCol} />
              <MappingBadge label="Кол-во факт" colId={actualQtyCol} />
              <MappingBadge label="Стоимость факт" colId={actualCostCol} />
              <MappingBadge label="Группировка" colId={groupCol} />
            </div>
            <div className="flex items-center gap-2">
              <span className={`flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full ${hasOverrides ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'}`}>
                {hasOverrides ? <ToggleRight className="w-3 h-3" /> : <ToggleLeft className="w-3 h-3" />}
                {hasOverrides ? 'Вручную' : 'Авто'}
              </span>
              {hasOverrides && (
                <button onClick={handleResetMapping}
                  className="flex items-center gap-1 px-2 py-1 text-xs text-amber-600 hover:text-amber-800 hover:bg-amber-50 rounded-md transition-colors"
                >
                  <RefreshCw className="w-3 h-3" />
                  Сбросить
                </button>
              )}
              <button onClick={() => setShowColConfig(!showColConfig)}
                className="flex items-center gap-1 px-2 py-1 text-xs text-slate-500 hover:text-indigo-600 hover:bg-indigo-50 rounded-md transition-colors flex-shrink-0"
              >
                <Settings2 className="w-3 h-3" />
                {showColConfig ? 'Готово' : 'Колонки'}
              </button>
            </div>
          </div>
        )}

        {showColConfig && (
          <div className="bg-slate-50 rounded-xl p-4 border border-slate-200">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs text-slate-500">При изменении колонок отключится автоподбор</span>
              {hasOverrides && (
                <button onClick={handleResetMapping}
                  className="flex items-center gap-1 px-2 py-1 text-xs text-amber-600 hover:bg-amber-50 rounded-md transition-colors"
                >
                  <RefreshCw className="w-3 h-3" />
                  Вернуть автоподбор
                </button>
              )}
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
              <ColSelect label="Кол-во план" value={planQtyCol} onChange={setPlanQtyCol} colKey="plan_qty" />
              <ColSelect label="Стоимость план" value={planCostCol} onChange={setPlanCostCol} colKey="plan_cost" />
              <ColSelect label="Кол-во факт" value={actualQtyCol} onChange={setActualQtyCol} colKey="actual_qty" />
              <ColSelect label="Стоимость факт" value={actualCostCol} onChange={setActualCostCol} colKey="actual_cost" />
              <ColSelect label="Группировка" value={groupCol} onChange={setGroupCol} colKey="group" />
              <ColSelect label="Направление" value={directionCol} onChange={setDirectionCol} colKey="direction" />
              <ColSelect label="Бюджет" value={budgetCol} onChange={setBudgetCol} colKey="budget" />
              <ColSelect label="ЕИ" value={unitCol} onChange={setUnitCol} colKey="unit" />
              <ColSelect label="Год" value={yearCol} onChange={setYearCol} colKey="year" />
              <ColSelect label="Месяц" value={monthCol} onChange={setMonthCol} colKey="month" />
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          <div>
            <label className="text-xs text-slate-500 mb-1 block">Направление</label>
            <select value={direction} onChange={e => setDirection(e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            >
              <option value="">Все направления</option>
              {data?.directions.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-500 mb-1 block">Элемент бюджета</label>
            <select value={budgetEl} onChange={e => setBudgetEl(e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            >
              <option value="">Все элементы</option>
              {data?.budget_elements.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-500 mb-1 block">Год</label>
            <select value={yearFilter} onChange={e => setYearFilter(e.target.value === '' ? '' : Number(e.target.value))}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            >
              <option value="">Все годы</option>
              {yearOptions.map(y => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-500 mb-1 block">Группировка</label>
            <select value={groupBy} onChange={e => setGroupBy(e.target.value as any)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            >
              <option value="material">По материалам</option>
              <option value="category">По категориям</option>
              <option value="month">По месяцам</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-500 mb-1 block">Поиск</label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input type="text" value={search} onChange={e => setSearch(e.target.value)}
                placeholder="Название материала..."
                className="w-full rounded-lg border border-slate-200 pl-9 pr-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              />
            </div>
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-2xl p-4 flex items-center gap-3 text-red-700">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <span className="text-sm">{error}</span>
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center h-40">
          <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
        </div>
      )}

      {selectedIds.length === 0 && !loading && (
        <div className="flex flex-col items-center justify-center h-40 text-slate-400 gap-2">
          <Database className="w-8 h-8" />
          <span className="text-sm">Выберите таблицу для построения отчёта</span>
        </div>
      )}

      {data && !loading && (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
            <SummaryCard label="План (сумма)" value={fmt(data.summary.total_plan_cost) + ' ₽'} icon={Wallet} color="text-indigo-600" bg="bg-indigo-100" />
            <SummaryCard label="Факт (сумма)" value={fmt(data.summary.total_actual_cost) + ' ₽'} icon={TrendingUp} color="text-emerald-600" bg="bg-emerald-100" />
            <SummaryCard label="Исполнение" value={data.summary.execution_pct_cost + '%'} icon={Percent} color="text-amber-600" bg="bg-amber-100" />
            <SummaryCard label="Кол-во план" value={fmt(data.summary.total_plan_qty)} icon={Package} color="text-indigo-600" bg="bg-indigo-100" />
            <SummaryCard label="Кол-во факт" value={fmt(data.summary.total_actual_qty)} icon={Package} color="text-emerald-600" bg="bg-emerald-100" />
            <SummaryCard label="% по кол-ву" value={data.summary.execution_pct_qty + '%'} icon={Percent} color="text-amber-600" bg="bg-amber-100" />
          </div>

          {/* Volume by UOM */}
          {data.summary.volume_by_uom?.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-200 p-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-700 mb-3">
                <Package className="w-4 h-4 text-indigo-600" />
                Реальный объём (факт)
              </div>
              <div className="flex flex-wrap gap-3">
                {data.summary.volume_by_uom.map(v => (
                  <div key={v.uom} className="bg-indigo-50 rounded-xl px-4 py-3 border border-indigo-100">
                    <div className="text-lg font-bold text-indigo-700">{fmt(v.qty)}</div>
                    <div className="text-xs text-indigo-500">{v.uom}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Chart */}
          {chartData.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-200 p-6">
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-2">
                  <BarChart3 className="w-5 h-5 text-indigo-600" />
                  <h3 className="font-semibold text-slate-800">План vs Факт</h3>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => setChartMode('qty')}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium border ${isQty ? 'bg-indigo-100 border-indigo-300 text-indigo-700' : 'bg-white border-slate-200 text-slate-600'}`}>По количеству</button>
                  <button onClick={() => setChartMode('cost')}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium border ${!isQty ? 'bg-indigo-100 border-indigo-300 text-indigo-700' : 'bg-white border-slate-200 text-slate-600'}`}>По стоимости</button>
                </div>
              </div>
              <ResponsiveContainer width="100%" height={350}>
                <BarChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 60 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#64748b' }} angle={-30} textAnchor="end" height={80} />
                  <YAxis tick={{ fontSize: 11, fill: '#64748b' }} />
                  <Tooltip contentStyle={{ borderRadius: '12px', border: '1px solid #e2e8f0', fontSize: '13px' }}
                    formatter={(value: any) => [fmt(Number(value) || 0), isQty ? 'Кол-во' : 'Стоимость']} />
                  <Legend />
                  <Bar dataKey={isQty ? 'plan_qty' : 'plan_cost'} name="План" fill="#6366f1" radius={[4, 4, 0, 0]} />
                  <Bar dataKey={isQty ? 'actual_qty' : 'actual_cost'} name="Факт" fill="#10b981" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Trend Chart (cumulative) */}
          {data.trend?.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-200 p-6">
              <div className="flex items-center gap-2 mb-6">
                <TrendingUp className="w-5 h-5 text-indigo-600" />
                <h3 className="font-semibold text-slate-800">Накопленный факт по месяцам</h3>
              </div>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={data.trend} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#64748b' }} />
                  <YAxis tick={{ fontSize: 11, fill: '#64748b' }} />
                  <Tooltip contentStyle={{ borderRadius: '12px', border: '1px solid #e2e8f0', fontSize: '13px' }}
                    formatter={(value: any) => [fmt(Number(value) || 0) + ' ₽', undefined]} />
                  <Legend />
                  <Line type="monotone" dataKey="plan_cost" name="План" stroke="#6366f1" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="actual_cost" name="Факт" stroke="#10b981" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="cumulative_actual_cost" name="Накопленный факт" stroke="#f59e0b" strokeWidth={3} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Top 10 Volume */}
          {data.top_volume?.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-200 p-6">
              <div className="flex items-center gap-2 mb-4">
                <Layers className="w-5 h-5 text-indigo-600" />
                <h3 className="font-semibold text-slate-800">Топ-10 материалов по объёму</h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200">
                      <th className="text-left px-4 py-3 font-semibold text-slate-600">Материал</th>
                      <th className="text-right px-4 py-3 font-semibold text-slate-600">Объём</th>
                      <th className="text-right px-4 py-3 font-semibold text-slate-600">ЕИ</th>
                      <th className="text-right px-4 py-3 font-semibold text-slate-600">План, ₽</th>
                      <th className="text-right px-4 py-3 font-semibold text-slate-600">Факт, ₽</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.top_volume.map((item, i) => (
                      <tr key={i} className="border-b border-slate-100 hover:bg-slate-50">
                        <td className="px-4 py-3 font-medium text-slate-800">{item.name}</td>
                        <td className="px-4 py-3 text-right text-slate-600">{fmt(item.volume_qty)}</td>
                        <td className="px-4 py-3 text-right text-slate-600">{item.uom}</td>
                        <td className="px-4 py-3 text-right text-slate-600">{fmt(item.plan_cost)}</td>
                        <td className="px-4 py-3 text-right text-slate-600">{fmt(item.actual_cost)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Table button */}
          {chartData.length > 0 && (
            <div className="flex justify-end">
              <button onClick={() => setShowTable(!showTable)}
                className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-indigo-600 bg-indigo-50 rounded-lg hover:bg-indigo-100 transition-colors">
                <Table2 className="w-4 h-4" />
                {showTable ? 'Скрыть таблицу' : 'Показать детальную таблицу'}
              </button>
            </div>
          )}

          {/* Table */}
          {showTable && chartData.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200">
                      <th className="text-left px-4 py-3 font-semibold text-slate-600">Группа</th>
                      <th className="text-right px-4 py-3 font-semibold text-slate-600">Кол-во план</th>
                      <th className="text-right px-4 py-3 font-semibold text-slate-600">Кол-во факт</th>
                      <th className="text-right px-4 py-3 font-semibold text-slate-600">% (кол-во)</th>
                      <th className="text-right px-4 py-3 font-semibold text-slate-600">Стоимость план</th>
                      <th className="text-right px-4 py-3 font-semibold text-slate-600">Стоимость факт</th>
                      <th className="text-right px-4 py-3 font-semibold text-slate-600">% (стоим.)</th>
                      <th className="text-right px-4 py-3 font-semibold text-slate-600">Объём</th>
                      <th className="text-right px-4 py-3 font-semibold text-slate-600">Строк</th>
                    </tr>
                  </thead>
                  <tbody>
                    {chartData.map((g, i) => {
                      const volStr = g.volume?.map((v: any) => `${fmt(v.qty)} ${v.uom}`).join(' + ') || '—';
                      return (
                        <tr key={i} className="border-b border-slate-100 hover:bg-slate-50">
                          <td className="px-4 py-3 font-medium text-slate-800">{g.name}</td>
                          <td className="px-4 py-3 text-right text-slate-600">{fmt(g.plan_qty)}</td>
                          <td className="px-4 py-3 text-right text-slate-600">{fmt(g.actual_qty)}</td>
                          <td className={`px-4 py-3 text-right font-medium ${g.execution_pct_qty >= 80 ? 'text-emerald-600' : g.execution_pct_qty >= 50 ? 'text-amber-600' : 'text-red-600'}`}>{g.execution_pct_qty}%</td>
                          <td className="px-4 py-3 text-right text-slate-600">{fmt(g.plan_cost)} ₽</td>
                          <td className="px-4 py-3 text-right text-slate-600">{fmt(g.actual_cost)} ₽</td>
                          <td className={`px-4 py-3 text-right font-medium ${g.execution_pct_cost >= 80 ? 'text-emerald-600' : g.execution_pct_cost >= 50 ? 'text-amber-600' : 'text-red-600'}`}>{g.execution_pct_cost}%</td>
                          <td className="px-4 py-3 text-right text-slate-500 text-xs">{volStr}</td>
                          <td className="px-4 py-3 text-right text-slate-500">{g.count}</td>
                        </tr>
                      );
                    })}
                    <tr className="bg-slate-100 font-semibold">
                      <td className="px-4 py-3 text-slate-800">Итого</td>
                      <td className="px-4 py-3 text-right text-slate-800">{fmt(data.summary.total_plan_qty)}</td>
                      <td className="px-4 py-3 text-right text-slate-800">{fmt(data.summary.total_actual_qty)}</td>
                      <td className={`px-4 py-3 text-right ${data.summary.execution_pct_qty >= 80 ? 'text-emerald-600' : data.summary.execution_pct_qty >= 50 ? 'text-amber-600' : 'text-red-600'}`}>{data.summary.execution_pct_qty}%</td>
                      <td className="px-4 py-3 text-right text-slate-800">{fmt(data.summary.total_plan_cost)} ₽</td>
                      <td className="px-4 py-3 text-right text-slate-800">{fmt(data.summary.total_actual_cost)} ₽</td>
                      <td className={`px-4 py-3 text-right ${data.summary.execution_pct_cost >= 80 ? 'text-emerald-600' : data.summary.execution_pct_cost >= 50 ? 'text-amber-600' : 'text-red-600'}`}>{data.summary.execution_pct_cost}%</td>
                      <td className="px-4 py-3 text-right text-slate-700 text-xs">
                        {data.summary.volume_by_uom?.map((v: any) => `${fmt(v.qty)} ${v.uom}`).join(' + ') || '—'}
                      </td>
                      <td className="px-4 py-3 text-right text-slate-800">{data.summary.total_rows}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};

const SummaryCard: React.FC<{
  label: string; value: string; icon: React.ElementType; color: string; bg: string;
}> = ({ label, value, icon: Icon, color, bg }) => (
  <div className="bg-white rounded-2xl border border-slate-200 p-4">
    <div className="flex items-center gap-2 mb-3">
      <div className={`w-8 h-8 rounded-lg ${bg} flex items-center justify-center`}>
        <Icon className={`w-4 h-4 ${color}`} />
      </div>
    </div>
    <div className="text-xl font-bold text-slate-800">{value}</div>
    <div className="text-xs text-slate-500 mt-0.5">{label}</div>
  </div>
);

export default ReportDashboard;