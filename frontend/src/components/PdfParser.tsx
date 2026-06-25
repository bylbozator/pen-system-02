import React, { useState, useRef } from 'react';
import { pdf } from '../api';
import toast from 'react-hot-toast';
import {
  FileText, Upload, Search, Table2, Loader2, Download, AlertCircle,
} from 'lucide-react';

interface KeywordMatch {
  keyword: string;
  position: number;
  context: string;
}

interface KeywordResult {
  keyword: string;
  count: number;
  matches: KeywordMatch[];
}

interface TableData {
  page: number;
  index: number;
  headers: string[];
  rows: string[][];
  row_count: number;
}

interface ParseResult {
  text: string;
  text_length: number;
  tables: TableData[];
  keyword_results: KeywordResult[];
}

const PdfParser: React.FC = () => {
  const [file, setFile] = useState<File | null>(null);
  const [keywords, setKeywords] = useState('');
  const [result, setResult] = useState<ParseResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'text' | 'tables' | 'keywords'>('tables');
  const fileRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f && f.type !== 'application/pdf') {
      toast.error('Пожалуйста, выберите PDF-файл');
      return;
    }
    setFile(f || null);
    setResult(null);
  };

  const handleParse = async () => {
    if (!file) {
      toast.error('Выберите PDF-файл');
      return;
    }
    setLoading(true);
    try {
      const resp = await pdf.parse(file, keywords || undefined);
      setResult(resp.data);
      toast.success('PDF успешно обработан');
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Ошибка обработки PDF');
    } finally {
      setLoading(false);
    }
  };

  const copyTableAsCsv = (table: TableData) => {
    const headers = table.headers.join('\t');
    const rows = table.rows.map(r => r.join('\t')).join('\n');
    const csv = headers + '\n' + rows;
    navigator.clipboard.writeText(csv).then(() => toast.success('Таблица скопирована'));
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center gap-3 mb-6">
        <FileText className="w-7 h-7 text-indigo-500" />
        <h1 className="text-2xl font-bold text-slate-800">Парсер PDF</h1>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 p-6 space-y-4">
        <div className="flex items-center gap-4">
          <div className="flex-1">
            <label className="block text-sm font-medium text-slate-700 mb-1">PDF-файл</label>
            <div
              onClick={() => fileRef.current?.click()}
              className="border-2 border-dashed border-slate-300 rounded-lg p-4 text-center cursor-pointer hover:border-indigo-400 transition-colors"
            >
              <input
                ref={fileRef}
                type="file"
                accept=".pdf,application/pdf"
                onChange={handleFileChange}
                className="hidden"
              />
              <Upload className="w-6 h-6 mx-auto text-slate-400 mb-1" />
              <p className="text-sm text-slate-500">
                {file ? file.name : 'Нажмите, чтобы выбрать PDF-файл'}
              </p>
            </div>
          </div>
          <div className="flex-1">
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Ключевые слова (через запятую)
            </label>
            <input
              type="text"
              value={keywords}
              onChange={e => setKeywords(e.target.value)}
              placeholder="напр.: Итого, Сумма, Поставщик"
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
            />
          </div>
        </div>

        <button
          onClick={handleParse}
          disabled={!file || loading}
          className="flex items-center gap-2 px-6 py-2.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm font-medium"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
          {loading ? 'Обработка...' : 'Извлечь данные'}
        </button>
      </div>

      {result && (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <div className="flex border-b border-slate-200">
            {[
              { key: 'tables', label: 'Таблицы', icon: Table2, count: result.tables.length },
              { key: 'text', label: 'Текст', icon: FileText, count: null },
              { key: 'keywords', label: 'Ключевые слова', icon: Search, count: result.keyword_results.length },
            ].map(tab => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key as any)}
                className={`flex items-center gap-2 px-5 py-3 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === tab.key
                    ? 'border-indigo-500 text-indigo-600'
                    : 'border-transparent text-slate-500 hover:text-slate-700'
                }`}
              >
                <tab.icon className="w-4 h-4" />
                {tab.label}
                {tab.count !== null && (
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    activeTab === tab.key ? 'bg-indigo-100 text-indigo-600' : 'bg-slate-100 text-slate-500'
                  }`}>
                    {tab.count}
                  </span>
                )}
              </button>
            ))}
          </div>

          <div className="p-6">
            {activeTab === 'text' && (
              <div>
                <p className="text-xs text-slate-400 mb-2">Всего символов: {result.text_length.toLocaleString()}</p>
                <pre className="text-sm text-slate-700 whitespace-pre-wrap max-h-[600px] overflow-y-auto bg-slate-50 rounded-lg p-4 border border-slate-200">
                  {result.text || '(текст не извлечён)'}
                </pre>
              </div>
            )}

            {activeTab === 'tables' && (
              <div className="space-y-6">
                {result.tables.length === 0 && (
                  <p className="text-sm text-slate-500">Таблицы не найдены</p>
                )}
                {result.tables.map((table, idx) => (
                  <div key={idx} className="border border-slate-200 rounded-lg overflow-hidden">
                    <div className="flex items-center justify-between bg-slate-50 px-4 py-2 border-b border-slate-200">
                      <span className="text-sm font-medium text-slate-700">
                        Таблица {idx + 1} (стр. {table.page}) — {table.row_count} строк
                      </span>
                      <button
                        onClick={() => copyTableAsCsv(table)}
                        className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800"
                      >
                        <Download className="w-3 h-3" />
                        Копировать
                      </button>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="bg-indigo-50">
                            {table.headers.map((h, i) => (
                              <th key={i} className="px-3 py-2 text-left text-xs font-semibold text-indigo-700 border-b border-indigo-200 whitespace-nowrap">
                                {h}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {table.rows.map((row, ri) => (
                            <tr key={ri} className={ri % 2 === 0 ? 'bg-white' : 'bg-slate-50'}>
                              {row.map((cell, ci) => (
                                <td key={ci} className="px-3 py-1.5 text-slate-700 border-b border-slate-100 whitespace-nowrap">
                                  {cell}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {activeTab === 'keywords' && (
              <div className="space-y-4">
                {result.keyword_results.length === 0 && (
                  <p className="text-sm text-slate-500">Ключевые слова не найдены</p>
                )}
                {result.keyword_results.map((kr, idx) => (
                  <div key={idx} className="border border-slate-200 rounded-lg overflow-hidden">
                    <div className="flex items-center gap-2 bg-amber-50 px-4 py-2 border-b border-amber-200">
                      <AlertCircle className="w-4 h-4 text-amber-600" />
                      <span className="text-sm font-medium text-amber-800">
                        «{kr.keyword}» — найдено {kr.count} раз
                      </span>
                    </div>
                    <div className="divide-y divide-slate-100">
                      {kr.matches.map((m, mi) => (
                        <div key={mi} className="px-4 py-2 text-sm text-slate-700">
                          <span className="font-medium text-indigo-600">{m.keyword}</span>
                          <span className="text-slate-400 ml-2">…{m.context}…</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default PdfParser;
