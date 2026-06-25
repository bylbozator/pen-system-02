import type { IFunctionInfo } from '@univerjs/engine-formula';

const I18N_KEY_PREFIX = 'sheets-formula.functionList';

/**
 * Строит map русских имён функций → английские (наоборот по сравнению с locale-файлом).
 */
function buildRuToEngMap(
  aliasLocale: { 'sheets-formula': { functionList: Record<string, { aliasFunctionName: string }> } },
): Map<string, string> {
  const map = new Map<string, string>();
  const aliases = aliasLocale['sheets-formula']['functionList'];
  for (const [engName, item] of Object.entries(aliases)) {
    const ruName = item.aliasFunctionName;
    if (ruName !== engName) map.set(ruName, engName);
  }
  return map;
}

/**
 * Создаёт функцию, конвертирующую русские имена функций в английские в строке формулы.
 * Возвращает ту же строку, если замен не было.
 */
export function createFormulaRusToEngConverter(
  aliasLocale: { 'sheets-formula': { functionList: Record<string, { aliasFunctionName: string }> } },
): (formula: string) => string {
  const ruToEng = buildRuToEngMap(aliasLocale);
  const sorted = [...ruToEng.entries()].sort(([a], [b]) => b.length - a.length);
  const pattern = sorted.map(([ru]) => ru.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
  const regex = new RegExp(`(?<=^|[=,(+\\-*/^<>&|\\s])(${pattern})(?=\\s*\\()`, 'g');
  const lookup = new Map(sorted);
  return (formula: string) => formula.replace(regex, (match) => lookup.get(match) || match);
}

/**
 * Регистрирует только executor-алиасы формул – чтобы `=СУММ()` выполнял SUM.
 * Должен вызываться ПОСЛЕ onReady-жизненного цикла Univer (после createWorkbook),
 * когда _functionExecutors уже заполнены.
 *
 * ВНИМАНИЕ: в Univer 0.25 executor-алиасы работают не для всех функций (баг).
 * Используйте `createFormulaRusToEngConverter` + command-interceptor как надёжную альтернативу.
 */
export function registerRussianExecutorAliases(
  functionService: any,
  aliasLocale: { 'sheets-formula': { functionList: Record<string, { aliasFunctionName: string }> } },
): void {
  const executors = functionService.getExecutors();
  const aliases = aliasLocale['sheets-formula']['functionList'];

  let registered = 0;

  for (const [engName, item] of Object.entries(aliases)) {
    const ruName = item.aliasFunctionName;
    if (ruName === engName) continue;
    const executor = executors.get(engName);
    if (executor) {
      executors.set(ruName, executor);
      registered++;
    }
  }
}

/**
 * Регистрирует IFunctionInfo с `aliasFunctionName` – чтобы подсказки/хинты
 * отображали русские имена.
 * Может вызываться в любое время после инициализации Univer.
 */
export function registerRussianDescriptions(
  descriptionService: any,
  aliasLocale: { 'sheets-formula': { functionList: Record<string, { aliasFunctionName: string }> } },
): void {
  const aliases = aliasLocale['sheets-formula']['functionList'];
  const descriptions = (descriptionService as any)._descriptions as Map<string, IFunctionInfo> | undefined;
  if (!descriptions) return;

  const batch: IFunctionInfo[] = [];

  descriptions.forEach((info) => {
    if (info.aliasFunctionName || !info.functionName) return;
    const engName = info.functionName;
    const aliasInfo = aliases[engName];
    if (!aliasInfo) return;
    if (aliasInfo.aliasFunctionName === engName) return;

    const ruKey = aliasInfo.aliasFunctionName.toUpperCase();
    if (descriptions.has(ruKey)) return;

    const clone: IFunctionInfo = {
      ...info,
      aliasFunctionName: `${I18N_KEY_PREFIX}.${engName}.aliasFunctionName`,
      functionParameter: info.functionParameter?.map((p) => ({ ...p })) ?? [],
    };
    batch.push(clone);
    descriptions.set(ruKey, clone);
  });

  if (batch.length > 0) {
    const method = (descriptionService as any)._registerDescriptions;
    if (typeof method === 'function') {
      method.call(descriptionService, batch);
      console.log(`[registerRussianDescriptions] Registered ${batch.length} Russian descriptions`);
    } else {
      console.warn('[registerRussianDescriptions] _registerDescriptions not found on descriptionService');
    }
  } else {
    console.log('[registerRussianDescriptions] No descriptions to register (batch empty)');
  }
}
