import { useState, useCallback, useEffect } from 'react';
import { datasets } from '../api';

export interface CondFormatRule {
  id: string; colId: string; type: 'greaterThan' | 'lessThan' | 'equals' | 'contains';
  value: string; color: string; bgColor: string; label: string;
}

export function useConditionalFormatting(datasetId: number | null) {
  const [rules, setRules] = useState<CondFormatRule[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!datasetId) return;
    setLoading(true);
    datasets.getCondFormatRules(datasetId)
      .then(res => {
        if (res.data && res.data.rules) setRules(res.data.rules);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [datasetId]);

  const saveRules = useCallback(async (newRules: CondFormatRule[]) => {
    if (!datasetId) return;
    setRules(newRules);
    try {
      await datasets.saveCondFormatRules(datasetId, newRules);
    } catch { /* ignore */ }
  }, [datasetId]);

  const addRule = useCallback(async (rule: CondFormatRule) => {
    const newRules = [...rules, rule];
    await saveRules(newRules);
  }, [rules, saveRules]);

  const removeRule = useCallback(async (id: string) => {
    const newRules = rules.filter(r => r.id !== id);
    await saveRules(newRules);
  }, [rules, saveRules]);

  return { rules, loading, addRule, removeRule, setRules: saveRules };
}
